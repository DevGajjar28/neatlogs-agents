"use client";

/**
 * Shared pipeline UI primitives (scenes, StatusPill, StreamLine, hooks).
 * Horizontal / stacked cards are the mobile fallback; desktop uses AgentPipelineCanvas.
 */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { Circle, Mail, Map as MapIcon, Search, Send, Sparkles, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  AGENT_ROLES,
  elapsedLabel,
  prefersReducedMotion,
  type PipelineAgent,
  type PipelineKey,
  type PipelineStatus,
} from "@/lib/pipeline";
import { cn } from "@/lib/utils";

export type { PipelineAgent };

const ICONS: Record<PipelineAgent["agent"], LucideIcon> = {
  planner: MapIcon,
  product_researcher: Search,
  buyer_finder: Users,
  account_researcher: Sparkles,
  email_writer_verifier: Mail,
  sender: Send,
};

const PILL_TEXT: Record<PipelineStatus, string> = {
  idle: "Queued",
  running: "Working",
  waiting: "Needs you",
  done: "Done",
  failed: "Failed",
};

export function useReducedMotion(): boolean {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    setReduce(prefersReducedMotion());
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduce(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduce;
}

/** Typewriter for detail while running; pass-through for stream. */
export function useStreamText(
  status: PipelineStatus,
  detail: string | null | undefined,
  stream: string | null | undefined,
): { text: string; live: boolean; streaming: boolean } {
  const [typed, setTyped] = useState("");
  const reduce = useReducedMotion();
  const source = stream || detail || "";

  useEffect(() => {
    if (stream) {
      setTyped(stream.slice(-150));
      return;
    }
    if (status !== "running" || reduce || !detail) {
      setTyped(detail || "");
      return;
    }
    setTyped("");
    let i = 0;
    const id = window.setInterval(() => {
      i = Math.min(detail.length, i + 2);
      setTyped(detail.slice(0, i));
      if (i >= detail.length) window.clearInterval(id);
    }, 22);
    return () => window.clearInterval(id);
  }, [detail, stream, status, reduce]);

  const idleMsg = "Waiting for the planner to hand over this job.";
  if (status === "idle" && !source) {
    return { text: idleMsg, live: false, streaming: false };
  }
  if (status === "waiting" && !source) {
    return { text: "Review drafts before send.", live: false, streaming: false };
  }
  return {
    text: typed || source,
    live: status === "running",
    streaming: Boolean(stream) && status === "running",
  };
}

export function StatusPill({ status }: { status: PipelineStatus }) {
  return (
    <span className={cn("ap-pill", `ap-pill-${status}`)}>
      <span
        className={cn("ap-pill-dot", status === "running" && "pulse")}
        aria-hidden
      />
      {PILL_TEXT[status]}
    </span>
  );
}

export function StreamLine({
  status,
  detail,
  stream,
  compact,
}: {
  status: PipelineStatus;
  detail?: string | null;
  stream?: string | null;
  compact?: boolean;
}) {
  const { text, live } = useStreamText(status, detail, stream);
  return (
    <div className="ap-stream">
      {live ? (
        <div className="ap-stream-label live">Working now</div>
      ) : null}
      <p className={cn(compact ? "line-clamp-1" : "line-clamp-3")}>
        {text}
        {live ? <span className="ap-stream-caret" aria-hidden /> : null}
      </p>
      <span className="ap-sr-only" aria-live="polite">
        {detail || stream || text}
      </span>
    </div>
  );
}

export function ProgressBar({
  status,
  progress,
}: {
  status: PipelineStatus;
  progress?: { done: number; total: number | null } | null;
}) {
  const indet = status === "running" && (!progress || progress.total == null);
  const pct =
    progress && progress.total && progress.total > 0
      ? Math.min(100, Math.round((progress.done / progress.total) * 100))
      : status === "done"
        ? 100
        : 0;
  return (
    <div className={cn("ap-progress", indet && "indet")} aria-hidden>
      <i style={indet ? undefined : { width: `${pct}%` }} />
    </div>
  );
}

/* ─── Scenes (SVG viewBox 200×80) ─── */

function SceneBox({
  status,
  running,
  className,
  children,
}: {
  status: PipelineStatus;
  running: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn("ap-scene", status === "idle" && "dim", className)}
      aria-hidden
    >
      <svg
        viewBox="0 0 200 80"
        className={running ? "ap-anim" : undefined}
        preserveAspectRatio="xMidYMid meet"
      >
        {children}
      </svg>
    </div>
  );
}

/** Clear planner badge — same visual language as other agent icons (no cryptic orbit). */
export function PlannerOrbit({
  agents,
  size = 56,
}: {
  agents: PipelineAgent[];
  size?: number;
}) {
  const planner = agents.find((a) => a.key === "planner");
  const active = planner?.status === "running" || agents.some((a) => a.status === "running");
  const Icon = ICONS.planner;
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-[8px] bg-[var(--ap-muted)]",
        active && "ring-2 ring-[var(--ap-accent)]/30",
      )}
      style={{ width: size, height: size }}
      title="Planner — routes work to the other agents"
      aria-hidden
    >
      <Icon
        className="text-[var(--ap-accent)]"
        style={{ width: Math.round(size * 0.4), height: Math.round(size * 0.4) }}
        strokeWidth={1.75}
      />
    </span>
  );
}

export function ProductScene({
  status,
  items,
  progress,
  tall,
  inspector,
}: {
  status: PipelineStatus;
  items?: string[] | null;
  progress?: { done: number; total: number | null } | null;
  tall?: boolean;
  inspector?: boolean;
}) {
  const running = status === "running";
  const found = Math.min(3, progress?.done ?? items?.length ?? 0);
  return (
    <SceneBox
      status={status}
      running={running}
      className={cn(tall && "tall", inspector && "inspector")}
    >
      <rect x="8" y="10" width="96" height="60" rx="4" className="ap-fill-surface ap-stroke-border" strokeWidth="1" />
      <circle cx="18" cy="20" r="2" className="ap-fill-danger" />
      <circle cx="26" cy="20" r="2" className="ap-fill-warning" />
      <circle cx="34" cy="20" r="2" className="ap-fill-success" />
      <rect x="14" y="28" width="50" height="4" rx="1" className="ap-fill-border" />
      <rect x="14" y="36" width="70" height="4" rx="1" className="ap-fill-border" />
      <rect x="14" y="44" width="40" height="18" rx="2" className="ap-fill-muted" />
      {running ? (
        <rect x="10" y="14" width="92" height="2" className="ap-fill-accent ap-scan" />
      ) : null}
      {[0, 1, 2].map((i) => {
        const y = 18 + i * 18;
        const ok = i < found;
        const label = (items?.[i] || "").slice(0, 12);
        return (
          <g key={i}>
            <line
              x1="104"
              y1={40}
              x2="118"
              y2={y + 8}
              className={ok ? "ap-stroke-accent" : "ap-stroke-border"}
              strokeWidth="1"
            />
            <rect
              x="118"
              y={y}
              width="72"
              height="16"
              rx="3"
              className={ok ? "ap-fill-accent-soft ap-stroke-accent" : "ap-fill-surface ap-stroke-border"}
              strokeWidth="1"
              strokeDasharray={ok ? undefined : "3 2"}
              style={running && !ok ? { animation: "ap-slot 1.4s ease-in-out infinite" } : undefined}
            />
            {ok && label ? (
              <text x="122" y={y + 11} fontSize="8.5" fontFamily="var(--ap-mono)" fill="var(--ap-accent)">
                {label}
              </text>
            ) : null}
          </g>
        );
      })}
    </SceneBox>
  );
}

export function BuyersScene({
  status,
  progress,
  listMode,
  tall,
  inspector,
}: {
  status: PipelineStatus;
  progress?: { done: number; total: number | null } | null;
  listMode?: boolean;
  tall?: boolean;
  inspector?: boolean;
}) {
  const running = status === "running";
  const total = Math.min(30, progress?.total ?? 30);
  const kept = Math.min(total, progress?.done ?? 0);
  const cols = 10;
  const rows = 3;
  const dots = Array.from({ length: cols * rows }, (_, i) => i);
  return (
    <SceneBox
      status={status}
      running={running}
      className={cn(tall && "tall", inspector && "inspector")}
    >
      {dots.map((i) => {
        const col = i % cols;
        const row = Math.floor(i / cols);
        const x = 20 + col * 16;
        const y = 18 + row * 18;
        const solid = i < kept;
        if (listMode) {
          return (
            <rect
              key={i}
              x={x - 3}
              y={y - 3}
              width="6"
              height="6"
              rx="1"
              className={solid ? "ap-fill-accent ap-wave" : "ap-fill-subtle ap-wave"}
              style={{ ["--d" as string]: i }}
              opacity={solid ? 1 : 0.4}
            />
          );
        }
        return (
          <circle
            key={i}
            cx={x}
            cy={y}
            r="3"
            className={solid ? "ap-fill-accent ap-wave" : "ap-fill-subtle ap-wave"}
            style={{ ["--d" as string]: i }}
            opacity={solid ? 1 : 0.4}
          />
        );
      })}
      {running ? (
        <rect x="16" y="12" width="2" height="56" className="ap-fill-accent ap-sweep" />
      ) : null}
    </SceneBox>
  );
}

export function AccountsScene({
  status,
  progress,
  tall,
  inspector,
}: {
  status: PipelineStatus;
  progress?: { done: number; total: number | null } | null;
  tall?: boolean;
  inspector?: boolean;
}) {
  const running = status === "running";
  const found = Math.min(6, progress?.done ?? 0);
  const people = Array.from({ length: 6 }, (_, i) => i);
  return (
    <SceneBox
      status={status}
      running={running}
      className={cn(tall && "tall", inspector && "inspector")}
    >
      {running ? (
        <circle cx="100" cy="40" r="13" className="ap-stroke-accent ap-ring" fill="none" strokeWidth="1.5" />
      ) : null}
      <rect x="90" y="28" width="20" height="24" rx="2" className="ap-fill-accent-soft ap-stroke-accent" strokeWidth="1.5" />
      <rect x="94" y="32" width="5" height="5" className="ap-fill-accent" />
      <rect x="101" y="32" width="5" height="5" className="ap-fill-accent" />
      <rect x="94" y="40" width="12" height="8" className="ap-fill-accent" opacity="0.5" />
      {people.map((i) => {
        const ang = ((i * 60 - 90) * Math.PI) / 180;
        const cx = 100 + Math.cos(ang) * 48;
        const cy = 40 + Math.sin(ang) * 26;
        const ok = i < found;
        return (
          <g key={i}>
            <line
              x1="100"
              y1="40"
              x2={cx}
              y2={cy}
              className={ok ? "ap-stroke-accent" : "ap-stroke-border ap-dash"}
              strokeWidth="1"
              strokeDasharray={ok ? undefined : "3 3"}
            />
            <circle
              cx={cx}
              cy={cy}
              r="5"
              className={ok ? "ap-fill-accent" : "ap-fill-surface ap-stroke-border"}
              strokeWidth="1"
            />
          </g>
        );
      })}
    </SceneBox>
  );
}

export function WriterScene({
  status,
  progress,
  tall,
  inspector,
}: {
  status: PipelineStatus;
  progress?: { done: number; total: number | null } | null;
  tall?: boolean;
  inspector?: boolean;
}) {
  const running = status === "running";
  const done = status === "done";
  const waiting = status === "waiting";
  const checked = progress?.done ?? 0;
  const total = progress?.total ?? 0;
  return (
    <SceneBox
      status={status}
      running={running}
      className={cn(tall && "tall", inspector && "inspector")}
    >
      <rect x="12" y="12" width="70" height="56" rx="3" className="ap-fill-surface ap-stroke-border" strokeWidth="1" />
      <rect x="18" y="18" width="28" height="10" rx="2" className="ap-fill-accent-soft ap-stroke-accent" strokeWidth="1" />
      <text x="22" y="25" fontSize="7" fill="var(--ap-accent)">
        To
      </text>
      {[0, 1, 2, 3, 4].map((i) => (
        <rect
          key={i}
          x="18"
          y={34 + i * 6}
          width={50 - i * 4}
          height="3"
          rx="1"
          className="ap-fill-border ap-type"
          style={{ ["--i" as string]: i }}
        />
      ))}
      <path d="M90 40 H118" className="ap-stroke-accent" strokeWidth="1.5" markerEnd="url(#ap-arrow)" />
      {running ? <circle cx="90" cy="40" r="3" className="ap-fill-accent ap-hop" /> : null}
      <defs>
        <marker id="ap-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" className="ap-fill-accent" />
        </marker>
      </defs>
      <circle
        cx="148"
        cy="40"
        r="22"
        className={
          done
            ? "ap-fill-success-soft ap-stroke-success"
            : waiting
              ? "ap-fill-warning-soft ap-stroke-warning"
              : "ap-fill-accent-soft ap-stroke-accent"
        }
        strokeWidth="1.5"
        fill={done ? "var(--ap-success-soft)" : waiting ? "var(--ap-warning-soft)" : "var(--ap-accent-soft)"}
      />
      {running ? (
        <circle
          cx="148"
          cy="40"
          r="14"
          fill="none"
          className="ap-stroke-accent ap-spin"
          strokeWidth="1.5"
          strokeDasharray="6 4"
        />
      ) : null}
      {done ? (
        <path d="M138 40 l6 6 12-14" fill="none" className="ap-stroke-success" strokeWidth="2" />
      ) : waiting ? (
        <path d="M148 30 v12 h8" fill="none" className="ap-stroke-warning" strokeWidth="2" />
      ) : null}
      {total > 0 ? (
        <text x="136" y="72" fontSize="8" fontFamily="var(--ap-mono)" fill="var(--ap-text-subtle)">
          {checked}/{total} checked
        </text>
      ) : null}
    </SceneBox>
  );
}

export function SenderScene({
  status,
  progress,
  tall,
  inspector,
}: {
  status: PipelineStatus;
  progress?: { done: number; total: number | null } | null;
  tall?: boolean;
  inspector?: boolean;
}) {
  const running = status === "running";
  const reduce = useReducedMotion();
  const sent = progress?.done ?? 0;
  const path = "M40 50 C 80 10, 120 10, 160 50";
  return (
    <SceneBox
      status={status}
      running={running}
      className={cn(tall && "tall", inspector && "inspector")}
    >
      <rect x="12" y="44" width="36" height="20" rx="2" className="ap-fill-muted ap-stroke-border" strokeWidth="1" />
      <path d="M12 44 L30 32 L48 44" fill="none" className="ap-stroke-border" strokeWidth="1" />
      <path
        id="ap-send-path"
        d={path}
        fill="none"
        className={sent > 0 || status === "done" ? "ap-stroke-accent" : "ap-stroke-border"}
        strokeWidth="1.5"
        strokeDasharray={sent > 0 || status === "done" ? undefined : "4 3"}
      />
      <rect x="152" y="40" width="36" height="24" rx="3" className="ap-fill-surface ap-stroke-border" strokeWidth="1" />
      <path d="M152 40 L170 52 L188 40" fill="none" className="ap-stroke-border" strokeWidth="1" />
      <circle
        cx="180"
        cy="36"
        r="9"
        className={status === "done" ? "ap-fill-success" : "ap-fill-accent"}
      />
      <text x="180" y="39" textAnchor="middle" fontSize="8" fill="#fff" fontFamily="var(--ap-mono)">
        {sent}
      </text>
      {running && !reduce
        ? [0, 1, 2].map((i) => (
            <g key={i} opacity="0.9">
              <polygon points="0,-3 8,0 0,3" className="ap-fill-accent">
                <animateMotion
                  dur="2.4s"
                  begin={`${i * 0.8}s`}
                  repeatCount="indefinite"
                  rotate="auto"
                  path={path}
                />
                <animate
                  attributeName="opacity"
                  values="0;1;1;0"
                  keyTimes="0;0.15;0.85;1"
                  dur="2.4s"
                  begin={`${i * 0.8}s`}
                  repeatCount="indefinite"
                />
              </polygon>
            </g>
          ))
        : null}
    </SceneBox>
  );
}

export function AgentScene({
  agentKey,
  status,
  items,
  progress,
  listMode,
  tall,
  inspector,
}: {
  agentKey: Exclude<PipelineKey, "gate">;
  status: PipelineStatus;
  items?: string[] | null;
  progress?: { done: number; total: number | null } | null;
  listMode?: boolean;
  tall?: boolean;
  inspector?: boolean;
}) {
  switch (agentKey) {
    case "product":
      return (
        <ProductScene
          status={status}
          items={items}
          progress={progress}
          tall={tall}
          inspector={inspector}
        />
      );
    case "buyers":
      return (
        <BuyersScene
          status={status}
          progress={progress}
          listMode={listMode}
          tall={tall}
          inspector={inspector}
        />
      );
    case "accounts":
      return (
        <AccountsScene
          status={status}
          progress={progress}
          tall={tall}
          inspector={inspector}
        />
      );
    case "writer":
      return (
        <WriterScene
          status={status}
          progress={progress}
          tall={tall}
          inspector={inspector}
        />
      );
    case "sender":
      return (
        <SenderScene
          status={status}
          progress={progress}
          tall={tall}
          inspector={inspector}
        />
      );
    default:
      return null;
  }
}

export function AgentIcon({ agent }: { agent: PipelineAgent["agent"] }) {
  const Icon = ICONS[agent] || Circle;
  return <Icon className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />;
}

/** Mobile / narrow fallback: stacked cards (§1 ≤640 / §7.6). */
export function AgentPipelineMobile({
  agents,
  listMode,
  selectedKey,
  onSelect,
}: {
  agents: PipelineAgent[];
  listMode?: boolean;
  selectedKey?: string | null;
  onSelect?: (key: string) => void;
}) {
  return (
    <div className="ap ap-mobile">
      {agents.map((agent) => {
        const time = elapsedLabel(agent.started_at, agent.updated_at);
        return (
          <button
            key={agent.key}
            type="button"
            aria-pressed={selectedKey === agent.key}
            aria-label={`${agent.label}: ${PILL_TEXT[agent.status]}. Show its activity`}
            onClick={() => onSelect?.(agent.key)}
            className={cn(
              "ap-card w-full p-3 text-left",
              `status-${agent.status}`,
              selectedKey === agent.key && "selected",
            )}
          >
            <div className="ap-mobile-card space-y-2">
              <div className="flex items-center gap-2">
                <AgentIcon agent={agent.agent} />
                <span className="text-[13px] font-semibold">{agent.label}</span>
                <StatusPill status={agent.status} />
                {time ? (
                  <span className="ml-auto text-[11px] text-[var(--ap-text-subtle)]">{time}</span>
                ) : null}
              </div>
              {agent.key !== "planner" ? (
                <AgentScene
                  agentKey={agent.key}
                  status={agent.status}
                  items={agent.items}
                  progress={agent.progress}
                  listMode={listMode}
                  tall
                />
              ) : (
                <div className="flex items-center gap-3">
                  <PlannerOrbit agents={agents} size={72} />
                  <p className="text-[12px] text-[var(--ap-text-muted)]">{AGENT_ROLES.planner}</p>
                </div>
              )}
              <StreamLine status={agent.status} detail={agent.detail} stream={agent.stream} />
              {agent.status === "waiting" ? (
                <Link
                  href="/approvals"
                  className="text-[12px] font-medium text-[var(--ap-accent)] underline-offset-2 hover:underline"
                >
                  Review drafts
                </Link>
              ) : agent.count_label ? (
                <span className="text-[12px] font-medium">{agent.count_label}</span>
              ) : null}
              <ProgressBar status={agent.status} progress={agent.progress} />
            </div>
          </button>
        );
      })}
    </div>
  );
}

/** @deprecated Prefer AgentPipelineCanvas; kept as mobile row alias. */
export function AgentPipeline({
  agents,
  onSelectAgent,
  selectedAgent,
}: {
  agents: PipelineAgent[];
  onSelectAgent?: (agent: PipelineAgent) => void;
  selectedAgent?: string | null;
}) {
  const byAgent = useMemo(() => {
    const m = new Map(agents.map((a) => [a.agent, a]));
    return m;
  }, [agents]);
  const selectedKey =
    agents.find((a) => a.agent === selectedAgent)?.key ||
    (selectedAgent as string | null) ||
    null;

  return (
    <AgentPipelineMobile
      agents={agents}
      selectedKey={selectedKey}
      onSelect={(key) => {
        const a = agents.find((x) => x.key === key);
        if (a) onSelectAgent?.(a);
        else {
          const legacy = byAgent.get(key as PipelineAgent["agent"]);
          if (legacy) onSelectAgent?.(legacy);
        }
      }}
    />
  );
}
