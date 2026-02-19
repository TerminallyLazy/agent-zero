"""Detection event storage for Prompt Stomper.

Stores scan events in memory with optional persistence to disk.
Used by extensions to log detections and by the dashboard API to retrieve them.
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from python.helpers import files


LOG_FILE = files.get_abs_path("usr", "prompt_stomper", "detection_log.json")
MAX_EVENTS = 500


@dataclass
class DetectionEvent:
    timestamp: float
    scan_type: str        # "direct", "indirect", "canary"
    severity: int         # 0-3
    severity_name: str
    score: float
    action: str           # "pass", "log", "warn", "block"
    categories: list[str]
    text_snippet: str
    source: str = ""      # e.g., "user_message", "tool:knowledge_tool", "canary"

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "scan_type": self.scan_type,
            "severity": self.severity,
            "severity_name": self.severity_name,
            "score": round(self.score, 3),
            "action": self.action,
            "categories": self.categories,
            "text_snippet": self.text_snippet[:200],
            "source": self.source,
        }


class StomperLog:
    def __init__(self):
        self._lock = threading.RLock()
        self._events: list[DetectionEvent] = []
        self._stats = {"total_scans": 0, "total_blocks": 0, "total_warns": 0}

    def add_event(self, event: DetectionEvent):
        with self._lock:
            self._events.append(event)
            self._stats["total_scans"] += 1
            if event.action == "block":
                self._stats["total_blocks"] += 1
            elif event.action == "warn":
                self._stats["total_warns"] += 1

            # Enforce limit
            if len(self._events) > MAX_EVENTS:
                self._events = self._events[-MAX_EVENTS:]

    def record_scan(self):
        """Record a scan that found nothing notable (Safe result)."""
        with self._lock:
            self._stats["total_scans"] += 1

    def get_events(self, limit: int = 50, offset: int = 0, min_severity: int = 0) -> list[dict]:
        with self._lock:
            filtered = [e for e in self._events if e.severity >= min_severity]
            # Most recent first
            filtered.reverse()
            page = filtered[offset:offset + limit]
            return [e.to_dict() for e in page]

    def get_stats(self) -> dict:
        with self._lock:
            last_event = self._events[-1].to_dict() if self._events else None
            return {
                **self._stats,
                "event_count": len(self._events),
                "last_event": last_event,
            }

    def clear(self):
        with self._lock:
            self._events = []
            self._stats = {"total_scans": 0, "total_blocks": 0, "total_warns": 0}

    def save_to_disk(self):
        """Persist current events to disk."""
        with self._lock:
            data = {
                "events": [e.to_dict() for e in self._events],
                "stats": self._stats,
            }
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "w") as f:
            json.dump(data, f)

    def load_from_disk(self):
        """Load events from disk if available."""
        if not os.path.exists(LOG_FILE):
            return
        try:
            with open(LOG_FILE, "r") as f:
                data = json.load(f)
            with self._lock:
                for e in data.get("events", []):
                    self._events.append(DetectionEvent(
                        timestamp=e["timestamp"],
                        scan_type=e["scan_type"],
                        severity=e["severity"],
                        severity_name=e["severity_name"],
                        score=e["score"],
                        action=e["action"],
                        categories=e["categories"],
                        text_snippet=e["text_snippet"],
                        source=e.get("source", ""),
                    ))
                self._stats = data.get("stats", self._stats)
        except (json.JSONDecodeError, KeyError):
            pass  # Corrupt file, start fresh


# Module-level singleton
_stomper_log = StomperLog()


def get_stomper_log() -> StomperLog:
    return _stomper_log
