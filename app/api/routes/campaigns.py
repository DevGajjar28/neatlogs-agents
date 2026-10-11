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
from app.api.pipeline import campaign_pipeline
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
    LeadSequencePatchIn,
    PendingApprovalItem,
    PendingApprovalsOut,
    PipelineOut,
    ReplyOut,
    StageOut,
)
from app.api.status import campaign_status, can_resume
from app.campaign_runner import ensure_campaign_row
from app.config import get_settings
from app.infra.audit import write_audit
from app.infra.budget import BudgetLedger, estimate_campaign
from app.infra.chaos import ChaosConfigError, ChaosController
from app.infra.db import connect, init_db
from app.infra.redact import mask_email
from app.mail import accounts as mail_accounts
from app.mail.policy import mode_allowed
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
                "SELECT stage, status, count_label, updated_at FROM campaign_stages WHERE campaign_id = ?",
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
                updated_at=row["updated_at"] if row else None,
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

    send_mode = body.send_mode or "sandbox"
    mail_account_id = body.mail_account_id
    account = None
    if send_mode != "sandbox":
        if not mail_account_id:
            raise HTTPException(422, detail="mail_account_id required for this send mode")
        account = mail_accounts.get_account(mail_account_id)
        if not account:
            raise HTTPException(422, detail="Mail account not found")
        if not mode_allowed(send_mode, account):
            raise HTTPException(422, detail="Send mode not allowed for this environment")
    live_confirm_ok = False
    if send_mode == "gmail_live":
        if not account:
            raise HTTPException(422, detail="Mail account required for live")
        confirm = (body.live_confirm_email or "").strip().lower()
        if confirm != str(account["email"]).strip().lower():
            raise HTTPException(
                422,
                detail="live_confirm_email must match the mail account email",
            )
        live_confirm_ok = True

    cid = f"ui-{uuid.uuid4().hex[:10]}"
    options = {
        "n": body.n,
        "mode": body.mode,
        "cap": cap,
        "chaos": chaos,
        "kill_after": body.kill_after,
        "send_mode": send_mode,
        "mail_account_id": mail_account_id,
        "live_confirm_ok": live_confirm_ok,
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
    if live_confirm_ok:
        write_audit(
            actor="api",
            action="live_send_confirmed",
            target=cid,
            details={
                "mail_account_id": mail_account_id,
                "confirmed_email": mask_email(body.live_confirm_email or ""),
            },
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
    opts = json.loads(row["options_json"] or "{}")
    send_mode = opts.get("send_mode") or "sandbox"
    mail_account_id = opts.get("mail_account_id")
    mail_label = None
    if mail_account_id:
        try:
            acc = mail_accounts.get_account(str(mail_account_id))
            mail_label = (acc or {}).get("label") or (acc or {}).get("email")
        except Exception:
            mail_label = None
    return CampaignDetail(
        **base.model_dump(),
        budget=budget,
        recoveries=recoveries,
        run_facts={
            "n": base.leads_target,
            "demo_mode": settings.demo_mode,
            "chaos": opts.get("chaos"),
            "send_mode": send_mode,
            "mail_account_id": mail_account_id,
            "mail_account_label": mail_label,
        },
        is_alive=run_manager.is_alive(campaign_id),
        can_resume=can_resume(campaign_id),
        links=links,
    )


@router.get("/campaigns/{campaign_id}/pipeline", response_model=PipelineOut)
def get_pipeline(campaign_id: str) -> PipelineOut:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        row = conn.execute("SELECT id FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, detail="Campaign not found")
    return campaign_pipeline(campaign_id)


@router.get("/campaigns/{campaign_id}/pending-approvals", response_model=PendingApprovalsOut)
def get_pending_approvals(campaign_id: str) -> PendingApprovalsOut:
    payload = state_reader.pending_interrupt(campaign_id)
    companies = {c["id"]: c for c in state_reader.companies(campaign_id) if isinstance(c, dict)}
    if not payload or payload.get("type") != "email_approval":
        return PendingApprovalsOut(campaign_id=campaign_id, waiting=False, items=[])
    items_out: list[PendingApprovalItem] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        draft = item.get("draft") or {}
        company = companies.get(item.get("company_id") or "") or {}
        email = item.get("email")
        conf = item.get("email_confidence") or "none"
        items_out.append(
            PendingApprovalItem(
                contact_id=str(item.get("contact_id") or ""),
                lead_id=item.get("lead_id"),
                name=item.get("name"),
                title=item.get("title"),
                email_masked=mask_email(email) if email else None,
                email_confidence=conf,
                company_name=company.get("name"),
                subject=(draft.get("subject") if isinstance(draft, dict) else None),
                body=(draft.get("body") if isinstance(draft, dict) else None),
                guessed=conf == "guessed",
            )
        )
    return PendingApprovalsOut(
        campaign_id=campaign_id,
        type="email_approval",
        waiting=True,
        items=items_out,
    )


@router.get("/campaigns/{campaign_id}/replies", response_model=list[ReplyOut])
def list_campaign_replies(campaign_id: str) -> list[ReplyOut]:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT id, options_json FROM campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, detail="Campaign not found")
        try:
            opts = json.loads(row["options_json"] or "{}")
        except Exception:  # noqa: BLE001
            opts = {}
        account_email = None
        acc_id = opts.get("mail_account_id")
        if acc_id:
            acc = conn.execute(
                "SELECT email FROM mail_accounts WHERE id = ?", (acc_id,)
            ).fetchone()
            if acc:
                account_email = acc["email"]
        rows = conn.execute(
            """
            SELECT r.id, r.lead_id, r.received_at, r.classification, r.snippet,
                   r.from_masked, r.message_id, r.source
            FROM replies r
            JOIN leads l ON l.id = r.lead_id
            WHERE l.campaign_id = ?
            ORDER BY r.received_at DESC
            """,
            (campaign_id,),
        ).fetchall()
        out: list[ReplyOut] = []
        for r in rows:
            gmail_url = None
            if r["message_id"] and account_email:
                mid = str(r["message_id"]).strip("<>")
                gmail_url = (
                    f"https://mail.google.com/mail/u/{account_email}/"
                    f"#search/rfc822msgid:{mid}"
                )
            out.append(
                ReplyOut(
                    id=str(r["id"]),
                    lead_id=r["lead_id"],
                    received_at=r["received_at"],
                    classification=r["classification"] or None,
                    snippet=(r["snippet"] or "")[:300],
                    from_masked=r["from_masked"],
                    message_id=r["message_id"],
                    source=r["source"],
                    open_in_gmail_url=gmail_url,
                )
            )
        return out
    finally:
        conn.close()


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


def _sequence_fields(
    contact_id: str,
    lead_id: str | None,
    drafts_by_contact: dict[str, Any],
    emails_by_lead: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    draft_seq = list(drafts_by_contact.get(contact_id) or [])
    email_rows = list(emails_by_lead.get(lead_id or "") or [])
    by_step: dict[int, dict[str, Any]] = {}
    for d in draft_seq:
        if isinstance(d, dict) and d.get("step"):
            by_step[int(d["step"])] = {
                "subject": d.get("subject"),
                "body": d.get("body"),
                "status": "draft",
                "sent_at": None,
            }
    for e in email_rows:
        step = int(e.get("step") or 1)
        by_step[step] = {
            "subject": e.get("subject") or (by_step.get(step) or {}).get("subject"),
            "body": e.get("body") or (by_step.get(step) or {}).get("body"),
            "status": e.get("delivery_status") or e.get("status") or "queued",
            "sent_at": e.get("sent_at"),
        }

    def _editable(step: int) -> bool:
        row = by_step.get(step) or {}
        status = str(row.get("status") or "draft").lower()
        return status not in {"sent", "drafted", "unknown"} and not row.get("sent_at")

    s1 = by_step.get(1) or {}
    s2 = by_step.get(2) or {}
    s3 = by_step.get(3) or {}
    return {
        "email_1_subject": s1.get("subject"),
        "email_1_body": s1.get("body"),
        "followup_1_subject": s2.get("subject"),
        "followup_1_body": s2.get("body"),
        "followup_2_subject": s3.get("subject"),
        "followup_2_body": s3.get("body"),
        "sent_at": s1.get("sent_at"),
        "email_1_editable": _editable(1) if by_step.get(1) else True,
        "followup_1_editable": _editable(2) if by_step.get(2) else True,
        "followup_2_editable": _editable(3) if by_step.get(3) else True,
    }


@router.get("/campaigns/{campaign_id}/leads", response_model=list[LeadRow])
def get_leads(campaign_id: str) -> list[LeadRow]:
    contacts = {c["id"]: c for c in state_reader.contacts(campaign_id) if isinstance(c, dict)}
    companies = {c["id"]: c for c in state_reader.companies(campaign_id) if isinstance(c, dict)}
    verifier = state_reader.verifier(campaign_id)
    drafts_by_contact = state_reader.drafts(campaign_id)
    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM leads WHERE campaign_id = ? ORDER BY updated_at DESC",
            (campaign_id,),
        ).fetchall()
        email_rows = conn.execute(
            """
            SELECT e.* FROM emails e
            JOIN leads l ON l.id = e.lead_id
            WHERE l.campaign_id = ?
            ORDER BY e.step
            """,
            (campaign_id,),
        ).fetchall()
    finally:
        conn.close()
    emails_by_lead: dict[str, list[dict[str, Any]]] = {}
    for er in email_rows:
        emails_by_lead.setdefault(str(er["lead_id"]), []).append(dict(er))
    out: list[LeadRow] = []
    for r in rows:
        contact_id = r["contact_id"] or ""
        contact = contacts.get(contact_id) or {}
        company = companies.get(r["company_id"] or contact.get("company_id") or "") or {}
        v = verifier.get(contact_id) or {}
        action = v.get("action") or ("pass" if v.get("passed") else "pending")
        vlabel = {
            "pass": "passed",
            "redraft": "redrafted",
            "downgrade": "downgraded",
            "drop": "dropped",
        }.get(action, "pending")
        seq = _sequence_fields(contact_id, r["id"], drafts_by_contact, emails_by_lead)
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
                contact_id=contact_id or None,
                **seq,
            )
        )
    # Also surface contacts not yet persisted as leads
    if not out:
        for cid, contact in contacts.items():
            company = companies.get(contact.get("company_id") or "") or {}
            seq = _sequence_fields(cid, None, drafts_by_contact, emails_by_lead)
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
                    contact_id=cid,
                    **seq,
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


@router.patch("/leads/{lead_or_contact_id}/sequence")
def patch_lead_sequence(lead_or_contact_id: str, body: LeadSequencePatchIn) -> dict[str, Any]:
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
    if not lead_row:
        raise HTTPException(404, detail="Lead not found")
    campaign_id = lead_row["campaign_id"]
    contact_id = lead_row["contact_id"] or lead_or_contact_id
    drafts_all = state_reader.drafts(campaign_id)
    seq = list(drafts_all.get(contact_id) or [])
    if not seq:
        # Build empty 3-step shell from existing emails if needed
        seq = [
            {"step": 1, "subject": "", "body": "", "cited_evidence_ids": [], "send_after_days": 0},
            {"step": 2, "subject": "", "body": "", "cited_evidence_ids": [], "send_after_days": 3},
            {"step": 3, "subject": "", "body": "", "cited_evidence_ids": [], "send_after_days": 7},
        ]
    by_step = {int(d.get("step") or i + 1): dict(d) for i, d in enumerate(seq) if isinstance(d, dict)}
    updated_steps: list[int] = []
    conn = connect(settings.db_path)
    try:
        for step_in in body.steps:
            step = int(step_in.step)
            email_row = conn.execute(
                "SELECT * FROM emails WHERE lead_id = ? AND step = ?",
                (lead_row["id"], step),
            ).fetchone()
            if email_row and (
                email_row["sent_at"]
                or (email_row["delivery_status"] or "") in {"sent", "drafted", "unknown"}
            ):
                raise HTTPException(409, detail=f"Step {step} already sent; cannot edit")
            cur = by_step.get(step) or {
                "step": step,
                "subject": "",
                "body": "",
                "cited_evidence_ids": [],
                "send_after_days": {1: 0, 2: 3, 3: 7}.get(step, 0),
            }
            if step_in.subject is not None:
                cur["subject"] = step_in.subject
            if step_in.body is not None:
                cur["body"] = step_in.body
            by_step[step] = cur
            updated_steps.append(step)
            if email_row:
                conn.execute(
                    """
                    UPDATE emails SET subject = COALESCE(?, subject), body = COALESCE(?, body)
                    WHERE lead_id = ? AND step = ?
                    """,
                    (step_in.subject, step_in.body, lead_row["id"], step),
                )
        conn.commit()
    finally:
        conn.close()
    new_seq = [by_step[s] for s in sorted(by_step)]
    drafts_all[contact_id] = new_seq
    state_reader.update_drafts(campaign_id, drafts_all)
    write_audit(
        actor="ui",
        action="edit",
        target=str(lead_row["id"]),
        details={"contact_id": contact_id, "steps": updated_steps},
    )
    return {"lead_id": lead_row["id"], "contact_id": contact_id, "steps": updated_steps}


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
