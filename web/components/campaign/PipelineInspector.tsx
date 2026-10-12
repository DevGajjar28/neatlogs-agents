"use client";

import Link from "next/link";
import {
  AgentIcon,
  AgentScene,
  PlannerOrbit,
  ProgressBar,
  StatusPill,
  StreamLine,
} from "@/components/campaign/AgentPipeline";
import {
  AGENT_ROLES,
  countToolEvents,
  elapsedLabel,
  type PipelineAgent,
  type PipelineKey,
} from "@/lib/pipeline";
import type { CampaignEvent, LeadRow } from "@/lib/api";
import { Mono } from "@/components/common/Mono";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Checkbox } from "@/components/ui/checkbox";

type Props = {
  agents: PipelineAgent[];
  selectedKey: PipelineKey | null;
  listMode: boolean;
  events: CampaignEvent[];
  leads: LeadRow[];
  followLive: boolean;
  onFollowLiveChange: (v: boolean) => void;
  planFacts?: {
    leads_target?: number;
    credit_cap?: number;
    send_mode?: string;
  };
};

const JOBS: { key: Exclude<PipelineKey, "gate" | "planner">; job: string }[] = [
  { key: "product", job: "Understand the product" },
  { key: "buyers", job: "Find buyers" },
  { key: "accounts", job: "Research accounts" },
  { key: "writer", job: "Write + verify emails" },
  { key: "sender", job: "Send approved mail" },
];

function fmtTime(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString(undefined, { hour12: false });
}

export function PipelineInspector({
  agents,
  selectedKey,
  listMode,
  events,
  leads,
  followLive,
  onFollowLiveChange,
  planFacts,
}: Props) {
  const agent =
    selectedKey === "gate"
      ? agents.find((a) => a.key === "writer")
      : agents.find((a) => a.key === selectedKey) ||
        agents.find((a) => a.status === "running") ||
        agents[0];

  if (!agent) {
    return (
      <div className="ap-inspector ap-inspector-desktop">
        <div className="ap-inspector-body">
          <p className="text-[13px] text-[var(--ap-text-muted)]">Select a node</p>
        </div>
      </div>
    );
  }

  const isGate = selectedKey === "gate";
  const time = elapsedLabel(agent.started_at, agent.updated_at);
  const status = isGate
    ? agent.status === "waiting"
      ? "waiting"
      : agent.status === "done"
        ? "done"
        : "idle"
    : agent.status;

  const agentEvents = events.filter((e) => {
    const a = (e.agent || "").toLowerCase();
    if (isGate) return a.includes("approval") || e.type.startsWith("approval.");
    if (agent.key === "planner") return a === "planner";
    if (agent.key === "product") return a.includes("product");
    if (agent.key === "buyers") return a.includes("buyer");
    if (agent.key === "accounts") return a.includes("account");
    if (agent.key === "writer")
      return a.includes("email") || a.includes("verif") || a.includes("approval");
    if (agent.key === "sender") return a.includes("sender") || a.startsWith("mail") || e.type.startsWith("send.");
    return false;
  });

  const toolsForAgent: ("bedrock" | "crustdata" | "gmail")[] =
    agent.key === "buyers" || agent.key === "accounts"
      ? ["crustdata"]
      : agent.key === "sender"
        ? ["gmail"]
        : agent.key === "product" || agent.key === "writer" || agent.key === "planner"
          ? ["bedrock"]
          : [];

  return (
    <div className="ap ap-inspector ap-inspector-desktop">
      <div className="border-b border-[var(--ap-border)] px-4 py-3">
        <div className="flex items-start gap-2">
          {!isGate ? <AgentIcon agent={agent.agent} /> : null}
          <div className="min-w-0 flex-1">
            <h3 className="text-[14px] font-semibold">
              {isGate ? "You approve emails" : agent.label}
            </h3>
            <p className="text-[12px] text-[var(--ap-text-muted)]">
              {isGate
                ? "Human gate before any mail leaves."
                : AGENT_ROLES[agent.key]}
            </p>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <StatusPill status={status} />
          {time ? <span className="text-[11px] text-[var(--ap-text-subtle)]">{time}</span> : null}
        </div>
      </div>
      <div className="ap-inspector-body">
        {agent.key === "planner" && !isGate ? (
          <div className="flex justify-center">
            <PlannerOrbit agents={agents} size={96} />
          </div>
        ) : !isGate ? (
          <AgentScene
            agentKey={agent.key}
            status={agent.status}
            items={agent.items}
            progress={agent.progress}
            listMode={listMode}
            tall
            inspector
          />
        ) : null}

        <div>
          <h4>Status</h4>
          <StreamLine status={status} detail={agent.detail} stream={agent.stream} />
        </div>

        {toolsForAgent.length > 0 ? (
          <div className="ap-inspector-section">
            <h4>Tools</h4>
            <ul className="space-y-2">
              {toolsForAgent.map((tool) => {
                const stats = countToolEvents(events, tool);
                if (stats.calls === 0) return null;
                const name =
                  tool === "bedrock"
                    ? "Amazon Bedrock"
                    : tool === "crustdata"
                      ? "Crustdata"
                      : "Gmail SMTP";
                return (
                  <li
                    key={tool}
                    className="flex justify-between gap-2 text-[12px] text-[var(--ap-text)]"
                  >
                    <span>{name}</span>
                    <Mono className="text-[11px] text-[var(--ap-text-muted)]">
                      {stats.calls} calls
                      {stats.credits > 0 ? ` · ${stats.credits.toFixed(1)} credits` : ""}
                    </Mono>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}

        <div className="ap-inspector-section">
          <h4>Output</h4>
          <InspectorOutput
            agent={agent}
            isGate={isGate}
            listMode={listMode}
            leads={leads}
            agents={agents}
            planFacts={planFacts}
          />
        </div>

        <div className="ap-inspector-section">
          <h4>Activity</h4>
          {agentEvents.length === 0 ? (
            <p className="text-[12px] text-[var(--ap-text-subtle)]">No events yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {agentEvents.slice(0, 40).map((ev) => (
                <li key={ev.id} className="flex gap-2 text-[12px]">
                  <Mono className="shrink-0 text-[11px] text-[var(--ap-text-subtle)]">
                    {fmtTime(ev.ts)}
                  </Mono>
                  <span className="text-[var(--ap-text-muted)]">{ev.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <label className="mt-auto flex items-center gap-2 text-[12px] text-[var(--ap-text)]">
          <Checkbox
            checked={followLive}
            onCheckedChange={(v) => onFollowLiveChange(v === true)}
          />
          Follow live
        </label>
      </div>
    </div>
  );
}

function InspectorOutput({
  agent,
  isGate,
  listMode,
  leads,
  agents,
  planFacts,
}: {
  agent: PipelineAgent;
  isGate: boolean;
  listMode: boolean;
  leads: LeadRow[];
  agents: PipelineAgent[];
  planFacts?: Props["planFacts"];
}) {
  if (isGate || agent.key === "writer") {
    const drafts = leads.filter((l) =>
      ["awaiting_approval", "drafted", "draft", "waiting_approval"].includes(
        (l.status || "").toLowerCase(),
      ),
    );
    return (
      <div className="space-y-2">
        {agent.count_label ? (
          <p className="text-[12px] font-medium">{agent.count_label}</p>
        ) : null}
        <ul className="space-y-1">
          {drafts.slice(0, 8).map((l) => (
            <li key={l.lead_id} className="flex items-center justify-between gap-2 text-[12px]">
              <span className="truncate">
                {l.contact_name || l.company_name}
              </span>
              <StatusBadge status={l.verifier || l.status} />
            </li>
          ))}
        </ul>
        {(isGate || agent.status === "waiting") && (
          <Link
            href="/approvals"
            className="text-[12px] font-medium text-[var(--ap-accent)] underline-offset-2 hover:underline"
          >
            Open in Approvals
          </Link>
        )}
        {!isGate ? <ProgressBar status={agent.status} progress={agent.progress} /> : null}
      </div>
    );
  }

  if (agent.key === "planner") {
    return (
      <div className="space-y-3">
        <ul className="space-y-1">
          {JOBS.map((j, i) => {
            const owner = agents.find((a) => a.key === j.key);
            const st = owner?.status || "idle";
            const icon =
              st === "done" ? "✓" : st === "running" ? "◐" : st === "waiting" ? "⏸" : st === "failed" ? "✕" : "○";
            return (
              <li
                key={j.key}
                className={
                  st === "running"
                    ? "rounded-[4px] bg-[var(--ap-accent-soft)] px-1.5 py-1 text-[12px]"
                    : "px-1.5 py-1 text-[12px]"
                }
              >
                <span className="mr-1.5">{icon}</span>
                <span className="text-[var(--ap-text-subtle)]">{i + 1}</span> {j.job}
                <span className="ml-1 text-[var(--ap-text-subtle)]">
                  · {owner?.label || j.key}
                </span>
              </li>
            );
          })}
        </ul>
        {planFacts ? (
          <p className="text-[12px] text-[var(--ap-text-muted)]">
            Cap {planFacts.leads_target ?? "—"} leads ·{" "}
            {planFacts.credit_cap != null ? `${planFacts.credit_cap} credits` : "—"} ·{" "}
            {planFacts.send_mode || "sandbox"}
          </p>
        ) : null}
      </div>
    );
  }

  if (agent.key === "product") {
    return (
      <ul className="list-disc space-y-1 pl-4 text-[12px] text-[var(--ap-text-muted)]">
        {(agent.items || []).map((f) => (
          <li key={f}>{f}</li>
        ))}
        {!agent.items?.length ? (
          <li className="list-none pl-0 text-[var(--ap-text-subtle)]">No facts yet.</li>
        ) : null}
      </ul>
    );
  }

  if (agent.key === "buyers") {
    return (
      <div className="space-y-1 text-[12px]">
        <p className="font-medium">{agent.count_label || (listMode ? "List import" : "Company search")}</p>
        <ul className="space-y-1 text-[var(--ap-text-muted)]">
          {(agent.items || []).map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </div>
    );
  }

  if (agent.key === "accounts") {
    const rows = leads.filter((l) => l.contact_name && l.status !== "no_contact");
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[11px]">
          <thead className="text-[var(--ap-text-subtle)]">
            <tr>
              <th className="pb-1 font-medium">Name</th>
              <th className="pb-1 font-medium">Role</th>
              <th className="pb-1 font-medium">Email</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 12).map((l) => (
              <tr key={l.lead_id} className="border-t border-[var(--ap-border)]">
                <td className="py-1 pr-2">{l.contact_name}</td>
                <td className="py-1 pr-2 text-[var(--ap-text-muted)]">{l.contact_title}</td>
                <td className="py-1">
                  <Mono className="text-[10px]">{l.email_masked}</Mono>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length ? (
          <p className="text-[12px] text-[var(--ap-text-subtle)]">No contacts yet.</p>
        ) : null}
      </div>
    );
  }

  if (agent.key === "sender") {
    const sent = leads.filter((l) => (l.status || "").toLowerCase() === "sent" || l.sent_at);
    return (
      <div className="space-y-2">
        <p className="text-[12px] font-medium">{agent.count_label || `${sent.length} sent`}</p>
        <ul className="space-y-1 text-[12px] text-[var(--ap-text-muted)]">
          {sent.slice(0, 8).map((l) => (
            <li key={l.lead_id}>
              {l.contact_name || l.company_name}
              {l.sent_at ? ` · ${new Date(l.sent_at).toLocaleString()}` : ""}
            </li>
          ))}
        </ul>
        <Link
          href="/outbox"
          className="text-[12px] font-medium text-[var(--ap-accent)] underline-offset-2 hover:underline"
        >
          Open Outbox
        </Link>
      </div>
    );
  }

  return <p className="text-[12px] text-[var(--ap-text-subtle)]">—</p>;
}
