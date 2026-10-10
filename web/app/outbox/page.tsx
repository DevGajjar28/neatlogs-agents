"use client";

import { useRouter } from "next/navigation";
import { EmptyState } from "@/components/common/EmptyState";
import { PageTitle } from "@/components/shell/page-title";

export default function OutboxPage() {
  const router = useRouter();
  return (
    <>
      <PageTitle title="Outbox" />
      <EmptyState
        title="Outbox is empty"
        description="Sent mail and scheduled follow-ups will show here after a campaign sends through Mailpit."
        actionLabel="Open campaigns"
        onAction={() => router.push("/campaigns")}
      />
    </>
  );
}
