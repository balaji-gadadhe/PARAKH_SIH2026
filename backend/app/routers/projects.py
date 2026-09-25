"""
projects.py
============
GET /api/projects       — paginated project list with filters
GET /api/projects/{id}  — full project detail (investigation view)

Detail fields follow docs/frontend-skeleton.md §2 and docs/frontend_card_reference.md §2:
identity, risk summary, investigation fields, financials, payments, vendor
summary, and other project fields. Missing values are None (frontend renders
"Not available" per card reference §6).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..data_loader import data_store
from ..schemas import (
    ProjectSummary,
    ProjectDetail,
    ProjectListResponse,
    EngineBreakdown,
)

# Reuse the authoritative investigation prioritizer (card reference §2):
# "These are calculated by analytics.investigation.prioritization.InvestigationPrioritizer."
_ML_FEATURES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "ml_features"
if str(_ML_FEATURES_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_FEATURES_ROOT))

from analytics.investigation.prioritization import InvestigationPrioritizer  # noqa: E402

router = APIRouter()


def _to_score_display(score: float) -> int:
    """Convert 0.0–1.0 risk score to 0–100 display integer."""
    return round(score * 100)


def _get(row: pd.Series, col: str):
    """Safe Series access — None when the column is missing or NaN."""
    if col not in row.index:
        return None
    val = row.get(col)
    return None if pd.isna(val) else val


def _load_master_works_row(project_id: str) -> Optional[pd.Series]:
    """Look up a single project in master_works (None if unavailable)."""
    mw = data_store.master_works
    if mw is None or "project_id" not in mw.columns:
        return None
    match = mw[mw["project_id"] == project_id]
    if match.empty:
        return None
    return match.iloc[0]


def _load_feature_row(project_id: str) -> Optional[pd.Series]:
    """Look up a single project in project_features (None if unavailable)."""
    pf = data_store.project_features
    if pf is None or "project_id" not in pf.columns:
        return None
    match = pf[pf["project_id"] == project_id]
    if match.empty:
        return None
    return match.iloc[0]


def _parse_float(val) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_int(val) -> Optional[int]:
    f = _parse_float(val)
    return None if f is None else int(round(f))


def _to_bool(val) -> Optional[bool]:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes")


def _row_to_summary(row: pd.Series) -> ProjectSummary:
    return ProjectSummary(
        project_id=str(row["project_id"]),
        mp_name=str(row["mp_name"]),
        state=str(row["state"]),
        constituency=str(row["constituency"]),
        category=str(row.get("category", "")) if pd.notna(row.get("category")) else "",
        work_description=(
            str(row.get("work_description"))
            if "work_description" in row.index and pd.notna(row.get("work_description"))
            else None
        ),
        status=(
            str(row.get("status"))
            if "status" in row.index and pd.notna(row.get("status"))
            else None
        ),
        recommended_amount=float(row.get("recommended_amount", 0) or 0),
        total_expenditure=float(row.get("total_expenditure", 0) or 0),
        expenditure_ratio=_parse_float(row.get("expenditure_ratio")),
        is_completed=int(row["is_completed"]) if pd.notna(row.get("is_completed")) else None,
        overall_risk_score=float(row["overall_risk_score"]),
        risk_score_display=_to_score_display(float(row["overall_risk_score"])),
        risk_category=str(row["risk_category"]),
        top_risk_signals=str(row.get("top_risk_signals", "")) if pd.notna(row.get("top_risk_signals")) else None,
    )


def _build_engines(row: pd.Series) -> list[EngineBreakdown]:
    engines = []
    for prefix, name in [
        ("cost_", "Cost Anomaly"),
        ("delay_", "Delay Prediction"),
        ("payment_", "Payment Anomaly"),
        ("rule_", "Compliance & Ghost Rules"),
        ("similarity_", "Duplicate Work Similarity"),
        ("iforest_", "Multivariate Isolation Forest"),
    ]:
        engines.append(EngineBreakdown(
            engine=name,
            score=_parse_float(row.get(f"{prefix}risk_score")),
            flag=bool(row[f"{prefix}risk_flag"]) if pd.notna(row.get(f"{prefix}risk_flag")) else None,
            available=bool(row[f"{prefix}available"]) if pd.notna(row.get(f"{prefix}available")) else None,
        ))
    return engines


def _build_detail(r: pd.Series) -> ProjectDetail:
    """Build the full investigation-view payload for one project row."""
    project_id = str(r["project_id"])
    mw = _load_master_works_row(project_id)
    if mw is None:
        mw = pd.Series(dtype=object)
    feat = _load_feature_row(project_id)
    if feat is None:
        feat = pd.Series(dtype=object)

    # Investigation fields — computed by the shared prioritizer (deterministic,
    # needs only overall_risk_score + total_expenditure; card reference §2).
    prio = InvestigationPrioritizer.prioritize_cases(
        pd.DataFrame([{
            "project_id": project_id,
            "overall_risk_score": float(r["overall_risk_score"]),
            "total_expenditure": float(r.get("total_expenditure", 0) or 0),
        }])
    ).iloc[0]

    return ProjectDetail(
        # Identity
        project_id=project_id,
        mp_name=str(r["mp_name"]),
        state=str(r["state"]),
        constituency=str(r["constituency"]),
        category=str(r.get("category", "")) if pd.notna(r.get("category")) else "",
        work_description=str(mw["work_description"]) if _get(mw, "work_description") is not None else None,
        status=str(mw["status"]) if _get(mw, "status") is not None else None,
        # Risk summary
        overall_risk_score=float(r["overall_risk_score"]),
        risk_score_display=_to_score_display(float(r["overall_risk_score"])),
        risk_category=str(r["risk_category"]),
        audit_explanation=str(r["audit_explanation"]) if _get(r, "audit_explanation") is not None else None,
        top_risk_signals=str(r["top_risk_signals"]) if _get(r, "top_risk_signals") is not None else None,
        risk_factors=str(r["risk_factors"]) if _get(r, "risk_factors") is not None else None,
        evidence_payload=str(r["evidence_payload"]) if _get(r, "evidence_payload") is not None else None,
        engines=_build_engines(r),
        # Investigation fields
        investigation_priority=_parse_float(prio.get("investigation_priority_score")),
        investigation_urgency=str(prio["investigation_urgency"]) if pd.notna(prio.get("investigation_urgency")) else None,
        audit_dispatch_recommended=_to_bool(prio.get("audit_dispatch_recommended")),
        # Financials
        recommended_amount=float(r.get("recommended_amount", 0) or 0),
        final_amount=_parse_float(_get(mw, "final_amount")),
        total_expenditure=float(r.get("total_expenditure", 0) or 0),
        expenditure_ratio=_parse_float(_get(r, "expenditure_ratio")),
        cost_variation_pct=_parse_float(_get(feat, "cost_variation_pct")),
        peer_median_cost=_parse_float(_get(feat, "peer_median_cost")),
        peer_mean_cost=_parse_float(_get(feat, "peer_mean_cost")),
        peer_std_cost=_parse_float(_get(feat, "peer_std_cost")),
        cost_deviation_from_peer=_parse_float(_get(feat, "cost_deviation_from_peer")),
        # Payments
        payment_count=_parse_int(_get(mw, "payment_count")),
        average_payment=_parse_float(_get(feat, "average_payment")),
        maximum_payment=_parse_float(_get(feat, "maximum_payment")),
        minimum_payment=_parse_float(_get(feat, "minimum_payment")),
        payment_frequency=_parse_float(_get(feat, "payment_frequency")),
        successful_payment_count=_parse_int(_get(mw, "successful_payment_count")),
        pending_payment_count=_parse_int(_get(mw, "pending_payment_count")),
        latest_payment_status=str(mw["latest_payment_status"]) if _get(mw, "latest_payment_status") is not None else None,
        # Vendor summary
        primary_vendor=str(mw["primary_vendor"]) if _get(mw, "primary_vendor") is not None else None,
        vendor_risk_score=_parse_float(_get(r, "vendor_risk_score")),
        vendor_risk_level=str(r["vendor_risk_level"]) if _get(r, "vendor_risk_level") is not None else None,
        # Other
        days_since_recommendation=_parse_float(_get(feat, "days_since_recommendation")),
        recommendation_to_completion_days=_parse_float(_get(feat, "recommendation_to_completion_days")),
        average_rating=_parse_float(_get(mw, "average_rating")),
        has_images=_to_bool(_get(mw, "has_images")),
        ida=_to_bool(_get(mw, "ida")),
        description_similarity_score=_parse_float(_get(feat, "description_similarity_score")),
        is_completed=int(r["is_completed"]) if pd.notna(r.get("is_completed")) else None,
    )


@router.get("", response_model=ProjectListResponse)
def list_projects(
    q: Optional[str] = Query(None, description="Search in project_id or work description"),
    tier: Optional[str] = Query(None, description="Risk tier: LOW, MEDIUM, HIGH, CRITICAL"),
    state: Optional[str] = Query(None, description="State name filter"),
    mp: Optional[str] = Query(None, description="MP name filter"),
    house: Optional[str] = Query(None, description="House: Lok Sabha / Rajya Sabha"),
    category: Optional[str] = Query(None, description="Work category filter"),
    status: Optional[str] = Query(None, description="Status: completed / ongoing"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Min risk score (0-100)"),
    sort: Optional[str] = Query("risk_desc", description="Sort: risk_desc, risk_asc, amount_desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    df = data_store.risk_results
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")

    filtered = df.copy()

    # Attach master_works fields needed for list filters/display (cheap merge)
    if data_store.master_works is not None:
        mw_cols = [c for c in ("project_id", "work_description", "status", "house") if c in data_store.master_works.columns]
        mw = data_store.master_works[mw_cols].copy()
        mw["project_id"] = mw["project_id"].astype(str)
        filtered["project_id"] = filtered["project_id"].astype(str)
        filtered = filtered.merge(mw, on="project_id", how="left")

    # Filter by tier
    if tier:
        filtered = filtered[filtered["risk_category"] == tier.upper()]

    # Filter by state — regex=False: user input may contain regex metacharacters
    if state:
        filtered = filtered[filtered["state"].str.contains(state, case=False, na=False, regex=False)]

    # Filter by MP
    if mp:
        filtered = filtered[filtered["mp_name"].str.contains(mp, case=False, na=False, regex=False)]

    # Filter by house (from master merge; risk CSV has no house column)
    if house and "house" in filtered.columns:
        filtered = filtered[filtered["house"].str.contains(house, case=False, na=False, regex=False)]

    # Filter by category
    if category:
        filtered = filtered[filtered["category"].astype(str).str.contains(category, case=False, na=False, regex=False)]

    # Filter by status (completed/ongoing) — works with or without master merge
    if status:
        status_l = status.lower().strip()
        if "status" in filtered.columns:
            mask = filtered["status"].astype(str).str.contains(status_l, case=False, na=False)
            if status_l in ("completed", "ongoing", "in progress", "in_progress"):
                mask = mask | (filtered["is_completed"] == (1 if status_l == "completed" else 0))
            filtered = filtered[mask]
        elif "is_completed" in filtered.columns:
            filtered = filtered[filtered["is_completed"] == (1 if status_l == "completed" else 0)]

    # Filter by min score (0-100 input → 0.0-1.0 in CSV)
    if min_score is not None:
        min_score_normalized = min_score / 100.0
        filtered = filtered[filtered["overall_risk_score"] >= min_score_normalized]

    # Search: project_id substring or work description substring
    if q:
        id_match = filtered["project_id"].str.contains(q, case=False, na=False, regex=False)
        if "work_description" in filtered.columns:
            mask = id_match | filtered["work_description"].astype(str).str.contains(q, case=False, na=False, regex=False)
        else:
            mask = id_match
        filtered = filtered[mask]

    # Sort
    if sort == "risk_asc":
        filtered = filtered.sort_values("overall_risk_score", ascending=True)
    elif sort == "amount_desc":
        filtered = filtered.sort_values("recommended_amount", ascending=False)
    else:
        filtered = filtered.sort_values("overall_risk_score", ascending=False)

    total = len(filtered)
    pages = math.ceil(total / page_size) if total > 0 else 1
    start = (page - 1) * page_size
    end = start + page_size
    page_df = filtered.iloc[start:end]

    items = [_row_to_summary(row) for _, row in page_df.iterrows()]

    return ProjectListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items,
    )


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project_detail(project_id: str):
    df = data_store.risk_results
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")

    row = df[df["project_id"].astype(str) == project_id]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    return _build_detail(row.iloc[0])
