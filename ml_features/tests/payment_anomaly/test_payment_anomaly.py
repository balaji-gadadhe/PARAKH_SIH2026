"""Unit and synthetic test suite for Payment Anomaly Detection Feature.

Tests cover:
1. Initialization
2. Required-column validation / graceful handling
3. Normal payment patterns
4. Clearly abnormal / planted payment patterns
5. Missing values (NaN) handling
6. Infinite values (Inf) handling
7. Zero values / division-by-zero safety
8. Output schema compliance
9. Score range [0, 1]
10. Model persistence (save / load)
"""

import os
import tempfile
import pytest
import numpy as np
import pandas as pd

from analytics.payment_anomaly.round_figure_analysis import (
    calculate_single_amount_roundness,
    analyze_round_figure_payments
)
from analytics.payment_anomaly.frequency_analysis import analyze_payment_frequency
from analytics.payment_anomaly.unusual_payments import analyze_unusual_payments
from analytics.payment_anomaly.payment_anomaly_detector import (
    PaymentAnomalyDetector,
    run_payment_anomaly_pipeline
)


@pytest.fixture
def normal_payment_dataset():
    """Synthetic dataset of legitimate normal payment patterns."""
    np.random.seed(42)
    n = 100
    rec_amounts = np.random.uniform(300000.0, 1500000.0, n)
    # Legitimate non-round expenditures (with BoQ odd rupees)
    total_exps = rec_amounts * np.random.uniform(0.70, 0.98, n) + np.random.uniform(113.0, 897.0, n)
    counts = np.random.choice([1, 2, 3], n)
    avg_pmts = total_exps / counts
    max_pmts = avg_pmts * 1.1

    return pd.DataFrame({
        "project_id": [f"norm_proj_{i}" for i in range(n)],
        "recommended_amount": rec_amounts,
        "total_expenditure": total_exps,
        "payment_count": counts,
        "average_payment": avg_pmts,
        "maximum_payment": max_pmts,
        "payment_frequency": np.random.uniform(0.005, 0.05, n),
        "pending_payment_count": np.zeros(n, dtype=int),
        "peer_median_cost": rec_amounts * 0.95
    })


@pytest.fixture
def planted_abnormal_dataset(normal_payment_dataset):
    """Dataset with clearly planted, distinct payment anomaly patterns."""
    df = normal_payment_dataset.copy()

    planted_cases = [
        # Case 1: Extreme Round-figure extraction (exactly ₹5,00,000 / ₹10,00,000)
        {
            "project_id": "planted_round_figure",
            "recommended_amount": 1000000.0,
            "total_expenditure": 1000000.0,
            "payment_count": 2,
            "average_payment": 500000.0,
            "maximum_payment": 500000.0,
            "payment_frequency": 0.02,
            "pending_payment_count": 0,
            "peer_median_cost": 1000000.0
        },
        # Case 2: Rapid payment burst (frequency 4.5 payments per day)
        {
            "project_id": "planted_rapid_burst",
            "recommended_amount": 500000.0,
            "total_expenditure": 480000.0,
            "payment_count": 5,
            "average_payment": 96000.0,
            "maximum_payment": 150000.0,
            "payment_frequency": 4.5,
            "pending_payment_count": 0,
            "peer_median_cost": 500000.0
        },
        # Case 3: Transaction structuring / churn (75 payments on a single project)
        {
            "project_id": "planted_transaction_churn",
            "recommended_amount": 800000.0,
            "total_expenditure": 780000.0,
            "payment_count": 75,
            "average_payment": 10400.0,
            "maximum_payment": 15000.0,
            "payment_frequency": 0.10,
            "pending_payment_count": 0,
            "peer_median_cost": 800000.0
        },
        # Case 4: Severe budget overrun (₹7.5 Crore spent on ₹5 Lakh allocation - 150x budget!)
        {
            "project_id": "planted_severe_overrun",
            "recommended_amount": 500000.0,
            "total_expenditure": 75000000.0,
            "payment_count": 10,
            "average_payment": 7500000.0,
            "maximum_payment": 75000000.0,
            "payment_frequency": 0.05,
            "pending_payment_count": 0,
            "peer_median_cost": 500000.0
        },
        # Case 5: Massive single payment concentration (₹3.5 Crore single check)
        {
            "project_id": "planted_massive_single_payment",
            "recommended_amount": 40000000.0,
            "total_expenditure": 35000000.0,
            "payment_count": 1,
            "average_payment": 35000000.0,
            "maximum_payment": 35000000.0,
            "payment_frequency": 0.01,
            "pending_payment_count": 0,
            "peer_median_cost": 5000000.0
        },
        # Case 6: Pending dispute / friction (5 pending transactions)
        {
            "project_id": "planted_pending_friction",
            "recommended_amount": 600000.0,
            "total_expenditure": 300000.0,
            "payment_count": 2,
            "average_payment": 150000.0,
            "maximum_payment": 200000.0,
            "payment_frequency": 0.02,
            "pending_payment_count": 5,
            "peer_median_cost": 600000.0
        }
    ]
    planted_df = pd.DataFrame(planted_cases)
    return pd.concat([df, planted_df], ignore_index=True)


# 1. Initialization Test
def test_initialization():
    detector = PaymentAnomalyDetector(anomaly_threshold=0.55, contamination=0.04)
    assert detector.anomaly_threshold == 0.55
    assert detector.contamination == 0.04
    assert not detector.is_fitted


# 2. Required Column Validation
def test_missing_column_graceful_handling():
    # DataFrame missing some payment columns should not crash but impute safely
    df = pd.DataFrame({
        "project_id": ["proj_minimal_1", "proj_minimal_2"],
        "total_expenditure": [150000.0, 300000.0]
    })
    detector = PaymentAnomalyDetector()
    detector.fit(df)
    results = detector.predict(df)
    assert len(results) == 2
    assert "payment_anomaly_score" in results.columns
    assert not results["payment_anomaly_score"].isna().any()


# 3. Normal Payment Pattern Test
def test_normal_payment_patterns(normal_payment_dataset):
    detector = PaymentAnomalyDetector(anomaly_threshold=0.50)
    detector.fit(normal_payment_dataset)
    results = detector.predict(normal_payment_dataset)

    # Normal projects should predominantly have low scores and normal flags
    assert (results["is_payment_anomaly"] == 0).sum() >= len(normal_payment_dataset) * 0.90
    assert results["payment_anomaly_score"].median() < 0.30


# 4. Clearly Abnormal / Planted Payment Patterns Test
def test_planted_abnormal_patterns(planted_abnormal_dataset):
    detector = PaymentAnomalyDetector(anomaly_threshold=0.50)
    detector.fit(planted_abnormal_dataset)
    results = detector.predict(planted_abnormal_dataset)

    # Check planted case 1: Round-figure extraction
    rf = results[results["project_id"] == "planted_round_figure"].iloc[0]
    assert rf["round_payment_indicator"] >= 0.70
    assert "ROUND_FIGURE_DISBURSEMENT" in rf["payment_anomaly_type"]

    # Check planted case 2: Rapid burst
    rb = results[results["project_id"] == "planted_rapid_burst"].iloc[0]
    assert rb["payment_frequency_indicator"] >= 0.70
    assert "RAPID_PAYMENT_BURST" in rb["payment_anomaly_type"]

    # Check planted case 3: Transaction structuring / churn
    tc = results[results["project_id"] == "planted_transaction_churn"].iloc[0]
    assert tc["payment_count"] == 75
    assert "TRANSACTION_CHURN_STRUCTURING" in tc["payment_anomaly_type"]
    assert tc["is_payment_anomaly"] == 1

    # Check planted case 4: Severe budget overrun
    so = results[results["project_id"] == "planted_severe_overrun"].iloc[0]
    assert so["budget_payment_ratio"] > 50.0
    assert "SEVERE_BUDGET_OVERRUN" in so["payment_anomaly_type"]
    assert so["is_payment_anomaly"] == 1
    assert so["payment_anomaly_score"] >= 0.90

    # Check planted case 5: Massive single payment
    ms = results[results["project_id"] == "planted_massive_single_payment"].iloc[0]
    assert "LARGE_SINGLE_PAYMENT" in ms["payment_anomaly_type"]
    assert ms["max_payment_amount"] == 35000000.0

    # Check planted case 6: Pending dispute
    pf = results[results["project_id"] == "planted_pending_friction"].iloc[0]
    assert "PENDING_DISPUTE_RISK" in pf["payment_anomaly_type"]


# 5. Missing Values (NaN) Test
def test_nan_handling():
    df = pd.DataFrame({
        "project_id": [f"nan_proj_{i}" for i in range(20)],
        "recommended_amount": [np.nan if i % 2 == 0 else 500000.0 for i in range(20)],
        "total_expenditure": [np.nan if i % 3 == 0 else 450000.0 for i in range(20)],
        "payment_count": [np.nan if i % 4 == 0 else 2 for i in range(20)],
        "average_payment": [np.nan for _ in range(20)],
        "maximum_payment": [np.nan for _ in range(20)],
        "payment_frequency": [np.nan if i % 5 == 0 else 0.05 for i in range(20)],
        "pending_payment_count": [np.nan for _ in range(20)],
        "peer_median_cost": [np.nan if i % 2 == 0 else 500000.0 for i in range(20)]
    })
    detector = PaymentAnomalyDetector()
    detector.fit(df)
    results = detector.predict(df)

    assert not results["payment_anomaly_score"].isna().any()
    assert not results["is_payment_anomaly"].isna().any()
    assert not results["round_payment_indicator"].isna().any()
    assert not results["payment_frequency_indicator"].isna().any()


# 6. Infinite Values Test
def test_infinite_values_handling():
    df = pd.DataFrame({
        "project_id": ["inf_1", "inf_2", "inf_3"],
        "recommended_amount": [np.inf, -np.inf, 500000.0],
        "total_expenditure": [np.inf, 400000.0, -np.inf],
        "payment_count": [np.inf, 2, 1],
        "average_payment": [np.inf, 200000.0, 100000.0],
        "maximum_payment": [np.inf, 200000.0, 100000.0],
        "payment_frequency": [np.inf, 0.05, -np.inf],
        "pending_payment_count": [np.inf, 0, 0],
        "peer_median_cost": [np.inf, 500000.0, -np.inf]
    })
    detector = PaymentAnomalyDetector()
    detector.fit(df)
    results = detector.predict(df)

    assert not np.isinf(results["payment_anomaly_score"]).any()
    assert not np.isinf(results["budget_payment_ratio"]).any()
    assert not np.isinf(results["peer_payment_deviation"]).any()


# 7. Zero Values and Division-by-Zero Safety
def test_zero_division_safety():
    df = pd.DataFrame({
        "project_id": ["zero_1", "zero_2"],
        "recommended_amount": [0.0, 0.0],
        "total_expenditure": [0.0, 0.0],
        "payment_count": [0, 0],
        "average_payment": [0.0, 0.0],
        "maximum_payment": [0.0, 0.0],
        "payment_frequency": [0.0, 0.0],
        "pending_payment_count": [0, 0],
        "peer_median_cost": [0.0, 0.0]
    })
    detector = PaymentAnomalyDetector()
    detector.fit(df)
    results = detector.predict(df)

    assert (results["payment_anomaly_score"] == 0.0).all()
    assert (results["budget_payment_ratio"] == 0.0).all()
    assert (results["is_payment_anomaly"] == 0).all()
    assert (results["payment_anomaly_type"] == "NORMAL").all()


# 8. Output Schema Test
def test_output_schema(normal_payment_dataset):
    detector = PaymentAnomalyDetector()
    detector.fit(normal_payment_dataset)
    results = detector.predict(normal_payment_dataset)

    expected_cols = [
        "project_id",
        "payment_anomaly_score",
        "is_payment_anomaly",
        "payment_anomaly_type",
        "payment_count",
        "total_payment_amount",
        "average_payment_amount",
        "max_payment_amount",
        "round_payment_indicator",
        "payment_frequency_indicator",
        "budget_payment_ratio",
        "peer_payment_deviation",
        "payment_anomaly_rank"
    ]
    for col in expected_cols:
        assert col in results.columns, f"Missing required column: {col}"

    assert len(results) == len(normal_payment_dataset)


# 9. Score Range [0, 1] Test
def test_score_bounds(planted_abnormal_dataset):
    detector = PaymentAnomalyDetector()
    detector.fit(planted_abnormal_dataset)
    results = detector.predict(planted_abnormal_dataset)

    assert results["payment_anomaly_score"].min() >= 0.0
    assert results["payment_anomaly_score"].max() <= 1.0
    assert results["round_payment_indicator"].between(0.0, 1.0).all()
    assert results["payment_frequency_indicator"].between(0.0, 1.0).all()


# 10. Model Persistence Test
def test_persistence(normal_payment_dataset):
    detector = PaymentAnomalyDetector()
    detector.fit(normal_payment_dataset)
    preds1 = detector.predict(normal_payment_dataset)

    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        detector.save(tmp_path)
        loaded = PaymentAnomalyDetector.load(tmp_path)
        preds2 = loaded.predict(normal_payment_dataset)

        pd.testing.assert_series_equal(preds1["payment_anomaly_score"], preds2["payment_anomaly_score"])
        pd.testing.assert_series_equal(preds1["is_payment_anomaly"], preds2["is_payment_anomaly"])
        pd.testing.assert_series_equal(preds1["payment_anomaly_type"], preds2["payment_anomaly_type"])
        pd.testing.assert_series_equal(preds1["payment_anomaly_rank"], preds2["payment_anomaly_rank"])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
