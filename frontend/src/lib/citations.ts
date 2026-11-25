import type { Citation } from "./types";

const MARKER = /\[(S\d+(?:\s*,\s*S\d+)*)\]/g;

/**
 * Turn backend-validated [S1] / [S1, S2] markers into markdown links (#cite-S1) so they render
 * as clickable citation chips. Markers without a matching citation are dropped defensively
 * (the backend already strips them; this guards against any mismatch).
 */
export function linkifyCitations(answer: string, citations: Citation[]): string {
  const known = new Set(citations.map((c) => c.label));
  return answer.replace(MARKER, (_m, group: string) => {
    const labels = group.split(/\s*,\s*/).filter((l) => known.has(l));
    return labels.map((l) => `[${l}](#cite-${l})`).join(" ");
  });
}

export function citationLabelFromHref(href: string | undefined): string | null {
  const m = href?.match(/^#cite-(S\d+)$/);
  return m ? m[1] : null;
}
