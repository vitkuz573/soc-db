"""SQLite database package for soc-db.

Provides connection management, schema creation, query functions with
dual-read (SQLite / JSON) fallback, and JSON-to-SQLite migration.
"""

from __future__ import annotations

# Core infrastructure — safe to import immediately
from soc_db.db.connection import clear_connection_cache, get_connection, get_connection_cached, get_db_path

# Migration
from soc_db.db.migrate import ensure_migrated, migrate, validate_migration

# Query functions — lazily resolved on first access
from soc_db.db.queries import (
    filter_chips,
    get_all,
    get_by_id,
    get_stats,
    get_vendors,
    search,
)
from soc_db.db.schema import create_fts_index, create_tables, drop_tables, rebuild_fts

__all__ = [
    "clear_connection_cache",
    "create_fts_index",
    "create_tables",
    "drop_tables",
    "ensure_migrated",
    "filter_chips",
    "get_all",
    "get_by_id",
    "get_connection",
    "get_connection_cached",
    "get_db_path",
    "get_stats",
    "get_vendors",
    "migrate",
    "rebuild_fts",
    "search",
    "validate_migration",
]
