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
import { EmailTemplatesSection } from "@/components/mail/EmailTemplatesSection";
import {
  ApiError,
  createCampaign,
  estimateCampaign,
  getSystemStatus,
  listEmailTemplates,
  listMailAccounts,
  parseCompaniesCsv,
  type ParseCompaniesRow,
  type SendMode,
} from "@/lib/api";
import { formatCredits } from "@/lib/format";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";
import Link from "next/link";

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
  "buyer_import",
  "account_enrich",
  "account_researcher",
  "email_writer",
  "verifier",
  "approval_gate",
  "sender",
] as const;

const SAMPLE_CSV = `company_name,website,description
Acme Analytics,https://acme-analytics.example,B2B product analytics
Northwind Labs,northwindlabs.example,Devtools for infra teams
Contoso Cloud,https://www.contoso-cloud.example/about,Cloud cost visibility
`;

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
  const [sendMode, setSendMode] = useState<SendMode>("sandbox");
  const [mailAccountId, setMailAccountId] = useState<string>("");
  const [liveConfirm, setLiveConfirm] = useState("");
  const [targetMode, setTargetMode] = useState<"discover" | "provided">("discover");
  const [csvText, setCsvText] = useState("");
  const [parsedRows, setParsedRows] = useState<ParseCompaniesRow[]>([]);
  const [okCount, setOkCount] = useState(0);
  const [parseError, setParseError] = useState<string | null>(null);
  const [templateId, setTemplateId] = useState<string>("");
  const [previewTemplateId, setPreviewTemplateId] = useState<string | null>(null);

  useEffect(() => {
    if (!newCampaignOpen) return;
    // keep form values between opens; only clear validation
    setWebsiteError(null);
  }, [newCampaignOpen]);

  const templatesQ = useQuery({
    queryKey: queryKeys.emailTemplates,
    queryFn: listEmailTemplates,
    enabled: newCampaignOpen,
  });

  useEffect(() => {
    if (!templatesQ.data?.length) return;
    setTemplateId((prev) => {
      if (prev && templatesQ.data.some((t) => t.id === prev)) return prev;
      const def = templatesQ.data.find((t) => t.is_default) || templatesQ.data[0];
      return def?.id || "";
    });
  }, [templatesQ.data]);

  const effectiveN = targetMode === "provided" ? Math.max(okCount, 1) : n;

  const estimateQ = useQuery({
    queryKey: ["estimate", effectiveN, mode, targetMode],
    queryFn: () => estimateCampaign(effectiveN, mode, targetMode),
    enabled:
      newCampaignOpen &&
      effectiveN >= 1 &&
      effectiveN <= 50 &&
      (targetMode === "discover" ? n >= 5 : okCount >= 1),
  });

  const parseMut = useMutation({
    mutationFn: (text: string) => parseCompaniesCsv(text),
    onSuccess: (data) => {
      setParsedRows(data.rows || []);
      setOkCount(data.ok_count || 0);
      setParseError(null);
    },
    onError: (err) => {
      setParsedRows([]);
      setOkCount(0);
      setParseError(
        err instanceof ApiError ? err.message : "Couldn't parse the company list.",
      );
    },
  });

  useEffect(() => {
    if (targetMode !== "provided") return;
    const t = csvText.trim();
    if (!t) {
      setParsedRows([]);
      setOkCount(0);
      setParseError(null);
      return;
    }
    const handle = window.setTimeout(() => {
      parseMut.mutate(csvText);
    }, 350);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [csvText, targetMode]);

  const statusQ = useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: getSystemStatus,
    enabled: newCampaignOpen,
  });

  const accountsQ = useQuery({
    queryKey: queryKeys.mailAccounts,
    queryFn: listMailAccounts,
    enabled: newCampaignOpen,
  });

  const okAccounts = (accountsQ.data || []).filter((a) => a.status === "ok");
  const selectedAccount = okAccounts.find((a) => a.id === mailAccountId);

  // When drawer opens with a verified Gmail account, default to gmail_test once.
  useEffect(() => {
    if (!newCampaignOpen || !accountsQ.isSuccess) return;
    const ok = (accountsQ.data || []).filter((a) => a.status === "ok");
    if (ok.length === 0) return;
    const preferred = ok.find((a) => a.is_default) || ok[0];
    setMailAccountId((prev) => prev || preferred.id);
    setSendMode((prev) => (prev === "sandbox" ? "gmail_test" : prev));
    // Only when accounts first resolve for this open — intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newCampaignOpen, accountsQ.isSuccess]);
  const maxMode = statusQ.data?.max_send_mode || "gmail_test";
  const liveAllowed =
    maxMode === "gmail_live" && Boolean(selectedAccount?.live_enabled);

  const sendModeHelper = useMemo(() => {
    switch (sendMode) {
      case "sandbox":
        return "Mail goes to your local catcher (Mailpit). No Gmail traffic.";
      case "gmail_drafts":
        return "Saves drafts in Gmail Drafts. Nothing is sent to prospects.";
      case "gmail_test":
        return "Safe mode: delivers only to addresses on the mail account's test allowlist. If the contact email is on that list, it goes there; otherwise it is rewritten to the first allowlisted inbox (usually your own). Real prospects need Gmail live.";
      case "gmail_live":
        return "Sends to the contact's real address. Enable Live on the mail account, then type the account email to confirm.";
      default:
        return "";
    }
  }, [sendMode]);

  const okCompanies = useMemo(
    () =>
      parsedRows
        .filter((r) => r.status === "ok")
        .map((r) => ({
          name: r.name,
          domain: r.domain,
          description: r.description || "",
        })),
    [parsedRows],
  );

  const valid =
    companyName.trim().length > 0 &&
    isValidHttpUrl(normalizeWebsite(website)) &&
    (targetMode === "provided"
      ? okCount >= 1 && okCount <= 50
      : n >= 5 && n <= 50) &&
    cap > 0 &&
    (sendMode === "sandbox" || Boolean(mailAccountId)) &&
    (sendMode !== "gmail_live" ||
      (liveAllowed &&
        liveConfirm.trim().toLowerCase() ===
          (selectedAccount?.email || "").toLowerCase()));

  const chaosCsv = useMemo(() => Array.from(chaos).join(","), [chaos]);

  const createMut = useMutation({
    mutationFn: () =>
      createCampaign({
        company_name: companyName.trim(),
        website: normalizeWebsite(website),
        description: description.trim(),
        n: targetMode === "provided" ? okCount : n,
        mode,
        cap,
        chaos: chaosCsv,
        kill_after: killAfter,
        send_mode: sendMode,
        mail_account_id: sendMode === "sandbox" ? null : mailAccountId || null,
        live_confirm_email:
          sendMode === "gmail_live" ? liveConfirm.trim() : null,
        target_mode: targetMode,
        provided_companies: targetMode === "provided" ? okCompanies : [],
        template_id: templateId || null,
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
    <>
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

          <Field label="Target companies">
            <div className="grid grid-cols-2 gap-2">
              {(
                [
                  ["discover", "Find buyers for me", "Search lookalikes from your ICP"],
                  ["provided", "Use my list", "Paste or upload a CSV of companies"],
                ] as const
              ).map(([value, title, hint]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setTargetMode(value)}
                  className={cn(
                    "rounded-[6px] border px-3 py-2 text-left",
                    targetMode === value
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

          {targetMode === "provided" ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[12px] font-medium text-[var(--text)]">
                  Company list
                </span>
                <button
                  type="button"
                  className="text-[12px] font-medium text-[var(--accent)] underline-offset-2 hover:underline"
                  onClick={() => {
                    const blob = new Blob([SAMPLE_CSV], { type: "text/csv;charset=utf-8" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = "sample-companies.csv";
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Download sample CSV
                </button>
              </div>
              <Textarea
                value={csvText}
                onChange={(e) => setCsvText(e.target.value)}
                rows={5}
                placeholder={"company_name,website,description\nAcme,https://acme.com,Notes"}
                className="rounded-[6px] font-mono text-[12px]"
              />
              <label className="inline-flex cursor-pointer text-[12px] font-medium text-[var(--accent)] underline-offset-2 hover:underline">
                Upload CSV
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    const text = await file.text();
                    setCsvText(text);
                    e.target.value = "";
                  }}
                />
              </label>
              <p className="text-[12px] text-[var(--text-muted)]">
                Header optional. One company per line:{" "}
                <span className="font-mono">Name, https://site.com</span>
                {" "}(or CSV with company_name, website, description). Max 50.
              </p>
              {parseError ? (
                <p className="text-[12px] text-[var(--status-danger)]">{parseError}</p>
              ) : null}
              {parsedRows.length > 0 ? (
                <div className="max-h-40 overflow-auto rounded-[6px] border border-[var(--border)]">
                  <table className="w-full text-left text-[11px]">
                    <thead className="sticky top-0 bg-[var(--surface-muted)] text-[var(--text-muted)]">
                      <tr>
                        <th className="px-2 py-1.5 font-medium">Name</th>
                        <th className="px-2 py-1.5 font-medium">Domain</th>
                        <th className="px-2 py-1.5 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {parsedRows.map((row, i) => (
                        <tr key={`${row.domain}-${i}`} className="border-t border-[var(--border)]">
                          <td className="px-2 py-1.5">{row.name || "—"}</td>
                          <td className="px-2 py-1.5 font-mono">{row.domain || "—"}</td>
                          <td
                            className={cn(
                              "px-2 py-1.5",
                              row.status === "ok"
                                ? "text-[var(--status-success)]"
                                : "text-[var(--status-danger)]",
                            )}
                          >
                            {row.status}
                            {row.reason ? ` · ${row.reason}` : ""}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              <p className="text-[12px] text-[var(--text-muted)]">
                {okCount} valid compan{okCount === 1 ? "y" : "ies"}
                {parseMut.isPending ? " · parsing…" : ""}
              </p>
            </div>
          ) : (
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
          )}

          <Field label="Email style">
            <div className="flex items-center gap-2">
              <Select
                value={templateId || "__none__"}
                onValueChange={(v) => setTemplateId(v === "__none__" ? "" : v)}
              >
                <SelectTrigger className="h-8 flex-1 rounded-[6px]">
                  <SelectValue placeholder="Default style" />
                </SelectTrigger>
                <SelectContent>
                  {(templatesQ.data || []).map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                      {t.is_default ? " · default" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {templateId ? (
                <button
                  type="button"
                  className="shrink-0 text-[12px] font-medium text-[var(--accent)] underline-offset-2 hover:underline"
                  onClick={() => setPreviewTemplateId(templateId)}
                >
                  Preview
                </button>
              ) : null}
            </div>
            <p className="text-[12px] text-[var(--text-subtle)]">
              Style guide snapshotted when the campaign starts.{" "}
              <Link href="/settings" className="text-[var(--accent)] underline-offset-2 hover:underline">
                Manage in Settings
              </Link>
            </p>
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
                : targetMode === "provided"
                  ? `Estimated ~${formatCredits(estimateQ.data?.total ?? 0)} credits for your list of ${okCount}`
                  : `Estimated ~${formatCredits(estimateQ.data?.total ?? 0)} credits for ${n} leads`}
            </p>
          </Field>

          <Field label="Send from">
            {okAccounts.length === 0 ? (
              <p className="text-[12px] text-[var(--text-muted)]">
                No connected accounts.{" "}
                <Link href="/settings" className="text-[var(--accent)] underline-offset-2 hover:underline">
                  Add one in Settings
                </Link>
                {" "}(sandbox still works without an account).
              </p>
            ) : (
              <Select
                value={mailAccountId || "__none__"}
                onValueChange={(v) => setMailAccountId(v === "__none__" ? "" : v)}
              >
                <SelectTrigger className="h-8 rounded-[6px]">
                  <SelectValue placeholder="Select account" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">None (sandbox only)</SelectItem>
                  {okAccounts.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.email} · {a.sent_24h}/{a.cap} today
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>

          <Field label="Send mode">
            <div className="grid grid-cols-2 gap-2">
              {(
                [
                  ["sandbox", "Sandbox"],
                  ["gmail_drafts", "Gmail drafts"],
                  ["gmail_test", "Gmail test"],
                  ["gmail_live", "Live"],
                ] as const
              ).map(([value, title]) => {
                const disabled =
                  (value !== "sandbox" && !mailAccountId) ||
                  (value === "gmail_live" && !liveAllowed);
                return (
                  <button
                    key={value}
                    type="button"
                    disabled={disabled}
                    title={
                      value === "gmail_live" && !liveAllowed
                        ? "Live requires DEMO_MODE=false, ALLOW_LIVE_SENDS=true in .env, and Live enabled on the mail account in Settings"
                        : value !== "sandbox" && !mailAccountId
                          ? "Select a verified mail account under Send from first"
                          : undefined
                    }
                    onClick={() => setSendMode(value)}
                    className={cn(
                      "rounded-[6px] border px-3 py-2 text-left text-[13px] font-medium",
                      sendMode === value
                        ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                        : "border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-strong)]",
                      disabled && "cursor-not-allowed opacity-50",
                    )}
                  >
                    {title}
                  </button>
                );
              })}
            </div>
            <p className="text-[12px] text-[var(--text-muted)]">{sendModeHelper}</p>
            {!liveAllowed ? (
              <p className="text-[11px] text-[var(--text-subtle)]">
                Live is locked until{" "}
                <span className="font-mono">DEMO_MODE=false</span>,{" "}
                <span className="font-mono">ALLOW_LIVE_SENDS=true</span>, and the
                selected account has Live enabled in Settings. Use{" "}
                <strong>Gmail test</strong> to send via your real account to allowlisted
                addresses only.
              </p>
            ) : null}
            {sendMode === "gmail_live" && selectedAccount ? (
              <Input
                className="mt-2 h-8 rounded-[6px] font-mono"
                placeholder={`Type ${selectedAccount.email} to confirm`}
                value={liveConfirm}
                onChange={(e) => setLiveConfirm(e.target.value)}
              />
            ) : null}
          </Field>

          {sendMode === "sandbox" ? (
            <div className="flex items-center gap-2 rounded-[6px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2 text-[12px] text-[var(--text-muted)]">
              <Lock className="size-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
              Demo sends only — mail goes to your local catcher
            </div>
          ) : null}

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
      {previewTemplateId ? (
        <EmailTemplatesSection
          openId={previewTemplateId}
          readOnly
          sheetOnly
          onOpenChange={(o) => {
            if (!o) setPreviewTemplateId(null);
          }}
        />
      ) : null}
    </>
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
