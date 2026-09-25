"use client";

/**
 * components/public-voice.tsx — "What the public says" dossier section
 * (D-032 Step 5; restyled to the Session-18 dossier design language).
 * The citizen-signal counterpart to the authority-facing Investigation
 * History: PSI score, combined concern bars (upvote reasons + report
 * criteria tallied together, with the honest split), public satisfaction,
 * and recent citizen reports — all labeled demo/unverified.
 *
 * Honesty (D-032): PSI is a participation signal, NOT a detection engine and
 * NOT part of the risk score; citizen reports are never auto-promoted to
 * verified; seed rows are labeled synthetic.
 */

import { useEffect, useState, type ReactNode } from "react";
import {
  citizenApi,
  CITIZEN_CRITERIA,
  type CitizenPsiResponse,
  type CitizenReportItem,
} from "@/lib/citizen-api";

const REASON_LABELS: Record<string, string> = Object.fromEntries(
  CITIZEN_CRITERIA.map((c) => [c.key, c.label])
);

const PSI_LABEL_STYLE: Record<string, string> = {
  NO_SIGNAL: "border-stone-200 bg-stone-50 text-stone-500",
  LOW: "border-low/40 bg-low/10 text-low",
  MODERATE: "border-accent/40 bg-accent/10 text-accent-dark",
  HIGH: "border-high/40 bg-high/10 text-high",
};

function satisfactionWord(avg: number): { word: string; cls: string } {
  if (avg <= 1.5) return { word: "very dissatisfied", cls: "text-high" };
  if (avg <= 2.5) return { word: "dissatisfied", cls: "text-accent-dark" };
  if (avg <= 3.5) return { word: "mixed", cls: "text-accent-dark" };
  if (avg <= 4.5) return { word: "satisfied", cls: "text-low" };
  return { word: "very satisfied", cls: "text-low" };
}

function fmtWhen(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Small stat cell inside the PSI hero strip. */
function HeroMetric({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-lg bg-white px-3 py-2.5 ring-1 ring-stone-100">
      <p className="text-[10px] font-bold uppercase tracking-wide text-stone-400">{label}</p>
      <div className="mt-1">{children}</div>
    </div>
  );
}

export function PublicVoice({
  projectId,
}: {
  projectId: string;
}) {
  // Open by default — the public signal is core dossier content (user call);
  // the chevron still collapses it for a focused print/review.
  const [open, setOpen] = useState(true);
  const [psi, setPsi] = useState<CitizenPsiResponse | null>(null);
  const [reports, setReports] = useState<CitizenReportItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Lazy: fetch on first expand — zero cost for the no-signal path.
  // `loading` is derived to keep the effect free of sync setState.
  const loading = open && !psi && !error;

  useEffect(() => {
    if (!open || psi || error) return;
    let alive = true;
    Promise.all([
      citizenApi.psi(projectId),
      citizenApi.listReports({ project_id: projectId, limit: 5 }),
    ])
      .then(([p, r]) => {
        if (!alive) return;
        setPsi(p);
        setReports(r.items);
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [open, psi, error, projectId]);

  const totalSignals = psi ? psi.upvote_count + psi.report_count : 0;
  const reportShare =
    psi && totalSignals > 0 ? (psi.report_count / totalSignals) * 100 : 0;
  const maxReason = psi
    ? Math.max(1, ...psi.reasons_breakdown.map((r) => r.count))
    : 1;
  const sat = psi?.satisfaction_avg != null ? satisfactionWord(psi.satisfaction_avg) : null;

  return (
    <section id="public-voice" className="panel scroll-mt-20 overflow-hidden !rounded-2xl">
      {/* Collapsible header — mirrors Investigation history / About this assessment */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full cursor-pointer select-none items-center justify-between p-6 font-display text-lg font-bold text-stone-900 transition-colors hover:bg-stone-50/60"
        aria-expanded={open}
      >
        <div className="flex flex-wrap items-center gap-3">
          <svg
            className={`h-5 w-5 transform text-primary transition-transform ${open ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden
          >
            <path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
          </svg>
          <span>What the public says</span>
          {psi && totalSignals > 0 ? (
            <span className="rounded-full border border-brd bg-surface-2 px-2.5 py-0.5 text-xs font-semibold text-muted">
              {totalSignals} signal{totalSignals === 1 ? "" : "s"} · PSI {psi.psi_score}
            </span>
          ) : (
            <span className="rounded-full border border-accent/40 bg-accent/10 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-accent-dark">
              citizen signal
            </span>
          )}
        </div>
        <span className="rounded border border-stone-200 bg-stone-100 px-2.5 py-1 text-xs font-medium text-stone-500">
          {open ? "Click to Collapse" : "Click to Expand"}
        </span>
      </button>

      {open && (
        <div className="border-t border-brd p-6 pt-4">
          {loading && <p className="text-sm text-muted">Loading public signal…</p>}
          {error && (
            <p className="text-sm text-critical">
              Could not load the citizen signal ({error}) — the risk analysis above is
              unaffected.
            </p>
          )}

          {psi && (
            <div className="space-y-5">
              {/* ── PSI hero strip: score + key public metrics ── */}
              <div className="rounded-xl border border-stone-200 bg-stone-50/60 p-4">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                  <div className="flex items-center gap-4 sm:min-w-[220px]">
                    <div className="flex items-baseline gap-1">
                      <span className="font-display text-5xl font-bold leading-none text-stone-900">
                        {psi.psi_score}
                      </span>
                      <span className="text-sm text-stone-400">/100</span>
                    </div>
                    <div className="space-y-1.5">
                      <span
                        className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${PSI_LABEL_STYLE[psi.label] ?? PSI_LABEL_STYLE.NO_SIGNAL}`}
                      >
                        {psi.label.replace("_", " ")}
                      </span>
                      <p className="text-[11px] leading-snug text-stone-500">
                        Public Satisfaction Indicator — a sentiment signal, not a
                        detection engine.
                      </p>
                    </div>
                  </div>
                  <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-3">
                    <HeroMetric label="Public activity">
                      <p className="text-xl font-bold text-stone-900">{totalSignals}</p>
                      <p className="text-[10px] text-stone-400">upvotes + reports</p>
                    </HeroMetric>
                    <HeroMetric label="Citizens engaged">
                      <p className="text-xl font-bold text-stone-900">{psi.distinct_citizens}</p>
                      <p className="text-[10px] text-stone-400">distinct participants</p>
                    </HeroMetric>
                    <HeroMetric label="Public satisfaction">
                      {psi.satisfaction_avg != null && sat ? (
                        <>
                          <p className={`text-xl font-bold ${sat.cls}`}>
                            {psi.satisfaction_avg.toFixed(1)}
                            <span className="text-sm font-semibold text-stone-400">/5</span>
                          </p>
                          <p className="text-[10px] text-stone-500">
                            {sat.word} · {psi.satisfaction_count} rating
                            {psi.satisfaction_count === 1 ? "" : "s"}
                          </p>
                        </>
                      ) : (
                        <>
                          <p className="text-xl font-bold text-stone-300">—</p>
                          <p className="text-[10px] text-stone-400">not rated yet</p>
                        </>
                      )}
                    </HeroMetric>
                  </div>
                </div>

                {/* Signal mix — honest split: reports carry evidence, upvotes echo */}
                {totalSignals > 0 && (
                  <div className="mt-3 border-t border-stone-200 pt-3">
                    <div
                      className="flex h-2 overflow-hidden rounded-full bg-stone-200"
                      title={`Signal mix: ${psi.upvote_count} upvotes · ${psi.report_count} citizen reports`}
                    >
                      <div className="bg-accent" style={{ width: `${100 - reportShare}%` }} />
                      <div className="bg-rose-500" style={{ width: `${reportShare}%` }} />
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-stone-500">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
                        {psi.upvote_count} upvote{psi.upvote_count === 1 ? "" : "s"} — echoes of
                        concern
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-rose-500" aria-hidden />
                        {psi.report_count} citizen report{psi.report_count === 1 ? "" : "s"} —
                        evidence-bearing
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {totalSignals === 0 ? (
                <p className="text-sm text-muted">
                  No public signals recorded for this work yet — no citizen has upvoted a
                  concern or filed a report.
                </p>
              ) : (
                <div className="grid gap-5 lg:grid-cols-2">
                  {/* ── Combined concern bars (two-tone: reports vs upvotes) ── */}
                  <div className="rounded-xl border border-stone-200 bg-white p-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-stone-100 pb-2.5">
                      <h3 className="font-display text-base font-bold text-stone-900">
                        What concerns them
                      </h3>
                      <span className="text-[10px] text-stone-400">
                        reports + upvote reasons · one vocabulary
                      </span>
                    </div>
                    <div className="mt-3 space-y-3">
                      {psi.reasons_breakdown.map((r) => (
                        <div
                          key={r.reason}
                          className="grid grid-cols-[6.5rem_1fr_auto] items-center gap-2.5"
                        >
                          <span className="truncate text-xs font-semibold text-stone-700">
                            {REASON_LABELS[r.reason] ?? r.reason}
                          </span>
                          <div
                            className="flex h-2.5 overflow-hidden rounded-full bg-stone-100"
                            title={`${REASON_LABELS[r.reason] ?? r.reason}: ${r.count} signals — ${r.report_count} reports, ${r.upvote_count} upvotes`}
                          >
                            <div
                              className="h-full bg-accent"
                              style={{ width: `${(r.report_count / maxReason) * 100}%` }}
                            />
                            <div
                              className="h-full bg-accent/40"
                              style={{ width: `${(r.upvote_count / maxReason) * 100}%` }}
                            />
                          </div>
                          <div className="w-24 text-right">
                            <span className="font-mono text-xs font-bold text-accent-dark">
                              ×{r.count}
                            </span>
                            <span className="block text-[10px] leading-tight text-stone-400">
                              {r.report_count} report{r.report_count === 1 ? "" : "s"} ·{" "}
                              {r.upvote_count} upvote{r.upvote_count === 1 ? "" : "s"}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                    <p className="mt-3 border-t border-stone-100 pt-2 text-[10px] leading-relaxed text-stone-400">
                      Solid = citizen reports (evidence-bearing) · lighter = upvote reasons
                      (echoes). Both use the same concern tags.
                    </p>
                  </div>

                  {/* ── Recent citizen reports ── */}
                  <div className="rounded-xl border border-stone-200 bg-white p-4">
                    <div className="flex items-baseline justify-between gap-2 border-b border-stone-100 pb-2.5">
                      <h3 className="font-display text-base font-bold text-stone-900">
                        Recent citizen reports
                      </h3>
                      {reports && reports.length > 0 && (
                        <span className="text-[10px] text-stone-400">
                          {reports.length} shown
                        </span>
                      )}
                    </div>
                    {reports && reports.length > 0 ? (
                      <ul className="divide-y divide-stone-100">
                        {reports.map((rep) => (
                          <li key={rep.id} className="space-y-1.5 py-2.5 first:pt-2.5">
                            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                              <span className="font-mono text-xs font-bold text-stone-700">
                                {rep.masked_id}
                              </span>
                              <span className="text-[10px] text-stone-400">
                                {fmtWhen(rep.created_at)}
                              </span>
                              <span className="ml-auto rounded-full border border-stone-300 bg-white px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-stone-500">
                                unverified
                              </span>
                            </div>
                            <div className="flex flex-wrap items-center gap-1.5">
                              {rep.criteria.map((c) => (
                                <span
                                  key={c}
                                  className="rounded-full border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-[9px] font-bold text-accent-dark"
                                >
                                  {c}
                                </span>
                              ))}
                              {rep.satisfaction != null && (
                                <span className="rounded-full border border-stone-200 bg-stone-50 px-1.5 py-0.5 text-[9px] font-semibold text-stone-600">
                                  ⭐ {rep.satisfaction}/5
                                </span>
                              )}
                              {rep.has_image && (
                                <span className="rounded-full border border-stone-200 bg-stone-50 px-1.5 py-0.5 text-[9px] font-semibold text-stone-600">
                                  📷 photo
                                </span>
                              )}
                              {rep.location_sanity === "PLAUSIBLE" && (
                                <span className="rounded-full border border-low/30 bg-low/10 px-1.5 py-0.5 text-[9px] font-semibold text-low">
                                  📍 location plausible
                                </span>
                              )}
                              {rep.location_sanity === "FAR_FROM_CLAIMED_STATE" && (
                                <span className="rounded-full border border-high/30 bg-high/10 px-1.5 py-0.5 text-[9px] font-semibold text-high">
                                  ⚠️ location far from the work&apos;s state
                                </span>
                              )}
                              {rep.is_seed && (
                                <span className="rounded-full border border-stone-200 bg-stone-100 px-1.5 py-0.5 text-[9px] font-semibold text-stone-500">
                                  synthetic seed
                                </span>
                              )}
                            </div>
                            {rep.comment && (
                              <p className="line-clamp-2 text-xs italic leading-relaxed text-stone-600">
                                &ldquo;{rep.comment}&rdquo;
                              </p>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="py-4 text-sm text-muted">
                        No citizen reports on this work yet — concern upvotes above may still
                        exist.
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Honesty footer — mirrors the PSI endpoint's own disclaimers */}
              <p className="border-t border-stone-100 pt-3 text-[11px] leading-relaxed text-faint">
                {psi.disclaimer} Citizen participation is context for investigation, not
                evidence.
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
