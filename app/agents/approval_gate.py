"""Human gate 2: approve/edit/reject verified email drafts before send."""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from app.infra.audit import write_audit
from app.tools.mailer import lead_id_for
from app.infra.events import EventBag


def _approval_items(
    contacts: dict[str, dict],
    drafts: dict[str, Any],
    verifier: dict[str, Any],
    campaign_id: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
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
    return items


def approval_gate_node(state: dict[str, Any]) -> dict[str, Any]:
    """Interrupt with draft queue; resume with per-contact approvals."""
    campaign_id = state["campaign_id"]
    contacts = {c["id"]: c for c in (state.get("contacts") or []) if isinstance(c, dict)}
    drafts = state.get("drafts") or {}
    verifier = state.get("verifier") or {}
    events = EventBag(state, "approval_gate")
    items = _approval_items(contacts, drafts, verifier, campaign_id)

    if not items:
        events.append({"type": "approval.empty_queue"})
        plan = dict(state.get("plan") or {})
        plan["phase"] = "after_email"
        return {"events": events, "plan": plan, "extras": dict(state.get("extras") or {})}

    payload = {
        "type": "email_approval",
        "campaign_id": campaign_id,
        "items": items,
        "message": "Approve this campaign once to send every verified draft.",
    }
    from app.infra.events import set_stage

    set_stage(campaign_id, "approval", "waiting")
    decision = interrupt(payload)
    set_stage(campaign_id, "approval", "done")
    if not isinstance(decision, dict):
        decision = {"approvals": {}}

    approvals = dict(decision.get("approvals") or {})
    guessed_skipped = 0

    # Convenience: approve_all — never auto-allow guessed addresses.
    if decision.get("approve_all"):
        include_guessed = bool(decision.get("include_guessed"))
        for item in items:
            cid = item["contact_id"]
            if cid in approvals:
                continue
            if item.get("email_confidence") == "guessed":
                if include_guessed:
                    approvals[cid] = {"approved": True, "allow_guessed": True}
                else:
                    approvals[cid] = {"approved": False}
                    guessed_skipped += 1
            else:
                approvals[cid] = {"approved": True}

    extras = dict(state.get("extras") or {})
    extras["email_approvals"] = approvals
    updated_drafts = dict(drafts)

    for item in items:
        cid = item["contact_id"]
        choice = approvals.get(cid) or {"approved": False}
        approved = bool(choice.get("approved"))
        if (
            approved
            and item.get("email_confidence") == "guessed"
            and not choice.get("allow_guessed")
        ):
            approved = False
            guessed_skipped += 1
            approvals[cid] = {**choice, "approved": False}
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
            events.append(
                {
                    "type": "approval.approved",
                    "contact_id": cid,
                    "lead_id": lead_id,
                    "contact": item.get("name"),
                }
            )
        else:
            write_audit(
                actor=str(decision.get("actor") or "human"),
                action="reject",
                target=lead_id,
                details={"contact_id": cid},
            )
            events.append(
                {
                    "type": "approval.rejected",
                    "contact_id": cid,
                    "lead_id": lead_id,
                    "contact": item.get("name"),
                }
            )

    if guessed_skipped:
        events.append({"type": "policy.guessed_skipped", "count": guessed_skipped})

    plan = dict(state.get("plan") or {})
    plan["phase"] = "after_approval"
    return {
        "drafts": updated_drafts,
        "events": events,
        "extras": extras,
        "plan": plan,
    }
