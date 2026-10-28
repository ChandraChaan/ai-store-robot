"""Threaded camera reader.

Reads frames continuously in a background thread so the main loop always gets
the *latest* frame (no lag build-up on IP/phone cameras) and reconnects
automatically if the stream drops.
"""
from __future__ import annotations

import os
import platform
import threading
import time

import cv2

ROTATIONS = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def parse_source(source: str | int):
    if isinstance(source, int):
        return source
    source = str(source).strip()
    return int(source) if source.isdigit() else source


class CameraStream:
    def __init__(self, source: str | int = 0, rotate: int = 0, width: int = 640, reconnect_delay: float = 2.0):
        self.source = parse_source(source)
        self.rotate = int(rotate) % 360
        self.width = width
        self.reconnect_delay = reconnect_delay
        self._cap = None
        self._frame = None
        self._frame_time = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.connected = False
        self.frames_read = 0

    # ---- lifecycle ----
    def start(self) -> "CameraStream":
        # First open happens on the calling (main) thread: macOS can only show the
        # camera permission prompt there. Reconnects happen on the reader thread.
        if not self._open():
            print(f"Camera {self.source!r} not available yet, will keep retrying in the background")
            if isinstance(self.source, int) and platform.system() == "Darwin":
                print("macOS: if no camera prompt appeared, allow camera access for your terminal app in "
                      "System Settings > Privacy & Security > Camera, then restart.")
                # background retries cannot show the permission prompt; stop OpenCV from trying
                os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
        else:
            print(f"Camera {self.source!r} connected")
        self._thread = threading.Thread(target=self._loop, name="camera", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._release()

    def _release(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap = None
        self.connected = False

    def _open(self) -> bool:
        self._release()
        cap = cv2.VideoCapture(self.source)
        if isinstance(self.source, int):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            cap.release()
            return False
        self._cap = cap
        self.connected = True
        return True

    # ---- reader thread ----
    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._cap is None:
                if not self._open():
                    self._stop.wait(self.reconnect_delay)
                    continue
                print(f"Camera {self.source!r} connected")
            ok, frame = self._cap.read()
            if not ok or frame is None:
                print("Camera read failed, reconnecting...")
                self._release()
                self._stop.wait(self.reconnect_delay)
                continue
            frame = self._prepare(frame)
            with self._lock:
                self._frame = frame
                self._frame_time = time.monotonic()
                self.frames_read += 1

    def _prepare(self, frame):
        if self.rotate in ROTATIONS:
            frame = cv2.rotate(frame, ROTATIONS[self.rotate])
        h, w = frame.shape[:2]
        if self.width and w != self.width:
            scale = self.width / float(w)
            frame = cv2.resize(frame, (self.width, int(h * scale)), interpolation=cv2.INTER_AREA)
        return frame

    # ---- consumer API ----
    def read(self, max_age: float = 2.0):
        """Return the latest frame (BGR) or None if nothing fresh is available."""
        with self._lock:
            if self._frame is None:
                return None
            if time.monotonic() - self._frame_time > max_age:
                return None
            return self._frame.copy()

    def read_wait(self, timeout: float = 10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self._stop.is_set():
            frame = self.read()
            if frame is not None:
                return frame
            time.sleep(0.02)
        return None
