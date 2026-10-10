"use client";

import { useEffect } from "react";
import { useShell } from "@/components/shell/shell-context";

export function PageTitle({
  title,
  parent,
}: {
  title: string;
  parent?: { label: string; href: string };
}) {
  const { setBreadcrumbs } = useShell();
  const parentLabel = parent?.label;
  const parentHref = parent?.href;
  useEffect(() => {
    if (parentLabel && parentHref) {
      setBreadcrumbs([
        { label: parentLabel, href: parentHref },
        { label: title },
      ]);
    } else {
      setBreadcrumbs([{ label: title }]);
    }
  }, [title, parentLabel, parentHref, setBreadcrumbs]);
  return null;
}
