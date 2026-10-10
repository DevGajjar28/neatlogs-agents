"use client";

import { useRouter } from "next/navigation";
import { EmptyState } from "@/components/common/EmptyState";
import { PageTitle } from "@/components/shell/page-title";

export default function ReportsPage() {
  const router = useRouter();
  return (
    <>
      <PageTitle title="Reports" />
      <EmptyState
        title="No reports yet"
        description="Run reports and v0 vs v1 comparisons land here in U6. You can still use `python cli.py report <id>` today."
        actionLabel="Open campaigns"
        onAction={() => router.push("/campaigns")}
      />
    </>
  );
}
