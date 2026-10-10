import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type EmptyStateProps = {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
};

export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-start gap-3 rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4",
        className,
      )}
    >
      <div className="space-y-1">
        <h2 className="text-[16px] font-semibold leading-6 text-[var(--text)]">{title}</h2>
        <p className="max-w-lg text-[14px] leading-5 text-[var(--text-muted)]">{description}</p>
      </div>
      {actionLabel && onAction ? (
        <Button type="button" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}
