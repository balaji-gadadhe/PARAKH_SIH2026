"""
test_shap_explainer.py
======================
Unit tests for TreeSHAP feature explainer and reason generator.
"""

import json
import pytest
import pandas as pd
from analytics.explainability.shap_explainer import ShapExplainer
from analytics.explainability.reason_generator import ReasonGenerator


def test_shap_explainer_initialization():
    explainer = ShapExplainer()
    assert explainer is not None
    assert "recommended_amount" in explainer.feature_names


def test_shap_feature_preparation():
    df = pd.DataFrame([
        {
            "project_id": "P001",
            "recommended_amount": 500000.0,
            "category": "Normal/Others",
            "payment_count": 5,
            "pending_payment_count": 1,
            "has_images": True,
            "completion_rate_pct": 80.0,
            "utilization_pct": 95.0,
            "completion_gap": 15.0
        }
    ])
    explainer = ShapExplainer()
    feat_matrix = explainer.prepare_features(df)
    assert len(feat_matrix) == 1
    assert "recommended_amount" in feat_matrix.columns
    assert feat_matrix["has_images_code"].iloc[0] == 1


def test_shap_dataset_explanation():
    df = pd.DataFrame([
        {
            "project_id": "P001",
            "recommended_amount": 1000000.0,
            "category": "Normal/Others",
            "payment_count": 20,
            "pending_payment_count": 10,
            "has_images": False,
            "completion_rate_pct": 20.0,
            "utilization_pct": 150.0,
            "completion_gap": 130.0
        }
    ])
    explainer = ShapExplainer()
    res = explainer.explain_dataset(df)
    assert len(res) == 1
    row = res.iloc[0]
    assert "project_id" in row
    assert "shap_base_value" in row
    assert "shap_top_delay_pusher" in row
    assert "shap_feature_attributions" in row

    attribs = json.loads(row["shap_feature_attributions"])
    assert isinstance(attribs, dict)


def test_reason_generator_output():
    row = pd.Series({
        "overall_risk_score": 0.85,
        "risk_category": "CRITICAL",
        "cost_risk_score": 0.90,
        "cost_risk_flag": True,
        "cost_anomaly_type": "EXTREME_PEER_INFLATION",
        "cost_z_score": 3.8,
        "delay_risk_score": 0.80,
        "delay_risk_flag": True,
        "predicted_completion_days": 550,
        "rule_risk_score": 0.70,
        "rule_risk_flag": True,
        "rules_triggered": "COMPLIANCE-001;GHOST-003",
        "rule_count": 2
    })
    reasons = ReasonGenerator.generate_reasons(row)
    assert reasons["risk_category"] == "CRITICAL"
    assert len(reasons["risk_factors"]) >= 3
    assert any("Cost Anomaly: EXTREME PEER INFLATION" in f for f in reasons["risk_factors"])
    assert any("Delay Risk" in f for f in reasons["risk_factors"])
    assert any("COMPLIANCE-001" in f for f in reasons["risk_factors"])
