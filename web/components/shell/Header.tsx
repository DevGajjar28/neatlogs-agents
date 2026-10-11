"use client";

import Link from "next/link";
import { Plus, Search } from "lucide-react";
import { useShell } from "@/components/shell/shell-context";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Header() {
  const { breadcrumbs, setCommandOpen, setNewCampaignOpen } = useShell();

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-4 border-b border-[var(--border)] bg-[var(--surface)] px-6">
      <nav
        aria-label="Breadcrumb"
        className="min-w-0 flex-1 truncate text-[14px] leading-5"
      >
        {breadcrumbs.map((crumb, i) => {
          const last = i === breadcrumbs.length - 1;
          return (
            <span key={`${crumb.label}-${i}`} className="inline">
              {i > 0 ? (
                <span className="mx-1.5 text-[var(--text-subtle)]" aria-hidden>
                  /
                </span>
              ) : null}
              {crumb.href && !last ? (
                <Link
                  href={crumb.href}
                  className="text-[var(--text-muted)] hover:text-[var(--text)]"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span
                  className={cn(
                    last
                      ? "font-semibold text-[var(--text)]"
                      : "text-[var(--text-muted)]",
                  )}
                >
                  {crumb.label}
                </span>
              )}
            </span>
          );
        })}
      </nav>

      <button
        type="button"
        onClick={() => setCommandOpen(true)}
        className="hidden h-8 min-w-[220px] items-center gap-2 rounded-[6px] border border-[var(--border-strong)] bg-[var(--surface)] px-2.5 text-left text-[13px] text-[var(--text-subtle)] hover:border-[var(--text-subtle)] md:inline-flex"
      >
        <Search className="size-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
        <span className="flex-1">Search or jump to…</span>
        <kbd className="rounded-[4px] border border-[var(--border)] bg-[var(--surface-muted)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-muted)]">
          ⌘K
        </kbd>
      </button>

      <Button
        type="button"
        className="h-8 gap-1.5 bg-[var(--primary)] text-[var(--primary-fg)] hover:bg-[var(--primary-hover)]"
        onClick={() => setNewCampaignOpen(true)}
      >
        <Plus className="size-4" strokeWidth={1.75} aria-hidden />
        New campaign
      </Button>
    </header>
  );
}
