from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    PROJECT_CREATED = "PROJECT_CREATED"
    PROJECT_RECOMMENDED = "PROJECT_RECOMMENDED"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    PAYMENT_STATUS_UPDATED = "PAYMENT_STATUS_UPDATED"
    PROJECT_STATUS_UPDATED = "PROJECT_STATUS_UPDATED"
    PROJECT_COMPLETED = "PROJECT_COMPLETED"


class EventSource(str, Enum):
    HISTORICAL_REPLAY = "historical_replay"
    SYNTHETIC_DEMO = "synthetic_demo"
    MANUAL = "manual"


class EventStatus(str, Enum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    INVALID = "invalid"
    SKIPPED = "skipped"


class SimulatorStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
