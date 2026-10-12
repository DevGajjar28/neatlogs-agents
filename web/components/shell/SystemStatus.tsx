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

export function SystemStatus({ collapsed }: { collapsed: boolean }) {
  const q = useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: getSystemStatus,
    refetchInterval: 30_000,
  });

  if (q.isLoading) {
    return (
      <div
        className={cn(
          "px-2 py-2 text-[11px] text-[var(--text-subtle)]",
          collapsed && "text-center",
        )}
      >
        …
      </div>
    );
  }

  if (q.isError) {
    const msg =
      q.error instanceof ApiError
        ? q.error.message
        : "Can't reach the API. Check EC2 / local backend.";
    return (
      <Link
        href="/settings"
        className={cn(
          "block rounded-[6px] border border-[var(--status-danger)]/20 bg-[var(--status-danger-soft)] px-2.5 py-2 text-[11px] leading-4 text-[var(--status-danger)]",
          collapsed && "px-1.5 text-center",
        )}
        title={msg}
      >
        {collapsed ? "Offline" : "API offline"}
      </Link>
    );
  }

  const status = q.data!;
  const credits = extractCredits(status);
  const tracingOn = Boolean(status.neatlogs?.configured);
  const hunterOn = Boolean(status.hunter?.configured);
  const modelLabel = friendlyModelName(status.llm?.fast || status.llm?.strong);
  const live = status.data_mode === "live";
  const paused = Boolean(status.sending_paused);
  const sendShort =
    status.max_send_mode === "gmail_live"
      ? "Gmail"
      : status.max_send_mode === "gmail_test"
        ? "Test"
        : status.max_send_mode === "gmail_drafts"
          ? "Drafts"
          : "Sandbox";

  if (collapsed) {
    return (
      <Link
        href="/settings"
        className="flex flex-col items-center gap-1.5 rounded-[6px] p-1.5 text-[10px] text-[var(--text-muted)] hover:bg-[var(--surface-muted)]"
        title={`${live ? "Live" : "Replay"} · ${formatCredits(credits)} credits · ${modelLabel}`}
      >
        <span
          className={cn(
            "size-2 rounded-full",
            paused
              ? "bg-[var(--status-danger)]"
              : tracingOn
                ? "bg-[var(--status-success)]"
                : "bg-[var(--text-subtle)]",
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
      className="block rounded-[8px] border border-[var(--border)] bg-[var(--surface)] px-3 py-3 hover:border-[var(--border-strong)]"
      title="Open Settings for full workspace details"
    >
      <div className="flex flex-wrap gap-1.5">
        <Pill>{live ? "Live" : "Replay"}</Pill>
        <Pill>{paused ? "Paused" : sendShort}</Pill>
        {status.demo_mode ? (
          <Pill>
            <Lock className="size-2.5" strokeWidth={2} aria-hidden />
            Demo
          </Pill>
        ) : null}
      </div>

      <div className="mt-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[11px] text-[var(--text-muted)]">Credits</span>
          <span className="text-[12px] font-medium tabular-nums text-[var(--text)]">
            {formatCredits(credits)}
          </span>
        </div>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-[var(--surface-muted)]">
          <div
            className="h-full rounded-full bg-[var(--accent)]"
            style={{ width: `${creditBarPct(status, credits)}%` }}
          />
        </div>
      </div>

      <p className="mt-3 truncate text-[11px] leading-4 text-[var(--text-muted)]">
        {hunterOn ? "Hunter" : "No Hunter"}
        <span className="mx-1.5 text-[var(--border-strong)]">·</span>
        {modelLabel}
        <span className="mx-1.5 text-[var(--border-strong)]">·</span>
        Trace {tracingOn ? "on" : "off"}
      </p>
    </Link>
  );
}

function Pill({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-[5px] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--text)]">
      {children}
    </span>
  );
}
