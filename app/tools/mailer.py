"""Sole send entrypoint: policy → compose → transport. Callers stay on send()."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.infra.audit import write_audit
from app.infra.db import connect, init_db
from app.infra.events import record_event
from app.infra.redact import mask_email
from app.mail.compose import compose
from app.mail.policy import PolicyContext, check_all, get_setting
from app.mail.transports import pick_transport


class MailerError(Exception):
    pass


class PolicyDenied(MailerError):
    def __init__(self, reason: str, event: str | None = None) -> None:
        self.reason = reason
        self.event = event or reason
        super().__init__(reason)


def lead_id_for(campaign_id: str, contact_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{campaign_id}:{contact_id}"))


def email_id_for(lead_id: str, step: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{lead_id}:{step}"))


def idempotency_key(lead_id: str, step: int) -> str:
    return f"{lead_id}:{step}"


def _load_campaign_mail(conn, campaign_id: str) -> tuple[str, str | None, str, bool]:
    """Return send_mode, mail_account_id, seller_domain, live_confirm_ok."""
    if not campaign_id:
        return "sandbox", None, "", False
    row = conn.execute(
        "SELECT options_json, seller_domain FROM campaigns WHERE id = ?",
        (campaign_id,),
    ).fetchone()
    if not row:
        return "sandbox", None, "", False
    try:
        opts = json.loads(row["options_json"] or "{}")
    except Exception:  # noqa: BLE001
        opts = {}
    mode = str(opts.get("send_mode") or "sandbox")
    acc = opts.get("mail_account_id")
    return mode, (str(acc) if acc else None), str(row["seller_domain"] or ""), bool(
        opts.get("live_confirm_ok")
    )


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
    approved: bool = True,
    verifier_passed: bool = True,
) -> dict[str, Any]:
    """Run all policy checks, then deliver. Only public send entrypoint."""
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        send_mode, mail_account_id, seller_domain, live_confirm_ok = _load_campaign_mail(
            conn, campaign_id
        )

        if email_confidence == "guessed" and not allow_guessed:
            raise PolicyDenied("guessed_email_requires_approval", event="policy.guessed_blocked")

        ctx = PolicyContext(
            campaign_id=campaign_id or "",
            lead_id=lead_id,
            step=step,
            to_email=to_email,
            subject=subject,
            body=body,
            email_confidence=email_confidence,
            allow_guessed=allow_guessed,
            send_mode=send_mode,
            mail_account_id=mail_account_id,
            approved=approved,
            verifier_passed=verifier_passed,
            seller_domain=seller_domain,
            live_confirm_ok=live_confirm_ok,
            db_path=path,
        )
        result = check_all(ctx)
        if not result.ok:
            if result.event == "policy.duplicate":
                return {
                    "status": "skipped_idempotent",
                    "idempotency_key": idempotency_key(lead_id, step),
                }
            if result.event in {"policy.rate_spaced", "policy.outside_window"} and result.reschedule_at:
                # Leave job pending; caller/worker should reschedule
                raise PolicyDenied(result.reason or result.event or "reschedule", event=result.event)
            if campaign_id and result.event:
                conn.commit()
                record_event(
                    campaign_id,
                    result.event,
                    "mailer",
                    f"Send blocked: {result.reason or result.event}",
                    lead_id=lead_id,
                    data={"step": step, "reason": result.reason},
                )
            # Preserve legacy reason strings for existing tests
            reason = result.reason or result.event or "denied"
            if result.event == "policy.mode_not_allowed" and "mailpit" in reason:
                raise PolicyDenied(reason, event=result.event)
            if result.event == "policy.suppressed":
                raise PolicyDenied(f"suppressed:{reason}", event=result.event)
            raise PolicyDenied(reason, event=result.event)

        account = result.account
        actual = result.actual_recipient or to_email
        domain = (result.extras or {}).get("domain") or (
            actual.split("@")[-1].lower() if "@" in actual else ""
        )

        key = idempotency_key(lead_id, step)
        existing = conn.execute(
            "SELECT id, status, delivery_status, message_id FROM emails WHERE idempotency_key = ?",
            (key,),
        ).fetchone()
        if existing and (
            existing["status"] in {"sent", "drafted"}
            or (existing["delivery_status"] or "") in {"sent", "drafted", "unknown"}
        ):
            return {"status": "skipped_idempotent", "idempotency_key": key}

        # Sandbox demo rewrite
        envelope_to = actual
        test_prefix = None
        if send_mode == "sandbox" and settings.demo_mode:
            envelope_to = f"{lead_id}@sandbox.local"
        elif send_mode == "gmail_test":
            test_prefix = (
                f"Test send · intended for contact at company "
                f"({mask_email(to_email)})"
            )

        # Threading
        in_reply_to = None
        step1_subject = None
        if step >= 2:
            prev = conn.execute(
                """
                SELECT message_id, subject FROM emails
                WHERE lead_id = ? AND step = 1
                ORDER BY sent_at DESC LIMIT 1
                """,
                (lead_id,),
            ).fetchone()
            if prev:
                in_reply_to = prev["message_id"]
                step1_subject = prev["subject"]

        from_email = settings.from_email
        display_name = "SignalSDR"
        signature = ""
        postal = ""
        if account:
            from_email = account["email"]
            display_name = account.get("display_name") or from_email
            signature = account.get("signature") or ""
            postal = account.get("postal_address") or ""

        composed = compose(
            subject=subject,
            body=body,
            to_addr=envelope_to,
            from_email=from_email,
            display_name=display_name,
            step=step,
            in_reply_to=in_reply_to,
            step1_subject=step1_subject,
            signature=signature,
            postal_address=postal,
            include_postal=(send_mode == "gmail_live"),
            test_prefix=test_prefix,
        )

        eid = existing["id"] if existing else email_id_for(lead_id, step)
        now = datetime.now(timezone.utc).isoformat()
        if existing:
            conn.execute(
                """
                UPDATE emails
                SET subject = ?, body = ?, status = 'queued', sent_at = NULL,
                    mail_account_id = ?, send_mode = ?, message_id = ?,
                    in_reply_to = ?, actual_recipient = ?, delivery_status = 'queued',
                    provider_response = NULL
                WHERE idempotency_key = ?
                """,
                (
                    composed.subject,
                    composed.body,
                    mail_account_id,
                    send_mode,
                    composed.message_id,
                    in_reply_to,
                    mask_email(envelope_to) if send_mode != "sandbox" else envelope_to,
                    key,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO emails (
                    id, lead_id, step, subject, body, status, idempotency_key, sent_at,
                    mail_account_id, send_mode, message_id, in_reply_to,
                    actual_recipient, delivery_status, provider_response
                ) VALUES (?, ?, ?, ?, ?, 'queued', ?, NULL, ?, ?, ?, ?, ?, 'queued', NULL)
                """,
                (
                    eid,
                    lead_id,
                    step,
                    composed.subject,
                    composed.body,
                    key,
                    mail_account_id,
                    send_mode,
                    composed.message_id,
                    in_reply_to,
                    mask_email(envelope_to) if send_mode != "sandbox" else envelope_to,
                ),
            )
        conn.commit()

        transport = pick_transport(send_mode, account, smtp_send=smtp_send)
        try:
            delivery = transport.deliver(composed.msg)
        except Exception as exc:  # noqa: BLE001
            conn.execute(
                """
                UPDATE emails SET status = 'failed', delivery_status = 'failed',
                    provider_response = ? WHERE id = ?
                """,
                ("delivery_error", eid),
            )
            conn.commit()
            raise MailerError("smtp_failure") from exc

        status_map = {
            "sent": ("sent", "sent"),
            "drafted": ("drafted", "drafted"),
            "unknown": ("unknown", "unknown"),
            "failed": ("failed", "failed"),
        }
        email_status, delivery_status = status_map.get(
            delivery.status, ("failed", "failed")
        )
        conn.execute(
            """
            UPDATE emails
            SET status = ?, delivery_status = ?, sent_at = ?, provider_response = ?,
                message_id = COALESCE(?, message_id)
            WHERE id = ?
            """,
            (
                email_status if email_status != "drafted" else "drafted",
                delivery_status,
                now if delivery_status in {"sent", "drafted", "unknown"} else None,
                (delivery.provider_response or "")[:200],
                delivery.message_id or composed.message_id,
                eid,
            ),
        )
        if delivery_status in {"sent", "drafted"}:
            conn.execute(
                "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
                ("sent" if step == 1 else "followup_scheduled", now, lead_id),
            )
            if mail_account_id and delivery_status == "sent":
                conn.execute(
                    """
                    INSERT INTO mail_send_log (account_id, recipient_hash, domain, ts)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        mail_account_id,
                        (result.extras or {}).get("recipient_hash") or "",
                        domain,
                        now,
                    ),
                )
        conn.commit()

        # Events/audit open their own connections — only after commit to avoid locks.
        if delivery_status == "unknown" and campaign_id:
            record_event(
                campaign_id,
                "mail.unknown_delivery",
                "mailer",
                "Delivery uncertain — check Gmail Sent before retrying.",
                lead_id=lead_id,
                db_path=path,
            )
        elif delivery_status in {"sent", "drafted"} and campaign_id:
            if delivery_status == "drafted":
                ev_type, ev_msg = "mail.drafted", "Draft saved to Gmail."
            elif step == 1:
                ev_type, ev_msg = "send.step1", "Email sent."
            else:
                ev_type, ev_msg = "mail.sent", "Follow-up sent."
            record_event(
                campaign_id,
                ev_type,
                "mailer",
                ev_msg,
                lead_id=lead_id,
                data={"step": step, "mode": send_mode},
                db_path=path,
            )

        write_audit(
            actor=actor,
            action="send" if delivery_status != "drafted" else "draft",
            target=eid,
            details={
                "lead_id": lead_id,
                "step": step,
                "campaign_id": campaign_id,
                "envelope_to": mask_email(envelope_to)
                if send_mode != "sandbox"
                else envelope_to,
                "recipient_domain": domain,
                "idempotency_key": key,
                "send_mode": send_mode,
                "mail_account_id": mail_account_id,
                "delivery_status": delivery_status,
                "message_id": composed.message_id,
            },
            db_path=path,
        )
        return {
            "status": delivery_status if delivery_status != "sent" else "sent",
            "email_id": eid,
            "idempotency_key": key,
            "envelope_to": envelope_to if send_mode == "sandbox" else mask_email(envelope_to),
            "sent_at": now,
            "message_id": composed.message_id,
            "send_mode": send_mode,
        }
    finally:
        conn.close()


def send_self_test(account_id: str, *, db_path: str | None = None) -> dict[str, Any]:
    """Send one short email to the account's own address via send()."""
    from app.mail.accounts import get_account

    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    account = get_account(account_id, db_path=path)
    if not account:
        raise MailerError("account_not_found")
    if account.get("status") == "disabled":
        raise PolicyDenied("account_unavailable", event="policy.account_unavailable")
    email = str(account["email"]).strip()
    cid = "mail-self-test"
    lead = f"selftest-{account_id}-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(path)
    try:
        row = conn.execute("SELECT id FROM campaigns WHERE id = ?", (cid,)).fetchone()
        options = {
            "send_mode": "gmail_test",
            "mail_account_id": account_id,
            "n": 1,
            "mode": "replay",
        }
        if not row:
            conn.execute(
                """
                INSERT INTO campaigns (
                    id, created_at, seller_name, seller_domain, input_json,
                    status, options_json
                ) VALUES (?, ?, 'SignalSDR', 'signalsdr.local', '{}', 'completed', ?)
                """,
                (cid, now, json.dumps(options)),
            )
        else:
            conn.execute(
                "UPDATE campaigns SET options_json = ? WHERE id = ?",
                (json.dumps(options), cid),
            )
        # emails.lead_id FK requires a leads row before mailer.send inserts
        conn.execute(
            """
            INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at)
            VALUES (?, ?, 'selftest', 'selftest', 'approved', ?)
            """,
            (lead, cid, now),
        )
        # gmail_test rewrites To → test_recipients[0]; docs require own inbox
        try:
            tests = json.loads(account.get("test_recipients_json") or "[]")
        except Exception:  # noqa: BLE001
            tests = list(account.get("test_recipients") or [])
        if not isinstance(tests, list):
            tests = []
        if email.lower() not in {str(t).lower() for t in tests}:
            tests = [email] + [t for t in tests if str(t).lower() != email.lower()]
        elif str(tests[0]).lower() != email.lower():
            tests = [email] + [t for t in tests if str(t).lower() != email.lower()]
        conn.execute(
            "UPDATE mail_accounts SET test_recipients_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(tests), now, account_id),
        )
        conn.commit()
    finally:
        conn.close()

    return send(
        lead_id=lead,
        step=1,
        subject="SignalSDR connection test",
        body=(
            "This is a SignalSDR connection test. You can delete this message.\n\n"
            "Reply STOP to opt out."
        ),
        to_email=email,
        email_confidence="verified",
        campaign_id=cid,
        actor="api",
        db_path=path,
        approved=True,
        verifier_passed=True,
    )
