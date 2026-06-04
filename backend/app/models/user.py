from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.sql import func

from app.database import Base, generate_uuid


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(300), unique=True, nullable=False)
    name = Column(String(300), nullable=False)
    password_hash = Column(String(500), nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)
