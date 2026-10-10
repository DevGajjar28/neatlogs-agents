"""U1 API tests — spawn is mocked; no live Crustdata / graph runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import clear_settings_cache
from app.infra.db import connect, init_db
from app.infra.events import emit, set_stage


@pytest.fixture()
def api_env(tmp_path, monkeypatch):
    db = tmp_path / "u1.db"
    monkeypatch.setenv("DB_PATH", str(db))
    monkeypatch.setenv("DATA_MODE", "replay")
    monkeypatch.setenv("DEMO_MODE", "true")
    clear_settings_cache()
    init_db(db)
    from app.api.main import app

    client = TestClient(app)
    yield client, db
    clear_settings_cache()


def _seed_campaign(db_path, cid: str = "u1-seed", status: str = "waiting_icp") -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO campaigns (
                id, created_at, input_json, status, trace_ids,
                options_json, seller_name, seller_domain, current_stage
            )
            VALUES (?, ?, ?, ?, '[]', ?, ?, ?, ?)
            """,
            (
                cid,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(
                    {
                        "company_name": "PostHog",
                        "website": "https://posthog.com",
                        "description": "analytics",
                        "n": 10,
                        "mode": "replay",
                    }
                ),
                status,
                json.dumps({"n": 10, "mode": "replay", "cap": 400}),
                "PostHog",
                "posthog.com",
                "icp",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_health(api_env):
    client, _ = api_env
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_estimate_replay_zero(api_env):
    client, _ = api_env
    r = client.post("/api/estimate", json={"n": 10, "mode": "replay"})
    assert r.status_code == 200
    assert r.json()["total"] == 0.0


def test_list_and_get_campaign(api_env):
    client, db = api_env
    _seed_campaign(db)
    set_stage("u1-seed", "icp", "waiting")
    with patch("app.api.status.pending_interrupt", return_value={"type": "icp_approval", "icp": {}}):
        with patch("app.api.runs.is_alive", return_value=False):
            r = client.get("/api/campaigns")
            assert r.status_code == 200
            rows = r.json()
            assert len(rows) == 1
            assert rows[0]["id"] == "u1-seed"
            assert rows[0]["seller_name"] == "PostHog"
            d = client.get("/api/campaigns/u1-seed")
            assert d.status_code == 200
            body = d.json()
            assert body["status"] == "waiting_icp"
            assert body["stages"]


def test_create_campaign_spawns_child(api_env):
    client, _ = api_env
    with patch("app.api.runs.start_campaign", return_value=4242) as start:
        r = client.post(
            "/api/campaigns",
            json={
                "company_name": "Acme",
                "website": "https://acme.example",
                "description": "widgets",
                "n": 10,
                "mode": "replay",
            },
        )
    assert r.status_code == 201
    body = r.json()
    assert body["id"].startswith("ui-")
    assert body["status"] in {"queued", "running", "waiting_icp", "completed", "failed"}
    start.assert_called_once()
    assert start.call_args.args[0] == body["id"]


def test_icp_post_stores_decision_and_spawns(api_env):
    client, db = api_env
    _seed_campaign(db)
    with patch("app.api.runs.approve_decision", return_value=99) as approve:
        with patch("app.api.state_reader.invalidate"):
            r = client.post(
                "/api/campaigns/u1-seed/icp",
                json={"approved": True, "icp": {"industries": ["Software"]}},
            )
    assert r.status_code == 200
    assert r.json()["decision_id"]
    assert r.json()["pid"] == 99
    approve.assert_called_once()
    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT * FROM gate_decisions WHERE id = ?",
            (r.json()["decision_id"],),
        ).fetchone()
        assert row["gate"] == "icp"
        assert row["status"] == "pending"
        decision = json.loads(row["decision_json"])
        assert decision["approved"] is True
        assert decision["icp"]["industries"] == ["Software"]
    finally:
        conn.close()


def test_email_stage_and_send_approved(api_env):
    client, db = api_env
    _seed_campaign(db, status="waiting_approval")
    contacts = [
        {
            "id": "c1",
            "company_id": "co1",
            "name": "Ada",
            "title": "CEO",
            "role_kind": "economic_buyer",
            "email": "ada@example.com",
            "email_source": "enrich",
            "email_confidence": "likely",
        },
        {
            "id": "c2",
            "company_id": "co1",
            "name": "Bob",
            "title": "CTO",
            "role_kind": "champion",
            "email": "bob@example.com",
            "email_source": "enrich",
            "email_confidence": "likely",
        },
        {
            "id": "c3",
            "company_id": "co1",
            "name": "Gus",
            "title": "VP",
            "role_kind": "champion",
            "email": "gus@example.com",
            "email_source": "guess",
            "email_confidence": "guessed",
        },
    ]
    interrupt = {
        "type": "email_approval",
        "items": [
            {"contact_id": "c1", "lead_id": "l1", "email_confidence": "likely"},
            {"contact_id": "c2", "lead_id": "l2", "email_confidence": "likely"},
            {"contact_id": "c3", "lead_id": "l3", "email_confidence": "guessed"},
        ],
    }
    with patch("app.api.routes.campaigns.state_reader.contacts", return_value=contacts):
        with patch("app.api.routes.campaigns.state_reader.drafts", return_value={}):
            with patch(
                "app.api.routes.campaigns.state_reader.pending_interrupt",
                return_value=interrupt,
            ):
                r1 = client.post(
                    "/api/emails/c1",
                    params={"campaign_id": "u1-seed"},
                    json={"action": "approve"},
                )
                r2 = client.post(
                    "/api/emails/c2",
                    params={"campaign_id": "u1-seed"},
                    json={"action": "reject"},
                )
                assert r1.status_code == 200
                assert r2.status_code == 200
                with patch("app.api.runs.approve_decision", return_value=7) as approve:
                    with patch("app.api.state_reader.invalidate"):
                        send = client.post("/api/campaigns/u1-seed/send-approved")
    assert send.status_code == 200
    approve.assert_called_once()
    conn = connect(db)
    try:
        staged = conn.execute(
            "SELECT contact_id, action FROM email_decisions WHERE campaign_id = ?",
            ("u1-seed",),
        ).fetchall()
        assert {r["contact_id"]: r["action"] for r in staged} == {
            "c1": "approve",
            "c2": "reject",
        }
        gate = conn.execute(
            "SELECT decision_json FROM gate_decisions WHERE id = ?",
            (send.json()["decision_id"],),
        ).fetchone()
        decision = json.loads(gate["decision_json"])
        assert decision["approvals"]["c1"]["approved"] is True
        assert decision["approvals"]["c2"]["approved"] is False
        assert decision["approvals"]["c3"]["approved"] is False  # undecided → not approved
    finally:
        conn.close()


def test_emit_and_set_stage_write_rows(api_env):
    _, db = api_env
    _seed_campaign(db, status="running")
    state = {"campaign_id": "u1-seed", "events": []}
    events = emit(state, "plan.started", "planner", n=10)
    assert events[-1]["type"] == "plan.started"
    set_stage("u1-seed", "plan", "running")
    set_stage("u1-seed", "plan", "done", "ok")
    conn = connect(db)
    try:
        ev = conn.execute(
            "SELECT type, message FROM events WHERE campaign_id = ?", ("u1-seed",)
        ).fetchall()
        assert any(r["type"] == "plan.started" for r in ev)
        st = conn.execute(
            "SELECT status, count_label FROM campaign_stages WHERE campaign_id = ? AND stage = ?",
            ("u1-seed", "plan"),
        ).fetchone()
        assert st["status"] == "done"
        assert st["count_label"] == "ok"
    finally:
        conn.close()


def test_bulk_approve_skips_guessed(api_env):
    client, db = api_env
    _seed_campaign(db, status="waiting_approval")
    contacts = [
        {
            "id": "c1",
            "company_id": "co1",
            "name": "Ada",
            "title": "CEO",
            "role_kind": "economic_buyer",
            "email": "ada@example.com",
            "email_source": "enrich",
            "email_confidence": "likely",
        },
        {
            "id": "c3",
            "company_id": "co1",
            "name": "Gus",
            "title": "VP",
            "role_kind": "champion",
            "email": "gus@example.com",
            "email_source": "guess",
            "email_confidence": "guessed",
        },
    ]
    with patch("app.api.routes.campaigns.state_reader.contacts", return_value=contacts):
        with patch("app.api.routes.campaigns.state_reader.drafts", return_value={}):
            r = client.post(
                "/api/emails/bulk",
                params={"campaign_id": "u1-seed"},
                json={"contact_ids": ["c1", "c3"], "action": "approve"},
            )
    assert r.status_code == 200
    body = r.json()
    assert body["done"] == ["c1"]
    assert body["skipped_guessed"] == ["c3"]
