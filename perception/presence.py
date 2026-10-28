"""Customer presence state machine.

The old approach compared the box area of consecutive frames, which fired on
every little movement. This tracker needs a person to be *near* (box covers
enough of the frame) for several consecutive detections before it says ENTER,
and needs them gone for a few seconds before it says LEAVE.
"""
from __future__ import annotations

import time
from enum import Enum


class PresenceEvent(str, Enum):
    ENTER = "enter"
    LEAVE = "leave"


class PresenceTracker:
    def __init__(
        self,
        near_area_ratio: float = 0.06,
        enter_frames: int = 6,
        leave_seconds: float = 4.0,
        greet_cooldown_seconds: float = 12.0,
        clock=time.monotonic,
    ):
        self.near_area_ratio = near_area_ratio
        self.enter_frames = max(1, enter_frames)
        self.leave_seconds = leave_seconds
        self.greet_cooldown = greet_cooldown_seconds
        self._clock = clock

        self.present = False
        self.consecutive_near = 0
        self.last_seen: float | None = None
        self.last_leave: float | None = None
        self.entered_at: float | None = None
        self.max_area_ratio = 0.0
        self.people_count = 0

    def update(self, detections, frame_shape) -> list[PresenceEvent]:
        now = self._clock()
        events: list[PresenceEvent] = []
        ratios = [d.area_ratio(frame_shape) for d in detections]
        self.people_count = len(detections)
        self.max_area_ratio = max(ratios) if ratios else 0.0
        near = self.max_area_ratio >= self.near_area_ratio

        if near:
            self.consecutive_near += 1
            self.last_seen = now
            cooldown_ok = self.last_leave is None or (now - self.last_leave) >= self.greet_cooldown
            if not self.present and self.consecutive_near >= self.enter_frames and cooldown_ok:
                self.present = True
                self.entered_at = now
                events.append(PresenceEvent.ENTER)
        else:
            self.consecutive_near = 0
            if self.present and self.last_seen is not None and (now - self.last_seen) >= self.leave_seconds:
                self.present = False
                self.last_leave = now
                events.append(PresenceEvent.LEAVE)
        return events

    def force_leave(self) -> None:
        """Called when the conversation ends on its own (customer said bye)."""
        if self.present:
            self.present = False
            self.last_leave = self._clock()

    def status_text(self) -> str:
        state = "CUSTOMER" if self.present else "idle"
        return f"{state}  people={self.people_count}  near={self.max_area_ratio:.2f}"
