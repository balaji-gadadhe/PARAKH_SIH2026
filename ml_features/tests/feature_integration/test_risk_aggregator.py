"""
test_risk_aggregator.py
=======================
Tests for risk score normalization, weight validation, category mapping,
dynamic renormalization, and Explainable AI (XAI) factor synthesis.
"""

import json
import pytest
import pandas as pd
from analytics.feature_integration.risk_signal_builder import RiskSignalBuilder
from analytics.feature_integration.risk_aggregator import RiskAggregator


def test_weight_validation_sum_to_one():
    # Valid weights
    valid_weights = {
        "cost_risk": 0.5,
        "delay_risk": 0.5
    }
    agg = RiskAggregator(weights=valid_weights)
    assert agg.weights["cost_risk"] == 0.5

    # Invalid weights sum != 1.0
    invalid_weights = {
        "cost_risk": 0.4,
        "delay_risk": 0.4
    }
    with pytest.raises(ValueError, match="must sum to 1.0"):
        RiskAggregator(weights=invalid_weights)


def test_risk_category_mapping():
    agg = RiskAggregator()
    assert agg.map_risk_category(0.15) == "LOW"
    assert agg.map_risk_category(0.45) == "MEDIUM"
    assert agg.map_risk_category(0.70) == "HIGH"
    assert agg.map_risk_category(0.95) == "CRITICAL"
    assert agg.map_risk_category(1.0) == "CRITICAL"


def test_score_normalization_via_signal_builder():
    raw_df = pd.DataFrame([
        {
            "project_id": "P1",
            "cost_anomaly_score": 0.75,
            "is_cost_anomaly": 1,
            "delay_risk_score": 0.85,
            "is_delayed_predicted": 1,
            "delay_risk_level": "CRITICAL",
            "raw_rule_risk_score": 210.0,
            "rule_count": 3
        }
    ])
    signaled = RiskSignalBuilder.build_signals(raw_df)

    assert signaled["cost_risk_score"].iloc[0] == 0.75
    assert signaled["cost_risk_flag"].iloc[0] is True or signaled["cost_risk_flag"].iloc[0] == 1
    assert signaled["delay_risk_score"].iloc[0] == 0.85
    assert signaled["delay_risk_flag"].iloc[0] is True or signaled["delay_risk_flag"].iloc[0] == 1
    # 210 / 300 = 0.70
    assert abs(signaled["rule_risk_score"].iloc[0] - 0.70) < 1e-4
    assert signaled["rule_risk_flag"].iloc[0] is True or signaled["rule_risk_flag"].iloc[0] == 1


def test_dynamic_weight_renormalization_for_missing_features():
    # If a feature like similarity is missing, remaining features renormalize to 1.0
    weights = {
        "cost_risk": 0.50,
        "similarity_risk": 0.50
    }
    agg = RiskAggregator(weights=weights)

    row = pd.Series({
        "cost_risk_score": 0.80,
        "cost_available": True,
        "similarity_risk_score": None,
        "similarity_available": False
    })
    res = agg.compute_project_risk(row)

    # Cost was 0.80, similarity was missing -> cost takes 100% of weight -> overall = 0.80
    assert res["overall_risk_score"] == 0.80
    assert res["risk_category"] == "CRITICAL"


def test_explainable_ai_risk_factors_generation():
    weights = {
        "cost_risk": 0.50,
        "delay_risk": 0.50
    }
    agg = RiskAggregator(weights=weights)

    row = pd.Series({
        "cost_risk_score": 0.85,
        "cost_risk_flag": True,
        "cost_available": True,
        "cost_anomaly_type": "EXTREME_PEER_INFLATION",
        "cost_z_score": 4.2,
        "delay_risk_score": 0.90,
        "delay_risk_flag": True,
        "delay_available": True,
        "predicted_completion_days": 650
    })
    res = agg.compute_project_risk(row)

    factors = json.loads(res["risk_factors"])
    assert any("Cost Anomaly: EXTREME PEER INFLATION" in f for f in factors)
    assert any("+4.2σ" in f for f in factors)
    assert any("Delay Risk" in f for f in factors)
    assert any("650 days" in f for f in factors)

    evidence_dict = json.loads(res["evidence_payload"])
    assert evidence_dict["overall_risk_score"] == 0.875
    assert evidence_dict["risk_category"] == "CRITICAL"
    assert "audit_explanation" in res
    assert "CRITICAL RISK" in res["audit_explanation"]
