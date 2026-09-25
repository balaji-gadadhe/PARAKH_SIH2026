"""
run_feature_integration.py
==========================
CLI entry point to execute the Unified Feature Integration & Aggregate Risk Pipeline.

Usage:
    python scripts/run_feature_integration.py
    python scripts/run_feature_integration.py --strict
    python scripts/run_feature_integration.py --output-dir ml_outputs --config config/risk_weights.json
"""

from __future__ import annotations
import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add ml_features directory to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from analytics.feature_integration.pipeline import run_feature_integration_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("RunFeatureIntegration")


def print_banner() -> None:
    print("=" * 80)
    print("      PARAKH - UNIFIED FEATURE INTEGRATION & AGGREGATE RISK ENGINE")
    print("=" * 80)


def print_summary(report: dict) -> None:
    print("\n" + "=" * 80)
    print("                         INTEGRATION PIPELINE REPORT")
    print("=" * 80)
    print(f"  Execution Time        : {report.get('elapsed_seconds', 0)} seconds")
    print(f"  Total Projects In     : {report.get('total_projects', 0):,}")
    print(f"  Final Projects Out    : {report.get('final_project_count', 0):,}")
    print(f"  Cardinality Preserved : {report.get('cardinality_preserved', False)} (1 row = 1 project)")
    print(f"  Duplicate Keys Found  : {report.get('duplicate_keys', 0)}")
    print("-" * 80)
    print("  FEATURE COVERAGE:")
    matched = report.get("matched_features", {})
    cov = report.get("coverage_percentages", {})
    for feat, count in matched.items():
        pct = cov.get(feat, 0.0)
        print(f"    - {feat:<28}: {count:>7,} projects ({pct:>5.1f}%)")
    print("-" * 80)
    print("  RISK DISTRIBUTION (TIERS):")
    dist = report.get("risk_distribution", {})
    dist_pct = report.get("risk_distribution_percentages", {})
    for tier in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        cnt = dist.get(tier, 0)
        pct = dist_pct.get(tier, 0.0)
        bar = "█" * int(pct // 2.5)
        print(f"    - {tier:<10}: {cnt:>7,} ({pct:>5.1f}%) | {bar}")
    print("-" * 80)
    print("  OUTPUT DELIVERABLES:")
    outputs = report.get("output_files", {})
    for name, path in outputs.items():
        print(f"    - {name:<20}: {path}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run Feature Integration & Risk Aggregation Pipeline.")
    parser.add_argument("--base-dir", type=str, default=str(BASE_DIR), help="Root directory of ml_features")
    parser.add_argument("--output-dir", type=str, default=os.path.join(BASE_DIR, "ml_outputs"), help="Output directory")
    parser.add_argument("--config", type=str, default=None, help="Path to risk_weights.json")
    parser.add_argument("--strict", action="store_true", help="Fail if any optional feature is missing or malformed")

    args = parser.parse_args()

    print_banner()
    logger.info(f"Starting integration pipeline with base_dir={args.base_dir}, output_dir={args.output_dir}, strict={args.strict}")

    try:
        final_df, risk_df, report = run_feature_integration_pipeline(
            base_dir=args.base_dir,
            output_dir=args.output_dir,
            config_path=args.config,
            strict=args.strict
        )
        print_summary(report)
        logger.info("Pipeline completed successfully.")
        return 0
    except Exception as e:
        logger.exception(f"Pipeline failed with error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
