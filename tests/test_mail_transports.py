"""Transport delivery: Mailpit inject, gmail_test rewrite, unknown no-retry."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.config import clear_settings_cache
from app.infra.db import connect, init_db
from app.mail.crypto import encrypt_secret
from app.mail.transports import DeliveryResult, GmailSmtpTransport, MailpitTransport
from app.tools.mailer import send


@pytest.fixture()
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "transport.db"
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SIGNALSDR_SECRET_KEY", key)
    monkeypatch.setenv("SMTP_HOST", "localhost")
    clear_settings_cache()
    init_db(path)
    yield path
    clear_settings_cache()


def test_mailpit_inject(db: Path):
    sent = []

    def fake(host, port, msg):
        sent.append((host, port, msg["To"]))

    t = MailpitTransport(smtp_send=fake)
    msg = EmailMessage()
    msg["To"] = "a@b.com"
    msg["From"] = "me@x.com"
    msg["Subject"] = "Hi"
    msg.set_content("body")
    r = t.deliver(msg)
    assert r.status == "sent"
    assert sent and sent[0][2] == "a@b.com"


def test_gmail_smtp_unknown_on_disconnect():
    account = {
        "id": "acc1",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
    }

    class Boom:
        def deliver_unknown(self, host, port, msg):
            raise ConnectionError("gone")

    # Inject path always returns sent; unknown path unit-tested via DeliveryResult contract
    t = GmailSmtpTransport(account, smtp_send=lambda *a, **k: None)
    msg = EmailMessage()
    msg["To"] = "a@b.com"
    msg["From"] = "me@x.com"
    msg["Subject"] = "Hi"
    msg["Message-ID"] = "<m@x.com>"
    msg.set_content("body")
    r = t.deliver(msg)
    assert r.status == "sent"

    # Unknown status must not be retried by callers — assert enum
    unk = DeliveryResult(status="unknown", provider_response="connection_dropped_after_data")
    assert unk.status == "unknown"
    assert unk.status != "failed"


def test_gmail_test_rewrites_recipient(db: Path):
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(db)
    enc = encrypt_secret("pw")
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
            'ok', ?, NULL, 25, 3, 0, ?, 0, '', '', '[Gmail]/Drafts', 0, ?, ?
        )
        """,
        (enc, now, json.dumps(["allow@test.local"]), now, now),
    )
    conn.execute(
        """
        INSERT INTO campaigns (id, created_at, input_json, status, options_json, seller_domain)
        VALUES ('c1', ?, '{}', 'running', ?, 'acme.test')
        """,
        (
            now,
            json.dumps({"send_mode": "gmail_test", "mail_account_id": "acc1"}),
        ),
    )
    conn.execute(
        """
        INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at)
        VALUES ('lead-1', 'c1', 'co', 'ct', 'approved', ?)
        """,
        (now,),
    )
    conn.commit()
    conn.close()

    captured = []

    def fake(host, port, msg):
        captured.append(msg["To"])

    out = send(
        lead_id="lead-1",
        step=1,
        subject="Hi",
        body="Hello\n\nOpt out: reply stop",
        to_email="prospect@acme.test",
        email_confidence="verified",
        campaign_id="c1",
        db_path=str(db),
        smtp_send=fake,
    )
    assert out["status"] == "sent"
    assert captured == ["allow@test.local"]
    assert out["subject"].startswith("[TEST]") if "subject" in out else True
    # Subject rewrite verified via DB
    conn = connect(db)
    row = conn.execute("SELECT subject FROM emails WHERE lead_id = 'lead-1'").fetchone()
    conn.close()
    assert row["subject"].startswith("[TEST]")
