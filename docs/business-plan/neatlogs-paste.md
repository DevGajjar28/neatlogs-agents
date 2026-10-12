# Paste into neatlogs chat — LLM usage for ReachPilot unit economics

Copy everything below the line into your **neatlogs** chat/assistant. They will pull analytics for our campaigns. We need LLM tokens + $ so cfo.ai can compute blended cost per lead. **Do not treat missing LLM $ as $0** — leave it blank if not found.

After neatlogs replies, paste their form back here (and to Ari). Bedrock inference is counted **once** (prefer per-lead from the campaign run; do **not** also add a separate monthly Bedrock line for the same spend).

---

Hi neatlogs — we need **measured LLM usage** for our neatHack outbound agent **ReachPilot** so we can finish unit economics with cfo.ai.

### How to find our runs

| Field | Value |
| --- | --- |
| Product / app | ReachPilot (repo may still say SignalSDR in older spans) |
| Ingest endpoint | `https://ingest.neatlogs.com` |
| Workflow names (from `init_tracing`) | `outbound-v0` (campaign start), `outbound-approve` / `outbound-resume` (resume kinds), `outbound-approve-ui` (legacy UI) |
| Campaign id in metadata | filter traces by campaign id (LangGraph run config metadata) |
| Primary campaign | **`v1-posthog-live1`** ← use this for unit economics |
| Baseline campaign | `v0-posthog-live2` (contrast only) |
| Chaos / resume | `p8-chaos-live2`, `p8-kill1` (optional) |
| Seller context | PostHog · N=10 companies · live Crustdata |

If campaign id is not indexed as a first-class filter, search metadata / tags / span attributes for `campaign_id` / `v1-posthog-live1`.

### What we already measured (not from you — Crustdata ledger)

| Metric | v1 (`v1-posthog-live1`) | v0 (`v0-posthog-live2`) |
| --- | --- | --- |
| Crustdata credits spent | 53.06 | 43.81 |
| Qualified contacts | 10 | 3 |
| Credits / qualified lead | **5.31** | 14.60 |
| Data $ / lead @ $0.05 | **$0.266** | — |
| Data $ / lead @ $0.06 | **$0.319** | — |

Local run report has `tokens/llm_cost: None` — we need that from **your** dashboard.

### Please return this form (fill every cell you can)

#### A) Campaign `v1-posthog-live1` (required)

| Field | Value |
| --- | --- |
| Trace / session URL(s) | |
| Workflow name(s) seen | |
| Time window (start → end UTC) | |
| Total input tokens | |
| Total output tokens | |
| Total tokens | |
| **Total LLM $ (USD)** | |
| Models used (e.g. Haiku / Sonnet Bedrock ids) | |
| LLM $ breakdown by model (if available) | |
| **LLM $ per qualified lead** (= total LLM $ ÷ 10) | |
| Spans / LLM calls count | |
| Tool spans count (Crustdata etc.) | |
| Any errors / retries noted | |

#### B) Campaign `v0-posthog-live2` (optional contrast)

| Field | Value |
| --- | --- |
| Total LLM $ (USD) | |
| LLM $ per qualified lead (÷ 3 contacts) | |
| Total tokens | |

#### C) Analytics summary we can paste to judges / cfo.ai

Please also give:

1. **One-line cost story:** “v1 used $X LLM + 5.31 Crustdata credits/lead → data ≈ $0.27–0.32/lead; LLM ≈ $Y/lead.”  
2. **Token mix:** % input vs output if available.  
3. **Hottest nodes:** which agent steps burned the most tokens (product researcher, ICP, writer, verifier, etc.).  
4. **Export:** CSV or table of LLM cost by day / by workflow for this project (last 14 days) if easy.  
5. **Dashboard deep-link:** exact Traces URL filter string for `v1-posthog-live1`.

### Rules for costing (important)

- Keep **LLM $ visible even if zero or missing** — write `NOT FOUND` rather than $0.00 when data is absent.  
- **Bedrock counts once:** report campaign LLM $ as **per-lead** (total ÷ qualified leads). Do **not** invent a second “Bedrock monthly subscription” that double-counts the same inference.  
- Separate monthly infra we already assume elsewhere: hosting $20, email $10–30 — those are **not** neatlogs.  
- Redact any prospect PII / email bodies in exports; we only need aggregates.

Thanks — once we have **LLM $ per qualified lead** for `v1-posthog-live1`, we hand it to cfo.ai for blended cost and put it on the ReachPilot landing page.

---
