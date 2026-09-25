# PARAKH Realtime Module

Historical-replay pipeline: replays the frozen MPLADS batch as chronological events with runtime state and a lightweight API.

> **It is a replay, not a live feed.** The datasets are historical; this module simulates their timeline. Never present it as real-time government monitoring (D-008/D-009).

## Pipeline

```text
historical_event_generator → schemas (validate) → event_processor (dedupe, log)
  → runtime_state (project/MP aggregates) → realtime_simulator (start/pause/resume/stop)
  → realtime_api (FastAPI)
```

**Event types:** `PROJECT_CREATED` · `PROJECT_RECOMMENDED` · `PAYMENT_RECEIVED` · `PAYMENT_STATUS_UPDATED` · `PROJECT_STATUS_UPDATED` · `PROJECT_COMPLETED`. Completion events are emitted only when `Completed Date` exists — dates are never invented. Verified totals: **239,230 events in ~38 s** (86,976 recommended · 76,063×2 payment · 128 completed).

## Key behaviors

- **Project ID mapping** — canonical `project_id` = existing `Work ID`. Expenditures match master projects on MP + State + Constituency + Work Description; only **exactly one** candidate resolves. Unresolved/ambiguous rows keep their raw fields, get a `mapping_status`, and are skipped before touching runtime state — no invented IDs.
- **Payment status normalization** — `payment success → successful`, `payment in-progress → payment_in_progress`; canonical value in `payment_status`, source preserved in `payment_status_raw`; unknown statuses are rejected as validation issues, not silently dropped.
- **Storage isolation** — reads frozen data only; writes only under `realtime/data/`:
  `events/events.jsonl` (processed history), `runtime/project_state.json`, `runtime/mp_state.json`, `runtime/validation_errors.jsonl`. Never writes to `data/` or the masters (D-015).

## Run

```bash
pip install -r realtime/requirements.txt

# replay API
uvicorn realtime.realtime_api:app --reload

# or drive the simulator directly
python -c "from realtime.realtime_simulator import RealtimeSimulator; s = RealtimeSimulator(); s.load_events(); s.start(); s.run_replay()"
```

## API endpoints

| | |
|---|---|
| `GET /realtime/status` | Simulator snapshot (status, processed/remaining, speed) |
| `POST /realtime/start` · `/pause` · `/resume` · `/stop` · `/reset` | Lifecycle control |
| `GET /realtime/events` | Event history (filter: type, project, state, constituency, source, timestamps; paginated) |
| `GET /realtime/projects` · `/realtime/project/{id}` | Runtime project state (+ per-project event history) |
| `GET /realtime/dashboard` | Aggregate summary + latest events |
| `POST /realtime/inject-event` | Inject a synthetic demo event (`event_source = synthetic_demo`, ID prefixed `DEMO-`) |

## Tests

```bash
python -m pytest realtime/tests/test_realtime_pipeline.py -q   # 15 passed
```

Covers validation, normalization, canonical resolution, unresolved/ambiguous skipping, deterministic IDs, lifecycle, chronology, runtime state, API routes, and data immutability.

## Limitations

- Lightweight in-process replay — not a distributed stream; JSON/JSONL storage is demo-grade.
- No connection to any live MPLADS feed.
- Expenditure rows without a unique master match are skipped for project state.
- FastAPI may log deprecation warnings for the startup hook depending on version.
