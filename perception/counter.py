"""Counter billing camera: find items placed on the counter and recognise them.

How it works (no training needed):
  1. Keep a photo of the EMPTY counter as reference.
  2. Anything that differs from the reference is an object: diff -> threshold -> blobs.
  3. Each blob is cropped and embedded (DINOv2); the closest learned product wins.
  4. Quantity of identical items touching each other is estimated from blob area.
  5. A stabiliser waits until the set of items stops changing before billing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np


@dataclass
class CounterItem:
    key: str | None
    name: str
    score: float
    box: tuple[int, int, int, int]      # x1, y1, x2, y2 in full-frame coordinates
    qty: int = 1
    area: float = 0.0

    @property
    def known(self) -> bool:
        return self.key is not None


def signature(items: list[CounterItem]) -> tuple:
    counts: dict[str, int] = {}
    for it in items:
        k = it.key or "?"
        counts[k] = counts.get(k, 0) + it.qty
    return tuple(sorted(counts.items()))


class CounterRecognizer:
    def __init__(self, settings, inventory, library, embedder):
        self.settings = settings
        self.inventory = inventory
        self.library = library
        self.embedder = embedder
        self.reference: np.ndarray | None = None      # gray, blurred, ROI size
        self.reference_time = 0.0
        self.last_items: list[CounterItem] = []
        self.last_boxes: list[tuple[int, int, int, int]] = []
        self.last_empty_since: float | None = None
        self.exclude_boxes: list[tuple[int, int, int, int]] = []   # full-frame boxes to ignore (people)

    # ---- geometry ----
    def roi_rect(self, frame) -> tuple[int, int, int, int]:
        h, w = frame.shape[:2]
        cam = self.settings.camera(self.settings.counter_camera_role())
        roi = cam.roi if cam and cam.roi else None
        if not roi or len(roi) != 4:
            return 0, 0, w, h
        x, y, rw, rh = roi
        return int(x * w), int(y * h), max(16, int(rw * w)), max(16, int(rh * h))

    def roi_crop(self, frame):
        x, y, w, h = self.roi_rect(frame)
        return frame[y:y + h, x:x + w]

    @staticmethod
    def _prep_gray(bgr):
        import cv2

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (7, 7), 0)

    # ---- reference (empty counter) ----
    def set_reference(self, frame) -> None:
        self.reference = self._prep_gray(self.roi_crop(frame))
        self.reference_time = time.monotonic()

    @property
    def has_reference(self) -> bool:
        return self.reference is not None

    def maybe_refresh_reference(self, frame, busy: bool) -> bool:
        """Re-learn the empty counter when nothing is on it for a while (handles lighting drift)."""
        if busy:
            self.last_empty_since = None
            return False
        if not self.has_reference:
            self.set_reference(frame)
            return True
        now = time.monotonic()
        if self.last_boxes:
            self.last_empty_since = None
            return False
        if self.last_empty_since is None:
            self.last_empty_since = now
            return False
        if now - self.last_empty_since >= self.settings.counter_reference_refresh_seconds:
            self.set_reference(frame)
            self.last_empty_since = now
            return True
        return False

    # ---- segmentation ----
    def segment(self, roi_bgr) -> list[tuple[int, int, int, int]]:
        import cv2

        if self.reference is None:
            return []
        gray = self._prep_gray(roi_bgr)
        if gray.shape != self.reference.shape:
            self.reference = None
            return []
        diff = cv2.absdiff(gray, self.reference)
        _, mask = cv2.threshold(diff, self.settings.counter_diff_threshold, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.dilate(mask, kernel, iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = gray.shape
        min_area = self.settings.counter_min_area_ratio * h * w
        boxes = []
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            if bw * bh < min_area or bw < 12 or bh < 12:
                continue
            if bw * bh > 0.85 * h * w:        # whole counter changed: light switched / camera moved
                continue
            boxes.append((x, y, x + bw, y + bh))
        return boxes

    # ---- recognition ----
    def recognize(self, frame) -> list[CounterItem]:
        rx, ry, _, _ = self.roi_rect(frame)
        roi = self.roi_crop(frame)
        boxes = [b for b in self.segment(roi) if not self._overlaps_excluded((b[0] + rx, b[1] + ry, b[2] + rx, b[3] + ry))]
        self.last_boxes = boxes
        if not boxes:
            self.last_items = []
            return []
        crops = [roi[y1:y2, x1:x2] for (x1, y1, x2, y2) in boxes]
        vecs = self.embedder.embed(crops)
        items: list[CounterItem] = []
        roi_area = float(roi.shape[0] * roi.shape[1])
        for (x1, y1, x2, y2), vec in zip(boxes, vecs):
            key, score = self.library.match(vec)
            area = (x2 - x1) * (y2 - y1) / roi_area
            if key is None or score < self.settings.counter_match_threshold:
                items.append(CounterItem(None, "unknown item", score, (x1 + rx, y1 + ry, x2 + rx, y2 + ry), 1, area))
                continue
            product = self.inventory.get(key)
            name = product.name if product else key
            qty = 1
            med = self.library.median_area(key)
            if med and med > 0:
                ratio = area / med
                if ratio >= 1.6:
                    qty = int(min(6, round(ratio)))
            items.append(CounterItem(key, name, score, (x1 + rx, y1 + ry, x2 + rx, y2 + ry), qty, area))
        self.last_items = items
        return items

    def _overlaps_excluded(self, box) -> bool:
        x1, y1, x2, y2 = box
        area = max(1, (x2 - x1) * (y2 - y1))
        for ex1, ey1, ex2, ey2 in self.exclude_boxes:
            ix = max(0, min(x2, ex2) - max(x1, ex1))
            iy = max(0, min(y2, ey2) - max(y1, ey1))
            if ix * iy / area > 0.5:
                return True
        return False

    # ---- learning ----
    def learn_from_frame(self, frame, key: str) -> tuple[int, str]:
        """Learn the single largest object on the counter as product `key`."""
        roi = self.roi_crop(frame)
        boxes = self.segment(roi)
        if not boxes:
            return 0, "nothing on the counter (or reference not set)"
        x1, y1, x2, y2 = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        crop = roi[y1:y2, x1:x2]
        area = (x2 - x1) * (y2 - y1) / float(roi.shape[0] * roi.shape[1])
        vec = self.embedder.embed([crop])
        return self.library.add(key, vec, [area], [crop]), "ok"


class ItemStabilizer:
    """Emits the counter contents only after they have stayed the same for a while."""

    def __init__(self, stable_seconds: float = 1.2, clock=time.monotonic):
        self.stable_seconds = stable_seconds
        self._clock = clock
        self._candidate: tuple | None = None
        self._candidate_since = 0.0
        self.committed: tuple | None = None
        self.committed_items: list[CounterItem] = field(default_factory=list) if False else []

    def update(self, items: list[CounterItem]) -> list[CounterItem] | None:
        sig = signature(items)
        now = self._clock()
        if sig != self._candidate:
            self._candidate, self._candidate_since = sig, now
            return None
        if sig == self.committed:
            return None
        if now - self._candidate_since >= self.stable_seconds:
            self.committed = sig
            self.committed_items = list(items)
            return list(items)
        return None

    def reset(self) -> None:
        self._candidate = None
        self.committed = None
        self.committed_items = []
