from pydantic import BaseModel
from datetime import datetime


class IntegrationCreate(BaseModel):
    name: str
    display_name: str
    integration_type: str = "generic_xml"  # "anda_present", "midocean", "generic_xml", "woocommerce"
    api_url: str = ""
    api_key: str = ""
    api_user: str = ""
    api_password: str = ""
    extra_config: dict = {}
    default_margin: float = 30.0
    sync_frequency: str = "manual"  # "daily", "weekly", "manual"
    is_active: bool = False


class IntegrationUpdate(BaseModel):
    display_name: str | None = None
    integration_type: str | None = None
    api_url: str | None = None
    api_key: str | None = None
    api_user: str | None = None
    api_password: str | None = None
    extra_config: dict | None = None
    default_margin: float | None = None
    sync_frequency: str | None = None
    is_active: bool | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None


class IntegrationResponse(BaseModel):
    id: str
    name: str
    display_name: str
    integration_type: str
    api_url: str
    api_key: str
    api_user: str
    api_password: str
    extra_config: dict
    default_margin: float
    sync_frequency: str
    is_active: bool
    last_sync_at: datetime | None = None
    last_sync_status: str
    last_sync_error: str
    last_sync_duration: int
    products_count: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SyncProgress(BaseModel):
    stage: str  # "download", "parse", "save", "index", "done", "error"
    current: int = 0
    total: int = 0
    percent: float = 0.0
    message: str = ""
