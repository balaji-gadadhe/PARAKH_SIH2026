"""Agency Risk Score Calculation and Profiling Pipeline for MPLAD-Sentinel.

Calculates an explainable Agency Risk Score between 0 and 100 representing
historical operational/project risk.
Components:
- Delay performance
- Completion performance
- Financial utilization and cost skewness
- Payment friction (pending payments)
- Anomaly frequency

Features empirical credibility shrinkage to avoid unfairly penalizing small-sample agencies.
Outputs risk bands: LOW, MEDIUM, HIGH, CRITICAL with human-readable reasons.
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

# Ensure workspace root is in sys.path when executed directly
WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from analytics.agency_profiling.historical_performance import extract_historical_performance
from analytics.agency_profiling.delay_history import evaluate_delay_history

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class AgencyProfiler:
    """Computes comprehensive agency intelligence profiles and evidence-based risk scores.

    Parameters
    ----------
    credibility_k : float, default=3.0
        Smoothing constant for small-sample shrinkage: W = N / (N + K).
    neutral_baseline : float, default=15.0
        Baseline risk score toward which low-volume agencies are shrunk.
    """

    def __init__(
        self,
        credibility_k: float = 3.0,
        neutral_baseline: float = 15.0
    ) -> None:
        self.credibility_k = credibility_k
        self.neutral_baseline = neutral_baseline

    def profile_agencies(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate agency profiles and risk scores from input DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Input DataFrame (project-level or vendor-level).

        Returns
        -------
        pd.DataFrame
            Profiles with agency_risk_score, agency_risk_level, and risk_reasons.
        """
        if df.empty:
            return pd.DataFrame(columns=[
                "agency_id", "agency_name", "total_projects", "completed_projects",
                "ongoing_projects", "completion_rate", "delay_rate", "average_delay_days",
                "average_utilization", "anomaly_count", "high_risk_project_count",
                "agency_risk_score", "agency_risk_level", "risk_level", "risk_reasons"
            ])

        # Step 1: Extract historical performance
        perf_df = extract_historical_performance(df)

        # Detect agency column in raw df
        agency_col = None
        for c in ["agency_name", "vendor", "vendor_name", "agency_id"]:
            if c in df.columns:
                agency_col = c
                break

        # Step 2: Evaluate delay history
        delay_rates, avg_delay_days, delay_risks = evaluate_delay_history(df, perf_df, agency_col)
        perf_df["delay_rate"] = delay_rates
        perf_df["average_delay_days"] = avg_delay_days

        # Step 3: Compute raw and credibility-adjusted risk scores
        n = len(perf_df)
        tot_proj = perf_df["total_projects"].values
        comp_rates = perf_df["completion_rate"].values
        pending_rates = perf_df["pending_payment_rate"].values
        pending_cnts = perf_df["pending_payment_count"].values
        skewness = perf_df["cost_skewness"].values
        anom_cnts = perf_df["anomaly_count"].values
        high_risk_cnts = perf_df["high_risk_project_count"].values
        avg_utils = perf_df["average_utilization"].values

        risk_scores = np.zeros(n, dtype=float)
        risk_levels: List[str] = []
        reasons_list: List[str] = []

        for i in range(n):
            N = float(tot_proj[i])
            d_risk = float(delay_risks[i])
            c_rate = float(comp_rates[i])
            p_rate = float(pending_rates[i])
            p_cnt = float(pending_cnts[i])
            skew = float(skewness[i])
            anom = float(anom_cnts[i])
            high_r = float(high_risk_cnts[i])
            util = float(avg_utils[i])

            # Component 1: Delay Risk Component (0 - 100)
            c_delay = d_risk

            # Component 2: Incompletion Risk Component (0 - 100)
            # Only penalize completion rate if agency has handled sufficient projects (N >= 2)
            if N >= 2:
                c_incomp = max(0.0, 100.0 - c_rate)
            else:
                c_incomp = 20.0

            # Component 3: Financial / Utilization / Skewness Risk (0 - 100)
            f_skew_score = min(100.0, max(0.0, (skew - 1.0) * 35.0))
            f_util_score = min(100.0, max(0.0, (util - 100.0) * 1.5)) if util > 105.0 else 0.0
            c_fin = max(f_skew_score, f_util_score)

            # Component 4: Payment Friction / Disputes (0 - 100)
            c_friction = min(100.0, p_rate * 75.0 + (p_cnt * 6.0))

            # Component 5: Project Anomaly Frequency (0 - 100)
            anom_rate = (anom / N) if N > 0 else 0.0
            high_risk_rate = (high_r / N) if N > 0 else 0.0
            c_anom = min(100.0, (anom_rate * 60.0) + (high_risk_rate * 40.0))

            # Raw multi-criteria fusion
            raw_risk = (
                0.28 * c_delay +
                0.24 * c_incomp +
                0.20 * c_fin +
                0.16 * c_friction +
                0.12 * c_anom
            )

            # Empirical Credibility Shrinkage: W = N / (N + K)
            weight = N / (N + self.credibility_k)
            adjusted_score = weight * raw_risk + (1.0 - weight) * self.neutral_baseline
            adjusted_score = float(np.clip(adjusted_score, 0.0, 100.0))
            risk_scores[i] = round(adjusted_score, 2)

            # Assign Risk Bands
            if adjusted_score < 30.0:
                level = "LOW"
            elif adjusted_score < 55.0:
                level = "MEDIUM"
            elif adjusted_score < 75.0:
                level = "HIGH"
            else:
                level = "CRITICAL"
            risk_levels.append(level)

            # Human-readable evidence-based reasons
            reasons = []
            if N < 3:
                reasons.append("Low historical volume (score credibility shrunk toward baseline)")

            if perf_df["delay_rate"].iloc[i] >= 40.0:
                reasons.append(f"High historical delay rate ({perf_df['delay_rate'].iloc[i]:.1f}%)")
            elif perf_df["average_delay_days"].iloc[i] >= 60.0:
                reasons.append(f"Significant average project delay ({perf_df['average_delay_days'].iloc[i]:.0f} days)")

            if c_rate < 20.0 and N >= 3:
                reasons.append(f"Low project completion rate ({c_rate:.1f}%)")

            if p_cnt >= 2:
                reasons.append(f"High pending payment friction ({p_cnt:.0f} pending payments)")

            if skew >= 1.5 and N >= 2:
                reasons.append(f"Significant cost skewness (mean project cost {skew:.1f}x median)")

            if anom > 0:
                reasons.append(f"Historical cost/project anomalies recorded ({int(anom)} projects)")

            if util > 120.0:
                reasons.append(f"Average expenditure exceeds sanctioned budget ({util:.1f}%)")

            if level == "LOW" and not reasons:
                reasons.append("Consistent on-time project execution with low operational friction")
            elif not reasons:
                reasons.append("Moderate overall operational and financial performance")

            reasons_list.append("; ".join(reasons))

        perf_df["agency_risk_score"] = risk_scores
        perf_df["agency_risk_level"] = risk_levels
        perf_df["risk_level"] = risk_levels
        perf_df["risk_reasons"] = reasons_list

        # Order columns cleanly
        output_cols = [
            "agency_id", "agency_name", "total_projects", "completed_projects",
            "ongoing_projects", "completion_rate", "delay_rate", "average_delay_days",
            "average_utilization", "anomaly_count", "high_risk_project_count",
            "agency_risk_score", "agency_risk_level", "risk_level", "risk_reasons"
        ]
        return perf_df[output_cols].sort_values("agency_risk_score", ascending=False).reset_index(drop=True)


def run_agency_profiling_pipeline(
    input_csv_path: str = "ml_input/vendor_features.csv",
    output_csv_path: str = "ml_outputs/agency_profiles.csv"
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Execute complete end-to-end Agency Profiling pipeline."""
    logger.info(f"Loading agency/vendor data from {input_csv_path}...")
    df = pd.read_csv(input_csv_path)
    total_records = len(df)
    logger.info(f"Loaded {total_records} agency records.")

    profiler = AgencyProfiler()
    profiles_df = profiler.profile_agencies(df)

    os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)
    profiles_df.to_csv(output_csv_path, index=False)
    logger.info(f"Agency profiles written successfully to {output_csv_path}")

    level_counts = profiles_df["agency_risk_level"].value_counts().to_dict()
    metrics = {
        "total_agencies": total_records,
        "risk_levels": level_counts,
        "score_min": float(profiles_df["agency_risk_score"].min()),
        "score_max": float(profiles_df["agency_risk_score"].max()),
        "score_mean": float(profiles_df["agency_risk_score"].mean()),
        "score_median": float(profiles_df["agency_risk_score"].median())
    }
    logger.info(f"Agency profiling summary metrics: {metrics}")
    return profiles_df, metrics


if __name__ == "__main__":
    run_agency_profiling_pipeline()
