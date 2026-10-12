"""SignalSDR command line. Agent commands are stubs until later phases."""

from __future__ import annotations

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True, help="SignalSDR outbound campaigns")


def _pending(name: str) -> None:
    typer.echo(f"{name} is not implemented yet")
    raise typer.Exit(code=1)


def _run_config(campaign_id: str, version: str = "v0.4") -> dict:
    from app.infra.tracing import callbacks

    return {
        "callbacks": callbacks(),
        "configurable": {"thread_id": campaign_id},
        "metadata": {"campaign_id": campaign_id, "version": version},
    }


def _interrupt_from_result(result: dict) -> dict | None:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return None
    first = interrupts[0]
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {"value": value}


def _interrupt_from_state(snapshot) -> dict | None:
    for task in snapshot.tasks or ():
        for item in getattr(task, "interrupts", ()) or ():
            value = getattr(item, "value", None)
            if isinstance(value, dict):
                return value
    return _interrupt_from_result(snapshot.values or {})


def _print_run_summary(cid: str, result: dict, report_path, db_path) -> None:
    kept = [c for c in (result.get("companies") or []) if c.get("status") == "kept"]
    typer.echo(f"campaign_id={cid}")
    typer.echo(f"companies={len(kept)}")
    typer.echo(f"contacts={len(result.get('contacts') or [])}")
    typer.echo(f"drafts={sum(len(v) for v in (result.get('drafts') or {}).values())}")
    typer.echo(f"credits={(result.get('budget') or {}).get('credits_spent')}")
    events = result.get("events") or []
    widen = [e for e in events if e.get("type") == "replan.widen_icp"]
    if widen:
        typer.echo(f"replan.widen_icp={len(widen)}")
    typer.echo(f"report={report_path}")
    typer.echo(f"db={db_path}")


@app.command()
def run(
    company_name: str = typer.Option("PostHog", help="Seller company name"),
    website: str = typer.Option("https://posthog.com", help="Seller website"),
    description: str = typer.Option(
        "Product analytics and feature flags for engineers",
        help="Optional one-line description",
    ),
    n: int = typer.Option(10, min=1, help="How many leads to keep"),
    campaign_id: str = typer.Option("", help="Optional campaign id / thread id"),
    chaos: str = typer.Option("", help="Comma-separated chaos flags"),
    narrow_icp: bool = typer.Option(
        False,
        "--narrow-icp",
        help="Force a thin ICP so the planner must emit replan.widen_icp",
    ),
) -> None:
    """Start a campaign (planner + ICP gate + search + account + email)."""
    import uuid
    from pathlib import Path

    from dotenv import load_dotenv

    from app.campaign_runner import (
        ensure_campaign_row,
        execute_campaign,
        interrupt_from_result,
    )
    from app.config import clear_settings_cache, get_settings

    load_dotenv(override=False)
    clear_settings_cache()
    settings = get_settings()
    cid = campaign_id.strip() or f"v0-{uuid.uuid4().hex[:10]}"
    options = {"n": n, "mode": settings.data_mode, "chaos": chaos, "narrow_icp": narrow_icp}
    ensure_campaign_row(
        cid,
        company_name=company_name,
        website=website,
        description=description,
        n=n,
        mode=settings.data_mode,
        options=options,
        status="queued",
    )
    typer.echo(f"DATA_MODE={settings.data_mode}")
    try:
        result = execute_campaign(
            cid,
            company_name=company_name,
            website=website,
            description=description,
            n=n,
            mode=settings.data_mode,
            chaos=chaos,
            narrow_icp=narrow_icp,
            kind="start",
            fresh=True,
        )
    except Exception as exc:
        from app.infra.chaos import ChaosConfigError

        if isinstance(exc, ChaosConfigError):
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        raise
    payload = interrupt_from_result(result)
    if payload and payload.get("type") == "icp_approval":
        icp = payload.get("icp") or {}
        typer.echo(f"campaign_id={cid}")
        typer.echo("status=awaiting_icp_approval")
        typer.echo(f"industries={icp.get('industries')}")
        typer.echo(f"countries={icp.get('countries')}")
        typer.echo(f"employee_count_ranges={icp.get('employee_count_ranges')}")
        typer.echo(f"Approve: python cli.py approve {cid} --yes")
        typer.echo(f"Or UI:   python -m app.ui.app -> http://127.0.0.1:8080/campaigns/{cid}/icp")
        return
    if payload and payload.get("type") == "email_approval":
        items = payload.get("items") or []
        typer.echo(f"campaign_id={cid}")
        typer.echo("status=awaiting_email_approval")
        typer.echo(f"drafts={len(items)}")
        typer.echo(f"Approve: python cli.py approve {cid} --yes")
        typer.echo(f"Or UI:   http://127.0.0.1:8080/campaigns/{cid}/emails")
        return
    from app.reporter.run_report import write_v0_report
    import time

    report_path = Path("reports") / f"{cid}.md"
    if not report_path.exists():
        write_v0_report(result, wall_seconds=0)
    _print_run_summary(cid, result, report_path, Path(settings.db_path))


@app.command("run-campaign")
def run_campaign(campaign_id: str = typer.Argument(..., help="Campaign id created by the API")) -> None:
    """Run a queued campaign row (options_json). Used by the API process spawner."""
    from dotenv import load_dotenv

    from app.campaign_runner import execute_campaign, interrupt_from_result, load_campaign_options
    from app.config import clear_settings_cache

    load_dotenv(override=False)
    clear_settings_cache()
    meta = load_campaign_options(campaign_id)
    result = execute_campaign(
        campaign_id,
        company_name=meta["company_name"],
        website=meta["website"],
        description=meta["description"],
        n=meta["n"],
        mode=meta["mode"],
        chaos=meta["chaos"],
        narrow_icp=meta["narrow_icp"],
        target_mode=meta.get("target_mode") or "discover",
        provided_companies=meta.get("provided_companies") or [],
        template_id=meta.get("template_id"),
        template_name=meta.get("template_name"),
        template_snapshot=meta.get("template_snapshot"),
        autopilot=meta.get("autopilot", True),
        kind="start",
        fresh=True,
    )
    payload = interrupt_from_result(result)
    if payload:
        typer.echo(f"campaign_id={campaign_id}")
        typer.echo(f"status=awaiting_{payload.get('type')}")
        return
    typer.echo(f"campaign_id={campaign_id} status=completed")


@app.command()
def resume(
    campaign_id: str = typer.Argument(..., help="Campaign to resume"),
    chaos: str = typer.Option("", help="Comma-separated chaos flags (omit kill_after to continue after a crash)"),
) -> None:
    """Resume a campaign from the last checkpoint (not for ICP interrupt; use approve)."""
    import time
    from pathlib import Path

    from dotenv import load_dotenv

    from app.campaign_runner import (
        begin_run,
        end_run,
        interrupt_from_result,
        interrupt_from_state,
        update_campaign_status,
    )
    from app.config import clear_settings_cache, get_settings
    from app.graph import build_graph, open_checkpointer
    from app.infra.chaos import ChaosConfigError, set_chaos
    from app.infra.tracing import finish, init_tracing
    from app.persist import persist_v0_run
    from app.reporter.run_report import write_v0_report

    load_dotenv(override=False)
    clear_settings_cache()
    settings = get_settings()
    if chaos:
        try:
            set_chaos(chaos)
        except ChaosConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
    init_tracing("outbound-resume")
    run_id = begin_run(campaign_id, "resume")
    conn, checkpointer = open_checkpointer()
    started = time.time()
    exit_code = 0
    try:
        app_graph = build_graph(checkpointer)
        config = _run_config(campaign_id)
        snap = app_graph.get_state(config)
        if interrupt_from_state(snap):
            typer.echo("Campaign is waiting on a human gate. Use: python cli.py approve <id> --yes")
            exit_code = 1
            raise typer.Exit(code=1)
        update_campaign_status(campaign_id, "running")
        result = app_graph.invoke(None, config=config)
        payload = interrupt_from_result(result)
        if payload and payload.get("type") == "icp_approval":
            update_campaign_status(campaign_id, "waiting_icp")
            typer.echo(f"campaign_id={campaign_id}")
            typer.echo("status=awaiting_icp_approval")
            return
        if payload and payload.get("type") == "email_approval":
            update_campaign_status(campaign_id, "waiting_approval")
            persist_v0_run(result)
            typer.echo(f"campaign_id={campaign_id}")
            typer.echo("status=awaiting_email_approval")
            return
        persist_v0_run(result)
        halt = result.get("halt_reason")
        update_campaign_status(campaign_id, "halted" if halt else "completed")
        report_path = write_v0_report(result, wall_seconds=time.time() - started)
        _print_run_summary(campaign_id, result, report_path, Path(settings.db_path))
    except typer.Exit:
        raise
    except Exception:
        exit_code = 1
        update_campaign_status(campaign_id, "failed")
        raise
    finally:
        end_run(run_id, exit_code)
        conn.close()
        finish()


@app.command()
def approve(
    campaign_id: str = typer.Argument(..., help="Campaign waiting for approval"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve without interactive prompt"),
    include_guessed: bool = typer.Option(
        False,
        "--include-guessed",
        help="When approving emails, also approve guessed addresses",
    ),
    chaos: str = typer.Option("", help="Comma-separated chaos flags for the resumed run"),
    decision_id: int | None = typer.Option(
        None,
        "--decision-id",
        help="Non-interactive: resume from gate_decisions row id (API)",
    ),
) -> None:
    """Approve ICP (gate 1) or email drafts (gate 2) and resume with Command(resume=...)."""
    import json
    import time
    from datetime import datetime, timezone
    from pathlib import Path

    from dotenv import load_dotenv
    from langgraph.types import Command

    from app.campaign_runner import begin_run, end_run, interrupt_from_result, interrupt_from_state
    from app.config import clear_settings_cache, get_settings
    from app.graph import build_graph, open_checkpointer
    from app.infra.chaos import ChaosConfigError, set_chaos
    from app.infra.db import connect, init_db
    from app.infra.tracing import finish, init_tracing
    from app.persist import persist_v0_run
    from app.reporter.run_report import write_v0_report

    load_dotenv(override=False)
    clear_settings_cache()
    settings = get_settings()
    if chaos:
        try:
            set_chaos(chaos)
        except ChaosConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
    init_tracing("outbound-approve")
    run_id = begin_run(campaign_id, "resume")
    conn, checkpointer = open_checkpointer()
    started = time.time()
    exit_code = 0
    try:
        app_graph = build_graph(checkpointer)
        config = _run_config(campaign_id)
        snap = app_graph.get_state(config)
        payload = interrupt_from_state(snap)
        if not payload:
            typer.echo("No approval interrupt found for this campaign", err=True)
            exit_code = 1
            raise typer.Exit(code=1)

        if decision_id is not None:
            init_db(settings.db_path)
            db = connect(settings.db_path)
            try:
                row = db.execute(
                    "SELECT * FROM gate_decisions WHERE id = ? AND campaign_id = ?",
                    (decision_id, campaign_id),
                ).fetchone()
                if not row:
                    typer.echo(f"gate_decisions id={decision_id} not found", err=True)
                    exit_code = 1
                    raise typer.Exit(code=1)
                if row["status"] != "pending":
                    typer.echo(f"gate_decisions id={decision_id} already {row['status']}", err=True)
                    exit_code = 1
                    raise typer.Exit(code=1)
                resume_payload = json.loads(row["decision_json"])
                result = app_graph.invoke(Command(resume=resume_payload), config=config)
                db.execute(
                    """
                    UPDATE gate_decisions
                    SET status = 'consumed', consumed_at = ?
                    WHERE id = ?
                    """,
                    (datetime.now(timezone.utc).isoformat(), decision_id),
                )
                db.commit()
            finally:
                db.close()
            typer.echo(f"campaign_id={campaign_id} decision_id={decision_id} resumed")
        elif payload.get("type") == "icp_approval":
            icp = dict(payload.get("icp") or {})
            typer.echo(f"industries={icp.get('industries')}")
            typer.echo(f"countries={icp.get('countries')}")
            typer.echo(f"employee_count_ranges={icp.get('employee_count_ranges')}")
            if not yes:
                answer = typer.prompt("Approve ICP? [y/N]", default="y")
                if str(answer).strip().lower() not in {"y", "yes"}:
                    result = app_graph.invoke(
                        Command(resume={"approved": False}),
                        config=config,
                    )
                    typer.echo("ICP rejected; campaign halted")
                    typer.echo(f"halt_reason={result.get('halt_reason')}")
                    return
            result = app_graph.invoke(
                Command(resume={"approved": True, "icp": icp}),
                config=config,
            )
        elif payload.get("type") == "email_approval":
            items = payload.get("items") or []
            typer.echo(f"drafts_waiting={len(items)}")
            for item in items:
                typer.echo(
                    f"- {item.get('name')} <{item.get('email')}> "
                    f"conf={item.get('email_confidence')} "
                    f"subject={(item.get('draft') or {}).get('subject')}"
                )
            if not yes:
                answer = typer.prompt("Approve all drafts? [y/N]", default="y")
                if str(answer).strip().lower() not in {"y", "yes"}:
                    result = app_graph.invoke(
                        Command(resume={"approve_all": False, "approvals": {}}),
                        config=config,
                    )
                    persist_v0_run(result)
                    typer.echo("All drafts rejected")
                    return
            result = app_graph.invoke(
                Command(
                    resume={
                        "approve_all": True,
                        "actor": "cli",
                        "include_guessed": include_guessed,
                    }
                ),
                config=config,
            )
        else:
            typer.echo(f"Unknown interrupt type: {payload.get('type')}", err=True)
            exit_code = 1
            raise typer.Exit(code=1)

        payload2 = interrupt_from_result(result)
        if payload2 and payload2.get("type") == "icp_approval":
            from app.campaign_runner import update_campaign_status

            update_campaign_status(campaign_id, "waiting_icp")
            typer.echo(f"Still awaiting approval: {payload2.get('type')}")
            return
        if payload2 and payload2.get("type") == "email_approval":
            from app.campaign_runner import update_campaign_status

            update_campaign_status(campaign_id, "waiting_approval")
            persist_v0_run(result)
            typer.echo(f"Still awaiting approval: {payload2.get('type')}")
            return
        persist_v0_run(result)
        halt = result.get("halt_reason")
        from app.campaign_runner import update_campaign_status

        update_campaign_status(campaign_id, "halted" if halt else "completed")
        if decision_id is None:
            report_path = write_v0_report(result, wall_seconds=time.time() - started)
            _print_run_summary(campaign_id, result, report_path, Path(settings.db_path))
            sent = [e for e in (result.get("events") or []) if e.get("type") == "send.step1"]
            scheduled = [e for e in (result.get("events") or []) if e.get("type") == "send.scheduled"]
            typer.echo(f"sent_step1={len(sent)} scheduled_followups={len(scheduled)}")
            typer.echo("Run worker: python cli.py worker --once")
    except typer.Exit:
        raise
    except Exception:
        exit_code = 1
        from app.campaign_runner import update_campaign_status

        update_campaign_status(campaign_id, "failed")
        raise
    finally:
        end_run(run_id, exit_code)
        conn.close()
        finish()


@app.command()
def serve(
    with_worker: bool = typer.Option(False, "--with-worker", help="Also poll scheduled follow-ups"),
    port: int = typer.Option(8000, help="API port"),
) -> None:
    """Serve the JSON API on 127.0.0.1 (UI later on :3000). Keep serve-ui for :8080 gates."""
    import threading

    import uvicorn

    if with_worker:
        from app.scheduler.worker import run_forever

        thread = threading.Thread(
            target=run_forever,
            kwargs={"poll_seconds": 20.0},
            name="followup-worker",
            daemon=True,
        )
        thread.start()
        typer.echo("worker thread started (poll=20s)")
    typer.echo(f"API http://127.0.0.1:{port}/api/health")
    uvicorn.run("app.api.main:app", host="127.0.0.1", port=port, reload=False)


@app.command("serve-ui")
def serve_ui(port: int = typer.Option(8080, help="Local port")) -> None:
    """Serve ICP + email approval UI."""
    import uvicorn

    uvicorn.run("app.ui.app:app", host="127.0.0.1", port=port, reload=False)


@app.command()
def report(
    campaign_id: str = typer.Argument(..., help="Campaign to report"),
    baseline: str = typer.Option("", "--baseline", help="Optional baseline campaign id"),
) -> None:
    """Write a structured run report (markdown + JSON) for a campaign."""
    from app.reporter.run_report import write_report

    path = write_report(campaign_id, baseline_id=baseline or None)
    typer.echo(f"report={path}")


@app.command()
def compare(
    baseline_id: str = typer.Argument(..., help="Baseline campaign id"),
    campaign_id: str = typer.Argument(..., help="Current campaign id"),
) -> None:
    """Write reports/comparison.md for two campaigns."""
    from app.reporter.run_report import write_comparison

    path = write_comparison(baseline_id, campaign_id)
    typer.echo(f"comparison={path}")


@app.command("simulate-reply")
def simulate_reply_cmd(
    lead_id: str = typer.Argument(..., help="Lead that replied"),
    opt_out: bool = typer.Option(False, "--opt-out", help="Record as opt-out instead of reply"),
) -> None:
    """Insert a demo reply so follow-ups stop."""
    from app.scheduler.worker import DemoModeRequired, simulate_reply

    try:
        simulate_reply(lead_id, kind="opt_out" if opt_out else "reply")
    except DemoModeRequired as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"recorded={'opt_out' if opt_out else 'reply'} lead_id={lead_id}")


@app.command()
def worker(
    once: bool = typer.Option(False, "--once", help="Process due jobs once and exit"),
    poll: float = typer.Option(20.0, help="Seconds between polls"),
) -> None:
    """Process scheduled follow-ups (survives restart via SQLite)."""
    from app.scheduler.worker import process_due_jobs, run_forever

    if once:
        results = process_due_jobs()
        typer.echo(f"processed={len(results)}")
        for row in results:
            typer.echo(str(row))
        return
    typer.echo(f"worker polling every {poll}s (Ctrl+C to stop)")
    run_forever(poll_seconds=poll)


@app.command()
def purge(campaign_id: str = typer.Argument(..., help="Campaign data to delete")) -> None:
    """Delete cache, leads, drafts, schedule rows, and checkpoint for one campaign."""
    from app.infra.purge import purge_campaign

    result = purge_campaign(campaign_id)
    typer.echo(f"purged campaign_id={result['campaign_id']} leads={result['leads']}")


@app.command("doctor-crustdata")
def doctor_crustdata(
    sample_search: bool = typer.Option(
        False,
        "--sample-search",
        help="Make one small live company/search (limit 5) and save a fixture",
    ),
    chaos: str = typer.Option("", help="Comma-separated chaos flags"),
) -> None:
    """Print enabled Crustdata endpoints, prices, and balance (08 §6)."""
    from pathlib import Path

    from app.config import clear_settings_cache, get_settings
    from app.infra.budget import ACCOUNT_FILE
    from app.infra.chaos import set_chaos
    from app.infra.tracing import finish, init_tracing
    from app.tools.crustdata import CrustdataClient, save_account_snapshot

    clear_settings_cache()
    settings = get_settings()
    if not settings.crustdata_api_key.strip():
        typer.echo("CRUSTDATA_API_KEY is missing in .env", err=True)
        raise typer.Exit(code=1)

    if chaos:
        try:
            set_chaos(chaos)
        except Exception as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc

    init_tracing("doctor-crustdata")
    client = CrustdataClient()
    try:
        endpoints = client.account_endpoints()
        credits = client.account_credits()
        path = save_account_snapshot(endpoints, credits)
        client.reload_prices()

        endpoint_list = []
        if isinstance(endpoints, dict):
            endpoint_list = endpoints.get("endpoints") or []
        elif isinstance(endpoints, list):
            endpoint_list = endpoints

        wanted = {
            "/company/identify",
            "/company/search",
            "/company/search/autocomplete",
            "/company/enrich",
            "/person/search",
            "/person/search/autocomplete",
            "/person/enrich",
            "/person/professional_network/search/live",
            "/person/contact/enrich",
            "/web/search/live",
            "/web/enrich/live",
            "/account/endpoints",
            "/account/credits",
            "/account/usage/events",
        }

        typer.echo(f"Saved account snapshot -> {path}")
        typer.echo("path\tstatus\trpm\tbase_credits")
        by_path = {}
        for item in endpoint_list:
            if not isinstance(item, dict):
                continue
            p = item.get("path")
            if p in wanted or p in {
                "/company/identify",
                "/company/search",
                "/company/enrich",
                "/person/search",
                "/person/enrich",
                "/web/search/live",
                "/web/enrich/live",
            }:
                by_path[p] = item
                typer.echo(
                    f"{p}\t{item.get('status')}\t{item.get('effective_rate_limit_rpm')}\t{item.get('base_credits')}"
                )

        # credits payload shapes vary; print compactly
        typer.echo(f"credits_payload={credits}")

        balance = None
        if isinstance(credits, dict):
            account = credits.get("account")
            if isinstance(account, dict) and isinstance(account.get("credits"), (int, float)):
                balance = float(account["credits"])
            if balance is None:
                for key in ("remaining_credits", "credits_remaining", "balance", "credits"):
                    if key in credits and isinstance(credits[key], (int, float)):
                        balance = float(credits[key])
                        break

        if balance is not None:
            typer.echo(f"balance={balance}")
            if balance < settings.max_credits:
                typer.echo(
                    f"WARNING: balance {balance} < MAX_CREDITS {settings.max_credits}; "
                    "keep live runs small or lower MAX_CREDITS"
                )

        person_enrich = by_path.get("/person/enrich") or {}
        enabled_fields = person_enrich.get("enabled_fields") or person_enrich.get("fields") or []
        live_people = by_path.get("/person/professional_network/search/live") or {}
        contact_enrich = by_path.get("/person/contact/enrich") or {}

        typer.echo("fallbacks:")
        typer.echo(
            f"  live_people_search={live_people.get('status', 'missing')} "
            f"(only use if enabled)"
        )
        typer.echo(f"  person_contact_enrich={contact_enrich.get('status', 'missing')}")
        typer.echo(
            f"  contact.business_emails_on_person_enrich="
            f"{'yes' if 'contact.business_emails' in str(enabled_fields) else 'check_snapshot'}"
        )
        typer.echo(f"  DATA_MODE={settings.data_mode} MAX_CREDITS={settings.max_credits}")

        if sample_search:
            if settings.data_mode != "live":
                typer.echo("Set DATA_MODE=live in .env for --sample-search", err=True)
                raise typer.Exit(code=1)
            body = {
                "filters": {
                    "op": "and",
                    "conditions": [
                        {"field": "locations.country", "type": "=", "value": "United States"},
                    ],
                },
                "fields": [
                    "crustdata_company_id",
                    "basic_info.name",
                    "basic_info.primary_domain",
                    "basic_info.employee_count_range",
                    "locations.country",
                ],
                "limit": 5,
            }
            result = client.company_search(body, campaign_id="doctor-sample", step="sample_search")
            fixtures = Path("fixtures")
            fixtures.mkdir(exist_ok=True)
            out = fixtures / "company_search_limit5.json"
            out.write_text(__import__("json").dumps(result, indent=2, default=str), encoding="utf-8")
            spent = client.ledger.spent("doctor-sample")
            typer.echo(f"sample_search saved -> {out} ledger_credits={spent}")
            # second call should be cache hit
            client.company_search(body, campaign_id="doctor-sample", step="sample_search_repeat")
            spent2 = client.ledger.spent("doctor-sample")
            typer.echo(f"repeat_search ledger_credits={spent2} (should match if cache hit added 0)")
    finally:
        client.close()
        finish()


@app.command("llm-smoke")
def llm_smoke() -> None:
    """Send one tiny Bedrock call through app/llm.py, then flush neatlogs."""
    from app.infra.tracing import finish, init_tracing
    from app.llm import get_llm

    init_tracing("llm-smoke")
    try:
        model = get_llm("fast")
        result = model.invoke("Reply with the single word ok.")
        text = getattr(result, "content", result)
        typer.echo(text)
    finally:
        finish()


@app.command("gen-key")
def gen_key() -> None:
    """Print a Fernet key for SIGNALSDR_SECRET_KEY (do not commit the value)."""
    from app.mail.crypto import generate_key

    typer.echo(generate_key())


@app.command("parse-companies")
def parse_companies_cmd(
    csv_path: str = typer.Argument(..., help="Path to CSV with company_name, website, description"),
) -> None:
    """Parse a company-list CSV and print ok_count + per-row status (no network)."""
    from pathlib import Path

    from app.infra.company_list import parse_companies_csv

    text = Path(csv_path).read_text(encoding="utf-8")
    parsed = parse_companies_csv(text)
    typer.echo(f"ok_count={parsed['ok_count']}")
    for row in parsed.get("rows") or []:
        typer.echo(
            f"{row.get('status')}\t{row.get('domain') or '-'}\t{row.get('name') or '-'}\t{row.get('reason') or ''}"
        )


@app.command("fix-drafts")
def fix_drafts(
    campaign_id: str = typer.Argument(..., help="Campaign whose drafts may contain ev_ ids"),
) -> None:
    """Strip leaked evidence ids from pending drafts and unsent email rows; re-verify."""
    from dotenv import load_dotenv

    from app.agents.evidence_refs import find_refs, strip_refs
    from app.agents.verifier import verify_draft
    from app.api import state_reader
    from app.config import clear_settings_cache, get_settings
    from app.infra.db import connect, init_db
    from app.models import Contact, DraftClaim, EmailDraft, EvidenceCard

    load_dotenv(override=False)
    clear_settings_cache()
    settings = get_settings()
    init_db(settings.db_path)

    drafts_all = state_reader.drafts(campaign_id)
    contacts = {c["id"]: c for c in state_reader.contacts(campaign_id) if isinstance(c, dict)}
    accounts = state_reader.accounts(campaign_id)
    changed = 0
    for contact_id, seq in list(drafts_all.items()):
        if not isinstance(seq, list):
            continue
        new_seq: list[dict] = []
        for step in seq:
            if not isinstance(step, dict):
                continue
            subj = str(step.get("subject") or "")
            body = str(step.get("body") or "")
            refs = find_refs(f"{subj}\n{body}")
            if refs:
                step = dict(step)
                step["subject"] = strip_refs(subj)
                step["body"] = strip_refs(body)
                claims = [DraftClaim.model_validate(c) for c in (step.get("claims") or []) if isinstance(c, dict)]
                for sentence in body.split(". "):
                    ids = find_refs(sentence)
                    if ids:
                        clean = strip_refs(sentence).strip().rstrip(".")
                        if clean and not any(c.text == clean for c in claims):
                            claims.append(DraftClaim(text=clean, evidence_ids=ids))
                step["claims"] = [c.model_dump(mode="json") for c in claims]
                cited = list(step.get("cited_evidence_ids") or [])
                for rid in refs:
                    if rid not in cited:
                        cited.append(rid)
                step["cited_evidence_ids"] = cited
                changed += 1
            # Deterministic re-verify
            contact_raw = contacts.get(contact_id) or {}
            account = accounts.get(contact_raw.get("company_id") or "") or {}
            evidence = [
                EvidenceCard.model_validate(e)
                for e in (account.get("evidence") or [])
                if isinstance(e, dict)
            ]
            try:
                draft = EmailDraft.model_validate(step)
                contact = Contact.model_validate(
                    {
                        "id": contact_id,
                        "company_id": contact_raw.get("company_id") or "",
                        "name": contact_raw.get("name") or "Contact",
                        "title": contact_raw.get("title") or "",
                        "role_kind": contact_raw.get("role_kind") or "champion",
                        "email": contact_raw.get("email"),
                        "email_source": contact_raw.get("email_source") or "none",
                        "email_confidence": contact_raw.get("email_confidence") or "none",
                        "profile_url": contact_raw.get("profile_url"),
                    }
                )
                result = verify_draft(draft, evidence=evidence, contact=contact, use_llm=False)
                typer.echo(
                    f"contact={contact_id} step={step.get('step')} "
                    f"refs_fixed={bool(refs)} passed={result.passed} issues={result.issues}"
                )
            except Exception as exc:  # noqa: BLE001
                typer.echo(f"contact={contact_id} verify_error={exc}", err=True)
            new_seq.append(step)
        drafts_all[contact_id] = new_seq

    if changed or drafts_all:
        state_reader.update_drafts(campaign_id, drafts_all)

    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            """
            SELECT e.id, e.subject, e.body, e.delivery_status, e.sent_at
            FROM emails e
            JOIN leads l ON l.id = e.lead_id
            WHERE l.campaign_id = ?
            """,
            (campaign_id,),
        ).fetchall()
        email_fixed = 0
        for r in rows:
            if r["sent_at"] or (r["delivery_status"] or "") in {"sent", "drafted", "unknown"}:
                continue
            subj, body = r["subject"] or "", r["body"] or ""
            if find_refs(f"{subj}\n{body}"):
                conn.execute(
                    "UPDATE emails SET subject = ?, body = ? WHERE id = ?",
                    (strip_refs(subj), strip_refs(body), r["id"]),
                )
                email_fixed += 1
        conn.commit()
    finally:
        conn.close()

    typer.echo(f"campaign_id={campaign_id} draft_steps_fixed={changed} email_rows_fixed={email_fixed}")
    leftover = 0
    for seq in drafts_all.values():
        for step in seq or []:
            if isinstance(step, dict) and find_refs(
                f"{step.get('subject') or ''}\n{step.get('body') or ''}"
            ):
                leftover += 1
    if leftover:
        typer.echo(f"warning={leftover} steps still contain ev_ ids", err=True)
        raise typer.Exit(code=1)


mail_app = typer.Typer(help="Mail account controls")
app.add_typer(mail_app, name="mail")


@mail_app.command("pause-all")
def mail_pause_all() -> None:
    """Set settings.sending_paused so no transport sends."""
    from app.config import get_settings
    from app.infra.db import connect, init_db
    from app.mail.policy import get_setting, set_setting

    path = get_settings().db_path
    init_db(path)
    conn = connect(path)
    try:
        set_setting(conn, "sending_paused", True)
        conn.commit()
        typer.echo(f"sending_paused={get_setting(conn, 'sending_paused')}")
    finally:
        conn.close()


@mail_app.command("resume-all")
def mail_resume_all() -> None:
    """Clear settings.sending_paused."""
    from app.config import get_settings
    from app.infra.db import connect, init_db
    from app.mail.policy import get_setting, set_setting

    path = get_settings().db_path
    init_db(path)
    conn = connect(path)
    try:
        set_setting(conn, "sending_paused", False)
        conn.commit()
        typer.echo(f"sending_paused={get_setting(conn, 'sending_paused')}")
    finally:
        conn.close()


if __name__ == "__main__":
    app()
