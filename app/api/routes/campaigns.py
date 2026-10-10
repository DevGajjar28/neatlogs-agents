"""Campaign list/detail, events, stream, gates, pause/resume."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api import runs as run_manager
from app.api import state_reader
from app.api.schemas import (
    BudgetOut,
    CampaignDetail,
    CampaignSummary,
    CreateCampaignIn,
    EmailBulkIn,
    EmailDecisionIn,
    EventOut,
    IcpDecisionIn,
    LeadDetail,
    LeadRow,
    StageOut,
)
from app.api.status import campaign_status, can_resume
from app.campaign_runner import ensure_campaign_row
from app.config import get_settings
from app.infra.budget import BudgetLedger, estimate_campaign
from app.infra.chaos import ChaosConfigError, ChaosController
from app.infra.db import connect, init_db
from app.infra.redact import mask_email
from app.models import Contact, EmailDraft, EvidenceCard
from app.agents.verifier import verify_draft

router = APIRouter(tags=["campaigns"])

STAGES = ["plan", "product", "buyers", "icp", "accounts", "emails", "verify", "approval", "send"]


def _stages(campaign_id: str) -> list[StageOut]:
    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        rows = {
            r["stage"]: r
            for r in conn.execute(
                "SELECT stage, status, count_label FROM campaign_stages WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchall()
        }
    finally:
        conn.close()
    out: list[StageOut] = []
    for stage in STAGES:
        row = rows.get(stage)
        out.append(
            StageOut(
                stage=stage,  # type: ignore[arg-type]
                status=(row["status"] if row else "pending"),  # type: ignore[arg-type]
                count_label=row["count_label"] if row else None,
            )
        )
    return out


def _summary(row: Any) -> CampaignSummary:
    settings = get_settings()
    cid = row["id"]
    inp = json.loads(row["input_json"] or "{}")
    opts = json.loads(row["options_json"] or "{}")
    ledger = BudgetLedger(settings.db_path)
    spent = ledger.spent(cid)
    conn = connect(settings.db_path)
    try:
        leads = conn.execute(
            "SELECT COUNT(*) AS n FROM leads WHERE campaign_id = ?", (cid,)
        ).fetchone()["n"]
        run = conn.execute(
            "SELECT trace_url FROM runs WHERE campaign_id = ? ORDER BY started_at DESC LIMIT 1",
            (cid,),
        ).fetchone()
    finally:
        conn.close()
    status = campaign_status(cid)
    traces = settings.neatlogs_traces_url or (run["trace_url"] if run else None)
    return CampaignSummary(
        id=cid,
        seller_name=row["seller_name"] or inp.get("company_name") or "",
        seller_domain=row["seller_domain"] or "",
        status=status,
        current_stage=row["current_stage"],
        stages=_stages(cid),
        leads_found=int(leads or 0),
        leads_target=int(opts.get("n") or inp.get("n") or 10),
        credits_spent=spent,
        credit_cap=float(opts.get("cap") or settings.max_credits),
        mode=opts.get("mode") or inp.get("mode") or settings.data_mode,  # type: ignore[arg-type]
        started_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        trace_url=traces,
    )


@router.get("/campaigns", response_model=list[CampaignSummary])
def list_campaigns() -> list[CampaignSummary]:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM campaigns ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [_summary(r) for r in rows]


@router.post("/campaigns", response_model=CampaignSummary, status_code=201)
def create_campaign(body: CreateCampaignIn) -> CampaignSummary:
    settings = get_settings()
    init_db(settings.db_path)
    parsed = urlparse(body.website)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(422, detail="website must be an http(s) URL")
    est = estimate_campaign(body.n, body.mode)
    cap = float(body.cap if body.cap is not None else settings.max_credits)
    if body.mode == "live" and cap < float(est["total"]):
        raise HTTPException(
            422,
            detail=f"cap {cap} is below estimate {est['total']:.2f}",
        )
    chaos = body.chaos.strip()
    if body.kill_after.strip():
        chaos = ",".join(x for x in [chaos, f"kill_after={body.kill_after.strip()}"] if x)
    if chaos:
        try:
            ChaosController.from_csv(chaos)
        except ChaosConfigError as exc:
            raise HTTPException(422, detail=str(exc)) from exc

    cid = f"ui-{uuid.uuid4().hex[:10]}"
    options = {
        "n": body.n,
        "mode": body.mode,
        "cap": cap,
        "chaos": chaos,
        "kill_after": body.kill_after,
    }
    ensure_campaign_row(
        cid,
        company_name=body.company_name,
        website=body.website,
        description=body.description,
        n=body.n,
        mode=body.mode,
        options=options,
        status="queued",
    )
    if body.baseline_campaign_id:
        conn = connect(settings.db_path)
        try:
            conn.execute(
                "UPDATE campaigns SET baseline_campaign_id = ? WHERE id = ?",
                (body.baseline_campaign_id, cid),
            )
            conn.commit()
        finally:
            conn.close()
    try:
        run_manager.start_campaign(cid)
    except RuntimeError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    conn = connect(settings.db_path)
    try:
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
    finally:
        conn.close()
    return _summary(row)


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
def get_campaign(campaign_id: str) -> CampaignDetail:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, detail="Campaign not found")
    base = _summary(row)
    from app.reporter.run_report import compute_metrics

    try:
        metrics = compute_metrics(campaign_id)
    except Exception:
        metrics = {}
    budget = BudgetOut(
        cap=base.credit_cap,
        spent=base.credits_spent,
        estimated_total=None,
        by_step=[
            {"step": k, "credits": v}
            for k, v in (metrics.get("credits_by_step") or {}).items()
        ],
        cache_hit_rate=float(metrics.get("cache_hit_rate") or 0),
        reconciled=metrics.get("reconciled"),
    )
    recoveries = dict(metrics.get("recoveries_by_type") or {})
    links = {
        "neatlogs": (
            f"{settings.neatlogs_traces_url} (filter by campaign {campaign_id})"
            if settings.neatlogs_traces_url
            else None
        ),
        "mailpit": "http://localhost:8025",
    }
    return CampaignDetail(
        **base.model_dump(),
        budget=budget,
        recoveries=recoveries,
        run_facts={
            "n": base.leads_target,
            "demo_mode": settings.demo_mode,
            "chaos": json.loads(row["options_json"] or "{}").get("chaos"),
        },
        is_alive=run_manager.is_alive(campaign_id),
        can_resume=can_resume(campaign_id),
        links=links,
    )


@router.get("/campaigns/{campaign_id}/events", response_model=list[EventOut])
def list_events(
    campaign_id: str,
    after: int = Query(0),
    type: str | None = None,
    limit: int = Query(200, le=500),
) -> list[EventOut]:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        sql = "SELECT * FROM events WHERE campaign_id = ? AND id > ?"
        args: list[Any] = [campaign_id, after]
        if type:
            sql += " AND type = ?"
            args.append(type)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()
    return [
        EventOut(
            id=r["id"],
            ts=r["ts"],
            type=r["type"],
            agent=r["agent"],
            level=r["level"],  # type: ignore[arg-type]
            message=r["message"],
            credits_delta=float(r["credits_delta"] or 0),
            lead_id=r["lead_id"],
            trace_ref=r["trace_ref"],
        )
        for r in rows
    ]


@router.get("/campaigns/{campaign_id}/stream")
async def stream_events(
    campaign_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    after: int = Query(0),
):
    settings = get_settings()
    init_db(settings.db_path)
    start_after = after
    if last_event_id and last_event_id.isdigit():
        start_after = max(start_after, int(last_event_id))

    async def gen():
        import asyncio

        cursor = start_after
        last_status = None
        last_stages = None
        idle = 0
        while True:
            if await request.is_disconnected():
                break
            conn = connect(settings.db_path)
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM events WHERE campaign_id = ? AND id > ?
                    ORDER BY id ASC LIMIT 50
                    """,
                    (campaign_id, cursor),
                ).fetchall()
                stages = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT stage, status, count_label, updated_at FROM campaign_stages WHERE campaign_id = ?",
                        (campaign_id,),
                    ).fetchall()
                ]
            finally:
                conn.close()
            for r in rows:
                cursor = r["id"]
                payload = EventOut(
                    id=r["id"],
                    ts=r["ts"],
                    type=r["type"],
                    agent=r["agent"],
                    level=r["level"],  # type: ignore[arg-type]
                    message=r["message"],
                    credits_delta=float(r["credits_delta"] or 0),
                    lead_id=r["lead_id"],
                    trace_ref=r["trace_ref"],
                )
                yield f"id: {r['id']}\nevent: activity\ndata: {payload.model_dump_json()}\n\n"
            stages_key = json.dumps(stages, default=str)
            if stages_key != last_stages:
                last_stages = stages_key
                yield f"event: stage\ndata: {json.dumps(stages, default=str)}\n\n"
            status = campaign_status(campaign_id)
            if status != last_status:
                last_status = status
                yield f"event: status\ndata: {json.dumps({'status': status})}\n\n"
            if status in {"completed", "failed", "halted"} and not run_manager.is_alive(campaign_id):
                break
            idle += 1
            if idle % 15 == 0:
                yield ": ping\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/campaigns/{campaign_id}/icp")
def get_icp(campaign_id: str) -> dict[str, Any]:
    payload = state_reader.pending_interrupt(campaign_id)
    icp = state_reader.icp(campaign_id)
    if not icp:
        raise HTTPException(404, detail="No ICP yet")
    return {
        "icp": icp,
        "waiting": bool(payload and payload.get("type") == "icp_approval"),
        "roles": (icp or {}).get("roles") or [],
        "evidence": (icp or {}).get("evidence") or [],
    }


@router.post("/campaigns/{campaign_id}/icp")
def post_icp(campaign_id: str, body: IcpDecisionIn) -> dict[str, Any]:
    settings = get_settings()
    init_db(settings.db_path)
    decision = {"approved": body.approved}
    if body.icp is not None:
        decision["icp"] = body.icp
    conn = connect(settings.db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO gate_decisions (campaign_id, gate, decision_json, status, created_at)
            VALUES (?, 'icp', ?, 'pending', ?)
            """,
            (campaign_id, json.dumps(decision), datetime.now(timezone.utc).isoformat()),
        )
        decision_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    try:
        pid = run_manager.approve_decision(campaign_id, int(decision_id))
    except RuntimeError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    state_reader.invalidate(campaign_id)
    return {"decision_id": decision_id, "pid": pid}


@router.post("/campaigns/{campaign_id}/pause")
def pause(campaign_id: str) -> dict[str, str]:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        conn.execute(
            "UPDATE campaigns SET pause_requested = 1 WHERE id = ?",
            (campaign_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "pause_requested"}


@router.post("/campaigns/{campaign_id}/resume")
def resume(campaign_id: str) -> dict[str, Any]:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        conn.execute(
            "UPDATE campaigns SET pause_requested = 0, status = 'queued' WHERE id = ?",
            (campaign_id,),
        )
        conn.commit()
    finally:
        conn.close()
    try:
        pid = run_manager.resume_campaign(campaign_id)
    except RuntimeError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return {"pid": pid}


@router.get("/campaigns/{campaign_id}/companies")
def get_companies(campaign_id: str) -> list[dict[str, Any]]:
    return state_reader.companies(campaign_id)


@router.get("/campaigns/{campaign_id}/seller")
def get_seller(campaign_id: str) -> dict[str, Any]:
    seller = state_reader.seller(campaign_id)
    if not seller:
        raise HTTPException(404, detail="No seller brief yet")
    return seller


@router.get("/campaigns/{campaign_id}/leads", response_model=list[LeadRow])
def get_leads(campaign_id: str) -> list[LeadRow]:
    contacts = {c["id"]: c for c in state_reader.contacts(campaign_id) if isinstance(c, dict)}
    companies = {c["id"]: c for c in state_reader.companies(campaign_id) if isinstance(c, dict)}
    verifier = state_reader.verifier(campaign_id)
    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM leads WHERE campaign_id = ? ORDER BY updated_at DESC",
            (campaign_id,),
        ).fetchall()
    finally:
        conn.close()
    out: list[LeadRow] = []
    for r in rows:
        contact = contacts.get(r["contact_id"] or "") or {}
        company = companies.get(r["company_id"] or contact.get("company_id") or "") or {}
        v = verifier.get(r["contact_id"] or "") or {}
        action = v.get("action") or ("pass" if v.get("passed") else "pending")
        vlabel = {
            "pass": "passed",
            "redraft": "redrafted",
            "downgrade": "downgraded",
            "drop": "dropped",
        }.get(action, "pending")
        out.append(
            LeadRow(
                lead_id=r["id"],
                company_name=company.get("name") or "",
                company_domain=company.get("domain") or "",
                contact_name=contact.get("name"),
                contact_title=contact.get("title"),
                role_kind=contact.get("role_kind"),
                email_masked=mask_email(contact["email"]) if contact.get("email") else None,
                email_confidence=contact.get("email_confidence") or "none",  # type: ignore[arg-type]
                fit=int(round(float(company.get("fit_score") or 0) * 100)),
                verifier=vlabel,  # type: ignore[arg-type]
                redraft_count=int(v.get("redraft_count") or 0),
                status=r["status"],
                updated_at=r["updated_at"],
            )
        )
    # Also surface contacts not yet persisted as leads
    if not out:
        for cid, contact in contacts.items():
            company = companies.get(contact.get("company_id") or "") or {}
            out.append(
                LeadRow(
                    lead_id=cid,
                    company_name=company.get("name") or "",
                    company_domain=company.get("domain") or "",
                    contact_name=contact.get("name"),
                    contact_title=contact.get("title"),
                    role_kind=contact.get("role_kind"),
                    email_masked=mask_email(contact["email"]) if contact.get("email") else None,
                    email_confidence=contact.get("email_confidence") or "none",  # type: ignore[arg-type]
                    fit=int(round(float(company.get("fit_score") or 0) * 100)),
                    status="discovered",
                )
            )
    return out


@router.get("/leads/{lead_or_contact_id}", response_model=LeadDetail)
def get_lead(lead_or_contact_id: str) -> LeadDetail:
    # Prefer contact_id match in checkpoint; fall back to leads table
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        lead_row = conn.execute(
            "SELECT * FROM leads WHERE id = ? OR contact_id = ?",
            (lead_or_contact_id, lead_or_contact_id),
        ).fetchone()
    finally:
        conn.close()
    campaign_id = lead_row["campaign_id"] if lead_row else None
    contact_id = (lead_row["contact_id"] if lead_row else None) or lead_or_contact_id
    if not campaign_id:
        # scan campaigns? require lead row for now
        raise HTTPException(404, detail="Lead not found")
    contacts = {c["id"]: c for c in state_reader.contacts(campaign_id) if isinstance(c, dict)}
    contact = contacts.get(contact_id) or {}
    companies = {c["id"]: c for c in state_reader.companies(campaign_id) if isinstance(c, dict)}
    company = companies.get(contact.get("company_id") or "") or {}
    accounts = state_reader.accounts(campaign_id)
    account = accounts.get(contact.get("company_id") or "") or {}
    drafts = state_reader.drafts(campaign_id).get(contact_id) or []
    verifier = state_reader.verifier(campaign_id).get(contact_id) or {}
    evidence = account.get("evidence") or []
    conn = connect(settings.db_path)
    try:
        audit = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM audit WHERE target = ? OR target = ? ORDER BY id DESC LIMIT 50",
                (lead_or_contact_id, contact_id),
            ).fetchall()
        ]
        emails = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM emails WHERE lead_id = ? ORDER BY step",
                (lead_row["id"] if lead_row else "",),
            ).fetchall()
        ]
    finally:
        conn.close()
    if not emails and drafts:
        emails = [
            {
                "id": f"{contact_id}-{d.get('step')}",
                "step": d.get("step"),
                "subject": d.get("subject"),
                "body": d.get("body"),
                "cited_evidence_ids": d.get("cited_evidence_ids") or [],
                "status": "draft",
            }
            for d in drafts
        ]
    row = LeadRow(
        lead_id=lead_row["id"] if lead_row else contact_id,
        company_name=company.get("name") or "",
        company_domain=company.get("domain") or "",
        contact_name=contact.get("name"),
        contact_title=contact.get("title"),
        role_kind=contact.get("role_kind"),
        email_masked=mask_email(contact["email"]) if contact.get("email") else None,
        email_confidence=contact.get("email_confidence") or "none",  # type: ignore[arg-type]
        fit=int(round(float(company.get("fit_score") or 0) * 100)),
        status=lead_row["status"] if lead_row else "discovered",
        updated_at=lead_row["updated_at"] if lead_row else None,
    )
    return LeadDetail(
        lead=row,
        email_full=contact.get("email"),
        found_via=contact.get("email_source") or "",
        account_story=account.get("story") or "",
        why_now=[{"text": w, "evidence_ids": []} for w in (account.get("why_now") or [])],
        emails=emails,
        verifier=verifier,
        evidence=evidence if isinstance(evidence, list) else [],
        audit=audit,
    )


def _stage_email_decision(
    campaign_id: str,
    contact_id: str,
    *,
    action: str,
    subject: str | None,
    body: str | None,
    allow_guessed: bool,
) -> dict[str, Any]:
    settings = get_settings()
    init_db(settings.db_path)
    issues: list[str] = []
    if action == "approve" and (subject or body):
        drafts = state_reader.drafts(campaign_id).get(contact_id) or []
        contacts = {c["id"]: c for c in state_reader.contacts(campaign_id) if isinstance(c, dict)}
        contact_raw = contacts.get(contact_id) or {}
        accounts = state_reader.accounts(campaign_id)
        account = accounts.get(contact_raw.get("company_id") or "") or {}
        evidence = [EvidenceCard.model_validate(e) for e in (account.get("evidence") or []) if isinstance(e, dict)]
        step1 = dict(drafts[0]) if drafts else {"step": 1, "subject": "", "body": "", "cited_evidence_ids": [], "send_after_days": 0}
        if subject:
            step1["subject"] = subject
        if body:
            step1["body"] = body
        draft = EmailDraft.model_validate(step1)
        contact = Contact.model_validate(
            {
                "id": contact_id,
                "company_id": contact_raw.get("company_id") or "",
                "name": contact_raw.get("name") or "Contact",
                "title": contact_raw.get("title") or "",
                "role_kind": contact_raw.get("role_kind") or "champion",
                "email": contact_raw.get("email"),
                "email_source": contact_raw.get("email_source") or "none",
                "email_confidence": contact_raw.get("email_confidence") or "none",
                "profile_url": contact_raw.get("profile_url"),
            }
        )
        result = verify_draft(draft, evidence=evidence, contact=contact, use_llm=False)
        issues = result.issues + result.unsupported_claims
        if not result.passed:
            action = "approve"  # still stage but return issues; UI keeps awaiting
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            INSERT INTO email_decisions (
                campaign_id, contact_id, action, subject, body, allow_guessed, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_id, contact_id) DO UPDATE SET
                action = excluded.action,
                subject = excluded.subject,
                body = excluded.body,
                allow_guessed = excluded.allow_guessed,
                updated_at = excluded.updated_at
            """,
            (
                campaign_id,
                contact_id,
                action,
                subject,
                body,
                1 if allow_guessed else 0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"contact_id": contact_id, "action": action, "issues": issues}


@router.post("/emails/bulk")
def email_bulk(body: EmailBulkIn, campaign_id: str = Query(...)) -> dict[str, Any]:
    # Registered before /emails/{contact_id} so "bulk" is not captured as an id.
    contacts = {c["id"]: c for c in state_reader.contacts(campaign_id) if isinstance(c, dict)}
    done: list[str] = []
    skipped_guessed: list[str] = []
    failed: list[str] = []
    for cid in body.contact_ids:
        contact = contacts.get(cid) or {}
        if body.action == "approve" and contact.get("email_confidence") == "guessed":
            skipped_guessed.append(cid)
            continue
        try:
            _stage_email_decision(
                campaign_id,
                cid,
                action=body.action,
                subject=None,
                body=None,
                allow_guessed=False,
            )
            done.append(cid)
        except Exception:
            failed.append(cid)
    return {"done": done, "skipped_guessed": skipped_guessed, "failed": failed}


@router.post("/emails/{contact_id}")
def email_decision(
    contact_id: str,
    body: EmailDecisionIn,
    campaign_id: str = Query(...),
) -> dict[str, Any]:
    contacts = {c["id"]: c for c in state_reader.contacts(campaign_id) if isinstance(c, dict)}
    contact = contacts.get(contact_id) or {}
    if body.action == "approve" and contact.get("email_confidence") == "guessed" and not body.confirm_guessed:
        raise HTTPException(422, detail="Guessed address: confirm you've checked it")
    return _stage_email_decision(
        campaign_id,
        contact_id,
        action=body.action,
        subject=body.subject,
        body=body.body,
        allow_guessed=bool(body.confirm_guessed),
    )


@router.post("/campaigns/{campaign_id}/send-approved")
def send_approved(campaign_id: str) -> dict[str, Any]:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM email_decisions WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchall()
    finally:
        conn.close()
    payload_interrupt = state_reader.pending_interrupt(campaign_id)
    items = (payload_interrupt or {}).get("items") or []
    item_ids = {i["contact_id"] for i in items if isinstance(i, dict)}
    approvals: dict[str, Any] = {}
    for r in rows:
        cid = r["contact_id"]
        if cid not in item_ids and item_ids:
            continue
        if r["action"] == "approve":
            approvals[cid] = {
                "approved": True,
                "allow_guessed": bool(r["allow_guessed"]),
                "subject": r["subject"],
                "body": r["body"],
            }
        else:
            approvals[cid] = {"approved": False}
    for item in items:
        cid = item["contact_id"]
        if cid not in approvals:
            approvals[cid] = {"approved": False}
    decision = {"approvals": approvals, "actor": "api"}
    conn = connect(settings.db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO gate_decisions (campaign_id, gate, decision_json, status, created_at)
            VALUES (?, 'send', ?, 'pending', ?)
            """,
            (campaign_id, json.dumps(decision), datetime.now(timezone.utc).isoformat()),
        )
        decision_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    try:
        pid = run_manager.approve_decision(campaign_id, int(decision_id))
    except RuntimeError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    state_reader.invalidate(campaign_id)
    return {"decision_id": decision_id, "pid": pid, "approvals": len(approvals)}
