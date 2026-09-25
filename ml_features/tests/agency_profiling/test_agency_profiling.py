"""Unit and synthetic test suite for Agency Profiling & Intelligence Feature.

Covers:
1. Initialization
2. Required-column handling
3. Agency aggregation from project-level records
4. Completion-rate calculation
5. Delay-rate calculation
6. Missing-value (NaN/Inf) handling
7. Small-sample agencies (shrinkage fairness)
8. Risk-score range [0, 100]
9. Risk-band classification (LOW, MEDIUM, HIGH, CRITICAL)
10. Planted scenario: Agency B (high risk) vs Agency A (good performance)
11. Normal agency scenario
12. Output schema validation
"""

import pytest
import numpy as np
import pandas as pd

from analytics.agency_profiling.historical_performance import extract_historical_performance
from analytics.agency_profiling.delay_history import evaluate_delay_history
from analytics.agency_profiling.agency_risk_score import (
    AgencyProfiler,
    run_agency_profiling_pipeline
)


@pytest.fixture
def project_level_dataset():
    """Synthetic project-level dataset with multiple agencies."""
    records = []
    
    # Agency A: High performing (20 projects, 18 completed, 1 delayed, normal costs)
    for i in range(20):
        records.append({
            "project_id": f"proj_A_{i}",
            "agency_name": "Agency A",
            "agency_id": "AG_A",
            "is_completed": 1 if i < 18 else 0,
            "is_delayed": 1 if i == 19 else 0,
            "delay_days": 15.0 if i == 19 else 0.0,
            "recommended_amount": 500000.0,
            "total_expenditure": 480000.0,
            "is_anomaly": 0,
            "pending_payment_count": 0
        })

    # Agency B: Chronic poor performer (20 projects, 2 completed, 16 delayed, extreme cost overrun/skew)
    for i in range(20):
        records.append({
            "project_id": f"proj_B_{i}",
            "agency_name": "Agency B",
            "agency_id": "AG_B",
            "is_completed": 1 if i < 2 else 0,
            "is_delayed": 1 if i < 16 else 0,
            "delay_days": 210.0 if i < 16 else 0.0,
            "recommended_amount": 500000.0,
            "total_expenditure": 1500000.0 if i % 2 == 0 else 450000.0,  # massive overrun and skew
            "is_anomaly": 1 if i % 3 == 0 else 0,
            "pending_payment_count": 2 if i % 4 == 0 else 0
        })

    # Agency C: Single-project small agency
    records.append({
        "project_id": "proj_C_1",
        "agency_name": "Agency C",
        "agency_id": "AG_C",
        "is_completed": 0,
        "is_delayed": 1,
        "delay_days": 100.0,
        "recommended_amount": 300000.0,
        "total_expenditure": 300000.0,
        "is_anomaly": 0,
        "pending_payment_count": 0
    })

    return pd.DataFrame(records)


@pytest.fixture
def vendor_level_dataset():
    """Synthetic pre-aggregated vendor records matching vendor_features.csv schema."""
    return pd.DataFrame({
        "vendor": ["Vendor X", "Vendor Y", "Vendor Z"],
        "project_count": [15, 1, 30],
        "total_expenditure": [7500000.0, 500000.0, 45000000.0],
        "average_project_cost": [500000.0, 500000.0, 1500000.0],
        "median_project_cost": [490000.0, 500000.0, 600000.0],  # Vendor Z has high cost skewness
        "completed_project_count": [12, 0, 5],
        "pending_payment_count": [0, 0, 8],
        "successful_payment_count": [0, 0, 0]
    })


# 1. Initialization Test
def test_initialization():
    profiler = AgencyProfiler(credibility_k=4.0, neutral_baseline=20.0)
    assert profiler.credibility_k == 4.0
    assert profiler.neutral_baseline == 20.0


# 2. Required-Column Handling
def test_required_column_validation():
    profiler = AgencyProfiler()
    # Missing agency column should raise ValueError
    invalid_df = pd.DataFrame({"some_num": [1, 2, 3]})
    with pytest.raises(ValueError, match="agency/vendor identification column"):
        profiler.profile_agencies(invalid_df)

    # Empty DataFrame should return empty schema
    empty_res = profiler.profile_agencies(pd.DataFrame())
    assert "agency_risk_score" in empty_res.columns
    assert len(empty_res) == 0


# 3. Agency Aggregation Test
def test_agency_aggregation(project_level_dataset):
    perf_df = extract_historical_performance(project_level_dataset)
    assert len(perf_df) == 3
    assert set(perf_df["agency_name"]) == {"Agency A", "Agency B", "Agency C"}
    
    ag_a = perf_df[perf_df["agency_name"] == "Agency A"].iloc[0]
    assert ag_a["total_projects"] == 20
    assert ag_a["completed_projects"] == 18
    assert ag_a["ongoing_projects"] == 2


# 4. Completion-Rate Calculation Test
def test_completion_rate(project_level_dataset):
    perf_df = extract_historical_performance(project_level_dataset)
    ag_a = perf_df[perf_df["agency_name"] == "Agency A"].iloc[0]
    ag_b = perf_df[perf_df["agency_name"] == "Agency B"].iloc[0]

    assert ag_a["completion_rate"] == 90.0
    assert ag_b["completion_rate"] == 10.0


# 5. Delay-Rate Calculation Test
def test_delay_rate(project_level_dataset):
    perf_df = extract_historical_performance(project_level_dataset)
    delay_rates, avg_days, _ = evaluate_delay_history(project_level_dataset, perf_df, "agency_name")
    
    idx_a = perf_df[perf_df["agency_name"] == "Agency A"].index[0]
    idx_b = perf_df[perf_df["agency_name"] == "Agency B"].index[0]

    assert delay_rates[idx_a] == 5.0    # 1 / 20 = 5%
    assert delay_rates[idx_b] == 80.0   # 16 / 20 = 80%
    assert avg_days[idx_b] >= 150.0


# 6. Missing-Value (NaN/Inf) Handling Test
def test_missing_and_inf_handling():
    df = pd.DataFrame({
        "agency_name": ["Agency NanInf", "Agency Normal"],
        "project_count": [np.nan, 5],
        "total_expenditure": [np.inf, 2500000.0],
        "average_project_cost": [np.nan, 500000.0],
        "median_project_cost": [-np.inf, 480000.0],
        "completed_project_count": [np.nan, 4],
        "pending_payment_count": [np.nan, 0]
    })
    profiler = AgencyProfiler()
    res = profiler.profile_agencies(df)

    assert not res["agency_risk_score"].isna().any()
    assert not np.isinf(res["agency_risk_score"]).any()
    assert len(res) == 2


# 7. Small-Sample Agencies Test (Shrinkage Fairness)
def test_small_sample_agencies(project_level_dataset):
    profiler = AgencyProfiler(credibility_k=3.0)
    res = profiler.profile_agencies(project_level_dataset)

    ag_c = res[res["agency_name"] == "Agency C"].iloc[0]
    # Agency C had 1 project that was delayed, but because N=1, its risk score must be dampened
    # and MUST NOT be classified as CRITICAL
    assert ag_c["total_projects"] == 1
    assert ag_c["agency_risk_level"] in ["LOW", "MEDIUM"]
    assert "Low historical volume" in ag_c["risk_reasons"]


# 8. Risk-Score Range [0, 100] Test
def test_risk_score_bounds(project_level_dataset):
    profiler = AgencyProfiler()
    res = profiler.profile_agencies(project_level_dataset)

    assert res["agency_risk_score"].min() >= 0.0
    assert res["agency_risk_score"].max() <= 100.0


# 9. Risk-Band Classification Test
def test_risk_band_classification(vendor_level_dataset):
    profiler = AgencyProfiler()
    res = profiler.profile_agencies(vendor_level_dataset)

    valid_bands = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert set(res["agency_risk_level"].unique()).issubset(valid_bands)


# 10. Planted High-Risk Agency Scenario (Agency B vs Agency A)
def test_planted_agency_comparison(project_level_dataset):
    profiler = AgencyProfiler()
    res = profiler.profile_agencies(project_level_dataset)

    score_a = res[res["agency_name"] == "Agency A"]["agency_risk_score"].iloc[0]
    score_b = res[res["agency_name"] == "Agency B"]["agency_risk_score"].iloc[0]
    level_b = res[res["agency_name"] == "Agency B"]["agency_risk_level"].iloc[0]

    # Agency B must receive a significantly higher risk score than Agency A
    assert score_b > score_a
    assert score_b >= 60.0
    assert level_b in ["HIGH", "CRITICAL"]

    reasons_b = res[res["agency_name"] == "Agency B"]["risk_reasons"].iloc[0]
    assert "High historical delay rate" in reasons_b
    assert "Low project completion rate" in reasons_b


# 11. Normal Agency Scenario
def test_normal_agency_scenario(project_level_dataset):
    profiler = AgencyProfiler()
    res = profiler.profile_agencies(project_level_dataset)

    row_a = res[res["agency_name"] == "Agency A"].iloc[0]
    assert row_a["agency_risk_score"] < 35.0
    assert row_a["agency_risk_level"] in ["LOW", "MEDIUM"]


# 12. Output Schema Test
def test_output_schema(vendor_level_dataset):
    profiler = AgencyProfiler()
    res = profiler.profile_agencies(vendor_level_dataset)

    expected_cols = [
        "agency_id",
        "agency_name",
        "total_projects",
        "completed_projects",
        "ongoing_projects",
        "completion_rate",
        "delay_rate",
        "average_delay_days",
        "average_utilization",
        "anomaly_count",
        "high_risk_project_count",
        "agency_risk_score",
        "agency_risk_level",
        "risk_level",
        "risk_reasons"
    ]
    for col in expected_cols:
        assert col in res.columns, f"Missing required column: {col}"

    assert len(res) == len(vendor_level_dataset)
