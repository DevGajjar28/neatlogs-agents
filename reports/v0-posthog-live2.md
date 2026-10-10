# SignalSDR run report - `v0-posthog-live2`

- generated_at: 2026-10-10T18:52:19.641822+00:00
- seller: PostHog
- n: 10
- data_mode: live
- wall_clock_seconds: 0.0
- crustdata_credits_spent: 43.81
- cache_hit_rate: 6.06%
- companies_found/kept/dropped: 10/10/0
- contacts_found: 3
- contacts_by_fallback_step: {}
- verifier pass/redraft/downgrade/drop: 0/0/0/0
- emails_sent: 0
- followups_sent/cancelled: 0/0
- recoveries_by_type: {}
- cost_per_qualified_lead: 14.603333333333333
- tokens/llm_cost: None/None (unavailable locally; read neatlogs dashboard for the campaign)
- reconciled: None — not reconciled (DATA_MODE=replay; usage/events skipped)
- halt_reason: None
- errors: 0

## Credits by step

```json
{
  "account.enrich": 20.0,
  "account.person_enrich": 6.0,
  "account.person_search": 0.91,
  "buyer.autocomplete": 0.0,
  "buyer.customers_enrich": 16.0,
  "buyer.customers_identify": 0.0,
  "buyer.search": 0.9,
  "product.customers_identify": 0.0,
  "product.enrich": 0.0,
  "product.identify": 0.0
}
```

## Events (truncated, redacted)

```json
[
  {
    "type": "product.customers_identified",
    "count": 8
  },
  {
    "type": "buyer.search",
    "strategy": "ranked",
    "count": 30
  },
  {
    "type": "buyer.kept",
    "count": 10,
    "low_confidence_icp": false
  },
  {
    "type": "account.enriched",
    "count": 10
  },
  {
    "type": "account.contact_from_people",
    "company_id": "631460"
  },
  {
    "type": "account.contact_from_search",
    "company_id": "631460"
  },
  {
    "type": "account.contact_from_people",
    "company_id": "***59"
  },
  {
    "type": "account.no_contact",
    "company_id": "***59"
  },
  {
    "type": "account.contact_from_people",
    "company_id": "635058"
  },
  {
    "type": "account.contact_from_search",
    "company_id": "635058"
  },
  {
    "type": "account.contact_from_people",
    "company_id": "665759"
  },
  {
    "type": "account.no_contact",
    "company_id": "665759"
  },
  {
    "type": "account.contact_from_people",
    "company_id": "900016"
  },
  {
    "type": "account.no_contact",
    "company_id": "900016"
  },
  {
    "type": "account.contact_from_people",
    "company_id": "654681"
  },
  {
    "type": "account.no_contact",
    "company_id": "654681"
  },
  {
    "type": "account.contact_from_people",
    "company_id": "954959"
  },
  {
    "type": "account.no_contact",
    "company_id": "954959"
  },
  {
    "type": "account.contact_from_people",
    "company_id": "633948"
  },
  {
    "type": "account.contact_from_search",
    "company_id": "633948"
  },
  {
    "type": "account.no_contact",
    "company_id": "***60"
  },
  {
    "type": "account.no_contact",
    "company_id": "650254"
  },
  {
    "type": "email.drafted",
    "contact_id": "631460:keren-arush-friedman"
  },
  {
    "type": "email.drafted",
    "contact_id": "635058:nils-wloka"
  },
  {
    "type": "email.drafted",
    "contact_id": "633948:hongbin-ma"
  }
]
```
