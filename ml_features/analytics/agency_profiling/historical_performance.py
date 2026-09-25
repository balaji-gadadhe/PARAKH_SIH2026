"""Historical Performance Analysis for Agency Profiling in MPLAD-Sentinel.

Aggregates or extracts agency historical metrics:
- Project volume (total, completed, ongoing)
- Completion rate
- Financial scale, utilization, and cost skewness
- Payment friction (pending payments)
Supports both project-level DataFrames and pre-aggregated vendor records.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, List, Optional


def extract_historical_performance(df: pd.DataFrame) -> pd.DataFrame:
    """Extract or aggregate agency historical performance indicators.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame. Can be either:
        1. Pre-aggregated vendor table (e.g. vendor_features.csv) containing 'vendor' or 'agency_id'.
        2. Project-level table containing 'agency_id' or 'agency_name' or 'vendor'.

    Returns
    -------
    pd.DataFrame
        Standardized agency-level performance DataFrame.
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "agency_id", "agency_name", "total_projects", "completed_projects",
            "ongoing_projects", "completion_rate", "total_expenditure",
            "average_project_cost", "median_project_cost", "average_utilization",
            "pending_payment_count", "pending_payment_rate", "cost_skewness",
            "anomaly_count", "high_risk_project_count"
        ])

    data = df.copy()

    # Determine agency identification column (prefer agency_name/vendor for readable grouping)
    agency_col = None
    for candidate in ["agency_name", "vendor", "vendor_name", "agency_id"]:
        if candidate in data.columns:
            agency_col = candidate
            break

    if agency_col is None:
        raise ValueError("Input data must contain an agency/vendor identification column ('agency_id', 'agency_name', 'vendor').")

    # Case A: Pre-aggregated vendor data (like vendor_features.csv with 'project_count')
    if "project_count" in data.columns and "total_expenditure" in data.columns and data[agency_col].nunique() == len(data):
        return _process_preaggregated_vendor_data(data, agency_col)

    # Case B: Project-level data requiring aggregation by agency
    return _aggregate_project_level_data(data, agency_col)


def _get_numeric_series(df: pd.DataFrame, col: str, default: float, n: int) -> np.ndarray:
    """Safely extract a numeric series from DataFrame with default and NaN/Inf cleaning."""
    if col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce").fillna(default).values
        return np.nan_to_num(s, nan=default, posinf=default, neginf=default)
    return np.full(n, default, dtype=float)


def _process_preaggregated_vendor_data(df: pd.DataFrame, agency_col: str) -> pd.DataFrame:
    """Process DataFrame that is already aggregated at the vendor level."""
    n = len(df)
    agency_names = df[agency_col].astype(str).values
    agency_ids = df["agency_id"].astype(str).values if "agency_id" in df.columns else agency_names

    total_projects = _get_numeric_series(df, "project_count", 1.0, n).astype(int)
    total_projects = np.maximum(1, total_projects)

    completed = _get_numeric_series(df, "completed_project_count", 0.0, n).astype(int)
    completed = np.clip(completed, 0, total_projects)

    ongoing = total_projects - completed

    # Completion rate in [0%, 100%]
    completion_rates = np.where(total_projects > 0, (completed / total_projects) * 100.0, 0.0)

    total_exp = _get_numeric_series(df, "total_expenditure", 0.0, n)
    total_exp = np.maximum(0.0, total_exp)

    avg_cost = _get_numeric_series(df, "average_project_cost", 0.0, n)
    median_cost = _get_numeric_series(df, "median_project_cost", 0.0, n)

    # Cost skewness (average_cost / median_cost)
    safe_median = np.where(median_cost > 0, median_cost, np.where(avg_cost > 0, avg_cost, 1.0))
    cost_skewness = np.where(avg_cost > 0, avg_cost / safe_median, 1.0)
    cost_skewness = np.clip(cost_skewness, 0.1, 50.0)

    pending_cnt = _get_numeric_series(df, "pending_payment_count", 0.0, n).astype(int)
    pending_cnt = np.maximum(0, pending_cnt)
    pending_rates = np.where(total_projects > 0, pending_cnt / total_projects, 0.0)

    # Utilization
    utilization = _get_numeric_series(df, "average_utilization", 100.0, n)

    anomaly_cnt = _get_numeric_series(df, "anomaly_count", 0.0, n).astype(int)
    high_risk_cnt = _get_numeric_series(df, "high_risk_project_count", 0.0, n).astype(int)

    return pd.DataFrame({
        "agency_id": agency_ids,
        "agency_name": agency_names,
        "total_projects": total_projects,
        "completed_projects": completed,
        "ongoing_projects": ongoing,
        "completion_rate": np.round(completion_rates, 2),
        "total_expenditure": np.round(total_exp, 2),
        "average_project_cost": np.round(avg_cost, 2),
        "median_project_cost": np.round(median_cost, 2),
        "average_utilization": np.round(utilization, 2),
        "pending_payment_count": pending_cnt,
        "pending_payment_rate": np.round(pending_rates, 4),
        "cost_skewness": np.round(cost_skewness, 2),
        "anomaly_count": anomaly_cnt,
        "high_risk_project_count": high_risk_cnt
    })


def _aggregate_project_level_data(df: pd.DataFrame, agency_col: str) -> pd.DataFrame:
    """Aggregate individual project records into an agency-level profile."""
    records = []

    for agency, grp in df.groupby(agency_col):
        tot_proj = len(grp)

        # Completed
        if "is_completed" in grp.columns:
            comp_proj = int(pd.to_numeric(grp["is_completed"], errors="coerce").fillna(0).sum())
        elif "completed" in grp.columns:
            comp_proj = int(pd.to_numeric(grp["completed"], errors="coerce").fillna(0).sum())
        else:
            comp_proj = 0
        comp_proj = min(comp_proj, tot_proj)
        ongoing_proj = tot_proj - comp_proj
        comp_rate = (comp_proj / tot_proj) * 100.0 if tot_proj > 0 else 0.0

        # Expenditure
        exp_col = "total_expenditure" if "total_expenditure" in grp.columns else ("expenditure" if "expenditure" in grp.columns else None)
        if exp_col:
            exps = pd.to_numeric(grp[exp_col], errors="coerce").fillna(0.0).values
            tot_exp = float(np.sum(exps))
            avg_cost = float(np.mean(exps)) if tot_proj > 0 else 0.0
            med_cost = float(np.median(exps)) if tot_proj > 0 else 0.0
        else:
            tot_exp, avg_cost, med_cost = 0.0, 0.0, 0.0

        # Utilization
        rec_col = "recommended_amount" if "recommended_amount" in grp.columns else ("budget" if "budget" in grp.columns else None)
        if exp_col and rec_col:
            recs = pd.to_numeric(grp[rec_col], errors="coerce").fillna(0.0).values
            safe_recs = np.where(recs > 0, recs, 1.0)
            util_ratios = np.where(exps > 0, (exps / safe_recs) * 100.0, 100.0)
            avg_util = float(np.mean(util_ratios))
        elif "utilization" in grp.columns:
            avg_util = float(pd.to_numeric(grp["utilization"], errors="coerce").fillna(100.0).mean())
        else:
            avg_util = 100.0

        # Cost skewness
        safe_med = med_cost if med_cost > 0 else (avg_cost if avg_cost > 0 else 1.0)
        cost_skew = avg_cost / safe_med if avg_cost > 0 else 1.0

        # Pending payments
        if "pending_payment_count" in grp.columns:
            pend_cnt = int(pd.to_numeric(grp["pending_payment_count"], errors="coerce").fillna(0).sum())
        else:
            pend_cnt = 0
        pend_rate = pend_cnt / tot_proj if tot_proj > 0 else 0.0

        # Anomalies
        anom_cols = [c for c in ["is_anomaly", "is_cost_anomaly", "is_payment_anomaly", "anomaly"] if c in grp.columns]
        if anom_cols:
            anom_sum = int(pd.to_numeric(grp[anom_cols[0]], errors="coerce").fillna(0).sum())
        else:
            anom_sum = 0

        # High risk projects
        risk_cols = [c for c in ["is_delayed", "is_high_risk", "high_risk"] if c in grp.columns]
        if risk_cols:
            high_risk_sum = int(pd.to_numeric(grp[risk_cols[0]], errors="coerce").fillna(0).sum())
        else:
            high_risk_sum = anom_sum

        agency_id = str(grp["agency_id"].iloc[0]) if "agency_id" in grp.columns else str(agency)
        agency_name = str(grp["agency_name"].iloc[0]) if "agency_name" in grp.columns else (
            str(grp["vendor"].iloc[0]) if "vendor" in grp.columns else str(agency)
        )

        records.append({
            "agency_id": agency_id,
            "agency_name": agency_name,
            "total_projects": tot_proj,
            "completed_projects": comp_proj,
            "ongoing_projects": ongoing_proj,
            "completion_rate": round(comp_rate, 2),
            "total_expenditure": round(tot_exp, 2),
            "average_project_cost": round(avg_cost, 2),
            "median_project_cost": round(med_cost, 2),
            "average_utilization": round(avg_util, 2),
            "pending_payment_count": pend_cnt,
            "pending_payment_rate": round(pend_rate, 4),
            "cost_skewness": round(cost_skew, 2),
            "anomaly_count": anom_sum,
            "high_risk_project_count": high_risk_sum
        })

    return pd.DataFrame(records)
