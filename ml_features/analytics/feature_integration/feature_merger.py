"""
feature_merger.py
=================
Safe join orchestrator executing verified left-joins onto base project master data.
Guarantees ONE ROW = ONE PROJECT by preventing column collisions and detecting row explosions.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd

from .schema import PRIMARY_KEY
from .validators import FeatureValidators

logger = logging.getLogger("FeatureIntegration.Merger")


class FeatureMerger:
    """Safe join engine guaranteeing strict preservation of project cardinality."""

    def __init__(self, primary_key: str = PRIMARY_KEY, strict: bool = True):
        self.primary_key = primary_key
        self.strict = strict
        self.merge_stats: Dict[str, Any] = {}

    def safe_left_join(
        self,
        base_df: pd.DataFrame,
        incoming_df: Optional[pd.DataFrame],
        feature_name: str,
        select_cols: Optional[List[str]] = None,
        col_rename_map: Optional[Dict[str, str]] = None
    ) -> pd.DataFrame:
        """Safely left-join an incoming feature DataFrame onto base_df.

        Guarantees:
        1. Base length is preserved.
        2. No duplicate keys are introduced.
        3. Column collisions (e.g. mp_name_x, mp_name_y) are prevented.
        4. Match statistics are tracked.
        """
        initial_rows = len(base_df)

        if incoming_df is None or incoming_df.empty:
            logger.warning(f"Feature '{feature_name}' is None or empty. Skipping join.")
            self.merge_stats[feature_name] = {
                "status": "unavailable",
                "matched_rows": 0,
                "unmatched_rows": initial_rows,
                "coverage_pct": 0.0
            }
            return base_df

        # Validate incoming primary key
        FeatureValidators.validate_primary_key(
            incoming_df,
            dataset_name=feature_name,
            key_col=self.primary_key,
            allow_duplicates=False,
            strict=self.strict
        )

        df_to_join = incoming_df.copy()

        # Select specific columns if requested
        if select_cols:
            actual_cols = [c for c in select_cols if c in df_to_join.columns]
            if self.primary_key not in actual_cols:
                actual_cols = [self.primary_key] + actual_cols
            df_to_join = df_to_join[actual_cols]

        # Apply renames if specified
        if col_rename_map:
            df_to_join = df_to_join.rename(columns=col_rename_map)

        # Drop overlapping columns with base_df (except primary_key) to avoid _x / _y
        overlapping = [c for c in df_to_join.columns if c in base_df.columns and c != self.primary_key]
        if overlapping:
            logger.debug(f"Dropping overlapping metadata columns from '{feature_name}': {overlapping}")
            df_to_join = df_to_join.drop(columns=overlapping)

        # Execute safe left merge
        merged = base_df.merge(df_to_join, on=self.primary_key, how="left")

        # Verify cardinality
        FeatureValidators.validate_merge_cardinality(base_df, merged, key_col=self.primary_key, strict=self.strict)

        # Record match statistics
        matched = int(merged[self.primary_key].isin(incoming_df[self.primary_key]).sum())
        unmatched = initial_rows - matched
        coverage = (matched / initial_rows) * 100.0 if initial_rows > 0 else 0.0

        self.merge_stats[feature_name] = {
            "status": "matched",
            "matched_rows": matched,
            "unmatched_rows": unmatched,
            "coverage_pct": round(coverage, 2)
        }
        logger.info(f"Joined '{feature_name}': {matched}/{initial_rows} projects matched ({coverage:.1f}% coverage).")

        return merged

    def merge_all(
        self,
        base_projects_df: pd.DataFrame,
        cost_df: Optional[pd.DataFrame] = None,
        delay_df: Optional[pd.DataFrame] = None,
        iforest_df: Optional[pd.DataFrame] = None,
        payment_df: Optional[pd.DataFrame] = None,
        rule_flagged_df: Optional[pd.DataFrame] = None,
        rule_aggregated_df: Optional[pd.DataFrame] = None,
        similarity_df: Optional[pd.DataFrame] = None,
        pair_similarity_df: Optional[pd.DataFrame] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Orchestrate all individual feature joins onto base project records."""
        base_df = base_projects_df.copy()
        FeatureValidators.validate_primary_key(base_df, "base_projects", self.primary_key, allow_duplicates=False, strict=True)

        logger.info(f"Beginning feature integration across {len(base_df)} base projects...")

        # 1. Cost Anomaly
        merged = self.safe_left_join(
            base_df, cost_df, "cost_anomaly",
            select_cols=[
                "project_id", "cost_anomaly_score", "is_cost_anomaly",
                "cost_anomaly_type", "cost_z_score", "cost_deviation_from_peer", "peer_median_cost"
            ]
        )

        # 2. Delay Predictions
        merged = self.safe_left_join(
            merged, delay_df, "delay_predictions",
            select_cols=[
                "project_id", "delay_risk_score", "delay_risk_level",
                "is_delayed_predicted", "predicted_completion_days"
            ]
        )

        # 3. Isolation Forest
        merged = self.safe_left_join(
            merged, iforest_df, "isolation_forest",
            select_cols=[
                "project_id", "anomaly_score", "anomaly_label", "is_anomaly", "top_anomaly_drivers"
            ],
            col_rename_map={
                "anomaly_score": "iforest_score",
                "is_anomaly": "iforest_is_anomaly"
            }
        )

        # 4. Payment Anomaly
        merged = self.safe_left_join(
            merged, payment_df, "payment_anomaly",
            select_cols=[
                "project_id", "payment_anomaly_score", "is_payment_anomaly",
                "payment_anomaly_type", "round_payment_indicator", "payment_frequency_indicator",
                "budget_payment_ratio", "peer_payment_deviation"
            ]
        )

        # 5. Rule Flagged Projects
        merged = self.safe_left_join(
            merged, rule_flagged_df, "rule_flagged",
            select_cols=[
                "project_id", "rule_risk_score", "risk_band", "rules_triggered", "rule_count", "top_reasons"
            ],
            col_rename_map={
                "rule_risk_score": "raw_rule_risk_score",
                "risk_band": "rule_risk_band",
                "top_reasons": "rule_top_reasons"
            }
        )

        # 6. Aggregated Rule Results (Detailed event stats)
        if rule_aggregated_df is not None and not rule_aggregated_df.empty:
            merged = self.safe_left_join(
                merged, rule_aggregated_df, "rule_aggregated_events",
                select_cols=[
                    "project_id", "rule_event_count", "max_rule_severity",
                    "max_rule_severity_score", "rule_ids_triggered", "rule_reasons_summary"
                ]
            )

        # 7. Similarity Project Features
        merged = self.safe_left_join(
            merged, similarity_df, "similarity_projects",
            select_cols=[
                "project_id", "max_similarity_score", "duplicate_count",
                "exact_text_duplicate_flag", "high_text_similarity_flag",
                "generic_template_pair_flag", "cross_mp_duplicate_flag",
                "same_constituency_duplicate_flag", "duplicate_risk_score"
            ]
        )

        # 8. Aggregated Pairwise Similarity (if provided)
        if pair_similarity_df is not None and not pair_similarity_df.empty:
            merged = self.safe_left_join(
                merged, pair_similarity_df, "similarity_pair_aggregates",
                select_cols=[
                    "project_id", "pair_duplicate_count", "max_pair_similarity_score",
                    "max_pair_risk_score", "pair_exact_text_flag", "pair_critical_geo_flag"
                ]
            )

        logger.info(f"Feature merge complete. Final table contains {len(merged)} rows, {len(merged.columns)} columns.")
        return merged, self.merge_stats
