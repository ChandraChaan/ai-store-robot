from perception.person import Detection
from perception.presence import PresenceEvent, PresenceTracker

SHAPE = (480, 640, 3)
BIG = [Detection(100, 50, 400, 450, 0.9)]     # ~39% of frame: at the counter
SMALL = [Detection(10, 10, 60, 110, 0.9)]     # far away
NONE = []


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_enter_needs_consecutive_near_frames():
    clock = Clock()
    tr = PresenceTracker(near_area_ratio=0.06, enter_frames=3, leave_seconds=2, greet_cooldown_seconds=0, clock=clock)
    assert tr.update(BIG, SHAPE) == []
    assert tr.update(BIG, SHAPE) == []
    assert tr.update(BIG, SHAPE) == [PresenceEvent.ENTER]
    assert tr.update(BIG, SHAPE) == []           # no duplicate ENTER


def test_far_person_does_not_trigger():
    tr = PresenceTracker(near_area_ratio=0.06, enter_frames=1, clock=Clock())
    for _ in range(10):
        assert tr.update(SMALL, SHAPE) == []


def test_flicker_does_not_cause_leave():
    clock = Clock()
    tr = PresenceTracker(enter_frames=1, leave_seconds=3, greet_cooldown_seconds=0, clock=clock)
    assert tr.update(BIG, SHAPE) == [PresenceEvent.ENTER]
    clock.t = 1.0
    assert tr.update(NONE, SHAPE) == []          # missed detection for a moment
    clock.t = 2.0
    assert tr.update(BIG, SHAPE) == []
    clock.t = 6.0
    assert tr.update(NONE, SHAPE) == [PresenceEvent.LEAVE]


def test_greet_cooldown():
    clock = Clock()
    tr = PresenceTracker(enter_frames=1, leave_seconds=1, greet_cooldown_seconds=10, clock=clock)
    assert tr.update(BIG, SHAPE) == [PresenceEvent.ENTER]
    clock.t = 5
    assert tr.update(NONE, SHAPE) == [PresenceEvent.LEAVE]
    clock.t = 6
    assert tr.update(BIG, SHAPE) == []           # too soon, don't greet again
    clock.t = 16
    assert tr.update(BIG, SHAPE) == [PresenceEvent.ENTER]
