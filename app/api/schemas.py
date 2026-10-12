"""Pydantic response models for the UI API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StageOut(BaseModel):
    stage: Literal[
        "plan", "product", "buyers", "icp", "accounts", "emails", "verify", "approval", "send"
    ]
    status: Literal["pending", "running", "waiting", "done", "skipped", "failed"]
    count_label: str | None = None
    detail: str | None = None
    updated_at: datetime | str | None = None


class PipelineProgressOut(BaseModel):
    done: int = 0
    total: int | None = None


class PipelineAgentOut(BaseModel):
    agent: Literal[
        "planner",
        "product_researcher",
        "buyer_finder",
        "account_researcher",
        "email_writer_verifier",
        "sender",
    ]
    key: Literal["planner", "product", "buyers", "accounts", "writer", "sender"]
    label: str
    status: Literal["idle", "running", "waiting", "done", "failed"]
    detail: str | None = None
    stream: str | None = None
    count_label: str | None = None
    progress: PipelineProgressOut | None = None
    items: list[str] | None = None
    started_at: datetime | str | None = None
    updated_at: datetime | str | None = None


class PipelineOut(BaseModel):
    target_mode: Literal["discover", "list"] = "discover"
    model: str | None = None
    agents: list[PipelineAgentOut] = Field(default_factory=list)


class EvidenceWhyOut(BaseModel):
    id: str
    fact: str
    source_type: str | None = None
    source_ref: str | None = None
    observed_at: str | None = None


class DraftClaimOut(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceWhyOut] = Field(default_factory=list)


class PendingApprovalItem(BaseModel):
    contact_id: str
    lead_id: str | None = None
    name: str | None = None
    title: str | None = None
    email_masked: str | None = None
    email_confidence: str | None = None
    company_name: str | None = None
    subject: str | None = None
    body: str | None = None
    guessed: bool = False
    has_internal_refs: bool = False
    claims: list[DraftClaimOut] = Field(default_factory=list)
    style_warnings: list[str] = Field(default_factory=list)


class PendingApprovalsOut(BaseModel):
    campaign_id: str
    type: str = "email_approval"
    waiting: bool = False
    items: list[PendingApprovalItem] = Field(default_factory=list)


class BudgetOut(BaseModel):
    cap: float
    spent: float
    estimated_total: float | None = None
    by_step: list[dict[str, Any]] = Field(default_factory=list)
    cache_hit_rate: float = 0.0
    reconciled: bool | None = None


class CampaignSummary(BaseModel):
    id: str
    seller_name: str
    seller_domain: str
    status: str
    current_stage: str | None = None
    stages: list[StageOut] = Field(default_factory=list)
    leads_found: int = 0
    leads_target: int = 10
    credits_spent: float = 0.0
    credit_cap: float = 400.0
    mode: Literal["replay", "live"] = "replay"
    target_mode: Literal["discover", "provided"] = "discover"
    started_at: datetime | None = None
    trace_url: str | None = None


class CampaignDetail(CampaignSummary):
    budget: BudgetOut
    recoveries: dict[str, int] = Field(default_factory=dict)
    run_facts: dict[str, Any] = Field(default_factory=dict)
    is_alive: bool = False
    can_resume: bool = False
    links: dict[str, str | None] = Field(default_factory=dict)


class EventOut(BaseModel):
    id: int
    ts: datetime | str
    type: str
    agent: str
    level: Literal["info", "warning", "danger", "neutral", "success"]
    message: str
    credits_delta: float = 0.0
    lead_id: str | None = None
    trace_ref: str | None = None


class MeetingSlotOut(BaseModel):
    label: str
    start_iso: str | None = None


class MeetingProposalOut(BaseModel):
    id: str
    slots: list[MeetingSlotOut] = Field(default_factory=list)
    booking_link: str | None = None
    status: str = "proposed"
    notes: str | None = None
    calendar_event_id: str | None = None
    calendar_html_link: str | None = None


class ReplyDraftOut(BaseModel):
    id: str
    lead_id: str
    campaign_id: str
    classification: str
    subject: str
    body: str
    status: str
    in_reply_to: str | None = None
    meeting: MeetingProposalOut | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ReplyDraftDecideIn(BaseModel):
    action: Literal["approve", "reject"]
    subject: str | None = None
    body: str | None = None
    selected_slot_label: str | None = None


class CompanyResearchOut(BaseModel):
    company_id: str
    company: dict[str, Any]
    account: dict[str, Any] | None = None
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    lead_ids: list[str] = Field(default_factory=list)


class LeadRow(BaseModel):
    lead_id: str
    company_id: str | None = None
    company_name: str
    company_domain: str
    contact_name: str | None = None
    contact_title: str | None = None
    role_kind: str | None = None
    email_masked: str | None = None
    email_confidence: Literal["verified", "likely", "guessed", "none"] = "none"
    fit: int = 0
    verifier: Literal["passed", "redrafted", "downgraded", "dropped", "pending"] = "pending"
    redraft_count: int = 0
    status: str = "discovered"
    updated_at: datetime | str | None = None
    contact_id: str | None = None
    email_1_subject: str | None = None
    email_1_body: str | None = None
    followup_1_subject: str | None = None
    followup_1_body: str | None = None
    followup_2_subject: str | None = None
    followup_2_body: str | None = None
    sent_at: datetime | str | None = None
    email_1_editable: bool = True
    followup_1_editable: bool = True
    followup_2_editable: bool = True
    claims: list[DraftClaimOut] = Field(default_factory=list)
    has_internal_refs: bool = False
    reply_classification: str | None = None
    reply_draft_status: str | None = None
    reply_draft_id: str | None = None
    finance_skipped_count: int = 0


class ManualContactIn(BaseModel):
    name: str
    title: str = "Contact"
    email: str


class LeadSequenceStepIn(BaseModel):
    step: Literal[1, 2, 3]
    subject: str | None = None
    body: str | None = None


class LeadSequencePatchIn(BaseModel):
    steps: list[LeadSequenceStepIn] = Field(default_factory=list)


class LeadDetail(BaseModel):
    lead: LeadRow
    email_full: str | None = None
    found_via: str = ""
    account_story: str = ""
    why_now: list[dict[str, Any]] = Field(default_factory=list)
    emails: list[dict[str, Any]] = Field(default_factory=list)
    verifier: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    audit: list[dict[str, Any]] = Field(default_factory=list)


class ProvidedCompanyIn(BaseModel):
    name: str
    domain: str
    description: str = ""


class CreateCampaignIn(BaseModel):
    company_name: str
    website: str
    description: str = ""
    n: int = Field(default=10, ge=1, le=50)
    mode: Literal["replay", "live"] = "replay"
    cap: float | None = None
    chaos: str = ""
    kill_after: str = ""
    baseline_campaign_id: str | None = None
    mail_account_id: str | None = None
    send_mode: Literal["sandbox", "gmail_drafts", "gmail_test", "gmail_live"] = "sandbox"
    live_confirm_email: str | None = None
    target_mode: Literal["discover", "provided"] = "discover"
    provided_companies: list[ProvidedCompanyIn] = Field(default_factory=list)
    template_id: str | None = None


class EmailTemplateOut(BaseModel):
    id: str
    name: str
    description: str = ""
    content_md: str
    is_default: bool = False
    is_system: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class EmailTemplateCreateIn(BaseModel):
    name: str
    description: str = ""
    content_md: str = Field(..., max_length=8000)


class EmailTemplateUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    content_md: str | None = Field(default=None, max_length=8000)


class EmailTemplatePreviewIn(BaseModel):
    campaign_id: str | None = None
    contact_id: str | None = None


class EmailTemplatePreviewStepOut(BaseModel):
    step: int
    subject: str
    body: str
    claims: list[dict[str, Any]] = Field(default_factory=list)
    style_warnings: list[str] = Field(default_factory=list)


class EmailTemplatePreviewOut(BaseModel):
    preview: bool = True
    template_id: str
    template_name: str
    campaign_id: str
    contact_id: str
    contact_name: str | None = None
    company_name: str | None = None
    steps: list[EmailTemplatePreviewStepOut] = Field(default_factory=list)
    verifier: dict[str, Any] = Field(default_factory=dict)
    prompt_contains_system_rules: bool = True
    crustdata_calls: int = 0


class ParseCompaniesIn(BaseModel):
    csv_text: str = ""


class ParseCompaniesRowOut(BaseModel):
    name: str = ""
    domain: str = ""
    description: str = ""
    status: str
    reason: str = ""


class ParseCompaniesOut(BaseModel):
    rows: list[ParseCompaniesRowOut] = Field(default_factory=list)
    ok_count: int = 0


class EstimateIn(BaseModel):
    n: int = Field(ge=1, le=50)
    mode: Literal["replay", "live"] = "live"
    target_mode: Literal["discover", "provided"] = "discover"


class EstimateOut(BaseModel):
    total: float
    by_step: list[dict[str, Any]]


class IcpDecisionIn(BaseModel):
    approved: bool = True
    icp: dict[str, Any] | None = None


class EmailDecisionIn(BaseModel):
    action: Literal["approve", "reject"]
    subject: str | None = None
    body: str | None = None
    confirm_guessed: bool = False


class EmailBulkIn(BaseModel):
    contact_ids: list[str]
    action: Literal["approve", "reject"] = "approve"


class HealthOut(BaseModel):
    ok: bool = True


class SystemStatusOut(BaseModel):
    crustdata: dict[str, Any]
    data_mode: str
    demo_mode: bool
    max_credits: int
    llm: dict[str, str]
    neatlogs: dict[str, Any]
    hunter: dict[str, Any] = {"configured": False}
    max_send_mode: str = "sandbox"
    sending_paused: bool = False
    mail_account_count: int = 0
    mail_account_error: bool = False


class CalendarStatusOut(BaseModel):
    configured: bool = False
    connected: bool = False
    email: str | None = None
    status: str = "disconnected"
    updated_at: str | None = None
    scope: str = "https://www.googleapis.com/auth/calendar.events"
    redirect_uri: str = ""


class MailAccountOut(BaseModel):
    id: str
    label: str
    provider: str
    email: str
    display_name: str
    username: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    imap_host: str
    imap_port: int
    status: str
    last_verified_at: str | None = None
    last_error: str | None = None
    daily_cap: int = 25
    per_domain_daily_cap: int = 3
    min_gap_seconds: int = 90
    test_recipients: list[str] = Field(default_factory=list)
    live_enabled: bool = False
    signature: str = ""
    postal_address: str = ""
    drafts_folder: str | None = None
    is_default: bool = False
    has_password: bool = False
    agent_enabled: bool = True
    sent_24h: int = 0
    cap: int = 25
    created_at: str | None = None
    updated_at: str | None = None


class MailAccountCreateIn(BaseModel):
    label: str | None = None
    provider: Literal["gmail", "workspace", "custom"] = "gmail"
    email: str
    display_name: str | None = None
    username: str | None = None
    password: str
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_security: str | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    daily_cap: int | None = None
    per_domain_daily_cap: int | None = None
    min_gap_seconds: int | None = None
    test_recipients: list[str] | None = None
    live_enabled: bool = False
    signature: str | None = None
    postal_address: str | None = None
    is_default: bool = False


class MailAccountPatchIn(BaseModel):
    label: str | None = None
    provider: Literal["gmail", "workspace", "custom"] | None = None
    email: str | None = None
    display_name: str | None = None
    username: str | None = None
    password: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_security: str | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    daily_cap: int | None = None
    per_domain_daily_cap: int | None = None
    min_gap_seconds: int | None = None
    test_recipients: list[str] | None = None
    live_enabled: bool | None = None
    signature: str | None = None
    postal_address: str | None = None
    is_default: bool | None = None


class MailPresetOut(BaseModel):
    id: str
    label: str
    provider: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    imap_host: str
    imap_port: int


class VerifyOut(BaseModel):
    ok: bool
    detail: str
    drafts_folder: str | None = None


class MailActivityOut(BaseModel):
    id: str
    ts: str | None = None
    kind: str
    send_mode: str | None = None
    recipient_masked: str | None = None
    message_id: str | None = None
    lead_id: str | None = None


class SendingPausedIn(BaseModel):
    sending_paused: bool


class SendingPausedOut(BaseModel):
    sending_paused: bool


class MailPoliciesPatchIn(BaseModel):
    daily_cap: int | None = None
    per_domain_daily_cap: int | None = None
    min_gap_seconds: int | None = None
    sending_window: dict[str, Any] | None = None
    default_test_recipients: list[str] | None = None


class MailPoliciesOut(BaseModel):
    sending_paused: bool
    max_send_mode: str
    demo_mode: bool
    allow_live_sends: bool
    values: dict[str, Any]
    rules: list[dict[str, Any]]


class PolicyEventOut(BaseModel):
    id: int
    ts: str | None = None
    type: str
    message: str
    campaign_id: str | None = None
    lead_id: str | None = None


class OutboxRow(BaseModel):
    id: str
    lead_id: str | None = None
    campaign_id: str | None = None
    campaign_name: str | None = None
    step: int = 1
    subject: str = ""
    body_preview: str = ""
    from_label: str = ""
    from_email: str | None = None
    send_mode: str = "sandbox"
    delivery_status: str = ""
    ui_status: str = ""
    message_id: str | None = None
    actual_recipient_masked: str | None = None
    sent_at: str | None = None
    scheduled_at: str | None = None
    open_in_gmail_url: str | None = None
    reply_classification: str | None = None


class OutboxSummaryOut(BaseModel):
    total: int = 0
    sent: int = 0
    scheduled: int = 0
    replied: int = 0
    bounced: int = 0
    opted_out: int = 0
    drafted: int = 0
    items: list[OutboxRow] = Field(default_factory=list)


class ReportCampaignRow(BaseModel):
    campaign_id: str
    seller_name: str
    status: str
    mode: str = "replay"
    started_at: str | None = None
    leads: int = 0
    emails_sent: int = 0
    followups_sent: int = 0
    replies: int = 0
    meetings: int = 0
    opted_out: int = 0
    bounced: int = 0
    credits_spent: float = 0.0
    reply_rate: float | None = None


class ReportsOverviewOut(BaseModel):
    campaigns: int = 0
    emails_sent: int = 0
    replies: int = 0
    meetings: int = 0
    opted_out: int = 0
    bounced: int = 0
    credits_spent: float = 0.0
    reply_rate: float | None = None
    rows: list[ReportCampaignRow] = Field(default_factory=list)


class ReplyOut(BaseModel):
    id: str
    lead_id: str
    received_at: str | None = None
    classification: str | None = None
    snippet: str | None = None
    from_masked: str | None = None
    message_id: str | None = None
    source: str | None = None
    open_in_gmail_url: str | None = None
