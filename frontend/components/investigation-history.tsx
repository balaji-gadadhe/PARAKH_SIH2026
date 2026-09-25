"use client";

/**
 * components/investigation-history.tsx — dossier history timeline
 * (D-031 Step 3). Renders GET /api/reports/history/{project_id}: every
 * report raised against this work, newest first, with status + ack
 * timestamps — the "what action has been taken after reporting" trail.
 *
 * Honesty: in-app demo notifications only (no email/SMS, D-029); the trail
 * reflects reports recorded in PARAKH, nothing about offline action taken.
 */

import { useEffect, useState } from "react";
import { api, type ProjectHistoryResponse } from "@/lib/api";

function fmtWhen(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function InvestigationHistory({ projectId }: { projectId: string }) {
  // Open by default (user call) — the action trail is core dossier content;
  // still collapsible via the chevron.
  const [open, setOpen] = useState(true);
  const [data, setData] = useState<ProjectHistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Lazy: fetch on first expand — zero cost for the common no-history path.
  // `loading` is derived (open && no data && no error) to keep the effect
  // free of synchronous setState (react-hooks/set-state-in-effect).
  const loading = open && !data && !error;

  useEffect(() => {
    if (!open || data || error) return;
    let alive = true;
    api
      .projectHistory(projectId)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });
    return () => {
      alive = false;
    };
  }, [open, data, error, projectId]);

  return (
    <section id="history" className="panel scroll-mt-20 overflow-hidden !rounded-2xl">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full cursor-pointer select-none items-center justify-between p-6 font-display text-lg font-bold text-stone-900 transition-colors hover:bg-stone-50/60"
        aria-expanded={open}
      >
        <div className="flex items-center gap-3">
          <svg
            className={`h-5 w-5 transform text-primary transition-transform ${open ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden
          >
            <path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
          </svg>
          <span>Investigation history — reports &amp; action</span>
          {data && data.total_reports > 0 && (
            <span className="rounded-full border border-brd bg-surface-2 px-2.5 py-0.5 text-xs font-semibold text-muted">
              {data.total_reports} report{data.total_reports === 1 ? "" : "s"}
              {data.new_reports > 0 && (
                <span className="ml-1.5 font-bold text-critical">{data.new_reports} new</span>
              )}
            </span>
          )}
        </div>
        <span className="rounded border border-stone-200 bg-stone-100 px-2.5 py-1 text-xs font-medium text-stone-500">
          {open ? "Click to Collapse" : "Click to Expand"}
        </span>
      </button>

      {open && (
        <div className="border-t border-brd p-6 pt-4">
          {loading && <p className="text-sm text-muted">Loading history…</p>}
          {error && <p className="text-sm text-critical">History unavailable — {error}</p>}

          {data && data.events.length === 0 && (
            <p className="text-sm text-muted">
              No reports recorded for this work yet — once an authority files
              one, the report → acknowledge trail will appear here.
            </p>
          )}

          {data && data.events.length > 0 && (
            <ol className="relative space-y-0 border-l-2 border-brd pl-5">
              {data.events.map((e) => (
                <li key={e.id} className="relative pb-5 last:pb-0">
                  {/* Timeline dot — red while NEW, green once acknowledged */}
                  <span
                    className={`absolute -left-[27px] top-1 h-3.5 w-3.5 rounded-full border-2 border-surface ${e.status === "NEW" ? "bg-critical" : "bg-low"
                      }`}
                    aria-hidden
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${e.status === "NEW"
                          ? "bg-critical-bg text-critical"
                          : "bg-surface-2 text-muted"
                        }`}
                    >
                      {e.status === "NEW" ? "New — awaiting review" : "Acknowledged"}
                    </span>
                    <span className="text-xs font-semibold text-foreground">
                      {e.reported_by_role}
                    </span>
                    <span className="text-xs text-muted">
                      → {e.target_role} · {fmtWhen(e.created_at)}
                    </span>
                    {e.has_snapshot && (
                      <span
                        className="rounded border border-brd px-1.5 py-0.5 text-[9px] font-semibold text-muted"
                        title="An analysis snapshot was attached to this report"
                      >
                        📄 snapshot
                      </span>
                    )}
                  </div>
                  {e.comment && (
                    <p className="mt-1.5 rounded-lg bg-surface-2 px-3 py-2 text-xs italic text-muted">
                      &ldquo;{e.comment}&rdquo;
                    </p>
                  )}
                  {e.status === "ACKNOWLEDGED" && e.acknowledged_at && (
                    <p className="mt-1 text-[11px] text-muted">
                      ✓ Reviewed by {e.target_role} on {fmtWhen(e.acknowledged_at)}
                    </p>
                  )}
                </li>
              ))}
            </ol>
          )}

          <p className="mt-4 border-t border-brd pt-3 text-[11px] leading-relaxed text-faint">
            In-app demo trail — records reports and acknowledgements made inside
            PARAKH; no email/SMS is sent and offline action is not tracked.
          </p>
        </div>
      )}
    </section>
  );
}
