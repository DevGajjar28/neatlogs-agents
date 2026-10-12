"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { Mono } from "@/components/common/Mono";
import { CardSkeleton } from "@/components/common/Skeletons";
import { PageTitle } from "@/components/shell/page-title";
import { useShell } from "@/components/shell/shell-context";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  decideEmail,
  getPendingApprovals,
  listCampaigns,
  sendApproved,
  type PendingApprovalItem,
} from "@/lib/api";
import { queryKeys } from "@/lib/keys";

const EV_RE = /\bev_[0-9a-f]{6,}\b/i;

/** Campaigns that may still have drafts waiting even if status briefly lags. */
const APPROVAL_STATUSES = new Set([
  "waiting_approval",
  "running",
  "waiting_icp",
  "paused",
]);

type DraftCard = PendingApprovalItem & {
  campaignId: string;
  sellerName: string;
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

  const cards: DraftCard[] = useMemo(() => {
    const out: DraftCard[] = [];
    pendingQueries.forEach((q, i) => {
      const campaign = candidates[i];
      if (!campaign || !q.data?.waiting) return;
      for (const item of q.data.items) {
        out.push({
          ...item,
          campaignId: campaign.id,
          sellerName: campaign.seller_name,
        });
      }
    });
    return out;
  }, [pendingQueries, candidates]);

  const loading =
    campaignsQ.isLoading || pendingQueries.some((q) => q.isLoading && !q.data);

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
      {!loading && cards.length === 0 ? (
        <EmptyState
          title="Nothing waiting for you"
          description="When verified drafts need a human OK, they'll show up here — one row per email, with the campaign name."
          actionLabel="New campaign"
          onAction={() => setNewCampaignOpen(true)}
        />
      ) : null}
      {cards.length > 0 ? (
        <div className="space-y-3">
          <p className="text-[13px] text-[var(--text-muted)]">
            {cards.length} email{cards.length === 1 ? "" : "s"} waiting — campaign · contact ·
            draft. Open the campaign name for the full pipeline.
          </p>
          <div className="overflow-hidden rounded-[8px] border border-[var(--border)] bg-[var(--surface)]">
            {cards.map((card, i) => (
              <ApprovalRow
                key={`${card.campaignId}:${card.contact_id}`}
                card={card}
                borderTop={i > 0}
                onDone={() => {
                  void qc.invalidateQueries({ queryKey: queryKeys.campaigns });
                  void qc.invalidateQueries({
                    queryKey: queryKeys.pendingApprovals(card.campaignId),
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

function ApprovalRow({
  card,
  borderTop,
  onDone,
}: {
  card: DraftCard;
  borderTop: boolean;
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [subject, setSubject] = useState(card.subject || "");
  const [body, setBody] = useState(card.body || "");
  const [confirmGuessed, setConfirmGuessed] = useState(false);

  useEffect(() => {
    setSubject(card.subject || "");
    setBody(card.body || "");
  }, [card.subject, card.body]);

  const hasRefs =
    Boolean(card.has_internal_refs) || EV_RE.test(`${subject}\n${body}`);
  const preview = (card.body || "").replace(/\s+/g, " ").trim().slice(0, 100);

  const mut = useMutation({
    mutationFn: async (action: "approve" | "reject") => {
      if (action === "approve" && hasRefs) {
        throw new ApiError(
          "This draft still has internal reference ids. Edit or regenerate it.",
          422,
          null,
        );
      }
      await decideEmail(card.campaignId, card.contact_id, {
        action,
        subject: action === "approve" ? subject : undefined,
        body: action === "approve" ? body : undefined,
        confirm_guessed: confirmGuessed,
      });
      await sendApproved(card.campaignId);
    },
    onSuccess: (_data, action) => {
      toast.success(action === "approve" ? "Approved — sending" : "Rejected");
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
          href={`/campaigns/${card.campaignId}`}
          className="min-w-[7rem] shrink-0 text-[13px] font-semibold text-[var(--accent)] hover:underline"
          title="Open campaign"
        >
          {card.sellerName || "Campaign"}
        </Link>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-[var(--text)]">
            {card.name || "Contact"}
            {card.company_name ? (
              <span className="font-normal text-[var(--text-muted)]">
                {" "}
                · {card.company_name}
              </span>
            ) : null}
          </p>
          <p className="truncate text-[12px] text-[var(--text-muted)]">
            <Mono className="text-[11px]">{card.email_masked || "—"}</Mono>
            {card.subject ? (
              <span className="text-[var(--text-subtle)]"> · {card.subject}</span>
            ) : null}
            {preview ? (
              <span className="text-[var(--text-subtle)]"> — {preview}</span>
            ) : null}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            className="h-8"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Hide email" : "Review email"}
          </Button>
          <Button
            type="button"
            className="h-8"
            disabled={mut.isPending || hasRefs || (card.guessed && !confirmGuessed && open)}
            onClick={() => {
              if (card.guessed && !confirmGuessed) {
                setOpen(true);
                toast.message("Confirm the guessed address before approving");
                return;
              }
              mut.mutate("approve");
            }}
          >
            Accept & send
          </Button>
          <Button
            type="button"
            variant="outline"
            className="h-8"
            disabled={mut.isPending}
            onClick={() => mut.mutate("reject")}
          >
            Reject
          </Button>
        </div>
      </div>
      {open ? (
        <div className="space-y-2 border-t border-[var(--border)] bg-[var(--surface-muted)]/40 px-4 py-3">
          <Input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject"
            className="bg-[var(--surface)] text-[13px]"
          />
          <Textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={8}
            className="bg-[var(--surface)] text-[13px]"
          />
          {hasRefs ? (
            <p className="text-[12px] font-medium text-[var(--status-danger)]">
              This draft still has internal reference ids. Edit them out before send.
            </p>
          ) : null}
          {card.guessed ? (
            <label className="flex items-center gap-2 text-[12px] text-[var(--text-muted)]">
              <Checkbox
                checked={confirmGuessed}
                onCheckedChange={(v) => setConfirmGuessed(Boolean(v))}
              />
              I checked this guessed address
            </label>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
