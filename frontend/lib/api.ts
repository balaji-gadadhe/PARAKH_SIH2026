/**
 * lib/api.ts — PARAKH API client
 * ===============================
 * Thin typed client over the FastAPI backend (backend/app).
 * Matches the Pydantic response models in backend/app/schemas.py.
 *
 * Score convention: the backend stores `overall_risk_score` as 0.0–1.0 and
 * also returns `risk_score_display` (0–100). Display rule: use
 * `risk_score_display` for cards; UI gauges take 0–100 integers.
 *
 * ID convention: `project_id` is a COMPOSITE string
 * ("80673|Shri Harbhajan Singh (2022-28)|Sitting Rajya Sabha|Punjab") —
 * always URL-encode it when building links to /investigation/[projectId].
 *
 * The one-line mock→real swap promised in docs/frontend-skeleton.md §5:
 * everything goes through `apiGet` — change BASE_URL only.
 */

export const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// ─── Types (mirror backend/app/schemas.py) ─────────────────────────────────

export type RiskTier = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface DashboardSummary {
  total_works: number;
  total_mps: number;
  funds_allocated: number;
  funds_utilized: number;
  utilization_pct: number;
  completed_works: number;
  completion_pct: number;
  avg_financial_progress: number;
  tier_distribution: Record<string, number>;
  top_states_by_risk: { state: string; count: number }[];
  top_mps_by_flagged: { mp_name: string; flagged_count: number }[];
}

/** Per-state risk aggregation — GET /api/dashboard/states (D-031 Step 2a). */
export interface StateRiskItem {
  state: string;
  total_works: number;
  low: number;
  medium: number;
  high: number;
  critical: number;
  high_critical: number;
  funds_allocated: number;
  funds_utilized: number;
  flagged_mps: number;
}

export interface StateRiskResponse {
  total_states: number;
  states: StateRiskItem[];
}

export interface ProjectSummary {
  project_id: string;
  mp_name: string;
  state: string;
  constituency: string;
  category: string;
  work_description: string | null;
  status: string | null;
  recommended_amount: number;
  total_expenditure: number;
  expenditure_ratio: number | null;
  is_completed: number | null;
  overall_risk_score: number; // 0.0–1.0
  risk_score_display: number; // 0–100
  risk_category: RiskTier;
  top_risk_signals: string | null;
}

export interface EngineBreakdown {
  engine: string;
  score: number | null;
  flag: boolean | null;
  available: boolean | null;
}

export interface ProjectDetail {
  project_id: string;
  mp_name: string;
  state: string;
  constituency: string;
  category: string;
  work_description: null | string;
  status: null | string;
  overall_risk_score: number;
  risk_score_display: number;
  risk_category: RiskTier;
  audit_explanation: string | null;
  top_risk_signals: string | null;
  risk_factors: string | null; // JSON array string
  evidence_payload: string | null; // JSON object string
  engines: EngineBreakdown[];
  investigation_priority: number | null; // 0–100
  investigation_urgency:
    | "TIER_1_IMMEDIATE_ACTION"
    | "TIER_2_PRIORITY_INSPECTION"
    | "TIER_3_DESK_REVIEW"
    | "TIER_4_ROUTINE"
    | null;
  audit_dispatch_recommended: boolean | null;
  recommended_amount: number;
  final_amount: number | null;
  total_expenditure: number;
  expenditure_ratio: number | null;
  cost_variation_pct: number | null;
  peer_median_cost: number | null;
  peer_mean_cost: number | null;
  peer_std_cost: number | null;
  cost_deviation_from_peer: number | null;
  payment_count: number | null;
  average_payment: number | null;
  maximum_payment: number | null;
  minimum_payment: number | null;
  payment_frequency: number | null;
  successful_payment_count: number | null;
  pending_payment_count: number | null;
  latest_payment_status: string | null;
  primary_vendor: string | null;
  vendor_risk_score: number | null;
  vendor_risk_level: string | null;
  days_since_recommendation: number | null;
  recommendation_to_completion_days: number | null;
  average_rating: number | null;
  has_images: boolean | null;
  ida: boolean | null;
  description_similarity_score: number | null;
  is_completed: number | null;
}

export interface ProjectListResponse {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  items: ProjectSummary[];
}

export interface MpSummary {
  mp_name: string;
  state: string;
  constituency: string;
  house: string | null;
  recommended_works: number | null;
  completed_works: null | number;
  completion_rate_pct: number | null;
  allocated_amount: number | null;
  total_expenditure: number | null;
  utilization_pct: number | null;
  unspent_amount: number | null;
  pending_payments: number | null;
  average_rating: number | null;
  flagged_works: number;
}

export interface MpDetail {
  mp: MpSummary;
  works: ProjectSummary[];
  total_works: number;
  critical_works: number;
  high_risk_works: number;
  medium_risk_works: number;
  low_risk_works: number;
  average_risk_score: number | null;
  highest_work_risk: number | null;
}

export interface MpListResponse {
  total: number;
  items: MpSummary[];
}

export interface AlertItem {
  project_id: string;
  mp_name: string;
  state: string;
  constituency: string;
  risk_score_display: number;
  risk_category: RiskTier;
  top_risk_signals: string | null;
  recommended_amount: number;
  total_expenditure: number;
}

export interface SignalAggregate {
  signal: string;
  count: number;
}

export interface AlertListResponse {
  total: number;
  tier_counts: Record<string, number>;
  signal_aggregates: SignalAggregate[];
  items: AlertItem[];
  page: number;
  page_size: number;
  pages: number;
}

export interface AgencySummary {
  agency_id: string;
  agency_risk_score: number | null;
  agency_risk_level: string | null;
  total_works: number | null;
  avg_completion_rate: number | null;
}

export interface AgencyListResponse {
  total: number;
  items: AgencySummary[];
}

// ─── Reports (authority notifications, D-029) ────────────────────────────────

/** Authority options as offered by the Report modal (backend routes by these). */
export const AUTHORITY_OPTIONS = [
  "MP",
  "District Magistrate",
  "State Nodal Officer",
  "MoSPI Audit Cell",
] as const;

export interface ReportItem {
  id: number;
  project_id: string;
  reported_by_role: string;
  target_role: string;
  comment: string | null;
  summary_md: string | null;
  summary_json: string | null;
  status: "NEW" | "ACKNOWLEDGED";
  created_at: string;
  acknowledged_at?: string | null;
  // Enrichment from risk_results (joined at read time)
  mp_name: string;
  state: string;
  risk_score_display: number;
  risk_category: RiskTier;
}

/**
 * Structured analysis snapshot attached to a report (D-031 Step-1 follow-up).
 * Stored as a JSON string in `summary_json`; the inbox renders it as rich UI
 * (chips + labeled rows) instead of a plain-text blob.
 */
export interface ReportSnapshot {
  tier: RiskTier;
  score: number;
  status: string | null;
  category: string;
  mp: string;
  state: string;
  constituency: string;
  description: string | null;
  why_flagged: string | null;
  flagged_engines: { engine: string; score: number | null }[];
  financials: { label: string; value: string; warn?: boolean }[];
  payments: { label: string; value: string }[];
  triage: { label: string; value: string }[];
}

/** GET /api/reports/{id}/summary — attached analysis snapshot (D-031 Step 1). */
export interface ReportSummary {
  report_id: number;
  project_id: string;
  status: string;
  created_at: string;
  acknowledged_at: string | null;
  reported_by_role: string;
  target_role: string;
  comment: string | null;
  summary_md: string | null;
}

/** One event in a work's investigation history (D-031 Step 3). */
export interface ReportEvent {
  id: number;
  reported_by_role: string;
  target_role: string;
  comment: string | null;
  has_snapshot: boolean;
  status: "NEW" | "ACKNOWLEDGED";
  created_at: string;
  acknowledged_at: string | null;
}

/** GET /api/reports/history/{project_id} — the work's report trail. */
export interface ProjectHistoryResponse {
  project_id: string;
  mp_name: string;
  state: string;
  risk_category: RiskTier;
  risk_score_display: number;
  total_reports: number;
  new_reports: number;
  events: ReportEvent[];
}

export interface ReportListResponse {
  total: number;
  items: ReportItem[];
}

// ─── Core fetch helper ──────────────────────────────────────────────────────

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function apiGet<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, BASE_URL);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "" && v !== null) {
        url.searchParams.set(k, String(v));
        }
    }
  }
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, `API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

async function apiPost<T>(
  path: string,
  body: unknown,
  params?: Record<string, string | number | undefined>
): Promise<T> {
  const url = new URL(path, BASE_URL);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "" && v !== null) {
        url.searchParams.set(k, String(v));
      }
    }
  }
  const res = await fetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === null ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const errBody = await res.json();
      detail = errBody?.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, `API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

// ─── API functions ──────────────────────────────────────────────────────────

export const api = {
  // Dashboard
  dashboardSummary: () => apiGet<DashboardSummary>("/api/dashboard/summary"),

  // State risk aggregation (India map + state panels, D-031 Step 2)
  stateRisk: () => apiGet<StateRiskResponse>("/api/dashboard/states"),

  // Projects
  listProjects: (params: {
    q?: string;
    tier?: RiskTier | "";
    state?: string;
    mp?: string;
    house?: string;
    category?: string;
    status?: string;
    min_score?: number;
    sort?: string;
    page?: number;
    page_size?: number;
  }) => apiGet<ProjectListResponse>("/api/projects", params as Record<string, string | number | undefined>),

  projectDetail: (projectId: string) =>
    apiGet<ProjectDetail>(`/api/projects/${encodeURIComponent(projectId)}`),

  // MPs
  listMps: (params: {
    q?: string;
    state?: string;
    house?: string;
    sort?: string;
  }) => apiGet<MpListResponse>("/api/mps", params as Record<string, string | number | undefined>),

  mpDetail: (mpName: string) =>
    apiGet<MpDetail>(`/api/mps/${encodeURIComponent(mpName)}`),

  // Alerts
  listAlerts: (params: {
    tier?: RiskTier | "";
    type?: string;
    state?: string;
    mp?: string;
    min_score?: number;
    q?: string;
    page?: number;
    page_size?: number;
  }) => apiGet<AlertListResponse>("/api/alerts", params as Record<string, string | number | undefined>),

  // Agencies
  listAgencies: (params: {
    q?: string;
    risk_level?: string;
    sort?: string;
    page?: number;
    page_size?: number;
  }) => apiGet<AgencyListResponse>("/api/agencies", params as Record<string, string | number | undefined>),

  // Reports (authority notifications, D-029 + D-031 Step 1)
  createReport: (payload: {
    project_id: string;
    reported_by_role: string;
    target_role: string;
    comment?: string | null;
    summary_md?: string | null;
    summary_json?: string | null;
  }) => apiPost<ReportItem>("/api/reports", payload),

  reportSummary: (id: number, params: { role: string; mp?: string; state?: string }) =>
    apiGet<ReportSummary>(
      `/api/reports/${id}/summary`,
      params as Record<string, string | number | undefined>
    ),

  // Investigation history for one work (D-031 Step 3)
  projectHistory: (projectId: string) =>
    apiGet<ProjectHistoryResponse>(
      `/api/reports/history/${encodeURIComponent(projectId)}`
    ),

  listReports: (params: {
    role: string;
    mp?: string;
    state?: string;
    status?: string;
  }) => apiGet<ReportListResponse>("/api/reports", params as Record<string, string | number | undefined>),

  ackReport: async (id: number, params: { role: string; mp?: string; state?: string }) => {
    const res = await apiPost<{ ok: boolean; id: number; status: string }>(
      `/api/reports/${id}/ack`,
      null,
      params as Record<string, string | number | undefined>
    );
    notifyReportsChanged();
    return res;
  },

  clearReports: async (params: {
    role: string;
    mp?: string;
    state?: string;
    status?: string;
  }) => {
    const res = await apiPost<{ ok: boolean; deleted: number }>(
      "/api/reports/clear",
      null,
      params as Record<string, string | number | undefined>
    );
    notifyReportsChanged();
    return res;
  },
};

/** Fired after ack/clear so live badges (dashboard header, inbox) can refresh. */
export const REPORTS_CHANGED_EVENT = "parakh:reports-changed";

function notifyReportsChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(REPORTS_CHANGED_EVENT));
  }
}

// ─── Formatting helpers (docs/frontend_card_reference.md §6 + honesty policy) ───

/** Format ₹ amounts with Indian Lakh/Crore units. */
export function formatINR(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "Not available";
  if (value >= 10000000) return `₹${(value / 10000000).toFixed(2)} Cr`;
  if (value >= 100000) return `₹${(value / 100000).toFixed(2)} L`;
  return `₹${value.toLocaleString("en-IN")}`;
}

/** Full Indian digit grouping (₹12,39,80,319). */
export function formatINRFull(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "Not available";
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

/** Never render raw NaN/None — "Not available" per card reference §6. */
export function notAvailable(value: number | string | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "Not available";
  return String(value);
}

/** Human labels for investigation urgency tiers. */
export const URGENCY_LABELS: Record<string, string> = {
  TIER_1_IMMEDIATE_ACTION: "Tier 1 — Immediate Action",
  TIER_2_PRIORITY_INSPECTION: "Tier 2 — Priority Inspection",
  TIER_3_DESK_REVIEW: "Tier 3 — Desk Review",
  TIER_4_ROUTINE: "Tier 4 — Routine",
};

/** Risk tier styling classes (tier colors only — neutral shell comes from the theme tokens). */
export const TIER_STYLES: Record<RiskTier, { text: string; bg: string; border: string }> = {
  LOW: { text: "text-low", bg: "bg-low/15", border: "border-low/40" },
  MEDIUM: { text: "text-medium", bg: "bg-medium/15", border: "border-medium/40" },
  HIGH: { text: "text-high", bg: "bg-high/15", border: "border-high/40" },
  CRITICAL: { text: "text-critical", bg: "bg-critical/15", border: "border-critical/40" },
};
