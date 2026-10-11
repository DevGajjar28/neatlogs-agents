"use client";

import { useQuery } from "@tanstack/react-query";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { Mono } from "@/components/common/Mono";
import { RelativeTime } from "@/components/common/RelativeTime";
import { StatusBadge } from "@/components/common/StatusBadge";
import { CardSkeleton } from "@/components/common/Skeletons";
import { PageTitle } from "@/components/shell/page-title";
import { useShell } from "@/components/shell/shell-context";
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
  if (step === 2) return "FU1";
  if (step === 3) return "FU2";
  return `Step ${step}`;
}

function formatAbsolute(value: string | null | undefined): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function WhenCell({ row }: { row: OutboxRow }) {
  const sentAbs = formatAbsolute(row.sent_at);
  const schedAbs = formatAbsolute(row.scheduled_at);
  if (sentAbs) {
    return (
      <div className="space-y-0.5">
        <div className="text-[12px] text-[var(--text)]">Sent · {sentAbs}</div>
        <RelativeTime value={row.sent_at} className="text-[11px]" />
      </div>
    );
  }
  if (schedAbs || row.ui_status === "Scheduled") {
    return (
      <div className="space-y-0.5">
        <div className="text-[12px] text-[var(--text)]">
          Scheduled · {schedAbs || "—"}
        </div>
        <RelativeTime value={row.scheduled_at} className="text-[11px]" />
      </div>
    );
  }
  return <span className="text-[12px] text-[var(--text-subtle)]">—</span>;
}

export default function OutboxPage() {
  const { setNewCampaignOpen } = useShell();
  const q = useQuery({
    queryKey: queryKeys.outbox,
    queryFn: listOutbox,
    refetchInterval: 10_000,
  });

  return (
    <>
      <PageTitle title="Outbox" />
      {q.isLoading ? <CardSkeleton /> : null}
      {q.isError ? (
        <ErrorBanner
          message={q.error instanceof ApiError ? q.error.message : "Couldn't load outbox"}
          actionLabel="Retry"
          onAction={() => q.refetch()}
        />
      ) : null}
      {!q.isLoading && (q.data || []).length === 0 ? (
        <EmptyState
          title="No mail sent yet"
          description="Approved emails and follow-ups will appear here after you send from a campaign."
          actionLabel="New campaign"
          onAction={() => setNewCampaignOpen(true)}
        />
      ) : null}
      {(q.data || []).length > 0 ? (
        <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-[12px]">Subject</TableHead>
                <TableHead className="text-[12px]">Step</TableHead>
                <TableHead className="text-[12px]">From</TableHead>
                <TableHead className="text-[12px]">Mode</TableHead>
                <TableHead className="text-[12px]">Status</TableHead>
                <TableHead className="text-[12px]">When</TableHead>
                <TableHead className="text-[12px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(q.data || []).map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="max-w-[240px] truncate text-[13px]">
                    {row.subject || "(no subject)"}
                  </TableCell>
                  <TableCell className="text-[12px] text-[var(--text-muted)]">
                    {stepLabel(row.step)}
                  </TableCell>
                  <TableCell>
                    <div className="text-[13px]">{row.from_label}</div>
                    {row.actual_recipient_masked ? (
                      <Mono className="text-[11px] text-[var(--text-subtle)]">
                        {row.actual_recipient_masked}
                      </Mono>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <span className="rounded-[6px] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[11px] font-medium">
                      {modeLabel(row.send_mode)}
                    </span>
                  </TableCell>
                  <TableCell>
                    <StatusBadge label={row.ui_status} />
                  </TableCell>
                  <TableCell>
                    <WhenCell row={row} />
                  </TableCell>
                  <TableCell>
                    {row.open_in_gmail_url ? (
                      <a
                        href={row.open_in_gmail_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[12px] font-medium text-[var(--accent)] underline-offset-2 hover:underline"
                      >
                        Open in Gmail ↗
                      </a>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
    </>
  );
}
