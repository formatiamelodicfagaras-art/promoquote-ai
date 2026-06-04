from sqlalchemy import Column, String, Float, Text, DateTime, Integer, Boolean, JSON
from sqlalchemy.sql import func

from app.database import Base, generate_uuid


class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    external_id = Column(String(100), unique=True, index=True)
    integration_id = Column(String(36), index=True, nullable=True)
    supplier_code = Column(String(100), default="", index=True)

    # Basic info
    name = Column(String(500), nullable=False, index=True)
    description = Column(Text, default="")
    short_description = Column(String(1000), default="")

    # Classification
    category = Column(String(200), default="", index=True)
    category_group = Column(String(200), default="", index=True)
    subcategory = Column(String(200), default="")
    brand = Column(String(200), default="")

    # Unified taxonomy (mapped from raw category fields via unified_taxonomy.map_to_unified)
    unified_category = Column(String(100), default="", index=True, nullable=True)
    unified_subcategory = Column(String(100), default="", index=True, nullable=True)

    # Pricing
    base_price = Column(Float, default=0.0)
    currency = Column(String(10), default="EUR")

    # Media
    images = Column(JSON, default=list)          # ["url1", "url2", ...]
    primary_image = Column(String(1000), default="")

    # Attributes
    colors = Column(JSON, default=list)          # [{"name": "Roșu", "hex": "#FF0000", "image": "url"}, ...]
    specifications = Column(JSON, default=dict)  # {"weight": "150g", "dimensions": "10x5x2cm", "material": "Plastic"}

    # Printing / Customization
    printing_options = Column(JSON, default=list)
    # [
    #   {
    #     "position": "Front",
    #     "max_width_mm": 50,
    #     "max_height_mm": 30,
    #     "techniques": [
    #       {"name": "Tampografie", "setup_cost": 25.0, "unit_cost": 0.5},
    #       {"name": "Serigrafie", "setup_cost": 35.0, "unit_cost": 0.3}
    #     ]
    #   }
    # ]

    # Stock & ordering
    stock = Column(Integer, default=0)
    min_order_qty = Column(Integer, default=1)

    # Status
    is_active = Column(Boolean, default=True, index=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_search_dict(self) -> dict:
        """Flatten product for Meilisearch indexing."""
        return {
            "id": self.id,
            "external_id": self.external_id or "",
            "integration_id": self.integration_id or "",
            "supplier_code": self.supplier_code or "",
            "name": self.name,
            "description": self.description,
            "short_description": self.short_description,
            "category": self.category,
            "category_group": self.category_group or "",
            "subcategory": self.subcategory,
            "unified_category": self.unified_category or "",
            "unified_subcategory": self.unified_subcategory or "",
            "brand": self.brand,
            "base_price": self.base_price,
            "currency": self.currency,
            "primary_image": self.primary_image or "",
            "images": self.images or [],
            "colors": self.colors or [],
            "specifications": self.specifications or {},
            "stock": self.stock,
            "min_order_qty": self.min_order_qty,
            "is_active": self.is_active,
            "last_synced_at": str(self.last_synced_at) if self.last_synced_at else "",
        }

    def to_card_dict(self, margin_percent: float = 30.0) -> dict:
        """Product summary for chat product cards."""
        sell_price = round(self.base_price * (1 + margin_percent / 100), 2)
        color_names = [c.get("name", "") for c in (self.colors or []) if c.get("name")]
        techniques = set()
        for opt in (self.printing_options or []):
            for tech in opt.get("techniques", []):
                techniques.add(tech.get("name", ""))

        return {
            "id": self.id,
            "supplier_code": self.supplier_code or "",
            "name": self.name,
            "description": self.description,
            "short_description": self.short_description,
            "category": self.category,
            "base_price": self.base_price,
            "sell_price": sell_price,
            "currency": self.currency,
            "image_url": self.primary_image,
            "primary_image": self.primary_image,
            "sku": self.external_id or "",
            "color_names": color_names[:5],
            "colors": self.colors or [],
            "material": (self.specifications or {}).get("material", ""),
            "size": (self.specifications or {}).get("size", ""),
            "print_area": (self.specifications or {}).get("print_area", ""),
            "customizable": bool(techniques),
            "printing_techniques": sorted(techniques),
            "min_quantity": self.min_order_qty,
            "min_order_qty": self.min_order_qty,
            "stock": self.stock,
        }
