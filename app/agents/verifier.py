"""Verifier: deterministic checks first, then a strict LLM judge; redraft/downgrade/drop."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.evidence_refs import find_refs, strip_refs
from app.infra.events import EventBag
from app.llm import get_llm
from app.models import AccountBrief, Contact, EmailDraft, EvidenceCard, SellerBrief, VerifierResult

BANNED = ("guaranteed", "100%", "no risk", "act now", "limited time", "congratulations")
INJECTION_HINTS = (
    "ignore previous",
    "you are now",
    "system prompt",
    "send all",
    "exfiltrat",
)
MAX_REDRAFTS = 2


class _JudgeOut(BaseModel):
    passed: bool = False
    unsupported_claims: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


def verifier_node(state: dict[str, Any]) -> dict[str, Any]:
    """Verify all drafts; set route hint in plan.next_verify for graph edges."""
    seller = SellerBrief.model_validate(state["seller"]) if state.get("seller") else None
    contacts = {c["id"]: Contact.model_validate(c) for c in (state.get("contacts") or []) if isinstance(c, dict)}
    accounts = state.get("accounts") or {}
    drafts = state.get("drafts") or {}
    events = EventBag(state, "verifier")
    errors = list(state.get("errors") or [])
    verifier: dict[str, Any] = dict(state.get("verifier") or {})
    extras = dict(state.get("extras") or {})
    attempts = dict(extras.get("verify_attempts") or {})
    notes = dict(extras.get("redraft_notes") or {})

    any_redraft = False
    all_terminal = True

    for contact_id, sequence in drafts.items():
        contact = contacts.get(contact_id)
        if not contact or not sequence:
            continue
        prior = verifier.get(contact_id) or {}
        if prior.get("action") == "pass" and prior.get("passed"):
            continue

        account_raw = accounts.get(contact.company_id) or {}
        try:
            account = AccountBrief.model_validate(account_raw)
        except Exception:  # noqa: BLE001
            account = None
        evidence = list(account.evidence if account else [])
        if seller:
            evidence.extend(seller.evidence[:5])

        step1 = EmailDraft.model_validate(sequence[0])
        attempt = int(attempts.get(contact_id, 0))
        result = verify_draft(
            step1,
            evidence=evidence,
            contact=contact,
            use_llm=True,
        )

        cited = len(step1.cited_evidence_ids or [])
        events.append(
            {
                "type": "verifier.checked",
                "contact": contact.name,
                "contact_id": contact_id,
                "n": cited,
                "total": max(cited, 1),
            }
        )
        if result.action == "pass":
            verifier[contact_id] = result.model_dump(mode="json")
            events.append(
                {
                    "type": "verify.pass",
                    "contact_id": contact_id,
                    "contact": contact.name,
                    "attempt": attempt,
                }
            )
            notes.pop(contact_id, None)
            continue

        # Fail path
        events.append(
            {
                "type": "verify.reject",
                "contact_id": contact_id,
                "contact": contact.name,
                "attempt": attempt,
                "issues": result.issues,
                "unsupported_claims": result.unsupported_claims,
            }
        )

        if attempt + 1 < MAX_REDRAFTS and result.action == "redraft":
            attempts[contact_id] = attempt + 1
            notes[contact_id] = "; ".join(result.issues + result.unsupported_claims)[:500]
            verifier[contact_id] = result.model_dump(mode="json")
            events.append({"type": "verify.redraft", "contact_id": contact_id, "attempt": attempt + 1})
            any_redraft = True
            all_terminal = False
            continue

        # Downgrade once, then drop
        if result.action in {"redraft", "downgrade"} and attempt + 1 >= MAX_REDRAFTS:
            downgraded = _downgrade_draft(step1, evidence)
            downgrade_result = verify_draft(
                downgraded,
                evidence=evidence,
                contact=contact,
                use_llm=False,
            )
            if downgrade_result.passed:
                sequence[0] = downgraded.model_dump(mode="json")
                drafts[contact_id] = sequence
                downgrade_result.action = "downgrade"
                verifier[contact_id] = downgrade_result.model_dump(mode="json")
                events.append({"type": "verify.downgrade", "contact_id": contact_id})
                notes.pop(contact_id, None)
                continue

        drop = VerifierResult(
            passed=False,
            unsupported_claims=result.unsupported_claims,
            stale_evidence_ids=result.stale_evidence_ids,
            issues=result.issues + ["max redrafts exceeded"],
            action="drop",
        )
        verifier[contact_id] = drop.model_dump(mode="json")
        events.append({"type": "verify.drop", "contact_id": contact_id})
        notes.pop(contact_id, None)
        attempts[contact_id] = attempt + 1

    extras["verify_attempts"] = attempts
    extras["redraft_notes"] = notes
    plan = dict(state.get("plan") or {})
    if any_redraft:
        plan["next_verify"] = "redraft"
    elif all_terminal or drafts:
        plan["next_verify"] = "pass"
        plan["phase"] = "awaiting_approval"
    else:
        plan["next_verify"] = "pass"
        plan["phase"] = "awaiting_approval"

    # Guessed emails always flagged for human approval later.
    for contact_id, contact in contacts.items():
        if contact.email_confidence == "guessed":
            events.append(
                {
                    "type": "verify.guessed_email_warning",
                    "contact_id": contact_id,
                    "badge": "awaiting_approval",
                }
            )

    return {
        "drafts": drafts,
        "verifier": verifier,
        "events": events,
        "errors": errors,
        "extras": extras,
        "plan": plan,
    }


def route_after_verifier(state: dict[str, Any]) -> Literal["email_writer", "approval_gate"]:
    nxt = (state.get("plan") or {}).get("next_verify") or "pass"
    if nxt == "redraft":
        return "email_writer"
    return "approval_gate"


def verify_draft(
    draft: EmailDraft,
    *,
    evidence: list[EvidenceCard],
    contact: Contact,
    use_llm: bool = True,
) -> VerifierResult:
    by_id = {e.id: e for e in evidence}
    issues: list[str] = []
    unsupported: list[str] = []
    stale: list[str] = []
    body_low = draft.body.lower()

    # 0) Internal evidence ids must never appear in outbound copy
    if find_refs(f"{draft.subject}\n{draft.body}"):
        issues.append("internal_ref")

    # 1) cited ids exist
    for eid in draft.cited_evidence_ids:
        if eid not in by_id:
            issues.append(f"unknown_citation:{eid}")

    # 1b) Structured claims: text must appear in body; ids must exist
    for claim in draft.claims or []:
        phrase = (claim.text or "").strip()
        if not phrase:
            continue
        if phrase.lower() not in body_low:
            issues.append(f"claim_missing_from_body:{phrase[:40]}")
        for eid in claim.evidence_ids:
            if eid not in by_id:
                issues.append(f"unknown_citation:{eid}")
            else:
                if eid not in draft.cited_evidence_ids:
                    # keep cited list in sync for downstream
                    pass

    # 2) stale "recent" claims
    cutoff = date_days_ago(90)
    claims_recent = any(w in body_low for w in ("recent", "this week", "today", "just announced", "why now"))
    for eid in draft.cited_evidence_ids:
        card = by_id.get(eid)
        if not card:
            continue
        if claims_recent and card.observed_at and card.observed_at < cutoff:
            stale.append(eid)
            issues.append(f"stale_evidence:{eid}")

    # 3) name/title/company consistency (soft)
    if contact.name and contact.name.split()[0].lower() not in body_low and contact.name.lower() not in body_low:
        pass
    for token in re.findall(r"\b[A-Z][a-z]+\b", draft.body):
        if token.lower() in {"opt", "subject", "hi", "hello", "thanks"}:
            continue
    if "dear " in body_low:
        pass

    # 5/6) injection residue, length, opt-out, banned
    for hint in INJECTION_HINTS:
        if hint in body_low:
            issues.append(f"injection_residue:{hint}")
    words = draft.body.split()
    max_words = 120 if draft.step == 1 else 70
    if len(words) > max_words + 15:  # small slack for opt-out line
        issues.append(f"too_long:{len(words)}>{max_words}")
    if (
        "opt-out" not in body_low
        and "opt out" not in body_low
        and "unsubscribe" not in body_low
        and 'reply "stop"' not in body_low
        and "won't email again" not in body_low
        and "wont email again" not in body_low
    ):
        issues.append("missing_opt_out")
    for phrase in BANNED:
        if phrase in body_low:
            issues.append(f"banned_phrase:{phrase}")

    # 4) LLM judge for factual support (also covers sentences without claims)
    if use_llm and not issues:
        judge = _llm_judge(draft, evidence, contact)
        if not judge.passed:
            unsupported.extend(judge.unsupported_claims)
            issues.extend(judge.issues or ["llm_unsupported_claims"])

    passed = not issues and not unsupported and not stale
    if passed:
        action: Literal["pass", "redraft", "downgrade", "drop"] = "pass"
    elif any(
        i.startswith("unknown_citation")
        or i.startswith("injection")
        or i == "internal_ref"
        for i in issues
    ):
        action = "redraft"
    elif stale or unsupported:
        action = "downgrade"
    else:
        action = "redraft"

    return VerifierResult(
        passed=passed,
        unsupported_claims=unsupported,
        stale_evidence_ids=stale,
        issues=issues,
        action=action,
    )


def _llm_judge(draft: EmailDraft, evidence: list[EvidenceCard], contact: Contact) -> _JudgeOut:
    cards = "\n".join(f"[{e.id}] {e.fact}" for e in evidence)
    prompt = (
        "You are a strict email fact verifier. Return whether EVERY factual claim in the email "
        "is supported by the cited evidence cards. Be harsh: inventing customers, metrics, or "
        "news fails. Greeting and opt-out do not need citations.\n"
        f"Prospect: {contact.name} / {contact.title}\n"
        f"Subject: {draft.subject}\nBody:\n{draft.body}\n"
        f"Cited ids: {draft.cited_evidence_ids}\nEvidence:\n{cards}\n"
    )
    try:
        llm = get_llm("strong")
        out = llm.with_structured_output(_JudgeOut).invoke(prompt)
        if isinstance(out, _JudgeOut):
            return out
        return _JudgeOut.model_validate(out)
    except Exception as exc:  # noqa: BLE001
        # If judge unavailable, do not block on LLM — deterministic checks already ran.
        return _JudgeOut(passed=True, issues=[f"judge_skipped:{exc}"[:120]])


def _downgrade_draft(draft: EmailDraft, evidence: list[EvidenceCard]) -> EmailDraft:
    """Remove sentences that reference unknown/stale ids; keep opt-out."""
    from app.agents.email_writer import OPT_OUT

    allowed = {e.id for e in evidence}
    lines = []
    for line in draft.body.splitlines():
        ids = find_refs(line)
        if ids and any(i not in allowed for i in ids):
            continue
        lines.append(strip_refs(line))
    body = "\n".join(lines).strip()
    body = strip_refs(body)
    low = body.lower()
    if (
        "opt-out" not in low
        and "opt out" not in low
        and "unsubscribe" not in low
        and 'reply "stop"' not in low
    ):
        body = body + "\n\n" + OPT_OUT
    cited = [i for i in draft.cited_evidence_ids if i in allowed]
    claims = [
        c
        for c in (draft.claims or [])
        if all(eid in allowed for eid in c.evidence_ids) and c.text.lower() in body.lower()
    ]
    return EmailDraft(
        step=draft.step,
        subject=strip_refs(draft.subject),
        body=body,
        cited_evidence_ids=cited or list(allowed)[:1],
        send_after_days=draft.send_after_days,
        claims=claims,
    )


def date_days_ago(days: int) -> date:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date()
