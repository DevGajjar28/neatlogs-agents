"""B0: purge, DEMO_MODE simulate_reply, structured reporter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import clear_settings_cache
from app.infra.cache import ResponseCache
from app.infra.db import connect, init_db
from app.infra.purge import purge_campaign
from app.reporter.run_report import compare, compute_metrics, write_comparison, write_report
from app.scheduler.worker import DemoModeRequired, simulate_reply


@pytest.fixture()
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "b0.db"
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATA_MODE", "replay")
    clear_settings_cache()
    init_db(path)
    yield path
    clear_settings_cache()


def _seed_campaign(db: Path, campaign_id: str = "camp-a") -> str:
    conn = connect(db)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO campaigns (id, created_at, input_json, status) VALUES (?, ?, ?, ?)",
        (campaign_id, now, json.dumps({"n": 5, "company_name": "Acme", "mode": "replay"}), "drafted"),
    )
    lead_id = f"{campaign_id}-lead"
    conn.execute(
        "INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at) VALUES (?,?,?,?,?,?)",
        (lead_id, campaign_id, "co", "ct", "sent", now),
    )
    conn.execute(
        """
        INSERT INTO emails (id, lead_id, step, subject, body, status, idempotency_key, sent_at)
        VALUES (?, ?, 1, 'Hi', 'Body', 'sent', ?, ?)
        """,
        (f"{lead_id}-e1", lead_id, f"{lead_id}:1", now),
    )
    conn.execute(
        """
        INSERT INTO budget_ledger (campaign_id, step, endpoint, credits, cache_hit, ts)
        VALUES (?, 'company_search', '/company/search', 1.5, 0, ?)
        """,
        (campaign_id, now),
    )
    conn.execute(
        """
        INSERT INTO budget_ledger (campaign_id, step, endpoint, credits, cache_hit, ts)
        VALUES (?, 'company_search', '/company/search', 0.0, 1, ?)
        """,
        (campaign_id, now),
    )
    conn.commit()
    conn.close()
    cache = ResponseCache(db)
    cache.put("k1", "/company/search", {"q": 1}, {"ok": True}, 1.5, campaign_id=campaign_id)
    return lead_id


def test_simulate_reply_requires_demo_mode(db: Path, monkeypatch: pytest.MonkeyPatch):
    lead_id = _seed_campaign(db)
    monkeypatch.setenv("DEMO_MODE", "false")
    clear_settings_cache()
    with pytest.raises(DemoModeRequired, match="DEMO_MODE"):
        simulate_reply(lead_id, db_path=str(db))


def test_simulate_reply_ok_in_demo(db: Path):
    lead_id = _seed_campaign(db)
    simulate_reply(lead_id, db_path=str(db))
    conn = connect(db)
    n = conn.execute("SELECT COUNT(*) AS n FROM replies WHERE lead_id = ?", (lead_id,)).fetchone()["n"]
    conn.close()
    assert n == 1


def test_purge_removes_cache_and_rows(db: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_campaign(db, "purge-me")
    # Seed a checkpoint thread
    from app.graph import build_graph, initial_state, open_checkpointer

    monkeypatch.setenv("NEATLOGS_API_KEY", "test-key-not-used")
    conn, saver = open_checkpointer(str(db))
    try:
        graph = build_graph(saver)
        state = initial_state(
            campaign_id="purge-me",
            company_name="Acme",
            website="https://acme.test",
            description="x",
            n=5,
            mode="replay",
        )
        # Put a checkpoint without running full graph: use saver via update_state
        graph.update_state(
            {"configurable": {"thread_id": "purge-me"}},
            state,
        )
    finally:
        conn.close()

    result = purge_campaign("purge-me", db_path=db)
    assert result["leads"] == 1
    conn = connect(db)
    assert conn.execute("SELECT COUNT(*) AS n FROM campaigns WHERE id='purge-me'").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM cache WHERE campaign_id='purge-me'").fetchone()["n"] == 0
    conn.close()

    conn2, saver2 = open_checkpointer(str(db))
    try:
        snap = build_graph(saver2).get_state({"configurable": {"thread_id": "purge-me"}})
        assert not (snap.values or {})
    finally:
        conn2.close()


def test_compute_metrics_and_compare(db: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_campaign(db, "m1")
    _seed_campaign(db, "m2")
    # Heavier spend on m2
    conn = connect(db)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO budget_ledger (campaign_id, step, endpoint, credits, cache_hit, ts)
        VALUES ('m2', 'enrich', '/company/enrich', 4.0, 0, ?)
        """,
        (now,),
    )
    conn.commit()
    conn.close()

    state = {
        "campaign_id": "m1",
        "input": {"company_name": "Acme", "n": 5, "mode": "replay"},
        "companies": [{"id": "1", "status": "kept"}, {"id": "2", "status": "dropped"}],
        "contacts": [{"id": "c1"}],
        "events": [
            {"type": "verify.pass"},
            {"type": "recovery.explain_retry"},
            {"type": "fallback.contact_step_2"},
        ],
        "errors": [],
    }
    metrics = compute_metrics("m1", state=state, wall_seconds=12.0, db_path=db)
    assert metrics["credits_spent"] == 1.5
    assert metrics["companies_kept"] == 1
    assert metrics["verifier_pass"] == 1
    assert metrics["recoveries_by_type"]["recovery.explain_retry"] == 1
    assert metrics["cache_hit_rate"] == 0.5

    path = write_report("m1", state=state, wall_seconds=12.0, db_path=db, path=db.parent / "m1.md")
    assert path.exists()
    assert path.with_suffix(".json").exists()

    rows = compare("m1", "m2", db_path=db)
    credits_row = next(r for r in rows if r["metric"] == "credits_spent")
    assert credits_row["current"] == 5.5
    assert credits_row["better"] is False

    cmp_path = write_comparison("m1", "m2", db_path=db, path=db.parent / "comparison.md")
    assert "credits_spent" in cmp_path.read_text(encoding="utf-8")
