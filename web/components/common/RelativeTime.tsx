"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

function formatRelative(ts: string | Date | null | undefined): string {
  if (!ts) return "—";
  const date = typeof ts === "string" ? new Date(ts) : ts;
  if (Number.isNaN(date.getTime())) return "—";
  const diffMs = date.getTime() - Date.now();
  const abs = Math.abs(diffMs);
  const mins = Math.round(abs / 60000);
  const hours = Math.round(abs / 3600000);
  const days = Math.round(abs / 86400000);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (mins < 1) return "just now";
  if (mins < 60) return rtf.format(Math.sign(diffMs) * mins, "minute");
  if (hours < 48) return rtf.format(Math.sign(diffMs) * hours, "hour");
  return rtf.format(Math.sign(diffMs) * days, "day");
}

type RelativeTimeProps = {
  value: string | Date | null | undefined;
  className?: string;
};

export function RelativeTime({ value, className }: RelativeTimeProps) {
  const [label, setLabel] = useState(() => formatRelative(value));
  useEffect(() => {
    setLabel(formatRelative(value));
    const id = window.setInterval(() => setLabel(formatRelative(value)), 30000);
    return () => window.clearInterval(id);
  }, [value]);
  const absolute =
    value == null
      ? undefined
      : typeof value === "string"
        ? value
        : value.toISOString();
  return (
    <time
      dateTime={absolute}
      title={absolute}
      className={cn("text-[12px] leading-4 text-[var(--text-subtle)]", className)}
    >
      {label}
    </time>
  );
}
