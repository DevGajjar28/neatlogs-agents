"use client";

import { EmptyState } from "@/components/common/EmptyState";
import { PageTitle } from "@/components/shell/page-title";
import { useShell } from "@/components/shell/shell-context";

export default function OutboxPage() {
  const { setNewCampaignOpen } = useShell();
  return (
    <>
      <PageTitle title="Outbox" />
      <EmptyState
        title="No mail sent yet"
        description="Approved emails and follow-ups will appear here after you send from a campaign."
        actionLabel="New campaign"
        onAction={() => setNewCampaignOpen(true)}
      />
    </>
  );
}
