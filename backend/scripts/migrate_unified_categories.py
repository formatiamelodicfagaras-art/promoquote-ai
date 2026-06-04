"""Migrate existing products to populate unified_category / unified_subcategory.

Idempotent: safe to re-run. Uses sync sqlite3 for the bulk UPDATE (faster than
SQLAlchemy async for migrations), then re-indexes everything into Meilisearch.

Run:
    python backend/scripts/migrate_unified_categories.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from collections import Counter

# Make `app` importable when run from backend/ or backend/scripts/
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.services.unified_taxonomy import map_to_unified  # noqa: E402

DB_PATH = os.environ.get("DB_PATH", os.path.join(BACKEND, "promoquote.db"))

BATCH_SIZE = 1000


def ensure_columns(conn: sqlite3.Connection) -> None:
    for col in ("unified_category", "unified_subcategory"):
        try:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} VARCHAR(100)")
            print(f"  + added column {col}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"  = column {col} already exists")
            else:
                raise
    # Index for fast filtering
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_products_unified_category "
            "ON products(unified_category)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_products_unified_subcategory "
            "ON products(unified_subcategory)"
        )
    except sqlite3.OperationalError as e:
        print(f"  ! index warning: {e}")
    conn.commit()


def migrate(conn: sqlite3.Connection) -> tuple[int, int, Counter]:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM products")
    total = cur.fetchone()[0]
    print(f"Total products: {total}")

    cur.execute(
        "SELECT id, COALESCE(category,''), COALESCE(category_group,''), "
        "COALESCE(subcategory,'') FROM products"
    )

    processed = 0
    matched = 0
    cat_dist: Counter = Counter()
    batch: list[tuple[str, str, str]] = []

    while True:
        rows = cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        for pid, cat, grp, sub in rows:
            ucat, usub = map_to_unified(cat, grp, sub)
            batch.append((ucat, usub, pid))
            cat_dist[ucat] += 1
            processed += 1
            if ucat != "Diverse":
                matched += 1

        conn.executemany(
            "UPDATE products SET unified_category=?, unified_subcategory=? WHERE id=?",
            batch,
        )
        conn.commit()
        batch.clear()
        print(f"  ... {processed}/{total}")

    return processed, matched, cat_dist


def reindex_meili() -> None:
    """Re-index all products via the existing async meili pipeline."""
    print("\nRe-indexing all products in Meilisearch...")
    import asyncio

    from app.database import async_session
    from app.services.search_service import is_available, setup_index, reindex_all

    if not is_available():
        print("  ! Meilisearch is not available — skipping reindex")
        return

    setup_index()

    async def _run():
        async with async_session() as db:
            await reindex_all(db)

    asyncio.run(_run())
    print("  done.")


def main() -> None:
    print(f"DB: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print(f"ERROR: database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    try:
        print("Ensuring columns + indexes...")
        ensure_columns(conn)

        print("Mapping products to unified taxonomy...")
        processed, matched, cat_dist = migrate(conn)
    finally:
        conn.close()

    pct = (matched / processed * 100) if processed else 0
    print()
    print("=" * 60)
    print(f"Processed: {processed}")
    print(f"Unified (non-Diverse): {matched} ({pct:.1f}%)")
    print()
    print("Distribution per top category:")
    for cat, cnt in cat_dist.most_common():
        share = cnt / processed * 100 if processed else 0
        print(f"  {cat:<32} {cnt:>8}  ({share:5.1f}%)")
    print("=" * 60)

    reindex_meili()


if __name__ == "__main__":
    main()
