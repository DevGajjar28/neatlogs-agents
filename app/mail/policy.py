"""Pre-send policy checks (docs/12 §3). Pure where possible; no transport calls."""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.infra.db import connect, init_db
from app.mail.compose import has_opt_out_line, strip_citations

ROLE_LIVE_BLOCK = frozenset({"info", "sales", "support"})
ROLE_ALWAYS_BLOCK = frozenset(
    {"noreply", "no-reply", "donotreply", "postmaster", "abuse", "mailer-daemon"}
)
URL_SHORTENERS = frozenset(
    {"bit.ly", "t.co", "goo.gl", "tinyurl.com", "ow.ly", "buff.ly", "rebrand.ly"}
)
URL_RE = re.compile(r"https?://([^\s/]+)", re.IGNORECASE)

HARD_MAX_DAILY = 100
HARD_MAX_DOMAIN = 10
HARD_MIN_GAP = 30


@dataclass
class PolicyContext:
    campaign_id: str
    lead_id: str
    step: int
    to_email: str
    subject: str
    body: str
    email_confidence: str
    allow_guessed: bool
    send_mode: str
    mail_account_id: str | None
    approved: bool = True
    verifier_passed: bool = True
    seller_domain: str = ""
    live_confirm_ok: bool = False
    intended_email: str | None = None  # before gmail_test rewrite
    db_path: str | None = None


@dataclass
class PolicyResult:
    ok: bool
    event: str | None = None
    reason: str = ""
    reschedule_at: str | None = None
    actual_recipient: str | None = None
    account: dict[str, Any] | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_recipient(email: str) -> str:
    return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()


def get_setting(conn, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value_json"])
    except Exception:  # noqa: BLE001
        return default


def set_setting(conn, key: str, value: Any) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value_json) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
        """,
        (key, json.dumps(value)),
    )


def max_send_mode_allowed() -> str:
    settings = get_settings()
    if not settings.demo_mode and settings.allow_live_sends:
        return "gmail_live"
    if settings.demo_mode:
        return "gmail_test"
    return "gmail_test"


def mode_allowed(send_mode: str, account: dict | None) -> bool:
    settings = get_settings()
    if send_mode == "sandbox":
        return True
    if send_mode == "gmail_live":
        return (
            (not settings.demo_mode)
            and settings.allow_live_sends
            and bool(account and account.get("live_enabled"))
        )
    if send_mode in {"gmail_drafts", "gmail_test"}:
        return True
    return False


def _fail(event: str, reason: str = "") -> PolicyResult:
    return PolicyResult(ok=False, event=event, reason=reason or event)


def check_all(ctx: PolicyContext) -> PolicyResult:
    settings = get_settings()
    path = ctx.db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        return _check_all_conn(conn, ctx, settings)
    finally:
        conn.close()


def _check_all_conn(conn, ctx: PolicyContext, settings) -> PolicyResult:
    # 1. Global kill switch
    if bool(get_setting(conn, "sending_paused", False)):
        return _fail("policy.sending_paused")

    account = None
    if ctx.mail_account_id:
        row = conn.execute(
            "SELECT * FROM mail_accounts WHERE id = ?", (ctx.mail_account_id,)
        ).fetchone()
        account = dict(row) if row else None

    # 2. Mode allowed
    if not mode_allowed(ctx.send_mode, account):
        return _fail("policy.mode_not_allowed", f"mode={ctx.send_mode}")

    # 3. Account for non-sandbox
    if ctx.send_mode != "sandbox":
        if not account:
            return _fail("policy.account_unavailable", "missing")
        if account.get("status") != "ok":
            return _fail("policy.account_unavailable", str(account.get("status")))

    # 4. Human approval + verifier
    if not ctx.approved or not ctx.verifier_passed:
        return _fail("policy.not_approved")

    # 5. Envelope
    to_email = (ctx.to_email or "").strip()
    if not to_email or "@" not in to_email or "," in to_email or ";" in to_email:
        return _fail("policy.bad_envelope")
    local, _, domain = to_email.lower().partition("@")
    if not domain:
        return _fail("policy.bad_envelope")

    # 6. Suppression / redacted
    if to_email.lower() == "redacted" or local == "redacted":
        return _fail("policy.suppressed", "redacted")
    sup = conn.execute(
        "SELECT reason FROM suppression WHERE email_or_domain IN (?, ?)",
        (to_email.lower(), domain),
    ).fetchone()
    if sup:
        return _fail("policy.suppressed", str(sup["reason"]))
    bounced = conn.execute(
        """
        SELECT 1 FROM emails
        WHERE delivery_status = 'bounced' AND lower(actual_recipient) = ?
        LIMIT 1
        """,
        (to_email.lower(),),
    ).fetchone()
    if bounced:
        return _fail("policy.suppressed", "prior_bounce")

    # 7. Guessed in live
    if ctx.send_mode == "gmail_live":
        if ctx.email_confidence != "verified" and not (
            ctx.email_confidence == "likely" and ctx.allow_guessed
        ):
            if ctx.email_confidence in {"guessed", "none", "likely"}:
                return _fail("policy.guessed_blocked")

    # 8. Role addresses
    if local in ROLE_ALWAYS_BLOCK or local.replace("-", "") in {"noreply", "donotreply"}:
        return _fail("policy.role_address", local)
    if ctx.send_mode == "gmail_live" and local in ROLE_LIVE_BLOCK:
        return _fail("policy.role_address", local)

    # Resolve actual recipient for gmail_test
    actual = to_email
    if ctx.send_mode == "gmail_test":
        tests = []
        if account:
            try:
                tests = json.loads(account.get("test_recipients_json") or "[]")
            except Exception:  # noqa: BLE001
                tests = []
        if not tests:
            return _fail("policy.test_recipient_missing")
        actual = str(tests[0]).strip()
        if not actual or "@" not in actual:
            return _fail("policy.test_recipient_missing")

    # 10–11 caps (per account for gmail modes; sandbox uses legacy global)
    policy_defaults = get_setting(conn, "mail_policy", {}) or {}
    daily_cap = int(
        (account or {}).get("daily_cap")
        or policy_defaults.get("daily_cap")
        or 25
    )
    daily_cap = min(max(1, daily_cap), HARD_MAX_DAILY)
    domain_cap = int(
        (account or {}).get("per_domain_daily_cap")
        or policy_defaults.get("per_domain_daily_cap")
        or 3
    )
    domain_cap = min(max(1, domain_cap), HARD_MAX_DOMAIN)
    min_gap = int(
        (account or {}).get("min_gap_seconds")
        or policy_defaults.get("min_gap_seconds")
        or 90
    )
    min_gap = max(HARD_MIN_GAP, min_gap)

    since = (_now() - timedelta(hours=24)).isoformat()
    if ctx.send_mode != "sandbox" and account:
        sent_24h = conn.execute(
            """
            SELECT COUNT(*) AS n FROM mail_send_log
            WHERE account_id = ? AND ts >= ?
            """,
            (account["id"], since),
        ).fetchone()["n"]
        if sent_24h >= daily_cap:
            return _fail("policy.cap_reached")
        domain_24h = conn.execute(
            """
            SELECT COUNT(*) AS n FROM mail_send_log
            WHERE account_id = ? AND domain = ? AND ts >= ?
            """,
            (account["id"], domain, since),
        ).fetchone()["n"]
        if domain_24h >= domain_cap:
            return _fail("policy.domain_cap_reached")

        last = conn.execute(
            """
            SELECT ts FROM mail_send_log
            WHERE account_id = ?
            ORDER BY ts DESC LIMIT 1
            """,
            (account["id"],),
        ).fetchone()
        if last:
            try:
                last_dt = datetime.fromisoformat(last["ts"])
            except ValueError:
                last_dt = _now() - timedelta(days=1)
            gap = min_gap + random.randint(0, 30)
            earliest = last_dt + timedelta(seconds=gap)
            if earliest > _now():
                return PolicyResult(
                    ok=False,
                    event="policy.rate_spaced",
                    reason="rate_spaced",
                    reschedule_at=earliest.isoformat(),
                    account=account,
                    actual_recipient=actual,
                )
    else:
        # sandbox: keep simple daily/domain caps for existing tests
        today = _now().strftime("%Y-%m-%d")
        daily = conn.execute(
            "SELECT COUNT(*) AS n FROM emails WHERE status = 'sent' AND sent_at LIKE ?",
            (f"{today}%",),
        ).fetchone()["n"]
        if daily >= 50:
            return _fail("policy.cap_reached", "daily_send_cap")

    # 13. Idempotency
    key = f"{ctx.lead_id}:{ctx.step}"
    existing = conn.execute(
        "SELECT status, delivery_status FROM emails WHERE idempotency_key = ?",
        (key,),
    ).fetchone()
    if existing:
        st = existing["status"]
        ds = existing["delivery_status"] if "delivery_status" in existing.keys() else None
        if st in {"sent", "drafted"} or ds in {"sent", "drafted", "unknown"}:
            return _fail("policy.duplicate")

    # 14. Follow-ups: lead not closed
    if ctx.step >= 2:
        reply = conn.execute(
            """
            SELECT kind, classification FROM replies
            WHERE lead_id = ?
            ORDER BY received_at DESC LIMIT 1
            """,
            (ctx.lead_id,),
        ).fetchone()
        if reply:
            return _fail("policy.lead_closed", str(reply["kind"]))

    # 15. Content — block any ev_ id in any wrapper (docs/13 + docs/12)
    from app.agents.evidence_refs import find_refs

    if find_refs(f"{ctx.subject}\n{ctx.body}"):
        return _fail("policy.content", "internal_ref")
    subject = strip_citations(ctx.subject)
    body = strip_citations(ctx.body)
    if find_refs(f"{subject}\n{body}"):
        return _fail("policy.content", "internal_ref")
    if not has_opt_out_line(body) and "unsubscribe" not in body.lower():
        # compose will add footer; require length limits here on raw
        pass
    if len(body) > 20_000 or len(subject) > 200:
        return _fail("policy.content", "length")
    for m in URL_RE.finditer(body):
        host = m.group(1).lower().split(":")[0]
        if host in URL_SHORTENERS:
            return _fail("policy.content", "shortener")
        if ctx.seller_domain and host != ctx.seller_domain.lower() and not host.endswith(
            "." + ctx.seller_domain.lower()
        ):
            # allow seller domain only when known
            if ctx.seller_domain:
                return _fail("policy.content", f"external_link:{host}")

    # 16. Live requirements
    if ctx.send_mode == "gmail_live":
        if not account or not (account.get("postal_address") or "").strip():
            return _fail("policy.live_requirements", "postal_address")
        if not ctx.live_confirm_ok:
            return _fail("policy.live_requirements", "confirm")

    # 17. Sending window (live only)
    if ctx.send_mode == "gmail_live":
        window = policy_defaults.get("sending_window") or {"start": 8, "end": 18}
        if isinstance(window, dict) and "timezone" in window and "timezone" not in policy_defaults:
            tz_name = str(window.get("timezone") or "Asia/Kolkata")
        else:
            tz_name = str(policy_defaults.get("timezone") or window.get("timezone") or "Asia/Kolkata")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            try:
                tz = ZoneInfo("Asia/Kolkata")
            except Exception:  # noqa: BLE001
                tz = timezone.utc
        local = _now().astimezone(tz)
        start_h = int(window.get("start", window.get("start_hour", 8)))
        end_h = int(window.get("end", window.get("end_hour", 18)))
        if local.weekday() >= 5 or not (start_h <= local.hour < end_h):
            # reschedule to next weekday window start
            days = 1
            candidate = local + timedelta(days=days)
            while candidate.weekday() >= 5:
                candidate += timedelta(days=1)
            candidate = candidate.replace(hour=start_h, minute=0, second=0, microsecond=0)
            if local.weekday() < 5 and local.hour < start_h:
                candidate = local.replace(hour=start_h, minute=0, second=0, microsecond=0)
            return PolicyResult(
                ok=False,
                event="policy.outside_window",
                reason="outside_window",
                reschedule_at=candidate.astimezone(timezone.utc).isoformat(),
                account=account,
                actual_recipient=actual,
            )

    # Demo sandbox smtp host lock
    if ctx.send_mode == "sandbox" and settings.demo_mode:
        host = (settings.smtp_host or "").strip().lower()
        if host not in {"localhost", "127.0.0.1", "mailpit", "::1"}:
            return _fail("policy.mode_not_allowed", f"demo_mode_requires_mailpit_host:{host}")

    return PolicyResult(
        ok=True,
        actual_recipient=actual,
        account=account,
        extras={"recipient_hash": _hash_recipient(actual), "domain": domain},
    )
