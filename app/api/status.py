"""Derive campaign status from runs + checkpoint interrupts."""

from __future__ import annotations

from datetime import datetime, timezone

from app.api.runs import HEARTBEAT_STALE_S, is_alive
from app.api.state_reader import pending_interrupt
from app.config import get_settings
from app.infra.db import connect, init_db


def campaign_status(campaign_id: str) -> str:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT status, pause_requested FROM campaigns WHERE id = ?",
            (campaign_id,),
        ).fetchone()
        if not row:
            return "failed"
        stored = str(row["status"] or "queued")
        if stored == "paused" or int(row["pause_requested"] or 0) == 1:
            status = "paused"
        else:
            run = conn.execute(
                """
                SELECT heartbeat_at, ended_at, exit_code FROM runs
                WHERE campaign_id = ?
                ORDER BY started_at DESC LIMIT 1
                """,
                (campaign_id,),
            ).fetchone()
            if run and not run["ended_at"]:
                hb = datetime.fromisoformat(run["heartbeat_at"])
                age = (datetime.now(timezone.utc) - hb).total_seconds()
                if age > HEARTBEAT_STALE_S:
                    status = "crashed"
                else:
                    status = "running"
            else:
                payload = pending_interrupt(campaign_id)
                if payload and payload.get("type") == "icp_approval":
                    status = "waiting_icp"
                elif payload and payload.get("type") == "email_approval":
                    status = "waiting_approval"
                elif stored in {"completed", "halted", "failed", "queued", "waiting_icp", "waiting_approval"}:
                    status = stored
                elif run and run["exit_code"] not in (None, 0):
                    status = "failed"
                else:
                    status = stored or "queued"

        if status != stored:
            conn.execute("UPDATE campaigns SET status = ? WHERE id = ?", (status, campaign_id))
            conn.commit()
        return status
    finally:
        conn.close()


def can_resume(campaign_id: str) -> bool:
    status = campaign_status(campaign_id)
    return status in {"crashed", "paused", "waiting_icp", "waiting_approval"} and not is_alive(
        campaign_id
    )
