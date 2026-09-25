"""
schemas.py
==========
Pydantic models for API request/response schemas.
Matches the columns of project_risk_results.csv (33 columns).
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ─── Dashboard ────────────────────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    total_works: int
    total_mps: int
    funds_allocated: float
    funds_utilized: float
    utilization_pct: float
    completed_works: int
    completion_pct: float
    avg_financial_progress: float
    tier_distribution: dict  # {"CRITICAL": 24, "HIGH": 158, ...}
    top_states_by_risk: list  # [{"state": "...", "count": 12}, ...]
    top_mps_by_flagged: list  # [{"mp_name": "...", "flagged_count": 5}, ...]


class StateRiskItem(BaseModel):
    """Per-state risk aggregation (D-031 Step 2a — India map + state panels).
    Frozen columns only: state, risk_category, recommended_amount,
    total_expenditure, mp_name."""
    state: str
    total_works: int
    low: int
    medium: int
    high: int
    critical: int
    high_critical: int          # HIGH + CRITICAL — map coloring priority
    funds_allocated: float      # Σ recommended_amount
    funds_utilized: float       # Σ total_expenditure
    flagged_mps: int            # distinct MPs with a HIGH/CRITICAL work


class StateRiskResponse(BaseModel):
    total_states: int
    states: List[StateRiskItem]  # sorted by high_critical desc, then works desc


# ─── Projects ─────────────────────────────────────────────────────────────────

class ProjectSummary(BaseModel):
    """List-level project fields (used in paginated lists)."""
    project_id: str
    mp_name: str
    state: str
    constituency: str
    category: str
    work_description: Optional[str] = None
    status: Optional[str] = None
    recommended_amount: float
    total_expenditure: float
    expenditure_ratio: Optional[float] = None
    is_completed: Optional[int] = None
    overall_risk_score: float  # 0.0–1.0 (API will multiply by 100)
    risk_score_display: int    # 0–100 for frontend
    risk_category: str
    top_risk_signals: Optional[str] = None


class EngineBreakdown(BaseModel):
    engine: str
    score: Optional[float] = None
    flag: Optional[bool] = None
    available: Optional[bool] = None


class ProjectDetail(BaseModel):
    """Full project detail (used in investigation view)."""
    # Identity
    project_id: str
    mp_name: str
    state: str
    constituency: str
    category: str
    work_description: Optional[str] = None
    status: Optional[str] = None
    # Risk summary
    overall_risk_score: float
    risk_score_display: int
    risk_category: str
    audit_explanation: Optional[str] = None
    top_risk_signals: Optional[str] = None
    risk_factors: Optional[str] = None  # JSON array string
    evidence_payload: Optional[str] = None  # JSON object string
    engines: List[EngineBreakdown]
    # Investigation fields (docs/frontend_card_reference.md §2)
    investigation_priority: Optional[float] = None  # 0–100
    investigation_urgency: Optional[str] = None  # TIER_1..4
    audit_dispatch_recommended: Optional[bool] = None
    # Financials
    recommended_amount: float
    final_amount: Optional[float] = None
    total_expenditure: float
    expenditure_ratio: Optional[float] = None
    cost_variation_pct: Optional[float] = None
    peer_median_cost: Optional[float] = None
    peer_mean_cost: Optional[float] = None
    peer_std_cost: Optional[float] = None
    cost_deviation_from_peer: Optional[float] = None
    # Payments
    payment_count: Optional[int] = None
    average_payment: Optional[float] = None
    maximum_payment: Optional[float] = None
    minimum_payment: Optional[float] = None
    payment_frequency: Optional[float] = None
    successful_payment_count: Optional[int] = None
    pending_payment_count: Optional[int] = None
    latest_payment_status: Optional[str] = None
    # Vendor summary
    primary_vendor: Optional[str] = None
    vendor_risk_score: Optional[float] = None
    vendor_risk_level: Optional[str] = None
    # Other
    days_since_recommendation: Optional[float] = None
    recommendation_to_completion_days: Optional[float] = None
    average_rating: Optional[float] = None
    has_images: Optional[bool] = None
    ida: Optional[bool] = None
    description_similarity_score: Optional[float] = None
    is_completed: Optional[int] = None


class ProjectListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    items: List[ProjectSummary]


# ─── MPs ──────────────────────────────────────────────────────────────────────

class MpSummary(BaseModel):
    """MP list item."""
    mp_name: str
    state: str
    constituency: str
    house: Optional[str] = None
    recommended_works: Optional[int] = None
    completed_works: Optional[int] = None
    completion_rate_pct: Optional[float] = None
    allocated_amount: Optional[float] = None
    total_expenditure: Optional[float] = None
    utilization_pct: Optional[float] = None
    unspent_amount: Optional[float] = None
    pending_payments: Optional[int] = None
    average_rating: Optional[float] = None
    flagged_works: int = 0


class MpDetail(BaseModel):
    """MP detail + summary of their works + per-tier risk counts."""
    mp: MpSummary
    works: List[ProjectSummary]
    total_works: int
    critical_works: int = 0
    high_risk_works: int = 0
    medium_risk_works: int = 0
    low_risk_works: int = 0
    average_risk_score: Optional[float] = None  # 0–100, 2dp
    highest_work_risk: Optional[float] = None  # 0–100, 2dp


class MpListResponse(BaseModel):
    total: int
    items: List[MpSummary]


# ─── Alerts ───────────────────────────────────────────────────────────────────

class AlertItem(BaseModel):
    """Flagged project for the alerts page."""
    project_id: str
    mp_name: str
    state: str
    constituency: str
    risk_score_display: int
    risk_category: str
    top_risk_signals: Optional[str] = None
    recommended_amount: float
    total_expenditure: float


class SignalAggregate(BaseModel):
    signal: str
    count: int


class AlertListResponse(BaseModel):
    total: int
    tier_counts: dict  # {"CRITICAL": 24, "HIGH": 158}
    signal_aggregates: List[SignalAggregate]
    items: List[AlertItem]
    page: int = 1
    page_size: int = 50
    pages: int = 1


# ─── Reports (notifications) ─────────────────────────────────────────────────

class ReportCreate(BaseModel):
    """Payload for POST /api/reports — a higher authority reporting a work."""
    project_id: str
    reported_by_role: str  # "MP" | "District Magistrate" | "State Nodal Officer" | "MoSPI Audit Cell"
    target_role: str       # authority the report is addressed to (same enum)
    comment: Optional[str] = None
    # Optional analysis snapshot (D-031 Step 1): the dossier's key insights
    # ride along with the notification so the reviewer sees the WHY in their
    # inbox. summary_json = structured snapshot (rendered as rich UI);
    # summary_md = plain-text fallback (legacy). Capped — a summary, not the
    # full dossier.
    summary_md: Optional[str] = Field(default=None, max_length=4000)
    summary_json: Optional[str] = Field(default=None, max_length=4000)


class ReportItem(BaseModel):
    """A routed report — appears in the target authority's inbox."""
    id: int
    project_id: str
    reported_by_role: str
    target_role: str
    comment: Optional[str] = None
    summary_md: Optional[str] = None
    summary_json: Optional[str] = None
    status: str  # "NEW" | "ACKNOWLEDGED"
    created_at: str  # ISO 8601
    # Enrichment from risk_results (joined at read time — not stored)
    mp_name: str
    state: str
    risk_score_display: int
    risk_category: str


class ReportListResponse(BaseModel):
    total: int
    items: List[ReportItem]


class ReportEvent(BaseModel):
    """One report event in a work's investigation history (D-031 Step 3)."""
    id: int
    reported_by_role: str
    target_role: str
    comment: Optional[str] = None
    has_snapshot: bool = False
    status: str  # "NEW" | "ACKNOWLEDGED"
    created_at: str
    acknowledged_at: Optional[str] = None


class ProjectHistoryResponse(BaseModel):
    """GET /api/reports/history/{project_id} — the work's report trail."""
    project_id: str
    mp_name: str
    state: str
    risk_category: str
    risk_score_display: int
    total_reports: int
    new_reports: int
    events: List[ReportEvent]


# ─── Citizen Participation Portal (D-032) ───────────────────────────────────

class CitizenLoginRequest(BaseModel):
    """Demo Aadhaar + OTP login — any 12-digit ID + any 6-digit OTP accepted.
    Simulated verification, clearly labeled (D-032): no real UIDAI integration."""
    aadhaar: str = Field(..., min_length=12, max_length=12, description="Demo Aadhaar number (12 digits, demo only)")
    otp: str = Field(..., min_length=6, max_length=6, description="Demo OTP (any 6 digits — simulated)")


class CitizenLoginResponse(BaseModel):
    token: str
    masked_id: str          # e.g. "CIT-•••• 1234"
    is_new: bool            # first login for this demo ID?
    demo_notice: str


class CitizenMe(BaseModel):
    masked_id: str
    created_at: str
    upvotes_cast: int
    reports_filed: int


class CitizenVoteRequest(BaseModel):
    token: str
    project_id: str
    reasons: Optional[List[str]] = Field(
        None, description="Optional concern tags (stalled/quality/cost/ghost/other) — upvote 'why'"
    )


class CitizenVoteResponse(BaseModel):
    project_id: str
    voted: bool             # True = vote now active (Reddit-style toggle)
    upvote_count: int
    demo_notice: str


class CitizenFeedItem(BaseModel):
    """One row of the citizen feed: the work + how much public attention it has."""
    project_id: str
    work_description: Optional[str] = None
    mp_name: str
    state: str
    constituency: str
    category: str
    status: Optional[str] = None
    risk_category: str
    risk_score_display: int
    recommended_amount: float
    upvote_count: int
    report_count: int
    top_concerns: List[dict] = []  # [{"reason": "stalled", "count": 12}, …] — combined votes+reports
    satisfaction_avg: Optional[float] = None  # mean of citizens' 1–5 ratings (None = unrated)
    satisfaction_count: int = 0
    voted: Optional[bool] = None  # present only when a token was supplied


class CitizenFeedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    demo_seed: bool
    items: List[CitizenFeedItem]


class CitizenReportItem(BaseModel):
    """A citizen report on a work. Images/coords are citizen-submitted and
    UNVERIFIED by definition (D-032) — never auto-promoted."""
    id: int
    project_id: str
    masked_id: str
    criteria: List[str]
    satisfaction: Optional[int] = None  # 1–5 (None = problem report only)
    comment: Optional[str] = None
    has_image: bool = False
    image_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_sanity: Optional[str] = None  # PLAUSIBLE | FAR_FROM_CLAIMED_STATE | NO_LOCATION | NO_REFERENCE
    verification_status: str = "UNVERIFIED"
    is_seed: bool = False
    created_at: str
    # Enrichment from the frozen risk data (read-only join)
    work_description: Optional[str] = None
    mp_name: str = ""
    state: str = ""
    risk_category: str = ""
    risk_score_display: int = 0


class CitizenReportListResponse(BaseModel):
    total: int
    demo_seed: bool
    items: List[CitizenReportItem]


class CitizenPsiResponse(BaseModel):
    """Public Satisfaction Indicator for ONE work — a participation/sentiment
    signal (upvotes + citizen reports), explicitly NOT a detection engine."""
    project_id: str
    upvote_count: int
    report_count: int
    distinct_citizens: int
    psi_score: int                       # 0–100
    label: str                           # NO_SIGNAL | LOW | MODERATE | HIGH
    reasons_breakdown: List[dict]        # [{"reason": "stalled", "count": 12, "report_count": 4, "upvote_count": 8}, …]
    satisfaction_avg: Optional[float] = None  # mean of 1–5 ratings (None = no ratings)
    satisfaction_count: int = 0
    methodology: str
    disclaimer: str


class CitizenOverviewResponse(BaseModel):
    """Citizen portal Overview tab — participation stats (labeled demo)."""
    total_citizens: int
    total_upvotes: int
    total_reports: int
    works_engaged: int
    top_upvoted: List[CitizenFeedItem]
    recent_reports: List[CitizenReportItem]
    by_state: List[dict]
    demo_seed: bool
    demo_notice: str


class CitizenFacetState(BaseModel):
    """One state in the citizen facet index — feeds the 'near me' filter
    dropdowns (D-032). Constituency lists come from the real dataset."""
    state: str
    works: int
    constituencies: List[str]
    mps: List[str]


class CitizenFacetsResponse(BaseModel):
    total_states: int
    total_constituencies: int
    states: List[CitizenFacetState]


# ─── Agencies ─────────────────────────────────────────────────────────────────

class AgencySummary(BaseModel):
    agency_id: str
    agency_risk_score: Optional[float] = None
    agency_risk_level: Optional[str] = None
    total_works: Optional[int] = None
    avg_completion_rate: Optional[float] = None


class AgencyListResponse(BaseModel):
    total: int
    items: List[AgencySummary]
