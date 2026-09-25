"use client";

/**
 * app/page.tsx — PARAKH public homepage (compact public edition).
 * Structure follows stitch-home ("Sovereign Saffron Civic", D-024) but at a
 * reduced scale: short hero, tighter rhythm, no long-scroll sections.
 *
 * PUBLIC SCOPE RULE (user decision, 2026-09-07): the public homepage shows
 * AGGREGATE statistics only — no specific flagged works, no critical-work
 * spotlight. Specific alerts belong to authorized roles after login (the
 * archived full-scale v1 homepage was deleted pre-demo — closes the D-026
 * scope leak, Session 16).
 *
 * Every number below is LIVE from the backend. Honesty rules
 * (frontend_card_reference.md §6/§7 + PRD §10.2):
 * - historical-batch disclaimer always visible (never "real-time sync")
 * - risk language only (indicators, never confirmed fraud)
 * - no physical-progress claims (field does not exist in the dataset)
 * - no invented trend deltas, emails, or helpdesk numbers
 */

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { api, type DashboardSummary, type RiskTier } from "@/lib/api";
import { PublicHeader, Footer } from "@/components/shell";
import { ErrorState, LoadingState } from "@/components/ui";

/* ─── Inline icon set (replaces Google Material Symbols CDN) ─────────── */

const ICON_PATHS: Record<string, ReactNode> = {
  wrench: (
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  ),
  users: (
    <>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </>
  ),
  wallet: (
    <>
      <path d="M21 12V7H5a2 2 0 0 1 0-4h14v4" />
      <path d="M3 5v14a2 2 0 0 0 2 2h16v-5" />
      <path d="M18 12a2 2 0 0 0 0 4h4v-4Z" />
    </>
  ),
  banknote: (
    <>
      <rect width="20" height="12" x="2" y="6" rx="2" />
      <circle cx="12" cy="12" r="2" />
      <path d="M6 12h.01M18 12h.01" />
    </>
  ),
  trending: (
    <>
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      <polyline points="16 7 22 7 22 13" />
    </>
  ),
  check: (
    <>
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </>
  ),
  alert: (
    <>
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </>
  ),
  flag: (
    <>
      <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
      <line x1="4" x2="4" y1="22" y2="15" />
    </>
  ),
  arrow: (
    <>
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </>
  ),
  pin: (
    <>
      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
      <circle cx="12" cy="10" r="3" />
    </>
  ),
  building: (
    <>
      <path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z" />
      <path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
      <path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2" />
      <path d="M10 6h4M10 10h4M10 14h4M10 18h4" />
    </>
  ),
  landmark: (
    <>
      <line x1="3" x2="21" y1="22" y2="22" />
      <line x1="6" x2="6" y1="18" y2="11" />
      <line x1="10" x2="10" y1="18" y2="11" />
      <line x1="14" x2="14" y1="18" y2="11" />
      <line x1="18" x2="18" y1="18" y2="11" />
      <polygon points="12 2 20 7 4 7" />
    </>
  ),
  mail: (
    <>
      <rect width="20" height="16" x="2" y="4" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </>
  ),
  phone: (
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
  ),
};

function Icon({ name, className }: { name: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {ICON_PATHS[name]}
    </svg>
  );
}

/* ─── Static content ─────────────────────────────────────────────────── */

/* Portal order = hierarchy: central ministry → state → constituency → district */
const ROLES = [
  {
    key: "mospi",
    icon: "building",
    label: "Central Ministry",
    desc: "National overview & directives",
  },
  {
    key: "sno",
    icon: "flag",
    label: "State Nodal Officer",
    desc: "State oversight & audit review",
  },
  {
    key: "mp",
    icon: "landmark",
    label: "Member of Parliament",
    desc: "Constituency allocation dashboard",
  },
  {
    key: "dm",
    icon: "building",
    label: "District Magistrate",
    desc: "Field verification · demo scope",
  },
];

const TIER_META: { tier: RiskTier; label: string }[] = [
  { tier: "LOW", label: "Low Risk" },
  { tier: "MEDIUM", label: "Medium Risk" },
  { tier: "HIGH", label: "High Risk" },
  { tier: "CRITICAL", label: "Critical" },
];

/* ─── Page ───────────────────────────────────────────────────────────── */

export default function HomePage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .dashboardSummary()
      .then(setSummary)
      .catch((e) => setError(String(e)));
  }, []);

  const inrCr = (v: number) =>
    `₹${(v / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 0 })} Cr`;

  const pct = (n: number, d: number) =>
    d > 0 ? `${((n / d) * 100).toFixed(1)}%` : "—";

  const total = summary?.total_works ?? 0;

  return (
    <div className="theme-saffron flex min-h-screen flex-col">
      <PublicHeader />

      <main className="w-full">
        {/* ─── Hero: compact saffron gradient + parliament watermark ──── */}
        <section className="relative overflow-hidden hero-saffron text-white">
          <div
            className="pointer-events-none absolute inset-0 bg-contain bg-center bg-no-repeat opacity-15"
            style={{ backgroundImage: "url('/theme/parliament-cutout.png')" }}
          />
          <div className="pointer-events-none absolute -bottom-16 -right-16 h-64 w-64 rounded-full bg-primary-tint-dim/20 blur-3xl" />

          <div className="relative mx-auto flex max-w-7xl flex-col items-center justify-between gap-6 px-4 pb-16 pt-10 sm:px-6 lg:flex-row lg:px-8 lg:pb-20 lg:pt-12">
            {/* Left: text */}
            <div className="z-10 max-w-2xl text-center lg:text-left">
              <span className="mb-3 inline-flex items-center gap-2 rounded-full bg-white/15 px-3.5 py-1 text-[10px] font-semibold tracking-wide text-white backdrop-blur-md">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-soft" />
                Historical batch data · Risk indicators only
              </span>
              <h1 className="font-display text-4xl font-bold leading-tight tracking-wide drop-shadow-sm sm:text-5xl">
                PARAKH
              </h1>
              <p className="mt-1.5 text-base font-semibold tracking-wide text-primary-tint sm:text-lg">
                Project Anomaly &amp; Risk Assessment Knowledge Hub
              </p>
              <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-white/85 lg:mx-0">
                AI-powered risk intelligence for MPLADS — surfacing potential
                anomalies across works, payments and vendors so oversight teams
                can prioritise investigation of public funds.
              </p>
              <div className="mt-5 flex flex-wrap items-center justify-center gap-2.5 lg:justify-start">
                <a
                  href="#overview"
                  className="flex items-center gap-2 rounded-full bg-surface-raised px-5 py-2.5 text-xs font-bold text-primary shadow-md transition-all hover:scale-[1.03] hover:shadow-xl"
                >
                  Explore the Overview
                </a>
                <a
                  href="#portals"
                  className="flex items-center gap-2 rounded-full border border-white/40 bg-white/10 px-5 py-2.5 text-xs font-semibold text-white backdrop-blur-md transition-colors hover:bg-white/20"
                >
                  Role-Based Access
                  <Icon name="arrow" className="h-3.5 w-3.5" />
                </a>
                <Link
                  href="/citizen"
                  className="flex items-center gap-2 rounded-full border border-white/40 bg-white/10 px-5 py-2.5 text-xs font-semibold text-white backdrop-blur-md transition-colors hover:bg-white/20"
                >
                  Citizen Portal
                  <Icon name="users" className="h-3.5 w-3.5" />
                </Link>
              </div>
            </div>

            {/* Right: PARAKH emblem card */}
            <div className="relative flex w-56 flex-shrink-0 items-center justify-center sm:w-64 lg:w-72">
              <div className="relative flex aspect-[3/2] w-full items-center justify-center rounded-2xl bg-white/10 p-3 shadow-2xl backdrop-blur-sm">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  alt="PARAKH emblem (transparent)"
                  className="h-full w-full object-contain drop-shadow-[0_10px_20px_rgba(0,0,0,0.35)] transition-transform duration-500 hover:scale-105"
                  src="/theme/parakh-emblem.png"
                />
                <span className="absolute bottom-3 right-3 flex items-center gap-1 rounded-full bg-white/90 px-2.5 py-0.5 text-[10px] font-bold text-primary shadow-md backdrop-blur-md">
                  <Icon name="pin" className="h-3 w-3" />
                  {total > 0
                    ? `${total.toLocaleString("en-IN")} works · Pan-India`
                    : "Pan-India coverage"}
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* ─── Floating role strip over the hero bottom ───────────────── */}
        <section id="portals" className="relative z-20 -mt-9 w-full scroll-mt-24">
          <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="relative z-10 grid grid-cols-2 gap-3 md:grid-cols-4">
              {ROLES.map((r) => (
                <Link
                  key={r.key}
                  href={`/login?role=${r.key}`}
                  className="panel-raised group flex min-h-[96px] flex-col items-center justify-center p-4 text-center transition-all hover:-translate-y-1 hover:shadow-raised"
                >
                  <span className="mb-1.5 flex h-10 w-10 items-center justify-center rounded-full bg-surface-2 text-primary transition-colors group-hover:bg-primary-tint">
                    <Icon name={r.icon} className="h-5 w-5" />
                  </span>
                  <span className="text-sm font-bold leading-tight text-primary transition-colors group-hover:text-primary-container">
                    {r.label}
                  </span>
                  <span className="mt-0.5 text-[10px] font-medium text-muted">
                    {r.desc}
                  </span>
                </Link>
              ))}
            </div>            <p className="mt-2.5 text-center text-[10px] text-muted">
              Demo authentication — any credentials are accepted; no real
              accounts exist.
            </p>
          </div>
        </section>

        {/* ─── National metrics snapshot ──────────────────────────────── */}
        <section
          id="overview"
          className="mx-auto mt-10 w-full max-w-7xl scroll-mt-24 px-4 sm:px-6 lg:px-8"
        >
          <div className="mx-auto mb-6 max-w-3xl text-center">
            <p className="section-label">Consolidated National Register</p>
            <h2 className="mt-1.5 font-display text-xl font-bold tracking-wide text-foreground sm:text-2xl">
              Overview of the Members of Parliament Local Area Development
              Scheme
            </h2>
            <p className="mt-1.5 text-xs text-muted">
              Aggregated from the historical MPLADS batch — 17th &amp; 18th Lok
              Sabha and Rajya Sabha records.
            </p>
          </div>

          {error && (
            <div className="mx-auto max-w-3xl">
              <ErrorState
                message={`Backend unreachable — start it with: cd backend && python -m uvicorn app.main:app --port 8000 (${error})`}
              />
            </div>
          )}
          {!summary && !error && (
            <div className="mx-auto max-w-3xl">
              <LoadingState label="Loading live statistics…" />
            </div>
          )}

          {summary && (
            <>
              {/* 6 KPI metric cards (3-up desktop) */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <KpiCard
                  icon="wrench"
                  label="Total Sanctioned Works"
                  value={summary.total_works.toLocaleString("en-IN")}
                  sub="Recorded across Lok Sabha & Rajya Sabha constituencies"
                />
                <KpiCard
                  icon="users"
                  label="MPs Covered"
                  value={summary.total_mps.toLocaleString("en-IN")}
                  sub="Active parliamentary records in the dataset"
                />
                <KpiCard
                  icon="wallet"
                  label="Funds Allocated"
                  value={inrCr(summary.funds_allocated)}
                  tone="primary"
                  sub="Cumulative sanctioned amounts"
                />
                <KpiCard
                  icon="banknote"
                  label="Funds Utilised"
                  value={inrCr(summary.funds_utilized)}
                  sub={
                    <>
                      <span className="font-semibold text-accent">
                        {summary.utilization_pct}%
                      </span>{" "}
                      aggregate absorption of allocated funds
                    </>
                  }
                />
                <KpiCard
                  icon="trending"
                  label="Avg Financial Progress"
                  value={`${summary.avg_financial_progress}%`}
                  sub="Expenditure vs sanctioned cost across works"
                />
                <KpiCard
                  icon="check"
                  iconTone="accent"
                  label="Completed Works"
                  value={summary.completed_works.toLocaleString("en-IN")}
                  sub={
                    <>
                      <span className="font-semibold text-accent">
                        ({summary.completion_pct}%)
                      </span>{" "}
                      of works — remainder in progress or pending
                    </>
                  }
                />
              </div>

              {/* ─── Risk overview: aggregate tiers + states (public scope:
                    no specific flagged works on the public page) ──────── */}
              <div className="mb-4 mt-10 flex flex-col items-start justify-between gap-3 sm:flex-row">
                <div>
                  <div className="mb-0.5 flex items-center gap-1.5 text-primary">
                    <Icon name="alert" className="h-4 w-4" />
                    <span className="section-label">
                      Automated Detection Engines
                    </span>
                  </div>
                  <h3 className="font-display text-xl font-bold tracking-wide text-foreground sm:text-2xl">
                    MPLADS Risk &amp; Anomaly Overview
                  </h3>
                </div>
                <span className="rounded-full bg-surface-2 px-3 py-1 text-[10px] font-semibold text-primary">
                  Batch scoring · {total.toLocaleString("en-IN")} works
                </span>
              </div>

              <div className="grid grid-cols-1 items-stretch gap-4 lg:grid-cols-2">
                {/* Aggregate tier distribution */}
                <div className="panel p-5">
                  <h4 className="mb-3 text-sm font-bold text-foreground">
                    Risk Classification Tiers
                  </h4>
                  <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                    {TIER_META.map(({ tier, label }) => {
                      const count = summary.tier_distribution[tier] ?? 0;
                      return (
                        <div
                          key={tier}
                          className="rounded-xl bg-surface-raised p-3 text-left shadow-sm"
                        >
                          <span
                            className="text-[10px] font-bold uppercase tracking-wider"
                            style={{ color: `var(--tier-${tier.toLowerCase()})` }}
                          >
                            {label}
                          </span>
                          <div className="mt-0.5 text-lg font-extrabold text-foreground">
                            {count.toLocaleString("en-IN")}
                          </div>
                          <span className="text-[10px] text-muted">
                            {tier === "CRITICAL"
                              ? "Action required"
                              : `${pct(count, total)} of all works`}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Aggregate states ranking */}
                <div className="panel p-5">
                  <div className="mb-3 flex items-center justify-between">
                    <h4 className="text-sm font-bold text-foreground">
                      States with Highest Anomaly Flags
                    </h4>
                    <span className="text-[10px] text-muted">
                      By flagged works count
                    </span>
                  </div>
                  <StateBars states={summary.top_states_by_risk.slice(0, 5)} />
                </div>
              </div>

              <p className="mt-3 text-center text-[11px] text-muted">
                Specific flagged works and investigation dossiers are available
                to authorized users after login.
              </p>
            </>
          )}
        </section>

        {/* ─── About ──────────────────────────────────────────────────── */}
        <section
          id="about"
          className="mx-auto mt-10 w-full max-w-7xl px-4 sm:px-6 lg:px-8"
        >
          <div className="mb-5 text-center">
            <h2 className="font-display text-xl font-bold tracking-wide text-foreground sm:text-2xl">
              About us
            </h2>
          </div>
          <div className="grid grid-cols-1 items-center gap-6 md:grid-cols-12">
            <div className="flex flex-col items-center justify-center text-center md:col-span-4">
              <div className="flex h-32 w-32 items-center justify-center p-2 sm:h-40 sm:w-40">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  alt="PARAKH emblem"
                  className="h-full w-full object-contain drop-shadow-md"
                  src="/theme/Logo-without-name.png"
                />
              </div>
              <div className="mt-1.5 text-sm font-bold tracking-wider text-accent">
                पारदर्शिता के साथ प्रगति की ओर
              </div>
              <div className="text-[11px] font-medium text-muted">
                Ministry of Statistics &amp; Programme Implementation
              </div>
            </div>
            <div className="panel space-y-3 p-6 md:col-span-8">
              <p className="text-sm leading-relaxed text-muted">
                <strong className="text-foreground">PARAKH</strong> is a project
                monitoring platform developed to support the effective
                implementation of public development works under the Members of
                Parliament Local Area Development Scheme (MPLADS) — a
                centralized, transparent view across constituencies, districts,
                and states.
              </p>
              <p className="text-sm leading-relaxed text-muted">
                Automated detection engines flag non-standard expenditure
                spikes, execution delays, duplicate-work patterns, and payment
                irregularities that may require administrative inspection.
              </p>
              <p className="text-sm font-medium text-foreground">
                Through data accessibility, an evidence-backed audit trail, and
                objective risk indicators, PARAKH helps ensure public funds
                translate into robust, timely community assets across the
                nation.
              </p>
            </div>
          </div>
        </section>

        {/* ─── Contact (honest — no fabricated channels) ──────────────── */}
        <section className="mx-auto mt-10 w-full max-w-7xl px-4 pb-10 sm:px-6 lg:px-8">
          <div className="panel-raised flex flex-col items-start justify-between gap-5 p-6 md:flex-row md:items-center">
            <div className="max-w-xl">
              <h3 className="font-display text-lg font-bold text-foreground">
                Contact
              </h3>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">
                PARAKH is a Smart India Hackathon 2026 evaluation build for
                MoSPI problem statement PS 26102. No live helpdesk is operated —
                evaluation queries go through the SIH programme and the PARAKH
                team.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="flex items-center gap-2.5 rounded-xl bg-surface p-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary-tint text-primary">
                  <Icon name="mail" className="h-4 w-4" />
                </span>
                <div className="flex flex-col">
                  <span className="text-[10px] font-medium text-muted">
                    Team
                  </span>
                  <span className="text-xs font-bold text-foreground">
                    PARAKH · SIH 2026
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2.5 rounded-xl bg-surface p-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-accent-soft text-accent">
                  <Icon name="phone" className="h-4 w-4" />
                </span>
                <div className="flex flex-col">
                  <span className="text-[10px] font-medium text-muted">
                    Problem Statement
                  </span>
                  <span className="text-xs font-bold text-foreground">
                    MoSPI · PS 26102
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}

/* ─── Local components ───────────────────────────────────────────────── */

/** Compact KPI metric card: tinted panel, icon, ink metric. */
function KpiCard({
  icon,
  iconTone = "primary",
  label,
  value,
  sub,
  tone = "ink",
}: {
  icon: string;
  iconTone?: "primary" | "accent";
  label: string;
  value: string;
  sub: ReactNode;
  tone?: "ink" | "primary";
}) {
  return (
    <div className="panel flex flex-col justify-between p-4 transition-shadow hover:shadow-raised">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[11px] font-medium text-muted">{label}</span>
        <Icon
          name={icon}
          className={`h-[18px] w-[18px] ${iconTone === "accent" ? "text-accent" : "text-primary"}`}
        />
      </div>
      <div
        className={`text-2xl font-extrabold tracking-tight sm:text-3xl ${
          tone === "primary" ? "text-primary" : "text-foreground"
        }`}
      >
        {value}
      </div>
      <p className="mt-1 text-[10px] font-normal leading-relaxed text-muted">
        {sub}
      </p>
    </div>
  );
}

/** Top states by flagged works — saffron bars in descending shades. */
function StateBars({
  states,
}: {
  states: { state: string; count: number }[];
}) {
  const max = Math.max(1, ...states.map((s) => s.count));
  const shades = ["#964500", "#B75B16", "#B75B16", "#994600", "#994600"];
  return (
    <div className="flex flex-col gap-3">
      {states.map((s, i) => (
        <div key={s.state}>
          <div className="mb-1 flex items-center justify-between text-xs font-semibold text-foreground">
            <span>{s.state}</span>
            <span className="font-bold text-primary">
              {s.count.toLocaleString("en-IN")} Works Flagged
            </span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full rounded-full"
              style={{
                width: `${(s.count / max) * 100}%`,
                background: shades[i % shades.length],
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
