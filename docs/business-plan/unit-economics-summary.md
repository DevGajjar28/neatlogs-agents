# ReachPilot unit economics (locked)

Source: `ReachPilot unit economics.xlsx` + neatlogs Option B (full async aggregation).

## Per qualified lead (v1-posthog-live1, N=10)

| Component | Value |
| --- | --- |
| Crustdata credits / lead | **5.31** |
| Data $ / lead @ $0.05 | **$0.266** |
| Data $ / lead @ $0.06 | **$0.318** |
| LLM $ / lead (Option B) | **$0.0102** |
| Direct (data + LLM) | **$0.276 – $0.329** |
| Blended (+ hosting/email amortized, base case 4k leads/mo) | **$0.285 – $0.341** |

## LLM measurement (Option B — use this)

- Total LLM $: **$0.102092** · tokens **56,787** · 55 LLM calls · 46 traces  
- Model: Claude Haiku 4.5 on Bedrock  
- Option A (parent-only) understates by ~65% — do not use for pricing  

## Pricing (base: 40 customers × 100 leads)

All three plans show positive surplus after blended cost; **$99/mo** and **$0.80/lead** have the healthiest margins.
