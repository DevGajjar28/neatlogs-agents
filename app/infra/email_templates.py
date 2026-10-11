"""Global email style templates (markdown guides, not mail-merge)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.infra.db import connect, init_db

MAX_TEMPLATES = 20
MAX_CONTENT = 8000
DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "agents" / "email_templates" / "default.md"
)

BANNED_PHRASES = (
    "guaranteed",
    "game-changer",
    "game changer",
    "revolutionary",
    "synergy",
    "circle back",
    "touch base",
)
EM_DASH = "—"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_default_content() -> str:
    if DEFAULT_TEMPLATE_PATH.is_file():
        return DEFAULT_TEMPLATE_PATH.read_text(encoding="utf-8")[:MAX_CONTENT]
    return (
        "# Default outbound style\n\n"
        "Short, direct, evidence-only. Never invent facts.\n"
    )


def seed_default_template(db_path: str | Path | None = None) -> None:
    """Ensure system default template exists (idempotent). Does not call init_db."""
    settings = get_settings()
    path = db_path or settings.db_path
    conn = connect(path)
    try:
        # Table may not exist yet on brand-new files before SCHEMA runs.
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "email_templates" not in tables:
            return
        row = conn.execute(
            "SELECT id FROM email_templates WHERE is_system = 1 LIMIT 1"
        ).fetchone()
        if row:
            return
        content = load_default_content()
        now = _now()
        conn.execute(
            """
            INSERT INTO email_templates (
                id, name, description, content_md, is_default, is_system, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, 1, ?, ?)
            """,
            (
                "tpl-system-default",
                "Default outbound",
                "System default style guide for first-touch and follow-ups.",
                content,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_templates(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        rows = conn.execute(
            """
            SELECT id, name, description, content_md, is_default, is_system, created_at, updated_at
            FROM email_templates
            ORDER BY is_default DESC, updated_at DESC
            """
        ).fetchall()
        return [_row(r) for r in rows]
    finally:
        conn.close()


def get_template(template_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        row = conn.execute(
            """
            SELECT id, name, description, content_md, is_default, is_system, created_at, updated_at
            FROM email_templates WHERE id = ?
            """,
            (template_id,),
        ).fetchone()
        return _row(row) if row else None
    finally:
        conn.close()


def get_default_template(db_path: str | Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        row = conn.execute(
            """
            SELECT id, name, description, content_md, is_default, is_system, created_at, updated_at
            FROM email_templates WHERE is_default = 1
            ORDER BY is_system DESC LIMIT 1
            """
        ).fetchone()
        if row:
            return _row(row)
        row = conn.execute(
            """
            SELECT id, name, description, content_md, is_default, is_system, created_at, updated_at
            FROM email_templates ORDER BY created_at LIMIT 1
            """
        ).fetchone()
        if not row:
            raise RuntimeError("no email templates available")
        return _row(row)
    finally:
        conn.close()


def create_template(
    *,
    name: str,
    description: str = "",
    content_md: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    content = (content_md or "").strip()
    if not content:
        raise ValueError("content_md is required")
    if len(content) > MAX_CONTENT:
        raise ValueError(f"content_md exceeds {MAX_CONTENT} characters")
    conn = connect(path)
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM email_templates").fetchone()["n"]
        if int(count) >= MAX_TEMPLATES:
            raise ValueError(f"max {MAX_TEMPLATES} templates")
        tid = f"tpl-{uuid.uuid4().hex[:12]}"
        now = _now()
        conn.execute(
            """
            INSERT INTO email_templates (
                id, name, description, content_md, is_default, is_system, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (tid, name, (description or "").strip()[:500], content, now, now),
        )
        conn.commit()
        return get_template(tid, path)  # type: ignore[return-value]
    finally:
        conn.close()


def update_template(
    template_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    content_md: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    path = db_path or settings.db_path
    existing = get_template(template_id, path)
    if not existing:
        raise KeyError("template not found")
    if existing["is_system"]:
        raise PermissionError("system template is read-only")
    new_name = existing["name"] if name is None else name.strip()
    new_desc = existing["description"] if description is None else description.strip()[:500]
    new_content = existing["content_md"] if content_md is None else content_md.strip()
    if not new_name:
        raise ValueError("name is required")
    if not new_content:
        raise ValueError("content_md is required")
    if len(new_content) > MAX_CONTENT:
        raise ValueError(f"content_md exceeds {MAX_CONTENT} characters")
    conn = connect(path)
    try:
        conn.execute(
            """
            UPDATE email_templates
            SET name = ?, description = ?, content_md = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_name, new_desc, new_content, _now(), template_id),
        )
        conn.commit()
    finally:
        conn.close()
    return get_template(template_id, path)  # type: ignore[return-value]


def delete_template(template_id: str, db_path: str | Path | None = None) -> None:
    settings = get_settings()
    path = db_path or settings.db_path
    existing = get_template(template_id, path)
    if not existing:
        raise KeyError("template not found")
    if existing["is_system"]:
        raise PermissionError("system template cannot be deleted")
    was_default = bool(existing["is_default"])
    conn = connect(path)
    try:
        conn.execute("DELETE FROM email_templates WHERE id = ?", (template_id,))
        if was_default:
            conn.execute(
                """
                UPDATE email_templates SET is_default = 1, updated_at = ?
                WHERE id = (
                    SELECT id FROM email_templates WHERE is_system = 1 LIMIT 1
                )
                """,
                (_now(),),
            )
        conn.commit()
    finally:
        conn.close()


def duplicate_template(template_id: str, db_path: str | Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    path = db_path or settings.db_path
    existing = get_template(template_id, path)
    if not existing:
        raise KeyError("template not found")
    base_name = f"{existing['name']} (copy)"
    return create_template(
        name=base_name[:120],
        description=existing.get("description") or "",
        content_md=existing["content_md"],
        db_path=path,
    )


def set_default_template(template_id: str, db_path: str | Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    path = db_path or settings.db_path
    existing = get_template(template_id, path)
    if not existing:
        raise KeyError("template not found")
    conn = connect(path)
    try:
        conn.execute("UPDATE email_templates SET is_default = 0")
        conn.execute(
            "UPDATE email_templates SET is_default = 1, updated_at = ? WHERE id = ?",
            (_now(), template_id),
        )
        conn.commit()
    finally:
        conn.close()
    return get_template(template_id, path)  # type: ignore[return-value]


def snapshot_for_campaign(
    template_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, str]:
    """Return {template_id, template_name, template_snapshot} for options_json."""
    tpl = get_template(template_id, db_path) if template_id else None
    if not tpl:
        tpl = get_default_template(db_path)
    return {
        "template_id": str(tpl["id"]),
        "template_name": str(tpl["name"]),
        "template_snapshot": str(tpl["content_md"]),
    }


def style_warnings(subject: str, body: str) -> list[str]:
    """Deterministic style warnings (not blocks) from the default banned list."""
    blob = f"{subject or ''}\n{body or ''}"
    low = blob.lower()
    warnings: list[str] = []
    for phrase in BANNED_PHRASES:
        if phrase in low:
            warnings.append(f"banned phrase: {phrase}")
    if EM_DASH in blob:
        warnings.append("em dash (—) used as stylistic crutch")
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "content_md": row["content_md"] or "",
        "is_default": bool(row["is_default"]),
        "is_system": bool(row["is_system"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
