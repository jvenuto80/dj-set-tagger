"""
Database service - SQLAlchemy async setup
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from contextlib import asynccontextmanager
from backend.config import settings
from loguru import logger

Base = declarative_base()

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True
)

# Create async session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        # Import all models to ensure they're registered
        from backend.models.track import Track, MatchCandidate
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized")
        
        # Run migrations for new columns
        await run_migrations(conn)


async def run_migrations(conn):
    """Run database migrations for new columns"""
    # Check and add fingerprint_hash column if missing
    try:
        result = await conn.execute(text("PRAGMA table_info(tracks)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'fingerprint_hash' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN fingerprint_hash VARCHAR(32)"
            ))
            logger.info("Added fingerprint_hash column to tracks table")
    except Exception as e:
        logger.warning(f"Migration check failed (may be normal) [{type(e).__name__}]: {e}")


@asynccontextmanager
async def get_db():
    """Get database session context manager"""
    async with async_session() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise e
