"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

type ShellContextValue = {
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
  toggleCollapsed: () => void;
  commandOpen: boolean;
  setCommandOpen: (v: boolean) => void;
  newCampaignOpen: boolean;
  setNewCampaignOpen: (v: boolean) => void;
  breadcrumbs: { label: string; href?: string }[];
  setBreadcrumbs: (crumbs: { label: string; href?: string }[]) => void;
};

const ShellContext = createContext<ShellContextValue | null>(null);

export function ShellProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [newCampaignOpen, setNewCampaignOpen] = useState(false);
  const [breadcrumbs, setBreadcrumbs] = useState<{ label: string; href?: string }[]>([
    { label: "Campaigns", href: "/campaigns" },
  ]);
  const toggleCollapsed = useCallback(() => setCollapsed((c) => !c), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;
      if (e.key.toLowerCase() === "n" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        setNewCampaignOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo(
    () => ({
      collapsed,
      setCollapsed,
      toggleCollapsed,
      commandOpen,
      setCommandOpen,
      newCampaignOpen,
      setNewCampaignOpen,
      breadcrumbs,
      setBreadcrumbs,
    }),
    [collapsed, toggleCollapsed, commandOpen, newCampaignOpen, breadcrumbs],
  );
  return <ShellContext.Provider value={value}>{children}</ShellContext.Provider>;
}

export function useShell() {
  const ctx = useContext(ShellContext);
  if (!ctx) throw new Error("useShell must be used within ShellProvider");
  return ctx;
}
