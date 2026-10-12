"""Hunter.io fallback after Crustdata — mocked HTTP only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.agents.account_researcher import account_join_node, research_company
from app.config import clear_settings_cache
from app.models import Company
from app.tools.crustdata import OutOfCredits
from app.tools import hunter as hunter_tool
from app.tools.hunter import HunterClient, HunterReplayMiss

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hunter"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class _FakeCrust:
    def __init__(self, *, enrich_exc: Exception | None = None, enrich: Any = None) -> None:
        self.enrich_exc = enrich_exc
        self.enrich = enrich
        self.calls: list[str] = []
        self.data_mode = "live"
        self.ledger = type("L", (), {"spent": lambda self, cid: 0.0})()

    def close(self) -> None:
        return None

    def person_enrich(self, body: dict, *, campaign_id: str = "default", step: str = "") -> Any:
        self.calls.append("person_enrich")
        if self.enrich_exc:
            raise self.enrich_exc
        if self.enrich is not None:
            return self.enrich
        return []

    def person_search(self, body: dict, *, campaign_id: str = "default", step: str = "") -> Any:
        self.calls.append(step or "person_search")
        return {"profiles": []}

    def web_search(self, body: dict, *, campaign_id: str = "default", step: str = "") -> Any:
        self.calls.append("web_search")
        return {"results": []}

    def web_fetch(self, body: dict, *, campaign_id: str = "default", step: str = "") -> Any:
        self.calls.append("web_fetch")
        return {"results": []}


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_email_finder_maps_confidence(tmp_path, monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "test-key")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "h.db"))
    clear_settings_cache()

    payload = _load("email_finder_ada.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-API-KEY") == "test-key"
        assert "/email-finder" in str(request.url)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = HunterClient(data_mode="live", transport=transport)
    hit = client.email_finder(domain="acme.test", first_name="Ada", last_name="Lovelace")
    client.close()
    assert hit is not None
    assert hit["email"] == "ada@acme.test"
    assert hit["confidence"] == "likely"


def test_replay_miss_no_network(tmp_path, monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "test-key")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "h.db"))
    clear_settings_cache()

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("replay must not hit network")

    client = HunterClient(data_mode="replay", transport=httpx.MockTransport(handler))
    with pytest.raises(HunterReplayMiss):
        client.email_finder(domain="acme.test", first_name="Ada", last_name="Lovelace")
    client.close()


def test_join_uses_hunter_when_enrich_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "test-key")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "h.db"))
    clear_settings_cache()

    payload = _load("email_finder_ada.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        "app.tools.hunter.HunterClient",
        lambda **kw: HunterClient(
            data_mode=kw.get("data_mode", "live"),
            transport=httpx.MockTransport(handler),
            api_key="test-key",
        ),
    )

    fake = _FakeCrust(enrich=[])
    monkeypatch.setattr(
        "app.agents.account_researcher.client_for_campaign",
        lambda *a, **k: fake,
    )
    monkeypatch.setattr("app.agents.account_researcher._mx_ok", lambda domain: True)

    state = {
        "campaign_id": "hunter-join",
        "input": {"mode": "live"},
        "companies": [
            {
                "id": "101",
                "name": "Acme",
                "domain": "acme.test",
                "industry": "Software",
                "headcount": None,
                "country": "US",
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
        "account_shards": [
            {
                "company_id": "101",
                "account": {"company_id": "101", "story": "s", "why_now": [], "evidence": []},
                "person": {
                    "name": "Ada Lovelace",
                    "title": "CTO",
                    "profile_url": "https://www.linkedin.com/in/ada",
                },
                "events": [],
                "errors": [],
            }
        ],
    }
    out = account_join_node(state)
    assert out["contacts"]
    contact = out["contacts"][0]
    assert contact["email"] == "ada@acme.test"
    assert contact["email_source"] == "hunter"
    assert contact["email_confidence"] == "likely"
    assert any(e.get("type") == "fallback.hunter_email" for e in out["events"])


def test_join_hunter_after_out_of_credits(tmp_path, monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "test-key")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "h.db"))
    clear_settings_cache()

    payload = _load("email_finder_ada.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        "app.tools.hunter.HunterClient",
        lambda **kw: HunterClient(
            data_mode=kw.get("data_mode", "live"),
            transport=httpx.MockTransport(handler),
            api_key="test-key",
        ),
    )

    fake = _FakeCrust(enrich_exc=OutOfCredits("402"))
    monkeypatch.setattr(
        "app.agents.account_researcher.client_for_campaign",
        lambda *a, **k: fake,
    )

    state = {
        "campaign_id": "hunter-ooc",
        "input": {"mode": "live"},
        "companies": [
            {
                "id": "101",
                "name": "Acme",
                "domain": "acme.test",
                "industry": "Software",
                "headcount": None,
                "country": "US",
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
        "account_shards": [
            {
                "company_id": "101",
                "account": {"company_id": "101", "story": "s", "why_now": [], "evidence": []},
                "person": {
                    "name": "Ada Lovelace",
                    "title": "CTO",
                    "profile_url": "https://www.linkedin.com/in/ada",
                },
                "events": [],
                "errors": [],
            }
        ],
    }
    out = account_join_node(state)
    assert out["contacts"][0]["email_source"] == "hunter"
    assert any(e.get("type") == "fallback.hunter_eligible" for e in out["events"])
    assert any(e.get("type") == "fallback.hunter_email" for e in out["events"])


def test_no_hunter_key_falls_to_pattern_guess(tmp_path, monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "h.db"))
    clear_settings_cache()

    fake = _FakeCrust(enrich=[])
    monkeypatch.setattr(
        "app.agents.account_researcher.client_for_campaign",
        lambda *a, **k: fake,
    )
    monkeypatch.setattr("app.agents.account_researcher._mx_ok", lambda domain: True)

    state = {
        "campaign_id": "hunter-skip",
        "input": {"mode": "live"},
        "companies": [
            {
                "id": "101",
                "name": "Acme",
                "domain": "acme.test",
                "industry": "Software",
                "headcount": None,
                "country": "US",
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
        "account_shards": [
            {
                "company_id": "101",
                "account": {"company_id": "101", "story": "s", "why_now": [], "evidence": []},
                "person": {
                    "name": "Ada Lovelace",
                    "title": "CTO",
                    "profile_url": "https://www.linkedin.com/in/ada",
                },
                "events": [],
                "errors": [],
            }
        ],
    }
    out = account_join_node(state)
    assert out["contacts"][0]["email"] == "ada.lovelace@acme.test"
    assert out["contacts"][0]["email_source"] == "pattern_guess"
    assert any(e.get("type") == "fallback.hunter_skipped" for e in out["events"])


def test_find_person_domain_search_when_crust_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "test-key")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "h.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATA_MODE", "replay")
    clear_settings_cache()
    monkeypatch.setattr(
        "app.agents.account_researcher.web.fetch_prospect_pages",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "app.agents.account_researcher.get_llm",
        lambda kind="fast": type(
            "L",
            (),
            {"invoke": lambda self, p: type("R", (), {"content": "Story (ev_x)"})()},
        )(),
    )

    payload = _load("domain_search_acme.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        "app.tools.hunter.HunterClient",
        lambda **kw: HunterClient(
            data_mode=kw.get("data_mode", "live"),
            transport=httpx.MockTransport(handler),
            api_key="test-key",
        ),
    )

    fake = _FakeCrust()
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
    shard = research_company(
        fake,  # type: ignore[arg-type]
        company=company,
        data={"people": {}},
        titles=["CTO", "VP Engineering"],
        campaign_id="hunter-domain",
        live_people_enabled=False,
        events=events,
        errors=errors,
    )
    assert shard["person"] is not None
    assert shard["person"]["name"] == "Ada Lovelace"
    assert shard["person"]["email"] == "cto@acme.test"
    assert shard["person"]["email_source"] == "hunter"
    assert any(e.get("type") == "fallback.hunter_domain" for e in events)


def test_find_email_helper_unconfigured(monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "")
    clear_settings_cache()
    assert hunter_tool.find_email_for_person(domain="acme.test", name="Ada Lovelace") is None
