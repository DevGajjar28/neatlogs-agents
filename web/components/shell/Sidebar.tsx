"use client";

import { useEffect, useMemo, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  FileText,
  Inbox,
  LayoutDashboard,
  LayoutList,
  PanelLeft,
  Send,
  Settings2,
} from "lucide-react";
import { toast } from "sonner";
import { SystemStatus } from "@/components/shell/SystemStatus";
import { useShell } from "@/components/shell/shell-context";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { getPendingApprovals, listCampaigns } from "@/lib/api";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/campaigns", label: "Campaigns", icon: LayoutList },
  { href: "/approvals", label: "Approvals", icon: Inbox },
  { href: "/outbox", label: "Outbox", icon: Send },
  { href: "/templates", label: "Templates", icon: FileText },
  { href: "/reports", label: "Reports", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings2 },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const { collapsed, toggleCollapsed } = useShell();
  const prevCount = useRef<number | null>(null);

  const campaignsQ = useQuery({
    queryKey: queryKeys.campaigns,
    queryFn: listCampaigns,
    refetchInterval: 8_000,
  });

  const waiting = useMemo(
    () => (campaignsQ.data || []).filter((c) => c.status === "waiting_approval"),
    [campaignsQ.data],
  );

  const pendingQueries = useQueries({
    queries: waiting.map((c) => ({
      queryKey: queryKeys.pendingApprovals(c.id),
      queryFn: () => getPendingApprovals(c.id),
      refetchInterval: 8_000,
    })),
  });

  const pendingCount = useMemo(() => {
    return pendingQueries.reduce((sum, q) => sum + (q.data?.items?.length || 0), 0);
  }, [pendingQueries]);

  useEffect(() => {
    if (prevCount.current !== null && pendingCount > prevCount.current) {
      toast.message("Approval needed", {
        description: `${pendingCount} draft${pendingCount === 1 ? "" : "s"} waiting`,
      });
    }
    prevCount.current = pendingCount;
  }, [pendingCount]);

  const badge =
    pendingCount > 0 ? String(pendingCount > 99 ? "99+" : pendingCount) : "0";

  return (
    <aside
      className={cn(
        "sticky top-0 flex h-screen shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] transition-[width] duration-200",
        collapsed ? "w-14" : "w-[232px]",
      )}
    >
      <div
        className={cn(
          "flex h-14 items-center border-b border-[var(--border)]",
          collapsed ? "justify-center px-1" : "justify-between px-3",
        )}
      >
        {!collapsed ? (
          <div className="flex items-baseline gap-1.5">
            <span className="text-[14px] font-semibold leading-5 text-[var(--text)]">
              ReachPilot
            </span>
            <span className="text-[11px] font-medium text-[var(--text-subtle)]">beta</span>
          </div>
        ) : (
          <span className="text-[12px] font-semibold text-[var(--text)]" title="ReachPilot">
            R
          </span>
        )}
        <button
          type="button"
          onClick={toggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="inline-flex size-8 items-center justify-center rounded-[6px] text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)]"
        >
          <PanelLeft className="size-4" strokeWidth={1.75} />
        </button>
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 p-2" aria-label="Primary">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          const link = (
            <Link
              href={href}
              className={cn(
                "relative flex h-8 items-center gap-2 rounded-[6px] px-2 text-[13px] font-medium text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)]",
                active && "bg-[var(--surface-muted)] text-[var(--text)]",
                collapsed && "justify-center px-0",
              )}
            >
              {active ? (
                <span
                  className="absolute top-1 bottom-1 left-0 w-0.5 rounded-r bg-[var(--accent)]"
                  aria-hidden
                />
              ) : null}
              <Icon className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
              {!collapsed ? <span>{label}</span> : null}
              {!collapsed && href === "/approvals" ? (
                <span
                  className={cn(
                    "ml-auto rounded-[6px] px-1.5 text-[11px]",
                    pendingCount > 0
                      ? "bg-[var(--status-warning-soft)] font-semibold text-[var(--status-warning)]"
                      : "bg-[var(--surface)] text-[var(--text-subtle)]",
                  )}
                >
                  {badge}
                </span>
              ) : null}
            </Link>
          );
          if (!collapsed) return <div key={href}>{link}</div>;
          return (
            <Tooltip key={href}>
              <TooltipTrigger asChild>{link}</TooltipTrigger>
              <TooltipContent side="right">
                {label}
                {href === "/approvals" && pendingCount > 0 ? ` (${pendingCount})` : ""}
              </TooltipContent>
            </Tooltip>
          );
        })}
      </nav>

      <div className={cn("border-t border-[var(--border)] p-2", collapsed && "px-1")}>
        <SystemStatus collapsed={collapsed} />
      </div>
    </aside>
  );
}
