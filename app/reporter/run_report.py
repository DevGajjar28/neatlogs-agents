"""Run metrics from the local ledger and campaign state (v0 markdown report)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.infra.budget import BudgetLedger


def write_v0_report(
    state: dict[str, Any],
    *,
    wall_seconds: float,
    path: Path | None = None,
) -> Path:
    settings = get_settings()
    campaign_id = state["campaign_id"]
    ledger = BudgetLedger(settings.db_path)
    credits = ledger.spent(campaign_id)
    companies = state.get("companies") or []
    contacts = state.get("contacts") or []
    drafts = state.get("drafts") or {}
    errors = state.get("errors") or []
    events = state.get("events") or []

    draft_count = sum(len(v) for v in drafts.values())
    # Hand-count placeholder: v0 has no verifier; flag drafts with zero citations
    unsupportedish = 0
    for seq in drafts.values():
        for draft in seq:
            if not draft.get("cited_evidence_ids"):
                unsupportedish += 1

    out = path or Path("reports") / "v0.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SignalSDR v0 run report",
        "",
        f"- campaign_id: `{campaign_id}`",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- seller: {(state.get('input') or {}).get('company_name')}",
        f"- n: {(state.get('input') or {}).get('n')}",
        f"- data_mode: {(state.get('input') or {}).get('mode')}",
        f"- wall_clock_seconds: {wall_seconds:.1f}",
        f"- crustdata_credits_spent: {credits}",
        f"- companies_kept: {len(companies)}",
        f"- contacts_found: {len(contacts)}",
        f"- drafts_written: {draft_count}",
        f"- drafts_missing_citations: {unsupportedish}",
        f"- errors: {len(errors)}",
        f"- events: {len(events)}",
        "",
        "## Notes",
        "",
        "- v0 is linear: no planner, no verifier, no contact fallback chain, one email per contact.",
        "- Token / LLM cost: read from the neatlogs `outbound-v0` (or run) trace in the dashboard.",
        "- Unsupported claims: counted here as drafts with empty `cited_evidence_ids`; spot-check bodies by hand for the Gate 1 comparison.",
        "",
        "## Events (truncated)",
        "",
        "```json",
        json.dumps(events[:40], indent=2, default=str),
        "```",
        "",
        "## Errors",
        "",
        "```json",
        json.dumps(errors[:40], indent=2, default=str),
        "```",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
