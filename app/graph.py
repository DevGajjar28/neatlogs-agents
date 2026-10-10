"""LangGraph StateGraph builder for SignalSDR.

v0 is deliberately linear: product → buyer → account → email → END.
Planner, verifier, human gates, and sender arrive in later phases.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agents.account_researcher import account_researcher_node
from app.agents.buyer_finder import buyer_finder_node
from app.agents.email_writer import email_writer_node
from app.agents.product_researcher import product_researcher_node
from app.config import get_settings
from app.state import CampaignState


def build_v0_graph(checkpointer: SqliteSaver | None = None):
    graph = StateGraph(CampaignState)
    graph.add_node("product_researcher", product_researcher_node)
    graph.add_node("buyer_finder", buyer_finder_node)
    graph.add_node("account_researcher", account_researcher_node)
    graph.add_node("email_writer", email_writer_node)

    graph.add_edge(START, "product_researcher")
    graph.add_edge("product_researcher", "buyer_finder")
    graph.add_edge("buyer_finder", "account_researcher")
    graph.add_edge("account_researcher", "email_writer")
    graph.add_edge("email_writer", END)

    return graph.compile(checkpointer=checkpointer)


def open_checkpointer(db_path: str | None = None) -> tuple[sqlite3.Connection, SqliteSaver]:
    settings = get_settings()
    path = db_path or settings.db_path
    conn = sqlite3.connect(path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return conn, saver


def initial_state(
    *,
    campaign_id: str,
    company_name: str,
    website: str,
    description: str,
    n: int,
    mode: str,
) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "input": {
            "company_name": company_name,
            "website": website,
            "description": description,
            "n": n,
            "mode": mode,
        },
        "plan": {"version": "v0", "steps": ["product", "buyer", "account", "email"]},
        "budget": {"credits_spent": 0},
        "seller": None,
        "icp": None,
        "companies": [],
        "contacts": [],
        "accounts": {},
        "drafts": {},
        "verifier": {},
        "events": [],
        "errors": [],
        "halt_reason": None,
    }
