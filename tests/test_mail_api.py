"""API never returns password / password_enc."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import clear_settings_cache
from app.infra.db import connect, init_db
from app.mail.crypto import encrypt_secret


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "api-mail.db"
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SIGNALSDR_SECRET_KEY", key)
    monkeypatch.setenv("SMTP_HOST", "localhost")
    clear_settings_cache()
    init_db(path)

    # Seed account without going through verify SMTP
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
            'acc1', 'T', 'gmail', 'sender@example.com', 'S', 'sender@example.com', ?,
            'smtp.gmail.com', 587, 'starttls', 'imap.gmail.com', 993,
            'ok', ?, NULL, 25, 3, 90, '[]', 0, '', '', NULL, 0, ?, ?
        )
        """,
        (encrypt_secret("secret-app-password"), now, now, now),
    )
    conn.commit()
    conn.close()

    from app.api.main import app

    with TestClient(app) as c:
        yield c
    clear_settings_cache()


def test_list_accounts_never_returns_password(client: TestClient):
    r = client.get("/api/mail-accounts")
    assert r.status_code == 200
    data = r.json()
    assert data
    blob = json.dumps(data)
    assert "secret-app-password" not in blob
    assert "password_enc" not in blob
    assert data[0]["has_password"] is True
    assert "password" not in data[0]


def test_system_status_mail_fields(client: TestClient):
    r = client.get("/api/system/status")
    assert r.status_code == 200
    body = r.json()
    assert "max_send_mode" in body
    assert "sending_paused" in body
    assert body["mail_account_count"] >= 1


def test_policies_and_sending(client: TestClient):
    r = client.put("/api/settings/sending", json={"sending_paused": True})
    assert r.status_code == 200
    assert r.json()["sending_paused"] is True
    p = client.get("/api/settings/policies")
    assert p.status_code == 200
    assert p.json()["sending_paused"] is True
    client.put("/api/settings/sending", json={"sending_paused": False})
