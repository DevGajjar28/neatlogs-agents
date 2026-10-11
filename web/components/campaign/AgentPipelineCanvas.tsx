"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
  BaseEdge,
  getBezierPath,
  getSmoothStepPath,
  EdgeLabelRenderer,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Database, Cpu, Mail, UserRound } from "lucide-react";
import {
  AgentIcon,
  AgentPipelineMobile,
  AgentScene,
  PlannerOrbit,
  ProgressBar,
  StatusPill,
  StreamLine,
} from "@/components/campaign/AgentPipeline";
import { PipelineInspector } from "@/components/campaign/PipelineInspector";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  AGENT_ROLES,
  countToolEvents,
  elapsedLabel,
  handoffLabel,
  normalizePipeline,
  prefersReducedMotion,
  toolRecentlyUsed,
  type PipelineAgent,
  type PipelineKey,
  type PipelineOut,
  type PipelineStatus,
} from "@/lib/pipeline";
import type { CampaignEvent, LeadRow } from "@/lib/api";
import { cn } from "@/lib/utils";

/* ── layout positions (compact vertical chain) ── */
const POS = {
  planner: { x: -160, y: 0 },
  product: { x: -140, y: 150 },
  buyers: { x: -140, y: 300 },
  accounts: { x: -140, y: 450 },
  writer: { x: -140, y: 600 },
  gate: { x: -140, y: 750 },
  sender: { x: -140, y: 850 },
  bedrock: { x: -320, y: 20 },
  crustdata: { x: -320, y: 360 },
  gmail: { x: -320, y: 860 },
} as const;

type PosKey = keyof typeof POS;

function nodeCenter(key: string): { x: number; y: number } | null {
  if (!(key in POS)) return null;
  const p = POS[key as PosKey];
  const w = key === "planner" ? 300 : key === "gate" ? 260 : 260;
  const h = key === "planner" ? 110 : key === "gate" ? 56 : 140;
  return { x: p.x + w / 2, y: p.y + h / 2 };
}

const CHAIN: Exclude<PipelineKey, "gate">[] = [
  "planner",
  "product",
  "buyers",
  "accounts",
  "writer",
  "sender",
];

type AgentNodeData = {
  agent: PipelineAgent;
  all: PipelineAgent[];
  listMode: boolean;
  selected: boolean;
  onSelect: (key: PipelineKey) => void;
};

type GateNodeData = {
  writer: PipelineAgent | undefined;
  selected: boolean;
  onSelect: (key: PipelineKey) => void;
};

type ToolNodeData = {
  id: "bedrock" | "crustdata" | "gmail";
  label: string;
  calls: number;
  active: boolean;
};

function AgentFlowNode({ data }: NodeProps & { data: AgentNodeData }) {
  const a = data.agent;
  const time = elapsedLabel(a.started_at, a.updated_at);
  const isPlanner = a.key === "planner";
  return (
    <div
      className={cn(
        "ap-card",
        `status-${a.status}`,
        data.selected && "selected",
        isPlanner ? "w-[300px]" : "w-[260px]",
      )}
      style={{ minHeight: isPlanner ? 110 : 140 }}
    >
      <Handle type="target" position={Position.Top} className="!bg-[var(--ap-border-strong)] !w-2 !h-2 !border-0" />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-[var(--ap-border-strong)] !w-2 !h-2 !border-0"
      />
      <Handle
        id="right"
        type="target"
        position={Position.Right}
        className="!bg-[var(--ap-border-strong)] !w-2 !h-2 !border-0"
      />
      <Handle
        id="left"
        type="target"
        position={Position.Left}
        className="!bg-[var(--ap-border-strong)] !w-2 !h-2 !border-0"
      />
      <Handle
        id="dispatch"
        type="source"
        position={Position.Right}
        className="!bg-[var(--ap-border-strong)] !w-2 !h-2 !border-0"
        style={{ top: "40%" }}
      />
      <button
        type="button"
        className="absolute inset-0 z-0 rounded-[8px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ap-accent)]"
        aria-pressed={data.selected}
        aria-label={`${a.label}: ${a.status}. Show its activity`}
        onClick={() => data.onSelect(a.key)}
      />
      <div className="pointer-events-none relative z-10 space-y-2 p-3">
        <div className="flex items-start gap-2">
          {isPlanner ? (
            <PlannerOrbit agents={data.all} size={56} />
          ) : (
            <span className="flex size-8 items-center justify-center rounded-[6px] bg-[var(--ap-muted)]">
              <AgentIcon agent={a.agent} />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] font-semibold">{a.label}</span>
              <StatusPill status={a.status} />
              {time ? (
                <span className="text-[11px] text-[var(--ap-text-subtle)]">{time}</span>
              ) : null}
            </div>
            {isPlanner ? (
              <p className="mt-0.5 line-clamp-2 text-[11px] text-[var(--ap-text-muted)]">
                {AGENT_ROLES.planner}
              </p>
            ) : null}
          </div>
        </div>
        {isPlanner ? (
          <StreamLine status={a.status} detail={a.detail} stream={a.stream} compact />
        ) : (
          <>
            <AgentScene
              agentKey={a.key}
              status={a.status}
              items={a.items}
              progress={a.progress}
              listMode={data.listMode}
            />
            <StreamLine status={a.status} detail={a.detail} stream={a.stream} compact />
            <div className="flex items-center justify-between gap-2">
              {a.status === "waiting" ? (
                <Link
                  href="/approvals"
                  className="pointer-events-auto text-[11px] font-medium text-[var(--ap-accent)]"
                >
                  Review drafts
                </Link>
              ) : (
                <span className="text-[11px] font-medium text-[var(--ap-text)]">
                  {a.count_label || "\u00a0"}
                </span>
              )}
            </div>
            <ProgressBar status={a.status} progress={a.progress} />
          </>
        )}
      </div>
    </div>
  );
}

function GateFlowNode({ data }: NodeProps & { data: GateNodeData }) {
  const st: PipelineStatus =
    data.writer?.status === "waiting"
      ? "waiting"
      : data.writer?.status === "done"
        ? "done"
        : "idle";
  const label =
    st === "waiting"
      ? "Needs you"
      : st === "done"
        ? `Approved`
        : "Queued";
  return (
    <div
      className={cn("ap-card w-[260px] p-2.5", `status-${st}`, data.selected && "selected")}
      style={{ minHeight: 56 }}
    >
      <Handle type="target" position={Position.Top} className="!bg-[var(--ap-border-strong)] !w-2 !h-2 !border-0" />
      <Handle type="source" position={Position.Bottom} className="!bg-[var(--ap-border-strong)] !w-2 !h-2 !border-0" />
      <Handle id="right" type="target" position={Position.Right} className="!bg-[var(--ap-border-strong)] !w-2 !h-2 !border-0" />
      <button
        type="button"
        className="absolute inset-0 z-0 rounded-[8px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ap-accent)]"
        aria-pressed={data.selected}
        aria-label={`You approve emails: ${label}`}
        onClick={() => data.onSelect("gate")}
      />
      <div className="pointer-events-none relative z-10 flex items-center gap-2">
        <UserRound className="size-4 text-[var(--ap-text)]" strokeWidth={1.75} />
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold">You approve emails</div>
          <div className="mt-1 flex items-center gap-2">
            <StatusPill status={st} />
            {st === "waiting" ? (
              <Link
                href="/approvals"
                className="pointer-events-auto text-[11px] font-medium text-[var(--ap-accent)]"
              >
                Review drafts
              </Link>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function ToolFlowNode({ data }: NodeProps & { data: ToolNodeData }) {
  const Icon = data.id === "crustdata" ? Database : data.id === "gmail" ? Mail : Cpu;
  return (
    <div
      className={cn(
        "flex h-10 w-[132px] items-center gap-1.5 rounded-full border px-3 text-[11px] font-medium",
        data.active
          ? "border-[var(--ap-accent)] bg-[var(--ap-accent-soft)] text-[var(--ap-accent)]"
          : "border-[var(--ap-border)] bg-[var(--ap-surface)] text-[var(--ap-text-muted)]",
      )}
    >
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-[var(--ap-border-strong)] !w-1.5 !h-1.5 !border-0"
      />
      <Icon className="size-3.5 shrink-0" strokeWidth={1.75} />
      <span className="truncate">{data.label}</span>
      {data.calls > 0 ? (
        <span className="ml-auto tabular-nums">{data.calls}</span>
      ) : null}
    </div>
  );
}

function HandoffEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  style,
  markerEnd,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  });
  const mode = (data as { mode?: string; label?: string })?.mode || "idle";
  const label = (data as { label?: string })?.label;
  const reduce = prefersReducedMotion();
  const stroke =
    mode === "flow" || mode === "done" ? "var(--ap-accent)" : "var(--ap-border-strong)";
  const dash = mode === "idle" ? "4 4" : undefined;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          ...style,
          stroke,
          strokeWidth: 1.5,
          strokeDasharray: dash,
        }}
      />
      {mode === "flow" && !reduce ? (
        <g>
          {[0, 1, 2].map((i) => (
            <circle key={i} r="3" fill="var(--ap-accent)">
              <animateMotion
                dur="1.2s"
                begin={`${i * 0.4}s`}
                repeatCount="indefinite"
                path={edgePath}
              />
              <animate
                attributeName="opacity"
                values="0;1;1;0"
                keyTimes="0;0.15;0.85;1"
                dur="1.2s"
                begin={`${i * 0.4}s`}
                repeatCount="indefinite"
              />
            </circle>
          ))}
        </g>
      ) : null}
      {label ? (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan absolute rounded-[4px] border border-[var(--ap-border)] bg-white px-1.5 py-0.5 font-[family-name:var(--ap-mono)] text-[11px] text-[var(--ap-text-muted)]"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

function DispatchEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps) {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    borderRadius: 12,
    offset: 40,
  });
  const active = Boolean((data as { active?: boolean })?.active);
  const pulse = Boolean((data as { pulse?: boolean })?.pulse);
  const reduce = prefersReducedMotion();
  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: active ? "var(--ap-accent)" : "var(--ap-border-strong)",
          strokeWidth: 1,
          strokeDasharray: active ? undefined : "4 4",
        }}
      />
      {pulse && !reduce ? (
        <circle r="4" fill="var(--ap-accent)">
          <animateMotion dur="1.3s" fill="freeze" path={edgePath} />
          <animate
            attributeName="opacity"
            values="0;1;1;0"
            keyTimes="0;0.1;0.85;1"
            dur="1.3s"
            fill="freeze"
          />
        </circle>
      ) : null}
    </>
  );
}

function ToolEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps) {
  const [edgePath] = getBezierPath({ sourceX, sourceY, targetX, targetY });
  const active = Boolean((data as { active?: boolean })?.active);
  return (
    <BaseEdge
      id={id}
      path={edgePath}
      style={{
        stroke: active ? "var(--ap-accent)" : "var(--ap-border-strong)",
        strokeWidth: 1,
        strokeDasharray: "2 3",
        strokeDashoffset: active ? 0 : undefined,
        animation: active ? "ap-dash 1s linear infinite" : undefined,
      }}
    />
  );
}

const nodeTypes = {
  agent: AgentFlowNode,
  gate: GateFlowNode,
  tool: ToolFlowNode,
};

const edgeTypes = {
  handoff: HandoffEdge,
  dispatch: DispatchEdge,
  tool: ToolEdge,
};

function layout(
  agents: PipelineAgent[],
  listMode: boolean,
  selected: PipelineKey | null,
  onSelect: (k: PipelineKey) => void,
  events: CampaignEvent[],
  dispatchPulse: Set<string>,
): { nodes: Node[]; edges: Edge[] } {
  const byKey = new Map(agents.map((a) => [a.key, a]));
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  for (const key of CHAIN) {
    const agent = byKey.get(key);
    if (!agent) continue;
    const p = POS[key];
    nodes.push({
      id: key,
      type: "agent",
      position: { x: p.x, y: p.y },
      data: { agent, all: agents, listMode, selected: selected === key, onSelect },
      draggable: true,
      selectable: true,
    });
  }

  const writer = byKey.get("writer");
  nodes.push({
    id: "gate",
    type: "gate",
    position: { x: POS.gate.x, y: POS.gate.y },
    data: { writer, selected: selected === "gate", onSelect },
    draggable: true,
  });

  const bedrockStats = countToolEvents(events, "bedrock");
  const crustStats = countToolEvents(events, "crustdata");
  const gmailStats = countToolEvents(events, "gmail");

  nodes.push(
    {
      id: "bedrock",
      type: "tool",
      position: POS.bedrock,
      data: {
        id: "bedrock",
        label: "Bedrock",
        calls: bedrockStats.calls,
        active: toolRecentlyUsed(events, "bedrock"),
      },
      draggable: true,
    },
    {
      id: "crustdata",
      type: "tool",
      position: POS.crustdata,
      data: {
        id: "crustdata",
        label: "Crustdata",
        calls: crustStats.calls,
        active: toolRecentlyUsed(events, "crustdata"),
      },
      draggable: true,
    },
    {
      id: "gmail",
      type: "tool",
      position: POS.gmail,
      data: {
        id: "gmail",
        label: "Gmail SMTP",
        calls: gmailStats.calls,
        active: toolRecentlyUsed(events, "gmail"),
      },
      draggable: true,
    },
  );

  // Handoffs: planner→product→…→writer→gate→sender
  const handoffChain: PipelineKey[] = [
    "planner",
    "product",
    "buyers",
    "accounts",
    "writer",
    "gate",
    "sender",
  ];
  for (let i = 0; i < handoffChain.length - 1; i++) {
    const from = handoffChain[i]!;
    const to = handoffChain[i + 1]!;
    const fromAgent =
      from === "gate" ? writer : byKey.get(from as Exclude<PipelineKey, "gate">);
    const toAgent =
      to === "gate" ? writer : byKey.get(to as Exclude<PipelineKey, "gate">);
    let mode: "idle" | "done" | "flow" = "idle";
    if (fromAgent && toAgent) {
      if (
        (fromAgent.status === "done" || fromAgent.status === "running") &&
        toAgent.status === "running"
      ) {
        mode = "flow";
      } else if (fromAgent.status === "done" && toAgent.status !== "idle") {
        mode = "done";
      }
    }
    if (from === "writer" && to === "gate") {
      if (writer?.status === "waiting") mode = "flow";
      else if (writer?.status === "done") mode = "done";
    }
    if (from === "gate" && to === "sender") {
      const sender = byKey.get("sender");
      if (writer?.status === "done" && sender?.status === "running") mode = "flow";
      else if (sender && sender.status !== "idle") mode = "done";
    }
    edges.push({
      id: `h-${from}-${to}`,
      source: from,
      target: to,
      type: "handoff",
      data: {
        mode,
        label: from !== "gate" && from !== "planner" ? handoffLabel(fromAgent) : undefined,
      },
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: mode === "idle" ? "#D4D4D8" : "#2563EB" },
    });
  }

  // Dispatch bus: planner → each sub-agent (right handles)
  for (const key of ["product", "buyers", "accounts", "writer", "sender"] as const) {
    const a = byKey.get(key);
    edges.push({
      id: `d-planner-${key}`,
      source: "planner",
      sourceHandle: "dispatch",
      target: key,
      targetHandle: "right",
      type: "dispatch",
      data: {
        active: a?.status === "running" || a?.status === "waiting",
        pulse: dispatchPulse.has(key),
      },
    });
  }

  // Tool edges
  edges.push(
    {
      id: "t-bedrock-planner",
      source: "bedrock",
      target: "planner",
      targetHandle: "left",
      type: "tool",
      data: { active: toolRecentlyUsed(events, "bedrock") && byKey.get("planner")?.status === "running" },
    },
    {
      id: "t-bedrock-writer",
      source: "bedrock",
      target: "writer",
      targetHandle: "left",
      type: "tool",
      data: {
        active:
          toolRecentlyUsed(events, "bedrock") &&
          (byKey.get("writer")?.status === "running" || byKey.get("product")?.status === "running"),
      },
    },
    {
      id: "t-crust-buyers",
      source: "crustdata",
      target: "buyers",
      targetHandle: "left",
      type: "tool",
      data: {
        active:
          toolRecentlyUsed(events, "crustdata") && byKey.get("buyers")?.status === "running",
      },
    },
    {
      id: "t-crust-accounts",
      source: "crustdata",
      target: "accounts",
      targetHandle: "left",
      type: "tool",
      data: {
        active:
          toolRecentlyUsed(events, "crustdata") && byKey.get("accounts")?.status === "running",
      },
    },
    {
      id: "t-gmail-sender",
      source: "gmail",
      target: "sender",
      targetHandle: "left",
      type: "tool",
      data: {
        active: toolRecentlyUsed(events, "gmail") && byKey.get("sender")?.status === "running",
      },
    },
  );

  return { nodes, edges };
}

function CanvasInner({
  pipeline,
  events,
  leads,
  selectedKey,
  onSelect,
  followLive,
  onFollowLiveChange,
  planFacts,
}: {
  pipeline: PipelineOut;
  events: CampaignEvent[];
  leads: LeadRow[];
  selectedKey: PipelineKey | null;
  onSelect: (k: PipelineKey) => void;
  followLive: boolean;
  onFollowLiveChange: (v: boolean) => void;
  planFacts?: { leads_target?: number; credit_cap?: number; send_mode?: string };
}) {
  const { setCenter, fitView } = useReactFlow();
  const prevStatus = useRef<Record<string, string>>({});
  const [dispatchPulse, setDispatchPulse] = useState<Set<string>>(new Set());
  const listMode = pipeline.target_mode === "list";
  const agents = pipeline.agents;

  const { nodes, edges } = useMemo(
    () => layout(agents, listMode, selectedKey, onSelect, events, dispatchPulse),
    [agents, listMode, selectedKey, onSelect, events, dispatchPulse],
  );

  // Dispatch packet + follow camera when an agent starts
  useEffect(() => {
    const nextPulse = new Set<string>();
    for (const a of agents) {
      const prev = prevStatus.current[a.key];
      if (a.status === "running" || a.status === "waiting") {
        if (prev && prev !== a.status && (a.status === "running" || a.status === "waiting")) {
          if (a.key !== "planner") nextPulse.add(a.key);
        }
        if (!prev && a.status === "running") {
          if (a.key !== "planner") nextPulse.add(a.key);
        }
      }
      prevStatus.current[a.key] = a.status;
    }
    if (nextPulse.size) {
      setDispatchPulse(nextPulse);
      const t = window.setTimeout(() => setDispatchPulse(new Set()), 1400);
      return () => window.clearTimeout(t);
    }
  }, [agents]);

  useEffect(() => {
    if (!followLive) return;
    const focus =
      agents.find((a) => a.status === "running" || a.status === "waiting") ||
      agents.find((a) => a.key === "planner");
    if (!focus?.key) return;
    const c = nodeCenter(focus.key);
    if (!c) return;
    setCenter(c.x, c.y, { zoom: 0.85, duration: 600 });
  }, [agents, followLive, setCenter]);

  // First view: fit the whole chain so progress is visible
  useEffect(() => {
    const t = window.setTimeout(() => {
      fitView({ padding: 0.12, duration: 0, maxZoom: 0.75 });
    }, 50);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onMoveStart = useCallback(() => {
    if (followLive) onFollowLiveChange(false);
  }, [followLive, onFollowLiveChange]);

  const doneCount = agents.filter((a) => a.status === "done").length;
  const header = (
    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-[14px] font-semibold">Agent pipeline</h3>
      <div className="flex flex-wrap items-center gap-3 text-[12px] text-[var(--ap-text-muted)]">
        <span>
          {doneCount}/{agents.length} done
        </span>
        {pipeline.model ? (
          <span className="rounded-[6px] border border-[var(--ap-border)] px-1.5 py-0.5">
            {pipeline.model}
          </span>
        ) : null}
      </div>
    </div>
  );

  return (
    <div className="ap">
      {header}
      <div className="ap-strip" role="list" aria-label="Agent progress">
        {agents.map((a) => (
          <button
            key={a.key}
            type="button"
            role="listitem"
            className={cn("ap-strip-item", `status-${a.status}`)}
            onClick={() => onSelect(a.key)}
          >
            <StatusPill status={a.status} />
            <span className="truncate">{a.label}</span>
            {a.count_label ? (
              <span className="ap-strip-count">{a.count_label}</span>
            ) : null}
          </button>
        ))}
      </div>
      <div className="ap-layout">
        <div className="ap-layout-canvas ap-canvas-desktop">
          <div className="ap-canvas-shell">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              nodesDraggable
              nodesConnectable={false}
              elementsSelectable
              zoomOnScroll={false}
              panOnScroll={false}
              panOnDrag
              minZoom={0.5}
              maxZoom={1.25}
              proOptions={{ hideAttribution: true }}
              onMoveStart={onMoveStart}
              onNodeClick={(_, n) => {
                if (
                  n.id === "gate" ||
                  CHAIN.includes(n.id as Exclude<PipelineKey, "gate">)
                ) {
                  onSelect(n.id as PipelineKey);
                }
              }}
              fitView
              fitViewOptions={{ padding: 0.12, maxZoom: 0.75 }}
            >
              <Background
                variant={BackgroundVariant.Dots}
                gap={16}
                size={1}
                color="#E4E4E7"
              />
              <Controls showInteractive={false} position="bottom-right" />
            </ReactFlow>
            <button
              type="button"
              className="ap-follow-btn"
              aria-pressed={followLive}
              onClick={() => onFollowLiveChange(!followLive)}
            >
              Follow live {followLive ? "✓" : ""}
            </button>
            <button
              type="button"
              className="ap-follow-btn"
              style={{ left: 120 }}
              onClick={() => fitView({ padding: 0.15, duration: 400 })}
            >
              Fit
            </button>
          </div>
        </div>
        <PipelineInspector
          agents={agents}
          selectedKey={selectedKey}
          listMode={listMode}
          events={events}
          leads={leads}
          followLive={followLive}
          onFollowLiveChange={onFollowLiveChange}
          planFacts={planFacts}
        />
      </div>
    </div>
  );
}

export function AgentPipelineCanvas({
  pipeline,
  events = [],
  leads = [],
  onSelectAgent,
  planFacts,
}: {
  pipeline: PipelineOut | undefined;
  events?: CampaignEvent[];
  leads?: LeadRow[];
  onSelectAgent?: (agent: PipelineAgent) => void;
  planFacts?: { leads_target?: number; credit_cap?: number; send_mode?: string };
}) {
  const normalized = useMemo(() => normalizePipeline(pipeline), [pipeline]);
  const agents = normalized?.agents || [];
  const [selectedKey, setSelectedKey] = useState<PipelineKey | null>(null);
  const [followLive, setFollowLive] = useState(true);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 768px)");
    const apply = () => setIsMobile(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  // Default selection: running node
  useEffect(() => {
    if (!followLive) return;
    const run = agents.find((a) => a.status === "running" || a.status === "waiting");
    if (run) setSelectedKey(run.key);
  }, [agents, followLive]);

  const onSelect = useCallback(
    (key: PipelineKey) => {
      setSelectedKey(key);
      const a = agents.find((x) => x.key === key);
      if (a) onSelectAgent?.(a);
      if (typeof window !== "undefined" && window.matchMedia("(max-width: 1279px)").matches) {
        setSheetOpen(true);
      }
    },
    [agents, onSelectAgent],
  );

  if (!normalized || agents.length === 0) {
    return (
      <div className="ap rounded-[8px] border border-[var(--ap-border)] bg-[var(--ap-surface)] p-4">
        <h3 className="text-[14px] font-semibold">Agent pipeline</h3>
        <p className="mt-2 text-[13px] text-[var(--ap-text-muted)]">Waiting for pipeline data…</p>
      </div>
    );
  }

  if (isMobile) {
    return (
      <div className="ap">
        <h3 className="mb-2 text-[14px] font-semibold">Agent pipeline</h3>
        <div className="ap-strip" role="list" aria-label="Agent progress">
          {agents.map((a) => (
            <button
              key={a.key}
              type="button"
              role="listitem"
              className={cn("ap-strip-item", `status-${a.status}`)}
              onClick={() => onSelect(a.key)}
            >
              <StatusPill status={a.status} />
              <span className="truncate">{a.label}</span>
              {a.count_label ? (
                <span className="ap-strip-count">{a.count_label}</span>
              ) : null}
            </button>
          ))}
        </div>
        <AgentPipelineMobile
          agents={agents}
          listMode={normalized.target_mode === "list"}
          selectedKey={selectedKey}
          onSelect={(k) => onSelect(k as PipelineKey)}
        />
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetContent
            side="right"
            className="w-full data-[side=right]:sm:max-w-[560px]"
          >
            <SheetHeader>
              <SheetTitle>Inspector</SheetTitle>
            </SheetHeader>
            <div className="overflow-y-auto px-1 pb-6">
              <PipelineInspector
                agents={agents}
                selectedKey={selectedKey}
                listMode={normalized.target_mode === "list"}
                events={events}
                leads={leads}
                followLive={followLive}
                onFollowLiveChange={setFollowLive}
                planFacts={planFacts}
              />
            </div>
          </SheetContent>
        </Sheet>
      </div>
    );
  }

  return (
    <ReactFlowProvider>
      <CanvasInner
        pipeline={normalized}
        events={events}
        leads={leads}
        selectedKey={selectedKey}
        onSelect={onSelect}
        followLive={followLive}
        onFollowLiveChange={setFollowLive}
        planFacts={planFacts}
      />
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent
          side="right"
          className="w-full data-[side=right]:sm:max-w-[560px] xl:hidden"
        >
          <SheetHeader>
            <SheetTitle>Inspector</SheetTitle>
          </SheetHeader>
          <div className="max-h-[80vh] overflow-y-auto px-1 pb-6">
            <PipelineInspector
              agents={agents}
              selectedKey={selectedKey}
              listMode={normalized.target_mode === "list"}
              events={events}
              leads={leads}
              followLive={followLive}
              onFollowLiveChange={setFollowLive}
              planFacts={planFacts}
            />
          </div>
        </SheetContent>
      </Sheet>
    </ReactFlowProvider>
  );
}
