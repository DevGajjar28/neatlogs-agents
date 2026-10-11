import { cn } from "@/lib/utils";

export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";

const TONE: Record<StatusTone, { text: string; soft: string }> = {
  success: { text: "var(--status-success)", soft: "var(--status-success-soft)" },
  warning: { text: "var(--status-warning)", soft: "var(--status-warning-soft)" },
  danger: { text: "var(--status-danger)", soft: "var(--status-danger-soft)" },
  info: { text: "var(--status-info)", soft: "var(--status-info-soft)" },
  neutral: { text: "var(--status-neutral)", soft: "var(--status-neutral-soft)" },
};

const STATUS_MAP: Record<string, { tone: StatusTone; label: string }> = {
  completed: { tone: "success", label: "Completed" },
  sent: { tone: "success", label: "Sent" },
  passed: { tone: "success", label: "Passed" },
  verified: { tone: "success", label: "Verified" },
  waiting_icp: { tone: "warning", label: "Waiting for you" },
  waiting_approval: { tone: "warning", label: "Waiting for you" },
  awaiting_approval: { tone: "warning", label: "Waiting for you" },
  guessed: { tone: "warning", label: "Guessed" },
  redrafted: { tone: "warning", label: "Redrafted" },
  recovered: { tone: "warning", label: "Recovered" },
  failed: { tone: "danger", label: "Failed" },
  dropped: { tone: "danger", label: "Dropped" },
  halted: { tone: "danger", label: "Halted" },
  rejected: { tone: "danger", label: "Rejected" },
  crashed: { tone: "danger", label: "Crashed" },
  running: { tone: "info", label: "Running" },
  queued: { tone: "info", label: "Queued" },
  scheduled: { tone: "info", label: "Scheduled" },
  replanned: { tone: "info", label: "Replanned" },
  drafted: { tone: "neutral", label: "Draft" },
  draft: { tone: "neutral", label: "Draft" },
  skipped: { tone: "neutral", label: "Skipped" },
  cancelled: { tone: "neutral", label: "Cancelled" },
  paused: { tone: "neutral", label: "Paused" },
  no_contact: { tone: "warning", label: "Not found" },
  replied: { tone: "success", label: "Replied" },
  opted_out: { tone: "danger", label: "Opted out" },
  bounced: { tone: "danger", label: "Bounced" },
  reply_draft: { tone: "warning", label: "Reply draft waiting" },
  meeting_request: { tone: "info", label: "Meeting request" },
  interested: { tone: "success", label: "Interested" },
  not_interested: { tone: "neutral", label: "Not interested" },
  question: { tone: "info", label: "Question" },
};

type StatusBadgeProps = {
  status?: string;
  tone?: StatusTone;
  label?: string;
  className?: string;
};

export function StatusBadge({ status, tone, label, className }: StatusBadgeProps) {
  const mapped = status ? STATUS_MAP[status.toLowerCase()] : undefined;
  const resolvedTone = tone ?? mapped?.tone ?? "neutral";
  const resolvedLabel =
    label ?? mapped?.label ?? (status ? status.replaceAll("_", " ") : "Unknown");
  const colors = TONE[resolvedTone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[6px] px-2 py-0.5 text-[12px] font-medium leading-4",
        className,
      )}
      style={{ background: colors.soft, color: colors.text }}
    >
      <span
        className="size-1.5 shrink-0 rounded-full"
        style={{ background: colors.text }}
        aria-hidden
      />
      {resolvedLabel}
    </span>
  );
}
