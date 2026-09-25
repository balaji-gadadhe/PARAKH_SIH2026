"use client";

/**
 * components/work-report.tsx — printable Investigation Report (D-031 Step 1).
 *
 * A precise, judge-friendly one-pager rendered from the SAME live ProjectDetail
 * the dossier uses — no recompute, no fabrication (D-008). Structure:
 *   A. Work identity        B. Assessment outcome        C. Why flagged
 *   D. Engine breakdown     E. Financials                F. Raw data record
 * Section F is the verbatim dataset fields (the raw evidence trail). Missing
 * values render "Not available" — never invented (honesty policy §6.4).
 *
 * Print path: the sheet lives in the DOM inside `.print-area`; the app shell
 * around it is hidden via the `@media print` rules in globals.css, so
 * window.print() produces exactly this document (offline, no deps).
 */

import {
  formatINR,
  formatINRFull,
  notAvailable,
  URGENCY_LABELS,
  type ProjectDetail,
  type ReportSnapshot,
} from "@/lib/api";

/** Composite ID "80673|MP|PC|State" → "80673". */
function shortId(id: string): string {
  return id.split("|")[0] ?? id;
}

/** "payment_success" → "Payment success". */
function humanize(s: string | null): string {
  if (!s) return "Not available";
  const t = s.toLowerCase().replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

function Section({
  n,
  title,
  className,
  children,
}: {
  n: string;
  title: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={`report-section${className ? ` ${className}` : ""}`}>
      <h2>
        <span className="report-n">{n}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ k, v, warn }: { k: string; v?: string; warn?: boolean }) {
  return (
    <div className="report-row">
      <dt>{k}</dt>
      <dd className={warn ? "report-warn" : undefined}>
        {v ?? "Not available"}
      </dd>
    </div>
  );
}

/**
 * Structured snapshot attached to POST /api/reports (D-031 Step-1 follow-up).
 * Values are PRE-FORMATTED display strings — the inbox renders them as rich
 * UI (chips + labeled rows), no parsing/formatting logic there. Kept under
 * the backend's 4000-char JSON cap.
 */
export function buildReportSnapshot(work: ProjectDetail): ReportSnapshot {
  const flagged = work.engines
    .filter((e) => e.available && e.flag)
    .map((e) => ({ engine: e.engine, score: e.score != null ? Math.round(e.score * 100) : null }));
  const ratioWarn = work.expenditure_ratio != null && work.expenditure_ratio > 2;
  return {
    tier: work.risk_category,
    score: work.risk_score_display,
    status: work.status,
    category: work.category,
    mp: work.mp_name,
    state: work.state,
    constituency: work.constituency,
    description: work.work_description,
    why_flagged: work.audit_explanation,
    flagged_engines: flagged,
    financials: [
      { label: "Recommended", value: formatINRFull(work.recommended_amount) },
      { label: "Expenditure", value: formatINRFull(work.total_expenditure), warn: ratioWarn },
      ...(work.expenditure_ratio != null
        ? [{ label: "Expenditure ratio", value: `${work.expenditure_ratio.toFixed(2)}x`, warn: ratioWarn }]
        : []),
      ...(work.cost_deviation_from_peer != null
        ? [{ label: "Cost deviation from peers", value: `${work.cost_deviation_from_peer.toFixed(1)}%` }]
        : []),
    ],
    payments: [
      { label: "Payments recorded", value: notAvailable(work.payment_count) },
      { label: "Latest payment status", value: work.latest_payment_status ?? "Not available" },
    ],
    triage: [
      {
        label: "Priority",
        value: work.investigation_priority != null ? `${work.investigation_priority} / 100` : "Not available",
      },
      {
        label: "Urgency",
        value: work.investigation_urgency
          ? URGENCY_LABELS[work.investigation_urgency] ?? work.investigation_urgency
          : "Not available",
      },
      {
        label: "Audit dispatch",
        value:
          work.audit_dispatch_recommended == null
            ? "Not available"
            : work.audit_dispatch_recommended
              ? "Recommended"
              : "Not recommended",
      },
    ],
  };
}

/**
 * Plain-text snapshot attached to POST /api/reports (D-031 Step 1) — the
 * report's key insights ride along to the authority's inbox. Precise:
 * identity → why flagged → key financials → triage, all from live data.
 * Capped under the backend's 4000-char limit.
 */
export function buildReportSummary(work: ProjectDetail): string {
  const flagged = work.engines.filter((e) => e.available && e.flag);
  const lines: string[] = [];
  lines.push(
    `RISK SNAPSHOT — Work ${shortId(work.project_id)} (${work.risk_category}, ${work.risk_score_display}/100)`
  );
  lines.push(`Work: ${work.work_description ?? "description not recorded"}`);
  lines.push(`MP: ${work.mp_name} · State: ${work.state} · ${work.constituency}`);
  lines.push(`Category: ${work.category} · Status: ${humanize(work.status)}`);
  lines.push("");
  lines.push("WHY FLAGGED (risk indicators, not findings):");
  lines.push(work.audit_explanation ?? "No explanation recorded for this work.");
  if (flagged.length) {
    lines.push(
      `Flagged engines: ${flagged
        .map((e) => `${e.engine} ${e.score != null ? Math.round(e.score * 100) : "—"}/100`)
        .join(" · ")}`
    );
  }
  lines.push("");
  lines.push("KEY FINANCIALS (dataset fields):");
  lines.push(
    `Recommended: ${formatINRFull(work.recommended_amount)} · Expenditure: ${formatINRFull(
      work.total_expenditure
    )}${work.expenditure_ratio != null ? ` · Ratio: ${work.expenditure_ratio.toFixed(2)}x` : ""}`
  );
  if (work.cost_deviation_from_peer != null)
    lines.push(`Cost deviation from peers: ${work.cost_deviation_from_peer.toFixed(1)}%`);
  if (work.primary_vendor)
    lines.push(
      `Primary vendor: ${work.primary_vendor}${
        work.vendor_risk_score != null
          ? ` (risk ${work.vendor_risk_score}${work.vendor_risk_level ? ` · ${work.vendor_risk_level}` : ""})`
          : ""
      }`
    );
  lines.push(
    `Payments: ${work.payment_count ?? "not available"} recorded · Status: ${
      work.latest_payment_status ?? "not available"
    }`
  );
  lines.push("");
  lines.push(
    `Priority ${work.investigation_priority ?? "n/a"}/100 · ${
      work.investigation_urgency
        ? URGENCY_LABELS[work.investigation_urgency] ?? work.investigation_urgency
        : "urgency n/a"
    } · Audit dispatch: ${
      work.audit_dispatch_recommended == null
        ? "n/a"
        : work.audit_dispatch_recommended
          ? "recommended"
          : "not recommended"
    }`
  );
  lines.push(
    "Source: PARAKH over the frozen MPLADS batch 2026-09-01 — indicators for review, not findings (PRD §10.2)."
  );
  return lines.join("\n").slice(0, 3800);
}

export function WorkReportSheet({ work }: { work: ProjectDetail }) {
  const flaggedEngines = work.engines.filter((e) => e.available && e.flag);
  const availableEngines = work.engines.filter((e) => e.available);
  const urgency = work.investigation_urgency
    ? URGENCY_LABELS[work.investigation_urgency] ?? work.investigation_urgency
    : null;
  const generated = new Date().toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="report-sheet" id="investigation-report">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="report-header">
        <div>
          <p className="report-kicker">PARAKH · MoSPI · PS 26102 — Investigation Report (demo)</p>
          <h1>Work {shortId(work.project_id)}</h1>
          <p className="report-sub">{work.work_description ?? "Work description not recorded"}</p>
        </div>
        <div className="report-scorebox">
          <span className="report-score">{work.risk_score_display}</span>
          <span className="report-score-tier">/ 100 · {work.risk_category}</span>
        </div>
      </header>

      {/* ── Key facts strip (at-a-glance, before the detail) ───────────── */}
      <div className="report-keyfacts">
        <div>
          <span>MP</span>
          <strong>{work.mp_name}</strong>
        </div>
        <div>
          <span>State</span>
          <strong>{work.state}</strong>
        </div>
        <div>
          <span>Recommended</span>
          <strong>{formatINR(work.recommended_amount)}</strong>
        </div>
        <div>
          <span>Expenditure</span>
          <strong>{formatINR(work.total_expenditure)}</strong>
        </div>
        <div>
          <span>Engines flagged</span>
          <strong>
            {flaggedEngines.length} / {work.engines.length}
          </strong>
        </div>
      </div>

      {/* ── A. Identity ────────────────────────────────────────────────── */}
      <Section n="A" title="Work identity">
        <dl>
          <Row k="Work description" v={work.work_description ?? undefined} />
          <Row k="MP" v={work.mp_name} />
          <Row k="State" v={work.state} />
          <Row k="Constituency" v={work.constituency} />
          <Row k="Category" v={work.category} />
          <Row k="Status (source field)" v={humanize(work.status)} />
          <Row k="Project ID (composite key)" v={work.project_id} />
        </dl>
      </Section>

      {/* ── B. Assessment outcome ──────────────────────────────────────── */}
      <Section n="B" title="Assessment outcome">
        <dl>
          <Row k="Overall risk score" v={`${work.risk_score_display} / 100 (${work.risk_category} tier)`} warn={work.risk_category === "CRITICAL" || work.risk_category === "HIGH"} />
          <Row
            k="Investigation priority"
            v={work.investigation_priority != null ? `${work.investigation_priority} / 100` : undefined}
          />
          <Row k="Urgency" v={urgency ?? undefined} />
          <Row
            k="Audit dispatch recommended"
            v={work.audit_dispatch_recommended == null ? undefined : work.audit_dispatch_recommended ? "Yes" : "No"}
          />
          <Row
            k="Engines flagged"
            v={`${flaggedEngines.length} of ${work.engines.length} (data on ${availableEngines.length})`}
            warn={flaggedEngines.length > 0}
          />
        </dl>
      </Section>

      {/* ── C. Why flagged ─────────────────────────────────────────────── */}
      <Section n="C" title="Why this work is flagged">
        <p className="report-para">
          {work.audit_explanation ?? "No explanation recorded for this work."}
        </p>
        {flaggedEngines.length > 0 && (
          <ul className="report-list">
            {flaggedEngines.map((e) => (
              <li key={e.engine}>
                <strong>{e.engine}</strong> — score{" "}
                {e.score != null ? `${Math.round(e.score * 100)}/100` : "not available"}
              </li>
            ))}
          </ul>
        )}
        <p className="report-note">
          These are risk indicators that rank the work for human review — not
          findings of wrongdoing.
        </p>
      </Section>

      {/* ── D. Engine breakdown ────────────────────────────────────────── */}
      <Section n="D" title="Detection engine breakdown">
        <table className="report-table">
          <thead>
            <tr>
              <th>Engine</th>
              <th>Score</th>
              <th>Flag</th>
            </tr>
          </thead>
          <tbody>
            {work.engines.map((e) => (
              <tr key={e.engine}>
                <td>{e.engine}</td>
                <td>
                  {e.available && e.score != null ? `${Math.round(e.score * 100)}/100` : "Not available"}
                </td>
                <td>{e.available ? (e.flag ? "Flagged" : "Normal") : "Not available"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {/* ── E. Financials ──────────────────────────────────────────────── */}
      <Section n="E" title="Financials">
        <dl>
          <Row k="Recommended amount" v={formatINRFull(work.recommended_amount)} />
          <Row k="Final amount" v={work.final_amount != null ? formatINRFull(work.final_amount) : undefined} />
          <Row
            k="Total expenditure"
            v={formatINRFull(work.total_expenditure)}
            warn={work.expenditure_ratio != null && work.expenditure_ratio > 2}
          />
          <Row
            k="Expenditure ratio"
            v={work.expenditure_ratio != null ? `${work.expenditure_ratio.toFixed(2)}x` : undefined}
            warn={work.expenditure_ratio != null && work.expenditure_ratio > 2}
          />
          <Row k="Cost variation" v={work.cost_variation_pct != null ? `${work.cost_variation_pct}%` : undefined} />
          <Row
            k="Deviation from peer cost"
            v={work.cost_deviation_from_peer != null ? `${work.cost_deviation_from_peer.toFixed(1)}%` : undefined}
          />
          <Row k="Peer median cost" v={work.peer_median_cost != null ? formatINR(work.peer_median_cost) : undefined} />
        </dl>
        <p className="report-note">
          Utilization figures can be a conservative artifact of the
          expenditure-matching process — low ratios are not, by themselves,
          evidence of wrongdoing.
        </p>
      </Section>

      {/* ── F. Raw data record (verbatim dataset fields) — own page ────── */}
      <Section n="F" title="Raw data record (dataset fields as ingested)" className="report-pagebreak">
        <dl className="report-raw">
          <Row k="recommended_amount" v={notAvailable(work.recommended_amount)} />
          <Row k="final_amount" v={work.final_amount != null ? notAvailable(work.final_amount) : undefined} />
          <Row k="total_expenditure" v={notAvailable(work.total_expenditure)} />
          <Row k="expenditure_ratio" v={work.expenditure_ratio != null ? notAvailable(work.expenditure_ratio) : undefined} />
          <Row k="is_completed" v={work.is_completed != null ? notAvailable(work.is_completed) : undefined} />
          <Row k="status" v={work.status ?? undefined} />
          <Row k="payment_count" v={work.payment_count != null ? notAvailable(work.payment_count) : undefined} />
          <Row k="average_payment" v={work.average_payment != null ? notAvailable(work.average_payment) : undefined} />
          <Row k="maximum_payment" v={work.maximum_payment != null ? notAvailable(work.maximum_payment) : undefined} />
          <Row k="latest_payment_status" v={work.latest_payment_status ?? undefined} />
          <Row k="pending_payment_count" v={work.pending_payment_count != null ? notAvailable(work.pending_payment_count) : undefined} />
          <Row k="days_since_recommendation" v={work.days_since_recommendation != null ? notAvailable(work.days_since_recommendation) : undefined} />
          <Row
            k="recommendation_to_completion_days"
            v={work.recommendation_to_completion_days != null ? notAvailable(work.recommendation_to_completion_days) : undefined}
          />
          <Row k="has_images" v={work.has_images != null ? (work.has_images ? "True" : "False") : undefined} />
          <Row k="ida" v={work.ida != null ? (work.ida ? "True" : "False") : undefined} />
          <Row k="description_similarity_score" v={work.description_similarity_score != null ? notAvailable(work.description_similarity_score) : undefined} />
          <Row k="primary_vendor" v={work.primary_vendor ?? undefined} />
          <Row k="vendor_risk_score" v={work.vendor_risk_score != null ? notAvailable(work.vendor_risk_score) : undefined} />
        </dl>
      </Section>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer className="report-footer">
        <p>
          Generated {generated} from PARAKH over the frozen MPLADS batch
          (2026-09-01). Detection outputs are risk indicators for prioritizing
          human review — not confirmed fraud or legal findings. PRD §10.2.
        </p>
      </footer>
    </div>
  );
}
