"use client";

import { Sidebar } from "@/components/shell/Sidebar";
import { Header } from "@/components/shell/Header";
import { CommandMenu } from "@/components/shell/CommandMenu";
import { ShellProvider } from "@/components/shell/shell-context";
import { TooltipProvider } from "@/components/ui/tooltip";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ShellProvider>
      <TooltipProvider delayDuration={200}>
        <div className="flex min-h-screen bg-[var(--bg)]">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <Header />
            <main className="mx-auto w-full max-w-[1440px] flex-1 px-6 py-6">{children}</main>
          </div>
        </div>
        <CommandMenu />
      </TooltipProvider>
    </ShellProvider>
  );
}
