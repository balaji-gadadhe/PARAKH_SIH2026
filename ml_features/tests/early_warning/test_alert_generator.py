"""
test_alert_generator.py
=======================
Tests for early warning alert triggers and severity assignments.
"""

import pytest
import pandas as pd
from analytics.early_warning.alert_generator import AlertGenerator


def test_alert_generator_triggers():
    projects_df = pd.DataFrame([
        {
            "project_id": "P_OVERRUN",
            "mp_name": "MP Alpha",
            "state": "Gujarat",
            "recommended_amount": 100000.0,
            "total_expenditure": 250000.0,
            "expenditure_ratio": 2.5,
            "days_since_recommendation": 120,
            "is_completed": 0,
            "payment_risk_flag": True
        }
    ])
    generator = AlertGenerator()
    alerts = generator.generate_alerts(projects_df)

    assert len(alerts) >= 2
    codes = alerts["alert_code"].tolist()
    assert "WARN_BUDGET_OVERRUN" in codes
    assert "WARN_PAYMENT_CHURN" in codes

    overrun = alerts[alerts["alert_code"] == "WARN_BUDGET_OVERRUN"].iloc[0]
    assert overrun["alert_severity"] == "CRITICAL"
    assert "Freeze disbursements" in overrun["recommended_action"]
