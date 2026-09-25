"""
test_investigation.py
=====================
Tests for case prioritization and investigation ranking.
"""

import pytest
import pandas as pd
from analytics.investigation.prioritization import InvestigationPrioritizer
from analytics.investigation.case_ranking import CaseRanker


def test_investigation_prioritization_tiers():
    df = pd.DataFrame([
        {
            "project_id": "P_HIGH",
            "overall_risk_score": 0.85,
            "total_expenditure": 15000000.0  # 1.5 Cr
        },
        {
            "project_id": "P_LOW",
            "overall_risk_score": 0.10,
            "total_expenditure": 50000.0
        }
    ])
    res = InvestigationPrioritizer.prioritize_cases(df)
    assert len(res) == 2

    p_high = res[res["project_id"] == "P_HIGH"].iloc[0]
    assert p_high["investigation_urgency"] == "TIER_1_IMMEDIATE_ACTION"
    assert p_high["audit_dispatch_recommended"] == True

    p_low = res[res["project_id"] == "P_LOW"].iloc[0]
    assert p_low["investigation_urgency"] == "TIER_4_ROUTINE"
    assert p_low["audit_dispatch_recommended"] == False


def test_case_ranker_ordering():
    df = pd.DataFrame([
        {"project_id": "P_MED", "overall_risk_score": 0.50, "total_expenditure": 200000.0},
        {"project_id": "P_CRIT", "overall_risk_score": 0.90, "total_expenditure": 10000000.0},
        {"project_id": "P_LOW", "overall_risk_score": 0.05, "total_expenditure": 50000.0}
    ])
    ranked = CaseRanker.rank_cases(df)
    assert ranked["project_id"].iloc[0] == "P_CRIT"
    assert ranked["investigation_rank"].iloc[0] == 1
    assert ranked["investigation_rank"].iloc[-1] == 3
