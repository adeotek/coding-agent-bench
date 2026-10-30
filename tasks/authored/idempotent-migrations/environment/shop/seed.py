#!/usr/bin/env python3
"""Seed the shop with orders and items. Idempotent: does nothing if orders already exist."""
import pathlib
import sqlite3

DB = pathlib.Path(__file__).resolve().parent / "shop.db"

ORDERS = [
    (1, "ada", "2026-01-04", "shipped"),
    (2, "linus", "2026-01-05", "new"),
    # deliberately an order with no items at all
    (3, "grace", "2026-01-06", "new"),
    (4, "alan", "2026-01-07", "shipped"),
]

ITEMS = [
    (1, 1, "widget", 2, 1250),
    (2, 1, "gizmo", 1, 400),
    (3, 2, "widget", 3, 1250),
    (4, 4, "bulk-bolt", 250, 3),
]


def main():
    conn = sqlite3.connect(DB)
    count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    if count:
        print(f"seed: {count} orders already present")
        return
    conn.executemany("INSERT INTO orders (id, customer, created_at, status) VALUES (?,?,?,?)", ORDERS)
    conn.executemany(
        "INSERT INTO order_items (id, order_id, sku, quantity, unit_price_cents) VALUES (?,?,?,?,?)",
        ITEMS,
    )
    conn.commit()
    print(f"seed: inserted {len(ORDERS)} orders, {len(ITEMS)} items")


if __name__ == "__main__":
    main()
