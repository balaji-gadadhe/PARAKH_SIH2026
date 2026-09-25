"""
alerts.py
=========
GET /api/alerts — ranked flagged works + signal-type aggregation.

Defaults to HIGH + CRITICAL per the alerts-page contract (docs/frontend-skeleton.md §4).
Aggregates (tier counts, signal-type counts) are computed over the *full*
filtered set; `items` are paginated.
"""

from __future__ import annotations

import math
from typing import Optional
from collections import Counter

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..data_loader import data_store
from ..schemas import AlertItem, AlertListResponse, SignalAggregate

router = APIRouter()


def _to_score_display(score: float) -> int:
    return round(score * 100)


@router.get("", response_model=AlertListResponse)
def list_alerts(
    tier: Optional[str] = Query(None, description="Filter tier: CRITICAL, HIGH, etc."),
    type: Optional[str] = Query(None, description="Filter by signal type substring"),
    state: Optional[str] = Query(None, description="State filter"),
    mp: Optional[str] = Query(None, description="MP name filter"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Min score (0-100)"),
    q: Optional[str] = Query(None, description="Search by project_id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    df = data_store.risk_results
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")

    # Default: HIGH + CRITICAL
    if tier:
        filtered = df[df["risk_category"] == tier.upper()]
    else:
        filtered = df[df["risk_category"].isin(["HIGH", "CRITICAL"])].copy()

    if state:
        filtered = filtered[filtered["state"].str.contains(state, case=False, na=False, regex=False)]

    if mp:
        filtered = filtered[filtered["mp_name"].str.contains(mp, case=False, na=False, regex=False)]

    if min_score is not None:
        min_norm = min_score / 100.0
        filtered = filtered[filtered["overall_risk_score"] >= min_norm]

    if q:
        filtered = filtered[filtered["project_id"].astype(str).str.contains(q, case=False, na=False, regex=False)]

    if type:
        filtered = filtered[
            filtered["top_risk_signals"].astype(str).str.contains(type, case=False, na=False, regex=False)
        ]

    # Sort by score descending
    filtered = filtered.sort_values("overall_risk_score", ascending=False)

    # Tier counts over the full filtered set
    tier_counts = filtered["risk_category"].value_counts().to_dict()

    # Signal-type aggregation over the full filtered set
    signal_counter = Counter()
    for sig_str in filtered["top_risk_signals"].dropna():
        for part in str(sig_str).split(";"):
            part = part.strip()
            if part:
                # Extract the signal name (before the parenthesis)
                name = part.split("(")[0].strip()
                if name:
                    signal_counter[name] += 1

    signal_aggregates = [
        SignalAggregate(signal=sig, count=cnt)
        for sig, cnt in signal_counter.most_common(20)
    ]

    # Paginate items
    total = len(filtered)
    pages = math.ceil(total / page_size) if total > 0 else 1
    start = (page - 1) * page_size
    end = start + page_size
    page_df = filtered.iloc[start:end]

    items = []
    for _, r in page_df.iterrows():
        items.append(AlertItem(
            project_id=str(r["project_id"]),
            mp_name=str(r["mp_name"]),
            state=str(r["state"]),
            constituency=str(r.get("constituency", "")),
            risk_score_display=_to_score_display(float(r["overall_risk_score"])),
            risk_category=str(r["risk_category"]),
            top_risk_signals=str(r.get("top_risk_signals", "")) if pd.notna(r.get("top_risk_signals")) else None,
            recommended_amount=float(r.get("recommended_amount", 0) or 0),
            total_expenditure=float(r.get("total_expenditure", 0) or 0),
        ))

    return AlertListResponse(
        total=total,
        tier_counts=tier_counts,
        signal_aggregates=signal_aggregates,
        items=items,
        page=page,
        page_size=page_size,
        pages=pages,
    )
