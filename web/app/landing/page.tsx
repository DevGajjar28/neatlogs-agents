import Link from "next/link";
import type { ReactNode } from "react";
import {
  Bot,
  Calendar,
  Code2,
  Eye,
  GitBranch,
  Lock,
  Mail,
  Radio,
  Scale,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";

/** Locked from ReachPilot unit economics.xlsx + neatlogs Option B */
const ECONOMICS = {
  creditsPerLead: "5.31",
  dataPerLead: "$0.27–0.32",
  llmPerLead: "$0.010",
  directPerLead: "$0.28–0.33",
  blendedPerLead: "$0.29–0.34",
  v0Credits: "14.60",
  reduction: "64%",
  llmTotal: "$0.10",
  tokens: "56.8k",
  model: "Claude Haiku 4.5",
} as const;

const PROFIT = [
  {
    plan: "$0.80 / lead",
    revenue: "$3,200 / mo",
    surplus: "$1.85k–2.06k",
    margin: "58–64%",
    note: "Base case · 40 customers · 100 leads each",
  },
  {
    plan: "$99 / mo",
    revenue: "$3,960 / mo",
    surplus: "$2.61k–2.82k",
    margin: "66–71%",
    note: "Healthiest subscription margin after blended cost",
  },
] as const;

const DIFFS = [
  {
    icon: Scale,
    title: "Governance, not spray-and-pray",
    body: "Approve gates, credit caps, verifier drops, and pause-all sending. Autopilot runs inside policy — not around it.",
  },
  {
    icon: Eye,
    title: "Data observation everywhere",
    body: "Crustdata spend in the budget ledger. Every LLM span in neatlogs. Recoveries in SQLite events. One campaign id ties them.",
  },
  {
    icon: Bot,
    title: "Controlled agents + sub-agents",
    body: "Parent orchestrator dispatches specialists. Sub-tasks write and verify per company — observed, not a single opaque prompt.",
  },
] as const;

const AGENTS = [
  { name: "Product", task: "Learn what you sell", icon: Search },
  { name: "ICP", task: "Propose who buys", icon: Users },
  { name: "Research", task: "Find & enrich accounts", icon: Radio },
  { name: "Writer", task: "Draft with evidence", icon: Sparkles },
  { name: "Verifier", task: "Drop unsupported claims", icon: ShieldCheck },
  { name: "Sender", task: "Deliver under policy", icon: Send },
  { name: "Meeting", task: "Book via Calendar", icon: Calendar },
] as const;

const STACK = [
  {
    name: "Crustdata",
    role: "Live research",
    metric: "5.31 credits / lead",
    detail: "Company & people APIs metered in the ledger — measured data cost.",
    icon: Radio,
  },
  {
    name: "neatlogs",
    role: "LLM tracing",
    metric: "$0.010 / lead",
    detail: "Option B full async traces. Tokens and Bedrock $ never guessed as zero.",
    icon: Eye,
  },
  {
    name: "Entire.io",
    role: "Build governance",
    metric: "Checkpoints",
    detail: "Git-linked agent checkpoints so judges see how the system evolved.",
    icon: GitBranch,
  },
  {
    name: "GitHub",
    role: "Source of truth",
    metric: "neatlogs-agents",
    detail: "Open control plane, agents, and deploy path — reviewable end to end.",
    icon: Code2,
  },
  {
    name: "Gmail",
    role: "Mail path",
    metric: "Read · write · send",
    detail: "Policy-gated outbound. Agents only touch mail the security rules allow.",
    icon: Mail,
  },
  {
    name: "Google Calendar",
    role: "Meetings",
    metric: "Autopilot booking",
    detail: "When a prospect names a time, book Meet links through Calendar OAuth.",
    icon: Calendar,
  },
] as const;

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <style>{`
        @keyframes lp-rise {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes lp-float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-4px); }
        }
        @keyframes lp-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.45; }
        }
        .lp-rise { animation: lp-rise 0.55s ease-out both; }
        .lp-rise-2 { animation: lp-rise 0.55s ease-out 0.08s both; }
        .lp-rise-3 { animation: lp-rise 0.55s ease-out 0.16s both; }
        .lp-float { animation: lp-float 4.5s ease-in-out infinite; }
        .lp-pulse { animation: lp-pulse 2.4s ease-in-out infinite; }
      `}</style>

      {/* Hero */}
      <header className="relative overflow-hidden border-b border-[var(--border)]">
        <div
          className="pointer-events-none absolute inset-0 opacity-90"
          aria-hidden
          style={{
            background:
              "radial-gradient(ellipse 70% 55% at 85% 0%, var(--accent-soft), transparent 55%), radial-gradient(ellipse 40% 30% at 5% 90%, #f0fdf4, transparent 50%)",
          }}
        />
        <nav className="relative z-10 mx-auto flex max-w-5xl items-center justify-between px-6 py-5 md:px-8">
          <span className="text-[15px] font-semibold tracking-tight text-[var(--text)]">
            ReachPilot
            <span className="ml-1.5 text-[11px] font-medium text-[var(--text-subtle)]">beta</span>
          </span>
          <div className="flex items-center gap-2">
            <a
              href="#cost"
              className="hidden rounded-[6px] px-3 py-1.5 text-[13px] font-medium text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)] sm:inline"
            >
              Unit cost
            </a>
            <Link
              href="/dashboard"
              className="rounded-[6px] bg-[var(--primary)] px-3.5 py-1.5 text-[13px] font-medium text-[var(--primary-fg)] hover:bg-[var(--primary-hover)]"
            >
              Open app
            </Link>
          </div>
        </nav>

        <div className="relative z-10 mx-auto max-w-5xl px-6 pb-16 pt-10 md:px-8 md:pb-20 md:pt-14">
          <p className="lp-rise text-[clamp(2.4rem,6vw,3.75rem)] font-semibold leading-[1.05] tracking-tight text-[var(--text)]">
            ReachPilot
          </p>
          <h1 className="lp-rise-2 mt-4 max-w-2xl text-[clamp(1.15rem,2.4vw,1.5rem)] font-medium leading-snug text-[var(--text)]">
            Autopilot outbound for real reach — multi-agent, observed, policy-controlled.
          </h1>
          <p className="lp-rise-3 mt-3 max-w-xl text-[15px] leading-relaxed text-[var(--text-muted)]">
            Not a blast tool. Controlled agents research with Crustdata, draft and verify, send
            through Gmail under security policy, and book meetings on Google Calendar — while
            neatlogs traces every LLM step and the ledger tracks every credit.
          </p>
          <div className="lp-rise-3 mt-7 flex flex-wrap gap-2.5">
            <Link
              href="/campaigns"
              className="inline-flex h-9 items-center rounded-[6px] bg-[var(--accent)] px-4 text-[13px] font-semibold text-white hover:bg-[var(--status-info)]"
            >
              Start a campaign
            </Link>
            <a
              href="#system"
              className="inline-flex h-9 items-center rounded-[6px] border border-[var(--border-strong)] bg-[var(--surface)] px-4 text-[13px] font-medium text-[var(--text)] hover:bg-[var(--surface-muted)]"
            >
              See the system
            </a>
          </div>
          <div className="lp-rise-3 mt-10 flex flex-wrap gap-2">
            <Chip>{ECONOMICS.creditsPerLead} credits / lead</Chip>
            <Chip>{ECONOMICS.llmPerLead} LLM / lead</Chip>
            <Chip>blended {ECONOMICS.blendedPerLead}</Chip>
          </div>
        </div>
      </header>

      {/* Why different */}
      <section id="system" className="border-b border-[var(--border)] px-6 py-16 md:px-8">
        <div className="mx-auto max-w-5xl">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--accent)]">
            Why we’re different
          </p>
          <h2 className="mt-2 text-[1.5rem] font-semibold tracking-tight text-[var(--text)] md:text-[1.75rem]">
            Traditional outbound guesses. ReachPilot measures and governs.
          </h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-3">
            {DIFFS.map((d) => (
              <div key={d.title} className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
                <d.icon className="size-5 text-[var(--accent)]" strokeWidth={1.75} aria-hidden />
                <h3 className="mt-3 text-[14px] font-semibold text-[var(--text)]">{d.title}</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-[var(--text-muted)]">{d.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Multi-agent */}
      <section className="border-b border-[var(--border)] px-6 py-16 md:px-8">
        <div className="mx-auto max-w-5xl">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--accent)]">
            Multi-agent
          </p>
          <h2 className="mt-2 text-[1.5rem] font-semibold tracking-tight text-[var(--text)] md:text-[1.75rem]">
            Each agent, one job — every call logged in neatlogs
          </h2>
          <p className="mt-2 max-w-2xl text-[14px] text-[var(--text-muted)]">
            Parent run orchestrates specialists. Async sub-agents write and verify per company.
            Spans show up in neatlogs so cost and behavior stay visible.
          </p>
          <ul className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {AGENTS.map((a, i) => (
              <li
                key={a.name}
                className="flex items-start gap-3 rounded-[8px] border border-[var(--border)] bg-[var(--surface)] px-3.5 py-3"
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <span className="lp-float mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-[6px] bg-[var(--accent-soft)] text-[var(--accent)]">
                  <a.icon className="size-4" strokeWidth={1.75} aria-hidden />
                </span>
                <div className="min-w-0">
                  <p className="text-[13px] font-semibold text-[var(--text)]">{a.name}</p>
                  <p className="text-[12px] text-[var(--text-muted)]">{a.task}</p>
                  <p className="mt-1 text-[11px] font-medium text-[var(--text-subtle)]">
                    <span className="lp-pulse inline-block size-1.5 rounded-full bg-[var(--status-success)] align-middle" />{" "}
                    traced in neatlogs
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Mail + calendar */}
      <section className="border-b border-[var(--border)] px-6 py-16 md:px-8">
        <div className="mx-auto max-w-5xl">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--accent)]">
            Integrations
          </p>
          <h2 className="mt-2 text-[1.5rem] font-semibold tracking-tight text-[var(--text)] md:text-[1.75rem]">
            Gmail and Calendar — with security policy in the loop
          </h2>
          <div className="mt-10 grid gap-6 lg:grid-cols-2">
            <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-5">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-10 items-center justify-center rounded-[8px] bg-[#fce8e6]">
                  <Mail className="size-5 text-[#ea4335]" strokeWidth={1.75} aria-hidden />
                </span>
                <div>
                  <h3 className="text-[15px] font-semibold">Gmail</h3>
                  <p className="text-[12px] text-[var(--text-muted)]">Read · write · send under policy</p>
                </div>
              </div>
              <p className="mt-4 text-[14px] leading-relaxed text-[var(--text-muted)]">
                Connect your mailbox. Agents draft and send only what mail policy allows — opt-out,
                rate limits, demo locks, and pause-all. Autopilot does not bypass security.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Chip>
                  <Lock className="size-3" strokeWidth={2} aria-hidden />
                  Policy gate
                </Chip>
                <Chip>Approve before send</Chip>
                <Chip>Pause-all</Chip>
              </div>
            </div>
            <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-5">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-10 items-center justify-center rounded-[8px] bg-[var(--accent-soft)]">
                  <Calendar className="size-5 text-[var(--accent)]" strokeWidth={1.75} aria-hidden />
                </span>
                <div>
                  <h3 className="text-[15px] font-semibold">Google Calendar</h3>
                  <p className="text-[12px] text-[var(--text-muted)]">Autopilot meeting booking</p>
                </div>
              </div>
              <p className="mt-4 text-[14px] leading-relaxed text-[var(--text-muted)]">
                When a prospect names a time, Autopilot creates the event and Meet link via Calendar
                OAuth — no manual back-and-forth for the booking step.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Chip>Meet links</Chip>
                <Chip>OAuth scoped</Chip>
                <Chip>Reply → book</Chip>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stack */}
      <section className="border-b border-[var(--border)] px-6 py-16 md:px-8">
        <div className="mx-auto max-w-5xl">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--accent)]">
            Stack
          </p>
          <h2 className="mt-2 text-[1.5rem] font-semibold tracking-tight text-[var(--text)] md:text-[1.75rem]">
            Every tool has a job — and a number
          </h2>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {STACK.map((t) => (
              <article
                key={t.name}
                className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4"
              >
                <div className="flex items-start gap-3">
                  <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-[6px] bg-[var(--surface-muted)] text-[var(--text)]">
                    <t.icon className="size-4" strokeWidth={1.75} aria-hidden />
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                      <h3 className="text-[14px] font-semibold text-[var(--text)]">{t.name}</h3>
                      <span className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-subtle)]">
                        {t.role}
                      </span>
                    </div>
                    <p className="mt-1 font-mono text-[12px] text-[var(--accent)]">{t.metric}</p>
                    <p className="mt-2 text-[13px] leading-relaxed text-[var(--text-muted)]">
                      {t.detail}
                    </p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Unit economics + profit */}
      <section id="cost" className="border-b border-[var(--border)] px-6 py-16 md:px-8">
        <div className="mx-auto max-w-5xl">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--accent)]">
            Unit economics
          </p>
          <h2 className="mt-2 text-[1.5rem] font-semibold tracking-tight text-[var(--text)] md:text-[1.75rem]">
            Measured cost — and what you earn
          </h2>
          <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-[var(--text-muted)]">
            Live run <span className="font-medium text-[var(--text)]">v1-posthog-live1</span> (N=10).
            Crustdata from the budget ledger. LLM from neatlogs Option B. Bedrock counted once as
            per-lead inference — never silently zero.
          </p>

          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Crustdata / lead" value={ECONOMICS.creditsPerLead} note="credits · −64% vs v0" />
            <Metric label="Data $" value={ECONOMICS.dataPerLead} note="@ $0.05–0.06 / credit" />
            <Metric
              label="LLM (neatlogs)"
              value={ECONOMICS.llmPerLead}
              note={`${ECONOMICS.llmTotal} · ${ECONOMICS.tokens} tok`}
            />
            <Metric
              label="Blended / lead"
              value={ECONOMICS.blendedPerLead}
              note="data + LLM + infra"
              highlight
            />
          </div>

          <div className="mt-8 overflow-x-auto rounded-[8px] border border-[var(--border)] bg-[var(--surface)]">
            <table className="w-full min-w-[480px] text-left text-[13px]">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--surface-muted)] text-[11px] uppercase tracking-wider text-[var(--text-subtle)]">
                  <th className="px-4 py-2.5 font-medium">Layer</th>
                  <th className="px-4 py-2.5 font-medium">Source</th>
                  <th className="px-4 py-2.5 font-medium">v1 / lead</th>
                </tr>
              </thead>
              <tbody className="text-[var(--text-muted)]">
                <tr className="border-b border-[var(--border)]">
                  <td className="px-4 py-2.5 text-[var(--text)]">Crustdata data</td>
                  <td className="px-4 py-2.5">Budget ledger</td>
                  <td className="px-4 py-2.5 font-mono text-[var(--text)]">{ECONOMICS.dataPerLead}</td>
                </tr>
                <tr className="border-b border-[var(--border)]">
                  <td className="px-4 py-2.5 text-[var(--text)]">Bedrock LLM</td>
                  <td className="px-4 py-2.5">neatlogs Option B</td>
                  <td className="px-4 py-2.5 font-mono text-[var(--text)]">{ECONOMICS.llmPerLead}</td>
                </tr>
                <tr className="border-b border-[var(--border)]">
                  <td className="px-4 py-2.5 text-[var(--text)]">Direct (data + LLM)</td>
                  <td className="px-4 py-2.5">Spreadsheet</td>
                  <td className="px-4 py-2.5 font-mono text-[var(--text)]">{ECONOMICS.directPerLead}</td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-[var(--text)]">Blended (+ hosting/email)</td>
                  <td className="px-4 py-2.5">Base 4k leads / mo</td>
                  <td className="px-4 py-2.5 font-mono text-[var(--accent)]">{ECONOMICS.blendedPerLead}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h3 className="mt-12 text-[15px] font-semibold text-[var(--text)]">
            Profit at base case (40 customers × 100 leads)
          </h3>
          <p className="mt-1 text-[13px] text-[var(--text-muted)]">
            After blended service cost — surplus is what you keep before sales overhead.
          </p>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {PROFIT.map((p) => (
              <div
                key={p.plan}
                className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-5"
              >
                <p className="text-[12px] font-medium uppercase tracking-wider text-[var(--text-subtle)]">
                  {p.plan}
                </p>
                <p className="mt-2 text-[22px] font-semibold tabular-nums text-[var(--text)]">
                  {p.surplus}
                  <span className="ml-2 text-[13px] font-normal text-[var(--status-success)]">
                    surplus / mo
                  </span>
                </p>
                <dl className="mt-3 space-y-1.5 text-[13px]">
                  <div className="flex justify-between gap-2">
                    <dt className="text-[var(--text-muted)]">Plan revenue</dt>
                    <dd className="font-medium text-[var(--text)]">{p.revenue}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-[var(--text-muted)]">Service margin</dt>
                    <dd className="font-medium text-[var(--text)]">{p.margin}</dd>
                  </div>
                </dl>
                <p className="mt-3 text-[12px] text-[var(--text-subtle)]">{p.note}</p>
              </div>
            ))}
          </div>
          <p className="mt-6 text-[12px] text-[var(--text-subtle)]">
            v0 was {ECONOMICS.v0Credits} credits/lead. Parent-only neatlogs match understates LLM by
            ~65% — we publish Option B. Model: {ECONOMICS.model}.
          </p>
        </div>
      </section>

      <footer className="px-6 py-10 md:px-8">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-[14px] font-semibold text-[var(--text)]">ReachPilot</p>
            <p className="mt-0.5 text-[12px] text-[var(--text-subtle)]">
              neatHack 2026 · measured Autopilot outbound
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <a
              href="https://github.com/DevGajjar28/neatlogs-agents"
              className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[var(--text-muted)] hover:text-[var(--text)]"
              target="_blank"
              rel="noreferrer"
            >
              <Code2 className="size-3.5" strokeWidth={1.75} aria-hidden />
              GitHub
            </a>
            <Link
              href="/dashboard"
              className="text-[13px] font-medium text-[var(--accent)] hover:underline"
            >
              Dashboard →
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-[5px] bg-[var(--surface-muted)] px-2 py-1 text-[11px] font-medium text-[var(--text)]">
      {children}
    </span>
  );
}

function Metric({
  label,
  value,
  note,
  highlight,
}: {
  label: string;
  value: string;
  note: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={
        highlight
          ? "rounded-[8px] border border-[var(--accent)]/30 bg-[var(--accent-soft)] px-4 py-4"
          : "rounded-[8px] border border-[var(--border)] bg-[var(--surface)] px-4 py-4"
      }
    >
      <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-subtle)]">
        {label}
      </p>
      <p className="mt-1.5 text-[1.35rem] font-semibold tracking-tight text-[var(--text)]">{value}</p>
      <p className="mt-1 text-[12px] text-[var(--text-muted)]">{note}</p>
    </div>
  );
}
