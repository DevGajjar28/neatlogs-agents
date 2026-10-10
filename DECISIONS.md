# UI build decisions after the U0 audit

Read with `docs/ui/BACKEND_MAP.md`. Where this file and `docs/10_UI_BACKEND_INTEGRATION.md` disagree, **this file wins**. Rule: keep the working code and its payload shapes; add the API and DB around them.

## Step B0 — backend fixes before any UI (these also unblock Phase 8 evidence)

1. **`kill_after=<node>` (chaos).** Add a node wrapper in `app/graph.py` used for every node. When `kill_after` names node X and X returns, set a process-global flag. The **next** node wrapper to start checks the flag, calls `flush()` on tracing and then `os._exit(1)`. Exiting at the start of the next node guarantees X's superstep is already checkpointed. Record a `chaos.kill_after` event before exiting. Accept `--chaos kill_after=account_researcher` (match real node names; print valid names on a bad value).
2. **`app/infra/redact.py`.** `mask_email("rahul@finly.io") -> "r***@finly.io"`, `mask_phone`, `redact_text(s)` (masks every email and phone in free text). Use it in event messages, reports, logs and every list API response. Tests.
3. **Guessed emails never bulk-approved.** In `approval_gate` resume handling, `approve_all` must **not** set `allow_guessed` for `email_confidence == "guessed"`; those items stay unapproved unless their per-contact entry has `allow_guessed: true`. CLI `approve --yes` skips guessed unless `--include-guessed`. Record `policy.guessed_skipped` with a count.
4. **`simulate_reply` enforces `DEMO_MODE`.** Raise if `DEMO_MODE` is false; the CLI prints the reason.
5. **Reporter with structured metrics.** `app/reporter/run_report.py`:
   - `compute_metrics(campaign_id) -> dict` from checkpoint state + `budget_ledger` + `emails`/`scheduled_jobs`/`replies` (all metrics in `docs/03` Run reporter: credits by step, cache hit rate, tokens/LLM cost if available, wall clock, companies found/kept/dropped, contacts by fallback step, verifier pass/redraft/downgrade/drop, emails sent, follow-ups sent/cancelled, recoveries by type, cost per qualified lead).
   - `compare(baseline_id, campaign_id) -> list[row]` (metric, baseline, current, change, better).
   - `write_report(campaign_id, baseline_id=None)` renders markdown from `compute_metrics` (keep `write_v0_report` as a thin wrapper so v0 still works).
   - Implement CLI `report <id> [--baseline <id>]` and `compare <a> <b>` writing `reports/comparison.md`.
   - Crustdata reconciliation (`/account/usage/events`, free) if quick; otherwise mark "not reconciled" honestly.
6. **Shared purge.** Move CLI purge SQL into `app/infra/purge.py::purge_campaign(id)`. Also delete the LangGraph checkpoint for `thread_id = id` (use the saver's delete-thread method if the installed version has one; otherwise delete from its checkpoint tables by `thread_id`). Add a `campaign_id` column to `cache` (set on insert) and delete that campaign's cache rows. CLI calls the function.
7. **Halt naming.** Keep `icp_rejected` / `icp.rejected` as the code has it. Docs adapt, not code.

Acceptance B0: `pytest` green; `python cli.py run ... --chaos kill_after=account_researcher` exits mid-run, `python cli.py resume <id>` finishes with cache hits (0 new credits for already-fetched data); `python cli.py report <id>` and `compare <v0> <v1>` produce markdown with real numbers; approve-all leaves guessed drafts unapproved.

## Step U1 — API around the existing system (adapted from docs/10)

**Process model (unchanged from docs/10):** every graph execution — start, resume, gate decisions — runs as a `cli.py` child process. The API process only reads checkpoints and DB, and writes decisions.

**DB additions:** `events`, `campaign_stages`, `runs`, `gate_decisions`, `settings` tables; new `campaigns` columns (`current_stage`, `pause_requested`, `options_json`, `seller_name`, `seller_domain`, `baseline_campaign_id`); WAL + 5 s busy timeout on every connection (app DB and the SqliteSaver connection).

**Events: one emit helper, not scattered edits.** Add `app/infra/events.py::emit(state, type, agent, **data)` that (a) appends the same dict to `state["events"]` exactly as today and (b) inserts an `events` row with `level` and a founder-readable `message` from `app/infra/event_messages.py` (a dict of type → message template, e.g. `"recovery.explain_retry": "Person search for {company} came back empty; the {culprit} filter was dropped and a semantic search found {found}."`). Unknown types get a generic readable message, never a crash. Replace every existing `state["events"].append(...)` site listed in BACKEND_MAP §2 with `emit`. Messages pass through `redact_text`.

**Stages: wrapper, not per-agent edits.** The same node wrapper from B0 calls `set_stage(campaign_id, stage, "running")` on entry and `"done"` with a count label on exit. Node → stage map lives in one dict in `graph.py` (planner→plan, product_researcher→product, buyer_propose_icp/buyer_search→buyers, icp_gate→icp, account_*→accounts, email_writer→emails, verifier→verify, approval_gate→approval, sender→send). Gate nodes set `"waiting"` before `interrupt()`.

**CLI:**
- `run-campaign <id>`: run a campaign row created by the API (options from `options_json`). Refactor `run` to create the row then call the same function. Heartbeat thread + `runs` row as docs/10 §3.
- `approve <id> --decision-id <n>`: non-interactive; load `gate_decisions` row, `Command(resume=decision_json)` using **today's exact payload shapes** (BACKEND_MAP §3), mark consumed. Existing interactive `approve` keeps working.
- `resume <id>`: unchanged behavior (refuses pending interrupt; `invoke(None)` otherwise) — used for crash and pause.
- `serve [--with-worker]`: API on 127.0.0.1:8000. Keep `serve-ui` (:8080) working until U5 passes.

**Gates from the API:**
- ICP: `GET /campaigns/{id}/icp` reads the pending interrupt (`snapshot.interrupts[0].value`, fallback `tasks[*].interrupts`). `POST` validates and stores `{"approved": bool, "icp": {...}}` in `gate_decisions`, spawns `approve <id> --decision-id`.
- Email: the gate is **one interrupt for all items**. Per-email actions in the UI are staged, not resumed: add table `email_decisions(campaign_id, contact_id, action approve|reject, subject, body, allow_guessed, updated_at)`. `POST /emails/{contact_id}` and `/emails/bulk` write staging rows (bulk never sets `allow_guessed`; guessed approve requires `confirm_guessed: true` → `allow_guessed: true`). Edits re-run the verifier's **deterministic** checks only and return issues. `POST /campaigns/{id}/send-approved` builds `{"approvals": {contact_id: {...}}}` from staging (undecided = not approved), stores it in `gate_decisions`, spawns `approve --decision-id`. The UI shows "N approved · M rejected · K undecided" and the **Send approved** button.
- The lead/email "id" in the API for gate 2 is `contact_id` (what the interrupt uses); after sending, outbox uses DB email ids.

**Reads from checkpoints (read-only, in the API process):** seller, ICP, companies, contacts, account briefs, drafts, verifier results and evidence come from `graph.get_state(config).values`. Put this in `app/api/state_reader.py` with one function per shape and a short TTL cache (2 s). Merge with SQL for emails/outbox/audit statuses.

**Pause:** add `pause_requested`; planner checks it at its next decision, emits `halt.paused`, sets status `paused`, ends. Resume via `resume`.

**Estimate:** move `planner.estimate_credits(n)` into `app/infra/budget.py::estimate_campaign(n, mode) -> {total, by_step[]}` priced from `config/crustdata_account.json`; replay → 0. Planner imports it from there.

**neatlogs links:** env `NEATLOGS_TRACES_URL`; UI shows "Open traces (filter by campaign {id})". Campaign id already in run metadata.

**Statuses for the UI:** derive campaign status from `runs` + checkpoint (`queued`, `running`, `waiting_icp`, `waiting_approval`, `paused`, `crashed`, `completed`, `halted`, `failed`) in one function `app/api/status.py::campaign_status(id)`; write it back to `campaigns.status` when it changes.

Acceptance U1: `pytest` green (API tests with spawn mocked); `curl :8000/api/campaigns` and `/campaigns/{id}` return real data; a CLI run writes `events` + `campaign_stages` rows; ICP approve via `curl POST` resumes through a child process; staging two email decisions + `send-approved` sends only those (Mailpit).

## Order recommendation

B0 → **Phase 8 evidence** (v1 run, chaos run, kill + resume, `compare v0 v1`, cfo.ai plan) → U1 … U6. Evidence first: it scores more and doesn't need the UI. If time is short, the UI stops at U4/U5.
