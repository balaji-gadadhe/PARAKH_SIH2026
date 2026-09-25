"use client";

/**
 * app/dashboard/mps.tsx - MPs directory tab (MoSPI only).
 * Full 731-MP roster from /api/mps fetched once; search/filter/sort and
 * pagination run client-side for a snappy demo. Card click opens the MP
 * profile (drill-down) from /api/mps/{name} with tier counts + works.
 * Card layout: Stitch-inspired financial tiles (works+done+% | utilised
 * +of-allocated+%), house/state eyebrow, serif name, flagged/No-flags pill.
 * Uses only fields served by /api/mps — no fabrication.
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  formatINR,
  type MpSummary,
  type MpDetail,
} from "@/lib/api";
import { FilterBar, Pagination } from "@/components/shell";
import { TierDonut } from "@/components/charts";
import {
  StatCard,
  SectionTitle,
  TierBadge,
  ScoreGauge,
  LoadingState,
  ErrorState,
  EmptyState,
} from "@/components/ui";

const PAGE_SIZE = 12;

type SortKey = "flagged_desc" | "works_desc" | "utilization_desc" | "completion_desc";

const SORTS: { value: SortKey; label: string }[] = [
  { value: "flagged_desc", label: "Most flagged first" },
  { value: "works_desc", label: "Most works first" },
  { value: "utilization_desc", label: "Best utilization first" },
  { value: "completion_desc", label: "Best completion first" },
];

export function MpsTab() {
  const [roster, setRoster] = useState<MpSummary[] | null>(null);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [state, setState] = useState("");
  const [house, setHouse] = useState("");
  const [sort, setSort] = useState<SortKey>("flagged_desc");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listMps({})
      .then((r) => setRoster(r.items))
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const states = useMemo(() => {
    if (!roster) return [];
    return [...new Set(roster.map((m) => m.state))].sort((a, b) =>
      a.localeCompare(b)
    );
  }, [roster]);

  const filtered = useMemo(() => {
    if (!roster) return [];
    const q = debounced.trim().toLowerCase();
    let list = roster;
    if (q)
      list = list.filter(
        (m) =>
          m.mp_name.toLowerCase().includes(q) ||
          m.constituency.toLowerCase().includes(q) ||
          m.state.toLowerCase().includes(q)
      );
    if (state) list = list.filter((m) => m.state === state);
    if (house) list = list.filter((m) => m.house === house);
    const by: Record<SortKey, (a: MpSummary, b: MpSummary) => number> = {
      flagged_desc: (a, b) => b.flagged_works - a.flagged_works,
      works_desc: (a, b) =>
        (b.recommended_works ?? 0) - (a.recommended_works ?? 0),
      utilization_desc: (a, b) =>
        (b.utilization_pct ?? -1) - (a.utilization_pct ?? -1),
      completion_desc: (a, b) =>
        (b.completion_rate_pct ?? -1) - (a.completion_rate_pct ?? -1),
    };
    return [...list].sort(by[sort]);
  }, [roster, debounced, state, house, sort]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const totals = useMemo(() => {
    if (!roster) return null;
    return {
      mps: roster.length,
      flagged: roster.reduce((a, m) => a + m.flagged_works, 0),
      allocated: roster.reduce((a, m) => a + (m.allocated_amount ?? 0), 0),
    };
  }, [roster]);

  if (error) return <ErrorState message={`Backend unreachable - ${error}`} />;

  if (selected) {
    return <MpProfile mpName={selected} onBack={() => setSelected(null)} />;
  }

  return (
    <div className="space-y-5">
      {/* Stat tiles */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label="MPs in Registry"
          value={totals ? totals.mps.toLocaleString("en-IN") : "…"}
          sub="Live roster"
        />
        <StatCard
          label="Flagged Works (all MPs)"
          value={totals ? totals.flagged.toLocaleString("en-IN") : "…"}
          sub="High + Critical"
        />
        <StatCard
          label="Allocated (sum of MPs)"
          value={totals ? formatINR(totals.allocated) : "…"}
          sub="Aggregated from MP records"
        />
      </section>

      <FilterBar
        search={search}
        onSearch={setSearch}
        selects={[
          {
            key: "state",
            label: "State",
            value: state,
            options: [
              { value: "", label: "All states" },
              ...states.map((s) => ({ value: s, label: s })),
            ],
          },
          {
            key: "house",
            label: "House",
            value: house,
            options: [
              { value: "", label: "Both houses" },
              { value: "Lok Sabha", label: "Lok Sabha" },
              { value: "Rajya Sabha", label: "Rajya Sabha" },
            ],
          },
          {
            key: "sort",
            label: "Sort",
            value: sort,
            options: SORTS.map((s) => ({ value: s.value, label: s.label })),
          },
        ]}
        onSelect={(key, value) => {
          setPage(1);
          if (key === "state") setState(value);
          if (key === "house") setHouse(value);
          if (key === "sort") setSort(value as SortKey);
        }}
      />

      {!roster && <LoadingState label="Loading MP registry..." />}

      {/* Card grid */}
      {roster && (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {paged.map((m) => (
              <button
                key={`${m.mp_name}-${m.constituency}`}
                onClick={() => setSelected(m.mp_name)}
                className="panel flex flex-col p-5 text-left transition-shadow hover:shadow-[var(--shadow-raised)]"
              >
                {/* Card header & badge (Stitch: eyebrow + big name + pill) */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold uppercase tracking-wider text-muted">
                      {m.house ?? "Member"} • {m.state}
                    </p>
                    <h2 className="mt-1 truncate font-display text-xl font-bold text-foreground">
                      {m.mp_name}
                    </h2>
                    <p className="mt-0.5 truncate text-xs text-muted">
                      Constituency: {m.constituency}
                    </p>
                  </div>
                  {m.flagged_works > 0 ? (
                    <span className="shrink-0 rounded-full bg-critical-bg px-3 py-1 text-xs font-bold text-critical">
                      {m.flagged_works} flagged
                    </span>
                  ) : (
                    <span
                      className="shrink-0 rounded-full px-3 py-1 text-xs font-semibold"
                      style={{ background: "var(--tier-low-bg)", color: "var(--tier-low)" }}
                    >
                      No flags
                    </span>
                  )}
                </div>

                {/* Key financial metric tiles (Stitch 2-up inset) */}
                <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg bg-surface-2 p-3.5">
                  <div className="flex flex-col">
                    <span className="text-[11px] font-medium text-muted">
                      Works executed
                    </span>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xl font-extrabold text-foreground">
                        {(m.recommended_works ?? 0).toLocaleString("en-IN")}
                      </span>
                      <span className="text-xs text-muted">
                        ({(m.completed_works ?? 0).toLocaleString("en-IN")} done)
                      </span>
                    </div>
                    <span className="text-xs font-semibold text-primary">
                      {m.completion_rate_pct != null
                        ? `${m.completion_rate_pct}% completed`
                        : "Completion not available"}
                    </span>
                  </div>
                  <div className="flex flex-col border-l border-brd pl-3">
                    <span className="text-[11px] font-medium text-muted">
                      Fund utilised
                    </span>
                    {m.total_expenditure != null ? (
                      <>
                        <span className="text-xl font-extrabold text-foreground">
                          {formatINR(m.total_expenditure)}
                        </span>
                        <span className="text-xs text-muted">
                          {m.allocated_amount != null
                            ? `of ${formatINR(m.allocated_amount)}`
                            : "allocation not recorded"}
                          {m.utilization_pct != null ? ` (${m.utilization_pct}%)` : ""}
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="text-xl font-extrabold text-foreground">
                          {m.allocated_amount != null ? (
                            formatINR(m.allocated_amount)
                          ) : (
                            <span className="na-value text-sm">Not available</span>
                          )}
                        </span>
                        <span className="text-xs text-muted">
                          {m.allocated_amount != null
                            ? "allocated"
                            : "no financial records"}
                        </span>
                      </>
                    )}
                  </div>
                </div>

                {/* Utilization bar (financial: expenditure vs allocated) */}
                {m.utilization_pct != null && (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs font-semibold">
                      <span className="text-muted">Fund utilization</span>
                      <span className="text-foreground">{m.utilization_pct}%</span>
                    </div>
                    <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-2">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{
                          width: `${Math.max(0, Math.min(100, m.utilization_pct))}%`,
                        }}
                      />
                    </div>
                  </div>
                )}

                <div className="mt-auto flex items-center justify-between pt-3 text-xs">
                  <span className="text-muted">
                    Pending payments:{" "}
                    <b className="text-foreground">
                      {(m.pending_payments ?? 0).toLocaleString("en-IN")}
                    </b>
                  </span>
                  <span className="font-semibold text-primary">Profile →</span>
                </div>
              </button>
            ))}
          </div>
          {filtered.length === 0 && (
            <EmptyState
              message="No MPs match these filters"
              hint="Try clearing the search or state filter"
            />
          )}
          <Pagination
            page={page}
            pages={totalPages}
            total={filtered.length}
            onPage={setPage}
          />
        </>
      )}
    </div>
  );
}

/* ═══ MP profile drill-down ════════════════════════════════════════════ */

function MpProfile({
  mpName,
  onBack,
}: {
  mpName: string;
  onBack: () => void;
}) {
  const [detail, setDetail] = useState<MpDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .mpDetail(mpName)
      .then(setDetail)
      .catch((e) => setError(String(e)));
  }, [mpName]);

  if (error) return <ErrorState message={`Backend unreachable - ${error}`} />;
  if (!detail) return <LoadingState label="Loading MP profile..." />;

  const mp = detail.mp;
  const tierCounts = {
    CRITICAL: detail.critical_works,
    HIGH: detail.high_risk_works,
    MEDIUM: detail.medium_risk_works,
    LOW: detail.low_risk_works,
  };
  const works = detail.works ?? [];

  return (
    <div className="space-y-5">
      <button
        onClick={onBack}
        className="text-sm font-semibold text-primary hover:underline"
      >
        ← Back to MPs directory
      </button>

      {/* Identity */}
      <section className="panel flex flex-wrap items-center justify-between gap-6 p-6">
        <div className="min-w-0">
          <p className="section-label">MP Profile</p>
          <h1 className="mt-1 font-display text-2xl font-bold text-primary">
            {mp.mp_name}
          </h1>
          <p className="mt-0.5 text-sm text-muted">
            {mp.constituency} · {mp.state}
            {mp.house ? ` · ${mp.house}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-8">
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
        <StatCard
          label="Completed"
          value={(mp.completed_works ?? 0).toLocaleString("en-IN")}
          sub={mp.completion_rate_pct != null ? `${mp.completion_rate_pct}%` : undefined}
        />
        <StatCard
          label="Allocated"
          value={mp.allocated_amount != null ? formatINR(mp.allocated_amount) : "Not available"}
        />
        <StatCard
          label="Utilised"
          value={mp.total_expenditure != null ? formatINR(mp.total_expenditure) : "Not available"}
          sub={mp.utilization_pct != null ? `${mp.utilization_pct}%` : undefined}
        />
        <StatCard label="Pending Payments" value={(mp.pending_payments ?? 0).toLocaleString("en-IN")} />
        <StatCard label="Flagged Works" value={(mp.flagged_works ?? 0).toLocaleString("en-IN")} sub="High + Critical" />
      </section>

      {/* Tier mix */}
      <section className="panel p-5">
        <SectionTitle>Risk Mix of Works</SectionTitle>
        <div className="mt-2 grid grid-cols-1 items-center gap-6 lg:grid-cols-2">
          <TierDonut counts={tierCounts} height={200} />
          <div className="flex flex-wrap gap-2">
            {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((t) => (
              <span key={t} className="flex items-center gap-1.5">
                <TierBadge tier={t} small />
                <span className="text-xs text-muted">
                  {(tierCounts[t] ?? 0).toLocaleString("en-IN")} works
                </span>
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Works table */}
      <section className="space-y-3">
        <SectionTitle>Works under this MP</SectionTitle>
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-brd bg-surface-2 text-left">
                {["Project ID", "Description", "Category", "Tier", "Score", ""].map((h) => (
                  <th key={h} className="px-4 py-3 text-[11px] font-bold uppercase tracking-wider text-muted">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {works.slice(0, 12).map((w) => (
                <tr key={w.project_id} className="border-b border-brd last:border-0 hover:bg-surface-2/60">
                  <td className="px-4 py-3 font-bold text-primary">{w.project_id}</td>
                  <td className="max-w-[280px] px-4 py-3">
                    <span className="block truncate">
                      {w.work_description ?? <span className="na-value">Not available</span>}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted">{w.category}</td>
                  <td className="px-4 py-3">
                    <TierBadge tier={w.risk_category} small />
                  </td>
                  <td className="px-4 py-3 font-extrabold">{w.risk_score_display}</td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/investigation/${encodeURIComponent(w.project_id)}?role=mospi`}
                      className="btn-primary inline-block px-3.5 py-1.5 text-xs"
                    >
                      Investigate
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {works.length > 12 && (
            <p className="px-4 py-3 text-xs text-muted">
              Showing 12 of {works.length.toLocaleString("en-IN")} works —
              see the MP&apos;s Overview or Works tab for the full list.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
