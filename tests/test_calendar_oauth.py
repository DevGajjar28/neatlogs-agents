"""Calendar OAuth is separate from Gmail; confirm writes an event when connected."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from app.calendar import oauth as cal_oauth
from app.calendar.events import create_meeting_event, resolve_slot_start
from app.config import clear_settings_cache
from app.infra.db import connect, init_db
from app.mail.crypto import encrypt_secret


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "cal.db"
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("SIGNALSDR_SECRET_KEY", key)
    monkeypatch.setenv("GOOGLE_CALENDAR_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CALENDAR_CLIENT_SECRET", "csecret")
    monkeypatch.setenv(
        "GOOGLE_CALENDAR_REDIRECT_URI",
        "http://127.0.0.1:8000/api/calendar/oauth/callback",
    )
    clear_settings_cache()
    init_db(path)
    yield path
    clear_settings_cache()


def test_status_not_connected(env: Path):
    st = cal_oauth.get_status(db_path=str(env))
    assert st["configured"] is True
    assert st["connected"] is False


def test_start_auth_url_stores_state(env: Path):
    url = cal_oauth.start_auth_url(db_path=str(env))
    assert "accounts.google.com" in url
    assert "calendar.events" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url


def test_create_event_posts_to_google(env: Path, monkeypatch: pytest.MonkeyPatch):
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(env)
    conn.execute(
        """
        INSERT INTO calendar_accounts (
            id, email, refresh_token_enc, access_token_enc, token_expiry,
            status, created_at, updated_at
        ) VALUES (
            'primary', 'testcal@example.com', ?, ?, ?,
            'ok', ?, ?
        )
        """,
        (
            encrypt_secret("refresh-token"),
            encrypt_secret("access-token"),
            (datetime.now(timezone.utc).replace(year=2099)).isoformat(),
            now,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO campaigns (id, created_at, input_json, status)
        VALUES ('c1', ?, '{}', 'running')
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at)
        VALUES ('l1', 'c1', 'co', 'ct', 'replied', ?)
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO meeting_proposals (
            id, lead_id, campaign_id, reply_draft_id, slots_json,
            booking_link, status, notes, created_at, updated_at
        ) VALUES (
            'mp1', 'l1', 'c1', NULL, '[]', NULL, 'confirmed', NULL, ?, ?
        )
        """,
        (now, now),
    )
    conn.commit()
    conn.close()

    mock = MagicMock()
    mock.post.return_value.status_code = 200
    mock.post.return_value.json.return_value = {
        "id": "evt123",
        "htmlLink": "https://calendar.google.com/event?eid=evt123",
    }

    out = create_meeting_event(
        meeting_id="mp1",
        slot_label="Tue 14 Oct 15:00 UTC",
        start_iso="2026-10-14T15:00:00+00:00",
        summary="Intro call",
        db_path=str(env),
        http_client=mock,
    )
    assert out["event_id"] == "evt123"
    assert "htmlLink" in out["html_link"] or "calendar.google.com" in out["html_link"]
    mock.post.assert_called_once()
    args, kwargs = mock.post.call_args
    assert "calendars/primary/events" in args[0]
    assert kwargs["params"].get("conferenceDataVersion") == 1
    assert kwargs["headers"]["Authorization"] == "Bearer access-token"
    assert kwargs["json"]["summary"] == "Intro call"
    assert "conferenceData" in kwargs["json"]

    conn = connect(env)
    row = conn.execute(
        "SELECT calendar_event_id, calendar_html_link FROM meeting_proposals WHERE id='mp1'"
    ).fetchone()
    conn.close()
    assert row["calendar_event_id"] == "evt123"


def test_disconnect_wipes_tokens(env: Path):
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(env)
    conn.execute(
        """
        INSERT INTO calendar_accounts (
            id, email, refresh_token_enc, access_token_enc, token_expiry,
            status, created_at, updated_at
        ) VALUES ('primary', 't@x.com', 'x', 'y', ?, 'ok', ?, ?)
        """,
        (now, now, now),
    )
    conn.commit()
    conn.close()
    cal_oauth.disconnect(db_path=str(env))
    st = cal_oauth.get_status(db_path=str(env))
    assert st["connected"] is False


def test_resolve_slot_start_rolls_past_llm_year():
    now = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)
    start = resolve_slot_start(
        "2025-01-07T14:00:00Z",
        "Tuesday 2:00 PM UTC",
        now=now,
    )
    assert start is not None
    assert start.year == 2026
    assert start.weekday() == 1  # Tuesday
    assert start.hour == 14
    assert start >= now
