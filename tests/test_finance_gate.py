"""Finance/OTP header gate: never open bodies for denylisted mail."""

from __future__ import annotations

from app.mail.finance_gate import finance_blocked, headers_look_safe


def test_otp_and_bank_subjects_blocked():
    assert finance_blocked(subject="Your OTP code is ready") == "subject_finance_or_otp"
    assert finance_blocked(subject="Monthly bank statement") == "subject_finance_or_otp"
    assert finance_blocked(subject="Invoice #4421 attached") == "subject_finance_or_otp"
    assert finance_blocked(subject="Do not share this code") == "subject_finance_or_otp"
    assert finance_blocked(subject="Wire transfer confirmation") == "subject_finance_or_otp"
    assert finance_blocked(subject="Payroll deposit notice") == "subject_finance_or_otp"


def test_finance_from_domains_blocked():
    assert finance_blocked(from_addr="alerts@chase.com", subject="Hello") == "from_finance_domain"
    assert finance_blocked(from_addr="noreply@paypal.com", subject="Hi") == "from_finance_domain"
    assert finance_blocked(from_addr="tax@irs.gov", subject="Notice") == "from_finance_domain"


def test_normal_reply_not_blocked():
    assert finance_blocked(subject="Re: quick intro", from_addr="alex@acme.io") is None
    assert headers_look_safe({"Subject": "Thanks for reaching out", "From": "p@corp.com"})


def test_inbox_skips_body_fetch_for_finance(monkeypatch, tmp_path):
    """Poller fetches HEADER only when finance denylist hits; never BODY for that UID."""
    from datetime import datetime, timezone
    from pathlib import Path

    from cryptography.fernet import Fernet

    from app.config import clear_settings_cache
    from app.infra.db import connect, init_db
    from app.mail.crypto import encrypt_secret
    from app.mail.inbox import poll_account

    db = tmp_path / "fin.db"
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("DB_PATH", str(db))
    monkeypatch.setenv("SIGNALSDR_SECRET_KEY", key)
    clear_settings_cache()
    init_db(db)
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(db)
    conn.execute(
        """
        INSERT INTO campaigns (id, created_at, input_json, status, seller_name, seller_domain)
        VALUES ('c1', ?, '{}', 'running', 'S', 's.com')
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at)
        VALUES ('l1', 'c1', 'co1', 'ct1', 'sent', ?)
        """,
        (now,),
    )
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
        INSERT INTO emails (
            id, lead_id, step, subject, body, status, idempotency_key,
            sent_at, mail_account_id, send_mode, message_id
        ) VALUES (
            'e1', 'l1', 1, 'Hello', 'Hi', 'sent', 'l1:1',
            ?, 'acc1', 'gmail_test', '<our-mid@example.com>'
        )
        """,
        (now,),
    )
    conn.commit()
    conn.close()

    header_bytes = (
        b"From: alerts@chase.com\r\n"
        b"Subject: Your OTP code\r\n"
        b"Message-ID: <otp1@chase.com>\r\n"
        b"\r\n"
    )
    fetches: list[str] = []

    class FakeIMAP:
        def login(self, *a):
            return "OK", [b"ok"]

        def select(self, mailbox, readonly=False):
            return "OK", [b"1"]

        def search(self, charset, *criteria):
            crit = " ".join(str(c) for c in criteria)
            if "In-Reply-To" in crit or "References" in crit:
                return "OK", [b"1"]
            return "OK", [b""]

        def fetch(self, message_set, message_parts):
            parts = str(message_parts)
            fetches.append(parts)
            if "HEADER" in parts.upper():
                return "OK", [(b"1 (BODY[HEADER] {n})", header_bytes)]
            raise AssertionError("BODY fetch must not run for finance mail")

        def logout(self):
            return "OK", [b"bye"]

    applied = poll_account("acc1", db_path=str(db), imap_factory=FakeIMAP)
    assert applied == 0
    assert any("HEADER" in f.upper() for f in fetches)
    assert not any(
        "BODY.PEEK[]" in f.upper() or "BODY.PEEK[TEXT" in f.upper() for f in fetches
    )

    conn = connect(db)
    ev = conn.execute(
        "SELECT type FROM events WHERE type = 'policy.finance_skipped'"
    ).fetchone()
    conn.close()
    assert ev is not None
    clear_settings_cache()
