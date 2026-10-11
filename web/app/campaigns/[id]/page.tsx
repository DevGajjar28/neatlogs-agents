"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { Mono } from "@/components/common/Mono";
import { StatusBadge } from "@/components/common/StatusBadge";
import { CardSkeleton } from "@/components/common/Skeletons";
import { PageTitle } from "@/components/shell/page-title";
import { ApiError, getCampaign } from "@/lib/api";
import { formatCredits } from "@/lib/format";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

export default function CampaignRunPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const q = useQuery({
    queryKey: queryKeys.campaign(id),
    queryFn: () => getCampaign(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && ["completed", "halted", "failed"].includes(status) && !query.state.data?.is_alive) {
        return false;
      }
      return 3_000;
    },
  });

  const title = q.data?.seller_name || id;

  return (
    <>
      <PageTitle title={title} parent={{ label: "Campaigns", href: "/campaigns" }} />
      {q.isLoading ? <CardSkeleton /> : null}
      {q.isError ? (
        <ErrorBanner
          message={
            q.error instanceof ApiError
              ? q.error.message
              : "Couldn't load this campaign."
          }
          actionLabel="Retry"
          onAction={() => q.refetch()}
        />
      ) : null}
      {q.data ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-[16px] font-semibold">{q.data.seller_name}</h2>
              <Mono className="text-[12px] text-[var(--text-muted)]">{q.data.seller_domain}</Mono>
            </div>
            <StatusBadge status={q.data.status} />
            {q.data.is_alive ? (
              <span className="inline-flex items-center gap-1.5 text-[12px] text-[var(--status-info)]">
                <span className="size-1.5 animate-pulse rounded-full bg-[var(--status-info)]" />
                Running
              </span>
            ) : null}
          </div>

          <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
            <h3 className="mb-3 text-[14px] font-semibold">Stages</h3>
            <ol className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-5">
              {(q.data.stages || []).map((stage) => (
                <li
                  key={stage.stage}
                  className={cn(
                    "rounded-[6px] border border-[var(--border)] px-2 py-2",
                    stage.status === "running" && "border-[var(--accent)] bg-[var(--accent-soft)]",
                    stage.status === "waiting" && "border-[var(--status-warning)] bg-[var(--status-warning-soft)]",
                    stage.status === "failed" && "border-[var(--status-danger)] bg-[var(--status-danger-soft)]",
                  )}
                >
                  <div className="text-[12px] font-medium capitalize">{stage.stage}</div>
                  <div className="text-[11px] text-[var(--text-subtle)] capitalize">
                    {stage.status}
                    {stage.count_label ? ` · ${stage.count_label}` : ""}
                  </div>
                </li>
              ))}
            </ol>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <Stat
              label="Leads"
              value={`${q.data.leads_found} / ${q.data.leads_target}`}
            />
            <Stat
              label="Credits"
              value={`${formatCredits(q.data.credits_spent)} / ${formatCredits(q.data.credit_cap)}`}
            />
            <Stat label="Mode" value={q.data.mode} />
          </div>

          <p className="text-[12px] text-[var(--text-subtle)]">
            ICP approval and the full run timeline ship next. If status is waiting for you, use Approvals
            or the Phase 7 UI until those screens are ready.
          </p>
        </div>
      ) : null}
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="text-[12px] text-[var(--text-subtle)]">{label}</div>
      <Mono className="mt-1 text-[18px] font-semibold">{value}</Mono>
    </div>
  );
}
