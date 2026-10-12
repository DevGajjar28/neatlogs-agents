export function formatCredits(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(n);
}

export function shortModelName(model: string | null | undefined): string {
  if (!model) return "—";
  const parts = model.split(/[./]/).filter(Boolean);
  return parts[parts.length - 1] || model;
}

/** Human-readable model label for product UI (not raw Bedrock ids). */
export function friendlyModelName(model: string | null | undefined): string {
  if (!model) return "Not set";
  const m = model.toLowerCase();
  if (m.includes("opus")) return "Claude Opus";
  if (m.includes("sonnet")) return "Claude Sonnet";
  if (m.includes("haiku")) return "Claude Haiku";
  if (m.includes("gpt-4o")) return "GPT-4o";
  if (m.includes("gpt-4")) return "GPT-4";
  if (m.includes("gpt-3.5") || m.includes("gpt35")) return "GPT-3.5";
  return shortModelName(model);
}
