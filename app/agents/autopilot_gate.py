"""Autopilot gate: auto-approve verifier-passed drafts (no interrupt)."""

from __future__ import annotations

from typing import Any

from app.agents.approval_gate import _approval_items
from app.infra.audit import write_audit
from app.infra.events import EventBag
def autopilot_gate_node(state: dict[str, Any]) -> dict[str, Any]:
    """Same queue as approval_gate but system approves (never guessed without flag)."""
    campaign_id = state["campaign_id"]
    contacts = {c["id"]: c for c in (state.get("contacts") or []) if isinstance(c, dict)}
    drafts = state.get("drafts") or {}
    verifier = state.get("verifier") or {}
    events = EventBag(state, "autopilot_gate")
    items = _approval_items(contacts, drafts, verifier, campaign_id)

    if not items:
        events.append({"type": "approval.empty_queue"})
        plan = dict(state.get("plan") or {})
        plan["phase"] = "after_email"
        return {"events": events, "plan": plan, "extras": dict(state.get("extras") or {})}

    approvals: dict[str, Any] = {}
    guessed_skipped = 0
    for item in items:
        cid = item["contact_id"]
        if item.get("email_confidence") == "guessed":
            approvals[cid] = {"approved": False}
            guessed_skipped += 1
            continue
        approvals[cid] = {"approved": True}
        lead_id = item["lead_id"]
        write_audit(
            actor="autopilot",
            action="autopilot_approve",
            target=lead_id,
            details={
                "contact_id": cid,
                "cited_evidence_ids": item.get("cited_evidence_ids"),
            },
        )
        events.append(
            {
                "type": "approval.autopilot_approved",
                "contact_id": cid,
                "lead_id": lead_id,
                "contact": item.get("name"),
            }
        )

    if guessed_skipped:
        events.append({"type": "policy.guessed_skipped", "count": guessed_skipped})

    extras = dict(state.get("extras") or {})
    extras["email_approvals"] = approvals
    plan = dict(state.get("plan") or {})
    plan["phase"] = "after_approval"
    return {
        "events": events,
        "extras": extras,
        "plan": plan,
    }
