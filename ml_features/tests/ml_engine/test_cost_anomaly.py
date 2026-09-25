"""Unit and synthetic test suite for Cost Anomaly Detection Model.
"""

import os
import tempfile
import pytest
import numpy as np
import pandas as pd

from analytics.ml_engine.cost_anomaly_model import (
    CostAnomalyDetector,
    DEFAULT_COST_FEATURES
)


@pytest.fixture
def normal_cost_data():
    """Generate synthetic normal project financial data."""
    np.random.seed(42)
    n = 150
    median_costs = np.full(n, 500000.0)
    rec_amounts = np.random.normal(500000.0, 40000.0, n)
    deviations = ((rec_amounts - median_costs) / median_costs) * 100.0
    tot_exps = rec_amounts * np.random.uniform(0.7, 0.98, n)
    exp_ratios = tot_exps / rec_amounts

    return pd.DataFrame({
        "project_id": [f"norm_proj_{i}" for i in range(n)],
        "recommended_amount": rec_amounts,
        "total_expenditure": tot_exps,
        "expenditure_ratio": exp_ratios,
        "peer_median_cost": median_costs,
        "peer_mean_cost": median_costs,
        "peer_std_cost": np.full(n, 50000.0),
        "cost_deviation_from_peer": deviations,
        "description_similarity_score": np.random.uniform(0.6, 0.8, n)
    })


@pytest.fixture
def synthetic_cost_with_planted_outliers(normal_cost_data):
    """Synthetic dataset with planted specific cost anomaly cases."""
    df = normal_cost_data.copy()

    outliers = [
        # 1. Severe expenditure overrun (expenditure is 15x sanctioned allocation)
        {
            "project_id": "outlier_severe_overrun",
            "recommended_amount": 200000.0,
            "total_expenditure": 3000000.0,
            "expenditure_ratio": 15.0,
            "peer_median_cost": 250000.0,
            "peer_mean_cost": 250000.0,
            "peer_std_cost": 30000.0,
            "cost_deviation_from_peer": -20.0,
            "description_similarity_score": 0.75
        },
        # 2. Extreme peer cost inflation (+3000% peer deviation, Rs 2 crore vs Rs 5 lakh)
        {
            "project_id": "outlier_extreme_peer_inflation",
            "recommended_amount": 20000000.0,
            "total_expenditure": 0.0,
            "expenditure_ratio": 0.0,
            "peer_median_cost": 500000.0,
            "peer_mean_cost": 500000.0,
            "peer_std_cost": 60000.0,
            "cost_deviation_from_peer": 3900.0,
            "description_similarity_score": 0.70
        },
        # 3. Boilerplate cost inflation (high similarity + substantial peer deviation)
        {
            "project_id": "outlier_boilerplate_inflation",
            "recommended_amount": 2500000.0,
            "total_expenditure": 0.0,
            "expenditure_ratio": 0.0,
            "peer_median_cost": 500000.0,
            "peer_mean_cost": 500000.0,
            "peer_std_cost": 50000.0,
            "cost_deviation_from_peer": 400.0,
            "description_similarity_score": 0.95
        },
        # 4. Implausible undercost (Rs 5,000 for work with peer median Rs 500,000)
        {
            "project_id": "outlier_implausible_undercost",
            "recommended_amount": 5000.0,
            "total_expenditure": 0.0,
            "expenditure_ratio": 0.0,
            "peer_median_cost": 500000.0,
            "peer_mean_cost": 500000.0,
            "peer_std_cost": 50000.0,
            "cost_deviation_from_peer": -99.0,
            "description_similarity_score": 0.75
        }
    ]
    outlier_df = pd.DataFrame(outliers)
    return pd.concat([df, outlier_df], ignore_index=True)


def test_initialization():
    """Test default initialization."""
    detector = CostAnomalyDetector(anomaly_threshold=0.6)
    assert detector.anomaly_threshold == 0.6
    assert detector.features == DEFAULT_COST_FEATURES
    assert not detector.is_fitted


def test_missing_column_error(normal_cost_data):
    """Test error when required feature is absent."""
    df_missing = normal_cost_data.drop(columns=["cost_deviation_from_peer"])
    detector = CostAnomalyDetector()
    with pytest.raises(ValueError, match="Missing required cost features"):
        detector.fit(df_missing)


def test_fit_and_predict_validity(normal_cost_data):
    """Test that predictions satisfy schema and value constraints."""
    detector = CostAnomalyDetector()
    detector.fit(normal_cost_data)
    results = detector.predict(normal_cost_data)

    expected_cols = [
        "project_id", "cost_anomaly_score", "is_cost_anomaly",
        "cost_anomaly_type", "cost_z_score", "cost_anomaly_rank"
    ]
    for col in expected_cols:
        assert col in results.columns

    assert results["cost_anomaly_score"].between(0.0, 1.0).all()
    assert set(results["is_cost_anomaly"].unique()).issubset({0, 1})
    assert results["cost_anomaly_rank"].min() == 1


def test_missing_and_inf_handling():
    """Test that NaNs and Infs in financial features are handled robustly."""
    df = pd.DataFrame({
        "project_id": [f"proj_{i}" for i in range(50)],
        "recommended_amount": [np.nan if i % 5 == 0 else 500000.0 for i in range(50)],
        "total_expenditure": [np.inf if i == 2 else 450000.0 for i in range(50)],
        "expenditure_ratio": [np.nan if i == 4 else 0.9 for i in range(50)],
        "peer_median_cost": np.full(50, 500000.0),
        "cost_deviation_from_peer": np.random.normal(0, 10, 50),
        "description_similarity_score": np.full(50, 0.8)
    })
    detector = CostAnomalyDetector()
    detector.fit(df)
    results = detector.predict(df)

    assert not results["cost_anomaly_score"].isna().any()
    assert not results["is_cost_anomaly"].isna().any()


def test_planted_cost_anomalies(synthetic_cost_with_planted_outliers):
    """Test that planted extreme cost anomalies are detected and categorized."""
    detector = CostAnomalyDetector(anomaly_threshold=0.5)
    detector.fit(synthetic_cost_with_planted_outliers)
    results = detector.predict(synthetic_cost_with_planted_outliers)

    # 1. Overrun
    overrun_row = results[results["project_id"] == "outlier_severe_overrun"].iloc[0]
    assert overrun_row["is_cost_anomaly"] == 1
    assert "SEVERE_EXPENDITURE_OVERRUN" in overrun_row["cost_anomaly_type"]
    assert overrun_row["cost_anomaly_score"] >= 0.85

    # 2. Extreme peer inflation
    inflation_row = results[results["project_id"] == "outlier_extreme_peer_inflation"].iloc[0]
    assert inflation_row["is_cost_anomaly"] == 1
    assert "EXTREME_PEER_INFLATION" in inflation_row["cost_anomaly_type"]
    assert inflation_row["cost_anomaly_score"] >= 0.70

    # 3. Boilerplate inflation
    bp_row = results[results["project_id"] == "outlier_boilerplate_inflation"].iloc[0]
    assert "BOILERPLATE_COST_INFLATION" in bp_row["cost_anomaly_type"]

    # 4. Implausible undercost
    undercost_row = results[results["project_id"] == "outlier_implausible_undercost"].iloc[0]
    assert "IMPLAUSIBLE_UNDERCOST" in undercost_row["cost_anomaly_type"]


def test_persistence(normal_cost_data):
    """Test save and load reproducibility."""
    detector = CostAnomalyDetector()
    detector.fit(normal_cost_data)
    preds1 = detector.predict(normal_cost_data)

    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        detector.save(tmp_path)
        loaded = CostAnomalyDetector.load(tmp_path)
        preds2 = loaded.predict(normal_cost_data)

        pd.testing.assert_series_equal(preds1["cost_anomaly_score"], preds2["cost_anomaly_score"])
        pd.testing.assert_series_equal(preds1["is_cost_anomaly"], preds2["is_cost_anomaly"])
        pd.testing.assert_series_equal(preds1["cost_anomaly_type"], preds2["cost_anomaly_type"])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
