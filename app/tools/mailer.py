"""SMTP to the local catcher with policy checks before every send."""

from __future__ import annotations

import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from app.config import get_settings
from app.infra.audit import write_audit
from app.infra.db import connect, init_db

MAILPIT_HOSTS = frozenset({"localhost", "127.0.0.1", "mailpit", "::1"})
DAILY_SEND_CAP = 50
PER_DOMAIN_CAP = 10


class MailerError(Exception):
    pass


class PolicyDenied(MailerError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def lead_id_for(campaign_id: str, contact_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{campaign_id}:{contact_id}"))


def email_id_for(lead_id: str, step: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{lead_id}:{step}"))


def idempotency_key(lead_id: str, step: int) -> str:
    return f"{lead_id}:{step}"


def send(
    *,
    lead_id: str,
    step: int,
    subject: str,
    body: str,
    to_email: str,
    email_confidence: str = "likely",
    allow_guessed: bool = False,
    campaign_id: str = "",
    actor: str = "mailer",
    db_path: str | None = None,
    smtp_send: Any | None = None,
) -> dict[str, Any]:
    """Run all policy checks, then deliver. Only public send entrypoint."""
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        _check_demo_smtp(settings)
        if email_confidence == "guessed" and not allow_guessed:
            raise PolicyDenied("guessed_email_requires_approval")

        domain = to_email.split("@")[-1].lower() if "@" in to_email else ""
        _check_suppression(conn, to_email, domain)
        _check_caps(conn, domain=domain)

        key = idempotency_key(lead_id, step)
        existing = conn.execute(
            "SELECT id, status FROM emails WHERE idempotency_key = ?",
            (key,),
        ).fetchone()
        if existing and existing["status"] == "sent":
            return {"status": "skipped_idempotent", "idempotency_key": key}

        # Demo mode rewrites the recipient so nothing hits a real inbox.
        envelope_to = f"{lead_id}@sandbox.local" if settings.demo_mode else to_email
        eid = existing["id"] if existing else email_id_for(lead_id, step)
        now = datetime.now(timezone.utc).isoformat()

        if existing:
            conn.execute(
                """
                UPDATE emails
                SET subject = ?, body = ?, status = 'queued', sent_at = NULL
                WHERE idempotency_key = ?
                """,
                (subject, body, key),
            )
        else:
            conn.execute(
                """
                INSERT INTO emails (id, lead_id, step, subject, body, status, idempotency_key, sent_at)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, NULL)
                """,
                (eid, lead_id, step, subject, body, key),
            )
        conn.commit()

        try:
            _deliver(
                settings,
                envelope_to=envelope_to,
                subject=subject,
                body=body,
                smtp_send=smtp_send,
            )
        except Exception as exc:  # noqa: BLE001
            conn.execute(
                "UPDATE emails SET status = ? WHERE id = ?",
                ("failed", eid),
            )
            conn.commit()
            raise MailerError(f"smtp_failure:{exc}") from exc

        conn.execute(
            "UPDATE emails SET status = ?, sent_at = ? WHERE id = ?",
            ("sent", now, eid),
        )
        conn.execute(
            "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
            ("sent" if step == 1 else "followup_scheduled", now, lead_id),
        )
        conn.commit()
        write_audit(
            actor=actor,
            action="send",
            target=eid,
            details={
                "lead_id": lead_id,
                "step": step,
                "campaign_id": campaign_id,
                "envelope_to": envelope_to,
                "recipient_domain": domain,
                "idempotency_key": key,
            },
            db_path=path,
        )
        return {
            "status": "sent",
            "email_id": eid,
            "idempotency_key": key,
            "envelope_to": envelope_to,
            "sent_at": now,
        }
    finally:
        conn.close()


def _check_demo_smtp(settings) -> None:
    if not settings.demo_mode:
        return
    host = (settings.smtp_host or "").strip().lower()
    if host not in MAILPIT_HOSTS:
        raise PolicyDenied(f"demo_mode_requires_mailpit_host:{host}")


def _check_suppression(conn, email: str, domain: str) -> None:
    row = conn.execute(
        "SELECT reason FROM suppression WHERE email_or_domain IN (?, ?)",
        (email.lower(), domain),
    ).fetchone()
    if row:
        raise PolicyDenied(f"suppressed:{row['reason']}")


def _check_caps(conn, domain: str) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = conn.execute(
        """
        SELECT COUNT(*) AS n FROM emails
        WHERE status = 'sent' AND sent_at LIKE ?
        """,
        (f"{today}%",),
    ).fetchone()["n"]
    if daily >= DAILY_SEND_CAP:
        raise PolicyDenied("daily_send_cap")

    if domain:
        # Count prior sends to this prospect domain via audit trail (demo envelopes share sandbox.local).
        rows = conn.execute(
            """
            SELECT details_json FROM audit
            WHERE action = 'send' AND ts LIKE ?
            """,
            (f"{today}%",),
        ).fetchall()
        domain_count = 0
        for row in rows:
            try:
                import json

                details = json.loads(row["details_json"] or "{}")
            except Exception:  # noqa: BLE001
                continue
            if str(details.get("recipient_domain") or "").lower() == domain:
                domain_count += 1
        if domain_count >= PER_DOMAIN_CAP:
            raise PolicyDenied(f"per_domain_cap:{domain}")


def _deliver(settings, *, envelope_to: str, subject: str, body: str, smtp_send) -> None:
    msg = EmailMessage()
    msg["From"] = settings.from_email
    msg["To"] = envelope_to
    msg["Subject"] = subject
    msg.set_content(body)

    if smtp_send is not None:
        smtp_send(settings.smtp_host, settings.smtp_port, msg)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.send_message(msg)
