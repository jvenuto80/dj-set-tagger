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

        # Ensure migration tracking exists before applying migrations
        await conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name VARCHAR PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))

        # Run migrations for new columns/indexes
        await run_migrations(conn)
    
    # Migrate settings.json to database if needed
    await _migrate_settings_json()


async def _table_columns(conn, table_name: str) -> set[str]:
    result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


async def _applied_migrations(conn) -> set[str]:
    result = await conn.execute(text("SELECT name FROM schema_migrations"))
    return {row[0] for row in result.fetchall()}


async def _record_migration(conn, name: str):
    await conn.execute(
        text("INSERT OR IGNORE INTO schema_migrations (name) VALUES (:name)"),
        {"name": name},
    )


async def run_migrations(conn):
    """Run idempotent schema migrations and fail loudly on migration errors."""
    await conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name VARCHAR PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    ))

    track_columns = await _table_columns(conn, "tracks")
    applied = await _applied_migrations(conn)

    migrations = [
        {
            "name": "tracks_add_fingerprint_hash",
            "sql": "ALTER TABLE tracks ADD COLUMN fingerprint_hash VARCHAR(32)",
            "already_applied": "fingerprint_hash" in track_columns,
            "log": "Added fingerprint_hash column to tracks table",
        },
        {
            "name": "tracks_add_ai_genre",
            "sql": "ALTER TABLE tracks ADD COLUMN ai_genre VARCHAR",
            "already_applied": "ai_genre" in track_columns,
            "log": "Added ai_genre column to tracks table",
        },
        {
            "name": "tracks_add_ai_genre_confidence",
            "sql": "ALTER TABLE tracks ADD COLUMN ai_genre_confidence INTEGER",
            "already_applied": "ai_genre_confidence" in track_columns,
            "log": "Added ai_genre_confidence column to tracks table",
        },
        {
            "name": "tracks_add_ai_genre_source",
            "sql": "ALTER TABLE tracks ADD COLUMN ai_genre_source VARCHAR",
            "already_applied": "ai_genre_source" in track_columns,
            "log": "Added ai_genre_source column to tracks table",
        },
        {
            "name": "tracks_add_mik_bpm",
            "sql": "ALTER TABLE tracks ADD COLUMN mik_bpm FLOAT",
            "already_applied": "mik_bpm" in track_columns,
            "log": "Added mik_bpm column to tracks table",
        },
        {
            "name": "tracks_add_mik_key",
            "sql": "ALTER TABLE tracks ADD COLUMN mik_key VARCHAR",
            "already_applied": "mik_key" in track_columns,
            "log": "Added mik_key column to tracks table",
        },
        {
            "name": "tracks_add_mik_energy",
            "sql": "ALTER TABLE tracks ADD COLUMN mik_energy INTEGER",
            "already_applied": "mik_energy" in track_columns,
            "log": "Added mik_energy column to tracks table",
        },
        {
            "name": "tracks_add_fingerprint_raw",
            "sql": "ALTER TABLE tracks ADD COLUMN fingerprint_raw TEXT",
            "already_applied": "fingerprint_raw" in track_columns,
            "log": "Added fingerprint_raw column to tracks table",
        },
        {
            "name": "tracks_add_ai_reasoning",
            "sql": "ALTER TABLE tracks ADD COLUMN ai_reasoning TEXT",
            "already_applied": "ai_reasoning" in track_columns,
            "log": "Added ai_reasoning column to tracks table",
        },
        {
            "name": "tracks_add_review_status",
            "sql": "ALTER TABLE tracks ADD COLUMN review_status VARCHAR",
            "already_applied": "review_status" in track_columns,
            "log": "Added review_status column to tracks table",
        },
        {
            "name": "tracks_add_consistency_flag",
            "sql": "ALTER TABLE tracks ADD COLUMN consistency_flag VARCHAR",
            "already_applied": "consistency_flag" in track_columns,
            "log": "Added consistency_flag column to tracks table",
        },
        {
            "name": "tracks_add_status_index",
            "sql": "CREATE INDEX IF NOT EXISTS ix_tracks_status ON tracks (status)",
            "already_applied": False,
            "log": "Ensured ix_tracks_status index on tracks.status",
        },
        {
            "name": "match_candidates_add_track_id_index",
            "sql": "CREATE INDEX IF NOT EXISTS ix_match_candidates_track_id ON match_candidates (track_id)",
            "already_applied": False,
            "log": "Ensured ix_match_candidates_track_id index on match_candidates.track_id",
        },
    ]

    for migration in migrations:
        name = migration["name"]
        if name in applied:
            continue

        if migration["already_applied"]:
            await _record_migration(conn, name)
            logger.info(f"Marked existing migration as applied: {name}")
            continue

        try:
            async with conn.begin_nested():
                await conn.execute(text(migration["sql"]))
                await _record_migration(conn, name)
            logger.info(migration["log"])
        except Exception as exc:
            raise RuntimeError(f"Migration failed [{name}]: {exc}") from exc


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
