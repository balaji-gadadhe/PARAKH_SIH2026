"use client";

/**
 * components/shell.tsx — page shells: public header, dashboard header,
 * footer, filter bar, pagination. Styling via tokens in globals.css (D-023).
 */

import Link from "next/link";
import { useState, type ReactNode } from "react";

/* ─── Brand logo ─────────────────────────────────────────────────────── */

export function Brand({ size = 44 }: { size?: number }) {
  return (
    <Link href="/" className="flex shrink-0 items-center gap-3">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/theme/Logo-english.png"
        alt="PARAKH logo"
        style={{ height: size, width: "auto" }}
      />
    </Link>
  );
}

/* ─── Public header ──────────────────────────────────────────────────── */

export function PublicHeader() {
  return (
    <header className="sticky top-0 z-40 bg-surface-raised/95 shadow-[0_4px_16px_-2px_rgba(200,104,36,0.08)] backdrop-blur-md">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between gap-6 px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/theme/Parakh-name.png"
            alt="PARAKH"
            className="h-9 w-auto"
          />
          <span className="hidden border-l border-brd pl-4 text-[11px] leading-tight text-muted sm:block">
            Ministry of Statistics &amp; Programme Implementation · Govt. of
            India
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden items-center gap-2 rounded-full bg-primary-tint px-3 py-1.5 text-[11px] font-semibold text-primary-dark sm:flex">
            <span className="h-2 w-2 rounded-full bg-primary" />
            Demo Data Mode
          </span>
          <Link href="/login?role=mospi" className="btn-portal px-5 py-2.5 text-sm">
            Official Login
          </Link>
        </div>
      </div>
      <div className="h-[2px] w-full bg-gradient-to-r from-primary via-primary-container to-primary-dark" />
    </header>
  );
}

/* ─── Dashboard header ───────────────────────────────────────────────── */

export interface DashTab {
  key: string;
  label: string;
  /** Optional unread-style pill (e.g. reports awaiting attention). */
  badge?: number;
}

export function DashHeader({
  tabs,
  active,
  onTab,
  userLabel,
  scopeNote,
  onLogout,
  bellCount = 0,
}: {
  tabs: DashTab[];
  active: string;
  onTab: (key: string) => void;
  userLabel: string;
  scopeNote?: string;
  onLogout: () => void;
  /** Unread notifications for the bell (reports awaiting attention). */
  bellCount?: number;
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-brd bg-surface shadow-sm">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4 sm:px-6 lg:px-8">
        <Brand size={36} />
        <nav className="flex flex-1 items-center gap-1 overflow-x-auto">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => onTab(t.key)}
              className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                active === t.key
                  ? "bg-primary-tint font-bold text-primary"
                  : "text-muted hover:bg-surface-2 hover:text-primary"
              }`}
            >
              {t.label}
              {t.badge ? (
                <span className="rounded-full bg-critical px-1.5 py-0.5 text-[10px] font-bold leading-none text-white">
                  {t.badge}
                </span>
              ) : null}
            </button>
          ))}
        </nav>
        <div className="hidden items-center gap-3 lg:flex">
          <div className="text-right leading-tight">
            <div className="text-xs font-semibold text-foreground">{userLabel}</div>
            {scopeNote && <div className="text-[10px] text-faint">{scopeNote}</div>}
          </div>
          <button
            onClick={() => onTab("alerts")}
            aria-label={`Notifications: ${bellCount} unread`}
            title={`Notifications: ${bellCount} unread — go to Alerts`}
            className="relative rounded-full border border-brd p-2 text-muted transition-colors hover:bg-surface-2 hover:text-primary"
          >
            {/* Bell outline (inline SVG — offline-demo safe) */}
            <svg
              className="h-4.5 w-4.5"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
            >
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            {bellCount > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-critical px-1 text-[10px] font-bold leading-none text-white">
                {bellCount > 9 ? "9+" : bellCount}
              </span>
            )}
          </button>
          <button
            onClick={onLogout}
            className="rounded-lg border border-brd px-3 py-1.5 text-xs font-semibold text-muted transition-colors hover:bg-surface-2 hover:text-primary"
          >
            Logout
          </button>
        </div>
      </div>
      {/* Persistent honesty chip on all dashboard screens */}
      <div className="border-t border-brd bg-surface-2">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-1.5 sm:px-6 lg:px-8">
          <span className="disclaimer-chip !border-brd !bg-surface">
            Historical batch data · Risk indicators only — requires investigation, not confirmed findings
          </span>
          {scopeNote && (
            <span className="text-[10px] font-semibold uppercase tracking-wider text-accent-dark lg:hidden">
              {scopeNote}
            </span>
          )}
        </div>
      </div>
    </header>
  );
}

/* ─── Footer ─────────────────────────────────────────────────────────── */

export function Footer() {
  return (
    <footer className="mt-auto border-t border-brd bg-surface">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="flex flex-col items-center justify-between gap-4 md:flex-row">
          <div className="flex flex-col items-center gap-1 md:items-start">
            <div className="flex items-center gap-2">
              <span className="font-display text-lg font-bold uppercase tracking-widest text-primary">
                PARAKH
              </span>
              <span className="text-xs text-muted">
                MPLADS Risk Intelligence System
              </span>
            </div>
            <p className="text-center text-xs text-muted md:text-left">
              Project Anomaly &amp; Risk Assessment Knowledge Hub · Smart India
              Hackathon 2026 · MoSPI PS 26102
            </p>
          </div>
          <p className="max-w-md text-center text-[11px] leading-relaxed text-muted md:text-right">
            Detection outputs are risk indicators for human review — never
            confirmed findings. Historical batch data; no live MoSPI sync.
          </p>
        </div>
      </div>
    </footer>
  );
}

/* ─── Filter bar ─────────────────────────────────────────────────────── */

export interface FilterSelect {
  key: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
}

export function FilterBar({
  search,
  onSearch,
  selects,
  onSelect,
  action,
}: {
  search: string;
  onSearch: (v: string) => void;
  selects?: FilterSelect[];
  onSelect?: (key: string, value: string) => void;
  action?: ReactNode;
}) {
  return (
    <div className="panel flex flex-wrap items-center gap-3 p-4">
      <div className="relative min-w-[220px] flex-1">
        <input
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search ID, description, name…"
          className="w-full rounded-lg border border-brd bg-surface px-3.5 py-2.5 text-sm text-foreground placeholder:text-faint focus:border-primary focus:outline-none"
        />
      </div>
      {selects?.map((s) => (
        <select
          key={s.key}
          value={s.value}
          onChange={(e) => onSelect?.(s.key, e.target.value)}
          className="rounded-lg border border-brd bg-surface px-3 py-2.5 text-sm text-foreground focus:border-primary focus:outline-none"
          aria-label={s.label}
        >
          {s.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ))}
      {action}
    </div>
  );
}

/* ─── Collapsible filter toggle (for secondary filters) ─────────────── */

export function useToggle(initial = false) {
  const [on, setOn] = useState(initial);
  return { on, toggle: () => setOn((v) => !v) };
}

/* ─── Pagination ─────────────────────────────────────────────────────── */

export function Pagination({
  page,
  pages,
  total,
  onPage,
}: {
  page: number;
  pages: number;
  total: number;
  onPage: (p: number) => void;
}) {
  if (pages <= 1) {
    return (
      <div className="py-3 text-center text-xs text-muted">
        {total.toLocaleString("en-IN")} result{total === 1 ? "" : "s"}
      </div>
    );
  }
  const windowStart = Math.max(1, Math.min(page - 2, pages - 4));
  const windowEnd = Math.min(pages, windowStart + 4);
  const nums: number[] = [];
  for (let i = windowStart; i <= windowEnd; i++) nums.push(i);

  return (
    <div className="flex flex-wrap items-center justify-center gap-2 py-4">
      <button
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
        className="rounded-lg border border-brd px-3 py-1.5 text-xs font-semibold text-muted disabled:opacity-40"
      >
        ← Prev
      </button>
      {windowStart > 1 && (
        <>
          <PageBtn n={1} page={page} onPage={onPage} />
          <span className="text-xs text-faint">…</span>
        </>
      )}
      {nums.map((n) => (
        <PageBtn key={n} n={n} page={page} onPage={onPage} />
      ))}
      {windowEnd < pages && (
        <>
          <span className="text-xs text-faint">…</span>
          <PageBtn n={pages} page={page} onPage={onPage} />
        </>
      )}
      <button
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
        className="rounded-lg border border-brd px-3 py-1.5 text-xs font-semibold text-muted disabled:opacity-40"
      >
        Next →
      </button>
      <span className="ml-2 text-xs text-muted">
        Page {page} of {pages.toLocaleString("en-IN")} · {total.toLocaleString("en-IN")} results
      </span>
    </div>
  );
}

function PageBtn({
  n,
  page,
  onPage,
}: {
  n: number;
  page: number;
  onPage: (p: number) => void;
}) {
  return (
    <button
      onClick={() => onPage(n)}
      className={`h-8 w-8 rounded-lg border text-xs font-semibold transition-colors ${
        n === page
          ? "border-primary bg-primary text-white"
          : "border-brd text-muted hover:bg-surface-2 hover:text-primary"
      }`}
    >
      {n}
    </button>
  );
}
