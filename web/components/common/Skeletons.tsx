import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function TableSkeleton({
  rows = 8,
  cols = 5,
  className,
}: {
  rows?: number;
  cols?: number;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-[8px] border border-[var(--border)] bg-[var(--surface)]",
        className,
      )}
    >
      <div className="flex h-9 items-center gap-3 border-b border-[var(--border)] bg-[var(--surface-muted)] px-3">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={`h-${i}`} className="h-3 flex-1 rounded-[6px]" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div
          key={`r-${r}`}
          className="flex h-10 items-center gap-3 border-b border-[var(--border)] px-3 last:border-b-0"
        >
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={`c-${r}-${c}`} className="h-3 flex-1 rounded-[6px]" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function CardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-[8px] border border-[var(--border)] bg-[var(--surface)] p-4",
        className,
      )}
    >
      <Skeleton className="h-3 w-24 rounded-[6px]" />
      <Skeleton className="h-8 w-32 rounded-[6px]" />
      <Skeleton className="h-3 w-40 rounded-[6px]" />
    </div>
  );
}

export function KpiRowSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}
