"""
risk_aggregator.py
==================
Configurable risk aggregation engine with Explainable AI (XAI) audit synthesis.
Computes weighted composite risk scores, dynamic feature renormalization,
actionable risk tiers, and evidence payloads.
"""

from __future__ import annotations
import json
import logging
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

from .schema import (
    DEFAULT_WEIGHTS,
    DEFAULT_RISK_THRESHOLDS,
    NORMALIZED_SCORE_COLS,
    NORMALIZED_FLAG_COLS
)

logger = logging.getLogger("FeatureIntegration.RiskAggregator")


class RiskAggregator:
    """Configurable risk aggregation with Explainable AI (XAI) attribution and audit payloads."""

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        thresholds: Optional[Dict[str, Tuple[float, float]]] = None
    ):
        self.weights = dict(DEFAULT_WEIGHTS) if weights is None else dict(weights)
        self.thresholds = dict(DEFAULT_RISK_THRESHOLDS) if thresholds is None else dict(thresholds)
        self._validate_weights()

    def _validate_weights(self) -> None:
        """Validate that configured weights sum to 1.0 within numerical tolerance."""
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-4:
            raise ValueError(f"Risk weights must sum to 1.0. Current sum is: {total:.6f} for weights: {self.weights}")
        for k, v in self.weights.items():
            if v < 0.0 or v > 1.0:
                raise ValueError(f"Weight for '{k}' must be between 0.0 and 1.0. Found: {v}")

    def map_risk_category(self, score: float) -> str:
        """Map a numeric risk score [0.0, 1.0] to an actionable risk category."""
        if pd.isna(score):
            return "UNKNOWN"
        val = float(score)
        for cat, (low, high) in self.thresholds.items():
            # Allow high edge inclusion for top category
            if low <= val < high or (high == 1.0 and val >= high):
                return cat
        if val >= 1.0:
            return "CRITICAL"
        return "LOW"

    def compute_project_risk(self, row: pd.Series) -> Dict[str, Any]:
        """Compute aggregate risk score, risk band, and Explainable AI factors for a single project record."""
        active_weights: Dict[str, float] = {}
        weighted_scores: Dict[str, float] = {}

        # 1. Evaluate available signals and renormalize weights
        for signal_name, base_weight in self.weights.items():
            score_col = f"{signal_name}_score"
            avail_col = f"{signal_name.replace('_risk', '')}_available"

            score = row.get(score_col, np.nan)
            avail = row.get(avail_col, pd.notna(score))

            if avail and pd.notna(score):
                active_weights[signal_name] = base_weight
                weighted_scores[signal_name] = float(score)

        total_active_weight = sum(active_weights.values())
        if total_active_weight > 0:
            # Dynamic Renormalization: active weights sum to 1.0
            overall_score = sum(
                (w / total_active_weight) * weighted_scores[sig]
                for sig, w in active_weights.items()
            )
            overall_score = float(np.clip(overall_score, 0.0, 1.0))
        else:
            overall_score = 0.0

        risk_category = self.map_risk_category(overall_score)

        # ---------------------------------------------------------------------
        # Explainable AI (XAI): Feature Attribution & Evidence Synthesis
        # ---------------------------------------------------------------------
        contributions: List[Tuple[str, float, float]] = []
        if overall_score > 0 and total_active_weight > 0:
            for sig, w in active_weights.items():
                s = weighted_scores[sig]
                raw_contrib = (w / total_active_weight) * s
                pct_contrib = (raw_contrib / overall_score) * 100.0 if overall_score > 0 else 0.0
                contributions.append((sig, s, pct_contrib))
            contributions.sort(key=lambda x: x[2], reverse=True)

        top_signals: List[str] = []
        for sig, s, pct in contributions[:3]:
            label = sig.replace("_risk", "").replace("_", " ").title()
            top_signals.append(f"{label} (Score: {s:.2f}, Weight: {pct:.1f}%)")

        risk_factors: List[str] = []

        def _get_float(key: str, default: float = 0.0) -> float:
            v = row.get(key, default)
            if v is None or pd.isna(v):
                return default
            try:
                return float(v)
            except (ValueError, TypeError):
                return default

        # Cost Anomaly explanation
        if row.get("cost_risk_flag", False) or _get_float("cost_risk_score") >= 0.5:
            anom_type = str(row.get("cost_anomaly_type", "INFLATION")).replace("_", " ")
            z_score = row.get("cost_z_score", np.nan)
            z_str = f" (+{z_score:.1f}σ)" if pd.notna(z_score) else ""
            risk_factors.append(f"Cost Anomaly: {anom_type}{z_str} (Score: {_get_float('cost_risk_score'):.2f})")

        # Delay Risk explanation
        if row.get("delay_risk_flag", False) or _get_float("delay_risk_score") >= 0.5:
            pred_days = row.get("predicted_completion_days", np.nan)
            day_str = f" (~{int(pred_days)} days predicted)" if pd.notna(pred_days) else ""
            risk_factors.append(f"Delay Risk: Forecasted project delay{day_str} (Score: {_get_float('delay_risk_score'):.2f})")

        # Payment Anomaly explanation
        if row.get("payment_risk_flag", False) or _get_float("payment_risk_score") >= 0.5:
            pay_type = str(row.get("payment_anomaly_type", "UNUSUAL_PAYMENT")).replace("_", " ")
            risk_factors.append(f"Payment Anomaly: {pay_type} (Score: {_get_float('payment_risk_score'):.2f})")

        # Rule Violations explanation
        if row.get("rule_risk_flag", False) or _get_float("rule_risk_score") >= 0.3:
            rules_trig = str(row.get("rules_triggered", row.get("rule_ids_triggered", "Rules Triggered")))
            rule_cnt = row.get("rule_count", row.get("rule_event_count", 1))
            risk_factors.append(f"Rule Violations: {rules_trig} [{int(rule_cnt)} triggered] (Score: {_get_float('rule_risk_score'):.2f})")

        # Similarity / Duplicate explanation
        if row.get("similarity_risk_flag", False) or _get_float("similarity_risk_score") >= 0.5:
            dup_cnt = row.get("duplicate_count", row.get("pair_duplicate_count", 1))
            sim_score = _get_float("max_similarity_score", _get_float("similarity_risk_score"))
            is_exact = row.get("exact_text_duplicate_flag", 0) == 1
            verbatim_tag = " [Verbatim Text Match]" if is_exact else ""
            risk_factors.append(f"Duplicate Work Alert: {sim_score:.2f} text similarity with {int(dup_cnt)} project(s){verbatim_tag}")

        # Multivariate Anomaly explanation
        if row.get("iforest_risk_flag", False) or _get_float("iforest_risk_score") >= 0.5:
            drivers = str(row.get("top_anomaly_drivers", "")).strip()
            driver_str = f" [Drivers: {drivers[:80]}...]" if drivers and drivers != "nan" else ""
            risk_factors.append(f"Multivariate ML Anomaly: High dimensional deviation{driver_str}")

        if not risk_factors:
            risk_factors.append("Nominal project indicators: execution within normal baseline variance.")

        # Plain-English Executive Summary
        if overall_score >= 0.60:
            audit_explanation = (
                f"Flagged as {risk_category} RISK (score {overall_score:.2f}). "
                f"Primary drivers: {'; '.join(top_signals[:2])}."
            )
        elif overall_score >= 0.30:
            audit_explanation = (
                f"Classified as {risk_category} RISK (score {overall_score:.2f}). "
                f"Moderate operational or financial friction observed."
            )
        else:
            audit_explanation = (
                f"Classified as LOW RISK (score {overall_score:.2f}). "
                f"Performance metrics within expected parameters."
            )

        # Structured evidence payload for FastAPI / React
        evidence_payload = {
            "overall_risk_score": round(overall_score, 4),
            "risk_category": risk_category,
            "audit_explanation": audit_explanation,
            "top_risk_signals": top_signals,
            "risk_factors": risk_factors,
            "component_scores": {
                "cost_risk": round(float(row.get("cost_risk_score", 0.0)), 4) if pd.notna(row.get("cost_risk_score")) else None,
                "delay_risk": round(float(row.get("delay_risk_score", 0.0)), 4) if pd.notna(row.get("delay_risk_score")) else None,
                "payment_risk": round(float(row.get("payment_risk_score", 0.0)), 4) if pd.notna(row.get("payment_risk_score")) else None,
                "rule_risk": round(float(row.get("rule_risk_score", 0.0)), 4) if pd.notna(row.get("rule_risk_score")) else None,
                "similarity_risk": round(float(row.get("similarity_risk_score", 0.0)), 4) if pd.notna(row.get("similarity_risk_score")) else None,
                "iforest_risk": round(float(row.get("iforest_risk_score", 0.0)), 4) if pd.notna(row.get("iforest_risk_score")) else None
            },
            "active_weights": {k: round(w / total_active_weight, 4) for k, w in active_weights.items()} if total_active_weight > 0 else {}
        }

        return {
            "overall_risk_score": round(overall_score, 4),
            "risk_category": risk_category,
            "top_risk_signals": "; ".join(top_signals),
            "risk_factors": json.dumps(risk_factors),
            "audit_explanation": audit_explanation,
            "evidence_payload": json.dumps(evidence_payload)
        }

    def aggregate_dataset(self, df: pd.DataFrame) -> pd.DataFrame:
        """Vectorized and batch computation of overall risk across all projects."""
        logger.info(f"Computing aggregate risk scores and Explainable AI factors for {len(df)} projects...")
        records = [self.compute_project_risk(row) for _, row in df.iterrows()]
        risk_df = pd.DataFrame(records, index=df.index)

        res = pd.concat([df, risk_df], axis=1)
        dist = res["risk_category"].value_counts().to_dict()
        logger.info(f"Risk aggregation complete. Risk tier distribution: {dist}")
        return res
