"""SQLite database package for soc-db.

Provides connection management, schema creation, query functions with
dual-read (SQLite / JSON) fallback, and JSON-to-SQLite migration.
"""

from __future__ import annotations

# Core infrastructure — safe to import immediately
from soc_db.db.connection import clear_connection_cache, get_connection, get_connection_cached, get_db_path
from soc_db.db.schema import create_tables, create_fts_index, drop_tables, rebuild_fts

# Query functions — imported lazily via getattr or direct import by callers
# to avoid circular imports when modules are created incrementally.

__all__ = [
    "get_connection",
    "get_connection_cached",
    "get_db_path",
    "clear_connection_cache",
    "create_tables",
    "create_fts_index",
    "drop_tables",
    "rebuild_fts",
    "get_all",
    "get_by_id",
    "search",
    "get_stats",
    "get_vendors",
    "filter_chips",
    "migrate",
    "validate_migration",
    "ensure_migrated",
]
