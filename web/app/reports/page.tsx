"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { RelativeTime } from "@/components/common/RelativeTime";
import { StatusBadge } from "@/components/common/StatusBadge";
import { CardSkeleton } from "@/components/common/Skeletons";
import { PageTitle } from "@/components/shell/page-title";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, getReports } from "@/lib/api";
import { formatCredits } from "@/lib/format";
import { queryKeys } from "@/lib/keys";

function pct(rate: number | null | undefined): string {
  if (rate == null || Number.isNaN(rate)) return "—";
  return `${Math.round(rate * 100)}%`;
}

export default function ReportsPage() {
  const router = useRouter();
  const q = useQuery({
    queryKey: queryKeys.reports,
    queryFn: getReports,
    refetchInterval: 15_000,
  });

  const data = q.data;
  // Show any campaign row — users expect completed runs even before first send.
  const hasActivity = Boolean(data?.rows?.length);

  return (
    <>
      <PageTitle title="Reports" />
      <p className="mb-4 max-w-2xl text-[13px] leading-5 text-[var(--text-muted)]">
        How your campaigns are performing — sent mail, replies, meetings booked, and
        Crustdata credits spent. Click a campaign to dig in.
      </p>

      {q.isLoading ? <CardSkeleton /> : null}
      {q.isError ? (
        <ErrorBanner
          message={q.error instanceof ApiError ? q.error.message : "Couldn't load reports"}
          actionLabel="Retry"
          onAction={() => q.refetch()}
        />
      ) : null}

      {!q.isLoading && !hasActivity ? (
        <EmptyState
          title="Nothing to report yet"
          description="Run a campaign and let Autopilot send. Reply rate, meetings, and credit spend will show up here."
          actionLabel="Open campaigns"
          onAction={() => router.push("/campaigns")}
        />
      ) : null}

      {hasActivity && data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {[
              { label: "Campaigns", value: String(data.campaigns) },
              { label: "Emails sent", value: String(data.emails_sent) },
              { label: "Replies", value: String(data.replies) },
              { label: "Reply rate", value: pct(data.reply_rate) },
              { label: "Meetings", value: String(data.meetings) },
              {
                label: "Credits spent",
                value: formatCredits(data.credits_spent),
              },
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

          {(data.opted_out > 0 || data.bounced > 0) && (
            <p className="text-[12px] text-[var(--text-muted)]">
              Watch-outs: {data.opted_out} opted out · {data.bounced} bounced. Pause or
              fix the mail account in Settings if bounces climb.
            </p>
          )}

          <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)]">
            <div className="border-b border-[var(--border)] px-4 py-3">
              <h3 className="text-[14px] font-semibold">By campaign</h3>
              <p className="text-[12px] text-[var(--text-muted)]">
                Compare which runs get replies and meetings for the credits you spent.
              </p>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-[12px]">Campaign</TableHead>
                  <TableHead className="text-[12px]">Status</TableHead>
                  <TableHead className="text-[12px]">Sent</TableHead>
                  <TableHead className="text-[12px]">Replies</TableHead>
                  <TableHead className="text-[12px]">Meetings</TableHead>
                  <TableHead className="text-[12px]">Reply rate</TableHead>
                  <TableHead className="text-[12px]">Credits</TableHead>
                  <TableHead className="text-[12px]">Started</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.rows.map((row) => (
                  <TableRow key={row.campaign_id}>
                    <TableCell>
                      <Link
                        href={`/campaigns/${row.campaign_id}`}
                        className="text-[13px] font-medium text-[var(--accent)] underline-offset-2 hover:underline"
                      >
                        {row.seller_name}
                      </Link>
                      <div className="text-[11px] text-[var(--text-subtle)]">
                        {row.leads} leads · {row.mode}
                      </div>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={row.status} />
                    </TableCell>
                    <TableCell className="tabular-nums text-[13px]">
                      {row.emails_sent}
                      {row.followups_sent > 0 ? (
                        <span className="text-[11px] text-[var(--text-subtle)]">
                          {" "}
                          (+{row.followups_sent} FU)
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell className="tabular-nums text-[13px]">{row.replies}</TableCell>
                    <TableCell className="tabular-nums text-[13px]">{row.meetings}</TableCell>
                    <TableCell className="tabular-nums text-[13px]">
                      {pct(row.reply_rate)}
                    </TableCell>
                    <TableCell className="tabular-nums text-[13px]">
                      {formatCredits(row.credits_spent)}
                    </TableCell>
                    <TableCell className="text-[12px]">
                      <RelativeTime value={row.started_at} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      ) : null}
    </>
  );
}
