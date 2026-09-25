"""
alert_generator.py
==================
Proactive early warning alert trigger engine for impending budget runaways,
chronic stalled decay, transaction bursts, and critical delivery delays.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

logger = logging.getLogger("EarlyWarning.AlertGenerator")


class AlertGenerator:
    """Generates structured, actionable early-warning alerts for field monitoring."""

    def generate_alerts(
        self,
        projects_df: pd.DataFrame,
        trends_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """Scan projects and emit early warning alerts with severity and recommended action.

        Returns DataFrame of alerts:
        - project_id
        - mp_name
        - state
        - alert_code
        - alert_severity (CRITICAL, WARNING, ADVISORY)
        - alert_title
        - alert_detail
        - recommended_action
        """
        alerts: List[Dict[str, Any]] = []

        # Merge trends if provided
        df = projects_df.copy()
        if trends_df is not None and not trends_df.empty:
            df = df.merge(trends_df, on="project_id", how="left")

        for _, r in df.iterrows():
            pid = r.get("project_id", "Unknown")
            mp = r.get("mp_name", "N/A")
            st = r.get("state", "N/A")

            rec_amt = float(r.get("recommended_amount", 0.0) or 0.0)
            exp_amt = float(r.get("total_expenditure", 0.0) or 0.0)
            ratio = float(r.get("expenditure_ratio", 0.0) or 0.0)
            days = float(r.get("days_since_recommendation", 0.0) or 0.0)
            is_comp = int(r.get("is_completed", 0) or 0) == 1

            # 1. Budget Overrun Alert
            if ratio > 1.10 and exp_amt > 100000:
                alerts.append({
                    "project_id": pid,
                    "mp_name": mp,
                    "state": st,
                    "alert_code": "WARN_BUDGET_OVERRUN",
                    "alert_severity": "CRITICAL",
                    "alert_title": "Severe Budget Overrun Triggered",
                    "alert_detail": f"Expenditure exceeds sanctioned amount by {(ratio - 1.0)*100:.1f}% (Spent: ₹{exp_amt:,.0f} vs Sanctioned: ₹{rec_amt:,.0f})",
                    "recommended_action": "Freeze disbursements and audit revised administrative sanction."
                })

            # 2. Runaway Spend Velocity Alert
            if r.get("is_runaway_spend", False) or r.get("burn_rate_status") == "RUNAWAY_BURN":
                vel = r.get("spend_velocity_daily", 0.0)
                peer_vel = r.get("peer_median_velocity", 1.0)
                alerts.append({
                    "project_id": pid,
                    "mp_name": mp,
                    "state": st,
                    "alert_code": "WARN_RUNAWAY_VELOCITY",
                    "alert_severity": "WARNING",
                    "alert_title": "Abnormal Expenditure Velocity",
                    "alert_detail": f"Project is burning funds at ₹{vel:.0f}/day ({vel/max(peer_vel, 1):.1f}x peer median rate) while incomplete.",
                    "recommended_action": "Conduct immediate physical site milestone verification."
                })

            # 3. Chronic Stalled Decay Alert
            if days >= 365 and ratio < 0.10 and not is_comp:
                alerts.append({
                    "project_id": pid,
                    "mp_name": mp,
                    "state": st,
                    "alert_code": "WARN_CHRONIC_STALL",
                    "alert_severity": "WARNING",
                    "alert_title": "Chronic Project Inactivity",
                    "alert_detail": f"Work has remained dormant for {int(days)} days since recommendation with <10% utilization.",
                    "recommended_action": "Issue inquiry to nodal district authority on implementation hurdles."
                })

            # 4. Impending Delivery Delay Alert
            pred_days = float(r.get("predicted_completion_days", 0.0) or 0.0)
            if pred_days >= 500 and not is_comp:
                alerts.append({
                    "project_id": pid,
                    "mp_name": mp,
                    "state": st,
                    "alert_code": "WARN_IMPENDING_DELAY",
                    "alert_severity": "ADVISORY",
                    "alert_title": "Predicted Prolonged Execution Duration",
                    "alert_detail": f"ML model forecasts completion will require ~{int(pred_days)} days based on agency friction and history.",
                    "recommended_action": "Review contractor capacity and establish monthly progress checkpoints."
                })

            # 5. Payment Structuring / Burst Alert
            if bool(r.get("payment_risk_flag", False)) or float(r.get("payment_risk_score", 0) or 0) >= 0.70:
                alerts.append({
                    "project_id": pid,
                    "mp_name": mp,
                    "state": st,
                    "alert_code": "WARN_PAYMENT_CHURN",
                    "alert_severity": "CRITICAL",
                    "alert_title": "High-Frequency Payment Churn Detected",
                    "alert_detail": "Unusual burst or round-sum payment pattern flagged by payment anomaly detector.",
                    "recommended_action": "Inspect bank transaction timestamps and contractor vendor vouchers."
                })

        alert_df = pd.DataFrame(alerts)
        logger.info(f"Generated {len(alert_df)} early warning alerts across projects.")
        return alert_df


def run_alert_generation_pipeline(
    projects_csv: str = "ml_outputs/project_risk_results.csv",
    trends_csv: str = "ml_outputs/project_trend_analysis.csv",
    output_csv: str = "ml_outputs/early_warning_alerts.csv"
) -> pd.DataFrame:
    """Execute complete early warning alert generation pipeline."""
    base = Path(__file__).resolve().parent.parent.parent
    proj_path = base / projects_csv
    trend_path = base / trends_csv
    out_path = base / output_csv

    logger.info(f"Loading data for alert generation from: {proj_path}")
    projects_df = pd.read_csv(proj_path, low_memory=False)
    trends_df = pd.read_csv(trend_path, low_memory=False) if trend_path.exists() else None

    generator = AlertGenerator()
    alerts_df = generator.generate_alerts(projects_df, trends_df)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    alerts_df.to_csv(out_path, index=False)
    logger.info(f"Early warning alerts written to: {out_path}")
    return alerts_df


if __name__ == "__main__":
    run_alert_generation_pipeline()
