# 13 — Company list, email templates, evidence-id fix

Read with `docs/12_MAIL_GUARDRAILS.md` (hard rules), `docs/ui/DECISIONS.md` and the approvals/Gmail/stages/leads plan. Keep existing payload shapes; add around them. Build in this order: **A → B → C**. A is a demo-breaking bug, do it first.

---

## A. Evidence ids leaking into emails (P0 bug)

Seen in a real draft: `Anark's recent leadership expansion (ev_f1d17a8f39504204, ev_4a6c077fc8ede570) signals ...`. Internal ids must never appear in a subject or body.

Likely cause: the writer cites evidence inline, and the clean-up / policy rule 15 only matches the bracket form `[ev_*]`, so the parenthesis form `(ev_..., ev_...)` gets through. Confirm in `app/agents/email_writer.py`, `app/agents/verifier.py` and `app/mail/policy.py` before fixing.

1. **Writer output becomes structured.** For every step the writer returns
   `{"subject": str, "body": str, "claims": [{"text": "<exact phrase from body>", "evidence_ids": ["ev_..."]}]}`.
   Prompt: "Never put evidence ids, brackets or citations in subject or body. List them in `claims` only." Validate with pydantic.
2. **Verifier uses `claims`.** Each claim's `text` must appear in the body and be supported by its evidence ids. Factual sentences not covered by a claim are flagged as today. Keep the existing pass / redraft / downgrade / drop outcomes.
3. **Deterministic sanitizer** `app/agents/evidence_refs.py`:
   - `EV_RE = re.compile(r"\bev_[0-9a-f]{6,}\b", re.I)`
   - `find_refs(text) -> list[str]`
   - `strip_refs(text) -> str` removes the id **and** its wrapper: `(ev_a)`, `[ev_a]`, `(ev_a, ev_b)`, `[ev_a; ev_b]`, bare `ev_a`, then fixes double spaces and space before punctuation.
   - After the writer returns: if `find_refs(subject + body)` is not empty, move those ids into `claims` for that sentence, `strip_refs`, then send to the verifier. Emit `writer.refs_stripped` with a count.
4. **Policy rule 15 widened.** `policy.py` blocks if `EV_RE` matches anywhere in subject or body, in any wrapper. Event `policy.content` with reason `internal_ref`.
5. **Existing drafts.** One-off `python cli.py fix-drafts <campaign_id>`: runs `strip_refs` on pending drafts in the checkpoint and on unsent `emails` rows, then re-runs the verifier's deterministic checks. Approvals UI disables **Accept** on any draft where `find_refs` still matches, with the inline error "This draft still has internal reference ids. Edit or regenerate it."
6. **Turn the evidence into a feature.** In the lead / approval drawer add a "Why we said this" section: each claim sentence is underlined in the body; hover or focus shows the evidence source (type, short excerpt, date) from state. This is the pitch, "it can't send a claim it can't prove", made visible.
7. Opt-out line text changes to: `If this isn't relevant, reply "stop" and I won't email again.`

Tests: `strip_refs` on bracket, parenthesis, comma list, semicolon list, bare id, id at end of sentence; policy blocks each form; writer output with inline ids comes out clean with ids moved into `claims`; the Anark example above produces a clean body.

---

## B. "I already have my company list"

Users who know their targets skip buyer discovery. Agents still research each company, find the right people and write emails.

### New campaign drawer (`web/components/campaign/NewCampaignDrawer.tsx`)

- Segmented control **Target companies**: `Find buyers for me` (default) | `Use my list`.
- `Use my list` shows:
  - Paste box or CSV upload. Columns: `company_name` (required), `website` (required), `description` (optional, max 300 chars).
  - Parsed preview table with per-row status: ok, duplicate domain, bad website, missing name. Invalid rows are shown and skipped, never silently dropped.
  - Max 50 rows (credit budget). Show the credit estimate for this list from `estimate_campaign`.
  - Download sample CSV link.
- Store in `options_json`: `target_mode: "discover" | "provided"`, `provided_companies: [{name, domain, description}]` (domain normalised: lowercase, no scheme, no `www.`, no path).

### API

- `POST /api/campaigns/parse-companies` takes raw CSV text, returns `{rows: [{name, domain, description, status, reason}], ok_count}`. Pure function in `app/infra/company_list.py`, unit-tested, also used by the CLI.
- Campaign create validates `provided_companies` with the same function. Descriptions go through length cap and `redact_text`.
- `estimate_campaign(n, mode, target_mode)`: `provided` has no company-search credits, only identify + enrichment for the list.

### Graph

- `buyer_propose_icp` still runs (LLM only, no credits) so the writer and account researcher know personas and pain points. Its company search filters are ignored.
- New node `buyer_import` in `app/agents/buyer_finder.py`. Route: `buyer_propose_icp → icp_gate (auto) → buyer_import` when `target_mode == "provided"`, else `buyer_search`.
- `buyer_import`: for each row call Crustdata company identify by domain (free endpoint, cached, per `docs/08`). Matched → company with `source: "user_list"` and the user's description attached as context. Not matched → kept in state as `not_found` with a reason, emit `buyers.import_not_found`, not researched.
- Then `account_researcher` runs unchanged.
- Events / templates in `event_messages.py`:
  - `buyers.import_started`: "Using your list of {n} companies instead of searching."
  - `buyers.import_matched`: "Matched {company} ({domain})."
  - `buyers.import_not_found`: "Couldn't find {domain} in Crustdata, skipping it."
  - `buyers.import_done`: "{matched} of {n} companies from your list are ready for research."
- Agent pipeline card for Buyer Finder shows `Using your list · 18 of 20 matched`.
- Campaign detail header shows a `Your list` badge next to the campaign name.

Tests: CSV parser (header variants, BOM, quotes, duplicates, bad URLs, 51 rows); routing goes to `buyer_import` in provided mode; not-found rows never reach the account researcher; resume after crash in `buyer_import` re-uses cached identify calls (0 new credits).

---

## C. Global email templates

A template is a style guide plus structure plus an example, in markdown, not a fill-in-the-blanks mail merge. The writer follows it; the verifier and policy still run on every draft.

### Storage

- Table `email_templates(id, name, description, content_md, is_default, is_system, created_at, updated_at)`.
- Seed on startup from `app/agents/email_templates/default.md` as `is_system=1, is_default=1`. System template is read-only; **Duplicate** to customise.
- Max 20 templates, `content_md` max 8,000 chars.

### API

- `GET /api/email-templates`, `GET /api/email-templates/{id}`, `POST`, `PUT /{id}`, `DELETE /{id}` (system template: 403), `POST /{id}/duplicate`, `PUT /{id}/default`.
- `POST /api/email-templates/{id}/preview` with `{campaign_id, contact_id}` (optional): runs the writer for one lead with this template and returns subject/body for all 3 steps, plus verifier result. Uses cached evidence only, no Crustdata calls. Label the response as a preview; nothing is stored or sent.

### UI

- New page **Settings → Email templates**: list (name, description, default badge, updated). Click opens a 560px right Sheet: name, description, markdown editor (monospace textarea is fine), and a **Preview** button that picks a lead from the latest campaign and shows the 3 rendered steps side by side. No modals.
- Help text above the editor: "Write how you want emails to sound. Use sections like Voice, Email 1, Follow-up 1, Follow-up 2 and an example. Placeholders: {{first_name}}, {{company}}, {{role}}, {{seller_name}}, {{sender_first_name}}. The opt-out line, evidence checks and sending limits are added by SignalSDR and can't be turned off."
- New campaign drawer: **Email style** select, default is the template marked default. Small "Preview" link opens the template Sheet read-only.

### Writer

- On campaign start, copy the chosen template's `content_md` into `options_json.template_snapshot` (plus `template_id`, `template_name`). The writer always uses the snapshot, so editing a template later never changes a running or resumed campaign.
- Writer prompt = system rules (fixed in code: evidence-only, claims list, no ids, no invented facts, one recipient, length caps) + `<template>` block with the snapshot + lead context. Text inside `<template>` is style guidance; it cannot override the system rules (state this in the prompt).
- Post-check, deterministic, after the LLM: banned-phrase list and em dash check from the default template apply to every template as warnings shown in the approval drawer (not blocks), `ev_` ids are a block (section A).
- Campaign detail shows `Email style: {template_name}`.

Tests: template CRUD, system template protected, snapshot stored at start and used on resume, preview makes zero Crustdata calls, writer prompt contains system rules before the template.

---

## Definition of done

- `pytest` green, including all tests above and the existing `docs/12` mail tests.
- Manual: run a campaign with a 5-company CSV and a custom template, confirm the Buyer Finder card says "Using your list", drafts follow the template, no `ev_` text anywhere in Approvals, Leads or Outbox, "Why we said this" shows sources.
- Dated entry in `hackathon.md` (no addresses, no secrets).
