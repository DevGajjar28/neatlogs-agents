"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

type ShellContextValue = {
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
  toggleCollapsed: () => void;
  commandOpen: boolean;
  setCommandOpen: (v: boolean) => void;
  breadcrumbs: { label: string; href?: string }[];
  setBreadcrumbs: (crumbs: { label: string; href?: string }[]) => void;
};

const ShellContext = createContext<ShellContextValue | null>(null);

export function ShellProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [breadcrumbs, setBreadcrumbs] = useState<{ label: string; href?: string }[]>([
    { label: "Campaigns", href: "/campaigns" },
  ]);
  const toggleCollapsed = useCallback(() => setCollapsed((c) => !c), []);
  const value = useMemo(
    () => ({
      collapsed,
      setCollapsed,
      toggleCollapsed,
      commandOpen,
      setCommandOpen,
      breadcrumbs,
      setBreadcrumbs,
    }),
    [collapsed, toggleCollapsed, commandOpen, breadcrumbs],
  );
  return <ShellContext.Provider value={value}>{children}</ShellContext.Provider>;
}

export function useShell() {
  const ctx = useContext(ShellContext);
  if (!ctx) throw new Error("useShell must be used within ShellProvider");
  return ctx;
}
