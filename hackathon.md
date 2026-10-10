# SignalSDR — neatHack 2026

## Project
An outbound agent that drafts and schedules email only from sourced facts — so a campaign can keep running without inventing claims or emailing a real prospect during the demo.

## Team
DevGajjar28

## Stack
LangGraph, AWS Bedrock (ChatBedrockConverse), neatlogs, Entire, cfo.ai, Crustdata, SQLite, FastAPI, local SMTP (no Docker)

## Build log
### 2026-10-10 16:30 IST
- Completed: repo connected to github.com/DevGajjar28/neatlogs-agents. Skeleton for config, models, SQLite schema, neatlogs callback factory, Bedrock factory, and CLI stubs. `.env.example` lists every variable the app reads.
- Planned: Crustdata client, cache, and budget. Test seller for later live runs: PostHog (https://posthog.com), overridable on the CLI.
- Tests run: `pytest` — 1 passed (`tests/test_db.py`). `python cli.py --help` lists the commands. Bedrock ping not run; `.env` is not filled yet.
- Failures remaining: Entire CLI is not installed, so this commit has no Entire checkpoint. neatlogs doctor and the Bedrock ping wait on `.env`.
- Evidence: none yet (no trace).

## Demo
Not available yet.

## Known limitations and next steps
Agent graph, verifier, and sender are not implemented. Demo mail will use a local SMTP catcher, not Docker.

## Submission
- [ ] public repo  - [ ] video ≤3 min  - [ ] neatlogs traces  - [ ] Entire checkpoint link + ID
- [ ] cfo.ai plan  - [ ] #neatHack posts  - [ ] quote post on X in window
