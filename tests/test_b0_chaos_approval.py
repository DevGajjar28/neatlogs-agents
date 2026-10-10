"""B0: kill_after wrapper, guessed-email approve_all, chaos validation."""

from __future__ import annotations

from typing import Any, TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.agents.approval_gate import approval_gate_node
from app.config import clear_settings_cache
from app.graph import wrap_node
from app.infra.chaos import ChaosConfigError, clear_kill_armed, set_chaos
from app.infra.db import init_db


class _S(TypedDict, total=False):
    events: list
    x: int


def test_kill_after_invalid_node_lists_valid_names():
    with pytest.raises(ChaosConfigError, match="valid names"):
        set_chaos("kill_after=not_a_node")


def test_kill_after_alias_account_researcher():
    clear_kill_armed()
    ctrl = set_chaos("kill_after=account_researcher")
    assert ctrl.kill_after == "account_enrich"


def test_kill_after_exits_on_next_node(monkeypatch: pytest.MonkeyPatch):
    clear_kill_armed()
    set_chaos("kill_after=product_researcher")
    exited: list[int] = []

    def fake_exit(code: int) -> None:
        exited.append(code)
        raise SystemExit(code)

    monkeypatch.setattr("app.graph.os._exit", fake_exit)

    def node_a(state: dict[str, Any]) -> dict[str, Any]:
        return {"x": 1, "events": list(state.get("events") or [])}

    def node_b(state: dict[str, Any]) -> dict[str, Any]:
        return {"x": 2}

    g = StateGraph(_S)
    g.add_node("product_researcher", wrap_node("product_researcher", node_a))
    g.add_node("planner", wrap_node("planner", node_b))
    g.add_edge(START, "product_researcher")
    g.add_edge("product_researcher", "planner")
    g.add_edge("planner", END)
    app = g.compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "kill-test"}}

    with pytest.raises(SystemExit):
        app.invoke({"events": [], "x": 0}, cfg)

    assert exited == [1]
    snap = app.get_state(cfg)
    events = (snap.values or {}).get("events") or []
    assert any(e.get("type") == "chaos.kill_after" and e.get("after_node") == "product_researcher" for e in events)


@pytest.fixture()
def audit_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "audit.db"
    monkeypatch.setenv("DB_PATH", str(path))
    clear_settings_cache()
    init_db(path)
    yield path
    clear_settings_cache()


def test_approve_all_skips_guessed_without_flag(audit_db):
    state = {
        "campaign_id": "c-guess",
        "contacts": [
            {
                "id": "c1",
                "name": "Ada",
                "email": "ada@acme.test",
                "email_confidence": "verified",
                "company_id": "co1",
                "title": "CEO",
            },
            {
                "id": "c2",
                "name": "Bob",
                "email": "bob@acme.test",
                "email_confidence": "guessed",
                "company_id": "co1",
                "title": "CTO",
            },
        ],
        "drafts": {
            "c1": [{"step": 1, "subject": "Hi", "body": "Hello", "cited_evidence_ids": []}],
            "c2": [{"step": 1, "subject": "Hi", "body": "Hello", "cited_evidence_ids": []}],
        },
        "verifier": {
            "c1": {"passed": True, "action": "pass"},
            "c2": {"passed": True, "action": "pass"},
        },
        "events": [],
        "extras": {},
        "plan": {},
    }

    g = StateGraph(dict)
    g.add_node("approval_gate", approval_gate_node)
    g.add_edge(START, "approval_gate")
    g.add_edge("approval_gate", END)
    app = g.compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "approve-guess"}}

    app.invoke(state, cfg)
    result = app.invoke(Command(resume={"approve_all": True, "actor": "test"}), cfg)

    events = result.get("events") or []
    approved = [e for e in events if e.get("type") == "approval.approved"]
    rejected = [e for e in events if e.get("type") == "approval.rejected"]
    skipped = [e for e in events if e.get("type") == "policy.guessed_skipped"]
    assert len(approved) == 1
    assert approved[0]["contact_id"] == "c1"
    assert any(e.get("contact_id") == "c2" for e in rejected)
    assert skipped and skipped[0]["count"] >= 1


def test_approve_all_include_guessed(audit_db):
    state = {
        "campaign_id": "c-guess2",
        "contacts": [
            {
                "id": "c2",
                "name": "Bob",
                "email": "bob@acme.test",
                "email_confidence": "guessed",
                "company_id": "co1",
                "title": "CTO",
            },
        ],
        "drafts": {
            "c2": [{"step": 1, "subject": "Hi", "body": "Hello", "cited_evidence_ids": []}],
        },
        "verifier": {"c2": {"passed": True, "action": "pass"}},
        "events": [],
        "extras": {},
        "plan": {},
    }
    g = StateGraph(dict)
    g.add_node("approval_gate", approval_gate_node)
    g.add_edge(START, "approval_gate")
    g.add_edge("approval_gate", END)
    app = g.compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "approve-guess2"}}
    app.invoke(state, cfg)
    result = app.invoke(
        Command(resume={"approve_all": True, "include_guessed": True, "actor": "test"}),
        cfg,
    )
    approved = [e for e in (result.get("events") or []) if e.get("type") == "approval.approved"]
    assert len(approved) == 1
