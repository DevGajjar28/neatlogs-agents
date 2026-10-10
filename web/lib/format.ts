export function formatCredits(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(n);
}

export function shortModelName(model: string | null | undefined): string {
  if (!model) return "—";
  const parts = model.split(/[./]/).filter(Boolean);
  return parts[parts.length - 1] || model;
}
