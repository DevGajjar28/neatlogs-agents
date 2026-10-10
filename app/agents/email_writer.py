"""Email writer: 3-step sequence, evidence-only, role-based tone."""

from __future__ import annotations

import re
from typing import Any, Literal

from app.llm import get_llm
from app.models import AccountBrief, BuyerRole, Contact, EmailDraft, ICPProposal, SellerBrief
from app.infra.events import EventBag

OPT_OUT = "Opt out: reply stop and I will not email again."


def email_writer_node(state: dict[str, Any]) -> dict[str, Any]:
    seller = SellerBrief.model_validate(state["seller"])
    contacts = [Contact.model_validate(c) for c in (state.get("contacts") or [])]
    accounts = state.get("accounts") or {}
    events = EventBag(state, "email_writer")
    errors = list(state.get("errors") or [])
    icp = ICPProposal.model_validate(state["icp"]) if state.get("icp") else None
    roles = {r.kind: r for r in (icp.roles if icp else [])}
    notes = dict((state.get("extras") or {}).get("redraft_notes") or {})
    attempts = dict((state.get("extras") or {}).get("verify_attempts") or {})
    existing = dict(state.get("drafts") or {})
    drafts: dict[str, list[dict]] = dict(existing)

    llm = get_llm("fast")
    for contact in contacts:
        # Skip contacts already passed verification.
        prior = (state.get("verifier") or {}).get(contact.id) or {}
        if prior.get("action") == "pass" and prior.get("passed"):
            continue
        if prior.get("action") in {"drop", "downgrade"} and attempts.get(contact.id, 0) >= 2:
            continue

        account_raw = accounts.get(contact.company_id)
        if not account_raw:
            continue
        account = AccountBrief.model_validate(account_raw)
        role = roles.get(contact.role_kind) or roles.get("economic_buyer")
        tone = _tone_for_role(role)
        evidence_cards = list(account.evidence) + list(seller.evidence[:5])
        evidence_lines = [f"[{e.id}] {e.fact}" for e in evidence_cards]
        allowed_ids = [e.id for e in evidence_cards]
        redraft_note = notes.get(contact.id) or ""

        try:
            sequence = _write_sequence(
                llm,
                seller=seller,
                contact=contact,
                account=account,
                tone=tone,
                evidence_lines=evidence_lines,
                allowed_ids=allowed_ids,
                redraft_note=redraft_note,
            )
            drafts[contact.id] = [d.model_dump(mode="json") for d in sequence]
            events.append(
                {
                    "type": "email.drafted",
                    "contact_id": contact.id,
                    "steps": len(sequence),
                    "attempt": int(attempts.get(contact.id, 0)),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"step": "email_writer", "contact_id": contact.id, "error": str(exc)})

    extras = dict(state.get("extras") or {})
    return {"drafts": drafts, "events": events, "errors": errors, "extras": extras}


def _write_sequence(
    llm,
    *,
    seller: SellerBrief,
    contact: Contact,
    account: AccountBrief,
    tone: str,
    evidence_lines: list[str],
    allowed_ids: list[str],
    redraft_note: str,
) -> list[EmailDraft]:
    specs: list[tuple[Literal[1, 2, 3], int, int]] = [
        (1, 120, 0),
        (2, 70, 3),
        (3, 70, 7),
    ]
    out: list[EmailDraft] = []
    for step, max_words, delay in specs:
        prompt = (
            f"Write cold email step {step} of 3. Max {max_words} words. "
            f"Tone: {tone}. Use ONLY listed evidence; never invent numbers or personal flattery. "
            f"Every factual claim must be grounded in evidence ids from this list: {allowed_ids}. "
            "Return plain text: first line 'Subject: ...', blank line, then body. "
            f"End body with exactly: {OPT_OUT}\n"
        )
        if step > 1:
            prompt += "Add one NEW point; do not say you are bumping or following up empty-handed.\n"
        if redraft_note:
            prompt += f"Verifier notes to fix: {redraft_note}\n"
        prompt += (
            f"Seller: {seller.company_name} — {seller.one_liner}\n"
            f"Value props: {seller.value_props}\n"
            f"Prospect: {contact.name}, {contact.title} at company {contact.company_id}\n"
            f"Account story: {account.story}\n"
            f"Why now: {account.why_now}\n"
            f"Evidence:\n" + "\n".join(evidence_lines)
        )
        result = llm.invoke(prompt)
        text = _content(result)
        subject, body = _split_email(str(text))
        body = _ensure_opt_out(_trim_words(body, max_words))
        cited = _extract_cited_ids(body + " " + subject, allowed_ids) or allowed_ids[:2]
        out.append(
            EmailDraft(
                step=step,
                subject=subject[:160],
                body=body,
                cited_evidence_ids=cited,
                send_after_days=delay,
            )
        )
    return out


def _tone_for_role(role: BuyerRole | None) -> str:
    if role and role.kind == "champion":
        return "day-to-day pain and workflow friction for a champion"
    return "risk, outcomes, and budget impact for an economic buyer"


def _content(result: Any) -> str:
    text = getattr(result, "content", str(result))
    if isinstance(text, list):
        text = " ".join(
            part.get("text", str(part)) if isinstance(part, dict) else str(part) for part in text
        )
    return str(text)


def _split_email(text: str) -> tuple[str, str]:
    lines = text.strip().splitlines()
    subject = "Quick idea"
    body_lines = lines
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip() or subject
        body_lines = lines[1:]
        if body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
    return subject, "\n".join(body_lines).strip()


def _ensure_opt_out(body: str) -> str:
    low = body.lower()
    if "opt-out" in low or "opt out" in low or "unsubscribe" in low:
        return body
    return (body.rstrip() + "\n\n" + OPT_OUT).strip()


def _trim_words(body: str, max_words: int) -> str:
    words = body.split()
    if len(words) <= max_words:
        return body
    # Keep opt-out if present at end
    trimmed = " ".join(words[:max_words])
    return _ensure_opt_out(trimmed)


def _extract_cited_ids(text: str, allowed: list[str]) -> list[str]:
    found = re.findall(r"ev_[a-f0-9]+", text, flags=re.I)
    out: list[str] = []
    for item in found:
        if item in allowed and item not in out:
            out.append(item)
    return out
