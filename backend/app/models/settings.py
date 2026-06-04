from sqlalchemy import Column, String, Integer, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, generate_uuid


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    key = Column(String(100), unique=True, index=True)
    value = Column(String(2000), default="")
    value_type = Column(String(20), default="string")  # "string", "number", "boolean", "json"
    description = Column(String(500), default="")
    group_name = Column(String(100), default="general")  # "pricing", "company", "general"


async def load_settings_dict(db: AsyncSession) -> dict[str, str]:
    """Load all app settings from DB as a flat key->value dict.

    Seeds defaults if missing. Number values are returned as strings;
    callers should cast as needed.
    """
    # Seed missing defaults
    result = await db.execute(select(AppSettings))
    existing = {s.key: s.value for s in result.scalars().all()}

    seeded = False
    for s in DEFAULT_SETTINGS:
        if s["key"] not in existing:
            db.add(AppSettings(**s))
            existing[s["key"]] = s["value"]
            seeded = True
    if seeded:
        await db.commit()

    return existing


def get_setting_float(settings: dict[str, str], key: str, default: float) -> float:
    """Helper to get a float setting with fallback."""
    try:
        return float(settings.get(key, default))
    except (ValueError, TypeError):
        return default


def get_setting_str(settings: dict[str, str], key: str, default: str = "") -> str:
    return settings.get(key, default)


# Default settings to seed
DEFAULT_SETTINGS = [
    # Pricing
    {"key": "margin_percent", "value": "30", "value_type": "number", "description": "Marja implicită (%)", "group_name": "pricing"},
    {"key": "currency", "value": "EUR", "value_type": "string", "description": "Moneda implicită", "group_name": "pricing"},
    {"key": "quote_validity_days", "value": "30", "value_type": "number", "description": "Valabilitate ofertă (zile)", "group_name": "pricing"},
    {"key": "printing_margin_percent", "value": "20", "value_type": "number", "description": "Marja pe personalizare (%)", "group_name": "pricing"},
    {"key": "exchange_rate_eur_ron", "value": "4.97", "value_type": "number", "description": "Curs valutar EUR → RON", "group_name": "pricing"},
    {"key": "quantity_discount_percent", "value": "2", "value_type": "number", "description": "Discount per nivel cantitate (%)", "group_name": "pricing"},
    {"key": "quantity_tiers", "value": "100,200,300,500,1000", "value_type": "string", "description": "Nivele cantitate pentru discount (separate prin virgulă)", "group_name": "pricing"},
    # Company
    {"key": "company_name", "value": "Demo Company SRL", "value_type": "string", "description": "Nume firmă", "group_name": "company"},
    {"key": "company_cui", "value": "", "value_type": "string", "description": "CUI / CIF", "group_name": "company"},
    {"key": "company_address", "value": "", "value_type": "string", "description": "Adresă", "group_name": "company"},
    {"key": "company_phone", "value": "", "value_type": "string", "description": "Telefon", "group_name": "company"},
    {"key": "company_email", "value": "demo@example.com", "value_type": "string", "description": "Email", "group_name": "company"},
    {"key": "company_website", "value": "", "value_type": "string", "description": "Website", "group_name": "company"},
    {"key": "company_bank", "value": "", "value_type": "string", "description": "Bancă", "group_name": "company"},
    {"key": "company_iban", "value": "", "value_type": "string", "description": "IBAN", "group_name": "company"},
    {"key": "company_logo_url", "value": "", "value_type": "string", "description": "URL logo companie", "group_name": "company"},
    # Template
    {"key": "template_primary_color", "value": "#C0392B", "value_type": "string", "description": "Culoare principală PDF", "group_name": "template"},
    {"key": "template_accent_color", "value": "#1A56DB", "value_type": "string", "description": "Culoare accent PDF", "group_name": "template"},
    {"key": "template_font", "value": "Arial", "value_type": "string", "description": "Font PDF", "group_name": "template"},
    {"key": "template_header_layout", "value": "logo-left", "value_type": "string", "description": "Poziție header", "group_name": "template"},
    {"key": "template_show_breakdown", "value": "true", "value_type": "boolean", "description": "Afișează detalii preț", "group_name": "template"},
    {"key": "template_footer_text", "value": "", "value_type": "string", "description": "Text footer ofertă", "group_name": "template"},
]
