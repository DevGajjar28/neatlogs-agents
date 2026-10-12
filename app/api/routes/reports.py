"""Cross-campaign reports for the UI."""

from __future__ import annotations

import json

from fastapi import APIRouter

from app.api.schemas import ReportCampaignRow, ReportsOverviewOut
from app.config import get_settings
from app.infra.db import connect, init_db

router = APIRouter(tags=["reports"])


@router.get("/reports", response_model=ReportsOverviewOut)
def reports_overview() -> ReportsOverviewOut:
    """Aggregate send / reply / credit stats users can act on."""
    settings = get_settings()
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        campaigns = conn.execute(
            """
            SELECT id, seller_name, status, created_at, options_json
            FROM campaigns
            ORDER BY created_at DESC
            LIMIT 50
            """
        ).fetchall()
        rows: list[ReportCampaignRow] = []
        tot_sent = tot_fu = tot_replies = tot_meet = tot_opt = tot_bounce = 0
        tot_credits = 0.0
        tot_leads = 0

        for c in campaigns:
            cid = str(c["id"])
            try:
                opts = json.loads(c["options_json"] or "{}")
            except Exception:  # noqa: BLE001
                opts = {}
            mode = str(opts.get("mode") or "replay")

            leads = conn.execute(
                "SELECT COUNT(*) AS n FROM leads WHERE campaign_id = ?",
                (cid,),
            ).fetchone()["n"]

            sent = conn.execute(
                """
                SELECT COUNT(*) AS n FROM emails e
                JOIN leads l ON l.id = e.lead_id
                WHERE l.campaign_id = ?
                  AND (e.delivery_status = 'sent' OR e.status = 'sent')
                  AND e.step = 1
                """,
                (cid,),
            ).fetchone()["n"]

            followups = conn.execute(
                """
                SELECT COUNT(*) AS n FROM emails e
                JOIN leads l ON l.id = e.lead_id
                WHERE l.campaign_id = ?
                  AND (e.delivery_status = 'sent' OR e.status = 'sent')
                  AND e.step > 1
                """,
                (cid,),
            ).fetchone()["n"]

            replies = conn.execute(
                """
                SELECT COUNT(DISTINCT r.lead_id) AS n
                FROM replies r
                JOIN leads l ON l.id = r.lead_id
                WHERE l.campaign_id = ?
                  AND COALESCE(r.classification, '') NOT IN ('bounce', 'opt_out')
                """,
                (cid,),
            ).fetchone()["n"]

            meetings = conn.execute(
                """
                SELECT COUNT(*) AS n FROM meeting_proposals
                WHERE campaign_id = ? AND status = 'confirmed'
                """,
                (cid,),
            ).fetchone()["n"]

            opted = conn.execute(
                """
                SELECT COUNT(*) AS n FROM leads
                WHERE campaign_id = ? AND status = 'opted_out'
                """,
                (cid,),
            ).fetchone()["n"]

            bounced = conn.execute(
                """
                SELECT COUNT(*) AS n FROM leads
                WHERE campaign_id = ? AND status = 'bounced'
                """,
                (cid,),
            ).fetchone()["n"]

            credits_row = conn.execute(
                """
                SELECT COALESCE(SUM(credits), 0) AS n FROM budget_ledger
                WHERE campaign_id = ?
                """,
                (cid,),
            ).fetchone()
            credits = float(credits_row["n"] or 0)

            reply_rate = (replies / sent) if sent else None
            rows.append(
                ReportCampaignRow(
                    campaign_id=cid,
                    seller_name=str(c["seller_name"] or cid),
                    status=str(c["status"] or ""),
                    mode=mode,
                    started_at=c["created_at"],
                    leads=int(leads or 0),
                    emails_sent=int(sent or 0),
                    followups_sent=int(followups or 0),
                    replies=int(replies or 0),
                    meetings=int(meetings or 0),
                    opted_out=int(opted or 0),
                    bounced=int(bounced or 0),
                    credits_spent=round(credits, 2),
                    reply_rate=round(reply_rate, 3) if reply_rate is not None else None,
                )
            )
            tot_sent += int(sent or 0)
            tot_fu += int(followups or 0)
            tot_replies += int(replies or 0)
            tot_meet += int(meetings or 0)
            tot_opt += int(opted or 0)
            tot_bounce += int(bounced or 0)
            tot_credits += credits
            tot_leads += int(leads or 0)

        overall_rate = (tot_replies / tot_sent) if tot_sent else None
        return ReportsOverviewOut(
            campaigns=len(rows),
            emails_sent=tot_sent + tot_fu,
            replies=tot_replies,
            meetings=tot_meet,
            opted_out=tot_opt,
            bounced=tot_bounce,
            credits_spent=round(tot_credits, 2),
            reply_rate=round(overall_rate, 3) if overall_rate is not None else None,
            rows=rows,
        )
    finally:
        conn.close()
