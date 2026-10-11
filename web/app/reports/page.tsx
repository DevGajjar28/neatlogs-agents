"use client";

import { EmptyState } from "@/components/common/EmptyState";
import { PageTitle } from "@/components/shell/page-title";
import { useRouter } from "next/navigation";

export default function ReportsPage() {
  const router = useRouter();
  return (
    <>
      <PageTitle title="Reports" />
      <EmptyState
        title="No reports yet"
        description="After a few runs you'll compare cost per lead, verifier pass rate, and recoveries here."
        actionLabel="Open campaigns"
        onAction={() => router.push("/campaigns")}
      />
    </>
  );
}
