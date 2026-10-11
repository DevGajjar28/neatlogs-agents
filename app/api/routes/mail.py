"""Mail accounts, sending kill switch, policies, outbox."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    MailAccountCreateIn,
    MailAccountOut,
    MailAccountPatchIn,
    MailActivityOut,
    MailPoliciesOut,
    MailPoliciesPatchIn,
    MailPresetOut,
    MeetingProposalOut,
    MeetingSlotOut,
    OutboxRow,
    PolicyEventOut,
    ReplyDraftDecideIn,
    ReplyDraftOut,
    SendingPausedIn,
    SendingPausedOut,
    VerifyOut,
)
from app.agents import reply_decision as reply_decision_mod
from app.config import get_settings
from app.infra.audit import write_audit
from app.infra.db import connect, init_db
from app.infra.redact import mask_email
from app.mail import accounts as mail_accounts
from app.mail.crypto import SecretKeyMissing
from app.mail.policy import (
    HARD_MAX_DAILY,
    HARD_MAX_DOMAIN,
    HARD_MIN_GAP,
    get_setting,
    max_send_mode_allowed,
    set_setting,
)
from app.mail.verify import verify_account
from app.tools.mailer import MailerError, PolicyDenied, send_self_test

router = APIRouter(tags=["mail"])

POLICY_RULES: list[dict[str, Any]] = [
    {
        "id": "sending_paused",
        "name": "Global kill switch",
        "protects": "Stops all transports immediately when paused.",
        "event": "policy.sending_paused",
        "editable": False,
        "always_on": False,
        "value_key": "sending_paused",
    },
    {
        "id": "mode_not_allowed",
        "name": "Send mode gate",
        "protects": "Blocks live/test modes the environment or account forbids.",
        "event": "policy.mode_not_allowed",
        "editable": False,
        "always_on": True,
    },
    {
        "id": "account_unavailable",
        "name": "Account health",
        "protects": "Requires a connected, non-disabled mail account.",
        "event": "policy.account_unavailable",
        "editable": False,
        "always_on": True,
    },
    {
        "id": "not_approved",
        "name": "Human approval + verifier",
        "protects": "Only approved, verifier-passed emails can leave.",
        "event": "policy.not_approved",
        "editable": False,
        "always_on": True,
    },
    {
        "id": "bad_envelope",
        "name": "Envelope shape",
        "protects": "Exactly one To; no CC/BCC/attachments.",
        "event": "policy.bad_envelope",
        "editable": False,
        "always_on": True,
    },
    {
        "id": "suppressed",
        "name": "Suppression list",
        "protects": "Never email suppressed, bounced, or redacted addresses.",
        "event": "policy.suppressed",
        "editable": False,
        "always_on": True,
    },
    {
        "id": "guessed_blocked",
        "name": "No guessed in live",
        "protects": "Live mode requires verified confidence.",
        "event": "policy.guessed_blocked",
        "editable": False,
        "always_on": True,
    },
    {
        "id": "role_address",
        "name": "Role addresses",
        "protects": "Blocks noreply and common role inboxes in live.",
        "event": "policy.role_address",
        "editable": False,
        "always_on": True,
    },
    {
        "id": "test_recipient_missing",
        "name": "Test recipient allowlist",
        "protects": "Gmail test only goes to allowlisted inboxes.",
        "event": "policy.test_recipient_missing",
        "editable": True,
        "always_on": False,
        "value_key": "default_test_recipients",
    },
    {
        "id": "daily_cap",
        "name": "Daily send cap",
        "protects": "Rolling 24h per-account volume limit.",
        "event": "policy.cap_reached",
        "editable": True,
        "always_on": False,
        "value_key": "daily_cap",
        "hard_max": HARD_MAX_DAILY,
        "default": 25,
    },
    {
        "id": "per_domain_cap",
        "name": "Per-domain cap",
        "protects": "Rolling 24h cap per recipient domain.",
        "event": "policy.domain_cap_reached",
        "editable": True,
        "always_on": False,
        "value_key": "per_domain_daily_cap",
        "hard_max": HARD_MAX_DOMAIN,
        "default": 3,
    },
    {
        "id": "min_gap_seconds",
        "name": "Send gap",
        "protects": "Minimum seconds between sends on an account.",
        "event": "policy.rate_spaced",
        "editable": True,
        "always_on": False,
        "value_key": "min_gap_seconds",
        "hard_min": HARD_MIN_GAP,
        "default": 90,
    },
    {
        "id": "sending_window",
        "name": "Sending window",
        "protects": "Live sends only inside weekday hours in account timezone.",
        "event": "policy.outside_window",
        "editable": True,
        "always_on": False,
        "value_key": "sending_window",
    },
    {
        "id": "duplicate",
        "name": "Idempotency",
        "protects": "No second delivery for the same lead step.",
        "event": "policy.duplicate",
        "editable": False,
        "always_on": True,
    },
    {
        "id": "lead_closed",
        "name": "Lead closed",
        "protects": "Stops follow-ups after reply, opt-out, or bounce.",
        "event": "policy.lead_closed",
        "editable": False,
        "always_on": True,
    },
    {
        "id": "content",
        "name": "Content policy",
        "protects": "Citations stripped; opt-out present; no foreign links.",
        "event": "policy.content",
        "editable": False,
        "always_on": True,
    },
    {
        "id": "live_requirements",
        "name": "Live requirements",
        "protects": "Postal address and typed confirmation for live.",
        "event": "policy.live_requirements",
        "editable": False,
        "always_on": True,
    },
    {
        "id": "encrypted_credentials",
        "name": "Encrypted credentials",
        "protects": "App passwords stored with SIGNALSDR_SECRET_KEY only.",
        "event": None,
        "editable": False,
        "always_on": True,
    },
    {
        "id": "read_only_inbox",
        "name": "Read-only inbox",
        "protects": "IMAP EXAMINE + BODY.PEEK only; never mutate mail.",
        "event": None,
        "editable": False,
        "always_on": True,
    },
]


def _public_account(row: dict[str, Any]) -> MailAccountOut:
    agent_on = row.get("agent_enabled")
    if agent_on is None:
        agent_on = 1
    return MailAccountOut(
        id=row["id"],
        label=row.get("label") or "",
        provider=row.get("provider") or "gmail",
        email=row.get("email") or "",
        display_name=row.get("display_name") or "",
        username=row.get("username") or "",
        smtp_host=row.get("smtp_host") or "",
        smtp_port=int(row.get("smtp_port") or 587),
        smtp_security=row.get("smtp_security") or "starttls",
        imap_host=row.get("imap_host") or "",
        imap_port=int(row.get("imap_port") or 993),
        status=row.get("status") or "unverified",
        last_verified_at=row.get("last_verified_at"),
        last_error=row.get("last_error"),
        daily_cap=int(row.get("daily_cap") or 25),
        per_domain_daily_cap=int(row.get("per_domain_daily_cap") or 3),
        min_gap_seconds=int(row.get("min_gap_seconds") or 90),
        test_recipients=list(row.get("test_recipients") or []),
        live_enabled=bool(row.get("live_enabled")),
        signature=row.get("signature") or "",
        postal_address=row.get("postal_address") or "",
        drafts_folder=row.get("drafts_folder"),
        is_default=bool(row.get("is_default")),
        has_password=bool(row.get("has_password")),
        agent_enabled=bool(int(agent_on)),
        sent_24h=int(row.get("sent_24h") or 0),
        cap=int(row.get("cap") or row.get("daily_cap") or 25),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _draft_out(d: dict[str, Any]) -> ReplyDraftOut:
    meeting = None
    raw_m = d.get("meeting")
    if isinstance(raw_m, dict) and raw_m.get("id"):
        slots = []
        for s in raw_m.get("slots") or []:
            if isinstance(s, dict):
                slots.append(
                    MeetingSlotOut(
                        label=str(s.get("label") or ""),
                        start_iso=s.get("start_iso"),
                    )
                )
        meeting = MeetingProposalOut(
            id=str(raw_m["id"]),
            slots=slots,
            booking_link=raw_m.get("booking_link"),
            status=str(raw_m.get("status") or "proposed"),
            notes=raw_m.get("notes"),
            calendar_event_id=raw_m.get("calendar_event_id"),
            calendar_html_link=raw_m.get("calendar_html_link"),
        )
    return ReplyDraftOut(
        id=d["id"],
        lead_id=d["lead_id"],
        campaign_id=d["campaign_id"],
        classification=d.get("classification") or "other",
        subject=d.get("subject") or "",
        body=d.get("body") or "",
        status=d.get("status") or "pending",
        in_reply_to=d.get("in_reply_to"),
        meeting=meeting,
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
    )


@router.get("/mail-accounts", response_model=list[MailAccountOut])
def list_mail_accounts() -> list[MailAccountOut]:
    return [_public_account(a) for a in mail_accounts.list_accounts()]


@router.get("/mail-accounts/presets", response_model=list[MailPresetOut])
def mail_presets() -> list[MailPresetOut]:
    out = []
    for key, preset in mail_accounts.PRESETS.items():
        out.append(
            MailPresetOut(
                id=key,
                label={"gmail": "Gmail", "workspace": "Google Workspace", "custom": "Other SMTP"}.get(
                    key, key
                ),
                **{k: v for k, v in preset.items() if k != "provider"},
                provider=preset["provider"],
            )
        )
    return out


@router.post("/mail-accounts", response_model=MailAccountOut, status_code=201)
def create_mail_account(body: MailAccountCreateIn) -> MailAccountOut:
    data = body.model_dump(exclude={"password"})
    try:
        aid = mail_accounts.create_account(data, password=body.password)
    except SecretKeyMissing as exc:
        raise HTTPException(
            400,
            detail="SIGNALSDR_SECRET_KEY is not set. Run: python cli.py gen-key",
        ) from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    account = mail_accounts.get_account(aid)
    assert account
    result = verify_account(aid, account)
    account = mail_accounts.get_account(aid)
    assert account
    # refresh list fields
    listed = next((a for a in mail_accounts.list_accounts() if a["id"] == aid), account)
    write_audit(
        actor="api",
        action="mail_account_create",
        target=aid,
        details={"email": account["email"], "verify_ok": result.get("ok")},
    )
    return _public_account(listed)


@router.patch("/mail-accounts/{account_id}", response_model=MailAccountOut)
def patch_mail_account(account_id: str, body: MailAccountPatchIn) -> MailAccountOut:
    data = body.model_dump(exclude_unset=True, exclude={"password"})
    password = body.password
    try:
        mail_accounts.update_account(account_id, data, password=password)
    except KeyError as exc:
        raise HTTPException(404, detail="Mail account not found") from exc
    except SecretKeyMissing as exc:
        raise HTTPException(
            400,
            detail="SIGNALSDR_SECRET_KEY is not set. Run: python cli.py gen-key",
        ) from exc
    listed = next((a for a in mail_accounts.list_accounts() if a["id"] == account_id), None)
    if not listed:
        raise HTTPException(404, detail="Mail account not found")
    return _public_account(listed)


@router.post("/mail-accounts/{account_id}/verify", response_model=VerifyOut)
def verify_mail_account(account_id: str) -> VerifyOut:
    account = mail_accounts.get_account(account_id)
    if not account:
        raise HTTPException(404, detail="Mail account not found")
    result = verify_account(account_id, account)
    return VerifyOut(
        ok=bool(result.get("ok")),
        detail=str(result.get("detail") or ""),
        drafts_folder=result.get("drafts_folder"),
    )


@router.post("/mail-accounts/{account_id}/test-send")
def test_send_mail_account(account_id: str) -> dict[str, Any]:
    account = mail_accounts.get_account(account_id)
    if not account:
        raise HTTPException(404, detail="Mail account not found")
    try:
        out = send_self_test(account_id)
    except PolicyDenied as exc:
        raise HTTPException(409, detail=exc.reason) from exc
    except MailerError as exc:
        raise HTTPException(502, detail=str(exc)) from exc
    except SecretKeyMissing as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    write_audit(
        actor="api",
        action="mail_test_send",
        target=account_id,
        details={"status": out.get("status")},
    )
    return {"ok": out.get("status") in {"sent", "drafted"}, "result": out}


@router.post("/mail-accounts/{account_id}/disable", response_model=MailAccountOut)
def disable_mail_account(account_id: str) -> MailAccountOut:
    if not mail_accounts.get_account(account_id):
        raise HTTPException(404, detail="Mail account not found")
    mail_accounts.set_account_status(account_id, "disabled", last_error="Disabled by user")
    listed = next(a for a in mail_accounts.list_accounts() if a["id"] == account_id)
    return _public_account(listed)


@router.post("/mail-accounts/{account_id}/disconnect", response_model=MailAccountOut)
def disconnect_mail_agent(account_id: str) -> MailAccountOut:
    """Disable inbox agent, wipe app password, cancel pending reply drafts."""
    if not mail_accounts.get_account(account_id):
        raise HTTPException(404, detail="Mail account not found")
    try:
        mail_accounts.disconnect_agent(account_id)
    except KeyError as exc:
        raise HTTPException(404, detail="Mail account not found") from exc
    write_audit(
        actor="api",
        action="mail_agent_disconnect",
        target=account_id,
        details={"event": "mail.agent_disconnected"},
    )
    listed = next(a for a in mail_accounts.list_accounts() if a["id"] == account_id)
    return _public_account(listed)


@router.get("/leads/{lead_id}/reply-draft", response_model=ReplyDraftOut | None)
def get_lead_reply_draft(lead_id: str) -> ReplyDraftOut | None:
    draft = reply_decision_mod.get_pending_draft_for_lead(lead_id)
    if not draft:
        return None
    return _draft_out(draft)


@router.post("/reply-drafts/{draft_id}/decide")
def decide_reply_draft(draft_id: str, body: ReplyDraftDecideIn) -> dict[str, Any]:
    if body.action == "reject":
        try:
            return reply_decision_mod.reject_reply_draft(draft_id)
        except KeyError as exc:
            raise HTTPException(404, detail="Reply draft not found") from exc
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc

    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT * FROM reply_drafts WHERE id = ?", (draft_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, detail="Reply draft not found")
        lead = conn.execute(
            "SELECT * FROM leads WHERE id = ?", (row["lead_id"],)
        ).fetchone()
        if not lead:
            raise HTTPException(404, detail="Lead not found")
        contact_id = lead["contact_id"]
        campaign_id = row["campaign_id"]
    finally:
        conn.close()

    from app.api import state_reader

    contacts = {
        c["id"]: c
        for c in state_reader.contacts(campaign_id)
        if isinstance(c, dict) and c.get("id")
    }
    contact = contacts.get(contact_id or "") or {}
    to_email = str(contact.get("email") or "").strip()
    if not to_email:
        raise HTTPException(422, detail="Lead has no contact email to reply to")

    try:
        return reply_decision_mod.approve_and_send_reply_draft(
            draft_id,
            subject=body.subject,
            body=body.body,
            selected_slot_label=body.selected_slot_label,
            to_email=to_email,
        )
    except KeyError as exc:
        raise HTTPException(404, detail="Reply draft not found") from exc
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except PolicyDenied as exc:
        raise HTTPException(409, detail=exc.reason) from exc
    except MailerError as exc:
        raise HTTPException(502, detail=str(exc)) from exc


@router.post("/mail-accounts/{account_id}/enable", response_model=MailAccountOut)
def enable_mail_account(account_id: str) -> MailAccountOut:
    account = mail_accounts.get_account(account_id)
    if not account:
        raise HTTPException(404, detail="Mail account not found")
    status = "ok" if account.get("last_verified_at") else "unverified"
    mail_accounts.set_account_status(account_id, status, last_error=None)
    listed = next(a for a in mail_accounts.list_accounts() if a["id"] == account_id)
    return _public_account(listed)


@router.delete("/mail-accounts/{account_id}", status_code=204)
def delete_mail_account(account_id: str) -> None:
    if not mail_accounts.get_account(account_id):
        raise HTTPException(404, detail="Mail account not found")
    try:
        mail_accounts.delete_account(account_id)
    except RuntimeError as exc:
        if str(exc) == "account_in_use":
            raise HTTPException(
                409, detail="Account is used by an active campaign"
            ) from exc
        raise
    write_audit(actor="api", action="mail_account_delete", target=account_id, details={})


@router.get("/mail-accounts/{account_id}/activity", response_model=list[MailActivityOut])
def mail_account_activity(account_id: str) -> list[MailActivityOut]:
    if not mail_accounts.get_account(account_id):
        raise HTTPException(404, detail="Mail account not found")
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            """
            SELECT e.id, e.sent_at AS ts, e.delivery_status AS kind, e.send_mode,
                   e.actual_recipient, e.message_id, e.lead_id
            FROM emails e
            WHERE e.mail_account_id = ?
            ORDER BY COALESCE(e.sent_at, '') DESC
            LIMIT 100
            """,
            (account_id,),
        ).fetchall()
        out: list[MailActivityOut] = []
        for r in rows:
            out.append(
                MailActivityOut(
                    id=str(r["id"]),
                    ts=r["ts"],
                    kind=r["kind"] or "unknown",
                    send_mode=r["send_mode"],
                    recipient_masked=r["actual_recipient"],
                    message_id=r["message_id"],
                    lead_id=r["lead_id"],
                )
            )
        replies = conn.execute(
            """
            SELECT r.id, r.received_at AS ts, r.classification AS kind,
                   r.from_masked, r.message_id, r.lead_id
            FROM replies r
            JOIN emails e ON e.lead_id = r.lead_id
            WHERE e.mail_account_id = ?
            GROUP BY r.id
            ORDER BY COALESCE(r.received_at, '') DESC
            LIMIT 50
            """,
            (account_id,),
        ).fetchall()
        for r in replies:
            out.append(
                MailActivityOut(
                    id=f"reply-{r['id']}",
                    ts=r["ts"],
                    kind=r["kind"] or "reply",
                    send_mode=None,
                    recipient_masked=r["from_masked"],
                    message_id=r["message_id"],
                    lead_id=r["lead_id"],
                )
            )
        out.sort(key=lambda x: x.ts or "", reverse=True)
        return out[:100]
    finally:
        conn.close()


@router.put("/settings/sending", response_model=SendingPausedOut)
def put_sending(body: SendingPausedIn) -> SendingPausedOut:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        set_setting(conn, "sending_paused", bool(body.sending_paused))
        conn.commit()
        write_audit(
            actor="api",
            action="sending_paused" if body.sending_paused else "sending_resumed",
            target="settings",
            details={"sending_paused": body.sending_paused},
        )
        return SendingPausedOut(sending_paused=bool(get_setting(conn, "sending_paused", False)))
    finally:
        conn.close()


def _default_mail_policy() -> dict[str, Any]:
    return {
        "daily_cap": 25,
        "per_domain_daily_cap": 3,
        "min_gap_seconds": 90,
        "sending_window": {
            "start_hour": 8,
            "end_hour": 18,
            "timezone": "Asia/Kolkata",
            "weekdays_only": True,
        },
        "default_test_recipients": [],
    }


@router.get("/settings/policies", response_model=MailPoliciesOut)
def get_policies() -> MailPoliciesOut:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        policy = dict(_default_mail_policy())
        stored = get_setting(conn, "mail_policy", {}) or {}
        if isinstance(stored, dict):
            policy.update(stored)
        paused = bool(get_setting(conn, "sending_paused", False))
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        rules_out = []
        for rule in POLICY_RULES:
            blocks = 0
            if rule.get("event"):
                blocks = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM events
                    WHERE type = ? AND ts >= ?
                    """,
                    (rule["event"], since),
                ).fetchone()["n"]
            value: Any = None
            if rule["id"] == "sending_paused":
                value = paused
            elif rule.get("value_key"):
                value = policy.get(rule["value_key"], rule.get("default"))
            rules_out.append(
                {
                    "id": rule["id"],
                    "name": rule["name"],
                    "protects": rule["protects"],
                    "editable": rule["editable"],
                    "always_on": rule.get("always_on", False),
                    "value": value,
                    "hard_max": rule.get("hard_max"),
                    "hard_min": rule.get("hard_min"),
                    "blocks_24h": int(blocks),
                    "event": rule.get("event"),
                }
            )
        return MailPoliciesOut(
            sending_paused=paused,
            max_send_mode=max_send_mode_allowed(),
            demo_mode=settings.demo_mode,
            allow_live_sends=settings.allow_live_sends,
            values={
                "daily_cap": int(policy.get("daily_cap") or 25),
                "per_domain_daily_cap": int(policy.get("per_domain_daily_cap") or 3),
                "min_gap_seconds": int(policy.get("min_gap_seconds") or 90),
                "sending_window": policy.get("sending_window") or _default_mail_policy()["sending_window"],
                "default_test_recipients": list(policy.get("default_test_recipients") or []),
            },
            rules=rules_out,
        )
    finally:
        conn.close()


@router.patch("/settings/policies", response_model=MailPoliciesOut)
def patch_policies(body: MailPoliciesPatchIn) -> MailPoliciesOut:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        policy = dict(_default_mail_policy())
        stored = get_setting(conn, "mail_policy", {}) or {}
        if isinstance(stored, dict):
            policy.update(stored)
        data = body.model_dump(exclude_unset=True)
        if "daily_cap" in data and data["daily_cap"] is not None:
            policy["daily_cap"] = min(HARD_MAX_DAILY, max(1, int(data["daily_cap"])))
        if "per_domain_daily_cap" in data and data["per_domain_daily_cap"] is not None:
            policy["per_domain_daily_cap"] = min(
                HARD_MAX_DOMAIN, max(1, int(data["per_domain_daily_cap"]))
            )
        if "min_gap_seconds" in data and data["min_gap_seconds"] is not None:
            policy["min_gap_seconds"] = max(HARD_MIN_GAP, int(data["min_gap_seconds"]))
        if "sending_window" in data and data["sending_window"] is not None:
            sw = dict(policy.get("sending_window") or {})
            sw.update(data["sending_window"])
            policy["sending_window"] = sw
        if "default_test_recipients" in data and data["default_test_recipients"] is not None:
            policy["default_test_recipients"] = list(data["default_test_recipients"])
        set_setting(conn, "mail_policy", policy)
        conn.commit()
    finally:
        conn.close()
    return get_policies()


@router.get("/settings/policies/{rule}/events", response_model=list[PolicyEventOut])
def policy_rule_events(rule: str) -> list[PolicyEventOut]:
    match = next((r for r in POLICY_RULES if r["id"] == rule), None)
    if not match or not match.get("event"):
        raise HTTPException(404, detail="Unknown policy rule")
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        rows = conn.execute(
            """
            SELECT id, ts, type, message, campaign_id, lead_id
            FROM events
            WHERE type = ? AND ts >= ?
            ORDER BY ts DESC
            LIMIT 100
            """,
            (match["event"], since),
        ).fetchall()
        return [
            PolicyEventOut(
                id=int(r["id"]),
                ts=r["ts"],
                type=r["type"],
                message=r["message"] or "",
                campaign_id=r["campaign_id"],
                lead_id=r["lead_id"],
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/outbox", response_model=list[OutboxRow])
def list_outbox() -> list[OutboxRow]:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            """
            SELECT e.id, e.lead_id, e.step, e.subject, e.status, e.delivery_status,
                   e.send_mode, e.message_id, e.actual_recipient, e.sent_at,
                   e.mail_account_id, a.label AS account_label, a.email AS account_email,
                   l.status AS lead_status,
                   (
                     SELECT j.run_at FROM scheduled_jobs j
                     WHERE j.email_id = e.id OR (j.lead_id = e.lead_id AND e.step > 1)
                     ORDER BY j.run_at DESC LIMIT 1
                   ) AS scheduled_at
            FROM emails e
            LEFT JOIN mail_accounts a ON a.id = e.mail_account_id
            LEFT JOIN leads l ON l.id = e.lead_id
            ORDER BY COALESCE(e.sent_at, e.id) DESC
            LIMIT 200
            """
        ).fetchall()
        out: list[OutboxRow] = []
        for r in rows:
            mode = r["send_mode"] or "sandbox"
            delivery = r["delivery_status"] or r["status"] or "queued"
            lead_status = (r["lead_status"] or "").lower()
            if lead_status in {"replied", "opted_out", "bounced"}:
                ui_status = {
                    "replied": "Replied",
                    "opted_out": "Opted out",
                    "bounced": "Bounced",
                }[lead_status]
            elif delivery == "drafted":
                ui_status = "Drafted in Gmail"
            elif delivery == "unknown":
                ui_status = "Unknown — check Gmail"
            elif delivery == "sent":
                ui_status = "Sent"
            elif r["status"] == "queued" or delivery == "queued":
                ui_status = "Scheduled"
            else:
                ui_status = delivery.title()
            gmail_url = None
            if r["message_id"] and r["account_email"] and mode != "sandbox":
                mid = str(r["message_id"]).strip("<>")
                gmail_url = (
                    f"https://mail.google.com/mail/u/{r['account_email']}/"
                    f"#search/rfc822msgid:{mid}"
                )
            out.append(
                OutboxRow(
                    id=str(r["id"]),
                    lead_id=r["lead_id"],
                    step=int(r["step"] or 1),
                    subject=r["subject"] or "",
                    from_label=r["account_label"] or r["account_email"] or "Sandbox",
                    from_email=r["account_email"],
                    send_mode=mode,
                    delivery_status=delivery,
                    ui_status=ui_status,
                    message_id=r["message_id"],
                    actual_recipient_masked=r["actual_recipient"],
                    sent_at=r["sent_at"],
                    scheduled_at=r["scheduled_at"],
                    open_in_gmail_url=gmail_url,
                )
            )
        return out
    finally:
        conn.close()
