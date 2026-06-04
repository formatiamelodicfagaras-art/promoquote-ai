import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.config import get_settings
from app.models.product import Product
from app.models.quote import Quote, QuoteItem
from app.models.settings import load_settings_dict, get_setting_float
from app.schemas.chat import ChatMessage
from app.services.search_service import (
    search_products as meili_search,
    SearchFilters,
)
from app.services.translation_service import translate_to_romanian

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT_TEMPLATE = """\
Ești PromoQuote AI, asistent de vânzări pentru produse promoționale și cadouri corporative.

COMPORTAMENT:
- Vorbești ÎNTOTDEAUNA în română
- Ești prietenos, profesional, orientat spre vânzări
- Calculează automat prețul cu marja configurată
- Sugerează opțiuni de personalizare relevante (logo, text, etc.)

CATALOGUL:
- Catalog full-text cu fuzzy matching — caută natural cu cuvinte-cheie
- Produsele sunt grupate automat — un rezultat per model (nu per culoare)
- Fiecare produs afișat include toate culorile disponibile
- Același produs poate exista la mai mulți furnizori cu prețuri diferite — compară când e cazul

CATEGORII PRINCIPALE (existente în catalog):
- PRODUSE TEXTILE: tricouri, tricouri polo, pulovere, polar, jachete, veste, softshells, cămăși, pantaloni, șepci
- GENȚI, CĂLĂTORII, WELLNESS: rucsacuri, genți sport, genți eco, sacoșe, genți laptop, accesorii călătorie
- DRINK TO GO: sticle, termosuri, căni, pahare, carafe, seturi băut
- ELECTRONICE ȘI ACCESORII: pendrive, powerbank, difuzoare, căști, încărcătoare wireless
- PIXURI ȘI INSTRUMENTE DE SCRIS: pixuri metalice, pixuri plastic, pixuri eco, creioane, markere, seturi scris
- BIROU ȘI CEASURI: caiete, agende, mape, calculatoare, accesorii birou
- BRELOCURI ȘI ALTELE: brelocuri, brichete, deschizătoare sticle, accesorii auto
- TIMP LIBER, SPORT, JUCĂRII: jucării, plajă, sport, fitness, ochelari soare, bicicletă
- UNELTE ȘI LANTERNE: cuțite, multitooluri, lanterne, rulete
- UMBRELE ȘI PELERINE DE PLOAIE: umbrele, pelerine
- PENTRU CASĂ ȘI BUCĂTĂRIE: accesorii bucătărie, casă, caserole, cuțite tocătoare

FLOW STANDARD:
1. Înțelege cererea (ocazie, cantitate, buget, culoare preferată)
2. Caută produse potrivite cu tool-ul search_products
3. CREEAZĂ IMEDIAT oferta cu create_quote — nu doar prezenta produse, ci creează oferta direct
4. Descrie pe scurt ce ai adăugat în ofertă (nume produs, culoare, cantitate, preț)
5. Spune clientului că poate edita oferta din panoul lateral (schimba cantități, șterge produse)

IMPORTANT - CREEAZĂ OFERTA AUTOMAT:
- După ce cauți și găsești produse, folosește IMEDIAT tool-ul create_quote
- NU aștepta confirmarea utilizatorului — creează oferta direct
- Utilizatorul poate edita/modifica oferta ulterior din panoul lateral
- Dacă utilizatorul specifică o cantitate, folosește-o la create_quote
- Dacă NU specifică cantitate, trimite quantity=1 la create_quote

INTERPRETAREA CERERILOR:
- "N variante" sau "N opțiuni" = N MODELE/PRODUSE DIFERITE (NU culori ale aceluiași produs!)
  Exemplu: "4 variante de pixuri" = 4 produse diferite de pixuri (modele diferite)
- Culoarea menționată (ex: "albastru", "roșu") = culoarea dorită pentru TOATE produsele
  Exemplu: "pixuri albastre, 3 variante" = 3 modele diferite de pixuri, toate în albastru
- Folosește parametrul "color" la search_products pentru a filtra după culoarea dorită
- Folosește parametrul "subcategory" când utilizatorul cere o categorie specifică
- Caută suficiente produse (limit mai mare) pentru a avea de unde alege

STRATEGIE CĂUTARE:
- Caută cu termeni SPECIFICI și relevanți (ex: "tricou polo", "pix metalic", "cană ceramică")
- NU folosi termeni generici sau prea scurți (ex: "T", "set", "cadou")
- NU filtra pe furnizor (category) decât dacă clientul cere explicit un anumit furnizor
- Dacă NU găsești rezultate, simplifică query-ul dar păstrează termenii cheie specifici
- Filtrele de preț sunt în EUR (preț de bază)

IMPORTANT - EFICIENȚĂ CĂUTARE:
- Fă O SINGURĂ căutare cu limit=25-30, apoi alege cele mai bune N produse din rezultate
- NU căuta de mai multe ori pentru aceeași cerere (ex: NU căuta pe fiecare furnizor separat)
- NU repeta căutări — un singur apel search_products este suficient pentru a găsi variante
- Din rezultate, ALEGE câte 1 produs de la FIECARE furnizor diferit, pe rând (round-robin)
  Exemplu pentru 5 variante: 1 de la EASYGIFTS, 1 de la MACMA, 1 de la MIDOCEAN, apoi al 2-lea de la EASYGIFTS, al 2-lea de la MACMA
- NICIODATĂ nu pune mai multe produse de la același furnizor dacă ai opțiuni de la alți furnizori nefolosiți
- Apelează search_products O SINGURĂ DATĂ, apoi create_quote cu produsele alese — doar 2 tool calls total

BUGET:
- Bugetul clientului este ÎNTOTDEAUNA în LEI (RON) dacă nu specifică altfel
- Cursul valutar actual: 1 EUR = {eur_ron} RON — folosește ACEST curs pentru conversie
- Convertește MEREU bugetul din LEI în EUR: buget_eur = buget_lei / {eur_ron}
- Folosește OBLIGATORIU AMBELE filtre: min_price = buget_eur * 0.7 și max_price = buget_eur * 1.1
- Scopul: produse cu preț CÂT MAI APROAPE de buget, NU cele mai ieftine
- Exemplu: "buget 150 lei" → 150 / {eur_ron} = {ex_budget} EUR → min_price={ex_min}, max_price={ex_max}
- Dacă nu găsești suficiente rezultate, lărgește: min_price = buget_eur * 0.5
- IMPORTANT: NICIODATĂ nu returna produse mult sub buget — clientul vrea calitate la prețul specificat

PREȚURI:
- Prețul afișat include deja marja furnizorului + marja generală (marjă globală: {margin}%)
- Afișează prețurile MEREU în AMBELE monede: EUR și LEI
- Pentru conversie: preț_lei = preț_eur × {eur_ron}
- Menționează costul personalizării separat
- Recomandă DOAR produse care sunt în stoc (stock > 0)

LIMBA:
- Prezintă ÎNTOTDEAUNA numele și descrierile produselor în ROMÂNĂ
- Dacă produsul are nume/descriere în engleză, traduce-le tu în română când le prezinți
- Păstrează numele de brand/model netraduse (ex: "Classic-T", "BENTE COLOUR")
- Traducerea se face automat la adăugarea în ofertă, dar prezintă și tu produsele în română

OCAZII COMUNE:
- Conferințe/evenimente: pixuri, badge-uri, agende, USB-uri, lanyard-uri
- Cadouri Crăciun: căni, pături, seturi birou, termosuri
- 8 Martie: cosmetice, genți cosmetice, căni, agende
- Team building: tricouri, șepci, bidoane, rucsacuri, prosoape
- Cadouri corporate: seturi premium, powerbank-uri, articole piele, termosuri
"""


def _build_system_prompt(eur_ron: float, margin: float) -> str:
    """Build the system prompt with live exchange rate and margin from DB settings."""
    ex_budget = round(150 / eur_ron)
    ex_min = round(ex_budget * 0.7)
    ex_max = round(ex_budget * 1.1)
    return _SYSTEM_PROMPT_TEMPLATE.format(
        eur_ron=eur_ron,
        margin=margin,
        ex_budget=ex_budget,
        ex_min=ex_min,
        ex_max=ex_max,
    )

# ---------------------------------------------------------------------------
# Claude tool definitions
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "search_products",
        "description": (
            "Caută produse promoționale în catalogul de ~80.000 produse (EASYGIFTS, MACMA, MIDOCEAN). "
            "Returnează produse grupate — un rezultat per model, nu per culoare. "
            "Suportă fuzzy matching — nu trebuie potrivire exactă."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Termen de căutare text liber (ex: 'tricouri polo', 'pixuri metalice', 'căni ceramice', 'rucsac laptop'). Suportă fuzzy matching."
                },
                "category": {
                    "type": "string",
                    "description": "Filtru furnizor: 'EASYGIFTS', 'MACMA' sau 'MIDOCEAN'. Lasă gol pentru toți furnizorii."
                },
                "subcategory": {
                    "type": "string",
                    "description": "Subcategorie exactă din catalog (ex: 'Tricou', 'Tricou polo', 'Sticle de baut', 'Pixuri din plastic', 'Umbrele'). Folosește doar dacă știi subcategoria exactă."
                },
                "min_price": {
                    "type": "number",
                    "description": "Preț minim EUR (preț de bază, fără marjă)"
                },
                "max_price": {
                    "type": "number",
                    "description": "Preț maxim EUR (preț de bază, fără marjă)"
                },
                "color": {
                    "type": "string",
                    "description": "Culoare dorită (ex: 'roșu', 'albastru', 'blue', 'White'). Funcționează cu orice limbă."
                },
                "limit": {
                    "type": "integer",
                    "description": "Număr maxim rezultate (implicit 15, maxim 30). Crește la 20-30 dacă utilizatorul cere 'variante' sau 'opțiuni'."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_product_details",
        "description": "Obține detaliile complete ale unui produs: specificații, opțiuni personalizare, stoc, imagini.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "ID-ul produsului"
                }
            },
            "required": ["product_id"]
        }
    },
    {
        "name": "calculate_quote_price",
        "description": "Calculează prețul total al unei oferte cu marje și costuri de personalizare.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Lista de produse pentru ofertă",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "string"},
                            "printing_method": {
                                "type": "string",
                                "description": "Metoda de personalizare (ex: 'Tampografie', 'Serigrafie', 'Gravură laser')"
                            }
                        },
                        "required": ["product_id"]
                    }
                }
            },
            "required": ["items"]
        }
    },
    {
        "name": "create_quote",
        "description": "Creează o ofertă oficială în sistem. Folosește IMEDIAT după căutare — nu aștepta confirmarea clientului. Cantitatea implicită este 1 bucată per produs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_name": {
                    "type": "string",
                    "description": "Numele clientului (poate fi gol dacă nu e cunoscut)"
                },
                "client_email": {
                    "type": "string",
                    "description": "Email-ul clientului"
                },
                "items": {
                    "type": "array",
                    "description": "Produse pentru ofertă. NU trimite quantity decât dacă clientul a specificat explicit o cantitate.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "string"},
                            "quantity": {"type": "integer", "description": "Doar dacă clientul specifică explicit cantitatea. Implicit = 1."},
                            "printing_method": {"type": "string"}
                        },
                        "required": ["product_id"]
                    }
                },
                "notes": {
                    "type": "string",
                    "description": "Note adiționale pentru ofertă"
                }
            },
            "required": ["client_name", "items"]
        }
    },
    {
        "name": "suggest_products_for_occasion",
        "description": "Sugerează produse potrivite pentru o ocazie specifică și buget. Caută în catalog produse relevante pentru ocazie.",
        "input_schema": {
            "type": "object",
            "properties": {
                "occasion": {
                    "type": "string",
                    "description": "Ocazia (ex: 'aniversare firmă', '8 martie', 'crăciun', 'conferință', 'team building')"
                },
                "budget_per_person": {
                    "type": "number",
                    "description": "Buget per persoană în EUR"
                },
                "quantity": {
                    "type": "integer",
                    "description": "Număr total de persoane/bucăți"
                },
                "gender": {
                    "type": "string",
                    "enum": ["mixed", "male", "female"],
                    "description": "Genul destinatarilor (implicit 'mixed')"
                }
            },
            "required": ["occasion", "budget_per_person", "quantity"]
        }
    }
]

# ---------------------------------------------------------------------------
# Occasion → search queries mapping
# ---------------------------------------------------------------------------
OCCASION_QUERIES: dict[str, list[str]] = {
    "conferință": ["pixuri metalice", "agenda caiet", "badge lanyard", "USB stick", "rucsac"],
    "conferinta": ["pixuri metalice", "agenda caiet", "badge lanyard", "USB stick", "rucsac"],
    "crăciun": ["cana ceramica", "patura polar", "set birou", "termos", "lumanare"],
    "craciun": ["cana ceramica", "patura polar", "set birou", "termos", "lumanare"],
    "8 martie": ["cosmetice", "geanta cosmetica", "cana", "agenda", "prosop"],
    "zi nastere": ["cana personalizata", "tricou", "set cadou", "powerbank"],
    "aniversare": ["set premium", "powerbank", "ceas", "termos metalic"],
    "team building": ["tricou", "sapca", "sticla sport bidon", "rucsac", "prosop"],
    "cadou corporate": ["set premium", "powerbank", "agenda piele", "termos", "ceas"],
    "paște": ["cana", "ciocolata", "set cadou", "patura", "lumanare"],
    "paste": ["cana", "ciocolata", "set cadou", "patura", "lumanare"],
}


# ---------------------------------------------------------------------------
# Helper: enrich Meilisearch hit for AI/card display
# ---------------------------------------------------------------------------
def _enrich_hit(hit: dict, global_margin: float, int_margins: dict[str, float] | None = None) -> dict:
    """Convert a Meilisearch hit into a product card dict with sell price."""
    base_price = hit.get("base_price", 0)
    iid = hit.get("integration_id", "")
    supplier_margin = (int_margins or {}).get(iid, 0)
    effective_margin = supplier_margin + global_margin
    sell_price = round(base_price * (1 + effective_margin / 100), 2)

    colors = hit.get("colors", [])
    if isinstance(colors, list):
        color_names = [c.get("name", "") for c in colors if isinstance(c, dict) and c.get("name")]
    else:
        color_names = []

    return {
        "id": hit.get("id", ""),
        "supplier_code": hit.get("supplier_code", ""),
        "name": hit.get("name", ""),
        "description": hit.get("description", ""),
        "short_description": hit.get("short_description", ""),
        "category": hit.get("category", ""),
        "base_price": base_price,
        "sell_price": sell_price,
        "currency": hit.get("currency", "EUR"),
        "image_url": hit.get("primary_image", ""),
        "primary_image": hit.get("primary_image", ""),
        "sku": hit.get("external_id", ""),
        "color_names": color_names[:10],
        "colors": colors[:10] if isinstance(colors, list) else [],
        "material": (hit.get("specifications") or {}).get("material", ""),
        "size": (hit.get("specifications") or {}).get("size", ""),
        "print_area": (hit.get("specifications") or {}).get("print_area", ""),
        "customizable": bool(hit.get("printing_options")),
        "min_quantity": hit.get("min_order_qty", 1),
        "min_order_qty": hit.get("min_order_qty", 1),
        "stock": hit.get("stock", 0),
    }


# ---------------------------------------------------------------------------
# Tool execution handlers
# ---------------------------------------------------------------------------
async def _exec_search_products(args: dict, db: AsyncSession, global_margin: float, int_margins: dict) -> dict:
    """Search products using Meilisearch with fuzzy matching and variant grouping."""
    query = args.get("query", "")
    category = args.get("category", "")
    subcategory = args.get("subcategory", "")
    min_price = args.get("min_price")
    max_price = args.get("max_price")
    color = args.get("color", "")
    limit = min(args.get("limit", 15), 30)

    filters = SearchFilters(
        query=query,
        category=category,
        subcategory=subcategory,
        min_price=min_price,
        max_price=max_price,
        color=color,
        in_stock=True,
        limit=limit,
        group_variants=True,
    )

    # meili_search is synchronous — run in thread pool
    result = await asyncio.to_thread(meili_search, filters)
    products = [_enrich_hit(hit, global_margin, int_margins) for hit in result.results]

    return {
        "products": products,
        "total_found": result.total,
    }


async def _exec_get_product_details(args: dict, db: AsyncSession, global_margin: float, int_margins: dict) -> dict:
    product_id = args["product_id"]
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return {"error": f"Produsul cu ID '{product_id}' nu a fost găsit."}

    supplier_margin = int_margins.get(product.integration_id or "", 0)
    effective_margin = supplier_margin + global_margin
    sell_price = round(product.base_price * (1 + effective_margin / 100), 2)
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "short_description": product.short_description,
        "category": product.category,
        "brand": product.brand,
        "base_price": product.base_price,
        "sell_price": sell_price,
        "currency": product.currency,
        "primary_image": product.primary_image,
        "images": product.images or [],
        "colors": product.colors or [],
        "specifications": product.specifications or {},
        "printing_options": product.printing_options or [],
        "stock": product.stock,
        "min_order_qty": product.min_order_qty,
    }


async def _exec_calculate_quote_price(args: dict, db: AsyncSession, global_margin: float, int_margins: dict) -> dict:
    items_input = args.get("items", [])
    calculated_items = []
    subtotal = 0.0

    for item_req in items_input:
        product_id = item_req["product_id"]
        quantity = item_req.get("quantity", 1)
        printing_method = item_req.get("printing_method", "")

        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product:
            calculated_items.append({"product_id": product_id, "error": "Produs negăsit"})
            continue

        supplier_margin = int_margins.get(product.integration_id or "", 0)
        effective_margin = supplier_margin + global_margin

        unit_cost = product.base_price
        printing_unit_cost = 0.0
        printing_setup_cost = 0.0

        # Find matching printing technique
        if printing_method:
            for opt in (product.printing_options or []):
                for tech in opt.get("techniques", []):
                    if tech.get("name", "").lower() == printing_method.lower():
                        printing_unit_cost = tech.get("unit_cost", 0.0)
                        printing_setup_cost = tech.get("setup_cost", 0.0)
                        break

        sell_price = round((unit_cost + printing_unit_cost) * (1 + effective_margin / 100), 2)
        line_total = round(sell_price * quantity + printing_setup_cost, 2)
        subtotal += line_total

        calculated_items.append({
            "product_id": product.id,
            "product_name": product.name,
            "quantity": quantity,
            "unit_cost": unit_cost,
            "printing_method": printing_method,
            "printing_unit_cost": printing_unit_cost,
            "printing_setup_cost": printing_setup_cost,
            "sell_price_per_unit": sell_price,
            "line_total": line_total,
        })

    return {
        "items": calculated_items,
        "subtotal": round(subtotal, 2),
        "currency": "EUR",
        "margin_percent": effective_margin if calculated_items else global_margin,
    }


async def _exec_create_quote(args: dict, db: AsyncSession, global_margin: float, int_margins: dict) -> dict:
    client_name = args.get("client_name", "")
    client_email = args.get("client_email", "")
    items_input = args.get("items", [])
    notes = args.get("notes", "")

    logger.info(f"create_quote called with {len(items_input)} items: {items_input}")

    quote_number = f"PQ-{uuid.uuid4().hex[:8].upper()}"
    quote = Quote(
        number=quote_number,
        client_name=client_name,
        client_email=client_email,
        margin_percent=global_margin,
        notes=notes,
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
    )

    not_found_ids = []
    for item_req in items_input:
        product_id = item_req.get("product_id", "")
        printing_method = item_req.get("printing_method", "")

        if not product_id:
            logger.warning("create_quote: item has no product_id, skipping")
            continue

        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()

        # Fallback: try by external_id (SKU) or supplier_code
        if not product:
            result = await db.execute(
                select(Product).where(
                    or_(
                        Product.external_id == product_id,
                        Product.supplier_code == product_id,
                    )
                ).limit(1)
            )
            product = result.scalar_one_or_none()

        # Fallback: try partial name match
        if not product:
            result = await db.execute(
                select(Product).where(
                    Product.name.ilike(f"%{product_id}%"),
                    Product.is_active == True,
                ).order_by(Product.stock.desc()).limit(1)
            )
            product = result.scalar_one_or_none()

        if not product:
            logger.warning(f"create_quote: product not found by id/sku/name={product_id}")
            not_found_ids.append(product_id)
            continue

        logger.info(f"create_quote: found product '{product.name}' (id={product.id})")

        # Always start with quantity=1 — user adjusts from the panel
        quantity = item_req.get("quantity", 1)

        # Combined margin for this product's supplier
        supplier_margin = int_margins.get(product.integration_id or "", 0)
        effective_margin = supplier_margin + global_margin

        printing_unit_cost = 0.0
        printing_setup_cost = 0.0
        if printing_method:
            for opt in (product.printing_options or []):
                for tech in opt.get("techniques", []):
                    if tech.get("name", "").lower() == printing_method.lower():
                        printing_unit_cost = tech.get("unit_cost", 0.0)
                        printing_setup_cost = tech.get("setup_cost", 0.0)
                        break

        # Extract color info + size prices — aggregate from all variants with same supplier_code
        all_colors = list(product.colors or [])
        size_prices = []
        if product.supplier_code:
            variant_rows = await db.execute(
                select(Product.colors, Product.base_price, Product.specifications).where(
                    Product.supplier_code == product.supplier_code,
                    Product.is_active == True,
                )
            )
            seen = {c.get("name", "").lower().strip() for c in all_colors}
            size_price_map: dict[str, float] = {}
            for v_colors, v_price, v_specs in variant_rows:
                for c in (v_colors or []):
                    cname = c.get("name", "").lower().strip()
                    if cname and cname not in seen:
                        seen.add(cname)
                        all_colors.append(c)
                v_size = (v_specs or {}).get("size", "") if isinstance(v_specs, dict) else ""
                if v_size and v_price and v_price > 0:
                    if v_size not in size_price_map:
                        size_price_map[v_size] = v_price

            _SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL",
                           "6XL", "7XL", "8XL", "9XL", "10XL"]
            def _size_sort_key(s):
                try:
                    return _SIZE_ORDER.index(s.upper())
                except ValueError:
                    return 100
            if size_price_map:
                size_prices = [
                    {"size": sz, "price": round(p, 4)}
                    for sz, p in sorted(size_price_map.items(), key=lambda x: _size_sort_key(x[0]))
                ]

        color_names = [c.get("name", "") for c in all_colors if c.get("name")]
        product_color = item_req.get("color", color_names[0] if color_names else "")
        product_size = (product.specifications or {}).get("size", "")

        # Prefer the color-specific image if one exists for the chosen colour
        product_image = product.primary_image or ""
        if product_color:
            target = product_color.lower().strip()
            for c in all_colors:
                if str(c.get("name", "")).lower().strip() == target:
                    c_img = str(c.get("image", "") or "").strip()
                    if c_img:
                        product_image = c_img
                    break

        # Translate product name/description to Romanian if needed
        translated_name, translated_desc = await translate_to_romanian(
            product.name, product.description or ""
        )

        item = QuoteItem(
            product_id=product.id,
            product_name=translated_name,
            product_description=translated_desc,
            product_sku=product.external_id or "",
            product_image=product_image,
            product_color=product_color,
            product_colors=all_colors,
            product_size=product_size,
            size_prices=size_prices,
            quantity=quantity,
            unit_price=product.base_price,
            margin_percent=effective_margin,
            printing_method=printing_method,
            printing_cost=printing_unit_cost,
            printing_setup=printing_setup_cost,
        )
        item.calculate()
        quote.items.append(item)

    quote.recalculate()
    db.add(quote)
    await db.commit()
    await db.refresh(quote)

    result = {
        "quote_id": quote.id,
        "quote_number": quote.number,
        "client_name": quote.client_name,
        "total": quote.total,
        "currency": quote.currency,
        "items_count": len(quote.items),
        "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
        "message": f"Oferta {quote.number} a fost creată cu succes!",
    }

    if not_found_ids:
        result["warning"] = f"Produsele cu ID-urile {not_found_ids} nu au fost găsite în catalog."
    if len(quote.items) == 0:
        result["error"] = "Nu s-a putut adăuga niciun produs în ofertă. Verifică ID-urile produselor."

    logger.info(f"create_quote result: items_count={len(quote.items)}, not_found={not_found_ids}")
    return result


async def _exec_suggest_for_occasion(args: dict, db: AsyncSession, global_margin: float, int_margins: dict) -> dict:
    """Suggest products for a specific occasion using Meilisearch queries."""
    occasion = args.get("occasion", "").lower()
    budget = args.get("budget_per_person", 100.0)
    quantity = args.get("quantity", 50)

    # Find matching occasion queries
    queries = []
    for key, q_list in OCCASION_QUERIES.items():
        if key in occasion:
            queries = q_list
            break

    # Fallback: use occasion text as search query
    if not queries:
        queries = [occasion]

    # Search for each query and collect unique results
    # Use a rough base_price estimate (reverse margin)
    max_base_price = budget / (1 + global_margin / 100) if global_margin > 0 else budget
    min_base_price = max_base_price * 0.7  # At least 70% of budget — find closest match
    all_products: list[dict] = []
    seen_ids: set[str] = set()

    for q in queries[:5]:  # Max 5 queries to limit API calls
        filters = SearchFilters(
            query=q,
            min_price=min_base_price,
            max_price=max_base_price,
            in_stock=True,
            limit=4,
            group_variants=True,
        )
        try:
            result = await asyncio.to_thread(meili_search, filters)
            for hit in result.results:
                pid = hit.get("id", "")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_products.append(_enrich_hit(hit, global_margin, int_margins))
        except Exception as e:
            logger.warning(f"Occasion search for '{q}' failed: {e}")

    return {
        "occasion": occasion,
        "budget_per_person": budget,
        "quantity": quantity,
        "suggestions": all_products[:15],
        "total_found": len(all_products),
    }


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------
TOOL_HANDLERS = {
    "search_products": _exec_search_products,
    "get_product_details": _exec_get_product_details,
    "calculate_quote_price": _exec_calculate_quote_price,
    "create_quote": _exec_create_quote,
    "suggest_products_for_occasion": _exec_suggest_for_occasion,
}


# ---------------------------------------------------------------------------
# Main chat processor with streaming SSE
# ---------------------------------------------------------------------------
async def process_chat_message(
    message: str,
    conversation_history: list[ChatMessage],
    quote_id: str | None,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Process a chat message using Claude with tool use, yielding SSE events."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Load margin + exchange rate from DB settings
    db_settings = await load_settings_dict(db)
    global_margin = get_setting_float(db_settings, "margin_percent", settings.default_margin_percent)
    eur_ron = get_setting_float(db_settings, "exchange_rate_eur_ron", 4.97)

    # Load per-supplier margins
    from app.models.integration import Integration
    int_result = await db.execute(select(Integration.id, Integration.default_margin))
    int_margins = {r[0]: (r[1] or 0.0) for r in int_result.all()}

    # Build system prompt with live exchange rate and margin
    system_prompt = _build_system_prompt(eur_ron=eur_ron, margin=global_margin)

    # Build messages array
    messages = [{"role": m.role, "content": m.content} for m in conversation_history]
    messages.append({"role": "user", "content": message})

    try:
        # ---- Initial Claude call (may request tool use) ----
        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        # ---- Process response, handling tool use loop ----
        tool_round = 0
        MAX_TOOL_ROUNDS = 4  # Prevent excessive looping (search + quote + maybe 2 more)
        while response.stop_reason == "tool_use" and tool_round < MAX_TOOL_ROUNDS:
            tool_round += 1
            # Collect all content blocks from assistant response
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

                    # Execute the tool
                    handler = TOOL_HANDLERS.get(tool_name)
                    if handler:
                        try:
                            tool_result = await handler(tool_input, db, global_margin, int_margins)
                        except Exception as e:
                            logger.error(f"Tool {tool_name} error: {e}")
                            tool_result = {"error": str(e)}
                    else:
                        tool_result = {"error": f"Unknown tool: {tool_name}"}

                    # Send product cards if search returned products
                    if tool_name in ("search_products", "suggest_products_for_occasion"):
                        products = tool_result.get("products") or tool_result.get("suggestions", [])
                        if products:
                            yield _sse({"type": "products", "content": products})

                    # Send quote update if quote was created
                    if tool_name == "create_quote" and "quote_id" in tool_result:
                        yield _sse({"type": "quote_update", "content": tool_result})

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    })

            # Continue the conversation with tool results
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

            response = await client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            )

        # ---- Final response (stop_reason == "end_turn") ----
        for block in response.content:
            if block.type == "text" and block.text:
                yield _sse({"type": "text", "content": block.text})

        yield _sse({"type": "done"})

    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        yield _sse({"type": "error", "content": f"Eroare AI: {e.message}"})
        yield _sse({"type": "done"})
    except Exception as e:
        logger.error(f"Chat processing error: {e}")
        yield _sse({"type": "error", "content": "A apărut o eroare internă. Încearcă din nou."})
        yield _sse({"type": "done"})


def _sse(payload: dict) -> str:
    """Format a dict as an SSE data line."""
    return json.dumps(payload, ensure_ascii=False)
