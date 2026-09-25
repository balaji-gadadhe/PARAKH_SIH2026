"""
agencies.py
============
GET /api/agencies          — vendor/agency profile list
GET /api/agencies/{id}     — single agency detail
"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..data_loader import data_store
from ..schemas import AgencySummary, AgencyListResponse

router = APIRouter()


def _row_to_summary(row: pd.Series) -> AgencySummary:
    return AgencySummary(
        agency_id=str(row.get("agency_id", "")),
        agency_risk_score=float(row["agency_risk_score"]) if pd.notna(row.get("agency_risk_score")) else None,
        agency_risk_level=str(row.get("agency_risk_level")) if pd.notna(row.get("agency_risk_level")) else None,
        total_works=int(row["total_projects"]) if pd.notna(row.get("total_projects")) else None,
        avg_completion_rate=float(row["completion_rate"]) if pd.notna(row.get("completion_rate")) else None,
    )


@router.get("", response_model=AgencyListResponse)
def list_agencies(
    q: Optional[str] = Query(None, description="Search by agency name"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level: LOW, MEDIUM, HIGH"),
    sort: Optional[str] = Query("risk_desc", description="Sort: risk_desc, risk_asc, projects_desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    df = data_store.agency_profiles
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Agency data not loaded")

    filtered = df.copy()

    if q:
        filtered = filtered[filtered["agency_name"].str.contains(q, case=False, na=False, regex=False)]

    if risk_level:
        filtered = filtered[filtered["agency_risk_level"] == risk_level.upper()]

    if sort == "risk_asc":
        filtered = filtered.sort_values("agency_risk_score", ascending=True, na_position="last")
    elif sort == "projects_desc":
        filtered = filtered.sort_values("total_projects", ascending=False, na_position="last")
    else:
        filtered = filtered.sort_values("agency_risk_score", ascending=False, na_position="last")

    total = len(filtered)
    pages = math.ceil(total / page_size) if total > 0 else 1
    start = (page - 1) * page_size
    end = start + page_size
    page_df = filtered.iloc[start:end]

    items = [_row_to_summary(row) for _, row in page_df.iterrows()]

    return AgencyListResponse(total=total, items=items)


@router.get("/{agency_id}")
def get_agency_detail(agency_id: str):
    df = data_store.agency_profiles
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Agency data not loaded")

    row = df[df["agency_id"] == agency_id]
    if row.empty:
        # Try partial match
        row = df[df["agency_id"].str.contains(agency_id, case=False, na=False, regex=False)]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"Agency not found: {agency_id}")

    r = row.iloc[0]
    return {
        "agency_id": str(r.get("agency_id", "")),
        "agency_name": str(r.get("agency_name", "")),
        "total_projects": int(r["total_projects"]) if pd.notna(r.get("total_projects")) else None,
        "completed_projects": int(r["completed_projects"]) if pd.notna(r.get("completed_projects")) else None,
        "ongoing_projects": int(r["ongoing_projects"]) if pd.notna(r.get("ongoing_projects")) else None,
        "completion_rate": float(r["completion_rate"]) if pd.notna(r.get("completion_rate")) else None,
        "delay_rate": float(r["delay_rate"]) if pd.notna(r.get("delay_rate")) else None,
        "average_delay_days": float(r["average_delay_days"]) if pd.notna(r.get("average_delay_days")) else None,
        "average_utilization": float(r["average_utilization"]) if pd.notna(r.get("average_utilization")) else None,
        "anomaly_count": int(r["anomaly_count"]) if pd.notna(r.get("anomaly_count")) else None,
        "high_risk_project_count": int(r["high_risk_project_count"]) if pd.notna(r.get("high_risk_project_count")) else None,
        "agency_risk_score": float(r["agency_risk_score"]) if pd.notna(r.get("agency_risk_score")) else None,
        "agency_risk_level": str(r.get("agency_risk_level")) if pd.notna(r.get("agency_risk_level")) else None,
        "risk_reasons": str(r.get("risk_reasons")) if pd.notna(r.get("risk_reasons")) else None,
    }
