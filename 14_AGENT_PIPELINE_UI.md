# 14 — Agent Pipeline UI (live, animated agent visibility)

Replaces the current "Agent pipeline" row on the campaign detail page. **Build the canvas layout in §7.** §1 is the fallback layout used on mobile. Goal: anyone watching the screen (judges, a founder) can see the planner create jobs, hand each one to a sub-agent, each agent doing its work, and data moving from one agent to the next. Without reading a log.

Reference implementation: `AgentPipeline.tsx` (attached, no dependencies besides React). Use it as the starting point and write `agent-pipeline.css` from §6 of this file. Hard rules from `docs/09` and `.cursor/rules/signalsdr-ui.mdc` still apply: our tokens, Geist, borders not shadows, no gradients/glass/purple/emoji, no modals, no mock data in `web/`.

---

## 1. Layout

```
┌ Agent pipeline ─────────────────────────────── 3/5 agents done · 02:14 elapsed · [Amazon Bedrock] ┐
│ ┌ PLANNER ──────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ (orbit)  Planner  [● Working]                        Jobs                                     │ │
│ │  ◉ ·5    Splits the campaign into 5 jobs...          ✓ 1 Understand the product   Product R.  │ │
│ │          LIVE  Handed "Find buyers" to Buyer F▌      ◐ 2 Find buyers              Buyer Finder│ │
│ │          Assigned Find buyers to Buyer Finder        ○ 3 Research accounts        Account R.  │ │
│ └───────────────────────────────────────────────────────────────────────────────────────────────┘ │
│      │  dispatch bus (packet travels from planner → down into the agent that just started)        │
│      └──────────┬──────────────┬──────────────┬──────────────┬──────────────┐                     │
│ ┌ Product ─┐ ═► ┌ Buyer ────┐ ─ ─ ┌ Account ──┐ ─ ─ ┌ Writer+V ─┐ ─ ─ ┌ Sender ──┐                 │
│ │ icon name│    │           │     │           │     │           │     │          │                 │
│ │ [Done] 0:42   │ [Working] │     │ [Queued]  │     │           │     │          │                 │
│ │ ┌scene──┐│    │ ┌scene──┐ │     │ ┌scene──┐ │     │ ┌scene──┐ │     │ ┌scene─┐ │                 │
│ │ └───────┘│    │ └───────┘ │     │ └───────┘ │     │ └───────┘ │     │ └──────┘ │                 │
│ │ LIVE text▌    │           │     │           │     │           │     │          │                 │
│ │ 3 facts  │    │ 8 of 24   │     │           │     │           │     │          │                 │
│ │ ▬▬▬▬▬▬▬▬ │    │ ▬▬▬───── │     │           │     │           │     │          │                 │
│ └──────────┘    └───────────┘     └───────────┘     └───────────┘     └──────────┘                 │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
═► = handoff connector with moving packets      ─ ─ = not reached yet
```

- **Planner panel** (full width): orbit glyph (72px) | name, status, role line, live stream line, "Assigned X to Y" | job checklist.
- **Dispatch bus** (32px tall): vertical stub under the planner glyph, horizontal line, one vertical drop into the top of each agent column.
- **5 agent cards** in a 5-column grid, gap 24px, connected by handoff connectors.
- Each card, top to bottom: icon + name + one-line role · status pill + elapsed time · **scene** (80px tall, the animated part) · stream line (3 lines max, mono) · count label (+ "Review drafts" link when waiting) · 4px progress bar.
- Responsive: ≥1100px as above. 641–1099px: bus + grid sit in a horizontally scrolling container (min-width 1000px), planner panel stays full width and its job list wraps under. ≤640px: one column, bus hidden, connectors turn vertical.

## 2. Status states (same everywhere)

| Status | Pill text | Card | Scene | Stream label |
| --- | --- | --- | --- | --- |
| idle | Queued | bg `#FAFAFA`, scene at 55% opacity | static, hollow/dashed shapes | "Latest" + "Waiting for the planner to hand over this job." |
| running | Working | border accent `#2563EB`, icon box accent-soft | **animated** | "● Live" (or "● Streaming" when real tokens) + typewriter + blinking caret |
| waiting | Needs you | border warning `#B45309` | static, warning shield | "Latest" + "Review drafts" link to `/approvals` |
| done | Done | normal border | static final state (filled shapes, check) | "Latest", full text |
| failed | Failed | border danger `#B91C1C` | static, danger mark | "Latest" + recovery message if any |

Pill = dot + text, never color alone. Running pill dot has a soft pulsing ring.

## 3. Animations (the important part)

All motion is CSS keyframes or SVG `animateMotion`. It only runs while the agent is `running`. With `prefers-reduced-motion: reduce`, nothing moves and every scene shows its resting state.

### 3.1 Planner orbit: "creating sub-agents"
- SVG 72×72: dashed orbit ring r=28, hub circle r=15 with the planner glyph, **5 seed dots on the orbit, one per sub-agent**, colored by that agent's status (idle hollow grey, running accent and bigger r=5 with pulse, waiting warning, done success, failed danger).
- While any agent runs: the seed group rotates, 12s per turn, linear. The running seed has a dashed **spoke** from the hub to it with flowing dashes (the planner "talking" to it).
- Job checklist rows: icon (○ idle, spinning ¼ arc running, ✓ done, ⏸ waiting, ✕ failed) · number · job · owner agent. Running row gets accent-soft background.

### 3.2 Dispatch bus: "assigning a job"
- When an agent's status changes to `running`, an 8px accent packet (with a 3px accent-soft halo ring) travels: down from the planner glyph → along the bus → down the drop into that card. 1.3s, `cubic-bezier(.4,0,.2,1)`, then disappears.
- The running agent's drop line is 2px accent; done drops are accent; waiting is warning; idle is grey.

### 3.3 Handoff connectors: "data moving between agents"
- Between card N and N+1, 24px wide line, vertically aligned with the card icons.
- `idle`: dashed grey. `done` (N done, N+1 started): solid accent. `flow` (N done or running and N+1 running): solid accent + **3 packets** (6px dots) moving left→right, 1.2s linear, staggered 0 / 0.4 / 0.8s, fading in and out at the ends.

### 3.4 Agent scenes (SVG viewBox 200×80, inside a bordered 80px box)

| Agent | Picture | Running animation | Data that drives it |
| --- | --- | --- | --- |
| **Product Researcher** | Mini browser window (3 dots, text lines, image block) with 3 "fact" pills to its right, linked by short lines | A 2px accent **scan bar sweeps** down the page (1.6s, ease-in-out, alternate). Unfound pills are dashed and softly pulse. Found pills fill accent-soft with the fact text inside (mono 8.5px, max 12 chars) | `items` = product facts found, `progress.done` |
| **Buyer Finder** (discover) | 10×3 grid of dots = companies considered | Grey dots **wave** (opacity 0.35→1, 1.8s, 60ms delay per dot) while a vertical accent **filter line sweeps** left→right (2.2s linear). Kept companies are solid accent | `progress.total` = considered (cap 30), `progress.done` = kept |
| **Your list** (list mode) | Same grid but **squares** = rows of the user's list | Same wave + sweep | `progress.total` = list rows, `progress.done` = matched |
| **Account Researcher** | Company node (building glyph) in the center, 6 person nodes on an ellipse, edges between | Center emits an expanding **radar ring** (r 13→~29, fade out, 1.8s). Edges to people not found yet are dashed with **flowing dashes** (stroke-dashoffset, 1s linear). Found people turn solid accent with a filled dot | `progress.done` = contacts found (cap 6) |
| **Writer + Verifier** | Document with a "To" chip and 5 text lines → arrow → shield | Text lines **type in** left to right (scaleX 0→1, 2.8s, 0.35s stagger, loop). A packet **hops** along the arrow from doc to shield (1.4s). A dashed ring **spins** inside the shield (verifier checking). Done: green shield with ✓. Waiting: amber shield with clock. Caption "3/6 checked" | `progress` = drafts checked / total |
| **Sender** | Outbox tray → curved dashed path → inbox envelope with a count badge | 3 **paper planes** fly along the curve (`<animateMotion rotate="auto">`, 2.4s, staggered 0.8s, fade in/out). Path turns solid accent once anything is sent. Badge shows sent count (accent while running, success when done) | `progress.done` = sent |

### 3.5 Stream line: "you can see it think"
- Mono 12/18px, max 3 lines, under the scene. Label "● Live" with pulsing dot while running.
- When `detail` changes while running, it **types out** (2 chars every 22ms) with a blinking accent block caret (1s, steps).
- If the API sends `stream` (real Bedrock token stream over SSE), show it as it arrives (no typewriter), label "● Streaming", keep the last ~150 chars.
- Screen readers get the full message once through a visually hidden `aria-live="polite"` span, never char by char.

### 3.6 Other motion
- Progress bar width transitions 0.6s. Running with no total → indeterminate bar (30% chunk sliding, 1.4s).
- Card border color transitions 0.2s when status changes.
- Nothing else moves. No bouncing, no confetti, no page-load choreography.

## 4. Data contract

`GET /api/campaigns/{id}/pipeline` returns 6 agents in this shape (extend what's already there):

```ts
{
  target_mode: "discover" | "list",
  model: string | null,          // e.g. "Amazon Bedrock"
  agents: Array<{
    key: "planner" | "product" | "buyers" | "accounts" | "writer" | "sender",
    status: "idle" | "running" | "waiting" | "done" | "failed",
    detail: string | null,        // latest founder-readable event message (event_messages.py, redacted)
    stream: string | null,        // optional live token stream text
    count_label: string | null,   // "8 of 24 kept", "6 passed", "4 sent"
    progress: { done: number, total: number | null } | null,
    items: string[] | null,       // product facts / company names, max 3-6 short strings
    started_at: string | null,
    updated_at: string | null
  }>
}
```

- Fill `progress` and `items` from state that already exists (product facts, companies kept/considered, contacts found, drafts verified, emails sent). Never invent numbers; leave `null` and the scene shows its neutral state.
- Planner `detail` should say what it just assigned: add event templates like `planner.assigned`: "Handed \"{task}\" to {agent}."
- Poll every 2s while campaign status is running or waiting (switch to `/stream` SSE if cheap). Map snake_case to the component's camelCase props in `web/lib/api.ts`.
- Clicking a card calls `onSelect(key)` → opens the existing Activity panel filtered to that agent.

## 5. Accessibility
- Each card has a full-card transparent `<button>` (aria-pressed, aria-label "Buyer Finder: Working. Show its activity") with a 2px accent focus ring at 2px offset; card content sits above it with `pointer-events: none` except the "Review drafts" link.
- All SVG scenes are `aria-hidden`; meaning is carried by pill text, count label and stream text.
- `prefers-reduced-motion`: CSS `animation: none` for everything inside `.ap`, and the component skips SMIL planes and dispatch packets.

## 6. CSS to write (`web/components/campaign/agent-pipeline.css`, import once in `app/layout.tsx`)

Hard-code our token values inside `.ap` (do not reference shadcn HSL vars):

```css
.ap{--ap-bg:#FAFAFA;--ap-surface:#FFFFFF;--ap-muted:#F4F4F5;--ap-border:#E4E4E7;--ap-border-strong:#D4D4D8;
--ap-text:#18181B;--ap-text-muted:#52525B;--ap-text-subtle:#71717A;--ap-accent:#2563EB;--ap-accent-soft:#EFF6FF;
--ap-success:#15803D;--ap-success-soft:#F0FDF4;--ap-warning:#B45309;--ap-warning-soft:#FFFBEB;
--ap-danger:#B91C1C;--ap-danger-soft:#FEF2F2;--gap:24px;
--ap-sans:"Geist","Geist Sans",ui-sans-serif,system-ui,sans-serif;--ap-mono:"Geist Mono",ui-monospace,Menlo,monospace}
```

Positions the bus needs (5 columns, gap `--gap`):

```css
/* centre of column i */
left: calc((100% - 4 * var(--gap)) / 5 * (var(--i) + 0.5) + var(--gap) * var(--i));
/* planner glyph centre = 1px border + 16px padding + 36px = 53px */
```

Keyframes (names used by the reference TSX):

```css
@keyframes ap-dispatch{0%{left:53px;top:0;opacity:0}10%{opacity:1}25%{left:53px;top:16px}
  80%{left:var(--to);top:16px}100%{left:var(--to);top:32px;opacity:0}}   /* --to = column centre */
@keyframes ap-pkt{0%{left:-3px;opacity:0}15%,85%{opacity:1}100%{left:calc(100% - 3px);opacity:0}}
@keyframes ap-pkt-v{0%{top:-3px;opacity:0}15%,85%{opacity:1}100%{top:calc(100% - 3px);opacity:0}}
@keyframes ap-pulse{0%{box-shadow:0 0 0 0 rgba(37,99,235,.45)}100%{box-shadow:0 0 0 6px rgba(37,99,235,0)}}
@keyframes ap-blink{50%{opacity:0}}
@keyframes ap-scan{from{transform:translateY(0)}to{transform:translateY(46px)}}
@keyframes ap-slot{0%,100%{opacity:.5}50%{opacity:1}}
@keyframes ap-wave{0%,100%{opacity:.35}50%{opacity:1}}
@keyframes ap-sweep{from{transform:translateX(0)}to{transform:translateX(152px)}}
@keyframes ap-ring{from{transform:scale(1);opacity:.6}to{transform:scale(2.2);opacity:0}}
@keyframes ap-dash{from{stroke-dashoffset:6}to{stroke-dashoffset:0}}
@keyframes ap-type{0%{transform:scaleX(0)}35%,85%{transform:scaleX(1)}100%{transform:scaleX(1);opacity:.4}}
@keyframes ap-hop{0%{transform:translateX(0);opacity:0}15%,80%{opacity:1}100%{transform:translateX(28px);opacity:0}}
@keyframes ap-spin{to{transform:rotate(360deg)}}
@keyframes ap-indet{from{transform:translateX(-100%)}to{transform:translateX(340%)}}
@media (prefers-reduced-motion:reduce){.ap *{animation:none!important;transition:none!important}}
```

Rules that matter:
- Animations only under `.ap-anim` (added to the scene SVG when running) or on running elements, e.g. `.ap-anim .ap-scan{animation:ap-scan 1.6s ease-in-out infinite alternate}`.
- SVG elements that scale or rotate need `transform-box: fill-box; transform-origin: center` (or `left center` for typing lines). The orbit group uses `transform-origin: 36px 36px`.
- Stagger with `animation-delay: calc(var(--d) * 60ms)` etc.; the TSX sets `--d` / `--i` inline.
- SVG colors through classes (`fill: var(--ap-accent)`), not presentation attributes, because `var()` in attributes is unreliable.

## 7. Layout v2: n8n-style canvas + inspector (USE THIS, overrides §1 layout)

The horizontal row is replaced by a **vertical workflow canvas** with a **right-side inspector**, like n8n. Animations (§3), states (§2), data (§4) and CSS tokens (§6) stay the same; the cards become canvas nodes.

### 7.1 Page layout (campaign detail, "Run" section)

```
┌ Campaign header (name, status, send mode, Email style, Your list badge) ────────────────────────┐
├──────────────────────────────── canvas (flex 1) ─────────────────────┬── Inspector 400px ───────┤
│  · · · · · · · · · · · dot grid · · · · · · · · · · · · · · · · ·    │ Account Researcher       │
│                      ┌──────────────┐                                 │ [● Working] 01:12        │
│     [Bedrock]╌╌╌╌╌╌╌╌│   Planner    │╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┐  dispatch    │ ┌ scene 160px ────────┐  │
│                      └──────┬───────┘                  │  bus (right)│ └─────────────────────┘  │
│                      ┌──────▼───────┐                  │              │ LIVE                     │
│                      │Product Resrch│◄─────────────────┤              │ Researching Anark: hiring│
│                      └──────┬───────┘                  │              │ and tech stack▌          │
│   [Crustdata]╌╌╌╌╌╌╌╌┌──────▼───────┐                  │              │ Tools                    │
│              ╌╌╌╌╌╌╌╌│ Buyer Finder │◄─────────────────┤              │ Crustdata 14 calls ·     │
│              ╌╌╌╌╌╌╌╌└──────┬───────┘                  │              │ 9 cached · 38 credits    │
│                      ┌──────▼───────┐                  │              │ Output                   │
│              ╌╌╌╌╌╌╌╌│Account Resrch│◄─────────────────┤              │ 4 contacts (table)       │
│                      └──────┬───────┘                  │              │ Activity                 │
│     [Bedrock]╌╌╌╌╌╌╌╌┌──────▼───────┐                  │              │ 23:41:02 Found VP Eng…   │
│                      │Writer+Verifier│◄────────────────┤              │ 23:40:51 Researching…    │
│                      └──────┬───────┘                  │              │                          │
│                      ┌──────▼───────┐  human gate      │              │ [Follow live ✓]          │
│                      │ You approve  │                  │              │                          │
│                      └──────┬───────┘                  │              │                          │
│  [Gmail SMTP]╌╌╌╌╌╌╌╌┌──────▼───────┐                  │              │                          │
│                      │    Sender    │◄─────────────────┘              │                          │
│                      └──────────────┘                                 │                          │
│  [Fit] [Follow live]                                  (controls)      │                          │
└──────────────────────────────────────────────────────────────────────┴──────────────────────────┘
```

- Canvas height 720px (min), white surface `#FFFFFF`, 1px border, radius 8, **dot grid** background (SVG pattern, dots `#E4E4E7`, 16px spacing). No gradients.
- Use **React Flow** (`@xyflow/react`, pin the version) for the canvas: custom node types, custom edges, `Background variant="dots"`, `Controls` (fit + zoom only). Settings: `nodesDraggable` true (fun to play with), `nodesConnectable` false, `elementsSelectable` true, `zoomOnScroll` false and `panOnScroll` false (so the page still scrolls), `panOnDrag` true, `minZoom 0.5`, `maxZoom 1.25`. Fixed positions, computed in one `layout()` function, no auto-layout library.

### 7.2 Nodes

| Node | Type | Size | Content |
| --- | --- | --- | --- |
| Planner | `agent` (planner variant) | 360×132 | orbit glyph 56px, name, pill, time, 2-line live stream, "Assigned X to Y". Job checklist moves to the inspector |
| 5 sub-agents | `agent` | 300×170 | icon + name + pill + time · scene 64px tall (same SVG scenes, viewBox unchanged) · 1-line live stream · count label + 4px progress |
| You approve | `gate` | 300×64 | person icon, "You approve emails", pill (Queued / Needs you with pulsing warning dot / Approved N), "Review drafts" link when waiting. Writer → Gate → Sender. Makes the human-in-the-loop visible |
| Crustdata, Bedrock, Gmail SMTP | `tool` | 132×40 | small pill-shaped node: icon + name + live counter (calls / tokens / sent). Placed to the left of the agents that use them |

Positions (x, y of top-left; chain centred on x=0):
- Planner (−180, 0). Product (−150, 196). Buyers (−150, 422). Accounts (−150, 648). Writer (−150, 874). Gate (−150, 1100). Sender (−150, 1220).
- Tools at x=−360: Bedrock next to Planner and Writer, Crustdata next to Buyers and Accounts (one node, two edges), Gmail SMTP next to Sender.

### 7.3 Edges

| Edge | From → to | Look | Animated when |
| --- | --- | --- | --- |
| Handoff | agent bottom → next agent top | straight, 1.5px | grey dashed idle · solid accent done · **3 packets** flowing down (`<animateMotion>` along the edge path, 1.2s, stagger 0.4s) when `flow` (§3.3 rule) |
| Dispatch | planner right → each agent right handle | `smoothstep`, rounded corners 12, routed down a vertical lane at x=+190 (the "bus") | 1px grey dashed always; when an agent starts, **one accent packet** travels the whole edge once (1.3s) and the edge stays accent while that agent runs |
| Tool call | tool right → agent left | `bezier`, 1px | dotted grey; while that agent is running AND the tool was called in the last 5s (from events, e.g. `crustdata.call`, `llm.call`, `mail.sent`) the edge turns accent with dashes flowing (stroke-dashoffset) and the tool node's counter ticks |

Edge labels (small, mono 11px, white pill with border) on handoffs only: what was passed, e.g. "3 facts", "8 companies", "6 contacts", "6 drafts", "6 approved". From `count_label` of the upstream agent.

### 7.4 Camera follows the work
- **Follow live** (on by default, toggle in the canvas controls and in the inspector): when an agent changes to `running` or `waiting`, call `setCenter(nodeCenterX, nodeCenterY, { zoom: 1, duration: 600 })`. The user can pan; any manual pan turns Follow live off until they turn it on again.
- **Fit** button: `fitView({ padding: 0.15, duration: 400 })`.
- First render: centre on the running node, or the planner if none.

### 7.5 Inspector (right, 400px, sticky, full canvas height)
Shows the selected node; defaults to the running node while Follow live is on. Clicking a node selects it (2px accent outline on the node).
1. Header: icon, name, role line, status pill, elapsed time.
2. Scene at 2× size (160px tall, same SVG).
3. **Live** stream: full text, mono, scrolls, caret while running (`stream` if present, else typewriter on `detail`).
4. **Tools**: rows per tool used by this agent: calls, cached hits, credits or tokens, last call time. From events / budget ledger. Hide the section when empty.
5. **Output**: what this agent produced, real data only:
   - Product: facts list + named customers.
   - Buyer Finder: kept companies (name, domain, why kept) and dropped count; list mode: matched / not found rows.
   - Account Researcher: contacts table (name, role, company, masked email, confidence badge).
   - Writer + Verifier: drafts with verifier result (passed / redrafted / dropped); "Open in Approvals" link.
   - Sender: sent / scheduled rows with absolute local time; "Open Outbox" link.
   - Planner: the job checklist from §3.1 and the run plan (lead cap, credit estimate, send mode).
6. **Activity**: this agent's events, newest first, `HH:MM:SS` + message.
7. Below 1280px wide the inspector becomes the existing right Sheet (560px), opened by clicking a node.

### 7.6 Mobile (≤ 768px)
No canvas. Render the nodes as the vertical stacked cards from §1 (≤640 rules), gate and tools shown as small rows between cards; tapping a card opens the inspector Sheet.

### 7.7 Why this layout
Vertical reads top to bottom like a story (planner → research → people → emails → you → send). The canvas shows the topology judges care about: one planner orchestrating 5 sub-agents, a human gate, and the three real integrations lighting up as they're used. The inspector gives depth without cluttering the canvas.

## 8. Done when
- A real run shows each card go Queued → Working → Done in order, a dispatch packet on every start, flowing packets on every handoff, writer card turns "Needs you" with "Review drafts" at the email approval gate.
- List-mode campaign shows "Your list" with square dots.
- Reduced motion: no movement, everything still readable.
- Canvas: camera follows the running node; dispatch packet on every start; handoff packets with labels; tool edges light up on real calls; gate node turns "Needs you"; inspector shows real Tools / Output / Activity for the selected node.
- 1440px (canvas + inspector), 1024px (canvas + Sheet) and 390px (stacked cards) look right, no page-level horizontal scroll.
- Short screen recording of one run saved for the demo video; dated entry in `hackathon.md`.
