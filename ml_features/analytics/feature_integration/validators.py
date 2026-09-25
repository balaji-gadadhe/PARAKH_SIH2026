"""
validators.py
=============
Validation routines for key integrity, duplicate detection, score bounds,
null checks, and post-merge cardinality verification.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

from .schema import PRIMARY_KEY, SCHEMA_REQUIREMENTS

logger = logging.getLogger("FeatureIntegration.Validators")


class FeatureValidators:
    """Validator class for input datasets, keys, and merged feature tables."""

    @staticmethod
    def validate_schema(df: pd.DataFrame, dataset_name: str, strict: bool = True) -> Tuple[bool, List[str]]:
        """Verify that all required columns are present in the DataFrame."""
        required = SCHEMA_REQUIREMENTS.get(dataset_name, [])
        missing = [c for c in required if c not in df.columns]
        if missing:
            msg = f"Dataset '{dataset_name}' is missing required columns: {missing}"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False, missing
        return True, []

    @staticmethod
    def validate_primary_key(
        df: pd.DataFrame,
        dataset_name: str,
        key_col: str = PRIMARY_KEY,
        allow_duplicates: bool = False,
        strict: bool = True
    ) -> Tuple[bool, Dict[str, Any]]:
        """Validate key existence, nulls, and uniqueness."""
        report: Dict[str, Any] = {
            "dataset": dataset_name,
            "key_col": key_col,
            "has_key": key_col in df.columns,
            "null_count": 0,
            "duplicate_count": 0,
            "unique_keys": 0,
            "total_rows": len(df)
        }

        if not report["has_key"]:
            msg = f"Dataset '{dataset_name}' does not contain primary key column '{key_col}'."
            if strict:
                raise KeyError(msg)
            logger.error(msg)
            return False, report

        report["null_count"] = int(df[key_col].isna().sum())
        if report["null_count"] > 0:
            msg = f"Dataset '{dataset_name}' has {report['null_count']} null values in '{key_col}'."
            if strict:
                raise ValueError(msg)
            logger.warning(msg)

        report["unique_keys"] = int(df[key_col].nunique())
        report["duplicate_count"] = len(df) - report["unique_keys"]
        if report["duplicate_count"] > 0 and not allow_duplicates:
            msg = (
                f"Dataset '{dataset_name}' contains {report['duplicate_count']} duplicate '{key_col}' rows! "
                f"Total rows: {len(df)}, Unique keys: {report['unique_keys']}."
            )
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False, report

        return True, report

    @staticmethod
    def validate_score_bounds(
        df: pd.DataFrame,
        column: str,
        min_val: float = 0.0,
        max_val: float = 1.0,
        strict: bool = False
    ) -> Tuple[bool, str]:
        """Verify numeric score values are bounded within [min_val, max_val]."""
        if column not in df.columns:
            return True, "Column not present"

        series = pd.to_numeric(df[column], errors='coerce').dropna()
        if series.empty:
            return True, "All values null/empty"

        c_min = float(series.min())
        c_max = float(series.max())
        has_inf = np.isinf(series).any()

        if has_inf:
            msg = f"Score column '{column}' contains infinite values."
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False, msg

        # Allow minor floating point rounding tolerance (1e-4)
        if c_min < (min_val - 1e-4) or c_max > (max_val + 1e-4):
            msg = f"Score column '{column}' outside expected bounds [{min_val}, {max_val}]. Observed: [{c_min:.4f}, {c_max:.4f}]."
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False, msg

        return True, "Valid"

    @staticmethod
    def validate_merge_cardinality(
        base_df: pd.DataFrame,
        merged_df: pd.DataFrame,
        key_col: str = PRIMARY_KEY,
        strict: bool = True
    ) -> bool:
        """Guarantee ONE ROW = ONE PROJECT by checking length and key count preservation."""
        base_len = len(base_df)
        merged_len = len(merged_df)

        if base_len != merged_len:
            msg = (
                f"Row explosion detected! Base dataset had {base_len} rows, but merged dataset has {merged_len} rows. "
                f"A one-to-many join or duplicate key occurred."
            )
            if strict:
                raise ValueError(msg)
            logger.critical(msg)
            return False

        merged_unique = merged_df[key_col].nunique()
        if merged_unique != merged_len:
            msg = f"Merged dataset has duplicate '{key_col}' values: {merged_len - merged_unique} duplicates found."
            if strict:
                raise ValueError(msg)
            logger.critical(msg)
            return False

        logger.info(f"Cardinality check passed: exactly {merged_len} unique project rows preserved.")
        return True
