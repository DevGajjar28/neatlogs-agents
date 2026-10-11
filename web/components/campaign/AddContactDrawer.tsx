"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
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
import { ApiError, addManualContact, type LeadRow } from "@/lib/api";
import { queryKeys } from "@/lib/keys";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignId: string;
  lead: LeadRow | null;
  onCreated?: (lead: LeadRow) => void;
};

export function AddContactDrawer({
  open,
  onOpenChange,
  campaignId,
  lead,
  onCreated,
}: Props) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [email, setEmail] = useState("");

  const mut = useMutation({
    mutationFn: () => {
      if (!lead?.company_id) throw new Error("Missing company");
      return addManualContact(campaignId, lead.company_id, {
        name: name.trim(),
        title: title.trim() || "Contact",
        email: email.trim(),
      });
    },
    onSuccess: (row) => {
      void qc.invalidateQueries({ queryKey: queryKeys.campaignLeads(campaignId) });
      void qc.invalidateQueries({ queryKey: queryKeys.campaignPipeline(campaignId) });
      void qc.invalidateQueries({ queryKey: queryKeys.campaign(campaignId) });
      toast.success("Contact added — sequence drafted");
      setName("");
      setTitle("");
      setEmail("");
      onOpenChange(false);
      onCreated?.(row);
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Couldn't add contact"),
  });

  const valid =
    Boolean(lead?.company_id) &&
    name.trim().length > 0 &&
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full gap-0 border-l border-[var(--border)] bg-[var(--surface)] p-0 sm:max-w-[420px]"
        style={{ borderRadius: 0 }}
      >
        <SheetHeader className="border-b border-[var(--border)] px-4 py-4">
          <SheetTitle className="text-[14px] font-semibold">Add contact</SheetTitle>
          <SheetDescription className="text-[12px] text-[var(--text-muted)]">
            {lead?.company_name
              ? `Research found no person at ${lead.company_name}. Add someone and we’ll draft the 3-step sequence.`
              : "Add a contact to draft emails."}
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-3 px-4 py-4">
          <label className="block space-y-1">
            <span className="text-[12px] font-medium">Name</span>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Jane Doe"
              className="h-8 rounded-[6px]"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-[12px] font-medium">Title</span>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="CTO"
              className="h-8 rounded-[6px]"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-[12px] font-medium">Work email</span>
            <Input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="jane@company.com"
              className="h-8 rounded-[6px] font-mono"
            />
          </label>
        </div>
        <SheetFooter className="flex-row justify-end gap-2 border-t border-[var(--border)] px-4 py-3">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!valid || mut.isPending}
            onClick={() => mut.mutate()}
          >
            {mut.isPending ? "Writing…" : "Add & draft emails"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
