"""
reason_generator.py
===================
Explainable AI reason generation engine for non-technical government auditors.
Translates multi-engine numerical scores and anomaly tags into plain-English narratives.
"""

from __future__ import annotations
import json
import logging
from typing import Dict, List, Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("Explainability.ReasonGenerator")


class ReasonGenerator:
    """Generates plain-English evidence briefs and factual bullet points for flagged projects."""

    @staticmethod
    def generate_reasons(row: pd.Series | Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize audit explanations and factual drivers from project risk signals."""
        def _get_float(k: str, def_val: float = 0.0) -> float:
            v = row.get(k, def_val)
            if v is None or pd.isna(v):
                return def_val
            try:
                return float(v)
            except (ValueError, TypeError):
                return def_val

        overall_score = _get_float("overall_risk_score", 0.0)
        risk_tier = str(row.get("risk_category", "LOW")).upper()

        risk_factors: List[str] = []

        # 1. Cost Overrun / Inflation
        cost_score = _get_float("cost_risk_score", _get_float("cost_anomaly_score"))
        is_cost = bool(row.get("cost_risk_flag", False)) or cost_score >= 0.5
        if is_cost:
            anom_type = str(row.get("cost_anomaly_type", "INFLATION")).replace("_", " ")
            z_score = row.get("cost_z_score", np.nan)
            z_str = f" (+{float(z_score):.1f}σ deviation)" if pd.notna(z_score) else ""
            risk_factors.append(f"Cost Anomaly: {anom_type}{z_str} (Score: {cost_score:.2f})")

        # 2. Delay Forecast
        delay_score = _get_float("delay_risk_score", 0.0)
        is_delay = bool(row.get("delay_risk_flag", False)) or delay_score >= 0.5
        if is_delay:
            pred_days = row.get("predicted_completion_days", np.nan)
            day_str = f" (~{int(pred_days)} days predicted)" if pd.notna(pred_days) else ""
            risk_factors.append(f"Delay Risk: Forecasted project stall{day_str} (Score: {delay_score:.2f})")

        # 3. Payment Anomaly
        pay_score = _get_float("payment_risk_score", _get_float("payment_anomaly_score"))
        is_pay = bool(row.get("payment_risk_flag", False)) or pay_score >= 0.5
        if is_pay:
            pay_type = str(row.get("payment_anomaly_type", "UNUSUAL_PAYMENT")).replace("_", " ")
            risk_factors.append(f"Payment Structuring: {pay_type} (Score: {pay_score:.2f})")

        # 4. Compliance & Ghost Rules
        rule_score = _get_float("rule_risk_score", 0.0)
        is_rule = bool(row.get("rule_risk_flag", False)) or rule_score >= 0.3
        if is_rule:
            rules_trig = str(row.get("rules_triggered", row.get("rule_ids_triggered", "Rules Triggered")))
            rule_cnt = row.get("rule_count", row.get("rule_event_count", 1))
            risk_factors.append(f"Rule Violations: {rules_trig} [{int(rule_cnt)} triggered] (Score: {rule_score:.2f})")

        # 5. Duplicate Work / Similarity
        sim_score = _get_float("similarity_risk_score", _get_float("duplicate_risk_score"))
        is_sim = bool(row.get("similarity_risk_flag", False)) or sim_score >= 0.5
        if is_sim:
            dup_cnt = row.get("duplicate_count", row.get("pair_duplicate_count", 1))
            exact = bool(row.get("exact_text_duplicate_flag", False))
            tag = " [Verbatim Duplicate Match]" if exact else ""
            risk_factors.append(f"Duplicate Work Alert: {sim_score:.2f} text similarity with {int(dup_cnt)} project(s){tag}")

        # 6. Multivariate ML Anomaly
        if_score = _get_float("iforest_risk_score", _get_float("iforest_score"))
        is_if = bool(row.get("iforest_risk_flag", False)) or if_score >= 0.5
        if is_if:
            drivers = str(row.get("top_anomaly_drivers", "")).strip()
            driver_str = f" [Drivers: {drivers[:80]}...]" if drivers and drivers != "nan" else ""
            risk_factors.append(f"Multivariate ML Outlier: High-dimensional deviation{driver_str}")

        if not risk_factors:
            risk_factors.append("Nominal project execution: operational metrics within normal historical tolerances.")

        # Executive summary
        if overall_score >= 0.60:
            summary = f"CRITICAL RISK: Severe financial, delay, or compliance anomalies detected. Immediate audit recommended."
        elif overall_score >= 0.30:
            summary = f"MODERATE RISK: Notable operational friction or cost deviations observed. Priority monitoring advised."
        else:
            summary = f"LOW RISK: Project performance aligns with standard baseline execution."

        return {
            "overall_risk_score": round(overall_score, 4),
            "risk_category": risk_tier,
            "executive_summary": summary,
            "risk_factors": risk_factors
        }
