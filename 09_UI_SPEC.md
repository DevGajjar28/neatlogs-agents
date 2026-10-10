# 09 — UI Spec: SignalSDR Web App (no login)

Role for Cursor: Principal SaaS product designer + design-systems engineer. Build a calm, dense, keyboard-friendly operator console in the style of Linear / Vercel / neatlogs. Not a marketing site.

## 0. Product context

| Item | Value |
| --- | --- |
| Product | SignalSDR — website-to-outbound multi-agent system |
| User | Founder or first sales hire at a small B2B company, running outbound themselves |
| Core problem | Finding the right buyers and writing outreach takes days, and AI tools invent facts and burn budget |
| Job of the UI | Start a campaign, approve the inferred ICP, review and approve verified emails, watch the agent recover from failures, prove cost |
| Key goal | Website pasted → first approved, verified email in under 10 minutes; every claim one click from its source |
| Demo goal | Every judged behavior (planning, recovery, verification, state, cost) is visible on screen without opening a terminal |

## 1. Design principles

1. **Evidence one click away.** Every fact in an email has a citation chip that opens its source.
2. **No modal popups.** Detail and forms open in a **right drawer** that keeps the table usable. The only blocking confirm is purge, done inline in the drawer.
3. **Show the agent thinking.** Planner decisions, fallbacks and recoveries are first-class rows in an activity timeline, not hidden logs.
4. **Cost is always visible.** Credits spent / cap sit in the sidebar footer and on every campaign.
5. **Safe by default, visibly.** "Demo sends" and "Replay" mode chips are always on screen.
6. **Dense but calm.** 13px table text, 40px rows, generous page padding, borders not shadows.

## 2. Tech stack (frontend)

| Concern | Choice |
| --- | --- |
| Framework | Next.js (App Router, current stable), TypeScript, in `web/` |
| Styling | Tailwind CSS with the tokens below as CSS variables |
| Components | shadcn/ui (Radix) — restyled to these tokens: Sheet (drawer), Table, Tabs, Badge, Button, Input, Textarea, Select, Command (⌘K), Tooltip, DropdownMenu, Checkbox, Switch, Skeleton, Toast (sonner) |
| Tables | TanStack Table (sorting, filtering, row selection, column visibility) |
| Data | TanStack Query (polling) + Server-Sent Events for live runs |
| Icons | lucide-react, 16px in UI, 14px in tables, stroke 1.75 |
| Charts | Recharts (bar charts only; no pies) |
| Fonts | `geist` package: Geist Sans (UI), Geist Mono (IDs, credits, numbers, emails) |

Why not indigo + Inter: indigo `#4F46E5` on slate with Inter is the default look of AI-generated SaaS. Ink-black primary buttons, one blue accent and Geist read as a deliberate developer tool (closer to Vercel, Linear and neatlogs).

## 3. Design tokens

### Color (light theme; dark is optional and out of scope for the hackathon)

| Token | Hex | Use |
| --- | --- | --- |
| `--bg` | `#FAFAFA` | App background |
| `--surface` | `#FFFFFF` | Cards, tables, drawer |
| `--surface-muted` | `#F4F4F5` | Table header, hover row, sidebar active bg, code |
| `--border` | `#E4E4E7` | All 1px borders, dividers |
| `--border-strong` | `#D4D4D8` | Inputs, focused card |
| `--text` | `#18181B` | Primary text |
| `--text-muted` | `#52525B` | Secondary text, table meta |
| `--text-subtle` | `#71717A` | Placeholders, timestamps (min for AA on white) |
| `--primary` | `#18181B` | Primary buttons (ink) |
| `--primary-hover` | `#3F3F46` | |
| `--primary-fg` | `#FFFFFF` | |
| `--accent` | `#2563EB` | Links, focus ring, selected-row bar, active nav marker, citation chips |
| `--accent-soft` | `#EFF6FF` | Selected row bg, citation chip bg |

Status (badge = soft bg + strong text + 6px dot):

| Status | Text | Soft bg | Used for |
| --- | --- | --- | --- |
| success | `#15803D` | `#F0FDF4` | Verified, Sent, Completed, Passed |
| warning | `#B45309` | `#FFFBEB` | Guessed email, Waiting for you, Redrafted, Recovered |
| danger | `#B91C1C` | `#FEF2F2` | Failed, Dropped, Halted, Rejected |
| info | `#1D4ED8` | `#EFF6FF` | Running, Scheduled, Replanned |
| neutral | `#3F3F46` | `#F4F4F5` | Draft, Skipped, Cancelled |

Never rely on color alone: every badge has a text label; every status icon has an accessible name.

### Typography (Geist Sans; numbers use `font-variant-numeric: tabular-nums`)

| Role | Size / line | Weight |
| --- | --- | --- |
| Page title | 24 / 32 | 600 |
| Section title | 16 / 24 | 600 |
| Card title / drawer title | 14 / 20 | 600 |
| Body | 14 / 20 | 400 |
| Table cell | 13 / 20 | 400 (name column 500) |
| Label / meta / badge | 12 / 16 | 500 |
| KPI number | 28 / 36 | 600, tabular |
| Mono (IDs, credits, emails) | Geist Mono 12–13 | 400 |

### Spacing, radius, elevation

- 4px grid. Page padding 24px. Card padding 16px. Gap between cards 16px. Section gap 24px.
- Radius: 6px buttons/inputs/badges, 8px cards/tables, 0 on drawer edge.
- Elevation: cards and tables use border only. Shadow only on the drawer (`-8px 0 24px rgba(24,24,27,.08)`), dropdowns and ⌘K (`0 8px 24px rgba(24,24,27,.10)`).
- Focus: `outline: 2px solid var(--accent); outline-offset: 2px` on `:focus-visible` for every interactive element.

### Layout sizes

| Element | Size |
| --- | --- |
| Sidebar | 232px expanded / 56px collapsed (icons only, tooltips) |
| Top header | 56px, sticky, bottom border |
| Content max width | 1440px, 12-column grid, 24px gutters |
| Table row | 40px (compact) — header 36px, sticky |
| Drawer | 560px (lead / email review), 480px (forms), full height under header |
| Buttons | 32px default, 28px in tables and toolbars |

## 4. App shell

### Left sidebar
- Top: wordmark "SignalSDR" (14px, 600) + small "beta" label. Collapse button (`PanelLeft`).
- Nav (icon + label, 32px rows, active = `--surface-muted` bg + 2px `--accent` left marker):
  1. Campaigns — `LayoutList`
  2. Approvals — `Inbox` + count badge (emails awaiting approval)
  3. Outbox — `Send`
  4. Reports — `BarChart3`
  5. Settings — `Settings2`
- Footer (no login, so no profile; system status instead):
  - Chips: `Replay` or `Live` (data mode), `Demo sends` (lock icon)
  - Crustdata: `1,842 credits` (mono) with mini bar vs starting balance
  - neatlogs: green dot "Tracing on" / red dot "Tracing off"
  - Bedrock: model short name
  - Click → Settings › System.

### Top header
- Left: breadcrumb (`Campaigns / Acme Security / Run`) with page title.
- Center-right: search button "Search or jump to… ⌘K" (opens Command palette).
- Right: live indicator when any run is active (pulsing dot + "1 running"), then primary button **New campaign** (`Plus`). No notification bell: there are no accounts, and live events already appear in the run timeline.

### ⌘K command palette
Groups: Campaigns (jump), Leads (search by company/contact), Actions (New campaign, Approve next, Open latest report, Toggle replay/live, Open neatlogs trace), Navigation.

## 5. Screens

### 5.1 Campaigns — `/campaigns` (home)

Top row — 4 KPI cards (3 cols each). Each shows value, small label, delta vs previous run, and a `Info` tooltip naming the source ("from budget ledger, reconciled with Crustdata usage"):

| Card | Value example | Delta |
| --- | --- | --- |
| Qualified leads | `38` | `+12 vs last run` |
| Awaiting approval | `9` | link "Review" |
| Cost per qualified lead | `8.6 credits` (mono) + `≈ $0.31` | `−41% vs v0` (green) |
| Verifier pass rate | `92%` | `3 redrafts, 1 dropped` |

Table "Campaigns" columns: Seller (favicon + name + domain mono), Status badge, Progress (9-segment stage bar), Leads (`18 / 20`), Credits (`171 / 250`, mono, red when > 90%), Mode (`Replay`/`Live` chip), Started (relative time, tooltip absolute), Trace (`ExternalLink` icon to neatlogs). Row click → `/campaigns/[id]`.

Empty state (centered in table area):
- Title: "No campaigns yet"
- Body: "Paste your company's website. SignalSDR finds who buys from you, researches them, and drafts emails it can prove."
- Buttons: **New campaign**, secondary "Try the demo fixture (replay, 0 credits)".

### 5.2 New campaign — right drawer (480px)

Title "New campaign". Fields:
1. Company name* (input)
2. Website* (input, `https://` prefix hint; validates URL on blur: "Enter a full URL like https://acme.com")
3. What it does (optional textarea, 3 rows, helper "Helps if your site is thin. One sentence is enough.")
4. Leads to find (number stepper 5–50, default 20)
5. Data mode (segmented): **Replay** "0 credits, cached data" / **Live** "Uses Crustdata credits"
6. Credit cap (number, default 250) + live estimate line: "Estimated ~170 credits for 20 leads at your account's prices" (from `/api/estimate`)
7. Sending: locked row "Demo sends only — mail goes to Mailpit" with `Lock` icon
8. Advanced (collapsed): Fault injection checkboxes (`crust_429`, `empty_people`, `llm_bad_json`, `crust_403_fields`, `poisoned_page`), Kill after (select node)

Footer: Cancel (ghost) · **Start campaign** (primary, disabled until valid). On submit: drawer closes, navigate to the run view, toast "Campaign started".

### 5.3 Campaign run — `/campaigns/[id]` (the demo screen)

Header row: seller favicon + name, domain (mono), status badge, actions: Pause/Resume (secondary), "Open trace" (`ExternalLink`, neatlogs), "Report" (secondary).

**Stage stepper** (full width card): Plan · Product · Buyers · ICP check · Accounts · Emails · Verify · Approval · Send. Each step: icon state (done `Check`, running spinner, waiting `Hand` amber, skipped `Minus`, failed `X` red), label, small count ("6 customers", "60 → 24 kept", "18 contacts").

**Gate panel** (appears inline under the stepper when waiting; never a modal):

ICP check (gate 1), two columns:
- Left "Inferred buyers": editable chip groups — Industries, Company size, Countries, Funding stage; Roles list with kind badge (Economic buyer / Champion) and title variants. Each chip removable; "Add" inline input.
- Right "Why we think so": table of the seller's real customers found on its site — Company, Industry, Size, Country, Source (link to the page it was found on). Note under table: "Derived from 6 customers named on acme.com/customers".
- Footer bar: microcopy "Nothing is enriched until you approve. Estimated after approval: ~150 credits." Buttons: Reject and stop (ghost danger) · Save edits · **Approve and continue** (primary).

Approval gate (gate 2): banner "12 emails are ready for review" + **Review emails** → Leads tab filtered to Awaiting approval.

**Main area (8 cols) — tabs:** Activity · Leads · Companies · Seller brief

Activity timeline (default tab while running): newest first, filter chips by type. Row = time (mono) · agent chip · icon · message · credits delta (mono) · "Trace" link.

| Event | Icon | Color | Example message |
| --- | --- | --- | --- |
| `replan.*` | `GitBranch` | info | "Planner widened ICP: added 'IT Services and IT Consulting' (14 companies, needed 20)" |
| `fallback.*` | `CornerDownRight` | neutral | "No CISO in company profile for Finly → person search found Head of Security" |
| `recovery.*` | `RotateCcw` | warning | "Crustdata 429 on /person/search — waited 3s, retried, succeeded" |
| `recovery.explain_retry` | `SearchCheck` | warning | "Person search empty; explain named the title filter; semantic retry found 2" |
| `verify.redraft` / `verify.drop` | `FileWarning` / `FileX` | warning / danger | "Removed unsupported claim 'raised $20M' (no source) — redraft passed" |
| `policy.*` / `security.*` | `ShieldCheck` | neutral | "Quarantined instruction-like text on partner page" |
| `halt.*` | `OctagonX` | danger | "Paused: 90% of credit cap used. Resume to finish 4 paid leads." |

**Right rail (4 cols):**
- Budget card: `171 / 250 credits` with bar, list by step (Seller, Buyers, Accounts, Contacts, Emails), cache hit rate, "Reconciled with Crustdata ✓" line.
- Run facts: mode, N, model (strong/fast), started, duration, campaign id (mono, copy button).
- Recoveries: counts by type (rate limits 2, explain retries 3, redrafts 3, resumed 1).
- Links: neatlogs trace(s), Entire checkpoint (optional), Mailpit.

### 5.4 Leads table — run tab and `/approvals`

Toolbar: search (`/` focuses), filter dropdowns (Status, Email confidence, Verifier, Role), column toggle, count "24 leads".
Bulk bar (replaces toolbar when rows selected): "5 selected" · **Approve 5** · Reject · Clear. If selection includes guessed emails: inline note "2 guessed emails need individual approval and were left out".

Columns: ☐ · Company (name 500 + domain mono 12) · Contact (name + title muted) · Role (badge: Buyer / Champion) · Email (masked mono `r***@finly.io` + confidence badge Verified/Likely/Guessed) · Fit (0–100 mono + 48px bar) · Verifier (Passed / Redrafted ×1 / Downgraded / Dropped) · Status (Awaiting approval / Approved / Sent / Replied / Opted out / Rejected) · Updated (relative).

Selected row: `--accent-soft` bg + 2px accent left bar. Row click or Enter → lead drawer.

### 5.5 Lead drawer (560px, right, non-blocking)

Header: contact name (14/600), "Head of Security · Finly" muted, prev/next buttons (`ChevronUp`/`ChevronDown`, keys K/J), close (`X`, Esc).

Body sections (scroll):
1. Summary strip: status badge, email (mono) + confidence badge, role badge, fit score, "Found via: person search after explain retry".
2. **Why this account** — 3–5 sentences with citation chips `[1]` `[2]` (accent-soft). Hover/focus highlights the matching evidence card.
3. **Why now** — bullets, each with date (mono) and citation chip.
4. **Email sequence** — tabs: Email 1 · Follow-up · Follow-up 2, each tab shows send timing ("Day 3" / demo "in 2 min"). Subject + body with citation chips inline. "Edit" toggles inline textarea; Save / Cancel. Word count + opt-out line check.
5. **Verifier** — checklist with pass/fail icons: claims supported (5/5), evidence ≤ 90 days, name/title match profile, opt-out line present, no injected text, length OK. Redraft history collapsed ("Redrafted once: removed 'raised $20M'").
6. **Evidence** — cards: fact, source domain + type (Crustdata / Web), date, confidence; `ExternalLink`.
7. **Audit** — who/when for approve/edit/reject, trace link.

Sticky footer: Reject (ghost, danger text) · Edit · **Approve** (primary). For guessed emails: warning callout "This address was built from the company's email pattern and is not verified" + required checkbox "I've checked this address" before Approve enables.

### 5.6 Outbox — `/outbox`

Banner (info): "Demo mode: every email goes to Mailpit at localhost:8025. Nothing reaches real inboxes." + "Open Mailpit".
Table: To (masked mono) · Company · Step (1/2/3) · Status (Sent / Scheduled · in 4m / Cancelled — replied / Cancelled — opted out / Failed — retrying) · Time · actions (`MoreHorizontal`: View email, Simulate reply (demo), Cancel follow-ups).
Empty: "Nothing sent yet. Approved emails appear here and send within a minute."

### 5.7 Reports — `/reports` and `/reports/[id]`

- KPI row: Credits per qualified lead · LLM cost per lead · Duration · Verifier pass rate · Recoveries.
- "Credits by step" horizontal bar chart (sorted, labeled values).
- "Where contacts came from" horizontal bar (enrich people / person search / explain retry / guessed / none).
- **Compare runs** card: baseline select (e.g. v0) vs this run; table Metric · Baseline · This run · Change (green/red arrows, mono). This is the before/after evidence for judges.
- Recoveries table (type, count, example message, trace link).
- Reconciliation: "Ledger 171.4 credits · Crustdata usage 171.4 credits ✓".
- Actions: Export Markdown (writes `reports/<id>.md`), Open neatlogs trace.

### 5.8 Settings — `/settings` (left sub-nav)

- System: Crustdata balance + table of endpoints we use (path mono, Enabled/Disabled badge, your price, RPM) from `/account/endpoints`; Bedrock profile/region/models (read-only); neatlogs status.
- Defaults: data mode, N, credit cap, follow-up gaps (demo minutes / real days).
- Sending: demo lock (read-only while DEMO_MODE=true), daily cap, per-domain cap, from address.
- Suppression list: table + add input (email or domain) + remove.
- Data: purge a campaign — select campaign, inline confirm by typing its id, **Delete campaign data** (danger). No modal.

## 6. States and micro-copy

- Loading: skeleton rows (8) for tables, skeleton blocks for KPI cards. No full-page spinners.
- Errors (inline banner in the affected card, always with next action):
  - 402: "Crustdata is out of credits. Campaign paused. Add credits or lower the number of leads, then Resume."
  - Backend down: "Can't reach the SignalSDR API at localhost:8000. Start it with `python cli.py serve`."
  - Replay miss: "This step isn't in the replay cache. Switch this campaign to Live or re-run with a cached company."
- Toasts (bottom-right, max 1 visible, 4s): only for completed async actions, with Undo where possible ("Approved 5 emails · Undo").
- All buttons use verbs: "Approve and continue", not "OK".

## 7. Keyboard and accessibility

| Key | Action |
| --- | --- |
| ⌘K / Ctrl K | Command palette |
| N | New campaign drawer |
| / | Focus table search |
| J / K | Next / previous row (also inside drawer) |
| Enter | Open selected row |
| A / R / E | Approve / Reject / Edit in lead drawer |
| Esc | Close drawer |
| ? | Shortcuts list (in a drawer) |

- Visible focus ring on every interactive element. Tab order follows layout. Drawer traps focus while open and returns focus to the row on close.
- Contrast ≥ 4.5:1 for text (subtle text is `#71717A`, not lighter).
- Tables use real `<table>` semantics; sortable headers are buttons with `aria-sort`.
- Live run updates announce via `aria-live="polite"` region for gate changes only (not every event).

## 8. Backend API (how the UI talks to the agents)

The UI drives the real system: same LangGraph graph, SQLite DB, Crustdata client and neatlogs tracing built in Phases 1–7. **All backend work is specified in `10_UI_BACKEND_INTEGRATION.md`** — run manager (each campaign runs as a `cli.py` child process), DB additions (`events`, `campaign_stages`, `runs`, `gate_decisions`), SSE stream, gates, every endpoint mapped to existing code, response models, and acceptance checks.

Frontend-side rules:
- Base URL from `NEXT_PUBLIC_API_BASE` (`http://127.0.0.1:8000/api`). SSE connects directly to the API, not through a Next proxy.
- Types are generated from `openapi.json` into `web/lib/api-types.ts` (`npm run gen:api`). Never hand-write a type the schema already has.
- No mock data anywhere in `web/`. If an endpoint doesn't exist yet, build it (per `10`) before the screen.
- Until U5 is done, keep the Phase 7 approval page working; delete it only after the new Approvals screen passes its acceptance.

## 9. Frontend structure

```
web/
├── app/
│   ├── layout.tsx                # shell: sidebar + header + Toaster + CommandMenu
│   ├── campaigns/page.tsx
│   ├── campaigns/[id]/page.tsx   # run view
│   ├── approvals/page.tsx
│   ├── outbox/page.tsx
│   ├── reports/page.tsx
│   ├── reports/[id]/page.tsx
│   └── settings/page.tsx
├── components/
│   ├── shell/ (Sidebar, Header, SystemStatus, CommandMenu)
│   ├── ui/ (shadcn, restyled)
│   ├── campaign/ (StageStepper, IcpGate, ActivityTimeline, BudgetCard, RunFacts, NewCampaignDrawer)
│   ├── leads/ (LeadsTable, BulkBar, LeadDrawer, EmailSequence, VerifierChecklist, EvidenceList, CitationChip)
│   ├── outbox/ (OutboxTable)
│   ├── reports/ (KpiCard, CreditsByStep, ContactSources, CompareRuns)
│   └── common/ (StatusBadge, ConfidenceBadge, EmptyState, ErrorBanner, Mono, RelativeTime)
├── lib/ (api.ts, api-types.ts, sse.ts, format.ts, keys.ts)
└── styles/tokens.css
```

## 10. Build steps for Cursor (one chat per step, commit after each)

Timebox the UI to about 6–8 hours. **Gate 2 evidence (v1 comparison, chaos runs, cfo.ai plan) is worth more points than UI polish** — if the UI runs long, stop after U4 and finish Gate 2 first, then continue.

| Step | Scope | Acceptance |
| --- | --- | --- |
| U0 | Audit existing code → `docs/ui/BACKEND_MAP.md` (`10` §1). No code changes | Map exists; you've read it |
| U1 | Backend: DB additions + `record_event`/`set_stage` wired into every agent, run manager, `run-campaign`/`resume`/`serve` CLI, read-only endpoints (status, campaigns, campaign, events, stream, leads, lead, seller, companies), pydantic schemas, tests (`10` §2–6, §10) | `pytest` passes; `curl /api/campaigns` returns real data; a CLI run writes events + stages to the DB |
| U2 | Next.js app in `web/`: tokens, Geist fonts, shell (sidebar with live system status, header, ⌘K), common components (StatusBadge, ConfidenceBadge, EmptyState, ErrorBanner, Mono, RelativeTime, Skeletons), `api.ts`, generated types | Shell matches §3–4 at 1440 and 1280 px; Tab shows focus on every control; system status shows real Crustdata balance |
| U3 | Campaigns list + KPI cards + New campaign drawer (estimate, chaos, kill-after) + `POST /campaigns`, `/estimate` | Start a replay campaign from the UI; it appears in neatlogs; row updates live |
| U4 | Run view: stage stepper, inline ICP gate (edit/approve/reject), activity timeline over SSE, budget + run facts + recoveries rail, pause/resume, crashed state with Resume | ICP approval in UI resumes the graph; kill-after run shows Crashed then resumes (`10` §11 items 1–4) |
| U5 | Leads table (filters, bulk bar, J/K) + lead drawer (citations ↔ evidence, email sequence with inline edit, verifier checklist, audit, guessed confirm) + `/approvals` + email endpoints | Approve from drawer → email in Mailpit; bulk approve skips guessed (`10` §11 item 5) |
| U6 | Outbox (simulate reply, cancel follow-ups), Reports (KPIs, credits by step, contact sources, compare runs, reconciliation, export), Settings (system, defaults, sending, suppression, purge) | v0 vs v1 comparison on one screen (`10` §11 item 6) |

Prompt template for each step:

> Read docs/09_UI_SPEC.md, docs/10_UI_BACKEND_INTEGRATION.md and docs/ui/BACKEND_MAP.md (plus docs/02, 03, 05 for data and rules). Implement step U<n> only. Backend: reuse existing functions, never duplicate agent logic, spawn runs via the run manager. Frontend: tokens in §3 exactly, shadcn/ui restyled to them, lucide icons, Geist fonts, no modals (right drawer per §1), focus ring and keyboard per §7, generated API types, loading skeletons, empty states and error banners with the copy in §6, no mock data. Run the tests and the step's acceptance check from §10; stop and tell me exactly what to verify by hand. Append a dated entry to hackathon.md. Do not commit; I will commit.

### Quality bar (check before saying a step is done)

- Nothing uses default shadcn colors, indigo, purple gradients, glassmorphism, emoji, or rounded-2xl cards with big shadows.
- Every number that matters is mono and tabular; every table column is aligned (numbers right-aligned).
- Every list has an empty state with a next action; every async card has a skeleton and an inline error.
- Text never truncates without a tooltip with the full value.
- Same spacing everywhere: 24px page padding, 16px card padding, 16px gaps, 40px table rows.
- Works at 1280px wide without horizontal page scroll (tables scroll inside their card).

## 11. What not to build

- No login, accounts, teams, billing pages, onboarding tours.
- No landing page, hero sections, gradients, stock images, illustrations, carousels.
- No dark mode, no charts beyond the bar charts listed.
- No notification center; events live in the timeline.
