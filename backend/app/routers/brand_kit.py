"""
Brand Kit Generator (PACKMAN) — API endpoints.

Uses existing Meilisearch product search with color_groups facets.
Logo upload, mockup zone overrides, PDF generation, save/load.
"""
import base64
import io
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models.brand_kit import BrandKit, MockupZoneOverride
from app.schemas.chat import ChatMessage
from app.services.search_service import search_products, SearchFilters
from app.services.packman_ai_service import process_packman_message

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = Path("uploads/brand-kit/logos")
PDF_DIR = Path("uploads/brand-kit/pdfs")


# ── Schemas ──────────────────────────────────────────

class MockupZoneIn(BaseModel):
    product_sku: str
    supplier: str
    x_percent: float = 25.0
    y_percent: float = 25.0
    width_percent: float = 40.0
    height_percent: float = 30.0
    opacity: float = 0.9
    blend_mode: str = "multiply"
    rotation: float = 0.0
    warp: str = "none"
    warp_intensity: float = 0.0


class BrandKitIn(BaseModel):
    name: str = ""
    client_name: str = ""
    logo_path: str = ""
    colors: list[str] = []
    selected_products: list[dict] = []
    mockup_overrides: dict = {}


class PdfProductIn(BaseModel):
    sku: str
    supplier: str
    name: str
    mockup_base64: str = ""
    image_url: str = ""
    colors: list[str] = []
    print_method: str = ""
    print_area: str = ""
    print_dimensions: str = ""
    min_order: int = 1


class GeneratePdfIn(BaseModel):
    client_name: str
    company_id: str = ""
    selected_products: list[PdfProductIn]
    logo_base64: str = ""


class PackmanChatIn(BaseModel):
    message: str
    conversation_history: list[ChatMessage] = []
    brand_colors: list[str] = []


# ── PACKMAN AI Chat ──────────────────────────────────

@router.post("/chat")
async def packman_chat(request: PackmanChatIn, db: AsyncSession = Depends(get_db)):
    """
    PACKMAN AI chat endpoint with Server-Sent Events streaming.

    Sends events:
    - type: "text"       → AI text response chunk
    - type: "products"   → Product cards with print area data
    - type: "tool_call"  → Tool being executed (for UI indicators)
    - type: "error"      → Error message
    - type: "done"       → Stream complete
    """
    return EventSourceResponse(
        process_packman_message(
            message=request.message,
            conversation_history=request.conversation_history,
            brand_colors=request.brand_colors,
            db=db,
        )
    )


# ── Product Search (reuses Meilisearch) ──────────────

@router.get("/products")
async def search_brand_kit_products(
    colors: str = Query("", description="Comma-separated color groups (Romanian): Roșu,Negru"),
    category: str = Query("", description="Supplier category filter"),
    category_group: str = Query("", description="Category group filter"),
    min_stock: int = Query(0, ge=0),
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Search products by color group(s) for brand kit.
    Uses existing Meilisearch color_groups facet.
    Returns products with printing_options data for mockup positioning.
    """
    import asyncio
    import time
    from app.models.product import Product
    from app.routers.products import _get_margin, _get_eur_ron, _get_integration_margins

    color_list = [c.strip() for c in colors.split(",") if c.strip()] if colors else []

    results = []
    total = 0
    facets = {}

    # Search — pass pagination directly to Meilisearch
    if len(color_list) == 1:
        # Single color: let Meilisearch handle pagination directly (fast)
        filters = SearchFilters(
            color_group=color_list[0],
            category=category,
            category_group=category_group,
            in_stock=min_stock > 0,
            page=page,
            limit=limit,
            group_variants=True,
            sort_by="name_asc",
        )
        try:
            result = await asyncio.to_thread(search_products, filters)
            results = result.results
            total = result.total
            facets = result.facets
        except Exception as e:
            logger.warning(f"Brand kit search error: {e}")
    elif color_list:
        # Multiple colors: merge results from each color group, paginate server-side
        seen_ids: set[str] = set()
        for color_group in color_list:
            filters = SearchFilters(
                color_group=color_group,
                category=category,
                category_group=category_group,
                in_stock=min_stock > 0,
                page=1,
                limit=500,
                group_variants=True,
            )
            try:
                result = await asyncio.to_thread(search_products, filters)
                for p in result.results:
                    pid = p.get("id", "")
                    if pid not in seen_ids and p.get("stock", 0) >= min_stock:
                        seen_ids.add(pid)
                        results.append(p)
                if not facets:
                    facets = result.facets
            except Exception as e:
                logger.warning(f"Brand kit search error for {color_group}: {e}")
        results.sort(key=lambda p: p.get("stock", 0), reverse=True)
        total = len(results)
        start = (page - 1) * limit
        results = results[start:start + limit]
    else:
        # No color filter — show all
        filters = SearchFilters(
            category=category,
            category_group=category_group,
            in_stock=min_stock > 0,
            page=page,
            limit=limit,
            group_variants=True,
        )
        try:
            result = await asyncio.to_thread(search_products, filters)
            results = result.results
            facets = result.facets
            total = result.total
        except Exception as e:
            logger.warning(f"Brand kit search error: {e}")

    page_results = results

    # Enrich with printing_options and images from DB
    product_ids = [p["id"] for p in page_results if p.get("id")]
    printing_map: dict[str, list] = {}
    images_map: dict[str, list] = {}
    if product_ids:
        q = select(Product.id, Product.printing_options, Product.images).where(
            Product.id.in_(product_ids)
        )
        rows = await db.execute(q)
        for row in rows.all():
            printing_map[row[0]] = row[1] or []
            images_map[row[0]] = row[2] or []

    # Collect ALL variant images per supplier_code (for image navigation)
    # Also find color-matched variant image if color filter is active
    from app.services.search_service import _color_to_groups, _strip_diacritics
    active_color_groups = {_strip_diacritics(c) for c in color_list} if color_list else set()
    color_image_map: dict[str, tuple[str, str]] = {}
    variant_images_map: dict[str, list[str]] = {}  # supplier_code -> [img_url, ...]

    supplier_codes = list({
        p.get("supplier_code", "") or p.get("external_id", "")
        for p in page_results if p.get("supplier_code") or p.get("external_id")
    })
    if supplier_codes:
        variant_q = select(
            Product.supplier_code, Product.primary_image, Product.colors, Product.images
        ).where(
            Product.supplier_code.in_(supplier_codes),
            Product.is_active == True,
        )
        variant_rows = await db.execute(variant_q)
        for scode, vimg, vcolors, vimages in variant_rows.all():
            # Collect all variant images
            if scode not in variant_images_map:
                variant_images_map[scode] = []
            if vimg and vimg not in variant_images_map[scode]:
                variant_images_map[scode].append(vimg)
            for vi in (vimages or []):
                if vi and vi not in variant_images_map[scode]:
                    variant_images_map[scode].append(vi)

            # Color-matched image
            if active_color_groups and scode not in color_image_map:
                if vcolors and isinstance(vcolors, list):
                    for vc in vcolors:
                        if not isinstance(vc, dict):
                            continue
                        vgroups = _color_to_groups(vc.get("name", ""))
                        if any(g in active_color_groups for g in vgroups):
                            color_image_map[scode] = (vimg or "", vc.get("hex", ""))
                            break

    # Build response with print_areas
    enriched = []
    for p in page_results:
        pid = p.get("id", "")
        scode = p.get("supplier_code", "") or p.get("external_id", "")
        printing_opts = printing_map.get(pid, [])
        print_areas = []
        for opt in printing_opts:
            w_mm = opt.get("max_width_mm", 0) or 0
            h_mm = opt.get("max_height_mm", 0) or 0
            # If top-level dimensions are 0, get from first technique
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
                "method": ", ".join(
                    t.get("name", "") for t in opt.get("techniques", [])
                ),
                "position_image": opt.get("position_image", ""),
            })

        # Use color-matched variant image if available
        img_url = p.get("primary_image") or p.get("image_url", "")
        color_hex = ""
        if scode in color_image_map:
            img_url, color_hex = color_image_map[scode]

        # Collect all available images for this product
        all_images: list[str] = []
        # Start with current image
        if img_url:
            all_images.append(img_url)
        # Add images from DB (this product's own images)
        for di in images_map.get(pid, []):
            if di and di not in all_images:
                all_images.append(di)
        # Add variant images (other color variants of same model)
        for vi in variant_images_map.get(scode, []):
            if vi and vi not in all_images:
                all_images.append(vi)

        enriched.append({
            "id": pid,
            "sku": scode,
            "name": p.get("name", ""),
            "supplier": p.get("category", ""),
            "category": p.get("subcategory") or p.get("category_group", ""),
            "color": ", ".join(p.get("color_names", [])[:3]),
            "color_hex": color_hex,
            "stock": p.get("stock", 0),
            "image_url": img_url,
            "images": all_images,
            "min_order": p.get("min_order_qty", 1),
            "print_areas": print_areas,
            "brand": p.get("brand", ""),
        })

    return {
        "results": enriched,
        "total": total,
        "page": page,
        "total_pages": max(1, (total + limit - 1) // limit),
        "facets": facets,
    }


# ── Color Stats ──────────────────────────────────────

@router.get("/colors")
async def get_color_stats():
    """Get available color groups with product counts from Meilisearch."""
    import asyncio
    try:
        filters = SearchFilters(page=1, limit=1, group_variants=True)
        result = await asyncio.to_thread(search_products, filters)
        color_groups = result.facets.get("color_groups", {})
        return [
            {"color_group": name, "product_count": count}
            for name, count in sorted(color_groups.items())
        ]
    except Exception as e:
        logger.warning(f"Color stats error: {e}")
        return []


# ── Logo Upload ──────────────────────────────────────

@router.post("/upload-logo")
async def upload_logo(file: UploadFile = File(...)):
    """Upload a PNG logo for brand kit. Returns the file path."""
    if not file.content_type or "png" not in file.content_type.lower():
        raise HTTPException(400, "Doar fișiere PNG sunt acceptate")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Fișierul depășește 5MB")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.png"
    filepath = UPLOAD_DIR / filename
    filepath.write_bytes(content)

    return {"path": str(filepath), "filename": filename}


@router.get("/logo/{filename}")
async def get_logo(filename: str):
    """Serve uploaded logo file."""
    filepath = UPLOAD_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, "Logo not found")
    return FileResponse(filepath, media_type="image/png")


# ── Mockup Zone Overrides ────────────────────────────

@router.get("/mockup-zone/{sku}")
async def get_mockup_zone(
    sku: str,
    supplier: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Get saved mockup zone override for a product."""
    q = select(MockupZoneOverride).where(MockupZoneOverride.product_sku == sku)
    if supplier:
        q = q.where(MockupZoneOverride.supplier == supplier)
    result = await db.execute(q)
    override = result.scalar_one_or_none()
    if not override:
        return None
    return {
        "product_sku": override.product_sku,
        "supplier": override.supplier,
        "x_percent": override.x_percent,
        "y_percent": override.y_percent,
        "width_percent": override.width_percent,
        "height_percent": override.height_percent,
        "opacity": override.opacity,
        "blend_mode": override.blend_mode,
        "rotation": override.rotation or 0.0,
        "warp": getattr(override, "warp", "none") or "none",
        "warp_intensity": getattr(override, "warp_intensity", 0.0) or 0.0,
    }


@router.put("/mockup-zone/{sku}")
async def save_mockup_zone(
    sku: str,
    data: MockupZoneIn,
    db: AsyncSession = Depends(get_db),
):
    """Save a manual mockup zone override."""
    q = select(MockupZoneOverride).where(
        MockupZoneOverride.product_sku == sku,
        MockupZoneOverride.supplier == data.supplier,
    )
    result = await db.execute(q)
    existing = result.scalar_one_or_none()

    if existing:
        existing.x_percent = data.x_percent
        existing.y_percent = data.y_percent
        existing.width_percent = data.width_percent
        existing.height_percent = data.height_percent
        existing.opacity = data.opacity
        existing.blend_mode = data.blend_mode
        existing.rotation = data.rotation
        existing.warp = data.warp
        existing.warp_intensity = data.warp_intensity
        existing.updated_at = datetime.now(timezone.utc)
    else:
        override = MockupZoneOverride(
            product_sku=sku,
            supplier=data.supplier,
            x_percent=data.x_percent,
            y_percent=data.y_percent,
            width_percent=data.width_percent,
            height_percent=data.height_percent,
            opacity=data.opacity,
            blend_mode=data.blend_mode,
            rotation=data.rotation,
            warp=data.warp,
            warp_intensity=data.warp_intensity,
        )
        db.add(override)

    await db.commit()
    return {"status": "ok"}


# ── PDF Generation ───────────────────────────────────

def _register_brandkit_fonts():
    """Register DejaVu TTF fonts for Romanian diacritics support."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    try:
        pdfmetrics.getFont("BKFont")
        return "BKFont", "BKFont-Bold"
    except KeyError:
        pass

    paths = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ]
    for regular, bold in paths:
        if os.path.isfile(regular) and os.path.isfile(bold):
            pdfmetrics.registerFont(TTFont("BKFont", regular))
            pdfmetrics.registerFont(TTFont("BKFont-Bold", bold))
            return "BKFont", "BKFont-Bold"

    return "Helvetica", "Helvetica-Bold"


def _logo_brightness(logo_base64: str) -> float:
    """Estimate average brightness of logo (0=black, 255=white)."""
    try:
        from PIL import Image
        logo_bytes = base64.b64decode(logo_base64.split(",")[-1])
        img = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
        # Sample center region, skip transparent pixels
        w, h = img.size
        cx, cy = w // 4, h // 4
        region = img.crop((cx, cy, w - cx, h - cy))
        pixels = list(region.getdata())
        total_brightness = 0
        count = 0
        for r, g, b, a in pixels:
            if a < 50:
                continue
            total_brightness += (r * 0.299 + g * 0.587 + b * 0.114)
            count += 1
        return total_brightness / count if count else 128
    except Exception:
        return 128  # default medium


async def _fetch_product_image(url: str) -> io.BytesIO | None:
    """Download a product image from URL for PDF embedding."""
    if not url:
        return None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and len(resp.content) > 100:
                return io.BytesIO(resp.content)
    except Exception:
        pass
    return None


@router.post("/generate-pdf")
async def generate_pdf(data: GeneratePdfIn, db: AsyncSession = Depends(get_db)):
    """Generate a modern presentation PDF — grid layout, adaptive colors."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    from reportlab.lib.utils import ImageReader
    from app.models.company import Company

    FONT, FONT_BOLD = _register_brandkit_fonts()

    # Load company data from DB
    company_name = "Demo Company SRL"
    company_email = "demo@example.com"
    company_phone = ""
    company_website = ""
    if data.company_id:
        result = await db.execute(select(Company).where(Company.id == data.company_id))
        company = result.scalar_one_or_none()
        if company:
            company_name = company.name or company_name
            company_email = company.email or company_email
            company_phone = company.phone or company_phone
            company_website = company.website or company_website

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_id = str(uuid.uuid4())
    pdf_path = PDF_DIR / f"{pdf_id}.pdf"

    width, height = A4
    c = canvas.Canvas(str(pdf_path), pagesize=A4)

    # Adaptive colors based on logo brightness
    brightness = _logo_brightness(data.logo_base64) if data.logo_base64 else 128
    if brightness < 100:
        # Dark logo → light/white pages
        cover_bg = HexColor("#FFFFFF")
        cover_text = HexColor("#1A1A2E")
        cover_sub = HexColor("#666666")
        accent = HexColor("#E74C3C")
        page_bg = HexColor("#FFFFFF")
        page_text = HexColor("#222222")
        page_sub = HexColor("#888888")
        header_bg = HexColor("#F5F5F5")
        header_text = HexColor("#333333")
        footer_text = HexColor("#AAAAAA")
    else:
        # Light/medium logo → dark pages
        cover_bg = HexColor("#1A1A2E")
        cover_text = HexColor("#FFFFFF")
        cover_sub = HexColor("#CCCCCC")
        accent = HexColor("#E74C3C")
        page_bg = HexColor("#FFFFFF")
        page_text = HexColor("#222222")
        page_sub = HexColor("#888888")
        header_bg = HexColor("#1A1A2E")
        header_text = HexColor("#FFFFFF")
        footer_text = HexColor("#AAAAAA")

    # Helper: draw logo on page
    def _draw_logo_small(canvas_obj, x, y, max_w_mm=25, max_h_mm=12):
        if not data.logo_base64:
            return
        try:
            logo_bytes = base64.b64decode(data.logo_base64.split(",")[-1])
            logo_img = ImageReader(io.BytesIO(logo_bytes))
            iw, ih = logo_img.getSize()
            s = min(max_w_mm * mm / iw, max_h_mm * mm / ih)
            canvas_obj.drawImage(logo_img, x, y, iw * s, ih * s, mask="auto")
        except Exception:
            pass

    # ── Page 1: Cover ──
    c.setFillColor(cover_bg)
    c.rect(0, 0, width, height, fill=True)

    # Accent line at top
    c.setFillColor(accent)
    c.rect(0, height - 3 * mm, width, 3 * mm, fill=True)

    # Logo centered
    logo_y = height / 2 + 30 * mm
    if data.logo_base64:
        try:
            logo_bytes = base64.b64decode(data.logo_base64.split(",")[-1])
            logo_img = ImageReader(io.BytesIO(logo_bytes))
            iw, ih = logo_img.getSize()
            max_w, max_h = 90 * mm, 70 * mm
            scale = min(max_w / iw, max_h / ih)
            dw, dh = iw * scale, ih * scale
            c.drawImage(logo_img, (width - dw) / 2, logo_y - dh / 2, dw, dh, mask="auto")
        except Exception:
            pass

    # Title
    c.setFillColor(cover_text)
    c.setFont(FONT_BOLD, 24)
    c.drawCentredString(width / 2, logo_y - 55 * mm, "Propunere Produse Promo\u021bionale")

    if data.client_name:
        c.setFont(FONT, 14)
        c.setFillColor(cover_sub)
        c.drawCentredString(width / 2, logo_y - 68 * mm,
                            f"Preg\u0103tit\u0103 pentru {data.client_name}")

    # Bottom
    c.setFillColor(cover_sub)
    c.setFont(FONT, 9)
    c.drawCentredString(width / 2, 25 * mm,
                        f"{company_name}  \u2022  {company_website}  \u2022  {datetime.now().strftime('%d.%m.%Y')}")

    # Accent line at bottom
    c.setFillColor(accent)
    c.rect(0, 0, width, 3 * mm, fill=True)
    c.showPage()

    # ── Product pages — grid layout (2 columns, 3 rows = 6 per page) ──
    products = data.selected_products
    COLS = 2
    ROWS = 3
    PER_PAGE = COLS * ROWS
    margin = 15 * mm
    header_h = 12 * mm
    footer_h = 12 * mm
    usable_w = width - 2 * margin
    usable_h = height - header_h - footer_h - 2 * margin
    cell_w = usable_w / COLS
    cell_h = usable_h / ROWS
    img_padding = 4 * mm

    # Pre-fetch all product images
    image_cache: dict[int, io.BytesIO | None] = {}
    for i, prod in enumerate(products):
        if prod.mockup_base64:
            try:
                img_bytes = base64.b64decode(prod.mockup_base64.split(",")[-1])
                image_cache[i] = io.BytesIO(img_bytes)
            except Exception:
                image_cache[i] = None
        elif prod.image_url:
            image_cache[i] = await _fetch_product_image(prod.image_url)
        else:
            image_cache[i] = None

    total_pages = max(1, (len(products) + PER_PAGE - 1) // PER_PAGE)

    for page_idx in range(total_pages):
        # White background
        c.setFillColor(page_bg)
        c.rect(0, 0, width, height, fill=True)

        # Header bar
        c.setFillColor(header_bg)
        c.rect(0, height - header_h, width, header_h, fill=True)
        c.setFillColor(header_text)
        c.setFont(FONT_BOLD, 8)
        if data.client_name:
            c.drawString(margin, height - header_h + 4 * mm,
                         f"BRAND KIT  \u2014  {data.client_name.upper()}")
        else:
            c.drawString(margin, height - header_h + 4 * mm, "BRAND KIT")
        c.setFont(FONT, 7)
        c.drawRightString(width - margin, height - header_h + 4 * mm,
                          f"Pagina {page_idx + 2}")

        # Accent line under header
        c.setFillColor(accent)
        c.rect(0, height - header_h - 0.5 * mm, width, 0.5 * mm, fill=True)

        # Draw products in grid
        page_products = products[page_idx * PER_PAGE: (page_idx + 1) * PER_PAGE]
        for cell_idx, prod in enumerate(page_products):
            prod_idx = page_idx * PER_PAGE + cell_idx
            col = cell_idx % COLS
            row = cell_idx // COLS

            cell_x = margin + col * cell_w
            cell_y = height - header_h - margin - (row + 1) * cell_h

            # Image area
            img_area_h = cell_h - 14 * mm  # leave room for name
            img_data = image_cache.get(prod_idx)
            if img_data:
                try:
                    img_data.seek(0)
                    img = ImageReader(img_data)
                    iw, ih = img.getSize()
                    max_img_w = cell_w - 2 * img_padding
                    max_img_h = img_area_h - 2 * img_padding
                    s = min(max_img_w / iw, max_img_h / ih)
                    dw, dh = iw * s, ih * s
                    ix = cell_x + (cell_w - dw) / 2
                    iy = cell_y + 14 * mm + (img_area_h - dh) / 2
                    c.drawImage(img, ix, iy, dw, dh, mask="auto")
                except Exception as e:
                    logger.warning(f"PDF grid image error: {e}")

            # Product name (below image, centered in cell)
            name = prod.name
            if len(name) > 35:
                name = name[:33] + "\u2026"
            c.setFillColor(page_text)
            c.setFont(FONT_BOLD, 8)
            c.drawCentredString(cell_x + cell_w / 2, cell_y + 7 * mm, name)

            # (no SKU displayed — clean layout)

        # Footer
        c.setFillColor(footer_text)
        c.setFont(FONT, 6)
        c.drawCentredString(width / 2, 5 * mm,
                            f"{company_name}  \u2022  {company_website}")
        # Small logo in footer
        _draw_logo_small(c, width - margin - 20 * mm, 3 * mm, 18, 8)

        c.showPage()

    # ── Last page: Contact ──
    c.setFillColor(cover_bg)
    c.rect(0, 0, width, height, fill=True)
    c.setFillColor(accent)
    c.rect(0, height - 3 * mm, width, 3 * mm, fill=True)
    c.rect(0, 0, width, 3 * mm, fill=True)

    c.setFillColor(cover_text)
    c.setFont(FONT_BOLD, 22)
    c.drawCentredString(width / 2, height / 2 + 25 * mm,
                        "V\u0103 mul\u021bumim!")

    c.setFont(FONT, 13)
    c.drawCentredString(width / 2, height / 2 + 10 * mm,
                        "Pentru pre\u021buri \u0219i comenzi:")

    c.setFont(FONT_BOLD, 14)
    c.setFillColor(accent)
    c.drawCentredString(width / 2, height / 2 - 8 * mm, company_email)

    y_contact = height / 2 - 24 * mm
    if company_phone:
        c.setFont(FONT, 12)
        c.setFillColor(cover_sub)
        c.drawCentredString(width / 2, y_contact, f"Tel: {company_phone}")
        y_contact -= 14 * mm

    c.setFont(FONT, 11)
    c.setFillColor(cover_sub)
    c.drawCentredString(width / 2, y_contact, company_website)

    # Logo
    if data.logo_base64:
        try:
            logo_bytes = base64.b64decode(data.logo_base64.split(",")[-1])
            logo_img = ImageReader(io.BytesIO(logo_bytes))
            iw, ih = logo_img.getSize()
            s = min(40 * mm / iw, 30 * mm / ih)
            dw, dh = iw * s, ih * s
            c.drawImage(logo_img, (width - dw) / 2, height / 2 + 45 * mm, dw, dh, mask="auto")
        except Exception:
            pass

    c.setFillColor(cover_sub)
    c.setFont(FONT, 8)
    c.drawCentredString(width / 2, 15 * mm,
                        f"\u00a9 {datetime.now().year} {company_name}")
    c.showPage()
    c.save()

    # Save brand kit reference
    kit = BrandKit(
        name=f"Kit {data.client_name}" if data.client_name else "Brand Kit",
        client_name=data.client_name,
        colors=[],
        selected_products=[p.model_dump() for p in data.selected_products],
        pdf_path=str(pdf_path),
    )
    db.add(kit)
    await db.commit()

    return {
        "pdf_url": f"/api/brand-kit/pdf/{pdf_id}.pdf",
        "brand_kit_id": kit.id,
    }


@router.get("/pdf/{filename}")
async def get_pdf(filename: str):
    """Serve generated PDF."""
    filepath = PDF_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, "PDF not found")
    return FileResponse(filepath, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/image-proxy")
async def image_proxy(url: str = Query(..., description="External image URL to proxy")):
    """Proxy external product images to avoid CORS issues in mockup canvas."""
    import httpx
    if not url.startswith("http"):
        raise HTTPException(400, "Invalid URL")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise HTTPException(502, "Failed to fetch image")
            content_type = resp.headers.get("content-type", "image/jpeg")
            from fastapi.responses import Response
            return Response(
                content=resp.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*",
                },
            )
    except httpx.HTTPError:
        raise HTTPException(502, "Failed to fetch image")


# ── Save/Load Brand Kits ─────────────────────────────

@router.get("/saved")
async def list_brand_kits(db: AsyncSession = Depends(get_db)):
    """List all saved brand kits."""
    result = await db.execute(
        select(BrandKit).order_by(BrandKit.created_at.desc())
    )
    kits = result.scalars().all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "client_name": k.client_name,
            "colors": k.colors or [],
            "product_count": len(k.selected_products or []),
            "pdf_path": k.pdf_path or "",
            "created_at": str(k.created_at) if k.created_at else "",
        }
        for k in kits
    ]


@router.get("/saved/{kit_id}")
async def get_brand_kit(kit_id: str, db: AsyncSession = Depends(get_db)):
    """Get a saved brand kit by ID."""
    result = await db.execute(select(BrandKit).where(BrandKit.id == kit_id))
    kit = result.scalar_one_or_none()
    if not kit:
        raise HTTPException(404, "Brand kit not found")
    return {
        "id": kit.id,
        "name": kit.name,
        "client_name": kit.client_name,
        "logo_path": kit.logo_path,
        "colors": kit.colors or [],
        "selected_products": kit.selected_products or [],
        "mockup_overrides": kit.mockup_overrides or {},
        "pdf_path": kit.pdf_path or "",
        "created_at": str(kit.created_at) if kit.created_at else "",
        "updated_at": str(kit.updated_at) if kit.updated_at else "",
    }


@router.post("/saved")
async def save_brand_kit(data: BrandKitIn, db: AsyncSession = Depends(get_db)):
    """Save a brand kit."""
    kit = BrandKit(
        name=data.name,
        client_name=data.client_name,
        logo_path=data.logo_path,
        colors=data.colors,
        selected_products=data.selected_products,
        mockup_overrides=data.mockup_overrides,
    )
    db.add(kit)
    await db.commit()
    return {"id": kit.id, "status": "saved"}


@router.delete("/saved/{kit_id}")
async def delete_brand_kit(kit_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a brand kit."""
    await db.execute(delete(BrandKit).where(BrandKit.id == kit_id))
    await db.commit()
    return {"status": "deleted"}
