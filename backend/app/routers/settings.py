"""App settings CRUD - margins, company info, template config."""
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.settings import AppSettings, DEFAULT_SETTINGS
from app.routers.products import invalidate_margin_caches

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads/logos")


class SettingUpdate(BaseModel):
    value: str


class SettingResponse(BaseModel):
    key: str
    value: str
    value_type: str
    description: str
    group_name: str

    model_config = {"from_attributes": True}


class SettingsBatchUpdate(BaseModel):
    settings: dict[str, str]  # key -> value


# ── Seed defaults ──────────────────────────────────────────────────────
async def _seed_defaults(db: AsyncSession):
    result = await db.execute(select(AppSettings))
    existing = {s.key for s in result.scalars().all()}

    for s in DEFAULT_SETTINGS:
        if s["key"] not in existing:
            db.add(AppSettings(**s))

    await db.commit()


# ── GET all settings ───────────────────────────────────────────────────
@router.get("/", response_model=list[SettingResponse])
async def list_settings(db: AsyncSession = Depends(get_db)):
    await _seed_defaults(db)
    result = await db.execute(select(AppSettings).order_by(AppSettings.group_name, AppSettings.key))
    return result.scalars().all()


# ── GET settings by group ─────────────────────────────────────────────
@router.get("/group/{group_name}", response_model=list[SettingResponse])
async def get_settings_by_group(
    group_name: str, db: AsyncSession = Depends(get_db)
):
    await _seed_defaults(db)
    result = await db.execute(
        select(AppSettings).where(AppSettings.group_name == group_name)
    )
    return result.scalars().all()


# ── GET single setting ─────────────────────────────────────────────────
@router.get("/{key}", response_model=SettingResponse)
async def get_setting(key: str, db: AsyncSession = Depends(get_db)):
    await _seed_defaults(db)
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == key)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return setting


# ── UPDATE single setting ─────────────────────────────────────────────
@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str, data: SettingUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == key)
    )
    setting = result.scalar_one_or_none()

    if not setting:
        # Create new setting
        setting = AppSettings(key=key, value=data.value, group_name="general")
        db.add(setting)
    else:
        setting.value = data.value

    await db.commit()
    await db.refresh(setting)

    # Invalidate margin caches if margin-related setting changed
    if "margin" in key:
        invalidate_margin_caches()

    return setting


# ── BATCH UPDATE settings ─────────────────────────────────────────────
@router.put("/batch/update")
async def batch_update_settings(
    data: SettingsBatchUpdate, db: AsyncSession = Depends(get_db)
):
    updated = []
    for key, value in data.settings.items():
        result = await db.execute(
            select(AppSettings).where(AppSettings.key == key)
        )
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = value
            updated.append(key)
        else:
            db.add(AppSettings(key=key, value=value, group_name="general"))
            updated.append(key)

    await db.commit()

    # Invalidate margin caches if any margin-related setting changed
    if any("margin" in k for k in data.settings):
        invalidate_margin_caches()

    return {"updated": updated, "count": len(updated)}


# ── Category margins (special JSON setting) ───────────────────────────
@router.get("/margins/categories")
async def get_category_margins(db: AsyncSession = Depends(get_db)):
    """Get margin overrides per category."""
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "category_margins")
    )
    setting = result.scalar_one_or_none()
    if not setting:
        return {"margins": {}}
    try:
        return {"margins": json.loads(setting.value)}
    except (json.JSONDecodeError, TypeError):
        return {"margins": {}}


@router.put("/margins/categories")
async def update_category_margins(
    margins: dict[str, float], db: AsyncSession = Depends(get_db)
):
    """Update margin overrides per category."""
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "category_margins")
    )
    setting = result.scalar_one_or_none()

    value = json.dumps(margins, ensure_ascii=False)

    if setting:
        setting.value = value
    else:
        db.add(
            AppSettings(
                key="category_margins",
                value=value,
                value_type="json",
                description="Marje pe categorii",
                group_name="pricing",
            )
        )

    await db.commit()
    return {"margins": margins}


# ── Logo upload ──────────────────────────────────────────────────────
@router.post("/upload/logo")
async def upload_logo(file: UploadFile = File(...)):
    """Upload a company logo image. Returns URL to access it."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Doar fișiere imagine sunt acceptate")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Fișierul depășește 5MB")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "logo.png").suffix or ".png"
    filename = f"{uuid.uuid4()}{ext}"
    filepath = UPLOAD_DIR / filename
    filepath.write_bytes(content)

    url = f"/api/settings/logo/{filename}"
    return {"url": url, "path": str(filepath.resolve()), "filename": filename}


@router.get("/logo/{filename}")
async def get_logo(filename: str):
    """Serve uploaded logo file."""
    filepath = UPLOAD_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, "Logo not found")
    # Detect media type from extension
    ext = filepath.suffix.lower()
    media_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".webp": "image/webp"}
    return FileResponse(filepath, media_type=media_types.get(ext, "image/png"))


# ── Product image upload ─────────────────────────────────────────────
PRODUCT_IMG_DIR = Path("uploads/products")


@router.post("/upload/product-image")
async def upload_product_image(file: UploadFile = File(...)):
    """Upload a product image. Returns URL to access it."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Doar fișiere imagine sunt acceptate")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Fișierul depășește 5MB")

    # Auto-resize to max 400px and compress to save space
    try:
        from PIL import Image as PILImage
        import io as _io
        img = PILImage.open(_io.BytesIO(content))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((400, 400), PILImage.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, "JPEG", quality=80, optimize=True)
        content = buf.getvalue()
    except Exception:
        pass  # fallback: save original if resize fails

    PRODUCT_IMG_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.jpg"
    filepath = PRODUCT_IMG_DIR / filename
    filepath.write_bytes(content)

    url = f"/api/settings/product-image/{filename}"
    return {"url": url, "filename": filename}


@router.get("/product-image/{filename}")
async def get_product_image(filename: str):
    """Serve uploaded product image."""
    filepath = PRODUCT_IMG_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, "Image not found")
    ext = filepath.suffix.lower()
    media_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
    return FileResponse(filepath, media_type=media_types.get(ext, "image/png"))
