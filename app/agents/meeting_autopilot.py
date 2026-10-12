"""Autopilot inbound meeting flows: propose slots or book + email without HITL."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agents.reply_decision import ReplyTicket, run_decision_for_ticket
from app.calendar.events import create_meeting_event, parse_meeting_time_from_text
from app.config import get_settings
from app.infra.db import connect, init_db
from app.infra.events import record_event
from app.tools.mailer import PolicyDenied, send


def _contact_for_lead(campaign_id: str, contact_id: str | None) -> dict[str, Any]:
    from app.api import state_reader

    contacts = {
        c["id"]: c
        for c in state_reader.contacts(campaign_id)
        if isinstance(c, dict) and c.get("id")
    }
    return contacts.get(contact_id or "") or {}


def _contact_email(campaign_id: str, contact_id: str | None) -> str | None:
    contact = _contact_for_lead(campaign_id, contact_id)
    email = str(contact.get("email") or "").strip()
    return email if email else None


def _last_meeting_context(conn, lead_id: str) -> dict[str, Any] | None:
    mp = conn.execute(
        """
        SELECT id, slots_json, notes, status FROM meeting_proposals
        WHERE lead_id = ?
        ORDER BY updated_at DESC LIMIT 1
        """,
        (lead_id,),
    ).fetchone()
    if not mp:
        return None
    label = None
    start_iso = None
    notes = str(mp["notes"] or "")
    if notes.lower().startswith("confirmed slot:"):
        label = notes.split(":", 1)[1].strip()
    try:
        for s in json.loads(mp["slots_json"] or "[]"):
            if isinstance(s, dict):
                if label and s.get("label") == label:
                    start_iso = s.get("start_iso")
                    break
                if not label and s.get("label"):
                    label = s.get("label")
                    start_iso = s.get("start_iso")
                    break
    except Exception:  # noqa: BLE001
        pass
    return {
        "meeting_id": mp["id"],
        "label": label,
        "start_iso": start_iso,
        "status": mp["status"],
    }


def handle_meeting_confirmed(
    *,
    lead_id: str,
    campaign_id: str,
    snippet: str,
    in_reply_to: str | None,
    our_subject: str | None,
    db_path: str | None = None,
) -> bool:
    """Book calendar (+ Meet) and send confirmation email. Returns True if handled."""
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        lead = conn.execute(
            "SELECT contact_id FROM leads WHERE id = ?", (lead_id,)
        ).fetchone()
        contact = _contact_for_lead(campaign_id, lead["contact_id"] if lead else None)
        to_email = str(contact.get("email") or "").strip() or None
        email_confidence = str(contact.get("email_confidence") or "verified")
        # User / autopilot replies are human-validated destinations.
        if contact.get("email_source") == "user":
            email_confidence = "verified"
        ctx = _last_meeting_context(conn, lead_id)
    finally:
        conn.close()

    if not to_email:
        return False

    parsed = parse_meeting_time_from_text(snippet)
    label = ctx.get("label") if ctx else None
    start_iso = ctx.get("start_iso") if ctx else None
    if parsed:
        label = parsed.strftime("%a %d %b %H:%M UTC")
        start_iso = parsed.isoformat()
    elif not label:
        return False

    meeting_id = (ctx or {}).get("meeting_id") or f"mp_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(path)
    try:
        existing = conn.execute(
            "SELECT id FROM meeting_proposals WHERE id = ?", (meeting_id,)
        ).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO meeting_proposals (
                    id, lead_id, campaign_id, reply_draft_id, slots_json,
                    booking_link, status, notes, created_at, updated_at
                ) VALUES (?, ?, ?, NULL, ?, NULL, 'confirmed', ?, ?, ?)
                """,
                (
                    meeting_id,
                    lead_id,
                    campaign_id,
                    json.dumps([{"label": label, "start_iso": start_iso}]),
                    f"Confirmed slot: {label}",
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE meeting_proposals
                SET status = 'confirmed', notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (f"Confirmed slot: {label}", now, meeting_id),
            )
        conn.commit()
    finally:
        conn.close()

    subj = our_subject or "Re: meeting"
    if not subj.lower().startswith("re:"):
        subj = f"Re: {subj}"

    calendar_result = None
    try:
        from app.calendar.oauth import CalendarNotConnected, get_status

        if get_status(db_path=path).get("connected"):
            calendar_result = create_meeting_event(
                meeting_id=meeting_id,
                slot_label=label,
                start_iso=start_iso,
                summary=subj[:160],
                description=f"SignalSDR Autopilot meeting\nLead: {lead_id}",
                attendee_email=to_email,
                db_path=path,
            )
    except CalendarNotConnected:
        calendar_result = None
    except Exception as exc:  # noqa: BLE001
        record_event(
            campaign_id,
            "meeting.calendar_failed",
            "meeting_autopilot",
            "Could not add meeting to Google Calendar.",
            lead_id=lead_id,
            data={"error": type(exc).__name__},
            db_path=path,
        )

    meet_link = (calendar_result or {}).get("meet_link") or ""
    body = (
        f"Perfect — confirmed for {label}.\n\n"
        + (f"Join Google Meet: {meet_link}\n\n" if meet_link else "")
        + "Looking forward to speaking then.\n\nBest regards\n"
    )

    conn2 = connect(path)
    try:
        max_step = conn2.execute(
            "SELECT COALESCE(MAX(step), 0) AS m FROM emails WHERE lead_id = ?",
            (lead_id,),
        ).fetchone()["m"]
    finally:
        conn2.close()
    step = max(10, int(max_step) + 1)

    try:
        send(
            lead_id=lead_id,
            step=step,
            subject=subj[:160],
            body=body,
            to_email=to_email,
            email_confidence=email_confidence,
            campaign_id=campaign_id,
            actor="meeting_autopilot",
            db_path=path,
            approved=True,
            verifier_passed=True,
            thread_in_reply_to=in_reply_to,
            keep_subject=True,
        )
    except PolicyDenied as exc:
        record_event(
            campaign_id,
            getattr(exc, "event", None) or "policy.denied",
            "meeting_autopilot",
            f"Meeting confirm blocked: {exc}",
            lead_id=lead_id,
            data={"error": str(exc)},
            db_path=path,
        )
        return False

    record_event(
        campaign_id,
        "reply.autopilot_sent",
        "meeting_autopilot",
        "Meeting confirmation sent (Autopilot).",
        lead_id=lead_id,
        data={"slot": label, "meet_link": meet_link or None},
        db_path=path,
    )
    return True


def handle_meeting_proposal_autopilot(
    *,
    lead_id: str,
    campaign_id: str,
    reply_id: int | None,
    classification: str,
    snippet: str,
    from_masked: str | None,
    in_reply_to: str | None,
    our_subject: str | None,
    contact_name: str | None = None,
    db_path: str | None = None,
) -> bool:
    """Auto-send slot proposal email (no pending draft)."""
    settings = get_settings()
    path = db_path or settings.db_path
    ticket = ReplyTicket(
        lead_id=lead_id,
        campaign_id=campaign_id,
        reply_id=reply_id,
        classification=classification,
        snippet=snippet,
        from_masked=from_masked,
        our_subject=our_subject,
        in_reply_to=in_reply_to,
        contact_name=contact_name,
    )
    conn = connect(path)
    try:
        lead = conn.execute("SELECT contact_id FROM leads WHERE id = ?", (lead_id,)).fetchone()
        contact_id = lead["contact_id"] if lead else None
        contact = _contact_for_lead(campaign_id, contact_id)
        to_email = str(contact.get("email") or "").strip()
    finally:
        conn.close()
    if not to_email:
        return False

    result = run_decision_for_ticket(ticket, use_llm=True, db_path=path)
    draft_id = result.get("draft_id")
    if not draft_id:
        return False

    from app.agents.reply_decision import approve_and_send_reply_draft

    try:
        approve_and_send_reply_draft(
            draft_id,
            to_email=to_email,
            db_path=path,
        )
    except (PolicyDenied, KeyError, ValueError):
        # Don't leave a pending HITL draft when Autopilot owns the flow.
        _cancel_pending_drafts(lead_id, db_path=path)
        return False
    record_event(
        campaign_id,
        "reply.autopilot_proposal_sent",
        "meeting_autopilot",
        "Meeting slot proposal sent (Autopilot).",
        lead_id=lead_id,
        data={"draft_id": draft_id},
        db_path=path,
    )
    return True


def _cancel_pending_drafts(lead_id: str, *, db_path: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(db_path)
    try:
        conn.execute(
            """
            UPDATE reply_drafts SET status = 'cancelled', updated_at = ?
            WHERE lead_id = ? AND status = 'pending'
            """,
            (now, lead_id),
        )
        conn.execute(
            """
            UPDATE meeting_proposals SET status = 'cancelled', updated_at = ?
            WHERE lead_id = ? AND status = 'proposed'
            """,
            (now, lead_id),
        )
        conn.commit()
    finally:
        conn.close()


def snippet_has_concrete_time(snippet: str) -> bool:
    return parse_meeting_time_from_text(snippet or "") is not None


def try_autopilot_inbound(
    *,
    lead_id: str,
    campaign_id: str,
    classification: str,
    snippet: str,
    reply_id: int | None,
    from_masked: str | None,
    in_reply_to: str | None,
    our_subject: str | None,
    db_path: str | None = None,
) -> bool:
    """Return True if autopilot handled this reply (no HITL draft)."""
    from app.infra.autopilot import campaign_autopilot_from_db_options
    import json as _json

    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT options_json FROM campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
    finally:
        conn.close()
    opts = _json.loads(row["options_json"] or "{}") if row else {}
    if not campaign_autopilot_from_db_options(opts):
        return False

    # Prospect named a time → book Meet + confirm email. Never leave a slot-picker draft.
    concrete = snippet_has_concrete_time(snippet)
    if classification in {"meeting_confirmed", "meeting_request", "interested"} and concrete:
        _cancel_pending_drafts(lead_id, db_path=path)
        ok = handle_meeting_confirmed(
            lead_id=lead_id,
            campaign_id=campaign_id,
            snippet=snippet,
            in_reply_to=in_reply_to,
            our_subject=our_subject,
            db_path=path,
        )
        if ok:
            return True
        # Fall through only if booking failed (e.g. no contact email).

    if classification == "meeting_confirmed":
        _cancel_pending_drafts(lead_id, db_path=path)
        return handle_meeting_confirmed(
            lead_id=lead_id,
            campaign_id=campaign_id,
            snippet=snippet,
            in_reply_to=in_reply_to,
            our_subject=our_subject,
            db_path=path,
        )
    if classification == "meeting_request":
        # No concrete time yet — propose slots and send automatically (no HITL).
        return handle_meeting_proposal_autopilot(
            lead_id=lead_id,
            campaign_id=campaign_id,
            reply_id=reply_id,
            classification=classification,
            snippet=snippet,
            from_masked=from_masked,
            in_reply_to=in_reply_to,
            our_subject=our_subject,
            db_path=path,
        )
    if classification == "interested":
        low = snippet.lower()
        if any(
            p in low
            for p in (
                "yes that works",
                "that works for me",
                "works for me",
                "sounds good",
                "see you",
                "confirmed",
            )
        ):
            _cancel_pending_drafts(lead_id, db_path=path)
            return handle_meeting_confirmed(
                lead_id=lead_id,
                campaign_id=campaign_id,
                snippet=snippet,
                in_reply_to=in_reply_to,
                our_subject=our_subject,
                db_path=path,
            )
    return False
