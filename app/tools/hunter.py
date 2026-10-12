"""Hunter.io client — Email Finder + Domain Search fallback after Crustdata."""

from __future__ import annotations

from typing import Any, Literal

import httpx

from app.config import get_settings
from app.infra.cache import ResponseCache, cache_key

DEFAULT_TIMEOUT = 30.0
ENDPOINT_EMAIL_FINDER = "hunter:/v2/email-finder"
ENDPOINT_DOMAIN_SEARCH = "hunter:/v2/domain-search"


class HunterError(Exception):
    pass


class HunterReplayMiss(HunterError):
    def __init__(self, endpoint: str, key: str) -> None:
        self.endpoint = endpoint
        self.key = key
        super().__init__(f"DATA_MODE=replay miss for {endpoint} key={key[:12]}")


class HunterSkipped(HunterError):
    """Soft skip — missing key, auth, quota, or rate limit."""


def hunter_configured() -> bool:
    return bool(get_settings().hunter_api_key.strip())


def _confidence_from_hunter(*, score: int | None, verification_status: str | None) -> str:
    if (verification_status or "").lower() == "valid" or (score is not None and score >= 90):
        return "likely"
    return "guessed"


def _split_name(name: str) -> tuple[str | None, str | None]:
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[-1]


class HunterClient:
    """Cache → replay guard → HTTP. Does not use Crustdata MAX_CREDITS ledger."""

    def __init__(
        self,
        *,
        data_mode: Literal["replay", "live"] = "live",
        api_key: str | None = None,
        base_url: str | None = None,
        cache: ResponseCache | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.data_mode = data_mode
        self.api_key = (api_key if api_key is not None else settings.hunter_api_key).strip()
        self.base_url = (base_url or settings.hunter_base_url).rstrip("/")
        self.cache = cache or ResponseCache()
        self._client = httpx.Client(timeout=DEFAULT_TIMEOUT, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HunterClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _get(self, endpoint: str, path: str, params: dict[str, Any]) -> Any:
        if not self.api_key:
            raise HunterSkipped("hunter_api_key_missing")

        key = cache_key(endpoint, params)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        if self.data_mode == "replay":
            raise HunterReplayMiss(endpoint, key)

        headers = {"X-API-KEY": self.api_key, "Accept": "application/json"}
        url = f"{self.base_url}{path}"
        try:
            resp = self._client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise HunterError(f"network:{type(exc).__name__}") from exc

        if resp.status_code in {401, 403}:
            raise HunterSkipped(f"auth:{resp.status_code}")
        if resp.status_code == 429:
            raise HunterSkipped("rate_limited")
        if resp.status_code in {402, 451}:
            raise HunterSkipped(f"quota:{resp.status_code}")
        if resp.status_code >= 400:
            raise HunterError(f"http:{resp.status_code}")

        try:
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise HunterError("invalid_json") from exc

        self.cache.put(key, endpoint, params, payload, credits=0.0)
        return payload

    def email_finder(
        self,
        *,
        domain: str,
        first_name: str,
        last_name: str | None = None,
        full_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Return {email, score, verification_status} or None if not found."""
        params: dict[str, Any] = {"domain": domain.strip().lower()}
        if full_name:
            params["full_name"] = full_name.strip()
        else:
            params["first_name"] = first_name.strip()
            if last_name:
                params["last_name"] = last_name.strip()

        payload = self._get(ENDPOINT_EMAIL_FINDER, "/email-finder", params)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None
        email = str(data.get("email") or "").strip()
        if not email or "@" not in email:
            return None
        score_raw = data.get("score")
        try:
            score = int(score_raw) if score_raw is not None else None
        except (TypeError, ValueError):
            score = None
        verification = data.get("verification") if isinstance(data.get("verification"), dict) else {}
        status = str(verification.get("status") or "") or None
        return {
            "email": email,
            "score": score,
            "verification_status": status,
            "confidence": _confidence_from_hunter(score=score, verification_status=status),
        }

    def domain_search(
        self,
        *,
        domain: str,
        limit: int = 10,
        seniority: str | None = None,
        department: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return list of email rows from Domain Search."""
        params: dict[str, Any] = {
            "domain": domain.strip().lower(),
            "limit": max(1, min(int(limit), 20)),
        }
        if seniority:
            params["seniority"] = seniority
        if department:
            params["department"] = department

        payload = self._get(ENDPOINT_DOMAIN_SEARCH, "/domain-search", params)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return []
        emails = data.get("emails") or []
        if not isinstance(emails, list):
            return []
        out: list[dict[str, Any]] = []
        for row in emails:
            if not isinstance(row, dict):
                continue
            value = str(row.get("value") or row.get("email") or "").strip()
            if not value or "@" not in value:
                continue
            out.append(row)
        return out


def find_email_for_person(
    *,
    domain: str,
    name: str,
    data_mode: Literal["replay", "live"] = "live",
) -> tuple[str, str, str] | None:
    """
    Hunter Email Finder helper.
    Returns (email, email_source, email_confidence) or None.
    """
    if not hunter_configured() or not domain or "." not in domain:
        return None
    first, last = _split_name(name)
    if not first:
        return None
    with HunterClient(data_mode=data_mode) as client:
        try:
            hit = client.email_finder(
                domain=domain,
                first_name=first,
                last_name=last,
                full_name=name if " " in name.strip() else None,
            )
        except (HunterSkipped, HunterReplayMiss, HunterError):
            return None
    if not hit:
        return None
    return hit["email"], "hunter", str(hit["confidence"])


def find_person_from_domain(
    *,
    domain: str,
    titles: list[str],
    data_mode: Literal["replay", "live"] = "live",
    is_decision_maker: Any = None,
) -> dict[str, Any] | None:
    """
    Hunter Domain Search → best decision-maker person dict
    {name, title, profile_url, email?, email_source?, email_confidence?}.
    """
    if not hunter_configured() or not domain or "." not in domain:
        return None

    def _dm(title: str) -> bool:
        if callable(is_decision_maker):
            return bool(is_decision_maker(title))
        return True

    rows: list[dict[str, Any]] = []
    with HunterClient(data_mode=data_mode) as client:
        for kwargs in (
            {"seniority": "executive,senior"},
            {},
        ):
            try:
                rows = client.domain_search(domain=domain, limit=10, **kwargs)
            except (HunterSkipped, HunterReplayMiss, HunterError):
                rows = []
            if rows:
                break

    if not rows:
        return None

    title_needles = [t.lower() for t in titles if t]

    def score(row: dict) -> int:
        position = str(row.get("position") or row.get("title") or "").lower()
        if not _dm(position):
            return -100
        s = 0
        for t in title_needles:
            if t and t in position:
                s += 2
        # Prefer personal emails over generic
        if str(row.get("type") or "") == "personal":
            s += 1
        try:
            s += min(3, int(row.get("confidence") or 0) // 30)
        except (TypeError, ValueError):
            pass
        return s

    ranked = sorted(rows, key=score, reverse=True)
    best = ranked[0]
    if score(best) < 0:
        return None

    first = str(best.get("first_name") or "").strip()
    last = str(best.get("last_name") or "").strip()
    name = f"{first} {last}".strip() or str(best.get("value") or "").split("@")[0]
    title = str(best.get("position") or best.get("title") or "Leader")
    email = str(best.get("value") or "").strip()
    conf_raw = best.get("confidence")
    try:
        conf_score = int(conf_raw) if conf_raw is not None else None
    except (TypeError, ValueError):
        conf_score = None
    confidence = _confidence_from_hunter(score=conf_score, verification_status=None)

    person: dict[str, Any] = {
        "name": name,
        "title": title,
        "profile_url": best.get("linkedin") or best.get("linkedin_url"),
        "match_status": None,
    }
    if email and "@" in email:
        person["email"] = email
        person["email_source"] = "hunter"
        person["email_confidence"] = confidence
    return person
