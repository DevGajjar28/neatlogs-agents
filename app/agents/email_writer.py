"""Email writer: v0 writes a single first email per contact (no follow-ups yet)."""

from __future__ import annotations

from typing import Any

from app.llm import get_llm
from app.models import AccountBrief, Contact, EmailDraft, SellerBrief


def email_writer_node(state: dict[str, Any]) -> dict[str, Any]:
    seller = SellerBrief.model_validate(state["seller"])
    contacts = [Contact.model_validate(c) for c in (state.get("contacts") or [])]
    accounts = state.get("accounts") or {}
    events = list(state.get("events") or [])
    errors = list(state.get("errors") or [])
    drafts: dict[str, list[dict]] = {}

    llm = get_llm("fast")
    for contact in contacts:
        account_raw = accounts.get(contact.company_id)
        if not account_raw:
            continue
        account = AccountBrief.model_validate(account_raw)
        evidence_lines = [f"[{e.id}] {e.fact}" for e in account.evidence + seller.evidence[:5]]
        prompt = (
            "Write one cold email (step 1 only). <=120 words. Use only listed evidence. "
            "Put evidence ids in cited_evidence_ids. End with a one-line opt-out. "
            "Return plain text with Subject: on first line, then blank line, then body.\n"
            f"Seller: {seller.company_name} — {seller.one_liner}\n"
            f"Value props: {seller.value_props}\n"
            f"Prospect: {contact.name}, {contact.title} at company_id={contact.company_id}\n"
            f"Account story: {account.story}\n"
            f"Why now: {account.why_now}\n"
            f"Evidence:\n" + "\n".join(evidence_lines)
        )
        try:
            result = llm.invoke(prompt)
            text = getattr(result, "content", str(result))
            if isinstance(text, list):
                text = " ".join(
                    part.get("text", str(part)) if isinstance(part, dict) else str(part) for part in text
                )
            subject, body = _split_email(str(text))
            cited = [e.id for e in account.evidence[:3]]
            draft = EmailDraft(
                step=1,
                subject=subject[:160],
                body=body,
                cited_evidence_ids=cited,
                send_after_days=0,
            )
            drafts[contact.id] = [draft.model_dump(mode="json")]
            events.append({"type": "email.drafted", "contact_id": contact.id})
        except Exception as exc:  # noqa: BLE001
            errors.append({"step": "email_writer", "contact_id": contact.id, "error": str(exc)})

    return {"drafts": drafts, "events": events, "errors": errors}


def _split_email(text: str) -> tuple[str, str]:
    lines = text.strip().splitlines()
    subject = "Quick idea"
    body_lines = lines
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip() or subject
        body_lines = lines[1:]
        if body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
    body = "\n".join(body_lines).strip()
    if "opt-out" not in body.lower() and "unsubscribe" not in body.lower():
        body = body + "\n\nOpt out: reply stop and I will not email again."
    return subject, body
