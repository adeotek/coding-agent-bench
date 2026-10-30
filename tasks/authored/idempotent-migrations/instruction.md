`/app/shop` is a small SQLite shop. `migrate.py` applies every file in `migrations/` in name order,
records each applied version in `schema_migrations`, and skips versions already recorded. The database
`shop.db` is seeded with orders and order items.

Add exactly one migration, `/app/shop/migrations/003_backfill_order_totals.py`, that caches each
order's total:

- `orders` gains `total_cents INTEGER NOT NULL DEFAULT 0`;
- existing rows are backfilled from `order_items` as `quantity * unit_price_cents`;
- an order with no items has a total of `0`, never NULL;
- the migration is **re-appliable**: if its bookkeeping row is removed and the runner runs again (which
  is what a retry after a failed deploy looks like), it must not fail and must recompute every order's
  total from the items as they are *now* — not only fill in rows that were zero.

Run `python migrate.py` from `/app/shop` and make sure it exits 0. Do not modify `migrate.py`, the other
migrations, `seed.py` or the database by hand: the only file you add is the migration.
