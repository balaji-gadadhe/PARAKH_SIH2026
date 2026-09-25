"use client";

/**
 * app/investigation/[projectId]/page.tsx - Investigation Center (Step 8,
 * restyled Session 12 from the Stitch dossier design stitch-investigate/).
 *
 * Layout per the Stitch mockup: top bar → dossier header card (gauge hero
 * badge, investigation brief) → Explainable-AI Score Anatomy (stacked
 * contribution bar + per-engine equation cards) → Triage summary + Six-Engine
 * list → Why-flagged (ranked signal cards + detection evidence) →
 * Financials/Payments/Vendor → About-this-assessment accordion → Report CTA.
 *
 * The Session-12 peer-cost distribution band (median/±σ horizontal bar) was
 * removed in Session 13: the visual comparison implied a precision the
 * peer-matching can't support and read as misleading in team testing. The
 * underlying peer stats remain as plain numbers in the Financials panel.
 *
 * All numbers are LIVE from the backend. The mockup's fabricated decoration
 * (triage codes, cohort N, "High Confidence Flag", per-engine editorial blurbs,
 * hardcoded cutoffs) is deliberately not reproduced — honesty rules §6/§7:
 * "Not available" for missing values; risk language only.
 */

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  api,
  ApiError,
  formatINR,
  formatINRFull,
  notAvailable,
  URGENCY_LABELS,
  type ProjectDetail,
  type ReportSnapshot,
} from "@/lib/api";
import { Footer } from "@/components/shell";
import { TierBadge, LoadingState, ErrorState } from "@/components/ui";
import {
  ENGINE_META,
  ContributionChart,
  SignalCards,
  computeContributions,
  parseSignals,
} from "@/components/xai";
import { WorkReportSheet, buildReportSummary, buildReportSnapshot } from "@/components/work-report";
import { InvestigationHistory } from "@/components/investigation-history";
import { PublicVoice } from "@/components/public-voice";

/* ─── JSON helpers ───────────────────────────────────────────────────── */

function parseJsonArray(s: string | null): string[] {
  if (!s) return [];
  try {
    const v = JSON.parse(s);
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
}

function humanizeStatus(s: string | null): string {
  if (!s) return "Not available";
  const t = s.toLowerCase().replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Composite ID "80673|MP|PC|State" -> short "80673" + rest. */
function splitId(id: string): { short: string; full: string } {
  const parts = id.split("|");
  return { short: parts[0] ?? id, full: id };
}

/**
 * useParams() returns the dynamic segment still URL-encoded in Next.js.
 * decodeURIComponent it exactly once before passing to the API client.
 */
function safeDecode(v: string): string {
  try {
    return decodeURIComponent(v);
  } catch {
    return v;
  }
}

type EvidenceCardData = {
  title: string;
  summary: string;
  metrics: { label: string; value: string }[];
  tone: "amber" | "rose" | "green" | "teal" | "orange";
};

function evidenceCards(work: ProjectDetail, factors: string[]): EvidenceCardData[] {
  const cards: EvidenceCardData[] = [];
  const hasFactor = (prefix: string) => factors.some((factor) => factor.startsWith(prefix));
  const predictedDelay = factors
    .find((factor) => factor.startsWith("Delay Risk:"))
    ?.match(/~([\d,]+) days predicted/i)?.[1];

  if (hasFactor("Cost Anomaly:") || work.peer_median_cost != null) {
    cards.push({
      title: "Spending is above the comparison benchmark",
      summary: "The recorded amounts should be checked against the sanction and similar works.",
      tone: "amber",
      metrics: [
        { label: "Recommended", value: formatINRFull(work.recommended_amount) },
        { label: "Expenditure", value: formatINRFull(work.total_expenditure) },
        {
          label: "Peer median",
          value: work.peer_median_cost != null ? formatINR(work.peer_median_cost) : "Not available",
        },
        {
          label: "Expenditure ratio",
          value: work.expenditure_ratio != null ? `${work.expenditure_ratio.toFixed(2)}x` : "Not available",
        },
      ],
    });
  }

  if (hasFactor("Delay Risk:")) {
    cards.push({
      title: "Completion delay risk is elevated",
      summary: "The delay model forecasts a longer completion path and prioritizes the work for review.",
      tone: "rose",
      metrics: [
        { label: "Current status", value: humanizeStatus(work.status) },
        {
          label: "Work age",
          value: work.days_since_recommendation != null ? `${work.days_since_recommendation} days` : "Not available",
        },
        { label: "Forecast", value: predictedDelay ? `~${predictedDelay} days additional delay` : "Elevated delay risk" },
      ],
    });
  }

  if (hasFactor("Payment Anomaly:") || work.payment_count != null) {
    cards.push({
      title: "Payment activity needs review",
      summary: "The payment engine found an unusual combination of frequency, amount, or transaction-pattern signals.",
      tone: "orange",
      metrics: [
        { label: "Total payments", value: notAvailable(work.payment_count) },
        {
          label: "Frequency",
          value: work.payment_frequency != null ? `${work.payment_frequency.toFixed(3)} / month` : "Not available",
        },
        { label: "Latest status", value: work.latest_payment_status ?? "Not available" },
      ],
    });
  }

  const rules = factors.find((factor) => factor.startsWith("Rule Violations:"));
  if (rules) {
    const ruleCount = rules.match(/\[(\d+) triggered\]/i)?.[1];
    cards.push({
      title: "Compliance rules were triggered",
      summary: "Deterministic checks found rule conditions that an investigator should verify against source records.",
      tone: "teal",
      metrics: [
        { label: "Triggered checks", value: ruleCount ? `${ruleCount} rules` : "Multiple rules" },
        { label: "Method", value: "Compliance and ghost/stall rules" },
      ],
    });
  }

  const similarity = factors.find((factor) => factor.startsWith("Duplicate Work Alert:"));
  if (similarity) {
    cards.push({
      title: "Description similarity needs a cross-check",
      summary: "Similar text can indicate overlap, but it is a signal and not proof of duplicate work.",
      tone: "green",
      metrics: [
        { label: "Similarity", value: "1.00 text similarity" },
        { label: "Matching works", value: similarity.match(/with (\d+) project/i)?.[1] ?? "Not available" },
      ],
    });
  }

  const outlier = factors.find((factor) => factor.startsWith("Multivariate ML Anomaly:"));
  if (outlier) {
    const driverCount = outlier.match(/Drivers:\s*(.+)$/i)?.[1]?.replace(/\.\.\.$/, "");
    cards.push({
      title: "The combined payment profile is unusual",
      summary: "The multivariate model compares several fields together and surfaces combinations that differ from typical works.",
      tone: "teal",
      metrics: [
        { label: "Method", value: "Isolation Forest" },
        { label: "Observed drivers", value: driverCount ?? "Multiple fields" },
      ],
    });
  }

  return cards;
}

const EVIDENCE_TONE: Record<EvidenceCardData["tone"], { border: string; bar: string; badge: string }> = {
  amber: { border: "border-amber-200", bar: "bg-amber-500", badge: "bg-amber-50 text-amber-800" },
  rose: { border: "border-rose-200", bar: "bg-rose-600", badge: "bg-rose-50 text-rose-800" },
  green: { border: "border-emerald-200", bar: "bg-emerald-600", badge: "bg-emerald-50 text-emerald-800" },
  teal: { border: "border-teal-200", bar: "bg-teal-600", badge: "bg-teal-50 text-teal-800" },
  orange: { border: "border-orange-200", bar: "bg-orange-600", badge: "bg-orange-50 text-orange-800" },
};

function EvidenceCard({ card }: { card: EvidenceCardData }) {
  const tone = EVIDENCE_TONE[card.tone];
  return (
    <article className={`overflow-hidden rounded-xl border bg-white ${tone.border}`}>
      <div className={`h-1 ${tone.bar}`} />
      <div className="space-y-2 p-3">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-sm font-bold leading-snug text-stone-900">{card.title}</h3>
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${tone.badge}`}>
            review signal
          </span>
        </div>
        <p className="text-xs leading-relaxed text-stone-600">{card.summary}</p>
        <dl className="grid grid-cols-2 gap-2 border-t border-stone-100 pt-2">
          {card.metrics.map((metric) => (
            <div key={metric.label}>
              <dt className="text-[10px] uppercase tracking-wide text-stone-400">{metric.label}</dt>
              <dd className="mt-0.5 text-xs font-bold text-stone-800">{metric.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </article>
  );
}

function FinancialComparison({ work }: { work: ProjectDetail }) {
  const values = [
    { label: "Peer median", value: work.peer_median_cost },
    { label: "Recommended", value: work.recommended_amount },
    { label: "Expenditure", value: work.total_expenditure },
  ].filter((item): item is { label: string; value: number } => item.value != null && item.value >= 0);
  if (values.length < 2) return null;
  const max = Math.max(...values.map((item) => item.value), 1);
  const recommended = work.recommended_amount ?? 0;
  return (
    <div className="space-y-3 rounded-xl border border-stone-200 bg-stone-50/70 p-4">
      <div>
        <h3 className="text-sm font-bold text-stone-900">Financial comparison</h3>
        <p className="text-[11px] text-stone-500">Values are shown against the largest recorded amount.</p>
      </div>
      <div className="space-y-2.5">
        {values.map((item) => (
          <div key={item.label} className="grid grid-cols-[82px_1fr_auto] items-center gap-2">
            <span className="text-[11px] font-semibold text-stone-600">{item.label}</span>
            <div className="h-3 overflow-hidden rounded-full bg-stone-200">
              <div
                className={`h-full rounded-full ${item.label === "Expenditure" ? "bg-rose-500" : item.label === "Recommended" ? "bg-amber-500" : "bg-teal-600"}`}
                style={{ width: `${Math.max(2, (item.value / max) * 100)}%` }}
              />
            </div>
            <span className="font-mono text-[11px] font-bold text-stone-800">{formatINR(item.value)}</span>
          </div>
        ))}
      </div>
      {recommended > 0 && work.total_expenditure != null && (
        <p className="border-t border-stone-200 pt-2 text-[11px] font-semibold text-rose-700">
          Recorded expenditure is {(work.total_expenditure / recommended).toFixed(2)}x the recommended amount.
        </p>
      )}
    </div>
  );
}

/** Circular SVG gauge per the Stitch hero badge (90/100 style). */
function HeroGauge({ score, tierHex }: { score: number; tierHex: string }) {
  return (
    <div className="relative flex h-28 w-28 items-center justify-center">
      <svg className="h-full w-full -rotate-90" viewBox="0 0 36 36">
        <path
          className="text-stone-200"
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none"
          stroke="currentColor"
          strokeWidth="3.5"
        />
        <path
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none"
          stroke={tierHex}
          strokeDasharray={`${score}, 100`}
          strokeLinecap="round"
          strokeWidth="3.5"
        />
      </svg>
      <div className="absolute flex flex-col items-center justify-center text-center">
        <span className="text-3xl font-extrabold leading-none text-foreground">
          {score}
        </span>
        <span className="mt-0.5 text-[10px] font-bold uppercase tracking-wider text-stone-500">
          / 100
        </span>
      </div>
    </div>
  );
}

function PriorityGauge({ priority }: { priority: number | null }) {
  const score = priority ?? 0;
  return (
    <div className="flex items-center gap-3">
      <div className="relative h-14 w-14 shrink-0">
        <svg className="h-full w-full -rotate-90" viewBox="0 0 36 36" aria-hidden>
          <path
            className="text-stone-200"
            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke="currentColor"
            strokeWidth="4"
          />
          {priority != null && (
            <path
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none"
              stroke="var(--accent)"
              strokeDasharray={`${score}, 100`}
              strokeLinecap="round"
              strokeWidth="4"
            />
          )}
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-xs font-bold text-stone-900">
          {priority != null ? Math.round(priority) : "—"}
        </span>
      </div>
      <div>
        <p className="text-xs font-bold uppercase tracking-wide text-stone-500">Review priority</p>
        <p className="text-[11px] leading-snug text-stone-600">
          {priority != null ? "Risk plus financial exposure" : "Not available"}
        </p>
      </div>
    </div>
  );
}

/* ─── Page ───────────────────────────────────────────────────────────── */

export default function InvestigationPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <InvestigationInner />
    </Suspense>
  );
}

function InvestigationInner() {
  const params = useParams<{ projectId: string }>();
  const search = useSearchParams();
  // Demo-auth convention: authority identity travels in the URL (?role=&mp=&state=).
  // No role param = public/citizen viewer — the dossier stays read-only.
  // (The citizen portal's Investigate links deliberately carry no role param.)
  const role = search.get("role");
  const isAuthority =
    role === "mospi" || role === "mp" || role === "sno" || role === "dm";
  const mp = search.get("mp");
  const state = search.get("state");
  const projectId = safeDecode(params.projectId);
  const [work, setWork] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showReport, setShowReport] = useState(false);

  useEffect(() => {
    api
      .projectDetail(projectId)
      .then(setWork)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) {
          setError(
            `Project not found: ${projectId}. If you opened this link directly, go back to the Works tab and click Investigate again.`
          );
        } else {
          setError(String(e));
        }
      });
  }, [projectId]);

  // Back link returns to wherever the viewer came from (scope preserved):
  // citizen portal → the portal feed; authority roles → their scoped dashboard.
  const fromCitizen = search.get("from") === "citizen";
  const backHref = fromCitizen
    ? "/citizen?tab=feed"
    : !role
      ? "/" // public viewer (no authority login) → public homepage
      : (role === "mp" || role === "dm") && mp
        ? `/dashboard?role=${role}&mp=${encodeURIComponent(mp)}`
        : role === "sno" && state
          ? `/dashboard?role=sno&state=${encodeURIComponent(state)}`
          : "/dashboard?role=mospi";

  return (
    <div className="flex min-h-screen flex-col">
      {/* Printable Investigation Report (D-031 Step 1) — screen: hidden;
          print: the app hides around it via the @media print rules. */}
      <div className="print-area">
        {work && <WorkReportSheet work={work} />}
      </div>

      <main className="mx-auto w-full max-w-[1360px] flex-1 px-4 py-8 sm:px-6 lg:px-8">
        {/* Top navigation bar (Stitch: inline header, not sticky) */}
        <header className="flex flex-col gap-4 pb-2 sm:flex-row sm:items-center sm:justify-between">
          <Link
            href={backHref}
            className="group inline-flex items-center gap-2 text-sm font-semibold text-primary transition-colors hover:text-emerald-950"
          >
            <span className="inline-block font-bold transition-transform group-hover:-translate-x-1">
              ←
            </span>
            <span>Back to Work Explorer</span>
          </Link>
          <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
            {!isAuthority && (
              <span className="disclaimer-chip">
                <span className="h-2 w-2 rounded-full bg-stone-400" />
                Public view — read-only · authority actions need role login
              </span>
            )}
            <span className="disclaimer-chip">
              <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
              Historical batch data · Risk indicators only
            </span>
          </div>
        </header>

        {error && <ErrorState message={`Backend unreachable - ${error}`} />}
        {!work && !error && <LoadingState label="Loading work dossier..." />}

        {work && isAuthority && (
          <WorkDossier
            work={work}
            onReport={() => setShowReport(true)}
            onPrint={() => window.print()}
          />
        )}
        {work && !isAuthority && <WorkDossier work={work} />}
      </main>

      <Footer />
      {work && isAuthority && showReport && (
        <ReportModal
          work={work}
          onClose={() => setShowReport(false)}
          attachSummary={buildReportSummary(work)}
          attachSnapshot={buildReportSnapshot(work)}
          reporter={
            role === "mp"
              ? "MP"
              : role === "sno"
                ? "State Nodal Officer"
                : role === "dm"
                  ? "District Magistrate"
                  : "MoSPI Audit Cell"
          }
        />
      )}
    </div>
  );
}

/* ─── Dossier ────────────────────────────────────────────────────────── */

function WorkDossier({
  work,
  onReport,
  onPrint,
}: {
  work: ProjectDetail;
  /** Present only for authority viewers — omit for the public read-only view. */
  onReport?: () => void;
  /** Present only for authority viewers — omit for the public read-only view. */
  onPrint?: () => void;
}) {
  const [showAbout, setShowAbout] = useState(false);
  const { short } = splitId(work.project_id);
  const factors = parseJsonArray(work.risk_factors);
  const { items: contribs, ok: contribOk } = computeContributions(work);
  const signals = parseSignals(work.top_risk_signals);
  const evidence = evidenceCards(work, factors);
  const flaggedEngines = work.engines.filter((e) => e.available && e.flag);
  const urgencyLabel = work.investigation_urgency
    ? URGENCY_LABELS[work.investigation_urgency] ?? work.investigation_urgency
    : "Not available";
  const riskColor =
    work.risk_category === "CRITICAL"
      ? "var(--tier-critical)"
      : work.risk_category === "HIGH"
        ? "var(--tier-high)"
        : work.risk_category === "MEDIUM"
          ? "var(--tier-medium)"
          : "var(--tier-low)";

  return (
    <div className="space-y-6">
      <nav className="sticky top-3 z-20 flex gap-1 overflow-x-auto rounded-xl border border-stone-200 bg-white/95 p-1.5 shadow-sm backdrop-blur" aria-label="Investigation sections">
        {[
          ["summary", "Decision"],
          ["risk-analysis", "Explain"],
          ["why-flagged", "Why flagged"],
          ["public-voice", "Public voice"],
          ["details", "Details"],
          ["history", "History"],
        ].map(([id, label]) => (
          <a
            key={id}
            href={`#${id}`}
            className="whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-semibold text-stone-600 transition-colors hover:bg-stone-100 hover:text-primary"
          >
            {label}
          </a>
        ))}
      </nav>

      {/* ── Decision: identity, priority, and next action ── */}
      <section id="summary" className="panel relative scroll-mt-20 overflow-hidden !rounded-2xl p-5 md:p-7">
        <div
          className="absolute left-0 right-0 top-0 h-1.5"
          style={{
            background:
              "linear-gradient(to right, var(--tier-critical), var(--accent), var(--primary))",
          }}
        />
        <div className="flex flex-col justify-between gap-6 pt-2 lg:flex-row lg:items-start">
          <div className="flex-1 space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded border border-stone-200 bg-stone-100 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-stone-500">
                Project Dossier
              </span>
              <TierBadge tier={work.risk_category} />
              <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-800">
                {humanizeStatus(work.status)}
              </span>
            </div>
            <div>
              <h1 className="font-display text-3xl font-bold tracking-tight text-stone-900">
                Work {short}
              </h1>
              <p className="mt-1 text-base font-medium text-foreground">
                {work.work_description ?? "Work description not recorded"}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-sm text-muted">
              <span className="font-semibold text-foreground">{work.mp_name}</span>
              <span className="text-stone-300">•</span>
              <span>{work.state}</span>
              <span className="text-stone-300">•</span>
              <span>{work.constituency}</span>
              <span className="text-stone-300">•</span>
              <span>{work.category}</span>
              <span className="w-full text-xs text-faint">Full ID: {work.project_id}</span>
            </div>
          </div>
          <div className="flex min-w-[230px] items-center gap-4 rounded-xl border border-stone-200 bg-stone-50 p-4">
            <HeroGauge
              score={work.risk_score_display}
              tierHex={riskColor}
            />
            <div className="space-y-1">
              <p className="text-xs font-bold uppercase tracking-wider text-stone-500">Risk indicator</p>
              <p className="text-sm font-bold text-stone-900">{work.risk_category} priority</p>
              <p className="text-[11px] leading-snug text-stone-500">
                {flaggedEngines.length} of {work.engines.length} engines flagged
              </p>
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 border-t border-stone-200 pt-4 sm:grid-cols-3">
          <PriorityGauge priority={work.investigation_priority} />
          <div className="rounded-lg bg-amber-50 p-3">
            <p className="text-[10px] font-bold uppercase tracking-wide text-amber-800">Recommended review</p>
            <p className="mt-1 text-sm font-bold text-stone-900">{urgencyLabel}</p>
            <p className="text-[11px] text-stone-600">Triage aid, not a finding</p>
          </div>
          <div className="rounded-lg bg-stone-50 p-3">
            <p className="text-[10px] font-bold uppercase tracking-wide text-stone-500">Assessment scope</p>
            <p className="mt-1 text-sm font-bold text-stone-900">Historical batch</p>
            <p className="text-[11px] text-stone-600">Signals require human review</p>
          </div>
        </div>
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/70 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-900">Decision brief</p>
          <p className="mt-1 text-sm leading-relaxed text-stone-800">
            {work.audit_explanation ?? "No explanation recorded for this work."} Review the evidence below before taking action.
          </p>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-stone-200 bg-white/80 p-3.5">
          <p className="text-xs text-stone-500">Ready for analyst review</p>
          <div className="flex gap-2">
            {onReport && (
              <button
                onClick={onReport}
                className="rounded-lg bg-primary px-3 py-2 text-xs font-bold text-white transition hover:brightness-110"
              >
                Report this work
              </button>
            )}
            {onPrint && (
              <button
                onClick={onPrint}
                className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-xs font-bold text-primary transition hover:border-primary"
              >
                Export PDF
              </button>
            )}
          </div>
        </div>
      </section>

      {/* ── Why flagged: ranked signals + detection evidence ───────────── */}
      <section id="why-flagged" className="panel scroll-mt-20 space-y-6 !rounded-2xl p-6 md:p-8">
        <div className="border-b border-brd pb-4">
          <h2 className="font-display text-2xl font-bold text-stone-900">
            Why this work is flagged
          </h2>
          <p className="mt-1 text-xs text-stone-600 sm:text-sm">
            Clear evidence cards from the detection engines, with the underlying
            values available in the dossier panels below.
          </p>
        </div>

        {contribOk && contribs.length > 0 && (
          <div id="risk-analysis" className="scroll-mt-20 space-y-4 border-b border-brd pb-5">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h3 className="font-display text-lg font-bold text-stone-900">How the score was formed</h3>
                <p className="mt-1 text-xs text-stone-600">Each engine contributes a weighted share of the 0–100 indicator.</p>
              </div>
              <span className="font-mono text-sm font-bold text-stone-700">{work.risk_score_display}/100</span>
            </div>
            <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
              <div className="rounded-xl border border-stone-200 bg-stone-50/60 p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="section-label">Risk contribution</span>
                  <span className="text-[11px] font-bold text-stone-600">weighted points</span>
                </div>
                <ContributionChart items={contribs} scoreDisplay={work.risk_score_display} />
                <div className="mt-3 grid grid-cols-2 gap-1.5 border-t border-stone-200 pt-3 sm:grid-cols-3">
                  {contribs.map((item) => (
                    <div key={item.key} className="flex items-center justify-between gap-1 rounded-md bg-white px-2 py-1.5 text-[11px]">
                      <span className="truncate font-semibold text-stone-700">{item.label}</span>
                      <span className="shrink-0 font-mono font-bold" style={{ color: item.hex }}>+{item.points.toFixed(1)}</span>
                    </div>
                  ))}
                </div>
              </div>
              <FinancialComparison work={work} />
            </div>
            <p className="text-[11px] leading-relaxed text-faint">Attribution for review, not proof of wrongdoing. Missing engines are re-weighted over available data.</p>
          </div>
        )}

        {signals.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="section-label">
                Top-ranked signals (from the aggregator)
              </span>
            </div>
            <SignalCards signals={signals} />
          </div>
        )}

        {evidence.length > 0 && (
          <div className="space-y-3 pt-2">
            <div className="section-label">What the engines found</div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {evidence.map((card) => (
                <EvidenceCard key={card.title} card={card} />
              ))}
            </div>
          </div>
        )}
        {!signals.length && !factors.length && (
          <p className="text-sm text-muted">
            No explanation recorded for this work.
          </p>
        )}
      </section>

      <section id="engine-table" className="panel scroll-mt-20 !rounded-2xl p-5 md:p-6">
        <div className="mb-3 flex items-end justify-between gap-2 border-b border-brd pb-3">
          <div><h2 className="font-display text-xl font-bold text-stone-900">Engine checks</h2><p className="mt-1 text-xs text-stone-500">What each detector contributed to the review signal.</p></div>
          <span className="text-xs text-stone-500">{flaggedEngines.length}/{work.engines.length} flagged</span>
        </div>
        <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
          {work.engines.map((engine) => {
            const pct = engine.score != null ? Math.round(engine.score * 100) : null;
            const meta = Object.values(ENGINE_META).find((item) => item.label === engine.engine);
            return <div key={engine.engine} className="rounded-lg border border-stone-200 bg-stone-50/60 p-3">
              <div className="flex items-center justify-between gap-2"><span className="text-xs font-bold text-stone-800">{engine.engine}</span><span className={`text-xs font-bold ${engine.flag ? "text-critical" : "text-low"}`}>{pct != null ? `${pct}%` : "—"}</span></div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-stone-200"><div className={`h-full rounded-full ${engine.flag ? "bg-critical" : "bg-low"}`} style={{ width: `${pct ?? 0}%` }} /></div>
              <p className="mt-2 text-[10px] leading-snug text-stone-500">{meta?.checks ?? "Detector status not available."}</p>
            </div>;
          })}
        </div>
      </section>

      {/* ── What the public says: citizen PSI + concerns (D-032 Step 5) ── */}
      <PublicVoice projectId={work.project_id} />

      {/* ── Core data panels: Financials / Payments / Vendor ───────────── */}
      <div id="financials" className="grid scroll-mt-20 grid-cols-1 gap-6 md:grid-cols-3">
        <div className="panel space-y-4 !rounded-2xl p-6">
          <div className="border-b border-brd pb-3">
            <h3 className="font-display text-lg font-bold text-stone-900">
              Financials
            </h3>
            <p className="text-xs text-stone-500">Sanctioned vs Utilised</p>
          </div>
          <FinancialComparison work={work} />
          <dl className="divide-y divide-stone-100 font-mono text-xs sm:text-sm">
            <DRow label="Recommended" value={formatINRFull(work.recommended_amount)} />
            <DRow
              label="Final amount"
              value={work.final_amount != null ? formatINRFull(work.final_amount) : undefined}
            />
            <DRow
              label="Total expenditure"
              value={formatINRFull(work.total_expenditure)}
              tone={
                work.expenditure_ratio != null && work.expenditure_ratio > 2
                  ? "critical"
                  : "normal"
              }
            />
            <DRow
              label="Expenditure ratio"
              value={
                work.expenditure_ratio != null
                  ? `${work.expenditure_ratio.toFixed(2)}x`
                  : undefined
              }
              tone={
                work.expenditure_ratio != null && work.expenditure_ratio > 2
                  ? "critical"
                  : "normal"
              }
            />
            <DRow
              label="Cost variation"
              value={work.cost_variation_pct != null ? `${work.cost_variation_pct}%` : undefined}
            />
            <DRow
              label="Peer median cost"
              value={work.peer_median_cost != null ? formatINR(work.peer_median_cost) : undefined}
            />
            <DRow
              label="Peer mean cost"
              value={work.peer_mean_cost != null ? formatINR(work.peer_mean_cost) : undefined}
            />
            <DRow
              label="Peer std deviation"
              value={work.peer_std_cost != null ? formatINR(work.peer_std_cost) : undefined}
            />
            <DRow
              label="Deviation from peer"
              value={
                work.cost_deviation_from_peer != null
                  ? `${work.cost_deviation_from_peer.toFixed(1)}%`
                  : undefined
              }
            />
          </dl>
        </div>

        <div className="panel space-y-4 !rounded-2xl p-6">
          <div className="border-b border-brd pb-3">
            <h3 className="font-display text-lg font-bold text-stone-900">
              Payments
            </h3>
            <p className="text-xs text-stone-500">Disbursement Frequency</p>
          </div>
          <dl className="divide-y divide-stone-100 font-mono text-xs sm:text-sm">
            <DRow label="Payment count" value={notAvailable(work.payment_count)} />
            <DRow
              label="Average payment"
              value={work.average_payment != null ? formatINR(work.average_payment) : undefined}
            />
            <DRow
              label="Maximum payment"
              value={work.maximum_payment != null ? formatINR(work.maximum_payment) : undefined}
              tone="amber"
            />
            <DRow
              label="Minimum payment"
              value={work.minimum_payment != null ? formatINR(work.minimum_payment) : undefined}
            />
            <DRow
              label="Payment frequency"
              value={
                work.payment_frequency != null
                  ? `${work.payment_frequency.toFixed(3)} / month`
                  : undefined
              }
            />
            <DRow label="Pending payments" value={notAvailable(work.pending_payment_count)} />
            <DRow
              label="Successful payments"
              value={notAvailable(work.successful_payment_count)}
            />
            <DRow label="Latest status" value={work.latest_payment_status ?? undefined} />
          </dl>
        </div>

        <div className="panel space-y-4 !rounded-2xl p-6">
          <div className="border-b border-brd pb-3">
            <h3 className="font-display text-lg font-bold text-stone-900">
              Vendor &amp; Other
            </h3>
            <p className="text-xs text-stone-500">Entity Profile &amp; Metadata</p>
          </div>
          <dl className="divide-y divide-stone-100 font-mono text-xs sm:text-sm">
            <div className="py-2.5">
              <dt className="text-xs text-stone-500">Primary vendor</dt>
              <dd className="mt-0.5 text-sm font-bold uppercase text-stone-900">
                {work.primary_vendor ?? <span className="na-value">Not available</span>}
              </dd>
            </div>
            <div className="flex items-center justify-between py-2.5">
              <dt className="text-stone-500">Vendor risk</dt>
              <dd>
                {work.vendor_risk_score != null ? (
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-bold ${(work.vendor_risk_level ?? "").toUpperCase() === "HIGH" ||
                        (work.vendor_risk_level ?? "").toUpperCase() === "CRITICAL"
                        ? "border-rose-200 bg-rose-50 text-critical"
                        : (work.vendor_risk_level ?? "").toUpperCase() === "MEDIUM"
                          ? "border-amber-200 bg-amber-100 text-amber-900"
                          : "border-emerald-200 bg-emerald-50 text-low"
                      }`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${(work.vendor_risk_level ?? "").toUpperCase() === "HIGH" ||
                          (work.vendor_risk_level ?? "").toUpperCase() === "CRITICAL"
                          ? "bg-critical"
                          : (work.vendor_risk_level ?? "").toUpperCase() === "MEDIUM"
                            ? "bg-amber-600"
                            : "bg-low"
                        }`}
                    />
                    {work.vendor_risk_score} · {work.vendor_risk_level ?? ""}
                  </span>
                ) : (
                  <span className="na-value">Not available</span>
                )}
              </dd>
            </div>
            <DRow
              label="Days since recommendation"
              value={notAvailable(work.days_since_recommendation)}
              suffix={work.days_since_recommendation != null ? " days" : undefined}
            />
            <DRow
              label="Recommendation to completion"
              value={
                work.recommendation_to_completion_days != null
                  ? `${work.recommendation_to_completion_days} days`
                  : undefined
              }
            />
            <DRow
              label="Average rating"
              value={
                work.average_rating != null ? `${work.average_rating} / 5` : undefined
              }
            />
            <DRow
              label="Images available"
              value={
                work.has_images == null ? undefined : work.has_images ? "Yes" : "No"
              }
            />
            <DRow
              label="Description similarity"
              value={
                work.description_similarity_score != null
                  ? `${work.description_similarity_score}`
                  : undefined
              }
            />
          </dl>
        </div>
      </div>

      {/* ── About this assessment: methodology & data provenance ────────── */}
      <section className="panel overflow-hidden !rounded-2xl">
        <button
          onClick={() => setShowAbout((v) => !v)}
          className="flex w-full cursor-pointer select-none items-center justify-between p-6 font-display text-lg font-bold text-stone-900 transition-colors hover:bg-stone-50/60"
        >
          <div className="flex items-center gap-3">
            <svg
              className={`h-5 w-5 transform text-primary transition-transform ${showAbout ? "rotate-90" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                d="M9 5l7 7-7 7"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
              />
            </svg>
            <span>About this assessment — data &amp; methodology</span>
          </div>
          <span className="rounded border border-stone-200 bg-stone-100 px-2.5 py-1 text-xs text-stone-500">
            {showAbout ? "Click to Collapse" : "Click to Expand"}
          </span>
        </button>
        {showAbout && (
          <div className="border-t border-brd p-6 pt-0">
            <div className="mt-4 grid grid-cols-1 gap-x-8 gap-y-6 md:grid-cols-2">
              <AboutBlock
                label="Where the data comes from"
                items={[
                  "MPLADS public releases — frozen batch as of 2026-09-01, committed with the repository so every installation serves identical numbers (86,976 works · 731 MPs · 28,123 vendors).",
                  "Map coordinates are synthetic demo data, clearly labeled — no real GPS tracking exists in this system.",
                ]}
              />
              <AboutBlock
                label="How the score is built"
                items={[
                  "Six detection engines each produce a 0–1 signal: rules & compliance, multivariate outliers, delay forecasting, cost anomaly, payment patterns, and duplicate-work similarity.",
                  "A weighted aggregator merges them: Σ (engine score × weight) × 100 → the 0–100 risk score shown in Score anatomy above.",
                  "Weights are re-normalized per work over the engines that had data, so the visible signals always sum to 100%.",
                ]}
              />
              <AboutBlock
                label="Reading the tiers"
                items={[
                  "LOW — routine monitoring · MEDIUM — watch list · HIGH — priority review · CRITICAL — immediate review queue.",
                  "Tiers rank works for human review — they are indicators, not findings of wrongdoing.",
                ]}
              />
              <AboutBlock
                label="What this data cannot show"
                items={[
                  "No GPS verification, image evidence, or physical-progress fields exist in the source data.",
                  "Low utilization figures can be a conservative expenditure-matching artifact.",
                  "The District Magistrate view is a constituency proxy — no district dimension exists in the data.",
                  "The Report action records an in-app notification in the selected authority's PARAKH inbox — no email/SMS is sent.",
                ]}
              />
            </div>
            <p className="mt-5 border-t border-brd pt-3 text-[11px] leading-relaxed text-faint">
              Full non-claims list: PRD.md §10.2 · Data frozen per decision
              D-027 · Scores computed by the risk aggregator over the frozen
              batch — reproducible run-for-run.
            </p>
          </div>
        )}
      </section>

      {/* ── Investigation history: reports & action trail (D-031 Step 3) ── */}
      <InvestigationHistory projectId={work.project_id} />

      {/* ── Report CTA (Stitch: critical-red button) + printable report ── */}
      {/* Authority-only: reporting routes to an authority inbox and printing
          is an investigation handoff — both belong to the logged-in workflow. */}
      {onReport && (
        <div className="report-actions space-y-3 py-6 text-center">
          <div className="flex flex-wrap items-center justify-center gap-3">
            <button
              onClick={onReport}
              className="inline-flex items-center justify-center rounded-xl border border-transparent bg-critical px-8 py-3.5 text-sm font-bold uppercase tracking-wide text-white shadow-md transition-all hover:bg-red-800"
            >
              Report this work
            </button>
            {onPrint && (
              <button
                onClick={onPrint}
                className="inline-flex items-center justify-center rounded-xl border border-brd bg-surface px-6 py-3.5 text-sm font-bold uppercase tracking-wide text-foreground shadow-sm transition-all hover:border-primary hover:text-primary"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2-4h6a2 2 0 012 2v4a2 2 0 01-2 2H9a2 2 0 01-2-2v-4a2 2 0 012-2zm4-11a2 2 0 012 2v4H9V4a2 2 0 012-2z"
                  />
                </svg>
                Export report (PDF)
              </button>
            )}
          </div>
          <p className="text-xs text-stone-500">
            Report routes an in-app notification to the selected authority&apos;s
            PARAKH alerts inbox — no email/SMS is sent. Export prints a precise
            one-page report: analysis, explainability, and the raw dataset record.
          </p>
        </div>
      )}
    </div>
  );
}

/* ─── Data-list row (Stitch dl style) ────────────────────────────────── */

function DRow({
  label,
  value,
  tone,
  suffix,
}: {
  label: string;
  value?: string;
  tone?: "normal" | "critical" | "amber";
  suffix?: string;
}) {
  const toneClass =
    tone === "critical"
      ? "font-bold text-critical"
      : tone === "amber"
        ? "font-bold text-amber-700"
        : "font-bold text-stone-900";
  return (
    <div
      className={`flex justify-between gap-3 py-2.5 ${tone === "critical" ? "rounded bg-rose-50/50 px-2" : tone === "amber" ? "rounded bg-amber-50/50 px-2" : ""
        }`}
    >
      <dt
        className={
          tone === "critical" ? "font-semibold text-critical" : "text-stone-500"
        }
      >
        {label}
      </dt>
      {value === undefined ? (
        <dd className="italic text-stone-400">Not available</dd>
      ) : (
        <dd className={`text-right ${toneClass}`}>
          {value}
          {suffix ?? ""}
        </dd>
      )}
    </div>
  );
}

/* ─── About-block (methodology accordion content) ────────────────────── */

function AboutBlock({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <p className="section-label">{label}</p>
      <ul className="mt-2 space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-xs leading-relaxed text-stone-600">
            <span aria-hidden className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-stone-400" />
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ─── Report modal (routes a real in-app notification, D-029) ─────────── */

/** Where the report will land, resolved live from the work's own data. */
function deliveryTarget(target: string, work: ProjectDetail): string {
  switch (target) {
    case "MP":
      return work.mp_name || "the work's MP";
    case "State Nodal Officer":
      return `SNO of ${work.state || "the work's state"}`;
    case "District Magistrate":
      return `DM of ${work.constituency || "the work's constituency"} (demo proxy)`;
    default:
      return "MoSPI central audit cell";
  }
}

function ReportModal({
  work,
  onClose,
  reporter,
  attachSummary,
  attachSnapshot,
}: {
  work: ProjectDetail;
  onClose: () => void;
  /** The logged-in authority — fixed, not selectable (who files a report is
   * determined by their session, per the role-in-URL demo auth). */
  reporter: string;
  /** Plain-text snapshot (preview + legacy fallback). */
  attachSummary: string;
  /** Structured snapshot — rendered as rich UI in the inbox. */
  attachSnapshot: ReportSnapshot;
}) {
  const [authority, setAuthority] = useState("MP");
  const [comment, setComment] = useState("");
  const [attach, setAttach] = useState(true);
  const [showAttachPreview, setShowAttachPreview] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { short } = splitId(work.project_id);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await api.createReport({
        project_id: work.project_id,
        reported_by_role: reporter,
        target_role: authority,
        comment: comment.trim() || null,
        summary_md: attach ? attachSummary : null,
        summary_json: attach ? JSON.stringify(attachSnapshot) : null,
      });
      setSubmitted(true);
    } catch (e) {
      setError(String(e instanceof ApiError ? e.message : e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="panel w-full max-w-md !shadow-[var(--shadow-modal)] p-7"
        onClick={(e) => e.stopPropagation()}
      >
        {submitted ? (
          <div className="py-6 text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-low-bg text-2xl text-low">
              ✓
            </div>
            <h3 className="mt-4 font-display text-xl font-bold text-primary">
              Report delivered
            </h3>
            <p className="mt-2 text-sm text-muted">
              Work {short} reported by {reporter} and sent to{" "}
              <strong>{deliveryTarget(authority, work)}</strong> — it now
              appears in their Alerts tab under “This needs your attention”.
            </p>
            <p className="mt-2 text-[11px] text-faint">
              In-app demo notification — no email/SMS is sent.
            </p>
            <button onClick={onClose} className="btn-primary mt-6 px-6 py-2.5 text-sm">
              Close
            </button>
          </div>
        ) : (
          <>
            <h3 className="font-display text-xl font-bold text-primary">
              Report work {short}
            </h3>
            <p className="mt-1 text-xs text-muted">
              Send this flagged work to the responsible authority — it lands in
              their PARAKH alerts inbox for review.
            </p>

            <div className="mt-5">
              <p className="text-xs font-semibold text-muted">Reported by</p>
              <div className="mt-1.5 flex items-center justify-between rounded-lg border border-brd bg-surface-2/60 px-3 py-2.5">
                <span className="text-sm font-bold text-foreground">{reporter}</span>
                <span className="rounded-full bg-low-bg px-2 py-0.5 text-[10px] font-bold text-low">
                  logged in
                </span>
              </div>
            </div>

            <label className="mt-4 block text-xs font-semibold text-muted">
              Reporting authority
              <select
                value={authority}
                onChange={(e) => setAuthority(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-brd bg-surface px-3 py-2.5 text-sm text-foreground focus:border-primary focus:outline-none"
              >
                <option>MP</option>
                <option>District Magistrate</option>
                <option>State Nodal Officer</option>
                <option>MoSPI Audit Cell</option>
              </select>
            </label>
            <p className="mt-1.5 text-[11px] text-faint">
              Will be delivered to: {deliveryTarget(authority, work)}
            </p>

            <label className="mt-4 block text-xs font-semibold text-muted">
              Comment (optional)
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Context for the reviewer…"
                className="mt-1.5 min-h-[90px] w-full rounded-lg border border-brd bg-surface px-3 py-2.5 text-sm text-foreground placeholder:text-faint focus:border-primary focus:outline-none"
              />
            </label>

            {/* Attach analysis snapshot (D-031 Step 1) */}
            <div className="mt-4 rounded-lg border border-brd bg-surface-2/50 p-3">
              <label className="flex cursor-pointer items-start gap-2.5">
                <input
                  type="checkbox"
                  checked={attach}
                  onChange={(e) => setAttach(e.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-[var(--primary)]"
                />
                <span className="text-xs">
                  <span className="font-semibold text-foreground">
                    Attach analysis snapshot
                  </span>
                  <span className="text-muted">
                    {" "}
                    — key insights from this dossier (why flagged, engine
                    scores, key financials) travel with the notification.
                  </span>
                </span>
              </label>
              <button
                type="button"
                onClick={() => setShowAttachPreview((v) => !v)}
                className="mt-2 text-[11px] font-semibold text-primary hover:underline"
              >
                {showAttachPreview ? "Hide preview" : "Preview snapshot"}
              </button>
              {showAttachPreview && (
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-brd bg-white p-2.5 font-mono text-[10px] leading-relaxed text-stone-700">
                  {attachSummary}
                </pre>
              )}
            </div>

            {error && (
              <p className="mt-3 rounded-lg border border-critical/40 bg-critical/10 px-3 py-2 text-xs text-critical">
                {error}
              </p>
            )}

            <div className="mt-5 flex gap-3">
              <button onClick={onClose} className="btn-ghost flex-1 py-2.5 text-sm">
                Cancel
              </button>
              <button
                onClick={submit}
                disabled={submitting}
                className="btn-primary flex-1 py-2.5 text-sm disabled:opacity-60"
              >
                {submitting ? "Sending…" : "Submit report"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
