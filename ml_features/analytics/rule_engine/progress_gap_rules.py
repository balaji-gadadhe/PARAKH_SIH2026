"""
analytics/rule_engine/progress_gap_rules.py

Expected vs. actual physical progress and timeline discrepancy rules for MPLAD-Sentinel.
Implements PROGRESS-001 through PROGRESS-004.
"""

from datetime import date
from typing import Any, Dict, List, Optional

try:
    from analytics.rule_engine.threshold_checks import (
        build_rule_result,
        calculate_elapsed_days,
        parse_date,
        safe_float,
    )
except ImportError:
    from threshold_checks import (  # type: ignore
        build_rule_result,
        calculate_elapsed_days,
        parse_date,
        safe_float,
    )

# Configurable analytical threshold boundaries (in percentage points)
DEFAULT_GAP_THRESHOLDS = {
    "LOW": 15.0,       # Gap >= 15% -> LOW risk indicator
    "MEDIUM": 30.0,    # Gap >= 30% -> MEDIUM risk indicator
    "HIGH": 50.0,      # Gap >= 50% -> HIGH risk indicator
    "CRITICAL": 70.0,  # Gap >= 70% -> CRITICAL risk indicator
}


def calculate_expected_progress(
    start_date: Any,
    expected_completion_date: Any,
    current_date: Any = None,
) -> Optional[float]:
    """
    PROGRESS-001: Computes expected progress percentage based on elapsed project timeline.

    Formula:
        elapsed_duration = current_date - start_date
        total_duration = expected_completion_date - start_date
        expected_progress = (elapsed_duration / total_duration) * 100

    Clamps result between 0.0% and 100.0%. Safe against zero/negative duration and None dates.

    Args:
        start_date: Project sanction or commencement date.
        expected_completion_date: Scheduled completion date.
        current_date: Evaluation reference date (defaults to date.today() if None).

    Returns:
        Optional[float]: Expected progress percentage clamped [0.0, 100.0],
                         or None if dates are invalid/missing.
    """
    p_start = parse_date(start_date)
    p_exp = parse_date(expected_completion_date)
    p_curr = parse_date(current_date) if current_date is not None else date.today()

    if p_start is None or p_exp is None or p_curr is None:
        return None

    total_days = (p_exp - p_start).days
    elapsed_days = (p_curr - p_start).days

    if total_days <= 0:
        # If expected completion is same or earlier than start date
        if elapsed_days >= 0:
            return 100.0
        return 0.0

    if elapsed_days <= 0:
        return 0.0

    raw_expected = (elapsed_days / total_days) * 100.0
    return round(max(0.0, min(100.0, raw_expected)), 2)


def check_expected_progress_rule(
    start_date: Any,
    expected_completion_date: Any,
    current_date: Any = None,
) -> Dict[str, Any]:
    """
    PROGRESS-001: Rule evaluation wrapper for expected progress calculation.

    Args:
        start_date: Project commencement date.
        expected_completion_date: Scheduled completion date.
        current_date: Evaluation reference date.

    Returns:
        Standard rule result dictionary.
    """
    p_curr = parse_date(current_date) if current_date is not None else date.today()
    expected = calculate_expected_progress(start_date, expected_completion_date, p_curr)

    if expected is None:
        return build_rule_result(
            rule_id="PROGRESS-001",
            rule_name="Expected progress estimation",
            category="PROGRESS",
            triggered=False,
            severity="LOW",
            message="Cannot calculate expected progress due to missing start or expected completion date.",
            evidence={
                "start_date": str(start_date) if start_date else None,
                "expected_completion_date": str(expected_completion_date) if expected_completion_date else None,
                "current_date": str(p_curr) if p_curr else None,
                "expected_progress": None,
            },
        )

    return build_rule_result(
        rule_id="PROGRESS-001",
        rule_name="Expected progress estimation",
        category="PROGRESS",
        triggered=False,  # Estimation utility, informational
        severity="LOW",
        message=f"Calculated expected progress is {expected}% based on elapsed timeline.",
        evidence={
            "start_date": str(start_date),
            "expected_completion_date": str(expected_completion_date),
            "current_date": str(p_curr),
            "expected_progress": expected,
        },
    )


def calculate_progress_gap(
    expected_progress: Any,
    actual_progress: Any,
) -> Optional[float]:
    """
    PROGRESS-002: Computes physical progress gap (expected_progress - actual_progress).

    A positive gap indicates that the project is lagging behind schedule.

    Args:
        expected_progress: Expected percentage based on elapsed timeline.
        actual_progress: Reported physical completion percentage.

    Returns:
        Optional[float]: Progress gap in percentage points, or None if inputs invalid.
    """
    f_exp = safe_float(expected_progress)
    f_act = safe_float(actual_progress)
    if f_exp is None or f_act is None:
        return None
    return round(f_exp - f_act, 2)


def check_significant_progress_gap(
    expected_progress: Any,
    actual_progress: Any,
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    PROGRESS-003: Flag significant progress gap.

    Evaluates whether the gap between expected and actual progress crosses
    analytical severity thresholds (LOW, MEDIUM, HIGH, CRITICAL).

    Args:
        expected_progress: Expected progress percentage (0-100).
        actual_progress: Reported progress percentage (0-100).
        thresholds: Dictionary of threshold boundaries.

    Returns:
        Standard rule result dictionary.
    """
    f_exp = safe_float(expected_progress)
    f_act = safe_float(actual_progress)
    gap = calculate_progress_gap(f_exp, f_act)

    if gap is None or f_exp is None or f_act is None:
        return build_rule_result(
            rule_id="PROGRESS-003",
            rule_name="Significant progress gap",
            category="PROGRESS",
            triggered=False,
            severity="LOW",
            message="Insufficient data to compute progress gap.",
            evidence={"expected_progress": f_exp, "actual_progress": f_act, "progress_gap": None},
        )

    t = thresholds or DEFAULT_GAP_THRESHOLDS
    t_crit = t.get("CRITICAL", 70.0)
    t_high = t.get("HIGH", 50.0)
    t_med = t.get("MEDIUM", 30.0)
    t_low = t.get("LOW", 15.0)

    if gap >= t_crit:
        triggered = True
        severity = "CRITICAL"
        message = (
            f"Critical progress gap: actual progress ({f_act}%) lags expected progress "
            f"({f_exp}%) by {gap} percentage points."
        )
    elif gap >= t_high:
        triggered = True
        severity = "HIGH"
        message = (
            f"High progress gap: actual progress ({f_act}%) is substantially below expected progress "
            f"({f_exp}%) by {gap} percentage points."
        )
    elif gap >= t_med:
        triggered = True
        severity = "MEDIUM"
        message = (
            f"Moderate progress gap: actual progress ({f_act}%) lags expected progress "
            f"({f_exp}%) by {gap} percentage points."
        )
    elif gap >= t_low:
        triggered = True
        severity = "LOW"
        message = (
            f"Minor progress gap: actual progress ({f_act}%) is {gap} percentage points behind "
            f"expected progress ({f_exp}%)."
        )
    else:
        triggered = False
        severity = "LOW"
        if gap < 0:
            message = (
                f"Project is ahead of schedule by {abs(gap)} percentage points "
                f"(actual: {f_act}%, expected: {f_exp}%)."
            )
        else:
            message = (
                f"Progress gap is within acceptable limits ({gap} percentage points; "
                f"actual: {f_act}%, expected: {f_exp}%)."
            )

    return build_rule_result(
        rule_id="PROGRESS-003",
        rule_name="Significant progress gap",
        category="PROGRESS",
        triggered=triggered,
        severity=severity,
        message=message,
        evidence={
            "expected_progress": f_exp,
            "actual_progress": f_act,
            "progress_gap": gap,
            "applied_thresholds": t,
        },
    )


def check_progress_duration_mismatch(
    start_date: Any,
    expected_completion_date: Any,
    actual_progress: Any,
    current_date: Any = None,
    duration_threshold_pct: float = 75.0,
    progress_threshold_pct: float = 25.0,
) -> Dict[str, Any]:
    """
    PROGRESS-004: Detect progress/duration mismatch.

    Flags projects where a large majority of the planned duration has elapsed,
    yet reported physical progress remains disproportionately low.
    Example: >= 90% of duration elapsed but only 25% progress completed.

    Args:
        start_date: Project commencement date.
        expected_completion_date: Scheduled completion date.
        actual_progress: Reported actual progress percentage.
        current_date: Evaluation reference date.
        duration_threshold_pct: Minimum elapsed duration % to trigger (default: 75.0).
        progress_threshold_pct: Maximum progress % below which to trigger (default: 25.0).

    Returns:
        Standard rule result dictionary.
    """
    f_act = safe_float(actual_progress)
    p_start = parse_date(start_date)
    p_exp = parse_date(expected_completion_date)
    p_curr = parse_date(current_date) if current_date is not None else date.today()

    if p_start is None or p_exp is None or p_curr is None or f_act is None:
        return build_rule_result(
            rule_id="PROGRESS-004",
            rule_name="Progress and duration mismatch",
            category="PROGRESS",
            triggered=False,
            severity="LOW",
            message="Insufficient date or progress data to evaluate progress/duration mismatch.",
            evidence={
                "start_date": str(start_date) if start_date else None,
                "expected_completion_date": str(expected_completion_date) if expected_completion_date else None,
                "actual_progress": f_act,
            },
        )

    total_days = (p_exp - p_start).days
    elapsed_days = (p_curr - p_start).days

    if total_days <= 0:
        elapsed_duration_pct = 100.0 if elapsed_days >= 0 else 0.0
    else:
        elapsed_duration_pct = round(max(0.0, (elapsed_days / total_days) * 100.0), 2)

    triggered = (elapsed_duration_pct >= duration_threshold_pct) and (f_act <= progress_threshold_pct)

    severity = "CRITICAL" if (elapsed_duration_pct >= 90.0 and f_act <= 15.0) else "HIGH"

    if triggered:
        message = (
            f"High duration/progress mismatch: {elapsed_duration_pct}% of project schedule has elapsed, "
            f"but only {f_act}% physical progress has been reported."
        )
    else:
        message = (
            f"Progress duration alignment is acceptable ({elapsed_duration_pct}% elapsed, "
            f"{f_act}% completed)."
        )

    return build_rule_result(
        rule_id="PROGRESS-004",
        rule_name="Progress and duration mismatch",
        category="PROGRESS",
        triggered=triggered,
        severity=severity,
        message=message,
        evidence={
            "elapsed_duration_percentage": elapsed_duration_pct,
            "actual_progress_percentage": f_act,
            "duration_threshold_percentage": duration_threshold_pct,
            "progress_threshold_percentage": progress_threshold_pct,
            "elapsed_days": elapsed_days,
            "total_planned_days": total_days,
        },
    )


def evaluate_all_progress_gap_rules(
    project: Dict[str, Any],
    current_date: Any = None,
) -> List[Dict[str, Any]]:
    """
    Executes all progress gap rules against a project dictionary.

    Args:
        project: Dictionary with project fields.
        current_date: Optional evaluation reference date.

    Returns:
        List[Dict[str, Any]]: List of rule outcome dictionaries.
    """
    if not isinstance(project, dict):
        project = {}

    start_date = project.get("start_date")
    expected_completion = project.get("expected_completion_date")
    progress = project.get("progress_percentage")
    if progress is None:
        progress = project.get("progress")

    expected_progress = calculate_expected_progress(
        start_date=start_date,
        expected_completion_date=expected_completion,
        current_date=current_date,
    )

    results: List[Dict[str, Any]] = [
        check_expected_progress_rule(
            start_date=start_date,
            expected_completion_date=expected_completion,
            current_date=current_date,
        ),
        check_significant_progress_gap(
            expected_progress=expected_progress,
            actual_progress=progress,
        ),
        check_progress_duration_mismatch(
            start_date=start_date,
            expected_completion_date=expected_completion,
            actual_progress=progress,
            current_date=current_date,
        ),
    ]

    return results


__all__ = [
    "DEFAULT_GAP_THRESHOLDS",
    "calculate_expected_progress",
    "check_expected_progress_rule",
    "calculate_progress_gap",
    "check_significant_progress_gap",
    "check_progress_duration_mismatch",
    "evaluate_all_progress_gap_rules",
]
