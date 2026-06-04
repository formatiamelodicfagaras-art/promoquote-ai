"""
PDF generation for quotes using ReportLab.
- Uses Arial TTF for full Romanian diacritics support (ă, î, ș, ț, â)
- Compact layout: multiple products per page
- Company header with configurable colors from DB settings
- Dual currency display (EUR + RON) using exchange rate from settings
"""
import io
import os
import logging
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    PageTemplate,
    Frame,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable, Flowable

from app.models.quote import Quote, QuoteItem

# ── Color name → hex fallback (for suppliers without hex data) ────────
_COLOR_HEX_FALLBACK: dict[str, str] = {
    "negru": "#1a1a1a", "black": "#1a1a1a",
    "alb": "#ffffff", "white": "#ffffff",
    "rosu": "#e53935", "roșu": "#e53935", "red": "#e53935",
    "albastru": "#1565c0", "blue": "#1565c0",
    "albastru regal": "#1a237e", "royal blue": "#1a237e",
    "albastru marin": "#0d47a1", "navy": "#0d47a1", "navy blue": "#0d47a1",
    "albastru marin francez": "#002395", "french navy": "#002395",
    "verde": "#2e7d32", "green": "#2e7d32",
    "verde inchis": "#1b5e20", "verde închis": "#1b5e20", "dark green": "#1b5e20",
    "galben": "#fdd835", "yellow": "#fdd835",
    "portocaliu": "#ef6c00", "orange": "#ef6c00",
    "roz": "#ec407a", "pink": "#ec407a",
    "mov": "#7b1fa2", "purple": "#7b1fa2", "violet": "#7b1fa2",
    "gri": "#9e9e9e", "grey": "#9e9e9e", "gray": "#9e9e9e",
    "gri deschis": "#bdbdbd", "light grey": "#bdbdbd",
    "gri inchis": "#616161", "gri închis": "#616161", "dark grey": "#616161",
    "gri piatra": "#78909c", "gri piatră": "#78909c", "stone grey": "#78909c",
    "maro": "#6d4c41", "brown": "#6d4c41",
    "bej": "#d7ccc8", "beige": "#d7ccc8",
    "turcoaz": "#00897b", "turquoise": "#00897b",
    "lime": "#aeea00",
    "argintiu": "#bdbdbd", "silver": "#bdbdbd",
    "auriu": "#ffc107", "gold": "#ffc107",
    "burgundy": "#880e4f",
    "kaki": "#827717", "khaki": "#827717",
    "coral": "#ff7043",
    "cyan": "#00bcd4",
    "charcoal": "#424242", "charcoal melange": "#616161",
}


def _resolve_color_hex(color: dict) -> str:
    """Get hex for a color, using fallback map if hex is missing."""
    h = (color.get("hex") or "").strip()
    if h and h != "#":
        return h
    name = (color.get("name") or "").strip().lower()
    return _COLOR_HEX_FALLBACK.get(name, "")


def _fmtn(value: float, decimals: int = 2) -> str:
    """Format number with European separators: 8.632,98"""
    formatted = f"{value:,.{decimals}f}"  # 8,632.98
    # Swap: comma→temp, dot→comma, temp→dot
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmtr(value: float) -> str:
    """Format RON value: 8.632,98 RON"""
    return f"{_fmtn(value)} RON"


def _fmte(value: float) -> str:
    """Format EUR value: 1.234,56 EUR"""
    return f"{_fmtn(value)} EUR"


# ── Color swatch flowable ─────────────────────────────────────────────

class ColorSwatches(Flowable):
    """Draw a row of colored circles for available product colors."""

    def __init__(self, color_list: list[dict], selected: str = "", size: float = 4 * mm, gap: float = 2 * mm, max_colors: int = 12):
        super().__init__()
        self.color_list = color_list[:max_colors]
        self.selected = selected.lower()
        self.size = size
        self.gap = gap
        self.width = len(self.color_list) * (size + gap)
        self.height = size + 2 * mm

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        r = self.size / 2
        x = r
        for c in self.color_list:
            hex_color = _resolve_color_hex(c)
            name = (c.get("name", "")).lower()
            if hex_color:
                try:
                    self.canv.setFillColor(colors.HexColor(hex_color))
                except Exception:
                    self.canv.setFillColor(colors.HexColor("#CCCCCC"))
            else:
                self.canv.setFillColor(colors.HexColor("#CCCCCC"))

            self.canv.setStrokeColor(colors.HexColor("#AAAAAA"))
            self.canv.setLineWidth(0.3)
            self.canv.circle(x, r + 1 * mm, r, fill=1, stroke=1)

            # Highlight selected color with a thicker border
            if name and name == self.selected:
                self.canv.setStrokeColor(colors.HexColor("#333333"))
                self.canv.setLineWidth(1.2)
                self.canv.circle(x, r + 1 * mm, r + 0.8, fill=0, stroke=1)

            x += self.size + self.gap

logger = logging.getLogger(__name__)

# ── Register TTF fonts for Romanian diacritics ──────────────────────
_fonts_registered = False

# Font search paths: Windows → Linux common locations
_FONT_SEARCH = [
    # Windows
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ariali.ttf"),
    # Linux - DejaVu (supports Romanian diacritics)
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    ),
    # Linux - Liberation Sans (metric-compatible with Arial)
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    ),
]

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"


def _register_fonts():
    global _fonts_registered, FONT, FONT_BOLD, FONT_ITALIC
    if _fonts_registered:
        return
    for regular, bold, italic in _FONT_SEARCH:
        if os.path.isfile(regular) and os.path.isfile(bold):
            try:
                pdfmetrics.registerFont(TTFont("SQFont", regular))
                pdfmetrics.registerFont(TTFont("SQFont-Bold", bold))
                if os.path.isfile(italic):
                    pdfmetrics.registerFont(TTFont("SQFont-Italic", italic))
                else:
                    pdfmetrics.registerFont(TTFont("SQFont-Italic", regular))
                pdfmetrics.registerFontFamily(
                    "SQFont", normal="SQFont", bold="SQFont-Bold", italic="SQFont-Italic"
                )
                FONT = "SQFont"
                FONT_BOLD = "SQFont-Bold"
                FONT_ITALIC = "SQFont-Italic"
                _fonts_registered = True
                logger.info("Registered TTF font from: %s", regular)
                return
            except Exception as e:
                logger.warning("Failed to register font %s: %s", regular, e)
    logger.warning("No TTF fonts found — using Helvetica (no diacritics support)")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


def _get_colors(db_settings: dict):
    """Extract color scheme from DB settings."""
    primary = db_settings.get("template_primary_color", "#C0392B")
    accent = db_settings.get("template_accent_color", "#1A56DB")
    return {
        "primary": colors.HexColor(primary),
        "accent": colors.HexColor(accent),
        "dark_text": colors.HexColor("#1A1A1A"),
        "gray_text": colors.HexColor("#555555"),
        "light_gray": colors.HexColor("#F5F5F5"),
        "white": colors.white,
    }


# ── Styles ────────────────────────────────────────────────────────────
def _build_styles(clr: dict):
    _register_fonts()
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "QuoteTitle", parent=styles["Normal"],
        fontName=FONT_BOLD, fontSize=22, textColor=clr["dark_text"],
        leading=26, spaceAfter=4 * mm,
    ))
    styles.add(ParagraphStyle(
        "QuoteInfo", parent=styles["Normal"],
        fontName=FONT, fontSize=9, textColor=clr["gray_text"], leading=13,
    ))
    styles.add(ParagraphStyle(
        "ProductTitle", parent=styles["Normal"],
        fontName=FONT_BOLD, fontSize=13, textColor=clr["dark_text"],
        leading=16, spaceAfter=1 * mm,
    ))
    styles.add(ParagraphStyle(
        "ProductDesc", parent=styles["Normal"],
        fontName=FONT, fontSize=9, textColor=clr["gray_text"], leading=12,
    ))
    styles.add(ParagraphStyle(
        "ProductCustom", parent=styles["Normal"],
        fontName=FONT_ITALIC, fontSize=9, textColor=clr["gray_text"], leading=12,
    ))
    styles.add(ParagraphStyle(
        "ProductPrice", parent=styles["Normal"],
        fontName=FONT_BOLD, fontSize=12, textColor=clr["accent"], leading=15,
    ))
    styles.add(ParagraphStyle(
        "ProductPriceSmall", parent=styles["Normal"],
        fontName=FONT, fontSize=8, textColor=clr["gray_text"], leading=11,
    ))
    styles.add(ParagraphStyle(
        "ProductMeta", parent=styles["Normal"],
        fontName=FONT, fontSize=8, textColor=clr["gray_text"], leading=11,
    ))
    styles.add(ParagraphStyle(
        "SummaryLabel", parent=styles["Normal"],
        fontName=FONT_BOLD, fontSize=11, textColor=clr["dark_text"], leading=15,
    ))
    styles.add(ParagraphStyle(
        "SummaryValue", parent=styles["Normal"],
        fontName=FONT_BOLD, fontSize=14, textColor=clr["accent"],
        leading=18, alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        "FooterText", parent=styles["Normal"],
        fontName=FONT, fontSize=7, textColor=clr["gray_text"], alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "NotesText", parent=styles["Normal"],
        fontName=FONT, fontSize=9, textColor=clr["gray_text"], leading=13,
    ))
    styles.add(ParagraphStyle(
        "NormalArial", parent=styles["Normal"],
        fontName=FONT, fontSize=9, textColor=clr["dark_text"], leading=12,
    ))

    return styles


# ── Header / Footer drawing ──────────────────────────────────────────
def _make_draw_header(db_settings: dict, clr: dict):
    """Return a header-drawing callback bound to the given settings."""
    company_name = db_settings.get("company_name", "Demo Company SRL")
    company_address = db_settings.get("company_address", "")
    company_phone = db_settings.get("company_phone", "")
    company_email = db_settings.get("company_email", "")
    company_logo = db_settings.get("company_logo_url", "")
    # Resolve API URLs to file paths (e.g. /api/settings/logo/xxx.png → uploads/logos/xxx.png)
    if company_logo and company_logo.startswith("/api/settings/logo/"):
        company_logo = os.path.join("uploads", "logos", company_logo.split("/")[-1])
    elif company_logo and company_logo.startswith("/api/brand-kit/logo/"):
        company_logo = os.path.join("uploads", "brand-kit", "logos", company_logo.split("/")[-1])

    def _draw_header(canvas, doc):
        _register_fonts()
        canvas.saveState()

        logo_w = 35 * mm
        has_logo = company_logo and os.path.isfile(company_logo)
        # Reserve space for logo so text doesn't overlap
        text_max_w = PAGE_W - 2 * MARGIN - (logo_w + 3 * mm if has_logo else 0)

        canvas.setFont(FONT_BOLD, 13)
        canvas.setFillColor(clr["dark_text"])
        name_text = company_name
        while canvas.stringWidth(name_text, FONT_BOLD, 13) > text_max_w and len(name_text) > 10:
            name_text = name_text[:len(name_text) - 4] + "..."
        canvas.drawString(MARGIN, PAGE_H - 14 * mm, name_text)

        canvas.setFont(FONT, 6.5)
        canvas.setFillColor(clr["gray_text"])
        info_parts = []
        if company_address:
            info_parts.append(company_address)
        if company_phone:
            info_parts.append(f"Tel: {company_phone}")
        if company_email:
            info_parts.append(company_email)
        if info_parts:
            info_text = "  |  ".join(info_parts)
            while canvas.stringWidth(info_text, FONT, 6.5) > text_max_w and len(info_text) > 20:
                info_text = info_text[:len(info_text) - 4] + "..."
            canvas.drawString(MARGIN, PAGE_H - 19 * mm, info_text)

        # Logo in far-right corner, above the header line
        if has_logo:
            try:
                canvas.drawImage(
                    company_logo,
                    PAGE_W - MARGIN - logo_w,  # flush to right margin
                    PAGE_H - 22 * mm,
                    width=logo_w, height=20 * mm,
                    preserveAspectRatio=True, anchor="ne",
                    mask="auto",
                )
            except Exception:
                logger.warning("Could not load logo: %s", company_logo)

        canvas.setStrokeColor(clr["primary"])
        canvas.setLineWidth(2)
        y_line = PAGE_H - 24 * mm
        canvas.line(MARGIN, y_line, PAGE_W - MARGIN, y_line)

        canvas.restoreState()

    return _draw_header


def _make_draw_footer(db_settings: dict, clr: dict):
    """Return a footer-drawing callback bound to the given settings."""
    company_email = db_settings.get("company_email", "")
    footer_text = db_settings.get("template_footer_text", "")

    def _draw_footer(canvas, doc):
        _register_fonts()
        canvas.saveState()

        y = 10 * mm
        canvas.setFont(FONT, 7)
        canvas.setFillColor(clr["gray_text"])

        canvas.setStrokeColor(colors.HexColor("#DDDDDD"))
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, y + 5 * mm, PAGE_W - MARGIN, y + 5 * mm)

        left_text = f"Generat de PromoQuote AI"
        if company_email:
            left_text += f"  |  {company_email}"
        canvas.drawString(MARGIN, y, left_text)
        canvas.drawRightString(PAGE_W - MARGIN, y, f"Pagina {doc.page}")

        if footer_text:
            canvas.setFont(FONT, 6.5)
            canvas.drawCentredString(PAGE_W / 2, y - 4 * mm, footer_text)

        canvas.restoreState()

    return _draw_footer


# ── Product image helper ──────────────────────────────────────────────
def _compress_image(raw_bytes: bytes, max_px: int = 400, quality: int = 70) -> io.BytesIO:
    """Resize and compress an image for PDF embedding.
    Returns a JPEG BytesIO, typically 10-40KB instead of 200-800KB.
    """
    from PIL import Image as PILImage
    img = PILImage.open(io.BytesIO(raw_bytes))
    if img.mode in ("RGBA", "P", "LA"):
        bg = PILImage.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    # Resize if larger than max_px
    w, h = img.size
    if w > max_px or h > max_px:
        ratio = min(max_px / w, max_px / h)
        img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    return buf


def _get_product_image(item: QuoteItem, max_w: float, max_h: float):
    image_url = item.product_image or ""
    if not image_url:
        return None

    raw_bytes: bytes | None = None

    # Handle uploaded product images (/api/settings/product-image/...)
    if image_url.startswith("/api/settings/product-image/"):
        filename = image_url.split("/")[-1]
        from pathlib import Path
        local_path = Path("uploads/products") / filename
        if local_path.exists():
            try:
                raw_bytes = local_path.read_bytes()
            except Exception:
                pass
        if not raw_bytes:
            return None

    # Handle local proxy URLs (/api/img/...)
    elif image_url.startswith("/api/img"):
        try:
            import httpx
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(image_url)
            params = parse_qs(parsed.query)
            real_url = params.get("url", [""])[0]
            if real_url:
                resp = httpx.get(real_url, timeout=10, follow_redirects=True)
                if resp.status_code == 200 and len(resp.content) > 500:
                    raw_bytes = resp.content
        except Exception:
            logger.debug("Could not fetch proxy image: %s", image_url)

    elif os.path.isfile(image_url):
        try:
            with open(image_url, "rb") as f:
                raw_bytes = f.read()
        except Exception:
            pass

    elif image_url.startswith("http"):
        try:
            import httpx
            _img_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = httpx.get(image_url, timeout=10, follow_redirects=True, headers=_img_headers)
            if resp.status_code == 200 and len(resp.content) > 500:
                raw_bytes = resp.content
        except Exception:
            logger.debug("Could not fetch product image: %s", image_url)

    if not raw_bytes:
        return None

    try:
        compressed = _compress_image(raw_bytes)
        return Image(compressed, width=max_w, height=max_h, kind="proportional")
    except Exception:
        # Fallback: embed raw
        return Image(io.BytesIO(raw_bytes), width=max_w, height=max_h, kind="proportional")


def _item_total_ron(item: QuoteItem, rate: float) -> float:
    """Compute full item total in RON.

    sell_price is EUR (product + margin, no printing).
    printing_cost and printing_setup are already in RON.
    """
    product_ron = item.sell_price * rate * item.quantity
    printing_ron = item.printing_cost * item.quantity + item.printing_setup
    return round(product_ron + printing_ron, 2)


def _item_unit_ron(item: QuoteItem, rate: float) -> float:
    """Per-unit price in RON (product + printing). BASE — no tier discount."""
    return round(item.sell_price * rate + item.printing_cost, 2)


def _tier_discount_pct(
    qty: int,
    quantity_tiers: list[int] | None,
    discount_step: float,
) -> float:
    """Largest tier discount % that applies to `qty`.

    quantity_tiers is sorted; index 0 = no discount, index 1 = 1*step, etc.
    Example: tiers=[100,200,300,500,1000], step=2 → 300 buc → 4%, 500 → 6%.
    """
    if not quantity_tiers or qty <= 0:
        return 0.0
    pct = 0.0
    for tier_idx, tier_qty in enumerate(quantity_tiers):
        if qty >= tier_qty:
            pct = tier_idx * discount_step
    return pct


def _item_unit_ron_tiered(
    item: QuoteItem, rate: float,
    quantity_tiers: list[int] | None = None,
    discount_step: float = 2.0,
) -> float:
    """Per-unit price in RON with tier discount applied based on item.quantity."""
    base = _item_unit_ron(item, rate)
    pct = _tier_discount_pct(item.quantity, quantity_tiers, discount_step)
    return round(base * (1 - pct / 100), 2) if pct > 0 else base


def _item_total_ron_tiered(
    item: QuoteItem, rate: float,
    quantity_tiers: list[int] | None = None,
    discount_step: float = 2.0,
) -> float:
    """Full item total in RON with tier discount applied to the per-unit price.
    Printing setup is added once (not discounted)."""
    unit_ron = _item_unit_ron_tiered(item, rate, quantity_tiers, discount_step)
    return round(unit_ron * item.quantity + item.printing_setup, 2)


def _item_size_qty_total(
    item: QuoteItem, rate: float,
    quantity_tiers: list[int] | None = None,
    discount_step: float = 2.0,
) -> tuple[float, float] | None:
    """Compute real total from size_quantities breakdown.

    Returns (unit_avg_ron, grand_total_ron) or None if not applicable.
    Uses the same logic as Case 1 in _build_product_section.
    """
    size_prices = item.size_prices if isinstance(item.size_prices, list) else []
    size_quantities = item.size_quantities if isinstance(item.size_quantities, list) else []
    if not size_quantities or not size_prices:
        return None

    sp_map = {sp.get("size", ""): sp.get("price", 0.0) for sp in size_prices}
    margin_mult = 1 + item.margin_percent / 100
    base_unit_ron = _item_unit_ron(item, rate)
    total_qty = sum(sq.get("qty", 0) for sq in size_quantities)
    if total_qty <= 0:
        return None

    # Discount based on total quantity
    discount_pct = 0.0
    if quantity_tiers:
        for tier_idx, tier_qty in enumerate(quantity_tiers):
            if total_qty >= tier_qty:
                discount_pct = tier_idx * discount_step

    active_sizes = [sq for sq in size_quantities if sq.get("qty", 0) > 0]
    active_eur_prices = [sp_map.get(sq.get("size", ""), 0) for sq in active_sizes]
    active_eur_prices = [p for p in active_eur_prices if p > 0]
    ref_size_eur = min(active_eur_prices) if active_eur_prices else item.unit_price

    grand_total = 0.0
    for sq in active_sizes:
        sz = sq.get("size", "")
        qty = sq.get("qty", 0)
        sz_eur = sp_map.get(sz, 0)
        premium = round((sz_eur - ref_size_eur) * margin_mult * rate, 2) if sz_eur > 0 else 0
        sz_unit = round(base_unit_ron + premium, 2)
        if discount_pct > 0:
            sz_unit = round(sz_unit * (1 - discount_pct / 100), 2)
        grand_total += round(sz_unit * qty, 2)

    unit_avg = round(grand_total / total_qty, 2)
    return (unit_avg, round(grand_total + item.printing_setup, 2))


# ── Build a compact product row ──────────────────────────────────────
def _build_product_section(
    item: QuoteItem, index: int, styles,
    exchange_rate: float, show_breakdown: bool,
    quantity_tiers: list[int] | None = None,
    discount_step: float = 2.0,
) -> list:
    """Build flowable elements for a single product — RON only layout."""
    elements = []
    rate = exchange_rate

    left_content = []

    left_content.append(Paragraph(
        f"<font color='#999999' size='8'>Produs #{index}</font>",
        styles["NormalArial"],
    ))
    # Title: always use product_name (editable by user on quote page)
    left_content.append(Paragraph(item.product_name, styles["ProductTitle"]))

    # Description below title
    desc = (item.product_description or "").strip()
    if desc:
        left_content.append(Paragraph(desc, styles["ProductDesc"]))

    # Color + size (SKU only in internal PDF)
    meta_parts = []
    if item.product_color:
        meta_parts.append(f"Culoare: {item.product_color}")
    # Show available sizes from size_prices if present
    _size_prices = []
    if hasattr(item, "size_prices") and item.size_prices:
        _size_prices = item.size_prices if isinstance(item.size_prices, list) else []
    sizes_str = ""
    if _size_prices:
        sizes_str = ", ".join(sp.get("size", "") for sp in _size_prices if sp.get("size"))
    if not sizes_str:
        # Try extracting sizes from description (pattern "Mărimi: XS, S, M, L, XL")
        import re
        desc = item.product_description or ""
        m = re.search(r'Mărimi[:\s]+([A-Z0-9/,\s]+?)(?:\n|$)', desc)
        if not m:
            m = re.search(r'Sizes?[:\s]+([A-Z0-9/,\s]+?)(?:\n|$)', desc)
        if m:
            sizes_str = m.group(1).strip().rstrip(',')
    if sizes_str:
        meta_parts.append(f"Mărimi: {sizes_str}")
    elif item.product_size:
        meta_parts.append(f"Mărime: {item.product_size}")
    if meta_parts:
        left_content.append(Paragraph(
            "  |  ".join(meta_parts),
            styles["ProductMeta"],
        ))

    # Color swatches
    product_colors = []
    if hasattr(item, "product_colors") and item.product_colors:
        product_colors = item.product_colors if isinstance(item.product_colors, list) else []
    if product_colors:
        left_content.append(Spacer(1, 1 * mm))
        left_content.append(ColorSwatches(
            color_list=product_colors,
            selected=item.product_color or "",
        ))

    # Printing info (hide prices in client-facing PDF)
    if item.printing_method:
        printing_text = f"Personalizare: {item.printing_method}"
        if show_breakdown:
            # Internal PDF: show costs
            if item.printing_cost > 0:
                printing_text += f"  (+{_fmtn(item.printing_cost)} RON/buc)"
            if item.printing_setup > 0:
                printing_text += f"  |  Setup: {_fmtr(item.printing_setup)}"
        left_content.append(Spacer(1, 1 * mm))
        left_content.append(Paragraph(printing_text, styles["ProductCustom"]))

    # Observations / notes
    if item.customization_notes:
        left_content.append(Spacer(1, 1 * mm))
        left_content.append(Paragraph(
            f"<i>Observatii: {item.customization_notes}</i>",
            styles["ProductDesc"],
        ))

    # Quantity + pricing in RON
    left_content.append(Spacer(1, 2 * mm))
    left_content.append(Paragraph(
        f"Cantitate: <b>{item.quantity}</b> buc",
        styles["ProductMeta"],
    ))

    # Bold price: when the quote opts into tier-discounted totals
    # (new quotes), apply the tier % to the per-unit RON; otherwise
    # keep the legacy base-price-only behaviour (old quotes unchanged).
    apply_tiers = bool(getattr(item.quote, "apply_tier_discount", False)) if item.quote else False
    tier_pct = _tier_discount_pct(item.quantity, quantity_tiers, discount_step) if apply_tiers else 0.0
    unit_ron_base = _item_unit_ron(item, rate)
    unit_ron = round(unit_ron_base * (1 - tier_pct / 100), 2) if tier_pct > 0 else unit_ron_base
    printing = item.printing_cost

    price_html = f"<b>{_fmtn(unit_ron)} RON / buc</b>"
    if tier_pct > 0:
        price_html += (
            f" <font size='8' color='#999999'>"
            f"(de la {_fmtn(unit_ron_base)} RON, -{tier_pct:.0f}% pentru {item.quantity} buc)"
            f"</font>"
        )
    left_content.append(Paragraph(price_html, styles["ProductPrice"]))

    # Price breakdown (if enabled)
    if show_breakdown:
        product_ron_unit = round(item.sell_price * rate * (1 - tier_pct / 100), 2)
        breakdown_parts = [f"Produs: {_fmtr(product_ron_unit)}"]
        if printing > 0:
            disc_printing = round(printing * (1 - tier_pct / 100), 2)
            breakdown_parts.append(f"Personalizare: +{_fmtr(disc_printing)}")
        left_content.append(Paragraph(
            "  |  ".join(breakdown_parts),
            styles["ProductPriceSmall"],
        ))

    # Size-based pricing table for textiles (when size_prices are available)
    size_prices = []
    if hasattr(item, "size_prices") and item.size_prices:
        size_prices = item.size_prices if isinstance(item.size_prices, list) else []

    size_quantities = []
    if hasattr(item, "size_quantities") and item.size_quantities:
        size_quantities = item.size_quantities if isinstance(item.size_quantities, list) else []

    # ── Case 1: Client specified exact sizes+quantities ──
    if size_quantities and size_prices and len(size_quantities) > 0:
        # Build size→price map from size_prices
        sp_map = {sp.get("size", ""): sp.get("price", 0.0) for sp in size_prices}
        margin_mult = 1 + item.margin_percent / 100
        base_unit_ron = _item_unit_ron(item, rate)
        total_qty = sum(sq.get("qty", 0) for sq in size_quantities)

        # Determine discount based on total quantity vs tiers
        discount_pct = 0.0
        if quantity_tiers:
            for tier_idx, tier_qty in enumerate(quantity_tiers):
                if total_qty >= tier_qty:
                    discount_pct = tier_idx * discount_step

        # Filter sizes with qty > 0
        active_sizes = [sq for sq in size_quantities if sq.get("qty", 0) > 0]

        # Reference = min EUR price from active sizes only (not children's sizes)
        active_eur_prices = [sp_map.get(sq.get("size", ""), 0) for sq in active_sizes]
        active_eur_prices = [p for p in active_eur_prices if p > 0]
        ref_size_eur = min(active_eur_prices) if active_eur_prices else item.unit_price

        if active_sizes:
            left_content.append(Spacer(1, 2 * mm))
            left_content.append(Paragraph(
                f"<font size='8' color='#999999'>Detaliere pe mărimi ({total_qty} buc total"
                + (f", -{discount_pct:.0f}%" if discount_pct > 0 else "")
                + "):</font>",
                styles["NormalArial"],
            ))

            sq_header = [
                Paragraph("<b>Mărime</b>", styles["ProductMeta"]),
                Paragraph("<b>Cantitate</b>", styles["ProductMeta"]),
                Paragraph("<b>Preț/buc</b>", styles["ProductMeta"]),
                Paragraph("<b>Subtotal</b>", styles["ProductMeta"]),
            ]
            sq_data = [sq_header]

            grand_subtotal = 0.0
            for sq in active_sizes:
                sz = sq.get("size", "")
                qty = sq.get("qty", 0)
                sz_eur = sp_map.get(sz, 0)
                premium = round((sz_eur - ref_size_eur) * margin_mult * rate, 2) if sz_eur > 0 else 0
                sz_unit = round(base_unit_ron + premium, 2)
                if discount_pct > 0:
                    sz_unit = round(sz_unit * (1 - discount_pct / 100), 2)
                subtotal = round(sz_unit * qty, 2)
                grand_subtotal += subtotal

                sq_data.append([
                    Paragraph(f"<b>{sz}</b>", styles["ProductMeta"]),
                    Paragraph(str(qty), styles["ProductMeta"]),
                    Paragraph(f"{_fmtr(sz_unit)}", styles["ProductMeta"]),
                    Paragraph(f"{_fmtr(subtotal)}", styles["ProductMeta"]),
                ])

            # Total row
            sq_data.append([
                Paragraph("<b>TOTAL</b>", styles["ProductMeta"]),
                Paragraph(f"<b>{total_qty}</b>", styles["ProductMeta"]),
                Paragraph("", styles["ProductMeta"]),
                Paragraph(f"<b>{_fmtr(grand_subtotal)}</b>", styles["ProductMeta"]),
            ])

            sq_col_w = [22 * mm, 22 * mm, 30 * mm, 30 * mm]
            sq_table = Table(sq_data, colWidths=sq_col_w)
            sq_table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                ("FONTNAME", (0, 1), (-1, -1), FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#555555")),
                ("TEXTCOLOR", (2, 1), (2, -2), colors.HexColor("#1A56DB")),
                ("TEXTCOLOR", (3, 1), (3, -2), colors.HexColor("#1A56DB")),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#333333")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F5F5")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F0F0F0")),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#DDDDDD")),
                ("LINEBELOW", (0, -2), (-1, -2), 0.5, colors.HexColor("#DDDDDD")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#EEEEEE")),
            ]))
            left_content.append(sq_table)

    # ── Case 2: Generic tier table (no specific quantities) ──
    elif size_prices and len(size_prices) > 1 and quantity_tiers and len(quantity_tiers) > 0:
        left_content.append(Spacer(1, 2 * mm))
        left_content.append(Paragraph(
            "<font size='8' color='#999999'>Preț în funcție de mărime și cantitate:</font>",
            styles["NormalArial"],
        ))

        # Use sell_price as base (consistent with bold price and internal sheet)
        # Size premiums are added on top for larger sizes
        margin_mult = 1 + item.margin_percent / 100
        base_unit_ron = _item_unit_ron(item, rate)  # sell_price * rate + printing

        # Reference = min EUR price from displayed sizes (not children's sizes that aren't shown)
        displayed_eur = [sp.get("price", 0) for sp in size_prices if sp.get("price", 0) > 0]
        ref_size_eur = min(displayed_eur) if displayed_eur else item.unit_price

        # Group consecutive sizes with the same price
        size_groups: list[dict] = []  # [{"label": "XS - 2XL", "base_eur": 2.28}, ...]
        current_group: dict | None = None

        for sp in size_prices:
            sz = sp.get("size", "")
            p = sp.get("price", 0.0)
            if current_group and abs(current_group["base_eur"] - p) < 0.001:
                current_group["sizes"].append(sz)
            else:
                current_group = {"sizes": [sz], "base_eur": p}
                size_groups.append(current_group)

        # Build labels: "XS - 2XL" for ranges, "3XL" for singles
        for g in size_groups:
            if len(g["sizes"]) > 2:
                g["label"] = f"{g['sizes'][0]} - {g['sizes'][-1]}"
            elif len(g["sizes"]) == 2:
                g["label"] = f"{g['sizes'][0]} - {g['sizes'][1]}"
            else:
                g["label"] = g["sizes"][0]

        # Build table: header = Mărime | qty1 | qty2 | ...
        tier_header = [Paragraph("<b>Mărime</b>", styles["ProductMeta"])]
        for tq in quantity_tiers:
            tier_header.append(Paragraph(f"<b>{tq} buc</b>", styles["ProductMeta"]))

        tier_data = [tier_header]

        for g in size_groups:
            row = [Paragraph(f"<b>{g['label']}</b>", styles["ProductMeta"])]
            # Size premium: difference from base size, with margin applied
            size_premium_ron = round((g["base_eur"] - ref_size_eur) * margin_mult * rate, 2)
            for tier_idx, tier_qty in enumerate(quantity_tiers):
                discount_pct = tier_idx * discount_step
                size_unit_ron = round(base_unit_ron + size_premium_ron, 2)
                discounted = round(size_unit_ron * (1 - discount_pct / 100), 2)
                cell_text = f"{_fmtn(discounted)}\nRON"
                if discount_pct > 0:
                    cell_text += f"\n<font size='5' color='#999999'>(-{discount_pct:.0f}%)</font>"
                row.append(Paragraph(cell_text, styles["ProductMeta"]))
            tier_data.append(row)

        n_cols = 1 + len(quantity_tiers)
        first_col_w = 28 * mm
        rest_col_w = (120 * mm - first_col_w) / max(len(quantity_tiers), 1)
        col_widths = [first_col_w] + [rest_col_w] * len(quantity_tiers)

        tier_table = Table(tier_data, colWidths=col_widths)
        tier_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTNAME", (0, 1), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#555555")),
            ("TEXTCOLOR", (1, 1), (-1, -1), colors.HexColor("#1A56DB")),
            ("TEXTCOLOR", (0, 1), (0, -1), colors.HexColor("#333333")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F5F5")),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#DDDDDD")),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#EEEEEE")),
        ]))
        left_content.append(tier_table)

    elif quantity_tiers and len(quantity_tiers) > 0:
        # Standard quantity discount table (non-textile products)
        left_content.append(Spacer(1, 2 * mm))
        left_content.append(Paragraph(
            "<font size='8' color='#999999'>Preț în funcție de cantitate:</font>",
            styles["NormalArial"],
        ))

        base_unit_ron = _item_unit_ron(item, rate)
        tier_header = ["Cantitate"]
        tier_prices = ["Preț/buc"]

        for tier_idx, tier_qty in enumerate(quantity_tiers):
            discount_pct = tier_idx * discount_step
            discounted = round(base_unit_ron * (1 - discount_pct / 100), 2)
            tier_header.append(f"{tier_qty} buc")
            if discount_pct > 0:
                tier_prices.append(f"{_fmtn(discounted)} RON\n(-{discount_pct:.0f}%)")
            else:
                tier_prices.append(f"{_fmtr(discounted)}")

        tier_data = [tier_header, tier_prices]
        n_cols = len(tier_header)
        tier_col_w = 120 * mm / n_cols

        tier_table = Table(tier_data, colWidths=[tier_col_w] * n_cols)
        tier_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTNAME", (0, 1), (-1, 1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#555555")),
            ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#1A56DB")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F5F5")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#DDDDDD")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ]))
        left_content.append(tier_table)

    # Image (right column)
    img_w = 40 * mm
    img_h = 40 * mm
    product_img = _get_product_image(item, img_w, img_h)
    right_content = []
    if product_img:
        right_content.append(product_img)
    else:
        right_content.append(Spacer(1, 10 * mm))

    # Two-column table — image centered in right column
    left_col_w = 115 * mm
    right_col_w = 55 * mm

    layout_table = Table(
        [[left_content, right_content]],
        colWidths=[left_col_w, right_col_w],
    )
    layout_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, 0), "TOP"),
        ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    elements.append(layout_table)

    # Separator
    elements.append(Spacer(1, 3 * mm))
    elements.append(HRFlowable(
        width="100%", thickness=0.5, color=colors.HexColor("#EEEEEE"),
    ))
    elements.append(Spacer(1, 3 * mm))

    return elements


# ── Summary section ──────────────────────────────────────────────────
def _build_summary(quote: Quote, styles, clr: dict, db_settings: dict, exchange_rate: float,
                    quantity_tiers: list[int] | None = None, discount_step: float = 2.0) -> list:
    elements = []
    rate = exchange_rate

    elements.append(Spacer(1, 6 * mm))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=clr["primary"]))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("REZUMAT OFERTĂ", styles["QuoteTitle"]))
    elements.append(Spacer(1, 3 * mm))

    # Items summary table — RON only
    header = ["#", "Produs", "Cant.", "Preț/buc", "Total"]
    col_widths = [10 * mm, 72 * mm, 16 * mm, 30 * mm, 42 * mm]

    table_data = [header]

    apply_tiers = bool(getattr(quote, "apply_tier_discount", False))
    eff_tiers = quantity_tiers if apply_tiers else None
    eff_step = discount_step if apply_tiers else 0.0

    grand_total_ron = 0.0
    for i, item in enumerate(quote.items, 1):
        name = item.product_name
        if item.product_color:
            name += f" ({item.product_color})"

        # Textile path (size_quantities) keeps its existing tier behaviour
        # — that calculation predates the flag.
        sq_result = _item_size_qty_total(item, rate, quantity_tiers, discount_step)
        if sq_result:
            unit_ron, total_ron = sq_result
        else:
            unit_ron = _item_unit_ron_tiered(item, rate, eff_tiers, eff_step)
            total_ron = _item_total_ron_tiered(item, rate, eff_tiers, eff_step)
        grand_total_ron += total_ron

        row = [
            str(i),
            Paragraph(name, styles["NormalArial"]),
            str(item.quantity),
            f"{_fmtr(unit_ron)}",
            f"{_fmtr(total_ron)}",
        ]
        table_data.append(row)

    items_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), clr["primary"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), clr["white"]),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -1), FONT),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [clr["white"], clr["light_gray"]]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 4 * mm))

    # Total row — use 2 columns: label + value, right-aligned
    total_label_w = 108 * mm  # covers first 3 col equivalents
    total_val_w = 62 * mm     # wider for large numbers
    total_data = [["TOTAL:", _fmtr(grand_total_ron)]]
    total_table = Table(total_data, colWidths=[total_label_w, total_val_w])
    total_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (1, 0), 13),
        ("TEXTCOLOR", (0, 0), (1, 0), clr["accent"]),
        ("ALIGN", (0, 0), (0, 0), "RIGHT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEABOVE", (0, 0), (1, 0), 1.5, clr["primary"]),
        ("TOPPADDING", (0, 0), (1, 0), 8),
    ]))
    elements.append(total_table)

    # Notes — only shown in internal PDF, not client-facing
    # (AI-generated notes are internal; client PDF stays clean)

    # Client info
    if quote.client_name or quote.client_company:
        elements.append(Spacer(1, 6 * mm))
        client_data = []
        if quote.client_company:
            client_data.append(["Companie:", quote.client_company])
        if quote.client_name:
            client_data.append(["Contact:", quote.client_name])
        if quote.client_email:
            client_data.append(["Email:", quote.client_email])
        if quote.client_phone:
            client_data.append(["Telefon:", quote.client_phone])

        client_table = Table(client_data, colWidths=[25 * mm, 120 * mm])
        client_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), FONT_BOLD),
            ("FONTNAME", (1, 0), (1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), clr["dark_text"]),
            ("TEXTCOLOR", (1, 0), (1, -1), clr["gray_text"]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(client_table)

    # Bank details from DB settings
    elements.append(Spacer(1, 8 * mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#DDDDDD")))
    elements.append(Spacer(1, 3 * mm))

    company_name = db_settings.get("company_name", "")
    company_cui = db_settings.get("company_cui", "")
    company_bank = db_settings.get("company_bank", "")
    company_iban = db_settings.get("company_iban", "")
    company_address = db_settings.get("company_address", "")

    bank_lines = []
    if company_cui:
        bank_lines.append(f"CUI: {company_cui}")
    if company_bank or company_iban:
        bank_text = ""
        if company_bank:
            bank_text += f"Bancă: {company_bank}"
        if company_iban:
            bank_text += f"  |  IBAN: {company_iban}"
        bank_lines.append(bank_text)
    if company_name or company_address:
        parts = [p for p in [company_name, company_address] if p]
        bank_lines.append("  |  ".join(parts))

    for line in bank_lines:
        elements.append(Paragraph(line, styles["FooterText"]))

    return elements


# ── Main PDF generator ───────────────────────────────────────────────
def generate_quote_pdf(quote: Quote, db_settings: dict | None = None) -> bytes:
    """
    Generate a professional PDF for the given quote.

    Args:
        quote: The Quote ORM object with items loaded.
        db_settings: Dict of app settings from DB (company, pricing, template).
                     If None, uses sensible defaults.

    Layout:
    - Cover: quote title + products (multiple per page, compact)
    - Summary section at the end with table, totals, bank details
    - Dual currency (EUR + RON) when exchange rate is set

    Returns raw PDF bytes.
    """
    if db_settings is None:
        db_settings = {}

    buffer = io.BytesIO()
    clr = _get_colors(db_settings)
    styles = _build_styles(clr)

    # Extract settings — prefer quote-level snapshot (frozen at creation)
    # so PDF regenerations stay stable even if admin changes global settings.
    exchange_rate = 0.0
    if getattr(quote, "exchange_rate", None):
        try:
            exchange_rate = float(quote.exchange_rate)
        except (ValueError, TypeError):
            exchange_rate = 0.0
    if not exchange_rate:
        try:
            exchange_rate = float(db_settings.get("exchange_rate_eur_ron", "0"))
        except (ValueError, TypeError):
            pass

    show_breakdown = db_settings.get("template_show_breakdown", "false") == "true"

    # Quantity discount tiers — prefer quote snapshot
    discount_step = 2.0
    if getattr(quote, "discount_step", None) is not None:
        try:
            discount_step = float(quote.discount_step)
        except (ValueError, TypeError):
            pass
    else:
        try:
            discount_step = float(db_settings.get("quantity_discount_percent", "2"))
        except (ValueError, TypeError):
            pass

    tiers_raw = (
        getattr(quote, "quantity_tiers", None)
        or db_settings.get("quantity_tiers", "100,200,300,500,1000")
    )
    quantity_tiers = []
    for t in tiers_raw.split(","):
        t = t.strip()
        if t.isdigit():
            quantity_tiers.append(int(t))

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=28 * mm,
        bottomMargin=18 * mm,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
    )

    content_frame = Frame(
        MARGIN, 18 * mm,
        PAGE_W - 2 * MARGIN, PAGE_H - 28 * mm - 18 * mm,
        id="content",
    )

    draw_header = _make_draw_header(db_settings, clr)
    draw_footer = _make_draw_footer(db_settings, clr)

    template = PageTemplate(
        id="main",
        frames=[content_frame],
        onPage=lambda canvas, doc: (draw_header(canvas, doc), draw_footer(canvas, doc)),
    )
    doc.addPageTemplates([template])

    # ── Build all elements ──
    all_elements = []

    # Cover header
    date_str = datetime.now().strftime("%d.%m.%Y")
    valid_str = quote.valid_until.strftime("%d.%m.%Y") if quote.valid_until else "—"

    all_elements.append(Paragraph("OFERTĂ DE PREȚ", styles["QuoteTitle"]))
    all_elements.append(Paragraph(
        f"Nr: <b>{quote.number}</b>  |  Data: {date_str}  |  Valabilă până: {valid_str}",
        styles["QuoteInfo"],
    ))

    if quote.client_company or quote.client_name:
        all_elements.append(Spacer(1, 3 * mm))
        client_parts = []
        if quote.client_company:
            client_parts.append(f"<b>{quote.client_company}</b>")
        if quote.client_name and quote.client_name.lower() not in ("client", ""):
            client_parts.append(quote.client_name)
        if client_parts:
            all_elements.append(Paragraph(
                f"Către: {'  —  '.join(client_parts)}",
                styles["QuoteInfo"],
            ))

    all_elements.append(Spacer(1, 6 * mm))
    all_elements.append(HRFlowable(width="100%", thickness=1, color=clr["primary"]))
    all_elements.append(Spacer(1, 6 * mm))

    # Product sections — compact, no page breaks
    for i, item in enumerate(quote.items, 1):
        product_elements = _build_product_section(
            item, i, styles,
            exchange_rate=exchange_rate,
            show_breakdown=show_breakdown,
            quantity_tiers=quantity_tiers,
            discount_step=discount_step,
        )
        all_elements.append(KeepTogether(product_elements))

    # Summary at the end
    if quote.items:
        summary_elements = _build_summary(
            quote, styles, clr, db_settings, exchange_rate,
            quantity_tiers=quantity_tiers, discount_step=discount_step,
        )
        all_elements.extend(summary_elements)

    doc.build(all_elements)
    return buffer.getvalue()


# ── Internal Order PDF ────────────────────────────────────────────────
def generate_internal_pdf(quote: Quote, db_settings: dict | None = None) -> bytes:
    """
    Generate an internal order sheet with FULL cost details:
    purchase price (EUR), margin %, sell price, printing costs, totals.

    This is for internal use only — NOT sent to clients.
    """
    if db_settings is None:
        db_settings = {}

    buffer = io.BytesIO()
    clr = _get_colors(db_settings)
    styles = _build_styles(clr)

    exchange_rate = 0.0
    try:
        exchange_rate = float(db_settings.get("exchange_rate_eur_ron", "0"))
    except (ValueError, TypeError):
        pass
    rate = exchange_rate

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=28 * mm,
        bottomMargin=18 * mm,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
    )

    content_frame = Frame(
        MARGIN, 18 * mm,
        PAGE_W - 2 * MARGIN, PAGE_H - 28 * mm - 18 * mm,
        id="content",
    )

    draw_header = _make_draw_header(db_settings, clr)
    draw_footer = _make_draw_footer(db_settings, clr)

    template = PageTemplate(
        id="main",
        frames=[content_frame],
        onPage=lambda canvas, doc: (draw_header(canvas, doc), draw_footer(canvas, doc)),
    )
    doc.addPageTemplates([template])

    all_elements = []

    # Title
    date_str = datetime.now().strftime("%d.%m.%Y")
    is_confirmed = quote.status == "accepted"
    title_text = "FIȘĂ INTERNĂ COMANDĂ" if is_confirmed else "FIȘĂ INTERNĂ OFERTĂ"
    all_elements.append(Paragraph(title_text, styles["QuoteTitle"]))

    status_label = "COMANDĂ FERMĂ" if is_confirmed else quote.status
    all_elements.append(Paragraph(
        f"Nr ofertă: <b>{quote.number}</b>  |  Data: {date_str}  |  Status: <b>{status_label}</b>",
        styles["QuoteInfo"],
    ))

    # Client info
    if quote.client_company or quote.client_name:
        all_elements.append(Spacer(1, 2 * mm))
        client_info_parts = []
        if quote.client_company:
            client_info_parts.append(f"Firma: <b>{quote.client_company}</b>")
        if quote.client_name:
            client_info_parts.append(f"Contact: {quote.client_name}")
        if quote.client_email:
            client_info_parts.append(f"Email: {quote.client_email}")
        if quote.client_phone:
            client_info_parts.append(f"Tel: {quote.client_phone}")
        all_elements.append(Paragraph("  |  ".join(client_info_parts), styles["QuoteInfo"]))

    # Quantity discount tiers (for size_quantities calculation)
    discount_step = 2.0
    try:
        discount_step = float(db_settings.get("quantity_discount_percent", "2"))
    except (ValueError, TypeError):
        pass
    tiers_raw = db_settings.get("quantity_tiers", "100,200,300,500,1000")
    quantity_tiers = []
    for t in tiers_raw.split(","):
        t = t.strip()
        if t.isdigit():
            quantity_tiers.append(int(t))

    all_elements.append(Spacer(1, 4 * mm))
    all_elements.append(HRFlowable(width="100%", thickness=1.5, color=clr["primary"]))
    all_elements.append(Spacer(1, 4 * mm))

    # Detailed items table
    header = [
        "#",
        "Produs",
        "Cant.",
        "Preț\nachiziție\n(EUR)",
        "Marjă\n%",
        "Preț\nvânzare\n(EUR)",
        "Preț\nvânzare\n(RON)",
        "Person.\n(RON/buc)",
        "Profit\nbrut\n(RON)",
        "Total\n(RON)",
    ]
    avail_w = PAGE_W - 2 * MARGIN  # ~174mm on A4
    col_widths = [7*mm, 38*mm, 10*mm, 16*mm, 12*mm, 16*mm, 16*mm, 16*mm, 14*mm, avail_w - 145*mm]

    table_data = [header]
    grand_total_ron = 0.0
    grand_cost_eur = 0.0
    grand_printing_ron = 0.0
    confirmed_total_ron = 0.0
    confirmed_rows = []  # 1-indexed row numbers of confirmed items

    internal_apply_tiers = bool(getattr(quote, "apply_tier_discount", False))
    internal_eff_tiers = quantity_tiers if internal_apply_tiers else None
    internal_eff_step = discount_step if internal_apply_tiers else 0.0

    for i, item in enumerate(quote.items, 1):
        # Textile path keeps existing tier behaviour.
        sq_result = _item_size_qty_total(item, rate, quantity_tiers, discount_step)
        if sq_result:
            _, total_ron = sq_result
        else:
            total_ron = _item_total_ron_tiered(item, rate, internal_eff_tiers, internal_eff_step)
        cost_eur = item.unit_price * item.quantity
        printing_total = item.printing_cost * item.quantity + item.printing_setup
        grand_total_ron += total_ron
        grand_cost_eur += cost_eur
        grand_printing_ron += printing_total

        if item.is_confirmed:
            confirmed_total_ron += total_ron
            confirmed_rows.append(i)

        name = item.product_name
        if item.product_color:
            name += f" ({item.product_color})"
        if item.product_sku:
            name += f"\n<font size='6' color='#888888'>{item.product_sku}</font>"

        # Add confirmed indicator to product name
        if is_confirmed:
            status_mark = "✓ " if item.is_confirmed else "✗ "
            name = status_mark + name

        # Profit brut per line = total_ron - (cost_eur * rate) - printing_total
        line_profit = round(total_ron - cost_eur * rate - printing_total, 2)

        row = [
            str(i),
            Paragraph(name, styles["ProductMeta"]),
            str(item.quantity),
            f"{item.unit_price:.2f}",
            f"{item.margin_percent:.0f}%",
            f"{item.sell_price:.2f}",
            f"{round(item.sell_price * rate, 2):.2f}",
            f"{_fmtn(item.printing_cost)}" if item.printing_cost > 0 else "—",
            _fmtn(line_profit),
            _fmtn(total_ron),
        ]
        table_data.append(row)

    items_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table_style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), clr["primary"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), clr["white"]),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTNAME", (0, 1), (-1, -1), FONT),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [clr["white"], clr["light_gray"]]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]

    # Highlight confirmed rows with green background, dim unconfirmed
    if is_confirmed and confirmed_rows:
        green_bg = colors.HexColor("#E8F5E9")
        gray_text = colors.HexColor("#AAAAAA")
        for row_idx in range(1, len(table_data)):
            if row_idx in confirmed_rows:
                table_style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), green_bg))
            else:
                table_style_cmds.append(("TEXTCOLOR", (0, row_idx), (-1, row_idx), gray_text))

    items_table.setStyle(TableStyle(table_style_cmds))
    all_elements.append(items_table)
    all_elements.append(Spacer(1, 6 * mm))

    # Totals summary
    all_elements.append(HRFlowable(width="100%", thickness=1, color=clr["primary"]))
    all_elements.append(Spacer(1, 3 * mm))

    grand_sell_ron = grand_total_ron - grand_printing_ron
    grand_cost_ron = round(grand_cost_eur * rate, 2)
    profit_ron = round(grand_total_ron - grand_cost_ron - grand_printing_ron, 2)
    effective_margin = round(profit_ron / grand_cost_ron * 100, 1) if grand_cost_ron > 0 else 0

    summary_data = [
        ["Cost achiziție total (EUR):", _fmte(grand_cost_eur)],
        ["Cost achiziție total (RON):", _fmtr(grand_cost_ron)],
        ["Personalizare total (RON):", _fmtr(grand_printing_ron)],
        ["Vânzare total (RON):", _fmtr(grand_total_ron)],
        ["Profit brut (RON):", _fmtr(profit_ron)],
        ["Marjă efectivă:", f"{effective_margin:.1f}%"],
    ]
    if rate > 0:
        summary_data.append(["Curs EUR/RON:", f"{rate:.4f}"])

    # Add confirmed items total if quote is a firm order with partial selection
    if is_confirmed and confirmed_rows and len(confirmed_rows) < len(quote.items):
        summary_data.append(["", ""])
        confirmed_count = len(confirmed_rows)
        total_count = len(quote.items)
        summary_data.append([
            f"COMANDĂ FERMĂ ({confirmed_count}/{total_count} produse):",
            _fmtr(confirmed_total_ron),
        ])

    summary_table = Table(summary_data, colWidths=[70*mm, 60*mm])
    summary_style_cmds = [
        ("FONTNAME", (0, 0), (0, -1), FONT_BOLD),
        ("FONTNAME", (1, 0), (1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), clr["dark_text"]),
        ("TEXTCOLOR", (1, 0), (1, -1), clr["accent"]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        # Highlight total and profit rows
        ("FONTNAME", (0, 3), (1, 3), FONT_BOLD),
        ("FONTSIZE", (0, 3), (1, 3), 12),
        ("FONTNAME", (0, 4), (1, 4), FONT_BOLD),
        ("TEXTCOLOR", (1, 4), (1, 4), colors.HexColor("#27AE60")),
        ("LINEABOVE", (0, 3), (1, 3), 1, clr["primary"]),
    ]

    # Highlight confirmed total row in green
    if is_confirmed and confirmed_rows and len(confirmed_rows) < len(quote.items):
        confirmed_row_idx = len(summary_data) - 1
        summary_style_cmds.append(("FONTNAME", (0, confirmed_row_idx), (1, confirmed_row_idx), FONT_BOLD))
        summary_style_cmds.append(("FONTSIZE", (0, confirmed_row_idx), (1, confirmed_row_idx), 12))
        summary_style_cmds.append(("TEXTCOLOR", (1, confirmed_row_idx), (1, confirmed_row_idx), colors.HexColor("#27AE60")))
        summary_style_cmds.append(("LINEABOVE", (0, confirmed_row_idx), (1, confirmed_row_idx), 1, colors.HexColor("#27AE60")))

    summary_table.setStyle(TableStyle(summary_style_cmds))
    all_elements.append(summary_table)

    # Notes
    if quote.notes:
        all_elements.append(Spacer(1, 6 * mm))
        all_elements.append(Paragraph("<b>Note:</b>", styles["SummaryLabel"]))
        all_elements.append(Spacer(1, 2 * mm))
        all_elements.append(Paragraph(quote.notes, styles["NotesText"]))

    doc.build(all_elements)
    return buffer.getvalue()
