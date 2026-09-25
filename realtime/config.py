from __future__ import annotations

from pathlib import Path

REALTIME_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = REALTIME_ROOT.parent

DATA_DIR = REALTIME_ROOT / "data"
EVENTS_DIR = DATA_DIR / "events"
RUNTIME_DIR = DATA_DIR / "runtime"

EVENT_LOG_PATH = EVENTS_DIR / "events.jsonl"
PROJECT_STATE_PATH = RUNTIME_DIR / "project_state.json"
MP_STATE_PATH = RUNTIME_DIR / "mp_state.json"
VALIDATION_ERROR_PATH = RUNTIME_DIR / "validation_errors.jsonl"

SIGNALS = ("START", "PAUSE", "RESUME", "STOP", "RESET")

FROZEN_FILES = [
    PROJECT_ROOT / "data" / "master" / "master_works.csv",
    PROJECT_ROOT / "data" / "master" / "master_mp_summary.csv",
    PROJECT_ROOT / "data" / "features" / "project_features.csv",
    PROJECT_ROOT / "data" / "features" / "mp_features.csv",
    PROJECT_ROOT / "data" / "features" / "project_similarity_data.csv",
    PROJECT_ROOT / "data" / "master" / "vendor_features.csv",
    PROJECT_ROOT / "data" / "location" / "project_locations.csv",
    PROJECT_ROOT / "data" / "location" / "project_similarity_location.csv",
]


def ensure_runtime_layout() -> None:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    for path in (EVENT_LOG_PATH, PROJECT_STATE_PATH, MP_STATE_PATH, VALIDATION_ERROR_PATH):
        if not path.exists():
            path.write_text("", encoding="utf-8")


def snapshot_frozen_files() -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in FROZEN_FILES:
        if path.exists():
            stat = path.stat()
            snapshot[str(path)] = (stat.st_mtime_ns, stat.st_size)
    return snapshot
