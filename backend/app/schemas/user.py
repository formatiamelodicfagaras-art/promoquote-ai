from pydantic import BaseModel, EmailStr
from datetime import datetime


# --- Auth schemas ---

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str
    is_admin: bool = False


class ProfileUpdate(BaseModel):
    name: str | None = None
    password: str | None = None


# --- User schemas (admin) ---

class UserCreate(BaseModel):
    email: str
    name: str
    password: str
    is_admin: bool = False


class UserUpdate(BaseModel):
    email: str | None = None
    name: str | None = None
    password: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    is_admin: bool
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


# Resolve forward reference
TokenResponse.model_rebuild()
