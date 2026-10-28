"""Dialog policy: turns a ParsedIntent into store actions and a spoken reply.

Keeps the per-customer session (cart, payment mode, name, what we are waiting
for) and talks to the inventory, ledger and robot.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from ai import nlu
from ai.nlu import Item, ParsedIntent
from ai.replies import fmt_num, t
from store.inventory import Inventory
from store.ledger import Ledger


@dataclass
class Session:
    started_at: float = field(default_factory=time.time)
    customer_name: str | None = None
    cart: list[Item] = field(default_factory=list)
    payment_mode: str | None = None     # None | cash | credit
    awaiting: str | None = None         # None | name | payment_choice | pay_amount
    pending_action: str | None = None   # what to do once we get the name: credit | balance | payment
    pending_amount: float | None = None
    closing: bool = False               # customer said 'done' but we still need their name
    history: list[tuple[str, str]] = field(default_factory=list)
    turns: int = 0

    @property
    def total(self) -> float:
        return round(sum(i.line_total for i in self.cart), 2)


@dataclass
class Reply:
    text: str
    end: bool = False


class StoreController:
    def __init__(self, inventory: Inventory, ledger: Ledger, robot=None, settings=None, on_event=None):
        self.inventory = inventory
        self.ledger = ledger
        self.robot = robot
        self.settings = settings
        self.lang = getattr(settings, "language", "te") if settings else "te"
        self.store_name = getattr(settings, "store_name", "store") if settings else "store"
        self.on_event = on_event or (lambda kind, text: None)
        self._lock = threading.RLock()
        self.session: Session | None = None
        self.customer_present = False
        self.conversation_active = False
        self.visits_today = 0
        self.last_customer_name: str | None = None

    # ------------------------------------------------------------ session lifecycle
    def begin_session(self) -> str:
        with self._lock:
            self.session = Session()
            self.customer_present = True
            self.conversation_active = True
            self.visits_today += 1
            greeting = t("greet", self.lang, store=self.store_name)
            self.session.history.append(("robot", greeting))
            return greeting

    def end_session(self) -> None:
        with self._lock:
            if self.session and self.session.cart:
                # customer walked away without finishing: cash sale is assumed so stock stays correct
                self._checkout(force_cash=True)
            self.session = None
            self.conversation_active = False
            self.customer_present = False

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
                s.awaiting = None
                s.pending_action = None
                s.payment_mode = "cash" if s.cart else None
                return self._checkout() if s.cart else Reply(t("bye", lang), end=True)
            if p.intent not in ("buy", "credit", "ask_price", "ask_stock"):
                return Reply(t("ask_name_again", lang))
            s.awaiting = None  # they moved on; keep going

        if s.awaiting == "payment_choice":
            s.awaiting = None
            if p.intent == "credit" or (p.intent == "pay_credit" and not p.items):
                s.payment_mode = "credit"
                if not s.customer_name:
                    s.awaiting, s.pending_action, s.closing = "name", "credit", True
                    return Reply(t("ask_name", lang))
                return self._checkout()
            if p.intent in ("affirm", "deny", "done", "goodbye", "thanks", "unknown", "chitchat") or self._mentions_cash(p.text):
                s.payment_mode = "cash"
                return self._checkout()

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
            if s.customer_name:
                return Reply(t("ok_anything_else", lang))
            return Reply(t("ask_name_again", lang))
        if intent == "list_products":
            names = [pr.name for pr in self.inventory.in_stock()][:10]
            return Reply(t("list", lang, items=", ".join(names)))
        if intent == "ask_price":
            return Reply(" ".join(self._price_line(i) for i in p.items) or t("unknown", lang))
        if intent == "ask_stock":
            return Reply(" ".join(self._stock_line(i) for i in p.items) or t("unknown", lang))
        if intent in ("buy", "credit"):
            if intent == "credit":
                s.payment_mode = "credit"
            before = len(s.cart)
            lines = [self._add_to_cart(i) for i in p.items]
            lines += [t("not_found", lang, name=n) for n in p.unknown_items]
            if len(s.cart) > before:
                lines.append(t("cart_total", lang, total=s.total))
            if intent == "credit":
                if not s.customer_name:
                    s.awaiting, s.pending_action = "name", "credit"
                    lines.append(t("ask_name", lang))
                elif not p.items:
                    lines.append(t("credit_ok", lang, name=s.customer_name))
            if not lines:
                lines.append(t("unknown", lang))
            return Reply(" ".join(lines))
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
            if s.cart:
                return self._finish_or_ask_payment()
            return Reply(t("thanks", lang))
        if intent in ("done", "goodbye", "deny"):
            if s.cart:
                return self._finish_or_ask_payment()
            return Reply(t("bye", lang), end=True)
        if intent == "affirm":
            return Reply(t("greet_again", lang))
        # chitchat / unknown
        if p.llm_reply:
            return Reply(p.llm_reply.get(lang) or p.llm_reply["en"])
        return Reply(t("unknown", lang))

    # ------------------------------------------------------------ actions
    def _mentions_cash(self, text: str) -> bool:
        norm = nlu.normalize(text)
        return any(nlu._contains(norm, w) for w in nlu.CASH_WORDS)

    def _price_line(self, item: Item) -> str:
        pr = item.product
        return t("price", self.lang, name=pr.name, unit=pr.unit, price=pr.price)

    def _stock_line(self, item: Item) -> str:
        pr = item.product
        if pr.stock <= 0:
            return t("out_of_stock", self.lang, name=pr.name)
        return t("in_stock", self.lang, name=pr.name, stock=pr.stock, unit=pr.unit)

    def _add_to_cart(self, item: Item) -> str:
        pr = item.product
        s = self.session
        already = sum(i.qty for i in s.cart if i.product.key == pr.key)
        if pr.stock <= 0:
            return t("out_of_stock", self.lang, name=pr.name)
        if already + item.qty > pr.stock:
            return t("not_enough", self.lang, name=pr.name, stock=pr.stock - already, unit=pr.unit)
        s.cart.append(item)
        self.on_event("cart", f"+{fmt_num(item.qty)} {pr.key} = {fmt_num(item.line_total)}")
        if self.robot is not None and pr.shelf:
            self.robot.fetch(pr.shelf, pr.name)
        return t("added", self.lang, qty=item.qty, unit=pr.unit, name=pr.name, line=item.line_total)

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
                return self._checkout()
            return Reply(t("credit_ok", self.lang, name=s.customer_name))
        return Reply(t("ok_anything_else", self.lang))

    def _balance_line(self) -> str:
        s = self.session
        bal = self.ledger.balance(s.customer_name)
        key = "balance" if bal > 0 else "balance_zero"
        return t(key, self.lang, name=s.customer_name, balance=bal)

    def _record_payment(self, amount: float) -> Reply:
        s = self.session
        s.pending_amount = None
        if amount <= 0:
            return Reply(t("ask_amount", self.lang))
        balance = self.ledger.record_payment(s.customer_name, amount, note="voice")
        self.on_event("khata", f"{s.customer_name} paid {fmt_num(amount)}, balance {fmt_num(balance)}")
        return Reply(t("payment_ok", self.lang, name=s.customer_name, amount=amount, balance=balance))

    def _finish_or_ask_payment(self) -> Reply:
        s = self.session
        if s.payment_mode is None:
            s.awaiting = "payment_choice"
            return Reply(t("ask_payment", self.lang, total=s.total))
        if s.payment_mode == "credit" and not s.customer_name:
            s.awaiting, s.pending_action = "name", "credit"
            s.closing = True
            return Reply(t("ask_name", self.lang))
        return self._checkout()

    def _checkout(self, force_cash: bool = False) -> Reply:
        s = self.session
        s.closing = False
        items = [(i.product.key, i.qty, i.line_total) for i in s.cart]
        total = s.total
        for i in s.cart:
            self.inventory.reduce_stock(i.product.key, i.qty)
        if s.payment_mode == "credit" and s.customer_name and not force_cash:
            balance = self.ledger.add_credit(s.customer_name, items, note="voice")
            self.on_event("khata", f"{s.customer_name} credit +{fmt_num(total)}, balance {fmt_num(balance)}")
            reply = t("bill_credit", self.lang, name=s.customer_name, total=total, balance=balance)
        else:
            self.ledger.record_sale(items, note="voice" if not force_cash else "auto-close")
            self.on_event("sale", f"cash sale {fmt_num(total)} ({len(items)} items)")
            reply = t("bill_cash", self.lang, total=total)
        if s.customer_name:
            self.last_customer_name = s.customer_name
        s.cart.clear()
        s.payment_mode = None
        low = self.inventory.low_stock()
        if low:
            self.on_event("stock", "low stock: " + ", ".join(f"{p.key}={fmt_num(p.stock)}" for p in low))
        return Reply(reply, end=True)

    # ------------------------------------------------------------ dashboard
    def snapshot(self) -> dict:
        s = self.session
        return {
            "customer_present": self.customer_present,
            "conversation_active": self.conversation_active,
            "customer_name": s.customer_name if s else None,
            "cart": [{"key": i.product.key, "name": i.product.name, "qty": i.qty, "total": i.line_total} for i in s.cart] if s else [],
            "cart_total": s.total if s else 0,
            "awaiting": s.awaiting if s else None,
            "visits_today": self.visits_today,
        }
