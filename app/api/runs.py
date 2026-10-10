"""Spawn CLI child processes for graph execution."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.infra.db import connect, init_db

HEARTBEAT_STALE_S = 15.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_alive(campaign_id: str) -> bool:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        row = conn.execute(
            """
            SELECT heartbeat_at, ended_at FROM runs
            WHERE campaign_id = ?
            ORDER BY started_at DESC LIMIT 1
            """,
            (campaign_id,),
        ).fetchone()
        if not row or row["ended_at"]:
            return False
        hb = datetime.fromisoformat(row["heartbeat_at"])
        age = (datetime.now(timezone.utc) - hb).total_seconds()
        return age < HEARTBEAT_STALE_S
    finally:
        conn.close()


def _spawn(campaign_id: str, args: list[str], kind: str) -> int:
    if is_alive(campaign_id):
        raise RuntimeError("This campaign is already running")
    settings = get_settings()
    init_db(settings.db_path)
    run_id = f"{campaign_id}-{uuid.uuid4().hex[:8]}"
    now = _now()
    logs = Path("logs")
    logs.mkdir(exist_ok=True)
    log_path = logs / f"{campaign_id}-{run_id}.log"
    traces = (settings.neatlogs_traces_url or "").strip() or None
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            INSERT INTO runs (id, campaign_id, kind, pid, started_at, heartbeat_at, trace_url)
            VALUES (?, ?, ?, NULL, ?, ?, ?)
            """,
            (run_id, campaign_id, kind, now, now, traces),
        )
        conn.commit()
    finally:
        conn.close()

    logf = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "cli.py", *args],
        cwd=str(Path.cwd()),
        env=os.environ.copy(),
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    conn = connect(settings.db_path)
    try:
        conn.execute("UPDATE runs SET pid = ? WHERE id = ?", (proc.pid, run_id))
        conn.commit()
    finally:
        conn.close()
    return proc.pid


def start_campaign(campaign_id: str) -> int:
    return _spawn(campaign_id, ["run-campaign", campaign_id], "start")


def resume_campaign(campaign_id: str) -> int:
    return _spawn(campaign_id, ["resume", campaign_id], "resume")


def approve_decision(campaign_id: str, decision_id: int) -> int:
    return _spawn(
        campaign_id,
        ["approve", campaign_id, "--decision-id", str(decision_id)],
        "resume",
    )
