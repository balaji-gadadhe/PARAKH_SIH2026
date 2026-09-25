"""
test_validators.py
==================
Tests for schema validation, key integrity, duplicate project detection,
score ranges, and cardinality verification.
"""

import pytest
import pandas as pd
from analytics.feature_integration.validators import FeatureValidators


def test_validator_primary_key_success():
    df = pd.DataFrame({"project_id": ["P1", "P2", "P3"], "val": [1, 2, 3]})
    valid, report = FeatureValidators.validate_primary_key(df, "test_ds", strict=True)
    assert valid is True
    assert report["duplicate_count"] == 0
    assert report["unique_keys"] == 3


def test_validator_missing_primary_key_raises():
    df = pd.DataFrame({"other_id": [1, 2, 3]})
    with pytest.raises(KeyError):
        FeatureValidators.validate_primary_key(df, "test_ds", key_col="project_id", strict=True)


def test_validator_duplicate_primary_key_detected():
    # Duplicate project_id should be detected and rejected
    df = pd.DataFrame({"project_id": ["P1", "P1", "P2"], "val": [10, 20, 30]})
    with pytest.raises(ValueError, match="duplicate"):
        FeatureValidators.validate_primary_key(df, "test_ds", key_col="project_id", strict=True)


def test_validator_null_primary_key_detected():
    df = pd.DataFrame({"project_id": ["P1", None, "P2"]})
    with pytest.raises(ValueError, match="null"):
        FeatureValidators.validate_primary_key(df, "test_ds", key_col="project_id", strict=True)


def test_validator_score_bounds():
    df_valid = pd.DataFrame({"score": [0.0, 0.5, 1.0]})
    valid, _ = FeatureValidators.validate_score_bounds(df_valid, "score", 0.0, 1.0, strict=True)
    assert valid is True

    df_invalid = pd.DataFrame({"score": [-0.1, 0.5, 1.2]})
    with pytest.raises(ValueError, match="outside expected bounds"):
        FeatureValidators.validate_score_bounds(df_invalid, "score", 0.0, 1.0, strict=True)


def test_validator_cardinality_mismatch_raises():
    base = pd.DataFrame({"project_id": ["P1", "P2"]})
    exploded = pd.DataFrame({"project_id": ["P1", "P2", "P2"]})
    with pytest.raises(ValueError, match="Row explosion detected"):
        FeatureValidators.validate_merge_cardinality(base, exploded, strict=True)
