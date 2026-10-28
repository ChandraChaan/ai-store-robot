"""Robot movement control.

Two backends share one interface:
  SimulatedRobot - no hardware, prints what it would do (default)
  SerialRobot    - talks to an Arduino/ESP32 over USB serial (see arduino/robot_firmware.ino)

Command protocol (one line per command, robot answers "OK" or "ERR ..."):
  F <ms>   forward      B <ms>  backward
  L <ms>   turn left    R <ms>  turn right
  S        stop         GRAB / RELEASE   gripper
  PING     -> "PONG"

Shelf routes are defined in data/products.json under "shelves"; a route is
the list of commands to reach the shelf from the counter. The way back is the
route reversed.
"""
from __future__ import annotations

import threading
import time

REVERSE = {"F": "B", "B": "F", "L": "R", "R": "L"}


class RobotBase:
    def __init__(self, shelves: dict[str, dict] | None = None, on_event=None):
        self.shelves = shelves or {}
        self.on_event = on_event or (lambda text: None)
        self.position = "counter"
        self.busy = False
        self._lock = threading.Lock()

    # ---- low level (implemented by backends) ----
    def send(self, command: str) -> str:
        raise NotImplementedError

    def connected(self) -> bool:
        return True

    # ---- high level ----
    def run_route(self, commands: list[str]) -> None:
        for cmd in commands:
            self.send(cmd)
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit():
                time.sleep(int(parts[1]) / 1000.0)

    def goto_shelf(self, shelf: str) -> bool:
        route = self.shelves.get(shelf, {}).get("route")
        if not route:
            self.on_event(f"robot: no route for shelf {shelf!r}")
            return False
        self.on_event(f"robot: going to shelf {shelf}")
        self.run_route(route)
        self.position = shelf
        return True

    def return_home(self) -> None:
        route = self.shelves.get(self.position, {}).get("route")
        if route:
            back = []
            for cmd in reversed(route):
                parts = cmd.split()
                back.append(" ".join([REVERSE.get(parts[0], parts[0])] + parts[1:]))
            self.run_route(back)
        self.position = "counter"
        self.send("S")
        self.on_event("robot: back at counter")

    def fetch(self, shelf: str, label: str = "", wait: bool = False):
        """Go to the shelf, grab the item, bring it to the counter. Runs in a thread unless wait=True."""

        def job():
            with self._lock:
                self.busy = True
                try:
                    if self.goto_shelf(shelf):
                        self.send("GRAB")
                        self.on_event(f"robot: picked {label or shelf}")
                        self.return_home()
                        self.send("RELEASE")
                        self.on_event(f"robot: delivered {label or shelf}")
                finally:
                    self.busy = False

        if wait:
            job()
            return None
        thread = threading.Thread(target=job, name="robot-fetch", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self.send("S")

    def status(self) -> dict:
        return {"backend": type(self).__name__, "position": self.position, "busy": self.busy, "connected": self.connected()}


class SimulatedRobot(RobotBase):
    def __init__(self, shelves=None, on_event=None, speed: float = 0.25):
        super().__init__(shelves, on_event)
        self.speed = speed  # 1.0 = real time, 0.25 = 4x faster simulation
        self.log: list[str] = []

    def send(self, command: str) -> str:
        self.log.append(command)
        self.on_event(f"robot(sim) > {command}")
        return "OK"

    def run_route(self, commands: list[str]) -> None:
        for cmd in commands:
            self.send(cmd)
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit():
                time.sleep(int(parts[1]) / 1000.0 * self.speed)


class SerialRobot(RobotBase):
    def __init__(self, port: str, baud: int = 115200, shelves=None, on_event=None, timeout: float = 2.0):
        super().__init__(shelves, on_event)
        import serial  # pyserial

        self.port = port
        self._serial = serial.Serial(port, baud, timeout=timeout)
        time.sleep(2.0)  # Arduino resets on connect
        self._serial.reset_input_buffer()
        reply = self.send("PING")
        if "PONG" not in reply:
            self.on_event(f"robot: unexpected reply to PING: {reply!r}")

    def connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def send(self, command: str) -> str:
        self._serial.write((command.strip() + "\n").encode())
        self._serial.flush()
        reply = self._serial.readline().decode(errors="ignore").strip()
        self.on_event(f"robot > {command}  < {reply}")
        return reply

    def close(self) -> None:
        try:
            self.send("S")
            self._serial.close()
        except Exception:
            pass


def create_robot(settings, shelves: dict | None = None, on_event=None) -> RobotBase:
    backend = (getattr(settings, "robot_backend", "sim") or "sim").lower()
    if backend == "serial":
        try:
            return SerialRobot(settings.robot_port, settings.robot_baud, shelves=shelves, on_event=on_event)
        except Exception as exc:
            print(f"Robot: could not open serial port {settings.robot_port}: {exc}. Using simulator.")
    return SimulatedRobot(shelves=shelves, on_event=on_event)
