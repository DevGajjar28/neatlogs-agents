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
  max_send_mode?: string;
  sending_paused?: boolean;
  mail_account_count?: number;
  mail_account_error?: boolean;
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
  target_mode?: "discover" | "provided";
  started_at?: string | null;
  trace_url?: string | null;
};

export type ProvidedCompany = {
  name: string;
  domain: string;
  description?: string;
};

export type ParseCompaniesRow = {
  name: string;
  domain: string;
  description: string;
  status: string;
  reason: string;
};

export type ParseCompaniesOut = {
  rows: ParseCompaniesRow[];
  ok_count: number;
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

export type SendMode = "sandbox" | "gmail_drafts" | "gmail_test" | "gmail_live";

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
  mail_account_id?: string | null;
  send_mode?: SendMode;
  live_confirm_email?: string | null;
  target_mode?: "discover" | "provided";
  provided_companies?: ProvidedCompany[];
  template_id?: string | null;
};

export type MailAccount = {
  id: string;
  label: string;
  provider: string;
  email: string;
  display_name: string;
  username: string;
  smtp_host: string;
  smtp_port: number;
  smtp_security: string;
  imap_host: string;
  imap_port: number;
  status: string;
  last_verified_at?: string | null;
  last_error?: string | null;
  daily_cap: number;
  per_domain_daily_cap: number;
  min_gap_seconds: number;
  test_recipients: string[];
  live_enabled: boolean;
  signature: string;
  postal_address: string;
  drafts_folder?: string | null;
  is_default: boolean;
  has_password: boolean;
  sent_24h: number;
  cap: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type MailPreset = {
  id: string;
  label: string;
  provider: string;
  smtp_host: string;
  smtp_port: number;
  smtp_security: string;
  imap_host: string;
  imap_port: number;
};

export type MailPolicies = {
  sending_paused: boolean;
  max_send_mode: string;
  demo_mode: boolean;
  allow_live_sends: boolean;
  values: {
    daily_cap: number;
    per_domain_daily_cap: number;
    min_gap_seconds: number;
    sending_window: Record<string, unknown>;
    default_test_recipients: string[];
  };
  rules: {
    id: string;
    name: string;
    protects: string;
    editable: boolean;
    always_on: boolean;
    value?: unknown;
    hard_max?: number | null;
    hard_min?: number | null;
    blocks_24h: number;
    event?: string | null;
  }[];
};

export type PolicyEvent = {
  id: number;
  ts?: string | null;
  type: string;
  message: string;
  campaign_id?: string | null;
  lead_id?: string | null;
};

export type OutboxRow = {
  id: string;
  lead_id?: string | null;
  step: number;
  subject: string;
  from_label: string;
  from_email?: string | null;
  send_mode: string;
  delivery_status: string;
  ui_status: string;
  message_id?: string | null;
  actual_recipient_masked?: string | null;
  sent_at?: string | null;
  scheduled_at?: string | null;
  open_in_gmail_url?: string | null;
};

export type ReplyRow = {
  id: string;
  lead_id: string;
  received_at?: string | null;
  classification?: string | null;
  snippet?: string | null;
  from_masked?: string | null;
  message_id?: string | null;
  source?: string | null;
  open_in_gmail_url?: string | null;
};

export type EvidenceWhy = {
  id: string;
  fact: string;
  source_type?: string | null;
  source_ref?: string | null;
  observed_at?: string | null;
};

export type DraftClaim = {
  text: string;
  evidence_ids: string[];
  evidence?: EvidenceWhy[];
};

export type LeadRow = {
  lead_id: string;
  company_id?: string | null;
  company_name: string;
  company_domain: string;
  contact_name?: string | null;
  contact_title?: string | null;
  role_kind?: string | null;
  email_masked?: string | null;
  email_confidence?: string;
  fit?: number;
  verifier?: string;
  redraft_count?: number;
  status: string;
  updated_at?: string | null;
  contact_id?: string | null;
  email_1_subject?: string | null;
  email_1_body?: string | null;
  followup_1_subject?: string | null;
  followup_1_body?: string | null;
  followup_2_subject?: string | null;
  followup_2_body?: string | null;
  sent_at?: string | null;
  email_1_editable?: boolean;
  followup_1_editable?: boolean;
  followup_2_editable?: boolean;
  claims?: DraftClaim[];
  has_internal_refs?: boolean;
};

export type PipelineAgent = {
  agent:
    | "planner"
    | "product_researcher"
    | "buyer_finder"
    | "account_researcher"
    | "email_writer_verifier"
    | "sender";
  key: "planner" | "product" | "buyers" | "accounts" | "writer" | "sender";
  label: string;
  status: "idle" | "running" | "waiting" | "done" | "failed";
  detail?: string | null;
  stream?: string | null;
  count_label?: string | null;
  progress?: { done: number; total: number | null } | null;
  items?: string[] | null;
  started_at?: string | null;
  updated_at?: string | null;
};

export type PipelineOut = {
  target_mode: "discover" | "list";
  model?: string | null;
  agents: PipelineAgent[];
};

export type CampaignEvent = {
  id: number;
  ts: string;
  type: string;
  agent: string;
  level: string;
  message: string;
  credits_delta?: number;
  lead_id?: string | null;
  trace_ref?: string | null;
};

export type PendingApprovalItem = {
  contact_id: string;
  lead_id?: string | null;
  name?: string | null;
  title?: string | null;
  email_masked?: string | null;
  email_confidence?: string | null;
  company_name?: string | null;
  subject?: string | null;
  body?: string | null;
  guessed?: boolean;
  has_internal_refs?: boolean;
  claims?: DraftClaim[];
  style_warnings?: string[];
};

export type EmailTemplate = {
  id: string;
  name: string;
  description: string;
  content_md: string;
  is_default: boolean;
  is_system: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type EmailTemplatePreview = {
  preview: boolean;
  template_id: string;
  template_name: string;
  campaign_id: string;
  contact_id: string;
  contact_name?: string | null;
  company_name?: string | null;
  steps: {
    step: number;
    subject: string;
    body: string;
    claims?: DraftClaim[];
    style_warnings?: string[];
  }[];
  verifier?: Record<string, unknown>;
  prompt_contains_system_rules?: boolean;
  crustdata_calls?: number;
};

export type PendingApprovalsOut = {
  campaign_id: string;
  type: string;
  waiting: boolean;
  items: PendingApprovalItem[];
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
      send_mode: "sandbox",
      ...body,
    }),
  });
}

export function listMailAccounts() {
  return api<MailAccount[]>("/mail-accounts");
}

export function listMailPresets() {
  return api<MailPreset[]>("/mail-accounts/presets");
}

export function createMailAccount(body: Record<string, unknown>) {
  return api<MailAccount>("/mail-accounts", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function patchMailAccount(id: string, body: Record<string, unknown>) {
  return api<MailAccount>(`/mail-accounts/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function verifyMailAccount(id: string) {
  return api<{ ok: boolean; detail: string; drafts_folder?: string | null }>(
    `/mail-accounts/${encodeURIComponent(id)}/verify`,
    { method: "POST" },
  );
}

export function testSendMailAccount(id: string) {
  return api<{ ok: boolean; result?: unknown }>(
    `/mail-accounts/${encodeURIComponent(id)}/test-send`,
    { method: "POST" },
  );
}

export function disableMailAccount(id: string) {
  return api<MailAccount>(`/mail-accounts/${encodeURIComponent(id)}/disable`, {
    method: "POST",
  });
}

export function enableMailAccount(id: string) {
  return api<MailAccount>(`/mail-accounts/${encodeURIComponent(id)}/enable`, {
    method: "POST",
  });
}

export function deleteMailAccount(id: string) {
  return api<void>(`/mail-accounts/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function putSendingPaused(sending_paused: boolean) {
  return api<{ sending_paused: boolean }>("/settings/sending", {
    method: "PUT",
    body: JSON.stringify({ sending_paused }),
  });
}

export function getMailPolicies() {
  return api<MailPolicies>("/settings/policies");
}

export function patchMailPolicies(body: Record<string, unknown>) {
  return api<MailPolicies>("/settings/policies", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function getPolicyRuleEvents(rule: string) {
  return api<PolicyEvent[]>(`/settings/policies/${encodeURIComponent(rule)}/events`);
}

export function listOutbox() {
  return api<OutboxRow[]>("/outbox");
}

export function listCampaignReplies(campaignId: string) {
  return api<ReplyRow[]>(`/campaigns/${encodeURIComponent(campaignId)}/replies`);
}

export function listCampaignLeads(campaignId: string) {
  return api<LeadRow[]>(`/campaigns/${encodeURIComponent(campaignId)}/leads`);
}

export function addManualContact(
  campaignId: string,
  companyId: string,
  body: { name: string; title?: string; email: string },
) {
  return api<LeadRow>(
    `/campaigns/${encodeURIComponent(campaignId)}/companies/${encodeURIComponent(companyId)}/contact`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function getCampaignPipeline(campaignId: string) {
  return api<PipelineOut>(`/campaigns/${encodeURIComponent(campaignId)}/pipeline`);
}

export function listCampaignEvents(campaignId: string, after = 0) {
  return api<CampaignEvent[]>(`/campaigns/${encodeURIComponent(campaignId)}/events`, {
    searchParams: { after, limit: 200 },
  });
}

export function getPendingApprovals(campaignId: string) {
  return api<PendingApprovalsOut>(
    `/campaigns/${encodeURIComponent(campaignId)}/pending-approvals`,
  );
}

export function decideEmail(
  campaignId: string,
  contactId: string,
  body: {
    action: "approve" | "reject";
    subject?: string | null;
    body?: string | null;
    confirm_guessed?: boolean;
  },
) {
  return api<{ contact_id: string; action: string; issues: string[] }>(
    `/emails/${encodeURIComponent(contactId)}`,
    {
      method: "POST",
      searchParams: { campaign_id: campaignId },
      body: JSON.stringify(body),
    },
  );
}

export function sendApproved(campaignId: string) {
  return api<{ decision_id: number; pid: number; approvals: number }>(
    `/campaigns/${encodeURIComponent(campaignId)}/send-approved`,
    { method: "POST" },
  );
}

export function patchLeadSequence(
  leadId: string,
  steps: { step: 1 | 2 | 3; subject?: string; body?: string }[],
) {
  return api<{ lead_id: string; contact_id: string; steps: number[] }>(
    `/leads/${encodeURIComponent(leadId)}/sequence`,
    {
      method: "PATCH",
      body: JSON.stringify({ steps }),
    },
  );
}

export function estimateCampaign(
  n: number,
  mode: "replay" | "live",
  target_mode: "discover" | "provided" = "discover",
) {
  return api<EstimateOut>("/estimate", {
    method: "POST",
    body: JSON.stringify({ n, mode, target_mode }),
  });
}

export function parseCompaniesCsv(csv_text: string) {
  return api<ParseCompaniesOut>("/campaigns/parse-companies", {
    method: "POST",
    body: JSON.stringify({ csv_text }),
  });
}

export function listEmailTemplates() {
  return api<EmailTemplate[]>("/email-templates");
}

export function getEmailTemplate(id: string) {
  return api<EmailTemplate>(`/email-templates/${encodeURIComponent(id)}`);
}

export function createEmailTemplate(body: {
  name: string;
  description?: string;
  content_md: string;
}) {
  return api<EmailTemplate>("/email-templates", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateEmailTemplate(
  id: string,
  body: { name?: string; description?: string; content_md?: string },
) {
  return api<EmailTemplate>(`/email-templates/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function deleteEmailTemplate(id: string) {
  return api<void>(`/email-templates/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function duplicateEmailTemplate(id: string) {
  return api<EmailTemplate>(
    `/email-templates/${encodeURIComponent(id)}/duplicate`,
    { method: "POST", body: "{}" },
  );
}

export function setDefaultEmailTemplate(id: string) {
  return api<EmailTemplate>(
    `/email-templates/${encodeURIComponent(id)}/default`,
    { method: "PUT", body: "{}" },
  );
}

export function previewEmailTemplate(
  id: string,
  body: { campaign_id?: string | null; contact_id?: string | null } = {},
) {
  return api<EmailTemplatePreview>(
    `/email-templates/${encodeURIComponent(id)}/preview`,
    { method: "POST", body: JSON.stringify(body) },
  );
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
