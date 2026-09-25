"""
test_trend_analysis.py
======================
Tests for spend velocity, peer acceleration, and stalled decay detection.
"""

import pytest
import pandas as pd
from analytics.early_warning.trend_analysis import TrendAnalyzer


def test_trend_analyzer_metrics():
    df = pd.DataFrame([
        {
            "project_id": "P001",
            "days_since_recommendation": 100,
            "total_expenditure": 500000.0,
            "recommended_amount": 500000.0,
            "is_completed": 0,
            "category": "ROADS",
            "state": "Gujarat"
        },
        {
            "project_id": "P002",
            "days_since_recommendation": 400,
            "total_expenditure": 10000.0,
            "recommended_amount": 500000.0,
            "is_completed": 0,
            "category": "ROADS",
            "state": "Gujarat"
        }
    ])
    analyzer = TrendAnalyzer()
    res = analyzer.analyze_trends(df)

    assert len(res) == 2
    # P001: 500k / 100 = 5000/day
    assert res.loc[res["project_id"] == "P001", "spend_velocity_daily"].values[0] == 5000.0
    # P002 is approved >365 days ago with only 10k/500k = 2% spent -> stalled decay
    assert res.loc[res["project_id"] == "P002", "is_stalled_decay"].values[0] == True
    assert res.loc[res["project_id"] == "P002", "burn_rate_status"].values[0] == "STALLED_DECAY"
