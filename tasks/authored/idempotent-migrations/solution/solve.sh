#!/bin/bash
set -euo pipefail

cat > /app/shop/migrations/003_backfill_order_totals.py <<'PY'
"""Cache each order's total in cents. Re-appliable: the column is added only if missing and every
total is recomputed from the items as they are now."""


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def up(conn):
    if "total_cents" not in _columns(conn, "orders"):
        conn.execute("ALTER TABLE orders ADD COLUMN total_cents INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        """
        UPDATE orders
           SET total_cents = COALESCE(
                   (SELECT SUM(quantity * unit_price_cents)
                      FROM order_items
                     WHERE order_items.order_id = orders.id), 0)
        """
    )
PY

cd /app/shop
python migrate.py
