/**
 * lib/citizen-api.ts — Citizen Participation Portal client (D-032)
 * ================================================================
 * Typed client over the /api/citizen endpoints (backend/app/routers/citizen.py)
 * plus the per-browser demo session (localStorage).
 *
 * Honesty (mirrors the backend): the Aadhaar+OTP flow is SIMULATED — the
 * session token is demo-grade and every surface using this client must keep
 * the "demo" labeling. PSI is a participation signal, never a detection
 * engine. Images/coords are citizen-submitted and UNVERIFIED.
 */

import { BASE_URL } from "./api";
import type { RiskTier } from "./api";

// ─── Types (mirror backend/app/schemas.py Citizen*) ─────────────────────────

export interface CitizenLoginResponse {
  token: string;
  masked_id: string;
  is_new: boolean;
  demo_notice: string;
}

export interface CitizenMe {
  masked_id: string;
  created_at: string;
  upvotes_cast: number;
  reports_filed: number;
}

export interface CitizenVoteResponse {
  project_id: string;
  voted: boolean;
  upvote_count: number;
  demo_notice: string;
}

export interface CitizenConcernCount {
  reason: string;
  count: number;
  report_count?: number;
  upvote_count?: number;
}

export interface CitizenFeedItem {
  project_id: string;
  work_description: string | null;
  mp_name: string;
  state: string;
  constituency: string;
  category: string;
  status: string | null;
  risk_category: RiskTier;
  risk_score_display: number;
  recommended_amount: number;
  upvote_count: number;
  report_count: number;
  /** Top combined concern reasons (votes + reports tallied together). */
  top_concerns: CitizenConcernCount[];
  /** Mean of citizens' 1–5 satisfaction ratings (null = unrated). */
  satisfaction_avg: number | null;
  satisfaction_count: number;
  voted: boolean | null;
}

export interface CitizenFeedResponse {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  demo_seed: boolean;
  items: CitizenFeedItem[];
}

export type LocationSanity =
  | "PLAUSIBLE"
  | "FAR_FROM_CLAIMED_STATE"
  | "NO_LOCATION"
  | "NO_REFERENCE";

export interface CitizenReportItem {
  id: number;
  project_id: string;
  masked_id: string;
  criteria: string[];
  satisfaction: number | null; // 1–5 (null = problem report only)
  comment: string | null;
  has_image: boolean;
  image_url: string | null;
  latitude: number | null;
  longitude: number | null;
  location_sanity: LocationSanity | null;
  verification_status: string;
  is_seed: boolean;
  created_at: string;
  work_description: string | null;
  mp_name: string;
  state: string;
  risk_category: string;
  risk_score_display: number;
}

export interface CitizenPsiResponse {
  project_id: string;
  upvote_count: number;
  report_count: number;
  distinct_citizens: number;
  psi_score: number;
  label: "NO_SIGNAL" | "LOW" | "MODERATE" | "HIGH";
  /** Upvote-why + report-criteria tags tallied together (same vocabulary),
   * each with the honest split: reports are evidence-bearing, upvotes echoes. */
  reasons_breakdown: {
    reason: string;
    count: number;
    report_count: number;
    upvote_count: number;
  }[];
  satisfaction_avg: number | null; // mean of 1–5 ratings (null = no ratings)
  satisfaction_count: number;
  methodology: string;
  disclaimer: string;
}

export interface CitizenReportListResponse {
  total: number;
  items: CitizenReportItem[];
}

export interface CitizenOverviewResponse {
  total_citizens: number;
  total_upvotes: number;
  total_reports: number;
  works_engaged: number;
  top_upvoted: CitizenFeedItem[];
  recent_reports: CitizenReportItem[];
  by_state: { state: string; engaged_works: number }[];
  demo_seed: boolean;
  demo_notice: string;
}

export interface CitizenFacetState {
  state: string;
  works: number;
  constituencies: string[];
  mps: string[];
}

export interface CitizenFacetsResponse {
  total_states: number;
  total_constituencies: number;
  states: CitizenFacetState[];
}

// ─── Demo session (per-browser localStorage) ────────────────────────────────

const CITIZEN_TOKEN_KEY = "parakh_citizen_token";
const CITIZEN_MASKED_KEY = "parakh_citizen_masked";

export interface CitizenSession {
  token: string;
  maskedId: string;
}

export function getCitizenSession(): CitizenSession | null {
  if (typeof window === "undefined") return null;
  const token = window.localStorage.getItem(CITIZEN_TOKEN_KEY);
  const maskedId = window.localStorage.getItem(CITIZEN_MASKED_KEY);
  if (!token || !maskedId) return null;
  return { token, maskedId };
}

export function setCitizenSession(session: CitizenSession): void {
  window.localStorage.setItem(CITIZEN_TOKEN_KEY, session.token);
  window.localStorage.setItem(CITIZEN_MASKED_KEY, session.maskedId);
}

export function clearCitizenSession(): void {
  window.localStorage.removeItem(CITIZEN_TOKEN_KEY);
  window.localStorage.removeItem(CITIZEN_MASKED_KEY);
}

// ─── Fetch helpers (same error discipline as lib/api.ts) ────────────────────

export class CitizenApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function citizenGet<T>(
  path: string,
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
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new CitizenApiError(res.status, `API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

async function citizenPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(new URL(path, BASE_URL).toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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
    throw new CitizenApiError(res.status, `API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

/** Multipart POST — file uploads (citizen reports with photo). */
async function citizenPostForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(new URL(path, BASE_URL).toString(), {
    method: "POST",
    body: form,
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
    throw new CitizenApiError(res.status, `API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

// ─── API functions ──────────────────────────────────────────────────────────

export const citizenApi = {
  login: (aadhaar: string, otp: string) =>
    citizenPost<CitizenLoginResponse>("/api/citizen/login", { aadhaar, otp }),

  me: (token: string) =>
    citizenGet<CitizenMe>("/api/citizen/me", { token }),

  vote: (token: string, projectId: string, reasons?: string[]) =>
    citizenPost<CitizenVoteResponse>("/api/citizen/vote", {
      token,
      project_id: projectId,
      reasons: reasons && reasons.length > 0 ? reasons : undefined,
    }),

  feed: (params: {
    token?: string;
    q?: string;
    tier?: RiskTier | "";
    state?: string;
    constituency?: string;
    mp?: string;
    category?: string;
    sort?: string;
    page?: number;
    page_size?: number;
  }) =>
    citizenGet<CitizenFeedResponse>(
      "/api/citizen/feed",
      params as Record<string, string | number | undefined>
    ),

  overview: () => citizenGet<CitizenOverviewResponse>("/api/citizen/overview"),

  /** Facet index for the feed's 'near me' filters — real states, their
   * constituencies and MPs, straight from the dataset. */
  facets: () => citizenGet<CitizenFacetsResponse>("/api/citizen/facets"),

  /** Public citizen reports (optionally filtered to one work) — used by the
   * dossier's "What the public says" section. */
  listReports: (params?: { project_id?: string; limit?: number }) =>
    citizenGet<CitizenReportListResponse>(
      "/api/citizen/reports",
      params as Record<string, string | number | undefined>
    ),

  /** File a citizen report (multipart: photo + claimed coords, all UNVERIFIED).
   * Problem report: ≥1 criteria. Pure feedback: satisfaction 1–5, no criteria. */
  createReport: (fields: {
    token: string;
    projectId: string;
    criteria?: string[];
    satisfaction?: number | null;
    comment?: string;
    image?: File | null;
    latitude?: number | null;
    longitude?: number | null;
  }) => {
    const fd = new FormData();
    fd.set("token", fields.token);
    fd.set("project_id", fields.projectId);
    fd.set("criteria", (fields.criteria ?? []).join(","));
    if (fields.satisfaction != null) fd.set("satisfaction", String(fields.satisfaction));
    if (fields.comment) fd.set("comment", fields.comment);
    if (fields.image) fd.set("image", fields.image);
    if (fields.latitude != null) fd.set("latitude", String(fields.latitude));
    if (fields.longitude != null) fd.set("longitude", String(fields.longitude));
    return citizenPostForm<CitizenReportItem>("/api/citizen/reports", fd);
  },

  psi: (projectId: string) =>
    citizenGet<CitizenPsiResponse>(
      `/api/citizen/psi/${encodeURIComponent(projectId)}`
    ),
};

/** Criteria vocabulary for citizen reports (mirrors REPORT_CRITERIA backend). */
export const CITIZEN_CRITERIA: { key: string; label: string }[] = [
  { key: "stalled", label: "Work stalled / no progress" },
  { key: "quality", label: "Poor work quality" },
  { key: "cost", label: "Cost looks inflated" },
  { key: "ghost", label: "Work may not exist" },
  { key: "other", label: "Other concern" },
];
