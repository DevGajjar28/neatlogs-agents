"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { Mono } from "@/components/common/Mono";
import { RelativeTime } from "@/components/common/RelativeTime";
import { StatusBadge } from "@/components/common/StatusBadge";
import { MailAccountDrawer } from "@/components/mail/MailAccountDrawer";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ApiError,
  deleteMailAccount,
  disableMailAccount,
  enableMailAccount,
  listMailAccounts,
  testSendMailAccount,
  type MailAccount,
  verifyMailAccount,
} from "@/lib/api";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

function statusTone(status: string): { tone?: "success" | "warning" | "danger" | "neutral"; label: string } {
  switch (status) {
    case "ok":
      return { tone: "success", label: "Connected" };
    case "error":
      return { tone: "danger", label: "Error" };
    case "disabled":
      return { tone: "neutral", label: "Disabled" };
    default:
      return { tone: "warning", label: "Unverified" };
  }
}

export function MailAccountsSection({ liveAllowed }: { liveAllowed: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: queryKeys.mailAccounts,
    queryFn: listMailAccounts,
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<MailAccount | null>(null);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.mailAccounts });
    void qc.invalidateQueries({ queryKey: queryKeys.systemStatus });
  };

  const verifyMut = useMutation({
    mutationFn: (id: string) => verifyMailAccount(id),
    onSuccess: (r) => {
      refresh();
      if (r.ok) toast.success(r.detail);
      else toast.error(r.detail);
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Verify failed"),
  });

  const testMut = useMutation({
    mutationFn: (id: string) => testSendMailAccount(id),
    onSuccess: (r) => {
      refresh();
      if (r.ok) toast.success("Test email sent to your account inbox");
      else toast.error("Test send failed");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Test send failed"),
  });

  const disableMut = useMutation({
    mutationFn: (id: string) => disableMailAccount(id),
    onSuccess: () => {
      refresh();
      toast.success("Account disabled");
    },
  });

  const enableMut = useMutation({
    mutationFn: (id: string) => enableMailAccount(id),
    onSuccess: () => {
      refresh();
      toast.success("Account enabled");
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteMailAccount(id),
    onSuccess: () => {
      refresh();
      toast.success("Account deleted");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Delete failed"),
  });

  return (
    <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h2 className="text-[14px] font-semibold leading-5">Mail accounts</h2>
          <p className="text-[12px] text-[var(--text-muted)]">
            Gmail SMTP/IMAP with app passwords. Passwords are never shown again.
          </p>
        </div>
        <Button
          type="button"
          className="h-8 bg-[var(--primary)] text-[var(--primary-fg)]"
          onClick={() => {
            setEditing(null);
            setDrawerOpen(true);
          }}
        >
          Add account
        </Button>
      </div>

      {q.isError ? (
        <ErrorBanner
          message={q.error instanceof ApiError ? q.error.message : "Couldn't load mail accounts"}
          actionLabel="Retry"
          onAction={() => q.refetch()}
        />
      ) : null}

      {!q.isLoading && (q.data || []).length === 0 ? (
        <EmptyState
          title="No mail accounts"
          description="Connect a Gmail account with an app password to send real emails safely."
          actionLabel="Add account"
          onAction={() => {
            setEditing(null);
            setDrawerOpen(true);
          }}
        />
      ) : null}

      {(q.data || []).length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-[12px]">Label</TableHead>
              <TableHead className="text-[12px]">Email</TableHead>
              <TableHead className="text-[12px]">Provider</TableHead>
              <TableHead className="text-[12px]">Status</TableHead>
              <TableHead className="text-[12px]">Today</TableHead>
              <TableHead className="text-[12px]">Modes</TableHead>
              <TableHead className="text-[12px]">Last checked</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(q.data || []).map((acc) => {
              const st = statusTone(acc.status);
              const pct = acc.cap > 0 ? (acc.sent_24h / acc.cap) * 100 : 0;
              return (
                <TableRow key={acc.id}>
                  <TableCell className="text-[13px] font-medium">{acc.label}</TableCell>
                  <TableCell>
                    <Mono className="text-[12px]">{acc.email}</Mono>
                  </TableCell>
                  <TableCell className="text-[12px] capitalize">{acc.provider}</TableCell>
                  <TableCell>
                    <StatusBadge tone={st.tone} label={st.label} />
                  </TableCell>
                  <TableCell>
                    <Mono
                      className={cn(
                        "text-[12px]",
                        pct >= 80 && "text-[var(--status-warning)]",
                      )}
                    >
                      {acc.sent_24h} / {acc.cap}
                    </Mono>
                  </TableCell>
                  <TableCell className="text-[11px] text-[var(--text-muted)]">
                    Test · Drafts{acc.live_enabled ? " · Live" : ""}
                  </TableCell>
                  <TableCell>
                    <RelativeTime value={acc.last_verified_at} />
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button type="button" variant="ghost" size="icon" className="size-7">
                          <MoreHorizontal className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => verifyMut.mutate(acc.id)}>
                          Verify
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => testMut.mutate(acc.id)}>
                          Send test email
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => {
                            setEditing(acc);
                            setDrawerOpen(true);
                          }}
                        >
                          Edit
                        </DropdownMenuItem>
                        {acc.status === "disabled" ? (
                          <DropdownMenuItem onClick={() => enableMut.mutate(acc.id)}>
                            Enable
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem onClick={() => disableMut.mutate(acc.id)}>
                            Disable
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuItem
                          className="text-[var(--status-danger)]"
                          onClick={() => {
                            if (window.confirm(`Delete ${acc.email}?`)) deleteMut.mutate(acc.id);
                          }}
                        >
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      ) : null}

      <MailAccountDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        account={editing}
        liveAllowed={liveAllowed}
      />
    </div>
  );
}
