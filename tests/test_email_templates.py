"""Email template CRUD, snapshot, writer prompt order, preview no Crustdata."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.email_writer import SYSTEM_RULES, build_writer_prompt
from app.infra.email_templates import (
    create_template,
    delete_template,
    get_default_template,
    list_templates,
    set_default_template,
    snapshot_for_campaign,
    style_warnings,
    update_template,
)
from app.models import AccountBrief, Contact, SellerBrief


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "t.db"
    monkeypatch.setenv("DB_PATH", str(path))
    from app.config import clear_settings_cache
    from app.infra.db import init_db

    clear_settings_cache()
    init_db(path)
    return path


def test_seed_system_default(db):
    rows = list_templates(db)
    assert any(r["is_system"] and r["is_default"] for r in rows)
    assert "Voice" in get_default_template(db)["content_md"]


def test_system_template_protected(db):
    system = next(r for r in list_templates(db) if r["is_system"])
    with pytest.raises(PermissionError):
        update_template(system["id"], name="hacked", db_path=db)
    with pytest.raises(PermissionError):
        delete_template(system["id"], db_path=db)


def test_crud_duplicate_default(db):
    created = create_template(
        name="Casual",
        description="warmer",
        content_md="# Voice\nFriendly but brief.\n",
        db_path=db,
    )
    assert created["id"]
    updated = update_template(
        created["id"], content_md="# Voice\nEven warmer.\n", db_path=db
    )
    assert "Even warmer" in updated["content_md"]
    set_default_template(created["id"], db_path=db)
    assert get_default_template(db)["id"] == created["id"]
    from app.infra.email_templates import duplicate_template

    copy = duplicate_template(created["id"], db_path=db)
    assert copy["id"] != created["id"]
    assert "(copy)" in copy["name"]


def test_snapshot_stored_independently(db):
    created = create_template(
        name="Snap",
        content_md="# Original snap content\n",
        db_path=db,
    )
    snap = snapshot_for_campaign(created["id"], db_path=db)
    assert snap["template_snapshot"] == "# Original snap content\n" or snap[
        "template_snapshot"
    ].startswith("# Original")
    update_template(created["id"], content_md="# Edited later\n", db_path=db)
    # Snapshot captured earlier is unchanged
    assert "Original" in snap["template_snapshot"]
    assert "Edited" not in snap["template_snapshot"]


def test_writer_prompt_system_rules_before_template():
    seller = SellerBrief(
        company_name="SellerCo",
        domain="seller.example",
        one_liner="Does X",
        products=["X"],
        value_props=["Y"],
        pricing_notes=None,
        named_customers=[],
        evidence=[],
    )
    contact = Contact(
        id="c1",
        company_id="co1",
        name="Ada Lovelace",
        title="CTO",
        role_kind="economic_buyer",
        email=None,
        email_source="none",
        email_confidence="none",
        profile_url=None,
    )
    account = AccountBrief(
        company_id="co1",
        story="Growing.",
        why_now=["Hiring"],
        evidence=[],
    )
    prompt = build_writer_prompt(
        step=1,
        max_words=120,
        tone="direct",
        allowed_ids=["ev_abc"],
        seller=seller,
        contact=contact,
        account=account,
        company_name="Acme",
        evidence_lines=["[ev_abc] fact"],
        template_snapshot="# Custom voice\nBe witty.\n",
    )
    assert prompt.startswith("SYSTEM RULES")
    sys_idx = prompt.index("SYSTEM RULES")
    tpl_idx = prompt.index("<template>")
    assert sys_idx < tpl_idx
    assert "Be witty" in prompt
    assert SYSTEM_RULES[:20] in prompt


def test_style_warnings_banned_and_emdash():
    warns = style_warnings("Hello", "This is a game-changer — synergy awaits")
    assert any("game-changer" in w for w in warns)
    assert any("em dash" in w for w in warns)
    assert any("synergy" in w for w in warns)


def test_api_crud_and_system_403(db, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(db))
    from app.config import clear_settings_cache
    from app.api.main import app

    clear_settings_cache()
    client = TestClient(app)
    listed = client.get("/api/email-templates")
    assert listed.status_code == 200
    system_id = next(t["id"] for t in listed.json() if t["is_system"])
    bad = client.put(
        f"/api/email-templates/{system_id}",
        json={"name": "nope"},
    )
    assert bad.status_code == 403
    created = client.post(
        "/api/email-templates",
        json={"name": "API style", "description": "", "content_md": "# Hi\n"},
    )
    assert created.status_code == 201
    tid = created.json()["id"]
    deleted = client.delete(f"/api/email-templates/{tid}")
    assert deleted.status_code == 204


def test_preview_reports_zero_crustdata(db, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(db))
    from app.config import clear_settings_cache
    from app.api.main import app
    from app.infra.db import connect, init_db

    clear_settings_cache()
    init_db(db)
    conn = connect(db)
    try:
        conn.execute(
            """
            INSERT INTO campaigns (id, created_at, input_json, status, options_json)
            VALUES ('camp-prev', '2026-01-01T00:00:00+00:00', '{}', 'completed', '{}')
            """
        )
        conn.commit()
    finally:
        conn.close()

    # Stub state_reader + writer preview
    monkeypatch.setattr(
        "app.api.state_reader.contacts",
        lambda _cid: [
            {
                "id": "c1",
                "company_id": "co1",
                "name": "Ada",
                "title": "CTO",
                "role_kind": "economic_buyer",
                "email": None,
                "email_source": "none",
                "email_confidence": "none",
                "profile_url": None,
            }
        ],
    )
    monkeypatch.setattr(
        "app.api.state_reader.accounts",
        lambda _cid: {
            "co1": {
                "company_id": "co1",
                "story": "Growing",
                "why_now": ["news"],
                "evidence": [],
            }
        },
    )
    monkeypatch.setattr(
        "app.api.state_reader.seller",
        lambda _cid: {
            "company_name": "Seller",
            "domain": "seller.example",
            "one_liner": "X",
            "products": ["X"],
            "value_props": ["Y"],
            "pricing_notes": None,
            "named_customers": [],
            "evidence": [],
        },
    )
    monkeypatch.setattr(
        "app.api.state_reader.companies",
        lambda _cid: [{"id": "co1", "name": "Acme"}],
    )

    def _fake_preview(**kwargs):
        return (
            [
                {
                    "step": 1,
                    "subject": "Hi",
                    "body": "Body\n\nIf this isn't relevant, reply \"stop\" and I won't email again.",
                    "claims": [],
                    "style_warnings": [],
                },
                {
                    "step": 2,
                    "subject": "Hi",
                    "body": "Follow",
                    "claims": [],
                    "style_warnings": [],
                },
                {
                    "step": 3,
                    "subject": "Hi",
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

    from app.api.main import app as fastapi_app

    client = TestClient(fastapi_app)
    system_id = list_templates(db)[0]["id"]
    resp = client.post(
        f"/api/email-templates/{system_id}/preview",
        json={"campaign_id": "camp-prev"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["preview"] is True
    assert data["crustdata_calls"] == 0
    assert data["prompt_contains_system_rules"] is True
    assert len(data["steps"]) == 3
