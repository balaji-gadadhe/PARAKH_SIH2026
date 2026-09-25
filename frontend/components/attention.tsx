"use client";

/**
 * components/attention.tsx - "Needs Your Attention" card grid.
 * Shared by the national and role-scoped overview tabs.
 * Risk language per card reference §7: indicators requiring investigation.
 *
 * Links carry the viewer's role/scope (?role=&mp=&state=) so the dossier's
 * back link and Report modal return to the right dashboard (D-029 flow).
 */

import Link from "next/link";
import { formatINR, type ProjectSummary } from "@/lib/api";
import { TierBadge, EmptyState } from "@/components/ui";

/** Composite "80673|MP|PC|State" -> "80673" (matches Works/Alerts tables). */
function shortId(id: string): string {
  return id.split("|")[0] ?? id;
}

export function AttentionGrid({
  items,
  emptyHint,
  scopeParams,
}: {
  items: ProjectSummary[];
  emptyHint?: string;
  /** Viewer role/scope — appended to Investigate links when present. */
  scopeParams?: Record<string, string>;
}) {
  if (items.length === 0) {
    return (
      <EmptyState
        message="No critical works in this scope"
        hint={emptyHint ?? "Try the Works tab for the full registry"}
      />
    );
  }

  // Role always travels to the dossier — an absent role means a public
  // read-only viewer there, so never strip it (the Ministry role included).
  const scopeQuery = scopeParams
    ? new URLSearchParams(
        Object.entries(scopeParams).filter(([, v]) => v)
      ).toString()
    : "";

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {items.map((w) => (
        <Link
          key={w.project_id}
          href={`/investigation/${encodeURIComponent(w.project_id)}${
            scopeQuery ? `?${scopeQuery}` : ""
          }`}
          className="panel block p-5 transition-shadow hover:shadow-[var(--shadow-raised)]"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-bold text-primary">{shortId(w.project_id)}</span>
            <TierBadge tier={w.risk_category} small />
          </div>
          <p className="mt-2 line-clamp-2 min-h-[2.5rem] text-sm text-foreground">
            {w.work_description ?? "Work description not recorded"}
          </p>
          <p className="mt-1 truncate text-xs text-muted">
            {w.mp_name} · {w.state} · {w.constituency}
          </p>
          <div className="mt-3 flex items-center justify-between border-t border-brd pt-3 text-xs">
            <span className="text-muted">
              {formatINR(w.recommended_amount)} recommended
            </span>
            <span className="font-extrabold text-critical">
              {w.risk_score_display}/100
            </span>
          </div>
        </Link>
      ))}
    </div>
  );
}
