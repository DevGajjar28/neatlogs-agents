"""Mail account CRUD. Passwords encrypted; never returned by public helpers."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.infra.db import connect, init_db
from app.mail.crypto import SecretKeyMissing, decrypt_secret, encrypt_secret

PRESETS: dict[str, dict[str, Any]] = {
    "gmail": {
        "provider": "gmail",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
    },
    "workspace": {
        "provider": "workspace",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
    },
    "custom": {
        "provider": "custom",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "imap_host": "",
        "imap_port": 993,
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_account_id() -> str:
    return f"acc_{uuid.uuid4().hex[:10]}"


def list_accounts(db_path: str | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        rows = conn.execute(
            "SELECT * FROM mail_accounts ORDER BY is_default DESC, created_at DESC"
        ).fetchall()
        out = []
        from datetime import timedelta

        since_s = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        for r in rows:
            d = dict(r)
            d.pop("password_enc", None)
            d["has_password"] = bool(r["password_enc"])
            d["agent_enabled"] = int(
                r["agent_enabled"] if "agent_enabled" in r.keys() and r["agent_enabled"] is not None else 1
            )
            sent = conn.execute(
                "SELECT COUNT(*) AS n FROM mail_send_log WHERE account_id = ? AND ts >= ?",
                (r["id"], since_s),
            ).fetchone()["n"]
            d["sent_24h"] = int(sent)
            d["cap"] = int(r["daily_cap"] or 25)
            try:
                d["test_recipients"] = json.loads(r["test_recipients_json"] or "[]")
            except Exception:  # noqa: BLE001
                d["test_recipients"] = []
            out.append(d)
        return out
    finally:
        conn.close()


def get_account(account_id: str, db_path: str | None = None) -> dict[str, Any] | None:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT * FROM mail_accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d.pop("password_enc", None)
        d["has_password"] = bool(row["password_enc"])
        d["agent_enabled"] = int(
            row["agent_enabled"]
            if "agent_enabled" in row.keys() and row["agent_enabled"] is not None
            else 1
        )
        try:
            d["test_recipients"] = json.loads(row["test_recipients_json"] or "[]")
        except Exception:  # noqa: BLE001
            d["test_recipients"] = []
        return d
    finally:
        conn.close()


def get_credentials(account_id: str, db_path: str | None = None) -> tuple[str, str]:
    """Return (username, password). Internal only — never log or return via API."""
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT username, password_enc FROM mail_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        if not row or not row["password_enc"]:
            raise KeyError("account_or_password_missing")
        return str(row["username"]), decrypt_secret(str(row["password_enc"]))
    finally:
        conn.close()


def create_account(data: dict[str, Any], *, password: str, db_path: str | None = None) -> str:
    if not password.strip():
        raise ValueError("password_required")
    try:
        enc = encrypt_secret(password.strip())
    except SecretKeyMissing:
        raise
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    aid = new_account_id()
    now = _now()
    email = str(data["email"]).strip()
    preset = PRESETS.get(str(data.get("provider") or "gmail"), PRESETS["gmail"])
    conn = connect(path)
    try:
        conn.execute(
            """
            INSERT INTO mail_accounts (
                id, label, provider, email, display_name, username, password_enc,
                smtp_host, smtp_port, smtp_security, imap_host, imap_port,
                status, last_verified_at, last_error, daily_cap, per_domain_daily_cap,
                min_gap_seconds, test_recipients_json, live_enabled, signature,
                postal_address, drafts_folder, is_default, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unverified', NULL, NULL,
                      ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                aid,
                data.get("label") or email,
                data.get("provider") or preset["provider"],
                email,
                data.get("display_name") or email.split("@")[0],
                data.get("username") or email,
                enc,
                data.get("smtp_host") or preset["smtp_host"],
                int(data.get("smtp_port") or preset["smtp_port"]),
                data.get("smtp_security") or preset["smtp_security"],
                data.get("imap_host") or preset["imap_host"],
                int(data.get("imap_port") or preset["imap_port"]),
                min(100, max(1, int(data.get("daily_cap") or 25))),
                min(10, max(1, int(data.get("per_domain_daily_cap") or 3))),
                max(30, int(data.get("min_gap_seconds") or 90)),
                json.dumps(data.get("test_recipients") or [email]),
                1 if data.get("live_enabled") else 0,
                data.get("signature") or "",
                data.get("postal_address") or "",
                1 if data.get("is_default") else 0,
                now,
                now,
            ),
        )
        conn.commit()
        return aid
    finally:
        conn.close()


def update_account(
    account_id: str,
    data: dict[str, Any],
    *,
    password: str | None = None,
    db_path: str | None = None,
) -> None:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT id FROM mail_accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not row:
            raise KeyError("not_found")
        fields = {
            "label": data.get("label"),
            "provider": data.get("provider"),
            "email": data.get("email"),
            "display_name": data.get("display_name"),
            "username": data.get("username"),
            "smtp_host": data.get("smtp_host"),
            "smtp_port": data.get("smtp_port"),
            "smtp_security": data.get("smtp_security"),
            "imap_host": data.get("imap_host"),
            "imap_port": data.get("imap_port"),
            "daily_cap": data.get("daily_cap"),
            "per_domain_daily_cap": data.get("per_domain_daily_cap"),
            "min_gap_seconds": data.get("min_gap_seconds"),
            "signature": data.get("signature"),
            "postal_address": data.get("postal_address"),
            "live_enabled": 1 if data.get("live_enabled") else 0 if "live_enabled" in data else None,
            "is_default": 1 if data.get("is_default") else 0 if "is_default" in data else None,
        }
        if "test_recipients" in data:
            fields["test_recipients_json"] = json.dumps(data["test_recipients"])
        sets = []
        args: list[Any] = []
        for k, v in fields.items():
            if v is None:
                continue
            sets.append(f"{k} = ?")
            args.append(v)
        if password and password.strip():
            sets.append("password_enc = ?")
            args.append(encrypt_secret(password.strip()))
            # Reconnect: new app password restores inbox agent
            sets.append("agent_enabled = 1")
            sets.append("last_error = NULL")
        sets.append("updated_at = ?")
        args.append(_now())
        args.append(account_id)
        conn.execute(f"UPDATE mail_accounts SET {', '.join(sets)} WHERE id = ?", args)
        conn.commit()
    finally:
        conn.close()


def set_account_status(
    account_id: str,
    status: str,
    *,
    last_error: str | None = None,
    drafts_folder: str | None = None,
    db_path: str | None = None,
) -> None:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        conn.execute(
            """
            UPDATE mail_accounts
            SET status = ?, last_error = ?, last_verified_at = ?,
                drafts_folder = COALESCE(?, drafts_folder), updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                last_error,
                _now() if status == "ok" else None,
                drafts_folder,
                _now(),
                account_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def disconnect_agent(account_id: str, db_path: str | None = None) -> None:
    """Disable inbox agent, wipe app password, cancel pending reply drafts for account."""
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT id FROM mail_accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not row:
            raise KeyError("not_found")
        conn.execute(
            """
            UPDATE mail_accounts
            SET agent_enabled = 0, status = 'disabled', password_enc = NULL,
                last_error = 'Disconnected by user — re-enter app password to reconnect.',
                updated_at = ?
            WHERE id = ?
            """,
            (_now(), account_id),
        )
        # Cancel pending reply drafts for leads that used this account
        conn.execute(
            """
            UPDATE reply_drafts SET status = 'cancelled', updated_at = ?
            WHERE status = 'pending'
              AND lead_id IN (
                SELECT DISTINCT e.lead_id FROM emails e
                WHERE e.mail_account_id = ?
              )
            """,
            (_now(), account_id),
        )
        conn.execute(
            """
            UPDATE meeting_proposals SET status = 'cancelled', updated_at = ?
            WHERE status = 'proposed'
              AND lead_id IN (
                SELECT DISTINCT e.lead_id FROM emails e
                WHERE e.mail_account_id = ?
              )
            """,
            (_now(), account_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_account(account_id: str, db_path: str | None = None) -> None:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        active = conn.execute(
            """
            SELECT id FROM campaigns
            WHERE options_json LIKE ?
              AND status NOT IN ('completed', 'halted', 'failed')
            LIMIT 1
            """,
            (f"%{account_id}%",),
        ).fetchone()
        if active:
            raise RuntimeError("account_in_use")
        conn.execute("DELETE FROM mail_accounts WHERE id = ?", (account_id,))
        conn.commit()
    finally:
        conn.close()
