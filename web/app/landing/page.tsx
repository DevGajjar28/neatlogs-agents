import Link from "next/link";
import { Syne } from "next/font/google";

const display = Syne({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  variable: "--font-display",
});

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

const PILLARS = [
  {
    title: "Multi-agent pipeline",
    body: "Specialists for product research, ICP, company find, people enrich, writing, verify, and send — not one mega-prompt.",
  },
  {
    title: "Multi-layer logging",
    body: "Budget ledger for Crustdata, neatlogs for every LLM span, SQLite events for recoveries — three lenses, one campaign id.",
  },
  {
    title: "Guardrails",
    body: "Credit caps, evidence verifier, approve-before-send, mail policy, opt-out, and demo locks so live runs stay safe.",
  },
  {
    title: "Secure & governed",
    body: "Secrets in env only, PII redaction on exports, pause-all sending, and Entire.io checkpoints on every meaningful change.",
  },
] as const;

const TOOLS = [
  {
    name: "Crustdata",
    role: "Research data",
    metric: "5.31 credits / lead",
    detail: "Live company & people APIs. Every call hits the budget ledger — this is the measured data cost.",
  },
  {
    name: "neatlogs",
    role: "LLM tracing",
    metric: "$0.010 / lead",
    detail: "Full async campaign traces (Option B). Tokens and Bedrock $ are measured, never guessed as zero.",
  },
  {
    name: "Entire.io",
    role: "Build governance",
    metric: "Checkpoints",
    detail: "Git-linked agent checkpoints so judges can see how the system was built and changed over time.",
  },
  {
    name: "GitHub",
    role: "Source of truth",
    metric: "DevGajjar28/neatlogs-agents",
    detail: "Open repo for the control plane, agents, and deploy path — reviewable end to end.",
  },
  {
    name: "Hunter.io",
    role: "Email fallback",
    metric: "When data is thin",
    detail: "Fills work emails if Crustdata is short or credits are tight — outreach still ships.",
  },
  {
    name: "Claude + Gmail",
    role: "Write & send",
    metric: "Haiku · approve-first",
    detail: "Evidence-backed drafts on Bedrock; Gmail send only after human (or policy) approval.",
  },
] as const;

const STEPS = [
  { n: "1", title: "Understand the seller", body: "Paste a website. Agents learn the product and who already buys." },
  { n: "2", title: "Find & research", body: "Crustdata lookalikes + people enrich under a hard credit cap." },
  { n: "3", title: "Draft & verify", body: "Personalized email with proof. Unsupported claims get dropped." },
  { n: "4", title: "Approve & measure", body: "You approve. neatlogs + ledger show real cost per qualified lead." },
] as const;

export default function LandingPage() {
  return (
    <div className={`${display.variable} min-h-screen bg-[#0b1220] text-[#e8eef8]`}>
      <style>{`
        @keyframes rp-rise {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes rp-drift {
          0%, 100% { transform: translate3d(0,0,0) scale(1); }
          50% { transform: translate3d(1.5%, -1%, 0) scale(1.02); }
        }
        @keyframes rp-glow {
          0%, 100% { opacity: 0.45; }
          50% { opacity: 0.7; }
        }
        .rp-rise { animation: rp-rise 0.65s ease-out both; }
        .rp-rise-2 { animation: rp-rise 0.65s ease-out 0.1s both; }
        .rp-rise-3 { animation: rp-rise 0.65s ease-out 0.2s both; }
        .rp-drift { animation: rp-drift 20s ease-in-out infinite; }
        .rp-glow { animation: rp-glow 6s ease-in-out infinite; }
      `}</style>

      {/* 1 — What this is */}
      <header className="relative isolate min-h-[100svh] overflow-hidden">
        <div
          className="rp-drift pointer-events-none absolute inset-0"
          aria-hidden
          style={{
            background:
              "radial-gradient(ellipse 70% 50% at 75% 15%, rgba(37,99,235,0.32), transparent 55%), radial-gradient(ellipse 45% 35% at 10% 85%, rgba(14,165,233,0.14), transparent 50%), linear-gradient(165deg, #060b14 0%, #0b1220 50%, #0f172a 100%)",
          }}
        />
        <div
          className="rp-glow pointer-events-none absolute -right-20 top-24 h-72 w-72 rounded-full bg-[#2563eb]/20 blur-3xl"
          aria-hidden
        />

        <nav className="relative z-10 flex items-center justify-between px-6 py-5 md:px-10">
          <span
            className="text-[1.25rem] font-bold tracking-tight text-white"
            style={{ fontFamily: "var(--font-display), system-ui" }}
          >
            ReachPilot
          </span>
          <div className="flex items-center gap-2 sm:gap-3">
            <a
              href="#cost"
              className="hidden rounded-md px-3 py-1.5 text-[13px] font-medium text-white/60 transition hover:text-white sm:inline"
            >
              Unit cost
            </a>
            <a
              href="#stack"
              className="hidden rounded-md px-3 py-1.5 text-[13px] font-medium text-white/60 transition hover:text-white sm:inline"
            >
              Stack
            </a>
            <Link
              href="/dashboard"
              className="rounded-md bg-white px-3.5 py-1.5 text-[13px] font-semibold text-[#0b1220] transition hover:bg-white/90"
            >
              Open app
            </Link>
          </div>
        </nav>

        <div className="relative z-10 mx-auto flex min-h-[calc(100svh-4.5rem)] max-w-5xl flex-col justify-center px-6 pb-20 pt-8 md:px-10">
          <p
            className="rp-rise text-[clamp(2.6rem,7.5vw,5rem)] font-extrabold leading-[0.95] tracking-tight text-white"
            style={{ fontFamily: "var(--font-display), system-ui" }}
          >
            ReachPilot
          </p>
          <h1 className="rp-rise-2 mt-5 max-w-2xl text-[clamp(1.25rem,3vw,1.85rem)] font-medium leading-snug text-white/90">
            Agentic outbound that finds buyers, proves every claim, and shows real cost per lead.
          </h1>
          <p className="rp-rise-3 mt-4 max-w-xl text-[15px] leading-relaxed text-white/50">
            Paste your website. A multi-agent system researches with Crustdata, drafts with Claude,
            traces with neatlogs, and only sends what you approve — with guardrails and measured
            unit economics for judges and CFOs.
          </p>
          <div className="rp-rise-3 mt-8 flex flex-wrap gap-3">
            <Link
              href="/campaigns"
              className="inline-flex items-center rounded-md bg-[#2563eb] px-5 py-2.5 text-[14px] font-semibold text-white transition hover:bg-[#1d4ed8]"
            >
              Launch a campaign
            </Link>
            <a
              href="#system"
              className="inline-flex items-center rounded-md border border-white/15 px-5 py-2.5 text-[14px] font-medium text-white/75 transition hover:border-white/30 hover:text-white"
            >
              How the system works
            </a>
          </div>
          <dl className="rp-rise-3 mt-14 grid max-w-2xl grid-cols-3 gap-4 border-t border-white/10 pt-6">
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-white/40">Direct / lead</dt>
              <dd className="mt-1 text-[18px] font-semibold text-white">{ECONOMICS.directPerLead}</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-white/40">Credits / lead</dt>
              <dd className="mt-1 text-[18px] font-semibold text-white">{ECONOMICS.creditsPerLead}</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-white/40">vs v0</dt>
              <dd className="mt-1 text-[18px] font-semibold text-[#93c5fd]">−{ECONOMICS.reduction}</dd>
            </div>
          </dl>
        </div>
      </header>

      {/* 2 — System: multi-agent, logs, guardrails, governance */}
      <section id="system" className="border-t border-white/10 px-6 py-20 md:px-10">
        <div className="mx-auto max-w-5xl">
          <p className="text-[12px] font-semibold uppercase tracking-widest text-[#60a5fa]">
            The system
          </p>
          <h2
            className="mt-2 text-[1.75rem] font-bold tracking-tight text-white md:text-[2rem]"
            style={{ fontFamily: "var(--font-display), system-ui" }}
          >
            Built like production outbound — not a demo script
          </h2>
          <div className="mt-12 grid gap-8 sm:grid-cols-2">
            {PILLARS.map((p) => (
              <div key={p.title} className="border-l-2 border-[#2563eb]/50 pl-4">
                <h3 className="text-[16px] font-semibold text-white">{p.title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-white/50">{p.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 3 — How it works */}
      <section className="border-t border-white/10 px-6 py-20 md:px-10">
        <div className="mx-auto max-w-5xl">
          <p className="text-[12px] font-semibold uppercase tracking-widest text-[#60a5fa]">
            Flow
          </p>
          <h2
            className="mt-2 text-[1.75rem] font-bold tracking-tight text-white md:text-[2rem]"
            style={{ fontFamily: "var(--font-display), system-ui" }}
          >
            From website to measured outreach
          </h2>
          <ol className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s) => (
              <li key={s.n}>
                <span className="text-[13px] font-bold text-[#60a5fa]">{s.n}</span>
                <h3 className="mt-2 text-[16px] font-semibold text-white">{s.title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-white/50">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* 4 — Stack per tool */}
      <section id="stack" className="border-t border-white/10 px-6 py-20 md:px-10">
        <div className="mx-auto max-w-5xl">
          <p className="text-[12px] font-semibold uppercase tracking-widest text-[#60a5fa]">
            Stack
          </p>
          <h2
            className="mt-2 text-[1.75rem] font-bold tracking-tight text-white md:text-[2rem]"
            style={{ fontFamily: "var(--font-display), system-ui" }}
          >
            Every tool has a job — and a number
          </h2>
          <p className="mt-3 max-w-2xl text-[15px] text-white/50">
            Judges can inspect each layer: data spend in Crustdata, LLM spend in neatlogs, build
            history in Entire.io + GitHub.
          </p>
          <div className="mt-12 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
            {TOOLS.map((t) => (
              <article key={t.name}>
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="text-[17px] font-semibold text-white">{t.name}</h3>
                  <span className="shrink-0 text-[11px] font-medium uppercase tracking-wider text-[#93c5fd]">
                    {t.role}
                  </span>
                </div>
                <p className="mt-2 font-mono text-[13px] text-[#bfdbfe]">{t.metric}</p>
                <p className="mt-2 text-[14px] leading-relaxed text-white/50">{t.detail}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* 5 — Unit economics */}
      <section id="cost" className="border-t border-white/10 px-6 py-20 md:px-10">
        <div className="mx-auto max-w-5xl">
          <p className="text-[12px] font-semibold uppercase tracking-widest text-[#60a5fa]">
            Unit economics
          </p>
          <h2
            className="mt-2 text-[1.75rem] font-bold tracking-tight text-white md:text-[2rem]"
            style={{ fontFamily: "var(--font-display), system-ui" }}
          >
            Real cost per qualified lead
          </h2>
          <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-white/50">
            Measured from live run <span className="text-white/70">v1-posthog-live1</span> (PostHog,
            N=10). Crustdata from the budget ledger. LLM from neatlogs Option B (full async
            aggregation — not parent-only). Bedrock counted once as per-lead inference.
          </p>

          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Crustdata / lead" value={ECONOMICS.creditsPerLead} note="credits · −64% vs v0" />
            <Metric label="Data $" value={ECONOMICS.dataPerLead} note="@ $0.05–0.06 / credit" />
            <Metric label="LLM $" value={ECONOMICS.llmPerLead} note={`${ECONOMICS.llmTotal} total · ${ECONOMICS.tokens} tok`} />
            <Metric label="Blended / lead" value={ECONOMICS.blendedPerLead} note="data + LLM + infra" highlight />
          </div>

          <div className="mt-10 overflow-x-auto rounded-lg border border-white/10">
            <table className="w-full min-w-[520px] text-left text-[13px]">
              <thead>
                <tr className="border-b border-white/10 text-[11px] uppercase tracking-wider text-white/40">
                  <th className="px-4 py-3 font-medium">Layer</th>
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 font-medium">v1 / lead</th>
                </tr>
              </thead>
              <tbody className="text-white/70">
                <tr className="border-b border-white/5">
                  <td className="px-4 py-3 text-white">Crustdata data</td>
                  <td className="px-4 py-3">Budget ledger</td>
                  <td className="px-4 py-3 font-mono text-white">{ECONOMICS.dataPerLead}</td>
                </tr>
                <tr className="border-b border-white/5">
                  <td className="px-4 py-3 text-white">Bedrock LLM</td>
                  <td className="px-4 py-3">neatlogs Option B</td>
                  <td className="px-4 py-3 font-mono text-white">{ECONOMICS.llmPerLead}</td>
                </tr>
                <tr className="border-b border-white/5">
                  <td className="px-4 py-3 text-white">Direct (data + LLM)</td>
                  <td className="px-4 py-3">Spreadsheet</td>
                  <td className="px-4 py-3 font-mono text-white">{ECONOMICS.directPerLead}</td>
                </tr>
                <tr>
                  <td className="px-4 py-3 text-white">Blended (+ hosting/email)</td>
                  <td className="px-4 py-3">Base case 4k leads/mo</td>
                  <td className="px-4 py-3 font-mono text-[#93c5fd]">{ECONOMICS.blendedPerLead}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <p className="mt-6 text-[13px] text-white/40">
            v0 was {ECONOMICS.v0Credits} credits/lead. Parent-only neatlogs match understates LLM by
            ~65% — we publish Option B so cost is not silently low. Model: {ECONOMICS.model}.
          </p>
        </div>
      </section>

      <footer className="border-t border-white/10 px-6 py-10 md:px-10">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4">
          <div>
            <span
              className="text-[15px] font-bold text-white"
              style={{ fontFamily: "var(--font-display), system-ui" }}
            >
              ReachPilot
            </span>
            <p className="mt-1 text-[12px] text-white/40">neatHack 2026 · measured outbound</p>
          </div>
          <div className="flex flex-wrap gap-4">
            <a
              href="https://github.com/DevGajjar28/neatlogs-agents"
              className="text-[13px] font-medium text-white/55 hover:text-white"
              target="_blank"
              rel="noreferrer"
            >
              GitHub
            </a>
            <Link
              href="/dashboard"
              className="text-[13px] font-medium text-[#93c5fd] hover:text-white"
            >
              Dashboard →
            </Link>
          </div>
        </div>
      </footer>
    </div>
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
          ? "rounded-lg border border-[#2563eb]/40 bg-[#2563eb]/10 px-4 py-4"
          : "rounded-lg border border-white/10 bg-white/[0.03] px-4 py-4"
      }
    >
      <p className="text-[11px] font-medium uppercase tracking-wider text-white/40">{label}</p>
      <p
        className="mt-2 text-[1.5rem] font-bold tracking-tight text-white"
        style={{ fontFamily: "var(--font-display), system-ui" }}
      >
        {value}
      </p>
      <p className="mt-1.5 text-[12px] text-white/40">{note}</p>
    </div>
  );
}
