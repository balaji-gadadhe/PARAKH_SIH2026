"""Payment Anomaly Detector for MPLAD-Sentinel.

Detects unusual, suspicious, or irregular payment patterns across MPLADS projects.
Integrates:
1. Round-figure extraction analysis
2. Payment frequency, velocity, and transaction churn (structuring)
3. Budget overruns and disproportionate single payments
4. Unsupervised multivariate outlier scoring via IsolationForest
5. Deterministic risk scoring and explainable typology classification
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

import sys
from pathlib import Path

# Ensure root directory is in sys.path when executed directly
WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from analytics.payment_anomaly.round_figure_analysis import analyze_round_figure_payments
from analytics.payment_anomaly.frequency_analysis import analyze_payment_frequency
from analytics.payment_anomaly.unusual_payments import analyze_unusual_payments

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_PAYMENT_FEATURES = [
    "total_expenditure",
    "payment_count",
    "pending_payment_count",
    "round_payment_indicator",
    "payment_frequency_indicator",
    "budget_payment_ratio",
    "peer_payment_deviation"
]


class PaymentAnomalyDetector:
    """End-to-end detector for payment anomalies in project/vendor records.

    Parameters
    ----------
    anomaly_threshold : float, default=0.50
        Score cutoff above which is_payment_anomaly is set to 1.
    contamination : float, default=0.03
        Expected proportion of outliers for the underlying IsolationForest model.
    random_state : int, default=42
        Seed for reproducibility.
    """

    def __init__(
        self,
        anomaly_threshold: float = 0.50,
        contamination: float = 0.03,
        random_state: int = 42
    ) -> None:
        self.anomaly_threshold = anomaly_threshold
        self.contamination = contamination
        self.random_state = random_state

        self.imputer = SimpleImputer(strategy="median")
        self.scaler = RobustScaler()
        self.model = IsolationForest(
            contamination=self.contamination,
            n_estimators=150,
            random_state=self.random_state,
            n_jobs=-1
        )

        self.is_fitted: bool = False
        self.score_min_: float = 0.0
        self.score_max_: float = 1.0

    def _extract_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract all payment features and sub-analyzer indicators."""
        data = df.copy()

        # Ensure required base columns exist with defaults
        if "total_expenditure" not in data.columns:
            data["total_expenditure"] = 0.0
        if "recommended_amount" not in data.columns:
            data["recommended_amount"] = 500000.0
        if "payment_count" not in data.columns:
            data["payment_count"] = 0
        if "pending_payment_count" not in data.columns:
            data["pending_payment_count"] = 0
        if "average_payment" not in data.columns:
            data["average_payment"] = 0.0
        if "maximum_payment" not in data.columns:
            data["maximum_payment"] = 0.0
        if "payment_frequency" not in data.columns:
            data["payment_frequency"] = 0.0
        if "peer_median_cost" not in data.columns:
            data["peer_median_cost"] = 500000.0

        # Safe numeric conversions
        for col in [
            "total_expenditure", "recommended_amount", "payment_count",
            "pending_payment_count", "average_payment", "maximum_payment",
            "payment_frequency", "peer_median_cost"
        ]:
            data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0.0)
            data[col] = data[col].replace([np.inf, -np.inf], 0.0)

        # 1. Round figure analysis
        data["round_payment_indicator"] = analyze_round_figure_payments(
            data,
            total_col="total_expenditure",
            avg_col="average_payment",
            max_col="maximum_payment"
        )

        # 2. Frequency analysis
        data["payment_frequency_indicator"] = analyze_payment_frequency(
            data,
            freq_col="payment_frequency",
            count_col="payment_count",
            pending_col="pending_payment_count"
        )

        # 3. Magnitude and overrun analysis
        budget_ratios, peer_devs, magnitude_scores = analyze_unusual_payments(
            data,
            total_col="total_expenditure",
            rec_col="recommended_amount",
            max_col="maximum_payment",
            peer_col="peer_median_cost"
        )
        data["budget_payment_ratio"] = budget_ratios
        data["peer_payment_deviation"] = peer_devs
        data["_magnitude_risk_score"] = magnitude_scores

        return data

    def _classify_payment_typology(
        self,
        b_ratio: float,
        freq_ind: float,
        round_ind: float,
        p_count: int,
        max_pmt: float,
        pending_cnt: int,
        tot_exp: float
    ) -> str:
        """Categorize payment anomaly typology based on forensic indicators."""
        if tot_exp <= 0 and pending_cnt <= 0:
            return "NORMAL"

        types: List[str] = []

        if b_ratio > 2.0 and tot_exp > 0:
            types.append("SEVERE_BUDGET_OVERRUN")
        elif b_ratio > 1.05 and tot_exp > 0:
            types.append("BUDGET_OVERRUN")

        if freq_ind >= 0.65:
            types.append("RAPID_PAYMENT_BURST")

        if round_ind >= 0.65:
            types.append("ROUND_FIGURE_DISBURSEMENT")

        if p_count >= 15:
            types.append("TRANSACTION_CHURN_STRUCTURING")

        if max_pmt >= 5000000.0:  # ₹50 Lakh single payment
            types.append("LARGE_SINGLE_PAYMENT")

        if pending_cnt >= 2:
            types.append("PENDING_DISPUTE_RISK")

        return "|".join(types) if types else "NORMAL"

    def fit(self, df: pd.DataFrame) -> PaymentAnomalyDetector:
        """Fit the payment anomaly detector and underlying IsolationForest model."""
        logger.info(f"Fitting PaymentAnomalyDetector on {len(df)} samples...")
        data = self._extract_derived_features(df)

        X_raw = data[DEFAULT_PAYMENT_FEATURES].values
        X_imputed = self.imputer.fit_transform(X_raw)
        X_scaled = self.scaler.fit_transform(X_imputed)

        self.model.fit(X_scaled)
        self.is_fitted = True

        raw_scores = -self.model.score_samples(X_scaled)
        self.score_min_ = float(np.min(raw_scores))
        self.score_max_ = float(np.max(raw_scores))
        if self.score_max_ <= self.score_min_:
            self.score_max_ = self.score_min_ + 1e-6

        logger.info(f"PaymentAnomalyDetector fit complete. Score range: [{self.score_min_:.4f}, {self.score_max_:.4f}]")
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute payment anomaly scores, typologies, and ranks."""
        if not self.is_fitted:
            raise RuntimeError("PaymentAnomalyDetector must be fitted before predict().")

        data = self._extract_derived_features(df)
        n = len(data)

        X_raw = data[DEFAULT_PAYMENT_FEATURES].values
        X_imputed = self.imputer.transform(X_raw)
        X_scaled = self.scaler.transform(X_imputed)

        # 1. Unsupervised isolation score in [0, 1]
        raw_scores = -self.model.score_samples(X_scaled)
        ml_score = np.clip((raw_scores - self.score_min_) / (self.score_max_ - self.score_min_), 0.0, 1.0)

        # 2. Extract feature arrays
        tot_exps = data["total_expenditure"].values
        b_ratios = data["budget_payment_ratio"].values
        round_inds = data["round_payment_indicator"].values
        freq_inds = data["payment_frequency_indicator"].values
        mag_scores = data["_magnitude_risk_score"].values
        p_counts = data["payment_count"].astype(int).values
        pending_cnts = data["pending_payment_count"].astype(int).values
        max_pmts = data["maximum_payment"].values
        avg_pmts = data["average_payment"].values

        # If average_payment was missing but total_expenditure and payment_count exist:
        avg_pmts = np.where(
            (avg_pmts <= 0) & (tot_exps > 0) & (p_counts > 0),
            tot_exps / np.maximum(p_counts, 1),
            avg_pmts
        )
        max_pmts = np.where((max_pmts <= 0) & (tot_exps > 0), tot_exps, max_pmts)

        # 3. Composite score calculation
        composite_scores = np.zeros(n, dtype=float)
        typologies: List[str] = []

        for i in range(n):
            tot = tot_exps[i]
            pend = pending_cnts[i]

            if tot <= 0 and pend <= 0:
                # No payment activity and no pending friction
                composite_scores[i] = 0.0
                typologies.append("NORMAL")
                continue

            r_ind = round_inds[i]
            f_ind = freq_inds[i]
            m_sc = mag_scores[i]
            ml_sc = ml_score[i]
            br = b_ratios[i]
            cnt = p_counts[i]
            mx = max_pmts[i]

            # Weighted fusion of domain indicators and ML isolation score
            heuristic_peak = max(m_sc, f_ind * 0.9, r_ind * 0.8)
            score = 0.50 * heuristic_peak + 0.35 * ml_sc + 0.15 * max(r_ind, f_ind)

            # Direct overrides for extreme conditions
            if br > 2.0 and tot > 0:
                score = max(score, 0.90)
            elif br > 1.20 and tot > 0:
                score = max(score, 0.70)

            if f_ind >= 0.80 or cnt >= 25:
                score = max(score, 0.85)

            if pend >= 3:
                score = max(score, 0.75)

            composite_scores[i] = np.clip(score, 0.0, 1.0)

            # Classify typology
            typology = self._classify_payment_typology(
                b_ratio=br,
                freq_ind=f_ind,
                round_ind=r_ind,
                p_count=cnt,
                max_pmt=mx,
                pending_cnt=pend,
                tot_exp=tot
            )
            typologies.append(typology)

        is_anomaly = (composite_scores >= self.anomaly_threshold).astype(int)

        project_ids = (
            df["project_id"].tolist()
            if "project_id" in df.columns
            else [f"proj_{i}" for i in range(n)]
        )

        results_df = pd.DataFrame({
            "project_id": project_ids,
            "payment_anomaly_score": np.round(composite_scores, 4),
            "is_payment_anomaly": is_anomaly,
            "payment_anomaly_type": typologies,
            "payment_count": p_counts,
            "total_payment_amount": np.round(tot_exps, 2),
            "average_payment_amount": np.round(avg_pmts, 2),
            "max_payment_amount": np.round(max_pmts, 2),
            "round_payment_indicator": np.round(round_inds, 4),
            "payment_frequency_indicator": np.round(freq_inds, 4),
            "budget_payment_ratio": np.round(b_ratios, 4),
            "peer_payment_deviation": np.round(data["peer_payment_deviation"].values, 2)
        })

        # Attach vendor if available in input
        if "vendor" in df.columns:
            results_df["vendor"] = df["vendor"].fillna("Unknown")
        elif "vendor_name" in df.columns:
            results_df["vendor_name"] = df["vendor_name"].fillna("Unknown")

        # Deterministic ranking: rank 1 is highest anomaly score
        results_df["payment_anomaly_rank"] = (
            results_df["payment_anomaly_score"].rank(ascending=False, method="min").astype(int)
        )

        return results_df

    def save(self, file_path: str) -> None:
        """Serialize detector to disk."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        payload = {
            "anomaly_threshold": self.anomaly_threshold,
            "contamination": self.contamination,
            "random_state": self.random_state,
            "imputer": self.imputer,
            "scaler": self.scaler,
            "model": self.model,
            "is_fitted": self.is_fitted,
            "score_min": self.score_min_,
            "score_max": self.score_max_
        }
        joblib.dump(payload, file_path)
        logger.info(f"PaymentAnomalyDetector saved successfully to {file_path}")

    @classmethod
    def load(cls, file_path: str) -> PaymentAnomalyDetector:
        """Load detector from disk."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Model file not found: {file_path}")
        payload = joblib.load(file_path)
        detector = cls(
            anomaly_threshold=payload["anomaly_threshold"],
            contamination=payload["contamination"],
            random_state=payload["random_state"]
        )
        detector.imputer = payload["imputer"]
        detector.scaler = payload["scaler"]
        detector.model = payload["model"]
        detector.is_fitted = payload["is_fitted"]
        detector.score_min_ = payload["score_min"]
        detector.score_max_ = payload["score_max"]
        logger.info(f"PaymentAnomalyDetector loaded successfully from {file_path}")
        return detector


def run_payment_anomaly_pipeline(
    input_csv_path: str = "ml_input/project_features.csv",
    output_csv_path: str = "ml_outputs/payment_anomaly_results.csv",
    model_save_path: str = "analytics/ml_engine/train/model_registry/payment_anomaly_detector.joblib",
    anomaly_threshold: float = 0.50
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Execute complete end-to-end payment anomaly detection pipeline."""
    logger.info(f"Loading dataset from {input_csv_path}...")
    df = pd.read_csv(input_csv_path)
    total_records = len(df)
    logger.info(f"Loaded {total_records} records.")

    detector = PaymentAnomalyDetector(anomaly_threshold=anomaly_threshold)
    detector.fit(df)
    detector.save(model_save_path)

    results_df = detector.predict(df)

    # Sort results by payment_anomaly_rank ascending (rank 1 at top)
    results_df = results_df.sort_values("payment_anomaly_rank", ascending=True).reset_index(drop=True)

    os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)
    results_df.to_csv(output_csv_path, index=False)
    logger.info(f"Results successfully written to {output_csv_path}")

    anomaly_count = int(results_df["is_payment_anomaly"].sum())
    metrics = {
        "total_records": total_records,
        "payment_anomaly_count": anomaly_count,
        "payment_anomaly_percentage": round((anomaly_count / total_records) * 100, 2),
        "score_min": float(results_df["payment_anomaly_score"].min()),
        "score_max": float(results_df["payment_anomaly_score"].max()),
        "score_median": float(results_df["payment_anomaly_score"].median()),
        "score_mean": float(results_df["payment_anomaly_score"].mean()),
        "typology_counts": results_df["payment_anomaly_type"].value_counts().to_dict()
    }
    logger.info(f"Pipeline summary metrics: {metrics}")
    return results_df, metrics


if __name__ == "__main__":
    run_payment_anomaly_pipeline()
