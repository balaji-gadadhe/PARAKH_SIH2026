"use client";

/**
 * app/dashboard/alerts.tsx - Alerts / risk queue tab (all roles, scope-filtered).
 * No Stitch screen exists for this tab - designed in-theme from /api/alerts:
 * tier filter pills with live counts, signal-type breakdown, ranked table.
 * Risk language per card reference §7: indicators requiring investigation.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  formatINR,
  notAvailable,
  REPORTS_CHANGED_EVENT,
  type AlertListResponse,
  type ProjectDetail,
  type ReportItem,
  type ReportSnapshot,
  type RiskTier,
} from "@/lib/api";
import { FilterBar, Pagination } from "@/components/shell";
import { HBarList } from "@/components/charts";
import { ENGINE_META } from "@/components/xai";
import {
  SectionTitle,
  TierBadge,
  LoadingState,
  ErrorState,
  EmptyState,
} from "@/components/ui";

const PAGE_SIZE = 15;

/* ─── Report detail (expandable row content, D-029) ──────────────────── */

/**
 * Lazily fetched work snapshot for an expanded inbox row: description,
 * financials, status + the six-engine score strip so the reviewer can see
 * WHY the work is flagged without leaving the inbox. Data comes from the
 * existing projectDetail endpoint — no backend changes.
 */
function ReportDetail({ projectId }: { projectId: string }) {
  const [work, setWork] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .projectDetail(projectId)
      .then(setWork)
      .catch((e) => setError(String(e)));
  }, [projectId]);

  if (error) {
    return <p className="text-xs text-critical">Snapshot unavailable — {error}</p>;
  }
  if (!work) {
    return <p className="text-xs text-muted">Loading work snapshot…</p>;
  }

  const engines = work.engines.filter((e) => e.available);

  return (
    <div className="mt-1 space-y-3 rounded-lg border border-brd bg-surface-2/50 p-3">
      {/* Work identity */}
      <div>
        <p className="text-sm font-semibold leading-snug text-foreground">
          {work.work_description ?? "Work description not recorded"}
        </p>
        <p className="mt-0.5 text-[11px] text-muted">
          {work.category} · {work.status ?? "Status not available"} ·{" "}
          {formatINR(work.recommended_amount)} recommended
        </p>
      </div>

      {/* Six-engine score strip (only engines with data) */}
      {engines.length > 0 && (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted">
            Why it is flagged — engine scores
          </p>
          <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
            {engines.map((e) => {
              const meta = ENGINE_META[e.engine];
              return (
                <div key={e.engine} className="flex items-center gap-2">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: meta?.hex ?? "var(--muted)" }}
                    title={meta?.checks ?? e.engine}
                  />
                  <span className="min-w-0 flex-1 truncate text-[11px] text-muted">
                    {meta?.label ?? e.engine}
                  </span>
                  <span
                    className={`shrink-0 text-[11px] font-bold ${
                      e.flag ? "text-critical" : "text-muted"
                    }`}
                  >
                    {e.score != null ? `${Math.round(e.score * 100)}` : "—"}
                    {e.flag ? " ⚑" : ""}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="mt-1 text-[10px] text-faint">
            Engine scores are 0–100 risk indicators; ⚑ = engine flagged the work.
          </p>
        </div>
      )}

      {/* Key financial facts */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 border-t border-brd pt-2 text-[11px] sm:grid-cols-3">
        <span className="text-muted">
          Expenditure{" "}
          <span className="font-semibold text-foreground">
            {formatINR(work.total_expenditure)}
          </span>
        </span>
        <span className="text-muted">
          Payments{" "}
          <span className="font-semibold text-foreground">
            {notAvailable(work.payment_count)}
          </span>
        </span>
        <span className="text-muted">
          Vendor{" "}
          <span className="max-w-[140px] truncate font-semibold text-foreground" title={work.primary_vendor ?? ""}>
            {work.primary_vendor ?? "Not available"}
          </span>
        </span>
      </div>
    </div>
  );
}

/* ─── Structured snapshot view (D-031 Step-1 follow-up) ───────────────── */

/**
 * Rich rendering of the attached analysis snapshot: tier chip, why-flagged
 * callout, flagged-engine chips, and compact labeled rows. Falls back to the
 * legacy plain-text `summary_md` when `summary_json` is absent/unparseable.
 * Honesty note is always shown (snapshot = indicators, not findings).
 */
function ReportSnapshotView({ report }: { report: ReportItem }) {
  const snap = useMemo<ReportSnapshot | null>(() => {
    if (!report.summary_json) return null;
    try {
      const v = JSON.parse(report.summary_json);
      return v && typeof v === "object" ? (v as ReportSnapshot) : null;
    } catch {
      return null;
    }
  }, [report.summary_json]);

  // Legacy plain-text fallback (pre-structured reports).
  if (!snap) {
    if (!report.summary_md) return null;
    return (
      <details className="mt-1.5 rounded-lg border border-brd bg-white">
        <summary className="cursor-pointer select-none px-3 py-2 text-[11px] font-semibold text-primary">
          📄 Analysis snapshot attached — open
        </summary>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap border-t border-brd px-3 py-2.5 font-mono text-[10px] leading-relaxed text-stone-700">
          {report.summary_md}
        </pre>
        <p className="border-t border-brd px-3 py-1.5 text-[10px] text-faint">
          Snapshot generated from the investigation dossier at report time —
          indicators for review, not findings.
        </p>
      </details>
    );
  }

  return (
    <div className="mt-2 overflow-hidden rounded-lg border border-brd bg-white">
      {/* Header strip: score + tier + identity */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-brd bg-surface-2/60 px-3 py-2">
        <span
          className={`rounded px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${
            snap.tier === "CRITICAL"
              ? "bg-critical text-white"
              : snap.tier === "HIGH"
                ? "bg-high text-white"
                : snap.tier === "MEDIUM"
                  ? "bg-medium text-white"
                  : "bg-low text-white"
          }`}
        >
          {snap.tier} · {snap.score}/100
        </span>
        <span className="truncate text-[11px] font-semibold text-foreground" title={snap.mp}>
          {snap.mp}
        </span>
        <span className="text-[11px] text-muted">
          {snap.state} · {snap.category}
        </span>
      </div>

      <div className="space-y-2.5 px-3 py-2.5">
        {/* Why flagged */}
        {snap.why_flagged && (
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-muted">
              Why flagged
            </p>
            <p className="mt-0.5 text-[11px] leading-relaxed text-foreground">
              {snap.why_flagged}
            </p>
          </div>
        )}

        {/* Flagged engines as chips */}
        {snap.flagged_engines.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {snap.flagged_engines.map((e) => (
              <span
                key={e.engine}
                className="rounded-full border border-critical/30 bg-critical/10 px-2 py-0.5 text-[10px] font-bold text-critical"
              >
                ⚑ {e.engine} · {e.score != null ? e.score : "—"}
              </span>
            ))}
          </div>
        )}

        {/* Financial rows */}
        {snap.financials.length > 0 && (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            {snap.financials.map((f) => (
              <div key={f.label} className="flex items-baseline justify-between gap-2 text-[11px]">
                <span className="text-muted">{f.label}</span>
                <span className={`font-bold ${f.warn ? "text-critical" : "text-foreground"}`}>
                  {f.value}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Payments + triage compact rows */}
        <div className="grid grid-cols-1 gap-x-4 gap-y-1 border-t border-brd pt-2 text-[11px] sm:grid-cols-2">
          {[...snap.payments, ...snap.triage].map((r) => (
            <div key={r.label} className="flex items-baseline justify-between gap-2">
              <span className="text-muted">{r.label}</span>
              <span className="font-semibold text-foreground">{r.value}</span>
            </div>
            ))}
        </div>
      </div>

      <p className="border-t border-brd bg-surface-2/40 px-3 py-1.5 text-[10px] text-faint">
        Snapshot generated from the investigation dossier at report time —
        indicators for review, not findings.
      </p>
    </div>
  );
}

/* ─── Reports inbox (D-029) ──────────────────────────────────────────── */

/**
 * "This needs your attention" — reports addressed to the logged-in
 * authority (routed by POST /api/reports from the Investigation Center).
 * Scope uses the same role params as every other tab:
 * mp/dm → mp name · sno → state · mospi → central audit cell.
 */
function ReportsInbox({ scopeParams }: { scopeParams: Record<string, string> }) {
  const role = scopeParams.role ?? "mospi";
  const canFetch =
    role === "mospi" || Boolean(scopeParams.mp || scopeParams.state);

  const [open, setOpen] = useState(false);
  const [reports, setReports] = useState<ReportItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [clearing, setClearing] = useState(false);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const inboxParams = useMemo(() => {
    const p: { role: string; mp?: string; state?: string } = { role };
    if (scopeParams.mp) p.mp = scopeParams.mp;
    if (scopeParams.state) p.state = scopeParams.state;
    return p;
  }, [role, scopeParams.mp, scopeParams.state]);

  const load = useCallback(() => {
    if (!canFetch) return;
    api
      .listReports(inboxParams)
      .then((r) => {
        setReports(r.items);
        setError(null);
      })
      .catch((e) => setError(String(e)));
  }, [canFetch, inboxParams]);

  useEffect(() => {
    load();
  }, [load]);

  // Live refresh when any inbox action (ack/clear) happens anywhere.
  useEffect(() => {
    if (!canFetch) return;
    const onChange = () => load();
    window.addEventListener(REPORTS_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(REPORTS_CHANGED_EVENT, onChange);
  }, [canFetch, load]);

  const ack = async (id: number) => {
    setBusyId(id);
    try {
      await api.ackReport(id, inboxParams);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusyId(null);
    }
  };

  const clearAll = async () => {
    // Two-click confirmation: first click arms the button, second deletes.
    if (!confirmingClear) {
      setConfirmingClear(true);
      return;
    }
    setClearing(true);
    try {
      await api.clearReports(inboxParams);
      setConfirmingClear(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setClearing(false);
    }
  };

  // Disarm the confirmation if the user walks away from it.
  useEffect(() => {
    if (!confirmingClear) return;
    const t = setTimeout(() => setConfirmingClear(false), 4000);
    return () => clearTimeout(t);
  }, [confirmingClear]);

  const newCount = reports?.filter((r) => r.status === "NEW").length ?? 0;
  const total = reports?.length ?? 0;

  // Scope query for Investigate links (identity travels to the dossier).
  // The dossier treats an absent role as a public viewer (read-only), so the
  // Ministry role is always explicit.
  const scopeQuery = useMemo(() => {
    const p = new URLSearchParams();
    if (role) p.set("role", role);
    if (scopeParams.mp) p.set("mp", scopeParams.mp);
    if (scopeParams.state) p.set("state", scopeParams.state);
    const s = p.toString();
    return s ? `?${s}` : "";
  }, [role, scopeParams.mp, scopeParams.state]);

  if (!canFetch) {
    return (
      <section className="panel p-5">
        <SectionTitle>This needs your attention</SectionTitle>
        <p className="mt-2 text-sm text-muted">
          Log in with your identity to see reports addressed to you.
        </p>
      </section>
    );
  }

  return (
    <section className="panel p-0">
      {/* Collapsed header (always visible) — expand to review reports */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center justify-between gap-3 px-5 py-4 text-left transition-colors hover:bg-surface-2/60"
      >
        <span className="flex items-center gap-3">
          <span
            className={`inline-block text-xs text-muted transition-transform ${open ? "rotate-90" : ""}`}
            aria-hidden
          >
            ▶
          </span>
          <SectionTitle>This needs your attention</SectionTitle>
          {reports && (
            <>
              {newCount > 0 && (
                <span className="rounded-full bg-critical px-2.5 py-0.5 text-[11px] font-bold text-white">
                  {newCount} new
                </span>
              )}
              <span className="rounded-full border border-brd px-2.5 py-0.5 text-[11px] font-semibold text-muted">
                {total.toLocaleString("en-IN")} total
              </span>
            </>
          )}
        </span>
        <span className="text-[11px] font-medium text-muted">
          {open ? "Hide" : "Show"} reports · routed in-app (demo)
        </span>
      </button>

      {open && (
        <div className="border-t border-brd px-5 pb-5 pt-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted">
              Reports on flagged works addressed to you by other authorities.
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={load}
                className="rounded-lg border border-brd px-2.5 py-1 text-[11px] font-semibold text-muted transition-colors hover:bg-surface-2 hover:text-primary"
              >
                ↻ Refresh
              </button>
              <button
                onClick={clearAll}
                disabled={clearing || total === 0}
                className={`rounded-lg border px-2.5 py-1 text-[11px] font-semibold transition-colors disabled:opacity-50 ${
                  confirmingClear
                    ? "border-critical bg-critical text-white hover:bg-red-800"
                    : "border-critical/40 text-critical hover:bg-critical/10"
                }`}
              >
                {clearing
                  ? "Clearing…"
                  : confirmingClear
                    ? "Really clear all? Click again"
                    : "Clear all"}
              </button>
            </div>
          </div>
      {error && (
        <div className="px-5 pb-4">
          <ErrorState message={`Backend unreachable - ${error}`} />
        </div>
      )}
      {!reports && !error && (
        <div className="px-5 pb-5">
          <LoadingState label="Checking your inbox..." />
        </div>
      )}
      {reports && reports.length === 0 && (
        <div className="px-5 pb-5">
          <EmptyState
            message="No reports addressed to you yet"
            hint="When a higher authority reports one of your works, it appears here"
          />
        </div>
      )}

      {canFetch && reports && reports.length > 0 && (
        <ul className="mt-2 divide-y divide-brd">
          {reports.map((r) => (
            <li
              key={r.id}
              className="flex flex-col gap-3 py-4 sm:flex-row sm:items-start sm:justify-between"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() =>
                      setExpandedId((cur) => (cur === r.id ? null : r.id))
                    }
                    aria-expanded={expandedId === r.id}
                    title={expandedId === r.id ? "Hide work snapshot" : "Show work snapshot"}
                    className="flex items-center gap-2 rounded text-left"
                  >
                    <span
                      className={`inline-block text-[10px] text-muted transition-transform ${expandedId === r.id ? "rotate-90" : ""}`}
                      aria-hidden
                    >
                      ▶
                    </span>
                    <TierBadge tier={r.risk_category} small />
                    <span className="font-extrabold text-foreground">
                      {r.risk_score_display}
                    </span>
                    <span className="font-bold text-primary hover:underline">
                      {r.project_id.split("|")[0]}
                    </span>
                  </button>
                  <span
                    className="max-w-[220px] truncate text-xs text-muted"
                    title={r.mp_name}
                  >
                    {r.mp_name} · {r.state}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted">
                  Reported by{" "}
                  <span className="font-semibold text-foreground">
                    {r.reported_by_role}
                  </span>{" "}
                  · for {r.target_role} review ·{" "}
                  {new Date(r.created_at).toLocaleString("en-IN", {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                  {r.status === "ACKNOWLEDGED" && r.acknowledged_at && (
                    <>
                      {" "}· <span className="font-semibold text-primary">✓ reviewed</span>{" "}
                      {new Date(r.acknowledged_at).toLocaleString("en-IN", {
                        day: "numeric",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </>
                  )}
                </p>
                {r.comment && (
                  <p className="mt-1.5 rounded-lg bg-surface-2 px-3 py-2 text-xs italic text-muted">
                    &ldquo;{r.comment}&rdquo;
                  </p>
                )}
                {/* Attached analysis snapshot — rich UI when structured JSON
                    is present, legacy plain-text block otherwise. */}
                {(r.summary_json || r.summary_md) && (
                  <details className="mt-1.5 rounded-lg border border-brd bg-white">
                    <summary className="cursor-pointer select-none px-3 py-2 text-[11px] font-semibold text-primary">
                      📄 Analysis snapshot attached — open
                    </summary>
                    <div className="border-t border-brd p-2.5">
                      <ReportSnapshotView report={r} />
                    </div>
                  </details>
                )}
                {expandedId === r.id && <ReportDetail projectId={r.project_id} />}
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                {r.status === "NEW" ? (
                  <span className="rounded-full bg-critical-bg px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-critical">
                    New
                  </span>
                ) : (
                  <span className="rounded-full bg-surface-2 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-muted">
                    Acknowledged
                  </span>
                )}
                {r.status === "NEW" && (
                  <button
                    onClick={() => ack(r.id)}
                    disabled={busyId === r.id}
                    className="rounded-lg border border-brd px-3 py-1.5 text-xs font-semibold text-muted transition-colors hover:bg-surface-2 hover:text-primary disabled:opacity-50"
                  >
                    {busyId === r.id ? "Saving…" : "Acknowledge"}
                  </button>
                )}
                <Link
                  href={`/investigation/${encodeURIComponent(r.project_id)}${scopeQuery}`}
                  className="btn-primary inline-block px-3.5 py-1.5 text-xs"
                >
                  Investigate
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
        </div>
      )}
    </section>
  );
}

/** First signal name from "Delay (Score: 1.00, Weight: 22.3%); ..." */
function firstSignal(top: string | null): string | null {
  if (!top) return null;
  const seg = top.split(";")[0];
  const name = seg.split("(Score")[0].trim();
  return name || null;
}

export function AlertsTab({
  scopeParams,
}: {
  scopeParams: Record<string, string>;
}) {
  const [tier, setTier] = useState<"" | RiskTier>("");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AlertListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 350);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    const params: Record<string, string | number> = { page, page_size: PAGE_SIZE };
    if (tier) params.tier = tier;
    if (debounced.trim()) params.q = debounced.trim();
    if (scopeParams.mp) params.mp = scopeParams.mp;
    if (scopeParams.state) params.state = scopeParams.state;

    api
      .listAlerts(params)
      .then((r) => {
        setData(r);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [page, tier, debounced, scopeParams.mp, scopeParams.state]);

  const tierCounts = data?.tier_counts ?? {};
  const flaggedTotal = (tierCounts.HIGH ?? 0) + (tierCounts.CRITICAL ?? 0);

  // Identity travels to the dossier (role + scope). The dossier treats an
  // absent role as a public viewer (read-only), so the role is always explicit.
  const investigateQuery = useMemo(() => {
    const p = new URLSearchParams();
    if (scopeParams.role) p.set("role", scopeParams.role);
    if (scopeParams.mp) p.set("mp", scopeParams.mp);
    if (scopeParams.state) p.set("state", scopeParams.state);
    const s = p.toString();
    return s ? `?${s}` : "";
  }, [scopeParams.role, scopeParams.mp, scopeParams.state]);

  const pills: { key: "" | RiskTier; label: string; count: number }[] = [
    { key: "", label: "All flagged", count: flaggedTotal },
    { key: "CRITICAL", label: "Critical", count: tierCounts.CRITICAL ?? 0 },
    { key: "HIGH", label: "High", count: tierCounts.HIGH ?? 0 },
  ];

  return (
    <div className="space-y-5">
      {/* Reports addressed to this authority (D-029) */}
      <ReportsInbox scopeParams={scopeParams} />

      {/* Tier filter pills + context */}
      <section className="panel flex flex-wrap items-center gap-3 p-5">
        <SectionTitle>Risk Queue</SectionTitle>
        <span className="text-xs text-muted">
          HIGH + CRITICAL works ranked for investigation — risk indicators,
          not confirmed findings
        </span>
        <div className="flex flex-wrap gap-2">
          {pills.map((p) => (
            <button
              key={p.label}
              onClick={() => {
                setTier(p.key);
                setPage(1);
              }}
              className={`rounded-full border px-4 py-1.5 text-xs font-bold transition-colors ${
                tier === p.key
                  ? "border-primary bg-primary text-white"
                  : "border-brd text-muted hover:bg-surface-2 hover:text-primary"
              }`}
            >
              {p.label} ({p.count.toLocaleString("en-IN")})
            </button>
          ))}
        </div>
      </section>

      {/* Signal-type breakdown */}
      {data && data.signal_aggregates.length > 0 && (
        <section className="panel p-5">
          <SectionTitle>Signal-type Breakdown (flagged works)</SectionTitle>
          <div className="mt-2">
            <HBarList
              data={data.signal_aggregates.slice(0, 6).map((s) => ({
                label: s.signal,
                value: s.count,
              }))}
              height={180}
            />
          </div>
        </section>
      )}

      {/* Search */}
      <FilterBar
        search={search}
        onSearch={setSearch}
        selects={[]}
        action={
          <span className="text-xs text-muted">
            Search by project ID
          </span>
        }
      />

      {error && <ErrorState message={`Backend unreachable - ${error}`} />}
      {loading && !data && <LoadingState label="Loading alerts..." />}

      {/* Ranked table */}
      {data && (
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-brd bg-surface-2 text-left">
                {["Tier", "Score", "Project ID", "MP", "State", "Top Signal", "Recommended", ""].map(
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
              {data.items.map((a) => (
                <tr
                  key={a.project_id}
                  className="border-b border-brd transition-colors last:border-0 hover:bg-surface-2/60"
                >
                  <td className="px-4 py-3">
                    <TierBadge tier={a.risk_category} small />
                  </td>
                  <td className="px-4 py-3 font-extrabold text-foreground">
                    {a.risk_score_display}
                  </td>
                  <td className="px-4 py-3 font-bold text-primary">
                    {a.project_id.split("|")[0]}
                  </td>
                  <td className="max-w-[180px] px-4 py-3">
                    <span className="block truncate text-muted" title={a.mp_name}>
                      {a.mp_name}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted">{a.state}</td>
                  <td className="px-4 py-3">
                    {firstSignal(a.top_risk_signals) ? (
                      <span className="rounded-full bg-surface-2 px-2.5 py-1 text-[11px] font-medium text-muted">
                        {firstSignal(a.top_risk_signals)}
                      </span>
                    ) : (
                      <span className="na-value text-xs">None recorded</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted">
                    {formatINR(a.recommended_amount)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/investigation/${encodeURIComponent(a.project_id)}${investigateQuery}`}
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
                      message="No alerts match this scope"
                      hint="Try clearing the search or switching tier"
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
