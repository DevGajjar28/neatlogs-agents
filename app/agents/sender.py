"""Sender: deliver approved step-1 emails and schedule follow-ups."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import get_settings
from app.infra.db import connect, init_db
from app.tools.mailer import PolicyDenied, email_id_for, lead_id_for, send
from app.infra.events import EventBag


def sender_node(state: dict[str, Any]) -> dict[str, Any]:
    campaign_id = state["campaign_id"]
    contacts = {c["id"]: c for c in (state.get("contacts") or []) if isinstance(c, dict)}
    drafts = state.get("drafts") or {}
    approvals = dict((state.get("extras") or {}).get("email_approvals") or {})
    events = EventBag(state, "sender")
    errors = list(state.get("errors") or [])
    settings = get_settings()
    init_db(settings.db_path)

    for contact_id, sequence in drafts.items():
        choice = approvals.get(contact_id) or {}
        if not choice.get("approved"):
            continue
        contact = contacts.get(contact_id) or {}
        lead_id = lead_id_for(campaign_id, contact_id)
        _ensure_lead(campaign_id, lead_id, contact)

        step1 = sequence[0] if sequence else None
        if not step1:
            continue
        try:
            from app.agents.email_writer import personalize_copy

            companies = {
                c["id"]: c
                for c in (state.get("companies") or [])
                if isinstance(c, dict) and c.get("id")
            }
            company = companies.get(contact.get("company_id") or "") or {}
            seller = state.get("seller") or {}
            subj, body = personalize_copy(
                str(choice.get("subject") or step1.get("subject") or ""),
                str(choice.get("body") or step1.get("body") or ""),
                contact_name=str(contact.get("name") or ""),
                company_name=str(company.get("name") or ""),
                role=str(contact.get("title") or ""),
                seller_name=str(seller.get("company_name") or ""),
            )
            result = send(
                lead_id=lead_id,
                step=1,
                subject=subj,
                body=body,
                to_email=str(contact.get("email") or f"{lead_id}@unknown.local"),
                email_confidence=str(contact.get("email_confidence") or "none"),
                allow_guessed=bool(choice.get("allow_guessed")),
                campaign_id=campaign_id,
                actor="sender",
            )
            events.append(
                {
                    "type": "send.step1",
                    "lead_id": lead_id,
                    "contact_id": contact_id,
                    "contact": contact.get("name"),
                    "status": result.get("status"),
                }
            )
        except PolicyDenied as exc:
            errors.append(
                {
                    "step": "sender",
                    "lead_id": lead_id,
                    "error": str(exc.reason),
                }
            )
            events.append({"type": "send.denied", "lead_id": lead_id, "reason": exc.reason})
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append({"step": "sender", "lead_id": lead_id, "error": str(exc)})
            events.append({"type": "recovery.send_retry", "lead_id": lead_id, "error": str(exc)})
            # Leave follow-ups unscheduled on hard failure of step 1
            continue

        # Schedule steps 2 and 3 (demo: minutes; live: days)
        for draft in sequence[1:]:
            step = int(draft.get("step") or 0)
            if step not in (2, 3):
                continue
            delay = int(draft.get("send_after_days") or (3 if step == 2 else 7))
            run_at = _run_at(delay, demo=settings.demo_mode)
            _schedule_followup(
                lead_id=lead_id,
                step=step,
                subject=str(draft.get("subject") or ""),
                body=str(draft.get("body") or ""),
                run_at=run_at,
            )
            events.append(
                {
                    "type": "send.scheduled",
                    "lead_id": lead_id,
                    "contact": contact.get("name"),
                    "step": step,
                    "run_at": run_at,
                }
            )

    plan = dict(state.get("plan") or {})
    plan["phase"] = "after_email"
    return {"events": events, "errors": errors, "plan": plan}


def _ensure_lead(campaign_id: str, lead_id: str, contact: dict) -> None:
    settings = get_settings()
    conn = connect(settings.db_path)
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            """
            INSERT INTO campaigns (id, created_at, input_json, status, trace_ids)
            VALUES (?, ?, '{}', 'running', '[]')
            ON CONFLICT(id) DO NOTHING
            """,
            (campaign_id, now),
        )
        conn.execute(
            """
            INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at)
            VALUES (?, ?, ?, ?, 'awaiting_approval', ?)
            ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (
                lead_id,
                campaign_id,
                contact.get("company_id"),
                contact.get("id"),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _run_at(delay: int, *, demo: bool) -> str:
    now = datetime.now(timezone.utc)
    delta = timedelta(minutes=delay) if demo else timedelta(days=delay)
    return (now + delta).isoformat()


def _schedule_followup(
    *,
    lead_id: str,
    step: int,
    subject: str,
    body: str,
    run_at: str,
) -> None:
    settings = get_settings()
    conn = connect(settings.db_path)
    eid = email_id_for(lead_id, step)
    job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"job:{lead_id}:{step}"))
    key = f"{lead_id}:{step}"
    try:
        conn.execute(
            """
            INSERT INTO emails (id, lead_id, step, subject, body, status, idempotency_key, sent_at)
            VALUES (?, ?, ?, ?, ?, 'scheduled', ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                subject = excluded.subject,
                body = excluded.body,
                status = 'scheduled'
            """,
            (eid, lead_id, step, subject, body, key),
        )
        conn.execute(
            """
            INSERT INTO scheduled_jobs (id, lead_id, email_id, run_at, status, attempts)
            VALUES (?, ?, ?, ?, 'pending', 0)
            ON CONFLICT(id) DO UPDATE SET run_at = excluded.run_at, status = 'pending'
            """,
            (job_id, lead_id, eid, run_at),
        )
        conn.commit()
    finally:
        conn.close()
