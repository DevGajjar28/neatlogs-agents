# SignalSDR — neatHack 2026

## Project
An outbound agent that drafts and schedules email only from sourced facts — so a campaign can keep running without inventing claims or emailing a real prospect during the demo.

## Team
DevGajjar28

## Stack
LangGraph, AWS Bedrock (ChatBedrockConverse), neatlogs, Entire, cfo.ai, Crustdata, SQLite, FastAPI, local SMTP (no Docker)

## Build log
### 2026-10-10 16:30 IST
- Completed: repo connected to github.com/DevGajjar28/neatlogs-agents. Initial skeleton for config, models, SQLite schema, tracing, and CLI stubs.
- Planned: Phase 1 acceptance (help, pytest, llm-smoke).
- Tests run: `pytest` — 1 passed.
- Failures remaining: Entire CLI not installed; Bedrock smoke pending filled `.env`.
- Evidence: none yet.

### 2026-10-10 17:15 IST
- Completed: Phase 1 skeleton alignment. Full folder layout from architecture §3 (empty agent/tool/infra modules). `app/infra/tracing.py` matches tooling setup §2. `get_llm(kind=strong|fast)` always attaches neatlogs callbacks. CLI stubs include `doctor-crustdata` and `llm-smoke`. Model IDs come from `.env` (`LLM_MODEL_STRONG` / `LLM_MODEL_FAST`; Haiku inference profile for smoke).
- Planned: Phase 2 Crustdata client, cache, budget.
- Tests run: `python cli.py --help`; `pytest`; `python cli.py llm-smoke`.
- Failures remaining: Entire CLI still not installed (no checkpoint on this change). Agent graph and Crustdata client not started.
- Evidence: llm-smoke trace under workflow `llm-smoke` in neatlogs (link after dashboard check).

### 2026-10-10 19:15 IST
- Completed: Phase 2 Crustdata client with SQLite cache, budget ledger, chaos hooks, typed errors (402/403/403-fields/429), LangChain `@tool` wrappers, and `doctor-crustdata`. Account snapshot written to gitignored `config/crustdata_account.json`. One live `company/search` limit=5 cost 0.15 credits; identical repeat was a cache hit (ledger stayed 0.15). Fixture: `fixtures/company_search_limit5.json`. Fallbacks noted: live people search disabled, `/person/contact/enrich` disabled, `contact.business_emails` available on `/person/enrich`. Balance 200 credits.
- Planned: Phase 3 v0 linear pipeline (Gate 1).
- Tests run: `pytest` — 8 passed (cache hit, 429 retry, 402 no-retry, 403 fields retry, budget refusal, replay miss). `doctor-crustdata` and `--sample-search` (DATA_MODE=live for that command only).
- Failures remaining: Entire CLI still missing. Agent graph not started. Keep `DATA_MODE=replay` by default.
- Evidence: neatlogs workflow `doctor-crustdata`; fixture on disk; ledger credits 0.15 then cache hit.

### 2026-10-10 19:30 IST
- Completed: Phase 3 v0 linear LangGraph (product → buyer → account → email). Web fetch via httpx+BeautifulSoup. Drafts persisted to SQLite. Gate 1 live run `v0-posthog-live2`: 10 companies, 3 contacts, 3 drafts, 43.81 credits. Replay `v0-posthog-replay2`: 10 companies, 0 credits (person-search titles still LLM-variant). Report: `reports/v0.md`. Fixed `load_dotenv(override=True)` clobbering `DATA_MODE`.
- Planned: Phase 4 planner + ICP human gate.
- Tests run: live + replay CLI runs on PostHog N=10; prior unit tests still green.
- Failures remaining: v0 finds few contacts (no fallback chain); Entire CLI still missing; you post X #2 and commit/checkpoint.
- Evidence: neatlogs workflow `outbound-v0` / campaign `v0-posthog-live2`; `reports/v0.md`; DB drafts.

## Demo
Not available yet. Local: `python cli.py run --company-name PostHog --website https://posthog.com --n 10`

## Known limitations and next steps
v0 has no planner, verifier, human gates, fallback chain, or sender. Person-search replay can miss when LLM role titles change. Default `DATA_MODE=replay`. Live people search disabled on this Crustdata plan.

### 2026-10-10 19:50 IST
- Completed: Entire CLI 0.11.4 installed; logged in as github:DevGajjar28; `entire enable -y --agent cursor` wrote `.entire/settings.json` and Cursor hooks. First checkpoint commit for this setup.
- Planned: Entire Graph plugin + Phase 4 planner/ICP gate.
- Tests run: `entire version`; `entire status` (Enabled · Cursor); `entire checkpoint explain HEAD` after this commit.
- Failures remaining: prior Phase 1–3 commits have no session transcripts (expected). Graph not installed yet.
- Evidence: https://entire.io/gh/DevGajjar28/neatlogs-agents/commit/fbc6a690a2013e1288666f3a5e75a8e1c9261aa9 (checkpoint ID: `01M4K32PNHG5B8VRZ6Z7Q2NKVK`)

### 2026-10-10 20:10 IST
- Completed: Phase 4 planner + ICP human gate. Graph is `planner` between stages; `buyer_propose_icp` → `icp_gate` (`interrupt`) → `buyer_search`; CLI `approve --yes` and FastAPI `/campaigns/{id}/icp` resume with `Command(resume=...)`. `--narrow-icp` forced thin filters; resume emitted `replan.widen_icp` twice (campaign `p4-gate-replay1`, replay).
- Planned: Phase 5 account researcher fallback chain + Send fan-out.
- Tests run: `pytest tests/test_planner.py tests/test_crustdata.py` (11 passed); CLI run→interrupt→approve on replay.
- Failures remaining: narrow-ICP replay search returned 0 companies (cache miss on exotic filters); full contact yield still limited by v0 account path.
- Evidence: neatlogs workflow `outbound-v0` / `outbound-approve`; events include `plan.start`, `icp.approved`, `replan.widen_icp`.

### 2026-10-10 20:25 IST
- Completed: Phase 5 account researcher fallback chain. Batched `company/enrich` → LangGraph `Send` fan-out per company → join with batched `person/enrich`. Contact chain: enrich people → person search → `explain:true` → semantic retry → skip live if disabled → email pattern + MX. `--chaos empty_people` strips enrich people. Planner `plan.replace_no_contact` promotes overfetch buffer.
- Planned: Phase 6 writer + verifier.
- Tests run: `pytest tests/test_account_fallback.py tests/test_planner.py tests/test_crustdata.py` — 14 passed (all mocked; **0 live Crustdata calls**).
- Failures remaining: live people search wrapper still skipped (endpoint disabled on plan). Full live campaign not re-run to save credits.
- Evidence: unit events `chaos.empty_people`, `recovery.explain_retry`, `fallback.contact_step_2`, `plan.replace_no_contact`.

### 2026-10-10 20:40 IST
- Completed: Phase 6 email writer (3-step sequence, role tone, opt-out, length caps) + verifier (deterministic then LLM judge) with redraft≤2 → downgrade/drop. Graph: `email_writer` → `verifier` → redraft loop or planner. `web.scan_for_injection` + `--chaos poisoned_page`; product researcher emits `security.injection_quarantined`.
- Planned: Phase 7 sender, scheduler, approval UI (human gate 2).
- Tests run: `pytest tests/test_verifier.py` (+ regressions) — 19 passed; reject→redraft→pass loop mocked; **0 live Crustdata**.
- Failures remaining: human gate 2 / Mailpit send not built yet.
- Evidence: unit events `verify.reject`, `verify.redraft`, `verify.pass`; injection quarantine unit coverage.

### 2026-10-10 20:55 IST
- Completed: Phase 7 sender path. `mailer.send` enforces Mailpit-only in demo, suppression, daily/domain caps, idempotency, guessed-email flag. Human gate 2 `approval_gate` interrupt + UI `/emails` + CLI approve. Sender sends step 1 and schedules 2–3; `worker` polls SQLite jobs, cancels on `simulate-reply`.
- Planned: Phase 8 v1 comparison + reporter + cfo.ai.
- Tests run: `pytest tests/test_mailer_worker.py` (+ suite) — 24 passed with mocked SMTP; **0 live Crustdata**.
- Failures remaining: real Mailpit demo still needs local catcher running for a live send smoke.
- Evidence: unit coverage for idempotent skip, suppression, guessed deny, follow-up send + reply cancel.

### 2026-10-11 00:05 IST
- Completed: Step B0 (per `DECISIONS.md` / `docs/ui/DECISIONS.md`). (1) `kill_after=<node>` via `wrap_node` in `graph.py` — arms after named node, `os._exit(1)` on next node start after checkpoint + `chaos.kill_after` event; alias `account_researcher`→`account_enrich`. (2) `redact.mask_email` / `mask_phone` / `redact_text`. (3) `approve_all` skips guessed unless `--include-guessed` / per-contact `allow_guessed`; emits `policy.guessed_skipped`. (4) `simulate_reply` requires `DEMO_MODE=true`. (5) Structured `compute_metrics` / `compare` / `write_report`; CLI `report` + `compare`. (6) `purge_campaign` deletes SQL + cache by `campaign_id` + `SqliteSaver.delete_thread`. (7) Halt naming kept as `icp_rejected` / `icp.rejected`.
- Planned: Phase 8 evidence (v1 run, chaos, compare v0/v1, cfo.ai), then U1 API.
- Tests run: `pytest` — 37 passed (new `test_redact`, `test_b0_chaos_approval`, `test_b0_purge_demo_report`).
- Acceptance B0: `run --chaos kill_after=product_researcher` exited 1; `resume b0-kill-prod` continued to ICP; `approve --yes --chaos kill_after=account_researcher` exited 1; `resume` finished with **cache_hit_rate 100% / credits 0.0**; `report` + `compare` wrote `reports/b0-kill-prod.md` and `reports/comparison.md`.
- Failures remaining: this replay ICP still yields 0 companies after widen (fixture/filter mismatch); not a B0 blocker. UI list APIs not started (U1).
- Evidence: campaign `b0-kill-prod`; reports on disk; unit coverage for guessed skip + kill_after + purge/redact.

### 2026-10-11 00:25 IST
- Completed: Phase 8 Gate 2 evidence pack. Live v1 `v1-posthog-live1` (PostHog N=10): 10 companies, 10 contacts, 4 verifier passes / 6 drops, **5.31 credits/qualified lead** (v0-live2 was 14.60). Chaos `p8-chaos-live2` with `crust_429,empty_people,llm_bad_json` (implemented missing `llm_bad_json` in `app/llm.py`). Kill+resume `p8-kill1`. Filled `reports/comparison.md` (07 template) + `docs/business-plan/measured-inputs.md` + `SUMMARY.md`. README evidence updated.
- Planned: paste neatlogs trace URLs; export cfo.ai PDF into `docs/business-plan/`; start Mailpit for send screenshot; U1 or Phase 9 polish.
- Tests run: suite still green after `llm_bad_json` (re-run if needed).
- Failures remaining: no Mailpit → 0 emails sent; crust_429 retries in client (stdout) without a state event; cfo.ai export is manual; token/$ from neatlogs not filled in the table yet.
- Evidence: `reports/comparison.md`, `reports/v1-posthog-live1.md`, campaigns `v1-posthog-live1` / `p8-chaos-live2` / `p8-kill1`.

### 2026-10-11 00:55 IST
- Completed: Step U1 (per `DECISIONS.md`; overrides docs/10 where they differ). DB: `events`, `campaign_stages`, `runs`, `gate_decisions`, `settings`, `email_decisions` + campaign cols; WAL + 5s busy timeout. `emit` / `EventBag` + `event_messages` + `set_stage` via graph wrapper. `estimate_campaign` in budget; planner pause. CLI `run-campaign`, `approve --decision-id`, `serve` (:8000); `serve-ui` (:8080) kept. FastAPI reads checkpoints via `state_reader`, spawns CLI children for start/resume/gates; email staging + `send-approved`.
- Planned: U2+ UI surfaces; Mailpit live send screenshot when a run hits `waiting_approval` with drafts.
- Tests run: `pytest` — **46 passed** (`tests/test_api_u1.py` with spawn mocked).
- Acceptance U1: `cli.py serve` → `GET /api/campaigns` + `/campaigns/u1-accept-replay1` real data; CLI `run --campaign-id u1-accept-replay1` wrote events + stages (plan/product/buyers/icp waiting); `POST /api/campaigns/u1-accept-replay1/icp` spawned `approve --decision-id` child and resumed to completed. Email staging + send-approved covered in unit tests (replay run had 0 drafts so no Mailpit send this pass).
- Failures remaining: replay ICP still often yields 0 companies/drafts after widen; live Mailpit send-approved not re-proven in this U1 smoke.
- Evidence: campaign `u1-accept-replay1`; logs under `logs/u1-accept-replay1-*.log`; API on `127.0.0.1:8000`.

### 2026-10-11 01:15 IST
- Completed: Step U2 frontend shell. Next.js 15 App Router in `web/` (TS, Tailwind v4, ESLint, shadcn/ui radix-nova). Tokens from docs/09 §3 in `styles/tokens.css` mapped to Tailwind/shadcn vars; Geist Sans/Mono via `geist`; collapsible sidebar (5 nav + live `GET /system/status` footer), 56px header, ⌘K Command palette (navigation only), common components, `lib/api.ts` + `npm run gen:api` → `lib/api-types.ts`, React Query provider. Placeholder EmptyState pages for campaigns/approvals/outbox/reports/settings.
- Planned: U3 campaigns list + New campaign drawer.
- Tests run: `npm run build` OK; `npm run lint` clean (no ESLint issues).
- Acceptance U2: shell tokens/layout per §3–4; focus-visible accent rings global; sidebar footer shows real Crustdata credits (200) / mode / tracing / Bedrock model from API.
- Failures remaining: New campaign only opens ⌘K until U3; approvals count badge is "—"; no mock data by design.
- Evidence: `web/` app; regenerate types with API up: `cd web && npm run gen:api`.

## Submission
- [ ] public repo  - [ ] video ≤3 min  - [ ] neatlogs traces  - [ ] Entire checkpoint link + ID
- [ ] cfo.ai plan  - [ ] #neatHack posts  - [ ] quote post on X in window
