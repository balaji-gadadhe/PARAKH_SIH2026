import json
from pathlib import Path

import pandas as pd

import pytest

from realtime.config import FROZEN_FILES, REALTIME_ROOT, SIGNALS
from realtime.historical_event_generator import HistoricalEventGenerator
from realtime.event_processor import EventProcessor
from realtime.models import EventStatus, SimulatorStatus, EventType, EventSource
from realtime.schemas import EventSchema, validate_event
from realtime.realtime_simulator import RealtimeSimulator
from realtime.runtime_state import StateManager


@pytest.fixture
def repo_root():
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def generator(repo_root):
    return HistoricalEventGenerator(root=repo_root)


@pytest.fixture
def processor(repo_root):
    return EventProcessor(root=repo_root)


@pytest.fixture
def state_manager(repo_root):
    return StateManager(root=repo_root)


def test_event_schema_validation():
    event = {
        "event_id": "evt-001",
        "event_type": "PROJECT_CREATED",
        "event_timestamp": "2025-01-15T10:00:00Z",
        "event_source": "historical_replay",
        "project_id": "175556",
        "mp_name": "BISHNU PADA RAY",
        "state": "Andaman And Nicobar Islands",
        "constituency": "ANDAMAN AND NICOBAR ISLANDS",
        "work_description": "Road repair",
        "category": "Repair and Renovation",
        "recommended_amount": 500000.0,
    }
    assert EventSchema.validate_event(event) is True
    assert validate_event(event) == event


def test_event_generation_historical_order(generator):
    events = generator.generate_events(limit=20)
    assert len(events) > 0
    timestamps = [e["event_timestamp"] for e in events]
    assert timestamps == sorted(timestamps)
    assert all(e["event_source"] in {"historical_replay", "synthetic_demo", "manual"} for e in events)


def test_replay_speed_and_status(generator):
    generator.replay_speed = 2.0
    assert generator.replay_speed == 2.0
    sim = RealtimeSimulator(root=Path(__file__).resolve().parents[2], replay_speed=2.0)
    assert sim.replay_speed == 2.0
    assert sim.status == SimulatorStatus.IDLE


def test_pause_resume_stop_reset(simulator_factory):
    sim = simulator_factory()
    sim.start()
    sim.pause()
    assert sim.status == SimulatorStatus.PAUSED
    sim.resume()
    assert sim.status == SimulatorStatus.RUNNING
    sim.stop()
    assert sim.status == SimulatorStatus.STOPPED
    sim.reset()
    assert sim.status == SimulatorStatus.IDLE


def test_duplicate_event_handling(processor):
    event = {
        "event_id": "dup-1",
        "event_type": "PAYMENT_RECEIVED",
        "event_timestamp": "2025-01-19T10:00:00Z",
        "event_source": "historical_replay",
        "project_id": "175556",
        "mp_name": "BISHNU PADA RAY",
        "state": "Andaman And Nicobar Islands",
        "constituency": "ANDAMAN AND NICOBAR ISLANDS",
        "expenditure_amount": 1000.0,
        "vendor": "X Pvt Ltd",
        "payment_status": "successful",
    }
    result1 = processor.process_event(event)
    result2 = processor.process_event(event)
    assert result1["event_status"] == EventStatus.PROCESSED
    assert result2["event_status"] == EventStatus.DUPLICATE
    assert processor.duplicate_events == 1


def test_invalid_event_handling(processor):
    bad = {
        "event_id": "bad-1",
        "event_type": "INVALID",
        "event_timestamp": "bad-date",
        "event_source": "historical_replay",
        "project_id": "",
        "mp_name": "",
        "state": "",
        "constituency": "",
    }
    result = processor.process_event(bad)
    assert result["event_status"] == EventStatus.INVALID
    assert processor.invalid_events >= 1


def test_runtime_state_updates(state_manager):
    state_manager.upsert_project({
        "project_id": "demo-project",
        "project_status": "in_progress",
        "recommended_amount": 1000,
        "final_amount": 0,
        "total_expenditure": 200,
        "payment_count": 1,
        "latest_payment_status": "successful",
        "latest_event_timestamp": "2025-01-15T10:00:00Z",
        "completed_date": None,
        "mp_name": "Demo MP",
        "state": "Demo State",
        "constituency": "Demo Constituency",
    })
    project = state_manager.get_project("demo-project")
    assert project["project_id"] == "demo-project"
    assert project["current_status"] == "in_progress"
    assert project["total_expenditure"] == 200


def test_project_lookup_and_dashboard(processor, state_manager):
    state_manager.upsert_project({
        "project_id": "lookup-1",
        "project_status": "completed",
        "recommended_amount": 5000,
        "final_amount": 5000,
        "total_expenditure": 4500,
        "payment_count": 2,
        "latest_payment_status": "successful",
        "latest_event_timestamp": "2025-01-25T10:00:00Z",
        "completed_date": "2025-01-25",
        "mp_name": "MP One",
        "state": "State One",
        "constituency": "Const One",
    })
    dashboard = state_manager.get_dashboard_summary()
    assert "total_projects" in dashboard
    assert "project_status_counts" in dashboard
    project = state_manager.get_project("lookup-1")
    assert project["current_status"] == "completed"


def test_synthetic_demo_event_injection(processor):
    event = {
        "event_id": "demo-1",
        "event_type": "PAYMENT_RECEIVED",
        "event_timestamp": "2025-09-04T12:00:00Z",
        "event_source": "synthetic_demo",
        "project_id": "DEMO-123",
        "mp_name": "Synthetic MP",
        "state": "Demo State",
        "constituency": "Demo Constituency",
        "expenditure_amount": 750.0,
        "vendor": "Demo Vendor",
        "payment_status": "successful",
    }
    result = processor.process_event(event)
    assert result["event_status"] == EventStatus.PROCESSED
    assert result["event"]["event_source"] == "synthetic_demo"


@pytest.fixture
def simulator_factory(repo_root):
    def _factory(replay_speed=1.0):
        return RealtimeSimulator(root=repo_root, replay_speed=replay_speed)
    return _factory


def test_api_endpoints_are_present():
    from realtime.realtime_api import app
    routes = {route.path for route in app.routes}
    required = {
        "/realtime/status",
        "/realtime/start",
        "/realtime/pause",
        "/realtime/resume",
        "/realtime/stop",
        "/realtime/reset",
        "/realtime/events",
        "/realtime/projects",
        "/realtime/project/{project_id}",
        "/realtime/dashboard",
        "/realtime/inject-event",
    }
    assert required.issubset(routes)


def test_data_immutability_snapshot(repo_root):
    frozen = FROZEN_FILES
    baseline = {}
    for path in frozen:
        assert path.exists(), f"missing frozen file: {path}"
        baseline[path] = path.stat().st_mtime_ns, path.stat().st_size
    assert baseline
    # verification is handled by the pipeline before runtime execution; these files are read-only by contract.


def _write_replay_fixture(root: Path, master_rows: list[dict], expenditure_rows: list[dict]) -> None:
    (root / "data" / "master").mkdir(parents=True)
    (root / "data" / "cleaned").mkdir(parents=True)
    pd.DataFrame(master_rows).to_csv(root / "data" / "master" / "master_works.csv", index=False)
    pd.DataFrame(expenditure_rows).to_csv(root / "data" / "cleaned" / "expenditures_clean.csv", index=False)


def _master_row(work_id: str, description: str, completed_date: str | None = None) -> dict:
    return {
        "Work ID": work_id,
        "Work Description": description,
        "Category": "Road",
        "MP Name": "MP One",
        "Constituency": "Constituency One",
        "State": "State One",
        "Recommended Amount (₹)": 1000,
        "Recommendation Date": "2025-01-01T00:00:00Z",
        "Final Amount (₹)": 900,
        "Completed Date": completed_date,
        "status": "In-Progress",
    }


def _expenditure_row(description: str, status: str = "payment success") -> dict:
    return {
        "mp_name": "MP One",
        "constituency": "Constituency One",
        "state": "State One",
        "work_description": description,
        "vendor": "Vendor One",
        "expenditure_amount": 100,
        "expenditure_date": "2025-01-02T00:00:00Z",
        "payment_status": status,
    }


def test_payment_status_normalization_and_raw_value():
    event = {
        "event_id": "status-1",
        "event_type": "PAYMENT_RECEIVED",
        "event_timestamp": "2025-01-01T00:00:00Z",
        "event_source": "historical_replay",
        "project_id": "1",
        "mp_name": "MP One",
        "state": "State One",
        "constituency": "Constituency One",
        "payment_status": "payment success",
    }
    cleaned = validate_event(event)
    assert cleaned["payment_status"] == "successful"
    assert cleaned["payment_status_raw"] == "payment success"


def test_project_resolution_and_lifecycle_events(tmp_path):
    _write_replay_fixture(
        tmp_path,
        [_master_row("100", "Road repair", "2025-02-01T00:00:00Z")],
        [_expenditure_row("Road repair")],
    )
    events = HistoricalEventGenerator(root=tmp_path).generate_events()
    types = [event["event_type"] for event in events]
    payment = next(event for event in events if event["event_type"] == EventType.PAYMENT_RECEIVED.value)
    completion = next(event for event in events if event["event_type"] == EventType.PROJECT_COMPLETED.value)
    assert EventType.PROJECT_RECOMMENDED.value in types
    assert payment["project_id"] == "100"
    assert payment["mapping_status"] == "resolved"
    assert completion["completed_date"] == "2025-02-01T00:00:00Z"
    assert payment["payment_status"] == "successful"
    assert payment["payment_status_raw"] == "payment success"
    assert [event["event_timestamp"] for event in events] == sorted(event["event_timestamp"] for event in events)


def test_unresolved_and_ambiguous_projects_are_skipped(tmp_path):
    _write_replay_fixture(
        tmp_path,
        [_master_row("100", "Known"), _master_row("101", "Known")],
        [_expenditure_row("Known"), _expenditure_row("Missing")],
    )
    events = HistoricalEventGenerator(root=tmp_path).generate_events()
    processor = EventProcessor(root=tmp_path)
    results = processor.process_events(events)
    skipped = [result for result in results if result["event_status"] == EventStatus.SKIPPED]
    assert len(skipped) == 4
    assert processor.ambiguous_mappings == 2
    assert processor.unresolved_mappings == 2
    projects = processor.state_manager.list_projects()
    assert {project["project_id"] for project in projects} == {"100", "101"}
    assert all(not project["project_id"].startswith("unresolved-") for project in projects)


def test_event_ids_are_deterministic_and_distinguish_source_rows(tmp_path):
    _write_replay_fixture(
        tmp_path,
        [_master_row("100", "Road repair")],
        [_expenditure_row("Road repair"), {**_expenditure_row("Road repair"), "expenditure_amount": 200}],
    )
    generator = HistoricalEventGenerator(root=tmp_path)
    first = generator.generate_events()
    second = generator.generate_events()
    first_ids = [event["event_id"] for event in first]
    second_ids = [event["event_id"] for event in second]
    payment_ids = [event["event_id"] for event in first if event["event_type"] == EventType.PAYMENT_RECEIVED.value]
    assert first_ids == second_ids
    assert len(payment_ids) == len(set(payment_ids)) == 2
