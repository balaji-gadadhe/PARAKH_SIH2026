"""
analytics/similarity_engine/cost_similarity.py
================================================
Cost divergence analysis for MPLAD-Sentinel similarity engine.

For project pairs with high text similarity (>=85%), flags cases where:
  - One project's budget is >2x the other's (Budget Inflation Anomaly).
  - A project deviates significantly from its peer-group median cost.

Usage:
    from analytics.similarity_engine.cost_similarity import CostSimilarityAnalyser
    csa = CostSimilarityAnalyser()
    pairs_df = csa.annotate_pairs(pairs_df, project_features_df)
    report   = csa.compute_peer_deviation(project_features_df)
"""
from __future__ import annotations
import logging
import numpy as np
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)

# Thresholds
BUDGET_INFLATION_RATIO_THRESHOLD: float = 2.0   # max/min > 2x → anomalous
HIGH_SIM_THRESHOLD_FOR_COST_CHECK: float = 0.85  # Only check costs for high-sim pairs
PEER_DEVIATION_CRITICAL_Z: float = 3.0           # Z-score > 3 → CRITICAL_COST
PEER_DEVIATION_HIGH_Z: float     = 2.0           # Z-score 2-3 → HIGH_COST


class CostSimilarityAnalyser:
    """
    Analyses cost discrepancy between similar project pairs and computes
    peer-group cost deviation for each project.
    """

    @staticmethod
    def _safe_ratio(a: float, b: float) -> float:
        """
        Compute max(a, b) / min(a, b) safely.
        Returns 0.0 if either value is zero, negative, or missing.
        """
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            return 0.0
        if a <= 0 or b <= 0:
            return 0.0
        return round(max(a, b) / min(a, b), 4)

    @staticmethod
    def _budget_anomaly_label(ratio: float) -> str:
        if ratio <= 0:
            return "MISSING_COST"
        if ratio > 10.0:
            return "CRITICAL_BUDGET_INFLATION"
        if ratio > BUDGET_INFLATION_RATIO_THRESHOLD:
            return "HIGH_BUDGET_INFLATION"
        return "NORMAL_COST"

    # ── Pair-level annotation ─────────────────────────────────────────────────
    def annotate_pairs(
        self,
        pairs_df: pd.DataFrame,
        project_features_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Join recommended_amount from project_features onto duplicate pairs
        and compute cost_ratio and budget_anomaly_label.

        Parameters
        ----------
        pairs_df : pd.DataFrame
            Output of TextSimilarityEngine.find_duplicate_pairs().
            Must have: project_id_a, project_id_b, similarity_score.
        project_features_df : pd.DataFrame
            Must have: project_id, recommended_amount.

        Returns
        -------
        pd.DataFrame with added columns:
            cost_a, cost_b, cost_ratio, budget_anomaly_label
        """
        if pairs_df.empty:
            for col in ["cost_a", "cost_b", "cost_ratio", "budget_anomaly_label"]:
                pairs_df[col] = pd.Series(dtype=object)
            return pairs_df

        cost_map = dict(zip(
            project_features_df["project_id"],
            pd.to_numeric(project_features_df["recommended_amount"], errors="coerce").fillna(0.0),
        ))

        pairs_df = pairs_df.copy()
        pairs_df["cost_a"] = pairs_df["project_id_a"].map(cost_map).fillna(0.0)
        pairs_df["cost_b"] = pairs_df["project_id_b"].map(cost_map).fillna(0.0)

        pairs_df["cost_ratio"] = pairs_df.apply(
            lambda r: self._safe_ratio(r["cost_a"], r["cost_b"]), axis=1
        )

        # Only flag budget inflation when text similarity is genuinely high
        pairs_df["budget_anomaly_label"] = pairs_df.apply(
            lambda r: (
                self._budget_anomaly_label(r["cost_ratio"])
                if r["similarity_score"] >= HIGH_SIM_THRESHOLD_FOR_COST_CHECK
                else "NOT_CHECKED"
            ),
            axis=1,
        )

        flagged = (pairs_df["budget_anomaly_label"].isin(
            ["CRITICAL_BUDGET_INFLATION", "HIGH_BUDGET_INFLATION"]
        )).sum()
        logger.info("Cost annotated: %d pairs flagged for budget inflation.", flagged)
        return pairs_df

    # ── Project-level peer deviation ──────────────────────────────────────────
    def compute_peer_deviation(self, project_features_df: pd.DataFrame) -> pd.DataFrame:
        """
        For each project, compute Z-score of its recommended_amount
        within its (state, category) peer group.

        Parameters
        ----------
        project_features_df : pd.DataFrame
            Must have: project_id, recommended_amount, state, category.

        Returns
        -------
        pd.DataFrame with columns:
            project_id, recommended_amount, peer_median, peer_std,
            cost_z_score, cost_deviation_label, peer_deviation_score (0-1)
        """
        df = project_features_df[
            ["project_id", "recommended_amount", "state", "category"]
        ].copy()
        df["recommended_amount"] = pd.to_numeric(df["recommended_amount"], errors="coerce").fillna(0.0)

        # Peer group: (state, category)
        grp = df.groupby(["state", "category"])["recommended_amount"]
        df["peer_median"] = grp.transform("median")
        df["peer_std"]    = grp.transform("std").fillna(1.0)
        df["peer_std"]    = df["peer_std"].replace(0, 1.0)  # Avoid zero-division

        df["cost_z_score"] = (df["recommended_amount"] - df["peer_median"]) / df["peer_std"]
        df["cost_z_score"] = df["cost_z_score"].round(4)

        # Label
        def _label(z: float) -> str:
            az = abs(z)
            if az >= PEER_DEVIATION_CRITICAL_Z:    return "CRITICAL_COST"
            if az >= PEER_DEVIATION_HIGH_Z:         return "HIGH_COST"
            if az >= 1.0:                           return "MEDIUM_COST"
            return "NORMAL_COST"

        df["cost_deviation_label"] = df["cost_z_score"].apply(_label)

        # Normalised 0-1 peer deviation score (capped at z=6 for scaling)
        df["peer_deviation_score"] = (
            df["cost_z_score"].abs().clip(upper=6.0) / 6.0
        ).round(4)

        critical = (df["cost_deviation_label"] == "CRITICAL_COST").sum()
        high     = (df["cost_deviation_label"] == "HIGH_COST").sum()
        logger.info(
            "Peer deviation: CRITICAL=%d (%.1f%%), HIGH=%d (%.1f%%)",
            critical, critical / len(df) * 100,
            high,     high     / len(df) * 100,
        )
        return df[[
            "project_id", "recommended_amount", "peer_median", "peer_std",
            "cost_z_score", "cost_deviation_label", "peer_deviation_score",
        ]].reset_index(drop=True)

    # ── Composite cost-similarity score ───────────────────────────────────────
    @staticmethod
    def pair_cost_risk_score(
        text_similarity: float,
        cost_ratio: float,
        geo_weight: float = 1.0,
    ) -> float:
        """
        Compute a single cost-risk score for a pair combining
        text similarity, cost ratio, and geographic weight.

        Score = text_similarity * cost_ratio_factor * geo_weight, capped at 1.0
        """
        if cost_ratio <= 1.0:
            cost_factor = 0.0
        elif cost_ratio >= 10.0:
            cost_factor = 1.0
        else:
            cost_factor = min(1.0, (cost_ratio - 1.0) / 9.0)

        raw = text_similarity * 0.6 + cost_factor * 0.4
        return round(min(1.0, raw * geo_weight), 4)
