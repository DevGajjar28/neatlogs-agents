"""LangGraph campaign state."""

from typing import TypedDict

from app.models import (
    AccountBrief,
    Company,
    Contact,
    EmailDraft,
    ICPProposal,
    SellerBrief,
    VerifierResult,
)


class CampaignState(TypedDict):
    campaign_id: str
    input: dict  # company_name, website, description, n, mode
    plan: dict  # planner step list + credit budget per step
    budget: dict  # planned vs spent credits, tokens
    seller: SellerBrief | None
    icp: ICPProposal | None
    companies: list[Company]
    contacts: list[Contact]
    accounts: dict[str, AccountBrief]
    drafts: dict[str, list[EmailDraft]]  # contact_id -> sequence
    verifier: dict[str, VerifierResult]
    events: list[dict]  # replans, fallbacks, recoveries (also traced)
    errors: list[dict]
    halt_reason: str | None  # budget_exhausted | awaiting_icp | awaiting_send_approval | out_of_credits
