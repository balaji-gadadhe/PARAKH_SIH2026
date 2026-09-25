"""
test_loaders.py
===============
Tests for dataset loading, path resolution, strict vs lenient modes,
and handling of missing optional files.
"""

import os
import pytest
import pandas as pd
from analytics.feature_integration.loaders import FeatureLoaders


def test_loaders_base_dir_resolution(tmp_path):
    loader = FeatureLoaders(base_dir=str(tmp_path))
    resolved = loader.resolve_path("sample.csv")
    assert resolved == os.path.join(str(tmp_path), "sample.csv")


def test_loaders_missing_optional_file(tmp_path):
    # Missing optional file returns None, False in non-strict mode
    loader = FeatureLoaders(base_dir=str(tmp_path))
    df, is_loaded, path = loader.load_single("cost_anomaly", strict=False)
    assert df is None
    assert is_loaded is False


def test_loaders_missing_required_file_strict_raises(tmp_path):
    # Missing required file raises FileNotFoundError
    loader = FeatureLoaders(base_dir=str(tmp_path))
    with pytest.raises(FileNotFoundError):
        loader.load_single("base_projects", strict=True)


def test_loaders_load_all_records_metadata(tmp_path):
    # Create mock base_projects file
    base_file = tmp_path / "ml_input" / "project_features.csv"
    base_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"project_id": ["P1", "P2"]}).to_csv(base_file, index=False)

    loader = FeatureLoaders(base_dir=str(tmp_path))
    datasets, metadata = loader.load_all(strict=False)

    assert "base_projects" in datasets
    assert datasets["base_projects"] is not None
    assert len(datasets["base_projects"]) == 2
    assert "cost_anomaly" in metadata["missing_files"]
