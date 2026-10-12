"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { Mono } from "@/components/common/Mono";
import { CardSkeleton } from "@/components/common/Skeletons";
import { CalendarConnectSection } from "@/components/mail/CalendarConnectSection";
import { MailAccountsSection } from "@/components/mail/MailAccountsSection";
import { PoliciesCard } from "@/components/mail/PoliciesCard";
import { PageTitle } from "@/components/shell/page-title";
import { Checkbox } from "@/components/ui/checkbox";
import {
  ApiError,
  extractCredits,
  getMailPolicies,
  getSystemStatus,
  putSendingPaused,
} from "@/lib/api";
import { formatCredits, shortModelName } from "@/lib/format";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

export default function SettingsPage() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: getSystemStatus,
    refetchInterval: 30_000,
  });
  const policiesQ = useQuery({
    queryKey: queryKeys.mailPolicies,
    queryFn: getMailPolicies,
  });

  const pauseMut = useMutation({
    mutationFn: (paused: boolean) => putSendingPaused(paused),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: queryKeys.systemStatus });
      void qc.invalidateQueries({ queryKey: queryKeys.mailPolicies });
      toast.success(r.sending_paused ? "All sending paused" : "Sending resumed");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't update sending"),
  });

  const liveAllowed =
    Boolean(q.data && !q.data.demo_mode) &&
    Boolean(policiesQ.data?.allow_live_sends);
  const paused = Boolean(
    policiesQ.data?.sending_paused ?? q.data?.sending_paused,
  );

  return (
    <>
      <PageTitle title="Settings" />
      <div className="space-y-4">
        {q.isLoading ? <CardSkeleton /> : null}
        {q.isError ? (
          <ErrorBanner
            message={
              q.error instanceof ApiError
                ? q.error.message
                : "Can't reach SignalSDR right now. Start the backend, then try again."
            }
            actionLabel="Retry"
            onAction={() => q.refetch()}
          />
        ) : null}

        <MailAccountsSection liveAllowed={liveAllowed} />

        <CalendarConnectSection />

        <div
          className={cn(
            "rounded-[8px] border bg-[var(--surface)] p-4",
            paused
              ? "border-[var(--status-danger)]"
              : "border-[var(--border)]",
          )}
        >
          <h2 className="mb-1 text-[14px] font-semibold leading-5">Sending</h2>
          <p className="mb-3 text-[12px] text-[var(--text-muted)]">
            Global kill switch. When on, no sandbox or Gmail transport can deliver.
          </p>
          <label className="flex items-center gap-2 text-[13px]">
            <Checkbox
              checked={paused}
              disabled={pauseMut.isPending}
              onCheckedChange={(c) => pauseMut.mutate(Boolean(c))}
            />
            <span className={paused ? "font-medium text-[var(--status-danger)]" : undefined}>
              Pause all sending
            </span>
          </label>
          <p className="mt-2 text-[12px] text-[var(--text-subtle)]">
            Max mode:{" "}
            <Mono>{policiesQ.data?.max_send_mode || q.data?.max_send_mode || "sandbox"}</Mono>
            {" · "}
            See Policies below for caps and always-on safety rules.
          </p>
        </div>

        <PoliciesCard />

        {q.data ? (
          <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
            <h2 className="mb-3 text-[14px] font-semibold leading-5">System</h2>
            <dl className="grid grid-cols-1 gap-3 text-[13px] sm:grid-cols-2">
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Data mode</dt>
                <dd className="font-medium">{q.data.data_mode}</dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Demo mode</dt>
                <dd className="font-medium">{q.data.demo_mode ? "on" : "off"}</dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Crustdata credits</dt>
                <dd>
                  <Mono>{formatCredits(extractCredits(q.data))}</Mono>
                </dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Credit cap</dt>
                <dd>
                  <Mono>{formatCredits(q.data.max_credits)}</Mono>
                </dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">LLM</dt>
                <dd>
                  <Mono>
                    {shortModelName(q.data.llm.fast || q.data.llm.strong)} (
                    {q.data.llm.provider || "—"})
                  </Mono>
                </dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">neatlogs</dt>
                <dd className="font-medium">
                  {q.data.neatlogs.configured ? "Tracing on" : "Tracing off"}
                </dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Mail accounts</dt>
                <dd className="font-medium">
                  {q.data.mail_account_count ?? 0}
                  {q.data.mail_account_error ? " · error" : ""}
                </dd>
              </div>
            </dl>
          </div>
        ) : null}
      </div>
    </>
  );
}
