"""Account researcher fallback chain — mocked Crustdata only (no live credits)."""

from __future__ import annotations

from typing import Any

from app.agents.account_researcher import account_enrich_node, account_join_node, research_company
from app.agents.planner import planner_node
from app.infra.chaos import set_chaos
from app.models import Company


class _FakeClient:
    def __init__(self, script: dict[str, Any] | None = None) -> None:
        self.script = script or {}
        self.calls: list[tuple[str, dict]] = []
        self.ledger = type("L", (), {"spent": lambda self, cid: 0.0})()

    def close(self) -> None:
        return None

    def company_enrich(self, body: dict, *, campaign_id: str = "default", step: str = "") -> Any:
        self.calls.append(("company_enrich", body))
        return self.script.get(
            "company_enrich",
            [
                {
                    "matches": [
                        {
                            "company_data": {
                                "crustdata_company_id": 101,
                                "basic_info": {"name": "Acme", "primary_domain": "acme.test"},
                                "people": {
                                    "decision_makers": [{"name": "Hidden", "title": "CTO"}]
                                },
                                "news": {},
                            }
                        }
                    ]
                }
            ],
        )

    def person_search(self, body: dict, *, campaign_id: str = "default", step: str = "") -> Any:
        self.calls.append((step or "person_search", body))
        if body.get("explain"):
            return {
                "profiles": [],
                "remarks": [
                    {
                        "code": "FILTER_TOO_STRICT",
                        "path": "experience.employment_details.current.title",
                    }
                ],
            }
        if body.get("search"):
            return {
                "profiles": [
                    {
                        "basic_profile": {"name": "Ada Lovelace", "current_title": "CTO"},
                        "social_handles": {
                            "professional_network_identifier": {
                                "profile_url": "https://www.linkedin.com/in/ada"
                            }
                        },
                    }
                ]
            }
        return {"profiles": []}

    def person_enrich(self, body: dict, *, campaign_id: str = "default", step: str = "") -> Any:
        self.calls.append(("person_enrich", body))
        return [
            {
                "matched_on": "https://www.linkedin.com/in/ada",
                "match_status": "matched",
                "matches": [
                    {"person_data": {"contact": {"business_emails": ["ada@example.com"]}}}
                ],
            }
        ]

    def web_search(self, body: dict, *, campaign_id: str = "default", step: str = "") -> Any:
        self.calls.append(("web_search", body))
        return {"results": []}

    def web_fetch(self, body: dict, *, campaign_id: str = "default", step: str = "") -> Any:
        self.calls.append(("web_fetch", body))
        return {"results": []}


def test_empty_people_triggers_explain_and_semantic_fallback(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATA_MODE", "replay")
    from app.config import clear_settings_cache

    clear_settings_cache()
    monkeypatch.setattr(
        "app.agents.account_researcher.web.fetch_prospect_pages",
        lambda *a, **k: [],
    )
    company = Company(
        id="101",
        name="Acme",
        domain="acme.test",
        industry="Software",
        headcount=None,
        country="United States",
        fit_score=0.9,
        status="kept",
    )
    fake = _FakeClient()
    events: list[dict] = []
    errors: list[dict] = []
    shard = research_company(
        fake,  # type: ignore[arg-type]
        company=company,
        data={"people": {}},
        titles=["CTO", "VP Engineering"],
        campaign_id="t-fallback",
        live_people_enabled=False,
        events=events,
        errors=errors,
    )
    assert shard["person"] is not None
    assert shard["person"]["name"] == "Ada Lovelace"
    assert any(e.get("type") == "recovery.explain_retry" for e in events)
    assert any(
        e.get("type") == "fallback.contact_step_2" and e.get("source") == "person_search_semantic"
        for e in events
    )
    steps = [c[0] for c in fake.calls]
    assert "account.person_search" in steps
    assert "account.person_search.explain" in steps
    assert "account.person_search.semantic" in steps


def test_planner_replace_no_contact(monkeypatch):
    monkeypatch.setenv("MAX_CREDITS", "400")
    from app.config import clear_settings_cache

    clear_settings_cache()
    state = {
        "campaign_id": "t1",
        "input": {"n": 2},
        "plan": {
            "initialized": True,
            "phase": "after_account",
            "widenings": 0,
            "max_widenings": 2,
            "max_credits": 400,
        },
        "budget": {"credits_spent": 1},
        "companies": [
            {
                "id": "1",
                "name": "A",
                "domain": "a.test",
                "industry": None,
                "headcount": None,
                "country": None,
                "fit_score": 0.9,
                "fit_reasons": [],
                "status": "dropped",
                "drop_reason": "no_contact",
            },
            {
                "id": "2",
                "name": "B",
                "domain": "b.test",
                "industry": None,
                "headcount": None,
                "country": None,
                "fit_score": 0.5,
                "fit_reasons": [],
                "status": "dropped",
                "drop_reason": "below_top_n",
            },
        ],
        "contacts": [],
        "events": [{"type": "account.no_contact", "company_id": "1"}],
    }
    out = planner_node(state)
    assert out["plan"]["next"] == "account_researcher"
    assert any(e.get("type") == "plan.replace_no_contact" for e in out["events"])
    promoted = [c for c in out["companies"] if c["id"] == "2"]
    assert promoted and promoted[0]["status"] == "kept"


def test_enrich_chaos_empty_people_and_join(monkeypatch):
    set_chaos("empty_people")
    fake = _FakeClient()
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATA_MODE", "replay")
    from app.config import clear_settings_cache

    clear_settings_cache()
    monkeypatch.setattr(
        "app.agents.account_researcher.web.fetch_prospect_pages",
        lambda *a, **k: [],
    )

    monkeypatch.setattr(
        "app.agents.account_researcher.CrustdataClient",
        lambda *a, **k: fake,
    )
    monkeypatch.setattr(
        "app.agents.account_researcher.client_for_campaign",
        lambda *a, **k: fake,
    )
    monkeypatch.setattr(
        "app.agents.account_researcher.get_llm",
        lambda kind="fast": type(
            "L",
            (),
            {"invoke": lambda self, p: type("R", (), {"content": "Story (ev_x)"})()},
        )(),
    )
    monkeypatch.setattr("app.agents.account_researcher._mx_ok", lambda domain: True)

    state = {
        "campaign_id": "mock-account",
        "companies": [
            {
                "id": "101",
                "name": "Acme",
                "domain": "acme.test",
                "industry": "Software",
                "headcount": None,
                "country": "United States",
                "fit_score": 0.9,
                "fit_reasons": [],
                "status": "kept",
                "drop_reason": None,
            }
        ],
        "accounts": {},
        "contacts": [],
        "events": [],
        "errors": [],
        "budget": {"credits_spent": 0},
        "extras": {},
        "plan": {},
    }
    enriched = account_enrich_node(state)
    assert any(e.get("type") == "chaos.empty_people" for e in enriched["events"])
    people = (enriched["extras"]["enrich_by_id"]["101"]).get("people")
    assert people == {}

    events: list[dict] = []
    errors: list[dict] = []
    shard = research_company(
        fake,  # type: ignore[arg-type]
        company=Company.model_validate(state["companies"][0]),
        data=enriched["extras"]["enrich_by_id"]["101"],
        titles=["CTO"],
        campaign_id="mock-account",
        live_people_enabled=False,
        events=events,
        errors=errors,
    )
    joined = account_join_node(
        {
            **state,
            **enriched,
            "account_shards": [shard],
            "events": enriched["events"] + events,
            "errors": errors,
        }
    )
    assert any(e.get("type") == "recovery.explain_retry" for e in joined["events"])
    assert joined["contacts"]
    assert joined["contacts"][0]["email"] == "ada@example.com"
    set_chaos("")
