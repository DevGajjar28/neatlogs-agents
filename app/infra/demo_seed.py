"""Demo seed loader for MindArmor preloaded contacts (local recording only)."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import get_settings
from app.infra.db import connect, init_db

FREE_MAIL = frozenset(
    {"gmail.com", "bigpond.com", "outlook.com", "yahoo.com", "hotmail.com"}
)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SEED_NAME = "mindarmor"
SEED_DOMAIN = "mindarmor.ai"
DEMO_DIR = Path("config/demo")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_seller_domain(website_or_domain: str) -> str:
    raw = (website_or_domain or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    host = urlparse(raw).hostname or ""
    if host.startswith("www."):
        host = host[4:]
    return host.strip(".")


def demo_seed_enabled() -> bool:
    return bool(get_settings().demo_seed)


def is_seed_campaign(state_or_opts: dict[str, Any] | None) -> bool:
    """True when this campaign was started from a demo seed snapshot."""
    if not isinstance(state_or_opts, dict):
        return False
    extras = state_or_opts.get("extras") if isinstance(state_or_opts.get("extras"), dict) else {}
    inp = state_or_opts.get("input") if isinstance(state_or_opts.get("input"), dict) else {}
    if extras.get("seed") or inp.get("seed"):
        return True
    tm = str(
        extras.get("target_mode")
        or inp.get("target_mode")
        or state_or_opts.get("target_mode")
        or ""
    )
    return tm == "provided_contacts"


def contacts_csv_path(name: str = SEED_NAME) -> Path:
    return DEMO_DIR / f"{name}_contacts.csv"


def seller_json_path(name: str = SEED_NAME) -> Path:
    return DEMO_DIR / f"{name}_seller.json"


def parse_contacts_csv(text: str) -> dict[str, Any]:
    """Parse + validate contact CSV. Dedupes by email (case-insensitive)."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    contacts: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    seen_emails: set[str] = set()
    domain_missing = 0

    for i, row in enumerate(reader, start=2):
        name = str(row.get("name") or "").strip()
        email = str(row.get("email") or "").strip().lower()
        company = str(row.get("company") or "").strip()
        domain = str(row.get("domain") or "").strip().lower()
        title = str(row.get("title") or "").strip()
        note = str(row.get("note") or "").strip()
        raw_test = str(row.get("is_test_inbox") or "").strip().lower()
        is_test = raw_test in {"1", "true", "yes", "y"}

        if not name or not email:
            skipped.append({"row": str(i), "reason": "name_and_email_required"})
            continue
        if not EMAIL_RE.match(email):
            skipped.append({"row": str(i), "reason": "bad_email", "email": email})
            continue
        if email in seen_emails:
            skipped.append({"row": str(i), "reason": "duplicate_email", "email": email})
            continue
        seen_emails.add(email)

        email_domain = email.rsplit("@", 1)[-1]
        flag_missing = False
        if not domain:
            if email_domain in FREE_MAIL:
                flag_missing = True
                domain_missing += 1
            else:
                domain = email_domain
        if domain.startswith("www."):
            domain = domain[4:]

        contacts.append(
            {
                "name": name,
                "email": email,
                "company": company or domain or "Unknown",
                "domain": domain,
                "title": title,
                "is_test_inbox": is_test,
                "note": note,
                "domain_missing": flag_missing,
            }
        )

    companies = sorted(
        {
            (c["company"], c["domain"] or "")
            for c in contacts
        }
    )
    return {
        "contacts": contacts,
        "skipped": skipped,
        "companies": [{"name": n, "domain": d} for n, d in companies],
        "test_inboxes": [c["email"] for c in contacts if c["is_test_inbox"]],
        "domain_missing": domain_missing,
        "counts": {
            "contacts": len(contacts),
            "companies": len(companies),
            "test_inboxes": sum(1 for c in contacts if c["is_test_inbox"]),
            "skipped": len(skipped),
            "domain_missing": domain_missing,
        },
    }


def load_seller_fallback(name: str = SEED_NAME) -> dict[str, Any]:
    path = seller_json_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"Missing seller fallback: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("seller JSON must be an object")
    return data


def clear_seed(seller_domain: str = SEED_DOMAIN, *, db_path: str | None = None) -> int:
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        cur = conn.execute(
            "DELETE FROM demo_seeds WHERE seller_domain = ?",
            (normalize_seller_domain(seller_domain) or seller_domain,),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def seed_mindarmor(*, clear: bool = False, db_path: str | None = None) -> dict[str, Any]:
    """Load CSV + seller JSON into demo_seeds. Returns summary for CLI."""
    settings = get_settings()
    path = db_path or settings.db_path
    domain = SEED_DOMAIN
    if clear:
        n = clear_seed(domain, db_path=path)
        return {"cleared": n, "seller_domain": domain}

    csv_path = contacts_csv_path(SEED_NAME)
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Missing {csv_path}. Place the contact list under config/demo/ (gitignored)."
        )
    parsed = parse_contacts_csv(csv_path.read_text(encoding="utf-8-sig"))
    seller = load_seller_fallback(SEED_NAME)

    init_db(path)
    conn = connect(path)
    try:
        conn.execute("DELETE FROM demo_seeds WHERE seller_domain = ?", (domain,))
        now = _now()
        conn.execute(
            """
            INSERT INTO demo_seeds (seller_domain, kind, payload_json, created_at)
            VALUES (?, 'seller', ?, ?)
            """,
            (domain, json.dumps(seller), now),
        )
        for contact in parsed["contacts"]:
            conn.execute(
                """
                INSERT INTO demo_seeds (seller_domain, kind, payload_json, created_at)
                VALUES (?, 'contact', ?, ?)
                """,
                (domain, json.dumps(contact), now),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "seller_domain": domain,
        "seed": SEED_NAME,
        **parsed["counts"],
        "skipped_rows": parsed["skipped"],
        "test_inboxes": parsed["test_inboxes"],
    }


def has_seed_for_domain(seller_domain: str, *, db_path: str | None = None) -> bool:
    domain = normalize_seller_domain(seller_domain)
    if not domain:
        return False
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT 1 FROM demo_seeds WHERE seller_domain = ? LIMIT 1",
            (domain,),
        ).fetchone()
        return bool(row)
    finally:
        conn.close()


def load_seed_snapshot(
    seller_domain: str, *, db_path: str | None = None
) -> dict[str, Any] | None:
    """Return {seller, contacts, test_inboxes} or None if no rows."""
    domain = normalize_seller_domain(seller_domain)
    if not domain:
        return None
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    try:
        rows = conn.execute(
            "SELECT kind, payload_json FROM demo_seeds WHERE seller_domain = ?",
            (domain,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    seller: dict[str, Any] = {}
    contacts: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row["payload_json"] or "{}")
        if row["kind"] == "seller" and isinstance(payload, dict):
            seller = payload
        elif row["kind"] == "contact" and isinstance(payload, dict):
            contacts.append(payload)
    if not contacts and not seller:
        return None
    return {
        "seller_domain": domain,
        "seed": SEED_NAME if domain == SEED_DOMAIN else domain,
        "seller": seller,
        "contacts": contacts,
        "test_inboxes": [
            str(c.get("email") or "").lower()
            for c in contacts
            if c.get("is_test_inbox") and c.get("email")
        ],
        "companies": _distinct_companies(contacts),
    }


def _distinct_companies(contacts: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for c in contacts:
        name = str(c.get("company") or "").strip() or "Unknown"
        domain = str(c.get("domain") or "").strip().lower()
        key = domain or name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "domain": domain})
    return out


def match_and_apply(
    *,
    website: str,
    send_mode: str,
) -> dict[str, Any] | None:
    """If DEMO_SEED and domain has rows, return options patch for campaign create."""
    if not demo_seed_enabled():
        return None
    domain = normalize_seller_domain(website)
    snap = load_seed_snapshot(domain)
    if not snap:
        return None
    if send_mode == "gmail_live":
        raise ValueError("Demo seed campaigns can't send live.")
    contacts = list(snap["contacts"])
    companies = list(snap["companies"])
    return {
        "target_mode": "provided_contacts",
        "seed": snap.get("seed") or SEED_NAME,
        "provided_contacts": contacts,
        "provided_companies": [
            {"name": c["name"], "domain": c["domain"], "description": ""}
            for c in companies
            if c.get("domain")
        ],
        # Target = contacts (demo shows live lead generation for every person).
        "n": max(len(contacts), 1),
        "send_mode": "gmail_test",
        "seed_test_inboxes": list(snap.get("test_inboxes") or []),
        "seller_fallback": snap.get("seller") or {},
        "demo_seed_event": {
            "type": "demo.seed_applied",
            "n": len(contacts),
            "m": len(companies),
            "message": (
                f"Using a preloaded list of {len(contacts)} contacts at "
                f"{len(companies)} companies for this demo."
            ),
        },
    }
