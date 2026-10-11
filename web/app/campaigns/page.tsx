"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { Mono } from "@/components/common/Mono";
import { RelativeTime } from "@/components/common/RelativeTime";
import { StatusBadge } from "@/components/common/StatusBadge";
import { TableSkeleton } from "@/components/common/Skeletons";
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
import { ApiError, listCampaigns } from "@/lib/api";
import { formatCredits } from "@/lib/format";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

export default function CampaignsPage() {
  const { setNewCampaignOpen } = useShell();
  const q = useQuery({
    queryKey: queryKeys.campaigns,
    queryFn: listCampaigns,
    refetchInterval: 5_000,
  });

  return (
    <>
      <PageTitle title="Campaigns" />
      {q.isLoading ? <TableSkeleton cols={6} rows={8} /> : null}
      {q.isError ? (
        <ErrorBanner
          message={
            q.error instanceof ApiError
              ? q.error.message
              : "Couldn't load campaigns. Try again in a moment."
          }
          actionLabel="Retry"
          onAction={() => q.refetch()}
        />
      ) : null}
      {q.data && q.data.length === 0 ? (
        <EmptyState
          title="No campaigns yet"
          description="Paste your company's website. SignalSDR finds who buys from you, researches them, and drafts emails it can prove."
          actionLabel="New campaign"
          onAction={() => setNewCampaignOpen(true)}
        />
      ) : null}
      {q.data && q.data.length > 0 ? (
        <div className="overflow-hidden rounded-[8px] border border-[var(--border)] bg-[var(--surface)]">
          <Table>
            <TableHeader>
              <TableRow className="h-9 hover:bg-transparent">
                <TableHead className="bg-[var(--surface-muted)] text-[12px]">Seller</TableHead>
                <TableHead className="bg-[var(--surface-muted)] text-[12px]">Status</TableHead>
                <TableHead className="bg-[var(--surface-muted)] text-[12px]">Leads</TableHead>
                <TableHead className="bg-[var(--surface-muted)] text-right text-[12px]">
                  Credits
                </TableHead>
                <TableHead className="bg-[var(--surface-muted)] text-[12px]">Mode</TableHead>
                <TableHead className="bg-[var(--surface-muted)] text-[12px]">Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data.map((c) => {
                const hot = c.credit_cap > 0 && c.credits_spent / c.credit_cap > 0.9;
                return (
                  <TableRow key={c.id} className="h-10">
                    <TableCell>
                      <Link
                        href={`/campaigns/${c.id}`}
                        className="block min-w-0 hover:text-[var(--accent)]"
                      >
                        <div className="truncate text-[13px] font-medium">{c.seller_name || c.id}</div>
                        <Mono className="text-[11px] text-[var(--text-subtle)]">
                          {c.seller_domain || c.id}
                        </Mono>
                      </Link>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={c.status} />
                    </TableCell>
                    <TableCell>
                      <Mono>
                        {c.leads_found} / {c.leads_target}
                      </Mono>
                    </TableCell>
                    <TableCell className="text-right">
                      <Mono className={cn(hot && "text-[var(--status-danger)]")}>
                        {formatCredits(c.credits_spent)} / {formatCredits(c.credit_cap)}
                      </Mono>
                    </TableCell>
                    <TableCell>
                      <span className="rounded-[6px] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[11px] font-medium capitalize">
                        {c.mode}
                      </span>
                    </TableCell>
                    <TableCell>
                      <RelativeTime value={c.started_at} />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      ) : null}
    </>
  );
}
