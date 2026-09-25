"""
analytics/rule_engine/compliance_rules.py

Project data consistency, completeness, and compliance validation rules for MPLAD-Sentinel.
Implements COMPLIANCE-001 through COMPLIANCE-008.
"""

from typing import Any, Dict, List, Optional, Set

try:
    from analytics.rule_engine.threshold_checks import (
        build_rule_result,
        parse_date,
        safe_float,
    )
except ImportError:
    from threshold_checks import (  # type: ignore
        build_rule_result,
        parse_date,
        safe_float,
    )

DEFAULT_CRITICAL_FIELDS: List[str] = [
    "project_id",
    "project_name",
    "sanctioned_amount",
    "start_date",
    "status",
    "location",
    "implementing_agency",
]

DEFAULT_ALLOWED_STATUSES: Set[str] = {
    "ongoing",
    "completed",
    "cancelled",
    "pending",
    "in progress",
    "active",
    "not started",
    "sanctioned",
    "closed",
}


def check_missing_critical_fields(
    project_data: Dict[str, Any],
    critical_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    COMPLIANCE-001: Missing critical project information.

    Checks if mandatory project record fields are missing or empty.
    Defensive against missing keys and non-dict inputs.

    Args:
        project_data: Dictionary containing project record.
        critical_fields: Optional list of field names to check.

    Returns:
        Standard rule result dictionary.
    """
    fields_to_check = critical_fields or DEFAULT_CRITICAL_FIELDS
    if not isinstance(project_data, dict):
        return build_rule_result(
            rule_id="COMPLIANCE-001",
            rule_name="Missing critical project information",
            category="COMPLIANCE",
            triggered=True,
            severity="CRITICAL",
            message="Invalid project data payload: expected dictionary.",
            evidence={"missing_fields": fields_to_check, "received_type": type(project_data).__name__},
        )

    missing_fields: List[str] = []
    for field in fields_to_check:
        val = project_data.get(field)
        if val is None:
            missing_fields.append(field)
        elif isinstance(val, str) and val.strip() == "":
            missing_fields.append(field)

    triggered = len(missing_fields) > 0
    severity = "HIGH" if len(missing_fields) > 1 else "MEDIUM"

    if triggered:
        message = (
            f"Project record is missing {len(missing_fields)} critical field(s): "
            f"{', '.join(missing_fields)}."
        )
    else:
        message = "All critical project fields are present."

    return build_rule_result(
        rule_id="COMPLIANCE-001",
        rule_name="Missing critical project information",
        category="COMPLIANCE",
        triggered=triggered,
        severity=severity,
        message=message,
        evidence={
            "missing_fields": missing_fields,
            "checked_fields_count": len(fields_to_check),
            "missing_count": len(missing_fields),
        },
    )


def check_invalid_status(
    status: Any,
    allowed_statuses: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    COMPLIANCE-002: Invalid project status.

    Validates project status against permissible MPLADS status vocabulary.

    Args:
        status: The reported status string or object.
        allowed_statuses: Set of lowercase valid status strings.

    Returns:
        Standard rule result dictionary.
    """
    valid_set = allowed_statuses or DEFAULT_ALLOWED_STATUSES

    if status is None or (isinstance(status, str) and not status.strip()):
        return build_rule_result(
            rule_id="COMPLIANCE-002",
            rule_name="Invalid project status",
            category="COMPLIANCE",
            triggered=True,
            severity="MEDIUM",
            message="Project status is missing or empty.",
            evidence={"reported_status": status, "allowed_statuses": sorted(list(valid_set))},
        )

    norm_status = str(status).strip().lower()
    is_valid = norm_status in valid_set

    triggered = not is_valid
    if triggered:
        message = (
            f"Project status '{status}' is not recognized among valid status values."
        )
    else:
        message = f"Project status '{status}' is valid."

    return build_rule_result(
        rule_id="COMPLIANCE-002",
        rule_name="Invalid project status",
        category="COMPLIANCE",
        triggered=triggered,
        severity="MEDIUM",
        message=message,
        evidence={
            "reported_status": status,
            "normalized_status": norm_status,
            "allowed_statuses": sorted(list(valid_set)),
        },
    )


def check_invalid_progress(progress_percentage: Any) -> Dict[str, Any]:
    """
    COMPLIANCE-003: Invalid progress percentage.

    Flags reported progress percentage outside the logical 0-100% boundary.

    Args:
        progress_percentage: Reported progress value.

    Returns:
        Standard rule result dictionary.
    """
    f_prog = safe_float(progress_percentage)
    if f_prog is None:
        return build_rule_result(
            rule_id="COMPLIANCE-003",
            rule_name="Invalid progress percentage",
            category="COMPLIANCE",
            triggered=False,
            severity="LOW",
            message="Progress percentage is not provided or unparseable; not evaluated.",
            evidence={"reported_progress": progress_percentage},
        )

    triggered = f_prog < 0.0 or f_prog > 100.0
    if triggered:
        message = (
            f"Reported progress percentage ({f_prog}%) is out of valid bounds [0.0, 100.0]."
        )
    else:
        message = f"Reported progress percentage ({f_prog}%) is within valid bounds."

    return build_rule_result(
        rule_id="COMPLIANCE-003",
        rule_name="Invalid progress percentage",
        category="COMPLIANCE",
        triggered=triggered,
        severity="HIGH",
        message=message,
        evidence={
            "progress_percentage": f_prog,
            "lower_bound": 0.0,
            "upper_bound": 100.0,
        },
    )


def check_negative_financials(
    project_data: Dict[str, Any],
    financial_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    COMPLIANCE-004: Negative financial values.

    Flags any monetary attributes (sanctioned amount, expenditure, payments)
    reported as negative numbers.

    Args:
        project_data: Project data dictionary.
        financial_keys: List of numerical financial field keys to verify.

    Returns:
        Standard rule result dictionary.
    """
    keys_to_check = financial_keys or [
        "sanctioned_amount",
        "actual_expenditure",
        "payment_amount",
        "total_payments",
        "released_amount",
    ]

    negative_entries: Dict[str, float] = {}
    for key in keys_to_check:
        val = project_data.get(key)
        f_val = safe_float(val)
        if f_val is not None and f_val < 0.0:
            negative_entries[key] = f_val

    triggered = len(negative_entries) > 0
    if triggered:
        details = ", ".join(f"{k}={v}" for k, v in negative_entries.items())
        message = f"Found negative financial value(s): {details}."
    else:
        message = "All checked financial values are non-negative."

    return build_rule_result(
        rule_id="COMPLIANCE-004",
        rule_name="Negative financial values",
        category="COMPLIANCE",
        triggered=triggered,
        severity="HIGH",
        message=message,
        evidence={"negative_financials": negative_entries},
    )


def check_invalid_dates(
    start_date: Any,
    completion_date: Any = None,
    expected_completion_date: Any = None,
    last_progress_update: Any = None,
) -> Dict[str, Any]:
    """
    COMPLIANCE-005: Invalid dates.

    Validates chronological sequence of project milestone dates.
    Flags when completion or progress dates precede project start date.

    Args:
        start_date: Project initiation/sanction date.
        completion_date: Actual project completion date.
        expected_completion_date: Planned project completion date.
        last_progress_update: Date of last recorded physical progress update.

    Returns:
        Standard rule result dictionary.
    """
    p_start = parse_date(start_date)
    p_comp = parse_date(completion_date)
    p_exp = parse_date(expected_completion_date)
    p_update = parse_date(last_progress_update)

    anomalies: List[str] = []

    if p_start is not None:
        if p_comp is not None and p_comp < p_start:
            anomalies.append(
                f"Actual completion date ({p_comp}) is earlier than start date ({p_start})"
            )
        if p_exp is not None and p_exp < p_start:
            anomalies.append(
                f"Expected completion date ({p_exp}) is earlier than start date ({p_start})"
            )
        if p_update is not None and p_update < p_start:
            anomalies.append(
                f"Last progress update date ({p_update}) is earlier than start date ({p_start})"
            )

    triggered = len(anomalies) > 0
    if triggered:
        message = f"Chronological inconsistency in project dates: {'; '.join(anomalies)}."
    else:
        message = "Project milestone dates are chronologically consistent."

    return build_rule_result(
        rule_id="COMPLIANCE-005",
        rule_name="Invalid dates chronology",
        category="COMPLIANCE",
        triggered=triggered,
        severity="HIGH",
        message=message,
        evidence={
            "start_date": str(p_start) if p_start else None,
            "completion_date": str(p_comp) if p_comp else None,
            "expected_completion_date": str(p_exp) if p_exp else None,
            "last_progress_update": str(p_update) if p_update else None,
            "anomalies": anomalies,
        },
    )


def check_completed_progress_mismatch(
    status: Any, progress_percentage: Any
) -> Dict[str, Any]:
    """
    COMPLIANCE-006: Completed project with progress below 100%.

    Flags projects marked as 'completed' whose physical progress is reported < 100%.

    Args:
        status: Project status.
        progress_percentage: Reported progress percentage.

    Returns:
        Standard rule result dictionary.
    """
    norm_status = str(status).strip().lower() if status is not None else ""
    f_prog = safe_float(progress_percentage)

    if norm_status != "completed":
        return build_rule_result(
            rule_id="COMPLIANCE-006",
            rule_name="Completed project with progress below 100%",
            category="COMPLIANCE",
            triggered=False,
            severity="LOW",
            message=f"Project status is '{status}', not 'completed'. Rule not triggered.",
            evidence={"status": status, "progress_percentage": f_prog},
        )

    if f_prog is None:
        return build_rule_result(
            rule_id="COMPLIANCE-006",
            rule_name="Completed project with progress below 100%",
            category="COMPLIANCE",
            triggered=True,
            severity="MEDIUM",
            message="Project is marked completed, but progress percentage is missing.",
            evidence={"status": status, "progress_percentage": None},
        )

    triggered = f_prog < 100.0
    if triggered:
        message = (
            f"Project is marked 'completed' but reported progress is only {f_prog}% "
            f"(expected 100%)."
        )
    else:
        message = "Project is marked 'completed' and reports 100% progress."

    return build_rule_result(
        rule_id="COMPLIANCE-006",
        rule_name="Completed project with progress below 100%",
        category="COMPLIANCE",
        triggered=triggered,
        severity="HIGH",
        message=message,
        evidence={"status": status, "progress_percentage": f_prog, "expected_progress": 100.0},
    )


def check_completed_missing_completion_date(
    status: Any, completion_date: Any
) -> Dict[str, Any]:
    """
    COMPLIANCE-007: Completed project with missing completion date.

    Flags projects marked 'completed' that lack an actual completion date.

    Args:
        status: Project status.
        completion_date: Recorded completion date.

    Returns:
        Standard rule result dictionary.
    """
    norm_status = str(status).strip().lower() if status is not None else ""
    p_comp = parse_date(completion_date)

    if norm_status != "completed":
        return build_rule_result(
            rule_id="COMPLIANCE-007",
            rule_name="Completed project with missing completion date",
            category="COMPLIANCE",
            triggered=False,
            severity="LOW",
            message=f"Project status is '{status}', not 'completed'. Rule not triggered.",
            evidence={"status": status, "completion_date": str(p_comp) if p_comp else None},
        )

    triggered = p_comp is None
    if triggered:
        message = "Project is marked 'completed' but no valid completion date is recorded."
    else:
        message = f"Project is marked 'completed' with recorded completion date {p_comp}."

    return build_rule_result(
        rule_id="COMPLIANCE-007",
        rule_name="Completed project with missing completion date",
        category="COMPLIANCE",
        triggered=triggered,
        severity="MEDIUM",
        message=message,
        evidence={"status": status, "completion_date": str(p_comp) if p_comp else None},
    )


def check_payment_expenditure_inconsistency(
    actual_expenditure: Any,
    total_payments: Any = None,
    payment_amount: Any = None,
) -> Dict[str, Any]:
    """
    COMPLIANCE-008: Payment/expenditure inconsistency.

    Flags cases where cumulative disbursed payments exceed reported actual expenditure.

    Args:
        actual_expenditure: Reported expenditure incurred.
        total_payments: Total cumulative payments disbursed.
        payment_amount: Single/latest payment amount (fallback if total_payments not present).

    Returns:
        Standard rule result dictionary.
    """
    f_exp = safe_float(actual_expenditure)
    f_payments = safe_float(total_payments)
    if f_payments is None:
        f_payments = safe_float(payment_amount)

    if f_exp is None or f_payments is None:
        return build_rule_result(
            rule_id="COMPLIANCE-008",
            rule_name="Payment/expenditure inconsistency",
            category="COMPLIANCE",
            triggered=False,
            severity="LOW",
            message="Insufficient expenditure or payment data to evaluate consistency.",
            evidence={"actual_expenditure": f_exp, "total_payments": f_payments},
        )

    excess = round(f_payments - f_exp, 2)
    triggered = excess > 0.01

    if triggered:
        message = (
            f"Total payments (INR {f_payments:,.2f}) exceed reported actual expenditure "
            f"(INR {f_exp:,.2f}) by INR {excess:,.2f}."
        )
    else:
        message = (
            f"Payments (INR {f_payments:,.2f}) are within reported actual expenditure "
            f"(INR {f_exp:,.2f})."
        )

    return build_rule_result(
        rule_id="COMPLIANCE-008",
        rule_name="Payment/expenditure inconsistency",
        category="COMPLIANCE",
        triggered=triggered,
        severity="HIGH",
        message=message,
        evidence={
            "actual_expenditure": f_exp,
            "total_payments": f_payments,
            "excess_amount": excess if triggered else 0.0,
        },
    )


def evaluate_all_compliance_rules(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Executes all compliance rules against a project dictionary.

    Args:
        project: Dictionary with project details.

    Returns:
        List[Dict[str, Any]]: List of rule outcome dictionaries.
    """
    if not isinstance(project, dict):
        project = {}

    status = project.get("status")
    progress = project.get("progress_percentage")
    if progress is None:
        progress = project.get("progress")

    results: List[Dict[str, Any]] = [
        check_missing_critical_fields(project),
        check_invalid_status(status),
        check_invalid_progress(progress),
        check_negative_financials(project),
        check_invalid_dates(
            start_date=project.get("start_date"),
            completion_date=project.get("completion_date"),
            expected_completion_date=project.get("expected_completion_date"),
            last_progress_update=project.get("last_progress_update"),
        ),
        check_completed_progress_mismatch(status=status, progress_percentage=progress),
        check_completed_missing_completion_date(
            status=status, completion_date=project.get("completion_date")
        ),
        check_payment_expenditure_inconsistency(
            actual_expenditure=project.get("actual_expenditure"),
            total_payments=project.get("total_payments"),
            payment_amount=project.get("payment_amount"),
        ),
    ]

    return results


__all__ = [
    "DEFAULT_CRITICAL_FIELDS",
    "DEFAULT_ALLOWED_STATUSES",
    "check_missing_critical_fields",
    "check_invalid_status",
    "check_invalid_progress",
    "check_negative_financials",
    "check_invalid_dates",
    "check_completed_progress_mismatch",
    "check_completed_missing_completion_date",
    "check_payment_expenditure_inconsistency",
    "evaluate_all_compliance_rules",
]
