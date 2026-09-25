"""XGBoost Delay Prediction Model for MPLAD-Sentinel DEV B.

This module provides gradient-boosted project duration and delay risk prediction for MPLADS works.
It predicts expected project completion duration (in days) using historical completed projects,
project scale, category, payment signals, and MP performance metrics.
It then assesses the delay risk of ongoing projects based on elapsed time vs expected timeline.

Outputs are written to `ml_outputs/delay_predictions.csv`.
"""

from __future__ import annotations

import os
import logging
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.impute import SimpleImputer
import joblib

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CATEGORY_MAP: Dict[str, int] = {
    "Normal/Others": 0,
    "Repair and Renovation": 1,
    "Trust and Society": 2,
    "Bar and Associations": 3
}

CORE_FEATURES: List[str] = [
    "recommended_amount",
    "category_code",
    "payment_count",
    "pending_payment_count",
    "has_images_code",
    "completion_rate_pct",
    "utilization_pct",
    "completion_gap"
]


class XGBoostDelayPredictor:
    """XGBoost Regressor for project completion duration and delay risk estimation.

    Parameters
    ----------
    n_estimators : int, default=100
        Number of gradient boosted trees.
    max_depth : int, default=4
        Maximum tree depth.
    learning_rate : float, default=0.05
        Boosting learning rate.
    random_state : int, default=42
        Random seed for reproducibility.
    """

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 4,
        learning_rate: float = 0.05,
        random_state: int = 42
    ) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.random_state = random_state

        self.model = xgb.XGBRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            random_state=self.random_state,
            n_jobs=-1
        )
        self.imputer = SimpleImputer(strategy="median")
        self.is_fitted: bool = False
        self.baseline_median_duration_: float = 500.0
        self.baseline_mean_duration_: float = 520.0

    def _prepare_features(self, df: pd.DataFrame, mp_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Merge auxiliary MP features if provided and encode features."""
        data = df.copy()

        # Merge MP features if available
        if mp_df is not None and "mp_name" in data.columns and "mp_name" in mp_df.columns:
            mp_cols = ["mp_name", "completion_rate_pct", "utilization_pct", "completion_gap"]
            mp_sub = mp_df[[c for c in mp_cols if c in mp_df.columns]].drop_duplicates(subset=["mp_name"])
            data = data.merge(mp_sub, on="mp_name", how="left")

        # Encode categorical and boolean columns
        if "category" in data.columns:
            data["category_code"] = data["category"].map(CATEGORY_MAP).fillna(0).astype(int)
        elif "category_code" not in data.columns:
            data["category_code"] = 0

        if "has_images" in data.columns:
            data["has_images_code"] = data["has_images"].astype(bool).astype(int)
        elif "has_images_code" not in data.columns:
            data["has_images_code"] = 0

        # Ensure all core features exist in DataFrame (defaulting if not merged)
        defaults = {
            "recommended_amount": 500000.0,
            "payment_count": 0,
            "pending_payment_count": 0,
            "completion_rate_pct": 50.0,
            "utilization_pct": 75.0,
            "completion_gap": 0.0
        }
        for col, default_val in defaults.items():
            if col not in data.columns:
                data[col] = default_val

        # Select only core features
        X_df = data[CORE_FEATURES].copy()
        for col in CORE_FEATURES:
            X_df[col] = pd.to_numeric(X_df[col], errors="coerce").replace([np.inf, -np.inf], np.nan)

        return X_df

    def fit(self, df: pd.DataFrame, mp_df: Optional[pd.DataFrame] = None) -> XGBoostDelayPredictor:
        """Fit the XGBoost regressor on completed projects."""
        logger.info("Preparing training dataset for XGBoost delay predictor...")

        # Filter completed projects
        if "is_completed" in df.columns:
            completed_mask = df["is_completed"] == 1
        elif "recommendation_to_completion_days" in df.columns:
            completed_mask = df["recommendation_to_completion_days"].notna()
        else:
            completed_mask = pd.Series(True, index=df.index)

        completed_df = df[completed_mask].copy()
        if len(completed_df) == 0:
            raise ValueError("No completed projects found in dataset for training.")

        logger.info(f"Training XGBoost on {len(completed_df)} completed project records.")

        # Compute physical duration (taking absolute value to handle sign conventions)
        if "recommendation_to_completion_days" in completed_df.columns:
            target_durations = completed_df["recommendation_to_completion_days"].abs()
        elif "duration_days" in completed_df.columns:
            target_durations = completed_df["duration_days"].abs()
        else:
            raise ValueError("No completion duration target column found.")

        # Filter invalid target durations
        valid_idx = target_durations > 0
        completed_df = completed_df[valid_idx]
        y = target_durations[valid_idx].values

        self.baseline_median_duration_ = float(np.median(y))
        self.baseline_mean_duration_ = float(np.mean(y))

        X_df = self._prepare_features(completed_df, mp_df=mp_df)
        X_imputed = self.imputer.fit_transform(X_df)

        self.model.fit(X_imputed, y)
        self.is_fitted = True
        logger.info(
            f"XGBoost fit complete. Baseline duration: Median={self.baseline_median_duration_:.1f}d, "
            f"Mean={self.baseline_mean_duration_:.1f}d"
        )
        return self

    def predict(self, df: pd.DataFrame, mp_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Predict expected duration and delay risk scores for all projects."""
        if not self.is_fitted:
            raise RuntimeError("XGBoostDelayPredictor must be fitted before predict().")

        X_df = self._prepare_features(df, mp_df=mp_df)
        X_imputed = self.imputer.transform(X_df)

        # Predict expected completion duration in days
        pred_durations = self.model.predict(X_imputed)
        # Clip predicted duration between realistic bounds: 90 days (~3 months) and 1200 days (~3.3 years)
        pred_durations = np.clip(pred_durations, 90.0, 1200.0)

        # Elapsed days
        elapsed_days = pd.to_numeric(df.get("days_since_recommendation", 0.0), errors="coerce").fillna(0.0).values
        elapsed_days = np.maximum(0.0, elapsed_days)

        is_comp = pd.to_numeric(df.get("is_completed", 0), errors="coerce").fillna(0).values.astype(int)

        # Calculate delay velocity ratio: elapsed / predicted
        ratio = elapsed_days / np.maximum(pred_durations, 60.0)

        # Delay risk score computation:
        # Sigmoid centered around ratio = 0.95 (where elapsed approaches expected timeline)
        base_risk = 1.0 / (1.0 + np.exp(-3.5 * (ratio - 0.95)))

        # Penalize projects with stalled/pending payments
        pending_payments = pd.to_numeric(df.get("pending_payment_count", 0), errors="coerce").fillna(0).values
        pending_boost = np.clip(pending_payments * 0.05, 0.0, 0.20)

        # If completed, risk reflects whether actual duration exceeded predicted
        if "recommendation_to_completion_days" in df.columns:
            actual_comp_days = pd.to_numeric(df["recommendation_to_completion_days"], errors="coerce").abs().values
        else:
            actual_comp_days = np.full(len(df), np.nan)

        completed_risk = np.where(
            np.nan_to_num(actual_comp_days, nan=0.0) > pred_durations,
            np.clip((np.nan_to_num(actual_comp_days, nan=0.0) - pred_durations) / pred_durations, 0.0, 1.0),
            0.05
        )

        final_risk = np.where(is_comp == 1, completed_risk, base_risk + pending_boost)
        final_risk = np.clip(final_risk, 0.0, 1.0)

        # Classify risk level
        risk_levels: List[str] = []
        for score in final_risk:
            if score < 0.35:
                risk_levels.append("LOW")
            elif score < 0.65:
                risk_levels.append("MEDIUM")
            elif score < 0.85:
                risk_levels.append("HIGH")
            else:
                risk_levels.append("CRITICAL")

        is_delayed_pred = (final_risk >= 0.50).astype(int)

        project_ids = df["project_id"].tolist() if "project_id" in df.columns else [f"proj_{i}" for i in range(len(df))]

        results_df = pd.DataFrame({
            "project_id": project_ids,
            "days_since_recommendation": np.round(elapsed_days, 1),
            "predicted_completion_days": np.round(pred_durations, 1),
            "delay_risk_score": np.round(final_risk, 4),
            "delay_risk_level": risk_levels,
            "is_delayed_predicted": is_delayed_pred
        })

        # Attach rank: rank 1 is highest delay risk
        results_df["delay_risk_rank"] = results_df["delay_risk_score"].rank(ascending=False, method="min").astype(int)

        return results_df

    def save(self, file_path: str) -> None:
        """Serialize model to disk."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        payload = {
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "learning_rate": self.learning_rate,
            "random_state": self.random_state,
            "model": self.model,
            "imputer": self.imputer,
            "is_fitted": self.is_fitted,
            "baseline_median_duration": self.baseline_median_duration_,
            "baseline_mean_duration": self.baseline_mean_duration_
        }
        joblib.dump(payload, file_path)
        logger.info(f"XGBoostDelayPredictor saved to {file_path}")

    @classmethod
    def load(cls, file_path: str) -> XGBoostDelayPredictor:
        """Load model from disk."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Model file not found: {file_path}")
        payload = joblib.load(file_path)
        predictor = cls(
            n_estimators=payload["n_estimators"],
            max_depth=payload["max_depth"],
            learning_rate=payload["learning_rate"],
            random_state=payload["random_state"]
        )
        predictor.model = payload["model"]
        predictor.imputer = payload["imputer"]
        predictor.is_fitted = payload["is_fitted"]
        predictor.baseline_median_duration_ = payload["baseline_median_duration"]
        predictor.baseline_mean_duration_ = payload["baseline_mean_duration"]
        logger.info(f"XGBoostDelayPredictor loaded from {file_path}")
        return predictor


def run_delay_prediction_pipeline(
    project_csv_path: str = "ml_input/project_features.csv",
    mp_csv_path: str = "ml_input/mp_features.csv",
    output_csv_path: str = "ml_outputs/delay_predictions.csv",
    model_save_path: str = "analytics/ml_engine/train/model_registry/xgboost_delay_model.joblib"
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Execute end-to-end Delay Prediction training and inference pipeline."""
    logger.info(f"Loading project features from {project_csv_path}...")
    df = pd.read_csv(project_csv_path)
    total_records = len(df)
    logger.info(f"Loaded {total_records} project records.")

    mp_df = None
    if os.path.exists(mp_csv_path):
        logger.info(f"Loading MP features from {mp_csv_path}...")
        mp_df = pd.read_csv(mp_csv_path)

    predictor = XGBoostDelayPredictor()
    predictor.fit(df, mp_df=mp_df)
    predictor.save(model_save_path)

    results_df = predictor.predict(df, mp_df=mp_df)

    # Attach helpful context fields
    for col in ["mp_name", "state", "constituency", "category", "recommended_amount", "is_completed"]:
        if col in df.columns:
            if col == "category":
                results_df[col] = df[col].fillna("Normal/Others")
            else:
                results_df[col] = df[col]

    # Sort results by delay_risk_rank ascending (rank 1 at top)
    results_df = results_df.sort_values("delay_risk_rank", ascending=True).reset_index(drop=True)

    os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)
    results_df.to_csv(output_csv_path, index=False)
    logger.info(f"Results written to {output_csv_path}")

    delayed_count = int(results_df["is_delayed_predicted"].sum())
    level_counts = results_df["delay_risk_level"].value_counts().to_dict()
    metrics = {
        "total_records": total_records,
        "delayed_predicted_count": delayed_count,
        "delayed_percentage": round((delayed_count / total_records) * 100, 2),
        "risk_levels": level_counts,
        "predicted_duration_mean": float(results_df["predicted_completion_days"].mean()),
        "predicted_duration_median": float(results_df["predicted_completion_days"].median()),
        "score_min": float(results_df["delay_risk_score"].min()),
        "score_max": float(results_df["delay_risk_score"].max())
    }
    logger.info(f"Delay pipeline summary metrics: {metrics}")
    return results_df, metrics


if __name__ == "__main__":
    run_delay_prediction_pipeline()
