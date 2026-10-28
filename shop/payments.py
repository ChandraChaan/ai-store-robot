"""Payments: UPI deep-link QR (no gateway, no fee), cash, khata.

A PaymentRequest is created when a bill is ready. It is settled by:
  - the owner tapping "paid" on the dashboard,
  - a POST to /api/payment_received from a notification-forwarder app on the
    owner's Android phone (MacroDroid / Tasker, free) when the bank SMS or
    UPI app notification arrives,
  - the customer choosing khata (handled by the store controller),
  - or cash, when the owner is present.
"""
from __future__ import annotations

import threading
import time
import urllib.parse
from dataclasses import dataclass, field


@dataclass
class PaymentRequest:
    bill_id: int
    amount: float
    note: str = ""
    upi_link: str = ""
    qr_svg: str = ""
    created_at: float = field(default_factory=time.time)
    status: str = "pending"        # pending | paid | cancelled
    method: str | None = None      # upi | cash | khata
    ref: str = ""
    paid_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "bill_id": self.bill_id, "amount": self.amount, "note": self.note, "upi_link": self.upi_link,
            "status": self.status, "method": self.method, "ref": self.ref, "created_at": self.created_at,
            "paid_at": self.paid_at, "age_seconds": int(time.time() - self.created_at),
        }


def upi_link(upi_id: str, payee: str, amount: float, note: str = "", currency: str = "INR") -> str:
    params = {"pa": upi_id, "pn": payee[:50], "am": f"{amount:.2f}", "cu": currency}
    if note:
        params["tn"] = note[:50]
    return "upi://pay?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def qr_svg(data: str, scale: int = 8) -> str:
    try:
        import segno
    except ImportError:
        return ""
    import io

    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=scale, border=2, xmldecl=False, svgns=True)
    return buf.getvalue().decode("utf-8")


class Payments:
    def __init__(self, settings, on_event=None, on_settled=None):
        self.settings = settings
        self.on_event = on_event or (lambda kind, text: None)
        self.on_settled = on_settled          # callback(PaymentRequest)
        self._lock = threading.Lock()
        self.current: PaymentRequest | None = None
        self.history: list[PaymentRequest] = []

    @property
    def upi_enabled(self) -> bool:
        return bool(self.settings.upi_id)

    def request(self, bill_id: int, amount: float, note: str = "") -> PaymentRequest:
        with self._lock:
            req = PaymentRequest(bill_id=bill_id, amount=round(amount, 2), note=note)
            if self.upi_enabled and amount > 0:
                req.upi_link = upi_link(self.settings.upi_id, self.settings.upi_payee_name or self.settings.store_name, amount, note, self.settings.currency)
                req.qr_svg = qr_svg(req.upi_link)
            self.current = req
            self.on_event("payment", f"bill #{bill_id} waiting for {amount:g}")
            return req

    def mark_paid(self, method: str = "upi", ref: str = "", bill_id: int | None = None, amount: float | None = None) -> PaymentRequest | None:
        with self._lock:
            req = self.current
            if req is None or req.status != "pending":
                return None
            if bill_id is not None and bill_id != req.bill_id:
                return None
            if amount is not None and abs(amount - req.amount) > 0.5:
                self.on_event("payment", f"amount mismatch: got {amount:g}, expected {req.amount:g} (bill #{req.bill_id})")
                # still accept: owner can correct in the ledger
            req.status, req.method, req.ref, req.paid_at = "paid", method, ref, time.time()
            self.history.append(req)
            self.current = None
        self.on_event("payment", f"bill #{req.bill_id} paid by {method} {ref}".strip())
        if self.on_settled:
            self.on_settled(req)
        return req

    def cancel(self, reason: str = "") -> PaymentRequest | None:
        with self._lock:
            req = self.current
            if req is None:
                return None
            req.status = "cancelled"
            self.history.append(req)
            self.current = None
        self.on_event("payment", f"bill #{req.bill_id} cancelled {reason}".strip())
        return req

    def is_overdue(self) -> bool:
        req = self.current
        return bool(req and time.time() - req.created_at > self.settings.payment_timeout_seconds)

    def snapshot(self) -> dict | None:
        return self.current.to_dict() if self.current else None
