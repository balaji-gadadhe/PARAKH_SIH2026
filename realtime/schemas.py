from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from .models import EventSource, EventType

VALID_EVENT_TYPES = {member.value for member in EventType}
VALID_EVENT_SOURCES = {member.value for member in EventSource}
VALID_PAYMENT_STATUSES = {
    "successful",
    "pending",
    "in_progress",
    "payment_in_progress",
    "paid",
    "payment_completed",
    "cancelled",
    "completed",
    "no_transactions",
}

PAYMENT_STATUS_ALIASES = {
    "payment success": "successful",
    "payment in-progress": "payment_in_progress",
}


def normalize_payment_status(value: Any) -> tuple[str | None, str | None]:
    if value is None or bool(pd.isna(value)):
        return None, None
    raw = str(value).strip()
    if not raw:
        return None, raw
    canonical = PAYMENT_STATUS_ALIASES.get(raw.lower(), raw.lower())
    return canonical, raw


class EventSchema:
    @staticmethod
    def validate_event(event: dict[str, Any]) -> bool:
        if not isinstance(event, dict):
            return False
        required = [
            "event_id",
            "event_type",
            "event_timestamp",
            "event_source",
            "project_id",
            "mp_name",
            "state",
            "constituency",
        ]
        for key in required:
            if key not in event or event.get(key) in (None, ""):
                return False

        raw_event_type = str(event["event_type"]).upper()
        if raw_event_type not in VALID_EVENT_TYPES:
            return False

        source = str(event["event_source"])
        if source not in VALID_EVENT_SOURCES:
            return False

        try:
            datetime.fromisoformat(str(event["event_timestamp"]).replace("Z", "+00:00"))
        except ValueError:
            return False

        amount_fields = [
            "recommended_amount",
            "final_amount",
            "expenditure_amount",
        ]
        for key in amount_fields:
            if key in event and event[key] not in (None, ""):
                try:
                    amount = float(event[key])
                except (TypeError, ValueError):
                    return False
                if amount < 0:
                    return False

        payment_status, _ = normalize_payment_status(event.get("payment_status"))
        if payment_status is not None and payment_status not in (None, ""):
            if payment_status not in VALID_PAYMENT_STATUSES:
                return False

        if "completed_date" in event and event["completed_date"] not in (None, ""):
            try:
                datetime.fromisoformat(str(event["completed_date"]).replace("Z", "+00:00"))
            except ValueError:
                return False

        if "payment_date" in event and event["payment_date"] not in (None, ""):
            try:
                datetime.fromisoformat(str(event["payment_date"]).replace("Z", "+00:00"))
            except ValueError:
                return False

        return True


def validate_event(event: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(event)
    if "payment_status" in cleaned:
        canonical, raw = normalize_payment_status(cleaned.get("payment_status"))
        if raw is not None:
            cleaned["payment_status_raw"] = cleaned.get("payment_status_raw", raw)
        cleaned["payment_status"] = canonical
    if not EventSchema.validate_event(cleaned):
        raise ValueError("Invalid MPLADS event payload")
    cleaned["event_type"] = str(cleaned["event_type"]).upper()
    cleaned["event_source"] = str(cleaned["event_source"]).lower()
    return cleaned
