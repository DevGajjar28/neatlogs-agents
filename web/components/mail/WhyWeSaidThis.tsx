"use client";

import type { DraftClaim } from "@/lib/api";

const EV_RE = /\bev_[0-9a-f]{6,}\b/i;

type Props = {
  body: string;
  claims: DraftClaim[];
};

/** Underline claim phrases; hover shows evidence source. */
export function WhyWeSaidThis({ body, claims }: Props) {
  const usable = (claims || []).filter((c) => (c.text || "").trim());
  if (!body && usable.length === 0) return null;

  const segments = highlightClaims(body || "", usable);

  return (
    <div className="space-y-2 rounded-[8px] border border-[var(--border)] p-3">
      <h4 className="text-[13px] font-semibold">Why we said this</h4>
      <p className="text-[11px] text-[var(--text-subtle)]">
        Underlined phrases are backed by sourced evidence. Hover to see the source.
      </p>
      {body ? (
        <p className="whitespace-pre-wrap text-[13px] leading-5 text-[var(--text)]">
          {segments.map((seg, i) =>
            seg.claim ? (
              <span
                key={i}
                className="cursor-help underline decoration-dotted decoration-[var(--accent)] underline-offset-2"
                title={claimTitle(seg.claim)}
              >
                {seg.text}
              </span>
            ) : (
              <span key={i}>{seg.text}</span>
            ),
          )}
        </p>
      ) : null}
      {usable.length > 0 ? (
        <ul className="space-y-2 border-t border-[var(--border)] pt-2">
          {usable.map((c, i) => (
            <li key={i} className="text-[12px] text-[var(--text-muted)]">
              <span className="font-medium text-[var(--text)]">&ldquo;{c.text}&rdquo;</span>
              {(c.evidence || []).length > 0 ? (
                <ul className="mt-1 space-y-0.5 pl-3">
                  {(c.evidence || []).map((e) => (
                    <li key={e.id}>
                      [{e.source_type || "source"}]
                      {e.observed_at ? ` · ${e.observed_at}` : ""} — {e.fact}
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="block pl-3 text-[var(--text-subtle)]">
                  Evidence ids: {(c.evidence_ids || []).join(", ") || "—"}
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      {EV_RE.test(body || "") ? (
        <p className="text-[12px] font-medium text-[var(--status-danger)]">
          This draft still has internal reference ids. Edit or regenerate it.
        </p>
      ) : null}
    </div>
  );
}

function claimTitle(claim: DraftClaim): string {
  const bits = (claim.evidence || []).map(
    (e) => `${e.source_type || "source"}: ${e.fact}${e.observed_at ? ` (${e.observed_at})` : ""}`,
  );
  return bits.join("\n") || (claim.evidence_ids || []).join(", ") || "Sourced claim";
}

function highlightClaims(
  body: string,
  claims: DraftClaim[],
): { text: string; claim?: DraftClaim }[] {
  type Hit = { start: number; end: number; claim: DraftClaim };
  const hits: Hit[] = [];
  const lower = body.toLowerCase();
  for (const claim of claims) {
    const phrase = claim.text.trim();
    if (!phrase) continue;
    let from = 0;
    const needle = phrase.toLowerCase();
    while (from < lower.length) {
      const idx = lower.indexOf(needle, from);
      if (idx < 0) break;
      hits.push({ start: idx, end: idx + phrase.length, claim });
      from = idx + phrase.length;
    }
  }
  hits.sort((a, b) => a.start - b.start || b.end - a.end);
  const picked: Hit[] = [];
  let cursor = 0;
  for (const h of hits) {
    if (h.start < cursor) continue;
    picked.push(h);
    cursor = h.end;
  }
  const out: { text: string; claim?: DraftClaim }[] = [];
  let at = 0;
  for (const h of picked) {
    if (h.start > at) out.push({ text: body.slice(at, h.start) });
    out.push({ text: body.slice(h.start, h.end), claim: h.claim });
    at = h.end;
  }
  if (at < body.length) out.push({ text: body.slice(at) });
  return out.length ? out : [{ text: body }];
}
