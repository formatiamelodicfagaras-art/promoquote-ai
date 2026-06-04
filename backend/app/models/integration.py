from sqlalchemy import Column, String, Boolean, DateTime, Integer, Float, JSON
from sqlalchemy.sql import func

from app.database import Base, generate_uuid


class Integration(Base):
    __tablename__ = "integrations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), unique=True, index=True)  # "anda", "midocean", custom
    display_name = Column(String(200), default="")
    integration_type = Column(String(50), default="generic_xml")  # "anda_present", "midocean", "generic_xml", "woocommerce"

    # Connection
    api_url = Column(String(500), default="")
    api_key = Column(String(500), default="")
    api_user = Column(String(200), default="")
    api_password = Column(String(500), default="")
    extra_config = Column(JSON, default=dict)  # Additional URLs, headers, mapping, etc.

    # Pricing
    default_margin = Column(Float, default=30.0)

    # Sync schedule
    sync_frequency = Column(String(20), default="manual")  # "daily", "weekly", "manual"

    # Status
    is_active = Column(Boolean, default=False)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_status = Column(String(50), default="")  # "success", "error", "in_progress"
    last_sync_error = Column(String(1000), default="")
    last_sync_duration = Column(Integer, default=0)  # seconds
    products_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
