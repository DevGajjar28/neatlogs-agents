"""Build the 6-agent demo pipeline from campaign_stages + events."""

from __future__ import annotations

from typing import Any

from app.api.schemas import PipelineAgentOut, PipelineOut
from app.config import get_settings
from app.infra.db import connect, init_db

PIPELINE_AGENTS: list[dict[str, Any]] = [
    {
        "agent": "planner",
        "label": "Planner",
        "stages": ["plan"],
        "event_agents": {"planner"},
    },
    {
        "agent": "product_researcher",
        "label": "Product Researcher",
        "stages": ["product"],
        "event_agents": {"product_researcher"},
    },
    {
        "agent": "buyer_finder",
        "label": "Buyer Finder",
        "stages": ["buyers", "icp"],
        "event_agents": {"buyer_finder"},
    },
    {
        "agent": "account_researcher",
        "label": "Account Researcher",
        "stages": ["accounts"],
        "event_agents": {"account_researcher", "account_enrich", "account_company", "account_join"},
    },
    {
        "agent": "email_writer_verifier",
        "label": "Email Writer + Verifier",
        "stages": ["emails", "verify", "approval"],
        "event_agents": {"email_writer", "verifier", "approval_gate"},
    },
    {
        "agent": "sender",
        "label": "Sender",
        "stages": ["send"],
        "event_agents": {"sender"},
    },
]


def _map_status(stage_statuses: list[str]) -> str:
    if not stage_statuses:
        return "idle"
    if any(s == "waiting" for s in stage_statuses):
        return "waiting"
    if any(s == "failed" for s in stage_statuses):
        return "failed"
    if any(s == "running" for s in stage_statuses):
        return "running"
    if all(s in {"done", "skipped"} for s in stage_statuses):
        return "done"
    if any(s in {"done", "skipped", "running", "waiting", "failed"} for s in stage_statuses):
        # Partially progressed while later mapped stages still pending
        if any(s == "pending" for s in stage_statuses) and any(
            s in {"done", "skipped"} for s in stage_statuses
        ):
            return "running"
        return "idle"
    return "idle"


def campaign_pipeline(campaign_id: str) -> PipelineOut:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        camp = conn.execute(
            "SELECT options_json, input_json FROM campaigns WHERE id = ?",
            (campaign_id,),
        ).fetchone()
        stage_rows = {
            r["stage"]: dict(r)
            for r in conn.execute(
                """
                SELECT stage, status, count_label, updated_at
                FROM campaign_stages WHERE campaign_id = ?
                """,
                (campaign_id,),
            ).fetchall()
        }
        event_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT id, ts, type, agent, level, message
                FROM events WHERE campaign_id = ?
                ORDER BY id DESC LIMIT 400
                """,
                (campaign_id,),
            ).fetchall()
        ]
    finally:
        conn.close()

    target_mode = "discover"
    if camp:
        import json

        opts = json.loads(camp["options_json"] or "{}")
        inp = json.loads(camp["input_json"] or "{}")
        target_mode = str(opts.get("target_mode") or inp.get("target_mode") or "discover")
    provided = target_mode == "provided"

    agents: list[PipelineAgentOut] = []
    for spec in PIPELINE_AGENTS:
        stages = list(spec["stages"])
        label = spec["label"]
        event_agents = set(spec["event_agents"])
        if spec["agent"] == "buyer_finder" and provided:
            label = "Your list"
            stages = ["buyers"]  # import only; no ICP stage
            event_agents = {"buyer_finder"}

        statuses = []
        count_label = None
        updated_at = None
        for stage in stages:
            row = stage_rows.get(stage)
            if not row:
                statuses.append("pending")
                continue
            statuses.append(str(row.get("status") or "pending"))
            if row.get("count_label") and not count_label:
                count_label = row["count_label"]
            ts = row.get("updated_at")
            if ts and (updated_at is None or str(ts) > str(updated_at)):
                updated_at = ts

        status = _map_status(statuses)
        # Prefer newest count_label from last non-empty among stages (reverse order)
        for stage in reversed(stages):
            row = stage_rows.get(stage)
            if row and row.get("count_label"):
                count_label = row["count_label"]
                break

        detail = None
        started_at = None
        latest_ts = None
        for ev in event_rows:
            if ev.get("agent") not in event_agents:
                continue
            if detail is None:
                detail = ev.get("message") or None
                latest_ts = ev.get("ts")
            # Walk all matching for earliest started_at (list is DESC)
            started_at = ev.get("ts")
        if latest_ts and (updated_at is None or str(latest_ts) > str(updated_at)):
            updated_at = latest_ts

        if status == "idle":
            detail = None
            count_label = None

        agents.append(
            PipelineAgentOut(
                agent=spec["agent"],
                label=label,
                status=status,  # type: ignore[arg-type]
                detail=detail,
                count_label=count_label,
                started_at=started_at,
                updated_at=updated_at,
            )
        )
    return PipelineOut(agents=agents)
