import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.quote import Quote, QuoteItem
from app.models.product import Product
from app.models.company import Company
from app.schemas.quote import QuoteCreate, QuoteUpdate, QuoteItemUpdate, QuoteResponse, QuoteItemCreate
from app.services.pdf_service import generate_quote_pdf, generate_internal_pdf
from app.models.settings import load_settings_dict
from app.services.translation_service import translate_to_romanian

router = APIRouter()


def _strip_diacritics(s: str) -> str:
    """Lowercase + remove diacritics for case/diacritic-insensitive matching."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


_COMPANY_SUFFIXES = (
    " srl", " s.r.l.", " s.r.l", " sa", " s.a.", " s.a",
    " pfa", " ii", " i.i.", " ltd", " llc", " gmbh", " inc",
    " sca", " s.c.a.",
)


def _normalize_company(s: str) -> str:
    """Aggressive normalization for grouping/dedup of company names."""
    out = _strip_diacritics(s or "").strip()
    # Strip trailing punctuation around suffix
    while True:
        before = out
        for suf in _COMPANY_SUFFIXES:
            if out.endswith(suf):
                out = out[: -len(suf)].rstrip(",.; ").strip()
                break
        if out == before:
            break
    # Collapse whitespace
    out = " ".join(out.split())
    return out


@router.get("/clients")
async def list_clients(
    q: str | None = Query(None, description="Substring filter (case/diacritic-insensitive)"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Distinct client triples (name, company, email) from all quotes,
    ordered by most-recent use. For autocomplete on quote forms.
    Dedup keys are normalized (case/diacritic/suffix-insensitive).
    """
    stmt = select(
        Quote.client_name,
        Quote.client_company,
        Quote.client_email,
        Quote.created_at,
    ).order_by(Quote.created_at.desc())
    result = await db.execute(stmt)
    rows = result.all()

    needle = _strip_diacritics(q.strip()) if q and q.strip() else None

    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for name, company, email, _ in rows:
        name = (name or "").strip()
        company = (company or "").strip()
        email = (email or "").strip()
        # Skip empty + skip generic placeholder "Client"
        if not (name or company or email):
            continue
        key = (
            _normalize_company(company),
            _strip_diacritics(name),
            _strip_diacritics(email),
        )
        if key in seen:
            continue
        seen.add(key)

        if needle:
            haystack = _strip_diacritics(f"{name} {company} {email}")
            if needle not in haystack:
                continue

        out.append({
            "client_name": name,
            "client_company": company,
            "client_email": email,
        })
        if len(out) >= limit:
            break
    return out


@router.get("/", response_model=list[QuoteResponse])
async def list_quotes(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all quotes, optionally filtered by status."""
    stmt = select(Quote).order_by(Quote.created_at.desc())
    if status:
        stmt = stmt.where(Quote.status == status)
    result = await db.execute(stmt)
    quotes = result.scalars().all()

    # Resolve company names
    company_ids = {q.company_id for q in quotes if q.company_id}
    company_names: dict[str, str] = {}
    if company_ids:
        comp_result = await db.execute(select(Company).where(Company.id.in_(company_ids)))
        for c in comp_result.scalars().all():
            company_names[c.id] = c.name

    responses = []
    for q in quotes:
        resp = QuoteResponse.model_validate(q)
        resp.company_name = company_names.get(q.company_id or "", None)
        responses.append(resp)
    return responses


@router.post("/", response_model=QuoteResponse)
async def create_quote(data: QuoteCreate, db: AsyncSession = Depends(get_db)):
    """Create a new quote with optional items."""
    # Use provided company_id, or fall back to default company
    company_id = data.company_id
    if not company_id:
        default_result = await db.execute(
            select(Company).where(Company.is_default == True).limit(1)
        )
        default_company = default_result.scalar_one_or_none()
        if default_company:
            company_id = default_company.id

    quote_number = (data.number or "").strip() or f"PQ-{uuid.uuid4().hex[:8].upper()}"

    # Reject duplicate numbers PER COMPANY with a clear 400
    existing = await db.execute(
        select(Quote).where(
            Quote.number == quote_number,
            Quote.company_id == company_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Numărul ofertei '{quote_number}' există deja pentru această companie. Alege alt număr.",
        )

    # Snapshot pricing settings at creation so future PDF regenerations
    # stay stable even if admin changes EUR/RON rate or qty tiers later.
    db_settings = await load_settings_dict(db)
    try:
        snap_rate = float(db_settings.get("exchange_rate_eur_ron", "0")) or None
    except (ValueError, TypeError):
        snap_rate = None
    snap_tiers = (db_settings.get("quantity_tiers") or "100,200,300,500,1000").strip() or None
    try:
        snap_step = float(db_settings.get("quantity_discount_percent", "2") or 2)
    except (ValueError, TypeError):
        snap_step = 2.0

    quote = Quote(
        number=quote_number,
        company_id=company_id,
        client_name=data.client_name,
        client_email=data.client_email,
        client_company=data.client_company,
        client_phone=data.client_phone,
        notes=data.notes,
        margin_percent=data.margin_percent,
        currency=data.currency,
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        exchange_rate=snap_rate,
        quantity_tiers=snap_tiers,
        discount_step=snap_step,
        apply_tier_discount=True,  # new quotes use tier-discounted totals
    )

    for item_data in data.items:
        item = QuoteItem(
            product_id=item_data.product_id,
            product_name=item_data.product_name,
            product_sku=item_data.product_sku,
            product_image=item_data.product_image,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            margin_percent=item_data.margin_percent,
            printing_method=item_data.printing_method,
            printing_cost=item_data.printing_cost,
            printing_setup=item_data.printing_setup,
            customization_notes=item_data.customization_notes,
            notes=item_data.notes,
        )
        item.calculate()
        quote.items.append(item)

    quote.recalculate()
    db.add(quote)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Eroare la salvarea ofertei: {e}")
    await db.refresh(quote)
    return quote


@router.get("/{quote_id}", response_model=QuoteResponse)
async def get_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


@router.patch("/{quote_id}", response_model=QuoteResponse)
async def update_quote(quote_id: str, data: QuoteUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    update_data = data.model_dump(exclude_unset=True)

    # Check if number is being changed and ensure uniqueness PER COMPANY
    new_number = update_data.get("number", quote.number)
    new_company_id = update_data.get("company_id", quote.company_id)
    if (new_number != quote.number) or ("company_id" in update_data and new_company_id != quote.company_id):
        existing = await db.execute(
            select(Quote).where(
                Quote.number == new_number,
                Quote.company_id == new_company_id,
                Quote.id != quote_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Numărul de ofertă '{new_number}' există deja pentru această companie."
            )

    for field, value in update_data.items():
        setattr(quote, field, value)

    await db.commit()
    await db.refresh(quote)
    return quote


@router.post("/{quote_id}/items", response_model=QuoteResponse)
async def add_quote_item(
    quote_id: str, item_data: QuoteItemCreate, db: AsyncSession = Depends(get_db)
):
    """Add a single item to an existing quote."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    # Aggregate all variant colors from DB when product_id is provided
    all_colors = list(item_data.product_colors or [])
    product_color = item_data.product_color
    product_description = item_data.product_description
    product_image = item_data.product_image

    size_prices = []

    if item_data.product_id:
        prod_result = await db.execute(select(Product).where(Product.id == item_data.product_id))
        product = prod_result.scalar_one_or_none()
        if product:
            if not all_colors:
                all_colors = list(product.colors or [])
            if not product_image:
                product_image = product.primary_image or ""
            if not product_description:
                product_description = product.description or ""
            # Aggregate colors and size_prices from all variants with same supplier_code
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
                    # Collect size → price mapping
                    v_size = (v_specs or {}).get("size", "") if isinstance(v_specs, dict) else ""
                    if v_size and v_price and v_price > 0:
                        # Keep the most common (first encountered) price per size
                        if v_size not in size_price_map:
                            size_price_map[v_size] = v_price

                # Build sorted size_prices list
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

    # Translate product name/description to Romanian if needed
    translated_name, translated_desc = await translate_to_romanian(
        item_data.product_name, product_description or ""
    )

    # If client provided size_quantities, recompute quantity from their sum
    size_quantities = item_data.size_quantities or []
    effective_qty = item_data.quantity
    if size_quantities:
        total_qty = sum(int(sq.get("qty", 0) or 0) for sq in size_quantities)
        if total_qty > 0:
            effective_qty = total_qty

    item = QuoteItem(
        quote_id=quote_id,
        product_id=item_data.product_id,
        product_name=translated_name,
        product_description=translated_desc,
        product_sku=item_data.product_sku,
        product_image=product_image,
        product_color=product_color,
        product_colors=all_colors,
        size_prices=size_prices,
        size_quantities=size_quantities,
        quantity=effective_qty,
        unit_price=item_data.unit_price,
        margin_percent=item_data.margin_percent,
        printing_method=item_data.printing_method,
        printing_cost=item_data.printing_cost,
        printing_setup=item_data.printing_setup,
        customization_notes=item_data.customization_notes,
        notes=item_data.notes,
    )
    item.calculate()
    db.add(item)

    # Reload items and recalculate
    await db.flush()
    await db.refresh(quote)
    quote.recalculate()

    await db.commit()
    await db.refresh(quote)
    return quote


@router.patch("/{quote_id}/items/{item_id}", response_model=QuoteResponse)
async def update_quote_item(
    quote_id: str, item_id: str, data: QuoteItemUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a quote item (quantity, color, size, etc.)."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    item_result = await db.execute(
        select(QuoteItem).where(QuoteItem.id == item_id, QuoteItem.quote_id == quote_id)
    )
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    update_data = data.model_dump(exclude_unset=True)

    # When size_quantities is set, auto-calculate total quantity from sizes
    if "size_quantities" in update_data:
        sq = update_data["size_quantities"]
        if sq:
            total_qty = sum(s.get("qty", 0) for s in sq)
            if total_qty > 0:
                update_data["quantity"] = total_qty

    for field, value in update_data.items():
        setattr(item, field, value)
    item.calculate()

    await db.flush()
    await db.refresh(quote)
    quote.recalculate()
    await db.commit()
    await db.refresh(quote)
    return quote


@router.delete("/{quote_id}/items/{item_id}", response_model=QuoteResponse)
async def remove_quote_item(
    quote_id: str, item_id: str, db: AsyncSession = Depends(get_db)
):
    """Remove an item from a quote."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    item_result = await db.execute(
        select(QuoteItem).where(QuoteItem.id == item_id, QuoteItem.quote_id == quote_id)
    )
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    await db.delete(item)
    await db.flush()
    await db.refresh(quote)
    quote.recalculate()

    await db.commit()
    await db.refresh(quote)
    return quote


@router.put("/{quote_id}/confirm", response_model=QuoteResponse)
async def confirm_quote(quote_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    """Confirm a quote as a firm order, optionally selecting specific items."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    confirmed_item_ids = data.get("confirmed_items", [])

    if confirmed_item_ids:
        # Mark only specified items as confirmed
        for item in quote.items:
            item.is_confirmed = item.id in confirmed_item_ids
    else:
        # Confirm all items
        for item in quote.items:
            item.is_confirmed = True

    quote.status = "accepted"
    await db.commit()
    await db.refresh(quote)
    return quote


@router.put("/{quote_id}/unconfirm", response_model=QuoteResponse)
async def unconfirm_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Revert a confirmed quote back to draft."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    for item in quote.items:
        item.is_confirmed = False
    quote.status = "draft"
    await db.commit()
    await db.refresh(quote)
    return quote


@router.delete("/{quote_id}")
async def delete_quote(quote_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    await db.delete(quote)
    await db.commit()
    return {"detail": "Quote deleted"}


def _get_product_summary(product_names: list[str]) -> str:
    """Build a smart generic summary like 'Cani personalizate' or 'Pixuri personalizate'."""
    if not product_names:
        return "Produse"

    # Common product type keywords and their plural generic forms
    type_map = {
        "cană": "Cani personalizate",
        "cana": "Cani personalizate",
        "căni": "Cani personalizate",
        "cani": "Cani personalizate",
        "pix": "Pixuri personalizate",
        "pixuri": "Pixuri personalizate",
        "rucsac": "Rucsacuri personalizate",
        "geantă": "Genti personalizate",
        "geanta": "Genti personalizate",
        "tricou": "Tricouri personalizate",
        "sapca": "Sepci personalizate",
        "șapcă": "Sepci personalizate",
        "breloc": "Brelocuri personalizate",
        "agendă": "Agende personalizate",
        "agenda": "Agende personalizate",
        "caiet": "Caiete personalizate",
        "sticla": "Sticle personalizate",
        "sticlă": "Sticle personalizate",
        "termos": "Termosuri personalizate",
        "set": "Seturi personalizate",
        "umbrelă": "Umbrele personalizate",
        "umbrela": "Umbrele personalizate",
        "lanyard": "Lanyard-uri personalizate",
        "stick": "Stick-uri USB personalizate",
        "usb": "Stick-uri USB personalizate",
        "borseta": "Borsete personalizate",
    }

    # Check if all products share a common type
    for keyword, label in type_map.items():
        if all(keyword in name for name in product_names):
            return label

    # If products are mixed, use generic
    if len(product_names) == 1:
        # Single product — use first 3 words
        words = [w for w in product_names[0].split() if len(w) > 2][:3]
        return " ".join(words).title() if words else "Produse personalizate"

    return "Produse personalizate"


async def _get_settings_with_company(quote: Quote, db: AsyncSession) -> dict:
    """Load app settings and override company fields from quote's company."""
    db_settings = await load_settings_dict(db)

    company = None
    if quote.company_id:
        result = await db.execute(select(Company).where(Company.id == quote.company_id))
        company = result.scalar_one_or_none()

    # Fall back to default company if quote has no company assigned
    if not company:
        result = await db.execute(select(Company).where(Company.is_default == True).limit(1))
        company = result.scalar_one_or_none()

    if company:
            db_settings["company_name"] = company.name or db_settings.get("company_name", "")
            db_settings["company_cui"] = company.cui or ""
            db_settings["company_address"] = company.address or ""
            db_settings["company_phone"] = company.phone or ""
            db_settings["company_email"] = company.email or ""
            db_settings["company_website"] = company.website or ""
            db_settings["company_bank"] = company.bank or ""
            db_settings["company_iban"] = company.iban or ""
            if company.logo_url:
                db_settings["company_logo_url"] = company.logo_url

    return db_settings


@router.get("/{quote_id}/pdf")
async def download_quote_pdf(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Generate and download quote as PDF using DB settings."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    db_settings = await _get_settings_with_company(quote, db)
    pdf_bytes = generate_quote_pdf(quote, db_settings=db_settings)

    # Build descriptive filename: Oferta-Nr_Data_Client_Rezumat.pdf
    date_str = quote.created_at.strftime("%Y-%m-%d") if quote.created_at else datetime.now().strftime("%Y-%m-%d")

    # Client: prefer company name, skip generic "Client"
    client_name = quote.client_name if quote.client_name and quote.client_name.lower() != "client" else ""
    client = quote.client_company or client_name or "fara-client"

    # Smart product summary — find common type and add "personalizate"
    product_names = [item.product_name.lower() for item in quote.items if item.product_name]
    products_summary = _get_product_summary(product_names)

    def _sanitize(s: str) -> str:
        s = re.sub(r'[<>:"/\\|?*,]', '', s)
        s = s.strip().replace(' ', '_')
        return s[:40]

    filename = f"Oferta-{quote.number}_{date_str}_{_sanitize(client)}_{_sanitize(products_summary)}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{url_quote(filename)}"},
    )


@router.get("/{quote_id}/internal-pdf")
async def download_internal_pdf(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Generate internal order sheet with full cost breakdown."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    db_settings = await _get_settings_with_company(quote, db)
    pdf_bytes = generate_internal_pdf(quote, db_settings=db_settings)

    date_str = quote.created_at.strftime("%Y-%m-%d") if quote.created_at else datetime.now().strftime("%Y-%m-%d")
    client = quote.client_name or quote.client_company or "intern"

    def _sanitize(s: str) -> str:
        s = re.sub(r'[<>:"/\\|?*]', '', s)
        s = s.strip().replace(' ', '_')
        return s[:60]

    filename = f"Fisa_interna-{quote.number}_{date_str}_{_sanitize(client)}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{url_quote(filename)}"},
    )
