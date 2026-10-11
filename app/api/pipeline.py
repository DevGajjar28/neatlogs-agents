"""Build the 6-agent demo pipeline from campaign_stages + events + checkpoint."""

from __future__ import annotations

import json
import re
from typing import Any

from app.api.schemas import PipelineAgentOut, PipelineOut, PipelineProgressOut
from app.api import state_reader
from app.config import get_settings
from app.infra.db import connect, init_db

PIPELINE_AGENTS: list[dict[str, Any]] = [
    {
        "agent": "planner",
        "key": "planner",
        "label": "Planner",
        "stages": ["plan"],
        "event_agents": {"planner"},
    },
    {
        "agent": "product_researcher",
        "key": "product",
        "label": "Product Researcher",
        "stages": ["product"],
        "event_agents": {"product_researcher"},
    },
    {
        "agent": "buyer_finder",
        "key": "buyers",
        "label": "Buyer Finder",
        "stages": ["buyers", "icp"],
        "event_agents": {"buyer_finder"},
    },
    {
        "agent": "account_researcher",
        "key": "accounts",
        "label": "Account Researcher",
        "stages": ["accounts"],
        "event_agents": {
            "account_researcher",
            "account_enrich",
            "account_company",
            "account_join",
        },
    },
    {
        "agent": "email_writer_verifier",
        "key": "writer",
        "label": "Email Writer + Verifier",
        "stages": ["emails", "verify", "approval"],
        "event_agents": {"email_writer", "verifier", "approval_gate"},
    },
    {
        "agent": "sender",
        "key": "sender",
        "label": "Sender",
        "stages": ["send"],
        "event_agents": {"sender"},
    },
]

_NUM = re.compile(r"(\d+)")


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
        if any(s == "pending" for s in stage_statuses) and any(
            s in {"done", "skipped"} for s in stage_statuses
        ):
            return "running"
        return "idle"
    return "idle"


def _parse_progress_from_label(label: str | None) -> PipelineProgressOut | None:
    if not label:
        return None
    nums = [int(x) for x in _NUM.findall(label)]
    if not nums:
        return None
    if len(nums) >= 2:
        return PipelineProgressOut(done=nums[0], total=nums[1])
    return PipelineProgressOut(done=nums[0], total=None)


def _enrich_from_state(
    campaign_id: str,
    *,
    provided: bool,
    stage_rows: dict[str, dict],
) -> dict[str, dict[str, Any]]:
    """Real progress/items from checkpoint + DB. Never invent."""
    out: dict[str, dict[str, Any]] = {spec["key"]: {} for spec in PIPELINE_AGENTS}
    try:
        values = state_reader.get_values(campaign_id)
    except Exception:  # noqa: BLE001
        values = {}

    seller = values.get("seller") or {}
    companies = [c for c in (values.get("companies") or []) if isinstance(c, dict)]
    contacts = [c for c in (values.get("contacts") or []) if isinstance(c, dict)]
    drafts = values.get("drafts") or {}
    verifier = values.get("verifier") or {}
    plan = values.get("plan") or {}

    # Product
    facts: list[str] = []
    for e in seller.get("evidence") or []:
        if isinstance(e, dict) and e.get("fact"):
            facts.append(str(e["fact"])[:48])
    for p in seller.get("products") or []:
        if p and str(p) not in facts:
            facts.append(str(p)[:48])
    if facts:
        out["product"]["items"] = facts[:6]
        out["product"]["progress"] = PipelineProgressOut(done=len(facts[:6]), total=None)
        out["product"]["count_label"] = f"{len(facts[:6])} facts"

    # Buyers
    kept = [c for c in companies if c.get("status") == "kept"]
    dropped = [c for c in companies if c.get("status") == "dropped"]
    considered = len(companies)
    if considered:
        done = len(kept)
        total = min(considered, 30) if not provided else considered
        out["buyers"]["progress"] = PipelineProgressOut(done=done, total=total)
        if provided:
            out["buyers"]["count_label"] = f"{done} of {total} matched"
        else:
            out["buyers"]["count_label"] = f"{done} of {total} kept"
        out["buyers"]["items"] = [
            str(c.get("name") or c.get("domain") or "")[:32] for c in kept[:6] if c.get("name") or c.get("domain")
        ]

    # Accounts
    n_contacts = len(contacts)
    if n_contacts or stage_rows.get("accounts"):
        out["accounts"]["progress"] = PipelineProgressOut(
            done=min(n_contacts, 6), total=6 if n_contacts else None
        )
        if n_contacts:
            out["accounts"]["count_label"] = f"{n_contacts} contacts"
            out["accounts"]["items"] = [
                str(c.get("name") or "")[:32] for c in contacts[:6] if c.get("name")
            ]

    # Writer
    n_drafts = len(drafts) if isinstance(drafts, dict) else 0
    passed = sum(
        1
        for cid, v in (verifier or {}).items()
        if isinstance(v, dict) and (v.get("passed") or v.get("action") in {"pass", "downgrade"})
    )
    if n_drafts:
        out["writer"]["progress"] = PipelineProgressOut(done=passed, total=n_drafts)
        out["writer"]["count_label"] = f"{passed}/{n_drafts} checked"

    # Sender — from emails table
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        sent_row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM emails e
            JOIN leads l ON l.id = e.lead_id
            WHERE l.campaign_id = ? AND (
              e.status = 'sent' OR e.delivery_status IN ('sent', 'drafted', 'unknown')
            )
            """,
            (campaign_id,),
        ).fetchone()
        sent_n = int(sent_row["n"] or 0) if sent_row else 0
    finally:
        conn.close()
    if sent_n or stage_rows.get("send"):
        out["sender"]["progress"] = PipelineProgressOut(done=sent_n, total=None)
        if sent_n:
            out["sender"]["count_label"] = f"{sent_n} sent"

    # Planner jobs: 5 sub-agents done count
    agent_status_later = []  # filled by caller after statuses known
    out["planner"]["_plan"] = plan
    out["planner"]["_kept"] = len(kept)
    out["planner"]["_dropped"] = len(dropped)
    out["product"]["_named"] = list(seller.get("named_customers") or [])[:6]
    return out


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

    target_mode_raw = "discover"
    model = "Amazon Bedrock"
    if camp:
        opts = json.loads(camp["options_json"] or "{}")
        inp = json.loads(camp["input_json"] or "{}")
        target_mode_raw = str(opts.get("target_mode") or inp.get("target_mode") or "discover")
        if opts.get("model_label"):
            model = str(opts["model_label"])
    provided = target_mode_raw == "provided"
    target_mode: str = "list" if provided else "discover"

    enrich = _enrich_from_state(campaign_id, provided=provided, stage_rows=stage_rows)

    agents: list[PipelineAgentOut] = []
    statuses_by_key: dict[str, str] = {}
    for spec in PIPELINE_AGENTS:
        stages = list(spec["stages"])
        label = spec["label"]
        event_agents = set(spec["event_agents"])
        key = spec["key"]
        if spec["agent"] == "buyer_finder" and provided:
            label = "Your list"
            stages = ["buyers"]
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
        statuses_by_key[key] = status
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
            started_at = ev.get("ts")
        if latest_ts and (updated_at is None or str(latest_ts) > str(updated_at)):
            updated_at = latest_ts

        # Planner assignment line from latest plan / buyer / product start events
        if key == "planner":
            for ev in event_rows:
                et = str(ev.get("type") or "")
                if et in {
                    "plan.start",
                    "buyer.search",
                    "buyers.import_started",
                    "email.drafting",
                    "account.researching",
                    "product.customers_identified",
                }:
                    detail = ev.get("message") or detail
                    break

        extra = enrich.get(key) or {}
        progress = extra.get("progress") or _parse_progress_from_label(count_label)
        items = extra.get("items")
        if extra.get("count_label"):
            count_label = extra["count_label"]

        if status == "idle":
            detail = None
            # keep progress for done-looking idle? Spec: idle clears stream; keep count if present from prior
            if not any(s in {"done", "skipped", "running", "waiting"} for s in statuses):
                count_label = None
                progress = None
                items = None

        agents.append(
            PipelineAgentOut(
                agent=spec["agent"],
                key=key,  # type: ignore[arg-type]
                label=label,
                status=status,  # type: ignore[arg-type]
                detail=detail,
                stream=None,
                count_label=count_label,
                progress=progress,
                items=items,
                started_at=started_at,
                updated_at=updated_at,
            )
        )

    # Planner progress = how many of 5 sub-agents finished
    sub_keys = ["product", "buyers", "accounts", "writer", "sender"]
    done_n = sum(1 for k in sub_keys if statuses_by_key.get(k) == "done")
    for a in agents:
        if a.key == "planner":
            a.progress = PipelineProgressOut(done=done_n, total=5)
            if done_n:
                a.count_label = f"{done_n}/5 jobs"

    return PipelineOut(
        target_mode=target_mode,  # type: ignore[arg-type]
        model=model,
        agents=agents,
    )
