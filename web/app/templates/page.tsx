"use client";

import { EmailTemplatesSection } from "@/components/mail/EmailTemplatesSection";
import { PageTitle } from "@/components/shell/page-title";

export default function TemplatesPage() {
  return (
    <>
      <PageTitle title="Email templates" />
      <p className="mb-4 max-w-2xl text-[13px] leading-5 text-[var(--text-muted)]">
        Styles used when ReachPilot writes outreach. Pick a default for new campaigns, or
        choose one when you start a run. Opt-out lines and evidence checks always stay on.
      </p>
      <EmailTemplatesSection />
    </>
  );
}
