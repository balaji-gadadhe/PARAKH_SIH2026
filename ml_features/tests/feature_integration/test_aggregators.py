"""
test_aggregators.py
===================
Tests for 1:N rule event aggregation and pairwise similarity aggregation.
Verifies that multi-record entities collapse strictly to one row per project_id.
"""

import pandas as pd
from analytics.feature_integration.aggregators import FeatureAggregators


def test_aggregate_rule_results_one_to_many():
    # 1 project with 3 triggered rules
    raw_rules = pd.DataFrame([
        {
            "project_id": "P100",
            "rule_id": "R01",
            "rule_name": "Compliance Check",
            "triggered": 1,
            "severity": "LOW",
            "reason": "Missing metadata"
        },
        {
            "project_id": "P100",
            "rule_id": "R02",
            "rule_name": "Ghost Project",
            "triggered": 1,
            "severity": "CRITICAL",
            "reason": "Stalled for >500 days"
        },
        {
            "project_id": "P100",
            "rule_id": "R03",
            "rule_name": "Cost Gap",
            "triggered": 1,
            "severity": "MEDIUM",
            "reason": "Unusual cost gap"
        },
        {
            "project_id": "P200",
            "rule_id": "R01",
            "rule_name": "Compliance Check",
            "triggered": 1,
            "severity": "LOW",
            "reason": "Minor note"
        }
    ])

    agg = FeatureAggregators.aggregate_rule_results(raw_rules)

    # Must have exactly 2 rows (P100 and P200)
    assert len(agg) == 2
    p100 = agg[agg["project_id"] == "P100"].iloc[0]
    assert p100["rule_event_count"] == 3
    assert p100["max_rule_severity"] == "CRITICAL"
    assert p100["max_rule_severity_score"] == 75.0
    assert "R02" in p100["rule_ids_triggered"]
    assert "Stalled for >500 days" in p100["rule_reasons_summary"]


def test_aggregate_pairwise_similarity():
    # Project pairs where P1 matches P2, and P2 matches P3
    pairs_df = pd.DataFrame([
        {
            "project_id_a": "P1",
            "project_id_b": "P2",
            "similarity_score": 0.95,
            "pair_risk_score": 0.88,
            "exact_text_duplicate_flag": 1,
            "geo_risk_label": "CRITICAL_GEO"
        },
        {
            "project_id_a": "P2",
            "project_id_b": "P3",
            "similarity_score": 0.82,
            "pair_risk_score": 0.70,
            "exact_text_duplicate_flag": 0,
            "geo_risk_label": "MEDIUM_GEO"
        }
    ])

    agg = FeatureAggregators.aggregate_pairwise_similarity(pairs_df)

    # Projects involved: P1, P2, P3
    assert len(agg) == 3
    assert set(agg["project_id"]) == {"P1", "P2", "P3"}

    # P2 is involved in 2 pairs
    p2 = agg[agg["project_id"] == "P2"].iloc[0]
    assert p2["pair_duplicate_count"] == 2
    assert p2["max_pair_similarity_score"] == 0.95
    assert p2["max_pair_risk_score"] == 0.88
    assert p2["pair_exact_text_flag"] == 1
    assert p2["pair_critical_geo_flag"] == 1
