"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import {
  ApiError,
  extractCredits,
  getSystemStatus,
  type SystemStatus as SystemStatusType,
} from "@/lib/api";
import { formatCredits, shortModelName } from "@/lib/format";
import { queryKeys } from "@/lib/keys";
import { Mono } from "@/components/common/Mono";
import { cn } from "@/lib/utils";

function creditBarPct(status: SystemStatusType, credits: number | null): number {
  const cap = status.max_credits || 400;
  if (credits == null || cap <= 0) return 0;
  return Math.max(0, Math.min(100, (credits / cap) * 100));
}

export function SystemStatus({ collapsed }: { collapsed: boolean }) {
  const q = useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: getSystemStatus,
    refetchInterval: 30_000,
  });

  if (q.isLoading) {
    return (
      <div className={cn("space-y-2 p-3 text-[12px] text-[var(--text-subtle)]", collapsed && "px-2")}>
        Loading status…
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
  const modeLabel = status.data_mode === "live" ? "Live" : "Replay";
  const model = shortModelName(status.llm?.fast || status.llm?.strong);

  if (collapsed) {
    return (
      <Link
        href="/settings"
        className="flex flex-col items-center gap-1 rounded-[6px] p-1 text-[10px] text-[var(--text-muted)] hover:bg-[var(--surface-muted)]"
        title={`${modeLabel} · ${formatCredits(credits)} credits · ${tracingOn ? "Tracing on" : "Tracing off"}`}
      >
        <span
          className={cn(
            "size-2 rounded-full",
            tracingOn ? "bg-[var(--status-success)]" : "bg-[var(--status-danger)]",
          )}
          aria-hidden
        />
        <Mono className="text-[10px]">{formatCredits(credits)}</Mono>
      </Link>
    );
  }

  return (
    <Link
      href="/settings"
      className="block space-y-2 rounded-[6px] border border-[var(--border)] bg-[var(--surface)] p-3 hover:border-[var(--border-strong)]"
    >
      <div className="flex flex-wrap gap-1.5">
        <span className="rounded-[6px] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--text)]">
          {modeLabel}
        </span>
        {status.demo_mode ? (
          <span className="inline-flex items-center gap-1 rounded-[6px] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--text)]">
            <Lock className="size-3" strokeWidth={1.75} aria-hidden />
            Demo sends
          </span>
        ) : null}
      </div>
      <div className="space-y-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[11px] text-[var(--text-muted)]">Crustdata</span>
          <Mono>{formatCredits(credits)} credits</Mono>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-[var(--surface-muted)]">
          <div
            className="h-full rounded-full bg-[var(--accent)]"
            style={{ width: `${creditBarPct(status, credits)}%` }}
          />
        </div>
      </div>
      <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
        <span
          className={cn(
            "size-1.5 rounded-full",
            tracingOn ? "bg-[var(--status-success)]" : "bg-[var(--status-danger)]",
          )}
          aria-hidden
        />
        <span>{tracingOn ? "Tracing on" : "Tracing off"}</span>
      </div>
      <div className="text-[11px] text-[var(--text-muted)]">
        Bedrock · <Mono className="text-[11px]">{model}</Mono>
      </div>
    </Link>
  );
}
