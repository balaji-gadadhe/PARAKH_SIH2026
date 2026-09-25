"""Delay History and Timeliness Analysis for Agency Profiling in MPLAD-Sentinel.

Evaluates:
- Agency delay rate (% of projects delayed)
- Average delay days
- Operational backlog / delay risk component in [0, 100]
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple


def evaluate_delay_history(
    raw_df: pd.DataFrame,
    agency_perf_df: pd.DataFrame,
    agency_col: Optional[str] = None
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calculate delay rate, average delay days, and delay risk component per agency.

    Parameters
    ----------
    raw_df : pd.DataFrame
        Input data before aggregation (may be project-level or vendor-level).
    agency_perf_df : pd.DataFrame
        Processed agency performance DataFrame from historical_performance.
    agency_col : Optional[str]
        Name of the agency identification column.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray, np.ndarray]
        - delay_rates: Array of delay percentages [0.0, 100.0].
        - average_delay_days: Array of average delay days.
        - delay_risk_components: Normalized risk score in [0.0, 100.0].
    """
    n = len(agency_perf_df)
    if n == 0:
        return np.array([]), np.array([]), np.array([])

    delay_rates = np.zeros(n, dtype=float)
    avg_delay_days = np.zeros(n, dtype=float)
    delay_risk = np.zeros(n, dtype=float)

    # Check if raw_df contains project-level delay indicators
    has_project_delays = (
        "is_delayed" in raw_df.columns
        or "delay_days" in raw_df.columns
        or "is_delayed_predicted" in raw_df.columns
    )

    if has_project_delays and agency_col and agency_col in raw_df.columns:
        delay_flag_col = "is_delayed" if "is_delayed" in raw_df.columns else "is_delayed_predicted"
        days_col = "delay_days" if "delay_days" in raw_df.columns else None

        # Group by agency in raw_df
        agency_to_idx = {}
        for idx in range(len(agency_perf_df)):
            name_val = str(agency_perf_df["agency_name"].iloc[idx])
            id_val = str(agency_perf_df["agency_id"].iloc[idx])
            agency_to_idx[name_val] = idx
            agency_to_idx[id_val] = idx

        for agency_key, grp in raw_df.groupby(agency_col):
            key_str = str(agency_key)
            if key_str not in agency_to_idx:
                continue
            idx = agency_to_idx[key_str]
            tot = len(grp)

            # Delayed projects count
            if delay_flag_col in grp.columns:
                delays = pd.to_numeric(grp[delay_flag_col], errors="coerce").fillna(0).values
                delayed_count = float(np.sum(delays > 0))
            else:
                delayed_count = 0.0

            d_rate = (delayed_count / tot) * 100.0 if tot > 0 else 0.0
            delay_rates[idx] = d_rate

            # Average delay days
            if days_col and days_col in grp.columns:
                days = pd.to_numeric(grp[days_col], errors="coerce").fillna(0.0).values
                avg_days = float(np.mean(days[days > 0])) if np.sum(days > 0) > 0 else 0.0
                avg_delay_days[idx] = avg_days
            else:
                avg_delay_days[idx] = d_rate * 3.65  # Approximate days scaling if only rate is provided

            # Delay risk component (0-100)
            # Combines delay rate and delay severity
            score = d_rate * 0.70 + min(100.0, (avg_delay_days[idx] / 180.0) * 30.0)
            delay_risk[idx] = np.clip(score, 0.0, 100.0)

    else:
        # Pre-aggregated vendor records (like vendor_features.csv)
        # Evaluates operational friction and pending payment backlog
        tot_proj = agency_perf_df["total_projects"].values
        pending_cnt = agency_perf_df["pending_payment_count"].values
        comp_rates = agency_perf_df["completion_rate"].values

        for i in range(n):
            p_cnt = float(pending_cnt[i])
            tot = float(tot_proj[i])
            c_rate = float(comp_rates[i])

            # Pending payment rate proxy for operational friction
            p_rate = (p_cnt / tot) if tot > 0 else 0.0

            # If agency has multiple projects and 0% completion, add delay risk
            incomp_factor = (100.0 - c_rate) if tot >= 3 else 20.0

            # Friction delay proxy
            friction_score = min(100.0, p_rate * 80.0 + (p_cnt * 5.0))

            combined_delay_risk = 0.60 * friction_score + 0.40 * incomp_factor
            delay_risk[i] = np.clip(combined_delay_risk, 0.0, 100.0)

            # Conservative delay rate proxy from pending friction
            delay_rates[i] = np.clip(p_rate * 100.0, 0.0, 100.0)
            avg_delay_days[i] = round(p_rate * 90.0, 1)

    return np.round(delay_rates, 2), np.round(avg_delay_days, 1), np.round(delay_risk, 2)
