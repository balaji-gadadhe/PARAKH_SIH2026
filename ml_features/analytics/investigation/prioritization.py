"""
prioritization.py
=================
Multi-criteria investigation prioritization engine.
Balances risk probability with financial exposure (expenditure volume) and alert severity.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

logger = logging.getLogger("Investigation.Prioritization")


class InvestigationPrioritizer:
    """Calculates prioritized case scores combining risk severity and financial exposure."""

    @staticmethod
    def prioritize_cases(df: pd.DataFrame) -> pd.DataFrame:
        """Compute investigation priority score and assign triage action tiers.

        Columns produced:
        - project_id
        - investigation_priority_score: composite 0-100 priority score
        - investigation_urgency: TIER_1_IMMEDIATE, TIER_2_PRIORITY, TIER_3_DESK_REVIEW, TIER_4_ROUTINE
        - audit_dispatch_recommended: boolean
        """
        res = pd.DataFrame(index=df.index)
        res["project_id"] = df.get("project_id", [f"P_{i}" for i in range(len(df))])

        risk_score = pd.to_numeric(df.get("overall_risk_score", 0.0), errors="coerce").fillna(0.0)
        exp = pd.to_numeric(df.get("total_expenditure", 0.0), errors="coerce").fillna(0.0)

        # Log financial exposure normalized (1 lakh to 5 crore scale)
        exp_clipped = exp.clip(lower=10000.0, upper=50000000.0)
        log_exp = np.log10(exp_clipped)
        # Scale log_exp from [4, 7.7] to [0, 1]
        exp_score = np.clip((log_exp - 4.0) / 3.7, 0.0, 1.0)

        # Priority calculation (0-100): 60% risk score + 40% financial exposure
        priority_raw = (risk_score * 0.60 + exp_score * 0.40) * 100.0
        res["investigation_priority_score"] = priority_raw.round(2)

        # Triage tiers
        conditions = [
            (risk_score >= 0.70) | (priority_raw >= 65.0),
            (risk_score >= 0.45) | (priority_raw >= 45.0),
            (risk_score >= 0.25) | (priority_raw >= 30.0),
        ]
        choices = [
            "TIER_1_IMMEDIATE_ACTION",
            "TIER_2_PRIORITY_INSPECTION",
            "TIER_3_DESK_REVIEW"
        ]
        res["investigation_urgency"] = np.select(conditions, choices, default="TIER_4_ROUTINE")
        res["audit_dispatch_recommended"] = res["investigation_urgency"] == "TIER_1_IMMEDIATE_ACTION"

        logger.info(f"Prioritization complete for {len(res)} cases.")
        return res
