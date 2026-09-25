"""
analytics/rule_engine/ghost_stalled_detection.py

Stalled, inactive, and ghost project detection rules for MPLAD-Sentinel.
Implements GHOST-001 through GHOST-004.
"""

from datetime import date
from typing import Any, Dict, List, Optional, Set

try:
    from analytics.rule_engine.threshold_checks import (
        build_rule_result,
        calculate_elapsed_days,
        calculate_ratio,
        parse_date,
        safe_float,
    )
except ImportError:
    from threshold_checks import (  # type: ignore
        build_rule_result,
        calculate_elapsed_days,
        calculate_ratio,
        parse_date,
        safe_float,
    )

ACTIVE_STATUS_SET: Set[str] = {
    "ongoing",
    "active",
    "in progress",
    "in-progress",
    "started",
}


def check_no_progress_stalled(
    progress_percentage: Any,
    last_progress_update: Any = None,
    start_date: Any = None,
    current_date: Any = None,
    low_progress_threshold: float = 5.0,
    stalled_days_threshold: int = 120,
) -> Dict[str, Any]:
    """
    GHOST-001: No-progress detection.

    Detects when a project has remained at zero or negligible progress
    for longer than a configurable number of days.

    Args:
        progress_percentage: Reported progress percentage.
        last_progress_update: Date of last progress report.
        start_date: Project start date (used if last_progress_update is missing).
        current_date: Evaluation reference date (defaults to today).
        low_progress_threshold: Max progress % considered negligible (default 5.0).
        stalled_days_threshold: Days of inactivity before flagging (default 120).

    Returns:
        Standard rule result dictionary.
    """
    f_prog = safe_float(progress_percentage)
    p_curr = parse_date(current_date) if current_date is not None else date.today()
    ref_date = parse_date(last_progress_update) or parse_date(start_date)

    if f_prog is None:
        return build_rule_result(
            rule_id="GHOST-001",
            rule_name="No-progress detection",
            category="GHOST_STALLED",
            triggered=False,
            severity="LOW",
            message="Progress percentage is missing; unable to evaluate no-progress rule.",
            evidence={"progress_percentage": None, "days_since_update": None},
        )

    if ref_date is None or p_curr is None:
        return build_rule_result(
            rule_id="GHOST-001",
            rule_name="No-progress detection",
            category="GHOST_STALLED",
            triggered=False,
            severity="LOW",
            message="Reference date (last update or start date) is missing; unable to calculate duration.",
            evidence={"progress_percentage": f_prog, "reference_date": None},
        )

    days_since_update = max(0, (p_curr - ref_date).days)
    is_low_progress = f_prog <= low_progress_threshold
    is_long_period = days_since_update >= stalled_days_threshold

    triggered = is_low_progress and is_long_period

    if triggered:
        message = (
            f"Project has shown no meaningful progress ({f_prog}%) for "
            f"{days_since_update} days (threshold: {stalled_days_threshold} days)."
        )
    else:
        message = (
            f"Project progress activity is within normal expectations "
            f"({f_prog}% progress, {days_since_update} days since update)."
        )

    return build_rule_result(
        rule_id="GHOST-001",
        rule_name="No-progress detection",
        category="GHOST_STALLED",
        triggered=triggered,
        severity="HIGH",
        message=message,
        evidence={
            "progress_percentage": f_prog,
            "days_since_update": days_since_update,
            "low_progress_threshold": low_progress_threshold,
            "stalled_days_threshold": stalled_days_threshold,
            "reference_date": str(ref_date),
            "current_date": str(p_curr),
        },
    )


def check_expenditure_progress_mismatch(
    actual_expenditure: Any,
    sanctioned_amount: Any,
    progress_percentage: Any,
    expenditure_ratio_threshold: float = 0.50,
    low_progress_threshold: float = 20.0,
) -> Dict[str, Any]:
    """
    GHOST-002: Expenditure-progress mismatch.

    Detects when financial expenditure is substantial relative to the sanctioned budget,
    while reported physical progress remains disproportionately low.

    Note: This is an analytical risk indicator, not a definitive declaration of fraud.

    Args:
        actual_expenditure: Disbursed or incurred expenditure.
        sanctioned_amount: Total approved/sanctioned budget.
        progress_percentage: Reported physical completion percentage.
        expenditure_ratio_threshold: Minimum expenditure ratio (default 0.50 = 50%).
        low_progress_threshold: Maximum progress percentage (default 20.0%).

    Returns:
        Standard rule result dictionary.
    """
    f_exp = safe_float(actual_expenditure)
    f_sanc = safe_float(sanctioned_amount)
    f_prog = safe_float(progress_percentage)

    if f_exp is None or f_sanc is None or f_prog is None:
        return build_rule_result(
            rule_id="GHOST-002",
            rule_name="Expenditure-progress mismatch",
            category="GHOST_STALLED",
            triggered=False,
            severity="LOW",
            message="Insufficient expenditure, sanctioned budget, or progress data to evaluate mismatch.",
            evidence={
                "actual_expenditure": f_exp,
                "sanctioned_amount": f_sanc,
                "progress_percentage": f_prog,
            },
        )

    exp_ratio = calculate_ratio(f_exp, f_sanc, default=0.0)
    exp_pct = round(exp_ratio * 100.0, 2)

    triggered = (exp_ratio >= expenditure_ratio_threshold) and (f_prog <= low_progress_threshold)

    # Escalated severity if expenditure >= 75% and progress <= 15%
    if exp_ratio >= 0.75 and f_prog <= 15.0:
        severity = "CRITICAL"
    else:
        severity = "HIGH"

    if triggered:
        message = (
            f"High expenditure with comparatively low reported progress: "
            f"INR {f_exp:,.2f} spent ({exp_pct}% of sanctioned INR {f_sanc:,.2f}) "
            f"with only {f_prog}% physical progress completed."
        )
    else:
        message = (
            f"Expenditure and progress relationship is within expected tolerance "
            f"({exp_pct}% budget spent, {f_prog}% progress)."
        )

    return build_rule_result(
        rule_id="GHOST-002",
        rule_name="Expenditure-progress mismatch",
        category="GHOST_STALLED",
        triggered=triggered,
        severity=severity,
        message=message,
        evidence={
            "actual_expenditure": f_exp,
            "sanctioned_amount": f_sanc,
            "expenditure_ratio": round(exp_ratio, 4),
            "expenditure_percentage": exp_pct,
            "progress_percentage": f_prog,
            "expenditure_ratio_threshold": expenditure_ratio_threshold,
            "low_progress_threshold": low_progress_threshold,
        },
    )


def check_active_project_inactivity(
    status: Any,
    last_progress_update: Any,
    start_date: Any = None,
    current_date: Any = None,
    max_inactive_days: int = 90,
) -> Dict[str, Any]:
    """
    GHOST-003: Active project with no recent activity.

    Flags projects recorded as ongoing or active that have had no reported
    updates or milestones for a configurable inactivity threshold.

    Args:
        status: Current recorded status.
        last_progress_update: Date of last recorded activity.
        start_date: Project commencement date (fallback if last_progress_update missing).
        current_date: Evaluation reference date (defaults to today).
        max_inactive_days: Inactivity threshold in days (default 90).

    Returns:
        Standard rule result dictionary.
    """
    norm_status = str(status).strip().lower() if status is not None else ""
    is_active = norm_status in ACTIVE_STATUS_SET
    p_curr = parse_date(current_date) if current_date is not None else date.today()
    ref_date = parse_date(last_progress_update) or parse_date(start_date)

    if not is_active:
        return build_rule_result(
            rule_id="GHOST-003",
            rule_name="Active project with no recent activity",
            category="GHOST_STALLED",
            triggered=False,
            severity="LOW",
            message=f"Project status is '{status}', not in active/ongoing states. Rule not triggered.",
            evidence={"status": status, "is_active": False},
        )

    if ref_date is None or p_curr is None:
        return build_rule_result(
            rule_id="GHOST-003",
            rule_name="Active project with no recent activity",
            category="GHOST_STALLED",
            triggered=False,
            severity="LOW",
            message="Active project is missing update and start dates; cannot measure inactivity period.",
            evidence={"status": status, "last_progress_update": None},
        )

    days_inactive = max(0, (p_curr - ref_date).days)
    triggered = days_inactive >= max_inactive_days

    severity = "HIGH" if days_inactive >= (max_inactive_days * 2) else "MEDIUM"

    if triggered:
        message = (
            f"Project is marked as '{status}' but has had no reported progress or updates for "
            f"{days_inactive} days (inactivity threshold: {max_inactive_days} days)."
        )
    else:
        message = (
            f"Active project has recent activity ({days_inactive} days since update, "
            f"within threshold of {max_inactive_days} days)."
        )

    return build_rule_result(
        rule_id="GHOST-003",
        rule_name="Active project with no recent activity",
        category="GHOST_STALLED",
        triggered=triggered,
        severity=severity,
        message=message,
        evidence={
            "status": status,
            "days_inactive": days_inactive,
            "max_inactive_days": max_inactive_days,
            "reference_date": str(ref_date),
            "current_date": str(p_curr),
        },
    )


def check_stalled_project_composite(
    progress_percentage: Any,
    last_progress_update: Any,
    start_date: Any,
    expected_completion_date: Any,
    current_date: Any = None,
    progress_threshold: float = 20.0,
    inactivity_days_threshold: int = 90,
    elapsed_duration_pct_threshold: float = 50.0,
) -> Dict[str, Any]:
    """
    GHOST-004: Stalled project indicator (Composite).

    Combines three signals to produce a robust stalled-project indicator:
    1. Low reported progress (<= progress_threshold)
    2. Long inactivity period (>= inactivity_days_threshold)
    3. Substantial elapsed project timeline (>= elapsed_duration_pct_threshold)

    Args:
        progress_percentage: Reported progress percentage.
        last_progress_update: Date of last recorded activity.
        start_date: Project commencement date.
        expected_completion_date: Scheduled completion date.
        current_date: Evaluation reference date.
        progress_threshold: Max progress % considered low (default: 20.0).
        inactivity_days_threshold: Minimum inactive days (default: 90).
        elapsed_duration_pct_threshold: Minimum elapsed duration % (default: 50.0).

    Returns:
        Standard rule result dictionary.
    """
    f_prog = safe_float(progress_percentage)
    p_curr = parse_date(current_date) if current_date is not None else date.today()
    p_start = parse_date(start_date)
    p_exp = parse_date(expected_completion_date)
    ref_update = parse_date(last_progress_update) or p_start

    if f_prog is None or p_start is None or p_exp is None or p_curr is None:
        return build_rule_result(
            rule_id="GHOST-004",
            rule_name="Stalled project composite indicator",
            category="GHOST_STALLED",
            triggered=False,
            severity="LOW",
            message="Insufficient data (progress, start date, or completion date missing) to evaluate composite stall indicator.",
            evidence={"progress_percentage": f_prog, "start_date": str(start_date) if start_date else None},
        )

    days_inactive = max(0, (p_curr - ref_update).days) if ref_update else 0
    total_days = (p_exp - p_start).days
    elapsed_days = (p_curr - p_start).days

    if total_days <= 0:
        elapsed_pct = 100.0 if elapsed_days >= 0 else 0.0
    else:
        elapsed_pct = round(max(0.0, (elapsed_days / total_days) * 100.0), 2)

    c1_low_prog = f_prog <= progress_threshold
    c2_long_inactive = days_inactive >= inactivity_days_threshold
    c3_high_elapsed = elapsed_pct >= elapsed_duration_pct_threshold

    triggered = c1_low_prog and c2_long_inactive and c3_high_elapsed

    if triggered:
        message = (
            f"Strong stalled-project indicator: Project has low progress ({f_prog}%), "
            f"has been inactive for {days_inactive} days, and has consumed {elapsed_pct}% of planned schedule."
        )
    else:
        message = (
            f"Composite stalled indicator not met (progress: {f_prog}%, "
            f"inactive: {days_inactive}d, elapsed schedule: {elapsed_pct}%)."
        )

    return build_rule_result(
        rule_id="GHOST-004",
        rule_name="Stalled project composite indicator",
        category="GHOST_STALLED",
        triggered=triggered,
        severity="CRITICAL",
        message=message,
        evidence={
            "progress_percentage": f_prog,
            "days_inactive": days_inactive,
            "elapsed_duration_percentage": elapsed_pct,
            "progress_threshold": progress_threshold,
            "inactivity_days_threshold": inactivity_days_threshold,
            "elapsed_duration_pct_threshold": elapsed_duration_pct_threshold,
            "criteria_met": {
                "low_progress": c1_low_prog,
                "long_inactivity": c2_long_inactive,
                "high_elapsed_duration": c3_high_elapsed,
            },
        },
    )


def evaluate_all_ghost_stalled_rules(
    project: Dict[str, Any],
    current_date: Any = None,
) -> List[Dict[str, Any]]:
    """
    Executes all ghost/stalled detection rules against a project dictionary.

    Args:
        project: Dictionary with project fields.
        current_date: Optional evaluation reference date.

    Returns:
        List[Dict[str, Any]]: List of rule outcome dictionaries.
    """
    if not isinstance(project, dict):
        project = {}

    progress = project.get("progress_percentage")
    if progress is None:
        progress = project.get("progress")

    status = project.get("status")
    last_update = project.get("last_progress_update")
    start_date = project.get("start_date")
    exp_completion = project.get("expected_completion_date")
    expenditure = project.get("actual_expenditure")
    sanctioned = project.get("sanctioned_amount")

    results: List[Dict[str, Any]] = [
        check_no_progress_stalled(
            progress_percentage=progress,
            last_progress_update=last_update,
            start_date=start_date,
            current_date=current_date,
        ),
        check_expenditure_progress_mismatch(
            actual_expenditure=expenditure,
            sanctioned_amount=sanctioned,
            progress_percentage=progress,
        ),
        check_active_project_inactivity(
            status=status,
            last_progress_update=last_update,
            start_date=start_date,
            current_date=current_date,
        ),
        check_stalled_project_composite(
            progress_percentage=progress,
            last_progress_update=last_update,
            start_date=start_date,
            expected_completion_date=exp_completion,
            current_date=current_date,
        ),
    ]

    return results


__all__ = [
    "ACTIVE_STATUS_SET",
    "check_no_progress_stalled",
    "check_expenditure_progress_mismatch",
    "check_active_project_inactivity",
    "check_stalled_project_composite",
    "evaluate_all_ghost_stalled_rules",
]
