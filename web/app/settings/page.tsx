"use client";

import { useQuery } from "@tanstack/react-query";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { Mono } from "@/components/common/Mono";
import { PageTitle } from "@/components/shell/page-title";
import { ApiError, extractCredits, getSystemStatus } from "@/lib/api";
import { formatCredits, shortModelName } from "@/lib/format";
import { queryKeys } from "@/lib/keys";
import { CardSkeleton } from "@/components/common/Skeletons";

export default function SettingsPage() {
  const q = useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: getSystemStatus,
    refetchInterval: 30_000,
  });

  return (
    <>
      <PageTitle title="Settings" />
      <div className="space-y-4">
        <EmptyState
          title="Settings screens land in U6"
          description="System status below is live from GET /api/system/status. Defaults, sending, and purge come later."
        />
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
            </dl>
          </div>
        ) : null}
      </div>
    </>
  );
}
