"""Read-only IMAP poller for replies and bounces (docs/11 §4, docs/12 §5)."""

from __future__ import annotations

import email
import email.utils
import imaplib
import ssl
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from typing import Any

from app.config import get_settings
from app.infra.db import connect, init_db
from app.infra.events import record_event
from app.infra.redact import mask_email, redact_text
from app.mail.accounts import get_credentials, list_accounts, set_account_status
from app.mail.classify import classify_reply, redact_snippet
from app.mail.policy import get_setting, set_setting
from app.mail.verify import sanitize_error


FORBIDDEN_IMAP = frozenset({"STORE", "EXPUNGE", "COPY", "MOVE", "APPEND", "SELECT"})


class ReadOnlyIMAP:
    """Wrapper that only allows EXAMINE / SEARCH / FETCH BODY.PEEK / LIST / LOGIN / LOGOUT."""

    def __init__(self, imap: imaplib.IMAP4_SSL) -> None:
        self._imap = imap
        self.calls: list[str] = []

    def login(self, user: str, password: str):
        self.calls.append("LOGIN")
        return self._imap.login(user, password)

    def examine(self, mailbox: str = "INBOX"):
        self.calls.append("EXAMINE")
        return self._imap.select(mailbox, readonly=True)

    def search(self, charset, *criteria):
        self.calls.append("SEARCH")
        return self._imap.search(charset, *criteria)

    def fetch(self, message_set, message_parts):
        parts = message_parts if isinstance(message_parts, str) else str(message_parts)
        if "BODY.PEEK" not in parts.upper() and "RFC822.HEADER" not in parts.upper():
            # Force peek semantics
            message_parts = "(BODY.PEEK[]<0.65536>)"
        self.calls.append("FETCH")
        return self._imap.fetch(message_set, message_parts)

    def list(self, *args, **kwargs):
        self.calls.append("LIST")
        return self._imap.list(*args, **kwargs)

    def logout(self):
        self.calls.append("LOGOUT")
        return self._imap.logout()

    def __getattr__(self, name: str):
        upper = name.upper()
        if upper in FORBIDDEN_IMAP or upper.startswith("UID") and "STORE" in upper:
            raise RuntimeError(f"IMAP command forbidden: {name}")
        raise AttributeError(name)


def _decode_mime(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out)


def _extract_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(
                part.get("Content-Disposition") or ""
            ):
                payload = part.get_payload(decode=True) or b""
                return payload[:65536].decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload[:65536].decode(msg.get_content_charset() or "utf-8", errors="replace")


def _apply_classification(
    conn,
    *,
    lead_id: str,
    campaign_id: str,
    email_id: str | None,
    classification: str,
    from_masked: str,
    snippet: str,
    message_id: str | None,
    account_id: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    kind = "opt_out" if classification == "opt_out" else "reply"
    if classification == "bounce":
        kind = "reply"
    conn.execute(
        """
        INSERT INTO replies (
            lead_id, kind, received_at, message_id, from_masked,
            classification, snippet, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'imap')
        """,
        (lead_id, kind, now, message_id, from_masked, classification, snippet),
    )
    if classification in {"interested", "not_interested", "question", "other"}:
        conn.execute(
            "UPDATE scheduled_jobs SET status = 'cancelled' WHERE lead_id = ? AND status = 'pending'",
            (lead_id,),
        )
        conn.execute(
            "UPDATE leads SET status = 'replied', updated_at = ? WHERE id = ?",
            (now, lead_id),
        )
        record_event(
            campaign_id,
            "mail.reply_detected",
            "inbox",
            f"Reply detected ({classification}).",
            lead_id=lead_id,
            data={"classification": classification, "from_masked": from_masked},
        )
    elif classification == "opt_out":
        conn.execute(
            "UPDATE scheduled_jobs SET status = 'cancelled' WHERE lead_id = ? AND status = 'pending'",
            (lead_id,),
        )
        # suppress — need actual address from emails if possible
        row = conn.execute(
            "SELECT actual_recipient FROM emails WHERE lead_id = ? ORDER BY step LIMIT 1",
            (lead_id,),
        ).fetchone()
        # We only have masked in replies; suppress domain-less via lead id key if needed
        conn.execute(
            "UPDATE leads SET status = 'opted_out', updated_at = ? WHERE id = ?",
            (now, lead_id),
        )
        record_event(
            campaign_id,
            "mail.opt_out",
            "inbox",
            "Recipient opted out; follow-ups cancelled.",
            lead_id=lead_id,
            data={"from_masked": from_masked},
        )
    elif classification == "bounce":
        if email_id:
            conn.execute(
                "UPDATE emails SET delivery_status = 'bounced', status = 'failed' WHERE id = ?",
                (email_id,),
            )
        conn.execute(
            "UPDATE leads SET status = 'bounced', updated_at = ? WHERE id = ?",
            (now, lead_id),
        )
        record_event(
            campaign_id,
            "mail.bounce",
            "inbox",
            "Bounce detected.",
            lead_id=lead_id,
            data={"from_masked": from_masked},
        )
        # auto-pause on 3 bounces / 24h
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        n = conn.execute(
            """
            SELECT COUNT(*) AS n FROM emails
            WHERE mail_account_id = ? AND delivery_status = 'bounced' AND sent_at >= ?
            """,
            (account_id, since),
        ).fetchone()["n"]
        if n >= 3:
            set_account_status(
                account_id,
                "disabled",
                last_error="Auto-paused after 3 bounces in 24h.",
            )
            record_event(
                campaign_id,
                "mail.account_paused",
                "inbox",
                "Mail account auto-paused after repeated bounces.",
                data={"account_id": account_id},
            )
    elif classification == "out_of_office":
        record_event(
            campaign_id,
            "mail.out_of_office",
            "inbox",
            "Out-of-office reply ignored.",
            lead_id=lead_id,
            data={"from_masked": from_masked},
        )
    conn.commit()


def poll_account(account_id: str, *, db_path: str | None = None, imap_factory=None) -> int:
    """Poll one account. Returns number of new classifications applied."""
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    applied = 0
    try:
        account = conn.execute(
            "SELECT * FROM mail_accounts WHERE id = ? AND status = 'ok'",
            (account_id,),
        ).fetchone()
        if not account:
            return 0
        since = (datetime.now(timezone.utc) - timedelta(days=30)).date().strftime("%d-%b-%Y")
        sent = conn.execute(
            """
            SELECT e.id, e.message_id, e.lead_id, l.campaign_id
            FROM emails e
            JOIN leads l ON l.id = e.lead_id
            WHERE e.mail_account_id = ?
              AND e.send_mode IN ('gmail_test', 'gmail_live')
              AND e.message_id IS NOT NULL
              AND e.sent_at >= ?
            """,
            (
                account_id,
                (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
            ),
        ).fetchall()
        if not sent:
            return 0

        state_key = f"mail_imap_state:{account_id}"
        state = get_setting(conn, state_key, {}) or {}
        processed = set(state.get("uids") or [])

        user, password = get_credentials(account_id, db_path=path)
        ctx = ssl.create_default_context()
        if imap_factory:
            raw = imap_factory()
        else:
            raw = imaplib.IMAP4_SSL(
                account["imap_host"], int(account["imap_port"] or 993), ssl_context=ctx
            )
        imap = ReadOnlyIMAP(raw)
        try:
            imap.login(user, password)
            imap.examine("INBOX")
            for row in sent:
                mid = (row["message_id"] or "").strip()
                if not mid:
                    continue
                mid_bare = mid.strip("<>")
                for crit in (
                    f'HEADER In-Reply-To "{mid}"',
                    f'HEADER References "{mid}"',
                    f'HEADER In-Reply-To "<{mid_bare}>"',
                ):
                    typ, data = imap.search(None, crit)
                    if typ != "OK" or not data or not data[0]:
                        continue
                    for num in data[0].split():
                        uid = num.decode() if isinstance(num, bytes) else str(num)
                        if uid in processed:
                            continue
                        typ, fetched = imap.fetch(num, "(BODY.PEEK[]<0.65536>)")
                        if typ != "OK" or not fetched or not fetched[0]:
                            continue
                        raw_bytes = fetched[0][1]
                        if not isinstance(raw_bytes, (bytes, bytearray)):
                            continue
                        msg = email.message_from_bytes(bytes(raw_bytes[:65536]))
                        from_addr = _decode_mime(msg.get("From"))
                        subject = _decode_mime(msg.get("Subject"))
                        body = _extract_text(msg)
                        headers = {k: msg.get(k) for k in ("Auto-Submitted", "X-Autoreply", "Precedence")}
                        label = classify_reply(
                            subject=subject,
                            body=body,
                            from_addr=from_addr,
                            headers=headers,
                        )
                        snippet = redact_snippet(body)
                        from_masked = mask_email(
                            email.utils.parseaddr(from_addr)[1] or from_addr
                        )
                        _apply_classification(
                            conn,
                            lead_id=row["lead_id"],
                            campaign_id=row["campaign_id"],
                            email_id=row["id"],
                            classification=label,
                            from_masked=from_masked,
                            snippet=snippet,
                            message_id=msg.get("Message-ID"),
                            account_id=account_id,
                        )
                        processed.add(uid)
                        applied += 1
            # Bounces
            typ, data = imap.search(None, f'(SINCE {since} FROM "mailer-daemon")')
            if typ == "OK" and data and data[0]:
                for num in data[0].split():
                    uid = num.decode() if isinstance(num, bytes) else str(num)
                    if uid in processed:
                        continue
                    typ, fetched = imap.fetch(num, "(BODY.PEEK[]<0.65536>)")
                    if typ != "OK" or not fetched or not fetched[0]:
                        continue
                    raw_bytes = fetched[0][1]
                    if not isinstance(raw_bytes, (bytes, bytearray)):
                        continue
                    msg = email.message_from_bytes(bytes(raw_bytes[:65536]))
                    text = _extract_text(msg)
                    matched = None
                    for row in sent:
                        mid = (row["message_id"] or "").strip("<>")
                        if mid and mid in text:
                            matched = row
                            break
                    if not matched:
                        processed.add(uid)
                        continue
                    _apply_classification(
                        conn,
                        lead_id=matched["lead_id"],
                        campaign_id=matched["campaign_id"],
                        email_id=matched["id"],
                        classification="bounce",
                        from_masked="mailer-daemon",
                        snippet=redact_text(text)[:300],
                        message_id=msg.get("Message-ID"),
                        account_id=account_id,
                    )
                    processed.add(uid)
                    applied += 1
            imap.logout()
        finally:
            password = ""
        set_setting(conn, state_key, {"uids": list(processed)[-500:]})
        conn.commit()
        return applied
    except Exception as exc:  # noqa: BLE001
        # sanitize — do not store password
        msg = sanitize_error(exc, host="imap", port=993)
        set_account_status(account_id, "error", last_error=msg, db_path=path)
        return applied
    finally:
        conn.close()


def poll_all_accounts(*, db_path: str | None = None, imap_factory=None) -> int:
    total = 0
    for acc in list_accounts(db_path=db_path):
        if acc.get("status") != "ok":
            continue
        total += poll_account(acc["id"], db_path=db_path, imap_factory=imap_factory)
    return total
