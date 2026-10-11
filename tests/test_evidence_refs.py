"""Evidence-id strip/find + writer sanitize + policy rule 15."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.agents.email_writer import sanitize_step
from app.agents.evidence_refs import find_refs, strip_refs
from app.agents.verifier import verify_draft
from app.config import clear_settings_cache
from app.infra.db import init_db
from app.mail.policy import PolicyContext, check_all
from app.models import Contact, DraftClaim, EmailDraft, EvidenceCard


ANARK = (
    "Anark's recent leadership expansion (ev_f1d17a8f39504204, ev_4a6c077fc8ede570) "
    "signals readiness to scale AI agents."
)


def test_strip_refs_bracket_paren_lists_and_bare():
    assert find_refs("Hello [ev_abc123] world") == ["ev_abc123"]
    assert "ev_" not in strip_refs("Hello [ev_abc123] world").lower()
    assert "ev_" not in strip_refs("Hello (ev_abc123) world").lower()
    assert "ev_" not in strip_refs("Hello (ev_abc123, ev_def456) world").lower()
    assert "ev_" not in strip_refs("Hello [ev_abc123; ev_def456] world").lower()
    assert "ev_" not in strip_refs("bare ev_abc123 end.").lower()
    clean = strip_refs(ANARK)
    assert "ev_" not in clean.lower()
    assert "Anark" in clean
    assert "signals readiness" in clean
    # no double spaces / space before punctuation
    assert "  " not in clean
    assert " ," not in clean


def test_sanitize_moves_ids_into_claims():
    subject = "Scale agents (ev_f1d17a8f39504204)"
    body = ANARK + '\n\nIf this isn\'t relevant, reply "stop" and I won\'t email again.'
    allowed = ["ev_f1d17a8f39504204", "ev_4a6c077fc8ede570"]
    subj, out_body, claims, n = sanitize_step(subject, body, [], allowed)
    assert n >= 2
    assert not find_refs(f"{subj}\n{out_body}")
    assert any("Anark" in c.text for c in claims)
    ids = {i for c in claims for i in c.evidence_ids}
    assert "ev_f1d17a8f39504204" in ids


def test_verify_draft_flags_internal_ref():
    contact = Contact(
        id="c1",
        company_id="1",
        name="Ada",
        title="CTO",
        role_kind="economic_buyer",
        email="a@x.test",
        email_source="crustdata",
        email_confidence="verified",
        profile_url=None,
    )
    evidence = [
        EvidenceCard(
            id="ev_f1d17a8f39504204",
            fact="Leadership expansion",
            source_type="web",
            source_ref="https://example.test",
            observed_at=None,
            fetched_at=datetime.now(timezone.utc),
            confidence="high",
        )
    ]
    draft = EmailDraft(
        step=1,
        subject="Hi",
        body=ANARK + '\n\nIf this isn\'t relevant, reply "stop" and I won\'t email again.',
        cited_evidence_ids=["ev_f1d17a8f39504204"],
        send_after_days=0,
        claims=[],
    )
    result = verify_draft(draft, evidence=evidence, contact=contact, use_llm=False)
    assert not result.passed
    assert "internal_ref" in result.issues


@pytest.fixture()
def policy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "pol.db"
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ALLOW_LIVE_SENDS", "false")
    monkeypatch.setenv("SIGNALSDR_SECRET_KEY", key)
    clear_settings_cache()
    init_db(path)
    from app.infra.db import connect
    from app.mail.policy import set_setting

    conn = connect(path)
    try:
        set_setting(conn, "sending_paused", False)
        conn.execute(
            """
            INSERT INTO campaigns (id, created_at, input_json, status, options_json)
            VALUES ('c1', ?, '{}', 'running', '{"send_mode":"sandbox"}')
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.execute(
            """
            INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at)
            VALUES ('l1', 'c1', 'co1', 'c1', 'approved', ?)
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
    finally:
        conn.close()
    yield path
    clear_settings_cache()


def _ctx(db: Path, body: str, subject: str = "Hi") -> PolicyContext:
    return PolicyContext(
        campaign_id="c1",
        lead_id="l1",
        step=1,
        send_mode="sandbox",
        mail_account_id=None,
        to_email="prospect@example.test",
        email_confidence="verified",
        allow_guessed=False,
        approved=True,
        verifier_passed=True,
        subject=subject,
        body=body,
        seller_domain="seller.test",
        live_confirm_ok=False,
        db_path=str(db),
    )


@pytest.mark.parametrize(
    "text",
    [
        "Hello [ev_abc123] there",
        "Hello (ev_abc123) there",
        "Hello (ev_abc123, ev_def456) there",
        "Hello [ev_abc123; ev_def456] there",
        "Hello ev_abc123 there",
        ANARK,
    ],
)
def test_policy_blocks_all_ev_forms(policy_db, text):
    r = check_all(
        _ctx(
            policy_db,
            text + '\n\nIf this isn\'t relevant, reply "stop" and I won\'t email again.',
        )
    )
    assert not r.ok
    assert r.event == "policy.content"
    assert r.reason == "internal_ref"
