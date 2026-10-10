"""LangGraph StateGraph builder for SignalSDR.

Phase 4 graph: planner between stages, ICP interrupt gate, then account/email.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agents.account_researcher import account_researcher_node
from app.agents.buyer_finder import buyer_propose_icp_node, buyer_search_node, icp_gate_node
from app.agents.email_writer import email_writer_node
from app.agents.planner import planner_node, route_after_planner
from app.agents.product_researcher import product_researcher_node
from app.config import get_settings
from app.state import CampaignState


def _product_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.agents.planner import set_plan_phase

    result = product_researcher_node(state)
    result["plan"] = set_plan_phase({**state, **result}, "after_product")
    return result


def _account_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.agents.planner import set_plan_phase

    result = account_researcher_node(state)
    result["plan"] = set_plan_phase({**state, **result}, "after_account")
    return result


def _email_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.agents.planner import set_plan_phase

    result = email_writer_node(state)
    result["plan"] = set_plan_phase({**state, **result}, "after_email")
    return result


def build_graph(checkpointer: SqliteSaver | None = None):
    graph = StateGraph(CampaignState)
    graph.add_node("planner", planner_node)
    graph.add_node("product_researcher", _product_node)
    graph.add_node("buyer_propose_icp", buyer_propose_icp_node)
    graph.add_node("icp_gate", icp_gate_node)
    graph.add_node("buyer_search", buyer_search_node)
    graph.add_node("account_researcher", _account_node)
    graph.add_node("email_writer", _email_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "product_researcher": "product_researcher",
            "buyer_propose_icp": "buyer_propose_icp",
            "icp_gate": "icp_gate",
            "buyer_search": "buyer_search",
            "account_researcher": "account_researcher",
            "email_writer": "email_writer",
            "done": END,
        },
    )
    graph.add_edge("product_researcher", "planner")
    graph.add_edge("buyer_propose_icp", "planner")
    graph.add_edge("icp_gate", "planner")
    graph.add_edge("buyer_search", "planner")
    graph.add_edge("account_researcher", "planner")
    graph.add_edge("email_writer", "planner")

    return graph.compile(checkpointer=checkpointer)


def build_v0_graph(checkpointer: SqliteSaver | None = None):
    """Backward-compatible alias — Phase 4+ uses the planner graph."""
    return build_graph(checkpointer=checkpointer)


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
    narrow_icp: bool = False,
) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "input": {
            "company_name": company_name,
            "website": website,
            "description": description,
            "n": n,
            "mode": mode,
            "narrow_icp": narrow_icp,
        },
        "plan": {},
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
        "extras": {},
    }
