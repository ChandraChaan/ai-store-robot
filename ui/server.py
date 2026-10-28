"""Owner dashboard + customer screen, served from the shop computer (stdlib only).

  http://<mac-ip>:8008          owner dashboard (phone)
  http://<mac-ip>:8008/screen   customer screen (tablet at the counter)
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).parent


class DashboardState:
    def __init__(self, settings, inventory, ledger, store, visit=None, library=None, counter=None, cameras=None):
        self.settings = settings
        self.inventory = inventory
        self.ledger = ledger
        self.store = store
        self.visit = visit
        self.library = library
        self.counter = counter
        self.cameras = cameras or {}          # role -> CameraStream
        self._jpeg: dict[str, bytes] = {}
        self._jpeg_time: dict[str, float] = {}
        self.latest: dict = {}                # role -> last raw frame (for learning products)
        self._lock = threading.Lock()
        self.presence_text = ""
        self.started = time.time()

    def set_frame(self, role: str, frame, raw=None) -> None:
        """Encode at most ~4 frames/sec per camera to keep CPU for detection."""
        self.latest[role] = raw if raw is not None else frame
        now = time.monotonic()
        if now - self._jpeg_time.get(role, 0.0) < 0.25:
            return
        import cv2

        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if ok:
            with self._lock:
                self._jpeg[role] = buf.tobytes()
                self._jpeg_time[role] = now

    def frame(self, role: str) -> bytes | None:
        with self._lock:
            return self._jpeg.get(role)

    def counter_role(self) -> str:
        return self.settings.counter_camera_role()

    def json_state(self) -> dict:
        from core.events import events

        cams = {}
        for role, cam in self.cameras.items():
            cams[role] = {"source": str(cam.source), "connected": cam.connected, "frames": cam.frames_read}
        return {
            "store_name": self.settings.store_name,
            "uptime_seconds": int(time.time() - self.started),
            "presence": self.presence_text,
            "session": self.store.snapshot(),
            "visit": self.visit.snapshot() if self.visit else None,
            "today": self.ledger.summary(),
            "balances": self.ledger.all_balances(),
            "bills": self.ledger.bills(12),
            "recent": self.ledger.recent(12),
            "inventory": [p.to_dict() for p in self.inventory.all()],
            "low_stock": [p.key for p in self.inventory.low_stock()],
            "learned": self.library.counts() if self.library else {},
            "cameras": cams,
            "counter_role": self.counter_role(),
            "events": events.recent(40),
            "upi_id": self.settings.upi_id,
            "accept_cash": self.settings.accept_cash,
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

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            url = urlparse(self.path)
            path, query = url.path, parse_qs(url.query)
            if path == "/":
                self._send(200, (HERE / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/screen":
                self._send(200, (HERE / "customer.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/state":
                self._json(200, state.json_state())
            elif path == "/api/screen":
                self._json(200, state.visit.screen_state() if state.visit else {"state": "idle", "store_name": state.settings.store_name})
            elif path == "/snapshot.jpg":
                role = (query.get("cam") or ["door"])[0]
                frame = state.frame(role)
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
                return self._json(400, {"error": "bad json"})
            try:
                return self._handle_post(self.path, data)
            except (KeyError, ValueError, TypeError) as exc:
                return self._json(400, {"error": str(exc)})

        def _handle_post(self, path: str, data: dict):
            inv, ledger, visit = state.inventory, state.ledger, state.visit
            if path == "/api/stock":
                return self._json(200, {"ok": True, "stock": inv.add_stock(str(data["key"]), float(data["delta"])).stock})
            if path == "/api/price":
                return self._json(200, {"ok": True, "price": inv.set_price(str(data["key"]), float(data["price"])).price})
            if path == "/api/payment":
                return self._json(200, {"ok": True, "balance": ledger.record_payment(str(data["name"]), float(data["amount"]), note="dashboard")})
            if path == "/api/credit":
                product = inv.get(str(data["key"]))
                if product is None:
                    return self._json(404, {"error": "no such product"})
                qty = float(data.get("qty", 1))
                inv.reduce_stock(product.key, qty)
                return self._json(200, {"ok": True, "balance": ledger.add_credit(str(data["name"]), [(product.key, qty, product.price * qty)], note="dashboard")})
            if path == "/api/pay":                       # owner taps "paid"
                if visit is None:
                    return self._json(409, {"error": "no visit manager"})
                ok = visit.simulate_payment(method=str(data.get("method", "upi")), ref=str(data.get("ref", "dashboard")))
                return self._json(200 if ok else 409, {"ok": ok})
            if path == "/api/payment_received":          # phone notification forwarder
                token = state.settings.payment_webhook_token
                if not token or data.get("token") != token:
                    return self._json(403, {"error": "bad token"})
                amount = float(data["amount"]) if data.get("amount") not in (None, "") else None
                req = visit.payments.mark_paid(method="upi", ref=str(data.get("ref", "webhook")), amount=amount) if visit else None
                return self._json(200 if req else 409, {"ok": bool(req)})
            if path == "/api/leave":                     # owner: customer has left
                if visit:
                    visit.on_leave()
                return self._json(200, {"ok": True})
            if path == "/api/counter/reference":
                frame = state.latest.get(state.counter_role())
                if frame is None or visit is None:
                    return self._json(409, {"error": "no counter frame yet"})
                visit.reset_counter_reference(frame)
                return self._json(200, {"ok": True})
            if path == "/api/learn":
                frame = state.latest.get(state.counter_role())
                if frame is None or state.counter is None:
                    return self._json(409, {"error": "no counter frame yet"})
                key = str(data["key"])
                if inv.get(key) is None:
                    return self._json(404, {"error": f"unknown product key {key}"})
                n, msg = state.counter.learn_from_frame(frame, key)
                return self._json(200 if n else 409, {"ok": bool(n), "added": n, "message": msg, "learned": state.library.counts()})
            if path == "/api/forget":
                if state.library is None:
                    return self._json(409, {"error": "no library"})
                return self._json(200, {"ok": True, "removed": state.library.forget(str(data["key"]))})
            return self._json(404, {"error": "not found"})

    return Handler


def start_dashboard(state: DashboardState, port: int = 8008) -> ThreadingHTTPServer | None:
    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(state))
    except OSError as exc:
        print(f"Dashboard: could not bind port {port}: {exc}")
        return None
    threading.Thread(target=server.serve_forever, name="dashboard", daemon=True).start()
    print(f"Dashboard: http://localhost:{port}   customer screen: http://localhost:{port}/screen   (use this Mac's IP from phones)")
    return server
