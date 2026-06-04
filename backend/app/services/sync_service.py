"""
Product synchronization from supplier XML feeds.
Downloads XML feeds, parses them, and upserts products into the database.
Supports progress callbacks for real-time SSE streaming.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models.product import Product
from app.models.integration import Integration
from app.services.xml_parser import (
    parse_products_xml,
    parse_prices_xml,
    parse_inventory_xml,
    parse_labeling_xml,
)
from app.services.search_service import index_products as meili_index
from app.services.category_groups import get_group

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 120.0
BATCH_SIZE = 500

# Type alias for progress callback
ProgressCallback = Callable[[str, int, int, str], None]


def _noop_progress(stage: str, current: int, total: int, message: str = ""):
    """No-op progress callback."""
    pass


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
async def _fetch_xml(url: str, api_key: str = "") -> bytes:
    """Fetch XML content from a URL with retries (respects 429 Retry-After)."""
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 429:
            wait_secs = int(response.headers.get("Retry-After", "60"))
            logger.warning(f"Rate limited (429), waiting {wait_secs}s before retry")
            await asyncio.sleep(wait_secs)
            response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.content


async def sync_integration(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback | None = None,
) -> int:
    """
    Dispatch sync based on integration type.
    Returns number of products synced.
    """
    cb = progress or _noop_progress
    itype = getattr(integration, "integration_type", None) or integration.name

    if itype in ("anda_present", "anda"):
        return await sync_anda_products(integration, db, cb)
    elif itype in ("easygifts", "macma"):
        return await sync_easygifts(integration, db, cb)
    elif itype in ("roly", "stamina"):
        return await sync_roly(integration, db, cb)
    elif itype == "malfini":
        return await sync_malfini(integration, db, cb)
    elif itype == "midocean":
        return await sync_midocean_products(integration, db, cb)
    elif itype == "makito":
        return await sync_makito(integration, db, cb)
    elif itype == "utt":
        return await sync_utt(integration, db, cb)
    elif itype == "stricker":
        return await sync_stricker(integration, db, cb)
    elif itype == "promolog":
        return await sync_promolog(integration, db, cb)
    elif itype == "sipec":
        return await sync_sipec(integration, db, cb)
    elif itype == "bluecollection":
        return await sync_bluecollection(integration, db, cb)
    elif itype == "xdconnects":
        return await sync_xdconnects(integration, db, cb)
    elif itype == "givingeurope":
        return await sync_givingeurope(integration, db, cb)
    elif itype == "colorissimo":
        return await sync_colorissimo(integration, db, cb)
    elif itype == "idgroup":
        return await sync_idgroup(integration, db, cb)
    elif itype == "inspirion":
        return await sync_inspirion(integration, db, cb)
    elif itype == "valento":
        return await sync_valento(integration, db, cb)
    elif itype == "generic_xml":
        return await sync_generic_xml(integration, db, cb)
    elif itype == "woocommerce":
        cb("error", 0, 0, "Sincronizare WooCommerce - în dezvoltare")
        raise NotImplementedError("WooCommerce sync not yet implemented")
    else:
        raise ValueError(f"Unknown integration type: {itype}")


async def sync_anda_products(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Full ANDA sync: products + prices + inventory + labeling.

    1. Fetch all 4 XML feeds
    2. Parse each feed
    3. Merge data by item_number (external_id)
    4. Upsert into database in batches
    5. Index in Meilisearch in batches
    """
    config = integration.extra_config or {}
    api_key = integration.api_key or ""

    products_url = config.get("products_url", integration.api_url)
    prices_url = config.get("prices_url", "")
    inventory_url = config.get("inventory_url", "")
    labeling_url = config.get("labeling_url", "")

    # --- Step 1: Download feeds ---
    progress("download", 0, 4, "Se descarcă catalogul de produse...")
    products_xml = await _fetch_xml(products_url, api_key)
    progress("download", 1, 4, "Se descarcă lista de prețuri...")

    prices_data: dict[str, float] = {}
    inventory_data: dict[str, int] = {}
    labeling_data: dict[str, list[dict]] = {}

    if prices_url:
        try:
            prices_xml = await _fetch_xml(prices_url, api_key)
            prices_data = parse_prices_xml(prices_xml)
        except Exception as e:
            logger.warning(f"Failed to fetch prices: {e}")
    progress("download", 2, 4, "Se descarcă stocurile...")

    if inventory_url:
        try:
            inventory_xml = await _fetch_xml(inventory_url, api_key)
            inventory_data = parse_inventory_xml(inventory_xml)
        except Exception as e:
            logger.warning(f"Failed to fetch inventory: {e}")
    progress("download", 3, 4, "Se descarcă opțiunile de personalizare...")

    if labeling_url:
        try:
            labeling_xml = await _fetch_xml(labeling_url, api_key)
            labeling_data = parse_labeling_xml(labeling_xml)
        except Exception as e:
            logger.warning(f"Failed to fetch labeling: {e}")
    progress("download", 4, 4, "Toate feed-urile descărcate")

    # --- Step 2: Parse products ---
    progress("parse", 0, 1, "Se parsează catalogul XML...")
    products_list = parse_products_xml(products_xml)
    total = len(products_list)
    progress("parse", total, total, f"{total} produse parsate")
    logger.info(f"ANDA sync: parsed {total} products")

    # --- Get EUR/RON rate for ANDA price conversion (ANDA prices are in RON) ---
    from app.models.settings import AppSettings
    rate_row = await db.execute(
        select(AppSettings.value).where(AppSettings.key == "exchange_rate_eur_ron")
    )
    eur_ron = float(rate_row.scalar() or _DEFAULT_EUR_RON)
    logger.info(f"ANDA sync: using EUR/RON rate {eur_ron} for price conversion")

    # --- Step 3 & 4: Merge + Upsert in batches ---
    supplier_tag = integration.name.upper()
    now = datetime.now(timezone.utc)
    count = 0
    skipped = 0
    search_docs = []

    for i, p_data in enumerate(products_list):
        ext_id = p_data["external_id"]

        # Skip temporarily unavailable products
        if p_data.pop("temp_unavailable", False):
            skipped += 1
            continue

        # Merge price (ANDA prices are in RON — convert to EUR)
        if ext_id in prices_data:
            p_data["base_price"] = round(prices_data[ext_id] / eur_ron, 4)

        # Merge inventory
        if ext_id in inventory_data:
            p_data["stock"] = inventory_data[ext_id]

        # Merge printing options (labeling uses rootItemNumber)
        root_item = p_data.get("supplier_code", "")
        if ext_id in labeling_data:
            p_data["printing_options"] = labeling_data[ext_id]
        elif root_item and root_item in labeling_data:
            p_data["printing_options"] = labeling_data[root_item]

        # Category hierarchy from ANDA levels
        cat_l1 = p_data.pop("category_l1", "")
        cat_l2 = p_data.pop("category_l2", "")
        cat_l3 = p_data.pop("category_l3", "")

        p_data["category"] = supplier_tag
        p_data["category_group"] = cat_l1
        p_data["subcategory"] = cat_l3 or cat_l2 or cat_l1

        # Upsert
        result = await db.execute(
            select(Product).where(Product.external_id == ext_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key, value in p_data.items():
                setattr(existing, key, value)
            existing.integration_id = integration.id
            existing.last_synced_at = now
            existing.is_active = True
            product = existing
        else:
            product = Product(
                **p_data,
                integration_id=integration.id,
                currency="EUR",
                last_synced_at=now,
                is_active=True,
            )
            db.add(product)

        await db.flush()
        search_docs.append(product.to_search_dict())
        count += 1

        # Batch commit every BATCH_SIZE products
        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total, f"Salvate {count}/{total} produse în baza de date")
            logger.info(f"ANDA sync: processed {count}/{total} products...")

    # Final commit
    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total, f"Toate {count} produse salvate")

    # --- Step 5: Index in Meilisearch in batches ---
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index",
                    batch_count,
                    len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse în motor de căutare",
                )
            logger.info(f"Indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"Meilisearch indexing failed: {e}")

    logger.info(f"ANDA sync complete: {count} products synced, {skipped} skipped (unavailable)")
    return count


async def sync_generic_xml(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Generic XML sync using configurable field mapping.
    Expects extra_config to contain a 'mapping' dict:
    {
        "root_element": "products/product",
        "fields": {
            "external_id": "sku",
            "name": "title",
            "description": "description",
            "base_price": "price",
            "stock": "stock_quantity",
            "image_url": "image",
            "category": "category"
        }
    }
    """
    config = integration.extra_config or {}
    mapping = config.get("mapping", {})
    fields = mapping.get("fields", {})
    root_path = mapping.get("root_element", "product")

    if not fields:
        raise ValueError("Generic XML integration requires a field mapping in extra_config")

    api_key = integration.api_key or ""

    # Download
    progress("download", 0, 1, "Se descarcă feed-ul XML...")
    xml_content = await _fetch_xml(integration.api_url, api_key)
    progress("download", 1, 1, "Feed descărcat")

    # Parse with lxml
    from lxml import etree

    progress("parse", 0, 1, "Se parsează XML...")
    tree = etree.fromstring(xml_content)

    # Find root elements
    elements = tree.xpath(f"//{root_path}")
    total = len(elements)
    progress("parse", total, total, f"{total} produse găsite")

    now = datetime.now(timezone.utc)
    count = 0
    search_docs = []

    for el in elements:
        p_data: dict = {}

        for db_field, xml_field in fields.items():
            node = el.find(xml_field)
            if node is not None and node.text:
                val = node.text.strip()
                if db_field in ("base_price", "stock"):
                    try:
                        val = float(val) if db_field == "base_price" else int(float(val))
                    except (ValueError, TypeError):
                        val = 0.0 if db_field == "base_price" else 0
                p_data[db_field] = val

        ext_id = p_data.get("external_id", "")
        if not ext_id:
            continue

        # Handle images
        if "primary_image" in p_data:
            p_data["images"] = [p_data["primary_image"]]

        # Upsert
        result = await db.execute(
            select(Product).where(Product.external_id == ext_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key, value in p_data.items():
                if key != "external_id":
                    setattr(existing, key, value)
            existing.integration_id = integration.id
            existing.last_synced_at = now
            existing.is_active = True
            product = existing
        else:
            product = Product(
                **p_data,
                integration_id=integration.id,
                currency="EUR",
                last_synced_at=now,
                is_active=True,
            )
            db.add(product)

        await db.flush()
        search_docs.append(product.to_search_dict())
        count += 1

        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total, f"Salvate {count}/{total} produse")

    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total, f"Toate {count} produse salvate")

    # Index
    if search_docs:
        try:
            meili_index(search_docs)
            progress("index", count, count, f"Indexate {count} produse")
        except Exception as e:
            logger.warning(f"Meilisearch indexing failed: {e}")

    return count


async def sync_easygifts(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    EasyGifts sync from local JSON files or API endpoint.

    Supports two modes:
    - Local files: extra_config.json_paths = ["path1.json", "path2.json"]
    - API URL: integration.api_url pointing to JSON endpoint

    EasyGifts JSON structure per product:
    {
        "id": "532903",
        "catalogcode": "5329",
        "name": "Product Name",
        "description": "...",
        "brand": "MoLu",
        "size": "10x5cm",
        "weight": 0.88,
        "color": {"code": "C_03", "name": "Negru", "rgb": "#000000"},
        "chapter": "Category1|Category2",
        "img": ["url1", "url2"],
        "mainpic": "url",
        "material": "...",
        "print": {"technology": [...]},
        ...
    }
    """
    import json as json_lib
    from pathlib import Path

    config = integration.extra_config or {}
    json_paths = config.get("json_paths", [])

    all_products: list[dict] = []

    # --- Load from local JSON files ---
    if json_paths:
        for i, fpath in enumerate(json_paths):
            progress("download", i, len(json_paths), f"Se încarcă {Path(fpath).name}...")
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json_lib.load(f)
                if isinstance(data, list):
                    all_products.extend(data)
                    logger.info(f"EasyGifts: loaded {len(data)} products from {fpath}")
            except Exception as e:
                logger.warning(f"Failed to load {fpath}: {e}")
        progress("download", len(json_paths), len(json_paths), f"Încărcate {len(all_products)} produse din {len(json_paths)} fișiere")

    # --- Or fetch from API URL ---
    elif integration.api_url:
        progress("download", 0, 1, "Se descarcă catalogul EasyGifts...")
        api_key = integration.api_key or ""
        content = await _fetch_xml(integration.api_url, api_key)
        all_products = json_lib.loads(content)
        progress("download", 1, 1, f"Descărcate {len(all_products)} produse")

    if not all_products:
        raise ValueError("Nu s-au găsit produse EasyGifts. Configurați json_paths sau api_url.")

    # --- Load pricelist files ---
    price_map: dict[str, float] = {}
    price_paths = config.get("pricelist_paths", [])
    for fpath in price_paths:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for item in json_lib.load(f):
                    pid = str(item.get("id", ""))
                    price = item.get("price", 0)
                    if pid and price:
                        price_map[pid] = float(price)
            logger.info(f"EasyGifts: loaded {len(price_map)} prices from {Path(fpath).name}")
        except Exception as e:
            logger.warning(f"Failed to load pricelist {fpath}: {e}")

    # --- Load stock files ---
    stock_map: dict[str, int] = {}
    stock_paths = config.get("stock_paths", [])
    for fpath in stock_paths:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for item in json_lib.load(f):
                    sid = str(item.get("id", ""))
                    total_stock = (
                        int(item.get("local", 0))
                        + int(item.get("regional", 0))
                        + int(item.get("international", 0))
                    )
                    if sid:
                        stock_map[sid] = total_stock
            logger.info(f"EasyGifts: loaded {len(stock_map)} stock entries from {Path(fpath).name}")
        except Exception as e:
            logger.warning(f"Failed to load stock {fpath}: {e}")

    if price_map:
        progress("parse", 0, 1, f"Încărcate {len(price_map)} prețuri")
    if stock_map:
        progress("parse", 0, 1, f"Încărcate {len(stock_map)} stocuri")

    # ID prefix from config (default EG for EasyGifts)
    id_prefix = config.get("id_prefix", "EG")
    supplier_tag = integration.name.upper()

    total = len(all_products)
    progress("parse", total, total, f"{total} produse găsite")
    logger.info(f"EasyGifts sync: {total} products to process (prices={len(price_map)}, stocks={len(stock_map)})")

    # --- Process and upsert ---
    now = datetime.now(timezone.utc)
    count = 0
    search_docs = []

    for i, item in enumerate(all_products):
        ext_id = str(item.get("id", ""))
        if not ext_id:
            continue

        # Parse categories from "Cat1|Cat2" string or list format
        chapter = item.get("chapter", "")
        if isinstance(chapter, list):
            categories = [str(c).strip() for c in chapter if c]
        elif isinstance(chapter, str):
            categories = [c.strip() for c in chapter.split("|") if c.strip()]
        else:
            categories = []
        category = supplier_tag
        subcategory = categories[0] if categories else ""
        category_group = get_group(supplier_tag, subcategory) if subcategory else ""

        # Parse color
        color_data = item.get("color", {})
        colors = []
        if color_data and color_data.get("name"):
            colors.append({
                "name": color_data["name"],
                "hex": color_data.get("rgb", ""),
            })

        # Parse images
        images = item.get("img", [])
        mainpic = item.get("mainpic", "")
        primary_image = mainpic or (images[0] if images else "")

        # Parse printing options
        printing_options = []
        print_data = item.get("print", {})
        if print_data and print_data.get("technology"):
            for tech in print_data["technology"]:
                if isinstance(tech, dict):
                    printing_options.append({
                        "position": tech.get("position", ""),
                        "techniques": [{
                            "name": tech.get("name", ""),
                            "max_colors": tech.get("maxColor", ""),
                            "max_width_mm": tech.get("maxWmm", 0),
                            "max_height_mm": tech.get("maxHmm", 0),
                        }],
                    })

        # Build specs
        specs = {}
        if item.get("size"):
            specs["size"] = item["size"]
        if item.get("weight"):
            specs["weight"] = f"{item['weight']} kg"
        if item.get("material"):
            specs["material"] = item["material"]
        if item.get("capacity"):
            specs["capacity"] = item["capacity"]
        if item.get("origin"):
            specs["country_of_origin"] = item["origin"]
        if item.get("gender"):
            specs["gender"] = item["gender"]

        p_data = {
            "external_id": f"{id_prefix}-{ext_id}",
            "supplier_code": item.get("catalogcode", ""),
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "category": category,
            "category_group": category_group,
            "subcategory": subcategory,
            "brand": item.get("brand", ""),
            "images": images,
            "primary_image": primary_image,
            "colors": colors,
            "specifications": specs,
            "printing_options": printing_options,
            "min_order_qty": item.get("exportcarton", 1),
            "base_price": price_map.get(ext_id, 0.0),
            "stock": stock_map.get(ext_id, 0),
        }

        # Upsert
        result = await db.execute(
            select(Product).where(Product.external_id == p_data["external_id"])
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key, value in p_data.items():
                if key != "external_id":
                    setattr(existing, key, value)
            existing.integration_id = integration.id
            existing.last_synced_at = now
            existing.is_active = True
            product = existing
        else:
            product = Product(
                **p_data,
                integration_id=integration.id,
                currency="EUR",
                last_synced_at=now,
                is_active=True,
            )
            db.add(product)

        await db.flush()
        search_docs.append(product.to_search_dict())
        count += 1

        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total, f"Salvate {count}/{total} produse în baza de date")
            logger.info(f"EasyGifts sync: processed {count}/{total} products...")

    # Final commit
    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total, f"Toate {count} produse salvate")

    # Index in Meilisearch
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index",
                    batch_count,
                    len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse în motor de căutare",
                )
            logger.info(f"Indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"Meilisearch indexing failed: {e}")

    logger.info(f"EasyGifts sync complete: {count} products synced")
    return count


# ── Midocean helpers ──────────────────────────────────────────────────

import re

_MO_LETTER_SUFFIX = re.compile(r'^([A-Z]{2}\d+)[a-z](-.*)')


def _mo_sku_fallback(sku: str) -> str | None:
    """Strip trailing letter from master code for pricelist/stock lookup.
    E.g. MO1001b-03-8G → MO1001-03-8G, MO9871c-13-16G → MO9871-13-16G
    """
    m = _MO_LETTER_SUFFIX.match(sku)
    return f"{m.group(1)}{m.group(2)}" if m else None


def _mo_lookup(mapping: dict, sku: str, default=None):
    """Lookup SKU in map with fallback to stripped-letter variant."""
    val = mapping.get(sku)
    if val is not None:
        return val
    alt = _mo_sku_fallback(sku)
    if alt:
        return mapping.get(alt, default)
    return default


_MO_COLOR_HEX: dict[str, str] = {
    "Black": "#000000",
    "Blue": "#3B82F6",
    "Brown": "#92400E",
    "Gold": "#FFD700",
    "Green": "#22C55E",
    "Grey": "#6B7280",
    "Mix": "",
    "Orange": "#F97316",
    "Pink": "#EC4899",
    "Purple": "#A855F7",
    "Red": "#EF4444",
    "Silver": "#C0C0C0",
    "White": "#FFFFFF",
    "Yellow": "#EAB308",
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
async def _fetch_midocean_json(url: str, api_key: str) -> dict | list:
    """Fetch JSON from Midocean API (follows 303 redirects)."""
    headers = {"x-Gateway-APIKey": api_key}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def sync_midocean_products(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Full Midocean sync: products + pricelist + stock.

    Midocean API structure:
    - Products: array of master products, each with variants (color/size combos)
    - Stock: {stock: [{sku, qty, first_arrival_date, first_arrival_qty}]}
    - Pricelist: {price: [{sku, variant_id, price, valid_until}]}

    Each variant becomes a separate Product row (like EasyGifts).
    """
    config = integration.extra_config or {}
    api_key = integration.api_key or ""
    base_url = (integration.api_url or "https://api.midocean.com/gateway").rstrip("/")

    if not api_key:
        raise ValueError("Midocean API key is required. Set MIDOCEAN_API_KEY in .env")

    # --- Step 1: Download all feeds ---
    progress("download", 0, 3, "Se descarcă catalogul Midocean (produse)...")
    products_raw = await _fetch_midocean_json(
        f"{base_url}/products/2.0?language=ro", api_key
    )
    if isinstance(products_raw, dict):
        products_list = products_raw.get("products", products_raw.get("product", []))
    else:
        products_list = products_raw
    logger.info(f"Midocean: downloaded {len(products_list)} master products")
    progress("download", 1, 3, f"{len(products_list)} produse master descărcate. Se descarcă prețuri...")

    # Pricelist
    price_map: dict[str, float] = {}
    try:
        prices_raw = await _fetch_midocean_json(
            f"{base_url}/pricelist/2.0/", api_key
        )
        price_list = prices_raw.get("price", []) if isinstance(prices_raw, dict) else []
        for p in price_list:
            sku = p.get("sku", "")
            price_str = str(p.get("price", "0")).replace(",", ".")
            try:
                price_map[sku] = float(price_str)
            except (ValueError, TypeError):
                pass
        logger.info(f"Midocean: loaded {len(price_map)} prices")
    except Exception as e:
        logger.warning(f"Midocean: failed to fetch pricelist: {e}")
    progress("download", 2, 3, f"{len(price_map)} prețuri descărcate. Se descarcă stocuri...")

    # Stock
    stock_map: dict[str, int] = {}
    try:
        stock_raw = await _fetch_midocean_json(
            f"{base_url}/stock/2.0", api_key
        )
        stock_list = stock_raw.get("stock", []) if isinstance(stock_raw, dict) else []
        for s in stock_list:
            sku = s.get("sku", "")
            qty = int(s.get("qty", 0))
            stock_map[sku] = qty
        logger.info(f"Midocean: loaded {len(stock_map)} stock entries")
    except Exception as e:
        logger.warning(f"Midocean: failed to fetch stock: {e}")
    progress("download", 3, 3, f"Toate feed-urile descărcate ({len(stock_map)} stocuri)")

    # --- Step 2: Flatten master→variants ---
    supplier_tag = integration.name.upper()
    progress("parse", 0, len(products_list), "Se procesează produsele...")
    now = datetime.now(timezone.utc)
    count = 0
    search_docs = []
    total_variants = sum(len(m.get("variants", [])) for m in products_list)
    progress("parse", 0, total_variants, f"{total_variants} variante din {len(products_list)} produse master")

    for master in products_list:
        master_code = master.get("master_code", "")
        product_name = master.get("product_name", "")
        short_desc = master.get("short_description", "")
        long_desc = master.get("long_description", "")
        brand = master.get("brand", "")
        material = master.get("material", "")
        dimensions = master.get("dimensions", "")
        printable = master.get("printable", "no") == "yes"
        country = master.get("country_of_origin", "")

        # Specs from master
        specs: dict = {}
        if material:
            specs["material"] = material
        if dimensions:
            specs["size"] = dimensions
        if master.get("gross_weight"):
            specs["weight"] = f"{master['gross_weight']} {master.get('gross_weight_unit', 'kg')}"
        if country:
            specs["country_of_origin"] = country
        if master.get("number_of_print_positions"):
            specs["print_positions"] = master["number_of_print_positions"]

        # Master-level documents (non-image assets)
        master_docs = [
            a for a in master.get("digital_assets", [])
            if a.get("type") == "document"
        ]

        variants = master.get("variants", [])
        if not variants:
            continue

        for variant in variants:
            sku = variant.get("sku", "")
            if not sku:
                continue

            ext_id = f"MO-{sku}"

            # Supplier as category, cat1 = broad group, cat3 preferred over cat2 as subcategory
            cat1 = variant.get("category_level1", "")
            cat2 = variant.get("category_level2", "")
            cat3 = variant.get("category_level3", "")
            category = supplier_tag
            category_group = cat1
            subcategory = cat3 or cat2 or cat1

            # Color (with hex from color_group)
            color_desc = variant.get("color_description", "")
            color_group = variant.get("color_group", "")
            pms = variant.get("pms_color", "")
            colors = []
            if color_desc:
                colors.append({
                    "name": color_desc,
                    "group": color_group,
                    "hex": _MO_COLOR_HEX.get(color_group, ""),
                    "pms": pms,
                })

            # Images from variant digital_assets
            images = []
            primary_image = ""
            for asset in variant.get("digital_assets", []):
                if asset.get("type") == "image":
                    img_url = asset.get("url_highress") or asset.get("url", "")
                    if img_url:
                        images.append(img_url)
                    if not primary_image and asset.get("subtype") == "item_picture_front":
                        primary_image = asset.get("url", img_url)
            if not primary_image and images:
                primary_image = images[0]

            # Price & stock from maps (with letter-suffix fallback)
            price = _mo_lookup(price_map, sku, 0.0)
            stock = _mo_lookup(stock_map, sku, 0)

            p_data = {
                "external_id": ext_id,
                "supplier_code": master_code,
                "name": product_name,
                "description": long_desc,
                "short_description": short_desc,
                "category": category,
                "category_group": category_group,
                "subcategory": subcategory,
                "brand": brand,
                "images": images,
                "primary_image": primary_image,
                "colors": colors,
                "specifications": specs,
                "printing_options": [],
                "min_order_qty": int(master.get("outer_carton_quantity", 1) or 1),
                "base_price": price,
                "stock": stock,
            }

            # Upsert
            result = await db.execute(
                select(Product).where(Product.external_id == ext_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                for key, value in p_data.items():
                    if key != "external_id":
                        setattr(existing, key, value)
                existing.integration_id = integration.id
                existing.last_synced_at = now
                existing.is_active = True
                product = existing
            else:
                product = Product(
                    **p_data,
                    integration_id=integration.id,
                    currency="EUR",
                    last_synced_at=now,
                    is_active=True,
                )
                db.add(product)

            await db.flush()
            search_docs.append(product.to_search_dict())
            count += 1

            if count % BATCH_SIZE == 0:
                await db.commit()
                progress("save", count, total_variants, f"Salvate {count}/{total_variants} produse în baza de date")
                logger.info(f"Midocean sync: processed {count}/{total_variants} variants...")

    # Final commit
    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total_variants, f"Toate {count} produse salvate")

    # --- Step 3: Index in Meilisearch ---
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index",
                    batch_count,
                    len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse în motor de căutare",
                )
            logger.info(f"Midocean: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"Midocean: Meilisearch indexing failed: {e}")

    logger.info(f"Midocean sync complete: {count} variants from {len(products_list)} master products")
    return count


# ── ROLY / STAMINA (Excel) ────────────────────────────────────────────

# Common color name → hex mapping (Romanian + English, sorted by specificity)
_COLOR_HEX: dict[str, str] = {
    # Whites / Creams
    "alb": "#FFFFFF", "white": "#FFFFFF",
    "crem": "#FFFDD0", "cream": "#FFFDD0",
    "bej": "#D2B48C", "beige": "#D2B48C",
    "natural": "#F5F0E1", "ivory": "#FFFFF0",
    "bourbon vanilla": "#F3E5AB", "vanilie": "#F3E5AB",
    "cameo": "#D9B99B",
    # Blacks / Grays
    "negru": "#000000", "black": "#000000",
    "gri închis": "#374151", "gri inchis": "#374151", "dark gray": "#374151",
    "gri deschis": "#9CA3AF", "gri melanj": "#9CA3AF",
    "gri": "#6B7280", "grey": "#6B7280", "gray": "#6B7280",
    "cenușiu": "#808080",
    "gri vigoare": "#A9A9A9",
    "antracit": "#36454F", "antracit deschis": "#5A6672",
    "antracit melange": "#4A5568",
    "ebony gray": "#555D50",
    "convoy gray": "#5B5B5B",
    "argintiu": "#C0C0C0", "silver": "#C0C0C0",
    # Blues
    "albastru marin": "#1E3A5F", "bleumarin": "#1E3A5F", "navy": "#1E3A5F",
    "dark navy": "#0C1D36",
    "albastru noapte": "#191970", "midnight": "#191970",
    "albastru regal": "#2563EB", "albastru royal": "#2563EB", "royal blue": "#2563EB",
    "albastru": "#2563EB", "blue": "#2563EB",
    "albastru celest": "#87CEEB", "sky blue": "#87CEEB",
    "albastru deschis": "#60A5FA", "light blue": "#60A5FA",
    "albastru azuriu": "#007FFF", "azure": "#007FFF",
    "albastru petrol": "#005F73", "petrol": "#005F73",
    "albastru denim": "#1560BD", "denim": "#1560BD", "denim blue": "#1560BD",
    "denim deschis": "#6B9AC4", "denim închis": "#1A3C6B",
    "albastru melanj": "#7393B3",
    # Reds (ș + ş variants for Romanian cedilla/comma)
    "roșu": "#DC2626", "roşu": "#DC2626", "rosu": "#DC2626", "red": "#DC2626",
    "roșu fucsie": "#E91E63", "roşu fucsie": "#E91E63",
    "roșu marlboro": "#CC0000", "roşu marlboro": "#CC0000",
    "roșu melanj": "#DC2626", "roşu melanj": "#DC2626",
    "bordo": "#800020", "bordeaux": "#800020", "wine": "#800020",
    "grena": "#800000", "maroon": "#800000",
    "roșu lotus": "#B22222",
    "coral": "#FF7F50",
    "formula red": "#CC0000", "marlboro red": "#CC0000",
    "garnet": "#733635",
    "rododendron": "#C71585",
    "vișiniu": "#722F37", "vișiniu melanj": "#722F37",
    # Greens
    "verde": "#16A34A", "green": "#16A34A",
    "verde militar": "#4B5320", "army": "#4B5320", "military green": "#4B5320",
    "verde sticla": "#00796B", "verde sticlă": "#00796B", "bottle green": "#00796B",
    "verde închis": "#14532D", "dark green": "#14532D",
    "verde deschis": "#4ADE80", "light green": "#4ADE80",
    "verde iarbă": "#16A34A", "verde iarba": "#16A34A", "grass green": "#16A34A",
    "verde tei": "#32CD32", "lime": "#84CC16",
    "verde mediu": "#22C55E",
    "kaki": "#6B6B47", "khaki": "#6B6B47",
    "avocado green": "#568203", "avocado": "#568203",
    # Yellows / Oranges
    "galben": "#EAB308", "yellow": "#EAB308",
    "portocaliu": "#EA580C", "orange": "#EA580C",
    "tangerine orange": "#FF9966", "tangerine": "#FF9966",
    "galben fluo": "#CCFF00", "neon yellow": "#CCFF00",
    "portocaliu fluo": "#FF5F1F",
    # Pinks / Purples
    "roz": "#EC4899", "pink": "#EC4899",
    "roz deschis": "#F9A8D4", "light pink": "#F9A8D4",
    "roz închis": "#BE185D",
    "fucsia": "#FF00FF", "fuchsia": "#FF00FF",
    "mov": "#7C3AED", "purple": "#7C3AED",
    "lila": "#C8A2C8", "lilac": "#C8A2C8",
    "lavandă": "#E6E6FA", "lavender": "#E6E6FA",
    "magenta": "#FF00FF",
    "roz fluo": "#FF69B4", "coral fluo": "#FF6F61",
    "verde fluo": "#39FF14",
    # Browns
    "maro": "#92400E", "brown": "#92400E",
    "cafea": "#6F4E37", "coffee": "#6F4E37",
    "ciocolatiu": "#3C1414", "chocolate": "#3C1414",
    "camuflaj maro": "#92400E",
    "camuflaj gri": "#6B7280",
    "camuflaj verde": "#4B5320",
    # Turquoise / Teal
    "turcoaz": "#06B6D4", "turquoise": "#06B6D4",
    # Purples / Violets
    "violet": "#7C3AED", "purpuriu": "#800080", "orchid": "#DA70D6",
    # Special / Other
    "military": "#4B5320",
    "nisip": "#C2B280", "sand": "#C2B280",
    "migdală": "#EFDECD", "almond": "#EFDECD",
    "migdală melanj": "#EFDECD",
    "lămâie": "#FFF44F", "lemon": "#FFF44F",
    "nuga": "#8B6F47", "nougat": "#8B6F47",
    "cafea": "#6F4E37",
    "lemn": "#DEB887", "wood": "#DEB887",
    "sage": "#9DC183",
    "frost": "#D0E8F2",
    "ink": "#1B1B3A",
    "stone melange": "#8A8D8F",
    "sunset melanj": "#FAA460",
    "neon mandarine": "#FF6600",
    # Fluos
    "fluo": "#CCFF00",
    # ROLY-specific colors
    "angora": "#D7C4B0",
    "ocru": "#CC7722", "ochre": "#CC7722",
    "țiglă": "#B66A50", "tigla": "#B66A50",
    "plumb închis": "#3C1053", "plumb inchis": "#3C1053",
    "iris purple": "#5D3FD3",
    "albastru sweet": "#6CA6CD",
    "albastru dusty": "#6E8FAC",
    "albastru profund": "#003366",
    "albastru moonlight": "#9DB8D2",
    "galben sweet": "#FFE99A",
    "alb vintage": "#FAF0E6",
    "verde oasis": "#008B45",
    "verde aventura": "#4CAF50",
    "verde kelly": "#4CBB17",
    "verde mentă": "#3EB489", "verde menta": "#3EB489",
    "gri piatră": "#928E85", "gri piatra": "#928E85",
    "roz mătase": "#E8879E", "roz matase": "#E8879E",
    "roz aprins": "#FF1493",
    "mov purpură": "#800080", "mov purpura": "#800080",
    "grena": "#800000",
}


def _roly_color_hex(color_name: str) -> str:
    """Lookup hex for a color name (case-insensitive, Romanian + English)."""
    if not color_name:
        return ""
    # Clean the name: remove brand label suffixes like "00 (brand label)"
    key = color_name.strip().lower()
    if "(brand label)" in key:
        key = key.split("(")[0].strip()
    # Remove trailing color codes like "00", "02" etc
    import re
    key = re.sub(r"\s+\d{2}$", "", key)

    # Exact match first
    if key in _COLOR_HEX:
        return _COLOR_HEX[key]

    # Partial match — try LONGEST match first to avoid "albastru marin" matching "alb"
    best_match = ""
    best_hex = ""
    for cname, chex in _COLOR_HEX.items():
        if (key.startswith(cname) or cname in key) and len(cname) > len(best_match):
            best_match = cname
            best_hex = chex
    return best_hex


async def sync_roly(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    ROLY / STAMINA sync from local Excel (.xlsx) files.

    Reads Excel files specified in extra_config.xlsx_paths,
    parses product rows by column name, and upserts into DB.

    Both ROLY and STAMINA share the same core columns:
    PRODUCTCODE, MODELCODE, MODELNAME, DESCRIPTION, COMPOSITION,
    FAMILIE, SIZE, COLOR, COLORCODE, CATEGORIES, PRODUCTIMAGE,
    MODELIMAGE, MIN_ORDER_QTY, MEASURES, MADE_IN

    Differences handled:
    - ROLY has GENDER column, STAMINA doesn't
    - Price column names differ (ROLY: 'PRICE UNIT', STAMINA: 'PRICE < 500 UNITS')
    - STAMINA has PRINTCODE column
    """
    import openpyxl
    from pathlib import Path

    config = integration.extra_config or {}
    xlsx_paths = config.get("xlsx_paths", [])
    id_prefix = config.get("id_prefix", "RL")
    supplier_tag = integration.name.upper()

    if not xlsx_paths:
        raise ValueError(
            f"Nu s-au configurat fișiere Excel pentru {supplier_tag}. "
            "Setați extra_config.xlsx_paths."
        )

    # --- Step 1: Load all rows from Excel files ---
    all_rows: list[dict] = []

    for fi, fpath in enumerate(xlsx_paths):
        progress("download", fi, len(xlsx_paths), f"Se încarcă {Path(fpath).name}...")
        try:
            wb = openpyxl.load_workbook(fpath, read_only=True)
            ws = wb[wb.sheetnames[0]]  # First sheet

            # Read header row to get column names
            header_row = next(ws.iter_rows(max_row=1, values_only=True))
            headers = [str(h).strip() if h else "" for h in header_row]

            for row in ws.iter_rows(min_row=2, values_only=True):
                row_dict = {}
                for col_name, val in zip(headers, row):
                    row_dict[col_name] = val
                if row_dict.get("PRODUCTCODE"):
                    all_rows.append(row_dict)

            wb.close()
            logger.info(f"{supplier_tag}: loaded {len(all_rows)} rows from {Path(fpath).name}")
        except Exception as e:
            logger.warning(f"Failed to load {fpath}: {e}")

    progress(
        "download", len(xlsx_paths), len(xlsx_paths),
        f"Încărcate {len(all_rows)} produse din {len(xlsx_paths)} fișiere"
    )

    total = len(all_rows)
    if not total:
        raise ValueError(f"Nu s-au găsit produse în fișierele Excel pentru {supplier_tag}.")

    progress("parse", total, total, f"{total} produse găsite")
    logger.info(f"{supplier_tag} sync: {total} products to process")

    # --- Step 2: Process and upsert ---
    now = datetime.now(timezone.utc)
    count = 0
    search_docs = []

    for i, row in enumerate(all_rows):
        product_code = str(row.get("PRODUCTCODE", "")).strip()
        if not product_code:
            continue

        ext_id = f"{id_prefix}-{product_code}"
        model_code = str(row.get("MODELCODE", "")).strip()
        model_name = str(row.get("MODELNAME", "") or "").strip()
        description = str(row.get("DESCRIPTION", "") or "").strip()
        composition = str(row.get("COMPOSITION", "") or "").strip()
        observation = str(row.get("OBSERVATION", "") or "").strip()

        # Name = model name + color context
        name = model_name or product_code

        # Full description
        full_desc = description
        if observation:
            full_desc = f"{description} {observation}".strip()

        # Categories from comma-separated CATEGORIES column
        categories_str = str(row.get("CATEGORIES", "") or "")
        categories = [c.strip() for c in categories_str.split(",") if c.strip()]
        # Last category is typically the broadest (e.g. "WORKWEAR")
        # First is the most specific
        subcategory = categories[0] if categories else ""
        cat_group = categories[-1] if len(categories) > 1 else (
            str(row.get("FAMILIE", "") or "").strip()
        )

        # Color
        color_name = str(row.get("COLOR", "") or "").strip()
        color_code = str(row.get("COLORCODE", "") or "").strip()
        colors = []
        if color_name:
            colors.append({
                "name": color_name,
                "hex": _roly_color_hex(color_name),
                "code": color_code,
                "image": "",
            })

        # Size
        size = str(row.get("SIZE", "") or "").strip()

        # Images
        product_image = str(row.get("PRODUCTIMAGE", "") or "").strip()
        model_image = str(row.get("MODELIMAGE", "") or "").strip()
        images = []
        primary_image = ""
        if product_image:
            images.append(product_image)
            primary_image = product_image
        if model_image and model_image != product_image:
            images.append(model_image)
        if not primary_image and model_image:
            primary_image = model_image

        # Price — unit price only
        base_price = 0.0
        for price_col in ("PRICE UNIT", "PRICE < 500 UNITS", "PRICE PACK",
                          "PRICE BOX", "PRICE FROM 500 TO 1999 UNITS"):
            val = row.get(price_col)
            if val is not None:
                try:
                    base_price = float(str(val).replace(",", "."))
                    if base_price > 0:
                        break
                except (ValueError, TypeError):
                    pass

        # Specs
        specs: dict = {}
        measures = str(row.get("MEASURES", "") or "").strip()
        if measures:
            specs["dimensions"] = measures
        if size:
            specs["size"] = size
        if composition:
            specs["material"] = composition
        gender = str(row.get("GENDER", "") or "").strip()
        if gender:
            specs["gender"] = gender
        made_in = str(row.get("MADE_IN", "") or "").strip()
        if made_in:
            specs["country_of_origin"] = made_in
        box_weight = str(row.get("PESO_CAJA", "") or "").strip()
        if box_weight:
            specs["box_weight"] = box_weight
        box_dims = str(row.get("MEDIDA_CAJA", "") or "").strip()
        if box_dims:
            specs["box_dimensions"] = box_dims

        # Printing options from PRINTCODE (STAMINA)
        printing_options = []
        print_code = str(row.get("PRINTCODE", "") or "").strip()
        if print_code:
            specs["print_techniques"] = print_code

        # Min order
        min_order = 1
        moq_val = row.get("MIN_ORDER_QTY")
        if moq_val is not None:
            try:
                min_order = max(1, int(float(str(moq_val))))
            except (ValueError, TypeError):
                pass

        p_data = {
            "external_id": ext_id,
            "supplier_code": model_code,
            "name": name,
            "description": full_desc,
            "short_description": description[:200] if description else name,
            "category": supplier_tag,
            "category_group": cat_group,
            "subcategory": subcategory,
            "brand": supplier_tag,
            "images": images,
            "primary_image": primary_image,
            "colors": colors,
            "specifications": specs,
            "printing_options": printing_options,
            "min_order_qty": min_order,
            "base_price": base_price,
            "stock": 999,  # Default available — Excel doesn't include stock
        }

        # Upsert
        result = await db.execute(
            select(Product).where(Product.external_id == ext_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key, value in p_data.items():
                if key != "external_id":
                    setattr(existing, key, value)
            existing.integration_id = integration.id
            existing.last_synced_at = now
            existing.is_active = True
            product = existing
        else:
            product = Product(
                **p_data,
                integration_id=integration.id,
                currency="EUR",
                last_synced_at=now,
                is_active=True,
            )
            db.add(product)

        await db.flush()
        search_docs.append(product.to_search_dict())
        count += 1

        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total, f"Salvate {count}/{total} produse în baza de date")
            logger.info(f"{supplier_tag} sync: processed {count}/{total} products...")

    # Final commit
    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total, f"Toate {count} produse salvate")

    # Index in Meilisearch
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index",
                    batch_count,
                    len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse în motor de căutare",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products synced")
    return count


# ── MALFINI sync ──────────────────────────────────────────────────────

# Default RON→EUR rate (used if DB setting unavailable)
_DEFAULT_EUR_RON = 4.97


async def sync_malfini(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from Malfini REST API (v4).

    1. Login with bearer token
    2. Fetch products, prices, availabilities
    3. Build lookup dicts for price + stock by productSizeCode
    4. Upsert one Product row per SKU (product+color+size)
    5. Index in Meilisearch
    """
    config = integration.extra_config or {}
    api_url = config.get("api_url") or integration.api_url or "https://api.malfini.com"
    username = config.get("username", "")
    password = config.get("password", "")

    if not username or not password:
        raise ValueError("Credențiale Malfini lipsă (username/password)")

    # Get EUR/RON exchange rate from settings
    from app.models.settings import AppSettings
    rate_row = await db.execute(
        select(AppSettings.value).where(AppSettings.key == "exchange_rate_eur_ron")
    )
    eur_ron = float(rate_row.scalar() or _DEFAULT_EUR_RON)

    now = datetime.now(timezone.utc)
    supplier_tag = "MALFINI"

    # ── Step 1: Login ─────────────────────────────────────────────────
    progress("download", 0, 4, "Autentificare la Malfini API...")

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        login_resp = await client.post(
            f"{api_url}/api/v4/api-auth/login",
            json={"username": username, "password": password},
        )
        login_resp.raise_for_status()
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        logger.info(f"{supplier_tag}: authenticated successfully")

        # ── Step 2: Fetch products ────────────────────────────────────
        progress("download", 1, 4, "Se descarcă catalogul de produse...")
        prod_resp = await client.get(
            f"{api_url}/api/v4/product?language=ro", headers=headers
        )
        prod_resp.raise_for_status()
        products_data = prod_resp.json()
        logger.info(f"{supplier_tag}: fetched {len(products_data)} products")

        # ── Step 3: Fetch prices ──────────────────────────────────────
        progress("download", 2, 4, "Se descarcă lista de prețuri...")
        price_resp = await client.get(
            f"{api_url}/api/v4/product/prices", headers=headers
        )
        price_resp.raise_for_status()
        prices_raw = price_resp.json()
        logger.info(f"{supplier_tag}: fetched {len(prices_raw)} price entries")

        # ── Step 4: Fetch stock ───────────────────────────────────────
        progress("download", 3, 4, "Se descarcă stocurile...")
        avail_resp = await client.get(
            f"{api_url}/api/v4/product/availabilities", headers=headers
        )
        avail_resp.raise_for_status()
        avail_raw = avail_resp.json()
        logger.info(f"{supplier_tag}: fetched {len(avail_raw)} availability entries")

    progress("download", 4, 4, "Toate datele descărcate")

    # ── Build price lookup: productSizeCode → price (lowest limit tier) ──
    price_map: dict[str, float] = {}
    for pe in prices_raw:
        sku = pe.get("productSizeCode", "")
        limit_val = pe.get("limit", 1)
        price_val = pe.get("price", 0.0)
        currency = pe.get("currency", "RON")
        # Keep the price for the lowest limit (base price)
        if limit_val <= 1 or sku not in price_map:
            # Convert RON → EUR
            if currency == "RON":
                price_val = round(price_val / eur_ron, 2)
            price_map[sku] = price_val

    # ── Build stock lookup: productSizeCode → quantity (current) ─────
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stock_map: dict[str, int] = {}
    for ae in avail_raw:
        sku = ae.get("productSizeCode", "")
        qty = ae.get("quantity", 0)
        date_str = (ae.get("date") or "")[:10]
        if date_str <= today:
            stock_map[sku] = stock_map.get(sku, 0) + qty

    # ── Build product rows ────────────────────────────────────────────
    total_skus = sum(
        len(nom)
        for p in products_data
        for v in p.get("variants", [])
        for nom in [v.get("nomenclatures", [])]
    )
    progress("parse", 0, total_skus, f"Se procesează {total_skus} SKU-uri...")

    search_docs = []
    count = 0

    for product in products_data:
        p_code = product.get("code", "")
        p_name = product.get("name", "")
        category_name = product.get("categoryName", "")
        gender = product.get("gender", "")
        trademark = product.get("trademark", "")
        p_type = product.get("type", "")
        subtitle = product.get("subtitle", "")
        specification = product.get("specification", "")
        description = product.get("description", "")
        full_desc = " ".join(filter(None, [subtitle, specification, description]))

        # Category mapping
        cat_group = get_group(supplier_tag, category_name)
        subcategory = category_name

        for variant in product.get("variants", []):
            v_code = variant.get("code", "")
            color_name = variant.get("name", "")
            color_code = variant.get("colorCode", "")
            color_icon = variant.get("colorIconLink", "")

            # Try to get hex from color name using ROLY mapper (Romanian names)
            color_hex = _roly_color_hex(color_name) if color_name else ""

            colors = [{
                "name": color_name,
                "hex": color_hex,
                "code": color_code,
                "image": color_icon,
            }]

            # Attributes → specs
            specs_base: dict[str, str] = {}
            for attr in variant.get("attributes", []):
                attr_code = attr.get("code", "")
                attr_text = attr.get("text", "")
                if attr_code == "material-composition":
                    specs_base["material"] = attr_text
                elif attr_code == "grammage":
                    specs_base["weight"] = attr_text
                elif attr_code == "type-of-application":
                    specs_base["print_techniques"] = attr_text
                elif attr_code == "label":
                    specs_base["label"] = attr_text

            if gender:
                specs_base["gender"] = gender

            # Images from variant
            images = []
            primary_image = ""
            # Sort images: prefer viewCodes that show the full product (c, d, e)
            # over close-ups (a) and soles/backs (b)
            _VIEW_PRIO = {"c": 0, "d": 1, "e": 2, "f": 3, "b": 4, "a": 5}
            sorted_imgs = sorted(
                variant.get("images", []),
                key=lambda x: _VIEW_PRIO.get(x.get("viewCode", "z")[-1:].lower(), 3)
            )
            for img in sorted_imgs:
                img_url = img.get("link", "")
                if img_url:
                    img_url = img_url.replace("~w400", "~w800")
                    images.append(img_url)
                    if not primary_image:
                        primary_image = img_url

            # Printing options from attributes
            printing_options = []
            print_tech = specs_base.get("print_techniques", "")
            if print_tech:
                printing_options = [
                    {"technique": t.strip()} for t in print_tech.split(",") if t.strip()
                ]

            for nom in variant.get("nomenclatures", []):
                sku = nom.get("productSizeCode", "")
                size_name = nom.get("sizeName", "")
                ean = nom.get("ean", "")
                expedition_qty = nom.get("expeditionQuantity", 1)
                net_weight = nom.get("netWeight", 0.0)

                ext_id = f"MF-{sku}"
                base_price = price_map.get(sku, 0.0)
                stock = stock_map.get(sku, 0)

                # Build variant name
                variant_name = f"{p_name} {color_name}" if color_name else p_name

                specs = dict(specs_base)
                if size_name:
                    specs["size"] = size_name
                if ean:
                    specs["ean"] = ean
                if net_weight:
                    specs["weight_kg"] = str(net_weight)

                p_data = {
                    "external_id": ext_id,
                    "supplier_code": p_code,
                    "name": variant_name,
                    "description": full_desc,
                    "short_description": subtitle or specification or p_name,
                    "category": supplier_tag,
                    "category_group": cat_group,
                    "subcategory": subcategory,
                    "brand": trademark,
                    "images": images,
                    "primary_image": primary_image,
                    "colors": colors,
                    "specifications": specs,
                    "printing_options": printing_options,
                    "min_order_qty": max(1, expedition_qty),
                    "base_price": base_price,
                    "stock": stock,
                }

                # Upsert
                result = await db.execute(
                    select(Product).where(Product.external_id == ext_id)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    for key, value in p_data.items():
                        if key != "external_id":
                            setattr(existing, key, value)
                    existing.integration_id = integration.id
                    existing.last_synced_at = now
                    existing.is_active = True
                    product_obj = existing
                else:
                    product_obj = Product(
                        **p_data,
                        integration_id=integration.id,
                        currency="EUR",
                        last_synced_at=now,
                        is_active=True,
                    )
                    db.add(product_obj)

                await db.flush()
                search_docs.append(product_obj.to_search_dict())
                count += 1

                if count % BATCH_SIZE == 0:
                    await db.commit()
                    progress("save", count, total_skus,
                             f"Salvate {count}/{total_skus} produse în baza de date")
                    logger.info(f"{supplier_tag} sync: processed {count}/{total_skus} products...")

    # Final commit
    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total_skus, f"Toate {count} produse salvate")

    # Index in Meilisearch
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse în motor de căutare",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products synced")
    return count


# ---------------------------------------------------------------------------
# MAKITO
# ---------------------------------------------------------------------------

_MAKITO_COLOR_MAP: dict[str, tuple[str, str]] = {
    # Yellows
    "AMA": ("Galben", "#EAB308"),
    "AMAP": ("Galben pastel", "#FDE047"),
    "FAMA": ("Galben fluorescent", "#CCFF00"),
    "LIMON": ("Galben lamaie", "#FEF08A"),
    "MOSTA": ("Mustar", "#CA8A04"),
    "DOR": ("Auriu", "#FFD700"),
    # Blues
    "AZUL": ("Albastru", "#3B82F6"),
    "AZULP": ("Albastru pastel", "#93C5FD"),
    "AZC": ("Albastru deschis", "#7DD3FC"),
    "AZR": ("Albastru royal", "#1D4ED8"),
    "AZU_F": ("Albastru fluorescent", "#3B82F6"),
    "CEL": ("Albastru cer", "#87CEEB"),
    "MAR": ("Bleumarin", "#1E3A5F"),
    "MROS": ("Bleumarin inchis", "#0F172A"),
    # Whites
    "BLA": ("Alb", "#FFFFFF"),
    "NATU": ("Natural", "#FAF9F6"),
    "TRANS": ("Transparent", "#FFFFFF"),
    # Blacks
    "NEG": ("Negru", "#000000"),
    # Reds
    "ROJ": ("Rosu", "#EF4444"),
    "BUR": ("Bordo", "#800020"),
    "GRNT": ("Bordo", "#800020"),
    # Greens
    "VER": ("Verde", "#22C55E"),
    "VEB": ("Verde sticla", "#006400"),
    "VEC": ("Verde deschis", "#86EFAC"),
    "VEM": ("Verde menta", "#98F5E1"),
    "VEO": ("Verde vanator", "#355E3B"),
    "VERMI": ("Verde militar", "#4B5320"),
    "VERP": ("Verde pastel", "#86EFAC"),
    "VERA": ("Verde aqua", "#00CED1"),
    "FVER": ("Verde fluorescent", "#39FF14"),
    "LIMA": ("Verde lime", "#84CC16"),
    "PIS": ("Verde fistic", "#93C572"),
    "KIWI": ("Verde kiwi", "#8EE53F"),
    "OLIVA": ("Verde oliv", "#6B8E23"),
    # Greys
    "GRI": ("Gri", "#6B7280"),
    "GRCL": ("Gri deschis", "#D1D5DB"),
    "GROS": ("Gri inchis", "#374151"),
    # Browns
    "MARR": ("Maro", "#8B4513"),
    "MAOS": ("Maro inchis", "#5D4037"),
    "BEI": ("Bej", "#D4A574"),
    "BEIGP": ("Bej pastel", "#F5F5DC"),
    "AREN": ("Nisipiu", "#C2B280"),
    "AREO": ("Nisipiu inchis", "#A0926B"),
    "TIERR": ("Maro pamant", "#8B6914"),
    # Oranges
    "NARA": ("Portocaliu", "#F97316"),
    "FNAR": ("Portocaliu fluorescent", "#FF6700"),
    "MANDA": ("Mandarin", "#FF8C00"),
    "SALM": ("Somon", "#FA8072"),
    "COR": ("Coral", "#FF7F50"),
    # Pinks
    "ROSA": ("Roz", "#EC4899"),
    "ROSAP": ("Roz pastel", "#FBCFE8"),
    "ROFL": ("Roz fluorescent", "#FF69B4"),
    "FUCSI": ("Fuchsia", "#FF00FF"),
    "FFUC": ("Fuchsia fluorescent", "#FF00FF"),
    "PITAY": ("Roz pitaya", "#E84B8A"),
    # Purples
    "MORA": ("Mov", "#A855F7"),
    "LILA": ("Lila", "#C084FC"),
    # Others
    "PLAT": ("Argintiu", "#C0C0C0"),
    "PLMT": ("Argintiu mat", "#B0B0B0"),
    "TURQ": ("Turcoaz", "#06B6D4"),
    "KAK": ("Kaki", "#6B6B37"),
    "CAMU": ("Camuflaj", "#4B5320"),
    "MULTI": ("Multicolor", "#000000"),
    "RAIN": ("Curcubeu", "#FF0000"),
    # Combos
    "AMBL": ("Galben/Alb", "#EAB308"),
    "AZBL": ("Albastru/Alb", "#3B82F6"),
    "BLAM": ("Alb/Galben", "#FFFFFF"),
    "BLAZ": ("Alb/Albastru", "#FFFFFF"),
    "BLFU": ("Alb/Fuchsia", "#FFFFFF"),
    "BLNA": ("Alb/Portocaliu", "#FFFFFF"),
    "BLNG": ("Alb/Negru", "#FFFFFF"),
    "BLPL": ("Alb/Argintiu", "#FFFFFF"),
    "BLRO": ("Alb/Rosu", "#FFFFFF"),
    "BLVE": ("Alb/Verde", "#FFFFFF"),
    "BENE": ("Bej/Negru", "#D4A574"),
    "GRAM": ("Gri/Galben", "#6B7280"),
    "GRAZ": ("Gri/Albastru", "#6B7280"),
    "GRNG": ("Gri/Negru", "#6B7280"),
    "GRRO": ("Gri/Rosu", "#6B7280"),
    "GRVE": ("Gri/Verde", "#6B7280"),
    "NABL": ("Portocaliu/Alb", "#F97316"),
    "NEAZ": ("Negru/Albastru", "#000000"),
    "NEBL": ("Negru/Alb", "#000000"),
    "NENE": ("Negru", "#000000"),
    "NEPL": ("Negru/Argintiu", "#000000"),
    "NERO": ("Negru/Rosu", "#000000"),
    "NGGR": ("Negru/Gri", "#000000"),
    "ROAM": ("Rosu/Galben", "#EF4444"),
    "ROBL": ("Rosu/Alb", "#EF4444"),
    "ROMA": ("Rosu/Bleumarin", "#EF4444"),
    "ROPL": ("Rosu/Argintiu", "#EF4444"),
    "VEBL": ("Verde/Alb", "#22C55E"),
    "VENE": ("Verde/Negru", "#22C55E"),
    # No color
    "S/C": ("", ""),
}


async def sync_makito(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from Makito REST/JSON API (data.makito.es).

    1. Login with email/password to get Bearer token
    2. Fetch products, stock, prices, images, descriptions, colors, categories
    3. Build lookup dicts
    4. Upsert one Product row per variant (color + size) using stock matnr mapping
    5. Index in Meilisearch
    """
    config = integration.extra_config or {}
    email = config.get("email", "")
    password = config.get("password", "")
    base_url = config.get("base_url", "https://data.makito.es/api")
    supplier_tag = "MAKITO"

    if not email or not password:
        progress("error", 0, 0, "Lipsesc credențialele Makito (email/password)")
        raise ValueError("Makito credentials not configured (email/password)")

    progress("download", 0, 8, "Autentificare Makito API...")

    # --- 1. Login to get Bearer token ---
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            login_resp = await client.post(
                f"{base_url}/login",
                json={"email": email, "password": password},
                headers={"Accept": "application/json"},
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()
            # Response format: {"status": 1, "msg": "client_id|token"}
            msg = login_data.get("msg", "")
            if login_data.get("status") == 1 and "|" in str(msg):
                token = str(msg).split("|", 1)[1]
            else:
                token = login_data.get("token") or login_data.get("access_token", "")
            if not token:
                raise ValueError(f"Login failed: {login_data}")
            logger.info(f"{supplier_tag}: authenticated successfully")
        except Exception as e:
            progress("error", 0, 0, f"Eroare autentificare Makito: {e}")
            raise

        auth_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        # Endpoint name -> JSON response key mapping
        _ENDPOINT_KEYS = {
            "products": "products",
            "stock": "stock",
            "prices": "tarifs",
            "images": "images",
            "descriptions": "descriptions",
            "colors": "colors",
            "categories": "categories",
        }

        async def _fetch_endpoint(name: str, step: int) -> list[dict]:
            """Fetch a JSON endpoint and return the data list."""
            url = f"{base_url}/{name}"
            try:
                resp = await client.get(url, headers=auth_headers)
                resp.raise_for_status()
                body = resp.json()
                # Each endpoint wraps data under its own key
                data_key = _ENDPOINT_KEYS.get(name, name)
                if isinstance(body, dict):
                    items = body.get(data_key, [])
                    if not isinstance(items, list):
                        # Fallback: find the first list value
                        for v in body.values():
                            if isinstance(v, list):
                                items = v
                                break
                        else:
                            items = []
                else:
                    items = body if isinstance(body, list) else []
                progress("download", step, 8, f"Descărcat {name}: {len(items)} intrări")
                logger.info(f"{supplier_tag}: fetched {name}: {len(items)} entries")
                return items
            except Exception as e:
                logger.warning(f"{supplier_tag}: failed to fetch {name}: {e}")
                progress("download", step, 8, f"Eroare {name}: {e}")
                return []

        # --- 2. Fetch all endpoints ---
        progress("download", 1, 8, "Descărcare produse...")
        products_data = await _fetch_endpoint("products", 1)
        stock_data = await _fetch_endpoint("stock", 2)
        prices_data = await _fetch_endpoint("prices", 3)
        images_data = await _fetch_endpoint("images", 4)
        descriptions_data = await _fetch_endpoint("descriptions", 5)
        colors_data = await _fetch_endpoint("colors", 6)
        categories_data = await _fetch_endpoint("categories", 7)
        progress("download", 8, 8, "Toate datele descărcate, procesare...")

    # --- 3. Build lookup dicts ---

    # Stock: group by ref, also keep per-matnr mapping
    # Stock values can be strings like "1.000.000" (European thousand-separator)
    def _parse_stock_value(val) -> int:
        if isinstance(val, (int, float)):
            return int(val)
        s = str(val).strip().replace(".", "").replace(",", "")
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 0

    stock_by_matnr: dict[str, int] = {}
    stock_by_ref: dict[str, int] = {}
    for entry in stock_data:
        matnr = str(entry.get("matnr", "")).strip()
        ref = str(entry.get("ref", "")).strip()
        qty = _parse_stock_value(entry.get("stock", 0))
        if matnr:
            stock_by_matnr[matnr] = qty
        if ref:
            stock_by_ref[ref] = stock_by_ref.get(ref, 0) + qty

    # Prices: ref -> base_price (unit price from price_1)
    price_map: dict[str, float] = {}
    for entry in prices_data:
        ref = str(entry.get("ref", "")).strip()
        if not ref:
            continue
        # price_1 is the base/single-unit price
        price_text = str(entry.get("price_1", "0")).strip().replace(",", ".")
        try:
            price_map[ref] = float(price_text)
        except ValueError:
            pass

    # Images: ref -> list of image URLs, with main image first
    images_by_ref: dict[str, list[str]] = {}
    primary_image_by_ref: dict[str, str] = {}
    for entry in images_data:
        ref = str(entry.get("ref", "")).strip()
        if not ref:
            continue
        img_url = str(entry.get("img_max", "") or entry.get("img_min", "")).strip()
        if not img_url:
            continue
        if ref not in images_by_ref:
            images_by_ref[ref] = []
        is_main = entry.get("main") in (1, "1", True)
        if is_main:
            primary_image_by_ref[ref] = img_url
            images_by_ref[ref].insert(0, img_url)
        elif img_url not in images_by_ref[ref]:
            images_by_ref[ref].append(img_url)

    # Descriptions: ref -> {info, type, comp} (prefer lang=2 English, fallback lang=1 Spanish)
    desc_by_ref: dict[str, dict[str, str]] = {}
    for entry in descriptions_data:
        ref = str(entry.get("ref", "")).strip()
        lang = entry.get("lang")
        info = str(entry.get("info", "")).strip()
        dtype = str(entry.get("type", "")).strip()
        comp = str(entry.get("comp", "")).strip()
        if not ref:
            continue
        # Prefer English (lang=2)
        if ref not in desc_by_ref or lang == 2 or lang == "2":
            desc_by_ref[ref] = {"info": info, "type": dtype, "comp": comp}

    # Colors from API: color_code -> (name, hex)  (prefer lang=2 English)
    api_colors: dict[str, tuple[str, str]] = {}
    for entry in colors_data:
        code = str(entry.get("color_code", "")).strip().upper()
        lang = entry.get("lang")
        name = str(entry.get("name", "")).strip()
        hex_val = str(entry.get("code", "")).strip()
        if not code or not name:
            continue
        # Prefer English (lang=2)
        if code not in api_colors or lang == 2 or lang == "2":
            if hex_val and not hex_val.startswith("#"):
                hex_val = f"#{hex_val}"
            api_colors[code] = (name, hex_val)

    # Categories: ref -> category name (prefer lang=2 English)
    cat_by_ref: dict[str, str] = {}
    for entry in categories_data:
        ref = str(entry.get("ref", "")).strip()
        lang = entry.get("lang")
        cat_name = str(entry.get("category", "")).strip()
        if not ref or not cat_name:
            continue
        if ref not in cat_by_ref or lang == 2 or lang == "2":
            cat_by_ref[ref] = cat_name

    logger.info(
        f"{supplier_tag}: built lookups - {len(stock_by_ref)} stock refs, "
        f"{len(price_map)} prices, {len(images_by_ref)} image refs, "
        f"{len(desc_by_ref)} descriptions, {len(api_colors)} colors, "
        f"{len(cat_by_ref)} categories"
    )

    # Extract color codes from stock unique_ref for products with empty colors
    # unique_ref format: "{ref}{COLOR_CODE}{SIZE}" e.g. "2008AMAS/T"
    import re as _re
    colors_from_stock: dict[str, set[str]] = {}
    for entry in stock_data:
        ref = str(entry.get("ref", "")).strip()
        unique_ref = str(entry.get("unique_ref", "")).strip()
        if ref and unique_ref and unique_ref.startswith(ref):
            suffix = unique_ref[len(ref):]
            # Extract color code (uppercase letters before size like S/T, S, M, L, XL etc.)
            m = _re.match(r"([A-Z_]+)", suffix)
            if m:
                cc = m.group(1)
                if ref not in colors_from_stock:
                    colors_from_stock[ref] = set()
                colors_from_stock[ref].add(cc)

    # --- 4. Process products and upsert ---
    now = datetime.now(timezone.utc)
    count = 0
    search_docs = []
    seen_external_ids: set[str] = set()

    total_products = len(products_data)
    progress("process", 0, total_products, f"Procesare {total_products} produse Makito...")

    for prod in products_data:
        ref = str(prod.get("ref", "")).strip()
        name = str(prod.get("name", "")).strip()
        if not ref or not name:
            continue

        desc_data = desc_by_ref.get(ref, {})
        description = desc_data.get("info", "")
        material = desc_data.get("comp", "")
        product_type = desc_data.get("type", "")
        brand = str(prod.get("brand", "")).strip() or "Makito"
        base_price = price_map.get(ref, 0.0)
        makito_cat = cat_by_ref.get(ref, "") or product_type
        category_group = get_group(supplier_tag, makito_cat) if makito_cat else ""

        # Parse color codes from comma-separated string or from stock data
        colors_str = str(prod.get("colors", "")).strip()
        color_codes = [c.strip().upper() for c in colors_str.split(",") if c.strip()]
        if not color_codes:
            # Fall back to colors extracted from stock unique_ref
            color_codes = sorted(colors_from_stock.get(ref, set()))

        # Parse sizes from comma-separated string
        sizes_str = str(prod.get("sizes", "")).strip()
        size_list = [s.strip() for s in sizes_str.split(",") if s.strip()]
        # Filter out "S/T" (one-size) markers
        size_list = [s for s in size_list if s.upper() not in ("S/T", "ST", "S.T")]

        # --- Fix: If sizes is empty but color codes contain size suffixes, split them ---
        # e.g. AZULL -> color=AZUL, size=L; GRIXXL -> color=GRI, size=XXL
        # Some codes are already translated names (e.g. "Gri", "Negru") — skip those
        _SIZE_SUFFIXES = ["XXXL", "XXL", "XL", "XS", "S", "M", "L"]
        if not size_list and len(color_codes) > 1:
            # Separate splittable codes from standalone color codes
            # A standalone color is one in _MAKITO_COLOR_MAP or api_colors (e.g. GRI, NEG, BLA)
            known_colors = set(_MAKITO_COLOR_MAP.keys()) | set(api_colors.keys())
            raw_codes = [cc for cc in color_codes
                         if cc.isalpha() and cc == cc.upper() and len(cc) > 1
                         and cc not in known_colors]

            split_colors = set()
            split_sizes = set()
            can_split = len(raw_codes) > 1  # Need at least 2 raw codes to detect pattern
            if can_split:
                for cc in raw_codes:
                    matched = False
                    for sz in _SIZE_SUFFIXES:
                        if cc.endswith(sz) and len(cc) > len(sz):
                            split_colors.add(cc[:-len(sz)])
                            split_sizes.add(sz)
                            matched = True
                            break
                    if not matched:
                        can_split = False
                        break
            # Only apply if every raw code was split and we have multiple sizes
            if can_split and len(split_sizes) > 1:
                color_codes = sorted(split_colors)
                # Order sizes logically
                _SIZE_ORDER = {"XS": 0, "S": 1, "M": 2, "L": 3, "XL": 4, "XXL": 5, "XXXL": 6}
                size_list = sorted(split_sizes, key=lambda s: _SIZE_ORDER.get(s, 99))
                logger.info(f"{supplier_tag} ref={ref}: split color+size -> colors={color_codes}, sizes={size_list}")

        # Get images for this ref
        images = images_by_ref.get(ref, [])
        primary_image = primary_image_by_ref.get(ref, images[0] if images else "")

        # Get dimensions from product fields
        length = str(prod.get("length", "")).strip()
        height = str(prod.get("height", "")).strip()
        width = str(prod.get("width", "")).strip()
        dim_parts = [f"{length}mm" if length else "", f"{height}mm" if height else "", f"{width}mm" if width else ""]
        dimensions = " x ".join(p for p in dim_parts if p)
        weight = str(prod.get("weight", "")).strip()
        printcode = str(prod.get("printcode", "")).strip()

        # Build color objects
        product_colors = []
        for cc in color_codes:
            if cc.upper() in _MAKITO_COLOR_MAP:
                cname, chex = _MAKITO_COLOR_MAP[cc.upper()]
            elif cc.upper() in api_colors:
                cname, chex = api_colors[cc.upper()]
            else:
                cname = cc
                chex = _roly_color_hex(cc)
            product_colors.append({
                "name": cname,
                "hex": chex,
                "code": cc,
                "image": "",
            })

        # If no color codes, create a single "no color" variant
        if not color_codes:
            product_colors = [{"name": "", "hex": "", "code": "", "image": ""}]

        total_stock = stock_by_ref.get(ref, 0)

        # Create one Product row per ref (aggregated) — matches how frontend groups by supplier_code
        external_id = f"MK-{ref}"
        seen_external_ids.add(external_id)

        p_data = {
            "external_id": external_id,
            "supplier_code": ref,
            "name": name,
            "description": description,
            "short_description": f"{product_type}. {description}" if description else product_type,
            "category": supplier_tag,
            "category_group": category_group,
            "subcategory": makito_cat,
            "brand": brand,
            "base_price": base_price,
            "currency": "EUR",
            "min_order_qty": 1,
            "stock": total_stock,
            "colors": product_colors,
            "specifications": {
                "sizes": ", ".join(size_list) if size_list else "",
                "dimensions": dimensions,
                "material": material,
                "weight": f"{weight}g" if weight else "",
                "printcode": printcode,
            },
            "primary_image": primary_image,
            "images": images[:20],  # Limit to 20 images
            "printing_options": [],
        }

        stmt = select(Product).where(
            Product.external_id == external_id,
            Product.integration_id == integration.id,
        )
        result = await db.execute(stmt)
        product_obj = result.scalar_one_or_none()

        if product_obj:
            for k, v in p_data.items():
                setattr(product_obj, k, v)
            product_obj.last_synced_at = now
            product_obj.is_active = True
        else:
            product_obj = Product(
                **p_data,
                integration_id=integration.id,
                last_synced_at=now,
                is_active=True,
            )
            db.add(product_obj)

        await db.flush()
        search_docs.append(product_obj.to_search_dict())
        count += 1

        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total_products,
                     f"Salvate {count} produse Makito în baza de date")
            logger.info(f"{supplier_tag} sync: processed {count} products...")

    # Deactivate old Makito products not in current sync
    old_stmt = select(Product).where(
        Product.integration_id == integration.id,
        Product.is_active == True,
        Product.last_synced_at < now,
    )
    old_result = await db.execute(old_stmt)
    deactivated = 0
    for old_product in old_result.scalars().all():
        old_product.is_active = False
        deactivated += 1
    if deactivated:
        logger.info(f"{supplier_tag}: deactivated {deactivated} old products")

    # Final commit
    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total_products, f"Toate {count} produse Makito salvate")

    # Index in Meilisearch
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse Makito",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products synced, {deactivated} deactivated")
    return count


# ── UTT (TShirt Europe) ──────────────────────────────────────────────

_UTT_IMAGE_BASE = "https://tshirteurope.com/img/product_images/640/"
_UTT_PRODUCT_URL = "https://tshirteurope.com/ro/catalog/product/"


def _utt_extract_price_stock(html: str) -> tuple[float, int]:
    """Extract base price and total stock from a UTT product detail page."""
    import re as _re
    from collections import Counter as _Counter

    standard_prices: list[float] = []
    all_prices: list[float] = []
    total_stock = 0

    for m in _re.finditer(
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

    if not all_prices and total_stock == 0:
        for p in _re.findall(r'"BaseSellingPrice"\s*:\s*"([^"]+)"', html):
            try:
                v = float(p)
                if v > 0:
                    all_prices.append(v)
            except ValueError:
                continue
        for inv in _re.findall(r'"Inventory"\s*:\s*"([^"]+)"', html):
            try:
                total_stock += int(inv)
            except ValueError:
                continue

    # Prefer standard prices; fall back to all prices (including outlet)
    prices = standard_prices if standard_prices else all_prices
    if prices:
        base_price = _Counter(round(p, 4) for p in prices).most_common(1)[0][0]
    else:
        base_price = 0.0

    return base_price, total_stock


async def _utt_fetch_prices(styles: list[str], progress: ProgressCallback) -> dict[str, tuple[float, int]]:
    """Scrape UTT product pages for price and stock data.

    Respects UTT rate limit: 2 requests/minute per API key.
    Sends 2 concurrent requests then waits 31s before the next pair.
    """
    import httpx

    result: dict[str, tuple[float, int]] = {}
    total = len(styles)

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        timeout=15,
    ) as client:
        batch_size = 2  # UTT limit: 2 requests per minute

        async def _fetch(style: str) -> tuple[str, float, int]:
            try:
                resp = await client.get(f"{_UTT_PRODUCT_URL}{style.lower()}", follow_redirects=True)
                if resp.status_code == 429:
                    wait_secs = int(resp.headers.get("Retry-After", "60"))
                    logger.warning(f"UTT rate limited, waiting {wait_secs}s")
                    await asyncio.sleep(wait_secs)
                    resp = await client.get(f"{_UTT_PRODUCT_URL}{style.lower()}", follow_redirects=True)
                if resp.status_code == 200:
                    price, stock = _utt_extract_price_stock(resp.text)
                    return style, price, stock
            except Exception:
                pass
            return style, 0.0, 0

        for i in range(0, total, batch_size):
            batch = styles[i : i + batch_size]
            results = await asyncio.gather(*[_fetch(s) for s in batch])
            for style, price, stock in results:
                if price > 0 or stock > 0:
                    result[style] = (price, stock)

            done = min(i + batch_size, total)
            progress("prices", done, total, f"Prețuri UTT: {done}/{total}")

            # Wait 31s between batches to respect 2 req/min limit
            if i + batch_size < total:
                await asyncio.sleep(31)

    return result


async def sync_utt(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from UTT (TShirt Europe) JSON feed.
    One Product row per style with all colors/sizes.
    """
    import json as _json
    import pathlib

    config = integration.extra_config or {}
    api_key = config.get("api_key") or integration.api_key or ""
    supplier_tag = "UTT"

    local_dir = config.get("local_json_dir", "")

    progress("download", 0, 1, "Descărcare catalog UTT...")

    feed_data: list[dict] = []
    if local_dir:
        local_path = pathlib.Path(local_dir)
        json_files = list(local_path.glob("style*.json"))
        if json_files:
            logger.info(f"{supplier_tag}: loading from local file {json_files[0]}")
            feed_data = _json.loads(json_files[0].read_bytes())
    if not feed_data:
        try:
            url = f"https://www.tshirteurope.com/api/v1/style?apikey={api_key}"
            raw = await _fetch_xml(url)
            feed_data = _json.loads(raw)
        except Exception as e:
            progress("error", 0, 0, f"Eroare descărcare UTT: {e}")
            raise

    progress("download", 1, 1, f"Catalog UTT încărcat: {len(feed_data)} stiluri")

    styles = [s for s in feed_data if not s.get("style", "").endswith("-cat")]
    total_styles = len(styles)
    logger.info(f"{supplier_tag}: {total_styles} real styles to process")

    # Scrape prices and stock from product pages
    progress("prices", 0, total_styles, "Descărcare prețuri UTT...")
    style_codes = [(s.get("style") or "").strip() for s in styles if (s.get("style") or "").strip()]
    price_stock_map = await _utt_fetch_prices(style_codes, progress)
    logger.info(f"{supplier_tag}: scraped prices for {len(price_stock_map)} products")

    now = datetime.now(timezone.utc)
    count = 0
    search_docs = []

    for item in styles:
        style = (item.get("style") or "").strip()
        if not style:
            continue

        name = (item.get("shortdesc_en") or "").strip()
        if not name:
            continue

        description = (item.get("longdesc_ro") or item.get("longdesc_en") or "").strip()
        short_desc = (item.get("shortdesc_en") or "").strip()
        category_ro = (item.get("category_ro") or item.get("category_en") or "").strip()
        brand = (item.get("brand") or "").strip()
        material = (item.get("fabric_ro") or item.get("fabric_en") or "").strip()
        weight_gsm = item.get("gsmweight") or 0

        category_group = get_group(supplier_tag, category_ro)

        colors_str = (item.get("colors") or "").strip()
        color_list = [c.strip() for c in colors_str.split("|") if c.strip()] if colors_str else []
        colors = [{"name": cn, "hex": _roly_color_hex(cn), "code": "", "image": ""} for cn in color_list]

        sizes_str = (item.get("sizes") or "").strip()
        size_list = [s.strip() for s in sizes_str.split("|") if s.strip()] if sizes_str else []

        image_path = (item.get("imageurl") or "").strip()
        primary_image = f"{_UTT_IMAGE_BASE}{image_path.lstrip('/')}" if image_path else ""

        images = []
        if primary_image:
            images.append(primary_image)
        alt_images_str = (item.get("altimageurl") or "").strip()
        if alt_images_str:
            for aimg in alt_images_str.split("|"):
                aimg = aimg.strip()
                if aimg:
                    full_url = f"{_UTT_IMAGE_BASE}{aimg.lstrip('/')}"
                    if full_url not in images:
                        images.append(full_url)

        external_id = f"UTT-{style}"

        p_data = {
            "external_id": external_id,
            "supplier_code": style,
            "name": name,
            "description": description,
            "short_description": short_desc,
            "category": supplier_tag,
            "category_group": category_group,
            "subcategory": category_ro,
            "brand": brand,
            "base_price": price_stock_map.get(style, (0.0, 0))[0],
            "currency": "EUR",
            "min_order_qty": 1,
            "stock": price_stock_map.get(style, (0.0, 0))[1],
            "colors": colors,
            "specifications": {
                "sizes": ", ".join(size_list),
                "material": material,
                "weight": f"{weight_gsm} g/m²" if weight_gsm else "",
            },
            "primary_image": primary_image,
            "images": images,
            "printing_options": [],
        }

        stmt = select(Product).where(
            Product.external_id == external_id,
            Product.integration_id == integration.id,
        )
        result = await db.execute(stmt)
        product_obj = result.scalar_one_or_none()

        if product_obj:
            for k, v in p_data.items():
                setattr(product_obj, k, v)
            product_obj.last_synced_at = now
            product_obj.is_active = True
        else:
            product_obj = Product(
                **p_data,
                integration_id=integration.id,
                last_synced_at=now,
                is_active=True,
            )
            db.add(product_obj)

        await db.flush()
        search_docs.append(product_obj.to_search_dict())
        count += 1

        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total_styles,
                     f"Salvate {count} produse UTT în baza de date")

    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total_styles, f"Toate {count} produse UTT salvate")

    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse UTT",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync utt complete: {count} products synced")
    return count


# ── STRICKER sync ─────────────────────────────────────────────────────


async def _fetch_stricker_json(url: str, timeout: float = HTTP_TIMEOUT) -> dict:
    """Fetch JSON from Stricker API."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def sync_stricker(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from Stricker REST API.

    1. Authenticate with access key to get session token
    2. Fetch products (master catalog), optionals (SKUs with prices/colors/sizes),
       and stocks
    3. Group optionals by ProdReference to build one Product row per reference
    4. Prices are in RON — convert to EUR using exchange rate
    5. Upsert + index in Meilisearch
    """
    config = integration.extra_config or {}
    api_key = config.get("access_key") or integration.api_key or ""
    base_url = (
        config.get("base_url")
        or integration.api_url
        or "https://ws.stricker-europe.com/api/v1SSL"
    ).rstrip("/")
    supplier_tag = "STRICKER"

    if not api_key:
        progress("error", 0, 0, "Lipsește cheia de acces Stricker (access_key)")
        raise ValueError("Stricker access key is required")

    # Get EUR/RON exchange rate from settings
    from app.models.settings import AppSettings
    rate_row = await db.execute(
        select(AppSettings.value).where(AppSettings.key == "exchange_rate_eur_ron")
    )
    eur_ron = float(rate_row.scalar() or _DEFAULT_EUR_RON)

    now = datetime.now(timezone.utc)

    # ── Step 1: Authenticate ─────────────────────────────────────────
    progress("download", 0, 4, "Autentificare la Stricker API...")
    try:
        auth_data = await _fetch_stricker_json(
            f"{base_url}/AuthenticateClient?accessKey={api_key}"
        )
        token = auth_data.get("Token", "")
        if not token:
            raise ValueError(f"Stricker auth failed: {auth_data}")
        logger.info(f"{supplier_tag}: authenticated successfully")
    except Exception as e:
        progress("error", 0, 0, f"Eroare autentificare Stricker: {e}")
        raise

    # ── Step 2: Fetch products ───────────────────────────────────────
    progress("download", 1, 4, "Se descarcă catalogul de produse Stricker...")
    products_data = await _fetch_stricker_json(
        f"{base_url}/products?token={token}&lang=EN"
    )
    products_list = products_data.get("Products", [])
    logger.info(f"{supplier_tag}: fetched {len(products_list)} products")

    # Build product lookup by ProdReference
    product_info: dict[str, dict] = {}
    for prod in products_list:
        ref = prod.get("ProdReference", "")
        if ref:
            product_info[ref] = prod

    # ── Step 3: Fetch optionalsComplete (SKUs with prices, colors, sizes) ─
    progress("download", 2, 4, f"{len(products_list)} produse descărcate. Se descarcă variantele (optionals)...")
    optionals_data = await _fetch_stricker_json(
        f"{base_url}/optionalsComplete?token={token}&lang=EN"
    )
    optionals_list = optionals_data.get("OptionalsComplete", optionals_data.get("Optionals", []))
    logger.info(f"{supplier_tag}: fetched {len(optionals_list)} optionals (SKUs)")

    # ── Step 4: Fetch stocks ─────────────────────────────────────────
    progress("download", 3, 4, f"{len(optionals_list)} variante descărcate. Se descarcă stocurile...")
    stock_data = await _fetch_stricker_json(
        f"{base_url}/Stocks?token={token}&lang=EN"
    )
    stocks_list = stock_data.get("Stocks", [])
    stock_map: dict[str, int] = {}
    for s in stocks_list:
        sku = s.get("Sku", "")
        qty = int(s.get("Quantity", 0))
        if sku:
            stock_map[sku] = qty
    logger.info(f"{supplier_tag}: fetched {len(stock_map)} stock entries")
    progress("download", 4, 4, "Toate datele Stricker descărcate")

    # ── Step 5: Group optionals by ProdReference ─────────────────────
    # Each ProdReference becomes one Product row (aggregated colors/sizes)
    from collections import defaultdict
    optionals_by_ref: dict[str, list[dict]] = defaultdict(list)
    for opt in optionals_list:
        ref = opt.get("ProdReference", "")
        if ref:
            optionals_by_ref[ref].append(opt)

    # Merge: use product_info keys + any refs from optionals not in product_info
    all_refs = set(product_info.keys()) | set(optionals_by_ref.keys())
    total_refs = len(all_refs)
    progress("parse", 0, total_refs, f"Se procesează {total_refs} produse Stricker...")

    count = 0
    search_docs = []

    for ref in all_refs:
        prod = product_info.get(ref, {})
        opts = optionals_by_ref.get(ref, [])

        # Basic info from Products endpoint
        product_name = prod.get("Name", "")
        description = prod.get("Description", "")
        is_textil = prod.get("IsTextil", False)
        prod_type = prod.get("Type", "")
        prod_subtype = prod.get("SubType", "")
        main_image_name = prod.get("MainImage", "")

        # If no product info (only optionals), try to get name from first optional
        if not product_name and opts:
            product_name = opts[0].get("ProdReference", ref)

        ext_id = f"STRICKER-{ref}"

        # Category
        category = supplier_tag
        category_group = prod_type
        subcategory = prod_subtype or prod_type

        # Aggregate colors from optionals
        colors = []
        seen_colors = set()
        sizes = set()
        min_price_ron = None
        total_stock = 0
        all_images = []
        printing_options = []
        seen_print_zones = set()

        for opt in opts:
            sku = opt.get("SKU", "") or opt.get("Sku", "")

            # Color
            color_name = opt.get("ColorDesc1", "")
            color_hex = opt.get("ColorHex1", "")
            color_code = opt.get("ColorCode", "")
            opt_image_name = opt.get("OptionalImage1", "")
            opt_image_url = ""
            if opt_image_name:
                opt_image_url = f"https://www.stricker-europe.com/fotos/produtos/{opt_image_name}"
                if opt_image_url not in all_images:
                    all_images.append(opt_image_url)

            if color_name and color_name not in seen_colors:
                seen_colors.add(color_name)
                hex_val = f"#{color_hex}" if color_hex and not color_hex.startswith("#") else (color_hex or "")
                colors.append({
                    "name": color_name,
                    "hex": hex_val,
                    "code": color_code,
                    "image": opt_image_url,
                })

            # Size (for textiles)
            size = opt.get("Size", "")
            if size:
                sizes.add(size)

            # Price (YourPrice or fallback to Price1 tier, all in RON)
            price_ron = opt.get("YourPrice")
            if price_ron is None:
                # Fallback: use lowest tier price available
                for pi in range(10, 0, -1):
                    pv = opt.get(f"Price{pi}")
                    if pv is not None:
                        try:
                            price_ron = float(pv)
                            break
                        except (ValueError, TypeError):
                            continue
            if price_ron is not None:
                try:
                    price_ron = float(price_ron)
                    if price_ron > 0 and (min_price_ron is None or price_ron < min_price_ron):
                        min_price_ron = price_ron
                except (ValueError, TypeError):
                    pass

            # Stock (aggregate from stock_map by SKU)
            if sku:
                total_stock += stock_map.get(sku, 0)

            # Print zones from Component/Location/Area/CustomizationTypes fields
            for i in range(1, 9):
                component = opt.get(f"Component{i}", "")
                location = opt.get(f"Location{i}", "")
                area = opt.get(f"Area{i}", "")
                custom_types = opt.get(f"CustomizationTypes{i}", "")

                if location and location not in seen_print_zones:
                    seen_print_zones.add(location)

                    # Parse area dimensions (e.g., "50x30" → width/height)
                    max_w = 0.0
                    max_h = 0.0
                    if area and "x" in str(area).lower():
                        parts = str(area).lower().split("x")
                        try:
                            max_w = float(parts[0].strip())
                            max_h = float(parts[1].strip())
                        except (ValueError, IndexError):
                            pass

                    # Parse customization types into technique list
                    techniques = []
                    if custom_types:
                        for tech_name in str(custom_types).split(","):
                            tech_name = tech_name.strip()
                            if tech_name:
                                techniques.append({
                                    "name": tech_name,
                                    "setup_cost": 0.0,
                                    "unit_cost": 0.0,
                                })

                    if techniques or area:
                        printing_options.append({
                            "position": location,
                            "component": component,
                            "max_width_mm": max_w,
                            "max_height_mm": max_h,
                            "area_raw": area,
                            "techniques": techniques,
                        })

        # Primary image from Products endpoint MainImage
        primary_image = ""
        if main_image_name:
            primary_image = f"https://www.stricker-europe.com/fotos/produtos/{main_image_name}"
            if primary_image not in all_images:
                all_images.insert(0, primary_image)
        elif all_images:
            primary_image = all_images[0]

        # Convert price: RON → EUR
        base_price_ron = min_price_ron or 0.0
        base_price_eur = round(base_price_ron / eur_ron, 2) if base_price_ron > 0 else 0.0

        # Build specifications
        specs: dict = {}
        if is_textil:
            specs["is_textile"] = True
        if sizes:
            specs["sizes"] = sorted(sizes, key=lambda s: _size_sort_key(s))
            specs["size"] = ", ".join(specs["sizes"])
        if prod.get("Material"):
            specs["material"] = prod["Material"]
        if prod.get("Weight"):
            specs["weight"] = str(prod["Weight"])
        if prod.get("Dimensions"):
            specs["dimensions"] = prod["Dimensions"]

        p_data = {
            "external_id": ext_id,
            "supplier_code": ref,
            "name": product_name,
            "description": description,
            "short_description": description[:500] if description else "",
            "category": category,
            "category_group": get_group(supplier_tag, subcategory) if subcategory else category_group,
            "subcategory": subcategory,
            "brand": supplier_tag,
            "images": all_images,
            "primary_image": primary_image,
            "colors": colors,
            "specifications": specs,
            "printing_options": printing_options,
            "min_order_qty": 1,
            "base_price": base_price_eur,
            "stock": total_stock,
        }

        # Upsert
        result = await db.execute(
            select(Product).where(Product.external_id == ext_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key, value in p_data.items():
                if key != "external_id":
                    setattr(existing, key, value)
            existing.integration_id = integration.id
            existing.last_synced_at = now
            existing.is_active = True
            product_obj = existing
        else:
            product_obj = Product(
                **p_data,
                integration_id=integration.id,
                currency="EUR",
                last_synced_at=now,
                is_active=True,
            )
            db.add(product_obj)

        await db.flush()
        search_docs.append(product_obj.to_search_dict())
        count += 1

        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total_refs,
                     f"Salvate {count}/{total_refs} produse Stricker în baza de date")
            logger.info(f"{supplier_tag}: processed {count}/{total_refs} products...")

    # Final commit
    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total_refs, f"Toate {count} produse Stricker salvate")

    # ── Step 6: Index in Meilisearch ─────────────────────────────────
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse Stricker în motor de căutare",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products synced")
    return count


# ──────────────────────────────────────────────────────────────────────
# Promolog
# ──────────────────────────────────────────────────────────────────────

_PROMOLOG_IMAGE_BASE = "https://d3aoz2g723acmw.cloudfront.net/__thumb/royal-feed/"
_PROMOLOG_IMAGE_PARAMS = "?source=images&height=500&quality=90"


async def sync_promolog(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from Promolog XML API.

    1. Fetch products XML + stock XML (Basic Auth)
    2. Build stock lookup
    3. Group color variants under base supplier_code
    4. Upsert aggregated products
    5. Index in Meilisearch
    """
    import xml.etree.ElementTree as ET

    config = integration.extra_config or {}
    login = config.get("login", "")
    password = config.get("password", "")
    supplier_tag = "PROMOLOG"

    if not login or not password:
        progress("error", 0, 0, "Lipsesc credențialele Promolog (login/password)")
        raise ValueError("Promolog credentials not configured (login/password)")

    progress("download", 0, 3, "Descărcare produse Promolog...")

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        auth = (login, password)

        # Fetch products XML
        try:
            resp = await client.get(
                "https://www.promolog.com/en/api/products-en",
                auth=auth,
            )
            resp.raise_for_status()
            products_xml = resp.content
            progress("download", 1, 3, "Produse descărcate")
        except Exception as e:
            progress("error", 0, 0, f"Eroare descărcare produse: {e}")
            raise

        # Fetch stock XML
        try:
            resp2 = await client.get(
                "https://www.promolog.com/en/api/stock",
                auth=auth,
            )
            resp2.raise_for_status()
            stock_xml = resp2.content
            progress("download", 2, 3, "Stocuri descărcate")
        except Exception as e:
            logger.warning(f"{supplier_tag}: stock fetch failed: {e}")
            stock_xml = b"<products></products>"

    # --- Parse stock ---
    stock_map: dict[str, int] = {}
    try:
        stock_root = ET.fromstring(stock_xml)
        for sp in stock_root.findall("product"):
            code = (sp.findtext("code") or "").strip()
            stock_val = (sp.findtext("stock") or "0").strip().replace(".", "").replace(",", "")
            try:
                stock_map[code] = int(float(stock_val))
            except (ValueError, TypeError):
                pass
    except ET.ParseError:
        logger.warning(f"{supplier_tag}: failed to parse stock XML")

    progress("download", 3, 3, f"Stocuri parsate: {len(stock_map)} intrări. Procesare produse...")

    # --- Parse products ---
    root = ET.fromstring(products_xml)
    xml_products = root.findall("product")
    logger.info(f"{supplier_tag}: parsed {len(xml_products)} product entries")

    # Group by base code (R73444.02 -> R73444)
    from collections import defaultdict
    grouped: dict[str, list] = defaultdict(list)
    for p in xml_products:
        code = (p.findtext("code") or "").strip()
        if not code:
            continue
        base = code.rsplit(".", 1)[0] if "." in code else code
        grouped[base].append(p)

    progress("process", 0, len(grouped), f"Procesare {len(grouped)} modele...")

    count = 0
    seen_ids: set[str] = set()
    search_docs: list[dict] = []

    for idx, (base_code, variants) in enumerate(grouped.items()):
        if idx % 100 == 0:
            progress("process", idx, len(grouped), f"Procesare {idx}/{len(grouped)} modele...")

        # Use first variant as reference
        ref = variants[0]
        name = (ref.findtext("name_en") or "").strip()
        # Strip color from name if present
        color_name_ref = (ref.findtext("colour_en") or "").strip()
        base_name = name
        if color_name_ref and name.lower().endswith(color_name_ref.lower()):
            base_name = name[: -len(color_name_ref)].rstrip(", ").strip()
        if not base_name:
            base_name = name

        description = (ref.findtext("long_description_en") or "").strip()
        short_desc = (ref.findtext("short_description_en") or "").strip()
        dimensions = (ref.findtext("dimensions") or "").strip()
        material = (ref.findtext("material_en") or "").strip()

        # Categories
        categories = []
        subcategories = []
        for ce in ref.findall("category_en"):
            if ce.text and ce.text.strip() and ce.text.strip() != "All products":
                categories.append(ce.text.strip())
        for se in ref.findall("sub_category_en"):
            if se.text and se.text.strip():
                subcategories.append(se.text.strip())
        category = categories[0] if categories else "All products"
        subcategory = subcategories[0] if subcategories else ""
        category_group = get_group(supplier_tag, subcategory or category) if (subcategory or category) else ""

        # Printing options from imprint_en
        printing_options = []
        for imp in ref.findall("imprint_en"):
            if imp.text and imp.text.strip():
                parts = imp.text.strip().split("|")
                method = parts[0].strip() if parts else ""
                position = parts[1].strip() if len(parts) > 1 else ""
                max_size = parts[2].strip() if len(parts) > 2 else ""
                max_colors = parts[3].strip() if len(parts) > 3 else ""
                printing_options.append({
                    "method": method,
                    "position": position,
                    "max_size": max_size,
                    "max_colors": max_colors,
                })

        # Aggregate colors, stock, best price, images
        colors = []
        total_stock = 0
        best_price = 999999.0
        catalogue_price = 0.0
        all_images: list[str] = []
        primary_image = ""

        for v in variants:
            v_code = (v.findtext("code") or "").strip()
            v_color = (v.findtext("colour_en") or "").strip()
            v_price_str = (v.findtext("your_price_EUR") or "0").strip()
            v_cat_price_str = (v.findtext("catalogue_price_EUR") or "0").strip()

            try:
                v_price = float(v_price_str)
            except ValueError:
                v_price = 0.0
            try:
                v_cat = float(v_cat_price_str)
            except ValueError:
                v_cat = 0.0

            if v_price > 0 and v_price < best_price:
                best_price = v_price
            if v_cat > catalogue_price:
                catalogue_price = v_cat

            v_stock = stock_map.get(v_code, 0)
            total_stock += v_stock

            # Color info
            color_suffix = v_code.rsplit(".", 1)[1] if "." in v_code else ""
            # Images for this variant
            v_images = []
            for img_el in v.findall("images"):
                if img_el.text and img_el.text.strip():
                    img_name = img_el.text.strip()
                    img_url = f"{_PROMOLOG_IMAGE_BASE}{img_name}{_PROMOLOG_IMAGE_PARAMS}"
                    v_images.append(img_url)
                    if img_url not in all_images:
                        all_images.append(img_url)

            color_image = v_images[0] if v_images else ""
            if v_color and v_color not in [c["name"] for c in colors]:
                colors.append({
                    "name": v_color,
                    "hex": "",
                    "code": color_suffix,
                    "image": color_image,
                })

            if not primary_image and v_images:
                primary_image = v_images[0]

        if best_price >= 999999:
            best_price = 0.0

        # Meilisearch IDs cannot contain dots — replace with underscore
        safe_code = base_code.replace(".", "_")
        external_id = f"PL-{safe_code}"
        seen_ids.add(external_id)

        p_data = {
            "external_id": external_id,
            "supplier_code": base_code,
            "name": base_name,
            "description": description,
            "short_description": short_desc,
            "category": supplier_tag,
            "category_group": category_group,
            "subcategory": subcategory or category,
            "brand": supplier_tag,
            "base_price": best_price,
            "currency": "EUR",
            "min_order_qty": 1,
            "stock": total_stock,
            "colors": colors,
            "specifications": {
                "dimensions": dimensions,
                "material": material,
            },
            "primary_image": primary_image,
            "images": all_images[:20],
            "printing_options": printing_options,
        }

        # Upsert
        result = await db.execute(
            select(Product).where(
                Product.integration_id == integration.id,
                Product.external_id == external_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            for k, v in p_data.items():
                setattr(existing, k, v)
            existing.is_active = True
            existing.updated_at = datetime.now(timezone.utc)
        else:
            new_p = Product(
                integration_id=integration.id,
                **p_data,
            )
            db.add(new_p)
        count += 1

        # Search doc
        color_names = [c["name"] for c in colors if c.get("name")]
        search_docs.append({
            "id": external_id,
            "external_id": external_id,
            "integration_id": str(integration.id),
            "supplier_code": base_code,
            "name": base_name,
            "description": description or short_desc,
            "short_description": short_desc,
            "category": supplier_tag,
            "category_group": category_group,
            "subcategory": subcategory or category,
            "brand": supplier_tag,
            "base_price": best_price,
            "currency": "EUR",
            "stock": total_stock,
            "colors": [{"name": cn, "hex": "", "image": ""} for cn in color_names],
            "primary_image": primary_image,
            "supplier": supplier_tag,
            "is_active": True,
        })

    # Flush DB
    await db.flush()
    progress("process", len(grouped), len(grouped), f"Procesate {count} modele Promolog")

    # Deactivate old products
    all_result = await db.execute(
        select(Product).where(Product.integration_id == integration.id)
    )
    for p in all_result.scalars().all():
        if p.external_id not in seen_ids:
            p.is_active = False

    await db.commit()

    # Index in Meilisearch
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i: i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse Promolog",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products synced")
    return count


# ──────────────────────────────────────────────────────────────────────
# SIPEC
# ──────────────────────────────────────────────────────────────────────

_SIPEC_API_BASE = "https://www.sipec.com/d/api-rivenditori"
_SIPEC_IMG_PROXY = "/api/img/?w=400&url="


def _sipec_img(url: str) -> str:
    """Wrap a SIPEC image URL through the proxy for resize+cache."""
    if not url:
        return ""
    from urllib.parse import quote
    return f"{_SIPEC_IMG_PROXY}{quote(url, safe='')}"


async def sync_sipec(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from SIPEC bulk download API.

    1. Download anagrafiche_articoli (items) + disponibilita (stock) as JSON
    2. Group items by prodotto__codice
    3. Non-textile: 1 Product row per product, aggregate color variants
    4. Textile (with sizes): 1 Product row per size/color combo
    5. Index in Meilisearch
    """
    config = integration.extra_config or {}
    api_key = config.get("api_key", "")
    supplier_tag = "SIPEC"

    if not api_key:
        raise ValueError("SIPEC api_key not configured")

    headers = {"Authorization": f"api-key {api_key}"}

    progress("fetch", 0, 3, "Descărcare articole SIPEC...")

    # 1. Download items (anagrafiche_articoli)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        items_resp = await client.get(
            f"{_SIPEC_API_BASE}/download-database/anagrafiche_articoli/?formato=json",
            headers=headers,
        )
        items_resp.raise_for_status()
        all_items = items_resp.json()
        progress("fetch", 1, 3, f"Descărcate {len(all_items)} articole")

        # 2. Download stock (disponibilita)
        progress("fetch", 1, 3, "Descărcare stoc SIPEC...")
        stock_resp = await client.get(
            f"{_SIPEC_API_BASE}/download-database/disponibilita/?formato=json",
            headers=headers,
        )
        stock_resp.raise_for_status()
        stock_data = stock_resp.json()
        progress("fetch", 2, 3, f"Descărcat stoc pentru {len(stock_data)} articole")

        # 3. Download categories
        progress("fetch", 2, 3, "Descărcare categorii SIPEC...")
        cat_resp = await client.get(
            f"{_SIPEC_API_BASE}/download-database/categorie/?formato=json",
            headers=headers,
        )
        cat_resp.raise_for_status()
        categories_data = cat_resp.json()
        progress("fetch", 3, 3, "Date SIPEC descărcate complet")

    # Build lookup maps
    stock_map: dict[str, float] = {}
    for s in stock_data:
        code = (s.get("articolo__codice") or "").strip()
        if code:
            stock_map[code] = float(s.get("disponibilita") or 0)

    # Build category lookup: id -> {name_en, parent_id}
    cat_lookup: dict[str, dict] = {}
    for c in categories_data:
        cid = str(c.get("id", ""))
        cat_lookup[cid] = {
            "name": (c.get("nome_en") or c.get("nome_it") or "").strip(),
            "parent_id": str(c.get("categoria_padre_id") or ""),
        }

    def get_top_category(cat_id: str) -> str:
        """Walk up to root category."""
        visited = set()
        current = cat_id
        while current and current in cat_lookup and current not in visited:
            visited.add(current)
            parent = cat_lookup[current]["parent_id"]
            if not parent or parent not in cat_lookup:
                return cat_lookup[current]["name"]
            current = parent
        return cat_lookup.get(cat_id, {}).get("name", "")

    # Group items by product code
    from collections import defaultdict
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in all_items:
        prod_code = (item.get("prodotto__codice") or item.get("codice", "")).strip()
        if prod_code:
            grouped[prod_code].append(item)

    progress("process", 0, len(grouped), f"Procesare {len(grouped)} produse SIPEC...")

    count = 0
    search_docs: list[dict] = []
    seen_ids: set[str] = set()

    for idx, (prod_code, items_list) in enumerate(grouped.items()):
        if idx % 100 == 0:
            progress("process", idx, len(grouped), f"Procesare {idx}/{len(grouped)}...")

        # Determine if textile (has sizes)
        has_sizes = any(it.get("taglia") for it in items_list)

        # Get common product info from first item
        first = items_list[0]
        name = (first.get("titolo_en") or first.get("titolo_it") or "").strip()
        description = (first.get("descrizione_en") or first.get("descrizione_it") or "").strip()
        long_desc = (first.get("descrizione_lunga_en") or first.get("descrizione_lunga_it") or "").strip()
        if long_desc:
            description = long_desc

        cat_id = str(first.get("categoria_id") or "")
        subcat_id = str(first.get("sottocategoria_id") or "")
        subcategory = (first.get("sottocategoria_nome_en") or first.get("sottocategoria_nome_it") or "").strip()
        category_group = (first.get("categoria_nome_en") or first.get("categoria_nome_it") or "").strip()
        # Get top-level category for grouping
        top_cat = get_top_category(cat_id) if cat_id else category_group

        material = (first.get("materiale_nome_en") or first.get("materiale_nome_it") or "").strip()
        dimensions = (first.get("dimensione articolo") or "").strip()
        weight = first.get("peso") or ""
        gramaj = (first.get("grammatura") or "").strip()

        if not has_sizes:
            # ── Non-textile: aggregate all color variants into one Product ──
            colors = []
            total_stock = 0
            best_price = 999999.0
            all_images: list[str] = []
            primary_image = ""

            for it in items_list:
                it_code = (it.get("codice") or "").strip()
                color_name = (it.get("colore_nome_en") or it.get("colore_nome_it") or "").strip()
                price_str = it.get("prezzo_listino_rivenditore")
                try:
                    price = float(price_str) if price_str else 0.0
                except (ValueError, TypeError):
                    price = 0.0

                if 0 < price < best_price:
                    best_price = price

                it_stock = stock_map.get(it_code, 0)
                total_stock += int(it_stock)

                # Images — link_immagine may contain comma-separated URLs
                raw_imgs = (it.get("link_immagine") or "").strip()
                v_images = [_sipec_img(u.strip()) for u in raw_imgs.split(",") if u.strip()] if raw_imgs else []
                for img_url in v_images:
                    if img_url not in all_images:
                        all_images.append(img_url)
                if not primary_image and v_images:
                    primary_image = v_images[0]

                color_image = v_images[0] if v_images else ""
                if color_name and color_name not in [c["name"] for c in colors]:
                    colors.append({
                        "name": color_name,
                        "hex": "",
                        "image": color_image,
                    })

            if best_price >= 999999:
                best_price = 0.0

            # Meilisearch IDs: only alphanumeric, hyphens, underscores
            safe_prod_code = prod_code.replace(" ", "_").replace(".", "_")
            external_id = f"SP-{safe_prod_code}"
            seen_ids.add(external_id)

            p_data = {
                "external_id": external_id,
                "supplier_code": prod_code,
                "name": name,
                "description": description,
                "short_description": name,
                "category": supplier_tag,
                "category_group": top_cat or category_group,
                "subcategory": subcategory or category_group,
                "brand": supplier_tag,
                "base_price": best_price,
                "currency": "EUR",
                "min_order_qty": 1,
                "stock": total_stock,
                "colors": colors,
                "specifications": {
                    "dimensions": dimensions,
                    "material": material,
                    "weight": str(weight) if weight else "",
                    "grammage": gramaj,
                },
                "primary_image": primary_image,
                "images": all_images[:20],
                "printing_options": [],
            }

            # Add available sizes if present (non-textile with sizes)
            taglie_raw = (first.get("taglie disponibili") or "").strip()
            if taglie_raw:
                all_sizes_str = ", ".join(
                    s.strip().strip("'\"") for s in taglie_raw.split(",") if s.strip().strip("'\"")
                )
                if all_sizes_str:
                    p_data["specifications"]["sizes"] = all_sizes_str

            existing = await db.execute(
                select(Product).where(
                    Product.integration_id == integration.id,
                    Product.external_id == external_id,
                )
            )
            product = existing.scalar_one_or_none()
            if product:
                for k, v in p_data.items():
                    setattr(product, k, v)
                product.is_active = True
                product.last_synced_at = datetime.now(timezone.utc)
            else:
                product = Product(
                    integration_id=integration.id,
                    is_active=True,
                    last_synced_at=datetime.now(timezone.utc),
                    **p_data,
                )
                db.add(product)

            await db.flush()

            # Search doc
            color_names = [c["name"] for c in colors if c.get("name")]
            search_docs.append({
                "id": external_id,
                "external_id": external_id,
                "integration_id": str(integration.id),
                "supplier_code": prod_code,
                "name": name,
                "description": description,
                "short_description": name,
                "category": supplier_tag,
                "category_group": top_cat or category_group,
                "subcategory": subcategory or category_group,
                "brand": supplier_tag,
                "base_price": best_price,
                "currency": "EUR",
                "stock": total_stock,
                "colors": [{"name": cn, "hex": "", "image": ""} for cn in color_names],
                "primary_image": primary_image,
                "supplier": supplier_tag,
                "is_active": True,
            })
            count += 1

        else:
            # ── Textile: one Product row per size/color combo ──
            # Group by color
            color_items: dict[str, list[dict]] = defaultdict(list)
            for it in items_list:
                color = (it.get("colore_nome_en") or it.get("colore_nome_it") or "default").strip()
                color_items[color].append(it)

            for color_name, c_items in color_items.items():
                for it in c_items:
                    it_code = (it.get("codice") or "").strip()
                    size = (it.get("taglia") or "").strip()
                    if not size:
                        continue

                    price_str = it.get("prezzo_listino_rivenditore")
                    try:
                        price = float(price_str) if price_str else 0.0
                    except (ValueError, TypeError):
                        price = 0.0

                    it_stock = int(stock_map.get(it_code, 0))
                    raw_imgs = (it.get("link_immagine") or "").strip()
                    v_images = [_sipec_img(u.strip()) for u in raw_imgs.split(",") if u.strip()] if raw_imgs else []
                    img_url = v_images[0] if v_images else ""

                    safe_it_code = it_code.replace(" ", "_").replace(".", "_")
                    ext_id = f"SP-{safe_it_code}"
                    seen_ids.add(ext_id)

                    # Available sizes from "taglie disponibili" field
                    taglie_raw = (it.get("taglie disponibili") or "").strip()
                    all_sizes_str = ", ".join(
                        s.strip().strip("'\"") for s in taglie_raw.split(",") if s.strip().strip("'\"")
                    ) if taglie_raw else ""

                    p_data = {
                        "external_id": ext_id,
                        "supplier_code": prod_code,
                        "name": f"{name} - {color_name} {size}",
                        "description": description,
                        "short_description": name,
                        "category": supplier_tag,
                        "category_group": top_cat or category_group,
                        "subcategory": subcategory or category_group,
                        "brand": supplier_tag,
                        "base_price": price,
                        "currency": "EUR",
                        "min_order_qty": 1,
                        "stock": it_stock,
                        "colors": [{"name": color_name, "hex": "", "image": img_url}],
                        "specifications": {
                            "is_textile": True,
                            "dimensions": dimensions,
                            "material": material,
                            "weight": str(weight) if weight else "",
                            "grammage": gramaj,
                            "size": size,
                            "sizes": all_sizes_str,
                        },
                        "primary_image": img_url,
                        "images": v_images[:10],
                        "printing_options": [],
                    }

                    existing = await db.execute(
                        select(Product).where(
                            Product.integration_id == integration.id,
                            Product.external_id == ext_id,
                        )
                    )
                    product = existing.scalar_one_or_none()
                    if product:
                        for k, v in p_data.items():
                            setattr(product, k, v)
                        product.is_active = True
                        product.last_synced_at = datetime.now(timezone.utc)
                    else:
                        product = Product(
                            integration_id=integration.id,
                            is_active=True,
                            last_synced_at=datetime.now(timezone.utc),
                            **p_data,
                        )
                        db.add(product)

                    await db.flush()

                    search_docs.append({
                        "id": ext_id,
                        "external_id": ext_id,
                        "integration_id": str(integration.id),
                        "supplier_code": prod_code,
                        "name": f"{name} - {color_name} {size}",
                        "description": description,
                        "short_description": name,
                        "category": supplier_tag,
                        "category_group": top_cat or category_group,
                        "subcategory": subcategory or category_group,
                        "brand": supplier_tag,
                        "base_price": price,
                        "currency": "EUR",
                        "stock": it_stock,
                        "colors": [{"name": color_name, "hex": "", "image": img_url}],
                        "primary_image": img_url,
                        "supplier": supplier_tag,
                        "is_active": True,
                    })
                    count += 1

    # Flush DB
    await db.flush()
    progress("process", len(grouped), len(grouped), f"Procesate {count} produse SIPEC")

    # Deactivate old products
    all_result = await db.execute(
        select(Product).where(Product.integration_id == integration.id)
    )
    for p in all_result.scalars().all():
        if p.external_id not in seen_ids:
            p.is_active = False

    await db.commit()

    # Index in Meilisearch
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i: i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse SIPEC",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products synced")
    return count


# ──────────────────────────────────────────────────────────────────────
# BlueCollection (GraphQL)
# ──────────────────────────────────────────────────────────────────────

_BC_GRAPHQL = "https://bluecollection.gifts/graphql"
_BC_IMG_PROXY = "/api/img/?w=400&url="


def _bc_img(url: str) -> str:
    """Wrap a BlueCollection image URL through proxy (CORS blocked)."""
    if not url or "no_selection" in url:
        return ""
    import re
    from urllib.parse import quote
    # Convert Magento cache URLs to originals: /cache/{hash}/ → /
    clean = re.sub(r"/cache/[a-f0-9]+/", "/", url)
    return f"{_BC_IMG_PROXY}{quote(clean, safe='')}"

_BC_COLOR_MAP: dict[str, tuple[str, str]] = {
    "00": ("Silver", "#C0C0C0"), "01": ("White", "#FFFFFF"), "02": ("Black", "#000000"),
    "03": ("Blue", "#0000FF"), "04": ("Red", "#FF0000"), "05": ("Green", "#008000"),
    "06": ("Dark blue", "#00008B"), "07": ("Orange", "#FF8C00"), "08": ("Light blue", "#87CEEB"),
    "09": ("Brown", "#8B4513"), "10": ("Violet", "#8B00FF"), "11": ("Burgundy", "#800020"),
    "12": ("Yellow", "#FFD700"), "13": ("Light green", "#90EE90"), "14": ("Light grey", "#D3D3D3"),
    "15": ("Grey", "#808080"), "16": ("Olive", "#808000"), "17": ("Beige", "#F5F5DC"),
    "18": ("Dark green", "#006400"), "19": ("Transparent", "#FFFFFF"),
    "20": ("Gold", "#FFD700"), "21": ("Rose", "#FF007F"), "22": ("Pink", "#FFC0CB"),
    "23": ("Turquoise", "#40E0D0"), "24": ("Cream", "#FFFDD0"), "25": ("Dark grey", "#A9A9A9"),
}

_BC_PRODUCTS_QUERY = """
{
    products(
        filter: { category_id: { eq: "2" } }
        pageSize: %d
        currentPage: %d
    ) {
        total_count
        items {
            sku
            name
            short_description { html }
            description { html }
            price_range {
                minimum_price { final_price { value currency } }
            }
            image { url }
            small_image { url }
            media_gallery { url }
            categories { id name }
            stock_status
            color
        }
    }
}
"""


async def sync_bluecollection(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from BlueCollection GraphQL API.

    1. Fetch all products via paginated GraphQL queries
    2. Group simple products by base SKU (color variants)
    3. Upsert aggregated products
    4. Index in Meilisearch
    """
    supplier_tag = "BLUECOLLECTION"
    page_size = 50

    progress("fetch", 0, 1, "Descărcare produse BlueCollection...")

    # Fetch all products
    all_items: list[dict] = []
    current_page = 1
    total = 0

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        while True:
            query = _BC_PRODUCTS_QUERY % (page_size, current_page)
            resp = await client.post(
                _BC_GRAPHQL,
                json={"query": query},
                headers={"Store": "en", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            products_data = data.get("data", {}).get("products", {})
            total = products_data.get("total_count", 0)
            items = products_data.get("items", [])

            if not items:
                break

            all_items.extend(items)
            progress(
                "fetch", len(all_items), total,
                f"Descărcate {len(all_items)}/{total} produse",
            )

            if len(all_items) >= total:
                break
            current_page += 1

    progress("fetch", total, total, f"Descărcate {len(all_items)} produse BlueCollection")

    # Group by base SKU (before last dash = color code)
    from collections import defaultdict
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in all_items:
        sku = (item.get("sku") or "").strip()
        if not sku:
            continue
        base_sku = sku.rsplit("-", 1)[0] if "-" in sku else sku
        grouped[base_sku].append(item)

    progress("process", 0, len(grouped), f"Procesare {len(grouped)} produse...")

    count = 0
    search_docs: list[dict] = []
    seen_ids: set[str] = set()

    for idx, (base_sku, variants) in enumerate(grouped.items()):
        if idx % 100 == 0:
            progress("process", idx, len(grouped), f"Procesare {idx}/{len(grouped)}...")

        first = variants[0]
        name = (first.get("name") or "").strip()

        # Skip catalogs and promotional materials
        if name.lower().startswith("katalog ") or name.lower().startswith("catalog "):
            continue
        all_cats = [c.get("name", "") for v in variants for c in (v.get("categories") or [])]
        if "Catalogue" in all_cats and len(all_cats) <= 3:
            continue
        short_desc_html = (first.get("short_description") or {}).get("html", "")
        desc_html = (first.get("description") or {}).get("html", "")
        # Strip HTML tags
        import re
        short_desc = re.sub(r"<[^>]+>", "", short_desc_html).strip()
        description = re.sub(r"<[^>]+>", "", desc_html).strip()
        if not description:
            description = short_desc

        # Categories
        cats = first.get("categories") or []
        cat_names = [c["name"] for c in cats if c.get("name") and c["name"] not in ("All", "Default Category", "Novelties and promotions")]
        category_group = cat_names[0] if cat_names else ""
        subcategory = cat_names[1] if len(cat_names) > 1 else cat_names[0] if cat_names else ""

        # Aggregate variants
        colors = []
        total_stock = 0
        best_price = 999999.0
        all_images: list[str] = []
        primary_image = ""

        for v in variants:
            v_sku = (v.get("sku") or "").strip()
            color_suffix = v_sku.rsplit("-", 1)[1] if "-" in v_sku else ""
            color_entry = _BC_COLOR_MAP.get(color_suffix, (color_suffix, ""))
            color_name, color_hex = color_entry

            # Price
            pr = v.get("price_range", {}).get("minimum_price", {}).get("final_price", {})
            price = pr.get("value", 0) or 0
            if 0 < price < best_price:
                best_price = price

            # Stock
            stock_status = v.get("stock_status", "")
            if stock_status == "IN_STOCK":
                total_stock += 1  # Binary stock (no quantity available)

            # Images — use 'image' (detail/individual photo), not 'small_image' (listing/group)
            raw_img = (v.get("image") or v.get("small_image") or {}).get("url", "")
            img_url = _bc_img(raw_img)
            if img_url and img_url not in all_images:
                all_images.append(img_url)
                if not primary_image:
                    primary_image = img_url

            # Gallery — _bc_img converts cache URLs to originals and proxies them
            for gi in (v.get("media_gallery") or []):
                raw_gu = gi.get("url", "")
                if not raw_gu or "no_selection" in raw_gu:
                    continue
                gu = _bc_img(raw_gu)
                if gu and gu not in all_images:
                    all_images.append(gu)

            color_image = img_url or ""
            if color_name and color_name not in [c["name"] for c in colors]:
                colors.append({
                    "name": color_name,
                    "hex": color_hex,
                    "image": color_image,
                })

        if best_price >= 999999:
            best_price = 0.0

        # Stock: IN_STOCK count > 0 means product available
        # Convert to estimated quantity (we don't have exact qty)
        stock_qty = total_stock * 100 if total_stock > 0 else 0

        external_id = f"BC-{base_sku}"
        seen_ids.add(external_id)

        p_data = {
            "external_id": external_id,
            "supplier_code": base_sku,
            "name": name,
            "description": description,
            "short_description": short_desc or name,
            "category": supplier_tag,
            "category_group": category_group,
            "subcategory": subcategory or category_group,
            "brand": supplier_tag,
            "base_price": best_price,
            "currency": "EUR",
            "min_order_qty": 1,
            "stock": stock_qty,
            "colors": colors,
            "specifications": {},
            "primary_image": primary_image,
            "images": all_images[:20],
            "printing_options": [],
        }

        existing = await db.execute(
            select(Product).where(
                Product.integration_id == integration.id,
                Product.external_id == external_id,
            )
        )
        product = existing.scalar_one_or_none()
        if product:
            for k, v in p_data.items():
                setattr(product, k, v)
            product.is_active = True
            product.last_synced_at = datetime.now(timezone.utc)
        else:
            product = Product(
                integration_id=integration.id,
                is_active=True,
                last_synced_at=datetime.now(timezone.utc),
                **p_data,
            )
            db.add(product)

        await db.flush()

        # Search doc
        color_names_list = [c["name"] for c in colors if c.get("name")]
        search_docs.append({
            "id": external_id,
            "external_id": external_id,
            "integration_id": str(integration.id),
            "supplier_code": base_sku,
            "name": name,
            "description": description,
            "short_description": short_desc or name,
            "category": supplier_tag,
            "category_group": category_group,
            "subcategory": subcategory or category_group,
            "brand": supplier_tag,
            "base_price": best_price,
            "currency": "EUR",
            "stock": stock_qty,
            "colors": colors,
            "primary_image": primary_image,
            "supplier": supplier_tag,
            "is_active": True,
        })
        count += 1

    # Flush DB
    await db.flush()
    progress("process", len(grouped), len(grouped), f"Procesate {count} produse BlueCollection")

    # Deactivate old products
    all_result = await db.execute(
        select(Product).where(Product.integration_id == integration.id)
    )
    for p in all_result.scalars().all():
        if p.external_id not in seen_ids:
            p.is_active = False

    await db.commit()

    # Index in Meilisearch
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i: i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse BlueCollection",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products synced")
    return count


# ──────────────────────────────────────────────────────────────────────
# XD CONNECTS (Xindao)
# ──────────────────────────────────────────────────────────────────────


async def _fetch_json(url: str, timeout: float = HTTP_TIMEOUT) -> list | dict:
    """Fetch JSON from a URL with retries."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def sync_xdconnects(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from XD CONNECTS (Xindao) JSON feeds.

    1. Fetch 3 feeds: products, prices, stock
    2. Build price_map and stock_map by ItemCode
    3. Group products by ModelCode (= supplier_code)
    4. Aggregate colors (with hex, per-color images), sizes, min price
    5. Convert RON prices to EUR
    6. Upsert Product rows + index in Meilisearch
    """
    config = integration.extra_config or {}
    products_url = config.get("products_url", "")
    prices_url = config.get("prices_url", "")
    stock_url = config.get("stock_url", "")
    supplier_tag = "XDCONNECTS"

    if not products_url:
        progress("error", 0, 0, "Lipsește URL-ul feed-ului de produse XD Connects (products_url)")
        raise ValueError("XD Connects products_url is required in extra_config")

    # Get EUR/RON exchange rate from settings
    from app.models.settings import AppSettings
    rate_row = await db.execute(
        select(AppSettings.value).where(AppSettings.key == "exchange_rate_eur_ron")
    )
    eur_ron = float(rate_row.scalar() or _DEFAULT_EUR_RON)

    now = datetime.now(timezone.utc)

    # ── Step 1: Fetch all 3 feeds ────────────────────────────────────
    progress("download", 0, 3, "Se descarcă catalogul de produse XD Connects...")
    try:
        products_list = await _fetch_json(products_url)
    except Exception as e:
        progress("error", 0, 0, f"Eroare descărcare produse XD Connects: {e}")
        raise
    logger.info(f"{supplier_tag}: fetched {len(products_list)} product items")

    progress("download", 1, 3, f"{len(products_list)} articole descărcate. Se descarcă prețurile...")
    price_map: dict[str, float] = {}
    if prices_url:
        try:
            prices_list = await _fetch_json(prices_url)
            for pr in prices_list:
                item_code = pr.get("ItemCode", "")
                price_val = pr.get("ItemPriceNet_Qty1") or pr.get("Price") or 0
                if item_code:
                    try:
                        price_map[item_code] = float(price_val)
                    except (ValueError, TypeError):
                        pass
            logger.info(f"{supplier_tag}: fetched {len(price_map)} price entries")
        except Exception as e:
            logger.warning(f"{supplier_tag}: failed to fetch prices: {e}")

    progress("download", 2, 3, f"{len(price_map)} prețuri descărcate. Se descarcă stocurile...")
    stock_map: dict[str, int] = {}
    if stock_url:
        try:
            stock_list = await _fetch_json(stock_url)
            for st in stock_list:
                item_code = st.get("ItemCode", "")
                current_stock = st.get("CurrentStock") or st.get("Stock") or 0
                if item_code:
                    try:
                        stock_map[item_code] = int(float(str(current_stock)))
                    except (ValueError, TypeError):
                        pass
            logger.info(f"{supplier_tag}: fetched {len(stock_map)} stock entries")
        except Exception as e:
            logger.warning(f"{supplier_tag}: failed to fetch stock: {e}")

    progress("download", 3, 3, "Toate datele XD Connects descărcate")

    # ── Step 2: Group products by ModelCode ──────────────────────────
    from collections import defaultdict
    items_by_model: dict[str, list[dict]] = defaultdict(list)
    for item in products_list:
        model_code = item.get("ModelCode", "")
        if model_code:
            items_by_model[model_code].append(item)

    total_models = len(items_by_model)
    progress("parse", 0, total_models, f"Se procesează {total_models} produse XD Connects...")

    count = 0
    search_docs = []

    for model_code, items in items_by_model.items():
        # Use first item for base product info
        first = items[0]

        product_name = first.get("ItemName", "").split(",")[0].strip() or model_code
        description = first.get("LongDescription", "") or ""
        brand = first.get("Brand", "") or "XD Connects"
        main_category = first.get("MainCategory", "")
        sub_category = first.get("SubCategory", "")

        ext_id = f"XD-{model_code.replace('.', '-')}"

        # Category mapping: MainCategory → subcategory, SubCategory → category_group
        category = supplier_tag
        subcategory = main_category
        category_group = get_group(supplier_tag, main_category) if main_category else sub_category

        # Aggregate colors, sizes, prices, stock, images
        colors = []
        seen_colors: set[str] = set()
        sizes: set[str] = set()
        min_price_ron: float | None = None
        total_stock = 0
        all_images: list[str] = []

        # Print area info (from model level)
        print_position = first.get("PrintPositionDefault", "")
        max_print_area = first.get("MaxPrintAreaDefault", "")
        print_technique = first.get("PrintTechniqueDefault", "")
        printing_options = []

        if print_position or max_print_area or print_technique:
            max_w = 0.0
            max_h = 0.0
            if max_print_area and "x" in str(max_print_area).lower():
                parts = str(max_print_area).lower().replace("mm", "").split("x")
                try:
                    max_w = float(parts[0].strip())
                    max_h = float(parts[1].strip())
                except (ValueError, IndexError):
                    pass

            techniques = []
            if print_technique:
                for tech_name in str(print_technique).split(","):
                    tech_name = tech_name.strip()
                    if tech_name:
                        techniques.append({
                            "name": tech_name,
                            "setup_cost": 0.0,
                            "unit_cost": 0.0,
                        })

            printing_options.append({
                "position": print_position or "Default",
                "max_width_mm": max_w,
                "max_height_mm": max_h,
                "area_raw": max_print_area or "",
                "techniques": techniques,
            })

        for item in items:
            item_code = item.get("ItemCode", "")

            # Color
            color_name = item.get("Color", "") or item.get("PMSColor1", "")
            color_hex = item.get("HexColor1", "")
            color_code = item_code.split(".")[1] if "." in item_code and len(item_code.split(".")) >= 2 else item_code.split("-")[-1] if "-" in item_code else ""

            # Image: use MainImage from feed (static.xdconnects.com)
            item_image = item.get("MainImage", "") or item.get("MainImage Neutral", "")

            if item_image and item_image not in all_images:
                all_images.append(item_image)

            if color_name and color_name not in seen_colors:
                seen_colors.add(color_name)
                hex_val = ""
                if color_hex:
                    hex_val = f"#{color_hex}" if not color_hex.startswith("#") else color_hex
                colors.append({
                    "name": color_name,
                    "hex": hex_val,
                    "code": color_code,
                    "image": item_image or "",
                })

            # Size — detect from ItemCode format: ModelCode.ColorCode.Size
            size = item.get("Size", "")
            if not size and "." in item_code:
                parts = item_code.split(".")
                if len(parts) >= 3:
                    size = parts[-1]  # last part is size for textiles
            if size:
                sizes.add(size)

            # Price (RON) from price_map
            if item_code and item_code in price_map:
                price_ron = price_map[item_code]
                if price_ron > 0 and (min_price_ron is None or price_ron < min_price_ron):
                    min_price_ron = price_ron

            # Also check if price is on the item itself (not normally, but fallback)
            item_price = item.get("ItemPriceNet_Qty1") or item.get("Price")
            if item_price is not None:
                try:
                    item_price_f = float(item_price)
                    if item_price_f > 0 and (min_price_ron is None or item_price_f < min_price_ron):
                        min_price_ron = item_price_f
                except (ValueError, TypeError):
                    pass

            # Stock
            if item_code and item_code in stock_map:
                total_stock += stock_map[item_code]

        # Primary image
        primary_image = ""
        if all_images:
            primary_image = all_images[0]

        # Convert price: RON → EUR
        base_price_ron = min_price_ron or 0.0
        base_price_eur = round(base_price_ron / eur_ron, 2) if base_price_ron > 0 else 0.0

        # Build specifications
        specs: dict = {}
        if sizes:
            specs["is_textile"] = True
            specs["sizes"] = sorted(sizes, key=lambda s: _size_sort_key(s))
            specs["size"] = ", ".join(specs["sizes"])
        if first.get("Material"):
            specs["material"] = first["Material"]
        if first.get("ItemWeightNetGr"):
            specs["weight"] = f"{first['ItemWeightNetGr']}g"
        if first.get("ItemDimensions"):
            specs["dimensions"] = first["ItemDimensions"]

        p_data = {
            "external_id": ext_id,
            "supplier_code": model_code,
            "name": product_name,
            "description": description,
            "short_description": description[:500] if description else "",
            "category": category,
            "category_group": category_group,
            "subcategory": subcategory,
            "brand": brand,
            "images": all_images,
            "primary_image": primary_image,
            "colors": colors,
            "specifications": specs,
            "printing_options": printing_options,
            "min_order_qty": int(first.get("MinimumOrderQuantity", 1) or 1),
            "base_price": base_price_eur,
            "stock": total_stock,
        }

        # Upsert
        result = await db.execute(
            select(Product).where(Product.external_id == ext_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key, value in p_data.items():
                if key != "external_id":
                    setattr(existing, key, value)
            existing.integration_id = integration.id
            existing.last_synced_at = now
            existing.is_active = True
            product_obj = existing
        else:
            product_obj = Product(
                **p_data,
                integration_id=integration.id,
                currency="EUR",
                last_synced_at=now,
                is_active=True,
            )
            db.add(product_obj)

        await db.flush()
        search_docs.append(product_obj.to_search_dict())
        count += 1

        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total_models,
                     f"Salvate {count}/{total_models} produse XD Connects în baza de date")
            logger.info(f"{supplier_tag}: processed {count}/{total_models} products...")

    # Final commit
    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total_models, f"Toate {count} produse XD Connects salvate")

    # ── Step 3: Index in Meilisearch ─────────────────────────────────
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse XD Connects în motor de căutare",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products synced")
    return count


def _size_sort_key(size: str) -> tuple:
    """Sort sizes in logical order: XS, S, M, L, XL, 2XL, 3XL, etc."""
    size_order = {
        "XXS": 0, "XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5,
        "2XL": 6, "XXL": 6, "3XL": 7, "XXXL": 7, "4XL": 8, "5XL": 9, "6XL": 10,
    }
    upper = size.upper().strip()
    if upper in size_order:
        return (0, size_order[upper])
    # Numeric sizes
    try:
        return (1, float(size))
    except ValueError:
        return (2, 0)


# ── Giving Europe color group → hex mapping ─────────────────────────
_GE_COLOR_HEX_MAP: dict[str, str] = {
    "black": "#000000",
    "white": "#FFFFFF",
    "red": "#FF0000",
    "blue": "#0000FF",
    "navy": "#000080",
    "navy blue": "#000080",
    "green": "#008000",
    "yellow": "#FFFF00",
    "orange": "#FF8C00",
    "pink": "#FFC0CB",
    "purple": "#800080",
    "grey": "#808080",
    "gray": "#808080",
    "brown": "#8B4513",
    "beige": "#F5F5DC",
    "silver": "#C0C0C0",
    "gold": "#FFD700",
    "lime": "#00FF00",
    "turquoise": "#40E0D0",
    "cyan": "#00FFFF",
    "magenta": "#FF00FF",
    "burgundy": "#800020",
    "khaki": "#C3B091",
    "olive": "#808000",
    "coral": "#FF7F50",
    "teal": "#008080",
    "mint": "#98FF98",
    "lavender": "#E6E6FA",
    "natural": "#F5F5DC",
    "transparent": "",
}


def _ge_localized(arr: list | None, locale: str = "en-US", fallback: str = "") -> str:
    """Extract a localized value from Giving Europe's [{locale, value}] arrays."""
    if not arr:
        return fallback
    for item in arr:
        if item.get("locale") == locale:
            return item.get("value", fallback)
    # Fallback: try any 'en' locale, then first entry
    for item in arr:
        loc = item.get("locale", "")
        if loc.startswith("en"):
            return item.get("value", fallback)
    if arr:
        return arr[0].get("value", fallback)
    return fallback


def _ge_color_hex_from_group(color_group: list | None) -> str:
    """Derive a hex color from Giving Europe's color_group localized array."""
    if not color_group:
        return ""
    # color_group is [{locale, values: [str, ...]}]
    group_names: list[str] = []
    for entry in color_group:
        loc = entry.get("locale", "")
        if loc == "en-US" or loc.startswith("en"):
            group_names = entry.get("values", [])
            break
    if not group_names and color_group:
        group_names = color_group[0].get("values", [])

    for gn in group_names:
        key = gn.strip().lower()
        if key in _GE_COLOR_HEX_MAP:
            return _GE_COLOR_HEX_MAP[key]
    return ""


async def _ge_fetch_paginated(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    params: dict | None = None,
    limit: int = 100,
) -> list[dict]:
    """Fetch all pages from a Giving Europe paginated endpoint."""
    all_items: list[dict] = []
    offset = 0
    base_params = dict(params or {})
    base_params["limit"] = limit

    while True:
        base_params["offset"] = offset
        resp = await client.get(url, headers=headers, params=base_params)
        if resp.status_code == 429:
            wait_secs = int(resp.headers.get("Retry-After", "60"))
            logger.warning(f"GIVINGEUROPE: rate limited, waiting {wait_secs}s")
            await asyncio.sleep(wait_secs)
            resp = await client.get(url, headers=headers, params=base_params)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        all_items.extend(items)

        total = data.get("total", 0)
        offset += limit
        if offset >= total or not items:
            break

    return all_items


async def sync_givingeurope(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from Giving Europe API.

    1. Fetch categories (code → name mapping)
    2. Fetch all products (paginated)
    3. Fetch all stock levels (paginated)
    4. For each product: aggregate variant colors, sizes, min price
    5. Upsert Product rows + index in Meilisearch
    """
    api_key = integration.api_key or ""
    if not api_key:
        progress("error", 0, 0, "Lipsește API key-ul Giving Europe (api_key)")
        raise ValueError("Giving Europe api_key is required")

    base_url = "https://debtorapi.givingeurope.com"
    supplier_tag = "GIVINGEUROPE"
    headers = {"Authorization": f"Bearer {api_key}"}
    now = datetime.now(timezone.utc)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:

        # ── Step 1: Fetch categories ─────────────────────────────────
        progress("download", 0, 3, "Se descarcă categoriile Giving Europe...")
        try:
            cat_list = await _ge_fetch_paginated(
                client, f"{base_url}/v1/categories", headers,
                params={"locale_code": "en"}, limit=100,
            )
        except Exception as e:
            logger.warning(f"{supplier_tag}: failed to fetch categories: {e}")
            cat_list = []

        cat_map: dict[str, str] = {}          # code → own name
        cat_parent_map: dict[str, str] = {}    # code → lvl1 parent name
        # Marketing categories to skip when picking primary category
        _GE_SKIP_CATS = {"Specials", "Eco collection", "Inspiration"}
        for cat in cat_list:
            code = cat.get("code", "")
            lvl1_name = _ge_localized(cat.get("name"), "en-US", code)
            if code:
                cat_map[code] = lvl1_name
                cat_parent_map[code] = lvl1_name
            for child in cat.get("children", []):
                ch_code = child.get("code", "")
                ch_name = _ge_localized(child.get("name"), "en-US", ch_code)
                if ch_code:
                    cat_map[ch_code] = ch_name
                    cat_parent_map[ch_code] = lvl1_name
                for grandchild in child.get("children", []):
                    gc_code = grandchild.get("code", "")
                    gc_name = _ge_localized(grandchild.get("name"), "en-US", gc_code)
                    if gc_code:
                        cat_map[gc_code] = gc_name
                        cat_parent_map[gc_code] = lvl1_name
        logger.info(f"{supplier_tag}: fetched {len(cat_map)} categories (all levels)")

        # ── Step 2: Fetch products ───────────────────────────────────
        progress("download", 1, 3, f"{len(cat_map)} categorii. Se descarcă produsele Giving Europe...")
        try:
            products_list = await _ge_fetch_paginated(
                client, f"{base_url}/v1/products", headers,
                params={"locale_code": "en"}, limit=100,
            )
        except Exception as e:
            progress("error", 0, 0, f"Eroare descărcare produse Giving Europe: {e}")
            raise
        logger.info(f"{supplier_tag}: fetched {len(products_list)} products")

        # ── Step 3: Fetch stock levels ───────────────────────────────
        progress("download", 2, 3, f"{len(products_list)} produse. Se descarcă stocurile...")
        stock_map: dict[str, dict[str, int]] = {}  # product_code → {variant_code → qty}
        try:
            stock_list = await _ge_fetch_paginated(
                client, f"{base_url}/v1/stock_levels", headers, limit=100,
            )
            for st in stock_list:
                pc = st.get("product_code", "")
                vc = st.get("variant_code", "")
                qty = int(st.get("available_quantity", 0) or 0)
                if pc:
                    stock_map.setdefault(pc, {})[vc] = qty
            logger.info(f"{supplier_tag}: fetched {len(stock_list)} stock entries")
        except Exception as e:
            logger.warning(f"{supplier_tag}: failed to fetch stock: {e}")

    progress("download", 3, 3, "Toate datele Giving Europe descărcate")

    # ── Step 4: Process products ─────────────────────────────────────
    total_products = len(products_list)
    progress("parse", 0, total_products, f"Se procesează {total_products} produse Giving Europe...")

    count = 0
    search_docs = []

    for prod in products_list:
        prod_code = prod.get("code", "")
        if not prod_code:
            continue

        product_name = _ge_localized(prod.get("name"), "en-US", prod_code)
        description = _ge_localized(prod.get("description_long"), "en-US", "")
        brand = _ge_localized(prod.get("brand"), "en-US", "")

        ext_id = f"GE-{prod_code}"

        # Category / subcategory — pick first non-marketing category
        prod_categories = prod.get("categories", [])
        subcategory = ""
        category_group_val = ""
        for pc in prod_categories:
            pc_str = pc if isinstance(pc, str) else ""
            parent_name = cat_parent_map.get(pc_str, "")
            if parent_name and parent_name not in _GE_SKIP_CATS:
                subcategory = parent_name          # lvl1: "Bags & Travel"
                category_group_val = cat_map.get(pc_str, pc_str)  # lvl3: "Backpacks"
                break
        # Fallback: use first category if all are marketing
        if not subcategory and prod_categories:
            first_code = prod_categories[0] if isinstance(prod_categories[0], str) else ""
            subcategory = cat_parent_map.get(first_code, cat_map.get(first_code, first_code))
            category_group_val = cat_map.get(first_code, first_code)

        category = supplier_tag
        category_group = get_group(supplier_tag, subcategory) if subcategory else ""

        # Product-level images
        all_images: list[str] = []
        prod_images = prod.get("images", [])
        if prod_images:
            sorted_imgs = sorted(prod_images, key=lambda x: x.get("prio", 999))
            for img in sorted_imgs:
                url = img.get("value", "")
                if url and url not in all_images:
                    all_images.append(url)

        # Aggregate variants
        variants = prod.get("variants", [])
        colors: list[dict] = []
        seen_colors: set[str] = set()
        sizes: set[str] = set()
        min_price: float | None = None
        total_stock = 0

        # Stock for this product
        prod_stock = stock_map.get(prod_code, {})

        for var in variants:
            var_code = var.get("code", "")

            # Color
            color_info = var.get("color", {}) or {}
            color_name = _ge_localized(color_info.get("names"), "en-US", "")
            color_code = color_info.get("code", "")
            color_hex = _ge_color_hex_from_group(var.get("color_group"))

            # Variant images
            var_images = var.get("images", [])
            var_image = ""
            if var_images:
                sorted_var_imgs = sorted(var_images, key=lambda x: x.get("prio", 999))
                var_image = sorted_var_imgs[0].get("value", "")
                for vi in sorted_var_imgs:
                    vurl = vi.get("value", "")
                    if vurl and vurl not in all_images:
                        all_images.append(vurl)

            if color_name and color_name not in seen_colors:
                seen_colors.add(color_name)
                colors.append({
                    "name": color_name,
                    "hex": color_hex,
                    "code": color_code,
                    "image": var_image or "",
                })

            # Size — code "999" means no size, skip
            size_info = var.get("size", {}) or {}
            size_code = size_info.get("code", "")
            if size_code and size_code != "999":
                size_name = _ge_localized(size_info.get("names"), "en-US", size_code)
                if size_name:
                    sizes.add(size_name)

            # Price from first price tier (lowest min_units)
            price_tiers = var.get("price_tiers", [])
            if price_tiers:
                sorted_tiers = sorted(price_tiers, key=lambda t: t.get("min_units", 0))
                tier_price = sorted_tiers[0].get("unit_net_price", 0)
                try:
                    tier_price_f = float(tier_price)
                    if tier_price_f > 0 and (min_price is None or tier_price_f < min_price):
                        min_price = tier_price_f
                except (ValueError, TypeError):
                    pass

            # Stock
            if var_code and var_code in prod_stock:
                total_stock += prod_stock[var_code]

        # Primary image
        primary_image = all_images[0] if all_images else ""

        base_price_eur = round(min_price, 2) if min_price else 0.0

        # Specifications
        specs: dict = {}
        if sizes:
            specs["is_textile"] = True
            specs["sizes"] = sorted(sizes, key=lambda s: _size_sort_key(s))
            specs["size"] = ", ".join(specs["sizes"])

        p_data = {
            "external_id": ext_id,
            "supplier_code": prod_code,
            "name": product_name,
            "description": description,
            "short_description": description[:500] if description else "",
            "category": category,
            "category_group": category_group_val,
            "subcategory": subcategory,
            "brand": brand,
            "images": all_images,
            "primary_image": primary_image,
            "colors": colors,
            "specifications": specs,
            "printing_options": [],
            "min_order_qty": 1,
            "base_price": base_price_eur,
            "stock": total_stock,
        }

        # Upsert
        result = await db.execute(
            select(Product).where(Product.external_id == ext_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key, value in p_data.items():
                if key != "external_id":
                    setattr(existing, key, value)
            existing.integration_id = integration.id
            existing.last_synced_at = now
            existing.is_active = True
            product_obj = existing
        else:
            product_obj = Product(
                **p_data,
                integration_id=integration.id,
                currency="EUR",
                last_synced_at=now,
                is_active=True,
            )
            db.add(product_obj)

        await db.flush()
        search_docs.append(product_obj.to_search_dict())
        count += 1

        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total_products,
                     f"Salvate {count}/{total_products} produse Giving Europe în baza de date")
            logger.info(f"{supplier_tag}: processed {count}/{total_products} products...")

    # Final commit
    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total_products, f"Toate {count} produse Giving Europe salvate")

    # ── Step 5: Index in Meilisearch ─────────────────────────────────
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse Giving Europe în motor de căutare",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products synced")
    return count


# ──────────────────────────────────────────────────────────────────────
# COLORISSIMO (Reiter Group)
# ──────────────────────────────────────────────────────────────────────

_COLORISSIMO_DEFAULT_URL = (
    "https://cloud.reitergroup.eu/xml-generator/index.php?discount=45&lang=RO"
)


async def sync_colorissimo(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from Colorissimo (Reiter Group) XML feed.

    1. Fetch XML from configured URL (or default)
    2. Parse products, group by <model>
    3. Aggregate colors, images, stock, pricing per model
    4. Upsert into DB
    5. Index in Meilisearch
    """
    import xml.etree.ElementTree as ET
    from collections import defaultdict

    config = integration.extra_config or {}
    xml_url = config.get("xml_url", _COLORISSIMO_DEFAULT_URL)
    supplier_tag = "COLORISSIMO"

    # ── Step 1: Fetch XML ────────────────────────────────────────────
    progress("download", 0, 1, "Descărcare catalog Colorissimo...")

    try:
        xml_data = await _fetch_xml(xml_url)
        progress("download", 1, 1, "Catalog Colorissimo descărcat")
    except Exception as e:
        progress("error", 0, 0, f"Eroare descărcare catalog Colorissimo: {e}")
        raise

    # ── Step 2: Parse XML ────────────────────────────────────────────
    root = ET.fromstring(xml_data)
    xml_products = root.findall(".//product")
    if not xml_products:
        xml_products = root.findall("product")
    logger.info(f"{supplier_tag}: parsed {len(xml_products)} product entries from XML")

    # ── Step 3: Group by model ───────────────────────────────────────
    grouped: dict[str, list] = defaultdict(list)
    for p in xml_products:
        model = (p.findtext("model") or "").strip()
        if not model:
            continue
        grouped[model].append(p)

    progress("process", 0, len(grouped), f"Procesare {len(grouped)} modele Colorissimo...")

    count = 0
    seen_ids: set[str] = set()
    search_docs: list[dict] = []

    for idx, (model_code, variants) in enumerate(grouped.items()):
        if idx % 50 == 0:
            progress("process", idx, len(grouped), f"Procesare {idx}/{len(grouped)} modele...")

        # Use first variant as reference for shared fields
        ref = variants[0]
        name = (ref.findtext("title") or "").strip()
        description = (ref.findtext("description") or "").strip()
        brand = (ref.findtext("brand") or "Colorissimo").strip()
        materials = (ref.findtext("materials") or "").strip()
        dimensions = (ref.findtext("dimensions") or "").strip()
        category_name = (ref.findtext("category_name") or "").strip()
        moq_str = (ref.findtext("moq") or "20").strip()

        try:
            moq = int(moq_str)
        except (ValueError, TypeError):
            moq = 20

        category_group = get_group(supplier_tag, category_name) if category_name else ""

        # Printing options
        printing_options = []
        for pt in ref.findall("printing_options/printing"):
            method = (pt.findtext("printing_method") or "").strip()
            position = (pt.findtext("printing_position") or "").strip()
            max_size = (pt.findtext("max_printing_size") or "").strip()
            max_colors = (pt.findtext("max_printing_colors") or "").strip()
            if method:
                printing_options.append({
                    "method": method,
                    "position": position,
                    "max_size": max_size,
                    "max_colors": max_colors,
                })

        # Aggregate colors, stock, images, pricing across variants
        colors: list[dict] = []
        total_stock = 0
        best_price = 999999.0
        all_images: list[str] = []
        primary_image = ""

        for vi, v in enumerate(variants):
            # Color
            v_color = (v.findtext("color") or "").strip()

            # Stock
            v_stock_str = (v.findtext("stock_qty") or "0").strip()
            if count == 0 and vi == 0:
                logger.info(f"COLORISSIMO DEBUG: model={model_code} color={v_color} stock_str='{v_stock_str}' price_20='{(v.findtext('prices/price_20') or v.findtext('price_20') or 'NONE')}' img='{(v.findtext('image_link') or 'NONE')[:60]}'")

            try:
                v_stock = int(float(v_stock_str.replace(",", "").replace(".", "")))
            except (ValueError, TypeError):
                v_stock = 0
            total_stock += v_stock

            # Price — use price_20 as base (lowest tier); nested under <prices>
            v_price_str = (v.findtext("prices/price_20") or v.findtext("price_20") or "0").strip()
            try:
                v_price = float(v_price_str)
            except (ValueError, TypeError):
                v_price = 0.0
            if v_price > 0 and v_price < best_price:
                best_price = v_price

            # Images — main image_link + additional images (direct URLs)
            v_main_img = (v.findtext("image_link") or "").strip()
            v_images: list[str] = []
            if v_main_img:
                v_images.append(v_main_img)
                if v_main_img not in all_images:
                    all_images.append(v_main_img)

            for img_el in v.findall("images/image"):
                img_url = (img_el.text or "").strip()
                if img_url:
                    if img_url not in v_images:
                        v_images.append(img_url)
                    if img_url not in all_images:
                        all_images.append(img_url)

            color_image = v_images[0] if v_images else ""
            if v_color and v_color not in [c["name"] for c in colors]:
                colors.append({
                    "name": v_color,
                    "hex": _roly_color_hex(v_color),
                    "code": "",
                    "image": color_image,
                    "stock": v_stock,
                })

            if not primary_image and v_images:
                primary_image = v_images[0]

        if best_price >= 999999:
            best_price = 0.0

        # Build external_id (Meilisearch safe — no dots, slashes, or spaces)
        safe_model = model_code.replace(".", "_").replace("/", "-").replace(" ", "_")
        external_id = f"CL-{safe_model}"
        seen_ids.add(external_id)

        p_data = {
            "external_id": external_id,
            "supplier_code": model_code,
            "name": name,
            "description": description,
            "short_description": "",
            "category": supplier_tag,
            "category_group": category_group,
            "subcategory": category_name,
            "brand": brand,
            "base_price": best_price,
            "currency": "EUR",
            "min_order_qty": moq,
            "stock": total_stock,
            "colors": colors,
            "specifications": {
                "dimensions": dimensions,
                "material": materials,
            },
            "primary_image": primary_image,
            "images": all_images[:20],
            "printing_options": printing_options,
        }

        # Upsert
        result = await db.execute(
            select(Product).where(
                Product.integration_id == integration.id,
                Product.external_id == external_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            for k, v in p_data.items():
                setattr(existing, k, v)
            existing.is_active = True
            existing.updated_at = datetime.now(timezone.utc)
        else:
            new_p = Product(
                integration_id=integration.id,
                **p_data,
            )
            db.add(new_p)
        count += 1

        # Search doc
        color_names = [c["name"] for c in colors if c.get("name")]
        search_docs.append({
            "id": external_id,
            "external_id": external_id,
            "integration_id": str(integration.id),
            "supplier_code": model_code,
            "name": name,
            "description": description,
            "short_description": description[:200] if description else name,
            "category": supplier_tag,
            "category_group": category_group,
            "subcategory": category_name,
            "brand": brand,
            "base_price": best_price,
            "currency": "EUR",
            "stock": total_stock,
            "colors": colors,
            "color_names": color_names,
            "color_groups": list(set(c.capitalize() for c in color_names if c)),
            "primary_image": primary_image,
            "images": all_images[:20],
            "min_order_qty": moq,
            "supplier": supplier_tag,
            "is_active": True,
        })

    # Flush DB
    await db.flush()
    progress("process", len(grouped), len(grouped), f"Procesate {count} modele Colorissimo")

    # Deactivate old products not in current feed
    all_result = await db.execute(
        select(Product).where(Product.integration_id == integration.id)
    )
    for p in all_result.scalars().all():
        if p.external_id not in seen_ids:
            p.is_active = False

    await db.commit()

    # ── Step 5: Index in Meilisearch ─────────────────────────────────
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i: i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse Colorissimo",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products synced")
    return count


# ──────────────────────────────────────────────────────────────────────
# ID GROUP (id.dk)
# ──────────────────────────────────────────────────────────────────────

_IDGROUP_FEED_URL = "https://id.dk/Files/Files/Feeds/products-en-gb.json"


def _idgroup_extract_images(item: dict) -> list[str]:
    """
    Extract product image URLs from an ID Group item.
    Checks SalesPackagings[].Images first, then regex-scans the whole
    item JSON string for http://id.dk/Files/Images/products/*.jpg URLs.
    """
    import re
    import json as _json

    images: list[str] = []
    seen: set[str] = set()

    # Check SalesPackagings images
    for sp in item.get("SalesPackagings", []):
        for img in sp.get("Images", []):
            url = ""
            if isinstance(img, str):
                url = img
            elif isinstance(img, dict):
                url = img.get("Url", "") or img.get("url", "") or img.get("Value", "")
            if url and url not in seen:
                seen.add(url)
                images.append(url)

    # Regex scan the full item JSON for product image URLs
    item_str = _json.dumps(item)
    pattern = r'https?://id\.dk/Files/Images/products/[^\s"\'<>]+\.jpg'
    for match in re.findall(pattern, item_str):
        if match not in seen:
            seen.add(match)
            images.append(match)

    return images


def _idgroup_get_field(item: dict, *keys: str, default="") -> str:
    """Safely navigate nested ProductFields dicts for ID Group items."""
    obj = item
    for k in keys:
        if isinstance(obj, dict):
            obj = obj.get(k, default)
        else:
            return default
    return str(obj) if obj is not None else default


async def sync_idgroup(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from ID Group (id.dk) JSON feed.

    1. Fetch large JSON (~156MB)
    2. Group items by Id (model)
    3. For each model: aggregate colors, sizes, stock, images, min price
    4. Upsert Product rows + index in Meilisearch
    """
    config = integration.extra_config or {}
    feed_url = config.get("json_url", config.get("feed_url", integration.api_url or _IDGROUP_FEED_URL))
    supplier_tag = "IDGROUP"
    now = datetime.now(timezone.utc)

    # ── Step 1: Fetch JSON feed ──────────────────────────────────────
    progress("download", 0, 1, "Se descarcă feed-ul ID Group (~156MB)...")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(600.0, connect=30.0),
            follow_redirects=True,
        ) as client:
            response = await client.get(feed_url)
            response.raise_for_status()
            raw_data = response.json()
    except Exception as e:
        progress("error", 0, 0, f"Eroare descărcare feed ID Group: {e}")
        raise
    # Extract products list from response
    if isinstance(raw_data, dict):
        items_list = raw_data.get("Products", [])
    else:
        items_list = raw_data
    progress("download", 1, 1, f"Feed ID Group descărcat ({len(items_list)} items)")

    # ── Step 2: Group items by model Id ──────────────────────────────
    progress("parse", 0, 1, "Se grupează produsele după model...")
    from collections import defaultdict
    models: dict[str, list[dict]] = defaultdict(list)
    for item in items_list:
        model_id = item.get("Id", "")
        if model_id:
            models[model_id].append(item)

    total_models = len(models)
    progress("parse", total_models, total_models,
             f"{total_models} modele unice găsite din {len(raw_data)} items")
    logger.info(f"{supplier_tag}: {total_models} models from {len(raw_data)} items")

    # ── Step 3: Process each model ───────────────────────────────────
    count = 0
    search_docs = []

    for model_id, items in models.items():
        # Find parent item (empty VariantId) or use first item as fallback
        parent = None
        for it in items:
            if not it.get("VariantId"):
                parent = it
                break
        if parent is None:
            parent = items[0]

        # Basic product info from parent
        product_number = parent.get("Number", "")
        ext_id = f"ID-{product_number}" if product_number else f"ID-{model_id}"
        product_name = parent.get("Name", "") or parent.get("Title", "")
        description = parent.get("LongDescription", "") or parent.get("Description", "")

        # ProductFields
        pf = parent.get("ProductFields", {}) or {}
        gender = _idgroup_get_field(pf, "Gender", "Value")
        # Category — raw value is a list [{"Name": "T-SHIRTS", "Value": "10"}]
        cat_field = (pf.get("Category") or {})
        cat_val_raw = cat_field.get("Value", "") if isinstance(cat_field, dict) else ""
        if isinstance(cat_val_raw, list) and cat_val_raw:
            category_val = cat_val_raw[0].get("Name", "") if isinstance(cat_val_raw[0], dict) else str(cat_val_raw[0])
        elif isinstance(cat_val_raw, str):
            category_val = cat_val_raw
        else:
            category_val = ""

        # Gender — same pattern
        gen_field = (pf.get("Gender") or {})
        gen_raw = gen_field.get("Value", "") if isinstance(gen_field, dict) else ""
        if isinstance(gen_raw, list) and gen_raw:
            gender = gen_raw[0].get("Name", "") if isinstance(gen_raw[0], dict) else str(gen_raw[0])
        elif isinstance(gen_raw, str):
            gender = gen_raw
        else:
            gender = ""

        # Fallback category from ProductCategories
        if not category_val:
            prod_cats = parent.get("ProductCategories", {}) or {}
            if prod_cats:
                category_val = next(iter(prod_cats.keys()), "")

        # Materials from ProductMaterials
        materials_dict = parent.get("ProductMaterials", {}) or {}
        materials_parts = []
        for mat_key, mat_vals in materials_dict.items():
            if isinstance(mat_vals, list):
                materials_parts.extend(mat_vals)
            else:
                materials_parts.append(str(mat_vals))
        materials_str = "; ".join(materials_parts) if materials_parts else ""

        # Aggregate variants: colors, sizes, stock, price, images
        colors: list[dict] = []
        seen_colors: set[str] = set()
        sizes: set[str] = set()
        min_price: float | None = None
        total_stock = 0
        all_images: list[str] = []
        seen_image_urls: set[str] = set()

        for it in items:
            it_pf = it.get("ProductFields", {}) or {}

            # Color
            color_name = _idgroup_get_field(it_pf, "ColorVariantText", "Value")
            color_code = _idgroup_get_field(it_pf, "ColorVariantValue", "Value")

            # Size
            size_val = _idgroup_get_field(it_pf, "SizeVariantText", "Value")
            if size_val and size_val != "One size":
                sizes.add(size_val)

            # Price from Prices[0].Price.Price
            prices_list = it.get("Prices", [])
            if prices_list:
                price_obj = prices_list[0]
                if isinstance(price_obj, dict):
                    inner_price = price_obj.get("Price", {})
                    if isinstance(inner_price, dict):
                        try:
                            p_val = float(inner_price.get("Price", 0))
                            if p_val > 0 and (min_price is None or p_val < min_price):
                                min_price = p_val
                        except (ValueError, TypeError):
                            pass
                    elif isinstance(inner_price, (int, float)):
                        try:
                            p_val = float(inner_price)
                            if p_val > 0 and (min_price is None or p_val < min_price):
                                min_price = p_val
                        except (ValueError, TypeError):
                            pass

            # Stock
            stock_level = it.get("StockLevel", 0)
            try:
                item_stock = int(float(stock_level or 0))
            except (ValueError, TypeError):
                item_stock = 0

            # Images
            item_images = _idgroup_extract_images(it)
            for img_url in item_images:
                if img_url not in seen_image_urls:
                    seen_image_urls.add(img_url)
                    all_images.append(img_url)

            # Build color entry (first image for this color)
            if color_name and color_name not in seen_colors:
                seen_colors.add(color_name)
                color_image = item_images[0] if item_images else ""
                colors.append({
                    "name": color_name,
                    "hex": "",
                    "code": color_code,
                    "image": color_image,
                    "stock": item_stock,
                })
                total_stock += item_stock
            elif color_name and color_name in seen_colors:
                # Add stock to existing color entry
                for c in colors:
                    if c["name"] == color_name:
                        c["stock"] = c.get("stock", 0) + item_stock
                        total_stock += item_stock
                        break
            else:
                # No color info, just accumulate stock
                total_stock += item_stock

        # Primary image
        primary_image = all_images[0] if all_images else ""
        base_price_eur = round(min_price, 2) if min_price else 0.0

        # Specifications
        specs: dict = {}
        if sizes:
            specs["is_textile"] = True
            specs["sizes"] = sorted(sizes, key=lambda s: _size_sort_key(s))
            specs["size"] = ", ".join(specs["sizes"])
        if materials_str:
            specs["material"] = materials_str
        if gender:
            specs["gender"] = gender

        # Build short description
        short_desc = description[:500] if description else ""

        p_data = {
            "external_id": ext_id,
            "supplier_code": product_number or model_id,
            "name": product_name,
            "description": description,
            "short_description": short_desc,
            "category": supplier_tag,
            "category_group": category_val,
            "subcategory": category_val,
            "brand": "ID Identity",
            "images": all_images,
            "primary_image": primary_image,
            "colors": colors,
            "specifications": specs,
            "printing_options": [],
            "min_order_qty": 1,
            "base_price": base_price_eur,
            "stock": total_stock,
        }

        # Upsert
        result = await db.execute(
            select(Product).where(Product.external_id == ext_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key, value in p_data.items():
                if key != "external_id":
                    setattr(existing, key, value)
            existing.integration_id = integration.id
            existing.last_synced_at = now
            existing.is_active = True
            product_obj = existing
        else:
            product_obj = Product(
                **p_data,
                integration_id=integration.id,
                currency="EUR",
                last_synced_at=now,
                is_active=True,
            )
            db.add(product_obj)

        await db.flush()
        search_docs.append(product_obj.to_search_dict())
        count += 1

        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total_models,
                     f"Salvate {count}/{total_models} produse ID Group în baza de date")
            logger.info(f"{supplier_tag}: processed {count}/{total_models} products...")

    # Final commit
    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total_models, f"Toate {count} produse ID Group salvate")

    # ── Step 5: Index in Meilisearch ─────────────────────────────────
    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse ID Group în motor de căutare",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products synced")
    return count


# ── Inspirion (LEO API) ──────────────────────────────────────────────

async def sync_inspirion(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from Inspirion LEO REST/JSON API (leoapi.inspirion.eu).

    1. Fetch products, pricelist, stock, categories via paginated v1 endpoints
       (X-Gateway-API-Key header auth)
    2. Build lookup dicts by article_id
    3. Upsert one Product row per top-level SKU with variants as colors
    4. Index in Meilisearch
    """
    config = integration.extra_config or {}
    api_key = config.get("api_key") or integration.api_key or ""
    base_url = (config.get("base_url") or integration.api_url or "https://leoapi.inspirion.eu").rstrip("/")
    language = config.get("language", "ro")
    per_page = int(config.get("per_page", 100))
    supplier_tag = "INSPIRION"

    if not api_key:
        progress("error", 0, 0, "Lipsește cheia API Inspirion")
        raise ValueError("Inspirion api_key not configured")

    auth_headers = {
        "X-Gateway-API-Key": api_key,
        "Accept": "application/json",
    }

    # Inspirion returns prices in RON (language=ro). Convert to EUR using the
    # configured exchange rate so prices live alongside other integrations.
    from app.models.settings import AppSettings
    rate_row = await db.execute(
        select(AppSettings.value).where(AppSettings.key == "exchange_rate_eur_ron")
    )
    eur_ron = float(rate_row.scalar() or _DEFAULT_EUR_RON)
    logger.info(f"{supplier_tag} sync: using EUR/RON rate {eur_ron} for price conversion")

    async def _fetch_paginated(path: str, include_lang: bool = True) -> list[dict]:
        """Fetch all pages from a v1 paginated endpoint."""
        items: list[dict] = []
        page = 1
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            while True:
                params: dict = {"page": page, "perPage": per_page}
                if include_lang:
                    params["language"] = language
                resp = await client.get(f"{base_url}{path}", params=params, headers=auth_headers)
                if resp.status_code == 429:
                    wait_secs = int(resp.headers.get("Retry-After", "30"))
                    logger.warning(f"{supplier_tag}: rate limited, waiting {wait_secs}s")
                    await asyncio.sleep(wait_secs)
                    continue
                resp.raise_for_status()
                body = resp.json()
                data = body.get("data", []) if isinstance(body, dict) else (body or [])
                if not data:
                    break
                items.extend(data)
                last_page = body.get("last_page") if isinstance(body, dict) else None
                if last_page is None or page >= int(last_page):
                    break
                page += 1
        return items

    async def _fetch_plain(path: str, include_lang: bool = True) -> list[dict]:
        """Fetch a non-paginated endpoint returning a JSON array."""
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            params: dict = {}
            if include_lang:
                params["language"] = language
            resp = await client.get(f"{base_url}{path}", params=params, headers=auth_headers)
            resp.raise_for_status()
            body = resp.json()
            if isinstance(body, list):
                return body
            if isinstance(body, dict):
                return body.get("data", []) or []
            return []

    # --- 1. Fetch all data ---
    progress("download", 0, 4, "Descărcare produse Inspirion...")
    try:
        products_data = await _fetch_paginated("/api/v1/products")
        progress("download", 1, 4, f"Descărcate {len(products_data)} produse. Descărcare prețuri...")
        prices_data = await _fetch_paginated("/api/v1/pricelist")
        progress("download", 2, 4, f"Descărcate {len(prices_data)} prețuri. Descărcare stocuri...")
        stock_data = await _fetch_plain("/api/v1/stock", include_lang=False)
        progress("download", 3, 4, f"Descărcate {len(stock_data)} stocuri. Descărcare categorii...")
        categories_data = await _fetch_plain("/api/v1/products/categories")
        progress("download", 4, 4, "Toate datele descărcate, procesare...")
    except Exception as e:
        progress("error", 0, 0, f"Eroare descărcare Inspirion: {e}")
        raise

    # --- 2. Build lookup dicts keyed by article_id ---
    # price_by_article stores (price_eur, "EUR"); source RON prices are divided
    # by eur_ron to align with the rest of the catalog (EUR-based).
    price_by_article: dict[str, tuple[float, str]] = {}
    for entry in prices_data:
        aid = str(entry.get("article_id", "")).strip()
        if not aid:
            continue
        tiers = entry.get("pricelist") or []
        min_price_ron = None
        for tier in tiers:
            try:
                p = float(str(tier.get("price", "0")).replace(",", "."))
            except (ValueError, TypeError):
                continue
            if p <= 0:
                continue
            src_cur = str(tier.get("currency", "RON") or "RON").upper()
            # If the API ever returns EUR natively, re-multiply so compare works
            p_ron = p if src_cur == "RON" else p * eur_ron
            if min_price_ron is None or p_ron < min_price_ron:
                min_price_ron = p_ron
        if min_price_ron is not None:
            price_eur = round(min_price_ron / eur_ron, 4) if eur_ron > 0 else min_price_ron
            price_by_article[aid] = (price_eur, "EUR")

    stock_by_article: dict[str, int] = {}
    for entry in stock_data:
        aid = str(entry.get("article_id", "")).strip()
        if not aid:
            continue
        dach = int(entry.get("stock_dach", 0) or 0)
        if dach > 0:
            stock_by_article[aid] = dach
            continue
        regions = [
            "stock_poland", "stock_hungary", "stock_eastern_europe",
            "stock_netherlands", "stock_france", "stock_italy",
            "stock_czechia", "stock_uk", "stock_scandinavia",
            "stock_spain", "stock_greece",
        ]
        best = 0
        for r in regions:
            try:
                v = int(entry.get(r, 0) or 0)
                if v > best:
                    best = v
            except (ValueError, TypeError):
                pass
        stock_by_article[aid] = best

    cat_by_article: dict[str, tuple[str, str]] = {}
    for entry in categories_data:
        aid = str(entry.get("articleId", "")).strip()
        if not aid:
            continue
        cats = entry.get("categories") or []
        if not cats:
            continue
        first = cats[0]
        parent = str(first.get("parent_category_translation") or first.get("parent_category") or "").strip()
        cat = str(first.get("category_translation") or first.get("category") or "").strip()
        parent_pretty = parent.replace("-", " ").replace("_", " ").strip().title()
        cat_pretty = cat.replace("-", " ").replace("_", " ").strip().title()
        cat_by_article[aid] = (parent_pretty, cat_pretty)

    logger.info(
        f"{supplier_tag}: built lookups - {len(price_by_article)} prices, "
        f"{len(stock_by_article)} stocks, {len(cat_by_article)} categories"
    )

    # --- 3. Process products and upsert ---
    now = datetime.now(timezone.utc)
    count = 0
    search_docs: list[dict] = []

    total_products = len(products_data)
    progress("process", 0, total_products, f"Procesare {total_products} produse Inspirion...")

    for prod in products_data:
        sku = str(prod.get("sku", "")).strip()
        name = str(prod.get("name", "")).strip()
        if not sku or not name:
            continue

        description = str(prod.get("description", "")).strip()
        materials_list = prod.get("materials") or []
        material = ", ".join(m for m in materials_list if m) if isinstance(materials_list, list) else ""
        brand = str(prod.get("brand", "") or "").strip() or "Inspirion"
        variants = prod.get("variants") or []
        branding_methods = prod.get("branding_methods") or []

        product_colors: list[dict] = []
        aggregated_images: list[str] = []
        primary_image = ""
        min_price: float | None = None
        currency = "EUR"
        total_stock = 0
        dimensions = ""
        weight_g = ""

        type_imgs = prod.get("type_images_default") or []
        for img_obj in type_imgs:
            url = str(img_obj.get("image_url", "")).strip()
            if url and img_obj.get("dpi") == 72:
                primary_image = url
                break

        for v in variants:
            aid = str(v.get("article_id", "")).strip()
            colour = str(v.get("colour", "")).strip()

            variant_price = None
            variant_currency = "RON"
            if aid in price_by_article:
                p, c = price_by_article[aid]
                variant_price = p
                variant_currency = c
                if min_price is None or p < min_price:
                    min_price = p
                    currency = c

            variant_stock = stock_by_article.get(aid, 0) if aid else 0
            total_stock += variant_stock

            if colour:
                v_imgs = v.get("images") or []
                v_img = ""
                for vi in v_imgs:
                    url = str(vi.get("image_url", "")).strip()
                    if url:
                        v_img = url
                        break
                # Inspirion colours are often comma-separated ("dark magenta, white")
                # Use the first segment as the primary for hex lookup
                primary_colour = colour.split(",")[0].strip()
                chex = _roly_color_hex(primary_colour)
                color_entry = {
                    "name": colour,
                    "hex": chex,
                    "code": aid,
                    "image": v_img,
                    "stock": variant_stock,
                }
                if variant_price is not None:
                    color_entry["price"] = variant_price
                    color_entry["currency"] = variant_currency
                product_colors.append(color_entry)
                if v_img and v_img not in aggregated_images:
                    aggregated_images.append(v_img)
                if not primary_image and v_img:
                    primary_image = v_img

            size_obj = v.get("size") or {}
            if isinstance(size_obj, dict) and not dimensions:
                l = str(size_obj.get("length", "") or "").strip()
                w = str(size_obj.get("width", "") or "").strip()
                h = str(size_obj.get("height", "") or "").strip()
                unit = str(size_obj.get("length_unit", "") or size_obj.get("unit", "") or "").strip()
                if l:
                    parts = [f"{l}{unit}" if unit else l]
                    if w:
                        parts.append(f"{w}{unit}" if unit else w)
                    if h:
                        parts.append(f"{h}{unit}" if unit else h)
                    dimensions = " x ".join(parts)

            weight_obj = v.get("weight") or {}
            if isinstance(weight_obj, dict) and not weight_g:
                net = str(weight_obj.get("net", "") or "").strip()
                wunit = str(weight_obj.get("unit", "g") or "g").strip()
                if net:
                    weight_g = f"{net}{wunit}"

        # Dedupe by color name, summing stock when collapsing duplicates
        merged: dict[str, dict] = {}
        for c in product_colors:
            key = c["name"].lower()
            if key in merged:
                merged[key]["stock"] = int(merged[key].get("stock", 0)) + int(c.get("stock", 0))
            else:
                merged[key] = c
        product_colors = list(merged.values())
        if not product_colors:
            product_colors = [{"name": "", "hex": "", "code": "", "image": "", "stock": total_stock}]

        parent_cat, sub_cat = "", ""
        for v in variants:
            aid = str(v.get("article_id", "")).strip()
            if aid in cat_by_article:
                parent_cat, sub_cat = cat_by_article[aid]
                break
        category_group = get_group(supplier_tag, sub_cat or parent_cat) if (sub_cat or parent_cat) else ""

        printing_options = []
        for bm in branding_methods:
            if not isinstance(bm, dict):
                continue
            printing_options.append({
                "method": str(bm.get("print_technique_title", "") or "").strip(),
                "position": str(bm.get("position_title", "") or "").strip(),
                "size": str(bm.get("size", "") or "").strip(),
                "max_colors": str(bm.get("max_number_of_colors", "") or "").strip(),
                "code": str(bm.get("print_codes", "") or "").strip(),
            })

        external_id = f"IN-{sku}"

        p_data = {
            "external_id": external_id,
            "supplier_code": sku,
            "name": name,
            "description": description,
            "short_description": description[:250] if description else "",
            "category": supplier_tag,
            "category_group": category_group,
            "subcategory": sub_cat or parent_cat,
            "brand": brand,
            "base_price": min_price or 0.0,
            "currency": currency,
            "min_order_qty": 1,
            "stock": total_stock,
            "colors": product_colors,
            "specifications": {
                "sizes": "",
                "dimensions": dimensions,
                "material": material,
                "weight": weight_g,
            },
            "primary_image": primary_image,
            "images": aggregated_images[:20],
            "printing_options": printing_options,
        }

        stmt = select(Product).where(
            Product.external_id == external_id,
            Product.integration_id == integration.id,
        )
        result = await db.execute(stmt)
        product_obj = result.scalar_one_or_none()

        if product_obj:
            for k, val in p_data.items():
                setattr(product_obj, k, val)
            product_obj.last_synced_at = now
            product_obj.is_active = True
        else:
            product_obj = Product(
                **p_data,
                integration_id=integration.id,
                last_synced_at=now,
                is_active=True,
            )
            db.add(product_obj)

        await db.flush()
        search_docs.append(product_obj.to_search_dict())
        count += 1

        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total_products,
                     f"Salvate {count}/{total_products} produse Inspirion")
            logger.info(f"{supplier_tag} sync: processed {count} products...")

    # Deactivate products not in current sync
    old_stmt = select(Product).where(
        Product.integration_id == integration.id,
        Product.is_active == True,
        Product.last_synced_at < now,
    )
    old_result = await db.execute(old_stmt)
    deactivated = 0
    for old_product in old_result.scalars().all():
        old_product.is_active = False
        deactivated += 1

    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total_products, f"Toate {count} produse Inspirion salvate")

    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse Inspirion",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products, {deactivated} deactivated")
    return count


# ── Valento (Excel + REST webservice) ────────────────────────────────

async def sync_valento(
    integration: Integration,
    db: AsyncSession,
    progress: ProgressCallback = _noop_progress,
) -> int:
    """
    Sync products from Valento.

    1. Read Excel catalog (SKU file) — one row per size×color variant
    2. Fetch live stock from REST webservice (JSON, HTTP Basic auth)
    3. Fetch live prices from REST webservice (base prices)
    4. Upsert one Product row per variant (REFERENCIA)
       grouped by model code (supplier_code) for frontend variant display
    """
    import openpyxl, re as _re
    from pathlib import Path

    config = integration.extra_config or {}
    xlsx_path = config.get("xlsx_path", "")
    ws_user = config.get("ws_user") or ""
    ws_pass = config.get("ws_password") or ""
    base_url = config.get("base_url", "https://www.valento.es/rest")
    supplier_tag = "VALENTO"

    if not xlsx_path:
        progress("error", 0, 0, "Lipsește calea către fișierul Excel Valento")
        raise ValueError("Valento xlsx_path not configured")

    # --- 1. Read Excel ---
    progress("download", 0, 3, "Se încarcă catalogul Excel Valento...")

    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb[wb.sheetnames[0]]
    header_row = next(ws.iter_rows(max_row=1, values_only=True))
    headers = [str(h or "").strip() for h in header_row]

    all_rows: list[dict] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        rd = {h: v for h, v in zip(headers, row)}
        ref = str(rd.get("REFERENCIA", "") or "").strip()
        if ref:
            all_rows.append(rd)
    wb.close()
    logger.info(f"{supplier_tag}: loaded {len(all_rows)} rows from Excel")
    progress("download", 1, 3, f"Încărcate {len(all_rows)} referințe. Descărcare stocuri...")

    # --- 2. Fetch live stock ---
    stock_map: dict[str, int] = {}
    if ws_user and ws_pass:
        try:
            async with httpx.AsyncClient(timeout=90, auth=(ws_user, ws_pass)) as client:
                resp = await client.get(
                    f"{base_url}/stock.php",
                    headers={"Accept": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for entry in data.get("catalog", []):
                        cref = str(entry.get("cref", "")).strip().upper()
                        stk = int(entry.get("stock", 0) or 0)
                        stock_map[cref] = stk
                    logger.info(f"{supplier_tag}: fetched {len(stock_map)} stock entries")
                else:
                    logger.warning(f"{supplier_tag}: stock API returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"{supplier_tag}: failed to fetch stock: {e}")
    progress("download", 2, 3, f"Stocuri: {len(stock_map)}. Descărcare prețuri...")

    # --- 3. Fetch live prices ---
    price_map: dict[str, float] = {}
    if ws_user and ws_pass:
        try:
            async with httpx.AsyncClient(timeout=90, auth=(ws_user, ws_pass)) as client:
                resp = await client.get(
                    f"{base_url}/price.php",
                    headers={"Accept": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for entry in data.get("catalog", []):
                        cref = str(entry.get("cref", "")).strip().upper()
                        # Price key is dynamic: "price_for_0_uds" for base
                        for k, v in entry.items():
                            if k.startswith("price_for_"):
                                try:
                                    price_map[cref] = float(v)
                                except (ValueError, TypeError):
                                    pass
                                break
                    logger.info(f"{supplier_tag}: fetched {len(price_map)} price entries")
                else:
                    logger.warning(f"{supplier_tag}: price API returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"{supplier_tag}: failed to fetch prices: {e}")
    progress("download", 3, 3, "Toate datele descărcate, procesare...")

    # --- 4. Process and upsert ---
    now = datetime.now(timezone.utc)
    count = 0
    search_docs: list[dict] = []
    total = len(all_rows)

    progress("process", 0, total, f"Procesare {total} referințe Valento...")

    for row in all_rows:
        ref = str(row.get("REFERENCIA", "")).strip().upper()
        articulo = str(row.get("ARTICULO", "") or "").strip()
        color = str(row.get("COLOR", "") or "").strip()
        talla = str(row.get("TALLA", "") or "").strip()
        desc = str(row.get("DESCRIPCION", "") or "").strip()
        desc_tech = str(row.get("DESCRIPCION TECNICA", "") or "").strip()
        pvp = row.get("PVP")
        img_url = str(row.get("RUTA IMAGEN", "") or "").strip()
        uds_caja = row.get("UDS CAJA")
        peso_caja = row.get("PESO CAJA")
        medidas_caja = str(row.get("MEDIDAS CAJA", "") or "").strip()
        pais = str(row.get("PAIS ORIGEN", "") or "").strip()

        if not ref or not articulo:
            continue

        # Valento images are HTTP-only; proxy through our /api/img/ endpoint
        # so the browser doesn't block mixed content on HTTPS pages.
        raw_img_url = img_url
        if img_url and img_url.startswith("http://"):
            from urllib.parse import quote as _urlquote
            img_url = f"/api/img/?url={_urlquote(img_url, safe='')}"

        # Extract model code from image path: articles/{MODEL_CODE}/{filename}.jpg
        model_code = ""
        if raw_img_url:
            m = _re.search(r'/articles/([^/]+)/', raw_img_url)
            if m:
                model_code = m.group(1)
        if not model_code:
            # Fallback: strip trailing color+size codes from REFERENCIA
            model_code = ref

        # Name
        name = articulo

        # Price: prefer live API, fallback to Excel PVP
        base_price = price_map.get(ref, 0.0)
        if base_price <= 0 and pvp is not None:
            try:
                base_price = float(str(pvp).replace(",", "."))
            except (ValueError, TypeError):
                base_price = 0.0

        # Stock: prefer live API, fallback to 0
        stock = stock_map.get(ref, 0)

        # Color
        colors = []
        if color:
            colors.append({
                "name": color,
                "hex": _roly_color_hex(color),
                "code": "",
                "image": img_url or "",
                "stock": stock,
            })

        # Specs
        specs: dict = {}
        if talla:
            specs["size"] = str(talla)
        if desc_tech:
            specs["material"] = desc_tech[:200]
        if medidas_caja:
            specs["box_dimensions"] = medidas_caja
        if peso_caja:
            specs["box_weight"] = str(peso_caja)
        if pais:
            specs["country_of_origin"] = pais

        # Category
        category_group = get_group(supplier_tag, articulo) if articulo else ""

        external_id = f"VL-{ref}"

        p_data = {
            "external_id": external_id,
            "supplier_code": model_code,
            "name": name,
            "description": desc_tech or desc,
            "short_description": desc[:200] if desc else name,
            "category": supplier_tag,
            "category_group": category_group,
            "subcategory": articulo,
            "brand": "Valento",
            "base_price": base_price,
            "currency": "EUR",
            "min_order_qty": 1,
            "stock": stock,
            "colors": colors,
            "specifications": specs,
            "primary_image": img_url,
            "images": [img_url] if img_url else [],
            "printing_options": [],
        }

        result = await db.execute(
            select(Product).where(
                Product.external_id == external_id,
                Product.integration_id == integration.id,
            )
        )
        product_obj = result.scalar_one_or_none()

        if product_obj:
            for k, v in p_data.items():
                setattr(product_obj, k, v)
            product_obj.last_synced_at = now
            product_obj.is_active = True
        else:
            product_obj = Product(
                **p_data,
                integration_id=integration.id,
                last_synced_at=now,
                is_active=True,
            )
            db.add(product_obj)

        await db.flush()
        search_docs.append(product_obj.to_search_dict())
        count += 1

        if count % BATCH_SIZE == 0:
            await db.commit()
            progress("save", count, total,
                     f"Salvate {count}/{total} produse Valento")
            logger.info(f"{supplier_tag} sync: processed {count} products...")

    # Deactivate products not in current sync
    old_stmt = select(Product).where(
        Product.integration_id == integration.id,
        Product.is_active == True,
        Product.last_synced_at < now,
    )
    old_result = await db.execute(old_stmt)
    deactivated = 0
    for old_product in old_result.scalars().all():
        old_product.is_active = False
        deactivated += 1

    integration.last_sync_at = now
    integration.products_count = count
    await db.commit()
    progress("save", count, total, f"Toate {count} produse Valento salvate")

    if search_docs:
        try:
            batch_count = 0
            for i in range(0, len(search_docs), BATCH_SIZE):
                batch = search_docs[i : i + BATCH_SIZE]
                meili_index(batch)
                batch_count += len(batch)
                progress(
                    "index", batch_count, len(search_docs),
                    f"Indexate {batch_count}/{len(search_docs)} produse Valento",
                )
            logger.info(f"{supplier_tag}: indexed {len(search_docs)} products in Meilisearch")
        except Exception as e:
            logger.warning(f"{supplier_tag}: Meilisearch indexing failed: {e}")

    logger.info(f"{supplier_tag} sync complete: {count} products, {deactivated} deactivated")
    return count
