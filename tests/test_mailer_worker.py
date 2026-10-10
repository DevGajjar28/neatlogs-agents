"""Mailer policy + scheduler worker — mocked SMTP, no Mailpit required."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import clear_settings_cache
from app.infra.db import connect, init_db
from app.scheduler.worker import process_due_jobs, simulate_reply
from app.tools.mailer import PolicyDenied, lead_id_for, send


@pytest.fixture()
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "mail.db"
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SMTP_HOST", "localhost")
    clear_settings_cache()
    init_db(path)
    yield path
    clear_settings_cache()


def _seed_lead(db: Path, lead_id: str = "lead-1", campaign_id: str = "c1") -> None:
    conn = connect(db)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO campaigns (id, created_at, input_json, status)
        VALUES (?, ?, '{}', 'running')
        ON CONFLICT(id) DO NOTHING
        """,
        (campaign_id, now),
    )
    conn.execute(
        """
        INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at)
        VALUES (?, ?, 'co', 'ct', 'approved', ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (lead_id, campaign_id, now),
    )
    conn.commit()
    conn.close()


def test_demo_mode_rejects_non_mailpit_host(db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    clear_settings_cache()
    _seed_lead(db)
    with pytest.raises(PolicyDenied, match="mailpit"):
        send(
            lead_id="lead-1",
            step=1,
            subject="Hi",
            body="Hello\n\nOpt out: reply stop",
            to_email="ada@acme.test",
            db_path=str(db),
            smtp_send=lambda *a, **k: None,
        )


def test_idempotent_skip_and_suppression(db: Path):
    _seed_lead(db)
    sent = []

    def fake_smtp(host, port, msg):
        sent.append(msg["To"])

    out1 = send(
        lead_id="lead-1",
        step=1,
        subject="Hi",
        body="Hello\n\nOpt out: reply stop",
        to_email="ada@acme.test",
        db_path=str(db),
        smtp_send=fake_smtp,
    )
    assert out1["status"] == "sent"
    assert sent == ["lead-1@sandbox.local"]

    out2 = send(
        lead_id="lead-1",
        step=1,
        subject="Hi",
        body="Hello again",
        to_email="ada@acme.test",
        db_path=str(db),
        smtp_send=fake_smtp,
    )
    assert out2["status"] == "skipped_idempotent"
    assert len(sent) == 1

    conn = connect(db)
    conn.execute(
        "INSERT INTO suppression (email_or_domain, reason) VALUES (?, ?)",
        ("blocked.test", "bounce"),
    )
    conn.commit()
    conn.close()
    with pytest.raises(PolicyDenied, match="suppressed"):
        send(
            lead_id="lead-2",
            step=1,
            subject="Hi",
            body="x",
            to_email="x@blocked.test",
            db_path=str(db),
            smtp_send=fake_smtp,
        )


def test_guessed_requires_flag(db: Path):
    _seed_lead(db, lead_id="lead-g")
    with pytest.raises(PolicyDenied, match="guessed"):
        send(
            lead_id="lead-g",
            step=1,
            subject="Hi",
            body="Hello",
            to_email="guess@acme.test",
            email_confidence="guessed",
            allow_guessed=False,
            db_path=str(db),
            smtp_send=lambda *a, **k: None,
        )


def test_worker_sends_one_followup_and_cancels_on_reply(db: Path):
    _seed_lead(db, lead_id="lead-a", campaign_id="camp")
    _seed_lead(db, lead_id="lead-b", campaign_id="camp")
    # campaign insert conflict for second seed — fix by only inserting leads
    conn = connect(db)
    now = datetime.now(timezone.utc)
    past = (now - timedelta(minutes=1)).isoformat()
    for lead_id, step, job in (("lead-a", 2, "job-a"), ("lead-b", 2, "job-b")):
        eid = f"email-{lead_id}-{step}"
        conn.execute(
            """
            INSERT INTO emails (id, lead_id, step, subject, body, status, idempotency_key)
            VALUES (?, ?, ?, 'Follow', 'Body follow\n\nOpt out: stop', 'scheduled', ?)
            """,
            (eid, lead_id, step, f"{lead_id}:{step}"),
        )
        conn.execute(
            """
            INSERT INTO scheduled_jobs (id, lead_id, email_id, run_at, status, attempts)
            VALUES (?, ?, ?, ?, 'pending', 0)
            """,
            (job, lead_id, eid, past),
        )
    conn.commit()
    conn.close()

    simulate_reply("lead-b", db_path=str(db))
    sent_to = []

    def fake_smtp(host, port, msg):
        sent_to.append(msg["To"])

    results = process_due_jobs(db_path=str(db), smtp_send=fake_smtp)
    statuses = {r["lead_id"]: r["status"] for r in results}
    assert statuses["lead-b"] == "cancelled"
    assert statuses["lead-a"] in {"sent", "skipped_idempotent"}
    assert any(addr.startswith("lead-a@") for addr in sent_to)
    assert not any(addr.startswith("lead-b@") for addr in sent_to)

    # Restart-safe: no pending jobs left for due work except failed/cancelled
    conn = connect(db)
    pending = conn.execute(
        "SELECT id, lead_id, status FROM scheduled_jobs"
    ).fetchall()
    conn.close()
    by_lead = {r["lead_id"]: r["status"] for r in pending}
    assert by_lead["lead-a"] == "done"
    assert by_lead["lead-b"] == "cancelled"


def test_lead_id_stable():
    assert lead_id_for("c", "contact") == lead_id_for("c", "contact")
