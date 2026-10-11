"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { RelativeTime } from "@/components/common/RelativeTime";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  ApiError,
  getMailPolicies,
  getPolicyRuleEvents,
  patchMailPolicies,
} from "@/lib/api";
import { queryKeys } from "@/lib/keys";
import { Mono } from "@/components/common/Mono";

export function PoliciesCard() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: queryKeys.mailPolicies,
    queryFn: getMailPolicies,
  });
  const [editKey, setEditKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [eventsRule, setEventsRule] = useState<string | null>(null);

  const eventsQ = useQuery({
    queryKey: queryKeys.policyEvents(eventsRule || ""),
    queryFn: () => getPolicyRuleEvents(eventsRule!),
    enabled: Boolean(eventsRule),
  });

  const patchMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => patchMailPolicies(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.mailPolicies });
      setEditKey(null);
      toast.success("Policy updated");
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Couldn't update policy");
    },
  });

  if (q.isLoading) {
    return (
      <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4 text-[13px] text-[var(--text-muted)]">
        Loading policies…
      </div>
    );
  }
  if (!q.data) return null;

  const values = q.data.values;

  return (
    <>
      <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
        <h2 className="mb-1 text-[14px] font-semibold leading-5">Policies</h2>
        <p className="mb-4 text-[12px] text-[var(--text-muted)]">
          Guardrails from the mail policy. Safety rules stay always on; volume limits can be lowered.
        </p>
        <ul className="divide-y divide-[var(--border)]">
          {q.data.rules.map((rule) => (
            <li key={rule.id} className="flex flex-wrap items-start gap-3 py-3">
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium">{rule.name}</div>
                <div className="text-[12px] text-[var(--text-muted)]">{rule.protects}</div>
                <div className="mt-1 text-[12px] text-[var(--text-subtle)]">
                  {rule.always_on ? (
                    <span className="font-medium text-[var(--status-success)]">Always on</span>
                  ) : rule.id === "sending_paused" ? (
                    <span>{q.data.sending_paused ? "Paused" : "Active (not paused)"}</span>
                  ) : rule.editable ? (
                    <span>
                      Current:{" "}
                      <Mono>
                        {rule.id === "sending_window"
                          ? JSON.stringify(values.sending_window)
                          : rule.id === "test_recipient_missing"
                            ? (values.default_test_recipients || []).join(", ") || "—"
                            : String(rule.value ?? "—")}
                      </Mono>
                    </span>
                  ) : (
                    <span>Always on</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="rounded-[6px] bg-[var(--surface-muted)] px-2 py-1 text-[12px] font-mono hover:bg-[var(--border)]"
                  onClick={() => setEventsRule(rule.id)}
                  disabled={!rule.event}
                  title="Blocks in last 24h"
                >
                  {rule.blocks_24h} blocks
                </button>
                {rule.editable && rule.id !== "sending_paused" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    className="h-7 px-2 text-[12px]"
                    onClick={() => {
                      setEditKey(rule.id);
                      if (rule.id === "daily_cap") setEditValue(String(values.daily_cap));
                      else if (rule.id === "per_domain_cap")
                        setEditValue(String(values.per_domain_daily_cap));
                      else if (rule.id === "min_gap_seconds")
                        setEditValue(String(values.min_gap_seconds));
                      else if (rule.id === "test_recipient_missing")
                        setEditValue((values.default_test_recipients || []).join(", "));
                      else if (rule.id === "sending_window")
                        setEditValue(JSON.stringify(values.sending_window));
                    }}
                  >
                    Edit
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </div>

      <Sheet open={Boolean(editKey)} onOpenChange={(o) => !o && setEditKey(null)}>
        <SheetContent
          side="right"
          className="w-full gap-0 border-l sm:max-w-[480px]"
          style={{ borderRadius: 0 }}
        >
          <SheetHeader className="border-b px-4 py-4">
            <SheetTitle className="text-[14px]">Edit policy</SheetTitle>
            <SheetDescription className="text-[13px] text-[var(--text-muted)]">
              Values are clamped to hard maximums.
            </SheetDescription>
          </SheetHeader>
          <div className="space-y-3 px-4 py-4">
            <Input
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              className="h-8 rounded-[6px] font-mono"
            />
            <Button
              type="button"
              className="bg-[var(--primary)] text-[var(--primary-fg)]"
              disabled={patchMut.isPending}
              onClick={() => {
                if (editKey === "daily_cap")
                  patchMut.mutate({ daily_cap: Number(editValue) || 1 });
                else if (editKey === "per_domain_cap")
                  patchMut.mutate({ per_domain_daily_cap: Number(editValue) || 1 });
                else if (editKey === "min_gap_seconds")
                  patchMut.mutate({ min_gap_seconds: Number(editValue) || 30 });
                else if (editKey === "test_recipient_missing")
                  patchMut.mutate({
                    default_test_recipients: editValue
                      .split(/[,;\s]+/)
                      .map((s) => s.trim())
                      .filter(Boolean),
                  });
                else if (editKey === "sending_window") {
                  try {
                    patchMut.mutate({ sending_window: JSON.parse(editValue) });
                  } catch {
                    toast.error("Invalid JSON for sending window");
                  }
                }
              }}
            >
              Save
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      <Sheet open={Boolean(eventsRule)} onOpenChange={(o) => !o && setEventsRule(null)}>
        <SheetContent
          side="right"
          className="w-full gap-0 border-l sm:max-w-[480px]"
          style={{ borderRadius: 0 }}
        >
          <SheetHeader className="border-b px-4 py-4">
            <SheetTitle className="text-[14px]">Policy blocks (24h)</SheetTitle>
            <SheetDescription className="text-[13px] text-[var(--text-muted)]">
              Recent events for this rule.
            </SheetDescription>
          </SheetHeader>
          <div className="space-y-2 overflow-y-auto px-4 py-4">
            {eventsQ.isLoading ? (
              <p className="text-[13px] text-[var(--text-muted)]">Loading…</p>
            ) : (eventsQ.data || []).length === 0 ? (
              <p className="text-[13px] text-[var(--text-muted)]">No blocks in the last 24 hours.</p>
            ) : (
              (eventsQ.data || []).map((ev) => (
                <div key={ev.id} className="rounded-[6px] border border-[var(--border)] p-2">
                  <div className="flex items-center justify-between gap-2">
                    <Mono className="text-[11px]">{ev.type}</Mono>
                    <RelativeTime value={ev.ts} />
                  </div>
                  <p className="mt-1 text-[12px] text-[var(--text)]">{ev.message}</p>
                </div>
              ))
            )}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
