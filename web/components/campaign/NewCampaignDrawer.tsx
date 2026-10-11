"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { toast } from "sonner";
import { useShell } from "@/components/shell/shell-context";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, createCampaign, estimateCampaign } from "@/lib/api";
import { formatCredits } from "@/lib/format";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

const CHAOS_FLAGS = [
  "crust_429",
  "empty_people",
  "llm_bad_json",
  "crust_403_fields",
  "poisoned_page",
] as const;

const KILL_NODES = [
  "",
  "planner",
  "product_researcher",
  "buyer_propose_icp",
  "buyer_search",
  "account_enrich",
  "account_researcher",
  "email_writer",
  "verifier",
  "approval_gate",
  "sender",
] as const;

function normalizeWebsite(raw: string): string {
  const t = raw.trim();
  if (!t) return t;
  if (/^https?:\/\//i.test(t)) return t;
  return `https://${t}`;
}

function isValidHttpUrl(value: string): boolean {
  try {
    const u = new URL(value);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

export function NewCampaignDrawer() {
  const router = useRouter();
  const qc = useQueryClient();
  const { newCampaignOpen, setNewCampaignOpen } = useShell();

  const [companyName, setCompanyName] = useState("PostHog");
  const [website, setWebsite] = useState("https://posthog.com");
  const [description, setDescription] = useState(
    "Product analytics and feature flags for engineers",
  );
  const [n, setN] = useState(10);
  const [mode, setMode] = useState<"replay" | "live">("replay");
  const [cap, setCap] = useState(250);
  const [chaos, setChaos] = useState<Set<string>>(new Set());
  const [killAfter, setKillAfter] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [websiteError, setWebsiteError] = useState<string | null>(null);

  useEffect(() => {
    if (!newCampaignOpen) return;
    // keep form values between opens; only clear validation
    setWebsiteError(null);
  }, [newCampaignOpen]);

  const estimateQ = useQuery({
    queryKey: ["estimate", n, mode],
    queryFn: () => estimateCampaign(n, mode),
    enabled: newCampaignOpen && n >= 5 && n <= 50,
  });

  const valid =
    companyName.trim().length > 0 &&
    isValidHttpUrl(normalizeWebsite(website)) &&
    n >= 5 &&
    n <= 50 &&
    cap > 0;

  const chaosCsv = useMemo(() => Array.from(chaos).join(","), [chaos]);

  const createMut = useMutation({
    mutationFn: () =>
      createCampaign({
        company_name: companyName.trim(),
        website: normalizeWebsite(website),
        description: description.trim(),
        n,
        mode,
        cap,
        chaos: chaosCsv,
        kill_after: killAfter,
      }),
    onSuccess: (campaign) => {
      setNewCampaignOpen(false);
      void qc.invalidateQueries({ queryKey: queryKeys.campaigns });
      toast.success("Campaign started");
      router.push(`/campaigns/${campaign.id}`);
    },
    onError: (err) => {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Couldn't start the campaign. Try again.";
      toast.error(msg);
    },
  });

  return (
    <Sheet open={newCampaignOpen} onOpenChange={setNewCampaignOpen}>
      <SheetContent
        side="right"
        className="w-full gap-0 border-l border-[var(--border)] bg-[var(--surface)] p-0 shadow-[var(--drawer-shadow)] sm:max-w-[480px]"
        style={{ borderRadius: 0 }}
      >
        <SheetHeader className="border-b border-[var(--border)] px-4 py-4">
          <SheetTitle className="text-[14px] font-semibold">New campaign</SheetTitle>
          <SheetDescription className="text-[13px] text-[var(--text-muted)]">
            Tell SignalSDR who you sell to. It finds buyers, researches them, and drafts emails.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          <Field label="Company name" required>
            <Input
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="Acme"
              className="h-8 rounded-[6px]"
            />
          </Field>

          <Field label="Website" required>
            <Input
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              onBlur={() => {
                const next = normalizeWebsite(website);
                setWebsite(next);
                setWebsiteError(
                  next && !isValidHttpUrl(next)
                    ? "Enter a full URL like https://acme.com"
                    : null,
                );
              }}
              placeholder="https://acme.com"
              className="h-8 rounded-[6px]"
            />
            {websiteError ? (
              <p className="text-[12px] text-[var(--status-danger)]">{websiteError}</p>
            ) : (
              <p className="text-[12px] text-[var(--text-subtle)]">Include https://</p>
            )}
          </Field>

          <Field label="What it does">
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="One sentence is enough if your site is thin."
              className="rounded-[6px]"
            />
          </Field>

          <Field label="Leads to find">
            <Input
              type="number"
              min={5}
              max={50}
              value={n}
              onChange={(e) => setN(Number(e.target.value) || 5)}
              className="h-8 w-28 rounded-[6px] font-mono"
            />
          </Field>

          <Field label="Data mode">
            <div className="grid grid-cols-2 gap-2">
              {(
                [
                  ["replay", "Replay", "0 credits, cached data"],
                  ["live", "Live", "Uses Crustdata credits"],
                ] as const
              ).map(([value, title, hint]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setMode(value)}
                  className={cn(
                    "rounded-[6px] border px-3 py-2 text-left",
                    mode === value
                      ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                      : "border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-strong)]",
                  )}
                >
                  <div className="text-[13px] font-medium">{title}</div>
                  <div className="text-[11px] text-[var(--text-subtle)]">{hint}</div>
                </button>
              ))}
            </div>
          </Field>

          <Field label="Credit cap">
            <Input
              type="number"
              min={1}
              value={cap}
              onChange={(e) => setCap(Number(e.target.value) || 1)}
              className="h-8 w-28 rounded-[6px] font-mono"
            />
            <p className="text-[12px] text-[var(--text-muted)]">
              {estimateQ.isLoading
                ? "Estimating…"
                : `Estimated ~${formatCredits(estimateQ.data?.total ?? 0)} credits for ${n} leads`}
            </p>
          </Field>

          <div className="flex items-center gap-2 rounded-[6px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2 text-[12px] text-[var(--text-muted)]">
            <Lock className="size-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
            Demo sends only — mail goes to your local catcher
          </div>

          <div>
            <button
              type="button"
              className="text-[12px] font-medium text-[var(--accent)] underline-offset-2 hover:underline"
              onClick={() => setAdvancedOpen((v) => !v)}
            >
              {advancedOpen ? "Hide advanced" : "Advanced"}
            </button>
            {advancedOpen ? (
              <div className="mt-3 space-y-3 rounded-[8px] border border-[var(--border)] p-3">
                <div className="space-y-2">
                  <p className="text-[12px] font-medium text-[var(--text)]">Fault injection</p>
                  {CHAOS_FLAGS.map((flag) => (
                    <label key={flag} className="flex items-center gap-2 text-[13px]">
                      <Checkbox
                        checked={chaos.has(flag)}
                        onCheckedChange={(checked) => {
                          setChaos((prev) => {
                            const next = new Set(prev);
                            if (checked) next.add(flag);
                            else next.delete(flag);
                            return next;
                          });
                        }}
                      />
                      <span className="font-mono text-[12px]">{flag}</span>
                    </label>
                  ))}
                </div>
                <Field label="Kill after">
                  <Select value={killAfter || "__none__"} onValueChange={(v) => setKillAfter(v === "__none__" ? "" : v)}>
                    <SelectTrigger className="h-8 rounded-[6px]">
                      <SelectValue placeholder="None" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">None</SelectItem>
                      {KILL_NODES.filter(Boolean).map((node) => (
                        <SelectItem key={node} value={node}>
                          {node}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
              </div>
            ) : null}
          </div>
        </div>

        <SheetFooter className="flex-row justify-end gap-2 border-t border-[var(--border)] px-4 py-3">
          <Button
            type="button"
            variant="ghost"
            onClick={() => setNewCampaignOpen(false)}
            disabled={createMut.isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!valid || createMut.isPending}
            className="bg-[var(--primary)] text-[var(--primary-fg)] hover:bg-[var(--primary-hover)]"
            onClick={() => createMut.mutate()}
          >
            {createMut.isPending ? "Starting…" : "Start campaign"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[12px] font-medium text-[var(--text)]">
        {label}
        {required ? <span className="text-[var(--status-danger)]"> *</span> : null}
      </span>
      {children}
    </label>
  );
}
