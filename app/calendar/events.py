"""Create Google Calendar events after human confirms a meeting slot."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.calendar.oauth import (
    CalendarNotConnected,
    get_access_token,
    get_status,
)
from app.config import get_settings
from app.infra.db import connect, init_db
from app.infra.events import record_event

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

_WEEKDAYS = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _parse_label_to_start(label: str | None, now: datetime) -> datetime | None:
    """Best-effort parse of labels like 'Tuesday 2:00 PM UTC' or 'Tue 13 Oct 15:00 UTC'."""
    if not label:
        return None
    text = " ".join(label.strip().split())
    low = text.lower().replace(",", " ")

    # Tue 13 Oct 15:00 UTC / Tuesday 13 October 15:00
    m = re.search(
        r"\b("
        + "|".join(_WEEKDAYS)
        + r")\b\s+(\d{1,2})\s+("
        + "|".join(_MONTHS)
        + r")\b\s+(\d{1,2}):(\d{2})\s*(am|pm)?",
        low,
    )
    if m:
        day = int(m.group(2))
        month = _MONTHS[m.group(3)]
        hour = int(m.group(4))
        minute = int(m.group(5))
        ampm = m.group(6)
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        year = now.year
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:
            return None
        if dt < now - timedelta(hours=1):
            try:
                dt = datetime(year + 1, month, day, hour, minute, tzinfo=timezone.utc)
            except ValueError:
                return None
        return dt

    # Tuesday 2:00 PM UTC
    m = re.search(
        r"\b(" + "|".join(_WEEKDAYS) + r")\b.*?\b(\d{1,2}):(\d{2})\s*(am|pm)\b",
        low,
    )
    if m:
        target_wd = _WEEKDAYS[m.group(1)]
        hour = int(m.group(2))
        minute = int(m.group(3))
        ampm = m.group(4)
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        d = now.date()
        for _ in range(8):
            if d.weekday() == target_wd:
                candidate = datetime(
                    d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc
                )
                if candidate >= now - timedelta(minutes=5):
                    return candidate
            d += timedelta(days=1)
    return None


def resolve_slot_start(
    start_iso: str | None,
    label: str | None,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Resolve a concrete UTC start; roll past / bad LLM years forward from the label."""
    now = now or datetime.now(timezone.utc)
    dt: datetime | None = None
    if start_iso:
        try:
            dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
        except ValueError:
            dt = None
    if dt is None or dt < now:
        parsed = _parse_label_to_start(label, now)
        if parsed:
            dt = parsed
    if dt is not None and dt < now:
        # Keep weekday+time, jump forward week by week.
        while dt < now:
            dt += timedelta(days=7)
    return dt


def _parse_start(start_iso: str | None, label: str | None) -> datetime | None:
    """Back-compat name used by tests/callers."""
    return resolve_slot_start(start_iso, label)


def create_meeting_event(
    *,
    meeting_id: str,
    slot_label: str,
    start_iso: str | None,
    summary: str,
    description: str = "",
    attendee_email: str | None = None,
    duration_minutes: int = 30,
    db_path: str | None = None,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Insert or update an event on the connected calendar. Returns {event_id, html_link}."""
    settings = get_settings()
    path = db_path or settings.db_path
    status = get_status(db_path=path)
    if not status.get("connected"):
        raise CalendarNotConnected("Google Calendar is not connected")

    start = resolve_slot_start(start_iso, slot_label)
    if not start:
        raise ValueError("slot_missing_start_iso")
    end = start + timedelta(minutes=max(15, duration_minutes))

    body: dict[str, Any] = {
        "summary": (summary or f"Meeting — {slot_label}")[:200],
        "description": (description or "")[:4000],
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
    }
    notify = bool(settings.google_calendar_notify_attendees)
    if attendee_email and "@" in attendee_email and notify:
        body["attendees"] = [{"email": attendee_email.strip()}]

    init_db(path)
    conn = connect(path)
    try:
        existing = conn.execute(
            """
            SELECT campaign_id, lead_id, calendar_event_id
            FROM meeting_proposals WHERE id = ?
            """,
            (meeting_id,),
        ).fetchone()
        existing_event_id = (
            str(existing["calendar_event_id"] or "") if existing else ""
        )
        campaign_id = existing["campaign_id"] if existing else None
        lead_id = existing["lead_id"] if existing else None
    finally:
        conn.close()

    token = get_access_token(db_path=path)
    params = {"sendUpdates": "all" if (notify and body.get("attendees")) else "none"}
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=30.0)
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if existing_event_id:
            r = client.patch(
                f"{EVENTS_URL}/{existing_event_id}",
                params=params,
                headers=headers,
                json=body,
            )
            if r.status_code >= 400:
                # Event may have been deleted in Google — create fresh.
                r = client.post(
                    EVENTS_URL,
                    params=params,
                    headers=headers,
                    json=body,
                )
        else:
            r = client.post(
                EVENTS_URL,
                params=params,
                headers=headers,
                json=body,
            )
        if r.status_code >= 400:
            raise RuntimeError(f"calendar_create_failed:{r.status_code}")
        data = r.json()
    finally:
        if owns_client:
            client.close()

    event_id = str(data.get("id") or existing_event_id or "")
    html_link = str(data.get("htmlLink") or "")
    conn = connect(path)
    try:
        conn.execute(
            """
            UPDATE meeting_proposals
            SET calendar_event_id = ?, calendar_html_link = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                event_id or None,
                html_link or None,
                datetime.now(timezone.utc).isoformat(),
                meeting_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    if campaign_id:
        record_event(
            campaign_id,
            "meeting.calendar_created",
            "calendar",
            "Meeting added to Google Calendar.",
            lead_id=lead_id,
            data={
                "meeting_id": meeting_id,
                "event_id": event_id,
                "html_link": html_link,
                "slot": slot_label,
                "start": start.isoformat(),
            },
            db_path=path,
        )
    return {"event_id": event_id, "html_link": html_link, "start": start.isoformat()}
