"""Tool-less reply decision agent + draft persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.agents.reply_decision import (
    ReplyTicket,
    approve_and_send_reply_draft,
    decide_reply,
    get_pending_draft_for_lead,
    reject_reply_draft,
    run_decision_for_ticket,
)
from app.config import clear_settings_cache
from app.infra.db import connect, init_db


@pytest.fixture()
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "rd.db"
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
        INSERT INTO campaigns (id, created_at, input_json, status, options_json)
        VALUES ('c1', ?, '{}', 'running', '{"send_mode":"sandbox"}')
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
    conn.commit()
    conn.close()
    yield path
    clear_settings_cache()


def test_opt_out_no_draft(db: Path):
    ticket = ReplyTicket(
        lead_id="l1",
        campaign_id="c1",
        classification="opt_out",
        snippet="unsubscribe please",
    )
    out = decide_reply(ticket, use_llm=False)
    assert out.action == "mark_only"


def test_meeting_request_creates_slots_and_draft(db: Path):
    ticket = ReplyTicket(
        lead_id="l1",
        campaign_id="c1",
        classification="meeting_request",
        snippet="Happy to jump on a call next week",
        our_subject="Intro",
        contact_name="Alex",
        in_reply_to="<inbound@x.com>",
    )
    result = run_decision_for_ticket(ticket, use_llm=False, db_path=str(db))
    assert result["draft_id"]
    assert result["meeting_id"]
    conn = connect(db)
    draft = conn.execute(
        "SELECT * FROM reply_drafts WHERE id = ?", (result["draft_id"],)
    ).fetchone()
    meeting = conn.execute(
        "SELECT * FROM meeting_proposals WHERE id = ?", (result["meeting_id"],)
    ).fetchone()
    conn.close()
    assert draft["status"] == "pending"
    assert meeting["status"] == "proposed"
    assert "Alex" in draft["body"] or "there" in draft["body"]


def test_reject_draft(db: Path):
    ticket = ReplyTicket(
        lead_id="l1",
        campaign_id="c1",
        classification="interested",
        snippet="Sounds good",
        our_subject="Intro",
    )
    result = run_decision_for_ticket(ticket, use_llm=False, db_path=str(db))
    out = reject_reply_draft(result["draft_id"], db_path=str(db))
    assert out["status"] == "rejected"


def test_approve_sends_via_mailer(db: Path, monkeypatch: pytest.MonkeyPatch):
    sent = {}

    def fake_send(**kwargs):
        sent.update(kwargs)
        return {"status": "sent"}

    monkeypatch.setattr("app.tools.mailer.send", fake_send)

    ticket = ReplyTicket(
        lead_id="l1",
        campaign_id="c1",
        classification="question",
        snippet="What does pricing look like?",
        our_subject="Intro",
        in_reply_to="<them@x.com>",
    )
    result = run_decision_for_ticket(ticket, use_llm=False, db_path=str(db))
    out = approve_and_send_reply_draft(
        result["draft_id"],
        to_email="alex@acme.io",
        db_path=str(db),
    )
    assert out["status"] == "sent"
    assert sent["thread_in_reply_to"] == "<them@x.com>"
    assert sent["keep_subject"] is True
    assert sent["to_email"] == "alex@acme.io"


def test_approve_with_slot_puts_time_in_body(db: Path, monkeypatch: pytest.MonkeyPatch):
    sent = {}

    def fake_send(**kwargs):
        sent.update(kwargs)
        return {"status": "sent"}

    monkeypatch.setattr("app.tools.mailer.send", fake_send)

    ticket = ReplyTicket(
        lead_id="l1",
        campaign_id="c1",
        classification="meeting_request",
        snippet="Happy to jump on a call Tuesday 5pm",
        our_subject="Intro",
        in_reply_to="<them@x.com>",
        contact_name="Alex",
    )
    result = run_decision_for_ticket(ticket, use_llm=False, db_path=str(db))
    draft = get_pending_draft_for_lead("l1", db_path=str(db))
    assert draft and draft.get("meeting") and draft["meeting"]["slots"]
    slot_label = draft["meeting"]["slots"][0]["label"]
    out = approve_and_send_reply_draft(
        result["draft_id"],
        to_email="alex@acme.io",
        selected_slot_label=slot_label,
        db_path=str(db),
    )
    assert out["status"] == "sent"
    assert slot_label in sent["body"]
    assert "confirmed for" in sent["body"].lower()
