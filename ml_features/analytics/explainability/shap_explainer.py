"""
shap_explainer.py
=================
TreeSHAP & Shapley Additive exPlanations for ML Risk and Delay Models.
Computes local feature attributions, base values, and positive/negative risk pushes.
"""

from __future__ import annotations
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
import joblib

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False

WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from analytics.ml_engine.xgboost_delay_model import CORE_FEATURES, CATEGORY_MAP

logger = logging.getLogger("Explainability.SHAP")


class ShapExplainer:
    """TreeSHAP explainer for XGBoost delay models and ML feature attributions."""

    def __init__(self, model_path: Optional[str] = None):
        if model_path is None:
            base = Path(__file__).resolve().parent.parent.parent
            model_path = str(base / "analytics" / "ml_engine" / "train" / "model_registry" / "xgboost_delay_model.joblib")
        self.model_path = model_path
        self.model = None
        self.imputer = None
        self.explainer = None
        self.expected_value = 0.0
        self.feature_names = list(CORE_FEATURES)
        self._load_model()

    def _load_model(self) -> None:
        if os.path.exists(self.model_path):
            try:
                data = joblib.load(self.model_path)
                if isinstance(data, dict):
                    self.model = data.get("model")
                    self.imputer = data.get("imputer")
                else:
                    self.model = data

                if HAS_SHAP and self.model is not None:
                    self.explainer = shap.TreeExplainer(self.model)
                    ev = self.explainer.expected_value
                    self.expected_value = float(ev) if np.isscalar(ev) else float(ev[0])
                    logger.info(f"TreeExplainer initialized with base expected value: {self.expected_value:.2f} days")
            except Exception as e:
                logger.warning(f"Could not load XGBoost model for SHAP from {self.model_path}: {e}")

    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        def _get_series(col: str, default: float) -> pd.Series:
            if col in df.columns:
                return pd.to_numeric(df[col], errors="coerce").fillna(default)
            return pd.Series(default, index=df.index, dtype=float)

        feat_df = pd.DataFrame(index=df.index)
        feat_df["recommended_amount"] = _get_series("recommended_amount", 0.0)

        # Map category code
        if "category" in df.columns:
            cat_series = df["category"].fillna("Normal/Others").astype(str)
        else:
            cat_series = pd.Series("Normal/Others", index=df.index)
        feat_df["category_code"] = cat_series.map(lambda c: CATEGORY_MAP.get(c, 0)).astype(int)

        feat_df["payment_count"] = _get_series("payment_count", 0.0)
        feat_df["pending_payment_count"] = _get_series("pending_payment_count", 0.0)

        # has_images
        if "has_images" in df.columns:
            feat_df["has_images_code"] = df["has_images"].fillna(False).astype(bool).astype(int)
        else:
            feat_df["has_images_code"] = 0

        feat_df["completion_rate_pct"] = _get_series("completion_rate_pct", 50.0)
        feat_df["utilization_pct"] = _get_series("utilization_pct", 50.0)
        feat_df["completion_gap"] = _get_series("completion_gap", 0.0)

        if self.imputer is not None:
            imputed = self.imputer.transform(feat_df)
            feat_df = pd.DataFrame(imputed, columns=self.feature_names, index=df.index)

        return feat_df

    def explain_dataset(self, df: pd.DataFrame, max_samples: Optional[int] = None) -> pd.DataFrame:
        """Compute SHAP feature attributions across a dataset.

        Returns DataFrame with:
        - project_id
        - shap_base_value: expected baseline prediction
        - shap_top_delay_pusher: feature adding the most predicted delay days
        - shap_top_delay_dampener: feature subtracting the most predicted delay days
        - shap_feature_attributions: JSON dictionary of feature -> delta days
        """
        subset = df.head(max_samples) if max_samples else df
        feat_matrix = self.prepare_features(subset)

        if not HAS_SHAP or self.explainer is None:
            logger.warning("SHAP not available or model not loaded. Using linear fallback attributions.")
            return self._heuristic_fallback(subset, feat_matrix)

        logger.info(f"Computing TreeSHAP values for {len(feat_matrix)} project records...")
        shap_vals = self.explainer.shap_values(feat_matrix)

        records: List[Dict[str, Any]] = []
        pids = subset.get("project_id", [f"P_{i}" for i in range(len(subset))]).tolist()

        for idx, pid in enumerate(pids):
            row_shap = shap_vals[idx]
            attribs: Dict[str, float] = {
                feat: round(float(row_shap[i]), 2)
                for i, feat in enumerate(self.feature_names)
            }

            # Top pusher (+ delay)
            sorted_pushes = sorted(attribs.items(), key=lambda x: x[1], reverse=True)
            top_pusher = f"{sorted_pushes[0][0]} (+{sorted_pushes[0][1]}d)" if sorted_pushes[0][1] > 0 else "None"

            # Top dampener (- delay)
            sorted_dampeners = sorted(attribs.items(), key=lambda x: x[1])
            top_dampener = f"{sorted_dampeners[0][0]} ({sorted_dampeners[0][1]}d)" if sorted_dampeners[0][1] < 0 else "None"

            records.append({
                "project_id": pid,
                "shap_base_value": round(self.expected_value, 2),
                "shap_top_delay_pusher": top_pusher,
                "shap_top_delay_dampener": top_dampener,
                "shap_feature_attributions": json.dumps(attribs)
            })

        res = pd.DataFrame(records)
        logger.info("SHAP attribution computation complete.")
        return res

    def _heuristic_fallback(self, df: pd.DataFrame, feat_matrix: pd.DataFrame) -> pd.DataFrame:
        """Lightweight statistical attribution fallback."""
        records = []
        pids = df.get("project_id", [f"P_{i}" for i in range(len(df))]).tolist()
        for idx, pid in enumerate(pids):
            row = feat_matrix.iloc[idx]
            pend = row.get("pending_payment_count", 0) * 15.0
            amt = (row.get("recommended_amount", 0) / 100000.0) * 2.0
            attribs = {
                "pending_payment_count": round(pend, 2),
                "recommended_amount": round(amt, 2)
            }
            records.append({
                "project_id": pid,
                "shap_base_value": 450.0,
                "shap_top_delay_pusher": f"pending_payment_count (+{pend:.1f}d)",
                "shap_top_delay_dampener": "None",
                "shap_feature_attributions": json.dumps(attribs)
            })
        return pd.DataFrame(records)


def run_shap_pipeline(
    input_csv: str = "ml_input/project_features.csv",
    output_csv: str = "ml_outputs/shap_delay_explanations.csv",
    sample_size: int = 500
) -> pd.DataFrame:
    """Execute SHAP analysis and export explanations."""
    base = Path(__file__).resolve().parent.parent.parent
    in_path = base / input_csv
    out_path = base / output_csv

    logger.info(f"Loading input data for SHAP analysis from: {in_path}")
    df = pd.read_csv(in_path, nrows=sample_size, low_memory=False)

    explainer = ShapExplainer()
    shap_df = explainer.explain_dataset(df)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    shap_df.to_csv(out_path, index=False)
    logger.info(f"SHAP explanations saved to: {out_path}")
    return shap_df


if __name__ == "__main__":
    run_shap_pipeline()
