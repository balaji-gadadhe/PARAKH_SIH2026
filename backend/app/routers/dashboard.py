"""
dashboard.py
============
GET /api/dashboard/summary — national KPIs + risk distribution.
"""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException

from ..data_loader import data_store
from ..schemas import DashboardSummary, StateRiskItem, StateRiskResponse

router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary():
    """Return national KPIs, tier distribution, top states and MPs by risk."""
    df = data_store.risk_results
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded yet")

    total_works = len(df)
    total_mps = df["mp_name"].nunique()

    funds_allocated = float(df["recommended_amount"].sum())
    funds_utilized = float(df["total_expenditure"].sum())
    utilization_pct = round((funds_utilized / funds_allocated * 100), 1) if funds_allocated > 0 else 0.0

    completed_works = int(df["is_completed"].sum()) if "is_completed" in df.columns else 0
    completion_pct = round((completed_works / total_works * 100), 1) if total_works > 0 else 0.0

    # avg financial progress — from master_works if available, else 0
    avg_financial_progress = 0.0
    if data_store.master_works is not None and "financial_progress_pct" in data_store.master_works.columns:
        avg_financial_progress = round(float(data_store.master_works["financial_progress_pct"].mean()), 2)

    # Tier distribution
    tier_dist = df["risk_category"].value_counts().to_dict()

    # Top states by HIGH+CRITICAL count
    high_crit = df[df["risk_category"].isin(["HIGH", "CRITICAL"])]
    top_states = (
        high_crit.groupby("state")
        .size()
        .sort_values(ascending=False)
        .head(10)
        .reset_index(name="count")
        .to_dict("records")
    )

    # Top MPs by flagged works count
    flagged = df[df["risk_category"].isin(["HIGH", "CRITICAL"])]
    top_mps = (
        flagged.groupby("mp_name")
        .size()
        .sort_values(ascending=False)
        .head(10)
        .reset_index(name="flagged_count")
        .to_dict("records")
    )

    return DashboardSummary(
        total_works=total_works,
        total_mps=total_mps,
        funds_allocated=round(funds_allocated, 2),
        funds_utilized=round(funds_utilized, 2),
        utilization_pct=utilization_pct,
        completed_works=completed_works,
        completion_pct=completion_pct,
        avg_financial_progress=avg_financial_progress,
        tier_distribution=tier_dist,
        top_states_by_risk=top_states,
        top_mps_by_flagged=top_mps,
    )


@router.get("/states", response_model=StateRiskResponse)
def get_state_risk():
    """Per-state risk aggregation for the India map + state panels (D-031 Step 2a).

    One read-only pass over risk_results — frozen columns only, consistent with
    the D-018 CSV-read architecture. Sort: HIGH+CRITICAL desc, then total works
    desc, so the map legend and panels lead with the most-attention states.
    """
    df = data_store.risk_results
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded yet")

    # Group state × tier in one pass (size() over the crosstab is fast on 87k rows)
    ct = pd.crosstab(df["state"], df["risk_category"])
    for col in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        if col not in ct.columns:
            ct[col] = 0

    funds = df.groupby("state")[["recommended_amount", "total_expenditure"]].sum()
    # Distinct MPs with at least one HIGH/CRITICAL work in the state
    flagged_mps = (
        df[df["risk_category"].isin(["HIGH", "CRITICAL"])]
        .groupby("state")["mp_name"].nunique()
    )

    items: list[StateRiskItem] = []
    for state, row in ct.iterrows():
        s = str(state)
        high = int(row.get("HIGH", 0))
        critical = int(row.get("CRITICAL", 0))
        f = funds.loc[s] if s in funds.index else {"recommended_amount": 0.0, "total_expenditure": 0.0}
        items.append(
            StateRiskItem(
                state=s,
                total_works=int(row.sum()),
                low=int(row.get("LOW", 0)),
                medium=int(row.get("MEDIUM", 0)),
                high=high,
                critical=critical,
                high_critical=high + critical,
                funds_allocated=round(float(f["recommended_amount"]), 2),
                funds_utilized=round(float(f["total_expenditure"]), 2),
                flagged_mps=int(flagged_mps.get(s, 0)),
            )
        )

    items.sort(key=lambda x: (-x.high_critical, -x.total_works, x.state))
    return StateRiskResponse(total_states=len(items), states=items)
