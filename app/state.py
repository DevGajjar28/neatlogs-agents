"""LangGraph campaign state."""

from typing import Any, TypedDict


class CampaignState(TypedDict, total=False):
    campaign_id: str
    input: dict
    plan: dict
    budget: dict
    seller: dict | None
    icp: dict | None
    companies: list
    contacts: list
    accounts: dict
    drafts: dict
    verifier: dict
    events: list
    errors: list
    halt_reason: str | None
    # Allow forward-compatible keys without breaking the graph.
    extras: Any
