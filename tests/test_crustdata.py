"""Unit tests for Crustdata client: cache, retries, budget, replay."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.infra.budget import BudgetExceeded, BudgetLedger
from app.infra.cache import ResponseCache, cache_key
from app.infra.chaos import set_chaos
from app.tools.crustdata import (
    CrustdataClient,
    FieldsDenied,
    OutOfCredits,
    ReplayMiss,
)


class MockTransport(httpx.BaseTransport):
    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return self.handler(request, len(self.calls))


def _client(tmp_path, monkeypatch, handler, data_mode: str = "live") -> CrustdataClient:
    monkeypatch.setenv("DATA_MODE", data_mode)
    monkeypatch.setenv("CRUSTDATA_API_KEY", "test-key")
    monkeypatch.setenv("MAX_CREDITS", "100")
    monkeypatch.setenv("CRUSTDATA_BASE_URL", "https://api.crustdata.com")
    from app.config import clear_settings_cache

    clear_settings_cache()
    set_chaos("")
    db = tmp_path / "t.db"
    account = tmp_path / "account.json"
    account.write_text(
        json.dumps(
            {
                "endpoints": {
                    "/company/search": {
                        "path": "/company/search",
                        "base_credits": 0.03,
                        "effective_rate_limit_rpm": 30,
                    },
                    "/person/enrich": {
                        "path": "/person/enrich",
                        "base_credits": 1.0,
                        "effective_rate_limit_rpm": 15,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    transport = MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://api.crustdata.com")
    client = CrustdataClient(
        cache=ResponseCache(db),
        ledger=BudgetLedger(db),
        http_client=http,
        account_file=account,
    )
    client._transport = transport  # type: ignore[attr-defined]
    return client


def test_cache_hit_second_call_skips_network(tmp_path, monkeypatch):
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        return httpx.Response(
            200,
            json={"companies": [{"id": 1}]},
            headers={"x-credits-used": "0.15", "x-request-id": "r1"},
        )

    client = _client(tmp_path, monkeypatch, handler)
    body = {"limit": 5, "fields": ["crustdata_company_id"]}
    a = client.company_search(body, campaign_id="c1", step="s")
    b = client.company_search(body, campaign_id="c1", step="s")
    assert a == b
    assert len(client._transport.calls) == 1  # type: ignore[attr-defined]
    assert client.ledger.spent("c1") == pytest.approx(0.15)


def test_429_retries_using_reset(tmp_path, monkeypatch):
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        if n == 1:
            return httpx.Response(
                429,
                json={"error": {"type": "rate_limit_error", "message": "slow"}},
                headers={"x-ratelimit-reset": "0"},
            )
        return httpx.Response(
            200,
            json={"companies": []},
            headers={"x-credits-used": "0", "x-request-id": "r2"},
        )

    client = _client(tmp_path, monkeypatch, handler)
    result = client.company_search({"limit": 1}, campaign_id="c2", step="s")
    assert result == {"companies": []}
    assert len(client._transport.calls) == 2  # type: ignore[attr-defined]


def test_402_halts_without_retry(tmp_path, monkeypatch):
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        return httpx.Response(
            402,
            json={"error": {"type": "insufficient_credits", "message": "empty"}},
            headers={"x-credits-used": "0"},
        )

    client = _client(tmp_path, monkeypatch, handler)
    with pytest.raises(OutOfCredits):
        client.company_search({"limit": 1}, campaign_id="c3", step="s")
    assert len(client._transport.calls) == 1  # type: ignore[attr-defined]


def test_403_denied_fields_retries_without_field(tmp_path, monkeypatch):
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else {}
        fields = body.get("fields") or []
        if n == 1:
            assert "contact.business_emails" in fields
            return httpx.Response(
                403,
                json={
                    "error": {
                        "type": "permission_error",
                        "message": "denied",
                        "metadata": [{"denied_fields": ["contact.business_emails"]}],
                    }
                },
                headers={"x-credits-used": "0"},
            )
        assert "contact.business_emails" not in fields
        return httpx.Response(
            200,
            json={"ok": True},
            headers={"x-credits-used": "1", "x-request-id": "r3"},
        )

    client = _client(tmp_path, monkeypatch, handler)
    result = client.person_enrich(
        {
            "professional_network_profile_urls": ["https://www.linkedin.com/in/x"],
            "fields": ["basic_profile", "contact.business_emails"],
        },
        campaign_id="c4",
        step="enrich",
    )
    assert result == {"ok": True}
    assert len(client._transport.calls) == 2  # type: ignore[attr-defined]


def test_budget_refusal(tmp_path, monkeypatch):
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        return httpx.Response(200, json={"companies": []}, headers={"x-credits-used": "0"})

    client = _client(tmp_path, monkeypatch, handler)
    client.ledger.max_credits = 0.01
    with pytest.raises(BudgetExceeded):
        client.company_search({"limit": 100}, campaign_id="c5", step="s")
    assert len(client._transport.calls) == 0  # type: ignore[attr-defined]


def test_replay_never_hits_network(tmp_path, monkeypatch):
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        raise AssertionError("network should not be called in replay")

    client = _client(tmp_path, monkeypatch, handler, data_mode="replay")
    with pytest.raises(ReplayMiss):
        client.company_search({"limit": 1}, campaign_id="c6", step="s")
    assert len(client._transport.calls) == 0  # type: ignore[attr-defined]


def test_cache_key_stable():
    a = cache_key("/company/search", {"limit": 5, "b": 1, "a": 2})
    b = cache_key("/company/search", {"a": 2, "b": 1, "limit": 5})
    assert a == b
