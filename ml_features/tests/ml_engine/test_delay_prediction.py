"""Unit and synthetic test suite for XGBoost Delay Prediction Model.
"""

import os
import tempfile
import pytest
import numpy as np
import pandas as pd

from analytics.ml_engine.xgboost_delay_model import (
    XGBoostDelayPredictor,
    CORE_FEATURES
)


@pytest.fixture
def synthetic_training_data():
    """Generate synthetic completed and ongoing project dataset."""
    np.random.seed(42)
    n_completed = 80
    n_ongoing = 120

    # Completed projects
    comp_amounts = np.random.uniform(200000.0, 3000000.0, n_completed)
    # Expected durations roughly 180 - 600 days based on scale
    comp_durations = 150.0 + (comp_amounts / 10000.0) + np.random.normal(0, 30, n_completed)
    comp_df = pd.DataFrame({
        "project_id": [f"comp_proj_{i}" for i in range(n_completed)],
        "is_completed": 1,
        "recommendation_to_completion_days": -comp_durations,  # negative convention
        "days_since_recommendation": comp_durations + 50.0,
        "recommended_amount": comp_amounts,
        "category": np.random.choice(["Normal/Others", "Repair and Renovation", "Trust and Society"], n_completed),
        "payment_count": np.random.randint(1, 10, n_completed),
        "pending_payment_count": np.zeros(n_completed),
        "has_images": np.random.choice([True, False], n_completed),
        "mp_name": [f"MP_{i % 10}" for i in range(n_completed)]
    })

    # Ongoing projects
    ong_amounts = np.random.uniform(200000.0, 3000000.0, n_ongoing)
    ong_elapsed = np.random.uniform(10.0, 800.0, n_ongoing)
    ong_df = pd.DataFrame({
        "project_id": [f"ong_proj_{i}" for i in range(n_ongoing)],
        "is_completed": 0,
        "recommendation_to_completion_days": np.nan,
        "days_since_recommendation": ong_elapsed,
        "recommended_amount": ong_amounts,
        "category": np.random.choice(["Normal/Others", "Repair and Renovation", "Trust and Society"], n_ongoing),
        "payment_count": np.random.randint(0, 5, n_ongoing),
        "pending_payment_count": np.random.choice([0, 1, 3], n_ongoing),
        "has_images": np.random.choice([True, False], n_ongoing),
        "mp_name": [f"MP_{i % 10}" for i in range(n_ongoing)]
    })

    full_df = pd.concat([comp_df, ong_df], ignore_index=True)

    mp_df = pd.DataFrame({
        "mp_name": [f"MP_{i}" for i in range(10)],
        "completion_rate_pct": np.random.uniform(30.0, 90.0, 10),
        "utilization_pct": np.random.uniform(60.0, 95.0, 10),
        "completion_gap": np.random.uniform(-10.0, 20.0, 10)
    })

    return full_df, mp_df


def test_initialization():
    """Test model parameter initialization."""
    model = XGBoostDelayPredictor(n_estimators=60, max_depth=3, learning_rate=0.1)
    assert model.n_estimators == 60
    assert model.max_depth == 3
    assert model.learning_rate == 0.1
    assert not model.is_fitted


def test_fit_and_predict_schema(synthetic_training_data):
    """Test fit and predict returns expected schema and valid values."""
    df, mp_df = synthetic_training_data
    predictor = XGBoostDelayPredictor(n_estimators=30, max_depth=3)
    predictor.fit(df, mp_df=mp_df)

    results = predictor.predict(df, mp_df=mp_df)

    expected_cols = [
        "project_id", "days_since_recommendation", "predicted_completion_days",
        "delay_risk_score", "delay_risk_level", "is_delayed_predicted", "delay_risk_rank"
    ]
    for col in expected_cols:
        assert col in results.columns

    assert results["delay_risk_score"].between(0.0, 1.0).all()
    assert set(results["delay_risk_level"].unique()).issubset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
    assert set(results["is_delayed_predicted"].unique()).issubset({0, 1})
    assert (results["predicted_completion_days"] >= 90.0).all()
    assert results["delay_risk_rank"].min() == 1


def test_missing_values_and_no_mp_data(synthetic_training_data):
    """Test model runs robustly when MP auxiliary data is omitted and NaNs exist."""
    df, _ = synthetic_training_data
    df_copy = df.copy()
    df_copy.loc[0:10, "recommended_amount"] = np.nan
    df_copy.loc[5:15, "payment_count"] = np.nan

    predictor = XGBoostDelayPredictor(n_estimators=20, max_depth=2)
    predictor.fit(df_copy, mp_df=None)
    results = predictor.predict(df_copy, mp_df=None)

    assert not results["delay_risk_score"].isna().any()
    assert not results["predicted_completion_days"].isna().any()


def test_planted_delay_scenarios(synthetic_training_data):
    """Test delay predictions on planted extreme scenarios."""
    df, mp_df = synthetic_training_data
    predictor = XGBoostDelayPredictor(n_estimators=50, max_depth=3)
    predictor.fit(df, mp_df=mp_df)

    test_cases = pd.DataFrame([
        # 1. Fresh project (15 days elapsed)
        {
            "project_id": "test_fresh",
            "is_completed": 0,
            "days_since_recommendation": 15.0,
            "recommended_amount": 500000.0,
            "category": "Normal/Others",
            "payment_count": 0,
            "pending_payment_count": 0,
            "has_images": False,
            "mp_name": "MP_0"
        },
        # 2. Critical overdue project (1100 days elapsed, 5 pending payments)
        {
            "project_id": "test_critical_overdue",
            "is_completed": 0,
            "days_since_recommendation": 1100.0,
            "recommended_amount": 500000.0,
            "category": "Normal/Others",
            "payment_count": 1,
            "pending_payment_count": 5,
            "has_images": False,
            "mp_name": "MP_0"
        }
    ])

    results = predictor.predict(test_cases, mp_df=mp_df)
    fresh_res = results[results["project_id"] == "test_fresh"].iloc[0]
    overdue_res = results[results["project_id"] == "test_critical_overdue"].iloc[0]

    # Fresh project should have low delay risk
    assert fresh_res["delay_risk_level"] == "LOW"
    assert fresh_res["delay_risk_score"] < 0.35
    assert fresh_res["is_delayed_predicted"] == 0

    # Overdue project should have critical delay risk
    assert overdue_res["delay_risk_level"] == "CRITICAL"
    assert overdue_res["delay_risk_score"] >= 0.85
    assert overdue_res["is_delayed_predicted"] == 1


def test_model_persistence(synthetic_training_data):
    """Test save and load reproducibility."""
    df, mp_df = synthetic_training_data
    predictor = XGBoostDelayPredictor(n_estimators=30, max_depth=3)
    predictor.fit(df, mp_df=mp_df)
    preds_before = predictor.predict(df, mp_df=mp_df)

    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        predictor.save(tmp_path)
        loaded = XGBoostDelayPredictor.load(tmp_path)
        preds_after = loaded.predict(df, mp_df=mp_df)

        pd.testing.assert_series_equal(preds_before["predicted_completion_days"], preds_after["predicted_completion_days"])
        pd.testing.assert_series_equal(preds_before["delay_risk_score"], preds_after["delay_risk_score"])
        pd.testing.assert_series_equal(preds_before["delay_risk_level"], preds_after["delay_risk_level"])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
