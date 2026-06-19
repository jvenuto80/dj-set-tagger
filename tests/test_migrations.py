import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.services.database import run_migrations


@pytest.mark.asyncio
async def test_run_migrations_adds_columns_and_indexes():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                """
                CREATE TABLE tracks (
                    id INTEGER PRIMARY KEY,
                    filepath VARCHAR NOT NULL,
                    filename VARCHAR NOT NULL,
                    directory VARCHAR NOT NULL,
                    status VARCHAR DEFAULT 'pending'
                )
                """
            ))
            await conn.execute(text(
                """
                CREATE TABLE match_candidates (
                    id INTEGER PRIMARY KEY,
                    track_id INTEGER NOT NULL
                )
                """
            ))

            await run_migrations(conn)

            columns_result = await conn.execute(text("PRAGMA table_info(tracks)"))
            columns = {row[1] for row in columns_result.fetchall()}
            assert "fingerprint_hash" in columns
            assert "ai_genre" in columns
            assert "review_status" in columns
            assert "consistency_flag" in columns

            tracks_indexes = await conn.execute(text("PRAGMA index_list(tracks)"))
            tracks_index_names = {row[1] for row in tracks_indexes.fetchall()}
            assert "ix_tracks_status" in tracks_index_names

            match_indexes = await conn.execute(text("PRAGMA index_list(match_candidates)"))
            match_index_names = {row[1] for row in match_indexes.fetchall()}
            assert "ix_match_candidates_track_id" in match_index_names

            applied_result = await conn.execute(text("SELECT name FROM schema_migrations"))
            applied_before = {row[0] for row in applied_result.fetchall()}
            assert "tracks_add_status_index" in applied_before
            assert "match_candidates_add_track_id_index" in applied_before

            await run_migrations(conn)

            applied_again_result = await conn.execute(text("SELECT name FROM schema_migrations"))
            applied_after = [row[0] for row in applied_again_result.fetchall()]
            assert len(applied_after) == len(set(applied_after))
            assert set(applied_after) == applied_before
    finally:
        await engine.dispose()
