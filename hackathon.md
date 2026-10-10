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

## Demo
Not available yet.

## Known limitations and next steps
Agent graph, verifier, and sender are not implemented. Demo mail will use a local SMTP catcher, not Docker. Default `DATA_MODE=replay`. Live people search and dedicated contact enrich are disabled on this Crustdata plan.

## Submission
- [ ] public repo  - [ ] video ≤3 min  - [ ] neatlogs traces  - [ ] Entire checkpoint link + ID
- [ ] cfo.ai plan  - [ ] #neatHack posts  - [ ] quote post on X in window
