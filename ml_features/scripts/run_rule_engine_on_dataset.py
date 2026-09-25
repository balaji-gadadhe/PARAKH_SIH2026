"""
run_rule_engine_on_dataset.py

MPLAD-Sentinel Real Dataset Rule Engine Runner.
Executes deterministic rule engine checks against the cleaned MPLADS dataset
(ml_input/project_features.csv) and produces audit and verification outputs.

Usage:
    python run_rule_engine_on_dataset.py [OPTIONS]

Options:
    --project_id <ID>     Filter and display findings for a specific project
    --rule_id <RULE_ID>   Filter and display projects triggering a specific rule
    --severity <SEV>      Filter by severity ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')
    --risk_band <BAND>    Filter by risk band ('CRITICAL_RISK', 'HIGH_RISK', 'MEDIUM_RISK', 'LOW_RISK')
    --limit <N>           Limit display output (default: 20)
    --export-all-results  Export both triggered and non-triggered rule evaluations to rule_results.csv (default: triggered only)
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

# Ensure root workspace is on path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from analytics.rule_engine.threshold_checks import (
    build_rule_result,
    get_severity_score,
    safe_float,
    safe_int,
)
from analytics.rule_engine.compliance_rules import (
    check_missing_critical_fields,
    check_invalid_status,
    check_invalid_progress,
    check_negative_financials,
    check_invalid_dates,
    check_completed_progress_mismatch,
    check_completed_missing_completion_date,
    check_payment_expenditure_inconsistency,
    evaluate_all_compliance_rules,
)
from analytics.rule_engine.progress_gap_rules import (
    calculate_expected_progress,
    calculate_progress_gap,
    check_expected_progress_rule,
    check_significant_progress_gap,
    check_progress_duration_mismatch,
    evaluate_all_progress_gap_rules,
)
from analytics.rule_engine.ghost_stalled_detection import (
    check_no_progress_stalled,
    check_expenditure_progress_mismatch,
    check_active_project_inactivity,
    check_stalled_project_composite,
    evaluate_all_ghost_stalled_rules,
)

OUTPUT_DIR = os.path.join(ROOT_DIR, "ml_outputs", "rules")


def load_dataset() -> pd.DataFrame:
    """Loads and prepares the project features and similarity datasets."""
    proj_path = os.path.join(ROOT_DIR, "ml_input", "project_features.csv")
    sim_path = os.path.join(ROOT_DIR, "ml_input", "project_similarity_data.csv")

    if not os.path.exists(proj_path):
        raise FileNotFoundError(f"Missing required dataset: {proj_path}")

    print(f"[*] Loading primary project features from: {proj_path}")
    df_proj = pd.read_csv(proj_path)
    print(f"    Loaded {len(df_proj):,} project records with {len(df_proj.columns)} columns.")

    if os.path.exists(sim_path):
        print(f"[*] Merging description text from: {sim_path}")
        df_sim = pd.read_csv(sim_path, usecols=["project_id", "work_description", "clean_description"])
        df = pd.merge(df_proj, df_sim, on="project_id", how="left")
    else:
        df = df_proj
        df["work_description"] = None
        df["clean_description"] = None

    return df


def evaluate_single_project(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Executes the Rule Engine against a single real dataset project record.
    Preserves explainability and avoids fabricating unavailable features.
    """
    pid = str(row.get("project_id", "UNKNOWN"))
    is_comp = safe_int(row.get("is_completed"), default=0)
    status_str = "completed" if is_comp == 1 else "ongoing"

    rec_amt = row.get("recommended_amount")
    tot_exp = row.get("total_expenditure")
    exp_ratio = safe_float(row.get("expenditure_ratio"), default=0.0)
    days_since_rec = safe_float(row.get("days_since_recommendation"))
    rec_to_comp_days = safe_float(row.get("recommendation_to_completion_days"))
    
    cat = str(row.get("category", "")).strip() if pd.notnull(row.get("category")) else ""
    const = str(row.get("constituency", "")).strip() if pd.notnull(row.get("constituency")) else ""
    work_desc = row.get("work_description") or (f"{cat} in {const}" if (cat or const) else "")

    max_pay = row.get("maximum_payment")
    avg_pay = row.get("average_payment")
    pay_cnt = safe_int(row.get("payment_count"), default=0)
    
    # Calculate disbursed payments if payment aggregates exist
    if pd.notnull(avg_pay) and pay_cnt and pay_cnt > 0:
        total_payments = float(pay_cnt) * float(avg_pay)
    else:
        total_payments = tot_exp

    proj_payload = {
        "project_id": pid,
        "project_name": work_desc if work_desc else None,
        "sanctioned_amount": rec_amt,
        "actual_expenditure": tot_exp,
        "status": status_str,
        "progress_percentage": None,  # Explicitly unavailable in cleaned source
        "location": f"{const}, {row.get('state', '')}".strip(", "),
        "implementing_agency": None,  # Not recorded in source master
        "total_payments": total_payments,
        "payment_amount": max_pay,
        "average_payment": avg_pay,
        "maximum_payment": max_pay,
        "minimum_payment": row.get("minimum_payment"),
        "final_amount": row.get("final_amount"),
        "start_date": None,
        "completion_date": None,
        "expected_completion_date": None,
        "last_progress_update": None,
        "recommendation_to_completion_days": rec_to_comp_days,
        "days_since_recommendation": days_since_rec,
    }

    findings: List[Dict[str, Any]] = []

    # -------------------------------------------------------------
    # 1. COMPLIANCE RULES
    # -------------------------------------------------------------
    # COMPLIANCE-001: Missing critical fields
    findings.append(check_missing_critical_fields(proj_payload))

    # COMPLIANCE-002: Invalid status
    findings.append(check_invalid_status(status_str))

    # COMPLIANCE-003: Invalid progress percentage (safely handles None)
    findings.append(check_invalid_progress(None))

    # COMPLIANCE-004: Negative financial values
    findings.append(check_negative_financials(proj_payload))

    # COMPLIANCE-005: Date chronology validation
    # If recommendation_to_completion_days is negative, completion preceded recommendation!
    if rec_to_comp_days is not None and rec_to_comp_days < 0:
        findings.append(build_rule_result(
            rule_id="COMPLIANCE-005",
            rule_name="Invalid dates chronology",
            category="COMPLIANCE",
            triggered=True,
            severity="HIGH",
            message=f"Chronological error: Recorded completion date preceded recommendation date by {abs(int(rec_to_comp_days))} days.",
            evidence={
                "recommendation_to_completion_days": rec_to_comp_days,
                "anomaly_type": "completion_before_recommendation",
            },
        ))
    else:
        findings.append(check_invalid_dates(start_date=None, completion_date=None))

    # COMPLIANCE-006: Completed project with progress < 100%
    findings.append(check_completed_progress_mismatch(status=status_str, progress_percentage=None))

    # COMPLIANCE-007: Completed project with missing completion date
    if is_comp == 1:
        has_comp_days = rec_to_comp_days is not None
        findings.append(build_rule_result(
            rule_id="COMPLIANCE-007",
            rule_name="Completed project with missing completion date",
            category="COMPLIANCE",
            triggered=not has_comp_days,
            severity="MEDIUM",
            message="Project is marked 'completed' but completion interval data is missing." if not has_comp_days else "Project is marked 'completed' with recorded completion duration.",
            evidence={"status": "completed", "has_completion_record": has_comp_days, "recommendation_to_completion_days": rec_to_comp_days},
        ))
    else:
        findings.append(check_completed_missing_completion_date(status=status_str, completion_date=None))

    # COMPLIANCE-008: Payment / expenditure inconsistency
    findings.append(check_payment_expenditure_inconsistency(
        actual_expenditure=tot_exp,
        total_payments=total_payments,
        payment_amount=max_pay,
    ))

    # -------------------------------------------------------------
    # 2. GHOST / STALLED DETECTION RULES
    # -------------------------------------------------------------
    # GHOST-001: No-progress detection (requires progress, safely handles None)
    findings.append(check_no_progress_stalled(progress_percentage=None))

    # GHOST-002: Expenditure-progress / budget overrun mismatch
    f_tot_exp = safe_float(tot_exp, default=0.0)
    f_rec_amt = safe_float(rec_amt, default=0.0)
    if exp_ratio is not None and exp_ratio > 1.0 and f_rec_amt > 0:
        overrun_pct = round((exp_ratio - 1.0) * 100.0, 2)
        sev = "CRITICAL" if exp_ratio >= 1.5 else "HIGH"
        findings.append(build_rule_result(
            rule_id="GHOST-002",
            rule_name="Expenditure-progress mismatch",
            category="GHOST_STALLED",
            triggered=True,
            severity=sev,
            message=(
                f"High expenditure relative to budget: INR {f_tot_exp:,.2f} spent "
                f"exceeds sanctioned amount (INR {f_rec_amt:,.2f}) by {overrun_pct}% "
                f"(expenditure_ratio={round(exp_ratio, 4)})."
            ),
            evidence={
                "actual_expenditure": f_tot_exp,
                "sanctioned_amount": f_rec_amt,
                "expenditure_ratio": round(exp_ratio, 4),
                "overrun_percentage": overrun_pct,
            },
        ))
    else:
        findings.append(check_expenditure_progress_mismatch(tot_exp, rec_amt, None))

    # GHOST-003: Active project with no recent activity
    if is_comp == 0 and days_since_rec is not None and days_since_rec >= 90:
        g3_sev = "HIGH" if days_since_rec >= 180 else "MEDIUM"
        findings.append(build_rule_result(
            rule_id="GHOST-003",
            rule_name="Active project with no recent activity",
            category="GHOST_STALLED",
            triggered=True,
            severity=g3_sev,
            message=(
                f"Project is marked as 'ongoing' but has had no completion or update for "
                f"{int(days_since_rec)} days (inactivity threshold: 90 days)."
            ),
            evidence={
                "status": "ongoing",
                "days_since_recommendation": days_since_rec,
                "inactivity_threshold_days": 90,
            },
        ))
    else:
        findings.append(check_active_project_inactivity(status=status_str, last_progress_update=None))

    # GHOST-004: Stalled project composite (safely handles None progress)
    findings.append(check_stalled_project_composite(
        progress_percentage=None,
        last_progress_update=None,
        start_date=None,
        expected_completion_date=None,
    ))

    # -------------------------------------------------------------
    # 3. PROGRESS GAP RULES (Safely handles None progress)
    # -------------------------------------------------------------
    findings.append(check_expected_progress_rule(start_date=None, expected_completion_date=None))
    findings.append(check_significant_progress_gap(expected_progress=None, actual_progress=None))
    findings.append(check_progress_duration_mismatch(start_date=None, expected_completion_date=None, actual_progress=None))

    return findings


def calculate_project_risk(triggered_findings: List[Dict[str, Any]]) -> Tuple[int, str]:
    """
    Computes aggregated risk score and risk band from triggered rules.
    Bands:
      - CRITICAL_RISK: Score >= 120 or any CRITICAL rule triggered
      - HIGH_RISK: Score >= 70 or any HIGH rule triggered
      - MEDIUM_RISK: Score >= 40 or any MEDIUM rule triggered
      - LOW_RISK: Score > 0
      - CLEAN: Score == 0
    """
    if not triggered_findings:
        return 0, "CLEAN"

    total_score = sum(f.get("score", 0) for f in triggered_findings)
    severities = {f.get("severity", "LOW") for f in triggered_findings}

    if "CRITICAL" in severities or total_score >= 120:
        band = "CRITICAL_RISK"
    elif "HIGH" in severities or total_score >= 70:
        band = "HIGH_RISK"
    elif "MEDIUM" in severities or total_score >= 40:
        band = "MEDIUM_RISK"
    else:
        band = "LOW_RISK"

    return total_score, band


def run_pipeline(export_all: bool = False) -> Dict[str, Any]:
    """
    Main pipeline execution against the real dataset.
    Generates all 4 required CSV outputs in rule_outputs/.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df = load_dataset()
    total_projects = len(df)

    print(f"\n[*] Executing Rule Engine across {total_projects:,} projects...")
    t0 = time.time()

    records = df.to_dict(orient="records")

    rule_results_rows: List[Dict[str, Any]] = []
    flagged_projects_rows: List[Dict[str, Any]] = []
    verification_input_rows: List[Dict[str, Any]] = []

    # Rule summary statistics counters
    rule_stats: Dict[str, Dict[str, Any]] = {}

    risk_band_counts = {
        "CRITICAL_RISK": 0,
        "HIGH_RISK": 0,
        "MEDIUM_RISK": 0,
        "LOW_RISK": 0,
        "CLEAN": 0,
    }

    total_triggers = 0
    projects_with_anomalies = 0

    for idx, row in enumerate(records):
        pid = str(row.get("project_id", "UNKNOWN"))
        try:
            findings = evaluate_single_project(row)
            exec_status = "SUCCESS"
        except Exception as err:
            exec_status = f"ERROR: {str(err)}"
            findings = []

        triggered_findings = [f for f in findings if f.get("triggered", False)]
        total_triggers += len(triggered_findings)

        if triggered_findings:
            projects_with_anomalies += 1

        tot_score, risk_band = calculate_project_risk(triggered_findings)
        risk_band_counts[risk_band] += 1

        # Track rule stats & append to rule_results
        for f in findings:
            rid = f["rule_id"]
            rname = f["rule_name"]
            is_trig = f.get("triggered", False)
            sev = f.get("severity", "LOW")

            if rid not in rule_stats:
                rule_stats[rid] = {
                    "rule_id": rid,
                    "rule_name": rname,
                    "projects_checked": 0,
                    "projects_triggered": 0,
                    "severity_counts": {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0},
                }

            rule_stats[rid]["projects_checked"] += 1
            if is_trig:
                rule_stats[rid]["projects_triggered"] += 1
                rule_stats[rid]["severity_counts"][sev] = rule_stats[rid]["severity_counts"].get(sev, 0) + 1

            if is_trig or export_all:
                rule_results_rows.append({
                    "project_id": pid,
                    "rule_id": rid,
                    "rule_name": rname,
                    "triggered": is_trig,
                    "severity": sev if is_trig else "NONE",
                    "reason": f.get("message", ""),
                    "evidence_value": json.dumps(f.get("evidence", {}), default=str),
                    "threshold": json.dumps({k: v for k, v in f.get("evidence", {}).items() if "threshold" in k}),
                    "execution_status": exec_status,
                })

        # Flagged project entry
        if triggered_findings:
            rules_trig_str = ";".join(f["rule_id"] for f in triggered_findings)
            top_reasons_str = " | ".join(f["message"] for f in triggered_findings[:3])
            flagged_projects_rows.append({
                "project_id": pid,
                "rules_triggered": rules_trig_str,
                "rule_count": len(triggered_findings),
                "rule_risk_score": tot_score,
                "risk_band": risk_band,
                "top_reasons": top_reasons_str,
            })

            # Verification Engine handoff entry
            evidence_aggregate = {f["rule_id"]: f["evidence"] for f in triggered_findings}
            verification_input_rows.append({
                "project_id": pid,
                "rule_risk_score": tot_score,
                "risk_band": risk_band,
                "rules_triggered": rules_trig_str,
                "rule_count": len(triggered_findings),
                "top_reasons": top_reasons_str,
                "rule_evidence": json.dumps(evidence_aggregate, default=str),
                # Preserved source features
                "mp_name": row.get("mp_name"),
                "state": row.get("state"),
                "constituency": row.get("constituency"),
                "category": row.get("category"),
                "recommended_amount": row.get("recommended_amount"),
                "final_amount": row.get("final_amount"),
                "total_expenditure": row.get("total_expenditure"),
                "expenditure_ratio": row.get("expenditure_ratio"),
                "payment_count": row.get("payment_count"),
                "days_since_recommendation": row.get("days_since_recommendation"),
                "is_completed": row.get("is_completed"),
                "description_similarity_score": row.get("description_similarity_score"),
                "peer_median_cost": row.get("peer_median_cost"),
                "cost_deviation_from_peer": row.get("cost_deviation_from_peer"),
                # Placeholders for future Evidence/Verification Engine components
                "ml_anomaly_score": None,
                "cost_anomaly_score": None,
                "delay_anomaly_score": None,
                "payment_anomaly_score": None,
                "similarity_anomaly_score": None,
                "gps_verification_status": None,
                "image_verification_status": None,
                "vendor_risk_score": None,
            })

    elapsed = time.time() - t0
    print(f"[*] Processed all {total_projects:,} projects in {elapsed:.2f} seconds ({total_projects/elapsed:,.0f} proj/sec).")

    # -------------------------------------------------------------
    # Write CSV Outputs
    # -------------------------------------------------------------
    # 1. rule_results.csv
    rule_results_file = os.path.join(OUTPUT_DIR, "rule_results.csv")
    pd.DataFrame(rule_results_rows).to_csv(rule_results_file, index=False)
    print(f"    [+] Generated: {rule_results_file} ({len(rule_results_rows):,} rows)")

    # 2. flagged_projects.csv
    flagged_projects_file = os.path.join(OUTPUT_DIR, "flagged_projects.csv")
    df_flagged = pd.DataFrame(flagged_projects_rows)
    df_flagged.sort_values(by=["rule_risk_score", "rule_count"], ascending=[False, False], inplace=True)
    df_flagged.to_csv(flagged_projects_file, index=False)
    print(f"    [+] Generated: {flagged_projects_file} ({len(df_flagged):,} rows)")

    # 3. rule_summary.csv
    summary_rows = []
    for rid, s in rule_stats.items():
        trig = s["projects_triggered"]
        chk = s["projects_checked"]
        rate = round((trig / chk) * 100.0, 2) if chk > 0 else 0.0
        summary_rows.append({
            "rule_id": rid,
            "rule_name": s["rule_name"],
            "projects_checked": chk,
            "projects_triggered": trig,
            "trigger_rate": rate,
            "severity_distribution": json.dumps(s["severity_counts"]),
        })
    df_summary = pd.DataFrame(summary_rows).sort_values(by="projects_triggered", ascending=False)
    rule_summary_file = os.path.join(OUTPUT_DIR, "rule_summary.csv")
    df_summary.to_csv(rule_summary_file, index=False)
    print(f"    [+] Generated: {rule_summary_file} ({len(df_summary):,} rules)")

    # 4. verification_input.csv
    verification_input_file = os.path.join(OUTPUT_DIR, "verification_input.csv")
    df_ver = pd.DataFrame(verification_input_rows)
    df_ver.sort_values(by=["rule_risk_score", "rule_count"], ascending=[False, False], inplace=True)
    df_ver.to_csv(verification_input_file, index=False)
    print(f"    [+] Generated: {verification_input_file} ({len(df_ver):,} rows)")

    # Clean projects count
    clean_projects = total_projects - projects_with_anomalies

    summary_payload = {
        "total_projects": total_projects,
        "projects_with_anomalies": projects_with_anomalies,
        "total_triggers": total_triggers,
        "clean_projects": clean_projects,
        "risk_band_counts": risk_band_counts,
        "df_summary": df_summary,
        "df_flagged": df_flagged,
    }

    return summary_payload


def print_final_report(summary: Dict[str, Any]) -> None:
    """Prints the comprehensive final report to the console."""
    tot = summary["total_projects"]
    anom = summary["projects_with_anomalies"]
    trig = summary["total_triggers"]
    clean = summary["clean_projects"]
    bands = summary["risk_band_counts"]
    df_summary: pd.DataFrame = summary["df_summary"]
    df_flagged: pd.DataFrame = summary["df_flagged"]

    print("\n" + "=" * 80)
    print("                MPLAD-SENTINEL REAL DATASET EXECUTION REPORT")
    print("=" * 80)
    print(f"Total projects checked       : {tot:,}")
    print(f"Total projects with anomalies: {anom:,} ({anom/tot*100:.2f}%)")
    print(f"Total rule triggers          : {trig:,}")
    print(f"Clean projects               : {clean:,} ({clean/tot*100:.2f}%)")
    print(f"Critical-risk projects       : {bands['CRITICAL_RISK']:,} ({bands['CRITICAL_RISK']/tot*100:.2f}%)")
    print(f"High-risk projects           : {bands['HIGH_RISK']:,} ({bands['HIGH_RISK']/tot*100:.2f}%)")
    print(f"Medium-risk projects         : {bands['MEDIUM_RISK']:,} ({bands['MEDIUM_RISK']/tot*100:.2f}%)")
    print(f"Low-risk projects            : {bands['LOW_RISK']:,} ({bands['LOW_RISK']/tot*100:.2f}%)")
    print("-" * 80)

    print("\nTop 10 Rules by Number of Triggered Projects:")
    print("-" * 80)
    print(f"{'Rule ID':<16} {'Rule Name':<42} {'Triggered':<10} {'Rate (%)':<8}")
    print("-" * 80)
    for _, row in df_summary.head(10).iterrows():
        print(f"{row['rule_id']:<16} {row['rule_name']:<42} {row['projects_triggered']:<10,d} {row['trigger_rate']:<8.2f}%")

    print("\nTop 20 Highest-Risk Projects:")
    print("-" * 80)
    print(f"{'Rank':<5} {'Project ID':<45} {'Score':<7} {'Band':<15} {'Rules':<6}")
    print("-" * 80)
    for rank, (_, row) in enumerate(df_flagged.head(20).iterrows(), 1):
        pid_short = str(row['project_id'])[:42] + "..." if len(str(row['project_id'])) > 45 else str(row['project_id'])
        print(f"{rank:<5} {pid_short:<45} {row['rule_risk_score']:<7} {row['risk_band']:<15} {row['rule_count']:<6}")
    print("=" * 80 + "\n")


def filter_and_display(
    project_id: Optional[str] = None,
    rule_id: Optional[str] = None,
    severity: Optional[str] = None,
    risk_band: Optional[str] = None,
    limit: int = 20,
) -> None:
    """Helper to inspect filtered results from the output CSVs."""
    res_path = os.path.join(OUTPUT_DIR, "rule_results.csv")
    flag_path = os.path.join(OUTPUT_DIR, "flagged_projects.csv")

    if not os.path.exists(res_path) or not os.path.exists(flag_path):
        print("[!] Output files not found. Running pipeline first...")
        run_pipeline()

    if project_id:
        print(f"\n[*] Querying Project ID: '{project_id}'")
        df_res = pd.read_csv(res_path)
        p_res = df_res[df_res["project_id"] == project_id]
        if p_res.empty:
            print(f"    No findings found for project ID: {project_id}")
        else:
            print(f"    Found {len(p_res)} rule findings:")
            for idx, (_, r) in enumerate(p_res.iterrows(), 1):
                print(f"    [{idx}] {r['rule_id']}: {r['rule_name']} | Severity: {r['severity']}")
                print(f"        Reason  : {r['reason']}")
                print(f"        Evidence: {r['evidence_value']}\n")

    if rule_id:
        print(f"\n[*] Querying Rule ID: '{rule_id}'")
        df_res = pd.read_csv(res_path)
        r_res = df_res[(df_res["rule_id"] == rule_id) & (df_res["triggered"] == True)]
        print(f"    Total projects triggered by {rule_id}: {len(r_res):,}")
        print(f"    Displaying first {min(limit, len(r_res))} projects:")
        for idx, (_, r) in enumerate(r_res.head(limit).iterrows(), 1):
            print(f"    [{idx}] Project: {r['project_id']}")
            print(f"        Reason  : {r['reason']}")
            print(f"        Evidence: {r['evidence_value']}\n")

    if severity:
        sev_upper = severity.upper()
        print(f"\n[*] Querying Severity: '{sev_upper}'")
        df_res = pd.read_csv(res_path)
        s_res = df_res[(df_res["severity"] == sev_upper) & (df_res["triggered"] == True)]
        print(f"    Total triggers with severity {sev_upper}: {len(s_res):,}")
        print(f"    Displaying first {min(limit, len(s_res))} findings:")
        for idx, (_, r) in enumerate(s_res.head(limit).iterrows(), 1):
            print(f"    [{idx}] {r['rule_id']} on {r['project_id']}")
            print(f"        Reason: {r['reason']}\n")

    if risk_band:
        band_upper = risk_band.upper()
        print(f"\n[*] Querying Risk Band: '{band_upper}'")
        df_flag = pd.read_csv(flag_path)
        b_res = df_flag[df_flag["risk_band"] == band_upper]
        print(f"    Total projects in {band_upper}: {len(b_res):,}")
        print(f"    Displaying first {min(limit, len(b_res))} projects:")
        for idx, (_, r) in enumerate(b_res.head(limit).iterrows(), 1):
            print(f"    [{idx}] Project: {r['project_id']} | Score: {r['rule_risk_score']} | Rules: {r['rules_triggered']}")
            print(f"        Top Reasons: {r['top_reasons']}\n")


def main():
    parser = argparse.ArgumentParser(description="MPLAD-Sentinel Real Dataset Rule Engine Runner")
    parser.add_argument("--project_id", type=str, help="Inspect findings for a specific project_id")
    parser.add_argument("--rule_id", type=str, help="Filter projects that triggered a specific rule_id")
    parser.add_argument("--severity", type=str, help="Filter findings by severity (CRITICAL, HIGH, MEDIUM, LOW)")
    parser.add_argument("--risk_band", type=str, help="Filter projects by risk band (CRITICAL_RISK, HIGH_RISK, etc.)")
    parser.add_argument("--limit", type=int, default=20, help="Max items to display when filtering (default: 20)")
    parser.add_argument("--export-all-results", action="store_true", help="Export both triggered and non-triggered rules to rule_results.csv")

    args = parser.parse_args()

    # If filter flags provided, execute filter view
    if args.project_id or args.rule_id or args.severity or args.risk_band:
        filter_and_display(
            project_id=args.project_id,
            rule_id=args.rule_id,
            severity=args.severity,
            risk_band=args.risk_band,
            limit=args.limit,
        )
    else:
        # Full pipeline execution
        summary = run_pipeline(export_all=args.export_all_results)
        print_final_report(summary)


if __name__ == "__main__":
    main()
