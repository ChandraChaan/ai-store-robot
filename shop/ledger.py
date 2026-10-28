"""Khata (credit ledger) and sales log in SQLite. Zero infrastructure, one file."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    created_at REAL NOT NULL,
    kind TEXT NOT NULL,               -- sale | credit | payment
    customer_id INTEGER,
    product_key TEXT,
    qty REAL,
    amount REAL NOT NULL,             -- rupees; positive for sale/credit, positive for payment too
    note TEXT,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);
CREATE INDEX IF NOT EXISTS idx_tx_created ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_tx_customer ON transactions(customer_id);
CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY,
    created_at REAL NOT NULL,
    visit_id TEXT,
    customer_id INTEGER,
    total REAL NOT NULL,
    status TEXT NOT NULL,             -- pending | paid | khata | unpaid | cancelled
    method TEXT,                      -- upi | cash | khata
    ref TEXT,
    items TEXT NOT NULL,              -- JSON [[product_key, qty, amount], ...]
    settled_at REAL,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);
"""


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(transactions)")}
            if "bill_id" not in cols:
                self._conn.execute("ALTER TABLE transactions ADD COLUMN bill_id INTEGER")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- customers ----
    def get_or_create_customer(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("customer name is empty")
        with self._lock:
            row = self._conn.execute("SELECT id FROM customers WHERE name = ?", (name,)).fetchone()
            if row:
                return int(row["id"])
            cur = self._conn.execute("INSERT INTO customers(name, created_at) VALUES (?, ?)", (name, time.time()))
            self._conn.commit()
            return int(cur.lastrowid)

    def find_customer(self, name: str) -> int | None:
        with self._lock:
            row = self._conn.execute("SELECT id FROM customers WHERE name = ?", (name.strip(),)).fetchone()
            return int(row["id"]) if row else None

    def customers(self) -> list[str]:
        with self._lock:
            return [r["name"] for r in self._conn.execute("SELECT name FROM customers ORDER BY name")]

    # ---- transactions ----
    def record_sale(self, items: list[tuple[str, float, float]], note: str = "", bill_id: int | None = None) -> float:
        """items: [(product_key, qty, line_total)] paid now (cash/UPI). Returns bill total."""
        total = 0.0
        with self._lock:
            now = time.time()
            for key, qty, amount in items:
                self._conn.execute(
                    "INSERT INTO transactions(created_at, kind, customer_id, product_key, qty, amount, note, bill_id) VALUES (?,?,?,?,?,?,?,?)",
                    (now, "sale", None, key, qty, amount, note, bill_id),
                )
                total += amount
            self._conn.commit()
        return total

    def add_credit(self, customer_name: str, items: list[tuple[str, float, float]], note: str = "", bill_id: int | None = None) -> float:
        """Sell on khata: customer owes the total. Returns new balance."""
        with self._lock:
            customer_id = self.get_or_create_customer(customer_name)
            now = time.time()
            for key, qty, amount in items:
                self._conn.execute(
                    "INSERT INTO transactions(created_at, kind, customer_id, product_key, qty, amount, note, bill_id) VALUES (?,?,?,?,?,?,?,?)",
                    (now, "credit", customer_id, key, qty, amount, note, bill_id),
                )
            self._conn.commit()
            return self.balance(customer_name)

    # ---- bills ----
    def create_bill(self, items: list[tuple[str, float, float]], visit_id: str = "", customer_name: str | None = None) -> int:
        with self._lock:
            customer_id = self.get_or_create_customer(customer_name) if customer_name else None
            total = round(sum(a for _, _, a in items), 2)
            cur = self._conn.execute(
                "INSERT INTO bills(created_at, visit_id, customer_id, total, status, items) VALUES (?,?,?,?,?,?)",
                (time.time(), visit_id, customer_id, total, "pending", json.dumps(items)),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def settle_bill(self, bill_id: int, status: str, method: str | None = None, ref: str = "", customer_name: str | None = None) -> dict:
        """Mark a bill paid/khata/unpaid/cancelled and write the matching ledger lines."""
        bill = self.get_bill(bill_id)
        if bill is None:
            raise ValueError(f"no bill {bill_id}")
        if bill["status"] != "pending":
            return bill
        items = [tuple(x) for x in bill["items"]]
        if status == "khata":
            if not customer_name:
                raise ValueError("khata needs a customer name")
            self.add_credit(customer_name, items, note=f"bill {bill_id}", bill_id=bill_id)
        elif status in ("paid", "unpaid"):
            self.record_sale(items, note=f"bill {bill_id} {status} {method or ''}".strip(), bill_id=bill_id)
        with self._lock:
            customer_id = self.get_or_create_customer(customer_name) if customer_name else bill.get("customer_id")
            self._conn.execute(
                "UPDATE bills SET status=?, method=?, ref=?, settled_at=?, customer_id=? WHERE id=?",
                (status, method, ref, time.time(), customer_id, bill_id),
            )
            self._conn.commit()
        return self.get_bill(bill_id)

    def get_bill(self, bill_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT b.*, c.name AS customer FROM bills b LEFT JOIN customers c ON c.id = b.customer_id WHERE b.id = ?", (bill_id,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["items"] = json.loads(d["items"])
        return d

    def bills(self, limit: int = 30, status: str | None = None) -> list[dict]:
        with self._lock:
            sql = "SELECT b.*, c.name AS customer FROM bills b LEFT JOIN customers c ON c.id = b.customer_id"
            args: list = []
            if status:
                sql += " WHERE b.status = ?"
                args.append(status)
            sql += " ORDER BY b.id DESC LIMIT ?"
            args.append(limit)
            rows = self._conn.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["items"] = json.loads(d["items"])
            out.append(d)
        return out

    def record_payment(self, customer_name: str, amount: float, note: str = "") -> float:
        """Customer pays back part/all of their khata. Returns new balance."""
        if amount <= 0:
            raise ValueError("payment must be positive")
        with self._lock:
            customer_id = self.get_or_create_customer(customer_name)
            self._conn.execute(
                "INSERT INTO transactions(created_at, kind, customer_id, product_key, qty, amount, note) VALUES (?,?,?,?,?,?,?)",
                (time.time(), "payment", customer_id, None, None, amount, note),
            )
            self._conn.commit()
            return self.balance(customer_name)

    # ---- reports ----
    def balance(self, customer_name: str) -> float:
        with self._lock:
            row = self._conn.execute(
                """SELECT COALESCE(SUM(CASE WHEN t.kind='credit' THEN t.amount WHEN t.kind='payment' THEN -t.amount ELSE 0 END), 0) AS bal
                   FROM transactions t JOIN customers c ON c.id = t.customer_id WHERE c.name = ?""",
                (customer_name.strip(),),
            ).fetchone()
            return round(float(row["bal"]), 2)

    def all_balances(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT c.name AS name,
                          COALESCE(SUM(CASE WHEN t.kind='credit' THEN t.amount WHEN t.kind='payment' THEN -t.amount ELSE 0 END), 0) AS balance,
                          MAX(t.created_at) AS last_activity
                   FROM customers c LEFT JOIN transactions t ON t.customer_id = c.id
                   GROUP BY c.id ORDER BY balance DESC, c.name"""
            ).fetchall()
            return [{"name": r["name"], "balance": round(float(r["balance"]), 2), "last_activity": r["last_activity"]} for r in rows]

    def summary(self, since: float | None = None) -> dict:
        if since is None:
            lt = time.localtime()
            since = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        with self._lock:
            rows = self._conn.execute(
                "SELECT kind, COUNT(*) AS n, COALESCE(SUM(amount),0) AS total FROM transactions WHERE created_at >= ? GROUP BY kind",
                (since,),
            ).fetchall()
        out = {"sales": 0.0, "credit": 0.0, "payments": 0.0, "transactions": 0}
        for r in rows:
            out["transactions"] += int(r["n"])
            if r["kind"] == "sale":
                out["sales"] = round(float(r["total"]), 2)
            elif r["kind"] == "credit":
                out["credit"] = round(float(r["total"]), 2)
            elif r["kind"] == "payment":
                out["payments"] = round(float(r["total"]), 2)
        out["total_outstanding"] = round(sum(b["balance"] for b in self.all_balances()), 2)
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN status='unpaid' THEN total ELSE 0 END),0) AS unpaid FROM bills WHERE created_at >= ?",
                (since,),
            ).fetchone()
        out["bills"] = int(row["n"])
        out["unpaid"] = round(float(row["unpaid"]), 2)
        return out

    def recent(self, limit: int = 30) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT t.id, t.created_at, t.kind, c.name AS customer, t.product_key, t.qty, t.amount, t.note
                   FROM transactions t LEFT JOIN customers c ON c.id = t.customer_id
                   ORDER BY t.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
