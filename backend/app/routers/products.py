import asyncio
import logging
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.product import Product
from app.models.settings import AppSettings
from app.schemas.product import ProductResponse
from app.config import get_settings
from app.services.search_service import (
    SearchFilters,
    search_products as meili_search,
    get_suggestions,
    get_variants_by_codes,
    is_available as meili_available,
    setup_index,
    reindex_all,
    get_index_stats,
)

_log = logging.getLogger("search")

router = APIRouter()
settings = get_settings()

# Cached exchange rate (refreshed every 5 minutes)
_cached_eur_ron: float | None = None
_cached_eur_ron_ts: float = 0
_EUR_RON_TTL = 300  # 5 minutes

# Cached margin percent (refreshed every 5 minutes)
_cached_margin: float | None = None
_cached_margin_ts: float = 0
_MARGIN_TTL = 300  # 5 minutes

# Cached integration margins {integration_id: default_margin} (refreshed every 5 minutes)
_cached_int_margins: dict[str, float] | None = None
_cached_int_margins_ts: float = 0
_INT_MARGINS_TTL = 300  # 5 minutes

# Static mapping: color group name -> hex (for Midocean products that lack hex)
_GROUP_HEX = {
    "Negru": "#000000", "Alb": "#FFFFFF", "Albastru": "#2563EB",
    "Verde": "#16A34A", "Roșu": "#DC2626", "Gri": "#6B7280",
    "Maro": "#92400E", "Portocaliu": "#EA580C", "Roz": "#EC4899",
    "Galben": "#EAB308", "Purple": "#7C3AED", "Argintiu": "#C0C0C0",
    "Auriu": "#D4A418", "Mix RM": "#888888",
}

# Cached color->hex map (refreshed every 30 minutes)
_color_hex_map: dict[str, str] | None = None
_color_hex_map_ts: float = 0
_COLOR_HEX_TTL = 1800  # 30 minutes


async def _get_color_hex_map(db: AsyncSession) -> dict[str, str]:
    """Build a map of color name -> hex from all products in the DB."""
    global _color_hex_map, _color_hex_map_ts
    now = time.time()
    if _color_hex_map is not None and (now - _color_hex_map_ts) < _COLOR_HEX_TTL:
        return _color_hex_map
    result = await db.execute(select(Product.colors).where(Product.is_active == True))
    hex_map: dict[str, str] = {}
    for (colors_json,) in result.all():
        if not colors_json:
            continue
        for c in colors_json:
            if isinstance(c, dict):
                name = c.get("name", "").strip()
                hex_val = c.get("hex", "").strip()
                if name and hex_val and name not in hex_map:
                    hex_map[name] = hex_val
    _color_hex_map = hex_map
    _color_hex_map_ts = now
    _log.info(f"Color hex map built: {len(hex_map)} colors")
    return hex_map


def _fill_missing_hex(colors: list[dict], hex_map: dict[str, str]) -> list[dict]:
    """Fill in missing hex values for colors using hex_map and group fallback."""
    for c in colors:
        if not isinstance(c, dict) or c.get("hex"):
            continue
        name = c.get("name", "")
        # Try exact name match from the global hex map
        if name in hex_map:
            c["hex"] = hex_map[name]
            continue
        # Try case-insensitive match
        name_lower = name.lower()
        for map_name, map_hex in hex_map.items():
            if map_name.lower() == name_lower:
                c["hex"] = map_hex
                break
        if c.get("hex"):
            continue
        # Fallback: use group name
        group = c.get("group", "")
        if group and group in _GROUP_HEX:
            c["hex"] = _GROUP_HEX[group]
    return colors


# Valid clothing size pattern (S, M, L, XL, 2XL, 3XL, etc.)
_SIZE_PATTERN = re.compile(
    r'^(XXS|XS|S|M|L|XL|XXL|2XL|3XL|XXXL|4XL|5XL|'
    r'ONE SIZE|ONE|UNICA|'
    r'\d{1,3}(/\d{1,3})?|'           # numeric sizes like "42", "42/44"
    r'\d{1,3}[.-]\d{1,3})$',         # numeric ranges like "3-4", "3.5"
    re.IGNORECASE,
)


def _extract_midocean_size(external_id: str) -> str:
    """Extract clothing size from Midocean external_id.

    Pattern: MO-{master}-{color_code}-{size} → returns size part.
    Returns empty string for non-clothing (only 3 parts) or invalid sizes.
    """
    if not external_id or not external_id.startswith("MO-"):
        return ""
    parts = external_id.split("-")
    # MO-S00553-CE-L → ["MO", "S00553", "CE", "L"]
    if len(parts) < 4:
        return ""
    candidate = parts[-1]
    if _SIZE_PATTERN.match(candidate):
        return candidate.upper()
    return ""


def _fix_variant_sizes(variants: list[dict]):
    """Fix specifications.size for Midocean variants: replace dimensions with actual size."""
    for v in variants:
        ext_id = v.get("external_id", "")
        actual_size = _extract_midocean_size(ext_id)
        specs = v.get("specifications") or {}
        current_size = specs.get("size", "")

        if actual_size:
            # Move dimensions to a separate field
            if current_size and "X" in current_size.upper() and "CM" in current_size.upper():
                specs["dimensions"] = current_size
            specs["size"] = actual_size
            v["specifications"] = specs
        elif current_size and "X" in current_size.upper() and "CM" in current_size.upper():
            # No clothing size, but specs.size is dimensions — move it
            specs["dimensions"] = current_size
            del specs["size"]
            v["specifications"] = specs


async def _get_integration_margins(db: AsyncSession) -> dict[str, float]:
    """Load all integration default_margin values, cached 5 min."""
    global _cached_int_margins, _cached_int_margins_ts
    now = time.time()
    if _cached_int_margins is not None and (now - _cached_int_margins_ts) < _INT_MARGINS_TTL:
        return _cached_int_margins
    from app.models.integration import Integration
    result = await db.execute(select(Integration.id, Integration.default_margin))
    _cached_int_margins = {row[0]: (row[1] or 0.0) for row in result.all()}
    _cached_int_margins_ts = now
    return _cached_int_margins


def invalidate_margin_caches():
    """Invalidate all margin caches so next request re-reads from DB."""
    global _cached_int_margins, _cached_int_margins_ts
    global _cached_margin, _cached_margin_ts
    _cached_int_margins = None
    _cached_int_margins_ts = 0
    _cached_margin = None
    _cached_margin_ts = 0


async def _get_margin(db: AsyncSession) -> float:
    global _cached_margin, _cached_margin_ts
    now = time.time()
    if _cached_margin is not None and (now - _cached_margin_ts) < _MARGIN_TTL:
        return _cached_margin
    rate_row = await db.execute(
        select(AppSettings.value).where(AppSettings.key == "margin_percent")
    )
    val = rate_row.scalar()
    _cached_margin = float(val) if val is not None else settings.default_margin_percent
    _cached_margin_ts = now
    return _cached_margin


async def _get_eur_ron(db: AsyncSession) -> float:
    global _cached_eur_ron, _cached_eur_ron_ts
    now = time.time()
    if _cached_eur_ron is not None and (now - _cached_eur_ron_ts) < _EUR_RON_TTL:
        return _cached_eur_ron
    rate_row = await db.execute(
        select(AppSettings.value).where(AppSettings.key == "exchange_rate_eur_ron")
    )
    _cached_eur_ron = float(rate_row.scalar() or 4.97)
    _cached_eur_ron_ts = now
    return _cached_eur_ron


@router.get("/search")
async def search_products(
    q: str = Query("", description="Search query text"),
    category: str = Query("", description="Filter by category name"),
    subcategory: str = Query("", description="Filter by subcategory name"),
    category_group: str = Query("", description="Filter by category group"),
    unified_category: str = Query("", description="Filter by unified taxonomy category"),
    unified_subcategory: str = Query("", description="Filter by unified taxonomy subcategory"),
    min_price: float | None = Query(None, description="Min base price EUR"),
    max_price: float | None = Query(None, description="Max base price EUR"),
    color: str = Query("", description="Filter by color name"),
    color_group: str = Query("", description="Filter by standard color group (Romanian)"),
    integration_id: str = Query("", description="Filter by supplier integration ID"),
    in_stock: bool = Query(False, description="Only show products in stock"),
    sort: str = Query("", description="Sort: price_asc, price_desc, name_asc, newest, stock"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    group_variants: bool = Query(True, description="Group color/size variants by model"),
    db: AsyncSession = Depends(get_db),
):
    """
    Search products. Uses Meilisearch if available, falls back to SQLite.
    """
    t0 = time.time()

    # Load margin + exchange rate + supplier margins from DB (cached 5 min)
    global_margin = await _get_margin(db)
    eur_ron = await _get_eur_ron(db)
    int_margins = await _get_integration_margins(db)

    # Try Meilisearch first (cached availability check)
    if meili_available():
        filters = SearchFilters(
            query=q,
            category=category,
            subcategory=subcategory,
            category_group=category_group,
            unified_category=unified_category,
            unified_subcategory=unified_subcategory,
            min_price=min_price,
            max_price=max_price,
            color=color,
            color_group=color_group,
            integration_id=integration_id,
            in_stock=in_stock,
            sort_by=sort,
            page=page,
            limit=limit,
            group_variants=group_variants,
        )
        # Run sync meilisearch call off the event loop
        result = await asyncio.to_thread(meili_search, filters)

        # Aggregate variant colors/stock from Meilisearch (~3ms extra)
        # Pass integration_ids alongside supplier_codes to prevent cross-supplier mixing
        codes = [p.get("supplier_code") for p in result.results if p.get("supplier_code")]
        iids = [p.get("integration_id", "") for p in result.results if p.get("supplier_code")]
        variant_agg = await asyncio.to_thread(get_variants_by_codes, codes, iids) if codes else {}

        for product in result.results:
            base = product.get("base_price", 0)
            iid = product.get("integration_id", "")
            supplier_margin = int_margins.get(iid, 0)
            # Supplier margin goes INTO the purchase price (what we actually pay)
            purchase_price = round(base * (1 + supplier_margin / 100), 2)
            # Global margin applies on top of purchase price (what we sell for)
            sell_price = round(purchase_price * (1 + global_margin / 100), 2)
            product["base_price"] = purchase_price  # show real acquisition cost
            product["sell_price"] = sell_price
            product["sell_price_ron"] = round(sell_price * eur_ron, 2)
            product["supplier_margin"] = supplier_margin
            product["effective_margin"] = global_margin
            product["raw_base_price"] = base  # original supplier API price
            # Add fields the frontend expects
            product["image_url"] = product.get("primary_image") or ""
            colors = product.get("colors") or []
            if isinstance(colors, str):
                colors = [{"name": c.strip(), "hex": "", "image": ""} for c in colors.split(",") if c.strip()]
            product["colors"] = colors
            product["sku"] = product.get("external_id") or ""
            product["min_quantity"] = product.get("min_order_qty", 1)
            product["material"] = (product.get("specifications") or {}).get("material", "") if isinstance(product.get("specifications"), dict) else ""
            product["size"] = (product.get("specifications") or {}).get("size", "") if isinstance(product.get("specifications"), dict) else ""
            # Variant aggregates
            agg = variant_agg.get(product.get("supplier_code", ""), {})
            product["variant_colors"] = agg.get("colors", colors)
            product["color_names"] = [c.get("name", "") for c in product["variant_colors"] if isinstance(c, dict)]
            product["total_stock"] = agg.get("total_stock", product.get("stock", 0))
            product["variant_count"] = agg.get("count", 1)
            # Price range across variants (apply same margin logic)
            agg_min = agg.get("min_price", 0)
            agg_max = agg.get("max_price", 0)
            if agg_min > 0 and agg_max > 0 and agg_min != agg_max:
                min_purchase = round(agg_min * (1 + supplier_margin / 100), 2)
                max_purchase = round(agg_max * (1 + supplier_margin / 100), 2)
                product["min_sell_price"] = round(min_purchase * (1 + global_margin / 100), 2)
                product["max_sell_price"] = round(max_purchase * (1 + global_margin / 100), 2)
            else:
                product["min_sell_price"] = None
                product["max_sell_price"] = None
        # Build color hex map and fill missing hex values in variant_colors
        color_hex_map = await _get_color_hex_map(db)
        for product in result.results:
            _fill_missing_hex(product.get("variant_colors", []), color_hex_map)
            _fill_missing_hex(product.get("colors", []), color_hex_map)

        return {
            "results": result.results,
            "total": result.total,
            "page": result.page,
            "total_pages": result.total_pages,
            "query": result.query,
            "processing_time_ms": result.processing_time_ms,
            "facets": result.facets,
            "color_hex_map": color_hex_map,
        }

    # SQLite fallback
    start = time.time()

    query = select(Product).where(Product.is_active == True)

    if q:
        query = query.where(
            Product.name.ilike(f"%{q}%") | Product.description.ilike(f"%{q}%")
        )
    if category:
        query = query.where(Product.category == category)
    if subcategory:
        query = query.where(Product.subcategory == subcategory)
    if min_price is not None:
        query = query.where(Product.base_price >= min_price)
    if max_price is not None:
        query = query.where(Product.base_price <= max_price)
    if in_stock:
        query = query.where(Product.stock > 0)
    if integration_id:
        query = query.where(Product.integration_id == integration_id)

    # Group variants: pick one representative per supplier_code
    if group_variants:
        from sqlalchemy import distinct
        # Subquery to get one ID per supplier_code
        sub = (
            select(func.min(Product.id).label("min_id"))
            .where(Product.is_active == True)
        )
        if q:
            sub = sub.where(
                Product.name.ilike(f"%{q}%") | Product.description.ilike(f"%{q}%")
            )
        if category:
            sub = sub.where(Product.category == category)
        if subcategory:
            sub = sub.where(Product.subcategory == subcategory)
        if min_price is not None:
            sub = sub.where(Product.base_price >= min_price)
        if max_price is not None:
            sub = sub.where(Product.base_price <= max_price)
        if in_stock:
            sub = sub.where(Product.stock > 0)
        if integration_id:
            sub = sub.where(Product.integration_id == integration_id)
        sub = sub.where(Product.supplier_code != "").group_by(Product.supplier_code)
        sub_scalar = sub.subquery()
        query = query.where(Product.id.in_(select(sub_scalar.c.min_id)))

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort
    if sort == "price_asc":
        query = query.order_by(Product.base_price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.base_price.desc())
    elif sort == "name_asc":
        query = query.order_by(Product.name.asc())
    elif sort == "newest":
        query = query.order_by(Product.created_at.desc())
    else:
        query = query.order_by(Product.name.asc())

    # Paginate
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    products = result.scalars().all()

    total_pages = max(1, (total + limit - 1) // limit)
    elapsed = round((time.time() - start) * 1000, 1)

    # Build facets from DB
    cat_result = await db.execute(
        select(Product.category, func.count(Product.id))
        .where(Product.is_active == True, Product.category != "")
        .group_by(Product.category)
        .order_by(func.count(Product.id).desc())
        .limit(30)
    )
    category_facets = {row[0]: row[1] for row in cat_result.all()}

    brand_result = await db.execute(
        select(Product.brand, func.count(Product.id))
        .where(Product.is_active == True, Product.brand != "")
        .group_by(Product.brand)
        .order_by(func.count(Product.id).desc())
        .limit(20)
    )
    brand_facets = {row[0]: row[1] for row in brand_result.all()}

    # Aggregate variant data (colors, total stock) per (supplier_code, integration_id)
    variant_agg: dict = {}
    if group_variants and products:
        # Build {supplier_code: integration_id} mapping from representative products
        code_to_iid: dict[str, str] = {}
        for p in products:
            if p.supplier_code:
                code_to_iid[p.supplier_code] = p.integration_id or ""
        codes = list(code_to_iid.keys())
        if codes:
            var_result = await db.execute(
                select(Product)
                .where(Product.supplier_code.in_(codes), Product.is_active == True)
            )
            for v in var_result.scalars().all():
                code = v.supplier_code
                # Only aggregate variants from the same supplier
                if code_to_iid.get(code) and v.integration_id != code_to_iid[code]:
                    continue
                if code not in variant_agg:
                    variant_agg[code] = {"colors": [], "seen_colors": set(), "total_stock": 0, "count": 0}
                variant_agg[code]["total_stock"] += v.stock
                variant_agg[code]["count"] += 1
                for c in (v.colors or []):
                    cname = c.get("name", "")
                    if cname and cname not in variant_agg[code]["seen_colors"]:
                        variant_agg[code]["seen_colors"].add(cname)
                        variant_agg[code]["colors"].append(c)

    results = []
    for p in products:
        d = p.to_search_dict()
        supplier_margin = int_margins.get(p.integration_id or "", 0)
        # Supplier margin goes INTO the purchase price
        purchase_price = round(p.base_price * (1 + supplier_margin / 100), 2)
        # Global margin applies on top of purchase price
        sell = round(purchase_price * (1 + global_margin / 100), 2)
        d["raw_base_price"] = p.base_price
        d["base_price"] = purchase_price  # show real acquisition cost
        d["sell_price"] = sell
        d["sell_price_ron"] = round(sell * eur_ron, 2)
        d["supplier_margin"] = supplier_margin
        d["effective_margin"] = global_margin
        # Frontend expects these fields
        d["image_url"] = p.primary_image or ""
        d["color_names"] = [c.get("name", "") for c in (p.colors or [])]
        d["material"] = (p.specifications or {}).get("material", "")
        d["size"] = (p.specifications or {}).get("size", "")
        d["print_area"] = ""
        d["sku"] = p.external_id or ""
        d["supplier_code"] = p.supplier_code or ""
        d["min_quantity"] = p.min_order_qty
        # Variant aggregates
        agg = variant_agg.get(p.supplier_code, {})
        d["variant_colors"] = agg.get("colors", p.colors or [])
        d["total_stock"] = agg.get("total_stock", p.stock)
        d["variant_count"] = agg.get("count", 1)
        results.append(d)

    color_hex_map = await _get_color_hex_map(db)
    for d in results:
        _fill_missing_hex(d.get("variant_colors", []), color_hex_map)
        _fill_missing_hex(d.get("colors", []), color_hex_map)

    return {
        "results": results,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "query": q,
        "processing_time_ms": elapsed,
        "exchange_rate_eur_ron": eur_ron,
        "facets": {
            "category": category_facets,
            "brand": brand_facets,
        },
        "color_hex_map": color_hex_map,
    }


@router.get("/suggest")
async def suggest(
    q: str = Query("", min_length=2, description="Partial query for autocomplete"),
    limit: int = Query(8, ge=1, le=20),
):
    """Fast autocomplete suggestions for the search bar."""
    if not meili_available():
        return {"suggestions": []}

    suggestions = await asyncio.to_thread(get_suggestions, q, limit)
    return {"suggestions": suggestions}


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    """Get all distinct product categories with counts."""
    result = await db.execute(
        select(Product.category, func.count(Product.id).label("count"))
        .where(Product.is_active == True, Product.category != "")
        .group_by(Product.category)
        .order_by(func.count(Product.id).desc())
    )
    return [{"name": row[0], "count": row[1]} for row in result.all()]


@router.get("/category-tree")
async def get_category_tree(db: AsyncSession = Depends(get_db)):
    """
    Returns 3-level category tree:
    { supplier: { group: { subcategory: count, ... }, ... }, ... }
    Uses category_group column from DB (populated during sync).
    Falls back to Python mapping for products without category_group.
    """
    from app.services.category_groups import get_group

    result = await db.execute(
        select(
            Product.category,
            Product.category_group,
            Product.subcategory,
            func.count(Product.id).label("cnt"),
        )
        .where(
            Product.is_active == True,
            Product.category != "",
            Product.subcategory != "",
        )
        .group_by(Product.category, Product.category_group, Product.subcategory)
        .order_by(Product.category, func.count(Product.id).desc())
    )

    # Build 3-level tree: supplier → group → subcategory → count
    tree: dict[str, dict[str, dict[str, int]]] = {}
    for supplier, cat_group, sub, cnt in result.all():
        if supplier not in tree:
            tree[supplier] = {}
        # Use DB category_group if available, otherwise fall back to mapping
        group = cat_group if cat_group else get_group(supplier, sub)
        if group not in tree[supplier]:
            tree[supplier][group] = {}
        tree[supplier][group][sub] = cnt

    return tree


@router.get("/unified-tree")
async def get_unified_tree(db: AsyncSession = Depends(get_db)):
    """
    Returns 2-level unified taxonomy tree with product counts:
    { unified_category: { unified_subcategory: count, ... }, ... }
    """
    result = await db.execute(
        select(
            Product.unified_category,
            Product.unified_subcategory,
            func.count(Product.id).label("cnt"),
        )
        .where(
            Product.is_active == True,
            Product.unified_category != "",
            Product.unified_category.isnot(None),
        )
        .group_by(Product.unified_category, Product.unified_subcategory)
        .order_by(Product.unified_category, func.count(Product.id).desc())
    )

    tree: dict[str, dict[str, int]] = {}
    for cat, sub, cnt in result.all():
        if not cat:
            continue
        tree.setdefault(cat, {})[sub or "Altele"] = cnt
    return tree


@router.get("/stats")
async def search_stats():
    """Get Meilisearch index statistics."""
    if not meili_available():
        return {"available": False}
    stats = await asyncio.to_thread(get_index_stats)
    return {"available": True, **stats}


@router.post("/reindex")
async def trigger_reindex(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a full reindex of all products into Meilisearch."""
    if not meili_available():
        raise HTTPException(status_code=503, detail="Meilisearch is not available")

    background_tasks.add_task(_do_reindex)
    return {"detail": "Reindex started in background"}


async def _do_reindex():
    from app.database import async_session
    setup_index()
    async with async_session() as db:
        await reindex_all(db)


@router.post("/setup-index")
async def trigger_setup_index():
    """Configure Meilisearch index settings (run once on deploy)."""
    if not meili_available():
        raise HTTPException(status_code=503, detail="Meilisearch is not available")
    result = setup_index()
    return result


@router.get("/variants/{supplier_code}")
async def get_product_variants(
    supplier_code: str,
    integration_id: str = Query("", description="Filter variants by supplier integration ID"),
    db: AsyncSession = Depends(get_db),
):
    """Get all color/size variants of a product model by supplier_code."""
    if not supplier_code:
        raise HTTPException(status_code=400, detail="supplier_code is required")

    global_margin = await _get_margin(db)
    eur_ron = await _get_eur_ron(db)
    int_margins = await _get_integration_margins(db)

    query = (
        select(Product)
        .where(Product.supplier_code == supplier_code, Product.is_active == True)
        .order_by(Product.external_id.asc())
    )
    if integration_id:
        query = query.where(Product.integration_id == integration_id)
    result = await db.execute(query)
    products = result.scalars().all()

    if not products:
        raise HTTPException(status_code=404, detail="No variants found")

    variants = []
    total_stock = 0
    for p in products:
        supplier_margin = int_margins.get(p.integration_id or "", 0)
        purchase_price = round(p.base_price * (1 + supplier_margin / 100), 2)
        sell = round(purchase_price * (1 + global_margin / 100), 2)
        total_stock += p.stock

        colors_list = p.colors or []
        specs = p.specifications or {}
        sizes_raw = specs.get("sizes", "")
        if isinstance(sizes_raw, list):
            size_list = [s.strip() for s in sizes_raw if s and str(s).strip()]
        elif isinstance(sizes_raw, str) and sizes_raw:
            size_list = [s.strip() for s in sizes_raw.split(",") if s.strip()]
        else:
            size_list = []

        # If a single product row has multiple colors or sizes,
        # explode into per-color-per-size virtual variants
        if len(colors_list) > 1 or (len(colors_list) == 1 and len(size_list) > 1):
            per_variant_stock = max(1, p.stock // max(len(colors_list) * max(len(size_list), 1), 1))

            # Pre-assign images to colors when colors lack own image.
            # Skip generic/main images (often first 1-3), distribute the
            # remaining per-color images round-robin across the colors.
            import re as _re
            all_imgs = p.images or []
            _colors_without_img = [c for c in colors_list if not (c.get("image") if isinstance(c, dict) else False)]
            if _colors_without_img and len(all_imgs) > 1:
                # Try to identify per-color images (Makito pattern: ref-XXX-P.jpg)
                ref_prefix = (p.supplier_code or p.external_id or "").split("-")[0] if p.supplier_code else ""
                per_color_imgs = []
                generic_imgs = []
                for img in all_imgs:
                    fname = img.rsplit("/", 1)[-1] if "/" in img else img
                    # Makito: {ref}-{colorcode}-P.jpg  or  UTT: {code}-{num}.jpg
                    if ref_prefix and _re.search(rf'{_re.escape(ref_prefix)}-\d{{2,3}}-[A-Z]', fname):
                        per_color_imgs.append(img)
                    elif _re.search(r'-\d{1,3}\.jpg$', fname) and not _re.search(r'-0{1,3}[.-]', fname):
                        per_color_imgs.append(img)
                    else:
                        generic_imgs.append(img)
                # If we found per-color images, assign them
                assign_imgs = per_color_imgs if per_color_imgs else all_imgs[1:]  # skip first (usually generic)
                if assign_imgs:
                    for ci, c in enumerate(_colors_without_img):
                        c["image"] = assign_imgs[ci % len(assign_imgs)]

            for color_info in (colors_list or [{"name": "", "hex": "", "image": ""}]):
                # Use per-color stock if available, otherwise divide equally
                c_stock = color_info.get("stock", per_variant_stock) if isinstance(color_info, dict) else per_variant_stock
                # Use color-specific image as primary if available
                c_img = color_info.get("image", "") if isinstance(color_info, dict) else ""
                v_primary = c_img or p.primary_image or ""
                # Try to filter images belonging to this color variant
                _color_id = ""
                if c_img:
                    _m = _re.search(r'(\d{5}-\d{2})', c_img)
                    if _m:
                        _color_id = _m.group(1)
                if _color_id:
                    v_images = [i for i in (p.images or []) if _color_id in i]
                    if c_img and c_img not in v_images:
                        v_images.insert(0, c_img)
                elif c_img:
                    v_images = [c_img] + [i for i in all_imgs if i != c_img]
                else:
                    v_images = list(all_imgs)
                if size_list:
                    for sz in size_list:
                        v_specs = {**specs, "size": sz}
                        v_specs.pop("sizes", None)
                        variants.append({
                            "id": p.id,
                            "external_id": p.external_id or "",
                            "supplier_code": p.supplier_code or "",
                            "name": p.name,
                            "description": p.description,
                            "short_description": p.short_description or "",
                            "category": p.category,
                            "subcategory": p.subcategory or "",
                            "brand": p.brand or "",
                            "base_price": purchase_price,
                            "sell_price": sell,
                            "sell_price_ron": round(sell * eur_ron, 2),
                            "currency": p.currency,
                            "primary_image": v_primary,
                            "images": v_images,
                            "color": color_info,
                            "colors": colors_list,
                            "specifications": v_specs,
                            "printing_options": p.printing_options or [],
                            "stock": c_stock,
                            "min_order_qty": p.min_order_qty,
                        })
                else:
                    variants.append({
                        "id": p.id,
                        "external_id": p.external_id or "",
                        "supplier_code": p.supplier_code or "",
                        "name": p.name,
                        "description": p.description,
                        "short_description": p.short_description or "",
                        "category": p.category,
                        "subcategory": p.subcategory or "",
                        "brand": p.brand or "",
                        "base_price": purchase_price,
                        "sell_price": sell,
                        "sell_price_ron": round(sell * eur_ron, 2),
                        "currency": p.currency,
                        "primary_image": v_primary,
                        "images": v_images,
                        "color": color_info,
                        "colors": colors_list,
                        "specifications": specs,
                        "printing_options": p.printing_options or [],
                        "stock": c_stock,
                        "min_order_qty": p.min_order_qty,
                    })
        else:
            color_info = colors_list[0] if colors_list else {"name": "", "hex": "", "image": ""}
            variants.append({
                "id": p.id,
                "external_id": p.external_id or "",
                "supplier_code": p.supplier_code or "",
                "name": p.name,
                "description": p.description,
                "short_description": p.short_description or "",
                "category": p.category,
                "subcategory": p.subcategory or "",
                "brand": p.brand or "",
                "base_price": purchase_price,
                "sell_price": sell,
                "sell_price_ron": round(sell * eur_ron, 2),
                "currency": p.currency,
                "primary_image": p.primary_image or "",
                "images": p.images or [],
                "color": color_info,
                "colors": colors_list,
                "specifications": specs,
                "printing_options": p.printing_options or [],
                "stock": p.stock,
                "min_order_qty": p.min_order_qty,
            })

    # Fill missing hex values in variant colors
    color_hex_map = await _get_color_hex_map(db)
    for v in variants:
        _fill_missing_hex(v.get("colors", []), color_hex_map)
        if isinstance(v.get("color"), dict) and not v["color"].get("hex"):
            group = v["color"].get("group", "")
            name = v["color"].get("name", "")
            v["color"]["hex"] = color_hex_map.get(name, _GROUP_HEX.get(group, ""))

    # Fix Midocean sizes: replace dimensions with actual clothing sizes
    _fix_variant_sizes(variants)

    return {
        "supplier_code": supplier_code,
        "name": products[0].name,
        "category": products[0].category,
        "brand": products[0].brand or "",
        "total_stock": total_stock,
        "variant_count": len(variants),
        "variants": variants,
    }


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str, db: AsyncSession = Depends(get_db)):
    """Get full product details by ID."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
