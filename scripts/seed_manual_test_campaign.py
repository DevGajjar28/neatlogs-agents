"""Seed a no-Crustdata campaign: one company ready for Add contact → draft → send."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.api import state_reader
from app.campaign_runner import ensure_campaign_row, run_config
from app.config import clear_settings_cache, get_settings
from app.graph import build_graph, open_checkpointer
from app.infra.db import connect, init_db
from app.infra.events import set_stage
from app.persist import persist_v0_run


CAMPAIGN_ID = "ui-manual-test"
COMPANY_ID = "anyco"


def main() -> None:
    clear_settings_cache()
    settings = get_settings()
    init_db(settings.db_path)
    now = datetime.now(timezone.utc).isoformat()

    # Prefer the user's verified mail account
    conn = connect(settings.db_path)
    try:
        acc = conn.execute(
            """
            SELECT id, label, email, live_enabled FROM mail_accounts
            WHERE status = 'ok' ORDER BY is_default DESC, updated_at DESC LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()

    mail_account_id = acc["id"] if acc else None
    send_mode = "gmail_test"
    if acc and int(acc["live_enabled"] or 0) == 1:
        # Still default to test so allowlist applies; user can create live later
        send_mode = "gmail_test"

    options = {
        "send_mode": send_mode,
        "mail_account_id": mail_account_id,
        "target_mode": "provided",
        "provided_companies": [
            {
                "name": "AnyCompany",
                "domain": "anycompany.test",
                "description": "Manual test target — add your own contact email.",
            }
        ],
        "template_snapshot": (
            "# Voice\nDirect and short.\n\n"
            "# Structure\nHook, one proof point, soft ask.\n\n"
            "# Do not\nNo pricing, no legal claims.\n"
        ),
        "manual_seed": True,
    }

    ensure_campaign_row(
        CAMPAIGN_ID,
        company_name="SignalSDR Demo",
        website="https://signalsdr.local",
        description="Manual send test without Crustdata. Add a contact and approve.",
        n=1,
        mode="replay",
        options=options,
        status="completed",
    )

    # Force completed + names even if row already existed as completed
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            UPDATE campaigns SET
              status = 'completed',
              seller_name = 'SignalSDR Demo',
              seller_domain = 'signalsdr.local',
              options_json = ?,
              input_json = ?
            WHERE id = ?
            """,
            (
                json.dumps(options),
                json.dumps(
                    {
                        "company_name": "SignalSDR Demo",
                        "website": "https://signalsdr.local",
                        "description": "Manual send test without Crustdata.",
                        "n": 1,
                        "mode": "replay",
                        "target_mode": "provided",
                        "template_snapshot": options["template_snapshot"],
                    }
                ),
                CAMPAIGN_ID,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    seller = {
        "company_name": "SignalSDR Demo",
        "domain": "signalsdr.local",
        "one_liner": "Outbound agent that only sends claims it can prove.",
        "products": ["SignalSDR"],
        "value_props": ["Evidence-backed outbound", "Human approval before send"],
        "pricing_notes": None,
        "named_customers": [],
        "evidence": [],
    }
    company = {
        "id": COMPANY_ID,
        "name": "AnyCompany",
        "domain": "anycompany.test",
        "status": "dropped",
        "drop_reason": "no_contact",
        "fit_score": 0.9,
        "description": "Placeholder company for manual contact testing.",
    }
    account = {
        "company_id": COMPANY_ID,
        "story": "AnyCompany is on your test list. Add a contact to draft email.",
        "why_now": ["Manual test — no Crustdata research."],
        "evidence": [
            {
                "id": "ev_manual_seed",
                "fact": "Company added from your list for a send test.",
                "source_type": "user_input",
                "source_ref": "manual_seed",
                "observed_at": now[:10],
                "fetched_at": now,
                "confidence": "high",
            }
        ],
    }

    state = {
        "campaign_id": CAMPAIGN_ID,
        "input": {
            "company_name": "SignalSDR Demo",
            "website": "https://signalsdr.local",
            "description": "Manual send test without Crustdata.",
            "n": 1,
            "mode": "replay",
            "target_mode": "provided",
            "provided_companies": options["provided_companies"],
            "template_snapshot": options["template_snapshot"],
        },
        "seller": seller,
        "icp": {
            "title_keywords": ["Founder", "CEO"],
            "seniority": ["c_level"],
            "industries": ["software"],
            "geo": ["US"],
            "notes": "Manual test ICP",
        },
        "companies": [company],
        "accounts": {COMPANY_ID: account},
        "contacts": [],
        "drafts": {},
        "verifier": {},
        "extras": {
            "target_mode": "provided",
            "template_snapshot": options["template_snapshot"],
            "pending_email_approval": True,
        },
        "events": [],
        "errors": [],
        "plan": {"phase": "after_email", "next": "done"},
    }

    # Write LangGraph checkpoint so Add contact / leads API work
    conn, checkpointer = open_checkpointer()
    try:
        graph = build_graph(checkpointer)
        cfg = run_config(CAMPAIGN_ID)
        try:
            graph.update_state(cfg, state)
        except Exception:
            graph.update_state(cfg, state, as_node="sender")
    finally:
        conn.close()
    state_reader.invalidate(CAMPAIGN_ID)

    persist_v0_run(state)

    for stage, st, label in (
        ("plan", "done", "Manual seed"),
        ("product", "done", "Seller ready"),
        ("buyers", "done", "Your list"),
        ("icp", "done", "Skipped"),
        ("accounts", "done", "1 company"),
        ("emails", "waiting", "Add a contact"),
        ("verify", "pending", None),
        ("approval", "pending", None),
        ("send", "pending", None),
    ):
        set_stage(CAMPAIGN_ID, stage, st, label)

    print(f"Seeded campaign: {CAMPAIGN_ID}")
    print(f"Open: http://localhost:3000/campaigns/{CAMPAIGN_ID}")
    print("1) Click + Add contact on AnyCompany")
    print("2) Put your test name + email (must be on mail test allowlist for gmail_test)")
    print("3) Approve & send from the lead drawer")
    if mail_account_id and acc:
        print(f"Mail account: {acc['email']} ({mail_account_id}), send_mode={send_mode}")
    else:
        print("WARNING: no mail account connected — attach one before send")


if __name__ == "__main__":
    main()
