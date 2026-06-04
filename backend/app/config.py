from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./promoquote.db"

    # Anthropic
    anthropic_api_key: str = ""

    # Meilisearch
    meilisearch_url: str = "http://localhost:7700"
    meilisearch_api_key: str = ""
    meilisearch_enabled: bool = False

    # ANDA Present
    anda_xml_products_url: str = "https://www.andapresent.com/xml/products.xml"
    anda_xml_prices_url: str = "https://www.andapresent.com/xml/prices.xml"
    anda_xml_inventory_url: str = "https://www.andapresent.com/xml/inventory.xml"
    anda_xml_labeling_url: str = "https://www.andapresent.com/xml/labeling.xml"
    anda_api_key: str = ""

    # Malfini
    malfini_api_url: str = "https://shop.malfini.com"
    malfini_username: str = ""
    malfini_password: str = ""

    # Midocean
    midocean_api_url: str = "https://api.midocean.com/gateway"
    midocean_api_key: str = ""

    # Company (override via .env or via Settings UI)
    company_name: str = "Demo Company SRL"
    company_address: str = ""
    company_phone: str = ""
    company_email: str = "demo@example.com"
    company_cui: str = ""
    company_reg: str = ""
    company_bank: str = ""
    company_logo_path: str = ""

    # Pricing
    default_margin_percent: float = 30.0
    default_currency: str = "EUR"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
