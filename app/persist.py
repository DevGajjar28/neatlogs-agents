"""Write campaign / lead / email rows for v0 runs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.infra.db import connect, init_db


def persist_v0_run(state: dict[str, Any]) -> None:
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    now = datetime.now(timezone.utc).isoformat()
    campaign_id = state["campaign_id"]
    try:
        conn.execute(
            """
            INSERT INTO campaigns (id, created_at, input_json, status, trace_ids)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET status = excluded.status, input_json = excluded.input_json
            """,
            (
                campaign_id,
                now,
                json.dumps(state.get("input") or {}),
                "drafted",
                json.dumps([]),
            ),
        )

        contacts = {c["id"]: c for c in (state.get("contacts") or []) if isinstance(c, dict)}
        drafts = state.get("drafts") or {}
        companies = [
            c for c in (state.get("companies") or []) if isinstance(c, dict) and c.get("id")
        ]

        # Companies with no contact still get a lead row so the UI can show Add contact.
        contact_company_ids = {
            str(c.get("company_id")) for c in contacts.values() if c.get("company_id")
        }
        for company in companies:
            cid = str(company["id"])
            drop = company.get("drop_reason")
            status = company.get("status")
            if cid in contact_company_ids:
                continue
            if status == "dropped" and drop == "no_contact":
                lead_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{campaign_id}:company:{cid}"))
                conn.execute(
                    """
                    INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        status = CASE
                            WHEN leads.status IN ('drafted', 'approved', 'sent') THEN leads.status
                            ELSE excluded.status
                        END,
                        updated_at = excluded.updated_at
                    """,
                    (lead_id, campaign_id, cid, None, "no_contact", now),
                )

        for contact_id, sequence in drafts.items():
            contact = contacts.get(contact_id) or {}
            lead_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{campaign_id}:{contact_id}"))
            conn.execute(
                """
                INSERT INTO leads (id, campaign_id, company_id, contact_id, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at,
                    contact_id = excluded.contact_id
                """,
                (
                    lead_id,
                    campaign_id,
                    contact.get("company_id"),
                    contact_id,
                    "drafted",
                    now,
                ),
            )
            for draft in sequence:
                email_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{lead_id}:{draft.get('step')}"))
                idem = f"{lead_id}:{draft.get('step')}"
                conn.execute(
                    """
                    INSERT INTO emails (id, lead_id, step, subject, body, status, idempotency_key, sent_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(id) DO UPDATE SET subject = excluded.subject, body = excluded.body, status = excluded.status
                    """,
                    (
                        email_id,
                        lead_id,
                        int(draft.get("step") or 1),
                        draft.get("subject") or "",
                        draft.get("body") or "",
                        "draft",
                        idem,
                    ),
                )
        conn.commit()
    finally:
        conn.close()
