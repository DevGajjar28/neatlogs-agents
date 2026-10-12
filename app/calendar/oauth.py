"""OAuth2 for Google Calendar — calendar.events only. Never uses Gmail app password."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.infra.db import connect, init_db
from app.mail.crypto import SecretKeyMissing, decrypt_secret, encrypt_secret
from app.mail.policy import get_setting, set_setting

SCOPE = "https://www.googleapis.com/auth/calendar.events"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
ACCOUNT_ID = "primary"
STATE_KEY = "calendar_oauth_state"
STATE_MAX_AGE_SEC = 600


def _state_secret() -> bytes:
    s = get_settings()
    raw = (s.signalsdr_secret_key or s.google_calendar_client_secret or "").strip()
    if not raw:
        raw = "dev-calendar-oauth-state"
    return raw.encode("utf-8")


def mint_oauth_state() -> str:
    """HMAC-signed state (ts.nonce.sig) so callback works even if SQLite state is lost."""
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(16)
    payload = f"{ts}.{nonce}"
    sig = hmac.new(_state_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_oauth_state(state: str) -> bool:
    if not state or state.count(".") != 2:
        return False
    ts_s, nonce, sig = state.split(".", 2)
    if not ts_s.isdigit() or not nonce or not sig:
        return False
    if abs(int(time.time()) - int(ts_s)) > STATE_MAX_AGE_SEC:
        return False
    payload = f"{ts_s}.{nonce}"
    expected = hmac.new(_state_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


class CalendarNotConfigured(RuntimeError):
    pass


class CalendarNotConnected(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def oauth_configured() -> bool:
    s = get_settings()
    return bool(
        (s.google_calendar_client_id or "").strip()
        and (s.google_calendar_client_secret or "").strip()
    )


def redirect_uri() -> str:
    s = get_settings()
    return (s.google_calendar_redirect_uri or "").strip() or (
        "http://127.0.0.1:8000/api/calendar/oauth/callback"
    )


def ui_settings_url() -> str:
    s = get_settings()
    return (s.ui_base_url or "").strip() or "http://localhost:3000"


def get_status(*, db_path: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT id, email, status, updated_at FROM calendar_accounts WHERE id = ?",
            (ACCOUNT_ID,),
        ).fetchone()
    finally:
        conn.close()
    connected = bool(row and row["status"] == "ok" and row["email"])
    return {
        "configured": oauth_configured(),
        "connected": connected,
        "email": (row["email"] if row else None),
        "status": (row["status"] if row else "disconnected"),
        "updated_at": (row["updated_at"] if row else None),
        "scope": SCOPE,
        "redirect_uri": redirect_uri(),
    }


def start_auth_url(*, db_path: str | None = None) -> str:
    if not oauth_configured():
        raise CalendarNotConfigured(
            "Set GOOGLE_CALENDAR_CLIENT_ID and GOOGLE_CALENDAR_CLIENT_SECRET in .env"
        )
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    state = mint_oauth_state()
    conn = connect(path)
    try:
        # Best-effort one-time hint; signed state is the source of truth on callback.
        set_setting(conn, STATE_KEY, {"state": state, "created_at": _now()})
        conn.commit()
    finally:
        conn.close()
    params = {
        "client_id": settings.google_calendar_client_id.strip(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def _exchange_code(code: str) -> dict[str, Any]:
    settings = get_settings()
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_calendar_client_id.strip(),
                "client_secret": settings.google_calendar_client_secret.strip(),
                "redirect_uri": redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"token_exchange_failed:{r.status_code}")
        return r.json()


def _refresh(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_calendar_client_id.strip(),
                "client_secret": settings.google_calendar_client_secret.strip(),
                "grant_type": "refresh_token",
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"token_refresh_failed:{r.status_code}")
        return r.json()


def _fetch_email(access_token: str) -> str:
    with httpx.Client(timeout=20.0) as client:
        r = client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if r.status_code >= 400:
            return ""
        return str(r.json().get("email") or "")


def complete_oauth(
    *,
    code: str,
    state: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        pending = get_setting(conn, STATE_KEY, {}) or {}
        pending_state = pending.get("state") if isinstance(pending, dict) else None
        ok = bool(state) and (
            verify_oauth_state(state) or (pending_state is not None and state == pending_state)
        )
        if not ok:
            raise ValueError("invalid_oauth_state")
        set_setting(conn, STATE_KEY, {})
        conn.commit()
    finally:
        conn.close()

    tokens = _exchange_code(code)
    access = str(tokens.get("access_token") or "")
    refresh = str(tokens.get("refresh_token") or "")
    expires_in = int(tokens.get("expires_in") or 3600)
    if not access:
        raise RuntimeError("no_access_token")
    email = _fetch_email(access)
    expiry = (datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 60))).isoformat()

    try:
        access_enc = encrypt_secret(access)
        refresh_enc = encrypt_secret(refresh) if refresh else None
    except SecretKeyMissing:
        raise

    conn = connect(path)
    try:
        existing = conn.execute(
            "SELECT refresh_token_enc FROM calendar_accounts WHERE id = ?",
            (ACCOUNT_ID,),
        ).fetchone()
        if not refresh_enc and existing and existing["refresh_token_enc"]:
            refresh_enc = existing["refresh_token_enc"]
        if not refresh_enc:
            raise RuntimeError("no_refresh_token — revoke app access and reconnect with consent")
        now = _now()
        conn.execute(
            """
            INSERT INTO calendar_accounts (
                id, email, refresh_token_enc, access_token_enc, token_expiry,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'ok', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email = excluded.email,
                refresh_token_enc = excluded.refresh_token_enc,
                access_token_enc = excluded.access_token_enc,
                token_expiry = excluded.token_expiry,
                status = 'ok',
                updated_at = excluded.updated_at
            """,
            (ACCOUNT_ID, email or "calendar", refresh_enc, access_enc, expiry, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_status(db_path=path)


def disconnect(*, db_path: str | None = None) -> None:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        conn.execute("DELETE FROM calendar_accounts WHERE id = ?", (ACCOUNT_ID,))
        set_setting(conn, STATE_KEY, {})
        conn.commit()
    finally:
        conn.close()


def get_access_token(*, db_path: str | None = None) -> str:
    """Return a valid access token, refreshing if needed. Never logs the token."""
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT * FROM calendar_accounts WHERE id = ? AND status = 'ok'",
            (ACCOUNT_ID,),
        ).fetchone()
        if not row or not row["refresh_token_enc"]:
            raise CalendarNotConnected("Connect Google Calendar in Settings first")
        expiry_s = row["token_expiry"] or ""
        access_enc = row["access_token_enc"]
        refresh_enc = row["refresh_token_enc"]
    finally:
        conn.close()

    try:
        if access_enc and expiry_s:
            exp = datetime.fromisoformat(expiry_s)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > datetime.now(timezone.utc) + timedelta(seconds=30):
                return decrypt_secret(access_enc)
    except Exception:  # noqa: BLE001
        pass

    refresh = decrypt_secret(refresh_enc)
    tokens = _refresh(refresh)
    access = str(tokens.get("access_token") or "")
    if not access:
        raise RuntimeError("refresh_returned_no_access_token")
    expires_in = int(tokens.get("expires_in") or 3600)
    expiry = (datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 60))).isoformat()
    access_enc = encrypt_secret(access)
    conn = connect(path)
    try:
        conn.execute(
            """
            UPDATE calendar_accounts
            SET access_token_enc = ?, token_expiry = ?, updated_at = ?
            WHERE id = ?
            """,
            (access_enc, expiry, _now(), ACCOUNT_ID),
        )
        conn.commit()
    finally:
        conn.close()
    return access
