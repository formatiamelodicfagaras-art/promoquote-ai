import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, engine, async_session
from app.routers import products, quotes, ai_agent, integrations, sync, settings, companies, brand_kit, image_proxy, auth, users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


_FREQ_INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
}


async def _auto_sync_loop():
    """Background loop: check integrations and trigger sync if overdue."""
    logger = logging.getLogger("auto_sync")
    first_run = True
    while True:
        try:
            await asyncio.sleep(300 if first_run else 3600)  # 5min first, then hourly
            first_run = False
            from app.models.integration import Integration
            from app.services.sync_service import sync_integration
            from sqlalchemy import select

            # Collect overdue integrations first, then sync ONE AT A TIME
            overdue = []
            async with async_session() as db:
                result = await db.execute(
                    select(Integration).where(
                        Integration.is_active == True,
                        Integration.sync_frequency.in_(list(_FREQ_INTERVALS.keys())),
                        Integration.last_sync_status != "in_progress",
                    )
                )
                for integration in result.scalars().all():
                    interval = _FREQ_INTERVALS.get(integration.sync_frequency)
                    if not interval:
                        continue
                    last = integration.last_sync_at
                    if last:
                        # Ensure both are timezone-aware for comparison
                        last_aware = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
                        if (datetime.now(timezone.utc) - last_aware) < interval:
                            continue
                    overdue.append(integration.id)

            # Sync sequentially to avoid SQLite "database locked" errors
            for integ_id in overdue:
                async with async_session() as db:
                    integ = await db.get(Integration, integ_id)
                    if not integ or integ.last_sync_status == "in_progress":
                        continue
                    logger.info(f"Auto-sync: starting {integ.name} (freq={integ.sync_frequency})")
                    integ.last_sync_status = "in_progress"
                    integ.last_sync_error = ""
                    await db.commit()
                    try:
                        count = await sync_integration(integ, db, lambda *a: None)
                        integ.last_sync_status = "success"
                        integ.last_sync_error = ""
                        integ.products_count = count
                        integ.last_sync_at = datetime.now(timezone.utc)
                        logger.info(f"Auto-sync: {integ.name} done — {count} products")
                    except Exception as e:
                        logger.exception(f"Auto-sync: {integ.name} failed")
                        integ.last_sync_status = "error"
                        integ.last_sync_error = str(e)[:1000]
                    await db.commit()
                # Small delay between syncs to let DB breathe
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Auto-sync loop error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Reset any stuck "in_progress" syncs from previous crashes
    from app.models.integration import Integration
    from sqlalchemy import update, select
    async with async_session() as db:
        await db.execute(
            update(Integration)
            .where(Integration.last_sync_status == "in_progress")
            .values(last_sync_status="error", last_sync_error="Server restarted during sync")
        )
        await db.commit()
    # Create default admin user if no users exist
    from app.models.user import User
    from app.services.auth_service import hash_password
    async with async_session() as db:
        result = await db.execute(select(User))
        if not result.scalars().first():
            admin = User(
                email="admin@demo.local",
                name="Admin",
                password_hash=hash_password("admin123"),
                is_admin=True,
            )
            db.add(admin)
            await db.commit()
            logging.getLogger("main").info(
                "Default admin created — email: admin@demo.local, password: admin123 "
                "(CHANGE THIS in production!)"
            )

    logging.getLogger("main").info("Database initialized")

    # Start auto-sync background task
    sync_task = asyncio.create_task(_auto_sync_loop())

    yield

    sync_task.cancel()
    await engine.dispose()


app = FastAPI(
    title="PromoQuote AI",
    description="AI-powered promotional product quoting system",
    version="1.0.0",
    lifespan=lifespan,
)

import os as _os
_cors_origins = [o.strip() for o in _os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(products.router, prefix="/api/products", tags=["Products"])
app.include_router(quotes.router, prefix="/api/quotes", tags=["Quotes"])
app.include_router(ai_agent.router, prefix="/api/chat", tags=["AI Agent"])
app.include_router(integrations.router, prefix="/api/integrations", tags=["Integrations"])
app.include_router(sync.router, prefix="/api/sync", tags=["Sync"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(companies.router, prefix="/api/companies", tags=["Companies"])
app.include_router(brand_kit.router, prefix="/api/brand-kit", tags=["Brand Kit"])
app.include_router(image_proxy.router, prefix="/api/img", tags=["Image Proxy"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "PromoQuote AI", "version": "1.0.0"}
