"""LangGraph StateGraph builder for SignalSDR.

Phase 7: approval gate + sender after verifier; account Send fan-out; ICP gate.
B0: node wrapper for kill_after chaos (exit at start of next node after checkpoint).
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agents.account_researcher import (
    account_company_node,
    account_enrich_node,
    account_join_node,
    fanout_account_companies,
)
from app.agents.approval_gate import approval_gate_node
from app.agents.buyer_finder import buyer_propose_icp_node, buyer_search_node, icp_gate_node
from app.agents.email_writer import email_writer_node
from app.agents.planner import planner_node, route_after_planner
from app.agents.product_researcher import product_researcher_node
from app.agents.sender import sender_node
from app.agents.verifier import route_after_verifier, verifier_node
from app.config import get_settings
from app.infra.chaos import arm_kill_after, get_chaos, kill_armed
from app.state import CampaignState


def _product_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.agents.planner import set_plan_phase

    result = product_researcher_node(state)
    result["plan"] = set_plan_phase({**state, **result}, "after_product")
    return result


def wrap_node(name: str, fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Wrap a node for kill_after: arm after named node returns; exit on next entry."""

    def _wrapped(state: dict[str, Any]) -> dict[str, Any]:
        if kill_armed():
            try:
                from app.infra.tracing import finish

                finish()
            except Exception:
                pass
            os._exit(1)

        result = fn(state)
        if not isinstance(result, dict):
            result = {}

        target = get_chaos().kill_after
        if target and target == name:
            arm_kill_after()
            events = list(result["events"]) if "events" in result else list(state.get("events") or [])
            events.append({"type": "chaos.kill_after", "after_node": name})
            result = {**result, "events": events}
        return result

    _wrapped.__name__ = getattr(fn, "__name__", name)
    _wrapped.__qualname__ = getattr(fn, "__qualname__", name)
    return _wrapped


def build_graph(checkpointer: SqliteSaver | None = None):
    graph = StateGraph(CampaignState)
    graph.add_node("planner", wrap_node("planner", planner_node))
    graph.add_node("product_researcher", wrap_node("product_researcher", _product_node))
    graph.add_node("buyer_propose_icp", wrap_node("buyer_propose_icp", buyer_propose_icp_node))
    graph.add_node("icp_gate", wrap_node("icp_gate", icp_gate_node))
    graph.add_node("buyer_search", wrap_node("buyer_search", buyer_search_node))
    graph.add_node("account_enrich", wrap_node("account_enrich", account_enrich_node))
    graph.add_node("account_company", wrap_node("account_company", account_company_node))
    graph.add_node("account_join", wrap_node("account_join", account_join_node))
    graph.add_node("email_writer", wrap_node("email_writer", email_writer_node))
    graph.add_node("verifier", wrap_node("verifier", verifier_node))
    graph.add_node("approval_gate", wrap_node("approval_gate", approval_gate_node))
    graph.add_node("sender", wrap_node("sender", sender_node))

    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "product_researcher": "product_researcher",
            "buyer_propose_icp": "buyer_propose_icp",
            "icp_gate": "icp_gate",
            "buyer_search": "buyer_search",
            "account_researcher": "account_enrich",
            "email_writer": "email_writer",
            "done": END,
        },
    )
    graph.add_edge("product_researcher", "planner")
    graph.add_edge("buyer_propose_icp", "planner")
    graph.add_edge("icp_gate", "planner")
    graph.add_edge("buyer_search", "planner")
    graph.add_conditional_edges("account_enrich", fanout_account_companies)
    graph.add_edge("account_company", "account_join")
    graph.add_edge("account_join", "planner")
    graph.add_edge("email_writer", "verifier")
    graph.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {
            "email_writer": "email_writer",
            "approval_gate": "approval_gate",
        },
    )
    graph.add_edge("approval_gate", "sender")
    graph.add_edge("sender", "planner")

    return graph.compile(checkpointer=checkpointer)


def build_v0_graph(checkpointer: SqliteSaver | None = None):
    """Backward-compatible alias."""
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
        "account_shards": [],
    }
