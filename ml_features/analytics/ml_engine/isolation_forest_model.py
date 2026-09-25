"""Isolation Forest Anomaly Detection Model for MPLAD-Sentinel DEV B.

This module provides unsupervised multivariate anomaly detection for MPLADS projects.
It identifies projects exhibiting anomalous combinations of financial allocation,
expenditure velocity, payment patterns, elapsed duration, and peer cost deviations.

Key Features:
- Clean modular class: IsolationForestDetector
- Robust missing value handling & feature scaling
- Calibrated anomaly score in [0, 1] interval (1.0 = most anomalous)
- Explainable anomaly drivers (top feature deviations per record)
- Export to ml_outputs/isolation_forest_results.csv
"""

from __future__ import annotations

import os
import logging
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler
import joblib

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Default feature set selected from project_features schema
DEFAULT_IF_FEATURES: List[str] = [
    "recommended_amount",
    "total_expenditure",
    "expenditure_ratio",
    "cost_deviation_from_peer",
    "payment_count",
    "pending_payment_count",
    "days_since_recommendation",
    "description_similarity_score"
]


class IsolationForestDetector:
    """Isolation Forest anomaly detector for MPLADS projects.

    Parameters
    ----------
    features : List[str], optional
        List of numerical feature columns to train on.
    contamination : float, default=0.05
        Expected proportion of outliers in the dataset.
    n_estimators : int, default=200
        Number of isolation trees in the ensemble.
    random_state : int, default=42
        Random seed for reproducibility.
    n_jobs : int, default=-1
        Number of CPU threads to use (-1 = all cores).
    """

    def __init__(
        self,
        features: Optional[List[str]] = None,
        contamination: float = 0.05,
        n_estimators: int = 200,
        random_state: int = 42,
        n_jobs: int = -1
    ) -> None:
        self.features = features or list(DEFAULT_IF_FEATURES)
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.n_jobs = n_jobs

        self.imputer = SimpleImputer(strategy="median")
        self.scaler = RobustScaler()
        self.model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=self.n_jobs
        )

        self.is_fitted: bool = False
        self.feature_means_: Dict[str, float] = {}
        self.feature_stds_: Dict[str, float] = {}
        self.score_min_: float = 0.0
        self.score_max_: float = 1.0

    def _prepare_matrix(self, df: pd.DataFrame, fit_preprocessor: bool = False) -> np.ndarray:
        """Extract and preprocess features matrix."""
        # Ensure all required features are present
        missing_cols = [col for col in self.features if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required feature columns in input: {missing_cols}")

        X_raw = df[self.features].copy()

        # Coerce numeric types and handle infs
        for col in self.features:
            X_raw[col] = pd.to_numeric(X_raw[col], errors="coerce")
            X_raw[col] = X_raw[col].replace([np.inf, -np.inf], np.nan)

        if fit_preprocessor:
            X_imputed = self.imputer.fit_transform(X_raw)
            X_scaled = self.scaler.fit_transform(X_imputed)

            # Store baseline statistics for feature attribution
            for idx, col in enumerate(self.features):
                vals = X_imputed[:, idx]
                self.feature_means_[col] = float(np.mean(vals))
                std = float(np.std(vals))
                self.feature_stds_[col] = std if std > 1e-6 else 1.0
        else:
            if not self.is_fitted:
                raise RuntimeError("Model must be fitted before transforming new data.")
            X_imputed = self.imputer.transform(X_raw)
            X_scaled = self.scaler.transform(X_imputed)

        return X_scaled

    def fit(self, df: pd.DataFrame) -> IsolationForestDetector:
        """Fit the Isolation Forest model on the input DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Dataset containing the feature columns.

        Returns
        -------
        IsolationForestDetector
            Fitted detector instance.
        """
        logger.info(f"Fitting IsolationForest with {len(self.features)} features on {len(df)} samples...")
        X_scaled = self._prepare_matrix(df, fit_preprocessor=True)

        self.model.fit(X_scaled)
        self.is_fitted = True

        # Calibrate score boundaries on training set
        raw_scores = -self.model.score_samples(X_scaled)
        self.score_min_ = float(np.min(raw_scores))
        self.score_max_ = float(np.max(raw_scores))
        if self.score_max_ <= self.score_min_:
            self.score_max_ = self.score_min_ + 1e-6

        logger.info(
            f"IsolationForest fit complete. Raw score range: [{self.score_min_:.4f}, {self.score_max_:.4f}]"
        )
        return self

    def compute_anomaly_drivers(self, df: pd.DataFrame, top_k: int = 3) -> List[str]:
        """Identify top features contributing to anomaly status via standardized deviations."""
        drivers: List[str] = []
        for _, row in df[self.features].iterrows():
            deviations = []
            for col in self.features:
                val = row[col]
                if pd.isna(val) or np.isinf(val):
                    continue
                mean = self.feature_means_.get(col, 0.0)
                std = self.feature_stds_.get(col, 1.0)
                z = (float(val) - mean) / std
                deviations.append((col, z, abs(z)))

            # Sort by absolute deviation descending
            deviations.sort(key=lambda x: x[2], reverse=True)
            top_devs = deviations[:top_k]
            formatted = "; ".join(
                [f"{col} ({'+' if z >= 0 else ''}{z:.1f} sigma)" for col, z, _ in top_devs]
            )
            drivers.append(formatted if formatted else "Normal profile")
        return drivers

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Score and flag anomalies for input projects.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame containing `project_id` and required feature columns.

        Returns
        -------
        pd.DataFrame
            Output DataFrame containing:
            - project_id
            - anomaly_score: float in [0, 1]
            - is_anomaly: 0 or 1
            - anomaly_rank: int (1 = highest anomaly)
            - top_anomaly_drivers: str
        """
        if not self.is_fitted:
            raise RuntimeError("Cannot predict with an unfitted IsolationForestDetector.")

        X_scaled = self._prepare_matrix(df, fit_preprocessor=False)

        # In scikit-learn, score_samples returns opposite of anomaly score (lower is more anomalous)
        # Invert so higher value = higher anomaly
        raw_scores = -self.model.score_samples(X_scaled)
        norm_scores = (raw_scores - self.score_min_) / (self.score_max_ - self.score_min_)
        norm_scores = np.clip(norm_scores, 0.0, 1.0)

        # Predictions: -1 is anomaly, +1 is inlier
        raw_preds = self.model.predict(X_scaled)
        is_anomaly = (raw_preds == -1).astype(int)

        project_ids = df["project_id"].tolist() if "project_id" in df.columns else [f"proj_{i}" for i in range(len(df))]

        results_df = pd.DataFrame({
            "project_id": project_ids,
            "anomaly_score": np.round(norm_scores, 4),
            "anomaly_label": raw_preds,
            "is_anomaly": is_anomaly
        })

        # Calculate rank: 1 is most anomalous
        results_df["anomaly_rank"] = results_df["anomaly_score"].rank(ascending=False, method="min").astype(int)

        # Compute explanatory drivers
        results_df["top_anomaly_drivers"] = self.compute_anomaly_drivers(df)

        return results_df

    def save(self, file_path: str) -> None:
        """Save the detector to disk."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        payload = {
            "features": self.features,
            "contamination": self.contamination,
            "n_estimators": self.n_estimators,
            "random_state": self.random_state,
            "imputer": self.imputer,
            "scaler": self.scaler,
            "model": self.model,
            "is_fitted": self.is_fitted,
            "feature_means": self.feature_means_,
            "feature_stds": self.feature_stds_,
            "score_min": self.score_min_,
            "score_max": self.score_max_
        }
        joblib.dump(payload, file_path)
        logger.info(f"IsolationForest detector saved successfully to {file_path}")

    @classmethod
    def load(cls, file_path: str) -> IsolationForestDetector:
        """Load a saved detector from disk."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Model file not found: {file_path}")
        payload = joblib.load(file_path)
        detector = cls(
            features=payload["features"],
            contamination=payload["contamination"],
            n_estimators=payload["n_estimators"],
            random_state=payload["random_state"]
        )
        detector.imputer = payload["imputer"]
        detector.scaler = payload["scaler"]
        detector.model = payload["model"]
        detector.is_fitted = payload["is_fitted"]
        detector.feature_means_ = payload["feature_means"]
        detector.feature_stds_ = payload["feature_stds"]
        detector.score_min_ = payload["score_min"]
        detector.score_max_ = payload["score_max"]
        logger.info(f"IsolationForest detector loaded successfully from {file_path}")
        return detector


def run_isolation_forest_pipeline(
    input_csv_path: str = "ml_input/project_features.csv",
    output_csv_path: str = "ml_outputs/isolation_forest_results.csv",
    model_save_path: str = "analytics/ml_engine/train/model_registry/isolation_forest.joblib",
    contamination: float = 0.05
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Execute complete end-to-end Isolation Forest training and inference pipeline."""
    logger.info(f"Loading input dataset from {input_csv_path}...")
    df = pd.read_csv(input_csv_path)
    total_records = len(df)
    logger.info(f"Loaded {total_records} records.")

    detector = IsolationForestDetector(contamination=contamination)
    detector.fit(df)
    detector.save(model_save_path)

    results_df = detector.predict(df)

    # Attach helpful context fields for auditing
    context_cols = [
        "mp_name", "state", "constituency", "category",
        "recommended_amount", "total_expenditure", "expenditure_ratio",
        "cost_deviation_from_peer", "days_since_recommendation"
    ]
    for col in context_cols:
        if col in df.columns:
            if col == "category":
                results_df[col] = df[col].fillna("Normal/Others")
            else:
                results_df[col] = df[col]

    # Sort results by anomaly_rank ascending (rank 1 at top)
    results_df = results_df.sort_values("anomaly_rank", ascending=True).reset_index(drop=True)

    os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)
    results_df.to_csv(output_csv_path, index=False)
    logger.info(f"Results successfully written to {output_csv_path}")

    anomaly_count = int(results_df["is_anomaly"].sum())
    metrics = {
        "total_records": total_records,
        "anomaly_count": anomaly_count,
        "anomaly_percentage": round((anomaly_count / total_records) * 100, 2),
        "score_min": float(results_df["anomaly_score"].min()),
        "score_max": float(results_df["anomaly_score"].max()),
        "score_median": float(results_df["anomaly_score"].median()),
        "score_95th": float(results_df["anomaly_score"].quantile(0.95))
    }
    logger.info(f"Pipeline summary metrics: {metrics}")
    return results_df, metrics


if __name__ == "__main__":
    run_isolation_forest_pipeline()
