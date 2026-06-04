from sqlalchemy import Column, String, Boolean
from sqlalchemy.sql import func
from sqlalchemy import DateTime

from app.database import Base, generate_uuid


class Company(Base):
    __tablename__ = "companies"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(300), default="")
    cui = Column(String(50), default="")
    address = Column(String(500), default="")
    phone = Column(String(50), default="")
    email = Column(String(300), default="")
    website = Column(String(500), default="")
    bank = Column(String(300), default="")
    iban = Column(String(100), default="")
    logo_url = Column(String(1000), default="")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
