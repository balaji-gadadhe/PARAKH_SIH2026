"""
test_feature_merger.py
======================
Tests for safe left-joins, column collision avoidance,
and strict cardinality preservation (1 row = 1 project).
"""

import pytest
import pandas as pd
from analytics.feature_integration.feature_merger import FeatureMerger


def test_basic_merge_success():
    base = pd.DataFrame({
        "project_id": ["P1", "P2", "P3"],
        "cost": [100.0, 200.0, 300.0]
    })
    cost_df = pd.DataFrame({
        "project_id": ["P1", "P2"],
        "cost_anomaly_score": [0.8, 0.2],
        "is_cost_anomaly": [1, 0]
    })

    merger = FeatureMerger(strict=True)
    merged = merger.safe_left_join(base, cost_df, "cost_anomaly")

    assert len(merged) == 3
    assert merged["project_id"].tolist() == ["P1", "P2", "P3"]
    assert merged.loc[merged["project_id"] == "P1", "cost_anomaly_score"].values[0] == 0.8
    assert pd.isna(merged.loc[merged["project_id"] == "P3", "cost_anomaly_score"].values[0])


def test_prevent_column_collision():
    # If incoming dataset contains metadata column like 'state', don't create state_x / state_y
    base = pd.DataFrame({
        "project_id": ["P1"],
        "state": ["Delhi"],
        "cost": [100.0]
    })
    incoming = pd.DataFrame({
        "project_id": ["P1"],
        "state": ["Delhi"],  # overlapping column
        "score": [0.9]
    })

    merger = FeatureMerger(strict=True)
    merged = merger.safe_left_join(base, incoming, "test_feat")

    assert "state_x" not in merged.columns
    assert "state_y" not in merged.columns
    assert "state" in merged.columns
    assert "score" in merged.columns


def test_final_uniqueness_guarantee():
    base = pd.DataFrame({
        "project_id": [f"P_{i}" for i in range(100)],
        "val": range(100)
    })
    feature_a = pd.DataFrame({
        "project_id": [f"P_{i}" for i in range(50)],
        "score_a": [0.5] * 50
    })

    merger = FeatureMerger(strict=True)
    merged = merger.safe_left_join(base, feature_a, "feat_a")

    assert len(merged) == 100
    assert merged["project_id"].nunique() == 100
