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
import { WhyWeSaidThis } from "@/components/mail/WhyWeSaidThis";
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

  const waiting = useMemo(
    () => (campaignsQ.data || []).filter((c) => c.status === "waiting_approval"),
    [campaignsQ.data],
  );

  const pendingQueries = useQueries({
    queries: waiting.map((c) => ({
      queryKey: queryKeys.pendingApprovals(c.id),
      queryFn: () => getPendingApprovals(c.id),
      refetchInterval: 5_000,
    })),
  });

  const cards: DraftCard[] = useMemo(() => {
    const out: DraftCard[] = [];
    pendingQueries.forEach((q, i) => {
      const campaign = waiting[i];
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
  }, [pendingQueries, waiting]);

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
          description="When verified drafts need a human OK, they'll show up here."
          actionLabel="New campaign"
          onAction={() => setNewCampaignOpen(true)}
        />
      ) : null}
      {cards.length > 0 ? (
        <div className="space-y-4">
          <p className="text-[13px] text-[var(--text-muted)]">
            {cards.length} draft{cards.length === 1 ? "" : "s"} waiting — accept or reject, then
            send continues via the campaign&apos;s Gmail account.
          </p>
          {cards.map((card) => (
            <ApprovalCard
              key={`${card.campaignId}:${card.contact_id}`}
              card={card}
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
      ) : null}
    </>
  );
}

function ApprovalCard({ card, onDone }: { card: DraftCard; onDone: () => void }) {
  const [subject, setSubject] = useState(card.subject || "");
  const [body, setBody] = useState(card.body || "");
  const [confirmGuessed, setConfirmGuessed] = useState(false);

  useEffect(() => {
    setSubject(card.subject || "");
    setBody(card.body || "");
  }, [card.subject, card.body]);

  const hasRefs =
    Boolean(card.has_internal_refs) || EV_RE.test(`${subject}\n${body}`);

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
    <article className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-[14px] font-semibold text-[var(--text)]">
            {card.name || "Contact"}
            {card.title ? (
              <span className="font-normal text-[var(--text-muted)]"> · {card.title}</span>
            ) : null}
          </h3>
          <p className="text-[12px] text-[var(--text-muted)]">
            {card.company_name || "Company"} ·{" "}
            <Link
              href={`/campaigns/${card.campaignId}`}
              className="text-[var(--accent)] underline-offset-2 hover:underline"
            >
              {card.sellerName}
            </Link>
          </p>
          <Mono className="text-[12px] text-[var(--text-subtle)]">
            {card.email_masked || "—"}
            {card.guessed ? " · guessed" : ""}
          </Mono>
        </div>
      </div>
      <div className="mb-3 space-y-2">
        <Input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="Subject"
          className="text-[13px]"
        />
        <Textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={6}
          className="text-[13px]"
        />
      </div>
      <div className="mb-3">
        <WhyWeSaidThis body={body} claims={card.claims || []} />
      </div>
      {(card.style_warnings || []).length > 0 ? (
        <ul className="mb-3 list-inside list-disc text-[12px] text-[var(--status-warning)]">
          {(card.style_warnings || []).map((w) => (
            <li key={w}>Style warning: {w}</li>
          ))}
        </ul>
      ) : null}
      {hasRefs ? (
        <p className="mb-3 text-[12px] font-medium text-[var(--status-danger)]">
          This draft still has internal reference ids. Edit or regenerate it.
        </p>
      ) : null}
      {card.guessed ? (
        <label className="mb-3 flex items-center gap-2 text-[12px] text-[var(--text-muted)]">
          <Checkbox
            checked={confirmGuessed}
            onCheckedChange={(v) => setConfirmGuessed(Boolean(v))}
          />
          I checked this guessed address
        </label>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          disabled={mut.isPending || hasRefs || (card.guessed && !confirmGuessed)}
          onClick={() => mut.mutate("approve")}
        >
          Accept & send
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={mut.isPending}
          onClick={() => mut.mutate("reject")}
        >
          Reject
        </Button>
      </div>
    </article>
  );
}
