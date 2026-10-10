import { StatusBadge, type StatusTone } from "@/components/common/StatusBadge";

const MAP: Record<string, { tone: StatusTone; label: string }> = {
  verified: { tone: "success", label: "Verified" },
  likely: { tone: "info", label: "Likely" },
  guessed: { tone: "warning", label: "Guessed" },
  none: { tone: "neutral", label: "None" },
};

type ConfidenceBadgeProps = {
  confidence: string | null | undefined;
  className?: string;
};

export function ConfidenceBadge({ confidence, className }: ConfidenceBadgeProps) {
  const key = (confidence || "none").toLowerCase();
  const mapped = MAP[key] ?? { tone: "neutral" as const, label: confidence || "None" };
  return (
    <StatusBadge tone={mapped.tone} label={mapped.label} className={className} />
  );
}
