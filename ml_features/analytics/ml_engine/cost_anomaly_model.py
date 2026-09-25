"""Cost Anomaly Detection Model for MPLAD-Sentinel DEV B.

This module provides multi-criteria and machine-learning-driven cost anomaly detection
for MPLADS projects. It detects:
1. Peer Cost Inflation: Projects with sanctioned amounts far exceeding category/state peer medians.
2. Budget / Expenditure Overrun: Projects where expenditure exceeds sanctioned recommendations.
3. Boilerplate Cost Inflation: Projects with generic boilerplate descriptions but high peer cost deviations.
4. Implausible Undercosting: Projects sanctioned at suspiciously token/tiny amounts for complex works.
5. Multivariate Cost Outlier Scoring: Unsupervised density scoring over the financial space.

Outputs are written to `ml_outputs/cost_anomaly_results.csv`.
"""

from __future__ import annotations

import os
import logging
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler
from sklearn.impute import SimpleImputer
import joblib

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_COST_FEATURES: List[str] = [
    "recommended_amount",
    "total_expenditure",
    "expenditure_ratio",
    "cost_deviation_from_peer",
    "peer_median_cost"
]


class CostAnomalyDetector:
    """Cost Anomaly Detector combining peer benchmarking, rule heuristics, and density outlier scoring.

    Parameters
    ----------
    features : List[str], optional
        List of financial/cost feature columns.
    anomaly_threshold : float, default=0.5
        Threshold above which a project is classified as an anomaly (is_cost_anomaly=1).
    n_neighbors : int, default=30
        Number of neighbors for LocalOutlierFactor density estimation.
    """

    def __init__(
        self,
        features: Optional[List[str]] = None,
        anomaly_threshold: float = 0.50,
        n_neighbors: int = 30
    ) -> None:
        self.features = features or list(DEFAULT_COST_FEATURES)
        self.anomaly_threshold = anomaly_threshold
        self.n_neighbors = n_neighbors

        self.imputer = SimpleImputer(strategy="median")
        self.scaler = RobustScaler()
        self.density_model = LocalOutlierFactor(
            n_neighbors=self.n_neighbors,
            novelty=True,
            contamination=0.05
        )

        self.is_fitted: bool = False
        self.global_peer_deviation_median_: float = 0.0
        self.global_peer_deviation_iqr_: float = 1.0

    def _classify_typology(
        self,
        cost_deviation: float,
        expenditure_ratio: float,
        total_expenditure: float,
        similarity_score: float,
        z_score: float
    ) -> str:
        """Assign interpretable anomaly categories based on financial indicators."""
        flags: List[str] = []

        # Overrun check
        if expenditure_ratio > 1.05 and total_expenditure > 0:
            if expenditure_ratio > 2.0:
                flags.append("SEVERE_EXPENDITURE_OVERRUN")
            else:
                flags.append("EXPENDITURE_OVERRUN")

        # Peer inflation check
        if cost_deviation >= 500.0 or z_score >= 3.5:
            flags.append("EXTREME_PEER_INFLATION")
        elif cost_deviation >= 200.0 or z_score >= 2.0:
            flags.append("MODERATE_PEER_INFLATION")

        # Boilerplate check
        if similarity_score >= 0.85 and cost_deviation >= 300.0:
            flags.append("BOILERPLATE_COST_INFLATION")

        # Implausible undercost
        if cost_deviation <= -95.0:
            flags.append("IMPLAUSIBLE_UNDERCOST")

        return "|".join(flags) if flags else "NORMAL"

    def fit(self, df: pd.DataFrame) -> CostAnomalyDetector:
        """Fit preprocessing, baseline statistics, and density model."""
        logger.info(f"Fitting CostAnomalyDetector on {len(df)} samples...")

        # Extract features
        missing = [f for f in self.features if f not in df.columns]
        if missing:
            raise ValueError(f"Missing required cost features: {missing}")

        X_raw = df[self.features].copy()
        for f in self.features:
            X_raw[f] = pd.to_numeric(X_raw[f], errors="coerce").replace([np.inf, -np.inf], np.nan)

        X_imputed = self.imputer.fit_transform(X_raw)
        X_scaled = self.scaler.fit_transform(X_imputed)

        # Train LOF on a representative subsample if dataset is large to maintain efficiency
        sample_size = min(len(df), 20000)
        if len(df) > sample_size:
            np.random.seed(42)
            indices = np.random.choice(len(df), size=sample_size, replace=False)
            self.density_model.fit(X_scaled[indices])
        else:
            self.density_model.fit(X_scaled)

        # Record distribution baselines
        devs = X_imputed[:, self.features.index("cost_deviation_from_peer")]
        q25, q50, q75 = np.percentile(devs, [25, 50, 75])
        self.global_peer_deviation_median_ = float(q50)
        self.global_peer_deviation_iqr_ = float(q75 - q25) if (q75 - q25) > 0 else 1.0

        self.is_fitted = True
        logger.info("CostAnomalyDetector fit complete.")
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute cost anomaly scores, typology classifications, and ranks."""
        if not self.is_fitted:
            raise RuntimeError("CostAnomalyDetector must be fitted before predict().")

        # Extract features
        missing = [f for f in self.features if f not in df.columns]
        if missing:
            raise ValueError(f"Missing required cost features: {missing}")

        X_raw = df[self.features].copy()
        for f in self.features:
            X_raw[f] = pd.to_numeric(X_raw[f], errors="coerce").replace([np.inf, -np.inf], np.nan)

        X_imputed = self.imputer.transform(X_raw)
        X_scaled = self.scaler.transform(X_imputed)

        # 1. Density anomaly score from LOF (higher negative decision_function = more anomalous)
        density_scores_raw = -self.density_model.decision_function(X_scaled)
        # Normalize density scores to [0, 1] using min-max on percentiles
        p5, p95 = np.percentile(density_scores_raw, [5, 95])
        p_denom = (p95 - p5) if (p95 - p5) > 1e-6 else 1.0
        norm_density = np.clip((density_scores_raw - p5) / p_denom, 0.0, 1.0)

        # 2. Peer deviation statistical risk (sigmoidal mapping centered at +150% deviation)
        cost_deviations = X_imputed[:, self.features.index("cost_deviation_from_peer")]
        # Sigmoid centered around +150% with slope 0.015
        peer_risk = 1.0 / (1.0 + np.exp(-0.015 * (cost_deviations - 150.0)))

        # 3. Budget overrun risk (penalize total_expenditure > recommended_amount)
        exp_ratios = X_imputed[:, self.features.index("expenditure_ratio")]
        total_exps = X_imputed[:, self.features.index("total_expenditure")]
        overrun_risk = np.zeros_like(exp_ratios)
        has_spend = total_exps > 0
        overrun_risk[has_spend] = np.clip((exp_ratios[has_spend] - 1.0) / 2.0, 0.0, 1.0)

        # 4. Peer Z-Score
        rec_amounts = X_imputed[:, self.features.index("recommended_amount")]
        if "peer_mean_cost" in df.columns and "peer_std_cost" in df.columns:
            peer_means_raw = pd.to_numeric(df["peer_mean_cost"], errors="coerce").to_numpy()
            peer_means = np.where(np.isnan(peer_means_raw), rec_amounts, peer_means_raw)
            peer_stds_raw = pd.to_numeric(df["peer_std_cost"], errors="coerce").to_numpy()
            peer_stds = np.where(np.isnan(peer_stds_raw) | (peer_stds_raw < 1.0), 1.0, peer_stds_raw)
            z_scores = (rec_amounts - peer_means) / peer_stds
        else:
            z_scores = (cost_deviations - self.global_peer_deviation_median_) / self.global_peer_deviation_iqr_
        z_scores = np.nan_to_num(z_scores, nan=0.0, posinf=10.0, neginf=-10.0)

        # Sigmoid on Z-score
        z_risk = 1.0 / (1.0 + np.exp(-1.0 * (z_scores - 2.5)))

        # 5. Composite Cost Anomaly Score
        # Maximum of the specific risk indicators + weighted density score
        heuristic_max = np.maximum(peer_risk, np.maximum(overrun_risk * 1.2, z_risk))
        composite_score = np.clip(0.65 * heuristic_max + 0.35 * norm_density, 0.0, 1.0)

        # Boost projects with severe overspend directly to >= 0.85
        severe_overspend_mask = (exp_ratios > 1.5) & (total_exps > 0)
        composite_score[severe_overspend_mask] = np.maximum(composite_score[severe_overspend_mask], 0.88)

        # Typology classification
        sim_scores = pd.to_numeric(df.get("description_similarity_score", 0.8), errors="coerce").fillna(0.8).values
        typologies = [
            self._classify_typology(
                cost_deviation=float(cost_deviations[i]),
                expenditure_ratio=float(exp_ratios[i]),
                total_expenditure=float(total_exps[i]),
                similarity_score=float(sim_scores[i]),
                z_score=float(z_scores[i])
            )
            for i in range(len(df))
        ]

        is_anomaly = (composite_score >= self.anomaly_threshold).astype(int)

        project_ids = df["project_id"].tolist() if "project_id" in df.columns else [f"proj_{i}" for i in range(len(df))]

        results_df = pd.DataFrame({
            "project_id": project_ids,
            "cost_anomaly_score": np.round(composite_score, 4),
            "is_cost_anomaly": is_anomaly,
            "cost_anomaly_type": typologies,
            "cost_z_score": np.round(z_scores, 2),
            "recommended_amount": rec_amounts,
            "total_expenditure": total_exps,
            "expenditure_ratio": np.round(exp_ratios, 4),
            "cost_deviation_from_peer": np.round(cost_deviations, 2)
        })

        if "peer_median_cost" in df.columns:
            results_df["peer_median_cost"] = df["peer_median_cost"].values

        # Compute rank: rank 1 is highest anomaly score
        results_df["cost_anomaly_rank"] = results_df["cost_anomaly_score"].rank(ascending=False, method="min").astype(int)

        return results_df

    def save(self, file_path: str) -> None:
        """Serialize detector to disk."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        payload = {
            "features": self.features,
            "anomaly_threshold": self.anomaly_threshold,
            "n_neighbors": self.n_neighbors,
            "imputer": self.imputer,
            "scaler": self.scaler,
            "density_model": self.density_model,
            "is_fitted": self.is_fitted,
            "global_peer_deviation_median": self.global_peer_deviation_median_,
            "global_peer_deviation_iqr": self.global_peer_deviation_iqr_
        }
        joblib.dump(payload, file_path)
        logger.info(f"CostAnomalyDetector saved to {file_path}")

    @classmethod
    def load(cls, file_path: str) -> CostAnomalyDetector:
        """Load detector from disk."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        payload = joblib.load(file_path)
        detector = cls(
            features=payload["features"],
            anomaly_threshold=payload["anomaly_threshold"],
            n_neighbors=payload["n_neighbors"]
        )
        detector.imputer = payload["imputer"]
        detector.scaler = payload["scaler"]
        detector.density_model = payload["density_model"]
        detector.is_fitted = payload["is_fitted"]
        detector.global_peer_deviation_median_ = payload["global_peer_deviation_median"]
        detector.global_peer_deviation_iqr_ = payload["global_peer_deviation_iqr"]
        logger.info(f"CostAnomalyDetector loaded from {file_path}")
        return detector


def run_cost_anomaly_pipeline(
    input_csv_path: str = "ml_input/project_features.csv",
    output_csv_path: str = "ml_outputs/cost_anomaly_results.csv",
    model_save_path: str = "analytics/ml_engine/train/model_registry/cost_anomaly_model.joblib",
    anomaly_threshold: float = 0.50
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Execute complete end-to-end Cost Anomaly pipeline."""
    logger.info(f"Loading input dataset from {input_csv_path}...")
    df = pd.read_csv(input_csv_path)
    total_records = len(df)
    logger.info(f"Loaded {total_records} records.")

    detector = CostAnomalyDetector(anomaly_threshold=anomaly_threshold)
    detector.fit(df)
    detector.save(model_save_path)

    results_df = detector.predict(df)

    # Attach helpful context fields
    for col in ["mp_name", "state", "constituency", "category"]:
        if col in df.columns:
            if col == "category":
                results_df[col] = df[col].fillna("Normal/Others")
            else:
                results_df[col] = df[col]

    # Sort results by cost_anomaly_rank ascending (rank 1 at top)
    results_df = results_df.sort_values("cost_anomaly_rank", ascending=True).reset_index(drop=True)

    os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)
    results_df.to_csv(output_csv_path, index=False)
    logger.info(f"Results written to {output_csv_path}")

    anomaly_count = int(results_df["is_cost_anomaly"].sum())
    metrics = {
        "total_records": total_records,
        "cost_anomaly_count": anomaly_count,
        "cost_anomaly_percentage": round((anomaly_count / total_records) * 100, 2),
        "score_min": float(results_df["cost_anomaly_score"].min()),
        "score_max": float(results_df["cost_anomaly_score"].max()),
        "score_median": float(results_df["cost_anomaly_score"].median()),
        "score_90th": float(results_df["cost_anomaly_score"].quantile(0.90))
    }
    logger.info(f"Pipeline summary metrics: {metrics}")
    return results_df, metrics


if __name__ == "__main__":
    run_cost_anomaly_pipeline()
