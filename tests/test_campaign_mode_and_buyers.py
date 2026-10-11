"""Campaign Live/Replay mode, ICP buyer titles, decision-maker filter."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents.account_researcher import is_decision_maker
from app.agents.buyer_finder import _is_buyer_title
from app.config import clear_settings_cache
from app.graph import _count_label
from app.infra.budget import BudgetLedger
from app.infra.cache import ResponseCache
from app.infra.chaos import set_chaos
from app.tools.crustdata import CrustdataClient, ReplayMiss, campaign_data_mode, client_for_campaign


class MockTransport(httpx.BaseTransport):
    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return self.handler(request, len(self.calls))


def test_campaign_data_mode_from_state_only(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "replay")
    clear_settings_cache()
    assert campaign_data_mode({"input": {"mode": "live"}}) == "live"
    assert campaign_data_mode({"input": {"mode": "replay"}}) == "replay"
    assert campaign_data_mode({}) == "replay"
    assert campaign_data_mode(None) == "replay"


def test_live_campaign_calls_network_when_env_is_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_MODE", "replay")
    monkeypatch.setenv("CRUSTDATA_API_KEY", "test-key")
    monkeypatch.setenv("MAX_CREDITS", "100")
    monkeypatch.setenv("CRUSTDATA_BASE_URL", "https://api.crustdata.com")
    clear_settings_cache()
    set_chaos("")

    def handler(request: httpx.Request, n: int) -> httpx.Response:
        return httpx.Response(
            200,
            json={"companies": [{"id": 1}]},
            headers={"x-credits-used": "0.03", "x-request-id": "r1"},
        )

    account = tmp_path / "account.json"
    account.write_text(
        json.dumps(
            {
                "endpoints": {
                    "/company/search": {
                        "path": "/company/search",
                        "base_credits": 0.03,
                        "effective_rate_limit_rpm": 30,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    transport = MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://api.crustdata.com")
    client = client_for_campaign(
        {"input": {"mode": "live"}},
        cache=ResponseCache(tmp_path / "c.db"),
        ledger=BudgetLedger(tmp_path / "c.db"),
        http_client=http,
        account_file=account,
    )
    assert client.data_mode == "live"
    out = client.company_search({"limit": 1}, campaign_id="live1", step="s")
    assert out["companies"]
    assert len(transport.calls) == 1


def test_replay_campaign_misses_even_if_env_live(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_MODE", "live")
    monkeypatch.setenv("CRUSTDATA_API_KEY", "test-key")
    clear_settings_cache()
    set_chaos("")
    account = tmp_path / "account.json"
    account.write_text("{}", encoding="utf-8")
    client = CrustdataClient(
        data_mode="replay",
        cache=ResponseCache(tmp_path / "r.db"),
        ledger=BudgetLedger(tmp_path / "r.db"),
        account_file=account,
    )
    with pytest.raises(ReplayMiss):
        client.company_search({"limit": 1, "fields": ["crustdata_company_id"]}, campaign_id="r1", step="s")


def test_decision_maker_titles():
    assert is_decision_maker("VP of Engineering")
    assert is_decision_maker("CTO")
    assert is_decision_maker("Head of Platform")
    assert is_decision_maker("Founder & CEO")
    assert not is_decision_maker("Staff Engineer")
    assert not is_decision_maker("Software Engineer")
    assert not is_decision_maker("Platform Engineer")
    assert _is_buyer_title("VP Infrastructure")
    assert not _is_buyer_title("Staff Platform Engineer")


def test_sender_stage_label_zero_when_empty():
    label = _count_label("sender", {"drafts": {}, "events": [], "contacts": []}, {})
    assert label == "0 sent"
