"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  ApiError,
  createMailAccount,
  listMailPresets,
  patchMailAccount,
  type MailAccount,
} from "@/lib/api";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  account?: MailAccount | null;
  liveAllowed: boolean;
};

const PROVIDERS = [
  { id: "gmail", label: "Gmail" },
  { id: "workspace", label: "Google Workspace" },
  { id: "custom", label: "Other SMTP" },
] as const;

export function MailAccountDrawer({ open, onOpenChange, account, liveAllowed }: Props) {
  const qc = useQueryClient();
  const editing = Boolean(account);
  const presetsQ = useQuery({
    queryKey: queryKeys.mailPresets,
    queryFn: listMailPresets,
    enabled: open,
  });

  const [provider, setProvider] = useState<"gmail" | "workspace" | "custom">("gmail");
  const [label, setLabel] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [testRecipients, setTestRecipients] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [smtpHost, setSmtpHost] = useState("smtp.gmail.com");
  const [smtpPort, setSmtpPort] = useState(587);
  const [smtpSecurity, setSmtpSecurity] = useState("starttls");
  const [imapHost, setImapHost] = useState("imap.gmail.com");
  const [imapPort, setImapPort] = useState(993);
  const [dailyCap, setDailyCap] = useState(25);
  const [domainCap, setDomainCap] = useState(3);
  const [minGap, setMinGap] = useState(90);
  const [signature, setSignature] = useState("");
  const [postal, setPostal] = useState("");
  const [liveEnabled, setLiveEnabled] = useState(false);
  const [ackLawful, setAckLawful] = useState(false);
  const [ackPolicy, setAckPolicy] = useState(false);
  const [verifyDetail, setVerifyDetail] = useState<string | null>(null);
  const [verifyOk, setVerifyOk] = useState<boolean | null>(null);

  useEffect(() => {
    if (!open) return;
    setVerifyDetail(null);
    setVerifyOk(null);
    setPassword("");
    if (account) {
      setProvider((account.provider as "gmail" | "workspace" | "custom") || "gmail");
      setLabel(account.label);
      setDisplayName(account.display_name);
      setEmail(account.email);
      setTestRecipients((account.test_recipients || []).join(", "));
      setSmtpHost(account.smtp_host);
      setSmtpPort(account.smtp_port);
      setSmtpSecurity(account.smtp_security);
      setImapHost(account.imap_host);
      setImapPort(account.imap_port);
      setDailyCap(account.daily_cap);
      setDomainCap(account.per_domain_daily_cap);
      setMinGap(account.min_gap_seconds);
      setSignature(account.signature || "");
      setPostal(account.postal_address || "");
      setLiveEnabled(Boolean(account.live_enabled));
      setAckLawful(Boolean(account.live_enabled));
      setAckPolicy(Boolean(account.live_enabled));
    } else {
      setProvider("gmail");
      setLabel("");
      setDisplayName("");
      setEmail("");
      setTestRecipients("");
      setSignature("");
      setPostal("");
      setLiveEnabled(false);
      setAckLawful(false);
      setAckPolicy(false);
      setDailyCap(25);
      setDomainCap(3);
      setMinGap(90);
      const preset = presetsQ.data?.find((p) => p.id === "gmail");
      if (preset) applyPreset(preset);
    }
  }, [open, account, presetsQ.data]);

  function applyPreset(preset: {
    id: string;
    smtp_host: string;
    smtp_port: number;
    smtp_security: string;
    imap_host: string;
    imap_port: number;
  }) {
    setSmtpHost(preset.smtp_host);
    setSmtpPort(preset.smtp_port);
    setSmtpSecurity(preset.smtp_security);
    setImapHost(preset.imap_host);
    setImapPort(preset.imap_port);
  }

  const canLive = liveAllowed && postal.trim().length > 0 && ackLawful && ackPolicy;

  const body = useMemo(() => {
    const recipients = testRecipients
      .split(/[,;\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const base: Record<string, unknown> = {
      label: label.trim() || email.trim(),
      provider,
      email: email.trim(),
      display_name: displayName.trim() || email.split("@")[0],
      username: email.trim(),
      smtp_host: smtpHost,
      smtp_port: smtpPort,
      smtp_security: smtpSecurity,
      imap_host: imapHost,
      imap_port: imapPort,
      daily_cap: Math.min(100, Math.max(1, dailyCap)),
      per_domain_daily_cap: Math.min(10, Math.max(1, domainCap)),
      min_gap_seconds: Math.max(30, minGap),
      test_recipients: recipients.length ? recipients : email.trim() ? [email.trim()] : [],
      signature,
      postal_address: postal,
      live_enabled: canLive && liveEnabled,
    };
    return base;
  }, [
    label,
    email,
    displayName,
    provider,
    smtpHost,
    smtpPort,
    smtpSecurity,
    imapHost,
    imapPort,
    dailyCap,
    domainCap,
    minGap,
    testRecipients,
    signature,
    postal,
    canLive,
    liveEnabled,
  ]);

  const saveMut = useMutation({
    mutationFn: async () => {
      if (editing && account) {
        const patch = { ...body };
        if (password.trim()) patch.password = password.trim();
        return patchMailAccount(account.id, patch);
      }
      if (!password.trim()) throw new ApiError("App password is required", 422, null);
      return createMailAccount({ ...body, password: password.trim() });
    },
    onSuccess: (acc) => {
      void qc.invalidateQueries({ queryKey: queryKeys.mailAccounts });
      void qc.invalidateQueries({ queryKey: queryKeys.systemStatus });
      if (editing) {
        toast.success("Account updated");
        setVerifyDetail(null);
        setVerifyOk(null);
      } else {
        const ok = acc.status === "ok";
        setVerifyOk(ok);
        setVerifyDetail(
          ok
            ? "SMTP ok · IMAP ok · Drafts folder found"
            : acc.last_error || "Verification failed",
        );
        if (ok) {
          toast.success("Connected");
          onOpenChange(false);
        } else {
          toast.error(acc.last_error || "Verification failed");
        }
      }
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Couldn't save account");
    },
  });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full gap-0 border-l border-[var(--border)] bg-[var(--surface)] p-0 shadow-[var(--drawer-shadow)] sm:max-w-[480px]"
        style={{ borderRadius: 0 }}
      >
        <SheetHeader className="border-b border-[var(--border)] px-4 py-4">
          <SheetTitle className="text-[14px] font-semibold">
            {editing ? "Edit mail account" : "Add mail account"}
          </SheetTitle>
          <SheetDescription className="text-[13px] text-[var(--text-muted)]">
            Connect Gmail with an app password. Credentials are encrypted at rest.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          <div className="grid grid-cols-3 gap-2">
            {PROVIDERS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  setProvider(p.id);
                  const preset = presetsQ.data?.find((x) => x.id === p.id);
                  if (preset) applyPreset(preset);
                }}
                className={cn(
                  "rounded-[6px] border px-2 py-2 text-[12px] font-medium",
                  provider === p.id
                    ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                    : "border-[var(--border)]",
                )}
              >
                {p.label}
              </button>
            ))}
          </div>

          <Field label="Label">
            <Input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="h-8 rounded-[6px]"
              placeholder="Work Gmail"
            />
          </Field>
          <Field label="From name">
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="h-8 rounded-[6px]"
            />
          </Field>
          <Field label="Email" required>
            <Input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-8 rounded-[6px] font-mono"
              type="email"
            />
          </Field>
          <Field label={editing ? "App password (leave blank to keep)" : "App password"} required={!editing}>
            <div className="relative">
              <Input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="h-8 rounded-[6px] pr-9 font-mono"
                type={showPw ? "text" : "password"}
                autoComplete="new-password"
              />
              <button
                type="button"
                className="absolute right-2 top-1.5 text-[var(--text-muted)]"
                onClick={() => setShowPw((v) => !v)}
                aria-label={showPw ? "Hide password" : "Show password"}
              >
                {showPw ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
            <p className="text-[12px] text-[var(--text-subtle)]">
              16-character app password. Requires 2-Step Verification.{" "}
              <a
                href="https://myaccount.google.com/apppasswords"
                target="_blank"
                rel="noreferrer"
                className="text-[var(--accent)] underline-offset-2 hover:underline"
              >
                Create an app password ↗
              </a>
            </p>
          </Field>

          <Field label="Test recipients">
            <Input
              value={testRecipients}
              onChange={(e) => setTestRecipients(e.target.value)}
              className="h-8 rounded-[6px] font-mono"
              placeholder="you@example.com"
            />
            <p className="text-[12px] text-[var(--text-subtle)]">
              Comma-separated. Gmail test mode only sends here.
            </p>
          </Field>

          <button
            type="button"
            className="text-[12px] font-medium text-[var(--accent)] underline-offset-2 hover:underline"
            onClick={() => setAdvanced((v) => !v)}
          >
            {advanced ? "Hide advanced" : "Advanced"}
          </button>
          {advanced ? (
            <div className="space-y-3 rounded-[8px] border border-[var(--border)] p-3">
              <div className="grid grid-cols-2 gap-2">
                <Field label="SMTP host">
                  <Input value={smtpHost} onChange={(e) => setSmtpHost(e.target.value)} className="h-8 rounded-[6px] font-mono" />
                </Field>
                <Field label="SMTP port">
                  <Input type="number" value={smtpPort} onChange={(e) => setSmtpPort(Number(e.target.value) || 587)} className="h-8 rounded-[6px] font-mono" />
                </Field>
                <Field label="IMAP host">
                  <Input value={imapHost} onChange={(e) => setImapHost(e.target.value)} className="h-8 rounded-[6px] font-mono" />
                </Field>
                <Field label="IMAP port">
                  <Input type="number" value={imapPort} onChange={(e) => setImapPort(Number(e.target.value) || 993)} className="h-8 rounded-[6px] font-mono" />
                </Field>
                <Field label="Daily cap">
                  <Input type="number" min={1} max={100} value={dailyCap} onChange={(e) => setDailyCap(Number(e.target.value) || 1)} className="h-8 rounded-[6px] font-mono" />
                </Field>
                <Field label="Per-domain cap">
                  <Input type="number" min={1} max={10} value={domainCap} onChange={(e) => setDomainCap(Number(e.target.value) || 1)} className="h-8 rounded-[6px] font-mono" />
                </Field>
                <Field label="Min gap (s)">
                  <Input type="number" min={30} value={minGap} onChange={(e) => setMinGap(Number(e.target.value) || 30)} className="h-8 rounded-[6px] font-mono" />
                </Field>
              </div>
              <Field label="Signature">
                <Textarea value={signature} onChange={(e) => setSignature(e.target.value)} rows={2} className="rounded-[6px]" />
              </Field>
              <Field label="Postal address (required for live)">
                <Textarea value={postal} onChange={(e) => setPostal(e.target.value)} rows={2} className="rounded-[6px]" />
              </Field>
            </div>
          ) : null}

          <div className="space-y-2 rounded-[8px] border border-[var(--border)] p-3">
            <p className="text-[13px] font-medium">Live sending</p>
            {!liveAllowed ? (
              <p className="text-[12px] text-[var(--text-muted)]">
                Disabled while DEMO_MODE is on or ALLOW_LIVE_SENDS is false.
              </p>
            ) : (
              <>
                <label className="flex items-start gap-2 text-[12px]">
                  <Checkbox checked={ackLawful} onCheckedChange={(c) => setAckLawful(Boolean(c))} />
                  Recipients are business contacts I may lawfully email
                </label>
                <label className="flex items-start gap-2 text-[12px]">
                  <Checkbox checked={ackPolicy} onCheckedChange={(c) => setAckPolicy(Boolean(c))} />
                  I&apos;ve read the sending policy
                </label>
                <label className="flex items-center gap-2 text-[12px]">
                  <Checkbox
                    checked={liveEnabled && canLive}
                    disabled={!canLive}
                    onCheckedChange={(c) => setLiveEnabled(Boolean(c))}
                  />
                  Enable live for this account
                </label>
              </>
            )}
          </div>

          {verifyDetail ? (
            <p
              className={cn(
                "text-[13px]",
                verifyOk ? "text-[var(--status-success)]" : "text-[var(--status-danger)]",
              )}
            >
              {verifyOk ? "✓ " : ""}
              {verifyDetail}
            </p>
          ) : null}
        </div>

        <SheetFooter className="flex-row justify-end gap-2 border-t border-[var(--border)] px-4 py-3">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={saveMut.isPending}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!email.trim() || (!editing && !password.trim()) || saveMut.isPending}
            className="bg-[var(--primary)] text-[var(--primary-fg)] hover:bg-[var(--primary-hover)]"
            onClick={() => saveMut.mutate()}
          >
            {saveMut.isPending ? "Saving…" : editing ? "Save" : "Save and verify"}
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
