import uuid

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Enable WAL mode + foreign keys for SQLite
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Lightweight migrations for new columns on existing tables
    async with engine.begin() as conn:
        await _add_column_if_missing(conn, "products", "supplier_code", "VARCHAR(100) DEFAULT ''")
        await _add_column_if_missing(conn, "quote_items", "product_color", "VARCHAR(200) DEFAULT ''")
        await _add_column_if_missing(conn, "quote_items", "product_size", "VARCHAR(200) DEFAULT ''")
        await _add_column_if_missing(conn, "quotes", "company_id", "VARCHAR(36)")


async def _add_column_if_missing(conn, table: str, column: str, col_type: str):
    """Add a column to an existing SQLite table if it doesn't exist."""
    import sqlalchemy as sa
    import logging
    result = await conn.execute(sa.text(f"PRAGMA table_info({table})"))
    columns = [row[1] for row in result.fetchall()]
    if column not in columns:
        await conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        logging.getLogger("database").info(f"Added column {column} to {table}")
