import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sa_delete
from sse_starlette.sse import EventSourceResponse

from app.database import get_db, async_session
from app.models.integration import Integration
from app.schemas.integration import (
    IntegrationCreate,
    IntegrationUpdate,
    IntegrationResponse,
)
from app.config import get_settings
from app.routers.products import invalidate_margin_caches

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

# In-memory progress store for SSE streaming
_sync_progress: dict[str, dict] = {}


# Default integrations to seed. Credentials are intentionally empty —
# admins fill them in via the Integrations UI after first login.
# Supported integration_type values (parsers live in sync_service.py):
#   anda_present, easygifts, macma, midocean, roly, stamina, makito,
#   utt, promolog, sipec, bluecollection, generic_xml, inspirion.
DEFAULTS = [
    {
        "name": "generic_xml",
        "display_name": "Generic XML Feed",
        "integration_type": "generic_xml",
        "api_url": "",
        "api_key": "",
        "extra_config": {},
    },
]


# ── LIST ───────────────────────────────────────────────────────────────
@router.get("/", response_model=list[IntegrationResponse])
async def list_integrations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Integration).order_by(Integration.created_at))
    integrations = result.scalars().all()

    if not integrations:
        for default in DEFAULTS:
            db.add(Integration(**default))
        await db.commit()
        result = await db.execute(select(Integration).order_by(Integration.created_at))
        integrations = result.scalars().all()

    return integrations


# ── CREATE ─────────────────────────────────────────────────────────────
@router.post("/", response_model=IntegrationResponse, status_code=201)
async def create_integration(
    data: IntegrationCreate, db: AsyncSession = Depends(get_db)
):
    # Check unique name
    existing = await db.execute(select(Integration).where(Integration.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Integration '{data.name}' already exists")

    integration = Integration(**data.model_dump())
    db.add(integration)
    await db.commit()
    await db.refresh(integration)
    return integration


# ── GET ONE ────────────────────────────────────────────────────────────
@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_integration(integration_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Integration).where(Integration.id == integration_id)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration


# ── UPDATE ─────────────────────────────────────────────────────────────
@router.put("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    integration_id: str,
    data: IntegrationUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Integration).where(Integration.id == integration_id)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(integration, field, value)

    await db.commit()
    await db.refresh(integration)

    # Invalidate margin caches if margin was changed
    if "default_margin" in update_data:
        invalidate_margin_caches()

    return integration


# Also support PATCH for backwards compat
@router.patch("/{integration_id}", response_model=IntegrationResponse)
async def patch_integration(
    integration_id: str,
    data: IntegrationUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await update_integration(integration_id, data, db)


# ── DELETE ─────────────────────────────────────────────────────────────
@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: str, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Integration).where(Integration.id == integration_id)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    if integration.last_sync_status == "in_progress":
        raise HTTPException(
            status_code=409, detail="Cannot delete while sync is in progress"
        )

    await db.delete(integration)
    await db.commit()
    return {"detail": "Integration deleted", "id": integration_id}


# ── SYNC (trigger) ────────────────────────────────────────────────────
@router.post("/{integration_id}/sync")
async def trigger_sync(
    integration_id: str, db: AsyncSession = Depends(get_db)
):
    """Trigger product sync. Returns immediately; poll SSE for progress."""
    result = await db.execute(
        select(Integration).where(Integration.id == integration_id)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    if not integration.is_active:
        raise HTTPException(status_code=400, detail="Integration is not active")
    if integration.last_sync_status == "in_progress":
        raise HTTPException(status_code=409, detail="Sync already in progress")

    # Mark as in_progress
    integration.last_sync_status = "in_progress"
    integration.last_sync_error = ""
    await db.commit()

    # Initialize progress
    _sync_progress[integration_id] = {
        "stage": "starting",
        "current": 0,
        "total": 0,
        "percent": 0.0,
        "message": "Se pornește sincronizarea...",
    }

    # Run in background
    asyncio.create_task(_run_sync(integration_id, integration.name))

    return {"detail": "Sync started", "status": "in_progress"}


# ── SYNC STATUS (SSE) ─────────────────────────────────────────────────
@router.get("/{integration_id}/sync/status")
async def sync_status_stream(integration_id: str):
    """SSE stream of sync progress."""

    async def event_generator():
        while True:
            progress = _sync_progress.get(integration_id)
            if progress:
                yield {
                    "event": "progress",
                    "data": json.dumps(progress, ensure_ascii=False),
                }
                if progress.get("stage") in ("done", "error"):
                    # Send final event then clean up
                    await asyncio.sleep(0.5)
                    _sync_progress.pop(integration_id, None)
                    return
            else:
                yield {
                    "event": "progress",
                    "data": json.dumps(
                        {"stage": "idle", "current": 0, "total": 0, "percent": 0, "message": ""},
                        ensure_ascii=False,
                    ),
                }
                return

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


# ── Background sync runner ────────────────────────────────────────────
async def _run_sync(integration_id: str, source: str):
    """Background task to run sync with progress updates."""
    from app.services.sync_service import sync_integration

    start_time = datetime.now(timezone.utc)

    def progress_callback(stage: str, current: int, total: int, message: str = ""):
        percent = round((current / total * 100) if total > 0 else 0, 1)
        _sync_progress[integration_id] = {
            "stage": stage,
            "current": current,
            "total": total,
            "percent": percent,
            "message": message,
        }

    async with async_session() as db:
        result = await db.execute(
            select(Integration).where(Integration.id == integration_id)
        )
        integration = result.scalar_one_or_none()
        if not integration:
            return

        try:
            count = await sync_integration(integration, db, progress_callback)
            elapsed = int((datetime.now(timezone.utc) - start_time).total_seconds())

            integration.last_sync_status = "success"
            integration.last_sync_error = ""
            integration.products_count = count
            integration.last_sync_at = datetime.now(timezone.utc)
            integration.last_sync_duration = elapsed

            _sync_progress[integration_id] = {
                "stage": "done",
                "current": count,
                "total": count,
                "percent": 100.0,
                "message": f"Sincronizare completă: {count} produse în {elapsed}s",
            }

        except Exception as e:
            logger.exception(f"Sync failed for {source}")
            integration.last_sync_status = "error"
            integration.last_sync_error = str(e)[:1000]

            _sync_progress[integration_id] = {
                "stage": "error",
                "current": 0,
                "total": 0,
                "percent": 0,
                "message": f"Eroare: {str(e)[:200]}",
            }

        await db.commit()
