"""Shared campaign execution used by CLI run / run-campaign (with run heartbeat)."""

from __future__ import annotations

import atexit
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import get_settings
from app.graph import build_graph, initial_state, open_checkpointer
from app.infra.chaos import set_chaos
from app.infra.db import connect, init_db
from app.infra.tracing import callbacks, finish, init_tracing
from app.persist import persist_v0_run
from app.reporter.run_report import write_v0_report


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_campaign_row(
    campaign_id: str,
    *,
    company_name: str,
    website: str,
    description: str,
    n: int,
    mode: str,
    options: dict[str, Any] | None = None,
    status: str = "queued",
) -> None:
    settings = get_settings()
    init_db(settings.db_path)
    domain = urlparse(website).netloc or website
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            INSERT INTO campaigns (
                id, created_at, input_json, status, trace_ids,
                options_json, seller_name, seller_domain, pause_requested
            )
            VALUES (?, ?, ?, ?, '[]', ?, ?, ?, 0)
            ON CONFLICT(id) DO UPDATE SET
                input_json = excluded.input_json,
                options_json = excluded.options_json,
                seller_name = excluded.seller_name,
                seller_domain = excluded.seller_domain,
                status = CASE
                    WHEN campaigns.status IN ('completed', 'halted', 'failed') THEN campaigns.status
                    ELSE excluded.status
                END
            """,
            (
                campaign_id,
                _now(),
                json.dumps(
                    {
                        "company_name": company_name,
                        "website": website,
                        "description": description,
                        "n": n,
                        "mode": mode,
                    }
                ),
                status,
                json.dumps(options or {}),
                company_name,
                domain,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_campaign_status(campaign_id: str, status: str) -> None:
    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        conn.execute("UPDATE campaigns SET status = ? WHERE id = ?", (status, campaign_id))
        conn.commit()
    finally:
        conn.close()


def begin_run(campaign_id: str, kind: str) -> str:
    """Reuse open runs row (API-spawned) or insert; start heartbeat thread."""
    settings = get_settings()
    init_db(settings.db_path)
    now = _now()
    traces = (settings.neatlogs_traces_url or "").strip() or None
    conn = connect(settings.db_path)
    try:
        open_row = conn.execute(
            """
            SELECT id FROM runs
            WHERE campaign_id = ? AND ended_at IS NULL
            ORDER BY started_at DESC LIMIT 1
            """,
            (campaign_id,),
        ).fetchone()
        if open_row:
            run_id = str(open_row["id"])
            conn.execute(
                "UPDATE runs SET pid = ?, heartbeat_at = ?, kind = ? WHERE id = ?",
                (os_getpid(), now, kind, run_id),
            )
        else:
            run_id = f"{campaign_id}-{uuid.uuid4().hex[:8]}"
            conn.execute(
                """
                INSERT INTO runs (id, campaign_id, kind, pid, started_at, heartbeat_at, trace_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, campaign_id, kind, os_getpid(), now, now, traces),
            )
        conn.commit()
    finally:
        conn.close()

    stop = threading.Event()

    def _beat() -> None:
        while not stop.wait(5.0):
            c = connect(settings.db_path)
            try:
                c.execute(
                    "UPDATE runs SET heartbeat_at = ? WHERE id = ? AND ended_at IS NULL",
                    (_now(), run_id),
                )
                c.commit()
            finally:
                c.close()

    thread = threading.Thread(target=_beat, name=f"heartbeat-{run_id}", daemon=True)
    thread.start()

    def _end(code: int | None = None) -> None:
        stop.set()
        c = connect(settings.db_path)
        try:
            c.execute(
                "UPDATE runs SET ended_at = ?, exit_code = ? WHERE id = ? AND ended_at IS NULL",
                (_now(), code, run_id),
            )
            c.commit()
        finally:
            c.close()

    atexit.register(lambda: _end(None))
    return run_id


def end_run(run_id: str, exit_code: int = 0) -> None:
    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        conn.execute(
            "UPDATE runs SET ended_at = ?, exit_code = ? WHERE id = ?",
            (_now(), exit_code, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def os_getpid() -> int:
    import os

    return os.getpid()


def run_config(campaign_id: str, version: str = "v0.4") -> dict:
    return {
        "callbacks": callbacks(),
        "configurable": {"thread_id": campaign_id},
        "metadata": {"campaign_id": campaign_id, "version": version},
    }


def interrupt_from_result(result: dict) -> dict | None:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return None
    first = interrupts[0]
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {"value": value}


def interrupt_from_state(snapshot) -> dict | None:
    interrupts = getattr(snapshot, "interrupts", None) or ()
    for item in interrupts:
        value = getattr(item, "value", None)
        if isinstance(value, dict):
            return value
    for task in snapshot.tasks or ():
        for item in getattr(task, "interrupts", ()) or ():
            value = getattr(item, "value", None)
            if isinstance(value, dict):
                return value
    return interrupt_from_result(snapshot.values or {})


def execute_campaign(
    campaign_id: str,
    *,
    company_name: str,
    website: str,
    description: str,
    n: int,
    mode: str,
    chaos: str = "",
    narrow_icp: bool = False,
    target_mode: str = "discover",
    provided_companies: list[dict[str, str]] | None = None,
    provided_contacts: list[dict] | None = None,
    seed: str | None = None,
    seller_fallback: dict | None = None,
    template_id: str | None = None,
    template_name: str | None = None,
    template_snapshot: str | None = None,
    autopilot: bool | None = None,
    kind: str = "start",
    fresh: bool = True,
) -> dict[str, Any]:
    """Invoke the graph; return final state or interrupt-bearing result."""
    if chaos:
        set_chaos(chaos)
    init_tracing("outbound-v0" if kind == "start" else f"outbound-{kind}")
    run_id = begin_run(campaign_id, kind)
    update_campaign_status(campaign_id, "running")
    conn, checkpointer = open_checkpointer()
    started = time.time()
    try:
        app_graph = build_graph(checkpointer)
        config = run_config(campaign_id)
        if fresh:
            state = initial_state(
                campaign_id=campaign_id,
                company_name=company_name,
                website=website,
                description=description,
                n=n,
                mode=mode,
                narrow_icp=narrow_icp,
                target_mode=target_mode,
                provided_companies=provided_companies,
                provided_contacts=provided_contacts,
                seed=seed,
                seller_fallback=seller_fallback,
                template_id=template_id,
                template_name=template_name,
                template_snapshot=template_snapshot,
                autopilot=True if autopilot is None else bool(autopilot),
            )
            result = app_graph.invoke(state, config=config)
        else:
            result = app_graph.invoke(None, config=config)

        payload = interrupt_from_result(result)
        if payload and payload.get("type") == "icp_approval":
            update_campaign_status(campaign_id, "waiting_icp")
            end_run(run_id, 0)
            return result
        if payload and payload.get("type") == "email_approval":
            update_campaign_status(campaign_id, "waiting_approval")
            persist_v0_run(result)
            end_run(run_id, 0)
            return result

        persist_v0_run(result)
        write_v0_report(result, wall_seconds=time.time() - started)
        halt = result.get("halt_reason")
        update_campaign_status(campaign_id, "halted" if halt else "completed")
        end_run(run_id, 0)
        return result
    except Exception:
        update_campaign_status(campaign_id, "failed")
        end_run(run_id, 1)
        raise
    finally:
        conn.close()
        finish()


def load_campaign_options(campaign_id: str) -> dict[str, Any]:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if not row:
            raise KeyError(f"campaign not found: {campaign_id}")
        data = dict(row)
        opts = json.loads(data.get("options_json") or "{}")
        inp = json.loads(data.get("input_json") or "{}")
        return {
            "row": data,
            "options": opts,
            "input": inp,
            "company_name": data.get("seller_name") or inp.get("company_name") or "Company",
            "website": inp.get("website") or f"https://{(data.get('seller_domain') or 'example.com')}",
            "description": inp.get("description") or "",
            "n": int(opts.get("n") or inp.get("n") or 10),
            "mode": str(opts.get("mode") or inp.get("mode") or get_settings().data_mode),
            "chaos": str(opts.get("chaos") or ""),
            "narrow_icp": bool(opts.get("narrow_icp") or inp.get("narrow_icp")),
            "target_mode": str(
                opts.get("target_mode") or inp.get("target_mode") or "discover"
            ),
            "provided_companies": list(
                opts.get("provided_companies") or inp.get("provided_companies") or []
            ),
            "provided_contacts": list(
                opts.get("provided_contacts") or inp.get("provided_contacts") or []
            ),
            "seed": opts.get("seed") or inp.get("seed"),
            "seller_fallback": opts.get("seller_fallback")
            or inp.get("seller_fallback")
            or {},
            "template_id": opts.get("template_id") or inp.get("template_id"),
            "template_name": opts.get("template_name") or inp.get("template_name"),
            "template_snapshot": opts.get("template_snapshot")
            or inp.get("template_snapshot"),
            "autopilot": False if opts.get("autopilot") is False else True,
        }
    finally:
        conn.close()


def logs_dir() -> Path:
    path = Path("logs")
    path.mkdir(exist_ok=True)
    return path
