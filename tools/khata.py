#!/usr/bin/env python3
"""Owner command line for the khata and stock (works while the robot is running).

  python tools/khata.py balances
  python tools/khata.py today
  python tools/khata.py pay "Ramu" 100
  python tools/khata.py credit "Ramu" rice 2
  python tools/khata.py stock                 # list stock
  python tools/khata.py stock coke +12        # adjust
  python tools/khata.py price coke 45
  python tools/khata.py recent
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shop.inventory import Inventory  # noqa: E402
from shop.ledger import Ledger  # noqa: E402
from core.config import load_settings  # noqa: E402


def main(argv=None) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Khata / stock tool")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("balances")
    sub.add_parser("today")
    sub.add_parser("recent")
    p = sub.add_parser("pay"); p.add_argument("name"); p.add_argument("amount", type=float)
    p = sub.add_parser("credit"); p.add_argument("name"); p.add_argument("product"); p.add_argument("qty", type=float, nargs="?", default=1)
    p = sub.add_parser("stock"); p.add_argument("product", nargs="?"); p.add_argument("delta", nargs="?")
    p = sub.add_parser("price"); p.add_argument("product"); p.add_argument("price", type=float)
    args = parser.parse_args(argv)

    inventory = Inventory(settings.products_file)
    ledger = Ledger(settings.database_file)

    if args.cmd == "balances":
        rows = ledger.all_balances()
        if not rows:
            print("No khata entries yet.")
        for r in rows:
            print(f"{r['name']:<20} ₹{r['balance']:>8.2f}")
        print(f"{'TOTAL':<20} ₹{sum(r['balance'] for r in rows):>8.2f}")
    elif args.cmd == "today":
        s = ledger.summary()
        print(f"Cash sales     ₹{s['sales']:.2f}\nOn khata       ₹{s['credit']:.2f}\nPayments       ₹{s['payments']:.2f}\n"
              f"Transactions   {s['transactions']}\nOutstanding    ₹{s['total_outstanding']:.2f}")
    elif args.cmd == "recent":
        for r in ledger.recent(30):
            when = time.strftime("%d %b %H:%M", time.localtime(r["created_at"]))
            who = r["customer"] or "-"
            item = f"{r['qty']:g}x {r['product_key']}" if r["product_key"] else ""
            print(f"{when}  {r['kind']:<8} {who:<15} {item:<18} ₹{r['amount']:.2f}")
    elif args.cmd == "pay":
        print(f"New balance for {args.name}: ₹{ledger.record_payment(args.name, args.amount, note='cli'):.2f}")
    elif args.cmd == "credit":
        product = inventory.find(args.product)
        if product is None:
            print(f"Unknown product {args.product!r}"); return 1
        inventory.reduce_stock(product.key, args.qty)
        bal = ledger.add_credit(args.name, [(product.key, args.qty, product.price * args.qty)], note="cli")
        print(f"{args.qty:g} {product.name} on khata for {args.name}. Balance ₹{bal:.2f}")
    elif args.cmd == "stock":
        if args.product is None:
            for p in inventory.all():
                flag = "  LOW" if p.stock <= p.low_stock else ""
                print(f"{p.key:<10} {p.name:<18} ₹{p.price:>6.2f}  {p.stock:>5g} {p.unit}{flag}")
        else:
            product = inventory.find(args.product) or inventory.get(args.product)
            if product is None:
                print(f"Unknown product {args.product!r}"); return 1
            if args.delta is None:
                print(f"{product.name}: {product.stock:g} {product.unit}")
            else:
                delta = float(args.delta)
                print(f"{product.name}: {inventory.add_stock(product.key, delta).stock:g} {product.unit}")
    elif args.cmd == "price":
        product = inventory.find(args.product) or inventory.get(args.product)
        if product is None:
            print(f"Unknown product {args.product!r}"); return 1
        print(f"{product.name}: ₹{inventory.set_price(product.key, args.price).price:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
