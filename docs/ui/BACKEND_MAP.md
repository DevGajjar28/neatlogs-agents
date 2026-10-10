# BACKEND_MAP — U0 audit (as of Phases 1–7)

Audit of existing code against `10_UI_BACKEND_INTEGRATION.md` §1 / §5.
**No feature code was changed in this step.** Where docs and code conflict, keep working code and adapt the API in later steps (per `10` §1 closing note).

Installed versions checked in `.venv`: **langgraph 1.2.14**, **neatlogs 1.4.26**.

---

## 1. Endpoint → existing function(s) or MISSING

Base planned: `http://127.0.0.1:8000/api` (`app/api/*` does **not** exist today).
Today’s human-gate UI is Jinja FastAPI `app/ui/app.py` on **`:8080`** via `cli.py serve-ui` — not the §5 API.

| Method · Path | Existing code to call | Gap |
| --- | --- | --- |
| GET `/system/status` | `config/crustdata_account.json` via `app.infra.budget.ACCOUNT_FILE` / `load_account_prices`; live credits via `CrustdataClient.account_credits()` (`app/tools/crustdata.py`); `app.config.get_settings()`; LLM ids in `app.llm` / settings; neatlogs readiness = whether `NEATLOGS_API_KEY` is set + `init_tracing` can run | **MISSING** route + response model. No cached “status” helper. |
| POST `/estimate` | Per-endpoint: `app.infra.budget.estimate(endpoint, body)`. Campaign-level ballpark: `app.agents.planner.estimate_credits(n)` (not in `budget.py`) | **MISSING** campaign-level estimator that returns `{total, by_step[]}` from account prices. Replay → 0 must be added. |
| GET `/campaigns` | SQLite `campaigns` (`app/infra/db.py`); ledger via `BudgetLedger.spent`; lead counts via `leads` | **MISSING** list API. Rows today lack `seller_name`, `current_stage`, `options_json`, etc. Stages table missing. |
| POST `/campaigns` | Partial: CLI `cli.py run` builds `initial_state` + `build_graph().invoke`. Persist via `persist_v0_run` / sender `_ensure_lead` | **MISSING** `run-campaign`, `app/api/runs.start_campaign`, insert-then-spawn flow, `options_json`, chaos/kill_after options persistence. |
| GET `/campaigns/{id}` | Campaign row + `BudgetLedger` + LangGraph `get_state` for plan/budget/events | **MISSING** detail assembler (`is_alive`, `can_resume`, stages, recoveries, trace urls). |
| GET `/campaigns/{id}/events` | Events live only in **checkpoint state** `state["events"]` (and report JSON dump) | **MISSING** `events` table + `record_event`. |
| GET `/campaigns/{id}/stream` | — | **MISSING** SSE entirely. |
| GET `/campaigns/{id}/icp` | `app/ui/app.py` `icp_page` reads interrupt / state ICP via `graph.get_state` + `_interrupt_payload` | **MISSING** JSON API. Logic pattern exists in UI. ICP not stored as its own DB table (only in graph state / interrupt). |
| POST `/campaigns/{id}/icp` | Resume patterns: `cli.py approve`, UI `icp_approve` → `Command(resume={"approved": bool, "icp": {...}})` | **MISSING** `gate_decisions` + spawn `resume`. Today resume is **in-process** in CLI/UI, not via decision row. |
| POST `/campaigns/{id}/pause` · `/resume` | Resume (non-gate): `cli.py resume` → `graph.invoke(None, config)`. Pause: **none** | **MISSING** `pause_requested`, planner `halt.paused`, API pause/resume run manager. |
| GET `/campaigns/{id}/companies` | Companies only in **graph state** `state["companies"]` (`Company` model); not a SQLite table | **MISSING** read path (must load checkpoint or persist companies). |
| GET `/campaigns/{id}/seller` | Seller only in **graph state** `state["seller"]` (`SellerBrief`) | **MISSING** read path (checkpoint). |
| GET `/campaigns/{id}/leads` | SQLite `leads` + `emails`; contact/company fields mostly in graph state / lead ids from `mailer.lead_id_for` | **MISSING** join/filter API; masking helper. `app/infra/redact.py` is an empty stub. |
| GET `/leads/{id}` | Partial DB (`leads`, `emails`, `audit`); account brief / evidence / verifier / drafts rich data in graph state | **MISSING** detail assembler; redraft history not a table. |
| POST `/emails/{id}` | Gate is **graph interrupt**, not per-email DB approve. Approvals today: CLI `approve --yes` / UI bulk `emails_approve` with `approve_all` | **MISSING** per-email approve/reject/edit API + re-run deterministic verifier-only checks. `approval_gate` supports per-`contact_id` `{approved, subject, body, allow_guessed}` in resume payload. |
| POST `/emails/bulk` | Same as above (CLI/UI approve-all) | **MISSING** bulk API with `skipped_guessed`. |
| GET `/approvals` | Interrupt queue in graph state; UI lists items from interrupt payload | **MISSING** cross-campaign DB query of `awaiting_approval` (leads status not set that way today). |
| GET `/outbox` | `emails`, `scheduled_jobs`, `replies` | **MISSING** API; tables exist. |
| POST `/leads/{id}/simulate-reply` | `app.scheduler.worker.simulate_reply(lead_id, kind=...)` used by `cli.py simulate-reply` | **MISSING** API wrapper. Function does **not** check `DEMO_MODE` today (docs want 403 when false). |
| POST `/emails/{id}/cancel-followups` | Worker `_cancel_lead_jobs` (private); cancels `scheduled_jobs` to `cancelled` | **MISSING** public cancel-by-email-id + audit. |
| GET `/reports/{id}` | `app.reporter.run_report.write_v0_report(state, wall_seconds=...)` only | **MISSING** comparison/`baseline` API; reporter is markdown-from-state, not structured metrics API. |
| POST `/reports/{id}/export` | Same `write_v0_report` → `reports/<…>.md` | **MISSING** HTTP wrapper; CLI `report` command is still a stub (`_pending`). |
| GET/PUT `/settings` | `app.config.get_settings()` (env / pydantic); no `settings` table | **MISSING** table + routes. |
| GET/POST/DELETE `/suppression` | SQLite `suppression`; enforced in `app.tools.mailer._check_suppression` | **MISSING** CRUD API (table exists). |
| DELETE `/campaigns/{id}` | Inline SQL in `cli.py purge` (not a shared function) | **MISSING** extract shared `purge_campaign(id)` + API `{confirm_id}` + refuse-while-alive. |
| GET `/health` | — | **MISSING** trivial route. |

### Related scaffolding (not §5 but required by §2–3)

| Piece | Status |
| --- | --- |
| `app/api/main.py`, `routes/*`, `schemas.py`, `runs.py` | **MISSING** |
| Tables `events`, `campaign_stages`, `runs`, `gate_decisions`, `settings` | **MISSING** |
| Campaign columns (`current_stage`, `pause_requested`, `options_json`, `seller_*`, …) | **MISSING** (today: `id`, `created_at`, `input_json`, `status`, `trace_ids`) |
| `record_event` / `set_stage` | **MISSING** |
| `cli.py run-campaign`, `cli.py serve` | **MISSING** (`serve-ui` exists on 8080) |
| WAL + busy timeout on app DB | **MISSING** (`connect` only sets `foreign_keys`) |
| Chaos `kill_after=<node>` → `os._exit(1)` | **MISSING** (comment only in `chaos.py`; flags parsed but never acted on for kill) |

---

## 2. How events are recorded today

**State only.** Agents append dicts to `state["events"]` (a plain `list` on `CampaignState`). Nothing writes an `events` table. No `record_event` helper. Events are:

- Carried in the LangGraph checkpoint (SqliteSaver on the same DB file as app tables).
- Echoed into markdown by `write_v0_report` (truncated JSON of `events[:40]`).
- Not streamed, not queryable by SQL, not leveled (`level` / founder-facing `message` fields absent).

`app/infra/audit.py` `write_audit` is separate (approve/edit/reject rows in `audit`), not the activity timeline.

### Where each agent appends

| Module / node | Event `type` values (non-exhaustive of payload keys) |
| --- | --- |
| `planner.planner_node` | `plan.reduce_n`, `plan.start`, `halt.budget`, `halt.budget_exhausted`, `replan.widen_icp`, `plan.search_thin`, `plan.replace_no_contact` |
| `product_researcher_node` | `security.injection_quarantined`, `error`, `product.customers_identified`, `product.no_customers` |
| `buyer_propose_icp_node` | `buyer.narrow_icp`, `buyer.icp_proposed` |
| `icp_gate_node` | interrupt payload `type=icp_approval` (not an events append); then `icp.rejected` / `icp.approved` |
| `buyer_search_node` | `buyer.search`, `buyer.kept` |
| `account_enrich` / `account_company` (`account_researcher.py`) | `account.enriched`, `chaos.empty_people`, `account.person_enrich_batch`, `policy.redacted`, `account.no_contact`, `fallback.contact_step_{1,2,3,4}`, `fallback.skipped_not_enabled`, `recovery.explain_retry`, `account.news_web_fallback`, `account.mx_fail`, `account.email_guessed` |
| `email_writer_node` | `email.drafted` |
| `verifier_node` | `verify.pass`, `verify.reject`, `verify.redraft`, `verify.downgrade`, `verify.drop`, `verify.guessed_email_warning` |
| `approval_gate_node` | `approval.empty_queue`, `approval.approved`, `approval.rejected` (+ interrupt `type=email_approval`) |
| `sender_node` | `send.step1`, `send.denied`, `recovery.send_retry`, `send.scheduled` |

U1 must keep these appends and **also** call `record_event` (per `10` §2).

---

## 3. Human gates (ICP + email)

### Gate 1 — ICP (`icp_gate` node)

- **Mechanism:** LangGraph `interrupt(payload)` in `app/agents/buyer_finder.py` `icp_gate_node`.
- **Interrupt value shape:**
  ```json
  {
    "type": "icp_approval",
    "campaign_id": "<id>",
    "icp": { /* ICPProposal dump */ },
    "roles": [...],
    "evidence": [...],
    "message": "Approve or edit the ICP before paid company search."
  }
  ```
- **Resume payload** (`Command(resume=...)`):
  - Approve: `{"approved": true, "icp": {…optional edits…}}`
  - Reject: `{"approved": false}` → sets `halt_reason="icp_rejected"`, event `icp.rejected` (docs’ `halt.rejected_by_user` string is **not** used).
- **Callers today:** `cli.py approve [--yes]`, UI `POST /campaigns/{id}/icp/approve` (form fields for industries/countries/ranges). Both invoke the graph **in the same process**; no `gate_decisions` table.

### Gate 2 — Email approval (`approval_gate` node)

- **Mechanism:** Also a **graph interrupt** (not DB-status-only).
- **Interrupt value shape:**
  ```json
  {
    "type": "email_approval",
    "campaign_id": "<id>",
    "items": [
      {
        "contact_id", "lead_id", "name", "title", "email", "email_confidence",
        "company_id", "verifier", "draft", "sequence_steps", "cited_evidence_ids"
      }
    ],
    "message": "Approve, edit, or reject verified drafts before send."
  }
  ```
- **Resume payload:**
  - Bulk: `{"approve_all": true, "actor": "cli"|"ui"}` (sets `allow_guessed: true` for every item).
  - Reject all: `{"approve_all": false, "approvals": {}}`.
  - Per contact: `approvals[contact_id] = {approved, allow_guessed?, subject?, body?}`.
- Writes `audit` rows on approve/edit/reject; then edges to `sender`.
- Emails in SQLite get statuses like `draft` / `scheduled` / sent via sender+mailer — approval itself is **not** driven by `emails.status = awaiting_approval`.

---

## 4. CLI surface today

| Command | Arguments | Behavior |
| --- | --- | --- |
| `run` | `--company-name`, `--website`, `--description`, `--n`, `--campaign-id`, `--chaos`, `--narrow-icp` | `set_chaos`, `init_tracing("outbound-v0")`, `initial_state` + `invoke`; stops on ICP/email interrupt; else `persist_v0_run` + `write_v0_report`. |
| `resume` | `campaign_id` | If pending interrupt → exit 1 (“use approve”). Else `invoke(None)`. **Does not** consume `gate_decisions` (table absent). |
| `approve` | `campaign_id`, `--yes/-y` | Reads interrupt via `get_state`; ICP or email resume with `Command`; persist/report. |
| `serve-ui` | `--port` (default 8080) | `uvicorn app.ui.app:app` on `127.0.0.1`. |
| `simulate-reply` | `lead_id`, `--opt-out` | `worker.simulate_reply(..., kind=reply\|opt_out)`. |
| `worker` | `--once`, `--poll` | Process due follow-ups. |
| `purge` | `campaign_id` | Deletes jobs/emails/replies/leads/ledger/campaign row for id (not checkpoints / cache by campaign). |
| `doctor-crustdata` | `--sample-search`, `--chaos` | Account endpoints/credits → `config/crustdata_account.json`. |
| `report` | `campaign_id` | **Stub** (`not implemented yet`). |
| `run-campaign` | — | **Does not exist** (planned). |
| `serve` | — | **Does not exist** (planned API :8000). |

Chaos CSV is accepted on `run` / `doctor-crustdata` (`crust_429`, `crust_5xx`, `crust_403_fields`, plus agent-side flags like `empty_people` / `llm_bad_json` elsewhere). **`kill_after=<node>` is not implemented.**

---

## 5. neatlogs — trace id / URL?

SDK **1.4.26** public surface used by the app: `init`, `langchain_handler`, `flush`, `shutdown` (`app/infra/tracing.py`).

Also present but unused for URL storage: `trace`, `span`, `identify`, `log`, `inject_trace_context`, `extract_trace_context`, `get_delivery_diagnostics` (loss counters only — **not** a dashboard URL).

**No installed helper returns a neatlogs web trace URL or stable trace id for storage.**  
`campaigns.trace_ids` column exists but `persist_v0_run` always writes `[]`.

**UI implication (per `10` §7):** store `NEATLOGS_TRACES_URL` (env) and link “Open traces (filter by campaign {id})”. Campaign id is already in run `metadata` via `_run_config`. Do not invent SDK calls.

---

## 6. LangGraph interrupts — version and how to read them

- **Installed:** `langgraph==1.2.14`.
- **After `invoke` hits an interrupt:** result dict includes `__interrupt__` list of `Interrupt` objects; read `.value` (see `cli._interrupt_from_result`).
- **Pending interrupt on a thread:** `graph.get_state(config)` returns a `StateSnapshot` where:
  - **`snapshot.interrupts`** is a tuple of `Interrupt` (confirmed on 1.2.14).
  - **`snapshot.tasks[*].interrupts`** also holds the same `Interrupt` objects (what `cli._interrupt_from_state` and `app/ui/app.py` `_interrupt_payload` use today).
  - Fallback: `snapshot.values.get("__interrupt__")` (UI helper).
- Resume: `graph.invoke(Command(resume=<decision dict>), config)` with `configurable.thread_id = campaign_id`.
- Prefer for new API code: `snapshot.interrupts[0].value` if present, else walk `tasks[*].interrupts` (keep parity with CLI/UI).

---

## Conflicts: docs (`09`/`10`/planned U1) vs how the code actually works

1. **No `app/api` / `:8000` server** — only Jinja approval UI on `:8080` (`serve-ui`). Planned `cli.py serve` / `run-campaign` absent.
2. **Events are state-only** — no `events` / `campaign_stages` / `runs` / `gate_decisions` / `settings` tables; no WAL/busy timeout; campaigns schema is the old 5-column shape.
3. **Gates are in-process resumes**, not “API writes `gate_decisions` → child `resume` consumes.” CLI `resume` **refuses** when an interrupt is pending (exit 1); only `approve` resumes gates.
4. **Email approval is a graph interrupt**, not DB `awaiting_approval` polling. Docs §3 already allows either; map must treat interrupt + `Command(resume=…)` as source of truth. Per-email REST approve/edit is not built.
5. **Companies + seller live in checkpoint state**, not SQLite — §5 list endpoints cannot be pure SQL today.
6. **`kill_after=<node>` is documented as working (`05`, `10`) but not implemented** — `chaos.py` only comments that the token is kept in the flag set; nothing calls `os._exit`. Crash/resume demo will not work until this exists.
7. **Pause** (`pause_requested`, `halt.paused`) does not exist in planner/DB.
8. **Campaign estimate:** docs say `infra.budget` estimator for `{n, mode}`; code has per-endpoint `budget.estimate` and a separate rough `planner.estimate_credits(n)` — no `{total, by_step[]}` helper.
9. **ICP reject halt name:** code uses `halt_reason="icp_rejected"` / event `icp.rejected`, not `halt.rejected_by_user`.
10. **CLI email approve-all sets `allow_guessed: true` for every draft** — conflicts with planned API rule “guessed requires `confirm_guessed` / bulk skips guessed.”
11. **`simulate_reply` does not enforce `DEMO_MODE`** (API plan wants 403 when false).
12. **`app/infra/redact.py` is empty** — docs assume it for event messages / list masking.
13. **Reporter** is `write_v0_report` markdown only; no baseline comparison API; CLI `report` stubbed.
14. **Purge** is CLI-inline SQL and does not clear LangGraph checkpoint rows or `cache` entries for the campaign.
15. **Persist status:** `persist_v0_run` sets campaign/lead status `"drafted"`; sender updates leads/emails when sending — not the richer status enum assumed by the UI run list.
16. **neatlogs:** no SDK trace URL — use env project Traces URL + campaign id filter (do not invent getters).

These conflicts should drive U1 adjustments: keep working CLI/UI interrupt resume shapes; add DB/API around them; implement `kill_after` before claiming crash demos; prefer checkpoint reads for companies/seller/ICP until persistence is added.
