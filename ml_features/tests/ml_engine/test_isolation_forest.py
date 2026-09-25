"""Unit and synthetic test suite for Isolation Forest Anomaly Detection Model.
"""

import os
import tempfile
import pytest
import numpy as np
import pandas as pd

from analytics.ml_engine.isolation_forest_model import (
    IsolationForestDetector,
    DEFAULT_IF_FEATURES,
    run_isolation_forest_pipeline
)


@pytest.fixture
def sample_normal_data():
    """Generate a clean synthetic sample of normal project features."""
    np.random.seed(42)
    n = 200
    df = pd.DataFrame({
        "project_id": [f"proj_{i}" for i in range(n)],
        "recommended_amount": np.random.normal(500000, 50000, n),
        "total_expenditure": np.random.normal(480000, 40000, n),
        "expenditure_ratio": np.random.normal(0.95, 0.05, n),
        "cost_deviation_from_peer": np.random.normal(0, 10, n),
        "payment_count": np.random.randint(1, 5, n),
        "pending_payment_count": np.zeros(n),
        "days_since_recommendation": np.random.normal(200, 30, n),
        "description_similarity_score": np.random.normal(0.8, 0.05, n)
    })
    return df


@pytest.fixture
def synthetic_data_with_outliers(sample_normal_data):
    """Synthetic dataset with 5 planted extreme anomalies."""
    df = sample_normal_data.copy()
    
    outliers = [
        # Extreme cost inflation (100x cost, +5000% peer deviation)
        {
            "project_id": "outlier_extreme_cost",
            "recommended_amount": 50000000.0,
            "total_expenditure": 49000000.0,
            "expenditure_ratio": 0.98,
            "cost_deviation_from_peer": 5000.0,
            "payment_count": 5,
            "pending_payment_count": 0,
            "days_since_recommendation": 250.0,
            "description_similarity_score": 0.82
        },
        # Extreme overspend ratio (expenditure 50x sanctioned amount)
        {
            "project_id": "outlier_extreme_overspend",
            "recommended_amount": 100000.0,
            "total_expenditure": 5000000.0,
            "expenditure_ratio": 50.0,
            "cost_deviation_from_peer": -80.0,
            "payment_count": 25,
            "pending_payment_count": 2,
            "days_since_recommendation": 300.0,
            "description_similarity_score": 0.75
        },
        # Abandoned zombie project (1500 days elapsed, 0 spend, 10 pending payments)
        {
            "project_id": "outlier_abandoned_zombie",
            "recommended_amount": 2500000.0,
            "total_expenditure": 0.0,
            "expenditure_ratio": 0.0,
            "cost_deviation_from_peer": 200.0,
            "payment_count": 0,
            "pending_payment_count": 10,
            "days_since_recommendation": 1500.0,
            "description_similarity_score": 0.1
        },
        # High-frequency transaction churning
        {
            "project_id": "outlier_payment_churn",
            "recommended_amount": 600000.0,
            "total_expenditure": 600000.0,
            "expenditure_ratio": 1.0,
            "cost_deviation_from_peer": 10.0,
            "payment_count": 80,
            "pending_payment_count": 15,
            "days_since_recommendation": 120.0,
            "description_similarity_score": 0.85
        },
        # Description novelty anomaly with exorbitant peer deviation
        {
            "project_id": "outlier_novelty_deviation",
            "recommended_amount": 35000000.0,
            "total_expenditure": 34000000.0,
            "expenditure_ratio": 0.97,
            "cost_deviation_from_peer": 8500.0,
            "payment_count": 12,
            "pending_payment_count": 0,
            "days_since_recommendation": 450.0,
            "description_similarity_score": 0.01
        }
    ]
    outlier_df = pd.DataFrame(outliers)
    full_synthetic = pd.concat([df, outlier_df], ignore_index=True)
    return full_synthetic


def test_initialization():
    """Test model defaults and parameter setting."""
    detector = IsolationForestDetector(contamination=0.08, n_estimators=100)
    assert detector.contamination == 0.08
    assert detector.n_estimators == 100
    assert detector.features == DEFAULT_IF_FEATURES
    assert not detector.is_fitted


def test_missing_required_column(sample_normal_data):
    """Test ValueError raised when required feature is missing."""
    df_incomplete = sample_normal_data.drop(columns=["expenditure_ratio"])
    detector = IsolationForestDetector()
    with pytest.raises(ValueError, match="Missing required feature columns"):
        detector.fit(df_incomplete)


def test_fit_and_predict_shapes(sample_normal_data):
    """Test that output DataFrame contains expected columns and valid values."""
    detector = IsolationForestDetector(contamination=0.05, n_estimators=50, random_state=42)
    detector.fit(sample_normal_data)
    results = detector.predict(sample_normal_data)

    assert len(results) == len(sample_normal_data)
    assert set(["project_id", "anomaly_score", "anomaly_label", "is_anomaly", "anomaly_rank", "top_anomaly_drivers"]).issubset(
        results.columns
    )
    assert results["anomaly_score"].between(0.0, 1.0).all()
    assert set(results["anomaly_label"].unique()).issubset({-1, 1})
    assert set(results["is_anomaly"].unique()).issubset({0, 1})
    assert results["anomaly_rank"].min() == 1


def test_missing_values_and_infinities():
    """Test robust imputation on data containing NaNs and infinite values."""
    np.random.seed(42)
    n = 100
    df = pd.DataFrame({
        "project_id": [f"proj_{i}" for i in range(n)],
        "recommended_amount": [np.nan if i % 10 == 0 else 500000 for i in range(n)],
        "total_expenditure": [np.inf if i == 5 else 480000 for i in range(n)],
        "expenditure_ratio": [np.nan if i == 7 else 0.95 for i in range(n)],
        "cost_deviation_from_peer": np.random.normal(0, 10, n),
        "payment_count": np.random.randint(1, 5, n),
        "pending_payment_count": np.zeros(n),
        "days_since_recommendation": np.random.normal(200, 30, n),
        "description_similarity_score": [np.nan if i % 15 == 0 else 0.85 for i in range(n)]
    })

    detector = IsolationForestDetector(n_estimators=50, random_state=42)
    detector.fit(df)
    results = detector.predict(df)

    assert not results["anomaly_score"].isna().any()
    assert not results["is_anomaly"].isna().any()


def test_synthetic_planted_outliers(synthetic_data_with_outliers):
    """Test that planted extreme outliers are correctly flagged and top-ranked."""
    planted_ids = [
        "outlier_extreme_cost",
        "outlier_extreme_overspend",
        "outlier_abandoned_zombie",
        "outlier_payment_churn",
        "outlier_novelty_deviation"
    ]
    # Set contamination to ~5/205 approx 0.05
    detector = IsolationForestDetector(contamination=0.05, n_estimators=150, random_state=42)
    detector.fit(synthetic_data_with_outliers)
    results = detector.predict(synthetic_data_with_outliers)

    outlier_results = results[results["project_id"].isin(planted_ids)]

    # All planted extreme outliers should be flagged as anomalies
    assert (outlier_results["is_anomaly"] == 1).all()

    # Verify that all planted outliers are ranked within the top 10%
    top_ranks = outlier_results["anomaly_rank"].tolist()
    max_acceptable_rank = int(0.10 * len(synthetic_data_with_outliers))
    for rank in top_ranks:
        assert rank <= max_acceptable_rank, f"Outlier rank {rank} exceeds threshold {max_acceptable_rank}"


def test_model_persistence(sample_normal_data):
    """Test save and load functionality preserves model state and produces identical scores."""
    detector = IsolationForestDetector(n_estimators=50, random_state=42)
    detector.fit(sample_normal_data)
    preds_before = detector.predict(sample_normal_data)

    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        detector.save(tmp_path)
        loaded_detector = IsolationForestDetector.load(tmp_path)
        preds_after = loaded_detector.predict(sample_normal_data)

        pd.testing.assert_series_equal(preds_before["anomaly_score"], preds_after["anomaly_score"])
        pd.testing.assert_series_equal(preds_before["anomaly_label"], preds_after["anomaly_label"])
        pd.testing.assert_series_equal(preds_before["is_anomaly"], preds_after["is_anomaly"])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
