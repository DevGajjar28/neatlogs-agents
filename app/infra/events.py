"""Activity timeline: state events + SQLite rows + stage stepper."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.infra.db import connect, init_db
from app.infra.event_messages import format_message, level_for
from app.infra.redact import redact_text


class EventBag(list):
    """List that mirrors appends into the events table (same dict shape as today)."""

    def __init__(self, state: dict[str, Any], agent: str) -> None:
        super().__init__(list(state.get("events") or []))
        self._campaign_id = str(state.get("campaign_id") or "")
        self._agent = agent

    def append(self, item: Any) -> None:  # type: ignore[override]
        super().append(item)
        if not isinstance(item, dict) or not self._campaign_id:
            return
        et = str(item.get("type") or "unknown")
        record_event(
            self._campaign_id,
            et,
            self._agent,
            format_message(et, item),
            level=level_for(et),
            credits_delta=float(item.get("credits_delta") or 0.0),
            lead_id=item.get("lead_id"),
            data=item,
        )


def emit(state: dict[str, Any], type: str, agent: str, **data: Any) -> list:
    """Append to state['events'] (same shape as today) and insert an events row.

    Returns the updated events list. Prefer EventBag at node start so existing
    appends are persisted; emit() is the explicit API from DECISIONS.md.
    """
    events = EventBag(state, agent)
    events.append({"type": type, **data})
    return list(events)


def record_event(
    campaign_id: str,
    type: str,
    agent: str,
    message: str,
    *,
    level: str = "info",
    credits_delta: float = 0.0,
    lead_id: str | None = None,
    data: dict | None = None,
    db_path: str | None = None,
) -> None:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        conn.execute(
            """
            INSERT INTO events (
                campaign_id, ts, type, agent, level, message,
                credits_delta, lead_id, trace_ref, data_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                campaign_id,
                datetime.now(timezone.utc).isoformat(),
                type,
                agent,
                level,
                redact_text(message),
                float(credits_delta),
                lead_id,
                json.dumps(data or {}, default=str),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def set_stage(
    campaign_id: str,
    stage: str,
    status: str,
    count_label: str | None = None,
    *,
    db_path: str | None = None,
) -> None:
    if not campaign_id:
        return
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(path)
    try:
        conn.execute(
            """
            INSERT INTO campaign_stages (campaign_id, stage, status, count_label, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(campaign_id, stage) DO UPDATE SET
                status = excluded.status,
                count_label = COALESCE(excluded.count_label, campaign_stages.count_label),
                updated_at = excluded.updated_at
            """,
            (campaign_id, stage, status, count_label, now),
        )
        conn.execute(
            "UPDATE campaigns SET current_stage = ? WHERE id = ?",
            (stage, campaign_id),
        )
        conn.commit()
    finally:
        conn.close()


def sync_new_events(
    campaign_id: str,
    before: list,
    after: list,
    *,
    agent: str,
) -> None:
    """Persist events newly appended by a node that did not call emit."""
    if not campaign_id:
        return
    start = len(before or [])
    for item in (after or [])[start:]:
        if not isinstance(item, dict):
            continue
        et = str(item.get("type") or "unknown")
        record_event(
            campaign_id,
            et,
            agent,
            format_message(et, item),
            level=level_for(et),
            lead_id=item.get("lead_id"),
            data=item,
        )
