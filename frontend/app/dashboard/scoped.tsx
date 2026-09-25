"use client";

/**
 * app/dashboard/scoped.tsx - Role-scoped Overview tabs (Step 5.5).
 * MP: constituency report card from /api/mps/{name}.
 * SNO: state rollup from /api/projects?state, /api/alerts?state, /api/mps?state.
 * DM: same mechanics as MP scope, demo-labeled (no district data exists).
 *
 * Honesty rules: KPIs the backend cannot serve for a scope are omitted, not
 * fabricated (e.g. no per-state funds aggregation -> SNO gets work counts
 * and risk mix, no funds figures).
 */

import { useEffect, useMemo, useState } from "react";
import {
  api,
  formatINR,
  type MpDetail,
  type MpSummary,
  type ProjectSummary,
  type RiskTier,
} from "@/lib/api";
import { TierDonut } from "@/components/charts";
import {
  StatCard,
  TierLegend,
  SectionTitle,
  ScoreGauge,
  ErrorState,
  LoadingState,
} from "@/components/ui";
import { AttentionGrid } from "@/components/attention";

/* ═══ MP-scoped overview (also DM) ════════════════════════════════════ */

export function MpOverview({
  mpName,
  isDm = false,
}: {
  mpName: string;
  isDm?: boolean;
}) {
  const [detail, setDetail] = useState<MpDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .mpDetail(mpName)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [mpName]);

  if (error)
    return <ErrorState message={`Backend unreachable - ${error}`} />;
  if (!detail) return <LoadingState label="Loading constituency report..." />;

  const mp = detail.mp;
  const tierCounts: Partial<Record<RiskTier, number>> = {
    CRITICAL: detail.critical_works,
    HIGH: detail.high_risk_works,
    MEDIUM: detail.medium_risk_works,
    LOW: detail.low_risk_works,
  };

  return (
    <div className="space-y-6">
      {isDm && (
        <div className="rounded-xl border border-brd bg-accent-wash px-4 py-3 text-sm text-accent-dark">
          <strong>Demo scope:</strong> no district-level data exists in the
          dataset — this view shows the works of one MP in the district as a
          proxy (D-012).
        </div>
      )}

      {/* Identity + headline numbers */}
      <section className="panel flex flex-wrap items-center justify-between gap-6 p-6">
        <div className="min-w-0">
          <p className="section-label">
            {isDm ? "District (demo proxy)" : "Constituency"} Report
          </p>
          <h1 className="mt-1 font-display text-2xl font-bold text-primary">
            {mp.mp_name}
          </h1>
          <p className="mt-0.5 text-sm text-muted">
            {mp.constituency} · {mp.state}
            {mp.house ? ` · ${mp.house}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-8">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">
              Average risk
            </div>
            <div className="text-2xl font-extrabold text-primary">
              {detail.average_risk_score ?? "—"}
            </div>
          </div>
          <ScoreGauge score={detail.highest_work_risk ?? 0} size={84} label="highest risk" />
        </div>
      </section>

      {/* KPI tiles */}
      <section className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Total Works" value={(detail.total_works ?? 0).toLocaleString("en-IN")} />
        <StatCard label="Completed" value={(mp.completed_works ?? 0).toLocaleString("en-IN")} sub={mp.completion_rate_pct != null ? `${mp.completion_rate_pct}%` : undefined} />
        <StatCard label="Allocated" value={mp.allocated_amount != null ? formatINR(mp.allocated_amount) : "Not available"} />
        <StatCard label="Utilised" value={mp.total_expenditure != null ? formatINR(mp.total_expenditure) : "Not available"} sub={mp.utilization_pct != null ? `${mp.utilization_pct}% utilization` : undefined} />
        <StatCard label="Pending Payments" value={(mp.pending_payments ?? 0).toLocaleString("en-IN")} />
        <StatCard label="Flagged Works" value={(mp.flagged_works ?? 0).toLocaleString("en-IN")} sub="High + Critical" />
      </section>

      {/* Risk mix + attention */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="panel p-5">
          <SectionTitle>Risk Mix of Works</SectionTitle>
          <TierDonut counts={tierCounts} />
          <div className="mt-3">
            <TierLegend counts={tierCounts} />
          </div>
        </div>
        <div className="panel p-5 lg:col-span-2">
          <SectionTitle>Flagged works needing review</SectionTitle>
          <div className="mt-4">
            <AttentionGrid
              items={(detail.works ?? []).slice(0, 6)}
              emptyHint="No HIGH/CRITICAL works for this MP"
              scopeParams={{ role: isDm ? "dm" : "mp", mp: mpName }}
            />
          </div>
        </div>
      </section>
    </div>
  );
}

/* ═══ SNO state overview ═══════════════════════════════════════════════ */

export function SnoOverview({ state }: { state: string }) {
  const [worksTotal, setWorksTotal] = useState<number | null>(null);
  const [completed, setCompleted] = useState<number | null>(null);
  const [tierCounts, setTierCounts] = useState<Partial<Record<RiskTier, number>> | null>(null);
  const [topMps, setTopMps] = useState<MpSummary[] | null>(null);
  const [attention, setAttention] = useState<ProjectSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const stateParam = useMemo(() => ({ state }), [state]);

  useEffect(() => {
    api
      .listProjects({ ...stateParam, page_size: 1 })
      .then((r) => setWorksTotal(r.total))
      .catch((e) => setError(String(e)));
    api
      .listProjects({ ...stateParam, status: "completed", page_size: 1 })
      .then((r) => setCompleted(r.total))
      .catch(() => {});
    api
      .listAlerts({ ...stateParam, page_size: 1 })
      .then((r) => setTierCounts(r.tier_counts as Partial<Record<RiskTier, number>>))
      .catch(() => {});
    api
      .listMps({ state, sort: "flagged_desc" })
      .then((r) => setTopMps(r.items.slice(0, 6)))
      .catch(() => {});
    api
      .listProjects({ ...stateParam, tier: "CRITICAL", sort: "risk_desc", page_size: 6 })
      .then((r) => setAttention(r.items))
      .catch(() => {});
  }, [stateParam, state]);

  if (error)
    return <ErrorState message={`Backend unreachable - ${error}`} />;

  return (
    <div className="space-y-6">
      <section className="panel flex flex-wrap items-center justify-between gap-4 p-6">
        <div>
          <p className="section-label">State Report</p>
          <h1 className="mt-1 font-display text-2xl font-bold text-primary">{state}</h1>
          <p className="mt-0.5 text-sm text-muted">
            Works and risk indicators across the state&apos;s MPs
          </p>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Works in State" value={worksTotal === null ? "…" : worksTotal.toLocaleString("en-IN")} sub="All sanctioned works" />
        <StatCard label="Completed" value={completed === null ? "…" : completed.toLocaleString("en-IN")} />
        <StatCard
          label="Flagged (High + Critical)"
          value={
            tierCounts
              ? ((tierCounts.HIGH ?? 0) + (tierCounts.CRITICAL ?? 0)).toLocaleString("en-IN")
              : "…"
          }
          sub="Risk indicators"
        />
        <StatCard
          label="MPs Representing"
          value={topMps ? topMps.length.toLocaleString("en-IN") : "…"}
          sub="In live roster"
        />
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="panel p-5">
          <SectionTitle>Risk Tier Distribution (state)</SectionTitle>
          {tierCounts ? (
            <>
              <TierDonut counts={tierCounts} />
              <div className="mt-3">
                <TierLegend counts={tierCounts} />
              </div>
            </>
          ) : (
            <LoadingState label="Loading tiers..." />
          )}
        </div>
        <div className="panel p-5">
          <SectionTitle>Top Flagged MPs in {state}</SectionTitle>
          <ol className="mt-3 divide-y divide-brd">
            {(topMps ?? []).map((m, i) => (
              <li key={m.mp_name} className="flex items-center justify-between py-2.5 text-sm">
                <span className="flex min-w-0 items-center gap-2.5">
                  <span className="w-4 shrink-0 text-xs text-faint">{i + 1}</span>
                  <span className="truncate font-semibold text-foreground">{m.mp_name}</span>
                </span>
                <span className="shrink-0 rounded-full bg-critical-bg px-2.5 py-0.5 text-xs font-bold text-critical">
                  {(m.flagged_works ?? 0).toLocaleString("en-IN")} flagged
                </span>
              </li>
            ))}
          </ol>
        </div>
        <div className="panel p-5">
          <SectionTitle>Scope Notes</SectionTitle>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-xs leading-relaxed text-muted">
            <li>
              Funds KPIs are not shown: the backend serves no per-state
              financial aggregation, and figures are never estimated.
            </li>
            <li>
              Tier counts come from the alerts engine (HIGH/CRITICAL focus);
              MEDIUM/LOW are indicative groupings.
            </li>
          </ul>
        </div>
      </section>

      <section className="space-y-3">
        <SectionTitle>Needs Your Attention</SectionTitle>
        <AttentionGrid items={attention} scopeParams={{ role: "sno", state }} />
      </section>
    </div>
  );
}
