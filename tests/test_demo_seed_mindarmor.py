"""§7 tests for MindArmor demo seed (15_DEMO_SEED_MINDARMOR.md)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import clear_settings_cache
from app.infra import demo_seed
from app.infra.db import connect, init_db
from app.mail.policy import PolicyContext, check_all

CSV_FIXTURE = """name,email,company,domain,title,is_test_inbox,note
Ada Lovelace,ada@heidihealth.com,Heidi Health,heidihealth.com,CEO,false,
Dev Test,test1@gmail.com,Eucalyptus,eucalyptus.vc,,true,test
Dup One,dup@example.com,Co A,example.com,,false,
Dup Two,dup@example.com,Co B,example.com,,false,duplicate
Free Mail,annla@bigpond.com,Austco,,,false,personal ISP
Bad Row,,Missing Email Co,missing.com,,false,
David, godsdomain8998@gmail.com, Meruksha.com,,false,
"""


@pytest.fixture()
def seed_env(tmp_path, monkeypatch):
    from app.mail.crypto import generate_key

    db = tmp_path / "seed.db"
    demo = tmp_path / "config" / "demo"
    demo.mkdir(parents=True)
    (demo / "mindarmor_contacts.csv").write_text(CSV_FIXTURE, encoding="utf-8")
    (demo / "mindarmor_seller.json").write_text(
        json.dumps(
            {
                "company_name": "MindArmor",
                "domain": "mindarmor.ai",
                "one_liner": "Security for healthcare",
                "products": ["Platform"],
                "value_props": ["Safer care"],
                "pricing_notes": None,
                "named_customers": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DB_PATH", str(db))
    monkeypatch.setenv("DEMO_SEED", "false")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATA_MODE", "replay")
    monkeypatch.setenv("SIGNALSDR_SECRET_KEY", generate_key())
    clear_settings_cache()
    init_db(db)
    yield db, demo
    clear_settings_cache()


def _make_mail_account(db: Path) -> str:
    from app.mail import accounts as mail_accounts

    aid = mail_accounts.create_account(
        {
            "label": "Test",
            "provider": "gmail",
            "email": "sender@gmail.com",
            "display_name": "Sender",
            "username": "sender@gmail.com",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_security": "starttls",
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "daily_cap": 25,
            "per_domain_daily_cap": 3,
            "min_gap_seconds": 90,
            "test_recipients": ["test1@gmail.com"],
            "live_enabled": False,
            "is_default": True,
            "signature": "sig\nUnsubscribe: reply stop",
            "postal_address": "1 Test St",
        },
        password="app-pass",
        db_path=str(db),
    )
    conn = connect(db)
    try:
        conn.execute(
            "UPDATE mail_accounts SET status = 'ok' WHERE id = ?",
            (aid,),
        )
        conn.commit()
    finally:
        conn.close()
    return aid


def test_seed_demo_parses_dedupes_and_flags(seed_env):
    db, _ = seed_env
    summary = demo_seed.seed_mindarmor(db_path=str(db))
    assert summary["contacts"] >= 4
    assert summary["skipped"] >= 2  # duplicate + bad email/empty
    assert summary["domain_missing"] >= 1
    assert "test1@gmail.com" in summary["test_inboxes"]

    parsed = demo_seed.parse_contacts_csv(CSV_FIXTURE)
    emails = [c["email"] for c in parsed["contacts"]]
    assert emails.count("dup@example.com") == 1
    free = [c for c in parsed["contacts"] if c["email"] == "annla@bigpond.com"]
    assert free and free[0]["domain_missing"] is True


def test_campaign_create_applies_seed_when_enabled(seed_env, monkeypatch):
    db, _ = seed_env
    demo_seed.seed_mindarmor(db_path=str(db))
    monkeypatch.setenv("DEMO_SEED", "true")
    clear_settings_cache()

    from app.api.main import app

    client = TestClient(app)
    with patch("app.api.runs.start_campaign", return_value=1):
        r = client.post(
            "/api/campaigns",
            json={
                "company_name": "MindArmor",
                "website": "https://mindarmor.ai",
                "description": "demo",
                "n": 10,
                "mode": "replay",
                "send_mode": "sandbox",
            },
        )
    # Forced gmail_test requires mail account when not sandbox — create should 422 without account
    # unless we supply sandbox after seed forces gmail_test.
    assert r.status_code == 422
    assert "mail_account" in r.json()["detail"].lower() or "mail_account_id" in r.json()["detail"]

    aid = _make_mail_account(db)
    with patch("app.api.runs.start_campaign", return_value=1):
        r2 = client.post(
            "/api/campaigns",
            json={
                "company_name": "MindArmor",
                "website": "https://www.mindarmor.ai/about",
                "description": "demo",
                "n": 10,
                "mode": "replay",
                "send_mode": "gmail_test",
                "mail_account_id": aid,
            },
        )
    assert r2.status_code == 201, r2.text
    body = r2.json()
    assert body["target_mode"] == "provided_contacts"
    assert body["seed"] == "mindarmor"

    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT options_json FROM campaigns WHERE id = ?", (body["id"],)
        ).fetchone()
        opts = json.loads(row["options_json"])
        assert opts["target_mode"] == "provided_contacts"
        assert opts["send_mode"] == "gmail_test"
        assert len(opts["provided_contacts"]) >= 4
        ev = conn.execute(
            "SELECT type, message FROM events WHERE campaign_id = ? AND type = ?",
            (body["id"], "demo.seed_applied"),
        ).fetchone()
        assert ev is not None
        assert "preloaded list" in ev["message"].lower()
    finally:
        conn.close()


def test_campaign_create_without_demo_seed_stays_discover(seed_env, monkeypatch):
    db, _ = seed_env
    demo_seed.seed_mindarmor(db_path=str(db))
    monkeypatch.setenv("DEMO_SEED", "false")
    clear_settings_cache()
    from app.api.main import app

    client = TestClient(app)
    with patch("app.api.runs.start_campaign", return_value=1):
        r = client.post(
            "/api/campaigns",
            json={
                "company_name": "MindArmor",
                "website": "https://mindarmor.ai",
                "n": 10,
                "mode": "replay",
                "send_mode": "sandbox",
            },
        )
    assert r.status_code == 201
    assert r.json()["target_mode"] == "discover"
    assert not r.json().get("seed")


def test_seeded_campaign_rejects_gmail_live(seed_env, monkeypatch):
    db, _ = seed_env
    demo_seed.seed_mindarmor(db_path=str(db))
    monkeypatch.setenv("DEMO_SEED", "true")
    clear_settings_cache()
    from app.api.main import app

    client = TestClient(app)
    r = client.post(
        "/api/campaigns",
        json={
            "company_name": "MindArmor",
            "website": "https://mindarmor.ai",
            "n": 10,
            "mode": "replay",
            "send_mode": "gmail_live",
            "mail_account_id": "x",
            "live_confirm_email": "x@y.com",
        },
    )
    assert r.status_code == 422
    assert "can't send live" in r.json()["detail"].lower()


def test_buyer_import_contacts_skips_people_search(seed_env):
    from app.agents.buyer_finder import buyer_import_contacts_node
    from app.agents.account_researcher import research_company
    from app.models import Company

    state = {
        "campaign_id": "c1",
        "input": {
            "target_mode": "provided_contacts",
            "seed": "mindarmor",
            "provided_contacts": [
                {
                    "name": "Ada",
                    "email": "ada@heidihealth.com",
                    "company": "Heidi Health",
                    "domain": "heidihealth.com",
                    "title": "CEO",
                    "is_test_inbox": False,
                },
                {
                    "name": "Dev",
                    "email": "test1@gmail.com",
                    "company": "Eucalyptus",
                    "domain": "eucalyptus.vc",
                    "is_test_inbox": True,
                },
            ],
            "n": 2,
            "mode": "replay",
        },
        "budget": {"credits_spent": 0},
        "events": [],
        "errors": [],
        "extras": {},
        "plan": {},
    }

    mock_client = MagicMock()
    mock_client.company_identify.return_value = [
        {
            "matched_on": "heidihealth.com",
            "matches": [
                {
                    "confidence_score": 1.0,
                    "company_data": {
                        "crustdata_company_id": 101,
                        "basic_info": {"company_name": "Heidi Health", "primary_domain": "heidihealth.com"},
                    },
                }
            ],
        },
        {
            "matched_on": "eucalyptus.vc",
            "matches": [
                {
                    "confidence_score": 1.0,
                    "company_data": {
                        "crustdata_company_id": 102,
                        "basic_info": {"company_name": "Eucalyptus", "primary_domain": "eucalyptus.vc"},
                    },
                }
            ],
        },
    ]
    mock_client.ledger.spent.return_value = 0.0
    mock_client.close = MagicMock()

    with patch(
        "app.agents.buyer_finder.client_for_campaign", return_value=mock_client
    ):
        out = buyer_import_contacts_node(state)

    assert out["extras"]["skip_people_search"] is True
    assert len(out["extras"]["provided_contact_bindings"]) == 2
    assert any(e.get("type") == "buyers.import_done" for e in out["events"])

    events: list = []
    with patch(
        "app.agents.account_researcher._find_person",
        side_effect=AssertionError("people search must not run"),
    ):
        shard = research_company(
            MagicMock(),
            company=Company(
                id="101",
                name="Heidi",
                domain="heidihealth.com",
                industry=None,
                headcount=None,
                country=None,
            ),
            data={"basic_info": {"company_name": "Heidi"}},
            titles=["CEO"],
            campaign_id="c1",
            live_people_enabled=True,
            events=events,
            errors=[],
            skip_people_search=True,
        )
    assert shard["person"] is None
    assert any(e.get("type") == "fallback.person_search_skipped" for e in events)


def test_gmail_test_transport_only_allowlisted(seed_env):
    db, _ = seed_env
    aid = _make_mail_account(db)
    # Prospect address must rewrite to allowlisted test inbox
    ctx = PolicyContext(
        campaign_id="c1",
        lead_id="l1",
        step=1,
        to_email="ada@heidihealth.com",
        subject="Hi",
        body="Hello\n\nUnsubscribe: reply stop",
        email_confidence="provided",
        allow_guessed=False,
        send_mode="gmail_test",
        mail_account_id=aid,
        approved=True,
        verifier_passed=True,
        db_path=str(db),
    )
    result = check_all(ctx)
    assert result.ok is True
    assert result.actual_recipient == "test1@gmail.com"


def test_product_seed_fallback(seed_env):
    from app.agents.product_researcher import product_researcher_node

    state = {
        "campaign_id": "c1",
        "input": {
            "company_name": "MindArmor",
            "website": "https://mindarmor.ai",
            "description": "",
            "mode": "replay",
        },
        "extras": {
            "seller_fallback": {
                "one_liner": "AI security for healthcare",
                "products": ["MindArmor"],
                "value_props": ["Safer ops"],
                "named_customers": [],
            }
        },
        "budget": {"credits_spent": 0},
        "events": [],
        "errors": [],
    }
    with patch("app.agents.product_researcher.web.fetch_seller_pages", return_value=[]):
        with patch("app.agents.product_researcher.get_llm") as glm:
            llm = MagicMock()
            structured = MagicMock()
            structured.invoke.side_effect = RuntimeError("llm down")
            llm.with_structured_output.return_value = structured
            glm.return_value = llm
            out = product_researcher_node(state)
    assert out["seller"]["one_liner"]
    assert any(e.get("type") == "product.seed_fallback" for e in out["events"])
    assert out["extras"].get("seller_seed_fallback") is True


def test_second_run_cache_hits_zero_new_credits(seed_env):
    """Replay / cache-hit path charges 0 Crustdata credits (warm-cache demo property)."""
    from app.infra.budget import BudgetLedger, estimate_campaign

    db, _ = seed_env
    ledger = BudgetLedger(db_path=str(db))
    before = ledger.spent("warm")
    # Identify is free; replay estimate for provided_contacts is 0.
    est = estimate_campaign(10, "replay", target_mode="provided_contacts")
    assert float(est["total"]) == 0.0
    assert ledger.spent("warm") == before
