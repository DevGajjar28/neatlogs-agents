# Measured inputs for cfo.ai (Phase 8)

Fill cfo.ai from these **ledger-backed** numbers. Do not invent credits.

## Runs

| Run | Mode | N | Credits spent | Contacts (qualified) | Credits / qualified lead | Cache hit rate |
| --- | --- | --- | --- | --- | --- | --- |
| `v0-posthog-live2` | live | 10 | 43.81 | 3 | **14.60** | 6.1% |
| `v1-posthog-live1` | live | 10 | 53.06 | 10 | **5.31** | 24.6% |
| `p8-chaos-live2` | live + chaos | 5 | 24.4 | 5 | 4.88 | 24% |
| `p8-kill1` resume | replay | 5 | 0.0 after kill | — | — | 100% on resume path |

Source: SQLite `budget_ledger` + LangGraph checkpoint via `python cli.py report <id>`.

## Unit economics (use v1)

- **Credits per qualified lead (measured):** 5.31
- **Crustdata $ / credit:** use your dashboard / team quote (neatHack docs ballpark **$0.05–0.06** list). Until confirmed, model both:
  - at $0.05/credit → **$0.266 / lead** data cost
  - at $0.06/credit → **$0.319 / lead** data cost
- **Tokens / LLM $ per lead:** pull from neatlogs for workflows `outbound-v0` / `outbound-approve` filtered by `v1-posthog-live1` (SDK has no local URL helper; paste into the table in `reports/comparison.md`).
- **Infra / month (assumptions to edit in cfo.ai):**
  - Hosting + SQLite disk: $20
  - Bedrock LLM (est. from neatlogs): _fill_
  - Email (Postmark/SES after demo): $10–30
  - Crustdata subscription / top-ups: variable

## Pricing options to model in cfo.ai

1. **Subscription:** $49/mo for 100 qualified leads → $0.49/lead list  
   - Margin vs $0.27–0.32 data + LLM: healthy if LLM &lt; ~$0.10/lead
2. **Subscription:** $99/mo for 100 leads → $0.99/lead (safer if LLM is higher)
3. **Per lead:** $0.80 / qualified lead

Break-even check (07): at ~8–10 credits/lead list, $0.49/lead is tight; **our v1 is 5.31 credits/lead**, so $49/100 clears data cost with headroom before tokens.

## Scenarios (suggested)

| Scenario | Customers / mo | Leads / customer | Churn | Notes |
| --- | --- | --- | --- | --- |
| Conservative | 10 | 100 | 8% | $99 plan |
| Base | 40 | 100 | 5% | $49 or $99 mix |
| Growth | 120 | 150 | 4% | watch Crustdata + Bedrock caps |

## Reconciliation

v1 live ledger is the cost source. `GET /account/usage/events` reconciliation is marked “not automated” in the reporter; re-check in the Crustdata dashboard before the video if judges ask.
