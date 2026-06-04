from pydantic import BaseModel
from datetime import datetime


class CompanyCreate(BaseModel):
    name: str
    cui: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    bank: str = ""
    iban: str = ""
    logo_url: str = ""
    is_default: bool = False


class CompanyUpdate(BaseModel):
    name: str | None = None
    cui: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    bank: str | None = None
    iban: str | None = None
    logo_url: str | None = None
    is_default: bool | None = None


class CompanyResponse(BaseModel):
    id: str
    name: str
    cui: str
    address: str
    phone: str
    email: str
    website: str
    bank: str
    iban: str
    logo_url: str
    is_default: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
