"""
Scrape UTT (TShirt Europe) product pages to extract prices and stock,
then update the local SQLite database and reindex Meilisearch.

Usage:
    cd backend
    python scripts/utt_fetch_prices.py
"""

import asyncio
import json
import re
import sys
import time
import pathlib

import httpx
from sqlalchemy import select

sys.stdout.reconfigure(encoding="utf-8")

# ── paths ──────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parent.parent          # backend/
sys.path.insert(0, str(ROOT))

from app.database import async_session                          # noqa: E402
from app.models import Product                                  # noqa: E402
from app.services.search_service import index_products          # noqa: E402

BASE_URL = "https://tshirteurope.com/ro/catalog/product/"
CONCURRENT = 10          # max concurrent requests
DELAY_BETWEEN = 0.15     # seconds between batches


# ── extract data from HTML ─────────────────────────────────────────────
def extract_price_stock(html: str) -> tuple[float, int]:
    """
    Parse the embedded JavaScript in a UTT product page.
    Returns (base_price, total_stock).

    Each variant object in the JS has: outlet, promo, BaseSellingPrice, Inventory.
    We use the per-variant outlet/promo flags to skip promo prices but still count all stock.
    """
    standard_prices: list[float] = []
    all_prices: list[float] = []
    total_stock = 0

    # Match each variant object inline — they contain all needed fields
    # Pattern: "outlet":0,"promo":0,"BaseSellingPrice":"4.89","Inventory":"2008"
    for m in re.finditer(
        r'"outlet"\s*:\s*(\d+)\s*,\s*"promo"\s*:\s*(\d+)\s*,\s*"BaseSellingPrice"\s*:\s*"([^"]+)"\s*,\s*"Inventory"\s*:\s*"([^"]+)"',
        html,
    ):
        is_outlet = m.group(1) != "0" or m.group(2) != "0"
        try:
            price = float(m.group(3))
            inv = int(m.group(4))
        except (ValueError, TypeError):
            continue

        total_stock += inv
        if price > 0:
            all_prices.append(price)
            if not is_outlet:
                standard_prices.append(price)

    # Fallback if no outlet/promo fields found (different page format)
    if not all_prices and total_stock == 0:
        for p in re.findall(r'"BaseSellingPrice"\s*:\s*"([^"]+)"', html):
            try:
                v = float(p)
                if v > 0:
                    all_prices.append(v)
            except ValueError:
                continue
        for inv in re.findall(r'"Inventory"\s*:\s*"([^"]+)"', html):
            try:
                total_stock += int(inv)
            except ValueError:
                continue

    # Prefer standard prices; fall back to all (including outlet)
    prices = standard_prices if standard_prices else all_prices
    if prices:
        from collections import Counter
        price_counts = Counter(round(p, 4) for p in prices)
        base_price = price_counts.most_common(1)[0][0]
    else:
        base_price = 0.0

    return base_price, total_stock


async def fetch_product_page(client: httpx.AsyncClient, style: str) -> tuple[str, float, int]:
    """Fetch a single product page and extract price/stock."""
    url = f"{BASE_URL}{style.lower()}"
    try:
        resp = await client.get(url, follow_redirects=True, timeout=15)
        if resp.status_code != 200:
            return style, 0.0, 0
        price, stock = extract_price_stock(resp.text)
        return style, price, stock
    except Exception as e:
        print(f"  Error fetching {style}: {e}")
        return style, 0.0, 0


async def main():
    print("=== UTT Price & Stock Scraper ===\n")

    # 1. Get all UTT product styles from DB
    async with async_session() as db:
        result = await db.execute(
            select(Product.id, Product.supplier_code, Product.external_id)
            .where(Product.external_id.like("UTT-%"))
        )
        products = result.all()

    print(f"Found {len(products)} UTT products in database.\n")
    if not products:
        return

    # 2. Scrape pages in batches
    updated = 0
    failed = 0
    price_stock_map: dict[str, tuple[float, int]] = {}

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        http2=False,
    ) as client:
        batch_size = CONCURRENT
        styles = [(p.id, p.supplier_code, p.external_id) for p in products]

        for i in range(0, len(styles), batch_size):
            batch = styles[i : i + batch_size]
            tasks = [fetch_product_page(client, s[1]) for s in batch]
            results = await asyncio.gather(*tasks)

            for style, price, stock in results:
                if price > 0 or stock > 0:
                    price_stock_map[style] = (price, stock)
                    updated += 1
                else:
                    failed += 1

            done = i + len(batch)
            pct = done * 100 // len(styles)
            print(f"  Scraped {done}/{len(styles)} ({pct}%) — {updated} with data, {failed} without")

            if i + batch_size < len(styles):
                await asyncio.sleep(DELAY_BETWEEN)

    print(f"\nScraping complete: {updated} products with price/stock data.\n")

    if not price_stock_map:
        print("No price/stock data found. Exiting.")
        return

    # 3. Update database
    print("Updating database...")
    search_docs = []

    async with async_session() as db:
        for pid, supplier_code, external_id in products:
            data = price_stock_map.get(supplier_code)
            if not data:
                continue

            price, stock = data
            result = await db.execute(select(Product).where(Product.id == pid))
            product = result.scalar_one_or_none()
            if not product:
                continue

            product.base_price = price
            product.stock = stock
            search_docs.append(product.to_search_dict())

        await db.commit()

    print(f"Updated {len(search_docs)} products in database.\n")

    # 4. Reindex Meilisearch
    if search_docs:
        print("Reindexing Meilisearch...")
        batch_size = 500
        for i in range(0, len(search_docs), batch_size):
            batch = search_docs[i : i + batch_size]
            index_products(batch)
            print(f"  Indexed {min(i + batch_size, len(search_docs))}/{len(search_docs)}")
        print("Reindex complete.")

    print(f"\nDone! {len(search_docs)} UTT products now have prices and stock.")


if __name__ == "__main__":
    asyncio.run(main())
