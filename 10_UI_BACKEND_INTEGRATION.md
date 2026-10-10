# 10 — Wiring the UI to the Agents (backend integration)

The UI in `09_UI_SPEC.md` must drive the **real** system built in Phases 1–7: the same LangGraph graph, the same SQLite DB, the same Crustdata client, the same neatlogs tracing. No mock data, no second implementation of any agent. This file says exactly how.

Read with: `02_ARCHITECTURE.md` (DB, graph, state), `03_AGENTS_SPEC.md` (agents, events), `05_RELIABILITY_SECURITY.md` (recovery, chaos, policy), `08_CRUSTDATA_API.md` (Crustdata).

## 0. Golden rules for this layer

1. **The API never runs agents in its own process.** It spawns the existing CLI as a child process for every graph run. Reason: `--chaos kill_after=…` calls `os._exit(1)`, and a crash must not take down the API. It also means UI runs are traced exactly like CLI runs.
2. **SQLite is the bus.** The run process writes events, stages, leads and emails; the API reads them. The API writes decisions (ICP approval, email approval, pause); the run process reads them.
3. **One function per side effect.** Reuse the existing modules: `app/tools/mailer.py` for anything that sends, `app/infra/audit.py` for audit rows, `app/infra/budget.py` for estimates and ledger, `app/reporter/run_report.py` for metrics. If the API needs logic that lives in a CLI command, move it into a function and call it from both.
4. **Local only, no login.** Bind to `127.0.0.1`. CORS allows only `http://localhost:3000`. README says: never deploy this publicly.
5. **No secrets in responses.** Never return API keys, `.env` values or raw Crustdata payloads. Prospect emails are masked in list endpoints (`r***@finly.io`); the full address appears only in lead detail.
6. **Every endpoint has a pydantic response model**, so `openapi.json` is complete and the TypeScript types generate cleanly.

## 1. Step U0 — audit what exists (do this first, write no feature code)

Cursor prompt:

> Read docs/02, 03, 05, 09 and 10. Then read the actual code: app/graph.py, app/state.py, app/agents/*, app/infra/db.py, app/infra/audit.py, app/infra/budget.py, app/tools/mailer.py, app/scheduler/worker.py, app/reporter/run_report.py, app/ui/*, cli.py. Write docs/ui/BACKEND_MAP.md with:
> 1. A table mapping every endpoint in docs/10 §5 to the existing function(s) it will call, or "MISSING" with what must be added.
> 2. How events are recorded today (state only, DB, logs?) and the exact place each agent appends them.
> 3. How the ICP gate is implemented (interrupt name, resume payload shape) and how email approval works today (graph interrupt or DB status only).
> 4. How `cli.py run`, `resume`, `approve`, `simulate-reply`, `purge` work today and what arguments they take.
> 5. Whether neatlogs exposes a trace id/URL we can store (check the installed SDK and docs.neatlogs.com; do not invent functions).
> 6. The installed LangGraph version and how to read pending interrupts with it (`graph.get_state(config)`; check `.tasks[*].interrupts` vs `.interrupts`).
> Do not change code in this step.

Read `BACKEND_MAP.md` yourself before U1. Everything below adapts to what it finds; where it conflicts with existing working code, keep the working code and adjust the API.

## 2. Database additions (migration in `app/infra/db.py`)

Add only what is missing (check `BACKEND_MAP.md`). Enable WAL mode (`PRAGMA journal_mode=WAL`) and a 5 s busy timeout, because the API and run processes read and write concurrently.

| Table | Columns | Written by | Purpose |
| --- | --- | --- | --- |
| `events` | `id INTEGER PK AUTOINCREMENT`, `campaign_id`, `ts`, `type` (e.g. `recovery.rate_limit`), `agent`, `level` (info/warning/danger/neutral/success), `message`, `credits_delta REAL`, `lead_id NULL`, `trace_ref NULL`, `data_json` | run process | Activity timeline + SSE |
| `campaign_stages` | `campaign_id`, `stage` (plan, product, buyers, icp, accounts, emails, verify, approval, send), `status` (pending/running/waiting/done/skipped/failed), `count_label`, `updated_at`; PK (campaign_id, stage) | run process | Stage stepper |
| `runs` | `id PK`, `campaign_id`, `kind` (start/resume), `pid`, `started_at`, `heartbeat_at`, `ended_at NULL`, `exit_code NULL`, `trace_url NULL` | API + run process | Process tracking, crash detection, trace links |
| `gate_decisions` | `id PK`, `campaign_id`, `gate` (icp/send), `decision_json`, `status` (pending/consumed), `created_at`, `consumed_at` | API → run process | Human gate answers |
| `campaigns` (add columns) | `status` (queued/running/waiting/paused/crashed/completed/failed/halted), `current_stage`, `pause_requested INT DEFAULT 0`, `options_json` (n, mode, cap, chaos, kill_after), `seller_name`, `seller_domain`, `baseline_campaign_id NULL` | API + run process | List + run view |
| `settings` | `key PK`, `value_json` | API | Defaults, caps, from-address |

Two helpers in `app/infra/events.py`, used by every agent:

```python
def record_event(campaign_id: str, type: str, agent: str, message: str, *,
                 level: str = "info", credits_delta: float = 0.0,
                 lead_id: str | None = None, data: dict | None = None) -> None: ...

def set_stage(campaign_id: str, stage: str, status: str, count_label: str | None = None) -> None: ...
```

- Wherever an agent already appends to `state["events"]`, also call `record_event` with the same type and message (the message must read as a sentence a founder understands, see the examples in `09` §5.3). Keep the state append; do not remove existing behavior.
- `level` follows the event family: `replan.*` info, `fallback.*` neutral, `recovery.*` warning, `verify.redraft` warning, `verify.drop` danger, `policy.*`/`security.*` neutral, `halt.*` danger, `done.*` success.
- Each node calls `set_stage(..., "running")` on entry and `"done"` with a count label on exit (e.g. `"60 → 24 kept"`); the gate nodes set `"waiting"`.
- Messages must never contain full prospect emails or secrets (use `app/infra/redact.py`).

## 3. Run manager (`app/api/runs.py`)

```python
def start_campaign(campaign_id: str) -> int:   # returns pid
    # spawn: [sys.executable, "cli.py", "run-campaign", campaign_id]
def resume_campaign(campaign_id: str) -> int:
    # spawn: [sys.executable, "cli.py", "resume", campaign_id]
def is_alive(campaign_id: str) -> bool        # latest runs row: ended_at is NULL and heartbeat < 15 s old
```

- Spawn with `subprocess.Popen`, `start_new_session=True`, same env as the API (so `AWS_PROFILE`, keys, `DATA_MODE` pass through), stdout/stderr to `logs/<campaign_id>-<run_id>.log` (gitignored).
- Insert the `runs` row before spawning; the child updates `heartbeat_at` every 5 s from a daemon thread and writes `ended_at` + `exit_code` in a `finally` / `atexit`.
- Refuse to start a second process for a campaign that is alive (HTTP 409 "This campaign is already running").
- **Crash detection:** a run with no `ended_at` and a heartbeat older than 15 s is `crashed`. The API sets `campaigns.status = "crashed"` on read and the UI shows a **Resume** button. This is the kill + resume demo, visible in the UI: start with `kill_after=account_researcher`, watch it crash, click Resume, it continues from the checkpoint without re-buying data.

### CLI changes (keep existing commands working)

| Command | Behavior |
| --- | --- |
| `cli.py run-campaign <id>` (new) | Load the `campaigns` row created by the API (options from `options_json`), init tracing, invoke the graph with `thread_id = id` and the neatlogs callbacks, write run status, flush tracing. Same code path as `cli.py run` — refactor `run` to create the row and then call the same function. |
| `cli.py resume <id>` (extend) | Read the graph state. If it is waiting at a gate and a `pending` row exists in `gate_decisions` for that gate → `graph.invoke(Command(resume=decision), config)` and mark the decision consumed. If it is waiting with no decision → exit 0 and leave status `waiting`. If there is no pending interrupt (crash or pause) → `graph.invoke(None, config)` to continue from the last checkpoint. |
| `cli.py serve` (new) | `uvicorn app.api.main:app --host 127.0.0.1 --port 8000`; `--with-worker` also starts `scheduler/worker.py` loop in a thread. |

### Pause

`POST /campaigns/{id}/pause` sets `pause_requested = 1`. The planner checks it between stages; if set it records `halt.paused` ("Paused by you. Resume to continue from {stage}."), sets status `paused`, clears the flag and ends the run. Resume → `resume_campaign`. Cooperative only; never kill a process to pause.

### Gates

- **ICP gate (gate 1)** — read the pending interrupt value via `graph.get_state(config)` (method per `BACKEND_MAP.md`) or from the ICP the buyer finder stored in DB. `POST /campaigns/{id}/icp` inserts a `gate_decisions` row (`{action: "approve"|"reject", edits: {...}}`, validated against `ICPProposal`) and calls `resume_campaign`. Reject → the graph ends with `halt.rejected_by_user`.
- **Email approval (gate 2)** — follow whatever Phase 7 built (see `BACKEND_MAP.md`):
  - If approval is DB status only: the email endpoints update `emails.status`, write `audit`, and the sender/worker picks up approved emails as it does today.
  - If it is a graph interrupt: the email endpoints update rows; when the user clicks **Send approved** (shown when no email is still `awaiting_approval` for the campaign, or explicitly) the API inserts a `send` decision and resumes.
- Guessed emails: the API rejects approve without `confirm_guessed: true` (HTTP 422, message "Guessed address: confirm you've checked it"). Bulk approve skips guessed emails and returns them in `skipped_guessed`.

## 4. Live updates (SSE)

`GET /campaigns/{id}/stream` — `text/event-stream`, implemented with `StreamingResponse` (or `sse-starlette`):

- On connect, send events with `id > Last-Event-ID` header (or `?after=` query), then poll the `events` table every 1 s.
- Emit `event: activity` (`data` = the Event model), `event: stage` when any `campaign_stages.updated_at` changed (`data` = full stage list), `event: status` when campaign status changed (`data` = `{status, current_stage}`).
- Send `: ping` every 15 s. Close when the campaign is `completed`/`failed`/`halted` and no process is alive.
- Frontend: `EventSource` pointed **directly at `http://127.0.0.1:8000`** (dev proxies buffer SSE). On `stage`/`status`, invalidate the matching TanStack Query keys. On error, fall back to polling `/events?after=` every 3 s and show a quiet "Live updates paused, retrying" note in the timeline header.

## 5. Endpoint → code map

Base `http://127.0.0.1:8000/api`. Router modules in `app/api/routes/`. "Uses" names the existing code to call (adjust names to `BACKEND_MAP.md`).

| Method · Path | Uses | Notes |
| --- | --- | --- |
| GET `/system/status` | `config/crustdata_account.json` (from `doctor-crustdata`), `tools.crustdata.account_credits` (cache 60 s; free), settings, `app.llm` model ids, neatlogs init check | If the account file is missing: `crustdata.status = "unknown"` + hint "Run python cli.py doctor-crustdata" |
| POST `/estimate` | `infra.budget` estimator (prices from account file) | `{n, mode}` → `{total, by_step[]}`; replay → total 0 |
| GET `/campaigns` | `campaigns`, `campaign_stages`, ledger sums, lead counts | Sorted newest first |
| POST `/campaigns` | insert `campaigns` (status `queued`, `options_json`) → `runs.start_campaign` | Validate URL; `n` 5–50; `cap` ≥ estimate or 422 with the estimate; chaos flags must be in the allowed list |
| GET `/campaigns/{id}` | campaign row, stages, budget by step, recoveries count by event type, `runs` (trace urls), run facts | Includes `is_alive`, `can_resume` |
| GET `/campaigns/{id}/events?after=&type=` | `events` | Paged, newest first, limit 200 |
| GET `/campaigns/{id}/stream` | §4 | |
| GET `/campaigns/{id}/icp` | pending interrupt value or stored ICP + customer evidence cards | 404 if no ICP yet |
| POST `/campaigns/{id}/icp` | §3 Gates | |
| POST `/campaigns/{id}/pause` · `/resume` | §3 | Resume also clears `crashed` |
| GET `/campaigns/{id}/companies` | companies with fit score, status, drop reason | Companies tab |
| GET `/campaigns/{id}/seller` | `SellerBrief` | Seller brief tab |
| GET `/campaigns/{id}/leads?status=&confidence=&verifier=&q=` | leads ⨝ contacts ⨝ companies ⨝ emails ⨝ verifier | Masked email |
| GET `/leads/{id}` | contact, account brief, why-now, 3 email drafts, verifier result + redraft history, evidence cards, audit rows, contact fallback step | Full email here |
| POST `/emails/{id}` | approve/reject/edit → existing approval functions + `audit` | Edit re-runs the deterministic verifier checks (code checks only, no LLM) and returns the new result; if they fail, status stays `awaiting_approval` with issues shown |
| POST `/emails/bulk` | same per id | `{done[], skipped_guessed[], failed[]}` |
| GET `/approvals` | leads `awaiting_approval` across campaigns | |
| GET `/outbox` | `emails` sent + `scheduled_jobs` + `replies` | Status strings exactly as `09` §5.6 |
| POST `/leads/{id}/simulate-reply` | same function as `cli.py simulate-reply` | Only when `DEMO_MODE=true`, else 403 |
| POST `/emails/{id}/cancel-followups` | cancel `scheduled_jobs` rows | audit row |
| GET `/reports/{id}?baseline=` | `reporter.run_report` functions + Crustdata reconciliation | `comparison[]` rows: metric, baseline, current, change, better(bool) |
| POST `/reports/{id}/export` | writes `reports/<id>.md` via reporter | returns path |
| GET/PUT `/settings` | `settings` table | DEMO lock is read-only from env |
| GET/POST/DELETE `/suppression` | `suppression` table | Validate email or domain |
| DELETE `/campaigns/{id}` | same function as `cli.py purge` | Body `{confirm_id}` must equal id; refuse while alive |
| GET `/health` | — | `{ok: true}` |

## 6. Response models (`app/api/schemas.py`)

Define these (extend as needed, keep names stable for the generated types):

```python
class StageOut(BaseModel):
    stage: Literal["plan","product","buyers","icp","accounts","emails","verify","approval","send"]
    status: Literal["pending","running","waiting","done","skipped","failed"]
    count_label: str | None

class BudgetOut(BaseModel):
    cap: float; spent: float; estimated_total: float | None
    by_step: list[dict]          # [{step, credits}]
    cache_hit_rate: float; reconciled: bool | None

class CampaignSummary(BaseModel):
    id: str; seller_name: str; seller_domain: str
    status: str; current_stage: str | None
    stages: list[StageOut]
    leads_found: int; leads_target: int
    credits_spent: float; credit_cap: float
    mode: Literal["replay","live"]; started_at: datetime; trace_url: str | None

class CampaignDetail(CampaignSummary):
    budget: BudgetOut
    recoveries: dict[str, int]   # event type family -> count
    run_facts: dict              # n, models, duration_s, demo_mode, chaos
    is_alive: bool; can_resume: bool
    links: dict                  # neatlogs, mailpit, entire (optional)

class EventOut(BaseModel):
    id: int; ts: datetime; type: str; agent: str
    level: Literal["info","warning","danger","neutral","success"]
    message: str; credits_delta: float; lead_id: str | None; trace_ref: str | None

class LeadRow(BaseModel):
    lead_id: str; company_name: str; company_domain: str
    contact_name: str | None; contact_title: str | None
    role_kind: str | None; email_masked: str | None
    email_confidence: Literal["verified","likely","guessed","none"]
    fit: int                     # 0..100
    verifier: Literal["passed","redrafted","downgraded","dropped","pending"]
    redraft_count: int; status: str; updated_at: datetime

class LeadDetail(BaseModel):
    lead: LeadRow; email_full: str | None; found_via: str
    account_story: str; why_now: list[dict]      # [{text, date, evidence_ids}]
    emails: list[dict]           # [{id, step, subject, body, cited_evidence_ids, status, send_timing}]
    verifier: dict               # checklist + history
    evidence: list[EvidenceCard] # from app.models
    audit: list[dict]
```

Citations: bodies keep evidence ids as `[ev_xxx]` markers (whatever the writer emits today). The API returns the ids; the frontend maps each to a numbered chip `[1]`, `[2]` in order of first appearance. Do not rewrite stored email text.

## 7. neatlogs and the UI

- Runs started from the UI go through `cli.py run-campaign`, so tracing is identical to the CLI. The API process itself makes no LLM calls and does not need tracing.
- Trace links: if `BACKEND_MAP.md` found a supported way to get the trace id/URL from the SDK, store it in `runs.trace_url`. Otherwise store `NEATLOGS_TRACES_URL` (env, your project's Traces page URL) and show "Open traces (filter by campaign {id})". Make sure campaign id is in the run metadata so the filter works. Never invent SDK calls.
- The run reporter's neatlogs readback stays in the reporter; the API only calls the reporter.

## 8. Frontend connection

- `web/.env.local`: `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000/api`, `NEXT_PUBLIC_MAILPIT_URL=http://localhost:8025`.
- `web/lib/api.ts`: one `fetch` wrapper that sets JSON headers, parses the error envelope `{detail}` into a typed `ApiError(status, message)`, and never retries POSTs. TanStack Query hooks per resource in `web/lib/queries.ts` (`useCampaigns`, `useCampaign(id)`, `useLeads(id, filters)`, `useLead(id)`, `useApprove()` …) with polling only where SSE doesn't cover (outbox: 5 s; system status: 30 s).
- Types: `npx openapi-typescript http://127.0.0.1:8000/openapi.json -o web/lib/api-types.ts`. Add `npm run gen:api`. Regenerate after any schema change; never hand-write a type that exists in the schema.
- Optimistic updates for approve/reject in the leads table (roll back on error with an inline row error).
- Error copy is in `09` §6; map `ApiError` status: network → backend-down banner, 402 → out-of-credits banner, 409 → "already running", 422 → field errors.

## 9. Dev workflow

`scripts/dev.sh` (or Makefile) starts, in order: check Mailpit at :8025 (print the docker command if down) → `python cli.py serve --with-worker` → `cd web && npm run dev`. README "Run the UI" section lists the three URLs: UI :3000, API docs :8000/docs, Mailpit :8025.

## 10. Tests (keep them small, run them every step)

- `tests/api/test_campaigns.py`: create campaign with `runs.start_campaign` monkeypatched (no real spawn) → row is `queued` with options; 409 when alive.
- `tests/api/test_gates.py`: ICP approve inserts a pending decision and calls resume; guessed email approve without confirm → 422; bulk skips guessed.
- `tests/api/test_stream.py`: insert 3 events → stream yields them in order, resumes after `Last-Event-ID`.
- `tests/test_events.py`: `record_event` redacts emails in messages.
- One manual end-to-end check per step, written into `hackathon.md`.

## 11. Acceptance for the whole integration (do before recording the demo)

1. Start a **replay** campaign from the UI with N=10. Stages advance live; activity rows appear within ~1 s; the run is in neatlogs.
2. ICP gate appears inline; edit one chip; approve; the run continues and the edit is visible in the next stage's search (event message).
3. Start a run with chaos `crust_429,empty_people,llm_bad_json`: recovery rows show in amber with sensible messages.
4. Start a run with `kill_after=account_researcher`: status turns **Crashed** within 15 s; **Resume** continues; budget shows cache hits, not new spend.
5. Approve 3 emails (one guessed with confirm); Mailpit receives them; outbox shows scheduled follow-ups; simulate reply cancels one lead's follow-ups.
6. Reports page shows v0 vs v1 comparison with real numbers and reconciliation.
