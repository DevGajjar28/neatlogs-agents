"""LangGraph campaign state."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


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
    extras: Any
    # Fan-out shards from account_company Send nodes (Phase 5).
    account_shards: Annotated[list, operator.add]
