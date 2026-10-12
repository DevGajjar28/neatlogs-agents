"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { CardSkeleton } from "@/components/common/Skeletons";
import { PageTitle } from "@/components/shell/page-title";
import { useShell } from "@/components/shell/shell-context";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  ApiError,
  approveCampaign,
  getPendingApprovals,
  listCampaigns,
  type PendingApprovalItem,
} from "@/lib/api";
import { queryKeys } from "@/lib/keys";

/** Campaigns that may still have drafts waiting even if status briefly lags. */
const APPROVAL_STATUSES = new Set([
  "waiting_approval",
  "running",
  "waiting_icp",
  "paused",
]);

type CampaignQueue = {
  campaignId: string;
  sellerName: string;
  items: PendingApprovalItem[];
};

export default function ApprovalsPage() {
  const { setNewCampaignOpen } = useShell();
  const qc = useQueryClient();

  const campaignsQ = useQuery({
    queryKey: queryKeys.campaigns,
    queryFn: listCampaigns,
    refetchInterval: 5_000,
  });

  const candidates = useMemo(
    () => (campaignsQ.data || []).filter((c) => APPROVAL_STATUSES.has(c.status)),
    [campaignsQ.data],
  );

  const pendingQueries = useQueries({
    queries: candidates.map((c) => ({
      queryKey: queryKeys.pendingApprovals(c.id),
      queryFn: () => getPendingApprovals(c.id),
      refetchInterval: 5_000,
    })),
  });

  const queues: CampaignQueue[] = useMemo(() => {
    const out: CampaignQueue[] = [];
    pendingQueries.forEach((q, i) => {
      const campaign = candidates[i];
      if (!campaign || !q.data?.waiting || !q.data.items?.length) return;
      out.push({
        campaignId: campaign.id,
        sellerName: campaign.seller_name,
        items: q.data.items,
      });
    });
    return out;
  }, [pendingQueries, candidates]);

  const loading =
    campaignsQ.isLoading || pendingQueries.some((q) => q.isLoading && !q.data);

  const totalDrafts = queues.reduce((n, q) => n + q.items.length, 0);

  return (
    <>
      <PageTitle title="Approvals" />
      {loading ? <CardSkeleton /> : null}
      {campaignsQ.isError ? (
        <ErrorBanner
          message={
            campaignsQ.error instanceof ApiError
              ? campaignsQ.error.message
              : "Couldn't load approvals"
          }
          actionLabel="Retry"
          onAction={() => campaignsQ.refetch()}
        />
      ) : null}
      {!loading && queues.length === 0 ? (
        <EmptyState
          title="Nothing waiting for you"
          description="When a campaign has verified drafts ready, you'll approve once for that campaign — then every lead gets sent and reply handling stays on autopilot."
          actionLabel="New campaign"
          onAction={() => setNewCampaignOpen(true)}
        />
      ) : null}
      {queues.length > 0 ? (
        <div className="space-y-3">
          <p className="text-[13px] text-[var(--text-muted)]">
            {queues.length} campaign{queues.length === 1 ? "" : "s"} · {totalDrafts}{" "}
            email{totalDrafts === 1 ? "" : "s"} ready. One approve sends every draft for
            that campaign.
          </p>
          <div className="overflow-hidden rounded-[8px] border border-[var(--border)] bg-[var(--surface)]">
            {queues.map((queue, i) => (
              <CampaignApprovalRow
                key={queue.campaignId}
                queue={queue}
                borderTop={i > 0}
                onDone={() => {
                  void qc.invalidateQueries({ queryKey: queryKeys.campaigns });
                  void qc.invalidateQueries({
                    queryKey: queryKeys.pendingApprovals(queue.campaignId),
                  });
                  void qc.invalidateQueries({ queryKey: queryKeys.approvalsInbox });
                }}
              />
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}

function CampaignApprovalRow({
  queue,
  borderTop,
  onDone,
}: {
  queue: CampaignQueue;
  borderTop: boolean;
  onDone: () => void;
}) {
  const [includeGuessed, setIncludeGuessed] = useState(false);
  const [showList, setShowList] = useState(false);

  const guessedCount = queue.items.filter((i) => i.guessed).length;
  const refsBlocked = queue.items.filter((i) => i.has_internal_refs).length;
  const previewNames = queue.items
    .slice(0, 4)
    .map((i) => i.name || i.email_masked || "Lead")
    .join(", ");
  const more =
    queue.items.length > 4 ? ` +${queue.items.length - 4} more` : "";

  const mut = useMutation({
    mutationFn: (action: "approve" | "reject") =>
      approveCampaign(queue.campaignId, {
        action,
        include_guessed: includeGuessed,
      }),
    onSuccess: (data, action) => {
      if (action === "approve") {
        const skipped = data.skipped_guessed || 0;
        toast.success(
          skipped
            ? `Approved — sending ${data.drafts - skipped} of ${data.drafts} (skipped guessed)`
            : `Approved — sending ${data.drafts} email${data.drafts === 1 ? "" : "s"}`,
        );
      } else {
        toast.success("Campaign drafts rejected");
      }
      onDone();
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Decision failed");
    },
  });

  return (
    <div className={borderTop ? "border-t border-[var(--border)]" : undefined}>
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <Link
          href={`/campaigns/${queue.campaignId}`}
          className="min-w-[7rem] shrink-0 text-[13px] font-semibold text-[var(--accent)] hover:underline"
          title="Open campaign"
        >
          {queue.sellerName || "Campaign"}
        </Link>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium text-[var(--text)]">
            {queue.items.length} email{queue.items.length === 1 ? "" : "s"} ready to send
          </p>
          <p className="truncate text-[12px] text-[var(--text-muted)]">
            {previewNames}
            {more}
            {guessedCount ? (
              <span className="text-[var(--text-subtle)]">
                {" "}
                · {guessedCount} guessed
              </span>
            ) : null}
            {refsBlocked ? (
              <span className="text-[var(--status-danger)]">
                {" "}
                · {refsBlocked} blocked (fix refs)
              </span>
            ) : null}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            className="h-8"
            onClick={() => setShowList((v) => !v)}
          >
            {showList ? "Hide leads" : "Leads"}
          </Button>
          <Button
            type="button"
            className="h-8"
            disabled={mut.isPending || refsBlocked > 0}
            onClick={() => mut.mutate("approve")}
          >
            Approve & send all
          </Button>
          <Button
            type="button"
            variant="outline"
            className="h-8"
            disabled={mut.isPending}
            onClick={() => mut.mutate("reject")}
          >
            Reject all
          </Button>
        </div>
      </div>
      {guessedCount > 0 ? (
        <label className="flex items-center gap-2 border-t border-[var(--border)] px-4 py-2 text-[12px] text-[var(--text-muted)]">
          <Checkbox
            checked={includeGuessed}
            onCheckedChange={(v) => setIncludeGuessed(Boolean(v))}
          />
          Also send {guessedCount} guessed address
          {guessedCount === 1 ? "" : "es"}
        </label>
      ) : null}
      {showList ? (
        <ul className="space-y-1 border-t border-[var(--border)] bg-[var(--surface-muted)]/40 px-4 py-3 text-[12px]">
          {queue.items.map((item) => (
            <li
              key={item.contact_id}
              className="flex flex-wrap items-baseline gap-x-2 text-[var(--text-muted)]"
            >
              <span className="font-medium text-[var(--text)]">
                {item.name || "Contact"}
              </span>
              {item.company_name ? <span>· {item.company_name}</span> : null}
              <span className="font-mono text-[11px]">
                {item.email_masked || "—"}
              </span>
              {item.subject ? (
                <span className="text-[var(--text-subtle)]">— {item.subject}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
