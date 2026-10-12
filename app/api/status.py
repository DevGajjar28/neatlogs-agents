"""Derive campaign status from runs + checkpoint interrupts."""

from __future__ import annotations

from datetime import datetime, timezone

from app.api.runs import HEARTBEAT_STALE_S, is_alive
from app.api.state_reader import get_values, pending_interrupt
from app.config import get_settings
from app.infra.db import connect, init_db


def _has_pending_email_approvals(campaign_id: str) -> bool:
    """True when drafts are ready for human approve/send without a live interrupt."""
    try:
        values = get_values(campaign_id)
    except Exception:  # noqa: BLE001
        return False
    extras = values.get("extras") or {}
    cached = extras.get("pending_email_approval")
    if isinstance(cached, dict) and cached.get("items"):
        return True
    already = dict(extras.get("email_approvals") or {})
    drafts = values.get("drafts") or {}
    verifier = values.get("verifier") or {}
    for contact_id, _seq in drafts.items():
        if already.get(contact_id, {}).get("approved") is True:
            continue
        v = verifier.get(contact_id) or {}
        if v.get("passed") or v.get("action") in {"pass", "downgrade"}:
            return True
    return False


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
            # Interrupt / pending email approve wins over "running" — otherwise the
            # Approvals page (which filters waiting_approval) stays empty while the
            # pipeline is blocked on human review.
            payload = pending_interrupt(campaign_id)
            if payload and payload.get("type") == "icp_approval":
                status = "waiting_icp"
            elif payload and payload.get("type") == "email_approval":
                status = "waiting_approval"
            elif _has_pending_email_approvals(campaign_id):
                status = "waiting_approval"
            elif run and not run["ended_at"]:
                hb = datetime.fromisoformat(run["heartbeat_at"])
                age = (datetime.now(timezone.utc) - hb).total_seconds()
                if age > HEARTBEAT_STALE_S:
                    status = "crashed"
                else:
                    status = "running"
            elif stored == "waiting_approval":
                status = "waiting_approval"
            elif stored in {"completed", "halted", "failed", "queued", "waiting_icp"}:
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
