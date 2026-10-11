"use client";

import {
  AlertCircle,
  CheckCircle2,
  Circle,
  Clock,
  Mail,
  Map,
  Search,
  Send,
  Sparkles,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { PipelineAgent } from "@/lib/api";
import { cn } from "@/lib/utils";

const ICONS: Record<PipelineAgent["agent"], LucideIcon> = {
  planner: Map,
  product_researcher: Search,
  buyer_finder: Users,
  account_researcher: Sparkles,
  email_writer_verifier: Mail,
  sender: Send,
};

const STATUS_META: Record<
  PipelineAgent["status"],
  { label: string; className: string; Icon: LucideIcon; dot: string }
> = {
  idle: {
    label: "Idle",
    className: "bg-[var(--surface-muted)] text-[var(--text-subtle)]",
    Icon: Circle,
    dot: "bg-[var(--text-subtle)]",
  },
  running: {
    label: "Running",
    className: "bg-[var(--status-info-soft)] text-[var(--status-info)]",
    Icon: Circle,
    dot: "bg-[var(--accent)] animate-pipeline-pulse",
  },
  waiting: {
    label: "Waiting",
    className: "bg-[var(--status-warning-soft)] text-[var(--status-warning)]",
    Icon: Clock,
    dot: "bg-[var(--status-warning)]",
  },
  done: {
    label: "Done",
    className: "bg-[var(--status-success-soft)] text-[var(--status-success)]",
    Icon: CheckCircle2,
    dot: "bg-[var(--status-success)]",
  },
  failed: {
    label: "Failed",
    className: "bg-[var(--status-danger-soft)] text-[var(--status-danger)]",
    Icon: AlertCircle,
    dot: "bg-[var(--status-danger)]",
  },
};

type Props = {
  agents: PipelineAgent[];
  onSelectAgent?: (agent: PipelineAgent) => void;
  selectedAgent?: string | null;
};

export function AgentPipeline({ agents, onSelectAgent, selectedAgent }: Props) {
  return (
    <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
      <h3 className="mb-3 text-[14px] font-semibold">Agent pipeline</h3>
      <ol className="flex flex-col md:flex-row md:items-stretch">
        {agents.map((agent, index) => {
          const Icon = ICONS[agent.agent] || Circle;
          const meta = STATUS_META[agent.status];
          const StatusIcon = meta.Icon;
          const next = agents[index + 1];
          const connectorDone = agent.status === "done";
          return (
            <li
              key={agent.agent}
              className="flex min-w-0 flex-1 flex-col md:flex-row md:items-center"
            >
              <button
                type="button"
                onClick={() => onSelectAgent?.(agent)}
                className={cn(
                  "flex w-full min-w-0 flex-1 flex-col gap-1.5 rounded-[6px] border px-3 py-3 text-left transition-colors",
                  agent.status === "idle" && "border-[var(--border-strong)]",
                  agent.status === "running" && "border-[var(--accent)] bg-[var(--accent-soft)]",
                  agent.status === "waiting" &&
                    "border-[var(--status-warning)] bg-[var(--status-warning-soft)]",
                  agent.status === "done" && "border-[var(--border)]",
                  agent.status === "failed" &&
                    "border-[var(--status-danger)] bg-[var(--status-danger-soft)]",
                  selectedAgent === agent.agent && "ring-2 ring-[var(--accent)] ring-offset-1",
                )}
              >
                <div className="flex items-center gap-2">
                  <Icon className="size-4 shrink-0 text-[var(--text)]" strokeWidth={1.75} />
                  <span className="truncate text-[12px] font-semibold text-[var(--text)]">
                    {agent.label}
                  </span>
                </div>
                <span
                  className={cn(
                    "inline-flex w-fit items-center gap-1.5 rounded-[6px] px-1.5 py-0.5 text-[11px] font-medium",
                    meta.className,
                  )}
                >
                  <span className={cn("size-1.5 shrink-0 rounded-full", meta.dot)} aria-hidden />
                  <StatusIcon className="size-3 shrink-0" strokeWidth={2} aria-hidden />
                  {meta.label}
                </span>
                <p
                  className={cn(
                    "line-clamp-2 min-h-[2.5em] text-[11px] leading-4",
                    agent.status === "idle" ? "text-[var(--text-subtle)]" : "text-[var(--text-muted)]",
                  )}
                >
                  {agent.status === "idle" ? "—" : agent.detail || "—"}
                </p>
                {agent.count_label ? (
                  <span className="text-[11px] font-medium text-[var(--text)]">
                    {agent.count_label}
                  </span>
                ) : (
                  <span className="text-[11px] text-[var(--text-subtle)]">&nbsp;</span>
                )}
              </button>
              {next ? (
                <div
                  className={cn(
                    "mx-auto h-3 w-0 border-l-2 md:mx-0 md:h-0 md:w-3 md:border-l-0 md:border-t-2",
                    connectorDone
                      ? "border-solid border-[var(--accent)]"
                      : "border-dashed border-[var(--border-strong)]",
                  )}
                  aria-hidden
                />
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
