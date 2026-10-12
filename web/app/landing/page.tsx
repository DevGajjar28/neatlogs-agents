import Link from "next/link";
import type { ReactNode } from "react";
import {
  Calendar,
  Code2,
  Eye,
  GitBranch,
  Lock,
  Mail,
  Radio,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import "./landing.css";

const ECONOMICS = {
  creditsPerLead: "5.31",
  dataPerLead: "$0.27–0.32",
  llmPerLead: "$0.010",
  directPerLead: "$0.28–0.33",
  blendedPerLead: "$0.29–0.34",
  reduction: "64%",
  llmTotal: "$0.10",
  tokens: "56.8k",
  model: "Claude Haiku 4.5",
} as const;

const MARQUEE = [
  "Crustdata",
  "neatlogs",
  "Gmail",
  "Google Calendar",
  "Claude · Bedrock",
  "Entire.io",
  "Hunter.io",
  "GitHub",
] as const;

const TRACES = [
  { t: "18:39:12", agent: "product", event: "seller.enriched", ok: true, ms: "1.2s" },
  { t: "18:40:04", agent: "icp", event: "icp.proposed", ok: true, ms: "2.1s" },
  { t: "18:41:18", agent: "research", event: "crustdata.enrich ×10", ok: true, ms: "48s" },
  { t: "18:43:02", agent: "writer", event: "draft.ready · evidence", ok: true, ms: "3.4s" },
  { t: "18:43:41", agent: "verifier", event: "claim.rejected → drop", ok: false, ms: "0.8s" },
] as const;

const AGENTS = [
  { name: "Product", task: "Learn the seller", icon: Search },
  { name: "ICP", task: "Who buys", icon: Users },
  { name: "Research", task: "Find & enrich", icon: Radio },
  { name: "Writer", task: "Draft w/ proof", icon: Sparkles },
  { name: "Verifier", task: "Drop fluff", icon: ShieldCheck },
  { name: "Sender", task: "Policy send", icon: Send },
  { name: "Meeting", task: "Book Meet", icon: Calendar },
] as const;

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)] antialiased">
      {/* —— Hero —— */}
      <header className="lp-spotlight relative isolate overflow-hidden">
        <div className="lp-grid-fade pointer-events-none absolute inset-0" aria-hidden />

        <nav className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-5 py-5 md:px-8">
          <span className="text-[15px] font-semibold tracking-tight">
            ReachPilot
            <span className="ml-1.5 text-[11px] font-medium text-[var(--text-subtle)]">beta</span>
          </span>
          <div className="flex items-center gap-2">
            <a
              href="#economics"
              className="hidden rounded-[6px] px-3 py-1.5 text-[13px] font-medium text-[var(--text-muted)] transition hover:bg-[var(--surface)] hover:text-[var(--text)] sm:inline"
            >
              Economics
            </a>
            <Link
              href="/dashboard"
              className="rounded-[6px] bg-[var(--primary)] px-3.5 py-1.5 text-[13px] font-medium text-[var(--primary-fg)] transition hover:bg-[var(--primary-hover)]"
            >
              Open app
            </Link>
          </div>
        </nav>

        <div className="relative z-10 mx-auto grid max-w-6xl gap-12 px-5 pb-16 pt-8 md:grid-cols-[1.05fr_0.95fr] md:gap-10 md:px-8 md:pb-24 md:pt-12">
          <div className="flex flex-col justify-center">
            <div className="lp-rise inline-flex w-fit items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)]/80 px-2.5 py-1 text-[11px] font-medium text-[var(--text-muted)] backdrop-blur">
              <span className="lp-pulse size-1.5 rounded-full bg-[var(--status-success)]" />
              Autopilot · observed · policy-gated
            </div>
            <h1 className="lp-rise-d1 mt-5 text-[clamp(2.35rem,5.5vw,3.6rem)] font-semibold leading-[1.05] tracking-tight text-[var(--text)]">
              ReachPilot
            </h1>
            <p className="lp-rise-d2 mt-4 max-w-md text-[17px] font-medium leading-snug text-[var(--text)]">
              Autopilot that finds buyers, proves every claim, and sends under your rules.
            </p>
            <p className="lp-rise-d2 mt-3 max-w-md text-[14px] leading-relaxed text-[var(--text-muted)]">
              Multi-agent outbound with real reach — Crustdata research, neatlogs traces, Gmail +
              Calendar under security policy. Measured cost per lead, not a black box.
            </p>
            <div className="lp-rise-d3 mt-7 flex flex-wrap gap-2.5">
              <Link
                href="/campaigns"
                className="inline-flex h-10 items-center rounded-[6px] bg-[var(--accent)] px-4 text-[13px] font-semibold text-white transition hover:bg-[var(--status-info)]"
              >
                Launch campaign
              </Link>
              <a
                href="#system"
                className="inline-flex h-10 items-center rounded-[6px] border border-[var(--border-strong)] bg-[var(--surface)] px-4 text-[13px] font-medium text-[var(--text)] transition hover:bg-[var(--surface-muted)]"
              >
                How it runs
              </a>
            </div>
            <dl className="lp-rise-d3 mt-10 flex flex-wrap gap-x-8 gap-y-3 border-t border-[var(--border)] pt-6">
              <HeroStat k="Credits / lead" v={ECONOMICS.creditsPerLead} />
              <HeroStat k="LLM / lead" v={ECONOMICS.llmPerLead} />
              <HeroStat k="Blended" v={ECONOMICS.blendedPerLead} />
            </dl>
          </div>

          {/* Product mock — neatlogs-style live surface */}
          <div className="lp-rise-d2 lp-chrome relative overflow-hidden rounded-[12px]">
            <div className="flex items-center gap-2 border-b border-[var(--border)] bg-[var(--surface-muted)]/60 px-3 py-2.5">
              <span className="size-2 rounded-full bg-[#fecaca]" />
              <span className="size-2 rounded-full bg-[#fde68a]" />
              <span className="size-2 rounded-full bg-[#bbf7d0]" />
              <span className="ml-2 font-mono text-[11px] text-[var(--text-subtle)]">
                app.reachpilot · campaign / v1-posthog-live1
              </span>
              <span className="lp-live-badge ml-auto rounded-[4px] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--status-success)]">
                LIVE
              </span>
            </div>
            <div className="grid grid-cols-[1fr_0.85fr] gap-0 divide-x divide-[var(--border)]">
              <div className="p-3">
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-subtle)]">
                  neatlogs spans
                </p>
                <ul className="space-y-1.5">
                  {TRACES.map((row) => (
                    <li
                      key={row.t + row.event}
                      className="lp-trace-row flex items-center gap-2 rounded-[6px] bg-[var(--surface-muted)]/70 px-2 py-1.5 font-mono text-[10px]"
                    >
                      <span className="text-[var(--text-subtle)]">{row.t}</span>
                      <span className="truncate font-medium text-[var(--text)]">{row.agent}</span>
                      <span className="min-w-0 flex-1 truncate text-[var(--text-muted)]">
                        {row.event}
                      </span>
                      <span
                        className={
                          row.ok
                            ? "text-[var(--status-success)]"
                            : "text-[var(--status-warning)]"
                        }
                      >
                        {row.ms}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="space-y-3 p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-subtle)]">
                  Unit cost
                </p>
                <CostBar label="Crustdata" value="5.31 cr" pct={64} />
                <CostBar label="LLM · Haiku" value="$0.010" pct={12} accent />
                <CostBar label="Blended" value="$0.29–0.34" pct={78} />
                <div className="rounded-[6px] border border-[var(--border)] bg-[var(--accent-soft)] px-2.5 py-2">
                  <p className="text-[10px] text-[var(--text-muted)]">vs v0 credits</p>
                  <p className="text-[18px] font-semibold tabular-nums text-[var(--accent)]">
                    −{ECONOMICS.reduction}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Marquee */}
        <div className="relative z-10 border-t border-[var(--border)] bg-[var(--surface)]/70 py-4 backdrop-blur">
          <div className="overflow-hidden">
            <div className="lp-marquee-track gap-10 px-5">
              {[...MARQUEE, ...MARQUEE].map((name, i) => (
                <span
                  key={`${name}-${i}`}
                  className="shrink-0 text-[12px] font-medium tracking-wide text-[var(--text-subtle)]"
                >
                  {name}
                </span>
              ))}
            </div>
          </div>
        </div>
      </header>

      {/* —— Bento: why different —— */}
      <section id="system" className="mx-auto max-w-6xl px-5 py-20 md:px-8">
        <div className="max-w-xl">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--accent)]">
            Not another sequencer
          </p>
          <h2 className="mt-2 text-[clamp(1.5rem,3vw,2rem)] font-semibold tracking-tight">
            Governance, observation, and Autopilot — in one control plane
          </h2>
        </div>

        <div className="mt-10 grid auto-rows-fr gap-3 md:grid-cols-6 md:grid-rows-2">
          <Bento
            className="md:col-span-3 md:row-span-2"
            title="Controlled multi-agent"
            body="Parent orchestrator + specialist sub-agents. Each company write/verify is a traced sub-task — not one mega-prompt."
          >
            <div className="mt-6 flex flex-wrap gap-1.5">
              {AGENTS.map((a) => (
                <span
                  key={a.name}
                  className="inline-flex items-center gap-1.5 rounded-[6px] border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-[11px] font-medium text-[var(--text)] transition hover:border-[var(--accent)]/40 hover:bg-[var(--accent-soft)]"
                >
                  <a.icon className="size-3 text-[var(--accent)]" strokeWidth={2} aria-hidden />
                  {a.name}
                </span>
              ))}
            </div>
            <p className="mt-4 flex items-center gap-1.5 text-[11px] text-[var(--text-subtle)]">
              <span className="lp-pulse size-1.5 rounded-full bg-[var(--status-success)]" />
              every step logged in neatlogs
            </p>
          </Bento>

          <Bento
            className="md:col-span-3"
            title="Data observation"
            body="Budget ledger for Crustdata. neatlogs for LLM $. SQLite events for recoveries. One campaign id."
            icon={<Eye className="size-4 text-[var(--accent)]" strokeWidth={1.75} />}
          />

          <Bento
            className="md:col-span-3"
            title="Hard guardrails"
            body="Credit caps, evidence verifier, approve-before-send, mail policy, pause-all, demo locks."
            icon={<ShieldCheck className="size-4 text-[var(--accent)]" strokeWidth={1.75} />}
          />
        </div>
      </section>

      {/* —— Mail + Calendar product panels —— */}
      <section className="border-y border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto grid max-w-6xl gap-0 md:grid-cols-2">
          <IntegrationPanel
            icon={<Mail className="size-5 text-[#ea4335]" strokeWidth={1.75} />}
            iconBg="bg-[#fce8e6]"
            title="Gmail under policy"
            subtitle="Read · write · send — never around security"
            body="Connect the mailbox. Agents draft and deliver only what policy allows: opt-out, rate limits, approve gates, pause-all. Autopilot stays inside the fence."
            chips={["Policy gate", "Approve first", "Pause-all"]}
          />
          <IntegrationPanel
            icon={<Calendar className="size-5 text-[var(--accent)]" strokeWidth={1.75} />}
            iconBg="bg-[var(--accent-soft)]"
            title="Calendar Autopilot"
            subtitle="Prospect names a time → Meet link booked"
            body="Google Calendar OAuth books the event and Meet link when replies include a time. No spreadsheet babysitting for scheduling."
            chips={["Meet links", "OAuth scoped", "Reply → book"]}
            borderLeft
          />
        </div>
      </section>

      {/* —— Stack strip —— */}
      <section className="mx-auto max-w-6xl px-5 py-20 md:px-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--accent)]">
              Stack
            </p>
            <h2 className="mt-2 text-[clamp(1.5rem,3vw,2rem)] font-semibold tracking-tight">
              Tools judges can inspect
            </h2>
          </div>
          <a
            href="https://github.com/DevGajjar28/neatlogs-agents"
            className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[var(--text-muted)] transition hover:text-[var(--text)]"
            target="_blank"
            rel="noreferrer"
          >
            <Code2 className="size-3.5" strokeWidth={1.75} aria-hidden />
            Source on GitHub
          </a>
        </div>

        <div className="mt-10 grid gap-px overflow-hidden rounded-[12px] border border-[var(--border)] bg-[var(--border)] sm:grid-cols-2 lg:grid-cols-3">
          <StackCell
            name="Crustdata"
            metric="5.31 credits / lead"
            detail="Live research metered in the ledger"
            icon={<Radio className="size-4" strokeWidth={1.75} />}
          />
          <StackCell
            name="neatlogs"
            metric="$0.010 LLM / lead"
            detail="Option B async traces · never $0 by default"
            icon={<Eye className="size-4" strokeWidth={1.75} />}
          />
          <StackCell
            name="Entire.io"
            metric="Checkpoints"
            detail="Build governance on every meaningful change"
            icon={<GitBranch className="size-4" strokeWidth={1.75} />}
          />
          <StackCell
            name="Gmail"
            metric="Policy send path"
            detail="Read / write / send with locks"
            icon={<Mail className="size-4" strokeWidth={1.75} />}
          />
          <StackCell
            name="Google Calendar"
            metric="Meeting Autopilot"
            detail="Meet links when prospects reply"
            icon={<Calendar className="size-4" strokeWidth={1.75} />}
          />
          <StackCell
            name="Claude · Bedrock"
            metric="Haiku 4.5"
            detail="Write + verify with evidence gates"
            icon={<Sparkles className="size-4" strokeWidth={1.75} />}
          />
        </div>
      </section>

      {/* —— Economics —— */}
      <section id="economics" className="lp-spotlight border-t border-[var(--border)]">
        <div className="mx-auto max-w-6xl px-5 py-20 md:px-8">
          <div className="max-w-xl">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--accent)]">
              Unit economics
            </p>
            <h2 className="mt-2 text-[clamp(1.5rem,3vw,2rem)] font-semibold tracking-tight">
              Real cost. Real surplus.
            </h2>
            <p className="mt-2 text-[14px] leading-relaxed text-[var(--text-muted)]">
              v1-posthog-live1 · N=10. Ledger + neatlogs Option B. Bedrock counted once per lead.
            </p>
          </div>

          <div className="mt-10 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="lp-chrome overflow-hidden rounded-[12px]">
              <div className="border-b border-[var(--border)] bg-[var(--surface-muted)]/50 px-4 py-2.5 font-mono text-[11px] text-[var(--text-subtle)]">
                cost_per_qualified_lead · measured
              </div>
              <table className="w-full text-left text-[13px]">
                <tbody>
                  <EcoRow k="Crustdata data" v={ECONOMICS.dataPerLead} sub="ledger" />
                  <EcoRow k="Bedrock LLM" v={ECONOMICS.llmPerLead} sub="neatlogs B" />
                  <EcoRow k="Direct (data + LLM)" v={ECONOMICS.directPerLead} sub="sum" />
                  <EcoRow
                    k="Blended (+ infra)"
                    v={ECONOMICS.blendedPerLead}
                    sub="4k leads/mo"
                    accent
                  />
                </tbody>
              </table>
            </div>

            <div className="flex flex-col gap-3">
              <ProfitCard
                plan="$0.80 / lead"
                surplus="$1.85k–2.06k"
                margin="58–64%"
                revenue="$3,200"
              />
              <ProfitCard
                plan="$99 / mo"
                surplus="$2.61k–2.82k"
                margin="66–71%"
                revenue="$3,960"
              />
            </div>
          </div>
          <p className="mt-6 text-[12px] text-[var(--text-subtle)]">
            Base case 40 customers × 100 leads. Parent-only neatlogs understates LLM ~65% — we
            publish Option B. Model: {ECONOMICS.model} · {ECONOMICS.tokens} tok · {ECONOMICS.llmTotal}{" "}
            campaign.
          </p>
        </div>
      </section>

      <footer className="border-t border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-8 md:px-8">
          <div>
            <p className="text-[14px] font-semibold">ReachPilot</p>
            <p className="mt-0.5 text-[12px] text-[var(--text-subtle)]">
              neatHack 2026 · Autopilot outbound with observation
            </p>
          </div>
          <div className="flex items-center gap-4">
            <a
              href="https://github.com/DevGajjar28/neatlogs-agents"
              className="text-[13px] font-medium text-[var(--text-muted)] hover:text-[var(--text)]"
              target="_blank"
              rel="noreferrer"
            >
              GitHub
            </a>
            <Link
              href="/dashboard"
              className="rounded-[6px] bg-[var(--primary)] px-3 py-1.5 text-[13px] font-medium text-[var(--primary-fg)] hover:bg-[var(--primary-hover)]"
            >
              Open dashboard
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function HeroStat({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-[11px] text-[var(--text-subtle)]">{k}</dt>
      <dd className="mt-0.5 font-mono text-[15px] font-semibold tabular-nums text-[var(--text)]">
        {v}
      </dd>
    </div>
  );
}

function CostBar({
  label,
  value,
  pct,
  accent,
}: {
  label: string;
  value: string;
  pct: number;
  accent?: boolean;
}) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-[10px]">
        <span className="text-[var(--text-muted)]">{label}</span>
        <span className="font-mono font-medium text-[var(--text)]">{value}</span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <div
          className={`lp-bar-fill h-full rounded-full ${accent ? "bg-[var(--accent)]" : "bg-[var(--text)]/30"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function Bento({
  className,
  title,
  body,
  icon,
  children,
}: {
  className?: string;
  title: string;
  body: string;
  icon?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div
      className={`lp-bento rounded-[12px] border border-[var(--border)] bg-[var(--surface)] p-5 ${className ?? ""}`}
    >
      {icon ? <div className="mb-3">{icon}</div> : null}
      <h3 className="text-[15px] font-semibold tracking-tight text-[var(--text)]">{title}</h3>
      <p className="mt-2 text-[13px] leading-relaxed text-[var(--text-muted)]">{body}</p>
      {children}
    </div>
  );
}

function IntegrationPanel({
  icon,
  iconBg,
  title,
  subtitle,
  body,
  chips,
  borderLeft,
}: {
  icon: ReactNode;
  iconBg: string;
  title: string;
  subtitle: string;
  body: string;
  chips: string[];
  borderLeft?: boolean;
}) {
  return (
    <div
      className={`px-5 py-12 md:px-10 ${borderLeft ? "md:border-l md:border-[var(--border)]" : ""}`}
    >
      <div className="flex items-center gap-3">
        <span className={`inline-flex size-10 items-center justify-center rounded-[8px] ${iconBg}`}>
          {icon}
        </span>
        <div>
          <h3 className="text-[16px] font-semibold">{title}</h3>
          <p className="text-[12px] text-[var(--text-muted)]">{subtitle}</p>
        </div>
      </div>
      <p className="mt-4 max-w-md text-[14px] leading-relaxed text-[var(--text-muted)]">{body}</p>
      <div className="mt-5 flex flex-wrap gap-2">
        {chips.map((c) => (
          <span
            key={c}
            className="inline-flex items-center gap-1 rounded-[5px] bg-[var(--surface-muted)] px-2 py-1 text-[11px] font-medium text-[var(--text)]"
          >
            {c === "Policy gate" ? <Lock className="size-3" strokeWidth={2} aria-hidden /> : null}
            {c}
          </span>
        ))}
      </div>
    </div>
  );
}

function StackCell({
  name,
  metric,
  detail,
  icon,
}: {
  name: string;
  metric: string;
  detail: string;
  icon: ReactNode;
}) {
  return (
    <div className="group bg-[var(--surface)] p-5 transition hover:bg-[var(--accent-soft)]/40">
      <div className="flex items-center gap-2 text-[var(--text-muted)] transition group-hover:text-[var(--accent)]">
        {icon}
        <span className="text-[14px] font-semibold text-[var(--text)]">{name}</span>
      </div>
      <p className="mt-3 font-mono text-[12px] text-[var(--accent)]">{metric}</p>
      <p className="mt-1 text-[12px] text-[var(--text-muted)]">{detail}</p>
    </div>
  );
}

function EcoRow({
  k,
  v,
  sub,
  accent,
}: {
  k: string;
  v: string;
  sub: string;
  accent?: boolean;
}) {
  return (
    <tr className="border-b border-[var(--border)] last:border-0">
      <td className="px-4 py-3.5 text-[var(--text)]">{k}</td>
      <td className="px-4 py-3.5 text-[12px] text-[var(--text-subtle)]">{sub}</td>
      <td
        className={`px-4 py-3.5 text-right font-mono font-medium ${accent ? "text-[var(--accent)]" : "text-[var(--text)]"}`}
      >
        {v}
      </td>
    </tr>
  );
}

function ProfitCard({
  plan,
  surplus,
  margin,
  revenue,
}: {
  plan: string;
  surplus: string;
  margin: string;
  revenue: string;
}) {
  return (
    <div className="lp-bento flex-1 rounded-[12px] border border-[var(--border)] bg-[var(--surface)] p-5">
      <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-subtle)]">
        {plan}
      </p>
      <p className="mt-2 text-[22px] font-semibold tabular-nums tracking-tight">
        {surplus}
        <span className="ml-2 text-[12px] font-medium text-[var(--status-success)]">
          surplus / mo
        </span>
      </p>
      <div className="mt-3 flex gap-4 text-[12px] text-[var(--text-muted)]">
        <span>
          Rev <strong className="text-[var(--text)]">{revenue}</strong>
        </span>
        <span>
          Margin <strong className="text-[var(--text)]">{margin}</strong>
        </span>
      </div>
    </div>
  );
}
