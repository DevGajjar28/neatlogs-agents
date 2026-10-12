"""Autopilot gate auto-approves verifier-passed drafts."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.agents.autopilot_gate import autopilot_gate_node
from app.config import clear_settings_cache
from app.infra.db import init_db
from app.tools.mailer import lead_id_for


@pytest.fixture()
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "ap.db"
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("SIGNALSDR_SECRET_KEY", key)
    clear_settings_cache()
    init_db(path)
    yield path
    clear_settings_cache()


def test_autopilot_gate_approves_verified(db: Path):
    cid = "c1"
    contact_id = "co1:alice"
    state = {
        "campaign_id": cid,
        "contacts": [
            {
                "id": contact_id,
                "name": "Alice",
                "title": "CTO",
                "email": "alice@acme.test",
                "email_confidence": "verified",
                "company_id": "co1",
            }
        ],
        "drafts": {
            contact_id: [
                {
                    "step": 1,
                    "subject": "Hi",
                    "body": "Hello\n\nOpt out: reply stop",
                    "cited_evidence_ids": [],
                }
            ]
        },
        "verifier": {contact_id: {"passed": True, "action": "pass"}},
        "extras": {},
        "plan": {},
    }
    out = autopilot_gate_node(state)
    approvals = out["extras"]["email_approvals"]
    assert approvals[contact_id]["approved"] is True
    assert lead_id_for(cid, contact_id)
