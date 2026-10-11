"use client";

import { EmptyState } from "@/components/common/EmptyState";
import { PageTitle } from "@/components/shell/page-title";
import { useShell } from "@/components/shell/shell-context";

export default function ApprovalsPage() {
  const { setNewCampaignOpen } = useShell();
  return (
    <>
      <PageTitle title="Approvals" />
      <EmptyState
        title="Nothing waiting for you"
        description="When drafts need a human OK, they'll show up here. Start a campaign to generate emails worth reviewing."
        actionLabel="New campaign"
        onAction={() => setNewCampaignOpen(true)}
      />
    </>
  );
}
