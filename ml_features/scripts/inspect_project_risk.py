"""
inspect_project_risk.py
=======================
Interactive CLI tool to test and inspect risk predictions against the dataset.

Usage:
    python scripts/inspect_project_risk.py
    python scripts/inspect_project_risk.py --limit 5
    python scripts/inspect_project_risk.py --tier CRITICAL
    python scripts/inspect_project_risk.py --state Gujarat
    python scripts/inspect_project_risk.py --project-id "161333|Gumma Thanuja Rani|ARAKU|Andhra Pradesh"
    python scripts/inspect_project_risk.py --compare
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

# Fix Windows console UTF-8 output
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
RESULTS_PATH = BASE_DIR / "ml_outputs" / "project_risk_results.csv"


def format_inr(val):
    if pd.isna(val) or val is None:
        return "N/A"
    try:
        v = float(val)
        if v >= 10000000:
            return f"₹{v / 10000000:.2f} Cr"
        elif v >= 100000:
            return f"₹{v / 100000:.2f} Lakh"
        else:
            return f"₹{v:,.0f}"
    except Exception:
        return str(val)


def display_project_card(r: pd.Series, rank: int | None = None) -> None:
    pid = r.get("project_id", "Unknown")
    score = r.get("overall_risk_score", 0.0)
    tier = r.get("risk_category", "UNKNOWN")
    mp = r.get("mp_name", "N/A")
    state = r.get("state", "N/A")
    constituency = r.get("constituency", "N/A")
    category = r.get("category", "N/A")
    rec_amt = format_inr(r.get("recommended_amount"))
    exp_amt = format_inr(r.get("total_expenditure"))
    ratio = r.get("expenditure_ratio", 0.0)
    ratio_str = f"{ratio * 100:.1f}%" if pd.notna(ratio) else "N/A"
    completed = "Yes (Completed)" if r.get("is_completed", 0) == 1 else "No (Ongoing / Stalled)"

    tier_color = {
        "CRITICAL": "[CRITICAL RISK]",
        "HIGH": "[HIGH RISK]",
        "MEDIUM": "[MEDIUM RISK]",
        "LOW": "[LOW RISK]"
    }.get(tier, f"[{tier}]")

    header = f"#{rank} " if rank is not None else ""
    print("=" * 80)
    print(f" {header}PROJECT: {pid}")
    print("=" * 80)
    print(f"  Risk Status          : {tier_color} (Overall Score: {score:.4f} / 1.00)")
    print(f"  Location / MP        : MP {mp} | {constituency}, {state}")
    print(f"  Project Category     : {category}")
    print(f"  Financials           : Sanctioned: {rec_amt} | Spent: {exp_amt} (Utilized: {ratio_str})")
    print(f"  Physical Status      : {completed}")
    print("-" * 80)
    print(f"  Audit Explanation    : {r.get('audit_explanation', 'N/A')}")
    print(f"  Top Risk Signals     : {r.get('top_risk_signals', 'N/A')}")
    print("-" * 80)
    print("  Engine Sub-Scores (0.0 to 1.0 scale):")
    engines = [
        ("Cost Anomaly Engine", r.get("cost_risk_score"), r.get("cost_risk_flag")),
        ("Delay Prediction Model", r.get("delay_risk_score"), r.get("delay_risk_flag")),
        ("Payment Anomaly Detector", r.get("payment_risk_score"), r.get("payment_risk_flag")),
        ("Compliance & Ghost Rules", r.get("rule_risk_score"), r.get("rule_risk_flag")),
        ("Duplicate Work Similarity", r.get("similarity_risk_score"), r.get("similarity_risk_flag")),
        ("Multivariate Isolation Forest", r.get("iforest_risk_score"), r.get("iforest_risk_flag")),
    ]
    for name, sc, flg in engines:
        sc_val = f"{float(sc):.2f}" if pd.notna(sc) else "N/A"
        flg_val = "🚩 FLAGGED" if flg else "✅ Normal"
        print(f"    - {name:<30}: Score {sc_val:>4} | {flg_val}")

    print("-" * 80)
    print("  Concrete Risk Indicators / Evidence Drivers:")
    factors_raw = r.get("risk_factors", "[]")
    try:
        factors = json.loads(factors_raw) if isinstance(factors_raw, str) else factors_raw
        if isinstance(factors, list):
            for idx, factor in enumerate(factors, start=1):
                print(f"    {idx}. {factor}")
        else:
            print(f"    - {factors}")
    except Exception:
        print(f"    - {factors_raw}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Inspect Risk Predictions against MPLADS Dataset.")
    parser.add_argument("--tier", type=str, choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"], help="Filter by risk tier")
    parser.add_argument("--state", type=str, help="Filter by State name (case-insensitive substring)")
    parser.add_argument("--project-id", type=str, help="Inspect a specific project_id")
    parser.add_argument("--limit", type=int, default=5, help="Number of projects to display (default: 5)")
    parser.add_argument("--compare", action="store_true", help="Compare 2 Critical-risk cases vs 2 Clean Low-risk cases")

    args = parser.parse_args()

    if not RESULTS_PATH.exists():
        print(f"Error: Results file not found at: {RESULTS_PATH}")
        print("Please run `python scripts/run_feature_integration.py` first.")
        return 1

    print(f"Loading prediction results from: {RESULTS_PATH} ...")
    df = pd.read_csv(RESULTS_PATH)
    print(f"Loaded {len(df):,} total projects from the dataset.\n")

    if args.project_id:
        match = df[df["project_id"].str.contains(args.project_id, case=False, na=False)]
        if match.empty:
            print(f"No project found matching ID: '{args.project_id}'")
            return 1
        for _, r in match.iterrows():
            display_project_card(r)
        return 0

    if args.compare:
        print("\n" + "#" * 80)
        print("                SIDE-BY-SIDE COMPARISON: HIGH-RISK vs CLEAN PROJECTS")
        print("#" * 80 + "\n")
        print(">>> 1. TOP CRITICAL / HIGH-RISK PROJECTS:")
        crit = df[df["risk_category"] == "CRITICAL"].sort_values("overall_risk_score", ascending=False).head(2)
        for idx, (_, r) in enumerate(crit.iterrows(), start=1):
            display_project_card(r, rank=idx)

        print(">>> 2. VERIFIED CLEAN / LOW-RISK PROJECTS:")
        low = df[df["risk_category"] == "LOW"].sort_values("overall_risk_score", ascending=True).head(2)
        for idx, (_, r) in enumerate(low.iterrows(), start=1):
            display_project_card(r, rank=idx)
        return 0

    # Default filtered view
    subset = df
    if args.tier:
        subset = subset[subset["risk_category"] == args.tier.upper()]
    if args.state:
        subset = subset[subset["state"].str.contains(args.state, case=False, na=False)]

    subset = subset.sort_values("overall_risk_score", ascending=False)

    if subset.empty:
        print("No projects found matching the specified filters.")
        return 0

    print(f"Displaying Top {min(args.limit, len(subset))} projects sorted by overall risk score:")
    for idx, (_, r) in enumerate(subset.head(args.limit).iterrows(), start=1):
        display_project_card(r, rank=idx)

    return 0


if __name__ == "__main__":
    sys.exit(main())
