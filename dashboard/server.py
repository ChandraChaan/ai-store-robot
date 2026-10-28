"""Tiny owner dashboard served from the robot itself (stdlib only, zero cost).

Open http://<this-mac-ip>:8008 on your phone (same Wi-Fi) to see the live
camera, who is at the counter, the conversation, today's sales, khata
balances and stock. Stock and payments can be adjusted from the page.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HTML = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")


class DashboardState:
    def __init__(self, settings, inventory, ledger, store, robot=None):
        self.settings = settings
        self.inventory = inventory
        self.ledger = ledger
        self.store = store
        self.robot = robot
        self._jpeg: bytes | None = None
        self._jpeg_time = 0.0
        self._lock = threading.Lock()
        self.presence_text = ""
        self.started = time.time()

    def set_frame(self, frame) -> None:
        """Encode at most ~4 frames/sec to keep CPU for YOLO."""
        now = time.monotonic()
        if now - self._jpeg_time < 0.25:
            return
        import cv2

        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if ok:
            with self._lock:
                self._jpeg = buf.tobytes()
                self._jpeg_time = now

    def frame(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    def json_state(self) -> dict:
        from utils.events import events

        return {
            "store_name": self.settings.store_name,
            "uptime_seconds": int(time.time() - self.started),
            "presence": self.presence_text,
            "session": self.store.snapshot(),
            "today": self.ledger.summary(),
            "balances": self.ledger.all_balances(),
            "recent": self.ledger.recent(15),
            "inventory": [p.to_dict() for p in self.inventory.all()],
            "low_stock": [p.key for p in self.inventory.low_stock()],
            "events": events.recent(40),
            "robot": self.robot.status() if self.robot else None,
            "has_camera": self._jpeg is not None,
        }


def make_handler(state: DashboardState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/state":
                self._send(200, json.dumps(state.json_state(), ensure_ascii=False).encode("utf-8"))
            elif path == "/snapshot.jpg":
                frame = state.frame()
                if frame is None:
                    self._send(404, b"no frame", "text/plain")
                else:
                    self._send(200, frame, "image/jpeg")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._send(400, b'{"error":"bad json"}')
            try:
                if self.path == "/api/stock":
                    product = state.inventory.add_stock(str(data["key"]), float(data["delta"]))
                    return self._send(200, json.dumps({"ok": True, "stock": product.stock}).encode())
                if self.path == "/api/price":
                    product = state.inventory.set_price(str(data["key"]), float(data["price"]))
                    return self._send(200, json.dumps({"ok": True, "price": product.price}).encode())
                if self.path == "/api/payment":
                    balance = state.ledger.record_payment(str(data["name"]), float(data["amount"]), note="dashboard")
                    return self._send(200, json.dumps({"ok": True, "balance": balance}).encode())
                if self.path == "/api/credit":
                    product = state.inventory.get(str(data["key"]))
                    if product is None:
                        return self._send(404, b'{"error":"no such product"}')
                    qty = float(data.get("qty", 1))
                    state.inventory.reduce_stock(product.key, qty)
                    balance = state.ledger.add_credit(str(data["name"]), [(product.key, qty, product.price * qty)], note="dashboard")
                    return self._send(200, json.dumps({"ok": True, "balance": balance}).encode())
            except (KeyError, ValueError, TypeError) as exc:
                return self._send(400, json.dumps({"error": str(exc)}).encode())
            self._send(404, b'{"error":"not found"}')

    return Handler


def start_dashboard(state: DashboardState, port: int = 8008) -> ThreadingHTTPServer | None:
    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(state))
    except OSError as exc:
        print(f"Dashboard: could not bind port {port}: {exc}")
        return None
    threading.Thread(target=server.serve_forever, name="dashboard", daemon=True).start()
    print(f"Dashboard: http://localhost:{port}  (open from your phone with this Mac's IP)")
    return server
