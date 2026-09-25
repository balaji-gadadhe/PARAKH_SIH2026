"use client";

/**
 * components/xai.tsx — Explainable-AI presentation kit for the Investigation
 * Center, styled per the Session 12 Stitch dossier design
 * (stitch-investigate/code.html): JetBrains Mono numerics, tinted engine
 * equation cards, ranked signal cards with #rank chips, stacked contribution
 * bar. (The Session-12 peer-cost band chart was removed in Session 13 as
 * misleading — peer stats remain plain numbers in the dossier's Financials
 * panel.)
 *
 * Everything derives from fields the backend already serves:
 *   - evidence_payload.component_scores × active_weights → score decomposition
 *   - top_risk_signals ("Label (Score: 0.88, Weight: 47.3%); ...") → ranked cards
 *
 * Honesty rules: contributions are the aggregator's own published math
 * (component × weight), shown as detection evidence — never a causal claim.
 * The Stitch mockup's fabricated bits (triage codes, cohort sizes, "High
 * Confidence Flag", per-engine editorial reasons) are NOT reproduced.
 */

import type { ProjectDetail } from "@/lib/api";

/* ─── Engine palette + captions ─────────────────────────────────────────── */

export const ENGINE_META: Record<
  string,
  { label: string; hex: string; tintBg: string; tintBorder: string; checks: string }
> = {
  cost_risk: {
    label: "Cost Anomaly",
    hex: "#B45309", // amber-700 family
    tintBg: "#FFFBEB", // amber-50
    tintBorder: "#FDE68A", // amber-200
    checks: "Flags cost inflation or under-spending versus comparable works.",
  },
  delay_risk: {
    label: "Delay Prediction",
    hex: "#BE123C", // rose-700
    tintBg: "#FFF1F2", // rose-50
    tintBorder: "#FECDD3", // rose-200
    checks: "ML model forecasts stall risk from payments, utilisation, history.",
  },
  payment_risk: {
    label: "Payment Anomaly",
    hex: "#EA580C", // orange-600
    tintBg: "#FFF7ED", // orange-50
    tintBorder: "#FED7AA", // orange-200
    checks: "Detects round-figure bursts, unusual frequency, structuring.",
  },
  rule_risk: {
    label: "Compliance & Ghost Rules",
    hex: "#065F46", // emerald-800
    tintBg: "#ECFDF5", // emerald-50
    tintBorder: "#A7F3D0", // emerald-200
    checks: "Rule engine: compliance checks, ghost/stalled-work markers.",
  },
  similarity_risk: {
    label: "Duplicate Work Similarity",
    hex: "#854D0E", // yellow-800
    tintBg: "#FEFCE8", // yellow-50
    tintBorder: "#FDE68A", // yellow-200
    checks: "TF-IDF text similarity + cost-deviation vs peer works.",
  },
  iforest_risk: {
    label: "Multivariate Outlier",
    hex: "#0F766E", // teal-700
    tintBg: "#F0FDFA", // teal-50
    tintBorder: "#99F6E4", // teal-200
    checks: "Isolation Forest over the joint feature space.",
  },
};

/* ─── Evidence payload parsing ───────────────────────────────────────────── */

export type Evidence = {
  component_scores: Record<string, number | null> | null;
  active_weights: Record<string, number> | null;
};

export function parseEvidence(s: string | null): Evidence {
  if (!s) return { component_scores: null, active_weights: null };
  try {
    const v = JSON.parse(s) as Record<string, unknown>;
    const cs = v.component_scores;
    const aw = v.active_weights;
    return {
      component_scores:
        cs && typeof cs === "object" ? (cs as Evidence["component_scores"]) : null,
      active_weights:
        aw && typeof aw === "object" ? (aw as Evidence["active_weights"]) : null,
    };
  } catch {
    return { component_scores: null, active_weights: null };
  }
}

/** Parse "Label (Score: 0.88, Weight: 47.3%); Label2 (...)" from the backend. */
export type Signal = { label: string; score: number; weightPct: number };

export function parseSignals(s: string | null | undefined): Signal[] {
  if (!s) return [];
  const out: Signal[] = [];
  for (const part of s.split(";")) {
    const m = part
      .trim()
      .match(/^(.*?)\s*\(Score:\s*([\d.]+),\s*Weight:\s*([\d.]+)%\)$/);
    if (m) {
      out.push({
        label: m[1],
        score: parseFloat(m[2]),
        weightPct: parseFloat(m[3]),
      });
    }
  }
  return out;
}

/* ─── Score-contribution decomposition ───────────────────────────────────── */

export type Contribution = {
  key: string;
  label: string;
  hex: string;
  tintBg: string;
  tintBorder: string;
  /** Engine score 0–1 as served. */
  score: number;
  /** Renormalized active weight 0–1. */
  weight: number;
  /** Points contributed to the final 0–100 display score. */
  points: number;
};

export function computeContributions(
  work: ProjectDetail
): { items: Contribution[]; total: number; ok: boolean } {
  const { component_scores: cs, active_weights: aw } = parseEvidence(
    work.evidence_payload
  );
  if (!cs || !aw) return { items: [], total: 0, ok: false };

  const items: Contribution[] = [];
  for (const [key, w] of Object.entries(aw)) {
    const meta = ENGINE_META[key];
    if (!meta) continue;
    const score = cs[key];
    if (score == null) continue;
    // Points added to the 0–100 display score: component_score × active
    // weight × 100. (active_weights are re-normalized over available engines
    // and sum to 1.0, so Σ score×weight = the 0–1 overall score.)
    items.push({
      key,
      label: meta.label,
      hex: meta.hex,
      tintBg: meta.tintBg,
      tintBorder: meta.tintBorder,
      score,
      weight: w,
      points: Math.round(score * w * 100 * 100) / 100,
    });
  }
  items.sort((a, b) => b.points - a.points);

  // Sanity gate: contributions must reconstruct the served score (±0.5 pt
  // display tolerance). If they don't (payload drift), hide the chart rather
  // than show wrong math.
  const total = items.reduce((s, i) => s + i.points, 0);
  const ok = Math.abs(total - work.risk_score_display) <= 0.5;
  return { items: ok ? items : [], total, ok };
}

/* ─── Shared small helpers ───────────────────────────────────────────────── */

function metaChecks(key: string): string {
  return ENGINE_META[key]?.checks ?? "";
}

/* ─── Stacked contribution bar (Stitch: "Weighted Point Contribution") ───── */

export function ContributionChart({
  items,
  scoreDisplay,
}: {
  items: Contribution[];
  scoreDisplay: number;
}) {
  return (
    <div>
      <div className="flex justify-between items-center text-xs text-muted">
        <span>Weighted point contribution (0 to 100 max potential points)</span>
        <span className="font-bold text-foreground">
          Total: {scoreDisplay.toFixed(1)} / 100 pts
        </span>
      </div>
      <div className="mt-2 flex h-8 w-full overflow-hidden rounded-lg border border-brd-strong bg-surface-2 shadow-inner">
        {items.map((c) => (
          <div
            key={c.key}
            title={`${c.label}: +${c.points.toFixed(1)} pts (score ${c.score.toFixed(2)} × weight ${(c.weight * 100).toFixed(1)}%)`}
            style={{
              width: `${(c.points / scoreDisplay) * 100}%`,
              background: c.hex,
            }}
            className="flex h-full items-center justify-center text-xs font-bold text-white"
          >
            {c.points.toFixed(1)}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Equation card per engine (Stitch "Equation Cards Grid"). */
export function ContributionLegend({
  items,
}: {
  items: Contribution[];
}) {
  return (
    <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2 lg:grid-cols-3">
      {items.map((c, i) => (
        <div
          key={c.key}
          className="space-y-1.5 rounded-lg border p-3.5"
          style={{ borderColor: c.tintBorder, background: `${c.tintBg}` }}
        >
          <div className="flex items-start justify-between gap-2">
            <span className="text-xs font-bold" style={{ color: c.hex }}>
              {i + 1}. {c.label}
            </span>
            <span
              className="rounded border px-1.5 py-0.5 text-[11px] font-extrabold"
              style={{ color: c.hex, borderColor: c.tintBorder, background: "#ffffff" }}
            >
              +{c.points.toFixed(1)} pts
            </span>
          </div>
          <div className="font-mono text-[11px] text-muted">
            Formula: {c.score.toFixed(2)} (Score) × {(c.weight * 100).toFixed(1)}% (Wt)
          </div>
          <p className="text-[11px] leading-relaxed text-faint">{metaChecks(c.key)}</p>
        </div>
      ))}
    </div>
  );
}

/* ─── Ranked signal cards (Stitch: TOP-RANKED SIGNALS) ──────────────────── */

export function SignalCards({ signals }: { signals: Signal[] }) {
  if (signals.length === 0) return null;
  const palette = ["#A92727", "#EA580C", "#B45309"]; // rose / orange / amber
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {signals.map((sig, i) => {
        const hex = palette[i % palette.length];
        return (
          <div
            key={i}
            className="relative space-y-2 overflow-hidden rounded-xl border p-3"
            style={{ borderColor: `${hex}40`, background: `${hex}0D` }}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className="inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold text-white shadow-sm"
                  style={{ background: hex }}
                >
                  #{i + 1}
                </span>
                <span className="font-display text-sm font-bold text-foreground">
                  {sig.label}
                </span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 border-t pt-1.5" style={{ borderColor: `${hex}40` }}>
              <div>
                <span className="block text-[10px] uppercase text-faint">Engine Score</span>
                <span className="text-sm font-bold text-foreground">{sig.score.toFixed(2)}</span>
              </div>
              <div className="text-right">
                <span className="block text-[10px] uppercase text-faint">Share of Score</span>
                <span className="text-sm font-bold text-foreground">
                  {sig.weightPct.toFixed(1)}%
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2 pt-0.5">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${sig.score * 100}%`, background: hex }}
                />
              </div>
              <span className="text-[10px] font-bold" style={{ color: hex }}>
                {Math.round(sig.score * 100)}% Impact
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
