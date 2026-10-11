/** Shared types + helpers for the agent pipeline canvas (14 §4). */

export type PipelineStatus = "idle" | "running" | "waiting" | "done" | "failed";

export type PipelineKey =
  | "planner"
  | "product"
  | "buyers"
  | "accounts"
  | "writer"
  | "sender"
  | "gate";

export type PipelineAgentKey =
  | "planner"
  | "product_researcher"
  | "buyer_finder"
  | "account_researcher"
  | "email_writer_verifier"
  | "sender";

export type PipelineProgress = { done: number; total: number | null };

export type PipelineAgent = {
  agent: PipelineAgentKey;
  key: Exclude<PipelineKey, "gate">;
  label: string;
  status: PipelineStatus;
  detail?: string | null;
  stream?: string | null;
  count_label?: string | null;
  progress?: PipelineProgress | null;
  items?: string[] | null;
  started_at?: string | null;
  updated_at?: string | null;
};

export type PipelineOut = {
  target_mode: "discover" | "list";
  model?: string | null;
  agents: PipelineAgent[];
};

export const AGENT_ROLES: Record<Exclude<PipelineKey, "gate">, string> = {
  planner: "Splits the campaign into jobs and hands each one to a sub-agent.",
  product: "Reads the seller site and extracts product facts.",
  buyers: "Finds lookalike companies (or matches your list).",
  accounts: "Researches each company and finds a buyer contact.",
  writer: "Writes a 3-step sequence and verifies claims.",
  sender: "Delivers approved step-1 emails and schedules follow-ups.",
};

export const KEY_TO_AGENT: Record<Exclude<PipelineKey, "gate">, PipelineAgentKey> = {
  planner: "planner",
  product: "product_researcher",
  buyers: "buyer_finder",
  accounts: "account_researcher",
  writer: "email_writer_verifier",
  sender: "sender",
};

export const AGENT_TO_KEY: Record<PipelineAgentKey, Exclude<PipelineKey, "gate">> = {
  planner: "planner",
  product_researcher: "product",
  buyer_finder: "buyers",
  account_researcher: "accounts",
  email_writer_verifier: "writer",
  sender: "sender",
};

/** Ensure every agent has a canvas key (older API responses may omit it). */
export function normalizePipeline(raw: PipelineOut | undefined | null): PipelineOut | undefined {
  if (!raw?.agents?.length) return raw ?? undefined;
  return {
    target_mode: raw.target_mode === "list" ? "list" : "discover",
    model: raw.model ?? "Amazon Bedrock",
    agents: raw.agents.map((a) => ({
      ...a,
      key: a.key || AGENT_TO_KEY[a.agent] || "planner",
    })),
  };
}

export function elapsedLabel(startedAt?: string | null, updatedAt?: string | null): string {
  const start = startedAt ? Date.parse(startedAt) : NaN;
  if (!Number.isFinite(start)) return "";
  const end = updatedAt ? Date.parse(updatedAt) : Date.now();
  const sec = Math.max(0, Math.floor((end - start) / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function handoffLabel(upstream?: PipelineAgent | null): string | undefined {
  if (!upstream?.count_label) return undefined;
  const c = upstream.count_label;
  if (/\d/.test(c)) return c.length > 18 ? c.slice(0, 16) + "…" : c;
  return undefined;
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Tool edge active if matching event in last 5s. */
export function toolRecentlyUsed(
  events: { type: string; ts: string; agent?: string }[],
  tool: "bedrock" | "crustdata" | "gmail",
  now = Date.now(),
): boolean {
  const match = (t: string) => {
    const x = t.toLowerCase();
    if (tool === "crustdata") {
      return (
        x.includes("crustdata") ||
        x.startsWith("buyer.search") ||
        x.startsWith("buyers.import") ||
        x.startsWith("account.") ||
        x.startsWith("fallback.contact") ||
        x.startsWith("person")
      );
    }
    if (tool === "gmail") {
      return x.startsWith("mail.") || x.startsWith("send.");
    }
    // bedrock / llm
    return (
      x.includes("llm") ||
      x.startsWith("product.") ||
      x.startsWith("email.") ||
      x.startsWith("verify.") ||
      x.startsWith("verifier.") ||
      x.startsWith("plan.")
    );
  };
  for (const ev of events) {
    if (!match(ev.type)) continue;
    const ts = Date.parse(ev.ts);
    if (Number.isFinite(ts) && now - ts <= 5000) return true;
  }
  return false;
}

export function countToolEvents(
  events: { type: string; credits_delta?: number }[],
  tool: "bedrock" | "crustdata" | "gmail",
): { calls: number; credits: number } {
  let calls = 0;
  let credits = 0;
  for (const ev of events) {
    const x = ev.type.toLowerCase();
    let hit = false;
    if (tool === "crustdata") {
      hit =
        x.includes("crustdata") ||
        x.startsWith("buyer.search") ||
        x.startsWith("buyers.import") ||
        x.startsWith("account.") ||
        x.startsWith("fallback.contact");
    } else if (tool === "gmail") {
      hit = x.startsWith("mail.") || x.startsWith("send.");
    } else {
      hit =
        x.includes("llm") ||
        x.startsWith("product.") ||
        x.startsWith("email.") ||
        x.startsWith("verify.") ||
        x.startsWith("verifier.");
    }
    if (hit) {
      calls += 1;
      credits += Number(ev.credits_delta || 0);
    }
  }
  return { calls, credits };
}
