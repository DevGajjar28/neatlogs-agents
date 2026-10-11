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
    mail_account_id TEXT,
    send_mode TEXT,
    message_id TEXT,
    in_reply_to TEXT,
    actual_recipient TEXT,
    delivery_status TEXT,
    provider_response TEXT,
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
    kind TEXT NOT NULL,
    received_at TEXT NOT NULL,
    message_id TEXT,
    from_masked TEXT,
    classification TEXT,
    snippet TEXT,
    source TEXT,
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

CREATE TABLE IF NOT EXISTS mail_accounts (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    provider TEXT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    username TEXT NOT NULL,
    password_enc TEXT,
    smtp_host TEXT NOT NULL,
    smtp_port INTEGER NOT NULL,
    smtp_security TEXT NOT NULL,
    imap_host TEXT NOT NULL,
    imap_port INTEGER NOT NULL,
    status TEXT NOT NULL,
    last_verified_at TEXT,
    last_error TEXT,
    daily_cap INTEGER NOT NULL DEFAULT 25,
    per_domain_daily_cap INTEGER NOT NULL DEFAULT 3,
    min_gap_seconds INTEGER NOT NULL DEFAULT 90,
    test_recipients_json TEXT NOT NULL DEFAULT '[]',
    live_enabled INTEGER NOT NULL DEFAULT 0,
    signature TEXT NOT NULL DEFAULT '',
    postal_address TEXT NOT NULL DEFAULT '',
    drafts_folder TEXT,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mail_send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    recipient_hash TEXT NOT NULL,
    domain TEXT NOT NULL,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    content_md TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    is_system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
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
    "mail_accounts",
    "mail_send_log",
    "email_templates",
)

_CAMPAIGN_COLS = {
    "current_stage": "TEXT",
    "pause_requested": "INTEGER NOT NULL DEFAULT 0",
    "options_json": "TEXT NOT NULL DEFAULT '{}'",
    "seller_name": "TEXT",
    "seller_domain": "TEXT",
    "baseline_campaign_id": "TEXT",
}

_EMAIL_COLS = {
    "mail_account_id": "TEXT",
    "send_mode": "TEXT",
    "message_id": "TEXT",
    "in_reply_to": "TEXT",
    "actual_recipient": "TEXT",
    "delivery_status": "TEXT",
    "provider_response": "TEXT",
}

_REPLY_COLS = {
    "message_id": "TEXT",
    "from_masked": "TEXT",
    "classification": "TEXT",
    "snippet": "TEXT",
    "source": "TEXT",
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


def _add_cols(conn: sqlite3.Connection, table: str, cols: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if not existing:
        return
    for name, decl in cols.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive migrations for existing DB files."""
    cache_cols = {row[1] for row in conn.execute("PRAGMA table_info(cache)").fetchall()}
    if cache_cols and "campaign_id" not in cache_cols:
        conn.execute("ALTER TABLE cache ADD COLUMN campaign_id TEXT")

    _add_cols(conn, "campaigns", _CAMPAIGN_COLS)
    _add_cols(conn, "emails", _EMAIL_COLS)
    _add_cols(conn, "replies", _REPLY_COLS)


def init_db(db_path: str | Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
    # Seed system default template (lazy import avoids circular deps at module load)
    try:
        from app.infra.email_templates import seed_default_template

        seed_default_template(db_path)
    except Exception:
        pass
