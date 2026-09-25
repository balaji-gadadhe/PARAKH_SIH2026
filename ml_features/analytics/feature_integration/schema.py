"""
schema.py
=========
Schema definitions, entity levels, column contracts, and risk thresholds
for the Feature Integration & Aggregate Risk Layer.
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, List, Tuple


PRIMARY_KEY = "project_id"


class EntityLevel(str, Enum):
    PROJECT = "PROJECT"
    AGENCY = "AGENCY"
    VENDOR = "VENDOR"
    MP = "MP"
    PAYMENT = "PAYMENT"
    PROJECT_PAIR = "PROJECT_PAIR"
    RULE_EVENT = "RULE_EVENT"


# Expected default relative paths within ml_features or workspace
DEFAULT_FILE_MAP: Dict[str, str] = {
    "base_projects": "ml_input/project_features.csv",
    "cost_anomaly": "ml_outputs/cost_anomaly_results.csv",
    "delay_predictions": "ml_outputs/delay_predictions.csv",
    "isolation_forest": "ml_outputs/isolation_forest_results.csv",
    "payment_anomaly": "ml_outputs/payment_anomaly_results.csv",
    "rule_flagged": "ml_outputs/rules/flagged_projects.csv",
    "rule_results": "ml_outputs/rules/rule_results.csv",
    "similarity_projects": "ml_outputs/similarity/project_similarity_features.csv",
    "similarity_pairs": "ml_outputs/similarity/duplicate_project_pairs.csv",
    "agency_profiles": "ml_outputs/agency_profiles.csv",
}

# Required columns for structural validation
SCHEMA_REQUIREMENTS: Dict[str, List[str]] = {
    "base_projects": [
        "project_id", "mp_name", "state", "constituency", "category",
        "recommended_amount", "total_expenditure", "expenditure_ratio"
    ],
    "cost_anomaly": [
        "project_id", "cost_anomaly_score", "is_cost_anomaly"
    ],
    "delay_predictions": [
        "project_id", "delay_risk_score", "is_delayed_predicted", "delay_risk_level"
    ],
    "isolation_forest": [
        "project_id", "anomaly_score", "is_anomaly"
    ],
    "payment_anomaly": [
        "project_id", "payment_anomaly_score", "is_payment_anomaly"
    ],
    "rule_flagged": [
        "project_id", "rule_risk_score", "risk_band", "rules_triggered", "rule_count"
    ],
    "rule_results": [
        "project_id", "rule_id", "rule_name", "triggered", "severity"
    ],
    "similarity_projects": [
        "project_id", "max_similarity_score", "duplicate_risk_score"
    ],
    "similarity_pairs": [
        "project_id_a", "project_id_b", "similarity_score"
    ],
    "agency_profiles": [
        "agency_id", "agency_risk_score", "agency_risk_level"
    ]
}

DEFAULT_WEIGHTS: Dict[str, float] = {
    "cost_risk": 0.20,
    "delay_risk": 0.20,
    "payment_risk": 0.20,
    "rule_risk": 0.20,
    "similarity_risk": 0.10,
    "iforest_risk": 0.10
}

DEFAULT_RISK_THRESHOLDS: Dict[str, Tuple[float, float]] = {
    "LOW": (0.0, 0.30),
    "MEDIUM": (0.30, 0.60),
    "HIGH": (0.60, 0.80),
    "CRITICAL": (0.80, 1.00)
}

# Normalized feature column names
NORMALIZED_SCORE_COLS = [
    "cost_risk_score",
    "delay_risk_score",
    "payment_risk_score",
    "rule_risk_score",
    "similarity_risk_score",
    "iforest_risk_score"
]

NORMALIZED_FLAG_COLS = [
    "cost_risk_flag",
    "delay_risk_flag",
    "payment_risk_flag",
    "rule_risk_flag",
    "similarity_risk_flag",
    "iforest_risk_flag"
]

AVAILABILITY_COLS = [
    "cost_available",
    "delay_available",
    "payment_available",
    "rule_available",
    "similarity_available",
    "iforest_available"
]
