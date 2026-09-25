"""
test_pipeline.py
================
End-to-end integration pipeline tests using synthetic fixtures.
Validates file outputs, schema consistency, and report generation.
"""

import json
import os
import pytest
import pandas as pd
from analytics.feature_integration.pipeline import run_feature_integration_pipeline


@pytest.fixture
def synthetic_workspace(tmp_path):
    """Create a minimal synthetic ml_features directory structure."""
    input_dir = tmp_path / "ml_input"
    output_dir = tmp_path / "ml_outputs"
    config_dir = tmp_path / "config"

    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    # 1. Base project features
    base_df = pd.DataFrame([
        {
            "project_id": "P001",
            "mp_name": "MP Alpha",
            "state": "State1",
            "constituency": "Const1",
            "category": "ROADS",
            "recommended_amount": 500000.0,
            "total_expenditure": 600000.0,
            "expenditure_ratio": 1.2,
            "is_completed": 0
        },
        {
            "project_id": "P002",
            "mp_name": "MP Beta",
            "state": "State2",
            "constituency": "Const2",
            "category": "WATER",
            "recommended_amount": 300000.0,
            "total_expenditure": 300000.0,
            "expenditure_ratio": 1.0,
            "is_completed": 1
        }
    ])
    base_df.to_csv(input_dir / "project_features.csv", index=False)

    # 2. Cost anomaly output
    cost_df = pd.DataFrame([
        {
            "project_id": "P001",
            "cost_anomaly_score": 0.85,
            "is_cost_anomaly": 1,
            "cost_anomaly_type": "EXTREME_PEER_INFLATION",
            "cost_z_score": 3.5,
            "cost_deviation_from_peer": 120.0,
            "peer_median_cost": 250000.0
        },
        {
            "project_id": "P002",
            "cost_anomaly_score": 0.10,
            "is_cost_anomaly": 0,
            "cost_anomaly_type": "NORMAL",
            "cost_z_score": -0.2,
            "cost_deviation_from_peer": 0.0,
            "peer_median_cost": 300000.0
        }
    ])
    cost_df.to_csv(output_dir / "cost_anomaly_results.csv", index=False)

    # 3. Config
    config_data = {
        "weights": {
            "cost_risk": 1.0
        },
        "risk_thresholds": {
            "LOW": [0.0, 0.30],
            "MEDIUM": [0.30, 0.60],
            "HIGH": [0.60, 0.80],
            "CRITICAL": [0.80, 1.00]
        }
    }
    with open(config_dir / "risk_weights.json", "w", encoding="utf-8") as f:
        json.dump(config_data, f)

    return str(tmp_path)


def test_run_feature_integration_pipeline_synthetic(synthetic_workspace):
    out_dir = os.path.join(synthetic_workspace, "ml_outputs")
    final_df, risk_df, report = run_feature_integration_pipeline(
        base_dir=synthetic_workspace,
        output_dir=out_dir,
        strict=False
    )

    # Check cardinality
    assert len(final_df) == 2
    assert len(risk_df) == 2
    assert report["cardinality_preserved"] is True
    assert report["duplicate_keys"] == 0

    # Verify scores
    p1 = risk_df[risk_df["project_id"] == "P001"].iloc[0]
    assert p1["overall_risk_score"] == 0.85
    assert p1["risk_category"] == "CRITICAL"
    assert "cost_risk_score" in p1
    assert p1["cost_risk_flag"] is True or p1["cost_risk_flag"] == 1

    p2 = risk_df[risk_df["project_id"] == "P002"].iloc[0]
    assert p2["overall_risk_score"] == 0.10
    assert p2["risk_category"] == "LOW"

    # Verify generated files exist
    assert os.path.exists(os.path.join(out_dir, "integrated_project_features.csv"))
    assert os.path.exists(os.path.join(out_dir, "project_risk_results.csv"))
    assert os.path.exists(os.path.join(out_dir, "integration_report.json"))
