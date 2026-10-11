"""Typed contracts for campaign data."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class EvidenceCard(BaseModel):
    id: str  # "ev_<hash>"
    fact: str  # one atomic fact, <= 200 chars
    source_type: Literal["crustdata", "web", "user_input"]
    source_ref: str  # URL or "crustdata:<endpoint>:<field>"
    observed_at: date | None  # date of the fact, if known
    fetched_at: datetime
    confidence: Literal["high", "medium", "low"]


class SellerBrief(BaseModel):
    company_name: str
    domain: str
    one_liner: str
    products: list[str]
    value_props: list[str]
    pricing_notes: str | None
    named_customers: list[str]  # from logos/case studies
    evidence: list[EvidenceCard]


class BuyerRole(BaseModel):
    title_variants: list[str]  # e.g. ["CISO", "Head of Security", "VP Security"]
    kind: Literal["economic_buyer", "champion", "user"]
    why: str


class ICPProposal(BaseModel):
    industries: list[str]
    headcount_min: int | None
    headcount_max: int | None
    countries: list[str]
    employee_count_ranges: list[str] = []
    funding_stages: list[str] = []
    roles: list[BuyerRole]
    rationale: str
    evidence: list[EvidenceCard]  # customers it was derived from
    approved: bool = False
    edited_by_user: bool = False


class Company(BaseModel):
    id: str  # crustdata company id or domain
    name: str
    domain: str
    industry: str | None
    headcount: int | None
    country: str | None
    fit_score: float = 0.0  # 0..1, deterministic
    fit_reasons: list[str] = []
    status: Literal["candidate", "kept", "dropped"] = "candidate"
    drop_reason: str | None = None


class Contact(BaseModel):
    id: str
    company_id: str
    name: str
    title: str
    role_kind: Literal["economic_buyer", "champion", "user"]
    email: str | None
    email_source: Literal["crustdata", "crustdata_realtime", "pattern_guess", "user", "none"]
    email_confidence: Literal["verified", "likely", "guessed", "none"]
    profile_url: str | None


class AccountBrief(BaseModel):
    company_id: str
    story: str  # 3–5 sentences, every claim cites evidence ids
    why_now: list[str]  # each cites evidence ids
    evidence: list[EvidenceCard]


class DraftClaim(BaseModel):
    text: str  # exact phrase from body (no evidence ids)
    evidence_ids: list[str]


class EmailDraft(BaseModel):
    step: Literal[1, 2, 3]  # first + 2 follow-ups
    subject: str
    body: str
    cited_evidence_ids: list[str]
    send_after_days: int  # 0, 3, 7 (demo: minutes)
    claims: list[DraftClaim] = []


class VerifierResult(BaseModel):
    passed: bool
    unsupported_claims: list[str]
    stale_evidence_ids: list[str]
    issues: list[str]  # tone, length, personal data, injection residue
    action: Literal["pass", "redraft", "downgrade", "drop"]


LeadStatus = Literal[
    "discovered",
    "enriched",
    "scored",
    "contact_found",
    "researched",
    "drafted",
    "verified",
    "awaiting_approval",
    "approved",
    "sent",
    "followup_scheduled",
    "replied",
    "opted_out",
    "completed",
    "rejected",
]
