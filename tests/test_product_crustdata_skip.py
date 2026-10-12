"""Product research must not depend on Crustdata; Hunter path when credits exhausted."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agents.account_researcher import _find_person, account_enrich_node, research_company
from app.agents.planner import planner_node
from app.agents.product_researcher import product_researcher_node
from app.config import clear_settings_cache
from app.models import Company
from app.tools.crustdata import OutOfCredits


def test_product_researcher_website_only_no_crustdata_client(monkeypatch):
    pages = [
        {
            "url": "https://acme.test/",
            "text": "Acme builds analytics for B2B teams. Customers include Globex.",
            "quarantined": [],
        }
    ]
    monkeypatch.setattr(
        "app.agents.product_researcher.web.fetch_seller_pages",
        lambda *a, **k: pages,
    )
    monkeypatch.setattr(
        "app.agents.product_researcher.web.heuristic_named_customers",
        lambda *a, **k: ["Globex"],
    )

    class _LLM:
        def with_structured_output(self, model):
            return self

        def invoke(self, prompt):
            from app.agents.product_researcher import _ExtractedSeller

            return _ExtractedSeller(
                one_liner="Analytics for B2B",
                products=["Acme Analytics"],
                value_props=["Faster insights"],
                named_customers=["Globex"],
            )

    monkeypatch.setattr("app.agents.product_researcher.get_llm", lambda kind="fast": _LLM())
    # If product research still imports/calls Crustdata, this blows up.
    monkeypatch.setattr(
        "app.tools.crustdata.client_for_campaign",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Crustdata must not be called")),
    )

    out = product_researcher_node(
        {
            "campaign_id": "prod-web",
            "input": {
                "company_name": "Acme",
                "website": "https://acme.test",
                "description": "Analytics",
            },
            "events": [],
            "errors": [],
            "budget": {"credits_spent": 0},
            "extras": {},
        }
    )
    assert out["seller"]["company_name"] == "Acme"
    assert out["seller"]["one_liner"]
    assert not any(
        "nsufficient credit" in str(e.get("error", "")).lower() for e in out.get("errors") or []
    )
    assert any(e.get("type") == "fallback.seller_crustdata_skipped" for e in out["events"])


def test_account_enrich_marks_exhausted_on_402(monkeypatch):
    class _Ledger:
        def spent(self, cid):
            return 0.0

    class _Client:
        ledger = _Ledger()

        def close(self):
            return None

        def company_enrich(self, body, *, campaign_id="default", step=""):
            raise OutOfCredits("Insufficient credits. Buy credits at https://crustdata.com")

    monkeypatch.setattr(
        "app.agents.account_researcher.client_for_campaign",
        lambda state: _Client(),
    )
    state = {
        "campaign_id": "c-ex",
        "companies": [
            {
                "id": "101",
                "name": "Acme",
                "domain": "acme.test",
                "industry": "Software",
                "headcount": None,
                "country": "US",
                "fit_score": 0.9,
                "status": "kept",
            }
        ],
        "accounts": {},
        "extras": {},
        "events": [],
        "errors": [],
        "budget": {"credits_spent": 0},
    }
    out = account_enrich_node(state)
    assert out["extras"]["crustdata_exhausted"] is True
    assert any(e.get("type") == "fallback.crustdata_exhausted" for e in out["events"])
    assert not any(e.get("step") == "account.enrich" for e in out.get("errors") or [])


def test_find_person_skips_person_search_when_exhausted(monkeypatch):
    calls: list[str] = []

    class _Client:
        data_mode = "replay"

        def person_search(self, *a, **k):
            calls.append("person_search")
            raise AssertionError("person_search must be skipped when exhausted")

    monkeypatch.setattr(
        "app.agents.account_researcher.hunter_tool.find_person_from_domain",
        lambda **kw: {
            "name": "Ada Lovelace",
            "title": "CTO",
            "email": "ada@acme.test",
            "email_source": "hunter",
            "email_confidence": "high",
            "profile_url": None,
        },
    )
    company = Company(
        id="101",
        name="Acme",
        domain="acme.test",
        industry="Software",
        headcount=None,
        country="US",
        fit_score=0.9,
        status="kept",
    )
    events: list[dict] = []
    errors: list[dict] = []
    person = _find_person(
        _Client(),  # type: ignore[arg-type]
        company=company,
        data={"people": {}},
        titles=["CTO"],
        campaign_id="c1",
        live_people_enabled=False,
        crustdata_exhausted=True,
        events=events,
        errors=errors,
    )
    assert person is not None
    assert person["name"] == "Ada Lovelace"
    assert calls == []
    assert any(e.get("type") == "fallback.person_search_skipped" for e in events)
    assert any(e.get("type") == "fallback.hunter_domain" for e in events)


def test_planner_partial_contacts_when_exhausted(monkeypatch):
    monkeypatch.setenv("MAX_CREDITS", "400")
    clear_settings_cache()
    state = {
        "campaign_id": "partial-1",
        "input": {"n": 10},
        "plan": {
            "initialized": True,
            "phase": "after_account",
            "widenings": 0,
            "max_widenings": 2,
            "max_credits": 400,
        },
        "budget": {"credits_spent": 5},
        "extras": {"crustdata_exhausted": True},
        "contacts": [
            {
                "id": "101:ada",
                "company_id": "101",
                "name": "Ada",
                "title": "CTO",
                "email": "ada@acme.test",
            }
        ],
        "companies": [
            {
                "id": "101",
                "name": "Acme",
                "domain": "acme.test",
                "status": "kept",
                "fit_score": 0.9,
                "industry": "Software",
                "headcount": None,
                "country": "US",
            },
            {
                "id": "102",
                "name": "BufferCo",
                "domain": "buffer.test",
                "status": "dropped",
                "drop_reason": "below_top_n",
                "fit_score": 0.5,
                "industry": "Software",
                "headcount": None,
                "country": "US",
            },
        ],
        "events": [],
    }
    out = planner_node(state)
    assert out["plan"]["next"] == "email_writer"
    assert any(e.get("type") == "plan.partial_contacts" for e in out["events"])


def test_format_credit_error_soft_message():
    from app.infra.event_messages import format_message

    msg = format_message(
        "error",
        {
            "step": "product_researcher",
            "detail": "Insufficient credits. Buy credits at https://crustdata.com",
        },
    )
    assert "Buy credits" not in msg
    assert "website" in msg.lower()
