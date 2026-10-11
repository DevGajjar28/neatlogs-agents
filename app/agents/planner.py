"""Main planner: budgets credits and routes between stages (deterministic)."""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.infra.budget import estimate_campaign
from app.infra.db import connect, init_db
from app.infra.events import EventBag
from app.models import Company, ICPProposal

# Adjacent size bands used when widening a thin ICP search.
_RANGE_NEIGHBORS: dict[str, list[str]] = {
    "1-10": ["11-50"],
    "11-50": ["1-10", "51-200"],
    "51-200": ["11-50", "201-500"],
    "201-500": ["51-200", "501-1000"],
    "501-1000": ["201-500", "1001-5000"],
    "1001-5000": ["501-1000", "5001-10000"],
    "5001-10000": ["1001-5000", "10001+"],
    "10001+": ["5001-10000"],
}


def estimate_credits(n: int, *, target_mode: str = "discover") -> float:
    """Rough credit estimate for an N-lead campaign (delegates to budget.estimate_campaign)."""
    return float(estimate_campaign(n, mode="live", target_mode=target_mode)["total"])


def _check_pause(campaign_id: str) -> bool:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT pause_requested FROM campaigns WHERE id = ?",
            (campaign_id,),
        ).fetchone()
        return bool(row and int(row["pause_requested"] or 0) == 1)
    finally:
        conn.close()


def _clear_pause(campaign_id: str, stage: str | None) -> None:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            UPDATE campaigns
            SET pause_requested = 0, status = 'paused', current_stage = COALESCE(?, current_stage)
            WHERE id = ?
            """,
            (stage, campaign_id),
        )
        conn.commit()
    finally:
        conn.close()


def planner_node(state: dict[str, Any]) -> dict[str, Any]:
    """Decide next node; emit plan / replan / halt events."""
    events = EventBag(state, "planner")
    plan = dict(state.get("plan") or {})
    input_data = dict(state.get("input") or {})
    n = int(input_data.get("n") or 10)
    settings = get_settings()
    max_credits = int(settings.max_credits)
    spent = float((state.get("budget") or {}).get("credits_spent") or 0)
    updates: dict[str, Any] = {}

    target_mode = str(
        input_data.get("target_mode") or plan.get("target_mode") or "discover"
    )
    if not plan.get("initialized"):
        estimate = estimate_credits(n, target_mode=target_mode)
        buyer_step = "buyer_import" if target_mode == "provided" else "buyer_search"
        if target_mode == "provided":
            steps = [
                "product_researcher",
                "buyer_import",
                "account_researcher",
                "email_writer",
            ]
            rationale = f"Plan for N={n}: product → import your list → account → email"
        else:
            steps = [
                "product_researcher",
                "buyer_propose_icp",
                "icp_gate",
                buyer_step,
                "account_researcher",
                "email_writer",
            ]
            rationale = f"Plan for N={n}: product → ICP gate → search → account → email"
        plan.update(
            {
                "initialized": True,
                "version": "v0.4",
                "widenings": 0,
                "max_widenings": 0 if target_mode == "provided" else 2,
                "estimated_credits": estimate,
                "max_credits": max_credits,
                "phase": "init",
                "target_mode": target_mode,
                "steps": steps,
                "rationale": rationale,
            }
        )
        if estimate > max_credits:
            reduced = max(1, int(n * max_credits / max(estimate, 1)))
            events.append(
                {
                    "type": "plan.reduce_n",
                    "from_n": n,
                    "to_n": reduced,
                    "estimated_credits": estimate,
                    "max_credits": max_credits,
                }
            )
            n = reduced
            input_data["n"] = reduced
            updates["input"] = input_data
            plan["rationale"] = f"Reduced N to {reduced} so estimate fits MAX_CREDITS={max_credits}"
        events.append(
            {
                "type": "plan.start",
                "n": n,
                "estimated_credits": plan["estimated_credits"],
                "max_credits": max_credits,
            }
        )
        plan["phase"] = "need_product"
        plan["next"] = "product_researcher"
        updates["plan"] = plan
        updates["events"] = events
        return updates

    if state.get("halt_reason"):
        plan["next"] = "done"
        updates["plan"] = plan
        updates["events"] = events
        return updates

    phase = plan.get("phase") or "init"
    campaign_id = str(state.get("campaign_id") or "")
    if campaign_id and _check_pause(campaign_id):
        stage = str(plan.get("next") or phase or "plan")
        events.append({"type": "halt.paused", "stage": stage})
        _clear_pause(campaign_id, stage)
        plan["next"] = "done"
        updates["plan"] = plan
        updates["events"] = events
        updates["halt_reason"] = "paused"
        return updates


    # Budget gate: stop new enrichment at 90%; finish already-kept companies if search done.
    if spent >= 0.9 * max_credits and phase not in ("after_account", "after_email", "done"):
        if phase == "after_search" and state.get("companies"):
            events.append(
                {
                    "type": "halt.budget",
                    "spent": spent,
                    "max_credits": max_credits,
                    "action": "finish_paid_leads",
                }
            )
            plan["next"] = "account_researcher"
            updates["plan"] = plan
            updates["events"] = events
            return updates
        events.append(
            {
                "type": "halt.budget_exhausted",
                "spent": spent,
                "max_credits": max_credits,
            }
        )
        plan["next"] = "done"
        updates["plan"] = plan
        updates["events"] = events
        updates["halt_reason"] = "budget_exhausted"
        return updates

    if phase == "need_product" or (phase == "init" and not state.get("seller")):
        plan["next"] = "product_researcher"
    elif phase == "after_product":
        # Your list: skip ICP propose/gate — titles fall back in account researcher.
        if target_mode == "provided":
            plan["next"] = "buyer_import"
            plan["phase"] = "searching"
        else:
            plan["next"] = "buyer_propose_icp"
            plan["phase"] = "need_icp"
    elif phase == "after_icp_proposed":
        plan["next"] = "icp_gate"
    elif phase == "after_icp_approved":
        plan["next"] = "buyer_import" if target_mode == "provided" else "buyer_search"
        plan["phase"] = "searching"
    elif phase == "after_search":
        kept = [c for c in (state.get("companies") or []) if c.get("status") == "kept"]
        widenings = int(plan.get("widenings") or 0)
        max_widenings = int(plan.get("max_widenings") or 2)
        # User-provided lists never widen / re-search.
        if target_mode == "provided":
            plan["next"] = "account_researcher"
        elif len(kept) < n and widenings < max_widenings:
            widenings += 1
            plan["widenings"] = widenings
            icp = ICPProposal.model_validate(state["icp"])
            widened = widen_icp(icp, widenings)
            events.append(
                {
                    "type": "replan.widen_icp",
                    "widening": widenings,
                    "kept": len(kept),
                    "n": n,
                    "industries": widened.industries,
                    "employee_count_ranges": widened.employee_count_ranges,
                    "countries": widened.countries,
                    "reason": f"kept {len(kept)} < N={n}",
                }
            )
            plan["phase"] = "after_icp_approved"
            plan["next"] = "buyer_search"
            updates["icp"] = widened.model_dump(mode="json")
            updates["companies"] = []
        else:
            if len(kept) < n:
                events.append(
                    {
                        "type": "plan.search_thin",
                        "kept": len(kept),
                        "n": n,
                        "widenings": widenings,
                        "action": "continue_with_available",
                    }
                )
            plan["next"] = "account_researcher"
    elif phase == "after_account":
        # Drop/replace: promote overfetch buffer into kept slots left empty by no_contact.
        companies = [Company.model_validate(c) for c in (state.get("companies") or [])]
        kept = [c for c in companies if c.status == "kept"]
        buffer = [
            c
            for c in companies
            if c.status == "dropped" and c.drop_reason == "below_top_n"
        ]
        promoted: list[Company] = []
        while len(kept) + len(promoted) < n and buffer:
            nxt = buffer.pop(0)
            nxt.status = "kept"
            nxt.drop_reason = None
            promoted.append(nxt)
        if promoted:
            events.append(
                {
                    "type": "plan.replace_no_contact",
                    "promoted": len(promoted),
                    "company_ids": [c.id for c in promoted],
                    "kept_before": len(kept),
                    "n": n,
                }
            )
            # Rewrite company list with promotions applied.
            by_id = {c.id: c for c in companies}
            for company in promoted:
                by_id[company.id] = company
            updates["companies"] = [c.model_dump(mode="json") for c in by_id.values()]
            plan["next"] = "account_researcher"
            plan["phase"] = "need_account_retry"
        else:
            contacts = state.get("contacts") or []
            if not contacts:
                # No people found — finish run; user can add contacts manually.
                from app.infra.events import set_stage

                if campaign_id:
                    set_stage(
                        campaign_id,
                        "emails",
                        "done",
                        "0 drafts — add a contact",
                    )
                    set_stage(campaign_id, "verify", "skipped")
                    set_stage(campaign_id, "approval", "skipped")
                    set_stage(campaign_id, "send", "skipped")
                events.append(
                    {
                        "type": "plan.no_contacts",
                        "detail": "No contacts found; add a contact to write emails",
                    }
                )
                plan["next"] = "done"
                plan["phase"] = "awaiting_manual_contact"
            else:
                plan["next"] = "email_writer"
    elif phase == "after_email":
        plan["next"] = "done"
        plan["phase"] = "done"
    else:
        # Recover from unexpected phase using available state.
        if not state.get("seller"):
            plan["next"] = "product_researcher"
            plan["phase"] = "need_product"
        elif target_mode == "provided" and not state.get("companies"):
            plan["next"] = "buyer_import"
        elif target_mode != "provided" and not state.get("icp"):
            plan["next"] = "buyer_propose_icp"
        elif target_mode != "provided" and not (state.get("icp") or {}).get("approved"):
            plan["next"] = "icp_gate"
        elif not state.get("companies"):
            plan["next"] = "buyer_import" if target_mode == "provided" else "buyer_search"
        elif not state.get("contacts") and not state.get("accounts"):
            plan["next"] = "account_researcher"
        elif state.get("contacts") and not state.get("drafts"):
            plan["next"] = "email_writer"
        else:
            plan["next"] = "done"

    updates["plan"] = plan
    updates["events"] = events
    return updates


def route_after_planner(state: dict[str, Any]) -> str:
    nxt = (state.get("plan") or {}).get("next") or "done"
    if nxt == "done":
        return "done"
    return str(nxt)


def set_plan_phase(state: dict[str, Any], phase: str) -> dict[str, Any]:
    """Return an updated plan dict with the worker-completed phase."""
    plan = dict(state.get("plan") or {})
    plan["phase"] = phase
    return plan


def widen_icp(icp: ICPProposal, widening: int) -> ICPProposal:
    """Widen ICP: expand size, then add countries, then broaden industries."""
    data = icp.model_copy(deep=True)
    ranges = list(data.employee_count_ranges or [])
    if widening == 1:
        expanded: list[str] = list(ranges)
        for band in ranges:
            for neighbor in _RANGE_NEIGHBORS.get(band, []):
                if neighbor not in expanded:
                    expanded.append(neighbor)
        if not expanded:
            expanded = ["51-200", "201-500", "501-1000"]
        data.employee_count_ranges = expanded
        data.rationale = (data.rationale or "") + f" [widen#{widening}: expanded size bands]"
    else:
        countries = list(data.countries or [])
        for extra_country in ("United States", "United Kingdom", "Canada", "Germany"):
            if extra_country not in countries:
                countries.append(extra_country)
        data.countries = countries
        industries = list(data.industries or [])
        for extra in (
            "Software Development",
            "Technology, Information and Internet",
            "Information Technology and Services",
            "Internet Publishing",
        ):
            if extra not in industries:
                industries.append(extra)
        data.industries = industries
        # Also nudge size once more on second widen
        expanded = list(data.employee_count_ranges or [])
        for band in list(expanded):
            for neighbor in _RANGE_NEIGHBORS.get(band, []):
                if neighbor not in expanded:
                    expanded.append(neighbor)
        data.employee_count_ranges = expanded
        data.rationale = (data.rationale or "") + f" [widen#{widening}: broader geo + industries]"
    return data
