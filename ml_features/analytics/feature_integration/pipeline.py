"""
pipeline.py
===========
End-to-end integration pipeline coordinating loading, validation, aggregation,
safe merging, risk signal normalization, risk scoring, Explainable AI generation,
and audit report creation.
"""

from __future__ import annotations
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

import pandas as pd

from .schema import PRIMARY_KEY
from .loaders import FeatureLoaders
from .validators import FeatureValidators
from .aggregators import FeatureAggregators
from .feature_merger import FeatureMerger
from .risk_signal_builder import RiskSignalBuilder
from .risk_aggregator import RiskAggregator

logger = logging.getLogger("FeatureIntegration.Pipeline")


def run_feature_integration_pipeline(
    base_dir: Optional[str] = None,
    output_dir: Optional[str] = None,
    config_path: Optional[str] = None,
    strict: bool = False
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Execute the complete end-to-end Feature Integration & Aggregate Risk Pipeline.

    Parameters
    ----------
    base_dir : str, optional
        Base directory of ml_features. Defaults to workspace parent.
    output_dir : str, optional
        Output directory for generated CSVs and reports. Defaults to ml_outputs/.
    config_path : str, optional
        Path to risk_weights.json. Defaults to config/risk_weights.json.
    strict : bool, default=False
        If True, fails immediately on schema mismatches or missing optional files.

    Returns
    -------
    integrated_df : pd.DataFrame
        Full unified project feature table.
    risk_results_df : pd.DataFrame
        Evidence-ready decision table for FastAPI, React, and Power BI.
    report : Dict[str, Any]
        Audit summary report with match statistics and risk distributions.
    """
    start_time = time.time()
    if base_dir is None:
        base_dir = str(Path(__file__).resolve().parent.parent.parent)
    base_dir = os.path.abspath(base_dir)

    if output_dir is None:
        output_dir = os.path.join(base_dir, "ml_outputs")
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 1. Load weights configuration
    weights = None
    thresholds = None
    if config_path is None:
        cand_config = os.path.join(base_dir, "config", "risk_weights.json")
        if os.path.exists(cand_config):
            config_path = cand_config
        else:
            root_cand = os.path.join(os.path.dirname(base_dir), "config", "risk_weights.json")
            if os.path.exists(root_cand):
                config_path = root_cand

    if config_path and os.path.exists(config_path):
        logger.info(f"Loading risk configuration from: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            cfg_data = json.load(f)
            weights = cfg_data.get("weights")
            raw_thresh = cfg_data.get("risk_thresholds")
            if raw_thresh:
                thresholds = {k: (v[0], v[1]) for k, v in raw_thresh.items()}

    # 2. Load all available datasets
    loader = FeatureLoaders(base_dir=base_dir)
    datasets, load_meta = loader.load_all(strict=strict)

    base_projects_df = datasets.get("base_projects")
    if base_projects_df is None or base_projects_df.empty:
        raise FileNotFoundError("Base project features dataset could not be loaded!")

    initial_project_count = len(base_projects_df)
    logger.info(f"Loaded {initial_project_count} base projects.")

    # 3. Aggregate 1:N rule events
    rule_results_df = datasets.get("rule_results")
    rule_aggregated_df = None
    if rule_results_df is not None and not rule_results_df.empty:
        rule_aggregated_df = FeatureAggregators.aggregate_rule_results(rule_results_df)

    # 4. Aggregate pairwise similarity
    similarity_pairs_df = datasets.get("similarity_pairs")
    pair_aggregated_df = None
    if similarity_pairs_df is not None and not similarity_pairs_df.empty:
        pair_aggregated_df = FeatureAggregators.aggregate_pairwise_similarity(similarity_pairs_df)

    # 5. Execute Safe Merge
    merger = FeatureMerger(primary_key=PRIMARY_KEY, strict=strict)
    merged_df, merge_stats = merger.merge_all(
        base_projects_df=base_projects_df,
        cost_df=datasets.get("cost_anomaly"),
        delay_df=datasets.get("delay_predictions"),
        iforest_df=datasets.get("isolation_forest"),
        payment_df=datasets.get("payment_anomaly"),
        rule_flagged_df=datasets.get("rule_flagged"),
        rule_aggregated_df=rule_aggregated_df,
        similarity_df=datasets.get("similarity_projects"),
        pair_similarity_df=pair_aggregated_df
    )

    # 6. Standardize Risk Signals
    signaled_df = RiskSignalBuilder.build_signals(merged_df)

    # 7. Aggregate Risk and Synthesize Explainable AI
    aggregator = RiskAggregator(weights=weights, thresholds=thresholds)
    final_df = aggregator.aggregate_dataset(signaled_df)

    # 8. Create Evidence-Ready Project Risk Results Table
    evidence_cols = [
        "project_id",
        "mp_name",
        "state",
        "constituency",
        "category",
        "recommended_amount",
        "total_expenditure",
        "expenditure_ratio",
        "is_completed",
        "overall_risk_score",
        "risk_category",
        "audit_explanation",
        "top_risk_signals",
        "risk_factors",
        "evidence_payload",
        "cost_risk_score",
        "cost_risk_flag",
        "cost_available",
        "delay_risk_score",
        "delay_risk_flag",
        "delay_available",
        "payment_risk_score",
        "payment_risk_flag",
        "payment_available",
        "rule_risk_score",
        "rule_risk_flag",
        "rule_available",
        "similarity_risk_score",
        "similarity_risk_flag",
        "similarity_available",
        "iforest_risk_score",
        "iforest_risk_flag",
        "iforest_available"
    ]
    # Filter to only existing columns
    available_evidence_cols = [c for c in evidence_cols if c in final_df.columns]
    project_risk_results = final_df[available_evidence_cols].copy()

    # 9. Write outputs
    integrated_features_path = os.path.join(output_dir, "integrated_project_features.csv")
    project_risk_results_path = os.path.join(output_dir, "project_risk_results.csv")
    report_path = os.path.join(output_dir, "integration_report.json")

    logger.info(f"Writing integrated project features to: {integrated_features_path}")
    final_df.to_csv(integrated_features_path, index=False)

    logger.info(f"Writing project risk decision table to: {project_risk_results_path}")
    project_risk_results.to_csv(project_risk_results_path, index=False)

    # 10. Generate Integration & Audit Report
    risk_dist = final_df["risk_category"].value_counts().to_dict()
    elapsed_seconds = round(time.time() - start_time, 2)

    report: Dict[str, Any] = {
        "execution_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": elapsed_seconds,
        "total_projects": initial_project_count,
        "final_project_count": len(final_df),
        "cardinality_preserved": bool(initial_project_count == len(final_df) == final_df[PRIMARY_KEY].nunique()),
        "duplicate_keys": int(len(final_df) - final_df[PRIMARY_KEY].nunique()),
        "matched_features": {k: v.get("matched_rows", 0) for k, v in merge_stats.items()},
        "coverage_percentages": {k: v.get("coverage_pct", 0.0) for k, v in merge_stats.items()},
        "missing_features": load_meta.get("missing_files", []),
        "risk_distribution": risk_dist,
        "risk_distribution_percentages": {k: round((v / len(final_df)) * 100.0, 2) for k, v in risk_dist.items()},
        "weights_applied": aggregator.weights,
        "output_files": {
            "integrated_features": integrated_features_path,
            "project_risk_results": project_risk_results_path,
            "integration_report": report_path
        }
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Integration report saved to: {report_path}")

    return final_df, project_risk_results, report
