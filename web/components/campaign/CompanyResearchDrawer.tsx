"use client";

import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Building2, ExternalLink, Users } from "lucide-react";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { CardSkeleton } from "@/components/common/Skeletons";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ApiError, getCompanyResearch } from "@/lib/api";
import { queryKeys } from "@/lib/keys";
import { cn } from "@/lib/utils";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignId: string;
  companyId: string | null;
  companyName?: string;
};

/** Strip evidence ids so non-technical users see readable copy. */
function plainText(raw: string): string {
  return String(raw || "")
    .replace(/\s*\[ev_[0-9a-f]+\]/gi, "")
    .replace(/\s*\(ev_[0-9a-f]+\)/gi, "")
    .replace(/\bev_[0-9a-f]+\b/gi, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function formatHeadcount(n: unknown): string | null {
  const num = typeof n === "number" ? n : Number(n);
  if (!Number.isFinite(num) || num <= 0) return null;
  return `About ${num.toLocaleString()} people`;
}

function fitLabel(score: unknown): string | null {
  if (score == null || score === "") return null;
  const n = Number(score);
  if (!Number.isFinite(n)) return null;
  const pct = Math.round(n * 100);
  if (pct >= 80) return `Strong fit · ${pct}%`;
  if (pct >= 55) return `Good fit · ${pct}%`;
  return `Possible fit · ${pct}%`;
}

function emailConfidenceLabel(c: unknown): string {
  switch (String(c || "").toLowerCase()) {
    case "verified":
      return "Confirmed email";
    case "likely":
      return "Likely real email";
    case "guessed":
      return "Estimated email";
    default:
      return "No email yet";
  }
}

function websiteUrl(domain: unknown): string | null {
  const d = String(domain || "").trim();
  if (!d) return null;
  if (d.startsWith("http://") || d.startsWith("https://")) return d;
  return `https://${d}`;
}

function Section({
  title,
  children,
  className,
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-2", className)}>
      <h3 className="text-[13px] font-semibold tracking-tight text-[var(--text)]">{title}</h3>
      {children}
    </section>
  );
}

export function CompanyResearchDrawer({
  open,
  onOpenChange,
  campaignId,
  companyId,
  companyName,
}: Props) {
  const q = useQuery({
    queryKey: queryKeys.companyResearch(campaignId, companyId || ""),
    queryFn: () => getCompanyResearch(campaignId, companyId!),
    enabled: open && Boolean(companyId),
  });

  const company = q.data?.company || {};
  const account = q.data?.account;
  const evidence = account?.evidence || [];
  const contacts = q.data?.contacts || [];
  const name = String(companyName || company.name || "Company");
  const domain = String(company.domain || "");
  const site = websiteUrl(domain);
  const industry = company.industry ? String(company.industry) : null;
  const country = company.country ? String(company.country) : null;
  const headcount = formatHeadcount(company.headcount);
  const fit = fitLabel(company.fit_score);
  const fitReasons = Array.isArray(company.fit_reasons)
    ? (company.fit_reasons as unknown[]).map((r) => plainText(String(r))).filter(Boolean)
    : [];
  const story = plainText(String(account?.story || ""));
  const whyNow = (account?.why_now || [])
    .map((line) => plainText(String(line)))
    .filter(Boolean);
  const webSources = evidence.filter(
    (e) => e.source_type === "web" || String(e.source_ref || "").startsWith("http"),
  );
  const otherSources = evidence.filter((e) => !webSources.includes(e));

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className={cn(
          "w-full gap-0 overflow-y-auto p-0",
          "sm:max-w-2xl data-[side=right]:w-full data-[side=right]:sm:max-w-2xl",
        )}
      >
        <div className="border-b border-[var(--border)] px-6 pb-4 pt-6 pr-14">
          <SheetHeader className="gap-2 text-left">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-[8px] bg-[var(--surface-muted)] text-[var(--text-muted)]">
                <Building2 className="size-5" strokeWidth={1.75} aria-hidden />
              </div>
              <div className="min-w-0 space-y-1">
                <SheetTitle className="text-[18px] leading-6">{name}</SheetTitle>
                <SheetDescription className="text-[13px] leading-5 text-[var(--text-muted)]">
                  Company research from this campaign — who they are, why they fit, and who we
                  found to contact.
                </SheetDescription>
                {site ? (
                  <a
                    href={site}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[13px] text-[var(--accent)] hover:underline"
                  >
                    {domain || site}
                    <ExternalLink className="size-3.5" aria-hidden />
                  </a>
                ) : domain ? (
                  <p className="text-[13px] text-[var(--text-muted)]">{domain}</p>
                ) : null}
              </div>
            </div>
          </SheetHeader>

          {(industry || country || headcount || fit) && (
            <div className="mt-4 flex flex-wrap gap-2">
              {fit ? <Chip>{fit}</Chip> : null}
              {industry ? <Chip>{industry}</Chip> : null}
              {headcount ? <Chip>{headcount}</Chip> : null}
              {country ? <Chip>{country}</Chip> : null}
            </div>
          )}
        </div>

        <div className="space-y-6 px-6 py-5">
          {q.isLoading ? <CardSkeleton /> : null}
          {q.isError ? (
            <ErrorBanner
              message={
                q.error instanceof ApiError ? q.error.message : "Could not load research"
              }
            />
          ) : null}

          {q.data ? (
            <>
              <Section title="What they do">
                {story ? (
                  <p className="text-[14px] leading-6 text-[var(--text)]">{story}</p>
                ) : (
                  <p className="text-[13px] leading-5 text-[var(--text-muted)]">
                    No company description yet. Research may still be running, or this company
                    was added before a full brief was written.
                  </p>
                )}
              </Section>

              {whyNow.length ? (
                <Section title="Why reach out now">
                  <ul className="space-y-2">
                    {whyNow.map((line, i) => (
                      <li
                        key={i}
                        className="rounded-[8px] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-[13px] leading-5"
                      >
                        {line}
                      </li>
                    ))}
                  </ul>
                </Section>
              ) : null}

              {fitReasons.length ? (
                <Section title="Why they match your ideal customer">
                  <ul className="list-disc space-y-1.5 pl-5 text-[13px] leading-5 text-[var(--text)]">
                    {fitReasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </Section>
              ) : null}

              <Section title="People we found">
                {contacts.length ? (
                  <ul className="space-y-3">
                    {contacts.map((c) => {
                      const cName = String(c.name || "Unknown");
                      const title = String(c.title || "—");
                      const profile = c.profile_url ? String(c.profile_url) : null;
                      const conf = emailConfidenceLabel(c.email_confidence);
                      return (
                        <li
                          key={String(c.id)}
                          className="flex gap-3 rounded-[10px] border border-[var(--border)] bg-[var(--surface)] px-3.5 py-3"
                        >
                          <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-[var(--surface-muted)] text-[var(--text-muted)]">
                            <Users className="size-4" strokeWidth={1.75} aria-hidden />
                          </div>
                          <div className="min-w-0 flex-1 space-y-1">
                            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                              <p className="text-[14px] font-medium text-[var(--text)]">{cName}</p>
                              {profile ? (
                                <a
                                  href={profile}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-[12px] text-[var(--accent)] hover:underline"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  Profile
                                </a>
                              ) : null}
                            </div>
                            <p className="text-[13px] text-[var(--text-muted)]">{title}</p>
                            <p className="text-[12px] text-[var(--text-subtle)]">{conf}</p>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="text-[13px] leading-5 text-[var(--text-muted)]">
                    No contact person found yet for this company. Use{" "}
                    <span className="font-medium text-[var(--text)]">Add contact</span> on the
                    leads row if you know who to email.
                  </p>
                )}
              </Section>

              {evidence.length ? (
                <Section title="Where this came from">
                  <p className="mb-2 text-[12px] text-[var(--text-muted)]">
                    Short notes from the company website and business data — useful if you want
                    to double-check.
                  </p>
                  <ul className="space-y-2">
                    {[...webSources, ...otherSources].map((ev) => {
                      const fact = plainText(String(ev.fact || ""));
                      const ref = String(ev.source_ref || "");
                      const isHttp = ref.startsWith("http");
                      const label =
                        ev.source_type === "web" || isHttp
                          ? "Website"
                          : ev.source_type === "crustdata"
                            ? "Company database"
                            : "Source";
                      return (
                        <li
                          key={ev.id}
                          className="rounded-[8px] border border-[var(--border)] px-3 py-2.5"
                        >
                          <p className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-subtle)]">
                            {label}
                          </p>
                          <p className="mt-1 text-[13px] leading-5 text-[var(--text)]">{fact}</p>
                          {isHttp ? (
                            <a
                              href={ref}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="mt-1.5 inline-flex max-w-full items-center gap-1 truncate text-[12px] text-[var(--accent)] hover:underline"
                            >
                              <span className="truncate">{ref}</span>
                              <ExternalLink className="size-3 shrink-0" aria-hidden />
                            </a>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                </Section>
              ) : null}
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-2.5 py-1 text-[12px] text-[var(--text)]">
      {children}
    </span>
  );
}
