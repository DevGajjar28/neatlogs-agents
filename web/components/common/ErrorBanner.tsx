import { AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type ErrorBannerProps = {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
};

export function ErrorBanner({
  message,
  actionLabel,
  onAction,
  className,
}: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-3 rounded-[8px] border border-[var(--status-danger)]/20 bg-[var(--status-danger-soft)] p-3 text-[13px] leading-5 text-[var(--status-danger)]",
        className,
      )}
    >
      <AlertCircle className="mt-0.5 size-4 shrink-0" strokeWidth={1.75} aria-hidden />
      <div className="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-2">
        <p>{message}</p>
        {actionLabel && onAction ? (
          <Button type="button" variant="outline" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
