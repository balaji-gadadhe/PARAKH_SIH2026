"""
analytics/rule_engine/threshold_checks.py

Reusable threshold and helper functions for MPLAD-Sentinel Rule Engine.
Provides deterministic, zero-division safe, and None-safe numeric and date checks.
"""

from datetime import date, datetime
from typing import Any, Dict, Optional, Union

# Standard Severity-to-Score Mapping
SEVERITY_SCORE_MAP: Dict[str, int] = {
    "LOW": 20,
    "MEDIUM": 40,
    "HIGH": 70,
    "CRITICAL": 90,
}


def get_severity_score(severity: str, triggered: bool = True) -> int:
    """
    Returns the analytical risk score associated with a severity level.
    Returns 0 if the rule is not triggered.

    Args:
        severity: One of 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'.
        triggered: Boolean indicating whether rule was triggered.

    Returns:
        int: Analytical score (0-90).
    """
    if not triggered:
        return 0
    return SEVERITY_SCORE_MAP.get(str(severity).upper(), 20)


def build_rule_result(
    rule_id: str,
    rule_name: str,
    category: str,
    triggered: bool,
    severity: str,
    message: str,
    evidence: Optional[Dict[str, Any]] = None,
    score: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Constructs a standardized, explainable rule result dictionary.

    Args:
        rule_id: Unique rule identifier (e.g., 'GHOST-001').
        rule_name: Human-readable rule title.
        category: Rule category (e.g., 'GHOST_STALLED', 'COMPLIANCE', 'PROGRESS').
        triggered: Whether the rule condition was met.
        severity: Severity string ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL').
        message: Concise explanation of the rule evaluation.
        evidence: Dictionary containing specific values that caused or evaluated the rule.
        score: Optional custom score override. If None, derived from severity and triggered status.

    Returns:
        Dict[str, Any]: Standard rule outcome structure.
    """
    calc_score = score if score is not None else get_severity_score(severity, triggered=triggered)
    return {
        "rule_id": rule_id,
        "rule_name": rule_name,
        "category": category,
        "triggered": triggered,
        "severity": severity if triggered else "LOW",
        "score": calc_score,
        "message": message,
        "evidence": evidence if evidence is not None else {},
    }


def safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Safely casts an input value to float, handling None, empty strings, and invalid formats.
    """
    if val is None:
        return default
    try:
        if isinstance(val, (int, float)):
            return float(val)
        val_str = str(val).strip().replace(",", "")
        if val_str == "":
            return default
        return float(val_str)
    except (ValueError, TypeError):
        return default


def safe_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    """
    Safely casts an input value to int, handling None, empty strings, and invalid formats.
    """
    if val is None:
        return default
    try:
        f_val = safe_float(val)
        if f_val is None:
            return default
        return int(f_val)
    except (ValueError, TypeError):
        return default


def parse_date(date_val: Any) -> Optional[date]:
    """
    Safely parses a date input into a datetime.date object.
    Supports datetime.date, datetime.datetime, and common ISO/Indian string formats.

    Args:
        date_val: String, date, datetime, or None.

    Returns:
        Optional[date]: Parsed date or None if invalid/missing.
    """
    if date_val is None:
        return None
    if isinstance(date_val, datetime):
        return date_val.date()
    if isinstance(date_val, date):
        return date_val

    if not isinstance(date_val, str):
        return None

    cleaned_str = date_val.strip().split("T")[0].split(" ")[0]
    if not cleaned_str:
        return None

    formats = (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%Y%m%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(cleaned_str, fmt).date()
        except ValueError:
            continue
    return None


def calculate_elapsed_days(start_date: Any, end_date: Any) -> Optional[int]:
    """
    Calculates elapsed calendar days between two dates.

    Args:
        start_date: Starting date (parseable).
        end_date: Ending or reference date (parseable).

    Returns:
        Optional[int]: Number of elapsed days (can be negative if end < start),
                       or None if either date is unparseable.
    """
    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date)
    if parsed_start is None or parsed_end is None:
        return None
    return (parsed_end - parsed_start).days


def calculate_ratio(
    numerator: Any, denominator: Any, default: float = 0.0
) -> float:
    """
    Computes ratio = numerator / denominator safely.
    Prevents ZeroDivisionError, handles None and invalid types.

    Args:
        numerator: Value for numerator.
        denominator: Value for denominator.
        default: Return value when denominator <= 0 or inputs invalid.

    Returns:
        float: Computed ratio or default.
    """
    num = safe_float(numerator)
    den = safe_float(denominator)
    if num is None or den is None or den == 0.0:
        return default
    return num / den


def _compare_values(val: float, threshold: float, comparison: str) -> bool:
    """Helper to evaluate relational operators."""
    comp = comparison.lower().strip()
    if comp in ("gt", ">"):
        return val > threshold
    if comp in ("gte", "ge", ">="):
        return val >= threshold
    if comp in ("lt", "<"):
        return val < threshold
    if comp in ("lte", "le", "<="):
        return val <= threshold
    if comp in ("eq", "=="):
        return val == threshold
    if comp in ("ne", "!="):
        return val != threshold
    return False


def check_percentage_threshold(
    value: Any, threshold: float, comparison: str = "gt"
) -> bool:
    """
    Checks if a percentage value satisfies the threshold comparison.

    Args:
        value: Input percentage value.
        threshold: Comparison threshold.
        comparison: Comparison operator ('gt', 'gte', 'lt', 'lte', 'eq').

    Returns:
        bool: True if condition satisfied, False otherwise or if value is None.
    """
    f_val = safe_float(value)
    if f_val is None:
        return False
    return _compare_values(f_val, threshold, comparison)


def check_amount_threshold(
    value: Any, threshold: float, comparison: str = "gt"
) -> bool:
    """
    Checks if a monetary amount exceeds or satisfies a threshold.

    Args:
        value: Monetary amount.
        threshold: Comparison threshold.
        comparison: Comparison operator.

    Returns:
        bool: Comparison result or False if value is None.
    """
    f_val = safe_float(value)
    if f_val is None:
        return False
    return _compare_values(f_val, threshold, comparison)


def check_duration_threshold(
    days: Any, allowed_days: int, comparison: str = "gt"
) -> bool:
    """
    Checks if a duration in days satisfies a threshold.

    Args:
        days: Number of days.
        allowed_days: Duration threshold in days.
        comparison: Comparison operator.

    Returns:
        bool: Comparison result or False if days is None.
    """
    i_days = safe_int(days)
    if i_days is None:
        return False
    return _compare_values(float(i_days), float(allowed_days), comparison)


def check_ratio_threshold(
    numerator: Any,
    denominator: Any,
    threshold: float,
    comparison: str = "gt",
    default: float = 0.0,
) -> bool:
    """
    Calculates ratio and checks if it satisfies the comparison against threshold.

    Args:
        numerator: Numerator value.
        denominator: Denominator value.
        threshold: Comparison threshold.
        comparison: Comparison operator.
        default: Default ratio if invalid or zero denominator.

    Returns:
        bool: Comparison result.
    """
    ratio = calculate_ratio(numerator, denominator, default=default)
    return _compare_values(ratio, threshold, comparison)


def check_progress_threshold(
    progress: Any, threshold: float, comparison: str = "lt"
) -> bool:
    """
    Checks if reported progress percentage satisfies the threshold.

    Args:
        progress: Reported progress value (0-100).
        threshold: Progress threshold.
        comparison: Comparison operator ('lt', 'lte', etc.).

    Returns:
        bool: Comparison result or False if progress is None.
    """
    f_prog = safe_float(progress)
    if f_prog is None:
        return False
    return _compare_values(f_prog, threshold, comparison)


__all__ = [
    "SEVERITY_SCORE_MAP",
    "get_severity_score",
    "build_rule_result",
    "safe_float",
    "safe_int",
    "parse_date",
    "calculate_elapsed_days",
    "calculate_ratio",
    "check_percentage_threshold",
    "check_amount_threshold",
    "check_duration_threshold",
    "check_ratio_threshold",
    "check_progress_threshold",
]
