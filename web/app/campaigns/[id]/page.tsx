"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ActivityPanel } from "@/components/campaign/ActivityPanel";
import { AddContactDrawer } from "@/components/campaign/AddContactDrawer";
import { CompanyResearchDrawer } from "@/components/campaign/CompanyResearchDrawer";
import { AgentPipelineCanvas } from "@/components/campaign/AgentPipelineCanvas";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { Mono } from "@/components/common/Mono";
import { RelativeTime } from "@/components/common/RelativeTime";
import { StatusBadge } from "@/components/common/StatusBadge";
import { CardSkeleton } from "@/components/common/Skeletons";
import { LeadReplyDrawer } from "@/components/mail/LeadReplyDrawer";
import { PageTitle } from "@/components/shell/page-title";
import { Button } from "@/components/ui/button";
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
  getCampaign,
  getCampaignPipeline,
  listCampaignEvents,
  listCampaignLeads,
  listCampaignReplies,
  type LeadRow,
  type PipelineAgent,
} from "@/lib/api";
import { formatCredits } from "@/lib/format";
import { queryKeys } from "@/lib/keys";

function truncate(s: string | null | undefined, n = 36): string {
  if (!s) return "—";
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

export default function CampaignRunPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [selectedLead, setSelectedLead] = useState<LeadRow | null>(null);
  const [researchCompany, setResearchCompany] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [addContactLead, setAddContactLead] = useState<LeadRow | null>(null);
  const [activityOpen, setActivityOpen] = useState(false);
  const [activityAgent, setActivityAgent] = useState<PipelineAgent | null>(null);

  const q = useQuery({
    queryKey: queryKeys.campaign(id),
    queryFn: () => getCampaign(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (
        status &&
        ["completed", "halted", "failed"].includes(status) &&
        !query.state.data?.is_alive
      ) {
        return false;
      }
      return 3_000;
    },
  });

  const live =
    Boolean(q.data?.is_alive) ||
    ["running", "waiting_approval", "queued"].includes(q.data?.status || "");

  const pipelineQ = useQuery({
    queryKey: queryKeys.campaignPipeline(id),
    queryFn: () => getCampaignPipeline(id),
    refetchInterval: live ? 2_000 : false,
  });

  const eventsQ = useQuery({
    queryKey: queryKeys.campaignEvents(id),
    queryFn: () => listCampaignEvents(id),
    refetchInterval: live || activityOpen ? 3_000 : 15_000,
  });

  const leadsQ = useQuery({
    queryKey: queryKeys.campaignLeads(id),
    queryFn: () => listCampaignLeads(id),
    refetchInterval: 5_000,
  });

  const repliesQ = useQuery({
    queryKey: queryKeys.campaignReplies(id),
    queryFn: () => listCampaignReplies(id),
    refetchInterval: 10_000,
  });

  const replies = repliesQ.data;
  const replyByLead = useMemo(() => {
    const map = new Map<string, NonNullable<typeof replies>[number]>();
    for (const r of replies || []) {
      if (!map.has(r.lead_id)) map.set(r.lead_id, r);
    }
    return map;
  }, [replies]);

  const title = q.data?.seller_name || id;
  const selectedReply = selectedLead
    ? replyByLead.get(selectedLead.lead_id) || null
    : null;
  const sendMode = String(q.data?.run_facts?.send_mode || "sandbox");
  const mailLabel = q.data?.run_facts?.mail_account_label
    ? String(q.data.run_facts.mail_account_label)
    : null;
  const autopilot = q.data?.run_facts?.autopilot !== false;

  return (
    <>
      <PageTitle title={title} parent={{ label: "Campaigns", href: "/campaigns" }} />
      {q.isLoading ? <CardSkeleton /> : null}
      {q.isError ? (
        <ErrorBanner
          message={
            q.error instanceof ApiError
              ? q.error.message
              : "Couldn't load this campaign."
          }
          actionLabel="Retry"
          onAction={() => q.refetch()}
        />
      ) : null}
      {q.data ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="truncate text-[16px] font-semibold">{q.data.seller_name}</h2>
                {q.data.target_mode === "provided" ||
                q.data.run_facts?.target_mode === "provided" ? (
                  <span className="rounded-[6px] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--text)]">
                    Your list
                  </span>
                ) : null}
              </div>
              <Mono className="text-[12px] text-[var(--text-muted)]">{q.data.seller_domain}</Mono>
            </div>
            <StatusBadge status={q.data.status} />
            {q.data.is_alive ? (
              <span className="inline-flex items-center gap-1.5 text-[12px] text-[var(--status-info)]">
                <span className="size-1.5 animate-pipeline-pulse rounded-full bg-[var(--status-info)]" />
                Running
              </span>
            ) : null}
          </div>

          <AgentPipelineCanvas
            pipeline={pipelineQ.data}
            events={eventsQ.data || []}
            leads={leadsQ.data || []}
            planFacts={{
              leads_target: q.data.leads_target,
              credit_cap: q.data.credit_cap,
              send_mode: sendMode,
            }}
            onSelectAgent={(agent) => {
              setActivityAgent(agent);
              setActivityOpen(true);
            }}
          />

          <div className="grid gap-4 md:grid-cols-4">
            <Stat label="Leads" value={`${q.data.leads_found} / ${q.data.leads_target}`} />
            <Stat
              label="Credits"
              value={`${formatCredits(q.data.credits_spent)} / ${formatCredits(q.data.credit_cap)}`}
            />
            <Stat label="Data mode" value={q.data.mode} />
            <Stat
              label="Send"
              value={
                sendMode === "sandbox"
                  ? "Sandbox"
                  : `${sendMode.replace("gmail_", "")}${mailLabel ? ` · ${mailLabel}` : ""}`
              }
            />
          </div>
          {autopilot ? (
            <p className="rounded-[8px] border border-[var(--status-info)] bg-[var(--status-info-soft)] px-3 py-2 text-[12px] text-[var(--text)]">
              Autopilot is on — verified emails send without manual approval. Pause all
              sending anytime in Settings.
            </p>
          ) : null}
          {sendMode === "gmail_test" ? (
            <p className="rounded-[8px] border border-[var(--status-warning)] bg-[var(--status-warning-soft)] px-3 py-2 text-[12px] text-[var(--text)]">
              Gmail test mode: mail only goes to your test-recipient allowlist. Contact
              addresses not on that list are rewritten to your first allowlisted inbox
              (often your own Gmail). Use <span className="font-medium">Gmail live</span>{" "}
              to send to real prospect addresses.
            </p>
          ) : null}
          {q.data.run_facts?.template_name ? (
            <p className="text-[12px] text-[var(--text-muted)]">
              Email style:{" "}
              <span className="font-medium text-[var(--text)]">
                {String(q.data.run_facts.template_name)}
              </span>
            </p>
          ) : null}

          <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)]">
            <div className="border-b border-[var(--border)] px-4 py-3">
              <h3 className="text-[14px] font-semibold">Leads</h3>
              <p className="text-[12px] text-[var(--text-muted)]">
                Click a company name for research. Open a row to edit the email sequence. If
                research finds no person, use Add contact.
              </p>
            </div>
            {(leadsQ.data || []).length === 0 ? (
              <p className="px-4 py-6 text-[13px] text-[var(--text-muted)]">
                No leads yet for this run.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-[12px]">Contact</TableHead>
                      <TableHead className="text-[12px]">Company</TableHead>
                      <TableHead className="text-[12px]">Email</TableHead>
                      <TableHead className="text-[12px]">Email 1</TableHead>
                      <TableHead className="text-[12px]">Follow-up 1</TableHead>
                      <TableHead className="text-[12px]">Follow-up 2</TableHead>
                      <TableHead className="text-[12px]">Sent</TableHead>
                      <TableHead className="text-[12px]">Status</TableHead>
                      <TableHead className="text-[12px]"> </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(leadsQ.data || []).map((lead) => {
                      const noContact = lead.status === "no_contact";
                      return (
                        <TableRow
                          key={lead.lead_id}
                          className={noContact ? undefined : "cursor-pointer"}
                          onClick={() => {
                            if (!noContact) setSelectedLead(lead);
                          }}
                        >
                          <TableCell className="text-[13px]">
                            {noContact ? (
                              <span className="text-[var(--status-warning)]">Not found</span>
                            ) : (
                              lead.contact_name || "—"
                            )}
                          </TableCell>
                          <TableCell
                            className="text-[13px] text-[var(--accent)] underline-offset-2 hover:underline"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (lead.company_id) {
                                setResearchCompany({
                                  id: lead.company_id,
                                  name: lead.company_name,
                                });
                              }
                            }}
                          >
                            {lead.company_name}
                          </TableCell>
                          <TableCell>
                            <Mono className="text-[12px]">{lead.email_masked || "—"}</Mono>
                          </TableCell>
                          <TableCell className="max-w-[140px] truncate text-[12px] text-[var(--text-muted)]">
                            {truncate(lead.email_1_subject)}
                          </TableCell>
                          <TableCell className="max-w-[140px] truncate text-[12px] text-[var(--text-muted)]">
                            {truncate(lead.followup_1_subject)}
                          </TableCell>
                          <TableCell className="max-w-[140px] truncate text-[12px] text-[var(--text-muted)]">
                            {truncate(lead.followup_2_subject)}
                          </TableCell>
                          <TableCell className="text-[12px]">
                            {lead.sent_at ? (
                              <RelativeTime value={lead.sent_at} />
                            ) : (
                              "—"
                            )}
                          </TableCell>
                          <TableCell>
                            {lead.reply_draft_status === "pending" ? (
                              <StatusBadge status="reply_draft" />
                            ) : (
                              <StatusBadge status={lead.status} />
                            )}
                          </TableCell>
                          <TableCell onClick={(e) => e.stopPropagation()}>
                            {noContact && lead.company_id ? (
                              <Button
                                type="button"
                                variant="outline"
                                className="h-7 px-2 text-[11px]"
                                onClick={() => setAddContactLead(lead)}
                              >
                                + Add contact
                              </Button>
                            ) : null}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </div>
      ) : null}

      <CompanyResearchDrawer
        open={Boolean(researchCompany)}
        onOpenChange={(o) => !o && setResearchCompany(null)}
        campaignId={id}
        companyId={researchCompany?.id ?? null}
        companyName={researchCompany?.name}
      />

      <LeadReplyDrawer
        open={Boolean(selectedLead)}
        onOpenChange={(o) => !o && setSelectedLead(null)}
        lead={selectedLead}
        reply={selectedReply}
        campaignId={id}
      />
      <AddContactDrawer
        open={Boolean(addContactLead)}
        onOpenChange={(o) => !o && setAddContactLead(null)}
        campaignId={id}
        lead={addContactLead}
        onCreated={(row) => setSelectedLead(row)}
      />

      <ActivityPanel
        open={activityOpen}
        onOpenChange={setActivityOpen}
        events={eventsQ.data || []}
        agentFilter={activityAgent?.agent}
        agentLabel={activityAgent?.label}
      />
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="text-[12px] text-[var(--text-subtle)]">{label}</div>
      <Mono className="mt-1 text-[16px] font-semibold">{value}</Mono>
    </div>
  );
}
