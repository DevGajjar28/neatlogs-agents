"""Crustdata HTTP client and LangChain @tool wrappers. Follows 08_CRUSTDATA_API.md exactly."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any, Literal

import httpx
from langchain_core.tools import tool

from app.config import clear_settings_cache, get_settings
from app.infra.budget import ACCOUNT_FILE, BudgetExceeded, BudgetLedger, estimate, load_account_prices
from app.infra.cache import ResponseCache, cache_key
from app.infra.chaos import ChaosFault, get_chaos

DEFAULT_TIMEOUT = 60.0
MAX_RETRIES_429 = 3
MAX_RETRIES_5XX = 3


def campaign_data_mode(state: dict[str, Any] | None) -> Literal["replay", "live"]:
    """Campaign UI mode only. Env DATA_MODE is not used for campaign runs."""
    mode = ((state or {}).get("input") or {}).get("mode")
    if mode == "live":
        return "live"
    return "replay"


class CrustdataError(Exception):
    pass


class OutOfCredits(CrustdataError):
    pass


class PermissionDenied(CrustdataError):
    def __init__(self, endpoint: str, message: str = "") -> None:
        self.endpoint = endpoint
        super().__init__(message or f"endpoint denied: {endpoint}")


class FieldsDenied(CrustdataError):
    def __init__(self, denied: list[str]) -> None:
        self.denied = denied
        super().__init__(f"fields denied: {denied}")


class BadRequest(CrustdataError):
    pass


class RateLimited(CrustdataError):
    def __init__(self, reset_seconds: float) -> None:
        self.reset_seconds = reset_seconds
        super().__init__(f"rate limited; reset in {reset_seconds}s")


class ReplayMiss(CrustdataError):
    def __init__(self, endpoint: str, key: str) -> None:
        self.endpoint = endpoint
        self.key = key
        super().__init__(f"DATA_MODE=replay miss for {endpoint} key={key[:12]}")


class EndpointDisabled(CrustdataError):
    pass


class TokenBucket:
    """Simple per-endpoint limiter paced from effective_rate_limit_rpm."""

    def __init__(self, rpm: float = 30.0) -> None:
        self.rpm = max(1.0, float(rpm))
        self._min_interval = 60.0 / self.rpm
        self._next_ok = 0.0

    def acquire(self) -> None:
        now = time.monotonic()
        if now < self._next_ok:
            time.sleep(self._next_ok - now)
        self._next_ok = time.monotonic() + self._min_interval

    def observe(self, headers: httpx.Headers | dict) -> None:
        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")
        if remaining is None or reset is None:
            return
        try:
            if float(remaining) <= 1:
                time.sleep(float(reset) + random.uniform(0.05, 0.25))
        except (TypeError, ValueError):
            return


def _headers(api_key: str, api_version: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
        "x-api-version": api_version,
    }


class CrustdataClient:
    def __init__(
        self,
        *,
        cache: ResponseCache | None = None,
        ledger: BudgetLedger | None = None,
        http_client: httpx.Client | None = None,
        account_file: Path | None = None,
        data_mode: Literal["replay", "live"] | None = None,
    ) -> None:
        clear_settings_cache()
        self.settings = get_settings()
        # Campaign Live/Replay is the source of truth when provided.
        self.data_mode: Literal["replay", "live"] = (
            data_mode if data_mode in {"replay", "live"} else self.settings.data_mode
        )
        self.base = self.settings.crustdata_base_url.rstrip("/")
        self.cache = cache or ResponseCache()
        self.ledger = ledger or BudgetLedger()
        self.account_file = account_file or ACCOUNT_FILE
        self._http = http_client
        self._owns_http = http_client is None
        self._limiters: dict[str, TokenBucket] = {}
        self._disabled: set[str] = set()
        self._prices = load_account_prices(self.account_file)

    def close(self) -> None:
        if self._owns_http and self._http is not None:
            self._http.close()

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=DEFAULT_TIMEOUT)
        return self._http

    def _limiter(self, endpoint: str) -> TokenBucket:
        if endpoint not in self._limiters:
            info = self._prices.get(endpoint) or {}
            rpm = float(info.get("effective_rate_limit_rpm") or 30)
            self._limiters[endpoint] = TokenBucket(rpm)
        return self._limiters[endpoint]

    def reload_prices(self) -> None:
        self._prices = load_account_prices(self.account_file)

    def call(
        self,
        method: str,
        endpoint: str,
        body: dict | None = None,
        *,
        campaign_id: str = "default",
        step: str = "unspecified",
        allow_network_in_replay: bool = False,
        _fields_retry: bool = False,
    ) -> Any:
        if endpoint in self._disabled:
            raise EndpointDisabled(endpoint)

        body = body or {}
        key = cache_key(endpoint, body)
        denial = self.cache.get_denial(key)
        if denial and not _fields_retry:
            raise FieldsDenied(denial)

        hit = self.cache.get(key)
        if hit is not None and not (isinstance(hit, dict) and "__denied_fields__" in hit):
            self.ledger.record(campaign_id, step, endpoint, credits=0.0, cache_hit=True)
            return hit

        if self.data_mode == "replay" and not allow_network_in_replay:
            raise ReplayMiss(endpoint, key)

        if not self.settings.crustdata_api_key.strip():
            raise CrustdataError("CRUSTDATA_API_KEY is missing")

        estimated = estimate(endpoint, body, self._prices)
        self.ledger.check_or_raise(campaign_id, estimated)

        attempts_429 = 0
        attempts_5xx = 0
        while True:
            status_code: int
            headers: dict
            payload: Any
            credits_header: str
            request_id: str | None

            try:
                get_chaos().maybe_fail(endpoint)
            except ChaosFault as fault:
                status_code = fault.status_code
                headers = dict(fault.headers)
                payload = fault.body
                credits_header = "0"
                request_id = None
            else:
                self._limiter(endpoint).acquire()
                client = self._client()
                url = self.base + endpoint
                hdrs = _headers(self.settings.crustdata_api_key, self.settings.crustdata_api_version)
                try:
                    if method.upper() == "GET":
                        response = client.get(url, headers=hdrs, params=body if body else None)
                    else:
                        response = client.post(url, headers=hdrs, json=body)
                except httpx.TimeoutException as exc:
                    attempts_5xx += 1
                    if attempts_5xx > MAX_RETRIES_5XX:
                        raise CrustdataError(f"timeout on {endpoint}") from exc
                    time.sleep(min(2 ** attempts_5xx, 8) + random.uniform(0.05, 0.2))
                    continue

                self._limiter(endpoint).observe(response.headers)
                status_code = response.status_code
                headers = dict(response.headers)
                credits_header = response.headers.get("x-credits-used", "0")
                request_id = response.headers.get("x-request-id")
                try:
                    payload = response.json() if response.content else {}
                except json.JSONDecodeError:
                    payload = {"raw": response.text}

            if status_code == 429:
                attempts_429 += 1
                if attempts_429 > MAX_RETRIES_429:
                    raise RateLimited(float(headers.get("x-ratelimit-reset", 1)))
                reset = headers.get("x-ratelimit-reset") or headers.get("Retry-After") or "1"
                # Side-channel note for reports (agents also see retries via latency/traces).
                print(
                    f"recovery.rate_limit endpoint={endpoint} attempt={attempts_429} "
                    f"sleep={reset}s campaign={campaign_id}",
                    flush=True,
                )
                time.sleep(float(reset) + random.uniform(0.05, 0.35))
                continue

            if status_code >= 500:
                attempts_5xx += 1
                if attempts_5xx > MAX_RETRIES_5XX:
                    raise CrustdataError(f"server error {status_code} on {endpoint}")
                time.sleep(min(2 ** attempts_5xx, 8) + random.uniform(0.05, 0.2))
                continue

            return self._handle_response(
                method,
                endpoint,
                body,
                campaign_id=campaign_id,
                step=step,
                key=key,
                status_code=status_code,
                headers=headers,
                payload=payload,
                credits_header=credits_header,
                request_id=request_id,
                _fields_retry=_fields_retry,
            )

    def _handle_response(
        self,
        method: str,
        endpoint: str,
        body: dict,
        *,
        campaign_id: str,
        step: str,
        key: str,
        status_code: int,
        headers: dict,
        payload: Any,
        credits_header: str,
        request_id: str | None,
        _fields_retry: bool,
    ) -> Any:
        try:
            credits = float(credits_header or 0)
        except ValueError:
            credits = 0.0

        # Record actual HTTP spend once (including error responses that still bill)
        if status_code != 429:
            self.ledger.record(
                campaign_id,
                step,
                endpoint,
                credits=credits,
                cache_hit=False,
                request_id=request_id,
            )

        if status_code == 402:
            raise OutOfCredits((payload.get("error") or {}).get("message", "insufficient credits"))

        if status_code == 403:
            err = payload.get("error") or {}
            meta = err.get("metadata") or []
            if meta and isinstance(meta[0], dict) and "denied_fields" in meta[0]:
                denied = list(meta[0]["denied_fields"])
                self.cache.put_denial(
                    key, endpoint, body, denied, campaign_id=campaign_id
                )
                if not _fields_retry and isinstance(body.get("fields"), list):
                    reduced = [f for f in body["fields"] if f not in denied]
                    retry_body = {**body, "fields": reduced}
                    return self.call(
                        method,
                        endpoint,
                        retry_body,
                        campaign_id=campaign_id,
                        step=step,
                        _fields_retry=True,
                    )
                raise FieldsDenied(denied)
            self._disabled.add(endpoint)
            raise PermissionDenied(endpoint, err.get("message", ""))

        if status_code == 400:
            raise BadRequest(str(payload))

        if status_code == 429:
            raise RateLimited(float(headers.get("x-ratelimit-reset", 1)))

        if status_code >= 400:
            raise CrustdataError(f"HTTP {status_code}: {payload}")

        self.cache.put(key, endpoint, body, payload, credits, campaign_id=campaign_id)
        return payload

    # --- public methods ---

    def account_endpoints(self, path: str | None = None, *, campaign_id: str = "doctor") -> Any:
        params = {"path": path} if path else {}
        return self.call(
            "GET",
            "/account/endpoints",
            params,
            campaign_id=campaign_id,
            step="doctor",
            allow_network_in_replay=True,
        )

    def account_credits(self, *, campaign_id: str = "doctor") -> Any:
        return self.call(
            "GET",
            "/account/credits",
            {},
            campaign_id=campaign_id,
            step="doctor",
            allow_network_in_replay=True,
        )

    def usage_events(self, *, campaign_id: str = "doctor") -> Any:
        return self.call(
            "GET",
            "/account/usage/events",
            {},
            campaign_id=campaign_id,
            step="doctor",
            allow_network_in_replay=True,
        )

    def company_identify(self, body: dict, *, campaign_id: str = "default", step: str = "identify") -> Any:
        return self.call("POST", "/company/identify", body, campaign_id=campaign_id, step=step)

    def company_autocomplete(self, body: dict, *, campaign_id: str = "default", step: str = "autocomplete") -> Any:
        return self.call("POST", "/company/search/autocomplete", body, campaign_id=campaign_id, step=step)

    def company_search(self, body: dict, *, campaign_id: str = "default", step: str = "company_search") -> Any:
        return self.call("POST", "/company/search", body, campaign_id=campaign_id, step=step)

    def company_enrich(self, body: dict, *, campaign_id: str = "default", step: str = "company_enrich") -> Any:
        for key in ("crustdata_company_ids", "domains", "names", "professional_network_profile_urls"):
            if key in body and len(body[key]) > 25:
                raise BadRequest(f"{key} exceeds 25 ids")
        return self.call("POST", "/company/enrich", body, campaign_id=campaign_id, step=step)

    def person_autocomplete(self, body: dict, *, campaign_id: str = "default", step: str = "person_autocomplete") -> Any:
        return self.call("POST", "/person/search/autocomplete", body, campaign_id=campaign_id, step=step)

    def person_search(self, body: dict, *, campaign_id: str = "default", step: str = "person_search") -> Any:
        return self.call("POST", "/person/search", body, campaign_id=campaign_id, step=step)

    def person_search_with_explain_retry(
        self,
        body: dict,
        *,
        campaign_id: str = "default",
        step: str = "person_search",
        semantic_query: str | None = None,
    ) -> Any:
        """Empty result → explain:true (free) → drop culprit → optional semantic retry."""
        result = self.person_search(body, campaign_id=campaign_id, step=step)
        profiles = result.get("profiles") if isinstance(result, dict) else None
        if profiles:
            return result

        explained = self.person_search(
            {**body, "explain": True},
            campaign_id=campaign_id,
            step=f"{step}.explain",
        )
        remarks = (explained.get("remarks") or []) if isinstance(explained, dict) else []
        culprit_paths = {
            item.get("path")
            for item in remarks
            if isinstance(item, dict) and item.get("path")
        }

        retry_body = json.loads(json.dumps(body))  # deep copy via JSON
        # Drop title filter group if explain blamed a title path
        filters = retry_body.get("filters")
        if culprit_paths and filters:
            retry_body["filters"] = _drop_filters_by_paths(filters, culprit_paths)

        if semantic_query:
            retry_body["search"] = {"query": semantic_query, "mode": "hybrid"}

        return self.person_search(retry_body, campaign_id=campaign_id, step=f"{step}.retry")

    def person_enrich(self, body: dict, *, campaign_id: str = "default", step: str = "person_enrich") -> Any:
        urls = body.get("professional_network_profile_urls") or []
        if len(urls) > 25:
            raise BadRequest("professional_network_profile_urls exceeds 25")
        return self.call("POST", "/person/enrich", body, campaign_id=campaign_id, step=step)

    def web_search(self, body: dict, *, campaign_id: str = "default", step: str = "web_search") -> Any:
        return self.call("POST", "/web/search/live", body, campaign_id=campaign_id, step=step)

    def web_fetch(self, body: dict, *, campaign_id: str = "default", step: str = "web_fetch") -> Any:
        urls = body.get("urls") or []
        if not 1 <= len(urls) <= 10:
            raise BadRequest("web_fetch requires 1–10 urls")
        return self.call("POST", "/web/enrich/live", body, campaign_id=campaign_id, step=step)


def _drop_filters_by_paths(node: Any, paths: set[str]) -> Any:
    if isinstance(node, dict):
        if node.get("field") in paths:
            return None
        if "conditions" in node:
            kept = []
            for cond in node["conditions"]:
                dropped = _drop_filters_by_paths(cond, paths)
                if dropped is not None:
                    kept.append(dropped)
            return {**node, "conditions": kept}
        return node
    if isinstance(node, list):
        return [x for x in (_drop_filters_by_paths(i, paths) for i in node) if x is not None]
    return node


def save_account_snapshot(endpoints_payload: Any, credits_payload: Any, path: Path | None = None) -> Path:
    out = path or ACCOUNT_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    endpoints_list = []
    if isinstance(endpoints_payload, dict):
        endpoints_list = endpoints_payload.get("endpoints") or []
    elif isinstance(endpoints_payload, list):
        endpoints_list = endpoints_payload

    by_path = {}
    for item in endpoints_list:
        if not isinstance(item, dict):
            continue
        p = item.get("path")
        if not p:
            continue
        by_path[p] = {
            "path": p,
            "status": item.get("status"),
            "effective_rate_limit_rpm": item.get("effective_rate_limit_rpm"),
            "base_credits": item.get("base_credits"),
            "premium_filters": item.get("premium_filters"),
            "premium_fields": item.get("premium_fields"),
            "enabled_fields": item.get("enabled_fields") or item.get("fields"),
        }

    snapshot = {
        "endpoints": by_path,
        "credits": credits_payload,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return out


# --- LangChain tools (neatlogs traces these as TOOL spans) ---

_default_client: CrustdataClient | None = None


def client_for_campaign(state: dict[str, Any] | None = None, **kwargs: Any) -> CrustdataClient:
    """Build a Crustdata client bound to the campaign's Live/Replay choice."""
    return CrustdataClient(data_mode=campaign_data_mode(state), **kwargs)


def get_client() -> CrustdataClient:
    global _default_client
    if _default_client is None:
        _default_client = CrustdataClient()
    return _default_client


@tool
def crustdata_account_endpoints(path: str = "") -> str:
    """List Crustdata account endpoint access, prices, and rate limits."""
    data = get_client().account_endpoints(path or None)
    return json.dumps(data, default=str)


@tool
def crustdata_account_credits() -> str:
    """Return remaining Crustdata credit balance."""
    return json.dumps(get_client().account_credits(), default=str)


@tool
def crustdata_usage_events() -> str:
    """Return recent Crustdata usage events for ledger reconciliation."""
    return json.dumps(get_client().usage_events(), default=str)


@tool
def crustdata_company_identify(request_json: str) -> str:
    """Resolve company domains or names to crustdata_company_id. Body as JSON string."""
    return json.dumps(get_client().company_identify(json.loads(request_json)), default=str)


@tool
def crustdata_company_autocomplete(request_json: str) -> str:
    """Autocomplete exact company filter values. Body as JSON string."""
    return json.dumps(get_client().company_autocomplete(json.loads(request_json)), default=str)


@tool
def crustdata_company_search(request_json: str) -> str:
    """Search companies with filters and/or ranked query. Body as JSON string."""
    return json.dumps(get_client().company_search(json.loads(request_json)), default=str)


@tool
def crustdata_company_enrich(request_json: str) -> str:
    """Enrich companies (max 25 ids). Body as JSON string."""
    return json.dumps(get_client().company_enrich(json.loads(request_json)), default=str)


@tool
def crustdata_person_autocomplete(request_json: str) -> str:
    """Autocomplete person filter values. Body as JSON string."""
    return json.dumps(get_client().person_autocomplete(json.loads(request_json)), default=str)


@tool
def crustdata_person_search(request_json: str) -> str:
    """Search people. Body as JSON string."""
    return json.dumps(get_client().person_search(json.loads(request_json)), default=str)


@tool
def crustdata_person_enrich(request_json: str) -> str:
    """Enrich people by profile URL (max 25). Body as JSON string."""
    return json.dumps(get_client().person_enrich(json.loads(request_json)), default=str)


@tool
def crustdata_web_search(request_json: str) -> str:
    """Live web/news search. Body as JSON string."""
    return json.dumps(get_client().web_search(json.loads(request_json)), default=str)


@tool
def crustdata_web_fetch(request_json: str) -> str:
    """Live web fetch (1–10 URLs). Body as JSON string."""
    return json.dumps(get_client().web_fetch(json.loads(request_json)), default=str)


CRUSTDATA_TOOLS = [
    crustdata_account_endpoints,
    crustdata_account_credits,
    crustdata_usage_events,
    crustdata_company_identify,
    crustdata_company_autocomplete,
    crustdata_company_search,
    crustdata_company_enrich,
    crustdata_person_autocomplete,
    crustdata_person_search,
    crustdata_person_enrich,
    crustdata_web_search,
    crustdata_web_fetch,
]
