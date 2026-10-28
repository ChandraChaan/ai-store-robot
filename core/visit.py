"""The visit: ARRIVE -> SHOP -> BILL -> PAY -> LEAVE.

Glues together the camera events, the counter recogniser, the dialog
controller, payments, the customer screen and Google Sheets. One instance per
shop; one Session (inside the StoreController) per customer visit.
"""
from __future__ import annotations

import time
import uuid

from brain.replies import t
from core.events import events


class VisitManager:
    def __init__(self, settings, store, engine, payments, speaker, counter=None, stabilizer=None, sheets=None, inventory=None):
        self.settings = settings
        self.store = store
        self.engine = engine
        self.payments = payments
        self.speaker = speaker
        self.counter = counter
        self.stabilizer = stabilizer
        self.sheets = sheets
        self.inventory = inventory
        self.lang = settings.language
        self._last_counter_time = 0.0
        self._last_result: dict | None = None     # what to show on the screen after a visit ends
        self._last_result_until = 0.0
        self.counter_items = []                   # latest recognised items (for overlay/dashboard)
        self.counter_person_near = False
        self.visit_started_at: float | None = None

        store.say = lambda text: self.speaker.say(text, block=False)
        store.on_record = self._record
        payments.on_settled = self.on_payment_settled
        if inventory is not None:
            inventory.on_change = lambda key, delta, stock: self._record("stock", {"product": key, "delta": delta, "stock": stock})

    # ------------------------------------------------------------------ camera events
    def on_enter(self, frame=None) -> None:
        if self.store.session is not None and self.store.conversation_active:
            return
        visit_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.store.next_visit_id = visit_id
        self.visit_started_at = time.time()
        if self.stabilizer:
            self.stabilizer.reset()
        events.add("visit", f"{visit_id} started")
        self._record("visits", {"visit": visit_id, "event": "arrive"})
        self.engine.start()

    def on_leave(self) -> None:
        if self.store.session is None:
            self.engine.stop(farewell=False)
            return
        items_on_counter = any(it.known for it in self.counter_items)
        result = self.store.end_session(items_taken=not items_on_counter)
        self.engine.stop(farewell=False)
        if self.stabilizer:
            self.stabilizer.reset()
        if result:
            self._show_result(result)
            if result.get("status") == "unpaid":
                self.speaker.say(t("unpaid_warning", self.lang, total=result.get("total", 0)), block=False)
                events.add("alert", f"UNPAID exit: bill #{result.get('bill_id')} {result.get('total')}")
            elif result.get("status") in ("paid", "khata"):
                pass
            else:
                self.speaker.say(t("bye", self.lang), block=False)
        duration = int(time.time() - (self.visit_started_at or time.time()))
        self._record("visits", {"visit": self.store.last_visit_id, "event": "leave", "seconds": duration, "status": (result or {}).get("status", "")})
        events.add("visit", f"ended ({(result or {}).get('status', 'no bill')}, {duration}s)")

    def on_counter_frame(self, frame, person_near: bool) -> None:
        """Called with the counter camera frame; rate limited to settings.counter_fps."""
        if self.counter is None or not self.settings.counter_enabled:
            return
        now = time.monotonic()
        if now - self._last_counter_time < 1.0 / max(0.5, self.settings.counter_fps):
            return
        self._last_counter_time = now
        self.counter_person_near = person_near
        busy = person_near or self.store.session is not None
        if self.counter.maybe_refresh_reference(frame, busy=busy):
            events.add("counter", "empty-counter reference updated")
            return
        items = self.counter.recognize(frame)
        self.counter_items = items
        if self.stabilizer is None:
            return
        stable = self.stabilizer.update(items)
        if stable is None or self.store.session is None:
            return
        self.apply_counter_items(stable)

    def apply_counter_items(self, items) -> None:
        reply = self.store.set_counter_items(items)
        if reply:
            events.add("counter", reply)
            self.speaker.say(reply, block=False)

    def reset_counter_reference(self, frame) -> None:
        if self.counter is not None:
            self.counter.set_reference(frame)
            if self.stabilizer:
                self.stabilizer.reset()
            events.add("counter", "empty-counter reference set")

    # ------------------------------------------------------------------ payments
    def on_payment_settled(self, req) -> None:
        text = self.store.settle_bill(req.bill_id, status="paid", method=req.method or "upi", ref=req.ref)
        if text:
            self.speaker.say(text, block=False)
            events.add("robot", text)
        if self.store.session is None:
            self._show_result({"status": "paid", "total": req.amount, "lines": [], "bill_id": req.bill_id})

    def simulate_payment(self, method: str = "upi", ref: str = "manual") -> bool:
        return self.payments.mark_paid(method=method, ref=ref) is not None

    # ------------------------------------------------------------------ records
    def _record(self, kind: str, data: dict) -> None:
        if self.sheets is not None and self.sheets.enabled:
            self.sheets.send(kind, data)

    def _show_result(self, result: dict) -> None:
        self._last_result = result
        self._last_result_until = time.time() + 10.0

    # ------------------------------------------------------------------ screen
    def screen_state(self) -> dict:
        s = self.store.session
        base = {"store_name": self.settings.store_name, "upi_id": self.settings.upi_id, "footer": self.settings.store_info,
                "lines": [], "total": 0, "qr_svg": "", "customer_name": None, "state": "idle",
                "message_te": "స్వాగతం", "message_en": "Welcome"}
        if s is None:
            if self._last_result and time.time() < self._last_result_until:
                r = self._last_result
                base.update({"lines": r.get("lines", []), "total": r.get("total", 0)})
                status = r.get("status")
                if status == "paid":
                    base.update(state="paid", message_te="చెల్లింపు అందింది. ధన్యవాదాలు!", message_en="Payment received. Thank you!")
                elif status == "khata":
                    base.update(state="khata", message_te=f"{r.get('customer') or ''} గారి ఖాతాలో రాశాము. ధన్యవాదాలు!", message_en=f"Added to {r.get('customer') or ''}'s khata. Thank you!")
                elif status == "unpaid":
                    base.update(state="unpaid", message_te="చెల్లింపు జరగలేదు!", message_en="Payment not received!")
                else:
                    base.update(state="thanks", message_te="ధన్యవాదాలు, మళ్ళీ రండి!", message_en="Thank you, come again!")
            return base
        lines = [{"name": i.product.name, "qty": i.qty, "unit": i.product.unit, "price": i.product.price, "total": i.line_total} for i in s.cart]
        base.update({"lines": lines, "total": s.total, "customer_name": s.customer_name})
        name = f"{s.customer_name} గారు, " if s.customer_name else ""
        if s.settled_status == "paid":
            base.update(state="paid", message_te="చెల్లింపు అందింది. ధన్యవాదాలు!", message_en="Payment received. Thank you!")
        elif s.settled_status == "khata":
            base.update(state="khata", message_te=f"{s.customer_name or ''} గారి ఖాతాలో రాశాము. ధన్యవాదాలు!", message_en=f"Added to {s.customer_name or ''}'s khata. Thank you!")
        elif s.awaiting == "payment" and self.payments.current:
            base.update(state="pay", qr_svg=self.payments.current.qr_svg,
                        message_te=f"{name}QR స్కాన్ చేసి చెల్లించండి", message_en="Scan to pay with any UPI app")
            if not self.payments.current.qr_svg:
                base.update(message_te=f"{name}చెల్లింపు చేయండి", message_en="Please pay at the counter")
        elif s.awaiting == "name":
            base.update(state="bill", message_te="మీ పేరు చెప్పండి", message_en="Please tell me your name")
        elif s.cart:
            base.update(state="bill", message_te=f"{name}మీ బిల్లు", message_en="Your bill so far")
        else:
            base.update(state="shopping", message_te=f"{name}నమస్కారం! వస్తువులు కౌంటర్ మీద పెట్టండి",
                        message_en="Welcome! Place your items on the counter")
        return base

    def snapshot(self) -> dict:
        return {
            "counter_items": [{"key": i.key, "name": i.name, "qty": i.qty, "score": round(i.score, 2), "box": i.box} for i in self.counter_items],
            "counter_reference": bool(self.counter and self.counter.has_reference),
            "payment": self.payments.snapshot(),
            "sheets": self.sheets.status() if self.sheets else {"enabled": False},
            "screen": self.screen_state()["state"],
        }
