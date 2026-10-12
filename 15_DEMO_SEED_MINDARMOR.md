# 15 — Demo seed: MindArmor preloaded list

Goal: during the demo video, a New Campaign for **MindArmor (mindarmor.ai)** must never break. Discovery (companies + contacts) comes from a preloaded list stored in the DB. Everything after that runs for real: account enrichment (from cache), email writer + verifier on Bedrock, neatlogs traces, approval, Gmail send, follow-ups.

Hard rules from `docs/12_MAIL_GUARDRAILS.md` and `docs/05` still apply. Read §6 before building.

---

## 1. How it works (one sentence)

When `DEMO_SEED=true` and the new campaign's seller domain normalises to `mindarmor.ai`, the campaign starts in **provided-contacts mode** with the seeded list, skips buyer search and people search, and runs the rest of the pipeline unchanged.

No special-casing inside agents. The switch happens once, at campaign creation; agents just see `target_mode = "provided_contacts"`.

## 2. Files

| File | Committed? | What |
| --- | --- | --- |
| `config/demo/mindarmor_contacts.csv` | **No** (`config/` is gitignored) | The contact list (real names and emails, must never reach the public repo) |
| `config/demo/mindarmor_seller.json` | No | Seller profile fallback for the Product Researcher |
| `app/infra/demo_seed.py` | Yes | Loader, matcher, apply-to-campaign |
| `docs/15_DEMO_SEED_MINDARMOR.md` | Yes | This file (no personal data in it) |

Check `.gitignore` covers `config/`. Run `git status` after seeding; nothing under `config/` may show.

## 3. Data model

New table `demo_seeds`:

```sql
CREATE TABLE demo_seeds (
  id INTEGER PRIMARY KEY,
  seller_domain TEXT NOT NULL,          -- 'mindarmor.ai'
  kind TEXT NOT NULL,                   -- 'seller' | 'contact'
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_demo_seeds_domain ON demo_seeds(seller_domain);
```

Contact payload: `{name, email, company, domain, title, is_test_inbox, note}`.

## 4. CLI

- `python cli.py seed-demo mindarmor` reads `config/demo/mindarmor_contacts.csv` + `mindarmor_seller.json`, validates, dedupes, writes `demo_seeds`. Prints a summary: N contacts, M companies, K test inboxes, rows skipped and why.
- `python cli.py seed-demo mindarmor --clear` deletes those rows.
- Validation per row: name and email required; email syntax check; dedupe by email (case-insensitive); `domain` taken from the CSV, else from the email domain unless it's a free provider (`gmail.com`, `bigpond.com`, `outlook.com`, `yahoo.com`, `hotmail.com`) → row kept but flagged `domain_missing`.

## 5. Campaign flow with the seed

1. **New Campaign** (API `POST /campaigns`): normalise seller domain. If `DEMO_SEED=true` and `demo_seeds` has rows for it:
   - set `options_json.target_mode = "provided_contacts"`, `options_json.seed = "mindarmor"`
   - copy the seeded contacts into `options_json.provided_contacts` (snapshot, so editing the seed later never changes a running campaign)
   - emit `demo.seed_applied`: "Using a preloaded list of {n} contacts at {m} companies for this demo."
2. **Product Researcher** runs live on mindarmor.ai. If the fetch fails or returns too little text, fall back to `mindarmor_seller.json` and emit `product.seed_fallback`. Never fails the run.
3. **ICP** (`buyer_propose_icp`) runs as normal (LLM only) for personas and pain points. Auto-approved as today.
4. **Buyer Finder** → new branch `buyer_import_contacts`: companies = distinct companies from the list; emit `buyers.import_done`: "{m} companies from your list are ready for research."
5. **Account Researcher**: for each company, Crustdata company identify/enrich **through the normal cached client** (free/cached calls first, per `docs/08`). Skip people search: contacts come from the list. Set `email_confidence = "verified"` only for rows with `is_test_inbox = true`; others `"provided"`.
6. **Writer + Verifier, approval, sender, follow-ups**: unchanged.
7. Agent canvas: Buyer Finder card label "Your list", Account Researcher shows contacts count from the list. Campaign header shows a small badge **"Preloaded list"** so the demo is honest about where the contacts came from.

### Warm the cache before recording
Run one full MindArmor campaign once (gmail_test). That fills the Crustdata cache for all companies. The recorded run then shows cache hits and 0 new credits, and can't break on an API hiccup. If a company enrich fails, mark that company `research_thin`, keep going; the writer uses the industry/role angle and the verifier still applies.

## 6. Safety (must be true before recording)

1. **Only test inboxes ever receive mail.** Campaign send mode is forced to `gmail_test` when `seed` is set (refuse `gmail_live` with "Demo seed campaigns can't send live."). Rows with `is_test_inbox = false` are drafted and can be approved, but delivery goes through the existing test-recipient rewrite (policy rule 9). Unit test: a seeded campaign never calls the transport with a non-allowlisted address.
2. **Allowlist** for the account's test recipients: the addresses marked `is_test_inbox = true` in the CSV.
3. **Mask** every non-test email in UI lists, events and traces (`redact.mask_email`). Do not show real prospects' full addresses in the video.
4. **No personal data in the repo, traces or hackathon.md.** The CSV stays under `config/`. neatlogs spans carry masked recipients only.
5. `DEMO_SEED` defaults to `false`. Set it only in your local `.env` for the recording, not on the public deployment.

## 7. Tests

- `seed-demo` parses the CSV: dedupes the duplicate row, flags free-mail domains, rejects bad emails.
- Campaign creation with `mindarmor.ai` + `DEMO_SEED=true` → `target_mode = provided_contacts`, snapshot stored, `demo.seed_applied` emitted. Same seller with `DEMO_SEED=false` → normal discovery.
- Graph routes to `buyer_import_contacts`; people search is never called.
- Seeded campaign rejects `gmail_live`; transport only ever receives allowlisted addresses.
- Product Researcher fetch failure → seller fallback used, run continues.
- Second run after cache warm: 0 new Crustdata credits.

## 8. Done when

`python cli.py seed-demo mindarmor` → New Campaign "MindArmor / mindarmor.ai" in the UI → runs end to end with the "Preloaded list" badge → drafts in Approvals → Accept → mail arrives only in the test inboxes → follow-ups scheduled → neatlogs trace for the run shows the full pipeline. Dated entry in `hackathon.md` (no names or emails).
