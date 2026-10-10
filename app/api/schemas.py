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


class LeadRow(BaseModel):
    lead_id: str
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


class CreateCampaignIn(BaseModel):
    company_name: str
    website: str
    description: str = ""
    n: int = Field(default=10, ge=5, le=50)
    mode: Literal["replay", "live"] = "replay"
    cap: float | None = None
    chaos: str = ""
    kill_after: str = ""
    baseline_campaign_id: str | None = None


class EstimateIn(BaseModel):
    n: int = Field(ge=1, le=50)
    mode: Literal["replay", "live"] = "live"


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
