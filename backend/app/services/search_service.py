"""
Meilisearch integration for 200k+ product search.

Features:
- Faceted search with category, price, color, integration filters
- Autocomplete suggestions
- Batch indexing with chunked uploads
- Full reindex from database
"""
import logging
import math
import time
from dataclasses import dataclass, field

import meilisearch
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.product import Product

logger = logging.getLogger(__name__)
settings = get_settings()

# Cached availability flag — avoids HTTP health check on every request
_meili_available: bool | None = None
_meili_available_ts: float = 0
_AVAILABILITY_TTL = 30  # seconds

INDEX_NAME = "products"
BATCH_SIZE = 5000  # docs per batch for indexing

# Price range buckets for faceting
PRICE_RANGES = [
    (0, 5),
    (5, 10),
    (10, 25),
    (25, 50),
    (50, 100),
    (100, 250),
    (250, 500),
    (500, float("inf")),
]

# ---------------------------------------------------------------------------
# Romanian ↔ English synonym groups for multilingual search
# Meilisearch normalizes diacritics (ă→a, ș→s, ț→t) so we only need
# the non-diacritic Romanian forms.
# ---------------------------------------------------------------------------
_SYNONYM_GROUPS: list[list[str]] = [
    # ── Bags & carrying ──
    ["rucsac", "backpack", "rucksack"],
    ["geanta", "bag"],
    ["sacosa", "tote", "shopping bag", "tote bag"],
    ["borseta", "waist bag", "fanny pack", "bum bag"],
    ["portofel", "wallet"],
    ["husa", "case", "cover", "pouch"],
    ["gentuta", "clutch", "small bag"],
    ["valiza", "trolley", "suitcase", "luggage"],

    # ── Drinkware ──
    ["cana", "mug"],
    ["pahar", "glass", "tumbler"],
    ["sticla", "bottle", "water bottle", "sport bottle"],
    ["termos", "thermos", "flask", "thermo", "thermal bottle"],

    # ── Writing instruments ──
    ["pix", "pen", "ballpoint", "ball pen"],
    ["stilou", "fountain pen"],
    ["creion", "pencil"],
    ["penar", "pencil case"],
    ["set de scris", "writing set"],

    # ── Stationery & office ──
    ["caiet", "notebook"],
    ["agenda", "planner", "diary", "organizer"],
    ["notepad", "bloc notes", "blocnotes"],
    ["mapa", "folder", "portfolio", "document folder"],
    ["clipboard", "clipboard"],
    ["rigla", "ruler"],
    ["calculator", "calculator"],
    ["suport pixuri", "pen holder", "desk organizer"],

    # ── Clothing tops ──
    ["tricou", "t-shirt", "tee"],
    ["polo", "polo shirt", "pique polo"],
    ["hanorac", "hoodie", "sweatshirt", "hooded sweatshirt"],
    ["jacheta", "jacket"],
    ["vesta", "vest", "gilet", "bodywarmer", "body warmer"],
    ["camasa", "shirt", "dress shirt"],
    ["bluza", "blouse"],
    ["pulover", "pullover", "sweater", "jumper"],
    ["fleece", "polar"],

    # ── Clothing bottoms ──
    ["pantaloni", "pants", "trousers"],
    ["pantaloni scurti", "shorts"],

    # ── Workwear ──
    ["sort", "apron"],
    ["halat", "bathrobe", "robe"],
    ["salopeta", "overalls", "coverall"],

    # ── Headwear ──
    ["sapca", "cap", "baseball cap"],
    ["palarie", "hat", "sun hat"],
    ["caciula", "beanie", "winter hat", "knit hat"],
    ["bandana", "bandana", "headband"],

    # ── Accessories ──
    ["breloc", "keychain", "keyring", "key ring", "key holder"],
    ["umbrela", "umbrella"],
    ["ochelari", "sunglasses", "glasses"],
    ["ochelari de soare", "sunglasses"],
    ["ceas", "watch"],
    ["manusi", "gloves"],
    ["esarfa", "scarf"],
    ["cravata", "tie", "necktie"],
    ["curea", "belt"],
    ["bratara", "bracelet", "wristband", "silicone band"],
    ["insigna", "badge", "pin", "button badge"],
    ["magnet", "fridge magnet"],
    ["snur", "lanyard"],

    # ── Tech & electronics ──
    ["stick USB", "USB flash drive", "memory stick", "USB stick"],
    ["baterie externa", "power bank", "powerbank"],
    ["incarcator", "charger"],
    ["incarcator wireless", "wireless charger"],
    ["boxa", "speaker", "bluetooth speaker"],
    ["casti", "headphones", "earphones", "earbuds"],

    # ── Home, kitchen & outdoor ──
    ["prosop", "towel"],
    ["patura", "blanket", "fleece blanket"],
    ["perna", "pillow", "cushion"],
    ["lanterna", "flashlight", "torch", "lantern"],
    ["cutit", "knife"],
    ["deschizator", "opener", "bottle opener"],
    ["tirbusom", "corkscrew"],
    ["racitor", "cooler", "cooler bag"],
    ["gratar", "grill", "barbecue", "BBQ"],
    ["lumanare", "candle"],
    ["farfurie", "plate"],
    ["tava", "tray"],
    ["cos", "basket"],
    ["cutie", "box"],
    ["cutie cadou", "gift box"],

    # ── Sports & leisure ──
    ["minge", "ball"],
    ["saltea", "mat", "yoga mat"],
    ["coarda", "jump rope", "skipping rope"],
    ["frisbee", "flying disc"],

    # ── Materials (appear in product descriptions) ──
    ["bumbac", "cotton"],
    ["poliester", "polyester"],
    ["lemn", "wood", "wooden"],
    ["bambus", "bamboo"],
    ["piele", "leather"],
    ["ceramica", "ceramic"],
    ["inox", "stainless steel"],
    ["silicon", "silicone"],
    ["plastic", "plastic"],
    ["nailon", "nylon"],
    ["reciclat", "recycled", "RPET"],
    ["organic", "organic"],

    # ── Common descriptors ──
    ["personalizat", "custom", "customizable", "personalised"],
    ["promotional", "promotional"],
    ["pliabil", "foldable", "folding", "collapsible"],
    ["impermeabil", "waterproof", "water resistant"],
    ["termoizolant", "insulated", "thermal"],
]


def _build_synonyms() -> dict[str, list[str]]:
    """Build bidirectional synonym map from synonym groups."""
    synonyms: dict[str, list[str]] = {}
    for group in _SYNONYM_GROUPS:
        for term in group:
            key = term.lower()
            others = [t.lower() for t in group if t.lower() != key]
            if not others:
                continue
            if key in synonyms:
                existing = set(synonyms[key])
                existing.update(others)
                synonyms[key] = sorted(existing)
            else:
                synonyms[key] = others
    return synonyms


# ---------------------------------------------------------------------------
# Color group mapping — maps any color name to standard Romanian categories
# Used for sidebar filtering. Keywords sorted longest-first for priority.
# ---------------------------------------------------------------------------
_COLOR_GROUP_KEYWORDS: list[tuple[str, str]] = sorted(
    [
        # ── Bleumarin (must match before "albastru" and "blue") ──
        ("french navy", "Bleumarin"),
        ("bleumarin", "Bleumarin"),
        ("dark navy", "Bleumarin"),
        ("deep navy", "Bleumarin"),
        ("midnight", "Bleumarin"),
        ("navy", "Bleumarin"),

        # ── Negru ──
        ("black", "Negru"),
        ("negru", "Negru"),
        ("abanos", "Negru"),
        ("ebony", "Negru"),
        ("onyx", "Negru"),
        ("carbon", "Negru"),
        ("nero", "Negru"),

        # ── Alb ──
        ("white", "Alb"),
        ("alb", "Alb"),
        ("arctic", "Alb"),
        ("fildes", "Alb"),

        # ── Albastru ──
        ("blue", "Albastru"),
        ("albastru", "Albastru"),
        ("azure", "Albastru"),
        ("cobalt", "Albastru"),
        ("sapphire", "Albastru"),
        ("royal", "Albastru"),
        ("celest", "Albastru"),
        ("electric blue", "Albastru"),
        ("sky", "Albastru"),
        ("soul", "Albastru"),
        ("atoll", "Albastru"),
        ("bright royal", "Albastru"),
        ("rinse", "Albastru"),
        ("petrol", "Albastru"),
        ("duckling", "Albastru"),
        ("rata", "Albastru"),

        # ── Roșu ──
        ("red", "Rosu"),
        ("rosu", "Rosu"),
        ("crimson", "Rosu"),
        ("cherry", "Rosu"),
        ("scarlet", "Rosu"),
        ("fire", "Rosu"),
        ("cardinal", "Rosu"),
        ("flame", "Rosu"),
        ("chili", "Rosu"),
        ("chilli", "Rosu"),
        ("fiesta", "Rosu"),

        # ── Verde ──
        ("green", "Verde"),
        ("verde", "Verde"),
        ("forest", "Verde"),
        ("emerald", "Verde"),
        ("bottle", "Verde"),
        ("aloe", "Verde"),
        ("mint", "Verde"),
        ("menta", "Verde"),
        ("lime", "Verde"),
        ("fir", "Verde"),
        ("amazon", "Verde"),
        ("oasis", "Verde"),
        ("kelly", "Verde"),
        ("aventura", "Verde"),
        ("spruce", "Verde"),

        # ── Galben ──
        ("yellow", "Galben"),
        ("galben", "Galben"),
        ("lemon", "Galben"),
        ("daisy", "Galben"),
        ("curry", "Galben"),
        ("cyber yellow", "Galben"),

        # ── Gri ──
        ("grey", "Gri"),
        ("gray", "Gri"),
        ("gri", "Gri"),
        ("charcoal", "Gri"),
        ("ash", "Gri"),
        ("anthracite", "Gri"),
        ("antracit", "Gri"),
        ("graphite", "Gri"),
        ("graphit", "Gri"),
        ("cement", "Gri"),
        ("slate", "Gri"),
        ("heather", "Gri"),
        ("melange", "Gri"),
        ("melanj", "Gri"),
        ("steel", "Gri"),
        ("convoy", "Gri"),
        ("cenusiu", "Gri"),
        ("ardezie", "Gri"),
        ("piatra", "Gri"),
        ("smoke", "Gri"),

        # ── Maro ──
        ("brown", "Maro"),
        ("maro", "Maro"),
        ("chocolate", "Maro"),
        ("coffee", "Maro"),
        ("cafea", "Maro"),
        ("camel", "Maro"),
        ("toffee", "Maro"),
        ("ciocolat", "Maro"),
        ("espresso", "Maro"),
        ("bear", "Maro"),
        ("brick", "Maro"),
        ("tigla", "Maro"),
        ("savana", "Maro"),
        ("clay", "Maro"),

        # ── Roz ──
        ("pink", "Roz"),
        ("roz", "Roz"),
        ("fuchsia", "Roz"),
        ("fucsia", "Roz"),
        ("salmon", "Roz"),
        ("blush", "Roz"),
        ("berry", "Roz"),
        ("candy", "Roz"),
        ("magenta", "Roz"),
        ("bubble", "Roz"),
        ("matase", "Roz"),
        ("aprins", "Roz"),
        ("azalea", "Roz"),

        # ── Portocaliu ──
        ("orange", "Portocaliu"),
        ("portocaliu", "Portocaliu"),
        ("tangerine", "Portocaliu"),

        # ── Mov ──
        ("purple", "Mov"),
        ("mov", "Mov"),
        ("violet", "Mov"),
        ("plum", "Mov"),
        ("iris", "Mov"),
        ("eggplant", "Mov"),
        ("purpura", "Mov"),
        ("plumb", "Mov"),

        # ── Bej ──
        ("beige", "Bej"),
        ("bej", "Bej"),
        ("cream", "Bej"),
        ("ivory", "Bej"),
        ("ecru", "Bej"),
        ("sand", "Bej"),
        ("vanilla", "Bej"),
        ("bone", "Bej"),
        ("angora", "Bej"),
        ("linen", "Bej"),
        ("latte", "Bej"),
        ("vintage", "Bej"),
        ("dust", "Bej"),
        ("desert", "Bej"),
        ("butter", "Bej"),
        ("biscuit", "Bej"),
        ("natural", "Bej"),
        ("nisip", "Bej"),

        # ── Bordo ──
        ("burgundy", "Bordo"),
        ("bordo", "Bordo"),
        ("grena", "Bordo"),
        ("garnet", "Bordo"),
        ("maroon", "Bordo"),
        ("bordeaux", "Bordo"),
        ("cranberry", "Bordo"),
        ("wine", "Bordo"),

        # ── Turcoaz ──
        ("turquoise", "Turcoaz"),
        ("turcoaz", "Turcoaz"),
        ("aqua", "Turcoaz"),
        ("teal", "Turcoaz"),
        ("cyan", "Turcoaz"),
        ("caribbean", "Turcoaz"),
        ("acvamarin", "Turcoaz"),

        # ── Kaki ──
        ("olive", "Kaki"),
        ("kaki", "Kaki"),
        ("khaki", "Kaki"),
        ("army", "Kaki"),
        ("military", "Kaki"),
        ("combat", "Kaki"),
        ("dark olive", "Kaki"),
        ("avocado", "Kaki"),

        # ── Argintiu ──
        ("silver", "Argintiu"),
        ("argintiu", "Argintiu"),
        ("argint", "Argintiu"),

        # ── Auriu ──
        ("gold", "Auriu"),
        ("auriu", "Auriu"),
        ("golden", "Auriu"),

        # ── Coral ──
        ("coral", "Coral"),

        # ── Denim ──
        ("denim", "Denim"),
        ("jeans", "Denim"),
        ("chambray", "Denim"),

        # ── Multicolor ──
        ("assorted", "Multicolor"),
        ("multicolor", "Multicolor"),
        ("camo", "Multicolor"),
        ("camuflaj", "Multicolor"),
        ("camouflage", "Multicolor"),
        ("pixel", "Multicolor"),

        # ── Transparent ──
        ("transparent", "Transparent"),
        ("clear", "Transparent"),

        # ── Cupru ──
        ("copper", "Cupru"),
        ("cupru", "Cupru"),
        ("bronze", "Cupru"),
        ("bronz", "Cupru"),
        ("rose gold", "Cupru"),

        # ── Piersică ──
        ("peach", "Piersica"),
        ("piersic", "Piersica"),
        ("apricot", "Piersica"),
        ("peche", "Piersica"),

        # ── Lavandă ──
        ("lavender", "Lavanda"),
        ("lavanda", "Lavanda"),
        ("lilac", "Lavanda"),
        ("wisteria", "Lavanda"),

        # ── Galben Neon / Fluor ──
        ("fluorescent", "Galben Neon"),
        ("fluor", "Galben Neon"),
        ("neon", "Galben Neon"),
        ("hi-vis", "Galben Neon"),
        ("hi vis", "Galben Neon"),
        ("signal", "Galben Neon"),
        ("vizibilitate", "Galben Neon"),
    ],
    key=lambda x: -len(x[0]),  # longest keywords first
)


def _strip_diacritics(s: str) -> str:
    """Remove diacritics: ș→s, ț→t, ă→a, â→a, î→i etc."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _color_to_groups(name: str) -> list[str]:
    """Map a color name to standard Romanian color group(s)."""
    if not name:
        return []

    # Normalize: lowercase + strip diacritics so "ROȘU" matches keyword "rosu"
    raw = _strip_diacritics(name.lower().strip())

    # Strip known non-color suffixes/prefixes
    import re
    raw = re.sub(r"\s*\(brand label\)\s*$", "", raw)
    raw = re.sub(r"^g\.\s*dyed\s+", "", raw)
    raw = re.sub(r"\s*\d+$", "", raw)  # trailing numbers like "alb 2"

    if not raw:
        return []

    # Split combo colors on "/"  or  "-" when both sides look like colors
    parts = [p.strip() for p in raw.split("/") if p.strip()]
    if len(parts) == 1:
        # Also try splitting on "-" for patterns like "Black-Cement Grey"
        dash_parts = [p.strip() for p in raw.split("-") if p.strip()]
        if len(dash_parts) >= 2:
            parts = dash_parts

    groups: list[str] = []
    for part in parts:
        for keyword, group in _COLOR_GROUP_KEYWORDS:
            if keyword in part:
                if group not in groups:
                    groups.append(group)
                break  # first (longest) match wins for this part

    return groups


@dataclass
class SearchFilters:
    query: str = ""
    category: str = ""
    subcategory: str = ""
    category_group: str = ""
    unified_category: str = ""
    unified_subcategory: str = ""
    min_price: float | None = None
    max_price: float | None = None
    color: str = ""
    color_group: str = ""
    integration_id: str = ""
    in_stock: bool = False
    sort_by: str = ""  # "price_asc", "price_desc", "name_asc", "newest"
    page: int = 1
    limit: int = 20
    group_variants: bool = True


@dataclass
class SearchResult:
    results: list[dict] = field(default_factory=list)
    total: int = 0
    page: int = 1
    total_pages: int = 0
    query: str = ""
    processing_time_ms: int = 0
    facets: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Client management
# ---------------------------------------------------------------------------
_client: meilisearch.Client | None = None


def get_client() -> meilisearch.Client:
    """Get or create Meilisearch client. Raises if unavailable."""
    global _client
    if _client is None:
        _client = meilisearch.Client(
            settings.meilisearch_url,
            settings.meilisearch_api_key,
        )
    return _client


def is_available() -> bool:
    """Check if Meilisearch is reachable (cached for 30s)."""
    global _meili_available, _meili_available_ts
    now = time.time()
    if _meili_available is not None and (now - _meili_available_ts) < _AVAILABILITY_TTL:
        return _meili_available
    try:
        get_client().health()
        _meili_available = True
    except Exception:
        _meili_available = False
    _meili_available_ts = now
    return _meili_available


# ---------------------------------------------------------------------------
# Index configuration
# ---------------------------------------------------------------------------
def setup_index() -> dict:
    """
    Configure the products index with optimal settings for 200k+ products.
    Call once on first deploy or after schema changes.
    Returns task info dict.
    """
    client = get_client()

    # Create index if it doesn't exist
    try:
        client.create_index(INDEX_NAME, {"primaryKey": "id"})
    except meilisearch.errors.MeilisearchApiError:
        pass  # already exists

    index = client.index(INDEX_NAME)

    # Searchable attributes (order = ranking priority)
    index.update_searchable_attributes([
        "name",
        "supplier_code",
        "external_id",
        "short_description",
        "category",
        "subcategory",
        "unified_category",
        "unified_subcategory",
        "brand",
        "description",
        "color_names",
    ])

    # Filterable attributes (used in filters + facets)
    index.update_filterable_attributes([
        "category",
        "category_group",
        "subcategory",
        "unified_category",
        "unified_subcategory",
        "base_price",
        "integration_id",
        "is_active",
        "stock",
        "color_names",
        "color_groups",
        "brand",
        "price_range",
        "supplier_code",
    ])

    # Sortable attributes
    index.update_sortable_attributes([
        "base_price",
        "name",
        "last_synced_at",
        "stock",
    ])

    # Ranking rules
    index.update_ranking_rules([
        "words",
        "typo",
        "proximity",
        "attribute",
        "sort",
        "exactness",
    ])

    # Typo tolerance for promotional product names
    index.update_typo_tolerance({
        "enabled": True,
        "minWordSizeForTypos": {"oneTypo": 4, "twoTypos": 8},
    })

    # Pagination limit for large datasets
    index.update_pagination_settings({"maxTotalHits": 100000})

    # Faceting - increase max values for categories
    index.update_faceting_settings({"maxValuesPerFacet": 500})

    # Romanian ↔ English synonyms for multilingual search
    synonyms = _build_synonyms()
    index.update_synonyms(synonyms)
    logger.info(f"Meilisearch synonyms configured: {len(synonyms)} terms")

    logger.info("Meilisearch index configured for 200k+ products")
    return {"status": "configured", "index": INDEX_NAME}


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------
def _prepare_doc(product_dict: dict) -> dict:
    """
    Prepare a product dict for Meilisearch indexing.
    Flattens colors into searchable/filterable strings and computes price_range.
    """
    doc = {**product_dict}

    # Flatten color names for filtering/searching
    colors_raw = doc.get("colors", "")
    if isinstance(colors_raw, list):
        color_names = [c.get("name", "") for c in colors_raw if isinstance(c, dict) and c.get("name")]
        doc["color_names"] = color_names
    elif isinstance(colors_raw, str) and colors_raw:
        doc["color_names"] = [c.strip() for c in colors_raw.split(",") if c.strip()]
    else:
        doc["color_names"] = []

    # Compute color_groups — standard Romanian categories for sidebar filtering
    groups: set[str] = set()
    for cn in doc["color_names"]:
        groups.update(_color_to_groups(cn))
    doc["color_groups"] = sorted(groups)

    # Compute price_range bucket label
    price = doc.get("base_price", 0)
    for low, high in PRICE_RANGES:
        if low <= price < high:
            if high == float("inf"):
                doc["price_range"] = f"{int(low)}+"
            else:
                doc["price_range"] = f"{int(low)}-{int(high)}"
            break

    return doc


def index_products(products: list[dict]) -> int:
    """
    Index a batch of products into Meilisearch.
    Handles chunking for large batches (200k+).
    """
    if not products:
        return 0

    client = get_client()
    index = client.index(INDEX_NAME)
    total = 0

    # Prepare all documents
    docs = [_prepare_doc(p) for p in products]

    # Upload in chunks
    for i in range(0, len(docs), BATCH_SIZE):
        chunk = docs[i : i + BATCH_SIZE]
        task = index.add_documents(chunk, primary_key="id")
        total += len(chunk)
        logger.info(
            f"Indexed batch {i // BATCH_SIZE + 1}: {len(chunk)} docs (task {task.task_uid})"
        )

    logger.info(f"Total indexed: {total} products")
    return total


def delete_products(product_ids: list[str]) -> None:
    """Remove products from the search index."""
    if not product_ids:
        return
    client = get_client()
    client.index(INDEX_NAME).delete_documents(product_ids)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def search_products(filters: SearchFilters) -> SearchResult:
    """
    Full-featured faceted search with pagination.

    Returns SearchResult with results, total, facets for category/price/color.
    """
    client = get_client()
    index = client.index(INDEX_NAME)

    # Build filter expressions
    filter_parts: list[str] = ["is_active = true"]

    if filters.category:
        filter_parts.append(f'category = "{_escape(filters.category)}"')

    if filters.subcategory:
        filter_parts.append(f'subcategory = "{_escape(filters.subcategory)}"')

    if filters.category_group:
        filter_parts.append(f'category_group = "{_escape(filters.category_group)}"')

    if filters.unified_category:
        filter_parts.append(f'unified_category = "{_escape(filters.unified_category)}"')

    if filters.unified_subcategory:
        filter_parts.append(f'unified_subcategory = "{_escape(filters.unified_subcategory)}"')

    if filters.min_price is not None:
        filter_parts.append(f"base_price >= {filters.min_price}")
    if filters.max_price is not None:
        filter_parts.append(f"base_price <= {filters.max_price}")

    if filters.color:
        filter_parts.append(f'color_names = "{_escape(filters.color)}"')

    if filters.color_group:
        filter_parts.append(f'color_groups = "{_escape(_strip_diacritics(filters.color_group))}"')

    if filters.integration_id:
        filter_parts.append(f'integration_id = "{_escape(filters.integration_id)}"')

    if filters.in_stock:
        filter_parts.append("stock > 0")

    # Sort
    sort_map = {
        "price_asc": ["base_price:asc"],
        "price_desc": ["base_price:desc"],
        "name_asc": ["name:asc"],
        "newest": ["last_synced_at:desc"],
        "stock": ["stock:desc"],
    }
    sort = sort_map.get(filters.sort_by, [])

    # Build search params (use page/hitsPerPage for exact totalHits)
    search_params = {
        "filter": " AND ".join(filter_parts),
        "sort": sort or None,
        "hitsPerPage": filters.limit,
        "page": filters.page,
        "facets": ["category", "subcategory", "price_range", "color_names", "color_groups", "brand"],
        "attributesToHighlight": ["name", "short_description"],
        "highlightPreTag": "<mark>",
        "highlightPostTag": "</mark>",
        # Use "frequency" matching: drops most common words first for better relevance
        "matchingStrategy": "frequency",
    }

    # Group variants by supplier_code to avoid duplicate product models
    if filters.group_variants:
        search_params["distinct"] = "supplier_code"

    # Execute search with facets (fallback without distinct if index not configured yet)
    try:
        raw = index.search(filters.query, search_params)
    except Exception:
        if filters.group_variants:
            search_params.pop("distinct", None)
            raw = index.search(filters.query, search_params)
        else:
            raise

    # Extract results
    hits = raw.get("hits", [])
    total = raw.get("totalHits", raw.get("estimatedTotalHits", 0))
    total_pages = raw.get("totalPages", math.ceil(total / filters.limit) if filters.limit else 0)
    processing_ms = raw.get("processingTimeMs", 0)

    # Build facets dict
    facet_distribution = raw.get("facetDistribution", {})
    facets = {
        "category": facet_distribution.get("category", {}),
        "subcategory": facet_distribution.get("subcategory", {}),
        "price_range": _sort_price_ranges(facet_distribution.get("price_range", {})),
        "color_names": facet_distribution.get("color_names", {}),
        "color_groups": facet_distribution.get("color_groups", {}),
        "brand": facet_distribution.get("brand", {}),
    }

    # Attach highlighted fields
    results = []
    for hit in hits:
        result = {**hit}
        formatted = hit.get("_formatted")
        if formatted:
            result["_highlighted_name"] = formatted.get("name", hit.get("name", ""))
            result["_highlighted_description"] = formatted.get(
                "short_description", hit.get("short_description", "")
            )
        results.append(result)

    return SearchResult(
        results=results,
        total=total,
        page=filters.page,
        total_pages=total_pages,
        query=filters.query,
        processing_time_ms=processing_ms,
        facets=facets,
    )


# ---------------------------------------------------------------------------
# Autocomplete / Suggestions
# ---------------------------------------------------------------------------
def get_suggestions(partial_query: str, limit: int = 10) -> list[dict]:
    """
    Fast autocomplete suggestions for partial queries.
    Returns a list of suggestion dicts with name, code, and category.
    """
    if not partial_query or len(partial_query) < 2:
        return []

    client = get_client()
    index = client.index(INDEX_NAME)

    raw = index.search(
        partial_query,
        {
            "limit": limit * 2,  # fetch more to deduplicate
            "filter": "is_active = true",
            "attributesToRetrieve": ["name", "supplier_code", "category", "primary_image"],
            "attributesToHighlight": ["name", "supplier_code"],
            "highlightPreTag": "<mark>",
            "highlightPostTag": "</mark>",
            "distinct": "supplier_code",
        },
    )

    suggestions: list[dict] = []
    seen: set[str] = set()

    for hit in raw.get("hits", []):
        code = hit.get("supplier_code", "")
        name = hit.get("name", "")
        key = code or name
        if key and key not in seen:
            seen.add(key)
            formatted = hit.get("_formatted", {})
            suggestions.append({
                "name": name,
                "code": code,
                "category": hit.get("category", ""),
                "image": hit.get("primary_image", ""),
                "highlighted_name": formatted.get("name", name),
                "highlighted_code": formatted.get("supplier_code", code),
            })
        if len(suggestions) >= limit:
            break

    return suggestions


# ---------------------------------------------------------------------------
# Reindex all products from database
# ---------------------------------------------------------------------------
async def reindex_all(db: AsyncSession) -> int:
    """
    Full reindex: reads all active products from DB, clears the index,
    and re-uploads everything in batches.
    """
    client = get_client()
    index = client.index(INDEX_NAME)

    # Clear existing index
    task = index.delete_all_documents()
    logger.info(f"Clearing index (task {task.task_uid})")
    client.wait_for_task(task.task_uid, timeout_in_ms=60000)

    # Ensure index settings
    setup_index()

    # Count total
    count_result = await db.execute(
        select(func.count(Product.id)).where(Product.is_active == True)
    )
    total_count = count_result.scalar() or 0
    logger.info(f"Reindexing {total_count} products...")

    # Stream products in batches
    total_indexed = 0
    batch_num = 0

    while total_indexed < total_count:
        result = await db.execute(
            select(Product)
            .where(Product.is_active == True)
            .offset(total_indexed)
            .limit(BATCH_SIZE)
        )
        products = result.scalars().all()
        if not products:
            break

        docs = [p.to_search_dict() for p in products]
        prepared = [_prepare_doc(d) for d in docs]
        task = index.add_documents(prepared, primary_key="id")

        batch_num += 1
        total_indexed += len(docs)
        logger.info(
            f"Reindex batch {batch_num}: {len(docs)} docs "
            f"({total_indexed}/{total_count}, task {task.task_uid})"
        )

    logger.info(f"Reindex complete: {total_indexed} products indexed")
    return total_indexed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _escape(value: str) -> str:
    """Escape quotes in Meilisearch filter values."""
    return value.replace('"', '\\"')


def _sort_price_ranges(raw: dict[str, int]) -> dict[str, int]:
    """Sort price range facets in order."""
    order = [
        f"{int(lo)}-{int(hi)}" if hi != float("inf") else f"{int(lo)}+"
        for lo, hi in PRICE_RANGES
    ]
    sorted_ranges: dict[str, int] = {}
    for key in order:
        if key in raw:
            sorted_ranges[key] = raw[key]
    for key, val in raw.items():
        if key not in sorted_ranges:
            sorted_ranges[key] = val
    return sorted_ranges


def get_variants_by_codes(
    supplier_codes: list[str],
    integration_ids: list[str] | None = None,
) -> dict[str, dict]:
    """
    Fetch all variants for given supplier_codes from Meilisearch.
    When integration_ids is provided, each code is scoped to its supplier
    to prevent cross-supplier variant mixing.
    Returns {supplier_code: {colors: [...], total_stock: int, count: int}}.
    """
    if not supplier_codes:
        return {}

    client = get_client()
    index = client.index(INDEX_NAME)

    # Build OR filter for all supplier codes, scoped by integration_id when available
    if integration_ids and len(integration_ids) == len(supplier_codes):
        # Build per-code filter scoped to its integration
        code_parts = []
        for code, iid in zip(supplier_codes, integration_ids):
            if iid:
                code_parts.append(
                    f'(supplier_code = "{_escape(code)}" AND integration_id = "{_escape(iid)}")'
                )
            else:
                code_parts.append(f'supplier_code = "{_escape(code)}"')
        code_filters = " OR ".join(code_parts)
    else:
        code_filters = " OR ".join(
            f'supplier_code = "{_escape(c)}"' for c in supplier_codes
        )

    raw = index.search("", {
        "filter": f"is_active = true AND ({code_filters})",
        "limit": min(len(supplier_codes) * 100, 5000),  # up to 100 variants per model (Malfini has ~80)
        "attributesToRetrieve": ["supplier_code", "colors", "stock", "integration_id", "base_price"],
    })

    agg: dict[str, dict] = {}
    # Build a lookup for expected integration_id per supplier_code
    code_iid_map: dict[str, str] = {}
    if integration_ids and len(integration_ids) == len(supplier_codes):
        for code, iid in zip(supplier_codes, integration_ids):
            code_iid_map[code] = iid

    for hit in raw.get("hits", []):
        code = hit.get("supplier_code", "")
        if not code:
            continue
        # Skip hits from wrong supplier if we have integration_id mapping
        if code_iid_map:
            expected_iid = code_iid_map.get(code, "")
            if expected_iid and hit.get("integration_id", "") != expected_iid:
                continue
        if code not in agg:
            agg[code] = {"colors": [], "seen": set(), "total_stock": 0, "count": 0,
                         "min_price": float("inf"), "max_price": 0.0}
        agg[code]["total_stock"] += hit.get("stock", 0)
        agg[code]["count"] += 1
        bp = hit.get("base_price", 0) or 0
        if bp > 0:
            if bp < agg[code]["min_price"]:
                agg[code]["min_price"] = bp
            if bp > agg[code]["max_price"]:
                agg[code]["max_price"] = bp
        for c in (hit.get("colors") or []):
            if isinstance(c, dict):
                cname = c.get("name", "").strip()
                if cname and cname not in agg[code]["seen"]:
                    agg[code]["seen"].add(cname)
                    agg[code]["colors"].append(c)

    # Remove internal 'seen' set and fix inf values before returning
    for v in agg.values():
        v.pop("seen", None)
        if v["min_price"] == float("inf"):
            v["min_price"] = 0.0
    return agg


def get_index_stats() -> dict:
    """Get index statistics (doc count, indexing status, etc.)."""
    client = get_client()
    index = client.index(INDEX_NAME)
    stats = index.get_stats()
    return {
        "number_of_documents": stats.number_of_documents,
        "is_indexing": stats.is_indexing,
        "field_distribution": stats.field_distribution,
    }
