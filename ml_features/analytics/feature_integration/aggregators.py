"""
aggregators.py
==============
Aggregation routines to convert 1:N and event-level outputs (rule events,
pairwise similarities, payments, and vendors) into strictly 1-row-per-project records.
"""

from __future__ import annotations
import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .schema import PRIMARY_KEY

logger = logging.getLogger("FeatureIntegration.Aggregators")

SEVERITY_ORDER: Dict[str, int] = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "UNKNOWN": 0
}

SEVERITY_WEIGHTS: Dict[str, float] = {
    "CRITICAL": 75.0,
    "HIGH": 50.0,
    "MEDIUM": 25.0,
    "LOW": 10.0,
    "UNKNOWN": 0.0
}


class FeatureAggregators:
    """Aggregators converting many-to-one entity signals to strictly project-level features."""

    @staticmethod
    def aggregate_rule_results(rule_results_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate event-level rule results (151k rows) into single-row-per-project records.

        Columns produced:
        - project_id
        - rule_event_count: total triggered rule instances
        - max_rule_severity: highest severity string (CRITICAL > HIGH > MEDIUM > LOW)
        - max_rule_severity_score: numeric severity score
        - rule_ids_triggered: semicolon-delimited unique rule IDs
        - rule_reasons_summary: concatenated unique trigger reasons
        """
        if rule_results_df.empty:
            return pd.DataFrame(columns=[
                PRIMARY_KEY, "rule_event_count", "max_rule_severity",
                "max_rule_severity_score", "rule_ids_triggered", "rule_reasons_summary"
            ])

        df = rule_results_df.copy()
        if "triggered" in df.columns:
            df = df[df["triggered"] == 1]
            if df.empty:
                return pd.DataFrame(columns=[
                    PRIMARY_KEY, "rule_event_count", "max_rule_severity",
                    "max_rule_severity_score", "rule_ids_triggered", "rule_reasons_summary"
                ])

        # Map severity to numeric order for safe max calculation
        df["severity_clean"] = df.get("severity", "LOW").fillna("LOW").astype(str).str.upper()
        df["sev_order"] = df["severity_clean"].map(lambda s: SEVERITY_ORDER.get(s, 1))
        df["sev_weight"] = df["severity_clean"].map(lambda s: SEVERITY_WEIGHTS.get(s, 10.0))

        # Sort so max severity is first per project
        df = df.sort_values(by=[PRIMARY_KEY, "sev_order"], ascending=[True, False])

        def _join_unique(series: pd.Series) -> str:
            vals = [str(x).strip() for x in series.dropna().unique() if str(x).strip() and str(x) != "nan"]
            return "; ".join(vals)

        grouped = df.groupby(PRIMARY_KEY, as_index=False).agg(
            rule_event_count=("rule_id", "count"),
            max_rule_severity=("severity_clean", "first"),
            max_rule_severity_score=("sev_weight", "max"),
            rule_ids_triggered=("rule_id", _join_unique),
            rule_reasons_summary=("reason", _join_unique)
        )

        logger.info(f"Aggregated {len(rule_results_df)} rule event rows into {len(grouped)} project records.")
        return grouped

    @staticmethod
    def aggregate_pairwise_similarity(pairs_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate project-pair similarity results (50k pairs) into single project records.

        Symmetrically considers project_id_a and project_id_b to ensure every involved
        project receives its duplicate risk attributes.

        Columns produced:
        - project_id
        - pair_duplicate_count: number of duplicate pairings involving this project
        - max_pair_similarity_score: highest similarity score across pairs
        - max_pair_risk_score: highest combined pair risk score
        - pair_exact_text_flag: boolean indicator of verbatim duplicate match
        - pair_critical_geo_flag: boolean indicator of cross-constituency / critical geo duplicate
        """
        if pairs_df.empty or "project_id_a" not in pairs_df.columns:
            return pd.DataFrame(columns=[
                PRIMARY_KEY, "pair_duplicate_count", "max_pair_similarity_score",
                "max_pair_risk_score", "pair_exact_text_flag", "pair_critical_geo_flag"
            ])

        # Extract projection from perspective A
        cols_a = {
            "project_id_a": PRIMARY_KEY,
            "similarity_score": "sim",
            "pair_risk_score": "risk",
            "exact_text_duplicate_flag": "exact_txt",
            "geo_risk_label": "geo_label"
        }
        avail_a = {k: v for k, v in cols_a.items() if k in pairs_df.columns}
        df_a = pairs_df[list(avail_a.keys())].rename(columns=avail_a)

        # Extract projection from perspective B
        cols_b = {
            "project_id_b": PRIMARY_KEY,
            "similarity_score": "sim",
            "pair_risk_score": "risk",
            "exact_text_duplicate_flag": "exact_txt",
            "geo_risk_label": "geo_label"
        }
        avail_b = {k: v for k, v in cols_b.items() if k in pairs_df.columns}
        df_b = pairs_df[list(avail_b.keys())].rename(columns=avail_b)

        combined = pd.concat([df_a, df_b], ignore_index=True).dropna(subset=[PRIMARY_KEY])
        if combined.empty:
            return pd.DataFrame(columns=[
                PRIMARY_KEY, "pair_duplicate_count", "max_pair_similarity_score",
                "max_pair_risk_score", "pair_exact_text_flag", "pair_critical_geo_flag"
            ])

        combined["sim"] = pd.to_numeric(combined.get("sim", 0.0), errors="coerce").fillna(0.0)
        combined["risk"] = pd.to_numeric(combined.get("risk", 0.0), errors="coerce").fillna(0.0)
        combined["exact_txt"] = pd.to_numeric(combined.get("exact_txt", 0), errors="coerce").fillna(0).astype(int)
        combined["is_crit_geo"] = combined.get("geo_label", "").fillna("").astype(str).str.contains("CRITICAL_GEO").astype(int)

        grouped = combined.groupby(PRIMARY_KEY, as_index=False).agg(
            pair_duplicate_count=("sim", "count"),
            max_pair_similarity_score=("sim", "max"),
            max_pair_risk_score=("risk", "max"),
            pair_exact_text_flag=("exact_txt", "max"),
            pair_critical_geo_flag=("is_crit_geo", "max")
        )

        logger.info(f"Aggregated {len(pairs_df)} pairwise rows into {len(grouped)} project-level similarity records.")
        return grouped
