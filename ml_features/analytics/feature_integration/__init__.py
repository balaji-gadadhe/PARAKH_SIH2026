"""
analytics.feature_integration
=============================
Unified Risk Integration Layer for MPLADS monitoring and risk/anomaly detection.
Integrates ML models, rule engines, similarity analyses, and payments into
standardized risk signals, weighted composite scores, and Explainable AI payloads.
"""

from .schema import (
    PRIMARY_KEY,
    EntityLevel,
    DEFAULT_WEIGHTS,
    DEFAULT_RISK_THRESHOLDS,
    NORMALIZED_SCORE_COLS,
    NORMALIZED_FLAG_COLS,
    AVAILABILITY_COLS
)
from .loaders import FeatureLoaders
from .validators import FeatureValidators
from .aggregators import FeatureAggregators
from .feature_merger import FeatureMerger
from .risk_signal_builder import RiskSignalBuilder
from .risk_aggregator import RiskAggregator
from .pipeline import run_feature_integration_pipeline

__all__ = [
    "PRIMARY_KEY",
    "EntityLevel",
    "DEFAULT_WEIGHTS",
    "DEFAULT_RISK_THRESHOLDS",
    "NORMALIZED_SCORE_COLS",
    "NORMALIZED_FLAG_COLS",
    "AVAILABILITY_COLS",
    "FeatureLoaders",
    "FeatureValidators",
    "FeatureAggregators",
    "FeatureMerger",
    "RiskSignalBuilder",
    "RiskAggregator",
    "run_feature_integration_pipeline"
]
