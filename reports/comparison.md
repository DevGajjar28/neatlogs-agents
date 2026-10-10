# v0 vs v1 comparison (Gate 2)

Seller: **PostHog** (`https://posthog.com`) · N=10 · same product page inputs.

| Metric | v0 (`v0-posthog-live2`) | v1 (`v1-posthog-live1`) | Change |
| --- | --- | --- | --- |
| Crustdata credits per qualified lead | 14.60 | 5.31 | **-9.29 (better)** |
| Total Crustdata credits | 43.81 | 53.06 | +9.25 (more work: fallback + verifier path) |
| Cache hit rate | 6.1% | 24.6% | **+18.5 pp** |
| Tokens per lead | _(fill from neatlogs)_ | _(fill from neatlogs)_ | |
| LLM cost per lead | _(fill from neatlogs)_ | _(fill from neatlogs)_ | |
| Wall-clock per campaign | _(v0 session)_ | ~300 s (ICP→email gate) | |
| Leads lost to errors | 0 | 4 (soft LLM/tool errors, recovered) | |
| Drafts with unsupported claim / verifier drop | n/a (no verifier) | 6 dropped after reject | verifier working |
| Verifier pass (step-1 ready) | 0 | 4 | **+4** |
| Contacts found (of N companies) | 3 / 10 | 10 / 10 | **+7** |
| Companies kept | 10 | 10 | 0 |
| Emails sent (Mailpit) | 0 | 0 | SMTP sandbox not running locally |
| Trace link | filter neatlogs by `v0-posthog-live2` | filter neatlogs by `v1-posthog-live1` | paste dashboard URLs below |

**Trace URLs (paste from neatlogs Traces, filter by campaign id in metadata):**

- v0: `NEATLOGS_TRACES_URL` → campaign `v0-posthog-live2`
- v1: `NEATLOGS_TRACES_URL` → campaign `v1-posthog-live1`
- Chaos (`p8-chaos-live2`): `crust_429` + `empty_people` + `llm_bad_json` — events include `recovery.llm_bad_json`, `chaos.empty_people`, `recovery.explain_retry`
- Kill + resume: `p8-kill1` / earlier `b0-kill-prod` — `chaos.kill_after` then resume at **0.0 new credits** / 100% cache on replay

What changed between them (one line each):

- **planner** — stages + budget halt + `replan.widen_icp` / `plan.replace_no_contact`
- **verifier** — reject → drop/redraft path; only grounded drafts reach approval
- **cache** — SQLite response cache; resume/replay hit rate up
- **enrich-survivors-only** — company enrich then contact work on kept set
- **fallback chain** — enrich people → person search → explain retry → pattern; v1 used `fallback.contact_step_2` ×10
- **cheaper extraction model** — fast model for product/account story; strong for ICP/verifier

Raw metric dumps: `reports/v0-posthog-live2.json`, `reports/v1-posthog-live1.json`.
