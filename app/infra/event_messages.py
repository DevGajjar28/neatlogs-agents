"""Founder-readable message templates for activity timeline events."""

from __future__ import annotations

from typing import Any

# type -> str.format template (unknown keys ignored via safe_format)
TEMPLATES: dict[str, str] = {
    "plan.start": "Campaign started for up to {n} leads.",
    "plan.reduce_n": "Budget tight — reducing target leads to {n}.",
    "plan.search_thin": "Company search was thin; planner may widen the ICP.",
    "plan.replace_no_contact": "Some companies had no contact; promoting buffer companies.",
    "replan.widen_icp": "Widening ICP (attempt {widening}) to find more companies.",
    "halt.budget": "Stopped: next step would exceed the credit cap.",
    "halt.budget_exhausted": "Stopped: credit budget exhausted.",
    "halt.paused": "Paused by you. Resume to continue from {stage}.",
    "product.customers_identified": "Identified {count} named customers from the seller site.",
    "product.no_customers": "No named customers found; ICP will be lower confidence.",
    "security.injection_quarantined": "Quarantined instruction-like text from a researched page.",
    "error": "Error in {step}: {detail}",
    "buyer.narrow_icp": "Forced a narrow ICP for replan testing.",
    "buyer.icp_proposed": "Proposed an ICP from customer evidence.",
    "icp.approved": "ICP approved{edited}.",
    "icp.rejected": "ICP rejected; campaign halted.",
    "buyer.search": "Company search ({strategy}) returned {count} rows.",
    "buyer.kept": "Kept {count} companies after scoring.",
    "account.enriched": "Enriched {count} companies.",
    "chaos.empty_people": "Chaos: emptied enrich people for testing fallbacks.",
    "chaos.kill_after": "Chaos kill armed after node {after_node}.",
    "account.person_enrich_batch": "Person enrich batch of {count} profiles.",
    "policy.redacted": "Skipped a redacted person (do not contact).",
    "policy.guessed_skipped": "Skipped {count} guessed email(s) pending confirmation.",
    "account.no_contact": "No contact found yet for a company.",
    "fallback.contact_step_1": "Contact fallback step 1 (enrich people).",
    "fallback.contact_step_2": "Contact fallback step 2 (person search).",
    "fallback.contact_step_3": "Contact fallback step 3 (live search) attempted.",
    "fallback.contact_step_4": "Contact fallback step 4 (email pattern guess).",
    "fallback.skipped_not_enabled": "Skipped a contact step — endpoint disabled on this plan.",
    "recovery.explain_retry": "Person search for {company_id} came back empty; filters were relaxed for a retry.",
    "recovery.llm_bad_json": "LLM returned bad JSON at {step}; used a safe fallback.",
    "recovery.send_retry": "Send failed for a lead; will retry policy allowing.",
    "account.news_web_fallback": "Used web news search for why-now.",
    "account.mx_fail": "MX check failed for guessed email domain.",
    "account.email_guessed": "Guessed a pattern email (needs human confirm).",
    "email.drafted": "Drafted a 3-step sequence for a contact.",
    "verify.pass": "Verifier passed a draft.",
    "verify.reject": "Verifier rejected a draft.",
    "verify.redraft": "Asking writer to redraft.",
    "verify.downgrade": "Downgraded draft to safer claims.",
    "verify.drop": "Dropped a lead after failed verification.",
    "verify.guessed_email_warning": "Draft uses a guessed email — confirm before send.",
    "approval.empty_queue": "No drafts waiting for approval.",
    "approval.approved": "Approved a draft for send.",
    "approval.rejected": "Rejected a draft.",
    "send.step1": "Sent step-1 email.",
    "send.scheduled": "Scheduled a follow-up.",
    "send.denied": "Send denied: {reason}.",
}


def level_for(event_type: str) -> str:
    if event_type.startswith("halt.") or event_type in {"verify.drop"}:
        return "danger"
    if event_type.startswith("recovery.") or event_type in {"verify.redraft"}:
        return "warning"
    if event_type.startswith("fallback.") or event_type.startswith("policy.") or event_type.startswith("security."):
        return "neutral"
    if event_type.startswith("done.") or event_type in {"verify.pass", "send.step1", "icp.approved", "approval.approved"}:
        return "success"
    return "info"


def format_message(event_type: str, data: dict[str, Any]) -> str:
    template = TEMPLATES.get(event_type)
    if not template:
        return f"Event {event_type}."
    safe = {k: ("" if v is None else v) for k, v in data.items()}
    if "edited" not in safe and "edited_by_user" in safe:
        safe["edited"] = " (with your edits)" if safe["edited_by_user"] else ""
    try:
        return template.format_map(_Default(safe))
    except Exception:
        return f"Event {event_type}."


class _Default(dict):
    def __missing__(self, key: str) -> str:
        return ""
