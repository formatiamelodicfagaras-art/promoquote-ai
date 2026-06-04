from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, async_session
from app.models.integration import Integration
from app.services.sync_service import sync_anda_products, sync_midocean_products

router = APIRouter()


@router.post("/{source}")
async def trigger_sync(
    source: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger product sync from a supplier. Runs in background."""
    if source not in ("anda", "midocean"):
        raise HTTPException(status_code=400, detail="Invalid source. Use 'anda' or 'midocean'")

    result = await db.execute(select(Integration).where(Integration.name == source))
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail=f"Integration '{source}' not found")
    if not integration.is_active:
        raise HTTPException(status_code=400, detail=f"Integration '{source}' is not active")
    if integration.last_sync_status == "in_progress":
        raise HTTPException(status_code=409, detail="Sync already in progress")

    # Mark as in_progress
    integration.last_sync_status = "in_progress"
    integration.last_sync_error = ""
    await db.commit()

    if source == "anda":
        background_tasks.add_task(_run_anda_sync, integration.id)
    elif source == "midocean":
        background_tasks.add_task(_run_midocean_sync, integration.id)
    else:
        raise HTTPException(status_code=501, detail=f"Sync for '{source}' not yet implemented")

    return {"detail": f"Sync started for {source}", "status": "in_progress"}


async def _run_anda_sync(integration_id: str):
    """Background task to sync ANDA products."""
    async with async_session() as db:
        result = await db.execute(select(Integration).where(Integration.id == integration_id))
        integration = result.scalar_one_or_none()
        if not integration:
            return

        try:
            count = await sync_anda_products(integration, db)
            integration.last_sync_status = "success"
            integration.last_sync_error = ""
            integration.products_count = count
        except Exception as e:
            integration.last_sync_status = "error"
            integration.last_sync_error = str(e)[:1000]

        await db.commit()


async def _run_midocean_sync(integration_id: str):
    """Background task to sync Midocean products."""
    async with async_session() as db:
        result = await db.execute(select(Integration).where(Integration.id == integration_id))
        integration = result.scalar_one_or_none()
        if not integration:
            return

        try:
            count = await sync_midocean_products(integration, db)
            integration.last_sync_status = "success"
            integration.last_sync_error = ""
            integration.products_count = count
        except Exception as e:
            integration.last_sync_status = "error"
            integration.last_sync_error = str(e)[:1000]

        await db.commit()


@router.get("/status")
async def sync_status(db: AsyncSession = Depends(get_db)):
    """Get sync status for all integrations."""
    result = await db.execute(select(Integration))
    integrations = result.scalars().all()
    return [
        {
            "source": i.name,
            "display_name": i.display_name,
            "is_active": i.is_active,
            "last_sync_at": i.last_sync_at.isoformat() if i.last_sync_at else None,
            "last_sync_status": i.last_sync_status,
            "last_sync_error": i.last_sync_error,
            "products_count": i.products_count,
        }
        for i in integrations
    ]
