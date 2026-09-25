"use client";

/**
 * app/dashboard/page.tsx - role-aware dashboard.
 * Step 4: real Overview tab for MoSPI (KPIs, donut, states, flagged MPs,
 * needs-attention). MP/SNO/DM scoping and Works/MPs/Alerts tabs arrive in
 * Steps 5-9 (same shell, filtered params).
 *
 * Note: the backend serves no per-state financial aggregation, so there is
 * deliberately NO "spend vs allocated by state" panel - we do not fabricate
 * numbers (honesty policy). It can be added backend-side later.
 */

import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { IndiaMap, MapColourIndex, stateIntensity } from "@/components/india-map";
import {
  api,
  formatINR,
  REPORTS_CHANGED_EVENT,
  type DashboardSummary,
  type ProjectSummary,
  type StateRiskItem,
} from "@/lib/api";
import { DashHeader, Footer, type DashTab } from "@/components/shell";
import { TierDonut } from "@/components/charts";
import { WorksTab } from "@/app/dashboard/works";
import { MpsTab } from "@/app/dashboard/mps";
import { AlertsTab } from "@/app/dashboard/alerts";
import { MpOverview, SnoOverview } from "@/app/dashboard/scoped";
import { AttentionGrid } from "@/components/attention";
import {
  StatCard,
  TierLegend,
  SectionTitle,
  ErrorState,
  LoadingState,
} from "@/components/ui";

const ROLE_LABELS: Record<string, string> = {
  mospi: "MoSPI / Central Ministry",
  mp: "Hon'ble MP",
  sno: "State Nodal Officer",
  dm: "District Magistrate",
}

/** Unread NEW-reports count for the viewer — drives the Alerts-tab badge. */
function useUnreadReportsCount(
  role: string,
  mp: string | null,
  state: string | null
): number {
  // Scoped roles need an identity; without one there is nothing to poll.
  const unscoped = role !== "mospi" && !mp && !state;
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (unscoped) return;
    const params: { role: string; status: string; mp?: string; state?: string } = {
      role,
      status: "NEW",
    };
    if (mp) params.mp = mp;
    if (state) params.state = state;
    let cancelled = false;
    const load = () =>
      api
        .listReports(params)
        .then((r) => {
          if (!cancelled) setCount(r.total);
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 15000); // keep the badge fresh
    const onChange = () => load();
    window.addEventListener(REPORTS_CHANGED_EVENT, onChange);
    return () => {
      cancelled = true;
      clearInterval(t);
      window.removeEventListener(REPORTS_CHANGED_EVENT, onChange);
    };
  }, [role, mp, state, unscoped]);

  return unscoped ? 0 : count;
};

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <DashboardInner />
    </Suspense>
  );
}

function DashboardInner() {
  const params = useSearchParams();
  const router = useRouter();
  const role = params.get("role") ?? "mospi";
  const mp = params.get("mp");
  const state = params.get("state");
  const unreadReports = useUnreadReportsCount(role, mp, state);

  // Deep-linkable active tab: /dashboard?...&tab=alerts survives refresh and
  // can be linked to directly (e.g. "check your alerts inbox" in the flow).
  const tabParam = params.get("tab");
  const tabs: DashTab[] = [
    { key: "overview", label: "Overview" },
    { key: "works", label: "Works" },
    ...(role === "mospi" ? [{ key: "mps", label: "MPs" }] : []),
    { key: "alerts", label: "Alerts", badge: unreadReports },
  ];
  const [tab, setTab] = useState(
    tabs.some((t) => t.key === tabParam) ? (tabParam as string) : "overview"
  );

  // Keep the URL in sync (replaceState — no navigation, refresh-safe).
  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    window.history.replaceState(null, "", url.toString());
  }, [tab]);

  const scopeNote =
    role === "mp"
      ? `Constituency scope - ${mp ?? "unassigned"}`
      : role === "sno"
        ? `State scope - ${state ?? "unassigned"}`
        : role === "dm"
          ? `District scope (demo proxy) - ${mp ?? "unassigned"}`
          : "Central scope";

  const scopeParams = useMemo(() => {
    const p: Record<string, string> = { role };
    if (mp) p.mp = mp;
    if (state) p.state = state;
    return p;
  }, [role, mp, state]);

  return (
    <div className="flex min-h-screen flex-col">
      <DashHeader
        tabs={tabs}
        active={tab}
        onTab={setTab}
        userLabel={ROLE_LABELS[role] ?? role}
        scopeNote={scopeNote}
        bellCount={unreadReports}
        onLogout={() => router.push("/")}
      />

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
        {/* Overview tab is role-scoped (Step 5.5): MP/DM see their constituency
            report, SNO sees the state rollup, MoSPI sees the national view.
            Works/Alerts tabs remain available to every role, scope-filtered. */}
        {tab === "overview" &&
          ((role === "mp" || role === "dm") && mp ? (
            <MpOverview key={mp} mpName={mp} isDm={role === "dm"} />
          ) : role === "sno" && state ? (
            <SnoOverview key={state} state={state} />
          ) : (
            <OverviewTab scopeParams={scopeParams} />
          ))}
        {tab === "works" && <WorksTab scopeParams={scopeParams} />}
        {tab === "mps" && role === "mospi" && <MpsTab />}
        {tab === "alerts" && <AlertsTab scopeParams={scopeParams} />}
      </main>

      <Footer />
    </div>
  );
}

/* == Overview tab ===================================================== */

function OverviewTab({ scopeParams }: { scopeParams: Record<string, string> }) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [attention, setAttention] = useState<ProjectSummary[]>([]);
  const [states, setStates] = useState<StateRiskItem[]>([]);
  const [statesLoading, setStatesLoading] = useState(true);
  const [selectedState, setSelectedState] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .dashboardSummary()
      .then(setSummary)
      .catch((e) => setError(String(e)));
    // Per-state aggregation for the India map (D-031 Step 2).
    api
      .stateRisk()
      .then((r) => setStates(r.states))
      .catch(() => setStates([]))
      .finally(() => setStatesLoading(false));
    // Scope-aware attention list: for MP/SNO/DM pass their filter params.
    const listParams: Record<string, string | number> = {
      tier: "CRITICAL",
      sort: "risk_desc",
      page_size: 6,
    };
    if (scopeParams.mp) listParams.mp = scopeParams.mp;
    if (scopeParams.state) listParams.state = scopeParams.state;
    api
      .listProjects(listParams)
      .then((r) => setAttention(r.items))
      .catch(() => {});
  }, [scopeParams]);

  const inrCr = (v: number) =>
    `₹${(v / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 1 })} Cr`;

  return (
    <div className="space-y-6">
      {error && <ErrorState message={`Backend unreachable - ${error}`} />}
      {!summary && !error && <LoadingState label="Loading overview..." />}

      {summary && (
        <>
          {/* KPI tiles */}
          <section className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
            <StatCard
              label="Total Works"
              value={summary.total_works.toLocaleString("en-IN")}
              sub="Sanctions tracked"
            />
            <StatCard
              label="MPs Covered"
              value={summary.total_mps.toLocaleString("en-IN")}
              sub="Active in dataset"
            />
            <StatCard
              label="Funds Allocated"
              value={inrCr(summary.funds_allocated)}
              sub="Cumulative"
            />
            <StatCard
              label="Funds Utilised"
              value={inrCr(summary.funds_utilized)}
              sub={`${summary.utilization_pct}% of allocated`}
            />
            <StatCard
              label="Avg Financial Progress"
              value={`${summary.avg_financial_progress}%`}
              sub="Expenditure vs sanctioned"
            />
            <StatCard
              label="Completed Works"
              value={summary.completed_works.toLocaleString("en-IN")}
              sub={`${summary.completion_pct}% of works`}
            />
          </section>

          {/* India states risk map (D-031 Step 2, rev 2: compact map +
              stats arranged around it, corner colour index on the map) */}
          <section className="panel p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <SectionTitle>State Risk Map</SectionTitle>
              <span className="text-xs text-muted">
                Hover a state for numbers · click to inspect — aggregate
                indicators, not findings
              </span>
            </div>
            <div className="mt-4 grid grid-cols-1 items-start gap-5 lg:grid-cols-12">
              <div className="lg:col-span-5">
                <IndiaMap
                  data={states}
                  loading={statesLoading}
                  selected={selectedState ?? undefined}
                  onSelect={(s) => setSelectedState(s === selectedState ? null : s)}
                />
              </div>
              <div className="lg:col-span-4">
                <TopFlaggedStates
                  states={states}
                  onPick={setSelectedState}
                  selected={selectedState}
                />
              </div>
              <div className="space-y-4 lg:col-span-3">
                <MapColourIndex />
                {selectedState ? (
                  <StateDetailCard
                    item={states.find((s) => s.state === selectedState) ?? null}
                    onClear={() => setSelectedState(null)}
                  />
                ) : (
                  <div className="rounded-xl border border-dashed border-brd bg-surface-2/40 p-4 text-xs leading-relaxed text-muted">
                    <p className="font-semibold text-foreground">How to read this</p>
                    <p className="mt-1">
                      States are colored by <strong>weighted flag load</strong> —
                      {" "}4×CRITICAL + 2×HIGH + 1×MEDIUM relative to the worst
                      state — so severity and concentration matter, not just
                      size.
                    </p>
                    <p className="mt-2">
                      Click any state (map or ranking) for its full numbers.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* Risk overview row */}
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="panel p-5">
              <SectionTitle>Risk Tier Distribution</SectionTitle>
              <TierDonut counts={summary.tier_distribution} />
              <div className="mt-3">
                <TierLegend counts={summary.tier_distribution} />
              </div>
            </div>
            <div className="panel p-5">
              <SectionTitle>Top States by Flagged Works</SectionTitle>
              <StateBars
                states={summary.top_states_by_risk.slice(0, 6)}
              />
            </div>
            <div className="panel p-5">
              <SectionTitle>Top Flagged MPs</SectionTitle>
              <MpRanking mps={summary.top_mps_by_flagged.slice(0, 6)} />
            </div>
          </section>
        </>
      )}

      {/* Needs your attention - top critical works (live) */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <SectionTitle>Needs Your Attention</SectionTitle>
          <span className="text-xs text-muted">
            Highest-risk critical works · risk indicators requiring
            investigation
          </span>
        </div>
        <AttentionGrid
          items={attention}
          emptyHint="Try the Works tab for the full registry"
          scopeParams={scopeParams}
        />
      </section>
    </div>
  );
}

/* == Small local renderers ============================================ */

/** Clicked-state detail beside the map (D-031 Step 2). */
function StateDetailCard({
  item,
  onClear,
}: {
  item: StateRiskItem | null;
  onClear: () => void;
}) {
  if (!item) {
    return (
      <div className="rounded-xl border border-brd bg-surface-2/40 p-4 text-sm text-muted">
        No works recorded for this state in the dataset.
      </div>
    );
  }
  const util =
    item.funds_allocated > 0 ? ((item.funds_utilized / item.funds_allocated) * 100).toFixed(1) : null;
  return (
    <div className="rounded-xl border border-brd bg-surface p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display text-lg font-bold text-foreground">{item.state}</h3>
        <button
          onClick={onClear}
          className="text-[11px] font-semibold text-muted transition-colors hover:text-primary"
        >
          ✕ back to ranking
        </button>
      </div>
      <dl className="mt-3 space-y-2 text-xs">
        {[
          { k: "Total works", v: item.total_works.toLocaleString("en-IN"), strong: true },
          { k: "CRITICAL", v: String(item.critical), cls: "text-critical" },
          { k: "HIGH", v: String(item.high), cls: "text-high" },
          { k: "MEDIUM", v: item.medium.toLocaleString("en-IN"), cls: "text-medium" },
          { k: "LOW", v: item.low.toLocaleString("en-IN"), cls: "text-low" },
          { k: "Funds allocated", v: formatINR(item.funds_allocated) },
          { k: "Funds utilised", v: `${formatINR(item.funds_utilized)}${util ? ` · ${util}%` : ""}` },
          { k: "MPs with flagged works", v: String(item.flagged_mps) },
        ].map((r) => (
          <div key={r.k} className="flex items-baseline justify-between gap-2">
            <dt className="text-muted">{r.k}</dt>
            <dd className={`font-bold ${r.cls ?? (r.strong ? "text-foreground" : "text-foreground")}`}>
              {r.v}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 border-t border-brd pt-2 text-[10px] text-faint">
        Aggregate risk indicators over the frozen batch — not findings.
      </p>
    </div>
  );
}

/** Middle panel: states ranked by weighted flag intensity (click → detail). */
function TopFlaggedStates({
  states,
  onPick,
  selected,
}: {
  states: StateRiskItem[];
  onPick: (state: string) => void;
  selected: string | null;
}) {
  if (!states.length) {
    return (
      <div className="rounded-xl border border-brd bg-surface-2/40 p-4 text-sm text-muted">
        State aggregation unavailable.
      </div>
    );
  }
  const ranked = [...states].sort((a, b) => stateIntensity(b) - stateIntensity(a));
  const max = Math.max(1e-9, ...ranked.map(stateIntensity));
  return (
    <div className="rounded-xl border border-brd bg-surface p-4">
      <p className="text-[10px] font-bold uppercase tracking-wider text-muted">
        States by weighted flag load
      </p>
      <ol className="mt-2 divide-y divide-brd">
        {ranked.slice(0, 10).map((s) => {
          const intensity = stateIntensity(s) / max;
          const isSel = selected === s.state;
          return (
            <li key={s.state}>
              <button
                onClick={() => onPick(s.state)}
                className={`flex w-full items-center justify-between gap-2 py-2 text-left transition-colors hover:text-primary ${
                  isSel ? "text-primary" : ""
                }`}
              >
                <span
                  className={`truncate text-xs font-semibold ${isSel ? "text-primary" : "text-foreground"}`}
                >
                  {s.state}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="h-1.5 w-14 overflow-hidden rounded-full bg-surface-2">
                    <span
                      className="block h-full rounded-full"
                      style={{
                        width: `${Math.max(4, intensity * 100)}%`,
                        background:
                          s.critical > 0
                            ? "var(--tier-critical)"
                            : s.high > 0
                              ? "var(--tier-high)"
                              : "var(--tier-medium)",
                      }}
                    />
                  </span>
                  <span className="w-16 text-right text-xs">
                    {s.critical > 0 && <span className="font-bold text-critical">{s.critical}C </span>}
                    {s.high > 0 && <span className="font-bold text-high">{s.high}H</span>}
                    {s.critical === 0 && s.high === 0 && (
                      <span className="text-muted">{s.medium}M</span>
                    )}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function StateBars({
  states,
}: {
  states: { state: string; count: number }[];
}) {
  const max = Math.max(1, ...states.map((s) => s.count));
  return (
    <div className="mt-3 flex flex-col gap-3">
      {states.map((s) => (
        <div key={s.state}>
          <div className="flex items-center justify-between text-xs">
            <span className="text-foreground">{s.state}</span>
            <span className="font-bold text-muted">
              {s.count.toLocaleString("en-IN")}
            </span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full rounded-full"
              style={{
                width: `${(s.count / max) * 100}%`,
                background: "var(--accent)",
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function MpRanking({
  mps,
}: {
  mps: { mp_name: string; flagged_count: number }[];
}) {
  return (
    <ol className="mt-3 divide-y divide-brd">
      {mps.map((m, i) => (
        <li
          key={m.mp_name}
          className="flex items-center justify-between py-2.5 text-sm"
        >
          <span className="flex min-w-0 items-center gap-2.5">
            <span className="w-4 shrink-0 text-xs text-faint">{i + 1}</span>
            <span className="truncate font-semibold text-foreground">
              {m.mp_name}
            </span>
          </span>
          <span className="shrink-0 rounded-full bg-critical-bg px-2.5 py-0.5 text-xs font-bold text-critical">
            {m.flagged_count.toLocaleString("en-IN")} flagged
          </span>
        </li>
      ))}
    </ol>
  );
}
