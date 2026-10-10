"""Request-hash cache for Crustdata and web responses."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.infra.db import connect, init_db


def normalize_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def cache_key(endpoint: str, body: Any) -> str:
    raw = endpoint + normalize_json(body if body is not None else {})
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self.db_path = Path(db_path or settings.db_path)
        init_db(self.db_path)

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def get(self, key: str) -> Any | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT response_json FROM cache WHERE key_hash = ?",
                (key,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return json.loads(row["response_json"])

    def put(
        self,
        key: str,
        endpoint: str,
        request: Any,
        response: Any,
        credits: float,
    ) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO cache (key_hash, endpoint, request_json, response_json, credits, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key_hash) DO UPDATE SET
                    response_json = excluded.response_json,
                    credits = excluded.credits,
                    created_at = excluded.created_at
                """,
                (
                    key,
                    endpoint,
                    normalize_json(request if request is not None else {}),
                    json.dumps(response, default=str),
                    float(credits),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def put_denial(self, key: str, endpoint: str, request: Any, denied_fields: list[str]) -> None:
        self.put(
            key,
            endpoint,
            request,
            {"__denied_fields__": denied_fields},
            credits=0.0,
        )

    def get_denial(self, key: str) -> list[str] | None:
        hit = self.get(key)
        if isinstance(hit, dict) and "__denied_fields__" in hit:
            return list(hit["__denied_fields__"])
        return None
