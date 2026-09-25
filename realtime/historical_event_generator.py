from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import PROJECT_ROOT
from .models import EventSource, EventType
from .schemas import normalize_payment_status


class HistoricalEventGenerator:
    # The canonical repo master table (`data/master/master_works.csv`, built by
    # scripts/03_build_master_data.py, D-003) uses snake_case columns. The
    # generator reads legacy display-style headers, so alias them on read.
    _MASTER_COLUMN_ALIASES = {
        "work_id": "Work ID",
        "work_description": "Work Description",
        "category": "Category",
        "mp_name": "MP Name",
        "constituency": "Constituency",
        "state": "State",
        "recommended_amount": "Recommended Amount (₹)",
        "recommendation_date": "Recommendation Date",
        "final_amount": "Final Amount (₹)",
        "completed_date": "Completed Date",
    }
    # NB: `project_id` is deliberately not aliased — in the generated master it
    # is a composite key; the canonical project id is the `work_id` (see README_REALTIME).

    @classmethod
    def _align_master_schema(cls, master_df: pd.DataFrame) -> pd.DataFrame:
        if master_df.empty or "Work ID" in master_df.columns:
            return master_df
        return master_df.rename(columns=cls._MASTER_COLUMN_ALIASES)

    def __init__(self, root: str | Path = PROJECT_ROOT, replay_speed: float = 1.0):
        self.root = Path(root)
        self.replay_speed = float(replay_speed)
        self.master_works_path = self.root / "data" / "master" / "master_works.csv"
        self.completed_works_path = self.root / "data" / "cleaned" / "completed_works_clean.csv"
        self.expenditures_path = self.root / "data" / "cleaned" / "expenditures_clean.csv"
        self.recommended_path = self.root / "data" / "cleaned" / "recommended_works_clean.csv"

    @staticmethod
    def _coerce_iso(dt_value: Any) -> str | None:
        if dt_value is None or pd.isna(dt_value):
            return None
        if isinstance(dt_value, str):
            text = dt_value.strip()
            if not text:
                return None
            # Fast path: ISO-8601 text avoids pandas scalar parsing (~0.6 ms per
            # call; the full dataset triggers hundreds of thousands of calls).
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                dt = pd.to_datetime(text, errors="coerce")
        else:
            dt = pd.to_datetime(dt_value, errors="coerce")
        if pd.isna(dt):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _text(value: Any) -> str:
        if value is None or pd.isna(value):
            return ""
        return str(value).strip()

    @classmethod
    def _canonical_project_id(cls, row: dict[str, Any]) -> str:
        return cls._text(row.get("Work ID") or row.get("work_id") or row.get("project_id"))

    @classmethod
    def _fingerprint(cls, row: dict[str, Any], source_row: int | None = None) -> str:
        values = {str(key): cls._text(value) for key, value in sorted(row.items())}
        if source_row is not None:
            values["_source_row"] = str(source_row)
        digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()
        return digest[:20]

    @classmethod
    def _event_id(cls, prefix: str, project_id: str, event_type: str, source_id: str) -> str:
        safe_project = str(project_id).replace(" ", "_")
        return f"{prefix}-{safe_project}-{event_type.lower()}-{source_id}"

    @classmethod
    def _resolve_expenditure(cls, row: dict[str, Any], project_lookup: dict[tuple[str, str, str, str], set[str]]) -> tuple[str | None, str]:
        key = tuple(cls._text(row.get(field)).casefold() for field in ("mp_name", "state", "constituency", "work_description"))
        ids = project_lookup.get(key, set())
        ids.discard("")
        if len(ids) == 1:
            return next(iter(ids)), "resolved"
        return None, "ambiguous" if ids else "unresolved"

    @staticmethod
    def _event_id(prefix: str, project_id: str, event_type: str, timestamp: str | None = None) -> str:
        stamp = timestamp or datetime.utcnow().strftime("%Y%m%d%H%M%S")
        safe_project = str(project_id).replace("|", "-").replace(" ", "_")
        return f"{prefix}-{safe_project}-{event_type.lower()}-{stamp}"

    def generate_events(self, limit: int | None = None, include_synthetic: bool = False) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        master_df = pd.read_csv(self.master_works_path) if self.master_works_path.exists() else pd.DataFrame()
        master_df = self._align_master_schema(master_df)
        expenditures_df = pd.read_csv(self.expenditures_path) if self.expenditures_path.exists() else pd.DataFrame()
        completed_df = pd.read_csv(self.completed_works_path) if self.completed_works_path.exists() else pd.DataFrame()
        project_lookup: dict[tuple[str, str, str, str], set[str]] = {}
        for master_row in master_df.to_dict("records"):
            project_id = self._canonical_project_id(master_row)
            key = tuple(self._text(master_row.get(field)).casefold() for field in ("MP Name", "State", "Constituency", "Work Description"))
            project_lookup.setdefault(key, set()).add(project_id)

        for master_index, (_, row) in enumerate(master_df.iterrows()):
            source = row.to_dict()
            project_id = self._canonical_project_id(source)
            if not project_id:
                continue
            recommended_amount = row.get("Recommended Amount (₹)")
            recommendation_date = self._coerce_iso(row.get("Recommendation Date"))
            final_amount = row.get("Final Amount (₹)")
            completed_date = self._coerce_iso(row.get("Completed Date"))
            project_status = self._text(row.get("status")) or "in_progress"
            mp_name = self._text(row.get("MP Name"))
            state = self._text(row.get("State"))
            constituency = self._text(row.get("Constituency"))
            work_description = self._text(row.get("Work Description"))
            category = self._text(row.get("Category"))
            source_id = self._fingerprint(source, master_index)

            if recommendation_date:
                recommended_event = {
                    "event_id": self._event_id("hist", project_id, EventType.PROJECT_RECOMMENDED.value, source_id),
                    "event_type": EventType.PROJECT_RECOMMENDED.value,
                    "event_timestamp": recommendation_date,
                    "event_source": EventSource.HISTORICAL_REPLAY.value,
                    "project_id": project_id,
                    "mp_name": mp_name,
                    "state": state,
                    "constituency": constituency,
                    "work_description": work_description,
                    "category": category,
                    "recommended_amount": float(recommended_amount) if pd.notna(recommended_amount) else None,
                    "project_status": project_status,
                }
                events.append(recommended_event)

            if completed_date:
                completion_event = {
                    "event_id": self._event_id("hist", project_id, EventType.PROJECT_COMPLETED.value, source_id),
                    "event_type": EventType.PROJECT_COMPLETED.value,
                    "event_timestamp": completed_date,
                    "event_source": EventSource.HISTORICAL_REPLAY.value,
                    "project_id": project_id,
                    "mp_name": mp_name,
                    "state": state,
                    "constituency": constituency,
                    "work_description": work_description,
                    "category": category,
                    "final_amount": float(final_amount) if pd.notna(final_amount) else None,
                    "completed_date": completed_date,
                    "project_status": "completed",
                }
                events.append(completion_event)

        for expenditure_index, (_, row) in enumerate(expenditures_df.iterrows()):
            source = row.to_dict()
            project_id, mapping_status = self._resolve_expenditure(source, project_lookup)
            payment_timestamp = self._coerce_iso(row.get("expenditure_date"))
            if not payment_timestamp:
                continue
            source_id = self._fingerprint(source, expenditure_index)
            project_key = project_id or f"unresolved-{source_id}"
            mp_name = self._text(row.get("mp_name"))
            state = self._text(row.get("state"))
            constituency = self._text(row.get("constituency"))
            work_description = self._text(row.get("work_description"))
            payment_status, payment_status_raw = normalize_payment_status(row.get("payment_status"))
            payment_status = payment_status or "unknown"
            project_status = payment_status
            payment_event = {
                "event_id": self._event_id("hist", project_key, EventType.PAYMENT_RECEIVED.value, source_id),
                "event_type": EventType.PAYMENT_RECEIVED.value,
                "event_timestamp": payment_timestamp,
                "event_source": EventSource.HISTORICAL_REPLAY.value,
                "project_id": project_key,
                "mapping_status": mapping_status,
                "mp_name": mp_name,
                "state": state,
                "constituency": constituency,
                "work_description": work_description,
                "expenditure_amount": float(row.get("expenditure_amount")) if pd.notna(row.get("expenditure_amount")) else None,
                "vendor": str(row.get("vendor") or "").strip(),
                "payment_status": payment_status,
                "payment_status_raw": payment_status_raw,
                "payment_date": payment_timestamp,
                "project_status": project_status,
            }
            payment_status_event = {
                "event_id": self._event_id("hist", project_key, EventType.PAYMENT_STATUS_UPDATED.value, source_id),
                "event_type": EventType.PAYMENT_STATUS_UPDATED.value,
                "event_timestamp": payment_timestamp,
                "event_source": EventSource.HISTORICAL_REPLAY.value,
                "project_id": project_key,
                "mapping_status": mapping_status,
                "mp_name": mp_name,
                "state": state,
                "constituency": constituency,
                "work_description": work_description,
                "payment_status": payment_status,
                "payment_status_raw": payment_status_raw,
                "payment_date": payment_timestamp,
                "project_status": project_status,
            }
            events.extend([payment_event, payment_status_event])

        if include_synthetic:
            demo_event = {
                "event_id": "demo-sample-001",
                "event_type": EventType.PROJECT_STATUS_UPDATED.value,
                "event_timestamp": self._coerce_iso(datetime.now(timezone.utc).isoformat()),
                "event_source": EventSource.SYNTHETIC_DEMO.value,
                "project_id": "DEMO-001",
                "mp_name": "Synthetic Demo MP",
                "state": "Demo State",
                "constituency": "Demo Constituency",
                "project_status": "in_progress",
            }
            events.append(demo_event)

        events = sorted(events, key=lambda e: (e.get("event_timestamp") or "", e.get("event_type") or ""))
        if limit is not None:
            events = events[:limit]
        return events
