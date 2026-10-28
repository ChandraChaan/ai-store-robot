"""Dialog policy: turns a ParsedIntent (or counter camera items) into store
actions and a spoken reply.

Keeps the per-customer Session (cart, payment mode, name, what we are waiting
for) and talks to the inventory, ledger and payments.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from brain import nlu
from brain.nlu import Item, ParsedIntent
from brain.replies import fmt_num, t
from shop.inventory import Inventory
from shop.ledger import Ledger


@dataclass
class CartItem(Item):
    source: str = "voice"           # voice | camera


@dataclass
class Session:
    visit_id: str = ""
    started_at: float = field(default_factory=time.time)
    customer_name: str | None = None
    cart: list[CartItem] = field(default_factory=list)
    excluded: set = field(default_factory=set)      # product keys the customer said "no" to
    payment_mode: str | None = None                  # None | cash | credit | upi
    awaiting: str | None = None                      # None | name | payment | pay_amount
    pending_action: str | None = None                # credit | balance | payment (after we get the name)
    pending_amount: float | None = None
    closing: bool = False
    bill_id: int | None = None
    settled_status: str | None = None               # paid | khata | unpaid | cancelled once the bill is closed
    unknown_on_counter: int = 0
    history: list[tuple[str, str]] = field(default_factory=list)
    turns: int = 0

    @property
    def total(self) -> float:
        return round(sum(i.line_total for i in self.cart), 2)

    def camera_qty(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for i in self.cart:
            if i.source == "camera":
                out[i.product.key] = out.get(i.product.key, 0) + i.qty
        return out


@dataclass
class Reply:
    text: str
    end: bool = False


class StoreController:
    def __init__(self, inventory: Inventory, ledger: Ledger, payments=None, settings=None, on_event=None):
        self.inventory = inventory
        self.ledger = ledger
        self.payments = payments
        self.settings = settings
        self.lang = getattr(settings, "language", "te") if settings else "te"
        self.store_name = getattr(settings, "store_name", "store") if settings else "store"
        self.accept_cash = getattr(settings, "accept_cash", True) if settings else True
        self.on_event = on_event or (lambda kind, text: None)
        self.on_record = None            # callback(kind, dict) for Google Sheets
        self.say = None                  # callback(text) for replies triggered outside the dialog (payment arrived)
        self._lock = threading.RLock()
        self.session: Session | None = None
        self.customer_present = False
        self.conversation_active = False
        self.visits_today = 0
        self.last_customer_name: str | None = None
        self.next_visit_id = ""
        self.last_visit_id = ""

    # ------------------------------------------------------------ session lifecycle
    def begin_session(self) -> str:
        with self._lock:
            self.session = Session(visit_id=self.next_visit_id or time.strftime("%Y%m%d-%H%M%S"))
            self.last_visit_id = self.session.visit_id
            self.next_visit_id = ""
            self.customer_present = True
            self.conversation_active = True
            self.visits_today += 1
            greeting = t("greet", self.lang, store=self.store_name)
            self.session.history.append(("robot", greeting))
            return greeting

    def end_session(self, items_taken: bool = True) -> dict | None:
        """Customer left. Returns a summary of how the visit ended (for the screen)."""
        with self._lock:
            s = self.session
            if s is None:
                return None
            result: dict | None = None
            try:
                if s.bill_id is not None:
                    bill = self.ledger.get_bill(s.bill_id)
                    if bill and bill["status"] == "pending":
                        status = "unpaid" if items_taken else "cancelled"
                        self._settle(status, method=None, ref="walked away")
                        result = self._result(status)
                    elif bill:
                        result = self._result(bill["status"])
                elif s.cart:
                    if items_taken:
                        self._create_bill()
                        self._settle("unpaid", method=None, ref="walked away")
                        result = self._result("unpaid")
                    else:
                        result = self._result("cancelled")
                else:
                    result = self._result("none")
            finally:
                if self.payments and self.payments.current:
                    self.payments.cancel("customer left")
                self.session = None
                self.conversation_active = False
                self.customer_present = False
            return result

    def _result(self, status: str) -> dict:
        s = self.session
        return {
            "status": status, "total": s.total if s else 0, "bill_id": s.bill_id if s else None, "customer": s.customer_name if s else None,
            "lines": [{"name": i.product.name, "qty": i.qty, "unit": i.product.unit, "price": i.product.price, "total": i.line_total} for i in s.cart] if s else [],
        }

    @property
    def awaiting_payment(self) -> bool:
        s = self.session
        return bool(s and s.awaiting == "payment")

    def state_text(self) -> str:
        s = self.session
        if not s:
            return "no customer"
        parts = [f"awaiting={s.awaiting or 'nothing'}", f"cart={len(s.cart)} items total={fmt_num(s.total)}"]
        if s.customer_name:
            parts.append(f"customer={s.customer_name}")
        if s.payment_mode:
            parts.append(f"payment={s.payment_mode}")
        return ", ".join(parts)

    # ------------------------------------------------------------ counter camera
    def set_counter_items(self, items) -> str | None:
        """Replace camera-sourced cart items with what the counter camera sees. Returns text to speak or None."""
        with self._lock:
            s = self.session
            if s is None:
                return None
            seen: dict[str, int] = {}
            unknown = 0
            for it in items:
                if it.key is None:
                    unknown += 1
                    continue
                if it.key in s.excluded or self.inventory.get(it.key) is None:
                    continue
                seen[it.key] = seen.get(it.key, 0) + int(it.qty)
            voice_keys = {i.product.key for i in s.cart if i.source == "voice"}
            for k in voice_keys:
                seen.pop(k, None)              # customer corrected this one by voice; camera does not override
            old = s.camera_qty()
            if s.awaiting == "payment":
                # while paying, customers pick items up: only NEW items change the bill
                if not any(seen.get(k, 0) > old.get(k, 0) for k in seen):
                    return None
                self._reopen_bill()
                prefix = t("bill_reopened", self.lang) + " "
            else:
                prefix = ""
            if seen == old and unknown == s.unknown_on_counter:
                return None
            s.unknown_on_counter = unknown
            s.cart = [i for i in s.cart if i.source != "camera"]
            for key, qty in seen.items():
                product = self.inventory.get(key)
                if product.stock <= 0:
                    continue
                s.cart.append(CartItem(product=product, qty=min(qty, product.stock), source="camera"))
            self.on_event("cart", "counter: " + (", ".join(f"{q}x {k}" for k, q in seen.items()) or "empty") + (f" +{unknown} unknown" if unknown else ""))
            if not s.cart and unknown:
                return prefix + t("counter_unknown", self.lang)
            if not s.cart:
                return None
            text = prefix + t("counter_bill", self.lang, items=self._items_text(), total=s.total)
            if unknown:
                text += " " + t("counter_unknown", self.lang)
            return text

    def _items_text(self) -> str:
        return ", ".join(f"{fmt_num(i.qty)} {i.product.name}" for i in self.session.cart)

    # ------------------------------------------------------------ main dispatcher
    def handle(self, parsed: ParsedIntent) -> Reply:
        with self._lock:
            if self.session is None:
                self.begin_session()
            s = self.session
            s.turns += 1
            s.history.append(("customer", parsed.text))
            reply = self._dispatch(parsed)
            s.history.append(("robot", reply.text))
            if reply.end:
                self.conversation_active = False
            return reply

    def _dispatch(self, p: ParsedIntent) -> Reply:
        s = self.session
        lang = self.lang
        if p.customer_name and not s.customer_name:
            s.customer_name = p.customer_name

        # ---- answers to something we asked ----
        if s.awaiting == "name":
            name = p.customer_name or nlu.bare_name(p.text, self.inventory)
            if name:
                s.customer_name = name
                s.awaiting = None
                return self._after_name()
            if p.intent in ("deny", "goodbye", "done"):
                s.awaiting, s.pending_action = None, None
                if s.cart and s.payment_mode == "credit":
                    s.payment_mode = None
                    return self._finish_or_ask_payment()
                return Reply(t("bye", lang), end=True)
            if p.intent not in ("buy", "credit", "ask_price", "ask_stock", "remove"):
                return Reply(t("ask_name_again", lang))
            s.awaiting = None

        if s.awaiting == "payment":
            if p.intent == "credit" or (p.intent == "pay_credit" and not p.items and p.amount is None):
                s.payment_mode = "credit"
                if not s.customer_name:
                    s.awaiting, s.pending_action, s.closing = "name", "credit", True
                    return Reply(t("ask_name", lang))
                return self._settle_reply("khata")
            if self.accept_cash and nlu.mentions_cash(p.text) and not nlu.mentions_upi(p.text):
                return self._settle_reply("paid", method="cash")
            if p.intent in ("buy", "remove"):
                self._reopen_bill()
                # fall through to normal handling below
            elif p.intent in ("affirm", "done", "goodbye", "thanks", "unknown", "chitchat", "greeting", "deny") or nlu.mentions_upi(p.text):
                return Reply(t("pay_wait_confirm", lang) if nlu.mentions_upi(p.text) else t("pay_reminder", lang))

        if s.awaiting == "pay_amount":
            if p.amount is not None:
                s.awaiting = None
                return self._record_payment(p.amount)
            if p.intent in ("deny", "goodbye", "done"):
                s.awaiting = None
                return Reply(t("ok_anything_else", lang))
            return Reply(t("ask_amount", lang))

        # ---- normal intents ----
        intent = p.intent
        if intent == "greeting":
            return Reply(t("greet_again", lang))
        if intent == "my_name":
            return Reply(t("ok_anything_else", lang) if s.customer_name else t("ask_name_again", lang))
        if intent == "list_products":
            names = [pr.name for pr in self.inventory.in_stock()][:10]
            return Reply(t("list", lang, items=", ".join(names)))
        if intent == "ask_price":
            return Reply(" ".join(self._price_line(i) for i in p.items) or t("unknown", lang))
        if intent == "ask_stock":
            return Reply(" ".join(self._stock_line(i) for i in p.items) or t("unknown", lang))
        if intent == "remove":
            return Reply(" ".join(self._remove(i) for i in p.items) or t("unknown", lang))
        if intent in ("buy", "credit"):
            if intent == "credit":
                s.payment_mode = "credit"
            lines = [self._add_or_set(i) for i in p.items]
            lines += [t("not_found", lang, name=n) for n in p.unknown_items]
            if p.items and s.cart:
                lines.append(t("cart_total", lang, total=s.total))
            if intent == "credit":
                if not s.customer_name:
                    s.awaiting, s.pending_action = "name", "credit"
                    lines.append(t("ask_name", lang))
                elif not p.items:
                    lines.append(t("credit_ok", lang, name=s.customer_name))
            return Reply(" ".join(lines) or t("unknown", lang))
        if intent == "check_balance":
            if not s.customer_name:
                s.awaiting, s.pending_action = "name", "balance"
                return Reply(t("ask_name", lang))
            return Reply(self._balance_line())
        if intent == "pay_credit":
            s.pending_amount = p.amount
            if not s.customer_name:
                s.awaiting, s.pending_action = "name", "payment"
                return Reply(t("ask_name", lang))
            if p.amount is None:
                s.awaiting = "pay_amount"
                return Reply(f"{self._balance_line()} {t('ask_amount', lang)}")
            return self._record_payment(p.amount)
        if intent == "thanks":
            return self._finish_or_ask_payment() if s.cart else Reply(t("thanks", lang))
        if intent in ("done", "goodbye", "deny"):
            if s.cart:
                return self._finish_or_ask_payment()
            if s.unknown_on_counter:
                return Reply(t("counter_unknown", lang))
            return Reply(t("bye", lang), end=True)
        if intent == "affirm":
            return Reply(t("greet_again", lang))
        if p.llm_reply:
            return Reply(p.llm_reply.get(lang) or p.llm_reply["en"])
        return Reply(t("unknown", lang))

    # ------------------------------------------------------------ cart actions
    def _price_line(self, item: Item) -> str:
        pr = item.product
        return t("price", self.lang, name=pr.name, unit=pr.unit, price=pr.price)

    def _stock_line(self, item: Item) -> str:
        pr = item.product
        if pr.stock <= 0:
            return t("out_of_stock", self.lang, name=pr.name)
        return t("in_stock", self.lang, name=pr.name, stock=pr.stock, unit=pr.unit)

    def _find_cart(self, key: str) -> CartItem | None:
        return next((i for i in self.session.cart if i.product.key == key), None)

    def _add_or_set(self, item: Item) -> str:
        """Voice 'buy': if the camera already saw this product, the spoken quantity corrects it; else add."""
        pr = item.product
        s = self.session
        s.excluded.discard(pr.key)
        if pr.stock <= 0:
            return t("out_of_stock", self.lang, name=pr.name)
        existing = self._find_cart(pr.key)
        if existing is not None:
            if item.qty > pr.stock:
                return t("not_enough", self.lang, name=pr.name, stock=pr.stock, unit=pr.unit)
            existing.qty = item.qty
            existing.source = "voice"
            self.on_event("cart", f"set {pr.key} = {fmt_num(item.qty)}")
            return t("qty_set", self.lang, name=pr.name, qty=item.qty, unit=pr.unit)
        if item.qty > pr.stock:
            return t("not_enough", self.lang, name=pr.name, stock=pr.stock, unit=pr.unit)
        s.cart.append(CartItem(product=pr, qty=item.qty, source="voice"))
        self.on_event("cart", f"+{fmt_num(item.qty)} {pr.key} = {fmt_num(item.line_total)}")
        return t("added", self.lang, qty=item.qty, unit=pr.unit, name=pr.name, line=item.line_total)

    def _remove(self, item: Item) -> str:
        pr = item.product
        s = self.session
        s.excluded.add(pr.key)
        before = len(s.cart)
        s.cart = [i for i in s.cart if i.product.key != pr.key]
        if len(s.cart) != before:
            self.on_event("cart", f"-{pr.key}")
        return t("removed", self.lang, name=pr.name)

    def _after_name(self) -> Reply:
        s = self.session
        action, s.pending_action = s.pending_action, None
        if action == "balance":
            return Reply(self._balance_line())
        if action == "payment":
            if s.pending_amount is None:
                s.awaiting = "pay_amount"
                return Reply(f"{self._balance_line()} {t('ask_amount', self.lang)}")
            return self._record_payment(s.pending_amount)
        if action == "credit":
            if s.cart and s.payment_mode == "credit" and s.closing:
                return self._settle_reply("khata")
            return Reply(t("credit_ok", self.lang, name=s.customer_name))
        return Reply(t("ok_anything_else", self.lang))

    def _balance_line(self) -> str:
        s = self.session
        bal = self.ledger.balance(s.customer_name)
        return t("balance" if bal > 0 else "balance_zero", self.lang, name=s.customer_name, balance=bal)

    def _record_payment(self, amount: float) -> Reply:
        s = self.session
        s.pending_amount = None
        if amount <= 0:
            return Reply(t("ask_amount", self.lang))
        balance = self.ledger.record_payment(s.customer_name, amount, note="voice")
        self.on_event("khata", f"{s.customer_name} paid {fmt_num(amount)}, balance {fmt_num(balance)}")
        self._emit("khata", {"customer": s.customer_name, "kind": "payment", "amount": amount, "balance": balance, "visit": s.visit_id})
        return Reply(t("payment_ok", self.lang, name=s.customer_name, amount=amount, balance=balance))

    # ------------------------------------------------------------ bill & payment
    def _finish_or_ask_payment(self) -> Reply:
        s = self.session
        if s.payment_mode == "credit":
            if not s.customer_name:
                s.awaiting, s.pending_action, s.closing = "name", "credit", True
                return Reply(t("ask_name", self.lang))
            return self._settle_reply("khata")
        self._create_bill()
        upi = bool(self.payments and self.payments.upi_enabled)
        if self.payments is not None:
            self.payments.request(s.bill_id, s.total, note=f"{self.store_name} bill {s.bill_id}")
        s.awaiting = "payment"
        if not upi and self.accept_cash:
            # no UPI configured: the old cash-or-khata question
            return Reply(t("ask_payment", self.lang, total=s.total))
        return Reply(t("pay_upi_or_khata", self.lang, total=s.total))

    def _create_bill(self) -> int:
        s = self.session
        if s.bill_id is None:
            items = [(i.product.key, i.qty, i.line_total) for i in s.cart]
            s.bill_id = self.ledger.create_bill(items, visit_id=s.visit_id, customer_name=s.customer_name)
            self.on_event("bill", f"bill #{s.bill_id} created: {fmt_num(s.total)}")
        return s.bill_id

    def _reopen_bill(self) -> None:
        s = self.session
        if s.bill_id is not None:
            bill = self.ledger.get_bill(s.bill_id)
            if bill and bill["status"] == "pending":
                self.ledger.settle_bill(s.bill_id, "cancelled", ref="reopened")
            s.bill_id = None
        if self.payments and self.payments.current:
            self.payments.cancel("bill changed")
        s.awaiting = None

    def _settle(self, status: str, method: str | None, ref: str = "") -> dict:
        """Write the bill result to the ledger and reduce stock. status: paid | khata | unpaid | cancelled."""
        s = self.session
        bill_id = self._create_bill()
        bill = self.ledger.settle_bill(bill_id, status, method=method, ref=ref, customer_name=s.customer_name)
        s.settled_status = status
        if status in ("paid", "khata", "unpaid"):
            for i in s.cart:
                self.inventory.reduce_stock(i.product.key, i.qty)
            low = self.inventory.low_stock()
            if low:
                self.on_event("stock", "low stock: " + ", ".join(f"{p.key}={fmt_num(p.stock)}" for p in low))
        self._emit("bills", {
            "bill": bill_id, "visit": s.visit_id, "customer": s.customer_name or "", "total": s.total, "status": status,
            "method": method or "", "ref": ref, "items": "; ".join(f"{fmt_num(i.qty)} x {i.product.key} = {fmt_num(i.line_total)}" for i in s.cart),
        })
        if status == "khata":
            balance = self.ledger.balance(s.customer_name)
            self.on_event("khata", f"{s.customer_name} credit +{fmt_num(s.total)}, balance {fmt_num(balance)}")
            self._emit("khata", {"customer": s.customer_name, "kind": "credit", "amount": s.total, "balance": balance, "visit": s.visit_id, "bill": bill_id})
        elif status == "paid":
            self.on_event("sale", f"bill #{bill_id} paid {fmt_num(s.total)} by {method}")
            self._emit("payments", {"bill": bill_id, "amount": s.total, "method": method or "", "ref": ref, "visit": s.visit_id})
        elif status == "unpaid":
            self.on_event("alert", f"bill #{bill_id} UNPAID {fmt_num(s.total)}")
        if s.customer_name:
            self.last_customer_name = s.customer_name
        return bill

    def _settle_reply(self, status: str, method: str | None = None, ref: str = "") -> Reply:
        s = self.session
        if self.payments and self.payments.current and status != "paid":
            self.payments.cancel(status)
        elif self.payments and self.payments.current and status == "paid":
            # cash: settle through the payments object so dashboards agree, but do the ledger work here
            self.payments.on_settled, saved = None, self.payments.on_settled
            self.payments.mark_paid(method=method or "cash", ref=ref)
            self.payments.on_settled = saved
        self._settle(status, method=method or ("khata" if status == "khata" else None), ref=ref)
        total = s.total
        s.awaiting = None
        self.conversation_active = False
        if status == "khata":
            balance = self.ledger.balance(s.customer_name)
            return Reply(t("bill_credit", self.lang, name=s.customer_name, total=total, balance=balance), end=True)
        if method == "cash":
            return Reply(t("cash_received", self.lang, amount=total), end=True)
        return Reply(t("paid_thanks", self.lang, amount=total), end=True)

    def settle_bill(self, bill_id: int, status: str = "paid", method: str = "upi", ref: str = "") -> str | None:
        """Called when a payment arrives from outside the dialog (dashboard tap, phone webhook)."""
        with self._lock:
            s = self.session
            if s is None or s.bill_id != bill_id:
                bill = self.ledger.get_bill(bill_id)
                if bill and bill["status"] == "pending":
                    self.ledger.settle_bill(bill_id, status, method=method, ref=ref)
                    return t("paid_thanks", self.lang, amount=bill["total"])
                return None
            self._settle(status, method=method, ref=ref)
            total = s.total
            s.awaiting = None
            self.conversation_active = False
            s.history.append(("robot", f"[payment {method}]"))
            return t("paid_thanks", self.lang, amount=total)

    def _emit(self, kind: str, data: dict) -> None:
        if self.on_record:
            try:
                self.on_record(kind, data)
            except Exception as exc:
                self.on_event("error", f"record failed: {exc}")

    # ------------------------------------------------------------ dashboard
    def snapshot(self) -> dict:
        s = self.session
        return {
            "customer_present": self.customer_present,
            "conversation_active": self.conversation_active,
            "customer_name": s.customer_name if s else None,
            "visit_id": s.visit_id if s else None,
            "cart": [{"key": i.product.key, "name": i.product.name, "qty": i.qty, "total": i.line_total, "source": i.source} for i in s.cart] if s else [],
            "cart_total": s.total if s else 0,
            "awaiting": s.awaiting if s else None,
            "bill_id": s.bill_id if s else None,
            "visits_today": self.visits_today,
        }
