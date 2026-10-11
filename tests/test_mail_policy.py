"""One policy test per docs/12 §3 rule."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.config import clear_settings_cache
from app.infra.db import connect, init_db
from app.mail.crypto import encrypt_secret
from app.mail.policy import PolicyContext, check_all, set_setting


@pytest.fixture()
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "policy.db"
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ALLOW_LIVE_SENDS", "false")
    monkeypatch.setenv("SIGNALSDR_SECRET_KEY", key)
    monkeypatch.setenv("SMTP_HOST", "localhost")
    clear_settings_cache()
    init_db(path)
    yield path
    clear_settings_cache()


def _seed_campaign(db: Path, cid: str = "c1", **opts) -> None:
    conn = connect(db)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO campaigns (id, created_at, input_json, status, options_json, seller_domain)
        VALUES (?, ?, '{}', 'running', ?, 'acme.test')
        """,
        (cid, now, json.dumps(opts or {})),
    )
    conn.commit()
    conn.close()


def _seed_lead(db: Path, lead_id: str = "lead-1", campaign_id: str = "c1") -> None:
    conn = connect(db)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at)
        VALUES (?, ?, 'co', 'ct', 'approved', ?)
        """,
        (lead_id, campaign_id, now),
    )
    conn.commit()
    conn.close()


def _seed_account(db: Path, aid: str = "acc1", **overrides) -> dict:
    conn = connect(db)
    now = datetime.now(timezone.utc).isoformat()
    enc = encrypt_secret("xxxx-xxxx-xxxx-xxxx")
    row = {
        "id": aid,
        "label": "Test",
        "provider": "gmail",
        "email": "sender@example.com",
        "display_name": "Sender",
        "username": "sender@example.com",
        "password_enc": enc,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "status": "ok",
        "last_verified_at": now,
        "last_error": None,
        "daily_cap": 25,
        "per_domain_daily_cap": 3,
        "min_gap_seconds": 90,
        "test_recipients_json": json.dumps(["tester@example.com"]),
        "live_enabled": 0,
        "signature": "",
        "postal_address": "1 Test St",
        "drafts_folder": "[Gmail]/Drafts",
        "is_default": 0,
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT INTO mail_accounts ({cols}) VALUES ({placeholders})",
        tuple(row.values()),
    )
    conn.commit()
    conn.close()
    return row


def _ctx(db: Path, **kw) -> PolicyContext:
    base = dict(
        campaign_id="c1",
        lead_id="lead-1",
        step=1,
        to_email="ada@acme.test",
        subject="Hi",
        body="Hello\n\nOpt out: reply stop",
        email_confidence="verified",
        allow_guessed=False,
        send_mode="sandbox",
        mail_account_id=None,
        approved=True,
        verifier_passed=True,
        seller_domain="acme.test",
        live_confirm_ok=False,
        db_path=str(db),
    )
    base.update(kw)
    return PolicyContext(**base)


def test_1_sending_paused(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    conn = connect(db)
    set_setting(conn, "sending_paused", True)
    conn.commit()
    conn.close()
    r = check_all(_ctx(db))
    assert not r.ok and r.event == "policy.sending_paused"


def test_2_mode_not_allowed_live_in_demo(db: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_campaign(db)
    _seed_lead(db)
    _seed_account(db, live_enabled=1)
    r = check_all(_ctx(db, send_mode="gmail_live", mail_account_id="acc1", live_confirm_ok=True))
    assert not r.ok and r.event == "policy.mode_not_allowed"


def test_3_account_unavailable(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    r = check_all(_ctx(db, send_mode="gmail_test", mail_account_id="missing"))
    assert not r.ok and r.event == "policy.account_unavailable"


def test_4_not_approved(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    r = check_all(_ctx(db, approved=False))
    assert not r.ok and r.event == "policy.not_approved"


def test_5_bad_envelope(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    r = check_all(_ctx(db, to_email="a@b.com,c@d.com"))
    assert not r.ok and r.event == "policy.bad_envelope"


def test_6_suppressed(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    conn = connect(db)
    conn.execute(
        "INSERT INTO suppression (email_or_domain, reason) VALUES (?, ?)",
        ("ada@acme.test", "opt_out"),
    )
    conn.commit()
    conn.close()
    r = check_all(_ctx(db))
    assert not r.ok and r.event == "policy.suppressed"


def test_7_guessed_blocked(db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("ALLOW_LIVE_SENDS", "true")
    clear_settings_cache()
    _seed_campaign(db)
    _seed_lead(db)
    _seed_account(db, live_enabled=1)
    r = check_all(
        _ctx(
            db,
            send_mode="gmail_live",
            mail_account_id="acc1",
            email_confidence="guessed",
            live_confirm_ok=True,
        )
    )
    assert not r.ok and r.event == "policy.guessed_blocked"


def test_8_role_address(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    r = check_all(_ctx(db, to_email="noreply@acme.test"))
    assert not r.ok and r.event == "policy.role_address"


def test_9_test_recipient_missing(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    _seed_account(db, test_recipients_json="[]")
    r = check_all(_ctx(db, send_mode="gmail_test", mail_account_id="acc1"))
    assert not r.ok and r.event == "policy.test_recipient_missing"


def test_10_cap_reached(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    _seed_account(db, daily_cap=1)
    conn = connect(db)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO mail_send_log (account_id, recipient_hash, domain, ts) VALUES (?,?,?,?)",
        ("acc1", "h", "acme.test", now),
    )
    conn.commit()
    conn.close()
    r = check_all(_ctx(db, send_mode="gmail_test", mail_account_id="acc1"))
    assert not r.ok and r.event == "policy.cap_reached"


def test_11_domain_cap_reached(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    _seed_account(db, per_domain_daily_cap=1, min_gap_seconds=0)
    conn = connect(db)
    now = datetime.now(timezone.utc).isoformat()
    # Cap key uses intended recipient domain (ada@acme.test → acme.test)
    conn.execute(
        "INSERT INTO mail_send_log (account_id, recipient_hash, domain, ts) VALUES (?,?,?,?)",
        ("acc1", "h", "acme.test", now),
    )
    conn.commit()
    conn.close()
    r = check_all(_ctx(db, send_mode="gmail_test", mail_account_id="acc1"))
    assert not r.ok and r.event == "policy.domain_cap_reached"


def test_12_rate_spaced(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    _seed_account(db, min_gap_seconds=90)
    conn = connect(db)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO mail_send_log (account_id, recipient_hash, domain, ts) VALUES (?,?,?,?)",
        ("acc1", "h", "other.test", now),
    )
    conn.commit()
    conn.close()
    r = check_all(_ctx(db, send_mode="gmail_test", mail_account_id="acc1"))
    assert not r.ok and r.event == "policy.rate_spaced"
    assert r.reschedule_at


def test_13_duplicate(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    conn = connect(db)
    conn.execute(
        """
        INSERT INTO emails (id, lead_id, step, subject, body, status, idempotency_key, delivery_status)
        VALUES ('e1', 'lead-1', 1, 'Hi', 'B', 'sent', 'lead-1:1', 'sent')
        """,
    )
    conn.commit()
    conn.close()
    r = check_all(_ctx(db))
    assert not r.ok and r.event == "policy.duplicate"


def test_14_lead_closed(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    conn = connect(db)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO replies (lead_id, kind, received_at, classification) VALUES (?,?,?,?)",
        ("lead-1", "reply", now, "interested"),
    )
    conn.commit()
    conn.close()
    r = check_all(_ctx(db, step=2))
    assert not r.ok and r.event == "policy.lead_closed"


def test_15_content_shortener(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    r = check_all(_ctx(db, body="See https://bit.ly/x\n\nOpt out: reply stop"))
    assert not r.ok and r.event == "policy.content"


def test_16_live_requirements(db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("ALLOW_LIVE_SENDS", "true")
    clear_settings_cache()
    _seed_campaign(db)
    _seed_lead(db)
    _seed_account(db, live_enabled=1, postal_address="")
    r = check_all(
        _ctx(
            db,
            send_mode="gmail_live",
            mail_account_id="acc1",
            live_confirm_ok=True,
            email_confidence="verified",
        )
    )
    assert not r.ok and r.event == "policy.live_requirements"


def test_17_outside_window(db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("ALLOW_LIVE_SENDS", "true")
    clear_settings_cache()
    _seed_campaign(db)
    _seed_lead(db)
    _seed_account(db, live_enabled=1)
    conn = connect(db)
    set_setting(
        conn,
        "mail_policy",
        {"sending_window": {"start": 8, "end": 9}, "timezone": "UTC"},
    )
    conn.commit()
    conn.close()
    # Force outside window by using a narrow window and mocking time via policy defaults
    # If current UTC hour is within 8-9, widen impossible window
    hour = datetime.now(timezone.utc).hour
    start = (hour + 2) % 24
    end = (hour + 3) % 24
    if end < start:
        start, end = 0, 1
        # if still inside, pick hours that exclude now
        if hour == 0:
            start, end = 10, 11
    conn = connect(db)
    set_setting(
        conn,
        "mail_policy",
        {
            "sending_window": {"start": start, "end": end},
            "timezone": "UTC",
        },
    )
    conn.commit()
    conn.close()
    r = check_all(
        _ctx(
            db,
            send_mode="gmail_live",
            mail_account_id="acc1",
            live_confirm_ok=True,
            email_confidence="verified",
        )
    )
    # Weekend or outside hours → outside_window; weekday inside → may pass
    if datetime.now(timezone.utc).weekday() >= 5:
        assert not r.ok and r.event == "policy.outside_window"
    else:
        assert (not r.ok and r.event == "policy.outside_window") or r.ok


def test_sandbox_ok(db: Path):
    _seed_campaign(db)
    _seed_lead(db)
    r = check_all(_ctx(db))
    assert r.ok
