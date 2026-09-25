from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, PROJECT_STATE_PATH, MP_STATE_PATH, ensure_runtime_layout


class StateManager:
    def __init__(self, root: str | Path = PROJECT_ROOT):
        self.root = Path(root)
        self.project_state_path = self.root / "realtime" / "data" / "runtime" / "project_state.json"
        self.mp_state_path = self.root / "realtime" / "data" / "runtime" / "mp_state.json"
        ensure_runtime_layout()
        self.reset_runtime_state()

    def reset_runtime_state(self) -> None:
        for path in (self.project_state_path, self.mp_state_path):
            if path.exists():
                path.write_text("{}", encoding="utf-8")

    def _load_json(self, path: Path, default: Any):
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)

    def get_project(self, project_id: str) -> dict[str, Any]:
        state = self._load_json(self.project_state_path, {})
        project = state.get(str(project_id), {})
        if isinstance(project, dict) and "current_status" not in project and "project_status" in project:
            project["current_status"] = project["project_status"]
        return project

    def list_projects(self, state: str | None = None, constituency: str | None = None, status: str | None = None):
        state_map = self._load_json(self.project_state_path, {})
        projects = []
        for project in state_map.values():
            if state and str(project.get("state", "")).strip().lower() != str(state).strip().lower():
                continue
            if constituency and str(project.get("constituency", "")).strip().lower() != str(constituency).strip().lower():
                continue
            if status and str(project.get("current_status", "")).strip().lower() != str(status).strip().lower():
                continue
            projects.append(project)
        return projects

    def upsert_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_json(self.project_state_path, {})
        project_id = str(payload.get("project_id", "")).strip()
        if not project_id:
            return payload

        normalized = dict(payload)
        if "current_status" not in normalized and "project_status" in normalized:
            normalized["current_status"] = normalized["project_status"]
        elif "current_status" not in normalized:
            normalized["current_status"] = "new"

        state[project_id] = normalized
        self._write_json(self.project_state_path, state)
        self._refresh_mp_state(state)
        return normalized

    def _refresh_mp_state(self, state: dict[str, Any]) -> None:
        mp_state: dict[str, Any] = {}
        for project in state.values():
            mp_name = str(project.get("mp_name", "")).strip() or "Unknown MP"
            bucket = mp_state.setdefault(
                mp_name,
                {
                    "mp_name": mp_name,
                    "project_count": 0,
                    "expenditure_total": 0.0,
                    "payment_count": 0,
                    "completed_count": 0,
                },
            )
            bucket["project_count"] += 1
            bucket["expenditure_total"] += float(project.get("total_expenditure") or 0)
            bucket["payment_count"] += int(project.get("payment_count") or 0)
            if str(project.get("current_status", "")).lower() == "completed":
                bucket["completed_count"] += 1
        self._write_json(self.mp_state_path, mp_state)

    def apply_event(self, event: dict[str, Any]) -> dict[str, Any]:
        project_id = str(event.get("project_id", "")).strip()
        base = self.get_project(project_id) or {
            "project_id": project_id,
            "current_status": "new",
            "recommended_amount": 0.0,
            "final_amount": 0.0,
            "total_expenditure": 0.0,
            "payment_count": 0,
            "latest_payment_status": "unknown",
            "latest_event_timestamp": None,
            "completed_date": None,
            "mp_name": event.get("mp_name", ""),
            "state": event.get("state", ""),
            "constituency": event.get("constituency", ""),
        }
        event_type = str(event.get("event_type", "")).upper()
        event_timestamp = event.get("event_timestamp")

        if "recommended_amount" in event and event.get("recommended_amount") is not None:
            base["recommended_amount"] = float(event["recommended_amount"])

        if "final_amount" in event and event.get("final_amount") is not None:
            base["final_amount"] = float(event["final_amount"])

        if event_type in {"PROJECT_CREATED", "PROJECT_RECOMMENDED"}:
            base["current_status"] = event.get("project_status") or "recommended"

        if event_type == "PAYMENT_RECEIVED":
            base["total_expenditure"] = float(base.get("total_expenditure") or 0.0) + float(event.get("expenditure_amount") or 0.0)
            base["payment_count"] = int(base.get("payment_count") or 0) + 1
            if event.get("payment_status"):
                base["latest_payment_status"] = str(event["payment_status"]).lower()

        if event_type == "PAYMENT_STATUS_UPDATED":
            if event.get("payment_status"):
                base["latest_payment_status"] = str(event["payment_status"]).lower()

        if event_type == "PROJECT_STATUS_UPDATED":
            base["current_status"] = event.get("project_status") or base.get("current_status") or "in_progress"

        if event_type == "PROJECT_COMPLETED":
            base["current_status"] = "completed"
            base["completed_date"] = event.get("completed_date")
            if event.get("final_amount") is not None:
                base["final_amount"] = float(event["final_amount"])

        base["mp_name"] = event.get("mp_name") or base.get("mp_name")
        base["state"] = event.get("state") or base.get("state")
        base["constituency"] = event.get("constituency") or base.get("constituency")
        base["latest_event_timestamp"] = event_timestamp
        self.upsert_project(base)
        return base

    def get_dashboard_summary(self) -> dict[str, Any]:
        projects = self.list_projects()
        project_status_counts: dict[str, int] = {}
        for project in projects:
            status = str(project.get("current_status") or "unknown")
            project_status_counts[status] = project_status_counts.get(status, 0) + 1
        total_expenditure = sum(float(project.get("total_expenditure") or 0.0) for project in projects)
        payments_processed = sum(int(project.get("payment_count") or 0) for project in projects)
        completed_projects = sum(1 for project in projects if str(project.get("current_status") or "").lower() == "completed")
        pending_payments = sum(1 for project in projects if str(project.get("latest_payment_status") or "").lower() in {"pending", "in_progress", "payment_in_progress"})
        return {
            "total_projects": len(projects),
            "events_processed": 0,
            "payments_processed": payments_processed,
            "completed_projects": completed_projects,
            "pending_payments": pending_payments,
            "total_expenditure": total_expenditure,
            "latest_events": [],
            "project_status_counts": project_status_counts,
        }

    def get_project_history(self, project_id: str):
        event_log_path = self.root / "realtime" / "data" / "events" / "events.jsonl"
        if not event_log_path.exists():
            return []
        history = []
        with event_log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(event.get("project_id", "")) == str(project_id):
                    history.append(event)
        return history

    def get_mp_state(self):
        return self._load_json(self.mp_state_path, {})
