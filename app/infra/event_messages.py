"""Founder-readable message templates for activity timeline events."""

from __future__ import annotations

from typing import Any

# type -> str.format template (unknown keys ignored via safe_format)
TEMPLATES: dict[str, str] = {
    "plan.start": "Campaign started for up to {n} leads.",
    "planner.assigned": 'Handed "{task}" to {agent}.',
    "plan.reduce_n": "Budget tight — reducing target leads to {n}.",
    "plan.search_thin": "Company search was thin; planner may widen the ICP.",
    "plan.replace_no_contact": "Some companies had no contact; promoting buffer companies.",
    "plan.no_contacts": "No contacts found. Add a contact on a company row to write emails.",
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
    "icp.auto_approved": "ICP auto-approved — starting company search.",
    "icp.rejected": "ICP rejected; campaign halted.",
    "buyer.search": "Searching lookalikes ({strategy}) — {count} companies returned.",
    "buyer.kept": "Kept {count} best-fit companies after scoring.",
    "buyers.import_started": "Using your list of {n} companies instead of searching.",
    "buyers.import_matched": "Matched {company} ({domain}).",
    "buyers.import_not_found": "Couldn't find {domain} in Crustdata, skipping it.",
    "buyers.import_done": "{matched} of {n} companies from your list are ready for research.",
    "account.researching": "Researching {company} — pulling tech stack + headcount",
    "account.contact_found": "Found {role} at {company} ({confidence})",
    "email.drafting": "Writing first email to {contact} at {company}",
    "verifier.checked": "Verified {n}/{total} claims in draft for {contact}",
    "buyer.search_failed": "Company search failed: {detail}.",
    "buyer.data_error": "Buyer data step failed: {detail}.",
    "account.skip_non_buyer": "Skipped non-buyer title for company contact.",
    "account.enriched": "Enriched {count} companies — tech stack and headcount loaded.",
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
    "email.drafted": "Drafted 3-step sequence for {contact} at {company}.",
    "writer.refs_stripped": "Removed {count} internal evidence id(s) from a draft.",
    "verify.pass": "Verifier passed draft for {contact}.",
    "verify.reject": "Verifier rejected draft for {contact}.",
    "verify.redraft": "Asking writer to redraft for {contact}.",
    "verify.downgrade": "Downgraded draft to safer claims for {contact}.",
    "verify.drop": "Dropped {contact} after failed verification.",
    "verify.guessed_email_warning": "Draft uses a guessed email — confirm before send.",
    "approval.empty_queue": "No drafts waiting for approval.",
    "approval.approved": "Approved draft for {contact} — ready to send.",
    "approval.rejected": "Rejected draft for {contact}.",
    "send.step1": "Sent first email to {contact}.",
    "send.scheduled": "Scheduled follow-up for {contact}.",
    "send.denied": "Send denied: {reason}.",
    "mail.sent": "Email sent via Gmail SMTP.",
    "mail.drafted": "Draft saved to Gmail Drafts.",
    "mail.unknown_delivery": "Delivery uncertain — check Gmail Sent before retrying.",
    "mail.reply_detected": "Reply detected; follow-ups cancelled.",
    "mail.opt_out": "Opt-out detected; address suppressed.",
    "mail.bounce": "Bounce detected; address suppressed.",
    "mail.out_of_office": "Out-of-office reply ignored.",
    "policy.finance_skipped": "Skipped a finance/OTP message (body never opened).",
    "reply.draft_ready": "Reply draft waiting for your approval.",
    "reply.draft_sent": "Approved reply sent.",
    "reply.draft_rejected": "Reply draft rejected.",
    "meeting.proposed": "Meeting slots proposed for your confirmation.",
    "meeting.calendar_created": "Meeting added to Google Calendar.",
    "meeting.calendar_failed": "Could not add meeting to Google Calendar.",
    "mail.agent_disconnected": "Inbox agent disconnected; app password removed.",
    "mail.account_paused": "Mail account auto-paused for safety.",
    "policy.sending_paused": "Sending paused globally.",
    "policy.mode_not_allowed": "Send mode not allowed for this environment.",
    "policy.account_unavailable": "Mail account unavailable.",
    "policy.not_approved": "Email not approved or not verified.",
    "policy.bad_envelope": "Invalid recipients (one To only).",
    "policy.suppressed": "Recipient is suppressed.",
    "policy.guessed_blocked": "Guessed email blocked in live mode.",
    "policy.role_address": "Role address blocked.",
    "policy.test_recipient_missing": "No test recipient allowlisted.",
    "policy.cap_reached": "Account daily send cap reached.",
    "policy.domain_cap_reached": "Per-domain send cap reached.",
    "policy.rate_spaced": "Waiting for send gap before next email.",
    "policy.duplicate": "Duplicate send blocked.",
    "policy.lead_closed": "Lead already replied or opted out.",
    "policy.content": "Content policy blocked this email.",
    "policy.live_requirements": "Live send requirements not met.",
    "policy.outside_window": "Outside sending window; rescheduled.",
}


def level_for(event_type: str) -> str:
    if event_type.startswith("halt.") or event_type in {"verify.drop"}:
        return "danger"
    if event_type.startswith("recovery.") or event_type in {"verify.redraft"}:
        return "warning"
    if event_type.startswith("fallback.") or event_type.startswith("policy.") or event_type.startswith("security."):
        return "neutral"
    if event_type.startswith("done.") or event_type in {
        "verify.pass",
        "send.step1",
        "icp.approved",
        "icp.auto_approved",
        "approval.approved",
    }:
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
