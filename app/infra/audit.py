"""Append-only audit log for approve, edit, reject, and send actions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.infra.db import connect, init_db


def write_audit(
    *,
    actor: str,
    action: str,
    target: str,
    details: dict[str, Any] | None = None,
    db_path: str | None = None,
) -> None:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        conn.execute(
            """
            INSERT INTO audit (ts, actor, action, target, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                actor,
                action,
                target,
                json.dumps(details or {}, default=str),
            ),
        )
        conn.commit()
    finally:
        conn.close()
