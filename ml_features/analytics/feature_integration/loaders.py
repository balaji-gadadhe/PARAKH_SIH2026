"""
loaders.py
==========
Robust, safe dataset loaders for ML outputs, rule outputs, and similarity engines.
Handles missing files gracefully according to strict/lenient policy.
"""

from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

import pandas as pd

from .schema import DEFAULT_FILE_MAP

logger = logging.getLogger("FeatureIntegration.Loaders")

REQUIRED_KEYS = ["base_projects"]
OPTIONAL_KEYS = [
    "cost_anomaly",
    "delay_predictions",
    "isolation_forest",
    "payment_anomaly",
    "rule_flagged",
    "rule_results",
    "similarity_projects",
    "similarity_pairs",
    "agency_profiles"
]


class FeatureLoaders:
    """Safe loader class that handles relative/absolute path resolution and missing files."""

    def __init__(self, base_dir: Optional[str] = None, custom_file_map: Optional[Dict[str, str]] = None):
        if base_dir is None:
            # Default to parent directory of analytics/feature_integration -> ml_features
            base_dir = str(Path(__file__).resolve().parent.parent.parent)
        self.base_dir = os.path.abspath(base_dir)
        self.file_map = dict(DEFAULT_FILE_MAP)
        if custom_file_map:
            self.file_map.update(custom_file_map)

    def resolve_path(self, rel_or_abs_path: str) -> str:
        """Resolve a file path against base_dir if it's relative."""
        if os.path.isabs(rel_or_abs_path):
            return rel_or_abs_path
        # First check inside base_dir
        candidate = os.path.join(self.base_dir, rel_or_abs_path)
        if os.path.exists(candidate):
            return candidate
        # Also check repo root (one level up) if base_dir is ml_features
        parent_candidate = os.path.join(os.path.dirname(self.base_dir), rel_or_abs_path)
        if os.path.exists(parent_candidate):
            return parent_candidate
        return candidate

    def load_single(self, key: str, strict: bool = False) -> Tuple[Optional[pd.DataFrame], bool, str]:
        """Load a single dataset by key.
        Returns: (df_or_none, is_loaded, resolved_path)
        """
        rel_path = self.file_map.get(key)
        if not rel_path:
            msg = f"Unknown dataset key: '{key}'"
            if strict:
                raise KeyError(msg)
            logger.warning(msg)
            return None, False, ""

        full_path = self.resolve_path(rel_path)
        if not os.path.exists(full_path):
            if strict or key in REQUIRED_KEYS:
                raise FileNotFoundError(f"Required dataset '{key}' not found at: {full_path}")
            logger.warning(f"Optional dataset '{key}' not found at: {full_path}. Will mark as unavailable.")
            return None, False, full_path

        try:
            df = pd.read_csv(full_path, low_memory=False)
            logger.info(f"Loaded '{key}' ({len(df)} rows, {len(df.columns)} cols) from: {full_path}")
            return df, True, full_path
        except Exception as e:
            if strict or key in REQUIRED_KEYS:
                raise RuntimeError(f"Error loading dataset '{key}' from {full_path}: {e}") from e
            logger.error(f"Failed reading optional dataset '{key}' ({e}). Treating as unavailable.")
            return None, False, full_path

    def load_all(self, strict: bool = False) -> Tuple[Dict[str, Optional[pd.DataFrame]], Dict[str, Any]]:
        """Load all registered datasets.
        Returns:
            datasets: Dict mapping key -> DataFrame or None
            metadata: Dict recording load status and paths
        """
        datasets: Dict[str, Optional[pd.DataFrame]] = {}
        metadata: Dict[str, Any] = {
            "loaded_files": {},
            "missing_files": [],
            "row_counts": {}
        }

        for key in list(REQUIRED_KEYS) + list(OPTIONAL_KEYS):
            df, is_loaded, path = self.load_single(key, strict=strict)
            datasets[key] = df
            if is_loaded and df is not None:
                metadata["loaded_files"][key] = path
                metadata["row_counts"][key] = len(df)
            else:
                metadata["missing_files"].append(key)

        return datasets, metadata
