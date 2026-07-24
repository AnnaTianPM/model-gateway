"""Database migration runner."""

from __future__ import annotations

import hashlib
import logging

import aiosqlite

from app.settings import get_settings
from app.storage import schema

logger = logging.getLogger(__name__)

MIGRATIONS = [
    {
        "version": 1,
        "name": "001_initial_schema",
        "statements": schema.ALL_TABLES_SQL,
    },
]


async def run_migrations(db: aiosqlite.Connection) -> None:
    """Run pending database migrations."""
    settings = get_settings()
    app_version = settings.version
    git_commit = settings.git_commit

    # Ensure schema_migrations table exists
    await db.execute(schema.SCHEMA_MIGRATIONS_SQL)
    await db.commit()

    cursor = await db.execute("SELECT schema_version FROM schema_migrations")
    rows = await cursor.fetchall()
    await cursor.close()
    applied_versions = {row[0] for row in rows}

    for migration in MIGRATIONS:
        version = migration["version"]
        if version in applied_versions:
            continue

        logger.info("Applying migration %s: %s", version, migration["name"])
        all_sql = "\n".join(migration["statements"])
        checksum = hashlib.sha256(all_sql.encode()).hexdigest()

        try:
            # Use executescript for multi-statement SQL (CREATE TABLE + CREATE INDEX)
            await db.executescript(all_sql)

            await db.execute(
                """INSERT INTO schema_migrations (schema_version, migration_name, checksum, applied_at, app_version, git_commit)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?)""",
                (version, migration["name"], checksum, app_version, git_commit),
            )
            await db.commit()
            logger.info("Migration %s applied successfully.", version)
        except Exception as e:
            await db.rollback()
            logger.error("Migration %s failed: %s", version, e)
            raise
