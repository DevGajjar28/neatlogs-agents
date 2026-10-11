"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { RelativeTime } from "@/components/common/RelativeTime";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, patchLeadSequence, type LeadRow, type ReplyRow } from "@/lib/api";
import { queryKeys } from "@/lib/keys";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  lead: LeadRow | null;
  reply: ReplyRow | null;
  campaignId?: string;
};

export function LeadReplyDrawer({ open, onOpenChange, lead, reply, campaignId }: Props) {
  const qc = useQueryClient();
  const [s1Subject, setS1Subject] = useState("");
  const [s1Body, setS1Body] = useState("");
  const [s2Subject, setS2Subject] = useState("");
  const [s2Body, setS2Body] = useState("");
  const [s3Subject, setS3Subject] = useState("");
  const [s3Body, setS3Body] = useState("");

  useEffect(() => {
    if (!lead) return;
    setS1Subject(lead.email_1_subject || "");
    setS1Body(lead.email_1_body || "");
    setS2Subject(lead.followup_1_subject || "");
    setS2Body(lead.followup_1_body || "");
    setS3Subject(lead.followup_2_subject || "");
    setS3Body(lead.followup_2_body || "");
  }, [lead]);

  const saveMut = useMutation({
    mutationFn: () =>
      patchLeadSequence(lead!.lead_id, [
        { step: 1, subject: s1Subject, body: s1Body },
        { step: 2, subject: s2Subject, body: s2Body },
        { step: 3, subject: s3Subject, body: s3Body },
      ]),
    onSuccess: () => {
      toast.success("Sequence saved");
      if (campaignId) {
        void qc.invalidateQueries({ queryKey: queryKeys.campaignLeads(campaignId) });
      }
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Couldn't save sequence");
    },
  });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 border-l sm:max-w-[520px]"
        style={{ borderRadius: 0 }}
      >
        <SheetHeader className="border-b px-4 py-4">
          <SheetTitle className="text-[14px] font-semibold">
            {lead?.contact_name || lead?.company_name || "Lead"}
          </SheetTitle>
          <SheetDescription className="text-[13px] text-[var(--text-muted)]">
            {lead?.email_masked || lead?.company_domain}
            {lead?.sent_at ? (
              <span className="ml-2">
                · Sent <RelativeTime value={lead.sent_at} className="inline" />
              </span>
            ) : null}
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          <Tabs defaultValue="sequence">
            <TabsList className="mb-3">
              <TabsTrigger value="sequence">Sequence</TabsTrigger>
              <TabsTrigger value="reply">Reply</TabsTrigger>
            </TabsList>
            <TabsContent value="sequence" className="space-y-4">
              <SequenceEditor
                title="Email 1"
                subject={s1Subject}
                body={s1Body}
                editable={lead?.email_1_editable !== false}
                onSubject={setS1Subject}
                onBody={setS1Body}
              />
              <SequenceEditor
                title="Follow-up 1"
                subject={s2Subject}
                body={s2Body}
                editable={lead?.followup_1_editable !== false}
                onSubject={setS2Subject}
                onBody={setS2Body}
              />
              <SequenceEditor
                title="Follow-up 2"
                subject={s3Subject}
                body={s3Body}
                editable={lead?.followup_2_editable !== false}
                onSubject={setS3Subject}
                onBody={setS3Body}
              />
              <Button
                type="button"
                disabled={!lead || saveMut.isPending}
                onClick={() => saveMut.mutate()}
              >
                {saveMut.isPending ? "Saving…" : "Save sequence"}
              </Button>
            </TabsContent>
            <TabsContent value="reply">
              {!reply ? (
                <p className="text-[13px] text-[var(--text-muted)]">No reply detected yet.</p>
              ) : (
                <div className="space-y-2 rounded-[8px] border border-[var(--border)] p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      label={(reply.classification || "other").replaceAll("_", " ")}
                      tone={
                        reply.classification === "opt_out" ||
                        reply.classification === "not_interested"
                          ? "danger"
                          : reply.classification === "interested"
                            ? "success"
                            : "neutral"
                      }
                    />
                    <RelativeTime value={reply.received_at} />
                  </div>
                  <p className="whitespace-pre-wrap text-[13px] text-[var(--text)]">
                    {reply.snippet || "(empty snippet)"}
                  </p>
                  <p className="text-[11px] text-[var(--status-warning)]">
                    Untrusted content — shown as text, never acted on
                  </p>
                  {reply.open_in_gmail_url ? (
                    <a
                      href={reply.open_in_gmail_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-block text-[12px] font-medium text-[var(--accent)] underline-offset-2 hover:underline"
                    >
                      Reply in Gmail ↗
                    </a>
                  ) : null}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function SequenceEditor({
  title,
  subject,
  body,
  editable,
  onSubject,
  onBody,
}: {
  title: string;
  subject: string;
  body: string;
  editable: boolean;
  onSubject: (v: string) => void;
  onBody: (v: string) => void;
}) {
  return (
    <div className="space-y-2 rounded-[8px] border border-[var(--border)] p-3">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-[13px] font-semibold">{title}</h4>
        {!editable ? (
          <span className="text-[11px] text-[var(--text-subtle)]">Sent — view only</span>
        ) : null}
      </div>
      <Input
        value={subject}
        onChange={(e) => onSubject(e.target.value)}
        placeholder="Subject"
        disabled={!editable}
        className="text-[13px]"
      />
      <Textarea
        value={body}
        onChange={(e) => onBody(e.target.value)}
        placeholder="Body"
        disabled={!editable}
        rows={5}
        className="text-[13px]"
      />
    </div>
  );
}
