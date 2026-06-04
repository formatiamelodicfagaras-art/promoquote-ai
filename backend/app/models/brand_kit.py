from sqlalchemy import Column, String, Float, Text, DateTime, JSON
from sqlalchemy.sql import func

from app.database import Base, generate_uuid


class BrandKit(Base):
    __tablename__ = "brand_kits"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(200), default="")
    client_name = Column(String(200), default="")
    logo_path = Column(String(500), default="")
    colors = Column(JSON, default=list)          # ["red", "black"]
    selected_products = Column(JSON, default=list)  # [{sku, supplier, name, ...}]
    mockup_overrides = Column(JSON, default=dict)   # {sku: {x_percent, y_percent, ...}}
    pdf_path = Column(String(500), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MockupZoneOverride(Base):
    __tablename__ = "mockup_zone_overrides"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    product_sku = Column(String(100), nullable=False, index=True)
    supplier = Column(String(50), nullable=False)
    x_percent = Column(Float, default=25.0)
    y_percent = Column(Float, default=25.0)
    width_percent = Column(Float, default=40.0)
    height_percent = Column(Float, default=30.0)
    opacity = Column(Float, default=0.9)
    blend_mode = Column(String(20), default="multiply")
    rotation = Column(Float, default=0.0)
    warp = Column(String(20), default="none")
    warp_intensity = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
