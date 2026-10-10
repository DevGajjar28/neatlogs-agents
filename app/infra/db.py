"""SQLite schema for campaigns, leads, mail, cache, budget, audit, and UI bus tables."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    input_json TEXT NOT NULL,
    status TEXT NOT NULL,
    trace_ids TEXT NOT NULL DEFAULT '[]',
    current_stage TEXT,
    pause_requested INTEGER NOT NULL DEFAULT 0,
    options_json TEXT NOT NULL DEFAULT '{}',
    seller_name TEXT,
    seller_domain TEXT,
    baseline_campaign_id TEXT
);

CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    company_id TEXT,
    contact_id TEXT,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    sent_at TEXT,
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    email_id TEXT NOT NULL,
    run_at TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (email_id) REFERENCES emails(id)
);

CREATE TABLE IF NOT EXISTS replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('reply', 'opt_out')),
    received_at TEXT NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS suppression (
    email_or_domain TEXT PRIMARY KEY,
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cache (
    key_hash TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    request_json TEXT NOT NULL,
    response_json TEXT NOT NULL,
    credits REAL NOT NULL,
    created_at TEXT NOT NULL,
    campaign_id TEXT
);

CREATE TABLE IF NOT EXISTS budget_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    step TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    credits REAL NOT NULL,
    cache_hit INTEGER NOT NULL,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    agent TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    credits_delta REAL NOT NULL DEFAULT 0,
    lead_id TEXT,
    trace_ref TEXT,
    data_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS campaign_stages (
    campaign_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    count_label TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (campaign_id, stage)
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    pid INTEGER,
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    ended_at TEXT,
    exit_code INTEGER,
    trace_url TEXT
);

CREATE TABLE IF NOT EXISTS gate_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    gate TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    consumed_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_decisions (
    campaign_id TEXT NOT NULL,
    contact_id TEXT NOT NULL,
    action TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    allow_guessed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (campaign_id, contact_id)
);
"""

TABLES = (
    "campaigns",
    "leads",
    "emails",
    "scheduled_jobs",
    "replies",
    "suppression",
    "cache",
    "budget_ledger",
    "audit",
    "events",
    "campaign_stages",
    "runs",
    "gate_decisions",
    "settings",
    "email_decisions",
)

_CAMPAIGN_COLS = {
    "current_stage": "TEXT",
    "pause_requested": "INTEGER NOT NULL DEFAULT 0",
    "options_json": "TEXT NOT NULL DEFAULT '{}'",
    "seller_name": "TEXT",
    "seller_domain": "TEXT",
    "baseline_campaign_id": "TEXT",
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive migrations for existing DB files."""
    cache_cols = {row[1] for row in conn.execute("PRAGMA table_info(cache)").fetchall()}
    if cache_cols and "campaign_id" not in cache_cols:
        conn.execute("ALTER TABLE cache ADD COLUMN campaign_id TEXT")

    camp_cols = {row[1] for row in conn.execute("PRAGMA table_info(campaigns)").fetchall()}
    for name, decl in _CAMPAIGN_COLS.items():
        if camp_cols and name not in camp_cols:
            conn.execute(f"ALTER TABLE campaigns ADD COLUMN {name} {decl}")


def init_db(db_path: str | Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
