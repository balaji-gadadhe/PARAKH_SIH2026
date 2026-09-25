"use client";

/**
 * app/dashboard/works.tsx - Works explorer tab.
 * Live table over /api/projects with search + tier/category/status/state
 * filters, stat tiles, pagination, and Investigate actions.
 * Scope params (mp=/state=) restrict everything for MP/SNO/DM roles.
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type ProjectListResponse } from "@/lib/api";
import { FilterBar, Pagination } from "@/components/shell";
import {
  StatCard,
  TierBadge,
  LoadingState,
  ErrorState,
  EmptyState,
} from "@/components/ui";

const PAGE_SIZE = 10;

const TIER_OPTIONS = [
  { value: "", label: "All tiers" },
  { value: "CRITICAL", label: "Critical" },
  { value: "HIGH", label: "High" },
  { value: "MEDIUM", label: "Medium" },
  { value: "LOW", label: "Low" },
];

const CATEGORY_OPTIONS = [
  { value: "", label: "All categories" },
  { value: "Normal/Others", label: "Normal / Others" },
  { value: "Repair and Renovation", label: "Repair & Renovation" },
  { value: "Trust and Society", label: "Trust & Society" },
  { value: "Bar and Associations", label: "Bar & Associations" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "completed", label: "Completed" },
  { value: "ongoing", label: "In Progress" },
];

/** First signal name from "Delay (Score: 1.00, Weight: 22.3%); ..." */
function firstSignal(top: string | null): string | null {
  if (!top) return null;
  const seg = top.split(";")[0];
  const name = seg.split("(Score")[0].trim();
  return name || null;
}

export function WorksTab({
  scopeParams,
}: {
  scopeParams: Record<string, string>;
}) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [tier, setTier] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [stateQ, setStateQ] = useState("");
  const [page, setPage] = useState(1);

  const [data, setData] = useState<ProjectListResponse | null>(null);
  const [completedTotal, setCompletedTotal] = useState<number | null>(null);
  const [flaggedTotal, setFlaggedTotal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Debounce the search box into the query (reset page)
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 400);
    return () => clearTimeout(t);
  }, [search]);

  const scopeOnly = useMemo(
    () => ({
      mp: scopeParams.mp,
      state: scopeParams.state,
    }),
    [scopeParams.mp, scopeParams.state]
  );

  // Role/scope travels to the dossier so its back link + Report modal
  // return to the right dashboard (D-029 flow). The dossier treats an
  // absent role as a public viewer (read-only), so the Ministry role is
  // always explicit.
  const scopeQuery = useMemo(() => {
    const p = new URLSearchParams();
    if (scopeParams.role) p.set("role", scopeParams.role);
    if (scopeParams.mp) p.set("mp", scopeParams.mp);
    if (scopeParams.state) p.set("state", scopeParams.state);
    const s = p.toString();
    return s ? `?${s}` : "";
  }, [scopeParams.role, scopeParams.mp, scopeParams.state]);

  // Main table query
  useEffect(() => {
    const listParams: Record<string, string | number> = {
      sort: "risk_desc",
      page,
      page_size: PAGE_SIZE,
    };
    if (debounced) listParams.q = debounced;
    if (tier) listParams.tier = tier;
    if (category) listParams.category = category;
    if (status) listParams.status = status;
    if (stateQ.trim()) listParams.state = stateQ.trim();
    if (scopeOnly.mp) listParams.mp = scopeOnly.mp;
    if (scopeOnly.state) listParams.state = scopeOnly.state;

    api
      .listProjects(listParams)
      .then((r) => {
        setData(r);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [page, debounced, tier, category, status, stateQ, scopeOnly]);

  // Scope-level stat tiles (independent of table filters)
  useEffect(() => {
    const statParams: Record<string, string> = {};
    if (scopeOnly.mp) statParams.mp = scopeOnly.mp;
    if (scopeOnly.state) statParams.state = scopeOnly.state;

    api
      .listProjects({ ...statParams, status: "completed", page_size: 1 })
      .then((r) => setCompletedTotal(r.total))
      .catch(() => setCompletedTotal(null));

    api
      .listAlerts({ ...statParams, page_size: 1 })
      .then((r) =>
        setFlaggedTotal(
          (r.tier_counts?.HIGH ?? 0) + (r.tier_counts?.CRITICAL ?? 0)
        )
      )
      .catch(() => setFlaggedTotal(null));
  }, [scopeOnly]);

  return (
    <div className="space-y-5">
      {/* Stat tiles */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label="Works in scope"
          value={data ? data.total.toLocaleString("en-IN") : "…"}
          sub="Matching current scope"
        />
        <StatCard
          label="Flagged (High + Critical)"
          value={
            flaggedTotal === null ? "…" : flaggedTotal.toLocaleString("en-IN")
          }
          sub="Risk indicators requiring review"
        />
        <StatCard
          label="Completed"
          value={
            completedTotal === null
              ? "…"
              : completedTotal.toLocaleString("en-IN")
          }
          sub="Marked completed in dataset"
        />
      </section>

      {/* Filters */}
      <FilterBar
        search={search}
        onSearch={(v) => {
          setSearch(v);
        }}
        selects={[
          { key: "tier", label: "Risk tier", value: tier, options: TIER_OPTIONS },
          {
            key: "category",
            label: "Category",
            value: category,
            options: CATEGORY_OPTIONS,
          },
          {
            key: "status",
            label: "Status",
            value: status,
            options: STATUS_OPTIONS,
          },
        ]}
        onSelect={(key, value) => {
          setPage(1);
          if (key === "tier") setTier(value);
          if (key === "category") setCategory(value);
          if (key === "status") setStatus(value);
        }}
        action={
          !scopeParams.state ? (
            <input
              value={stateQ}
              onChange={(e) => {
                setStateQ(e.target.value);
                setPage(1);
              }}
              placeholder="State contains…"
              className="w-36 rounded-lg border border-brd bg-surface px-3 py-2.5 text-sm focus:border-primary focus:outline-none"
              aria-label="State filter"
            />
          ) : null
        }
      />

      {error && <ErrorState message={`Backend unreachable - ${error}`} />}
      {loading && !data && <LoadingState label="Loading works..." />}

      {/* Table */}
      {data && (
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-brd bg-surface-2 text-left">
                {["Project ID", "Work Description", "MP", "State", "Tier", "Score", "Top Signal", ""].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-[11px] font-bold uppercase tracking-wider text-muted"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {data.items.map((w) => (
                <tr
                  key={w.project_id}
                  className="border-b border-brd transition-colors last:border-0 hover:bg-surface-2/60"
                >
                  <td className="px-4 py-3 font-bold text-primary">
                    {w.project_id}
                  </td>
                  <td className="max-w-[260px] px-4 py-3">
                    <span className="block truncate" title={w.work_description ?? undefined}>
                      {w.work_description ?? (
                        <span className="na-value">Not available</span>
                      )}
                    </span>
                  </td>
                  <td className="max-w-[180px] px-4 py-3">
                    <span className="block truncate text-muted" title={w.mp_name}>
                      {w.mp_name}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted">{w.state}</td>
                  <td className="px-4 py-3">
                    <TierBadge tier={w.risk_category} small />
                  </td>
                  <td className="px-4 py-3 font-extrabold text-foreground">
                    {w.risk_score_display}
                  </td>
                  <td className="px-4 py-3">
                    {firstSignal(w.top_risk_signals) ? (
                      <span className="rounded-full bg-surface-2 px-2.5 py-1 text-[11px] font-medium text-muted">
                        {firstSignal(w.top_risk_signals)}
                      </span>
                    ) : (
                      <span className="na-value text-xs">None recorded</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/investigation/${encodeURIComponent(w.project_id)}${scopeQuery}`}
                      className="btn-primary inline-block px-3.5 py-1.5 text-xs"
                    >
                      Investigate
                    </Link>
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-2">
                    <EmptyState
                      message="No works match these filters"
                      hint="Try clearing a filter or widening the search"
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <Pagination
            page={data.page}
            pages={data.pages}
            total={data.total}
            onPage={setPage}
          />
        </div>
      )}
    </div>
  );
}
