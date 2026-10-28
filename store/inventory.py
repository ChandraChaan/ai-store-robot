"""Product catalogue + stock, stored in data/products.json (human editable)."""
from __future__ import annotations

import difflib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Product:
    key: str
    name: str
    price: float
    stock: float
    unit: str = "piece"
    shelf: str = ""
    low_stock: float = 3
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "key": self.key, "name": self.name, "unit": self.unit, "price": self.price,
            "stock": self.stock, "shelf": self.shelf, "low_stock": self.low_stock, "aliases": self.aliases,
        }


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\sఀ-౿ऀ-ॿ']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class Inventory:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.products: dict[str, Product] = {}
        self.shelves: dict[str, dict] = {}
        self.load()

    # ---- persistence ----
    def load(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        with self._lock:
            self.shelves = data.get("shelves", {})
            self.products = {}
            for item in data.get("products", []):
                product = Product(
                    key=item["key"], name=item["name"], price=float(item["price"]), stock=float(item.get("stock", 0)),
                    unit=item.get("unit", "piece"), shelf=item.get("shelf", ""), low_stock=float(item.get("low_stock", 3)),
                    aliases=[normalize(a) for a in item.get("aliases", [])] or [normalize(item["name"])],
                )
                self.products[product.key] = product
            self._alias_index = sorted(
                ((alias, key) for key, p in self.products.items() for alias in set(p.aliases + [normalize(key.replace("_", " "))])),
                key=lambda pair: -len(pair[0]),
            )

    def save(self) -> None:
        with self._lock:
            data = {"shelves": self.shelves, "products": [p.to_dict() for p in self.products.values()]}
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)

    # ---- queries ----
    def get(self, key: str) -> Product | None:
        return self.products.get(key)

    def all(self) -> list[Product]:
        return list(self.products.values())

    def in_stock(self) -> list[Product]:
        return [p for p in self.products.values() if p.stock > 0]

    def low_stock(self) -> list[Product]:
        return [p for p in self.products.values() if p.stock <= p.low_stock]

    def find_all(self, text: str) -> list[tuple[Product, int, int]]:
        """Find every product mentioned in text. Returns (product, start, end) sorted by position.

        Longest aliases are matched first so "thums up" wins over "up"; a product
        is reported once even if several of its aliases appear.
        """
        norm = normalize(text)
        taken = [False] * len(norm)
        found: dict[str, tuple[int, int]] = {}
        for alias, key in self._alias_index:
            if not alias or key in found:
                continue
            for match in re.finditer(re.escape(alias), norm):
                start, end = match.span()
                # word boundary for latin aliases, substring ok for Telugu/Hindi (suffixes attach)
                if alias[0].isascii():
                    if start > 0 and norm[start - 1].isalnum():
                        continue
                    if end < len(norm) and norm[end] == "s":  # allow simple plural: cokes, biscuits
                        end += 1
                    if end < len(norm) and norm[end].isalnum():
                        continue
                if any(taken[start:end]):
                    continue
                for i in range(start, end):
                    taken[i] = True
                found[key] = (start, end)
                break
        return sorted(((self.products[k], s, e) for k, (s, e) in found.items()), key=lambda t: t[1])

    def find(self, text: str) -> Product | None:
        """Best single match for a product name (exact alias first, then fuzzy)."""
        hits = self.find_all(text)
        if hits:
            return hits[0][0]
        norm = normalize(text)
        if not norm:
            return None
        aliases = [a for a, _ in self._alias_index]
        close = difflib.get_close_matches(norm, aliases, n=1, cutoff=0.75)
        if close:
            for alias, key in self._alias_index:
                if alias == close[0]:
                    return self.products[key]
        return None

    # ---- stock changes ----
    def reduce_stock(self, key: str, qty: float) -> None:
        with self._lock:
            product = self.products[key]
            product.stock = max(0.0, product.stock - qty)
            self.save()

    def add_stock(self, key: str, qty: float) -> Product:
        with self._lock:
            product = self.products[key]
            product.stock = max(0.0, product.stock + qty)
            self.save()
            return product

    def set_price(self, key: str, price: float) -> Product:
        with self._lock:
            product = self.products[key]
            product.price = float(price)
            self.save()
            return product
