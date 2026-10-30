#!/usr/bin/env python3
"""Apply migrations/*.py in name order, recording each version in schema_migrations."""
import importlib.util
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent
DB = ROOT / "shop.db"
MIGRATIONS = ROOT / "migrations"


def connect():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def applied(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY,"
        " applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    conn = connect()
    done = applied(conn)
    pending = [p for p in sorted(MIGRATIONS.glob("*.py")) if p.stem not in done]
    for path in pending:
        module = load(path)
        try:
            module.up(conn)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (path.stem,))
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - a migration may fail for any reason
            conn.rollback()
            print(f"migration {path.stem} failed: {exc}", file=sys.stderr)
            return 1
        print(f"applied {path.stem}")
    if not pending:
        print("nothing to apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
