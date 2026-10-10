# SignalSDR run report - `p8-chaos-live2`

- generated_at: 2026-10-10T18:50:53.502292+00:00
- seller: PostHog
- n: 5
- data_mode: live
- wall_clock_seconds: 24.068693
- crustdata_credits_spent: 24.4
- cache_hit_rate: 26.92%
- companies_found/kept/dropped: 15/5/10
- contacts_found: 5
- contacts_by_fallback_step: {'fallback.contact_step_2': 5}
- verifier pass/redraft/downgrade/drop: 1/0/0/4
- emails_sent: 0
- followups_sent/cancelled: 0/0
- recoveries_by_type: {'recovery.llm_bad_json': 1, 'recovery.explain_retry': 4}
- cost_per_qualified_lead: 4.88
- tokens/llm_cost: None/None (unavailable locally; read neatlogs dashboard for the campaign)
- reconciled: None — not reconciled (usage/events fetched; X-Request-Id join not automated yet)
- halt_reason: None
- errors: 1

## Credits by step

```json
{
  "account.enrich": 12.0,
  "account.person_enrich_batch": 10.0,
  "account.person_search.explain": 0.0,
  "account.person_search.semantic": 1.17,
  "account.person_search": 0.78,
  "buyer.autocomplete": 0.0,
  "buyer.search": 0.45,
  "doctor": 0.0,
  "product.enrich": 0.0,
  "product.identify": 0.0
}
```

## Events (truncated, redacted)

```json
[
  {
    "type": "plan.start",
    "n": 5,
    "estimated_credits": 60.0,
    "max_credits": 400
  },
  {
    "type": "recovery.llm_bad_json",
    "step": "product_researcher"
  },
  {
    "type": "product.no_customers",
    "detail": "buyer_finder will use low-confidence ICP"
  },
  {
    "type": "buyer.icp_proposed",
    "industries": [
      "Software Development"
    ],
    "countries": [
      "United States"
    ],
    "employee_count_ranges": [
      "51-200",
      "201-500"
    ],
    "low_confidence_icp": true,
    "customer_profiles": 0
  },
  {
    "type": "icp.approved",
    "edited_by_user": true,
    "industries": [
      "Software Development"
    ],
    "countries": [
      "United States"
    ]
  },
  {
    "type": "buyer.search",
    "strategy": "ranked",
    "count": 15
  },
  {
    "type": "buyer.kept",
    "count": 5,
    "pool": 15,
    "buffer": 10,
    "n": 5
  },
  {
    "type": "account.enriched",
    "count": 5
  },
  {
    "type": "chaos.empty_people",
    "companies": [
      "634663",
      "635089",
      "892856",
      "***65",
      "642116"
    ]
  },
  {
    "type": "recovery.explain_retry",
    "company_id": "634663",
    "culprit_paths": [
      "filters.conditions[0]",
      "filters.conditions[1]",
      "filters.conditions[2]",
      "filters.conditions[3]"
    ],
    "remarks_codes": [
      "condition_eliminates_all",
      "condition_eliminates_all",
      "condition_eliminates_all",
      "condition_eliminates_all"
    ]
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "634663",
    "source": "person_search_semantic"
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "635089",
    "source": "person_search"
  },
  {
    "type": "fallback.contact_step_2",
    "company_id": "892856",
    "source": "person_search"
  },
  {
    "type": "recovery.explain_retry",
    "company_id": "***65",
    "culprit_paths": [
      "filters.conditions[0]"
    ],
    "remarks_codes": [
      "condition_eliminates_all"
    ]
  },
  {
    "type": "fallback.skipped_not_enabled",
    "company_id": "***65",
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
    "count": 4
  },
  {
    "type": "account.no_contact",
    "company_id": "***65"
  },
  {
    "type": "plan.replace_no_contact",
    "promoted": 1,
    "company_ids": [
      "***83"
    ],
    "kept_before": 4,
    "n": 5
  },
  {
    "type": "account.enriched",
    "count": 1
  },
  {
    "type": "chaos.empty_people",
    "companies": [
      "***83"
    ]
  },
  {
    "type": "recovery.explain_retry",
    "company_id": "***83",
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
    "company_id": "***83",
    "source": "person_search_semantic"
  },
  {
    "type": "account.person_enrich_batch",
    "count": 1
  },
  {
    "type": "email.drafted",
    "contact_id": "634663:kaz-haruna",
    "steps": 3,
    "attempt": 0
  },
  {
    "type": "email.drafted",
    "contact_id": "635089:neal-kaviratna",
    "steps": 3,
    "attempt": 0
  },
  {
    "type": "email.drafted",
    "contact_id": "892856:nathaniel-gilmore",
    "steps": 3,
    "attempt": 0
  },
  {
    "type": "email.drafted",
    "contact_id": "642116:parker-syddall",
    "steps": 3,
    "attempt": 0
  },
  {
    "type": "email.drafted",
    "contact_id": "***83:cristian-daniel-v",
    "steps": 3,
    "attempt": 0
  },
  {
    "type": "verify.reject",
    "contact_id": "634663:kaz-haruna",
    "attempt": 0,
    "issues": [
      "ev_23d4f4299b3f33a9 does not support the claim that 'PostHog provides product analytics and feature flags for engineers.' The evidence card shows only a webpage header/navigation snippet ('your product's context layer Products Pricing Docs...') with no substantive information about PostHog's offerings or capabilities.",
      "ev_0ff34000c0114e3c supports accusations regarding immigration law violations but does NOT specify that Statsig was OpenAI's 'former subsidiary' - the evidence states it was 'once-subsidiary' but does not confirm the subsidiary relationship as fact or provide context for when/why it ceased being a subsidiary."
    ],
    "unsupported_claims": [
      "PostHog provides product analytics and feature flags for engineers - the cited evidence (ev_23d4f4299b3f33a9) is insufficient to verify this specific product capability claim"
    ]
  },
  {
    "type": "verify.drop",
    "contact_id": "634663:kaz-haruna"
  },
  {
    "type": "verify.reject",
    "contact_id": "635089:neal-kaviratna",
    "attempt": 0,
    "issues": [
      "Claim about 'Similar AI-first products have scaled to 170,000+ installs' is unsupported: ev_da3e5325102b1522 references 'ivault' achieving 170,000 installs, not 'similar AI-first products' in general. This is a specific company, not a market trend.",
      "PostHog claim lacks proper support: ev_23d4f4299b3f33a9 appears to be a webpage header/navigation menu, not evidence that PostHog's product analytics and feature flags unify AI and traditional workflows or reduce tool sprawl costs.",
      "No evidence supports the specific claim that PostHog consolidation 'reduces tool sprawl costs while accelerating AI agent instrumentation' - this is an unsupported value proposition."
    ],
    "unsupported_claims": [
      "Similar AI-first products have scaled to 170,000+ installs (generalizes from ivault, a specific company)",
      "PostHog's product analytics and feature flags unify these workflows and reduce tool sprawl costs",
      "PostHog directly impacts engineering team productivity and platform costs for Mixpanel's Headless adoption scenario"
    ]
  },
  {
    "type": "verify.drop",
    "contact_id": "635089:neal-kaviratna"
  },
  {
    "type": "verify.pass",
    "contact_id": "892856:nathaniel-gilmore",
    "attempt": 0
  },
  {
    "type": "verify.reject",
    "contact_id": "642116:parker-syddall",
    "attempt": 0,
    "issues": [
      "ev_a8d8c8e45aa31aef claims 'Harness expands experimentation and feature management for DevOps teams' but does not specify that this was through an ACQUISITION of Split - the email states 'Your team recently acquired Split' as fact, which is not supported by this evidence alone. Evidence ev_552b8926ccc7fc90 shows 'Harness Completes Acquisition of Split Software' which would support this, but that evidence card was not cited.",
      "ev_30dcedec2c58cf23 is about 'Harness and Traceable Complete Merger' creating an 'AI-Native DevSecOps Platform' - the email claims integration into an 'AI-native platform' but does not cite evidence that Harness itself has acquired or integrated Split into this platform. The connection between the Traceable merger and Split integration is not established in the cited evidence.",
      "ev_23d4f4299b3f33a9 appears to be a generic PostHog homepage snippet listing products as 'Products Pricing Docs Community Company' - this does not provide specific evidence that PostHog provides both 'product analytics AND feature flags' in the unified layer as claimed. The evidence is insufficient."
    ],
    "unsupported_claims": [
      "Your team recently acquired Split to expand experimentation and feature management for DevOps teams - the acquisition fact is supported but the causal connection to expanding this capability is not clearly established in ev_a8d8c8e45aa31aef alone",
      "fragmented analytics across your feature flag infrastructure creates visibility gaps - this is presented as fact about the prospect's situation with no evidence provided",
      "PostHog provides product analytics and feature flags in a unified layer - ev_23d4f4299b3f33a9 does not substantiate that PostHog provides both capabilities in a unified solution"
    ]
  },
  {
    "type": "verify.drop",
    "contact_id": "642116:parker-syddall"
  },
  {
    "type": "verify.reject",
    "contact_id": "***83:cristian-daniel-v",
    "attempt": 0,
    "issues": [
      "The cited evidence cards do not support any of the factual claims in the email body. The email makes specific claims about: (1) QA teams lacking real-time visibility causing blind spots and delayed issue detection, (2) incomplete observability extending debugging cycles and inflating operational spend, and (3) PostHog providing product analytics and feature flags. However, the cited evidence cards [ev_7c55b54ffd9dae33] and [ev_2790d1764d6e3288] are about Bowery (an art gallery) and have nothing to do with QA teams, product visibility, PostHog, debugging, or operational spend.",
      "The email's core value proposition claims are completely unsupported by the cited evidence. The references to 'real-time visibility', 'blind spots', 'remediation costs', 'issue detection', 'observability', and 'debugging cycles' lack any evidentiary backing.",
      "While additional evidence cards exist in the provided list (ev_23d4f4299b3f33a9, ev_954219fc6ba6a348, ev_e464e73317869e6c, ev_777c3e0f5c9e2462) that appear relevant to PostHog, they were not cited by the sender. Only the two Bowery-related cards were cited, making the email factually unverifiable against the stated evidence."
    ],
    "unsupported_claims": [
      "Most QA teams lack real-time visibility into how features perform post-launch",
      "This visibility gap creates blind spots that delay issue detection",
      "Blind spots inflate remediation costs",
      "PostHog provides product analytics and feature flags for engineers",
      "PostHog enables faster identification of problems",
      "Incomplete observability extends debugging cycles",
      "Incomplete observability inflates operational spend"
    ]
  },
  {
    "type": "verify.drop",
    "contact_id": "***83:cristian-daniel-v"
  }
]
```
