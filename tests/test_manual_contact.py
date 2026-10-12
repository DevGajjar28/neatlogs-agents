"""No-contact leads and manual add-contact → draft sequence."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.infra.db import connect, init_db
from app.persist import persist_v0_run


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "mc.db"
    monkeypatch.setenv("DB_PATH", str(path))
    from app.config import clear_settings_cache

    clear_settings_cache()
    init_db(path)
    return path


def test_persist_no_contact_lead(db):
    state = {
        "campaign_id": "c-nc",
        "input": {},
        "contacts": [],
        "drafts": {},
        "companies": [
            {
                "id": "42",
                "name": "Mindarmor",
                "domain": "mindarmor.ai",
                "status": "dropped",
                "drop_reason": "no_contact",
                "fit_score": 1.0,
            }
        ],
    }
    persist_v0_run(state)
    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT status, company_id, contact_id FROM leads WHERE campaign_id = ?",
            ("c-nc",),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["status"] == "no_contact"
    assert row["company_id"] == "42"
    assert row["contact_id"] is None


def test_add_manual_contact_writes_drafts(db, monkeypatch):
    from app.config import clear_settings_cache
    from app.api.main import app

    clear_settings_cache()
    init_db(db)
    conn = connect(db)
    try:
        conn.execute(
            """
            INSERT INTO campaigns (id, created_at, input_json, status, options_json)
            VALUES (
              'c-add',
              '2026-01-01T00:00:00+00:00',
              '{"target_mode":"provided","template_snapshot":"# Voice\\nDirect.","autopilot":false}',
              'completed',
              '{"target_mode":"provided","template_snapshot":"# Voice\\nDirect.","autopilot":false}'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        "app.api.state_reader.companies",
        lambda _cid: [
            {
                "id": "co1",
                "name": "Mindarmor",
                "domain": "mindarmor.ai",
                "status": "dropped",
                "drop_reason": "no_contact",
                "fit_score": 1.0,
            }
        ],
    )
    monkeypatch.setattr(
        "app.api.state_reader.seller",
        lambda _cid: {
            "company_name": "Meruksha",
            "domain": "meruksha.com",
            "one_liner": "AI systems",
            "products": ["AI"],
            "value_props": ["Ship copilots"],
            "pricing_notes": None,
            "named_customers": [],
            "evidence": [],
        },
    )
    monkeypatch.setattr("app.api.state_reader.accounts", lambda _cid: {})
    monkeypatch.setattr("app.api.state_reader.contacts", lambda _cid: [])
    monkeypatch.setattr("app.api.state_reader.drafts", lambda _cid: {})
    monkeypatch.setattr("app.api.state_reader.verifier", lambda _cid: {})
    monkeypatch.setattr(
        "app.api.state_reader.get_values",
        lambda _cid: {
            "extras": {"template_snapshot": "# Voice\nDirect."},
            "input": {"template_snapshot": "# Voice\nDirect."},
        },
    )

    updates: list[dict] = []

    def _upd(cid, patch):
        updates.append(patch)

    monkeypatch.setattr("app.api.state_reader.update_values", _upd)
    monkeypatch.setattr("app.infra.events.set_stage", lambda *a, **k: None)

    def _fake_preview(**kwargs):
        return (
            [
                {
                    "step": 1,
                    "subject": "Hello",
                    "body": 'Hi\n\nIf this isn\'t relevant, reply "stop" and I won\'t email again.',
                    "claims": [],
                    "style_warnings": [],
                },
                {
                    "step": 2,
                    "subject": "Hello",
                    "body": "Follow",
                    "claims": [],
                    "style_warnings": [],
                },
                {
                    "step": 3,
                    "subject": "Hello",
                    "body": "Close",
                    "claims": [],
                    "style_warnings": [],
                },
            ],
            {"system_rules_first": True},
        )

    monkeypatch.setattr(
        "app.agents.email_writer.preview_sequence_for_lead",
        _fake_preview,
    )

    client = TestClient(app)
    resp = client.post(
        "/api/campaigns/c-add/companies/co1/contact",
        json={"name": "Ada Lovelace", "title": "CTO", "email": "ada@mindarmor.ai"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "awaiting_approval"
    assert data["contact_name"] == "Ada Lovelace"
    assert data["email_1_subject"] == "Hello"
    assert updates and updates[0]["contacts"]
    assert updates[0]["drafts"]
    assert updates[0]["extras"]["pending_email_approval"]["type"] == "email_approval"
    assert updates[0]["extras"]["pending_email_approval"]["items"]
    assert updates[0]["plan"]["next"] == "done"
    assert updates[0]["plan"]["phase"] == "awaiting_approval"

    # No Crustdata: preview stub only; ensure contact source is user
    contact = updates[0]["contacts"][0]
    assert contact["email_source"] == "user"
    assert contact["email_confidence"] == "verified"

    conn = connect(db)
    try:
        camp = conn.execute(
            "SELECT status FROM campaigns WHERE id = ?", ("c-add",)
        ).fetchone()
        lead = conn.execute(
            "SELECT status FROM leads WHERE campaign_id = ?", ("c-add",)
        ).fetchone()
    finally:
        conn.close()
    assert camp["status"] == "waiting_approval"
    assert lead["status"] == "awaiting_approval"


def test_pending_approvals_and_inline_send_after_manual_contact(db, monkeypatch):
    """Finished campaign + manual draft → Approvals queue → send-approved without interrupt."""
    from app.config import clear_settings_cache
    from app.api.main import app

    clear_settings_cache()
    init_db(db)
    conn = connect(db)
    try:
        conn.execute(
            """
            INSERT INTO campaigns (id, created_at, input_json, status, options_json)
            VALUES (
              'c-send',
              '2026-01-01T00:00:00+00:00',
              '{"target_mode":"provided","template_snapshot":"# Voice\\nDirect."}',
              'completed',
              '{"target_mode":"provided","send_mode":"sandbox","template_snapshot":"# Voice\\nDirect."}'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    contact_id = "co1:user:abcd1234"
    values = {
        "campaign_id": "c-send",
        "contacts": [
            {
                "id": contact_id,
                "company_id": "co1",
                "name": "Ada",
                "title": "CTO",
                "email": "ada@mindarmor.ai",
                "email_confidence": "verified",
                "email_source": "user",
                "role_kind": "economic_buyer",
            }
        ],
        "companies": [
            {
                "id": "co1",
                "name": "Mindarmor",
                "domain": "mindarmor.ai",
                "status": "kept",
                "fit_score": 1.0,
            }
        ],
        "accounts": {},
        "drafts": {
            contact_id: [
                {
                    "step": 1,
                    "subject": "Hello",
                    "body": 'Hi\n\nIf this isn\'t relevant, reply "stop" and I won\'t email again.',
                    "cited_evidence_ids": [],
                    "claims": [],
                    "send_after_days": 0,
                },
                {
                    "step": 2,
                    "subject": "Hello",
                    "body": "F2",
                    "claims": [],
                    "send_after_days": 3,
                },
                {
                    "step": 3,
                    "subject": "Hello",
                    "body": "F3",
                    "claims": [],
                    "send_after_days": 7,
                },
            ]
        },
        "verifier": {
            contact_id: {"passed": True, "action": "pass", "issues": []}
        },
        "extras": {
            "pending_email_approval": {
                "type": "email_approval",
                "campaign_id": "c-send",
                "items": [
                    {
                        "contact_id": contact_id,
                        "lead_id": "lead-1",
                        "name": "Ada",
                        "title": "CTO",
                        "email": "ada@mindarmor.ai",
                        "email_confidence": "verified",
                        "company_id": "co1",
                        "verifier": {"passed": True},
                        "draft": {
                            "step": 1,
                            "subject": "Hello",
                            "body": 'Hi\n\nIf this isn\'t relevant, reply "stop" and I won\'t email again.',
                        },
                        "sequence_steps": [1, 2, 3],
                        "cited_evidence_ids": [],
                    }
                ],
            }
        },
        "events": [],
        "errors": [],
    }

    monkeypatch.setattr("app.api.state_reader.get_values", lambda _cid: values)
    monkeypatch.setattr("app.api.state_reader.companies", lambda _cid: values["companies"])
    monkeypatch.setattr("app.api.state_reader.accounts", lambda _cid: {})
    monkeypatch.setattr("app.api.state_reader.drafts", lambda _cid: values["drafts"])
    monkeypatch.setattr("app.api.state_reader.contacts", lambda _cid: values["contacts"])
    monkeypatch.setattr(
        "app.api.state_reader.pending_interrupt", lambda _cid: None
    )
    monkeypatch.setattr("app.api.state_reader.invalidate", lambda _cid: None)
    monkeypatch.setattr("app.infra.events.set_stage", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.agents.sender.send",
        lambda **kwargs: {"status": "sent", "email_id": "e1", "message_id": None},
    )

    patches: list[dict] = []

    def _upd(_cid, patch):
        patches.append(patch)
        values.update(patch)

    monkeypatch.setattr("app.api.state_reader.update_values", _upd)

    client = TestClient(app)
    pending = client.get("/api/campaigns/c-send/pending-approvals")
    assert pending.status_code == 200
    body = pending.json()
    assert body["waiting"] is True
    assert len(body["items"]) == 1

    # Stage approve decision
    dec = client.post(
        f"/api/emails/{contact_id}?campaign_id=c-send",
        json={
            "action": "approve",
            "subject": "Hello",
            "body": values["drafts"][contact_id][0]["body"],
        },
    )
    assert dec.status_code == 200, dec.text

    sent = client.post("/api/campaigns/c-send/send-approved")
    assert sent.status_code == 200, sent.text
    data = sent.json()
    assert data.get("inline") is True
    assert data.get("sent", 0) >= 1


def test_pipeline_label_your_list(db):
    from app.api.pipeline import campaign_pipeline
    from app.config import clear_settings_cache

    clear_settings_cache()
    conn = connect(db)
    try:
        conn.execute(
            """
            INSERT INTO campaigns (id, created_at, input_json, status, options_json)
            VALUES (
              'c-pipe',
              '2026-01-01T00:00:00+00:00',
              '{}',
              'running',
              '{"target_mode":"provided"}'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    pipe = campaign_pipeline("c-pipe")
    buyer = next(a for a in pipe.agents if a.agent == "buyer_finder")
    assert buyer.label == "Your list"
