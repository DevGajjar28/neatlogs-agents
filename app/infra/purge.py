"""Delete all persisted data for one campaign (SQLite + LangGraph thread)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import get_settings
from app.infra.db import connect, init_db


def purge_campaign(campaign_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    """Remove campaign rows, related mail data, ledger, cache, and checkpoint thread."""
    settings = get_settings()
    path = Path(db_path or settings.db_path)
    init_db(path)
    conn = connect(path)
    try:
        lead_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM leads WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchall()
        ]
        for lead_id in lead_ids:
            conn.execute("DELETE FROM scheduled_jobs WHERE lead_id = ?", (lead_id,))
            conn.execute("DELETE FROM emails WHERE lead_id = ?", (lead_id,))
            conn.execute("DELETE FROM replies WHERE lead_id = ?", (lead_id,))
        conn.execute("DELETE FROM leads WHERE campaign_id = ?", (campaign_id,))
        conn.execute("DELETE FROM budget_ledger WHERE campaign_id = ?", (campaign_id,))
        conn.execute("DELETE FROM cache WHERE campaign_id = ?", (campaign_id,))
        conn.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
        conn.commit()
    finally:
        conn.close()

    # LangGraph SqliteSaver shares the same DB file.
    from app.graph import open_checkpointer

    cp_conn, checkpointer = open_checkpointer(str(path))
    try:
        checkpointer.delete_thread(campaign_id)
    finally:
        cp_conn.close()

    return {"campaign_id": campaign_id, "leads": len(lead_ids)}
