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
    CampaignApproveIn,
    CampaignDetail,
    CampaignSummary,
    CompanyResearchOut,
    CreateCampaignIn,
    EmailBulkIn,
    EmailDecisionIn,
    EventOut,
    IcpDecisionIn,
    LeadDetail,
    LeadRow,
    LeadSequencePatchIn,
    ManualContactIn,
    ParseCompaniesIn,
    ParseCompaniesOut,
    ParseCompaniesRowOut,
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
from app.infra.company_list import parse_companies_csv, validate_provided_companies
from app.infra.db import connect, init_db
from app.infra.email_templates import snapshot_for_campaign
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
    target_mode = str(opts.get("target_mode") or inp.get("target_mode") or "discover")
    if target_mode not in {"discover", "provided", "provided_contacts"}:
        target_mode = "discover"
    # Mid-run seed: checkpoint contacts may exist before DB lead rows.
    leads_found = int(leads or 0)
    if target_mode == "provided_contacts" or opts.get("seed"):
        try:
            ck_contacts = state_reader.contacts(cid) or []
            leads_found = max(leads_found, len([c for c in ck_contacts if isinstance(c, dict)]))
        except Exception:  # noqa: BLE001
            pass
        snap_n = len(opts.get("provided_contacts") or [])
        if snap_n:
            leads_target_default = snap_n
        else:
            leads_target_default = int(opts.get("n") or inp.get("n") or 10)
    else:
        leads_target_default = int(opts.get("n") or inp.get("n") or 10)
    return CampaignSummary(
        id=cid,
        seller_name=row["seller_name"] or inp.get("company_name") or "",
        seller_domain=row["seller_domain"] or "",
        status=status,
        current_stage=row["current_stage"],
        stages=_stages(cid),
        leads_found=leads_found,
        leads_target=leads_target_default,
        credits_spent=spent,
        credit_cap=float(opts.get("cap") or settings.max_credits),
        mode=opts.get("mode") or inp.get("mode") or settings.data_mode,  # type: ignore[arg-type]
        target_mode=target_mode,  # type: ignore[arg-type]
        seed=opts.get("seed") or inp.get("seed"),
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


@router.post("/campaigns/parse-companies", response_model=ParseCompaniesOut)
def parse_companies(body: ParseCompaniesIn) -> ParseCompaniesOut:
    parsed = parse_companies_csv(body.csv_text or "")
    return ParseCompaniesOut(
        rows=[ParseCompaniesRowOut(**r) for r in parsed.get("rows") or []],
        ok_count=int(parsed.get("ok_count") or 0),
    )


@router.post("/campaigns", response_model=CampaignSummary, status_code=201)
def create_campaign(body: CreateCampaignIn) -> CampaignSummary:
    settings = get_settings()
    init_db(settings.db_path)
    parsed = urlparse(body.website)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(422, detail="website must be an http(s) URL")

    target_mode = body.target_mode or "discover"
    provided: list[dict[str, str]] = []
    provided_contacts: list[dict] = []
    seed: str | None = None
    seller_fallback: dict = {}
    seed_test_inboxes: list[str] = []
    n = int(body.n)
    send_mode = body.send_mode or "sandbox"

    # Demo seed (MindArmor): force provided_contacts + gmail_test when enabled.
    from app.infra import demo_seed as demo_seed_mod
    from app.infra.events import record_event

    try:
        seed_patch = demo_seed_mod.match_and_apply(
            website=body.website, send_mode=send_mode
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    if seed_patch:
        target_mode = str(seed_patch["target_mode"])
        provided = list(seed_patch.get("provided_companies") or [])
        provided_contacts = list(seed_patch.get("provided_contacts") or [])
        seed = str(seed_patch.get("seed") or "mindarmor")
        seller_fallback = dict(seed_patch.get("seller_fallback") or {})
        seed_test_inboxes = list(seed_patch.get("seed_test_inboxes") or [])
        n = int(seed_patch.get("n") or max(len(provided), 1))
        send_mode = "gmail_test"

    if target_mode == "provided":
        try:
            provided = validate_provided_companies(
                [c.model_dump() for c in body.provided_companies]
            )
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        n = len(provided)
    elif target_mode == "provided_contacts":
        if not provided_contacts:
            raise HTTPException(422, detail="No preloaded contacts for this seller")
        n = max(len(provided_contacts), 1)
    elif n < 5:
        raise HTTPException(422, detail="n must be between 5 and 50 for discover mode")

    est = estimate_campaign(n, body.mode, target_mode=target_mode)
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
        if seed:
            raise HTTPException(422, detail="Demo seed campaigns can't send live.")
        if not account:
            raise HTTPException(422, detail="Mail account required for live")
        confirm = (body.live_confirm_email or "").strip().lower()
        if confirm != str(account["email"]).strip().lower():
            raise HTTPException(
                422,
                detail="live_confirm_email must match the mail account email",
            )
        live_confirm_ok = True

    # Merge seed test inboxes into the mail account allowlist.
    if seed and seed_test_inboxes and mail_account_id:
        try:
            existing = json.loads(account.get("test_recipients_json") or "[]") if account else []
        except Exception:  # noqa: BLE001
            existing = []
        merged = []
        seen = set()
        for addr in list(existing) + seed_test_inboxes:
            a = str(addr).strip().lower()
            if a and "@" in a and a not in seen:
                seen.add(a)
                merged.append(a)
        mail_accounts.update_account(mail_account_id, {"test_recipients": merged})

    cid = f"ui-{uuid.uuid4().hex[:10]}"
    try:
        tpl_snap = snapshot_for_campaign(body.template_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, detail=f"email template: {exc}") from exc
    options = {
        "n": n,
        "mode": body.mode,
        "cap": cap,
        "chaos": chaos,
        "kill_after": body.kill_after,
        "send_mode": send_mode,
        "mail_account_id": mail_account_id,
        "live_confirm_ok": live_confirm_ok,
        "target_mode": target_mode,
        "provided_companies": provided,
        "provided_contacts": provided_contacts,
        "seed": seed,
        "seller_fallback": seller_fallback,
        "seed_test_inboxes": seed_test_inboxes,
        "template_id": tpl_snap["template_id"],
        "template_name": tpl_snap["template_name"],
        "template_snapshot": tpl_snap["template_snapshot"],
        "autopilot": True,
    }
    ensure_campaign_row(
        cid,
        company_name=body.company_name,
        website=body.website,
        description=body.description,
        n=n,
        mode=body.mode,
        options=options,
        status="queued",
    )
    if seed_patch and seed_patch.get("demo_seed_event"):
        ev = seed_patch["demo_seed_event"]
        record_event(
            cid,
            str(ev.get("type") or "demo.seed_applied"),
            "planner",
            str(ev.get("message") or "Using a preloaded list for this demo."),
            data={"n": ev.get("n"), "m": ev.get("m")},
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
            "target_mode": opts.get("target_mode") or base.target_mode,
            "template_id": opts.get("template_id"),
            "template_name": opts.get("template_name"),
            "autopilot": opts.get("autopilot") is not False,
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


def _build_email_approval_payload(campaign_id: str) -> dict[str, Any] | None:
    """Build approval queue from checkpoint drafts (interrupt or post-run manual contacts)."""
    from app.tools.mailer import lead_id_for

    values = state_reader.get_values(campaign_id)
    extras = values.get("extras") or {}
    cached = extras.get("pending_email_approval")
    if isinstance(cached, dict) and cached.get("type") == "email_approval" and cached.get("items"):
        return cached

    contacts = {c["id"]: c for c in (values.get("contacts") or []) if isinstance(c, dict)}
    drafts = values.get("drafts") or {}
    verifier = values.get("verifier") or {}
    already = dict(extras.get("email_approvals") or {})
    items: list[dict[str, Any]] = []
    for contact_id, sequence in drafts.items():
        if already.get(contact_id, {}).get("approved") is True:
            continue
        v = verifier.get(contact_id) or {}
        if not v.get("passed") and v.get("action") not in {"pass", "downgrade"}:
            continue
        contact = contacts.get(contact_id) or {}
        step1 = sequence[0] if isinstance(sequence, list) and sequence else {}
        items.append(
            {
                "contact_id": contact_id,
                "lead_id": lead_id_for(campaign_id, contact_id),
                "name": contact.get("name"),
                "title": contact.get("title"),
                "email": contact.get("email"),
                "email_confidence": contact.get("email_confidence"),
                "company_id": contact.get("company_id"),
                "verifier": v,
                "draft": step1,
                "sequence_steps": [
                    d.get("step") for d in sequence if isinstance(d, dict)
                ]
                if isinstance(sequence, list)
                else [],
                "cited_evidence_ids": step1.get("cited_evidence_ids") or [],
            }
        )
    if not items:
        return None
    return {
        "type": "email_approval",
        "campaign_id": campaign_id,
        "items": items,
        "message": "Approve, edit, or reject verified drafts before send.",
    }


@router.get("/campaigns/{campaign_id}/pending-approvals", response_model=PendingApprovalsOut)
def get_pending_approvals(campaign_id: str) -> PendingApprovalsOut:
    from app.agents.evidence_refs import find_refs
    from app.api.schemas import DraftClaimOut, EvidenceWhyOut

    from app.infra.events import set_stage

    payload = state_reader.pending_interrupt(campaign_id)
    companies = {c["id"]: c for c in state_reader.companies(campaign_id) if isinstance(c, dict)}
    accounts = state_reader.accounts(campaign_id)
    drafts_all = state_reader.drafts(campaign_id)
    used_fallback = False
    if not payload or payload.get("type") != "email_approval":
        payload = _build_email_approval_payload(campaign_id)
        used_fallback = bool(payload)
    if not payload or payload.get("type") != "email_approval":
        return PendingApprovalsOut(campaign_id=campaign_id, waiting=False, items=[])
    if used_fallback and (payload.get("items") or []):
        # Heal pipeline cards after post-run manual drafts (run already finished).
        set_stage(campaign_id, "emails", "done")
        set_stage(campaign_id, "verify", "done", "1 passed")
        set_stage(campaign_id, "approval", "waiting")
        set_stage(campaign_id, "send", "pending")
    items_out: list[PendingApprovalItem] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        contact_id = str(item.get("contact_id") or "")
        draft = item.get("draft") or {}
        # Prefer latest checkpoint draft (may include claims after fix-drafts)
        seq = drafts_all.get(contact_id) or []
        if seq and isinstance(seq[0], dict):
            draft = seq[0]
        company = companies.get(item.get("company_id") or "") or {}
        account = accounts.get(item.get("company_id") or "") or {}
        ev_by_id = {
            e.get("id"): e
            for e in (account.get("evidence") or [])
            if isinstance(e, dict) and e.get("id")
        }
        email = item.get("email")
        conf = item.get("email_confidence") or "none"
        from app.agents.email_writer import personalize_copy

        raw_subject = draft.get("subject") if isinstance(draft, dict) else None
        raw_body = draft.get("body") if isinstance(draft, dict) else None
        seller_brief = state_reader.seller(campaign_id) or {}
        subject, body = personalize_copy(
            str(raw_subject or ""),
            str(raw_body or ""),
            contact_name=str(item.get("name") or ""),
            company_name=str(company.get("name") or ""),
            role=str(item.get("title") or ""),
            seller_name=str(seller_brief.get("company_name") or ""),
        )
        claims_out: list[DraftClaimOut] = []
        for c in (draft.get("claims") or []) if isinstance(draft, dict) else []:
            if not isinstance(c, dict):
                continue
            eids = list(c.get("evidence_ids") or [])
            claims_out.append(
                DraftClaimOut(
                    text=str(c.get("text") or ""),
                    evidence_ids=eids,
                    evidence=[
                        EvidenceWhyOut(
                            id=str(ev_by_id[eid]["id"]),
                            fact=str(ev_by_id[eid].get("fact") or ""),
                            source_type=ev_by_id[eid].get("source_type"),
                            source_ref=ev_by_id[eid].get("source_ref"),
                            observed_at=str(ev_by_id[eid].get("observed_at") or "")
                            or None,
                        )
                        for eid in eids
                        if eid in ev_by_id
                    ],
                )
            )
        from app.infra.email_templates import style_warnings as _style_warnings

        warns = list((draft.get("style_warnings") or []) if isinstance(draft, dict) else [])
        if not warns:
            warns = _style_warnings(str(subject or ""), str(body or ""))
        items_out.append(
            PendingApprovalItem(
                contact_id=contact_id,
                lead_id=item.get("lead_id"),
                name=item.get("name"),
                title=item.get("title"),
                email_masked=mask_email(email) if email else None,
                email_confidence=conf,
                company_name=company.get("name"),
                subject=subject,
                body=body,
                guessed=conf == "guessed",
                has_internal_refs=bool(find_refs(f"{subject or ''}\n{body or ''}")),
                claims=claims_out,
                style_warnings=warns,
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


@router.get(
    "/campaigns/{campaign_id}/companies/{company_id}",
    response_model=CompanyResearchOut,
)
def get_company_research(campaign_id: str, company_id: str) -> CompanyResearchOut:
    companies = {
        c["id"]: c
        for c in state_reader.companies(campaign_id)
        if isinstance(c, dict) and c.get("id")
    }
    company = companies.get(company_id)
    if not company:
        raise HTTPException(404, detail="Company not found in campaign")
    accounts = state_reader.accounts(campaign_id)
    account = accounts.get(company_id)
    contacts = [
        c
        for c in state_reader.contacts(campaign_id)
        if isinstance(c, dict) and c.get("company_id") == company_id
    ]
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT id FROM leads WHERE campaign_id = ? AND company_id = ?",
            (campaign_id, company_id),
        ).fetchall()
    finally:
        conn.close()
    lead_ids = [str(r["id"]) for r in rows]
    return CompanyResearchOut(
        company_id=company_id,
        company=company,
        account=account if isinstance(account, dict) else None,
        contacts=contacts,
        lead_ids=lead_ids,
    )


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
    *,
    evidence_by_id: dict[str, dict[str, Any]] | None = None,
    contact_name: str = "",
    company_name: str = "",
    role: str = "",
    seller_name: str = "",
) -> dict[str, Any]:
    from app.agents.email_writer import personalize_copy
    from app.agents.evidence_refs import find_refs
    from app.api.schemas import DraftClaimOut, EvidenceWhyOut

    draft_seq = list(drafts_by_contact.get(contact_id) or [])
    email_rows = list(emails_by_lead.get(lead_id or "") or [])
    by_step: dict[int, dict[str, Any]] = {}
    step1_claims_raw: list[dict[str, Any]] = []
    for d in draft_seq:
        if isinstance(d, dict) and d.get("step"):
            subj, body = personalize_copy(
                str(d.get("subject") or ""),
                str(d.get("body") or ""),
                contact_name=contact_name,
                company_name=company_name,
                role=role,
                seller_name=seller_name,
            )
            by_step[int(d["step"])] = {
                "subject": subj,
                "body": body,
                "status": "draft",
                "sent_at": None,
            }
            if int(d.get("step") or 0) == 1:
                step1_claims_raw = list(d.get("claims") or [])
    for e in email_rows:
        step = int(e.get("step") or 1)
        prior = by_step.get(step) or {}
        subj, body = personalize_copy(
            str(e.get("subject") or prior.get("subject") or ""),
            str(e.get("body") or prior.get("body") or ""),
            contact_name=contact_name,
            company_name=company_name,
            role=role,
            seller_name=seller_name,
        )
        by_step[step] = {
            "subject": subj,
            "body": body,
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
    ev_map = evidence_by_id or {}
    claims_out: list[DraftClaimOut] = []
    for c in step1_claims_raw:
        if not isinstance(c, dict):
            continue
        eids = list(c.get("evidence_ids") or [])
        claims_out.append(
            DraftClaimOut(
                text=str(c.get("text") or ""),
                evidence_ids=eids,
                evidence=[
                    EvidenceWhyOut(
                        id=str(ev_map[eid]["id"]),
                        fact=str(ev_map[eid].get("fact") or ""),
                        source_type=ev_map[eid].get("source_type"),
                        source_ref=ev_map[eid].get("source_ref"),
                        observed_at=str(ev_map[eid].get("observed_at") or "") or None,
                    )
                    for eid in eids
                    if eid in ev_map
                ],
            )
        )
    subj = s1.get("subject") or ""
    body = s1.get("body") or ""
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
        "claims": claims_out,
        "has_internal_refs": bool(find_refs(f"{subj}\n{body}")),
    }


def _lead_email_confidence(raw: Any) -> str:
    v = str(raw or "none").strip().lower()
    if v in {"verified", "likely", "guessed", "provided", "none"}:
        return v
    return "none"


@router.get("/campaigns/{campaign_id}/leads", response_model=list[LeadRow])
def get_leads(campaign_id: str) -> list[LeadRow]:
    contacts = {c["id"]: c for c in state_reader.contacts(campaign_id) if isinstance(c, dict)}
    companies = {c["id"]: c for c in state_reader.companies(campaign_id) if isinstance(c, dict)}
    verifier = state_reader.verifier(campaign_id)
    drafts_by_contact = state_reader.drafts(campaign_id)
    accounts = state_reader.accounts(campaign_id)
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
        reply_class_rows = conn.execute(
            """
            SELECT r.lead_id, r.classification
            FROM replies r
            JOIN leads l ON l.id = r.lead_id
            WHERE l.campaign_id = ?
            ORDER BY r.received_at DESC
            """,
            (campaign_id,),
        ).fetchall()
        draft_rows = conn.execute(
            """
            SELECT id, lead_id, status FROM reply_drafts
            WHERE campaign_id = ? AND status = 'pending'
            """,
            (campaign_id,),
        ).fetchall()
        finance_n = conn.execute(
            """
            SELECT COUNT(*) AS n FROM events
            WHERE campaign_id = ? AND type = 'policy.finance_skipped'
            """,
            (campaign_id,),
        ).fetchone()["n"]
    finally:
        conn.close()
    emails_by_lead: dict[str, list[dict[str, Any]]] = {}
    for er in email_rows:
        emails_by_lead.setdefault(str(er["lead_id"]), []).append(dict(er))
    reply_class_by_lead: dict[str, str] = {}
    for rr in reply_class_rows:
        lid = str(rr["lead_id"])
        if lid not in reply_class_by_lead and rr["classification"]:
            reply_class_by_lead[lid] = str(rr["classification"])
    draft_by_lead: dict[str, dict[str, str]] = {}
    for dr in draft_rows:
        draft_by_lead[str(dr["lead_id"])] = {
            "id": str(dr["id"]),
            "status": str(dr["status"]),
        }
    seller_raw = state_reader.seller(campaign_id) or {}
    seller_name = str(seller_raw.get("company_name") or "")
    out: list[LeadRow] = []
    seen_companies: set[str] = set()
    for r in rows:
        contact_id = r["contact_id"] or ""
        contact = contacts.get(contact_id) or {}
        company_id = str(r["company_id"] or contact.get("company_id") or "")
        company = companies.get(company_id) or {}
        v = verifier.get(contact_id) or {}
        action = v.get("action") or ("pass" if v.get("passed") else "pending")
        vlabel = {
            "pass": "passed",
            "redraft": "redrafted",
            "downgrade": "downgraded",
            "drop": "dropped",
        }.get(action, "pending")
        account = accounts.get(company_id) or {}
        ev_by_id = {
            e["id"]: e for e in (account.get("evidence") or []) if isinstance(e, dict) and e.get("id")
        }
        status = r["status"]
        contact_name = contact.get("name")
        if status == "no_contact" or (not contact_id and not contact_name):
            contact_name = contact_name or "Not found"
        seq = _sequence_fields(
            contact_id,
            r["id"],
            drafts_by_contact,
            emails_by_lead,
            evidence_by_id=ev_by_id,
            contact_name=str(contact.get("name") or ""),
            company_name=str(company.get("name") or ""),
            role=str(contact.get("title") or ""),
            seller_name=seller_name,
        )
        if company_id:
            seen_companies.add(company_id)
        draft_info = draft_by_lead.get(str(r["id"]))
        out.append(
            LeadRow(
                lead_id=r["id"],
                company_id=company_id or None,
                company_name=company.get("name") or "",
                company_domain=company.get("domain") or "",
                contact_name=contact_name,
                contact_title=contact.get("title"),
                role_kind=contact.get("role_kind"),
                email_masked=mask_email(contact["email"]) if contact.get("email") else None,
                email_confidence=_lead_email_confidence(contact.get("email_confidence")),  # type: ignore[arg-type]
                fit=int(round(float(company.get("fit_score") or 0) * 100)),
                verifier=vlabel,  # type: ignore[arg-type]
                redraft_count=int(v.get("redraft_count") or 0),
                status=status,
                updated_at=r["updated_at"],
                contact_id=contact_id or None,
                reply_classification=reply_class_by_lead.get(str(r["id"])),
                reply_draft_status=draft_info["status"] if draft_info else None,
                reply_draft_id=draft_info["id"] if draft_info else None,
                finance_skipped_count=int(finance_n or 0),
                **seq,
            )
        )
    # Surface contacts from checkpoint that are not yet in the leads table
    # (seed demos + mid-run: Leads must show live as contacts appear).
    seen_contact_ids = {str(r.contact_id) for r in out if r.contact_id}
    for cid, contact in contacts.items():
        if str(cid) in seen_contact_ids:
            continue
        company_id = str(contact.get("company_id") or "")
        company = companies.get(company_id) or {}
        account = accounts.get(company_id) or {}
        ev_by_id = {
            e["id"]: e
            for e in (account.get("evidence") or [])
            if isinstance(e, dict) and e.get("id")
        }
        seq = _sequence_fields(
            cid,
            None,
            drafts_by_contact,
            emails_by_lead,
            evidence_by_id=ev_by_id,
            contact_name=str(contact.get("name") or ""),
            company_name=str(company.get("name") or ""),
            role=str(contact.get("title") or ""),
            seller_name=seller_name,
        )
        if company_id:
            seen_companies.add(company_id)
        out.append(
            LeadRow(
                lead_id=cid,
                company_id=company_id or None,
                company_name=company.get("name") or "",
                company_domain=company.get("domain") or "",
                contact_name=contact.get("name"),
                contact_title=contact.get("title"),
                role_kind=contact.get("role_kind"),
                email_masked=mask_email(contact["email"]) if contact.get("email") else None,
                email_confidence=_lead_email_confidence(contact.get("email_confidence")),  # type: ignore[arg-type]
                fit=int(round(float(company.get("fit_score") or 0) * 100)),
                status="discovered",
                contact_id=cid,
                **seq,
            )
        )
    # Companies researched with no person/email (checkpoint may precede DB persist)
    contact_companies = {
        str(c.get("company_id")) for c in contacts.values() if c.get("company_id")
    }
    import uuid as _uuid

    for cid, company in companies.items():
        if cid in seen_companies or cid in contact_companies:
            continue
        is_no_contact = company.get("drop_reason") == "no_contact"
        researched_no_person = (
            company.get("status") == "kept"
            and cid in accounts
            and cid not in contact_companies
        )
        if not (is_no_contact or researched_no_person):
            continue
        lead_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"{campaign_id}:company:{cid}"))
        out.append(
            LeadRow(
                lead_id=lead_id,
                company_id=cid,
                company_name=company.get("name") or "",
                company_domain=company.get("domain") or "",
                contact_name="Not found",
                contact_title=None,
                role_kind=None,
                email_masked=None,
                email_confidence="none",
                fit=int(round(float(company.get("fit_score") or 0) * 100)),
                status="no_contact",
                contact_id=None,
            )
        )
    return out


@router.post(
    "/campaigns/{campaign_id}/companies/{company_id}/contact",
    response_model=LeadRow,
)
def add_manual_contact(
    campaign_id: str, company_id: str, body: ManualContactIn
) -> LeadRow:
    """Attach a user-provided contact and generate a 3-step sequence (no Crustdata)."""
    import re
    import uuid
    from datetime import datetime, timezone

    from app.agents.email_writer import preview_sequence_for_lead
    from app.infra.email_templates import style_warnings
    from app.infra.events import set_stage
    from app.models import AccountBrief, DraftClaim, SellerBrief

    name = (body.name or "").strip()
    email = (body.email or "").strip().lower()
    title = (body.title or "Contact").strip() or "Contact"
    if not name:
        raise HTTPException(422, detail="name is required")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(422, detail="email is invalid")

    companies = {
        c["id"]: c for c in state_reader.companies(campaign_id) if isinstance(c, dict)
    }
    company = companies.get(company_id)
    if not company:
        raise HTTPException(404, detail="Company not found in campaign")

    seller_raw = state_reader.seller(campaign_id)
    if not seller_raw:
        raise HTTPException(422, detail="Seller brief missing; wait for product research")

    accounts = dict(state_reader.accounts(campaign_id))
    account_raw = accounts.get(company_id)
    if not account_raw:
        account_raw = {
            "company_id": company_id,
            "story": f"{company.get('name') or company_id} was on your target list.",
            "why_now": ["User-provided contact; research did not find a person."],
            "evidence": [],
        }
        accounts[company_id] = account_raw
    else:
        # Manual / seed paths may have thin or invalid evidence — keep story, drop bad cards.
        account_raw = dict(account_raw)
        account_raw["company_id"] = company_id
        account_raw.setdefault(
            "story",
            f"{company.get('name') or company_id} was on your target list.",
        )
        account_raw.setdefault(
            "why_now",
            ["User-provided contact; research did not find a person."],
        )
        safe_ev = []
        for ev in account_raw.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            try:
                from app.models import EvidenceCard

                safe_ev.append(EvidenceCard.model_validate(ev).model_dump(mode="json"))
            except Exception:  # noqa: BLE001
                continue
        account_raw["evidence"] = safe_ev
        accounts[company_id] = account_raw

    contact_id = f"{company_id}:user:{uuid.uuid4().hex[:8]}"
    contact = Contact(
        id=contact_id,
        company_id=company_id,
        name=name,
        title=title,
        role_kind="economic_buyer",
        email=email,
        email_source="user",
        email_confidence="verified",
        profile_url=None,
    )

    # Restore company to kept
    company = dict(company)
    company["status"] = "kept"
    company["drop_reason"] = None
    companies[company_id] = company

    values = state_reader.get_values(campaign_id)
    extras = dict(values.get("extras") or {})
    template_snapshot = str(
        extras.get("template_snapshot")
        or (values.get("input") or {}).get("template_snapshot")
        or ""
    )
    if not template_snapshot:
        from app.infra.email_templates import get_default_template

        template_snapshot = str(get_default_template().get("content_md") or "")

    try:
        steps, _meta = preview_sequence_for_lead(
            seller_raw=seller_raw,
            contact=contact,
            account_raw=account_raw,
            company_name=str(company.get("name") or company_id),
            template_snapshot=template_snapshot,
            template_name=str(extras.get("template_name") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=f"Could not write sequence: {exc}") from exc

    draft_models: list[EmailDraft] = []
    draft_dicts: list[dict[str, Any]] = []
    for s in steps:
        claims = [
            DraftClaim(
                text=str(c.get("text") or ""),
                evidence_ids=list(c.get("evidence_ids") or []),
            )
            for c in (s.get("claims") or [])
            if isinstance(c, dict) and c.get("text")
        ]
        draft = EmailDraft(
            step=int(s["step"]),  # type: ignore[arg-type]
            subject=str(s.get("subject") or "")[:160],
            body=str(s.get("body") or ""),
            cited_evidence_ids=[i for c in claims for i in c.evidence_ids][:8],
            send_after_days={1: 0, 2: 3, 3: 7}.get(int(s["step"]), 0),
            claims=claims,
        )
        draft_models.append(draft)
        row = draft.model_dump(mode="json")
        warns = style_warnings(draft.subject, draft.body)
        if warns:
            row["style_warnings"] = warns
        draft_dicts.append(row)

    seller = SellerBrief.model_validate(seller_raw)
    account = AccountBrief.model_validate(account_raw)
    evidence = list(account.evidence) + list(seller.evidence[:5])
    verifier_map = dict(state_reader.verifier(campaign_id))
    # User-provided contact: allow approval even when account evidence is thin.
    try:
        vr = verify_draft(
            draft_models[0],
            evidence=evidence,
            contact=contact,
            use_llm=False,
        )
        vdump = vr.model_dump(mode="json")
        # Soft-pass: block only on internal_ref / hard policy; empty evidence is OK for manual.
        hard = [i for i in (vdump.get("issues") or []) if "internal_ref" in str(i)]
        if hard:
            vdump["passed"] = False
            vdump["action"] = "drop"
        else:
            vdump["passed"] = True
            vdump["action"] = "pass"
            vdump["issues"] = [
                i for i in (vdump.get("issues") or []) if "internal_ref" not in str(i)
            ][:5]
        verifier_map[contact_id] = vdump
    except Exception as exc:  # noqa: BLE001
        verifier_map[contact_id] = {
            "passed": True,
            "action": "pass",
            "issues": [f"manual_soft_pass:{exc}"],
            "unsupported_claims": [],
            "stale_evidence_ids": [],
        }

    contacts = [
        c for c in state_reader.contacts(campaign_id) if isinstance(c, dict)
    ]
    contacts = [c for c in contacts if c.get("id") != contact_id]
    contacts.append(contact.model_dump(mode="json"))
    drafts = dict(state_reader.drafts(campaign_id))
    drafts[contact_id] = draft_dicts

    from app.tools.mailer import lead_id_for as _lead_id_for

    lead_id = _lead_id_for(campaign_id, contact_id)
    approval_item = {
        "contact_id": contact_id,
        "lead_id": lead_id,
        "name": name,
        "title": title,
        "email": email,
        "email_confidence": "verified",
        "company_id": company_id,
        "verifier": verifier_map[contact_id],
        "draft": draft_dicts[0] if draft_dicts else {},
        "sequence_steps": [d.get("step") for d in draft_dicts],
        "cited_evidence_ids": (draft_dicts[0] or {}).get("cited_evidence_ids") or [],
    }
    pending_payload = {
        "type": "email_approval",
        "campaign_id": campaign_id,
        "items": [approval_item],
        "message": "Approve the draft for your added contact, then send.",
    }
    # Merge with any other pending items from prior manual adds
    prior = extras.get("pending_email_approval")
    if isinstance(prior, dict) and prior.get("items"):
        existing = [
            i
            for i in prior["items"]
            if isinstance(i, dict) and i.get("contact_id") != contact_id
        ]
        pending_payload["items"] = existing + [approval_item]
    settings = get_settings()
    init_db(settings.db_path)
    conn_opts = connect(settings.db_path)
    try:
        crow = conn_opts.execute(
            "SELECT options_json FROM campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
    finally:
        conn_opts.close()
    from app.infra.autopilot import campaign_autopilot_from_db_options

    campaign_opts = json.loads(crow["options_json"] or "{}") if crow else {}
    autopilot_on = campaign_autopilot_from_db_options(campaign_opts)
    approvals = dict(extras.get("email_approvals") or {})
    approvals.pop(contact_id, None)
    if autopilot_on and verifier_map[contact_id].get("passed"):
        approvals[contact_id] = {"approved": True}
        extras.pop("pending_email_approval", None)
    else:
        extras["pending_email_approval"] = pending_payload
    extras["email_approvals"] = approvals

    state_reader.update_values(
        campaign_id,
        {
            "contacts": contacts,
            "companies": list(companies.values()),
            "accounts": accounts,
            "drafts": drafts,
            "verifier": verifier_map,
            "extras": extras,
            # next must stay a planner-valid route ("done"). approval_gate is not
            # reachable from the planner; setting it makes update_state KeyError.
            "plan": {
                **dict(values.get("plan") or {}),
                "phase": "awaiting_approval",
                "next": "done",
            },
        },
    )

    now = datetime.now(timezone.utc).isoformat()
    # Remove placeholder no_contact lead for this company
    old_lead = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{campaign_id}:company:{company_id}"))
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        conn.execute("DELETE FROM leads WHERE id = ?", (old_lead,))
        conn.execute(
            """
            INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                contact_id = excluded.contact_id,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (lead_id, campaign_id, company_id, contact_id, "awaiting_approval", now),
        )
        for draft in draft_dicts:
            email_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{lead_id}:{draft.get('step')}"))
            conn.execute(
                """
                INSERT INTO emails (id, lead_id, step, subject, body, status, idempotency_key, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(id) DO UPDATE SET subject = excluded.subject, body = excluded.body, status = excluded.status
                """,
                (
                    email_id,
                    lead_id,
                    int(draft.get("step") or 1),
                    draft.get("subject") or "",
                    draft.get("body") or "",
                    "draft",
                    f"{lead_id}:{draft.get('step')}",
                ),
            )
        conn.execute(
            "UPDATE campaigns SET status = ? WHERE id = ?",
            ("waiting_approval", campaign_id),
        )
        conn.commit()
    finally:
        conn.close()

    set_stage(campaign_id, "emails", "done", f"{len(drafts)} sequences")
    set_stage(campaign_id, "verify", "done", "1 passed")
    lead_status = "awaiting_approval"
    if autopilot_on and verifier_map[contact_id].get("passed"):
        from app.agents.sender import sender_node

        set_stage(campaign_id, "approval", "done", "autopilot")
        set_stage(campaign_id, "send", "running")
        values2 = state_reader.get_values(campaign_id)
        send_state = {
            **values2,
            "campaign_id": campaign_id,
            "drafts": drafts,
            "contacts": contacts,
            "extras": extras,
            "events": list(values2.get("events") or []),
            "errors": list(values2.get("errors") or []),
        }
        out = sender_node(send_state)
        sent_n = sum(
            1
            for e in (out.get("events") or [])
            if isinstance(e, dict) and e.get("type") == "send.step1"
        )
        state_reader.update_values(
            campaign_id,
            {
                "extras": out.get("extras") or extras,
                "events": out.get("events") or send_state["events"],
                "errors": out.get("errors") or send_state["errors"],
                "plan": out.get("plan") or {"phase": "after_email"},
            },
        )
        set_stage(campaign_id, "send", "done", f"{sent_n} sent")
        if sent_n:
            lead_status = "sent"
            conn = connect(settings.db_path)
            try:
                conn.execute(
                    "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
                    ("sent", now, lead_id),
                )
                conn.execute(
                    "UPDATE campaigns SET status = ? WHERE id = ?",
                    ("running", campaign_id),
                )
                conn.commit()
            finally:
                conn.close()
    else:
        set_stage(campaign_id, "approval", "waiting")
        set_stage(campaign_id, "send", "pending")

    seq0 = draft_dicts[0] if draft_dicts else {}
    seq1 = draft_dicts[1] if len(draft_dicts) > 1 else {}
    seq2 = draft_dicts[2] if len(draft_dicts) > 2 else {}
    return LeadRow(
        lead_id=lead_id,
        company_id=company_id,
        company_name=str(company.get("name") or ""),
        company_domain=str(company.get("domain") or ""),
        contact_name=name,
        contact_title=title,
        role_kind="economic_buyer",
        email_masked=mask_email(email),
        email_confidence="verified",
        fit=int(round(float(company.get("fit_score") or 0) * 100)),
        verifier="passed",
        status=lead_status,
        updated_at=now,
        contact_id=contact_id,
        email_1_subject=seq0.get("subject"),
        email_1_body=seq0.get("body"),
        followup_1_subject=seq1.get("subject"),
        followup_1_body=seq1.get("body"),
        followup_2_subject=seq2.get("subject"),
        followup_2_body=seq2.get("body"),
    )


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
        email_confidence=_lead_email_confidence(contact.get("email_confidence")),  # type: ignore[arg-type]
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


@router.post("/campaigns/{campaign_id}/approve-campaign")
def approve_campaign(campaign_id: str, body: CampaignApproveIn) -> dict[str, Any]:
    """One permission for the campaign: approve/reject every pending draft, then send."""
    from app.agents.evidence_refs import find_refs
    from app.agents.sender import sender_node
    from app.infra.events import set_stage

    payload_interrupt = state_reader.pending_interrupt(campaign_id)
    has_interrupt = bool(
        payload_interrupt and payload_interrupt.get("type") == "email_approval"
    )
    payload = payload_interrupt if has_interrupt else _build_email_approval_payload(campaign_id)
    items = [i for i in ((payload or {}).get("items") or []) if isinstance(i, dict)]
    if not items:
        raise HTTPException(404, detail="No drafts waiting for approval")

    drafts_all = state_reader.drafts(campaign_id)
    blocked_refs: list[str] = []
    for item in items:
        cid = str(item.get("contact_id") or "")
        seq = drafts_all.get(cid) or []
        draft = seq[0] if seq and isinstance(seq[0], dict) else (item.get("draft") or {})
        text = f"{draft.get('subject') or ''}\n{draft.get('body') or ''}"
        if find_refs(text):
            blocked_refs.append(cid)

    if body.action == "approve" and blocked_refs:
        raise HTTPException(
            422,
            detail=(
                f"{len(blocked_refs)} draft(s) still have internal reference ids. "
                "Fix them on the campaign before approving."
            ),
        )

    # Live graph interrupt: one resume decision for the whole queue
    if has_interrupt:
        if body.action == "approve":
            decision: dict[str, Any] = {
                "approve_all": True,
                "include_guessed": bool(body.include_guessed),
                "actor": "api",
            }
        else:
            decision = {
                "approvals": {
                    str(i.get("contact_id")): {"approved": False}
                    for i in items
                    if i.get("contact_id")
                },
                "actor": "api",
            }
        settings = get_settings()
        init_db(settings.db_path)
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
        return {
            "decision_id": decision_id,
            "pid": pid,
            "action": body.action,
            "drafts": len(items),
            "inline": False,
        }

    # Post-run / manual path: stage all decisions and send inline
    approvals: dict[str, Any] = {}
    skipped_guessed = 0
    for item in items:
        cid = str(item.get("contact_id") or "")
        if not cid:
            continue
        guessed = item.get("email_confidence") == "guessed"
        if body.action == "reject":
            approvals[cid] = {"approved": False}
            _stage_email_decision(
                campaign_id, cid, action="reject", subject=None, body=None, allow_guessed=False
            )
            continue
        if guessed and not body.include_guessed:
            approvals[cid] = {"approved": False}
            skipped_guessed += 1
            continue
        approvals[cid] = {
            "approved": True,
            "allow_guessed": bool(guessed and body.include_guessed),
        }
        _stage_email_decision(
            campaign_id,
            cid,
            action="approve",
            subject=None,
            body=None,
            allow_guessed=bool(guessed and body.include_guessed),
        )

    if body.action == "reject":
        values = state_reader.get_values(campaign_id)
        extras = dict(values.get("extras") or {})
        extras["email_approvals"] = approvals
        extras.pop("pending_email_approval", None)
        state_reader.update_values(
            campaign_id,
            {
                "extras": extras,
                "plan": {**dict(values.get("plan") or {}), "phase": "after_approval"},
            },
        )
        set_stage(campaign_id, "approval", "done")
        set_stage(campaign_id, "send", "skipped", "rejected")
        state_reader.invalidate(campaign_id)
        return {
            "decision_id": None,
            "pid": None,
            "action": "reject",
            "drafts": len(items),
            "sent": 0,
            "skipped_guessed": 0,
            "inline": True,
        }

    if not any(a.get("approved") for a in approvals.values()):
        raise HTTPException(
            422,
            detail="No drafts to send — all were guessed addresses (enable include_guessed) or empty",
        )

    values = state_reader.get_values(campaign_id)
    drafts = dict(values.get("drafts") or {})
    extras = dict(values.get("extras") or {})
    extras["email_approvals"] = approvals
    extras.pop("pending_email_approval", None)
    state = {
        **values,
        "campaign_id": campaign_id,
        "drafts": drafts,
        "extras": extras,
        "events": list(values.get("events") or []),
        "errors": list(values.get("errors") or []),
    }
    set_stage(campaign_id, "approval", "done")
    set_stage(campaign_id, "send", "running")
    out = sender_node(state)
    sent_n = sum(
        1
        for e in (out.get("events") or [])
        if isinstance(e, dict) and e.get("type") == "send.step1"
    )
    merged_extras = dict(out.get("extras") or extras)
    merged_extras["email_approvals"] = approvals
    merged_extras.pop("pending_email_approval", None)
    state_reader.update_values(
        campaign_id,
        {
            "drafts": out.get("drafts") or drafts,
            "extras": merged_extras,
            "events": out.get("events") or state["events"],
            "errors": out.get("errors") or state["errors"],
            "plan": out.get("plan") or {"phase": "after_email"},
        },
    )
    set_stage(campaign_id, "send", "done", f"{sent_n} sent")
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        for item in items:
            cid = str(item.get("contact_id") or "")
            if not approvals.get(cid, {}).get("approved"):
                continue
            lead_id = item.get("lead_id")
            if lead_id:
                conn.execute(
                    "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
                    ("sent" if sent_n else "approved", now, str(lead_id)),
                )
        conn.execute(
            "UPDATE campaigns SET status = ? WHERE id = ?",
            ("completed", campaign_id),
        )
        conn.commit()
    finally:
        conn.close()
    state_reader.invalidate(campaign_id)
    return {
        "decision_id": None,
        "pid": None,
        "action": "approve",
        "drafts": len(items),
        "sent": sent_n,
        "skipped_guessed": skipped_guessed,
        "inline": True,
    }


@router.post("/campaigns/{campaign_id}/send-approved")
def send_approved(campaign_id: str) -> dict[str, Any]:
    """Resume graph interrupt when present; otherwise send approved drafts inline (manual contacts)."""
    from app.agents.sender import sender_node
    from app.infra.events import set_stage

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
    has_interrupt = bool(
        payload_interrupt and payload_interrupt.get("type") == "email_approval"
    )
    payload = payload_interrupt if has_interrupt else _build_email_approval_payload(campaign_id)
    items = (payload or {}).get("items") or []
    item_ids = {i["contact_id"] for i in items if isinstance(i, dict)}
    approvals: dict[str, Any] = {}
    for r in rows:
        cid = r["contact_id"]
        if item_ids and cid not in item_ids:
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

    if not any(a.get("approved") for a in approvals.values()):
        raise HTTPException(422, detail="No approved drafts to send")

    decision = {"approvals": approvals, "actor": "api"}

    # Live graph interrupt: resume via approve CLI spawn
    if has_interrupt:
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

    # Post-run / manual-contact path: no interrupt — apply approvals and send here
    values = state_reader.get_values(campaign_id)
    drafts = dict(values.get("drafts") or {})
    for item in items:
        if not isinstance(item, dict):
            continue
        cid = item["contact_id"]
        choice = approvals.get(cid) or {}
        if not choice.get("approved"):
            continue
        seq = list(drafts.get(cid) or [])
        if seq and (choice.get("subject") or choice.get("body")):
            step1 = dict(seq[0])
            if choice.get("subject"):
                step1["subject"] = choice["subject"]
            if choice.get("body"):
                step1["body"] = choice["body"]
            seq[0] = step1
            drafts[cid] = seq
        write_audit(
            actor="api",
            action="approve",
            target=str(item.get("lead_id") or cid),
            details={"contact_id": cid, "inline_send": True},
        )

    extras = dict(values.get("extras") or {})
    extras["email_approvals"] = approvals
    extras.pop("pending_email_approval", None)

    state = {
        **values,
        "campaign_id": campaign_id,
        "drafts": drafts,
        "extras": extras,
        "events": list(values.get("events") or []),
        "errors": list(values.get("errors") or []),
    }
    set_stage(campaign_id, "approval", "done")
    set_stage(campaign_id, "send", "running")
    out = sender_node(state)
    sent_n = sum(
        1
        for e in (out.get("events") or [])
        if isinstance(e, dict) and e.get("type") == "send.step1"
    )
    merged_extras = dict(out.get("extras") or extras)
    merged_extras["email_approvals"] = approvals
    merged_extras.pop("pending_email_approval", None)
    state_reader.update_values(
        campaign_id,
        {
            "drafts": out.get("drafts") or drafts,
            "extras": merged_extras,
            "events": out.get("events") or state["events"],
            "errors": out.get("errors") or state["errors"],
            "plan": out.get("plan") or {"phase": "after_email"},
        },
    )
    set_stage(campaign_id, "send", "done", f"{sent_n} sent")
    conn = connect(settings.db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        for cid, choice in approvals.items():
            if not choice.get("approved"):
                continue
            lead_id = next(
                (
                    str(i.get("lead_id"))
                    for i in items
                    if isinstance(i, dict) and i.get("contact_id") == cid
                ),
                None,
            )
            if lead_id:
                conn.execute(
                    "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
                    ("sent" if sent_n else "approved", now, lead_id),
                )
        conn.execute(
            "UPDATE campaigns SET status = ? WHERE id = ?",
            ("completed", campaign_id),
        )
        conn.commit()
    finally:
        conn.close()
    state_reader.invalidate(campaign_id)
    return {
        "decision_id": None,
        "pid": None,
        "approvals": len(approvals),
        "sent": sent_n,
        "inline": True,
    }
