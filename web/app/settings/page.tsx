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
import { formatCredits, friendlyModelName } from "@/lib/format";
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
                : "Can't reach ReachPilot right now. Start the backend, then try again."
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
            <h2 className="mb-1 text-[14px] font-semibold leading-5">Workspace status</h2>
            <p className="mb-4 text-[12px] text-[var(--text-muted)]">
              Plain-language view of data sources, sending, and the writing model — same summary
              as the sidebar.
            </p>
            <dl className="grid grid-cols-1 gap-4 text-[13px] sm:grid-cols-2">
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Company research</dt>
                <dd className="font-medium">
                  {formatCredits(extractCredits(q.data))} credits left
                  <span className="mt-0.5 block text-[12px] font-normal text-[var(--text-muted)]">
                    Crustdata budget for finding companies and people (cap{" "}
                    {formatCredits(q.data.max_credits)}).
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Backup email finder</dt>
                <dd className="font-medium">
                  {q.data.hunter?.configured ? "Hunter.io connected" : "Hunter.io not set up"}
                  <span className="mt-0.5 block text-[12px] font-normal text-[var(--text-muted)]">
                    {q.data.hunter?.configured
                      ? "Used when primary data is thin or out of credits."
                      : "Optional — add HUNTER_API_KEY to keep finding emails."}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Writing assistant</dt>
                <dd className="font-medium">
                  {friendlyModelName(q.data.llm.fast || q.data.llm.strong)}
                  <span className="mt-0.5 block text-[12px] font-normal text-[var(--text-muted)]">
                    Used for research summaries and email drafts
                    {q.data.llm.provider ? ` · ${q.data.llm.provider}` : ""}.
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Research mode</dt>
                <dd className="font-medium">
                  {q.data.data_mode === "live" ? "Live research" : "Saved / replay data"}
                  <span className="mt-0.5 block text-[12px] font-normal text-[var(--text-muted)]">
                    {q.data.data_mode === "live"
                      ? "Pulls fresh company and people data."
                      : "Uses cached results without new data spend."}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Demo safety</dt>
                <dd className="font-medium">
                  {q.data.demo_mode ? "On" : "Off"}
                  <span className="mt-0.5 block text-[12px] font-normal text-[var(--text-muted)]">
                    When on, live prospect sends stay locked.
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Activity log</dt>
                <dd className="font-medium">
                  {q.data.neatlogs.configured ? "Recording" : "Off"}
                  <span className="mt-0.5 block text-[12px] font-normal text-[var(--text-muted)]">
                    neatlogs traces of what agents did on each run.
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-[12px] text-[var(--text-subtle)]">Mail accounts</dt>
                <dd className="font-medium">
                  {q.data.mail_account_count ?? 0} connected
                  {q.data.mail_account_error ? " · needs attention" : ""}
                </dd>
              </div>
            </dl>
          </div>
        ) : null}
      </div>
    </>
  );
}
