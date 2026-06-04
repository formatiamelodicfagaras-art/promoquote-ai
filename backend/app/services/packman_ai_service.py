"""
PACKMAN AI — AI agent for brand kit product proposals.

Uses Claude to interpret user requests (e.g., "vreau o geacă, notebook și pix"),
searches products by color/category via Meilisearch, and returns product suggestions
with mockup-ready data (print areas, dimensions). No prices — just creative proposals.
"""
import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.product import Product
from app.schemas.chat import ChatMessage
from app.services.search_service import (
    search_products as meili_search,
    SearchFilters,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
Ești PACKMAN AI, asistent creativ pentru propuneri de produse promoționale personalizate. \
Rolul tău este să ajuți la crearea de pachete de produse cu logo pentru clienți — \
fără prețuri, doar idei vizuale.

COMPORTAMENT:
- Vorbești ÎNTOTDEAUNA în română
- Ești creativ, entuziasmant, orientat spre propuneri vizuale
- NU menționezi NICIODATĂ prețuri — PACKMAN este doar despre idei și mockup-uri
- Recomanzi combinații atractive de produse care se potrivesc cu brandul clientului
- Sugerezi produse din categorii diverse pentru un pachet complet

CATALOGUL:
- ~150.000 produse de la 9 furnizori (EASYGIFTS, MACMA, MIDOCEAN, ANDA, etc.)
- Produsele sunt grupate automat — un rezultat per model
- Fiecare produs are zone de personalizare (print_areas) cu dimensiuni și metode

FLOW:
1. Utilizatorul încarcă un logo PNG și selectează culorile brand-ului
2. Utilizatorul descrie ce produse dorește (ex: "vreau o geacă, notebook și pix metalic")
3. Tu cauți produse potrivite folosind tool-ul search_products
4. Returnezi produse cu detalii despre zona de print pentru mockup
5. Utilizatorul poate ajusta, adăuga/elimina produse
6. La final, se generează un PDF cu mockup-uri

INTERPRETAREA CERERILOR — FOARTE IMPORTANT:
- FIECARE tip de produs menționat de utilizator necesită o CĂUTARE SEPARATĂ!
  Exemplu: "tricou, șapcă și sticlă sport" = 3 căutări separate:
    1. search_products(query="tricou", ...)
    2. search_products(query="șapcă", ...)
    3. search_products(query="sticlă sport", ...)
- NU combina mai multe tipuri de produse într-o singură căutare!
- Folosește termeni specifici și scurți: "tricou", "șapcă", "sticlă", "pix", "rucsac"
- Caută în culorile selectate de utilizator (primite ca context)
- Dacă nu sunt culori selectate, caută fără filtru de culoare
- Poți sugera și produse complementare dacă e relevant

RĂSPUNS:
- Descrie pe scurt fiecare produs propus
- Menționează zona de print și metoda de personalizare
- Sugerează unde ar arăta cel mai bine logo-ul
- Propune combinații creative de produse
- NU menționa prețuri sau costuri — doar propuneri vizuale
- Grupează răspunsul pe categorii de produse

IMPORTANT:
- FIECARE tip de produs = o căutare separată cu search_products
- Caută cu limit=10 per categorie de produs cerut
- Preferă produse cu stoc mare
- Preferă produse cu zone de print bine definite (width_mm > 0)
- Verifică că produsele returnate corespund cu ce a cerut utilizatorul
"""


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------
PACKMAN_TOOLS = [
    {
        "name": "search_products",
        "description": (
            "Caută produse promoționale în catalogul de ~150.000 produse. "
            "IMPORTANT: Caută un singur tip de produs per apel! "
            "Dacă utilizatorul cere 'tricou, șapcă și sticlă', fă 3 apeluri separate. "
            "Returnează produse cu detalii despre zonele de personalizare."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "UN SINGUR tip de produs (ex: 'tricou', 'șapcă', 'sticlă sport', 'pix metalic', 'rucsac'). NU combina mai multe tipuri!"
                },
                "color_group": {
                    "type": "string",
                    "description": "Grup de culoare în română (ex: 'Negru', 'Albastru', 'Roșu', 'Maro'). Filtrează produse pe culoare."
                },
                "supplier": {
                    "type": "string",
                    "description": "Filtru furnizor (ex: 'EASYGIFTS', 'MACMA', 'MIDOCEAN', 'ANDA'). Lasă gol pentru toți furnizorii."
                },
                "limit": {
                    "type": "integer",
                    "description": "Număr maxim rezultate (implicit 10, maxim 20)"
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_product_print_details",
        "description": "Obține detaliile complete de personalizare ale unui produs: zone de print, dimensiuni, metode disponibile.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "ID-ul produsului",
                },
            },
            "required": ["product_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------
def _build_brand_product(
    hit: dict,
    printing_opts: list | None = None,
    color_image: tuple[str, str] | None = None,
) -> dict:
    """Convert a Meilisearch hit to a PACKMAN product card.

    color_image: optional (image_url, hex) from a color-matched DB variant.
    """
    colors = hit.get("colors", [])
    if isinstance(colors, list):
        color_names = [c.get("name", "") for c in colors if isinstance(c, dict) and c.get("name")]
    else:
        color_names = []

    image_url = hit.get("primary_image") or hit.get("image_url", "")
    color_hex = ""
    if color_image and color_image[0]:
        image_url, color_hex = color_image

    # Build print areas from printing_options
    print_areas = []
    for opt in (printing_opts or hit.get("printing_options") or []):
        w_mm = opt.get("max_width_mm", 0) or 0
        h_mm = opt.get("max_height_mm", 0) or 0
        if w_mm == 0 or h_mm == 0:
            for t in opt.get("techniques", []):
                tw = t.get("max_width_mm", 0) or 0
                th = t.get("max_height_mm", 0) or 0
                if tw > 0 and th > 0:
                    w_mm, h_mm = tw, th
                    break
        print_areas.append({
            "location": opt.get("position", "front"),
            "width_mm": w_mm,
            "height_mm": h_mm,
            "method": ", ".join(t.get("name", "") for t in opt.get("techniques", [])),
            "position_image": opt.get("position_image", ""),
        })

    # Collect all available images
    all_images: list[str] = []
    if image_url:
        all_images.append(image_url)
    for img in (hit.get("images") or []):
        if img and img not in all_images:
            all_images.append(img)

    return {
        "id": hit.get("id", ""),
        "sku": hit.get("external_id") or hit.get("supplier_code", ""),
        "name": hit.get("name", ""),
        "supplier": hit.get("category", ""),
        "category": hit.get("subcategory") or hit.get("category_group", ""),
        "color": ", ".join(color_names[:3]),
        "color_hex": color_hex,
        "stock": hit.get("stock", 0),
        "image_url": image_url,
        "images": all_images,
        "min_order": hit.get("min_order_qty", 1),
        "print_areas": print_areas,
        "brand": hit.get("brand", ""),
    }


async def _exec_search(args: dict, db: AsyncSession) -> dict:
    """Search products for PACKMAN."""
    query = args.get("query", "")
    color_group = args.get("color_group", "")
    supplier = args.get("supplier", "") or args.get("category", "")  # backwards compat
    limit = min(args.get("limit", 10), 20)

    filters = SearchFilters(
        query=query,
        category=supplier,
        color_group=color_group,
        in_stock=True,
        limit=limit,
        group_variants=True,
    )

    result = await asyncio.to_thread(meili_search, filters)

    # Enrich with printing_options from DB
    product_ids = [h.get("id", "") for h in result.results if h.get("id")]
    printing_map: dict[str, list] = {}
    if product_ids:
        q = select(Product.id, Product.printing_options).where(Product.id.in_(product_ids))
        rows = await db.execute(q)
        for row in rows.all():
            printing_map[row[0]] = row[1] or []

    # Find color-matched variant images from DB
    from app.services.search_service import _color_to_groups, _strip_diacritics
    color_image_map: dict[str, tuple[str, str]] = {}
    color_group_normalized = _strip_diacritics(color_group) if color_group else ""
    if color_group_normalized:
        supplier_codes = list({
            h.get("supplier_code", "") or h.get("external_id", "")
            for h in result.results if h.get("supplier_code") or h.get("external_id")
        })
        if supplier_codes:
            vq = select(
                Product.supplier_code, Product.primary_image, Product.colors
            ).where(
                Product.supplier_code.in_(supplier_codes),
                Product.is_active == True,
                Product.primary_image != "",
                Product.primary_image != None,
            )
            for scode, vimg, vcolors in (await db.execute(vq)).all():
                if scode in color_image_map:
                    continue
                if not vcolors or not isinstance(vcolors, list):
                    continue
                for vc in vcolors:
                    if not isinstance(vc, dict):
                        continue
                    if color_group_normalized in _color_to_groups(vc.get("name", "")):
                        color_image_map[scode] = (vimg or "", vc.get("hex", ""))
                        break

    products = []
    for hit in result.results:
        pid = hit.get("id", "")
        scode = hit.get("supplier_code", "") or hit.get("external_id", "")
        products.append(_build_brand_product(
            hit, printing_map.get(pid),
            color_image=color_image_map.get(scode),
        ))

    return {
        "products": products,
        "total_found": result.total,
    }


async def _exec_get_print_details(args: dict, db: AsyncSession) -> dict:
    """Get detailed print area info for a specific product."""
    product_id = args["product_id"]
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return {"error": f"Produsul cu ID '{product_id}' nu a fost găsit."}

    print_areas = []
    for opt in (product.printing_options or []):
        w_mm = opt.get("max_width_mm", 0) or 0
        h_mm = opt.get("max_height_mm", 0) or 0
        techniques = []
        for tech in opt.get("techniques", []):
            techniques.append({
                "name": tech.get("name", ""),
                "max_colors": tech.get("max_colors", 0),
            })
            if (w_mm == 0 or h_mm == 0):
                tw = tech.get("max_width_mm", 0) or 0
                th = tech.get("max_height_mm", 0) or 0
                if tw > 0 and th > 0:
                    w_mm, h_mm = tw, th
        print_areas.append({
            "location": opt.get("position", "front"),
            "width_mm": w_mm,
            "height_mm": h_mm,
            "techniques": techniques,
            "position_image": opt.get("position_image", ""),
        })

    return {
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "image_url": product.primary_image or "",
        "print_areas": print_areas,
        "colors": product.colors or [],
        "specifications": product.specifications or {},
    }


TOOL_HANDLERS = {
    "search_products": _exec_search,
    "get_product_print_details": _exec_get_print_details,
}


# ---------------------------------------------------------------------------
# Main chat processor
# ---------------------------------------------------------------------------
async def process_packman_message(
    message: str,
    conversation_history: list[ChatMessage],
    brand_colors: list[str],
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Process a PACKMAN AI chat message, yielding SSE events."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Build context about brand colors
    color_context = ""
    if brand_colors:
        color_context = f"\n\nCULORILE BRAND-ULUI CLIENTULUI: {', '.join(brand_colors)}\nFoloseşte color_group cu aceste culori la căutare pentru a găsi produse în culorile brand-ului."

    system_prompt = _SYSTEM_PROMPT + color_context

    messages = [{"role": m.role, "content": m.content} for m in conversation_history]
    messages.append({"role": "user", "content": message})

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
            system=system_prompt,
            tools=PACKMAN_TOOLS,
            messages=messages,
        )

        tool_round = 0
        MAX_TOOL_ROUNDS = 10  # PACKMAN needs multiple rounds (separate search per product type)

        while response.stop_reason == "tool_use" and tool_round < MAX_TOOL_ROUNDS:
            tool_round += 1
            assistant_content = response.content
            tool_results = []

            for block in assistant_content:
                if block.type == "text" and block.text:
                    yield _sse({"type": "text", "content": block.text})

                elif block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    yield _sse({
                        "type": "tool_call",
                        "content": {"tool": tool_name, "input": tool_input},
                    })

                    handler = TOOL_HANDLERS.get(tool_name)
                    if handler:
                        try:
                            tool_result = await handler(tool_input, db)
                        except Exception as e:
                            logger.error(f"PACKMAN tool {tool_name} error: {e}")
                            tool_result = {"error": str(e)}
                    else:
                        tool_result = {"error": f"Unknown tool: {tool_name}"}

                    # Send product cards to frontend
                    if tool_name == "search_products":
                        products = tool_result.get("products", [])
                        if products:
                            yield _sse({"type": "products", "content": products})

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    })

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

            response = await client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                system=system_prompt,
                tools=PACKMAN_TOOLS,
                messages=messages,
            )

        # Final response
        for block in response.content:
            if block.type == "text" and block.text:
                yield _sse({"type": "text", "content": block.text})

        yield _sse({"type": "done"})

    except anthropic.APIError as e:
        logger.error(f"PACKMAN Anthropic API error: {e}")
        yield _sse({"type": "error", "content": f"Eroare AI: {e.message}"})
        yield _sse({"type": "done"})
    except Exception as e:
        logger.error(f"PACKMAN processing error: {e}")
        yield _sse({"type": "error", "content": "A apărut o eroare internă. Încearcă din nou."})
        yield _sse({"type": "done"})


def _sse(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)
