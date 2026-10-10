"use client";

import { EmptyState } from "@/components/common/EmptyState";
import { PageTitle } from "@/components/shell/page-title";
import { useRouter } from "next/navigation";

export default function ApprovalsPage() {
  const router = useRouter();
  return (
    <>
      <PageTitle title="Approvals" />
      <EmptyState
        title="Nothing waiting for approval"
        description="Email drafts that need a human decision will appear here. Until U5, use the Phase 7 approval UI on :8080."
        actionLabel="Open campaigns"
        onAction={() => router.push("/campaigns")}
      />
    </>
  );
}
