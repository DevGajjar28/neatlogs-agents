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

## Submission
- [ ] public repo  - [ ] video ≤3 min  - [ ] neatlogs traces  - [ ] Entire checkpoint link + ID
- [ ] cfo.ai plan  - [ ] #neatHack posts  - [ ] quote post on X in window
