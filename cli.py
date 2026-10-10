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
    import time
    import uuid
    from pathlib import Path

    from dotenv import load_dotenv

    from app.config import clear_settings_cache, get_settings
    from app.graph import build_graph, initial_state, open_checkpointer
    from app.infra.chaos import set_chaos
    from app.infra.tracing import finish, init_tracing
    from app.persist import persist_v0_run
    from app.reporter.run_report import write_v0_report

    # Load .env defaults first; process env (DATA_MODE=live etc.) wins.
    load_dotenv(override=False)
    clear_settings_cache()
    settings = get_settings()
    if chaos:
        set_chaos(chaos)

    cid = campaign_id.strip() or f"v0-{uuid.uuid4().hex[:10]}"
    init_tracing("outbound-v0")
    typer.echo(f"DATA_MODE={settings.data_mode}")
    conn, checkpointer = open_checkpointer()
    started = time.time()
    try:
        app_graph = build_graph(checkpointer)
        state = initial_state(
            campaign_id=cid,
            company_name=company_name,
            website=website,
            description=description,
            n=n,
            mode=settings.data_mode,
            narrow_icp=narrow_icp,
        )
        result = app_graph.invoke(state, config=_run_config(cid))
        payload = _interrupt_from_result(result)
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

        persist_v0_run(result)
        report_path = write_v0_report(result, wall_seconds=time.time() - started)
        _print_run_summary(cid, result, report_path, Path(settings.db_path))
    finally:
        conn.close()
        finish()


@app.command()
def resume(campaign_id: str = typer.Argument(..., help="Campaign to resume")) -> None:
    """Resume a campaign from the last checkpoint (not for ICP interrupt; use approve)."""
    import time
    from pathlib import Path

    from dotenv import load_dotenv

    from app.config import clear_settings_cache, get_settings
    from app.graph import build_graph, open_checkpointer
    from app.infra.tracing import finish, init_tracing
    from app.persist import persist_v0_run
    from app.reporter.run_report import write_v0_report

    load_dotenv(override=False)
    clear_settings_cache()
    settings = get_settings()
    init_tracing("outbound-resume")
    conn, checkpointer = open_checkpointer()
    started = time.time()
    try:
        app_graph = build_graph(checkpointer)
        config = _run_config(campaign_id)
        snap = app_graph.get_state(config)
        if _interrupt_from_state(snap):
            typer.echo("Campaign is waiting on a human gate. Use: python cli.py approve <id> --yes")
            raise typer.Exit(code=1)
        result = app_graph.invoke(None, config=config)
        payload = _interrupt_from_result(result)
        if payload and payload.get("type") == "icp_approval":
            typer.echo(f"campaign_id={campaign_id}")
            typer.echo("status=awaiting_icp_approval")
            return
        persist_v0_run(result)
        report_path = write_v0_report(result, wall_seconds=time.time() - started)
        _print_run_summary(campaign_id, result, report_path, Path(settings.db_path))
    finally:
        conn.close()
        finish()


@app.command()
def approve(
    campaign_id: str = typer.Argument(..., help="Campaign waiting for approval"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve without interactive prompt"),
) -> None:
    """Approve an ICP (human gate 1) and resume with Command(resume=...)."""
    import time
    from pathlib import Path

    from dotenv import load_dotenv
    from langgraph.types import Command

    from app.config import clear_settings_cache, get_settings
    from app.graph import build_graph, open_checkpointer
    from app.infra.tracing import finish, init_tracing
    from app.persist import persist_v0_run
    from app.reporter.run_report import write_v0_report

    load_dotenv(override=False)
    clear_settings_cache()
    settings = get_settings()
    init_tracing("outbound-approve")
    conn, checkpointer = open_checkpointer()
    started = time.time()
    try:
        app_graph = build_graph(checkpointer)
        config = _run_config(campaign_id)
        snap = app_graph.get_state(config)
        payload = _interrupt_from_state(snap)
        if not payload or payload.get("type") != "icp_approval":
            typer.echo("No ICP approval interrupt found for this campaign", err=True)
            raise typer.Exit(code=1)
        icp = dict(payload.get("icp") or {})
        typer.echo(f"industries={icp.get('industries')}")
        typer.echo(f"countries={icp.get('countries')}")
        typer.echo(f"employee_count_ranges={icp.get('employee_count_ranges')}")
        typer.echo(f"roles={[(r.get('kind'), r.get('title_variants')) for r in (icp.get('roles') or [])]}")
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
        payload2 = _interrupt_from_result(result)
        if payload2 and payload2.get("type") == "icp_approval":
            typer.echo("Still awaiting ICP approval (unexpected)")
            return
        persist_v0_run(result)
        report_path = write_v0_report(result, wall_seconds=time.time() - started)
        _print_run_summary(campaign_id, result, report_path, Path(settings.db_path))
    finally:
        conn.close()
        finish()


@app.command("serve-ui")
def serve_ui(port: int = typer.Option(8080, help="Local port")) -> None:
    """Serve the minimal ICP approval UI."""
    import uvicorn

    uvicorn.run("app.ui.app:app", host="127.0.0.1", port=port, reload=False)


@app.command()
def report(campaign_id: str = typer.Argument(..., help="Campaign to report")) -> None:
    """Write a run report for a campaign."""
    _ = campaign_id
    _pending("report")


@app.command("simulate-reply")
def simulate_reply(lead_id: str = typer.Argument(..., help="Lead that replied")) -> None:
    """Insert a demo reply so follow-ups stop."""
    _ = lead_id
    _pending("simulate-reply")


@app.command()
def purge(campaign_id: str = typer.Argument(..., help="Campaign data to delete")) -> None:
    """Delete cache, leads, drafts, and schedule rows for one campaign."""
    _ = campaign_id
    _pending("purge")


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
        set_chaos(chaos)

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


if __name__ == "__main__":
    app()
