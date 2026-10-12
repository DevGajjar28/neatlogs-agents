"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { Mono } from "@/components/common/Mono";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  disconnectCalendar,
  getCalendarStatus,
  startCalendarOAuth,
} from "@/lib/api";
import { queryKeys } from "@/lib/keys";

export function CalendarConnectSection() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: queryKeys.calendarStatus,
    queryFn: getCalendarStatus,
  });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const cal = params.get("calendar");
    if (!cal) return;
    if (cal === "connected") {
      toast.success("Google Calendar connected (test account)");
      void qc.invalidateQueries({ queryKey: queryKeys.calendarStatus });
    } else if (cal === "error") {
      const reason = params.get("reason") || "unknown";
      const hint =
        reason === "state"
          ? "OAuth state mismatch — restart the API, confirm GOOGLE_CALENDAR_REDIRECT_URI matches Google Cloud Console, then Connect again."
          : reason === "token"
            ? "Google token exchange failed — check client id/secret and redirect URI."
            : reason === "secret_key"
              ? "SIGNALSDR_SECRET_KEY missing — required to store calendar tokens."
              : reason;
      toast.error(`Calendar connect failed: ${hint}`);
    }
    const url = new URL(window.location.href);
    url.searchParams.delete("calendar");
    url.searchParams.delete("reason");
    window.history.replaceState({}, "", url.pathname + url.search);
  }, [qc]);

  const connectMut = useMutation({
    mutationFn: startCalendarOAuth,
    onSuccess: (r) => {
      window.location.href = r.auth_url;
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Couldn't start Calendar OAuth"),
  });

  const disconnectMut = useMutation({
    mutationFn: disconnectCalendar,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.calendarStatus });
      toast.success("Calendar disconnected — tokens removed");
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Couldn't disconnect calendar"),
  });

  const st = q.data;

  return (
    <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-[14px] font-semibold leading-5">Google Calendar</h2>
          <p className="text-[12px] text-[var(--text-muted)]">
            Separate OAuth for a test Google account. Scope is{" "}
            <Mono className="text-[11px]">calendar.events</Mono> only — never the Gmail
            app password. Confirmed meeting slots are written here after you approve a
            reply.
          </p>
        </div>
        {st?.connected ? (
          <StatusBadge tone="success" label="Connected" />
        ) : (
          <StatusBadge tone="neutral" label="Not connected" />
        )}
      </div>

      {q.isError ? (
        <ErrorBanner
          message={
            q.error instanceof ApiError ? q.error.message : "Couldn't load calendar status"
          }
          actionLabel="Retry"
          onAction={() => q.refetch()}
        />
      ) : null}

      {!st?.configured ? (
        <p className="mb-3 text-[12px] text-[var(--status-warning)]">
          Add <Mono>GOOGLE_CALENDAR_CLIENT_ID</Mono> and{" "}
          <Mono>GOOGLE_CALENDAR_CLIENT_SECRET</Mono> to <Mono>.env</Mono>, then restart
          the API. Redirect URI must be{" "}
          <Mono className="text-[11px]">
            {st?.redirect_uri ||
              "http://127.0.0.1:8000/api/calendar/oauth/callback"}
          </Mono>
          .
        </p>
      ) : null}

      {st?.connected ? (
        <div className="mb-3 space-y-1 text-[13px]">
          <p>
            Calendar account: <Mono>{st.email}</Mono>
          </p>
          <p className="text-[12px] text-[var(--text-subtle)]">
            Use a dedicated test Google account. Disconnect anytime to wipe tokens.
          </p>
        </div>
      ) : (
        <p className="mb-3 text-[12px] text-[var(--text-muted)]">
          Connect with your test Google account in the browser consent screen.
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {st?.connected ? (
          <Button
            type="button"
            variant="outline"
            className="h-8"
            disabled={disconnectMut.isPending}
            onClick={() => {
              if (
                window.confirm(
                  "Disconnect Google Calendar? Stored OAuth tokens will be deleted.",
                )
              ) {
                disconnectMut.mutate();
              }
            }}
          >
            {disconnectMut.isPending ? "Disconnecting…" : "Disconnect calendar"}
          </Button>
        ) : (
          <Button
            type="button"
            className="h-8 bg-[var(--primary)] text-[var(--primary-fg)]"
            disabled={!st?.configured || connectMut.isPending}
            onClick={() => connectMut.mutate()}
          >
            {connectMut.isPending ? "Opening Google…" : "Connect test calendar"}
          </Button>
        )}
      </div>
    </div>
  );
}
