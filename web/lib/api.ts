const DEFAULT_BASE = "http://127.0.0.1:8000/api";

export function apiBase(): string {
  return (process.env.NEXT_PUBLIC_API_BASE || DEFAULT_BASE).replace(/\/$/, "");
}

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

type ApiOptions = RequestInit & {
  searchParams?: Record<string, string | number | boolean | undefined | null>;
};

export async function api<T = unknown>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const { searchParams, headers, ...init } = options;
  const url = new URL(
    path.startsWith("http") ? path : `${apiBase()}${path.startsWith("/") ? "" : "/"}${path}`,
  );
  if (searchParams) {
    for (const [key, value] of Object.entries(searchParams)) {
      if (value === undefined || value === null) continue;
      url.searchParams.set(key, String(value));
    }
  }

  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      "Can't reach SignalSDR right now. Start the backend, then try again.",
      0,
      null,
    );
  }

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const detail =
      typeof data === "object" && data && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : res.statusText;
    if (res.status === 402) {
      throw new ApiError(
        "Crustdata is out of credits. Campaign paused. Add credits or lower the number of leads, then Resume.",
        402,
        data,
      );
    }
    throw new ApiError(detail || `Request failed (${res.status})`, res.status, data);
  }

  return data as T;
}

export type SystemStatus = {
  crustdata: {
    status?: string;
    credits?: number | { remaining?: number; balance?: number; [k: string]: unknown };
    live_credits?: unknown;
    saved_at?: string;
    hint?: string;
    detail?: string;
    live_error?: string;
    [k: string]: unknown;
  };
  data_mode: string;
  demo_mode: boolean;
  max_credits: number;
  llm: { strong?: string; fast?: string; provider?: string; [k: string]: string | undefined };
  neatlogs: {
    configured?: boolean;
    traces_url?: string | null;
    endpoint?: string;
    [k: string]: unknown;
  };
};

export function getSystemStatus() {
  return api<SystemStatus>("/system/status");
}

export type CampaignSummary = {
  id: string;
  seller_name: string;
  seller_domain: string;
  status: string;
  current_stage?: string | null;
  stages?: {
    stage: string;
    status: string;
    count_label?: string | null;
  }[];
  leads_found: number;
  leads_target: number;
  credits_spent: number;
  credit_cap: number;
  mode: "replay" | "live";
  started_at?: string | null;
  trace_url?: string | null;
};

export type CampaignDetail = CampaignSummary & {
  budget?: {
    cap: number;
    spent: number;
    estimated_total?: number | null;
    by_step?: { step: string; credits: number }[];
    cache_hit_rate?: number;
    reconciled?: boolean | null;
  };
  recoveries?: Record<string, number>;
  run_facts?: Record<string, unknown>;
  is_alive?: boolean;
  can_resume?: boolean;
  links?: Record<string, string | null>;
};

export type CreateCampaignInput = {
  company_name: string;
  website: string;
  description?: string;
  n?: number;
  mode?: "replay" | "live";
  cap?: number | null;
  chaos?: string;
  kill_after?: string;
  baseline_campaign_id?: string | null;
};

export type EstimateOut = {
  total: number;
  by_step: { step: string; endpoint?: string; credits: number }[];
};

export function listCampaigns() {
  return api<CampaignSummary[]>("/campaigns");
}

export function getCampaign(id: string) {
  return api<CampaignDetail>(`/campaigns/${encodeURIComponent(id)}`);
}

export function createCampaign(body: CreateCampaignInput) {
  return api<CampaignSummary>("/campaigns", {
    method: "POST",
    body: JSON.stringify({
      description: "",
      n: 10,
      mode: "replay",
      chaos: "",
      kill_after: "",
      ...body,
    }),
  });
}

export function estimateCampaign(n: number, mode: "replay" | "live") {
  return api<EstimateOut>("/estimate", {
    method: "POST",
    body: JSON.stringify({ n, mode }),
  });
}

/** Best-effort credit number from /system/status crustdata payload. */
export function extractCredits(status: SystemStatus): number | null {
  const c = status.crustdata;
  if (typeof c.credits === "number") return c.credits;
  if (c.credits && typeof c.credits === "object") {
    const obj = c.credits as Record<string, unknown>;
    for (const key of ["remaining", "balance", "credits", "total"]) {
      if (typeof obj[key] === "number") return obj[key] as number;
    }
  }
  const live = c.live_credits;
  if (typeof live === "number") return live;
  if (live && typeof live === "object") {
    const obj = live as Record<string, unknown>;
    for (const key of ["remaining", "balance", "credits", "total"]) {
      if (typeof obj[key] === "number") return obj[key] as number;
    }
    const account = obj.account;
    if (account && typeof account === "object") {
      const a = account as Record<string, unknown>;
      if (typeof a.credits === "number") return a.credits;
    }
  }
  return null;
}
