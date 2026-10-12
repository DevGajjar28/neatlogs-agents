"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { Mono } from "@/components/common/Mono";
import { RelativeTime } from "@/components/common/RelativeTime";
import { StatusBadge } from "@/components/common/StatusBadge";
import { CardSkeleton } from "@/components/common/Skeletons";
import { PageTitle } from "@/components/shell/page-title";
import { useShell } from "@/components/shell/shell-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, listOutbox, type OutboxRow } from "@/lib/api";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

function modeLabel(mode: string): string {
  switch (mode) {
    case "gmail_drafts":
      return "Drafts";
    case "gmail_test":
      return "Test";
    case "gmail_live":
      return "Live";
    default:
      return "Sandbox";
  }
}

function stepLabel(step: number): string {
  if (step === 1) return "Email 1";
  if (step === 2) return "Follow-up 1";
  if (step === 3) return "Follow-up 2";
  return `Step ${step}`;
}

function formatAbsolute(value: string | null | undefined): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const STATUS_FILTERS = [
  { id: "all", label: "All" },
  { id: "Sent", label: "Sent" },
  { id: "Scheduled", label: "Scheduled" },
  { id: "Replied", label: "Replied" },
  { id: "Bounced", label: "Bounced" },
  { id: "Opted out", label: "Opted out" },
] as const;

export default function OutboxPage() {
  const { setNewCampaignOpen } = useShell();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [modeFilter, setModeFilter] = useState<string>("all");
  const [qtext, setQtext] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const q = useQuery({
    queryKey: queryKeys.outbox,
    queryFn: listOutbox,
    refetchInterval: 10_000,
  });

  const items = q.data?.items || [];
  const filtered = useMemo(() => {
    const needle = qtext.trim().toLowerCase();
    return items.filter((row) => {
      if (statusFilter !== "all" && row.ui_status !== statusFilter) return false;
      if (modeFilter !== "all" && row.send_mode !== modeFilter) return false;
      if (!needle) return true;
      const hay = [
        row.subject,
        row.campaign_name,
        row.from_label,
        row.actual_recipient_masked,
        row.body_preview,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(needle);
    });
  }, [items, statusFilter, modeFilter, qtext]);

  const modes = useMemo(() => {
    const set = new Set(items.map((i) => i.send_mode).filter(Boolean));
    return Array.from(set);
  }, [items]);

  return (
    <>
      <PageTitle title="Outbox" />
      <p className="mb-4 max-w-2xl text-[13px] leading-5 text-[var(--text-muted)]">
        Everything ReachPilot has queued or delivered — open a row to read the copy, jump to
        the campaign, or check Gmail.
      </p>

      {q.isLoading ? <CardSkeleton /> : null}
      {q.isError ? (
        <ErrorBanner
          message={q.error instanceof ApiError ? q.error.message : "Couldn't load outbox"}
          actionLabel="Retry"
          onAction={() => q.refetch()}
        />
      ) : null}

      {!q.isLoading && items.length === 0 ? (
        <EmptyState
          title="No mail yet"
          description="When Autopilot sends (or you approve a draft), every message lands here with status and a Gmail link."
          actionLabel="New campaign"
          onAction={() => setNewCampaignOpen(true)}
        />
      ) : null}

      {items.length > 0 ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {[
              { label: "Total", value: q.data?.total ?? 0 },
              { label: "Sent", value: q.data?.sent ?? 0 },
              { label: "Scheduled", value: q.data?.scheduled ?? 0 },
              { label: "Replied", value: q.data?.replied ?? 0 },
              { label: "Opted out", value: q.data?.opted_out ?? 0 },
              { label: "Bounced", value: q.data?.bounced ?? 0 },
            ].map((s) => (
              <div
                key={s.label}
                className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] px-3 py-2"
              >
                <p className="text-[11px] text-[var(--text-subtle)]">{s.label}</p>
                <p className="text-[18px] font-semibold tabular-nums">{s.value}</p>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap gap-1">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setStatusFilter(f.id)}
                  className={cn(
                    "rounded-[6px] px-2.5 py-1 text-[12px] font-medium",
                    statusFilter === f.id
                      ? "bg-[var(--surface-muted)] text-[var(--text)]"
                      : "text-[var(--text-muted)] hover:bg-[var(--surface-muted)]",
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                className="h-8 rounded-[6px] border border-[var(--border)] bg-[var(--surface)] px-2 text-[12px]"
                value={modeFilter}
                onChange={(e) => setModeFilter(e.target.value)}
              >
                <option value="all">All modes</option>
                {modes.map((m) => (
                  <option key={m} value={m}>
                    {modeLabel(m)}
                  </option>
                ))}
              </select>
              <Input
                value={qtext}
                onChange={(e) => setQtext(e.target.value)}
                placeholder="Search subject, campaign…"
                className="h-8 w-full max-w-[220px] rounded-[6px] text-[12px]"
              />
            </div>
          </div>

          {filtered.length === 0 ? (
            <p className="text-[13px] text-[var(--text-muted)]">No messages match these filters.</p>
          ) : (
            <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-[12px]">Subject</TableHead>
                    <TableHead className="text-[12px]">Campaign</TableHead>
                    <TableHead className="text-[12px]">To</TableHead>
                    <TableHead className="text-[12px]">Mode</TableHead>
                    <TableHead className="text-[12px]">Status</TableHead>
                    <TableHead className="text-[12px]">When</TableHead>
                    <TableHead className="text-[12px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((row) => (
                    <OutboxTableRow
                      key={row.id}
                      row={row}
                      expanded={expanded === row.id}
                      onToggle={() =>
                        setExpanded((id) => (id === row.id ? null : row.id))
                      }
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      ) : null}
    </>
  );
}

function OutboxTableRow({
  row,
  expanded,
  onToggle,
}: {
  row: OutboxRow;
  expanded: boolean;
  onToggle: () => void;
}) {
  const when =
    formatAbsolute(row.sent_at) ||
    (row.scheduled_at ? `Sched · ${formatAbsolute(row.scheduled_at)}` : null);

  return (
    <>
      <TableRow
        className="cursor-pointer"
        onClick={onToggle}
      >
        <TableCell className="max-w-[220px]">
          <div className="truncate text-[13px] font-medium">
            {row.subject || "(no subject)"}
          </div>
          <div className="text-[11px] text-[var(--text-subtle)]">{stepLabel(row.step)}</div>
        </TableCell>
        <TableCell className="max-w-[140px] truncate text-[12px] text-[var(--text-muted)]">
          {row.campaign_name || "—"}
        </TableCell>
        <TableCell>
          <Mono className="text-[11px]">
            {row.actual_recipient_masked || "—"}
          </Mono>
        </TableCell>
        <TableCell>
          <span className="rounded-[6px] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[11px] font-medium">
            {modeLabel(row.send_mode)}
          </span>
        </TableCell>
        <TableCell>
          <StatusBadge label={row.ui_status} />
          {row.reply_classification ? (
            <div className="mt-0.5 text-[10px] text-[var(--text-subtle)]">
              {row.reply_classification.replace(/_/g, " ")}
            </div>
          ) : null}
        </TableCell>
        <TableCell className="text-[12px]">
          {when ? (
            <div className="space-y-0.5">
              <div>{when}</div>
              <RelativeTime
                value={row.sent_at || row.scheduled_at}
                className="text-[11px]"
              />
            </div>
          ) : (
            "—"
          )}
        </TableCell>
        <TableCell onClick={(e) => e.stopPropagation()}>
          {row.open_in_gmail_url ? (
            <a
              href={row.open_in_gmail_url}
              target="_blank"
              rel="noreferrer"
              className="text-[12px] font-medium text-[var(--accent)] underline-offset-2 hover:underline"
            >
              Gmail ↗
            </a>
          ) : null}
        </TableCell>
      </TableRow>
      {expanded ? (
        <TableRow>
          <TableCell colSpan={7} className="bg-[var(--surface-muted)]">
            <div className="space-y-2 py-1 text-[12px]">
              <p className="whitespace-pre-wrap leading-5 text-[var(--text)]">
                {row.body_preview || "No body preview."}
                {row.body_preview && row.body_preview.length >= 200 ? "…" : ""}
              </p>
              <div className="flex flex-wrap gap-2">
                {row.campaign_id ? (
                  <Button asChild variant="outline" className="h-7 px-2 text-[11px]">
                    <Link href={`/campaigns/${row.campaign_id}`}>Open campaign</Link>
                  </Button>
                ) : null}
                <span className="self-center text-[11px] text-[var(--text-subtle)]">
                  From {row.from_label}
                </span>
              </div>
            </div>
          </TableCell>
        </TableRow>
      ) : null}
    </>
  );
}
