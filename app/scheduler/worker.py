"""Durable follow-up worker loop over scheduled_jobs."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.infra.db import connect, init_db
from app.tools.mailer import MailerError, PolicyDenied, send


def process_due_jobs(
    *,
    limit: int = 20,
    db_path: str | None = None,
    smtp_send: Any | None = None,
) -> list[dict[str, Any]]:
    """Process pending jobs whose run_at <= now. Safe to call after restart."""
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    results: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    try:
        jobs = conn.execute(
            """
            SELECT id, lead_id, email_id, run_at, attempts
            FROM scheduled_jobs
            WHERE status = 'pending' AND run_at <= ?
            ORDER BY run_at ASC
            LIMIT ?
            """,
            (now, limit),
        ).fetchall()

        for job in jobs:
            lead_id = job["lead_id"]
            job_id = job["id"]
            email_id = job["email_id"]

            reply = conn.execute(
                """
                SELECT kind FROM replies
                WHERE lead_id = ?
                ORDER BY received_at DESC
                LIMIT 1
                """,
                (lead_id,),
            ).fetchone()
            if reply:
                _cancel_lead_jobs(conn, lead_id, status_lead=reply["kind"])
                results.append(
                    {
                        "job_id": job_id,
                        "lead_id": lead_id,
                        "status": "cancelled",
                        "reason": reply["kind"],
                    }
                )
                continue

            email_row = conn.execute(
                "SELECT step, subject, body FROM emails WHERE id = ?",
                (email_id,),
            ).fetchone()
            if not email_row:
                conn.execute(
                    "UPDATE scheduled_jobs SET status = 'failed', attempts = attempts + 1 WHERE id = ?",
                    (job_id,),
                )
                results.append({"job_id": job_id, "status": "missing_email"})
                continue

            lead = conn.execute(
                "SELECT contact_id, campaign_id FROM leads WHERE id = ?",
                (lead_id,),
            ).fetchone()
            contact_email = f"{lead_id}@unknown.local"
            confidence = "likely"
            allow_guessed = True  # already approved path to schedule
            # Prefer sandbox; original address unknown at worker — demo rewrite handles it.

            try:
                outcome = send(
                    lead_id=lead_id,
                    step=int(email_row["step"]),
                    subject=email_row["subject"],
                    body=email_row["body"],
                    to_email=contact_email,
                    email_confidence=confidence,
                    allow_guessed=allow_guessed,
                    campaign_id=(lead["campaign_id"] if lead else ""),
                    actor="worker",
                    db_path=path,
                    smtp_send=smtp_send,
                )
                conn.execute(
                    "UPDATE scheduled_jobs SET status = 'done' WHERE id = ?",
                    (job_id,),
                )
                results.append(
                    {
                        "job_id": job_id,
                        "lead_id": lead_id,
                        "status": outcome.get("status"),
                        "step": int(email_row["step"]),
                    }
                )
            except (PolicyDenied, MailerError) as exc:
                conn.execute(
                    """
                    UPDATE scheduled_jobs
                    SET attempts = attempts + 1, status = CASE WHEN attempts + 1 >= 3 THEN 'failed' ELSE 'pending' END
                    WHERE id = ?
                    """,
                    (job_id,),
                )
                results.append(
                    {
                        "job_id": job_id,
                        "lead_id": lead_id,
                        "status": "retry",
                        "error": str(exc),
                    }
                )
            conn.commit()
        conn.commit()
        return results
    finally:
        conn.close()


def run_forever(poll_seconds: float = 20.0, db_path: str | None = None) -> None:
    """Poll loop for local demos. Ctrl+C to stop; schedule survives in SQLite."""
    while True:
        results = process_due_jobs(db_path=db_path)
        if results:
            for row in results:
                print(row)
        time.sleep(poll_seconds)


def simulate_reply(lead_id: str, *, kind: str = "reply", db_path: str | None = None) -> None:
    """Insert a reply/opt_out so the next worker pass cancels remaining follow-ups."""
    if kind not in {"reply", "opt_out"}:
        raise ValueError("kind must be reply or opt_out")
    settings = get_settings()
    path = db_path or settings.db_path
    init_db(path)
    conn = connect(path)
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "INSERT INTO replies (lead_id, kind, received_at) VALUES (?, ?, ?)",
            (lead_id, kind, now),
        )
        conn.execute(
            "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
            ("replied" if kind == "reply" else "opted_out", now, lead_id),
        )
        conn.commit()
    finally:
        conn.close()


def _cancel_lead_jobs(conn, lead_id: str, *, status_lead: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE scheduled_jobs
        SET status = 'cancelled'
        WHERE lead_id = ? AND status = 'pending'
        """,
        (lead_id,),
    )
    conn.execute(
        "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
        (status_lead if status_lead in {"replied", "opted_out"} else "replied", now, lead_id),
    )
