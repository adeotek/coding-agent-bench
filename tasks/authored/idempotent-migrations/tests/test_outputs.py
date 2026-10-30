"""Verifier for the idempotent-migration task.

Every check is local: it drives the repository's own runner against its own database.
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

APP = Path("/app/shop")
DB = APP / "shop.db"
VERSION = "003_backfill_order_totals"


def migrate():
    return subprocess.run([sys.executable, "migrate.py"], cwd=APP, capture_output=True, text=True)


def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def snapshot(conn):
    return [(row["id"], row["total_cents"]) for row in conn.execute("SELECT id, total_cents FROM orders ORDER BY id")]


def expected_totals(conn):
    return {
        row["order_id"]: row["total"]
        for row in conn.execute(
            "SELECT order_id, SUM(quantity * unit_price_cents) AS total FROM order_items GROUP BY order_id"
        )
    }


def test_migration_file_exists():
    assert (APP / "migrations" / f"{VERSION}.py").exists(), f"migrations/{VERSION}.py is missing"


def test_migration_applies_and_adds_column():
    result = migrate()
    assert result.returncode == 0, f"migrate.py failed:\n{result.stdout}\n{result.stderr}"
    conn = connect()
    versions = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    assert VERSION in versions, f"{VERSION} was not recorded: {sorted(versions)}"
    columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
    assert "total_cents" in columns, f"orders has no total_cents column: {sorted(columns)}"


def test_totals_match_items_and_empty_orders_are_zero():
    conn = connect()
    totals = expected_totals(conn)
    rows = list(conn.execute("SELECT id, total_cents FROM orders ORDER BY id"))
    assert rows, "no orders in the database"
    for row in rows:
        want = totals.get(row["id"], 0)
        assert row["total_cents"] is not None, f"order {row['id']} has a NULL total"
        assert row["total_cents"] == want, f"order {row['id']} total is {row['total_cents']}, expected {want}"
    empty = [row["id"] for row in rows if row["id"] not in totals]
    assert empty, "the seed has an order with no items; a total of 0 for it was never exercised"


def test_second_run_is_a_noop():
    conn = connect()
    before = snapshot(conn)
    conn.close()
    result = migrate()
    assert result.returncode == 0, f"second run failed:\n{result.stdout}\n{result.stderr}"
    conn = connect()
    assert snapshot(conn) == before, "a second run changed the cached totals"
    recorded = conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = ?", (VERSION,)).fetchone()[0]
    assert recorded == 1, f"{VERSION} recorded {recorded} times"


def test_reapply_recomputes_every_total():
    """A retry after a failed deploy: the bookkeeping row is gone and new data arrived."""
    conn = connect()
    conn.execute("DELETE FROM schema_migrations WHERE version = ?", (VERSION,))
    conn.execute("INSERT OR REPLACE INTO orders (id, customer, created_at, status) VALUES (99, 'late', '2026-02-01', 'new')")
    conn.execute(
        "INSERT INTO order_items (order_id, sku, quantity, unit_price_cents) VALUES (99, 'post-deploy', 3, 250)"
    )
    # an existing order whose items changed after the first backfill
    conn.execute("INSERT INTO order_items (order_id, sku, quantity, unit_price_cents) VALUES (2, 'extra', 1, 500)")
    conn.commit()
    conn.close()

    result = migrate()
    assert result.returncode == 0, (
        "re-applying the migration failed (did it try to add the column twice?):\n"
        f"{result.stdout}\n{result.stderr}"
    )

    conn = connect()
    totals = expected_totals(conn)
    assert conn.execute("SELECT total_cents FROM orders WHERE id = 99").fetchone()[0] == 750
    for row in conn.execute("SELECT id, total_cents FROM orders"):
        want = totals.get(row["id"], 0)
        assert row["total_cents"] == want, f"order {row['id']} is stale: {row['total_cents']} != {want}"
