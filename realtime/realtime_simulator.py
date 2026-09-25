from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, ensure_runtime_layout
from .historical_event_generator import HistoricalEventGenerator
from .event_processor import EventProcessor
from .models import SimulatorStatus


class RealtimeSimulator:
    def __init__(self, root: str | Path = PROJECT_ROOT, replay_speed: float = 1.0):
        self.root = Path(root)
        self.replay_speed = float(replay_speed)
        self.status = SimulatorStatus.IDLE
        self.event_generator = HistoricalEventGenerator(root=self.root, replay_speed=self.replay_speed)
        self.event_processor = EventProcessor(root=self.root)
        self._event_buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        ensure_runtime_layout()

    def load_events(self) -> list[dict[str, Any]]:
        self._event_buffer = self.event_generator.generate_events()
        return list(self._event_buffer)

    def start(self) -> dict[str, Any]:
        with self._lock:
            if not self._event_buffer:
                self._event_buffer = self.load_events()
            self.status = SimulatorStatus.RUNNING
            return {"status": self.status.value, "events_loaded": len(self._event_buffer)}

    def pause(self) -> dict[str, Any]:
        with self._lock:
            if self.status == SimulatorStatus.RUNNING:
                self.status = SimulatorStatus.PAUSED
            return {"status": self.status.value}

    def resume(self) -> dict[str, Any]:
        with self._lock:
            if self.status == SimulatorStatus.PAUSED:
                self.status = SimulatorStatus.RUNNING
            return {"status": self.status.value}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self.status = SimulatorStatus.STOPPED
            return {"status": self.status.value}

    def reset(self) -> dict[str, Any]:
        with self._lock:
            self.status = SimulatorStatus.IDLE
            self._event_buffer = []
            return {"status": self.status.value}

    def run_replay(self) -> list[dict[str, Any]]:
        if not self._event_buffer:
            self.load_events()
        results = []
        for event in self._event_buffer:
            if self.status in {SimulatorStatus.STOPPED, SimulatorStatus.IDLE}:
                break
            if self.status == SimulatorStatus.PAUSED:
                while self.status == SimulatorStatus.PAUSED:
                    time.sleep(0.05)
            results.append(self.event_processor.process_event(event))
            time.sleep(max(0.05, 1.0 / max(self.replay_speed, 0.1)))
        if self.status == SimulatorStatus.RUNNING:
            self.status = SimulatorStatus.COMPLETED
        return results

    def get_status_snapshot(self) -> dict[str, Any]:
        event_log = self.event_processor.get_event_history()
        return {
            "simulator_status": self.status.value,
            "events_total": len(self._event_buffer),
            "events_processed": self.event_processor.processed_events,
            "events_remaining": max(0, len(self._event_buffer) - self.event_processor.processed_events),
            "duplicate_events": self.event_processor.duplicate_events,
            "invalid_events": self.event_processor.invalid_events,
            "replay_speed": self.replay_speed,
            "latest_event_timestamp": event_log[-1]["event_timestamp"] if event_log else None,
        }
