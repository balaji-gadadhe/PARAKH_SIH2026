"""
trend_analysis.py
=================
Temporal velocity, expenditure acceleration, and project decay analytics for early warning.
Detects runaway burn rates, stalled project lag, and anomalous fiscal velocity.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

import numpy as np
import pandas as pd

logger = logging.getLogger("EarlyWarning.TrendAnalysis")


class TrendAnalyzer:
    """Computes project spend velocity, peer acceleration, and stalled decay metrics."""

    def analyze_trends(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute temporal and velocity features for all projects.

        Columns produced:
        - project_id
        - days_since_recommendation
        - spend_velocity_daily: expenditure per elapsed day (₹/day)
        - peer_median_velocity: peer group median spend velocity (₹/day)
        - velocity_ratio_vs_peer: ratio of project velocity to peer velocity
        - is_runaway_spend: boolean (velocity ratio > 2.5x peer)
        - is_stalled_decay: boolean (approved > 365 days ago, < 10% expenditure)
        - burn_rate_status: NORMAL, ACCELERATED, RUNAWAY, STALLED, DORMANT
        """
        res = pd.DataFrame(index=df.index)
        res["project_id"] = df.get("project_id", [f"P_{i}" for i in range(len(df))])

        days = pd.to_numeric(df.get("days_since_recommendation", 0), errors="coerce").fillna(0).clip(lower=1)
        res["days_since_recommendation"] = days

        exp = pd.to_numeric(df.get("total_expenditure", 0.0), errors="coerce").fillna(0.0)
        rec = pd.to_numeric(df.get("recommended_amount", 0.0), errors="coerce").fillna(0.0)
        completed = pd.to_numeric(df.get("is_completed", 0), errors="coerce").fillna(0) == 1

        # 1. Daily spend velocity
        res["spend_velocity_daily"] = (exp / days).round(2)

        # 2. Peer group median velocity by category & state
        category = df.get("category", "Other").fillna("Other")
        state = df.get("state", "Other").fillna("Other")
        temp = pd.DataFrame({
            "category": category,
            "state": state,
            "velocity": res["spend_velocity_daily"]
        })
        peer_vel = temp.groupby(["category", "state"])["velocity"].transform("median").fillna(100.0)
        res["peer_median_velocity"] = peer_vel.round(2)

        # 3. Velocity ratio
        res["velocity_ratio_vs_peer"] = np.where(
            res["peer_median_velocity"] > 0,
            (res["spend_velocity_daily"] / res["peer_median_velocity"]).round(2),
            1.0
        )

        # 4. Runaway spend: spending > 2.5x peer velocity while incomplete
        res["is_runaway_spend"] = (res["velocity_ratio_vs_peer"] >= 2.5) & (~completed) & (exp > 50000)

        # 5. Stalled decay: approved > 365 days ago, < 10% spent or zero progress
        utilization = np.where(rec > 0, exp / rec, 0.0)
        res["is_stalled_decay"] = (days >= 365) & (utilization < 0.10) & (~completed)

        # 6. Burn rate status classification
        conditions = [
            res["is_runaway_spend"],
            res["is_stalled_decay"],
            res["velocity_ratio_vs_peer"] >= 1.5,
            days < 90
        ]
        choices = [
            "RUNAWAY_BURN",
            "STALLED_DECAY",
            "ACCELERATED",
            "NEW_PROJECT"
        ]
        res["burn_rate_status"] = np.select(conditions, choices, default="NORMAL")

        logger.info(f"Trend analysis complete for {len(res)} projects.")
        return res


def run_trend_analysis_pipeline(
    input_csv: str = "ml_input/project_features.csv",
    output_csv: str = "ml_outputs/project_trend_analysis.csv"
) -> pd.DataFrame:
    """Execute trend analysis on project features dataset."""
    base = Path(__file__).resolve().parent.parent.parent
    in_path = base / input_csv
    out_path = base / output_csv

    logger.info(f"Loading project data for trend analysis from: {in_path}")
    df = pd.read_csv(in_path, low_memory=False)

    analyzer = TrendAnalyzer()
    trends_df = analyzer.analyze_trends(df)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    trends_df.to_csv(out_path, index=False)
    logger.info(f"Trend analysis written to: {out_path}")
    return trends_df


if __name__ == "__main__":
    run_trend_analysis_pipeline()
