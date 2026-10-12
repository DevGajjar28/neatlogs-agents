"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import {
  ApiError,
  extractCredits,
  getSystemStatus,
  type SystemStatus as SystemStatusType,
} from "@/lib/api";
import { formatCredits, friendlyModelName } from "@/lib/format";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

function creditBarPct(status: SystemStatusType, credits: number | null): number {
  const cap = status.max_credits || 400;
  if (credits == null || cap <= 0) return 0;
  return Math.max(0, Math.min(100, (credits / cap) * 100));
}

function dataModeCopy(mode: string): { title: string; hint: string } {
  if (mode === "live") {
    return {
      title: "Live research",
      hint: "Pulls fresh company & people data",
    };
  }
  return {
    title: "Saved data",
    hint: "Uses cached results — no new data spend",
  };
}

function sendModeCopy(mode: string | undefined): { title: string; hint: string } {
  switch (mode) {
    case "gmail_live":
      return { title: "Gmail sending", hint: "Emails go to real inboxes" };
    case "gmail_test":
      return { title: "Gmail test", hint: "Only sends to your allowlisted addresses" };
    case "gmail_drafts":
      return { title: "Gmail drafts", hint: "Creates drafts — you send manually" };
    default:
      return { title: "Sandbox mail", hint: "Safe local delivery for demos" };
  }
}

export function SystemStatus({ collapsed }: { collapsed: boolean }) {
  const q = useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: getSystemStatus,
    refetchInterval: 30_000,
  });

  if (q.isLoading) {
    return (
      <div
        className={cn("space-y-2 p-3 text-[12px] text-[var(--text-subtle)]", collapsed && "px-2")}
      >
        Loading workspace…
      </div>
    );
  }

  if (q.isError) {
    const msg =
      q.error instanceof ApiError
        ? q.error.message
        : "Can't reach SignalSDR right now. Start the backend, then try again.";
    return (
      <Link
        href="/settings"
        className={cn(
          "block rounded-[6px] border border-[var(--status-danger)]/20 bg-[var(--status-danger-soft)] p-2 text-[11px] leading-4 text-[var(--status-danger)]",
          collapsed && "px-1.5 text-center",
        )}
        title={msg}
      >
        {collapsed ? "Offline" : msg}
      </Link>
    );
  }

  const status = q.data!;
  const credits = extractCredits(status);
  const tracingOn = Boolean(status.neatlogs?.configured);
  const hunterOn = Boolean(status.hunter?.configured);
  const modelLabel = friendlyModelName(status.llm?.fast || status.llm?.strong);
  const data = dataModeCopy(status.data_mode);
  const send = sendModeCopy(status.max_send_mode);
  const paused = Boolean(status.sending_paused);
  const cap = status.max_credits || 400;

  if (collapsed) {
    return (
      <Link
        href="/settings"
        className="flex flex-col items-center gap-1 rounded-[6px] p-1 text-[10px] text-[var(--text-muted)] hover:bg-[var(--surface-muted)]"
        title={`${data.title} · ${formatCredits(credits)} data credits · ${modelLabel}`}
      >
        <span
          className={cn(
            "size-2 rounded-full",
            paused
              ? "bg-[var(--status-danger)]"
              : tracingOn
                ? "bg-[var(--status-success)]"
                : "bg-[var(--status-warning)]",
          )}
          aria-hidden
        />
        <span className="font-medium tabular-nums">{formatCredits(credits)}</span>
      </Link>
    );
  }

  return (
    <Link
      href="/settings"
      className="block space-y-3 rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-3 hover:border-[var(--border-strong)]"
    >
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-subtle)]">
          Workspace
        </p>
        <p className="mt-0.5 text-[11px] leading-4 text-[var(--text-muted)]">
          How SignalSDR finds leads and sends mail right now.
        </p>
      </div>

      <div className="space-y-2">
        <StatusRow label={data.title} value={status.data_mode === "live" ? "On" : "Replay"} hint={data.hint} />
        <StatusRow label={send.title} value={paused ? "Paused" : "Ready"} hint={paused ? "All outbound mail is paused" : send.hint} />
        {status.demo_mode ? (
          <StatusRow
            label="Demo safety"
            value="On"
            hint="Live prospect sends stay locked"
            icon={<Lock className="size-3 shrink-0" strokeWidth={1.75} aria-hidden />}
          />
        ) : null}
      </div>

      <div className="space-y-1.5 border-t border-[var(--border)] pt-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[12px] font-medium text-[var(--text)]">Company research</span>
          <span className="text-[12px] tabular-nums text-[var(--text)]">
            {formatCredits(credits)} left
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-muted)]">
          <div
            className="h-full rounded-full bg-[var(--accent)]"
            style={{ width: `${creditBarPct(status, credits)}%` }}
          />
        </div>
        <p className="text-[11px] leading-4 text-[var(--text-muted)]">
          Crustdata budget for finding companies and people
          {credits != null ? ` · cap ${formatCredits(cap)}` : ""}.
        </p>
      </div>

      <div className="space-y-0.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[12px] font-medium text-[var(--text)]">Backup email finder</span>
          <span
            className={cn(
              "text-[12px] font-medium",
              hunterOn ? "text-[var(--status-success)]" : "text-[var(--text-muted)]",
            )}
          >
            {hunterOn ? "Connected" : "Not set up"}
          </span>
        </div>
        <p className="text-[11px] leading-4 text-[var(--text-muted)]">
          {hunterOn
            ? "Hunter.io fills emails when primary data is thin or out of credits."
            : "Add a Hunter.io key to keep finding emails if Crustdata runs low."}
        </p>
      </div>

      <div className="space-y-0.5 border-t border-[var(--border)] pt-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[12px] font-medium text-[var(--text)]">Writing assistant</span>
          <span className="text-[12px] text-[var(--text)]">{modelLabel}</span>
        </div>
        <p className="text-[11px] leading-4 text-[var(--text-muted)]">
          AI model used for research summaries and email drafts.
        </p>
      </div>

      <div className="flex items-start gap-2">
        <span
          className={cn(
            "mt-1 size-1.5 shrink-0 rounded-full",
            tracingOn ? "bg-[var(--status-success)]" : "bg-[var(--text-subtle)]",
          )}
          aria-hidden
        />
        <div>
          <p className="text-[12px] font-medium text-[var(--text)]">
            {tracingOn ? "Activity log on" : "Activity log off"}
          </p>
          <p className="text-[11px] leading-4 text-[var(--text-muted)]">
            {tracingOn
              ? "Run steps are recorded so you can audit what the agents did."
              : "Enable neatlogs tracing to record agent activity."}
          </p>
        </div>
      </div>
    </Link>
  );
}

function StatusRow({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: string;
  hint: string;
  icon?: ReactNode;
}) {
  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1 text-[12px] font-medium text-[var(--text)]">
          {icon}
          {label}
        </span>
        <span className="text-[12px] text-[var(--text-muted)]">{value}</span>
      </div>
      <p className="text-[11px] leading-4 text-[var(--text-muted)]">{hint}</p>
    </div>
  );
}
