"""ICP auto-approve and agent pipeline shape."""

from __future__ import annotations

from app.agents.buyer_finder import icp_gate_node
from app.api.pipeline import campaign_pipeline
from app.infra.db import connect, init_db
from app.infra.events import set_stage
from app.infra.event_messages import format_message


def test_icp_gate_auto_approves_without_interrupt(monkeypatch):
    monkeypatch.setattr("app.infra.events.set_stage", lambda *a, **k: None)
    state = {
        "campaign_id": "pipe-1",
        "icp": {
            "industries": ["Software"],
            "headcount_min": 50,
            "headcount_max": 200,
            "countries": ["United States"],
            "employee_count_ranges": ["51-200"],
            "funding_stages": [],
            "roles": [],
            "rationale": "Lookalikes of named customers",
            "evidence": [],
            "approved": False,
        },
        "events": [],
        "plan": {"phase": "after_icp_proposed"},
    }
    out = icp_gate_node(state)
    assert out["icp"]["approved"] is True
    types = [e["type"] for e in out["events"] if isinstance(e, dict)]
    assert "icp.auto_approved" in types
    assert out["plan"]["phase"] == "after_icp_approved"


def test_pipeline_six_agents_idle(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setenv("DB_PATH", str(db))
    from app.config import clear_settings_cache

    clear_settings_cache()
    init_db(str(db))
    conn = connect(str(db))
    try:
        conn.execute(
            """
            INSERT INTO campaigns (id, status, input_json, options_json, created_at)
            VALUES ('pipe-1', 'queued', '{}', '{}', '2026-01-01T00:00:00+00:00')
            """
        )
        conn.commit()
    finally:
        conn.close()

    pipe = campaign_pipeline("pipe-1")
    assert len(pipe.agents) == 6
    assert [a.agent for a in pipe.agents] == [
        "planner",
        "product_researcher",
        "buyer_finder",
        "account_researcher",
        "email_writer_verifier",
        "sender",
    ]
    assert all(a.status == "idle" for a in pipe.agents)
    assert all(a.detail is None for a in pipe.agents)


def test_pipeline_waiting_on_approval(tmp_path, monkeypatch):
    db = tmp_path / "t2.db"
    monkeypatch.setenv("DB_PATH", str(db))
    from app.config import clear_settings_cache, get_settings

    clear_settings_cache()
    init_db(str(db))
    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            INSERT INTO campaigns (id, status, input_json, options_json, created_at)
            VALUES ('pipe-2', 'waiting_approval', '{}', '{}', '2026-01-01T00:00:00+00:00')
            """
        )
        conn.commit()
    finally:
        conn.close()
    set_stage("pipe-2", "emails", "done", "6 sequences")
    set_stage("pipe-2", "verify", "done", "1 passed")
    set_stage("pipe-2", "approval", "waiting")

    pipe = campaign_pipeline("pipe-2")
    email_card = next(a for a in pipe.agents if a.agent == "email_writer_verifier")
    assert email_card.status == "waiting"
    assert email_card.count_label == "1 passed"


def test_event_message_templates_concrete():
    msg = format_message(
        "account.researching",
        {"company": "Acme"},
    )
    assert "Acme" in msg
    assert "tech stack" in msg
