"use client";

import { RelativeTime } from "@/components/common/RelativeTime";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { CampaignEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

const AGENT_FILTER: Record<string, string[]> = {
  planner: ["planner"],
  product_researcher: ["product_researcher"],
  buyer_finder: ["buyer_finder"],
  account_researcher: [
    "account_researcher",
    "account_enrich",
    "account_company",
    "account_join",
  ],
  email_writer_verifier: ["email_writer", "verifier", "approval_gate"],
  sender: ["sender"],
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  events: CampaignEvent[];
  agentFilter?: string | null;
  agentLabel?: string | null;
};

export function ActivityPanel({
  open,
  onOpenChange,
  events,
  agentFilter,
  agentLabel,
}: Props) {
  const allowed = agentFilter ? AGENT_FILTER[agentFilter] || [agentFilter] : null;
  const filtered = allowed
    ? events.filter((e) => allowed.includes(e.agent))
    : events;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full gap-0 border-l sm:max-w-[420px]"
        style={{ borderRadius: 0 }}
      >
        <SheetHeader className="border-b px-4 py-4">
          <SheetTitle className="text-[14px] font-semibold">
            {agentLabel ? `${agentLabel} activity` : "Activity"}
          </SheetTitle>
          <SheetDescription className="text-[13px] text-[var(--text-muted)]">
            Live events from this campaign run.
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {filtered.length === 0 ? (
            <p className="text-[13px] text-[var(--text-muted)]">No events yet for this agent.</p>
          ) : (
            <ul className="space-y-3">
              {filtered.map((ev) => (
                <li key={ev.id} className="border-b border-[var(--border)] pb-3 last:border-0">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span
                      className={cn(
                        "text-[11px] font-medium capitalize",
                        ev.level === "danger" && "text-[var(--status-danger)]",
                        ev.level === "warning" && "text-[var(--status-warning)]",
                        ev.level === "success" && "text-[var(--status-success)]",
                        !["danger", "warning", "success"].includes(ev.level) &&
                          "text-[var(--text-subtle)]",
                      )}
                    >
                      {ev.agent.replaceAll("_", " ")}
                    </span>
                    <RelativeTime value={ev.ts} />
                  </div>
                  <p className="text-[13px] leading-5 text-[var(--text)]">{ev.message}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
