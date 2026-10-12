"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  createEmailTemplate,
  deleteEmailTemplate,
  duplicateEmailTemplate,
  listEmailTemplates,
  previewEmailTemplate,
  setDefaultEmailTemplate,
  updateEmailTemplate,
  type EmailTemplate,
  type EmailTemplatePreview,
} from "@/lib/api";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

const HELP =
  'Write how you want emails to sound. Use sections like Voice, Email 1, Follow-up 1, Follow-up 2 and an example. You can use {{first_name}}, {{company}}, {{role}}, {{seller_name}}, {{sender_first_name}} in the template — ReachPilot replaces them with each lead\'s real name and company before send. The opt-out line, evidence checks and sending limits can\'t be turned off.';

type Props = {
  /** When set, open this template read-only (e.g. from New campaign Preview). */
  openId?: string | null;
  onOpenChange?: (open: boolean) => void;
  readOnly?: boolean;
  /** Only render the editor sheet (no list card). */
  sheetOnly?: boolean;
};

export function EmailTemplatesSection({
  openId,
  onOpenChange,
  readOnly = false,
  sheetOnly = false,
}: Props) {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preview, setPreview] = useState<EmailTemplatePreview | null>(null);

  const listQ = useQuery({
    queryKey: queryKeys.emailTemplates,
    queryFn: listEmailTemplates,
  });

  const sheetOpen = Boolean(openId || selectedId);
  const activeId = openId || selectedId;
  const active = useMemo(
    () => (listQ.data || []).find((t) => t.id === activeId) || null,
    [listQ.data, activeId],
  );

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [content, setContent] = useState("");

  const syncForm = (t: EmailTemplate | null) => {
    setName(t?.name || "");
    setDescription(t?.description || "");
    setContent(t?.content_md || "");
    setPreview(null);
  };

  const openTemplate = (t: EmailTemplate) => {
    setSelectedId(t.id);
    syncForm(t);
    onOpenChange?.(true);
  };

  const closeSheet = () => {
    setSelectedId(null);
    setPreview(null);
    onOpenChange?.(false);
  };

  useEffect(() => {
    if (openId && listQ.data) {
      const t = listQ.data.find((x) => x.id === openId) || null;
      syncForm(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId, listQ.data]);

  const saveMut = useMutation({
    mutationFn: async () => {
      if (!active) throw new Error("No template");
      if (active.is_system) throw new Error("System template is read-only");
      return updateEmailTemplate(active.id, {
        name,
        description,
        content_md: content,
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.emailTemplates });
      toast.success("Template saved");
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Couldn't save template"),
  });

  const createMut = useMutation({
    mutationFn: () =>
      createEmailTemplate({
        name: "New style",
        description: "",
        content_md:
          "# Voice\n\nShort and direct.\n\n## Email 1\n\nOpen with one sourced observation.\n",
      }),
    onSuccess: (t) => {
      void qc.invalidateQueries({ queryKey: queryKeys.emailTemplates });
      openTemplate(t);
      toast.success("Template created");
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Couldn't create"),
  });

  const dupMut = useMutation({
    mutationFn: (id: string) => duplicateEmailTemplate(id),
    onSuccess: (t) => {
      void qc.invalidateQueries({ queryKey: queryKeys.emailTemplates });
      openTemplate(t);
      toast.success("Duplicated — customise the copy");
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Couldn't duplicate"),
  });

  const delMut = useMutation({
    mutationFn: (id: string) => deleteEmailTemplate(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.emailTemplates });
      closeSheet();
      toast.success("Template deleted");
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Couldn't delete"),
  });

  const defaultMut = useMutation({
    mutationFn: (id: string) => setDefaultEmailTemplate(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.emailTemplates });
      toast.success("Default updated");
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Couldn't set default"),
  });

  const previewMut = useMutation({
    mutationFn: (id: string) => previewEmailTemplate(id, {}),
    onSuccess: (data) => setPreview(data),
    onError: (e) =>
      toast.error(
        e instanceof ApiError
          ? e.message
          : "Preview needs a campaign with a researched lead",
      ),
  });

  const locked = readOnly || Boolean(active?.is_system);

  const sheet = (
      <Sheet
        open={sheetOpen && Boolean(active)}
        onOpenChange={(o) => {
          if (!o) closeSheet();
        }}
      >
        <SheetContent
          side="right"
          className="w-full gap-0 border-l border-[var(--border)] bg-[var(--surface)] p-0 shadow-[var(--drawer-shadow)] sm:max-w-[560px]"
          style={{ borderRadius: 0 }}
        >
          <SheetHeader className="border-b border-[var(--border)] px-4 py-4">
            <SheetTitle className="text-[14px] font-semibold">
              {active?.name || "Template"}
            </SheetTitle>
            <SheetDescription className="text-[12px] text-[var(--text-muted)]">
              {locked
                ? active?.is_system
                  ? "System template is read-only. Duplicate to customise."
                  : "Preview only"
                : "Edit the style guide markdown."}
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            <p className="text-[12px] leading-5 text-[var(--text-muted)]">{HELP}</p>
            <label className="block space-y-1">
              <span className="text-[12px] font-medium">Name</span>
              <Input
                value={name}
                disabled={locked}
                onChange={(e) => setName(e.target.value)}
                className="h-8 rounded-[6px]"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[12px] font-medium">Description</span>
              <Input
                value={description}
                disabled={locked}
                onChange={(e) => setDescription(e.target.value)}
                className="h-8 rounded-[6px]"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[12px] font-medium">Markdown</span>
              <Textarea
                value={content}
                disabled={locked}
                onChange={(e) => setContent(e.target.value)}
                rows={14}
                className="rounded-[6px] font-mono text-[12px]"
              />
            </label>

            {preview ? (
              <div className="space-y-2 rounded-[6px] border border-[var(--border)] p-3">
                <p className="text-[12px] font-medium">
                  Preview · {preview.contact_name} at {preview.company_name}
                  <span className="ml-1 text-[var(--text-subtle)]">(not stored)</span>
                </p>
                <div className="grid gap-2 md:grid-cols-3">
                  {preview.steps.map((s) => (
                    <div
                      key={s.step}
                      className="rounded-[6px] border border-[var(--border)] p-2"
                    >
                      <p className="mb-1 text-[11px] font-semibold text-[var(--text-muted)]">
                        Step {s.step}
                      </p>
                      <p className="mb-1 text-[12px] font-medium">{s.subject}</p>
                      <p className="whitespace-pre-wrap text-[11px] leading-4 text-[var(--text)]">
                        {s.body}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <SheetFooter className="flex-row flex-wrap justify-end gap-2 border-t border-[var(--border)] px-4 py-3">
            {active && !readOnly ? (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  className="h-8"
                  disabled={dupMut.isPending}
                  onClick={() => dupMut.mutate(active.id)}
                >
                  Duplicate
                </Button>
                {!active.is_default ? (
                  <Button
                    type="button"
                    variant="ghost"
                    className="h-8"
                    disabled={defaultMut.isPending}
                    onClick={() => defaultMut.mutate(active.id)}
                  >
                    Set default
                  </Button>
                ) : null}
                {!active.is_system ? (
                  <Button
                    type="button"
                    variant="ghost"
                    className={cn("h-8 text-[var(--status-danger)]")}
                    disabled={delMut.isPending}
                    onClick={() => delMut.mutate(active.id)}
                  >
                    Delete
                  </Button>
                ) : null}
              </>
            ) : null}
            <Button
              type="button"
              variant="outline"
              className="h-8"
              disabled={!active || previewMut.isPending}
              onClick={() => active && previewMut.mutate(active.id)}
            >
              {previewMut.isPending ? "Previewing…" : "Preview"}
            </Button>
            {!locked ? (
              <Button
                type="button"
                className="h-8"
                disabled={saveMut.isPending}
                onClick={() => saveMut.mutate()}
              >
                Save
              </Button>
            ) : null}
          </SheetFooter>
        </SheetContent>
      </Sheet>
  );

  if (sheetOnly) {
    return sheet;
  }

  return (
    <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-[14px] font-semibold leading-5">Email templates</h2>
          <p className="mt-1 text-[12px] text-[var(--text-muted)]">
            Style guides for voice and structure. Evidence rules stay on.
          </p>
        </div>
        {!readOnly ? (
          <Button
            type="button"
            variant="outline"
            className="h-8"
            disabled={createMut.isPending}
            onClick={() => createMut.mutate()}
          >
            New
          </Button>
        ) : null}
      </div>

      {listQ.isLoading ? (
        <p className="text-[13px] text-[var(--text-muted)]">Loading…</p>
      ) : null}
      {(listQ.data || []).length === 0 ? (
        <p className="text-[13px] text-[var(--text-muted)]">No templates yet.</p>
      ) : (
        <ul className="divide-y divide-[var(--border)]">
          {(listQ.data || []).map((t) => (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => openTemplate(t)}
                className="flex w-full items-start justify-between gap-2 px-1 py-2.5 text-left hover:bg-[var(--surface-muted)]"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="truncate text-[13px] font-medium">{t.name}</span>
                    {t.is_default ? (
                      <span className="rounded-[4px] bg-[var(--accent-soft)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--accent)]">
                        Default
                      </span>
                    ) : null}
                    {t.is_system ? (
                      <span className="rounded-[4px] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] text-[var(--text-subtle)]">
                        System
                      </span>
                    ) : null}
                  </div>
                  <p className="truncate text-[12px] text-[var(--text-muted)]">
                    {t.description || "—"}
                  </p>
                </div>
                <span className="shrink-0 text-[11px] text-[var(--text-subtle)]">
                  {t.updated_at ? String(t.updated_at).slice(0, 10) : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {sheet}
    </div>
  );
}
