"""
run_early_warning_pipeline.py
==============================
Post-processing step: runs trend analysis, alert generation, and agency risk
wiring after the main integration pipeline has produced project_risk_results.csv.

Usage:
    cd ml_features
    python scripts/run_early_warning_pipeline.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Ensure UTF-8 on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("EarlyWarningPipeline")

import pandas as pd

from analytics.early_warning.trend_analysis import TrendAnalyzer
from analytics.early_warning.alert_generator import AlertGenerator


def main():
    start = time.time()
    output_dir = BASE_DIR / "ml_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Trend Analysis ──────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 1: Running trend analysis on project features...")
    logger.info("=" * 60)

    project_features_path = BASE_DIR / "ml_input" / "project_features.csv"
    if not project_features_path.exists():
        logger.error(f"Project features not found: {project_features_path}")
        return

    projects_df = pd.read_csv(project_features_path, low_memory=False)
    logger.info(f"Loaded {len(projects_df):,} projects for trend analysis")

    analyzer = TrendAnalyzer()
    trends_df = analyzer.analyze_trends(projects_df)

    trends_path = output_dir / "project_trend_analysis.csv"
    trends_df.to_csv(trends_path, index=False)
    logger.info(f"Trend analysis written: {trends_path} ({len(trends_df):,} rows)")

    # Summary
    burn_counts = trends_df["burn_rate_status"].value_counts()
    logger.info("Burn rate distribution:")
    for status, count in burn_counts.items():
        logger.info(f"  {status}: {count:,}")

    # ── 2. Alert Generation ────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 2: Generating early warning alerts...")
    logger.info("=" * 60)

    risk_results_path = output_dir / "project_risk_results.csv"
    if not risk_results_path.exists():
        logger.error(f"Risk results not found: {risk_results_path}")
        logger.error("Run the integration pipeline first: python scripts/run_feature_integration.py")
        return

    risk_df = pd.read_csv(risk_results_path, low_memory=False)
    logger.info(f"Loaded {len(risk_df):,} risk results")

    generator = AlertGenerator()
    alerts_df = generator.generate_alerts(risk_df, trends_df)

    alerts_path = output_dir / "early_warning_alerts.csv"
    alerts_path.parent.mkdir(parents=True, exist_ok=True)
    alerts_df.to_csv(alerts_path, index=False)
    logger.info(f"Alerts written: {alerts_path} ({len(alerts_df):,} alerts)")

    if not alerts_df.empty:
        sev_counts = alerts_df["alert_severity"].value_counts()
        logger.info("Alert severity distribution:")
        for sev, count in sev_counts.items():
            logger.info(f"  {sev}: {count:,}")

    # ── 3. Wire Agency Risk Scores ─────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 3: Wiring agency risk scores into risk results...")
    logger.info("=" * 60)

    agency_path = output_dir / "agency_profiles.csv"
    master_works_path = BASE_DIR.parent / "data" / "master" / "master_works.csv"

    if agency_path.exists() and master_works_path.exists():
        agency_df = pd.read_csv(agency_path, low_memory=False)
        master_df = pd.read_csv(master_works_path, usecols=["project_id", "primary_vendor"], low_memory=False)

        # Build agency lookup: agency_id → risk_score, risk_level
        agency_lookup = agency_df.set_index("agency_id")[["agency_risk_score", "agency_risk_level"]].to_dict("index")

        # Map vendor → agency risk
        def get_agency_risk(vendor):
            if pd.isna(vendor) or str(vendor).strip() == "":
                return None, None
            info = agency_lookup.get(str(vendor).strip(), None)
            if info:
                return info.get("agency_risk_score"), info.get("agency_risk_level")
            return None, None

        master_df["vendor_risk_score"], master_df["vendor_risk_level"] = zip(
            *master_df["primary_vendor"].apply(get_agency_risk)
        )

        # Merge into risk results
        agency_cols = master_df[["project_id", "vendor_risk_score", "vendor_risk_level"]]
        risk_with_agency = risk_df.merge(agency_cols, on="project_id", how="left")

        # Overwrite risk results with agency-enriched version
        risk_with_agency.to_csv(risk_results_path, index=False)
        logger.info(f"Risk results enriched with agency risk scores ({len(risk_with_agency):,} rows, {len(risk_with_agency.columns)} cols)")

        vendor_matched = risk_with_agency["vendor_risk_score"].notna().sum()
        logger.info(f"Projects with agency risk data: {vendor_matched:,} / {len(risk_with_agency):,} ({vendor_matched/len(risk_with_agency)*100:.1f}%)")
    else:
        logger.warning("Agency profiles or master_works not found — skipping agency wiring")

    elapsed = round(time.time() - start, 2)
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"Early warning pipeline complete in {elapsed}s")
    logger.info(f"  Trends:   {trends_path}")
    logger.info(f"  Alerts:   {alerts_path} ({len(alerts_df):,} alerts)")
    logger.info(f"  Agency:   enriched {risk_results_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
