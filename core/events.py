"""Small thread-safe event log shared by the camera loop, conversation and dashboard."""
from __future__ import annotations

import threading
import time
from collections import deque


class EventLog:
    def __init__(self, maxlen: int = 200):
        self._items: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, kind: str, text: str) -> None:
        entry = {"time": time.strftime("%H:%M:%S"), "ts": time.time(), "kind": kind, "text": text}
        with self._lock:
            self._items.append(entry)
        print(f"[{entry['time']}] {kind.upper():<9} {text}", flush=True)

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            items = list(self._items)
        return items[-limit:]


events = EventLog()
