"""Human gate 2: approve/edit/reject verified email drafts before send."""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from app.infra.audit import write_audit
from app.tools.mailer import lead_id_for


def approval_gate_node(state: dict[str, Any]) -> dict[str, Any]:
    """Interrupt with draft queue; resume with per-contact approvals."""
    campaign_id = state["campaign_id"]
    contacts = {c["id"]: c for c in (state.get("contacts") or []) if isinstance(c, dict)}
    drafts = state.get("drafts") or {}
    verifier = state.get("verifier") or {}
    events = list(state.get("events") or [])
    items = []

    for contact_id, sequence in drafts.items():
        v = verifier.get(contact_id) or {}
        if not v.get("passed") and v.get("action") not in {"pass", "downgrade"}:
            continue
        contact = contacts.get(contact_id) or {}
        lead_id = lead_id_for(campaign_id, contact_id)
        step1 = sequence[0] if sequence else {}
        items.append(
            {
                "contact_id": contact_id,
                "lead_id": lead_id,
                "name": contact.get("name"),
                "title": contact.get("title"),
                "email": contact.get("email"),
                "email_confidence": contact.get("email_confidence"),
                "company_id": contact.get("company_id"),
                "verifier": v,
                "draft": step1,
                "sequence_steps": [d.get("step") for d in sequence],
                "cited_evidence_ids": step1.get("cited_evidence_ids") or [],
            }
        )

    if not items:
        events.append({"type": "approval.empty_queue"})
        plan = dict(state.get("plan") or {})
        plan["phase"] = "after_email"
        return {"events": events, "plan": plan, "extras": dict(state.get("extras") or {})}

    payload = {
        "type": "email_approval",
        "campaign_id": campaign_id,
        "items": items,
        "message": "Approve, edit, or reject verified drafts before send.",
    }
    decision = interrupt(payload)
    if not isinstance(decision, dict):
        decision = {"approvals": {}}

    approvals = decision.get("approvals") or {}
    # Convenience: approve_all
    if decision.get("approve_all"):
        approvals = {
            item["contact_id"]: {
                "approved": True,
                "allow_guessed": True,
            }
            for item in items
        }

    extras = dict(state.get("extras") or {})
    extras["email_approvals"] = approvals
    updated_drafts = dict(drafts)

    for item in items:
        cid = item["contact_id"]
        choice = approvals.get(cid) or {"approved": False}
        approved = bool(choice.get("approved"))
        lead_id = item["lead_id"]
        if approved:
            seq = list(updated_drafts.get(cid) or [])
            if seq and (choice.get("subject") or choice.get("body")):
                step1 = dict(seq[0])
                if choice.get("subject"):
                    step1["subject"] = choice["subject"]
                if choice.get("body"):
                    step1["body"] = choice["body"]
                seq[0] = step1
                updated_drafts[cid] = seq
                write_audit(
                    actor=str(decision.get("actor") or "human"),
                    action="edit",
                    target=lead_id,
                    details={"contact_id": cid, "fields": ["subject", "body"]},
                )
            write_audit(
                actor=str(decision.get("actor") or "human"),
                action="approve",
                target=lead_id,
                details={
                    "contact_id": cid,
                    "allow_guessed": bool(choice.get("allow_guessed")),
                    "cited_evidence_ids": item.get("cited_evidence_ids"),
                },
            )
            events.append({"type": "approval.approved", "contact_id": cid, "lead_id": lead_id})
        else:
            write_audit(
                actor=str(decision.get("actor") or "human"),
                action="reject",
                target=lead_id,
                details={"contact_id": cid},
            )
            events.append({"type": "approval.rejected", "contact_id": cid, "lead_id": lead_id})

    plan = dict(state.get("plan") or {})
    plan["phase"] = "after_approval"
    return {
        "drafts": updated_drafts,
        "events": events,
        "extras": extras,
        "plan": plan,
    }
