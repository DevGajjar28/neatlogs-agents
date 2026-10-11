"""CRUD + preview for global email style templates."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.api import state_reader
from app.api.schemas import (
    EmailTemplateCreateIn,
    EmailTemplateOut,
    EmailTemplatePreviewIn,
    EmailTemplatePreviewOut,
    EmailTemplatePreviewStepOut,
    EmailTemplateUpdateIn,
)
from app.config import get_settings
from app.infra.db import connect, init_db
from app.infra import email_templates as tpl

router = APIRouter(tags=["email-templates"])


def _out(row: dict[str, Any]) -> EmailTemplateOut:
    return EmailTemplateOut(**row)


@router.get("/email-templates", response_model=list[EmailTemplateOut])
def list_email_templates() -> list[EmailTemplateOut]:
    return [_out(r) for r in tpl.list_templates()]


@router.get("/email-templates/{template_id}", response_model=EmailTemplateOut)
def get_email_template(template_id: str) -> EmailTemplateOut:
    row = tpl.get_template(template_id)
    if not row:
        raise HTTPException(404, detail="Template not found")
    return _out(row)


@router.post("/email-templates", response_model=EmailTemplateOut, status_code=201)
def create_email_template(body: EmailTemplateCreateIn) -> EmailTemplateOut:
    try:
        row = tpl.create_template(
            name=body.name,
            description=body.description or "",
            content_md=body.content_md,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return _out(row)


@router.put("/email-templates/{template_id}", response_model=EmailTemplateOut)
def update_email_template(template_id: str, body: EmailTemplateUpdateIn) -> EmailTemplateOut:
    try:
        row = tpl.update_template(
            template_id,
            name=body.name,
            description=body.description,
            content_md=body.content_md,
        )
    except KeyError as exc:
        raise HTTPException(404, detail="Template not found") from exc
    except PermissionError as exc:
        raise HTTPException(403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return _out(row)


@router.delete("/email-templates/{template_id}", status_code=204)
def delete_email_template(template_id: str) -> None:
    try:
        tpl.delete_template(template_id)
    except KeyError as exc:
        raise HTTPException(404, detail="Template not found") from exc
    except PermissionError as exc:
        raise HTTPException(403, detail=str(exc)) from exc


@router.post("/email-templates/{template_id}/duplicate", response_model=EmailTemplateOut)
def duplicate_email_template(template_id: str) -> EmailTemplateOut:
    try:
        row = tpl.duplicate_template(template_id)
    except KeyError as exc:
        raise HTTPException(404, detail="Template not found") from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return _out(row)


@router.put("/email-templates/{template_id}/default", response_model=EmailTemplateOut)
def set_default_email_template(template_id: str) -> EmailTemplateOut:
    try:
        row = tpl.set_default_template(template_id)
    except KeyError as exc:
        raise HTTPException(404, detail="Template not found") from exc
    return _out(row)


@router.post(
    "/email-templates/{template_id}/preview",
    response_model=EmailTemplatePreviewOut,
)
def preview_email_template(
    template_id: str, body: EmailTemplatePreviewIn
) -> EmailTemplatePreviewOut:
    """Preview 3 steps for one lead using this template. No Crustdata calls; not stored."""
    from app.agents.email_writer import preview_sequence_for_lead
    from app.agents.verifier import verify_draft
    from app.models import AccountBrief, Contact, EmailDraft, EvidenceCard, SellerBrief

    row = tpl.get_template(template_id)
    if not row:
        raise HTTPException(404, detail="Template not found")

    settings = get_settings()
    init_db(settings.db_path)
    campaign_id = body.campaign_id
    contact_id = body.contact_id
    if not campaign_id:
        conn = connect(settings.db_path)
        try:
            crow = conn.execute(
                "SELECT id FROM campaigns ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        if not crow:
            raise HTTPException(422, detail="No campaign available for preview")
        campaign_id = str(crow["id"])

    contacts = [c for c in state_reader.contacts(campaign_id) if isinstance(c, dict)]
    if not contacts:
        raise HTTPException(422, detail="No contacts in campaign for preview")
    contact_raw = None
    if contact_id:
        contact_raw = next((c for c in contacts if c.get("id") == contact_id), None)
    if not contact_raw:
        contact_raw = contacts[0]
    contact = Contact.model_validate(contact_raw)

    accounts = state_reader.accounts(campaign_id)
    account_raw = accounts.get(contact.company_id)
    if not account_raw:
        raise HTTPException(422, detail="No account brief for selected contact")

    seller_raw = state_reader.seller(campaign_id)
    if not seller_raw:
        raise HTTPException(422, detail="No seller brief in campaign for preview")

    companies = {
        c["id"]: c
        for c in state_reader.companies(campaign_id)
        if isinstance(c, dict) and c.get("id")
    }
    company_name = (companies.get(contact.company_id) or {}).get("name") or contact.company_id

    try:
        steps, prompt_preview = preview_sequence_for_lead(
            seller_raw=seller_raw,
            contact=contact,
            account_raw=account_raw,
            company_name=str(company_name),
            template_snapshot=str(row["content_md"]),
            template_name=str(row["name"]),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=f"Preview failed: {exc}") from exc

    seller = SellerBrief.model_validate(seller_raw)
    account = AccountBrief.model_validate(account_raw)
    evidence = list(account.evidence) + list(seller.evidence[:5])
    verifier_summary: dict[str, Any] = {}
    if steps:
        try:
            draft0 = EmailDraft(
                step=1,
                subject=steps[0]["subject"],
                body=steps[0]["body"],
                cited_evidence_ids=[],
                send_after_days=0,
                claims=[],
            )
            # Prefer claims from preview if present
            from app.models import DraftClaim

            claims = []
            for c in steps[0].get("claims") or []:
                if isinstance(c, dict) and c.get("text"):
                    claims.append(
                        DraftClaim(
                            text=str(c["text"]),
                            evidence_ids=list(c.get("evidence_ids") or []),
                        )
                    )
            draft0 = draft0.model_copy(
                update={
                    "claims": claims,
                    "cited_evidence_ids": [
                        i for c in claims for i in c.evidence_ids
                    ][:8]
                    or [e.id for e in evidence[:2]],
                }
            )
            vr = verify_draft(
                draft0,
                evidence=list(evidence),
                contact=contact,
                use_llm=False,
            )
            verifier_summary = {
                "passed": vr.passed,
                "action": vr.action,
                "issues": list(vr.issues or [])[:8],
            }
        except Exception as exc:  # noqa: BLE001
            verifier_summary = {"passed": False, "action": "drop", "issues": [str(exc)]}

    return EmailTemplatePreviewOut(
        preview=True,
        template_id=str(row["id"]),
        template_name=str(row["name"]),
        campaign_id=campaign_id,
        contact_id=contact.id,
        contact_name=contact.name,
        company_name=str(company_name),
        steps=[EmailTemplatePreviewStepOut(**s) for s in steps],
        verifier=verifier_summary,
        prompt_contains_system_rules=bool(prompt_preview.get("system_rules_first")),
        crustdata_calls=0,
    )
