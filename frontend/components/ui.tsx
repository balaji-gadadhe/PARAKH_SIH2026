"use client";

/**
 * components/ui.tsx — shared PARAKH UI primitives.
 * All styling flows through the tokens in app/globals.css (D-023).
 */

import type { ReactNode } from "react";
import type { RiskTier } from "@/lib/api";
import { TIER_STYLES } from "@/lib/api";
import { TIER_ORDER } from "@/lib/theme";

/* ─── Tier badge ─────────────────────────────────────────────────────── */

export function TierBadge({ tier, small }: { tier: RiskTier; small?: boolean }) {
  const s = TIER_STYLES[tier];
  return (
    <span
      className={`inline-flex items-center rounded-full border font-semibold ${
        s.text
      } ${s.bg} ${s.border} ${small ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs"}`}
    >
      {tier}
    </span>
  );
}

/* ─── Stat card (KPI tile) ───────────────────────────────────────────── */

export function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="panel p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">
        {label}
      </div>
      <div className="mt-1.5 text-2xl font-extrabold text-primary">{value}</div>
      {sub != null && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

/* ─── Score gauge (0–100 SVG ring) ───────────────────────────────────── */

export function ScoreGauge({
  score,
  size = 96,
  label,
}: {
  score: number;
  size?: number;
  label?: string;
}) {
  const s = Math.max(0, Math.min(100, Math.round(score)));
  const tier: RiskTier =
    s >= 85 ? "CRITICAL" : s >= 65 ? "HIGH" : s >= 35 ? "MEDIUM" : "LOW";
  const stroke = Math.max(6, Math.round(size / 12));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Risk score ${s} of 100`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--surface-2)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`var(--tier-${tier.toLowerCase()})`}
          strokeWidth={stroke}
          strokeDasharray={`${(s / 100) * c} ${c}`}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="font-extrabold leading-none"
          style={{ fontSize: size * 0.26, color: "var(--foreground)" }}
        >
          {s}
        </span>
        <span className="mt-0.5 text-[10px] text-muted">
          {label ?? "/ 100"}
        </span>
      </div>
    </div>
  );
}

/* ─── Missing-value cell ─────────────────────────────────────────────── */

export function Na({ children }: { children: ReactNode }) {
  return <span className="na-value">{children ?? "Not available"}</span>;
}

/** Render a numeric/text value or "Not available" per card reference §6. */
export function ValueOrNa({
  value,
  format,
}: {
  value: number | string | null | undefined;
  format?: (v: number | string) => string;
}) {
  if (value === null || value === undefined || value === "") {
    return <Na>Not available</Na>;
  }
  return <>{format ? format(value) : String(value)}</>;
}

/* ─── Section title (serif) ──────────────────────────────────────────── */

export function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h3 className="font-display text-lg font-bold text-primary">{children}</h3>
  );
}

/* ─── Small label chip ───────────────────────────────────────────────── */

export function Pill({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-brd bg-surface-2 px-2.5 py-1 text-[11px] font-medium text-muted">
      {children}
    </span>
  );
}

/* ─── Empty / loading / error states ─────────────────────────────────── */

export function EmptyState({
  message,
  hint,
}: {
  message: string;
  hint?: string;
}) {
  return (
    <div className="panel flex flex-col items-center justify-center gap-1 p-10 text-center">
      <span className="text-sm font-semibold text-muted">{message}</span>
      {hint && <span className="text-xs text-faint">{hint}</span>}
    </div>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="panel flex items-center justify-center p-10">
      <span className="animate-pulse text-sm text-muted">{label}</span>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div
      className="panel p-4 text-sm"
      style={{ color: "var(--tier-critical)" }}
    >
      {message}
    </div>
  );
}

/* ─── Tier distribution mini-table (legend rows) ─────────────────────── */

export function TierLegend({
  counts,
}: {
  counts: Partial<Record<RiskTier, number>>;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      {TIER_ORDER.map((t) => (
        <div key={t} className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ background: `var(--tier-${t.toLowerCase()})` }}
            />
            <span className="text-muted">{t}</span>
          </span>
          <span className="font-bold text-foreground">
            {(counts[t] ?? 0).toLocaleString("en-IN")}
          </span>
        </div>
      ))}
    </div>
  );
}
