from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request

from .config import PROJECT_ROOT, ensure_runtime_layout
from .event_processor import EventProcessor
from .models import EventSource, EventType, SimulatorStatus
from .realtime_simulator import RealtimeSimulator

app = FastAPI(title="PARAKH Realtime API")
ROOT = Path(__file__).resolve().parents[1]
SIMULATOR = RealtimeSimulator(root=ROOT, replay_speed=1.0)


@app.on_event("startup")
def startup_event():
    ensure_runtime_layout()
    SIMULATOR.load_events()


@app.get("/realtime/status")
def get_status():
    return SIMULATOR.get_status_snapshot()


@app.post("/realtime/start")
def start_simulator():
    SIMULATOR.start()
    return SIMULATOR.get_status_snapshot()


@app.post("/realtime/pause")
def pause_simulator():
    return SIMULATOR.pause()


@app.post("/realtime/resume")
def resume_simulator():
    return SIMULATOR.resume()


@app.post("/realtime/stop")
def stop_simulator():
    return SIMULATOR.stop()


@app.post("/realtime/reset")
def reset_simulator():
    SIMULATOR.reset()
    return {"simulator_status": SimulatorStatus.IDLE.value}


@app.get("/realtime/events")
def get_events(
    event_type: str | None = None,
    project_id: str | None = None,
    state: str | None = None,
    constituency: str | None = None,
    event_source: str | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    processor = EventProcessor(root=ROOT)
    items = processor.get_event_history()
    filtered = []
    for event in items:
        if event_type and str(event.get("event_type", "")).upper() != str(event_type).upper():
            continue
        if project_id and str(event.get("project_id", "")) != str(project_id):
            continue
        if state and str(event.get("state", "")).lower() != str(state).lower():
            continue
        if constituency and str(event.get("constituency", "")).lower() != str(constituency).lower():
            continue
        if event_source and str(event.get("event_source", "")).lower() != str(event_source).lower():
            continue
        if from_timestamp and event.get("event_timestamp", "") < from_timestamp:
            continue
        if to_timestamp and event.get("event_timestamp", "") > to_timestamp:
            continue
        filtered.append(event)
    start = (page - 1) * page_size
    end = start + page_size
    return {"items": filtered[start:end], "page": page, "page_size": page_size, "total": len(filtered)}


@app.get("/realtime/projects")
def get_projects(
    state: str | None = None,
    constituency: str | None = None,
    status: str | None = None,
):
    project_state = SIMULATOR.event_processor.state_manager.list_projects(state=state, constituency=constituency, status=status)
    return {"projects": project_state}


@app.get("/realtime/project/{project_id}")
def get_project(project_id: str):
    project = SIMULATOR.event_processor.state_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    history = SIMULATOR.event_processor.get_event_history(project_id=project_id)
    return {"project": project, "event_history": history}


@app.get("/realtime/dashboard")
def get_dashboard():
    summary = SIMULATOR.event_processor.state_manager.get_dashboard_summary()
    all_events = SIMULATOR.event_processor.get_event_history()
    summary["events_processed"] = len(all_events)
    summary["latest_events"] = all_events[-5:]
    return summary


@app.post("/realtime/inject-event")
async def inject_event(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON payload must be an object")
    payload["event_source"] = str(payload.get("event_source") or EventSource.SYNTHETIC_DEMO.value)
    payload["event_id"] = str(payload.get("event_id") or f"DEMO-{uuid.uuid4()}")
    if not payload["event_id"].startswith("DEMO-"):
        payload["event_id"] = f"DEMO-{payload['event_id']}"
    if payload.get("event_type") not in {member.value for member in EventType}:
        raise HTTPException(status_code=400, detail="Unsupported event_type for synthetic demo")
    result = SIMULATOR.event_processor.process_event(payload)
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("realtime.realtime_api:app", host="0.0.0.0", port=8000, reload=False)
