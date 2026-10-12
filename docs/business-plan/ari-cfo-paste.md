# Paste to Ari (cfo.ai) — fill LLM line from neatlogs, then return numbers

Copy everything below the line into Slack/email. After Ari runs cfo.ai, paste the returned blended cost / break-even back so we can put it on the ReachPilot landing page.

---

Hey Ari — measured unit economics for **ReachPilot** (neatHack outbound agent). Please run these through **cfo.ai** so we get real cost-per-lead (not guesses).

### Measured from run report (`v1-posthog-live1`)

| Input | Value | Source |
| --- | --- | --- |
| Seller / N | PostHog · 10 companies | live run |
| Crustdata credits spent | **53.06** | budget ledger |
| Qualified contacts | **10** | run report |
| **Credits per qualified lead** | **5.31** | 53.06 / 10 |
| Cache hit rate | 24.6% | run report |
| Crustdata $ / credit (model both) | $0.05 and $0.06 | team quote / dashboard |
| Data $ / lead @ $0.05 | **$0.266** | 5.31 × 0.05 |
| Data $ / lead @ $0.06 | **$0.319** | 5.31 × 0.06 |
| LLM $ per lead (Option B) | **$0.010209** | neatlogs full async aggregation · 56,787 tok · $0.102092 / 10 |
| Hosting + SQLite / mo | $20 | assumption (not LLM) |
| Email (Postmark/SES) / mo | $10–30 | mid $20 in spreadsheet |
| Bedrock monthly line | **Do not double-count** | Per-lead LLM already includes Bedrock; monthly Bedrock = leads × $0.010209 only if projecting volume |
| Direct cost / lead | **$0.276–$0.329** | data + LLM |
| Blended / lead (base 4k/mo) | **$0.285–$0.341** | + hosting/email amortized |

v0 baseline for contrast: **14.60 credits / qualified lead** (`v0-posthog-live2`) — v1 is **−9.29 credits/lead**.

### Pricing options to model

1. Subscription **$49/mo** for 100 qualified leads → $0.49/lead  
2. Subscription **$99/mo** for 100 qualified leads → $0.99/lead  
3. Per lead **$0.80** / qualified lead  

### Scenarios

| Scenario | Customers / mo | Leads / customer | Churn |
| --- | --- | --- | --- |
| Conservative | 10 | 100 | 8% |
| Base | 40 | 100 | 5% |
| Growth | 120 | 150 | 4% |

### Please send back (we’ll put these on the landing page)

- Blended **cost per qualified lead** (data + LLM + infra amortized)  
- Recommended plan ($49 / $99 / per-lead) and why  
- Break-even customers / mo for the recommended plan  
- Any risk notes on Crustdata or Bedrock caps  

Measured Crustdata + neatlogs Option B are locked in `ReachPilot unit economics.xlsx` and on the landing page. Use those for any cfo.ai scenario refresh — do not treat LLM as $0.

---
