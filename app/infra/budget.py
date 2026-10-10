"""Credit ledger and plan versus actual spend. Prices come from account file, not constants."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.infra.db import connect, init_db

ACCOUNT_FILE = Path("config/crustdata_account.json")

# Fallback list prices only when doctor has not run yet.
_FALLBACK_BASE = {
    "/company/identify": 0.0,
    "/company/search/autocomplete": 0.0,
    "/person/search/autocomplete": 0.0,
    "/account/endpoints": 0.0,
    "/account/credits": 0.0,
    "/account/usage/events": 0.0,
    "/company/search": 0.03,
    "/company/enrich": 2.0,
    "/person/search": 0.03,
    "/person/enrich": 1.0,
    "/web/search/live": 1.0,
    "/web/enrich/live": 1.0,
}


class BudgetExceeded(Exception):
    def __init__(self, campaign_id: str, spent: float, needed: float, cap: float) -> None:
        self.campaign_id = campaign_id
        self.spent = spent
        self.needed = needed
        self.cap = cap
        super().__init__(
            f"budget refused for {campaign_id}: spent={spent:.4f} need={needed:.4f} cap={cap}"
        )


def load_account_prices(path: Path | None = None) -> dict[str, dict[str, Any]]:
    file_path = path or ACCOUNT_FILE
    if not file_path.exists():
        return {}
    data = json.loads(file_path.read_text(encoding="utf-8"))
    endpoints = data.get("endpoints") or {}
    if isinstance(endpoints, list):
        return {item["path"]: item for item in endpoints if "path" in item}
    return endpoints


def estimate(endpoint: str, body: dict | None = None, prices: dict | None = None) -> float:
    """Conservative credit estimate used before a paid call."""
    body = body or {}
    price_map = prices if prices is not None else load_account_prices()
    info = price_map.get(endpoint) or {}
    base = info.get("base_credits")
    if base is None:
        base = _FALLBACK_BASE.get(endpoint, 1.0)
    base = float(base)

    if endpoint == "/company/enrich":
        ids = (
            body.get("crustdata_company_ids")
            or body.get("domains")
            or body.get("names")
            or []
        )
        return base * max(1, len(ids))

    if endpoint == "/person/enrich":
        urls = body.get("professional_network_profile_urls") or []
        n = max(1, len(urls))
        fields = body.get("fields") or []
        email_premium = 1.0 if "contact.business_emails" in fields else 0.0
        # account file may list field premiums later; keep +1 for business email
        return (base + email_premium) * n

    if endpoint == "/company/search":
        limit = int(body.get("limit") or 20)
        return base * limit + 0.1 * limit  # industry filter cushion

    if endpoint == "/person/search":
        limit = int(body.get("limit") or 20)
        return base * limit + 0.2 * limit

    if endpoint == "/web/enrich/live":
        urls = body.get("urls") or []
        return base * max(1, len(urls))

    if endpoint == "/web/search/live":
        return base

    return base


class BudgetLedger:
    def __init__(self, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self.db_path = Path(db_path or settings.db_path)
        self.max_credits = float(settings.max_credits)
        init_db(self.db_path)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def spent(self, campaign_id: str) -> float:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(credits), 0) AS total FROM budget_ledger WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
        finally:
            conn.close()
        return float(row["total"])

    def check_or_raise(self, campaign_id: str, estimated: float) -> None:
        used = self.spent(campaign_id)
        if used + estimated > self.max_credits:
            raise BudgetExceeded(campaign_id, used, estimated, self.max_credits)

    def near_limit(self, campaign_id: str) -> bool:
        return self.spent(campaign_id) >= 0.9 * self.max_credits

    def record(
        self,
        campaign_id: str,
        step: str,
        endpoint: str,
        credits: float,
        cache_hit: bool,
        request_id: str | None = None,
    ) -> None:
        conn = self._conn()
        try:
            # request_id stored in step suffix when present (schema has no request_id column)
            step_value = f"{step}|rid={request_id}" if request_id else step
            conn.execute(
                """
                INSERT INTO budget_ledger (campaign_id, step, endpoint, credits, cache_hit, ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id,
                    step_value,
                    endpoint,
                    float(credits),
                    1 if cache_hit else 0,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
