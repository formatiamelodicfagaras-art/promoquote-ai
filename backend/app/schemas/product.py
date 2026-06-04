from pydantic import BaseModel
from datetime import datetime


class PrintingTechnique(BaseModel):
    name: str = ""
    setup_cost: float = 0.0
    unit_cost: float = 0.0


class PrintingOption(BaseModel):
    position: str = ""
    max_width_mm: float = 0.0
    max_height_mm: float = 0.0
    techniques: list[PrintingTechnique] = []


class ColorInfo(BaseModel):
    name: str = ""
    hex: str = ""
    image: str = ""


class ProductCreate(BaseModel):
    external_id: str
    integration_id: str | None = None
    name: str
    description: str = ""
    short_description: str = ""
    category: str = ""
    subcategory: str = ""
    brand: str = ""
    base_price: float = 0.0
    currency: str = "EUR"
    images: list[str] = []
    primary_image: str = ""
    colors: list[ColorInfo] = []
    specifications: dict = {}
    printing_options: list[PrintingOption] = []
    stock: int = 0
    min_order_qty: int = 1


class ProductResponse(BaseModel):
    id: str
    external_id: str | None = None
    integration_id: str | None = None
    name: str
    description: str
    short_description: str
    category: str
    subcategory: str
    brand: str
    base_price: float
    currency: str
    images: list = []
    primary_image: str
    colors: list = []
    specifications: dict = {}
    printing_options: list = []
    stock: int
    min_order_qty: int
    is_active: bool
    last_synced_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProductCardResponse(BaseModel):
    """Compact product data for chat cards."""
    id: str
    name: str
    short_description: str
    category: str
    base_price: float
    sell_price: float
    currency: str
    primary_image: str
    colors: list[str] = []
    printing_techniques: list[str] = []
    min_order_qty: int
    stock: int


class ProductSearchParams(BaseModel):
    query: str = ""
    category: str = ""
    min_price: float | None = None
    max_price: float | None = None
    color: str = ""
    limit: int = 20
    offset: int = 0
