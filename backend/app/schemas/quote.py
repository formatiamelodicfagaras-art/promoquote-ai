from pydantic import BaseModel
from datetime import datetime


class QuoteItemCreate(BaseModel):
    product_id: str | None = None
    product_name: str
    product_description: str = ""
    product_sku: str = ""
    product_image: str = ""
    product_color: str = ""
    product_colors: list[dict] = []
    product_size: str = ""
    quantity: int = 1
    unit_price: float = 0.0
    margin_percent: float = 30.0
    printing_method: str = ""
    printing_cost: float = 0.0
    printing_setup: float = 0.0
    customization_notes: str = ""
    notes: str = ""
    size_quantities: list[dict] = []


class QuoteItemResponse(BaseModel):
    id: str
    product_id: str | None = None
    product_name: str
    product_description: str = ""
    product_sku: str
    product_image: str
    product_color: str
    product_colors: list[dict] = []
    product_size: str
    size_prices: list[dict] = []
    size_quantities: list[dict] = []
    quantity: int
    unit_price: float
    margin_percent: float
    sell_price: float
    total: float
    printing_method: str
    printing_cost: float
    printing_setup: float
    customization_notes: str
    notes: str
    is_confirmed: bool = False

    model_config = {"from_attributes": True}


class QuoteCreate(BaseModel):
    number: str | None = None
    company_id: str | None = None
    client_name: str = ""
    client_email: str = ""
    client_company: str = ""
    client_phone: str = ""
    notes: str = ""
    status: str = "draft"
    margin_percent: float = 30.0
    currency: str = "EUR"
    items: list[QuoteItemCreate] = []


class QuoteUpdate(BaseModel):
    number: str | None = None
    company_id: str | None = None
    client_name: str | None = None
    client_email: str | None = None
    client_company: str | None = None
    client_phone: str | None = None
    status: str | None = None
    notes: str | None = None
    margin_percent: float | None = None
    # Pricing snapshot (editable so user can override frozen values per quote)
    exchange_rate: float | None = None
    quantity_tiers: str | None = None
    discount_step: float | None = None


class QuoteItemUpdate(BaseModel):
    product_name: str | None = None
    product_description: str | None = None
    quantity: int | None = None
    unit_price: float | None = None
    margin_percent: float | None = None
    product_image: str | None = None
    product_color: str | None = None
    product_colors: list[dict] | None = None
    product_size: str | None = None
    size_quantities: list[dict] | None = None
    printing_method: str | None = None
    printing_cost: float | None = None
    printing_setup: float | None = None
    customization_notes: str | None = None
    notes: str | None = None
    is_confirmed: bool | None = None


class QuoteResponse(BaseModel):
    id: str
    number: str
    company_id: str | None = None
    company_name: str | None = None
    client_name: str
    client_email: str
    client_company: str
    client_phone: str
    status: str
    notes: str
    subtotal: float
    margin_percent: float
    total: float
    currency: str
    exchange_rate: float | None = None
    quantity_tiers: str | None = None
    discount_step: float | None = None
    apply_tier_discount: bool | None = None
    items: list[QuoteItemResponse] = []
    valid_until: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
