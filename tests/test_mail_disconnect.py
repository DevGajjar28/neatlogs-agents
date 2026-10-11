"""Disconnect agent wipes app password and stops polling."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import clear_settings_cache
from app.infra.db import connect, init_db
from app.mail.accounts import disconnect_agent, get_account
from app.mail.crypto import encrypt_secret
from app.mail.inbox import poll_all_accounts


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "disc.db"
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("SIGNALSDR_SECRET_KEY", key)
    monkeypatch.setenv("DEMO_MODE", "true")
    clear_settings_cache()
    init_db(path)
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(path)
    conn.execute(
        """
        INSERT INTO mail_accounts (
            id, label, provider, email, display_name, username, password_enc,
            smtp_host, smtp_port, smtp_security, imap_host, imap_port,
            status, last_verified_at, last_error, daily_cap, per_domain_daily_cap,
            min_gap_seconds, test_recipients_json, live_enabled, signature,
            postal_address, drafts_folder, is_default, created_at, updated_at
        ) VALUES (
            'acc1', 'T', 'gmail', 'me@example.com', 'M', 'me@example.com', ?,
            'smtp.gmail.com', 587, 'starttls', 'imap.gmail.com', 993,
            'ok', ?, NULL, 25, 3, 90, '[]', 0, '', '', NULL, 0, ?, ?
        )
        """,
        (encrypt_secret("app-pass"), now, now, now),
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
        VALUES ('l1', 'c1', 'co1', 'ct1', 'replied', ?)
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO emails (
            id, lead_id, step, subject, body, status, idempotency_key,
            sent_at, mail_account_id, send_mode, message_id
        ) VALUES (
            'e1', 'l1', 1, 'Hi', 'Body', 'sent', 'l1:1',
            ?, 'acc1', 'gmail_test', '<mid@x.com>'
        )
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO reply_drafts (
            id, lead_id, campaign_id, reply_id, classification,
            subject, body, status, in_reply_to, created_at, updated_at
        ) VALUES (
            'rd1', 'l1', 'c1', NULL, 'interested',
            'Re: Hi', 'Thanks', 'pending', NULL, ?, ?
        )
        """,
        (now, now),
    )
    conn.commit()
    conn.close()
    yield path
    clear_settings_cache()


def test_disconnect_wipes_secret_and_cancels_drafts(env: Path):
    disconnect_agent("acc1", db_path=str(env))
    acc = get_account("acc1", db_path=str(env))
    assert acc is not None
    assert acc["has_password"] is False
    assert int(acc["agent_enabled"]) == 0
    assert acc["status"] == "disabled"
    conn = connect(env)
    draft = conn.execute("SELECT status FROM reply_drafts WHERE id = 'rd1'").fetchone()
    conn.close()
    assert draft["status"] == "cancelled"


def test_poll_skips_disconnected(env: Path):
    disconnect_agent("acc1", db_path=str(env))

    class Boom:
        def __init__(self, *a, **k):
            raise AssertionError("IMAP must not open for disconnected account")

    n = poll_all_accounts(db_path=str(env), imap_factory=Boom)
    assert n == 0


def test_disconnect_api_public_shape(env: Path):
    """Disconnect endpoint fields without importing full app graph stack."""
    from app.api.routes.mail import _public_account
    from app.mail import accounts as mail_accounts

    mail_accounts.disconnect_agent("acc1", db_path=str(env))
    listed = next(a for a in mail_accounts.list_accounts(db_path=str(env)) if a["id"] == "acc1")
    out = _public_account(listed)
    body = out.model_dump()
    assert body["has_password"] is False
    assert body["agent_enabled"] is False
    assert "password" not in body
    assert "password_enc" not in body
    assert "app-pass" not in str(body)
