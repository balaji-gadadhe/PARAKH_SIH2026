"use client";

/**
 * app/citizen/page.tsx — Citizen Participation Portal (D-032)
 * ===========================================================
 * The PUBLIC counterpart to the authority dashboards: citizens browse the
 * MPLADS works, upvote the ones that concern them most (Reddit-style), and
 * file reports with photo + location (Step 4).
 *
 * Tabs are deep-linkable (?tab=overview|feed|report), same pattern as the
 * authority dashboard. The Aadhaar+OTP login is SIMULATED and clearly
 * labeled (D-032) — session lives in per-browser localStorage.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { IndiaMap } from "@/components/india-map";
import { Footer, Pagination } from "@/components/shell";
import {
  StatCard,
  TierBadge,
  SectionTitle,
  EmptyState,
  LoadingState,
  ErrorState,
  Pill,
} from "@/components/ui";
import { HBarList } from "@/components/charts";
import { api, formatINR, type StateRiskItem } from "@/lib/api";
import {
  citizenApi,
  getCitizenSession,
  clearCitizenSession,
  CITIZEN_CRITERIA,
  type CitizenSession,
  type CitizenOverviewResponse,
  type CitizenFeedResponse,
  type CitizenFeedItem,
  type CitizenFacetsResponse,
} from "@/lib/citizen-api";

type Tab = "overview" | "feed" | "report";
const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "feed", label: "Critical Feed" },
  { key: "report", label: "Report a Work" },
];

const DEMO_BANNER =
  "Demo prototype: citizen participation data shown here is synthetic seed + demo submissions, clearly labeled. Aadhaar/OTP verification is simulated — production would integrate with UIDAI.";

export default function CitizenPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <CitizenInner />
    </Suspense>
  );
}

function CitizenInner() {
  const router = useRouter();
  const params = useSearchParams();
  const tab = (params.get("tab") as Tab) ?? "overview";
  const stateParam = params.get("state") ?? "";

  // Lazy init reads localStorage on the client's first render — safe because
  // the server only renders the Suspense fallback (useSearchParams pattern).
  const [session, setSession] = useState<CitizenSession | null>(
    () => getCitizenSession()
  );
  const [loginOpen, setLoginOpen] = useState(false);
  /** Work queued from the feed's "Report this work" — the report tab shows
   * its confirm modal first, then the form. Cleared on manual tab change. */
  const [reportTarget, setReportTarget] = useState<CitizenFeedItem | null>(null);
  /** Bumped per queue action so the ReportTab remounts (lazy-init pattern)
   * even when the same work is queued twice in a row. */
  const [reportNonce, setReportNonce] = useState(0);

  function goTab(t: Tab) {
    setReportTarget(null); // manual navigation cancels any queued report
    router.push(`/citizen?tab=${t}`);
  }

  // Full-page login (/citizen/login) returns here with a fresh session.
  // Re-checked on focus too — logging in in another tab updates this one.
  useEffect(() => {
    const sync = () => setSession(getCitizenSession());
    window.addEventListener("focus", sync);
    return () => window.removeEventListener("focus", sync);
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* ─── Header ─────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-brd bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-3">
          <Link href="/" className="flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/theme/Logo-english.png" alt="PARAKH" className="h-9" />
          </Link>
          <span className="section-label ml-1">Citizen Portal</span>
          <nav className="ml-4 hidden gap-1 md:flex">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => goTab(t.key)}
                className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${tab === t.key
                  ? "bg-primary text-white"
                  : "text-muted hover:bg-surface-2 hover:text-primary"
                  }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {session ? (
              <>
                <Pill>
                  👤 {session.maskedId}
                </Pill>
                <button
                  onClick={() => {
                    clearCitizenSession();
                    setSession(null);
                  }}
                  className="rounded-lg border border-brd px-3 py-1.5 text-xs font-semibold text-muted hover:text-primary"
                >
                  Log out
                </button>
              </>
            ) : (
              <button
                onClick={() => setLoginOpen(true)}
                className="rounded-lg bg-accent px-4 py-1.5 text-sm font-bold text-white shadow-sm hover:brightness-110"
              >
                Citizen login
              </button>
            )}
          </div>
          {/* Mobile tabs */}
          <nav className="flex w-full gap-1 md:hidden">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => goTab(t.key)}
                className={`flex-1 rounded-lg px-2 py-1.5 text-xs font-semibold ${tab === t.key
                  ? "bg-primary text-white"
                  : "text-muted hover:bg-surface-2"
                  }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* ─── Demo banner (honesty, D-008/D-032) ─────────────────────── */}
      <div className="border-b border-accent/30 bg-accent/10 px-4 py-2 text-center text-xs font-medium text-foreground">
        ⚠️ {DEMO_BANNER}
      </div>

      {/* ─── Body ───────────────────────────────────────────────────── */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        {tab === "overview" && (
          <OverviewTab session={session} onNeedLogin={() => setLoginOpen(true)} onReport={(work) => {
            setReportTarget(work);
            setReportNonce((n) => n + 1);
            router.push("/citizen?tab=report");
          }} />
        )}
        {tab === "feed" && (
          <FeedTab
            key={stateParam}
            session={session}
            initialState={stateParam}
            onNeedLogin={() => setLoginOpen(true)}
            onReport={(work) => {
              setReportTarget(work);
              setReportNonce((n) => n + 1);
              router.push("/citizen?tab=report");
            }}
          />
        )}
        {tab === "report" && (
          <ReportTab
            key={`report-${reportTarget?.project_id ?? "blank"}-${reportNonce}`}
            session={session}
            onLogin={() => setLoginOpen(true)}
            prePicked={reportTarget}
          />
        )}
      </main>

      <Footer />

      {loginOpen && <CitizenLoginGate onClose={() => setLoginOpen(false)} />}
    </div>
  );
}

/* ─── Login gate dialog: "you need to log in" -> full login page ───────── */

function CitizenLoginGate({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="panel w-full max-w-sm p-6 text-center"
        onClick={(e) => e.stopPropagation()}
      >
        <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-accent-soft text-2xl text-accent">
          🔐
        </span>
        <h2 className="mt-3 font-display text-lg font-bold text-primary">
          Log in to participate
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          Upvotes and reports carry a{" "}
          <strong className="text-foreground">verified demo identity</strong> —
          one person, one vote per work. Log in with a demo Aadhaar + OTP (10
          seconds, nothing real is stored).
        </p>
        <div className="mt-5 flex flex-col gap-2">
          <Link
            href="/citizen/login"
            className="rounded-lg bg-accent px-4 py-2.5 text-sm font-bold text-white transition hover:brightness-110"
          >
            Go to login →
          </Link>
          <button
            onClick={onClose}
            className="rounded-lg border border-brd px-4 py-2 text-xs font-semibold text-muted transition hover:text-primary"
          >
            Maybe later
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Overview tab ──────────────────────────────────────────────────────── */

function OverviewTab({
  session,
  onReport,
  onNeedLogin,
}: {
  session: CitizenSession | null;
  /** Jump to the Report tab pre-confirmed on this work. */
  onReport?: (work: CitizenFeedItem) => void;
  /** Open the login modal (upvote/report while logged out). */
  onNeedLogin?: () => void;
}) {
  const router = useRouter();
  const [data, setData] = useState<CitizenOverviewResponse | null>(null);
  const [states, setStates] = useState<StateRiskItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    citizenApi
      .overview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    api
      .stateRisk()
      .then((r) => setStates(r.states))
      .catch(() => setStates([])); // map panel degrades gracefully
  }, [refreshTick]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <LoadingState label="Loading participation stats…" />;

  return (
    <div className="flex flex-col gap-6">
      <SectionTitle>Citizen participation — public voice on MPLADS works</SectionTitle>

      {/* Intro + how-it-works strip (compact, homepage-style) */}
      <div className="panel flex flex-col gap-3 p-4 md:flex-row md:items-center">
        <p className="flex-1 text-xs leading-relaxed text-muted">
          <strong className="text-foreground">What this is:</strong> a public
          window on MPLADS works. Citizens upvote the works that concern them
          and file reports with photo + location; the aggregated signal shows
          on each work&apos;s page. Public voice is participation context — it
          never replaces the detection engines.
        </p>
        <ol className="flex shrink-0 flex-col gap-1 text-xs text-muted md:border-l md:border-brd md:pl-4">
          <li>
            ① <strong>Log in</strong> — demo Aadhaar + OTP, 10 seconds
          </li>
          <li>
            ② <strong>Upvote with a reason</strong> in the Critical Feed
          </li>
          <li>
            ③ <strong>Report a work</strong> — photo + location, unverified
          </li>
        </ol>
      </div>

      {/* ─── Row 1: stats + engagement chart (left) · map (right) ────── */}
      <div className="grid gap-4 lg:grid-cols-12">
        {/* Left: participation stats stacked over the by-state chart */}
        <div className="flex flex-col gap-3 lg:col-span-5">
          <div className="grid grid-cols-2 gap-3">
            <StatCard label="Citizens engaged" value={data.total_citizens.toLocaleString("en-IN")} sub="demo identities" />
            <StatCard label="Upvotes cast" value={data.total_upvotes.toLocaleString("en-IN")} sub="one per citizen per work" />
            <StatCard label="Citizen reports" value={data.total_reports.toLocaleString("en-IN")} sub="with photo / location" />
            <StatCard label="Works engaged" value={data.works_engaged.toLocaleString("en-IN")} sub="public attention on" />
          </div>
          <div className="panel flex-1 p-4">
            <h3 className="font-display text-sm font-bold text-primary">
              Participation by state
            </h3>
            <p className="mb-2 text-xs text-faint">Works with citizen engagement.</p>
            {data.by_state.length > 0 ? (
              <HBarList
                data={data.by_state.map((s) => ({ label: s.state, value: s.engaged_works }))}
                height={200}
              />
            ) : (
              <EmptyState message="No engagement yet" />
            )}
          </div>
        </div>

        {/* Right (first): the India map — risk intensity + click-to-feed */}
        <div className="panel p-4 lg:col-span-7">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="font-display text-sm font-bold text-primary">
              States on the map
            </h3>
            <span className="text-[10px] text-faint">click a state → its works in the feed</span>
          </div>
          {states === null ? (
            <LoadingState label="Loading map…" />
          ) : (
            <div className="mx-auto mt-2 max-w-[420px]">
              <IndiaMap
                data={states}
                onSelect={(state) =>
                  router.push(
                    `/citizen?tab=feed&state=${encodeURIComponent(state)}`
                  )
                }
              />
            </div>
          )}
          <p className="mt-2 border-t border-brd pt-2 text-[11px] leading-snug text-muted">
            Shading = <strong>risk intensity</strong> from the detection engines
            (4×critical + 2×high + medium, relative to the worst state). The
            chart on the left shows where <strong>citizen engagement</strong>{" "}
            concentrates — the two don&apos;t always match, and the gap is worth
            investigating. Risk layer = frozen MPLADS batch (2026-09-01);
            engagement = demo participation data.
          </p>
        </div>
      </div>

      {/* ─── Row 2: most upvoted (left) · recent reports (right) ──────── */}
      <div className="grid gap-4 lg:grid-cols-12">
        {/* Top upvoted */}
        <div className="panel p-4 lg:col-span-7">
          <h3 className="font-display text-sm font-bold text-primary">
            🔥 Most upvoted works
          </h3>
          <p className="mb-3 text-xs text-faint">
            Where public concern concentrates — engines flag these too.
          </p>
          <div className="flex flex-col divide-y divide-brd">
            {data.top_upvoted.map((w) => (
              <FeedRow
                key={`${w.project_id}|${w.upvote_count}|${w.voted ? 1 : 0}`}
                item={w}
                session={session}
                compact
                onVoted={() => setRefreshTick((t) => t + 1)}
                onReport={onReport}
                onNeedLogin={onNeedLogin}
              />
            ))}
            {data.top_upvoted.length === 0 && (
              <p className="py-4 text-center text-xs text-muted">No upvotes yet.</p>
            )}
          </div>
        </div>

        {/* Recent reports */}
        <div className="panel p-4 lg:col-span-5">
          <h3 className="font-display text-sm font-bold text-primary">
            Recent citizen reports
          </h3>
          <p className="mb-3 text-xs text-faint">
            Citizen-submitted, unverified — the works page has the full risk picture.
          </p>
          <div className="flex flex-col divide-y divide-brd">
            {data.recent_reports.map((r) => (
              <RecentReportRow key={r.id} report={r} />
            ))}
            {data.recent_reports.length === 0 && (
              <EmptyState message="No citizen reports yet" hint="Be the first from the Report a Work tab" />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function RecentReportRow({ report }: { report: import("@/lib/citizen-api").CitizenReportItem }) {
  const shortId = report.project_id.split("|")[0];
  return (
    <div className="flex flex-wrap items-center gap-2 py-2 text-sm">
      <span className="font-mono text-xs text-muted">{shortId}</span>
      <span className="font-medium text-foreground">
        {report.work_description ?? "Work details not available"}
      </span>
      <TierBadge tier={(report.risk_category as never) ?? "MEDIUM"} small />
      <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-muted">
        {report.criteria.join(" · ")}
      </span>
      <span className="rounded-full border border-brd px-2 py-0.5 text-[10px] font-bold uppercase text-faint">
        {report.is_seed ? "synthetic seed" : "demo submission"} · unverified
      </span>
      {report.has_image && <span title="Photo attached">📷</span>}
      {report.latitude != null && <span title="Location attached">📍</span>}
      <Link
        href={`/investigation/${encodeURIComponent(report.project_id)}`}
        className="ml-auto text-xs font-semibold text-primary underline"
      >
        Investigate →
      </Link>
    </div>
  );
}

/* ─── Feed tab (Reddit-style upvote ranking) ───────────────────────────── */

const TIER_FILTERS = ["", "CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;
const SORTS = [
  { key: "upvotes_desc", label: "Most upvoted" },
  { key: "reports_desc", label: "Most reported" },
  { key: "risk_desc", label: "Highest risk score" },
  { key: "amount_desc", label: "Largest funds" },
] as const;

function FeedTab({
  session,
  initialState = "",
  onReport,
  onNeedLogin,
}: {
  session: CitizenSession | null;
  initialState?: string;
  /** Jump to the Report tab pre-confirmed on this work. */
  onReport?: (work: CitizenFeedItem) => void;
  /** Open the login modal (upvote/report while logged out). */
  onNeedLogin?: () => void;
}) {
  const [data, setData] = useState<CitizenFeedResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [tier, setTier] = useState<string>("");
  const [state, setState] = useState(initialState);
  const [constituency, setConstituency] = useState("");
  const [mp, setMp] = useState("");
  const [sort, setSort] = useState<string>("upvotes_desc");
  const [page, setPage] = useState(1);
  const [facets, setFacets] = useState<CitizenFacetsResponse | null>(null);
  /** Bumped after a vote so the effect refetches (counts are server-side). */
  const [refreshTick, setRefreshTick] = useState(0);

  /** Filter changes reset pagination (event-time, no effect needed). */
  function withReset<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setPage(1);
    };
  }

  /** Facet index for the 'near me' dropdowns — real states/constituencies/MPs. */
  useEffect(() => {
    let cancelled = false;
    citizenApi
      .facets()
      .then((f) => {
        if (!cancelled) setFacets(f);
      })
      .catch(() => { }); // dropdowns degrade to search-only if facets fail
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    citizenApi
      .feed({
        token: session?.token,
        q: q || undefined,
        tier: (tier || undefined) as never,
        state: state || undefined,
        constituency: constituency || undefined,
        mp: mp.trim() || undefined,
        sort,
        page,
        page_size: 20,
      })
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [session, q, tier, state, constituency, mp, sort, page, refreshTick]);

  const areaActive = Boolean(state || constituency || mp.trim());
  const constituencyOptions =
    facets?.states.find((s) => s.state === state)?.constituencies ?? [];

  return (
    <div className="flex flex-col gap-4">
      <SectionTitle>
        Critical works feed — sorted by public concern
      </SectionTitle>

      {/* Row 1 — search + universal filters */}
      <div className="panel flex flex-wrap items-center gap-2 p-3">
        <input
          value={q}
          onChange={(e) => withReset(setQ)(e.target.value)}
          placeholder="Search work description / ID…"
          className="min-w-52 flex-1 rounded-lg border border-brd bg-white px-3 py-1.5 text-sm outline-none focus:border-primary"
        />
        <select
          value={tier}
          onChange={(e) => withReset(setTier)(e.target.value)}
          className="rounded-lg border border-brd bg-white px-2 py-1.5 text-sm"
        >
          {TIER_FILTERS.map((t) => (
            <option key={t} value={t}>
              {t === "" ? "All risk tiers" : t}
            </option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(e) => withReset(setSort)(e.target.value)}
          className="rounded-lg border border-brd bg-white px-2 py-1.5 text-sm"
        >
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              Sort: {s.label}
            </option>
          ))}
        </select>
      </div>

      {/* Row 2 — 'near me' area filters (the citizen-as-judge story):
          pick your state, then your constituency, or search your MP. */}
      <div className="panel flex flex-wrap items-center gap-2 border-l-4 border-l-primary p-3">
        <span className="text-sm font-semibold">📍 Your area</span>
        <select
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            setConstituency(""); // cascade reset — new state, new list
            setPage(1);
          }}
          className="w-48 rounded-lg border border-brd bg-white px-2 py-1.5 text-sm"
        >
          <option value="">All states</option>
          {(facets?.states ?? []).map((s) => (
            <option key={s.state} value={s.state}>
              {s.state} ({s.works})
            </option>
          ))}
        </select>
        <select
          value={constituency}
          onChange={(e) => withReset(setConstituency)(e.target.value)}
          disabled={!state}
          title={
            state
              ? "Constituencies in " + state
              : "Pick a state first — constituencies cascade from it"
          }
          className="w-56 rounded-lg border border-brd bg-white px-2 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          <option value="">
            {state ? "All constituencies" : "Pick a state first…"}
          </option>
          {constituencyOptions.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <input
          value={mp}
          onChange={(e) => withReset(setMp)(e.target.value)}
          placeholder="or MP name…"
          className="w-44 rounded-lg border border-brd bg-white px-3 py-1.5 text-sm outline-none focus:border-primary"
        />
        {areaActive && (
          <button
            onClick={() => {
              setState("");
              setConstituency("");
              setMp("");
              setPage(1);
            }}
            className="rounded-lg border border-brd bg-white px-3 py-1.5 text-sm text-foreground/70 hover:border-primary hover:text-primary"
          >
            ✕ Clear area
          </button>
        )}
        <span className="ml-auto text-xs text-foreground/50">
          {facets
            ? `${facets.total_states} states · ${facets.total_constituencies} constituencies`
            : "loading areas…"}
        </span>
      </div>

      {error && <ErrorState message={error} />}
      {!data && !error && <LoadingState label="Loading feed…" />}

      {data && (
        <>
          <div className="flex flex-col gap-2">
            {data.items.map((w) => (
              <FeedRow
                key={`${w.project_id}|${w.upvote_count}|${w.voted ? 1 : 0}`}
                item={w}
                session={session}
                onVoted={() => setRefreshTick((t) => t + 1)}
                onReport={onReport}
                onNeedLogin={onNeedLogin}
              />
            ))}
            {data.items.length === 0 && (
              <EmptyState message="No works match those filters" hint="Try clearing the search or tier filter" />
            )}
          </div>
          <Pagination
            page={data.page}
            pages={data.pages}
            total={data.total}
            onPage={setPage}
          />
        </>
      )}
    </div>
  );
}

/* ─── One feed row: work + upvote toggle ────────────────────────────────── */

function FeedRow({
  item,
  session,
  compact = false,
  onVoted,
  onReport,
  onNeedLogin,
}: {
  item: CitizenFeedItem;
  session: CitizenSession | null;
  compact?: boolean;
  /** Parent refresh hook — fires after a successful upvote (stats re-fetch). */
  onVoted?: () => void;
  /** Parent hook — jumps to the Report tab pre-confirmed on this work. */
  onReport?: (work: CitizenFeedItem) => void;
  /** Parent hook — opens the login dialog when acting while logged out. */
  onNeedLogin?: () => void;
}) {
  // Local vote state initializes from props; parents remount rows via the
  // React `key` pattern when the server-side counts change (no sync effect).
  const [votes, setVotes] = useState(item.upvote_count);
  const [voted, setVoted] = useState(item.voted ?? false);
  const [busy, setBusy] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const shortId = item.project_id.split("|")[0];

  function flashNotice(msg: string) {
    setNotice(msg);
    window.setTimeout(() => setNotice(null), 4000);
  }

  async function toggleVote() {
    if (!session) {
      // Popup, not a toast: the login dialog opens right here (user call).
      onNeedLogin?.();
      return;
    }
    if (busy) return;
    if (!voted) {
      // Upvoting opens the reason dialog — an upvote carries a "why",
      // which is what makes it a signal instead of a mindless click.
      setDialogOpen(true);
      return;
    }
    // Removing an upvote is immediate (toggle-off).
    await confirmVote([]);
  }

  async function confirmVote(reasons: string[]) {
    if (!session || busy) return;
    setBusy(true);
    setDialogOpen(false);
    try {
      const res = await citizenApi.vote(session.token, item.project_id, reasons);
      setVotes(res.upvote_count);
      setVoted(res.voted);
      if (res.voted) onVoted?.();
    } catch (e) {
      flashNotice(e instanceof Error ? e.message : "Vote failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`flex flex-col gap-2 ${compact ? "py-2" : "panel p-3"}`}>
      {notice && (
        <div
          className="rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent-dark"
          role="status"
        >
          {notice}
        </div>
      )}
      <div className="flex items-stretch gap-3 overflow-hidden">
        {/* Work ID — first column */}
        <div className={`shrink-0 ${compact ? "w-16" : "w-20"} flex flex-col justify-center`}>
          <span className="font-mono text-sm font-bold text-primary">{shortId}</span>
          {!compact && <span className="text-[10px] uppercase tracking-wide text-faint">Work ID</span>}
        </div>

        {/* Work info — capped so the concerns column starts right after it
          instead of floating far right with a dead gap */}
        <div className="min-w-0 max-w-lg flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <TierBadge tier={item.risk_category} small />
            <span
              title="PARAKH composite risk score (0–100, higher = more suspicious)"
              className="font-mono text-xs font-bold text-high"
            >
              {item.risk_score_display}/100
            </span>
            <span className="text-xs text-faint">{item.state}</span>
            {item.report_count > 0 && (
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-bold text-muted">
                {item.report_count} citizen report{item.report_count === 1 ? "" : "s"}
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-sm font-semibold text-foreground">
            {item.work_description ?? "Work details not available"}
          </p>
          <p className="truncate text-xs text-muted">
            {item.mp_name} · {formatINR(item.recommended_amount)} recommended
          </p>
        </div>

        {/* Public concerns — cylinder chips, left-anchored next to the work info */}
        <div className="hidden min-w-40 flex-1 flex-col justify-center gap-1 sm:flex">
          <span className="text-[10px] uppercase tracking-wide text-faint">
            Public concerns
          </span>
          <div className="flex flex-wrap gap-1">
            {item.top_concerns.length > 0
              ? item.top_concerns.slice(0, 3).map((c) => (
                <span
                  key={c.reason}
                  title={`Combined citizen signal: ${c.count} × ${c.reason} — ${c.report_count ?? 0} report(s) + ${c.upvote_count ?? 0} upvote(s)`}
                  className="rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] font-bold text-accent-dark"
                >
                  {c.reason} ×{c.count}
                  {(c.report_count ?? 0) > 0 && (
                    <span className="ml-1 font-semibold text-accent-dark/60">·{c.report_count}r</span>
                  )}
                </span>
              ))
              : (
                <span className="text-[11px] italic text-faint/70">no signals yet</span>
              )}
          </div>
        </div>

        {/* Public satisfaction — citizens' mean 1–5 rating with a color word */}
        <div className="hidden w-24 shrink-0 flex-col justify-center gap-0.5 md:flex">
          <span className="text-[10px] uppercase tracking-wide text-faint">
            Public satisfaction
          </span>
          {item.satisfaction_avg != null ? (
            <>
              <span
                title={`${item.satisfaction_count} citizen rating(s), 1–5 scale`}
                className={`text-sm font-bold ${item.satisfaction_avg <= 1.5
                  ? "text-high"
                  : item.satisfaction_avg <= 2.5
                    ? "text-accent-dark"
                    : "text-low"
                  }`}
              >
                {item.satisfaction_avg.toFixed(1)}/5
              </span>
              <span className="text-[10px] text-muted">
                {item.satisfaction_avg <= 1.5
                  ? "very dissatisfied"
                  : item.satisfaction_avg <= 2.5
                    ? "dissatisfied"
                    : item.satisfaction_avg <= 3.5
                      ? "mixed"
                      : item.satisfaction_avg <= 4.5
                        ? "satisfied"
                        : "very satisfied"}
              </span>
            </>
          ) : (
            <span className="text-[11px] italic text-faint/70">not rated</span>
          )}
        </div>

        {/* Actions — stacked full-label buttons, aligned column */}
        <div className="flex w-36 shrink-0 flex-col items-stretch justify-center gap-1.5">
          <button
            onClick={toggleVote}
            disabled={busy}
            aria-label={voted ? "Remove upvote" : "Upvote this work"}
            className={`flex items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 text-xs font-bold transition ${voted
              ? "border-accent bg-accent text-white shadow-sm"
              : "border-brd bg-white text-muted hover:border-accent hover:text-accent"
              } ${busy ? "opacity-50" : ""}`}
          >
            <span className={`text-sm leading-none ${voted ? "text-white" : "text-accent"}`}>▲</span>
            {votes}
            <span>{voted ? "Upvoted" : "Upvote"}</span>
          </button>
          <button
            onClick={() => {
              if (!session) {
                onNeedLogin?.();
                return;
              }
              onReport?.(item);
            }}
            title="File a report on this work"
            className="flex items-center justify-center gap-1 rounded-lg border border-high/50 bg-high/10 px-2 py-1.5 text-xs font-bold text-high transition hover:bg-high/20"
          >
            ⚠ Report
          </button>
          <Link
            href={`/investigation/${encodeURIComponent(item.project_id)}?from=citizen`}
            className="flex items-center justify-center rounded-lg border border-brd bg-white px-2 py-1.5 text-xs font-semibold text-primary transition hover:border-primary"
          >
            Investigate →
          </Link>
        </div>
      </div>
      {dialogOpen && (
        <VoteReasonDialog
          shortId={shortId}
          busy={busy}
          onCancel={() => setDialogOpen(false)}
          onConfirm={confirmVote}
        />
      )}
    </div>
  );
}

/** Upvote reason dialog — the anti-mindless-spam friction: an upvote must
 * carry a "why" (same tags as reports; both feed the same PSI signal). */
function VoteReasonDialog({
  shortId,
  busy,
  onCancel,
  onConfirm,
}: {
  shortId: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (reasons: string[]) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);

  function toggleTag(key: string) {
    setSelected((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onCancel}
    >
      <div
        className="panel w-full max-w-sm p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-display text-base font-bold text-primary">
          Why does work #{shortId} concern you?
        </h3>
        <p className="mt-1 text-xs text-muted">
          Pick what applies — this is what officials see. Your upvote counts
          once per work; you can remove it any time.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {CITIZEN_CRITERIA.map((c) => {
            const active = selected.includes(c.key);
            return (
              <button
                key={c.key}
                type="button"
                onClick={() => toggleTag(c.key)}
                className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${active
                  ? "border-accent bg-accent text-white"
                  : "border-brd bg-white text-muted hover:border-accent hover:text-accent"
                  }`}
              >
                {c.label}
              </button>
            );
          })}
        </div>
        <p className="mt-3 text-[11px] text-faint">
          Demo: one upvote per citizen per work, enforced server-side.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg border border-brd px-3 py-1.5 text-xs font-semibold text-muted"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(selected)}
            disabled={selected.length === 0 || busy}
            className="rounded-lg bg-accent px-4 py-1.5 text-xs font-bold text-white disabled:opacity-40"
            title={selected.length === 0 ? "Pick at least one reason" : ""}
          >
            {busy ? "Submitting…" : `Upvote (${selected.length} reason${selected.length === 1 ? "" : "s"})`}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Report tab (Step 4): find work → criteria → photo → location ─────── */

const LOCATION_SANITY_LABELS: Record<string, { label: string; cls: string }> = {
  PLAUSIBLE: { label: "📍 location plausible", cls: "border-low/40 bg-low/10 text-low" },
  FAR_FROM_CLAIMED_STATE: { label: "⚠️ location far from the work's state", cls: "border-high/40 bg-high/10 text-high" },
  NO_LOCATION: { label: "no location attached", cls: "border-brd bg-surface-2 text-muted" },
  NO_REFERENCE: { label: "location not checkable", cls: "border-brd bg-surface-2 text-muted" },
};

const DEMO_LOCATION = { lat: 18.5913, lng: 73.7389, label: "Hinjewadi, Pune" };

function ReportTab({
  session,
  onLogin,
  prePicked,
}: {
  session: CitizenSession | null;
  onLogin: () => void;
  /** Work queued from a feed row's "Report this work" button. */
  prePicked?: CitizenFeedItem | null;
}) {
  // Work finder (searches the frozen works list via the feed endpoint)
  const [query, setQuery] = useState("");
  const [fState, setFState] = useState("");
  const [fConstituency, setFConstituency] = useState("");
  const [fMp, setFMp] = useState("");
  const [fTier, setFTier] = useState("");
  const [results, setResults] = useState<CitizenFeedItem[] | null>(null);
  const [resultsTotal, setResultsTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const [confirming, setConfirming] = useState<CitizenFeedItem | null>(prePicked ?? null);
  const [picked, setPicked] = useState<CitizenFeedItem | null>(null);
  const [facets, setFacets] = useState<CitizenFacetsResponse | null>(null);

  /** A work queued from the feed's "Report this work" lands here as the
   * initial confirm modal — the parent remounts this tab via `key` when it
   * queues a work, so lazy state-init sees the fresh prop (no sync effect). */

  /** Same facet index the feed uses — real states/constituencies/MPs. */
  useEffect(() => {
    let cancelled = false;
    citizenApi
      .facets()
      .then((f) => {
        if (!cancelled) setFacets(f);
      })
      .catch(() => { }); // degrade to text search if facets fail
    return () => {
      cancelled = true;
    };
  }, []);

  // Report fields
  const [criteria, setCriteria] = useState<string[]>([]);
  const [satisfaction, setSatisfaction] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [manualLat, setManualLat] = useState("");
  const [manualLng, setManualLng] = useState("");
  const [locError, setLocError] = useState<string | null>(null);

  // Submit / result state
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<import("@/lib/citizen-api").CitizenReportItem | null>(null);

  function searchWorks() {
    if (searching) return;
    const q = query.trim();
    if (!q && !fState.trim() && !fConstituency.trim() && !fMp.trim() && !fTier) return;
    setSearching(true);
    citizenApi
      .feed({
        q: q || undefined,
        state: fState.trim() || undefined,
        constituency: fConstituency.trim() || undefined,
        mp: fMp.trim() || undefined,
        tier: (fTier || undefined) as never,
        page_size: 20,
        sort: "risk_desc",
      })
      .then((r) => {
        setResults(r.items);
        setResultsTotal(r.total);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSearching(false));
  }

  function onImageChosen(f: File | null) {
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setImage(f);
    setImagePreview(f ? URL.createObjectURL(f) : null);
  }

  function useMyLocation() {
    setLocError(null);
    setCoords({ lat: DEMO_LOCATION.lat, lng: DEMO_LOCATION.lng });
  }

  const effectiveCoords = coords ?? (
    /^-?\d+(\.\d+)?$/.test(manualLat.trim()) && /^-?\d+(\.\d+)?$/.test(manualLng.trim())
      ? { lat: Number(manualLat), lng: Number(manualLng) }
      : null
  );

  const canSubmit =
    !!session &&
    !!picked &&
    !!coords &&
    (criteria.length > 0 || satisfaction != null) &&
    !busy;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !picked || !canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const res = await citizenApi.createReport({
        token: session.token,
        projectId: picked.project_id,
        criteria,
        satisfaction,
        comment: comment.trim() || undefined,
        image,
        latitude: effectiveCoords?.lat ?? null,
        longitude: effectiveCoords?.lng ?? null,
      });
      setDone(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  }

  function resetAll() {
    setPicked(null);
    setConfirming(null);
    setCriteria([]);
    setSatisfaction(null);
    setComment("");
    onImageChosen(null);
    setCoords(null);
    setManualLat("");
    setManualLng("");
    setDone(null);
    setError(null);
  }

  /* ─── Not logged in ──────────────────────────────────────────── */
  if (!session) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <span className="text-4xl">🔐</span>
        <h2 className="font-display text-xl font-bold text-primary">
          Log in to file a report
        </h2>
        <p className="max-w-md text-sm text-muted">
          Reports carry your demo citizen identity, and every report is labeled{" "}
          <strong>citizen-submitted, unverified</strong>. Login is a demo
          Aadhaar + OTP — 10 seconds.
        </p>
        <button
          onClick={onLogin}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-bold text-white"
        >
          Citizen login (demo Aadhaar)
        </button>
      </div>
    );
  }

  /* ─── Success card ───────────────────────────────────────────── */
  if (done) {
    const sanity = done.location_sanity
      ? LOCATION_SANITY_LABELS[done.location_sanity]
      : undefined;
    return (
      <div className="panel mx-auto flex max-w-lg flex-col items-center gap-3 p-8 text-center">
        <span className="text-4xl">✅</span>
        <h2 className="font-display text-xl font-bold text-primary">Report filed</h2>
        <p className="text-sm text-muted">
          Work <span className="font-mono font-bold">{done.project_id.split("|")[0]}</span>
          {done.satisfaction != null && (
            <>
              {" · rated "}
              <span className="font-bold text-accent-dark">{done.satisfaction}/5</span>
            </>
          )}
          {done.criteria.length > 0 && <>{" · "}{done.criteria.join(", ")}</>}
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          <span className="rounded-full border border-brd bg-surface-2 px-3 py-1 text-[11px] font-bold uppercase text-muted">
            citizen-submitted · unverified
          </span>
          {sanity && (
            <span className={`rounded-full border px-3 py-1 text-[11px] font-bold ${sanity.cls}`}>
              {sanity.label}
            </span>
          )}
          {done.has_image && (
            <span className="rounded-full border border-brd px-3 py-1 text-[11px] text-muted">
              📷 photo stored
            </span>
          )}
          {done.satisfaction != null && (
            <span className="rounded-full border border-brd px-3 py-1 text-[11px] text-muted">
              ⭐ satisfaction signal
            </span>
          )}
        </div>
        <p className="text-xs text-faint">
          It now shows on this work&apos;s page under “What the public says” and
          counts toward its Public Satisfaction Indicator — as an unverified
          participation signal, never as evidence.
        </p>
        <div className="mt-2 flex gap-2">
          <button
            onClick={resetAll}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-bold text-white"
          >
            File another report
          </button>
          <Link
            href={`/investigation/${encodeURIComponent(done.project_id)}?from=citizen`}
            className="rounded-lg border border-brd px-4 py-2 text-sm font-semibold text-primary"
          >
            View the work →
          </Link>
        </div>
      </div>
    );
  }

  /* ─── The form ───────────────────────────────────────────────── */
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <SectionTitle>Report a work — tell officials what looks wrong</SectionTitle>

      {error && <ErrorState message={error} />}

      {/* Step 1 — find + confirm the work */}
      <div className="panel p-4">
        <h3 className="font-display text-sm font-bold text-primary">① Which work?</h3>
        {picked ? (
          <div className="mt-2 flex items-center gap-3 rounded-lg border border-accent/40 bg-accent/5 p-3">
            <span className="font-mono text-sm font-bold text-primary">
              {picked.project_id.split("|")[0]}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-foreground">
                {picked.work_description ?? "Work details not available"}
              </p>
              <p className="text-xs text-muted">
                {picked.mp_name} · {picked.state}
              </p>
            </div>
            <TierBadge tier={picked.risk_category} small />
            <button
              onClick={() => setPicked(null)}
              className="text-xs font-semibold text-muted underline"
            >
              change
            </button>
          </div>
        ) : (
          <>
            <p className="mt-1 text-xs text-faint">
              Search by work ID / description, or filter by your area (state →
              constituency), MP, or risk tier.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && searchWorks()}
                placeholder="e.g. water supply, road…"
                className="min-w-44 flex-1 rounded-lg border border-brd bg-white px-3 py-2 text-sm outline-none focus:border-primary"
              />
              <select
                value={fState}
                onChange={(e) => {
                  setFState(e.target.value);
                  setFConstituency(""); // cascade reset
                }}
                className="w-44 rounded-lg border border-brd bg-white px-2 py-2 text-sm"
              >
                <option value="">All states</option>
                {(facets?.states ?? []).map((s) => (
                  <option key={s.state} value={s.state}>
                    {s.state} ({s.works})
                  </option>
                ))}
              </select>
              <select
                value={fConstituency}
                onChange={(e) => setFConstituency(e.target.value)}
                disabled={!fState}
                title={
                  fState
                    ? "Constituencies in " + fState
                    : "Pick a state first — constituencies cascade from it"
                }
                className="w-48 rounded-lg border border-brd bg-white px-2 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="">
                  {fState ? "All constituencies" : "Pick a state first…"}
                </option>
                {(facets?.states.find((s) => s.state === fState)?.constituencies ?? []).map(
                  (c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  )
                )}
              </select>
              <input
                value={fMp}
                onChange={(e) => setFMp(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && searchWorks()}
                placeholder="MP name"
                className="w-36 rounded-lg border border-brd bg-white px-3 py-2 text-sm outline-none focus:border-primary"
              />
              <select
                value={fTier}
                onChange={(e) => setFTier(e.target.value)}
                className="rounded-lg border border-brd bg-white px-2 py-2 text-sm"
              >
                <option value="">All tiers</option>
                {TIER_FILTERS.filter(Boolean).map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <button
                onClick={searchWorks}
                disabled={searching}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-40"
              >
                {searching ? "Searching…" : "Search"}
              </button>
            </div>
            {results && (
              <div className="mt-3 flex flex-col rounded-lg border border-brd">
                <div className="flex max-h-80 flex-col divide-y divide-brd overflow-y-auto">
                  {results.map((w) => (
                    <button
                      key={w.project_id}
                      onClick={() => setConfirming(w)}
                      className="flex shrink-0 items-center gap-3 px-3 py-2 text-left hover:bg-surface-2"
                    >
                      <span className="font-mono text-xs font-bold text-primary">
                        {w.project_id.split("|")[0]}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm text-foreground">
                        {w.work_description ?? "Work details not available"}
                      </span>
                      <span className="hidden text-xs text-faint sm:inline">{w.state}</span>
                      <TierBadge tier={w.risk_category} small />
                    </button>
                  ))}
                  {results.length === 0 && (
                    <p className="px-3 py-3 text-center text-xs text-muted">
                      No works matched — try another search or filter.
                    </p>
                  )}
                </div>
                {results.length > 0 && (
                  <p className="border-t border-brd px-3 py-1.5 text-center text-[11px] text-faint">
                    {results.length === resultsTotal
                      ? `${resultsTotal} work${resultsTotal === 1 ? "" : "s"} matched`
                      : `Top ${results.length} of ${resultsTotal} matches — narrow the search or pick from these`}
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Confirm-this-work popup (between search and the form) */}
      {confirming && !picked && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setConfirming(null)}
        >
          <div
            className="panel w-full max-w-lg border-accent/40 p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h3 className="font-display text-base font-bold text-primary">
                Is this the work you want to report?
              </h3>
              <button
                onClick={() => setConfirming(null)}
                className="text-lg leading-none text-muted hover:text-foreground"
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            <p className="mt-1 text-xs text-muted">
              Reports are tied to one specific work — check the details below
              before continuing.
            </p>
            <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg bg-surface-2 p-3 text-sm md:grid-cols-3">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wide text-faint">Work ID</p>
                <p className="font-mono font-bold text-primary">{confirming.project_id.split("|")[0]}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wide text-faint">Risk</p>
                <TierBadge tier={confirming.risk_category} small />
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wide text-faint">Risk score</p>
                <p className="font-bold text-foreground">{confirming.risk_score_display}/100</p>
              </div>
              <div className="col-span-2 md:col-span-3">
                <p className="text-[10px] font-bold uppercase tracking-wide text-faint">Description</p>
                <p className="text-foreground">{confirming.work_description ?? "Not available"}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wide text-faint">MP</p>
                <p className="text-foreground">{confirming.mp_name}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wide text-faint">State</p>
                <p className="text-foreground">{confirming.state}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wide text-faint">Funds recommended</p>
                <p className="text-foreground">{formatINR(confirming.recommended_amount)}</p>
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirming(null)}
                className="rounded-lg border border-brd px-4 py-1.5 text-xs font-semibold text-muted"
              >
                No, search again
              </button>
              <button
                onClick={() => {
                  setPicked(confirming);
                  setConfirming(null);
                }}
                className="rounded-lg bg-accent px-4 py-1.5 text-xs font-bold text-white"
              >
                Yes, report this work
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 2 — satisfaction + what's wrong */}
      <div className={`panel p-4 ${picked ? "" : "opacity-50"}`}>
        <h3 className="font-display text-sm font-bold text-primary">
          ② How satisfied are you with this work?
        </h3>
        <p className="mt-1 text-xs text-faint">
          1 = very dissatisfied · 5 = very satisfied. Rating alone is enough —
          problems below are optional.
        </p>
        <div className="mt-2 flex items-center gap-2">
          {[1, 2, 3, 4, 5].map((n) => {
            const active = satisfaction != null && n <= satisfaction;
            return (
              <button
                key={n}
                type="button"
                disabled={!picked}
                onClick={() => setSatisfaction(satisfaction === n ? null : n)}
                aria-label={`Satisfaction ${n} of 5`}
                className={`h-9 w-9 rounded-lg border text-sm font-bold transition disabled:cursor-not-allowed ${active
                  ? "border-accent bg-accent text-white"
                  : "border-brd bg-white text-muted hover:border-accent hover:text-accent"
                  }`}
              >
                {n}
              </button>
            );
          })}
          {satisfaction != null && (
            <span className="ml-1 text-xs font-semibold text-accent-dark">
              {satisfaction === 1 && "Very dissatisfied"}
              {satisfaction === 2 && "Dissatisfied"}
              {satisfaction === 3 && "Neutral"}
              {satisfaction === 4 && "Satisfied"}
              {satisfaction === 5 && "Very satisfied"}
            </span>
          )}
        </div>

        <h4 className="mt-4 text-xs font-bold uppercase tracking-wide text-muted">
          Spotted a problem? (optional)
        </h4>
        <p className="mt-0.5 text-xs text-faint">
          Same tags as upvotes — they count toward the same public signal.
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {CITIZEN_CRITERIA.map((c) => {
            const active = criteria.includes(c.key);
            return (
              <button
                key={c.key}
                type="button"
                disabled={!picked}
                onClick={() =>
                  setCriteria((prev) =>
                    prev.includes(c.key)
                      ? prev.filter((k) => k !== c.key)
                      : [...prev, c.key]
                  )
                }
                className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed ${active
                  ? "border-accent bg-accent text-white"
                  : "border-brd bg-white text-muted hover:border-accent hover:text-accent"
                  }`}
              >
                {c.label}
              </button>
            );
          })}
        </div>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          disabled={!picked}
          rows={3}
          maxLength={2000}
          placeholder="Tell officials more — what you saw at the site, since when… (optional)"
          className="mt-3 w-full rounded-lg border border-brd bg-white px-3 py-2 text-sm outline-none focus:border-primary"
        />
      </div>

      {/* Step 3 — photo + location */}
      <div className={`panel p-4 ${picked ? "" : "opacity-50"}`}>
        <h3 className="font-display text-sm font-bold text-primary">③ Evidence (optional)</h3>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-muted">
              📷 Photo of the site
            </label>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={!picked}
              onChange={(e) => onImageChosen(e.target.files?.[0] ?? null)}
              className="mt-1.5 w-full text-xs text-muted file:mr-2 file:rounded-lg file:border-0 file:bg-primary-tint file:px-3 file:py-1.5 file:text-xs file:font-bold file:text-primary"
            />
            {imagePreview && (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={imagePreview}
                alt="Upload preview"
                className="mt-2 h-28 w-full rounded-lg border border-brd object-cover"
              />
            )}
            <p className="mt-1 text-[11px] text-faint">
              JPEG/PNG/WebP, max 5 MB. Stored as-is — never “verified”.
            </p>
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-muted">
              📍 Location
            </label>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={useMyLocation}
                className="rounded-lg border border-brd bg-white px-3 py-1.5 text-xs font-bold text-primary"
              >
                Choose location
              </button>
              {coords && (
                <span className="font-mono text-xs text-muted">
                  {coords.lat}, {coords.lng}
                </span>
              )}
            </div>
            {coords && (
              <p className="mt-1 text-[11px] font-semibold text-accent-dark">
                {DEMO_LOCATION.label}
              </p>
            )}
            <div className="mt-2 flex items-center gap-2">
              <input
                value={manualLat}
                onChange={(e) => setManualLat(e.target.value)}
                disabled={!picked}
                placeholder="lat"
                className="w-24 rounded-lg border border-brd bg-white px-2 py-1 font-mono text-xs outline-none focus:border-primary"
              />
              <input
                value={manualLng}
                onChange={(e) => setManualLng(e.target.value)}
                disabled={!picked}
                placeholder="lng"
                className="w-24 rounded-lg border border-brd bg-white px-2 py-1 font-mono text-xs outline-none focus:border-primary"
              />
              <span className="text-[10px] text-faint">manual fallback</span>
            </div>
            {locError && <p className="mt-1 text-[11px] text-high">{locError}</p>}
            <p className="mt-1 text-[11px] text-faint">
              Claimed coordinates only — a coarse sanity check may flag them;
              nothing is verified.
            </p>
          </div>
        </div>
      </div>

      {/* Submit */}
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-faint">
          Every report is labeled <strong>citizen-submitted, unverified</strong> —
          a participation signal, never evidence.
        </p>
        <button
          onClick={submit}
          disabled={!canSubmit}
          className="shrink-0 rounded-lg bg-accent px-6 py-2.5 text-sm font-bold text-white shadow-sm disabled:opacity-40"
          title={
            picked && !coords
              ? "Choose a location before submitting"
              : picked && criteria.length === 0 && satisfaction == null
                ? "Give a satisfaction rating or pick at least one problem"
                : ""
          }
        >
          {busy
            ? "Filing report…"
            : satisfaction != null && criteria.length === 0
              ? "Submit feedback"
              : "File report"}
        </button>
      </div>
    </div>
  );
}
