"use client";

import { useQuery } from "@tanstack/react-query";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { Mono } from "@/components/common/Mono";
import { CardSkeleton } from "@/components/common/Skeletons";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, getCompanyResearch } from "@/lib/api";
import { queryKeys } from "@/lib/keys";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignId: string;
  companyId: string | null;
  companyName?: string;
};

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

  const account = q.data?.account;
  const evidence = account?.evidence || [];
  const hasWebEvidence = evidence.some(
    (e: { source_type?: string }) => e.source_type === "web",
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{companyName || q.data?.company?.name || "Company"}</SheetTitle>
          <SheetDescription>
            Research dossier from Crustdata and the company website.
            {hasWebEvidence ? " Includes web crawl evidence." : null}
          </SheetDescription>
        </SheetHeader>
        {q.isLoading ? <CardSkeleton /> : null}
        {q.isError ? (
          <ErrorBanner
            message={
              q.error instanceof ApiError ? q.error.message : "Could not load research"
            }
          />
        ) : null}
        {q.data ? (
          <div className="mt-4 space-y-5 text-[13px]">
            <div>
              <p className="text-[12px] font-medium text-[var(--text-muted)]">Domain</p>
              <Mono>{String(q.data.company?.domain || "—")}</Mono>
              {q.data.company?.fit_score != null ? (
                <p className="mt-1 text-[12px] text-[var(--text-muted)]">
                  Fit score:{" "}
                  <span className="text-[var(--text)]">
                    {Math.round(Number(q.data.company.fit_score) * 100)}%
                  </span>
                </p>
              ) : null}
            </div>
            {account?.story ? (
              <div>
                <p className="mb-1 text-[12px] font-medium">Description</p>
                <p className="whitespace-pre-wrap text-[var(--text)]">{account.story}</p>
              </div>
            ) : null}
            {account?.why_now?.length ? (
              <div>
                <p className="mb-1 text-[12px] font-medium">Why now</p>
                <ul className="list-disc space-y-1 pl-4">
                  {(account.why_now as string[]).map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {evidence.length ? (
              <div>
                <p className="mb-2 text-[12px] font-medium">Evidence</p>
                <ul className="space-y-2">
                  {evidence.map((ev: { id: string; fact: string; source_ref?: string }) => (
                    <li
                      key={ev.id}
                      className="rounded-[6px] border border-[var(--border)] px-3 py-2"
                    >
                      <p>{ev.fact}</p>
                      {ev.source_ref?.startsWith("http") ? (
                        <a
                          href={ev.source_ref}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-1 block truncate text-[11px] text-[var(--accent)]"
                        >
                          {ev.source_ref}
                        </a>
                      ) : (
                        <Mono className="mt-1 text-[11px] text-[var(--text-muted)]">
                          {ev.source_ref || ev.id}
                        </Mono>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {q.data.contacts?.length ? (
              <div>
                <p className="mb-2 text-[12px] font-medium">People found</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-[11px]">Name</TableHead>
                      <TableHead className="text-[11px]">Title</TableHead>
                      <TableHead className="text-[11px]">Email</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {q.data.contacts.map((c) => (
                      <TableRow key={String(c.id)}>
                        <TableCell>{String(c.name || "—")}</TableCell>
                        <TableCell className="text-[12px] text-[var(--text-muted)]">
                          {String(c.title || "—")}
                        </TableCell>
                        <TableCell>
                          <Mono className="text-[11px]">
                            {String(c.email_confidence || "—")}
                          </Mono>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <p className="text-[12px] text-[var(--text-muted)]">
                No contacts found yet for this company.
              </p>
            )}
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
