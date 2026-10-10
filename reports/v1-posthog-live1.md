# SignalSDR run report - `v1-posthog-live1`

- generated_at: 2026-10-10T18:52:19.702546+00:00
- seller: PostHog
- n: 10
- data_mode: live
- wall_clock_seconds: 300
- crustdata_credits_spent: 53.06
- cache_hit_rate: 24.59%
- companies_found/kept/dropped: 30/10/20
- contacts_found: 10
- contacts_by_fallback_step: {'fallback.contact_step_2': 10}
- verifier pass/redraft/downgrade/drop: 4/0/0/6
- emails_sent: 0
- followups_sent/cancelled: 0/0
- recoveries_by_type: {'recovery.explain_retry': 9, 'recovery.send_retry': 4}
- cost_per_qualified_lead: 5.306
- tokens/llm_cost: None/None (unavailable locally; read neatlogs dashboard for the campaign)
- reconciled: None — not reconciled (DATA_MODE=replay; usage/events skipped)
- halt_reason: None
- errors: 4

## Credits by step

```json
{
  "account.enrich": 26.0,
  "account.news_web": 2.0,
  "account.person_enrich_batch": 20.0,
  "account.person_search.explain": 0.0,
  "account.person_search.semantic": 3.12,
  "account.person_search": 1.04,
  "buyer.autocomplete": 0.0,
  "buyer.customers_enrich": 0.0,
  "buyer.customers_identify": 0.0,
  "buyer.search_lookalike": 0.0,
  "buyer.search": 0.9,
  "doctor": 0.0,
  "product.customers_identify": 0.0,
  "product.enrich": 0.0,
  "product.identify": 0.0
}
```

## Events (truncated, redacted)

```json
[
  {
    "type": "plan.start",
    "n": 10,
    "estimated_credits": 100.0,
    "max_credits": 400
  },
  {
    "type": "product.customers_identified",
    "count": 8
  },
  {
    "type": "buyer.icp_proposed",
    "industries": [
      "Sporting Goods Manufacturing",
      "Advertising Services",
      "IT Services and IT Consulting"
    ],
    "countries": [
      "Italy",
      "USA"
    ],
    "employee_count_ranges": [
      "***00",
      "51-200",
      "201-500"
    ],
    "low_confidence_icp": false,
    "customer_profiles": 8
  },
  {
    "type": "icp.approved",
    "edited_by_user": true,
    "industries": [
      "Software Development",
      "SaaS",
      "IT Services and IT Consulting",
      "Advertising Services",
      "Computer Software"
    ],
    "countries": [
      "USA",
      "GBR",
      "DEU",
      "France",
      "Italy"
    ]
  },
  {
    "type": "buyer.search",
    "strategy": "competitors",
    "count": 0
  },
  {
    "type": "buyer.search",
    "strategy": "ranked",
    "count": 30
  },
  {
    "type": "buyer.kept",
    "count": 10,
    "pool": 30,
    "buffer": 20,
    "n": 10
  },
  {
    "type": "account.enriched",
    "count": 10
  },
  {
    "type": "account.news_web_fallback",
    "company_id": "***29"
  },
  {
    "type": "recovery.explain_retry",
    "company_id": "***29",
    "culprit_paths": [
      "filters.conditions[0]",
      "filters.conditions[2]"
    ],
    "remarks_codes": [
      "condition_eliminates_all",
      "condition_eliminates_all"
    ]
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "***29",
    "source": "person_search_semantic"
  },
  {
    "type": "recovery.explain_retry",
    "company_id": "***87",
    "culprit_paths": [
      "filters.conditions[0]",
      "filters.conditions[2]"
    ],
    "remarks_codes": [
      "condition_eliminates_all",
      "condition_eliminates_all"
    ]
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "***87",
    "source": "person_search_semantic"
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "634663",
    "source": "person_search"
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "***62",
    "source": "person_search"
  },
  {
    "type": "account.news_web_fallback",
    "company_id": "***02"
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "***02",
    "source": "person_search"
  },
  {
    "type": "account.news_web_fallback",
    "company_id": "***68"
  },
  {
    "type": "recovery.explain_retry",
    "company_id": "***68",
    "culprit_paths": [
      "filters.conditions[0]"
    ],
    "remarks_codes": [
      "condition_eliminates_all"
    ]
  },
  {
    "type": "fallback.skipped_not_enabled",
    "company_id": "***68",
    "endpoint": "/person/professional_network/search/live"
  },
  {
    "type": "recovery.explain_retry",
    "company_id": "***38",
    "culprit_paths": [
      "filters.conditions[0]",
      "filters.conditions[2]"
    ],
    "remarks_codes": [
      "condition_eliminates_all",
      "condition_eliminates_all"
    ]
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "***38",
    "source": "person_search_semantic"
  },
  {
    "type": "recovery.explain_retry",
    "company_id": "***35",
    "culprit_paths": [
      "filters.conditions[0]",
      "filters.conditions[2]"
    ],
    "remarks_codes": [
      "condition_eliminates_all",
      "condition_eliminates_all"
    ]
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "***35",
    "source": "person_search_semantic"
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "635089",
    "source": "person_search"
  },
  {
    "type": "account.news_web_fallback",
    "company_id": "954039"
  },
  {
    "type": "recovery.explain_retry",
    "company_id": "954039",
    "culprit_paths": [
      "filters.conditions[0]"
    ],
    "remarks_codes": [
      "condition_eliminates_all"
    ]
  },
  {
    "type": "fallback.skipped_not_enabled",
    "company_id": "954039",
    "endpoint": "/person/professional_network/search/live"
  },
  {
    "type": "account.person_enrich_batch",
    "count": 8
  },
  {
    "type": "account.no_contact",
    "company_id": "***68"
  },
  {
    "type": "account.no_contact",
    "company_id": "954039"
  },
  {
    "type": "plan.replace_no_contact",
    "promoted": 2,
    "company_ids": [
      "***09",
      "642116"
    ],
    "kept_before": 8,
    "n": 10
  },
  {
    "type": "account.enriched",
    "count": 2
  },
  {
    "type": "account.news_web_fallback",
    "company_id": "***09"
  },
  {
    "type": "recovery.explain_retry",
    "company_id": "***09",
    "culprit_paths": [
      "filters.conditions[0]"
    ],
    "remarks_codes": [
      "condition_eliminates_all"
    ]
  },
  {
    "type": "fallback.skipped_not_enabled",
    "company_id": "***09",
    "endpoint": "/person/professional_network/search/live"
  },
  {
    "type": "recovery.explain_retry",
    "company_id": "642116",
    "culprit_paths": [
      "filters.conditions[0]",
      "filters.conditions[2]"
    ],
    "remarks_codes": [
      "condition_eliminates_all",
      "condition_eliminates_all"
    ]
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "642116",
    "source": "person_search_semantic"
  },
  {
    "type": "account.person_enrich_batch",
    "count": 1
  },
  {
    "type": "account.no_contact",
    "company_id": "***09"
  }
]
```
