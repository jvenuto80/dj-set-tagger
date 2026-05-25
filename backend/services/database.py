"""
Database service - SQLAlchemy async setup
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text, select
from contextlib import asynccontextmanager
from backend.config import settings
from loguru import logger
import json
import os

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
        from backend.models.track import Track, MatchCandidate, AppSettingDB
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized")
        
        # Run migrations for new columns
        await run_migrations(conn)
    
    # Migrate settings.json to database if needed
    await _migrate_settings_json()


async def run_migrations(conn):
    """Run database migrations for new columns"""
    try:
        result = await conn.execute(text("PRAGMA table_info(tracks)"))
        columns = [row[1] for row in result.fetchall()]
        
        # Audio fingerprint column
        if 'fingerprint_hash' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN fingerprint_hash VARCHAR(32)"
            ))
            logger.info("Added fingerprint_hash column to tracks table")
        
        # AI genre classification columns
        if 'ai_genre' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN ai_genre VARCHAR"
            ))
            logger.info("Added ai_genre column to tracks table")
        
        if 'ai_genre_confidence' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN ai_genre_confidence INTEGER"
            ))
            logger.info("Added ai_genre_confidence column to tracks table")
        
        if 'ai_genre_source' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN ai_genre_source VARCHAR"
            ))
            logger.info("Added ai_genre_source column to tracks table")
        
        # Mixed In Key cached fields
        if 'mik_bpm' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN mik_bpm FLOAT"
            ))
            logger.info("Added mik_bpm column to tracks table")
        
        if 'mik_key' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN mik_key VARCHAR"
            ))
            logger.info("Added mik_key column to tracks table")
        
        if 'mik_energy' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN mik_energy INTEGER"
            ))
            logger.info("Added mik_energy column to tracks table")
        
        # Raw Chromaprint fingerprint for similarity comparison
        if 'fingerprint_raw' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN fingerprint_raw TEXT"
            ))
            logger.info("Added fingerprint_raw column to tracks table")

        # Phase 4: review queue + consistency pass
        if 'ai_reasoning' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN ai_reasoning TEXT"
            ))
            logger.info("Added ai_reasoning column to tracks table")

        if 'review_status' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN review_status VARCHAR"
            ))
            logger.info("Added review_status column to tracks table")

        if 'consistency_flag' not in columns:
            await conn.execute(text(
                "ALTER TABLE tracks ADD COLUMN consistency_flag VARCHAR"
            ))
            logger.info("Added consistency_flag column to tracks table")

    except Exception as e:
        logger.warning(f"Migration check failed (may be normal) [{type(e).__name__}]: {e}")


async def clear_all_tracks():
    """Drop all track data (tracks, match_candidates, library_suggestions) but keep settings"""
    async with engine.begin() as conn:
        for table in ["match_candidates", "library_suggestions", "tracks"]:
            try:
                result = await conn.execute(text(f"DELETE FROM {table}"))
                logger.info(f"Cleared {result.rowcount} rows from {table}")
            except Exception:
                pass  # Table may not exist yet
        logger.info("All track data cleared")


@asynccontextmanager
async def get_db():
    """Get database session context manager"""
    async with async_session() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise e


async def _migrate_settings_json():
    """One-time migration: import settings.json into database if it exists"""
    settings_file = os.path.join(settings.config_dir, "settings.json")
    if not os.path.exists(settings_file):
        return
    
    try:
        with open(settings_file, "r") as f:
            data = json.load(f)
        
        if not data:
            return
        
        # Check if we already have settings in the database
        existing = await load_saved_settings_db()
        if existing:
            # Already migrated, skip
            return
        
        # Write each setting to the database
        await save_settings_db(data)
        
        # Rename the old file so we don't re-migrate
        os.rename(settings_file, settings_file + ".migrated")
        logger.info("Migrated settings.json to database")
    except Exception as e:
        logger.warning(f"Failed to migrate settings.json: {e}")


async def load_saved_settings_db() -> dict:
    """Load saved settings from database"""
    from backend.models.track import AppSettingDB
    
    async with async_session() as session:
        result = await session.execute(select(AppSettingDB))
        rows = result.scalars().all()
        
        data = {}
        for row in rows:
            try:
                data[row.key] = json.loads(row.value)
            except (json.JSONDecodeError, TypeError):
                data[row.key] = row.value
        return data


async def save_settings_db(data: dict):
    """Save settings to database"""
    from backend.models.track import AppSettingDB
    
    async with async_session() as session:
        for key, value in data.items():
            serialized = json.dumps(value) if not isinstance(value, str) else json.dumps(value)
            existing = await session.execute(
                select(AppSettingDB).where(AppSettingDB.key == key)
            )
            row = existing.scalar_one_or_none()
            if row:
                row.value = serialized
            else:
                session.add(AppSettingDB(key=key, value=serialized))
        await session.commit()
