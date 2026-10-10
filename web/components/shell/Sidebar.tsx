"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Inbox,
  LayoutList,
  PanelLeft,
  Send,
  Settings2,
} from "lucide-react";
import { SystemStatus } from "@/components/shell/SystemStatus";
import { useShell } from "@/components/shell/shell-context";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/campaigns", label: "Campaigns", icon: LayoutList },
  { href: "/approvals", label: "Approvals", icon: Inbox },
  { href: "/outbox", label: "Outbox", icon: Send },
  { href: "/reports", label: "Reports", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings2 },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const { collapsed, toggleCollapsed } = useShell();

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
              SignalSDR
            </span>
            <span className="text-[11px] font-medium text-[var(--text-subtle)]">beta</span>
          </div>
        ) : (
          <span className="text-[12px] font-semibold text-[var(--text)]" title="SignalSDR">
            S
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
                <span className="ml-auto rounded-[6px] bg-[var(--surface)] px-1.5 text-[11px] text-[var(--text-subtle)]">
                  —
                </span>
              ) : null}
            </Link>
          );
          if (!collapsed) return <div key={href}>{link}</div>;
          return (
            <Tooltip key={href}>
              <TooltipTrigger asChild>{link}</TooltipTrigger>
              <TooltipContent side="right">{label}</TooltipContent>
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
