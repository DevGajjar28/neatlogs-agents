"use client";

import { useRouter } from "next/navigation";
import { EmptyState } from "@/components/common/EmptyState";
import { PageTitle } from "@/components/shell/page-title";
import { useShell } from "@/components/shell/shell-context";

export default function CampaignsPage() {
  const router = useRouter();
  const { setCommandOpen } = useShell();
  return (
    <>
      <PageTitle title="Campaigns" />
      <EmptyState
        title="No campaigns yet"
        description="Start a replay or live run from New campaign. The API must be running at localhost:8000."
        actionLabel="New campaign"
        onAction={() => setCommandOpen(true)}
      />
      <p className="mt-4 text-[12px] text-[var(--text-subtle)]">
        Full campaigns list lands in U3.{" "}
        <button
          type="button"
          className="text-[var(--accent)] underline-offset-2 hover:underline"
          onClick={() => router.push("/settings")}
        >
          Check system status
        </button>
      </p>
    </>
  );
}
