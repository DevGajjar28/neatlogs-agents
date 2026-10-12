"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { PageTitle } from "@/components/shell/page-title";
import { useShell } from "@/components/shell/shell-context";
import { StatusBadge } from "@/components/common/StatusBadge";
import { RelativeTime } from "@/components/common/RelativeTime";
import {
  ApiError,
  extractCredits,
  getPendingApprovals,
  getSystemStatus,
  listCampaigns,
} from "@/lib/api";
import { formatCredits, friendlyModelName } from "@/lib/format";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  const { setNewCampaignOpen } = useShell();

  const campaignsQ = useQuery({
    queryKey: queryKeys.campaigns,
    queryFn: listCampaigns,
    refetchInterval: 8_000,
  });

  const statusQ = useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: getSystemStatus,
    refetchInterval: 30_000,
  });

  const waiting = useMemo(
    () => (campaignsQ.data || []).filter((c) => c.status === "waiting_approval"),
    [campaignsQ.data],
  );

  const pendingQueries = useQueries({
    queries: waiting.map((c) => ({
      queryKey: queryKeys.pendingApprovals(c.id),
      queryFn: () => getPendingApprovals(c.id),
      refetchInterval: 8_000,
    })),
  });

  const pendingCount = useMemo(
    () => pendingQueries.reduce((sum, q) => sum + (q.data?.items?.length || 0), 0),
    [pendingQueries],
  );

  const campaigns = campaignsQ.data || [];
  const running = campaigns.filter((c) =>
    ["running", "researching", "writing", "sending"].includes(c.status),
  ).length;
  const credits = statusQ.data ? extractCredits(statusQ.data) : null;
  const model = statusQ.data
    ? friendlyModelName(statusQ.data.llm?.fast || statusQ.data.llm?.strong)
    : "—";

  return (
    <>
      <PageTitle title="Dashboard" />

      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-[var(--text)]">
            Dashboard
          </h1>
          <p className="mt-1 text-[13px] text-[var(--text-muted)]">
            ReachPilot at a glance — campaigns, approvals, and workspace spend.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/landing"
            className="inline-flex h-8 items-center rounded-[6px] border border-[var(--border)] px-3 text-[13px] font-medium text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)]"
          >
            Landing
          </Link>
          <button
            type="button"
            onClick={() => setNewCampaignOpen(true)}
            className="inline-flex h-8 items-center rounded-[6px] bg-[var(--primary)] px-3 text-[13px] font-medium text-[var(--primary-fg)] hover:bg-[var(--primary-hover)]"
          >
            New campaign
          </button>
        </div>
      </div>

      {campaignsQ.isError ? (
        <ErrorBanner
          message={
            campaignsQ.error instanceof ApiError
              ? campaignsQ.error.message
              : "Couldn't load campaigns."
          }
          actionLabel="Retry"
          onAction={() => campaignsQ.refetch()}
        />
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Campaigns" value={String(campaigns.length)} href="/campaigns" />
        <Stat
          label="Waiting approval"
          value={String(pendingCount)}
          href="/approvals"
          hot={pendingCount > 0}
        />
        <Stat label="Active runs" value={String(running)} href="/campaigns" />
        <Stat
          label="Credits left"
          value={credits == null ? "—" : formatCredits(credits)}
          href="/settings"
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <section className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)]">
          <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
            <h2 className="text-[13px] font-semibold text-[var(--text)]">Recent campaigns</h2>
            <Link
              href="/campaigns"
              className="text-[12px] font-medium text-[var(--accent)] hover:underline"
            >
              View all
            </Link>
          </div>
          {campaigns.length === 0 ? (
            <p className="px-4 py-8 text-[13px] text-[var(--text-muted)]">
              No campaigns yet. Paste a seller website to start.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--border)]">
              {campaigns.slice(0, 6).map((c) => (
                <li key={c.id}>
                  <Link
                    href={`/campaigns/${c.id}`}
                    className="flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--surface-muted)]"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium text-[var(--text)]">
                        {c.seller_name || c.id}
                      </p>
                      <p className="text-[11px] text-[var(--text-subtle)]">
                        <RelativeTime value={c.started_at} />
                      </p>
                    </div>
                    <StatusBadge status={c.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
          <h2 className="text-[13px] font-semibold text-[var(--text)]">Workspace</h2>
          <dl className="mt-4 space-y-3 text-[13px]">
            <Row
              k="Research"
              v={statusQ.data?.data_mode === "live" ? "Live" : statusQ.data ? "Replay" : "—"}
            />
            <Row k="Model" v={model} />
            <Row
              k="Hunter"
              v={
                statusQ.data
                  ? statusQ.data.hunter?.configured
                    ? "Connected"
                    : "Off"
                  : "—"
              }
            />
            <Row
              k="Tracing"
              v={
                statusQ.data
                  ? statusQ.data.neatlogs?.configured
                    ? "neatlogs on"
                    : "Off"
                  : "—"
              }
            />
          </dl>
          <div className="mt-6 border-t border-[var(--border)] pt-4">
            <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-subtle)]">
              Measured unit economics
            </p>
            <p className="mt-2 text-[22px] font-semibold tabular-nums text-[var(--text)]">
              $0.29–0.34
              <span className="ml-1.5 text-[13px] font-normal text-[var(--text-muted)]">
                blended / lead
              </span>
            </p>
            <p className="mt-1 text-[12px] text-[var(--text-muted)]">
              5.31 credits · $0.010 LLM · $0.80/lead surplus ~$1.9k–2.1k/mo
            </p>
            <Link
              href="/landing"
              className="mt-3 inline-block text-[12px] font-medium text-[var(--accent)] hover:underline"
            >
              Cost & profit on landing →
            </Link>
          </div>
        </section>
      </div>
    </>
  );
}

function Stat({
  label,
  value,
  href,
  hot,
}: {
  label: string;
  value: string;
  href: string;
  hot?: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-[8px] border border-[var(--border)] bg-[var(--surface)] px-4 py-3 hover:border-[var(--border-strong)]",
        hot && "border-[var(--status-warning)]/30 bg-[var(--status-warning-soft)]",
      )}
    >
      <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-subtle)]">
        {label}
      </p>
      <p className="mt-1 text-[22px] font-semibold tabular-nums text-[var(--text)]">{value}</p>
    </Link>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-[var(--text-muted)]">{k}</dt>
      <dd className="truncate font-medium text-[var(--text)]">{v}</dd>
    </div>
  );
}
