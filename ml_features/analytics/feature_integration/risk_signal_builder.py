"""
risk_signal_builder.py
======================
Standardizes heterogeneous detection outputs into normalized float risk scores [0.0, 1.0],
interpretable boolean flags, and explicit feature availability indicators.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .schema import PRIMARY_KEY

logger = logging.getLogger("FeatureIntegration.RiskSignals")


class RiskSignalBuilder:
    """Builds clean, standardized risk signals [0.0, 1.0] and boolean flags from raw outputs."""

    @staticmethod
    def build_signals(df: pd.DataFrame) -> pd.DataFrame:
        """Enrich merged DataFrame with standardized risk scores, flags, and availability."""
        res = df.copy()

        # ---------------------------------------------------------------------
        # 1. Cost Anomaly Signal
        # ---------------------------------------------------------------------
        if "cost_anomaly_score" in res.columns:
            cost_numeric = pd.to_numeric(res["cost_anomaly_score"], errors="coerce")
            res["cost_available"] = cost_numeric.notna()
            res["cost_risk_score"] = cost_numeric.clip(lower=0.0, upper=1.0)
            is_anom = pd.to_numeric(res.get("is_cost_anomaly", 0), errors="coerce").fillna(0) == 1
            high_score = res["cost_risk_score"].fillna(0.0) >= 0.60
            res["cost_risk_flag"] = (is_anom | high_score) & res["cost_available"]
        else:
            res["cost_available"] = False
            res["cost_risk_score"] = np.nan
            res["cost_risk_flag"] = False

        # ---------------------------------------------------------------------
        # 2. Delay Prediction Signal
        # ---------------------------------------------------------------------
        if "delay_risk_score" in res.columns:
            delay_numeric = pd.to_numeric(res["delay_risk_score"], errors="coerce")
            res["delay_available"] = delay_numeric.notna()
            res["delay_risk_score"] = delay_numeric.clip(lower=0.0, upper=1.0)
            is_delayed = pd.to_numeric(res.get("is_delayed_predicted", 0), errors="coerce").fillna(0) == 1
            lvl_crit = res.get("delay_risk_level", "").fillna("").astype(str).str.upper().isin(["HIGH", "CRITICAL"])
            res["delay_risk_flag"] = (is_delayed | lvl_crit) & res["delay_available"]
        else:
            res["delay_available"] = False
            res["delay_risk_score"] = np.nan
            res["delay_risk_flag"] = False

        # ---------------------------------------------------------------------
        # 3. Payment Anomaly Signal
        # ---------------------------------------------------------------------
        if "payment_anomaly_score" in res.columns:
            pay_numeric = pd.to_numeric(res["payment_anomaly_score"], errors="coerce")
            res["payment_available"] = pay_numeric.notna()
            res["payment_risk_score"] = pay_numeric.clip(lower=0.0, upper=1.0)
            is_pay_anom = pd.to_numeric(res.get("is_payment_anomaly", 0), errors="coerce").fillna(0) == 1
            res["payment_risk_flag"] = (is_pay_anom | (res["payment_risk_score"].fillna(0.0) >= 0.50)) & res["payment_available"]
        else:
            res["payment_available"] = False
            res["payment_risk_score"] = np.nan
            res["payment_risk_flag"] = False

        # ---------------------------------------------------------------------
        # 4. Rule Engine Signal
        # ---------------------------------------------------------------------
        # Raw rule score ranges 0 to 300 based on severity weights
        if "raw_rule_risk_score" in res.columns:
            rule_raw = pd.to_numeric(res["raw_rule_risk_score"], errors="coerce")
            res["rule_available"] = rule_raw.notna()
            res["rule_risk_score"] = (rule_raw / 300.0).clip(lower=0.0, upper=1.0)
            rule_cnt = pd.to_numeric(res.get("rule_count", 0), errors="coerce").fillna(0)
            res["rule_risk_flag"] = (rule_cnt > 0) & res["rule_available"]
        elif "max_rule_severity_score" in res.columns:
            rule_raw = pd.to_numeric(res["max_rule_severity_score"], errors="coerce")
            res["rule_available"] = rule_raw.notna()
            res["rule_risk_score"] = (rule_raw / 100.0).clip(lower=0.0, upper=1.0)
            res["rule_risk_flag"] = (res["rule_risk_score"].fillna(0.0) > 0.0) & res["rule_available"]
        else:
            res["rule_available"] = False
            res["rule_risk_score"] = np.nan
            res["rule_risk_flag"] = False

        # ---------------------------------------------------------------------
        # 5. Similarity & Duplicate Signal
        # ---------------------------------------------------------------------
        if "duplicate_risk_score" in res.columns:
            sim_numeric = pd.to_numeric(res["duplicate_risk_score"], errors="coerce")
            res["similarity_available"] = sim_numeric.notna()
            res["similarity_risk_score"] = sim_numeric.clip(lower=0.0, upper=1.0)
            exact_txt = pd.to_numeric(res.get("exact_text_duplicate_flag", 0), errors="coerce").fillna(0) == 1
            high_txt = pd.to_numeric(res.get("high_text_similarity_flag", 0), errors="coerce").fillna(0) == 1
            res["similarity_risk_flag"] = (exact_txt | high_txt | (res["similarity_risk_score"].fillna(0.0) >= 0.50)) & res["similarity_available"]
        elif "max_pair_risk_score" in res.columns:
            sim_numeric = pd.to_numeric(res["max_pair_risk_score"], errors="coerce")
            res["similarity_available"] = sim_numeric.notna()
            res["similarity_risk_score"] = sim_numeric.clip(lower=0.0, upper=1.0)
            res["similarity_risk_flag"] = (res["similarity_risk_score"].fillna(0.0) >= 0.50) & res["similarity_available"]
        else:
            res["similarity_available"] = False
            res["similarity_risk_score"] = np.nan
            res["similarity_risk_flag"] = False

        # ---------------------------------------------------------------------
        # 6. Multivariate Anomaly (Isolation Forest) Signal
        # ---------------------------------------------------------------------
        if "iforest_score" in res.columns:
            if_numeric = pd.to_numeric(res["iforest_score"], errors="coerce")
            res["iforest_available"] = if_numeric.notna()
            res["iforest_risk_score"] = if_numeric.clip(lower=0.0, upper=1.0)
            is_if_anom = pd.to_numeric(res.get("iforest_is_anomaly", 0), errors="coerce").fillna(0) == 1
            res["iforest_risk_flag"] = (is_if_anom | (res["iforest_risk_score"].fillna(0.0) >= 0.50)) & res["iforest_available"]
        else:
            res["iforest_available"] = False
            res["iforest_risk_score"] = np.nan
            res["iforest_risk_flag"] = False

        logger.info("Standardized risk signals and availability flags constructed successfully.")
        return res
