"""SQLite connection management.

Provides synchronous connection opening with WAL mode, Row factory,
and a module-level cached connection for reuse within a process.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from soc_db.config import settings

_connection_cache: sqlite3.Connection | None = None
"""Module-level cached connection.  Cleared when SOC_DB_USE_JSON toggles."""


def get_db_path() -> Path:
    """Resolve the SQLite database path from settings.

    Default path: ``<project-root>/data/soc-db.db`` — same root resolution
    used by ``soc_db.common.DATA_DIR``.

    Returns:
        Path to the SQLite database file.
    """
    path = settings.db_path
    if isinstance(path, str):
        path = Path(path)
    return path.resolve()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a synchronous SQLite connection.

    Enables WAL journal mode and foreign keys, and sets
    ``sqlite3.Row`` as the row factory.

    Args:
        db_path: Path to the database file.  ``None`` uses the default
            path from :func:`get_db_path`.

    Returns:
        An open :class:`sqlite3.Connection`.
    """
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_connection_cached(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Return a module-level cached connection.

    Creates the connection on first call and reuses it for subsequent
    calls.  The cache is a plain module variable — it persists for the
    lifetime of the process.

    Args:
        db_path: Path to the database file.  ``None`` uses the default.

    Returns:
        An open :class:`sqlite3.Connection`.
    """
    global _connection_cache
    if _connection_cache is None:
        _connection_cache = get_connection(db_path)
    return _connection_cache


def clear_connection_cache() -> None:
    """Close and clear the cached connection.

    Call when ``SOC_DB_USE_JSON`` transitions to allow a fresh connection
    to be created on the next call.
    """
    global _connection_cache
    if _connection_cache is not None:
        _connection_cache.close()
        _connection_cache = None
