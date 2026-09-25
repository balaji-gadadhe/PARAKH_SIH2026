from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, VALIDATION_ERROR_PATH, ensure_runtime_layout
from .models import EventStatus
from .schemas import validate_event
from .runtime_state import StateManager


class EventProcessor:
    def __init__(self, root: str | Path = PROJECT_ROOT):
        self.root = Path(root)
        ensure_runtime_layout()
        self.state_manager = StateManager(root=self.root)
        self.event_log_path = self.root / "realtime" / "data" / "events" / "events.jsonl"
        self.validation_error_path = VALIDATION_ERROR_PATH
        self.seen_event_ids: set[str] = set()
        self.duplicate_events = 0
        self.invalid_events = 0
        self.processed_events = 0
        self.unresolved_mappings = 0
        self.ambiguous_mappings = 0
        self.reset_runtime()
        self.loaded_event_ids()

    def reset_runtime(self) -> None:
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.validation_error_path.parent.mkdir(parents=True, exist_ok=True)
        for path in (self.event_log_path, self.validation_error_path):
            if path.exists():
                path.write_text("", encoding="utf-8")
        self.seen_event_ids.clear()
        self.duplicate_events = 0
        self.invalid_events = 0
        self.processed_events = 0
        self.unresolved_mappings = 0
        self.ambiguous_mappings = 0

    def loaded_event_ids(self) -> None:
        self.seen_event_ids.clear()
        if not self.event_log_path.exists():
            return
        with self.event_log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    event_id = payload.get("event_id")
                    if event_id:
                        self.seen_event_ids.add(str(event_id))
                except json.JSONDecodeError:
                    continue

    def _record_validation_error(self, event: dict[str, Any], reason: str) -> None:
        payload = {
            "event": event,
            "reason": reason,
        }
        with self.validation_error_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")

    def _append_event_log(self, event: dict[str, Any]) -> None:
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.event_log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str) + "\n")

    def process_event(self, event: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(event, dict):
            self.invalid_events += 1
            self._record_validation_error({"event": event}, "event is not a dictionary")
            return {"event_status": EventStatus.INVALID, "event": event, "message": "Invalid event payload"}

        mapping_status = str(event.get("mapping_status", "")).lower()
        if mapping_status in {"unresolved", "ambiguous"}:
            if mapping_status == "ambiguous":
                self.ambiguous_mappings += 1
            else:
                self.unresolved_mappings += 1
            self._record_validation_error(event, f"{mapping_status} project mapping")
            return {"event_status": EventStatus.SKIPPED, "event": event, "message": f"{mapping_status} project mapping"}

        try:
            cleaned = validate_event(event)
        except ValueError as exc:
            self.invalid_events += 1
            self._record_validation_error(event, str(exc))
            return {"event_status": EventStatus.INVALID, "event": event, "message": str(exc)}

        event_id = str(cleaned.get("event_id", "")).strip()
        if not event_id:
            self.invalid_events += 1
            self._record_validation_error(cleaned, "missing event_id")
            return {"event_status": EventStatus.INVALID, "event": cleaned, "message": "missing event_id"}

        if event_id in self.seen_event_ids:
            self.duplicate_events += 1
            return {"event_status": EventStatus.DUPLICATE, "event": cleaned, "message": "duplicate event_id"}

        self.seen_event_ids.add(event_id)
        self.processed_events += 1
        self._append_event_log(cleaned)
        self.state_manager.apply_event(cleaned)
        return {"event_status": EventStatus.PROCESSED, "event": cleaned, "message": "processed"}

    def process_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for event in events:
            results.append(self.process_event(event))
        return results

    def get_event_history(self, project_id: str | None = None, event_type: str | None = None):
        items: list[dict[str, Any]] = []
        if not self.event_log_path.exists():
            return items
        with self.event_log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if project_id and str(payload.get("project_id", "")) != str(project_id):
                    continue
                if event_type and str(payload.get("event_type", "")) != str(event_type):
                    continue
                items.append(payload)
        return items
