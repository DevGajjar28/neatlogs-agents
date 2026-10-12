"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  FileText,
  Inbox,
  LayoutDashboard,
  LayoutList,
  Plus,
  Send,
  Settings2,
} from "lucide-react";
import { useShell } from "@/components/shell/shell-context";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/campaigns", label: "Campaigns", icon: LayoutList },
  { href: "/approvals", label: "Approvals", icon: Inbox },
  { href: "/outbox", label: "Outbox", icon: Send },
  { href: "/templates", label: "Templates", icon: FileText },
  { href: "/reports", label: "Reports", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings2 },
] as const;

export function CommandMenu() {
  const router = useRouter();
  const { commandOpen, setCommandOpen, setNewCampaignOpen } = useShell();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandOpen(!commandOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [commandOpen, setCommandOpen]);

  return (
    <CommandDialog
      open={commandOpen}
      onOpenChange={setCommandOpen}
      title="Command palette"
    >
      <CommandInput placeholder="Jump to…" />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        <CommandGroup heading="Actions">
          <CommandItem
            value="New campaign"
            onSelect={() => {
              setCommandOpen(false);
              setNewCampaignOpen(true);
            }}
          >
            <Plus className="size-4" strokeWidth={1.75} />
            New campaign
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading="Navigation">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
            <CommandItem
              key={href}
              value={label}
              onSelect={() => {
                setCommandOpen(false);
                router.push(href);
              }}
            >
              <Icon className="size-4" strokeWidth={1.75} />
              {label}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
