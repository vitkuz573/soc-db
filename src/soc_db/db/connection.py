"""SQLite connection management.

Provides synchronous connection opening with WAL mode, Row factory,
and a per-thread cached connection for reuse within a process.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from soc_db.config import settings

_thread_local = threading.local()
"""Thread-local storage for the cached connection."""


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
    """Return a per-thread cached connection.

    Creates the connection on first call per thread and reuses it for
    subsequent calls within the same thread.  The cache uses
    ``threading.local()`` so connections are not shared across threads
    (SQLite connections are not thread-safe).

    Args:
        db_path: Path to the database file.  ``None`` uses the default.

    Returns:
        An open :class:`sqlite3.Connection`.
    """
    conn = getattr(_thread_local, "cached_connection", None)
    if conn is None:
        conn = get_connection(db_path)
        _thread_local.cached_connection = conn
    return conn


def clear_connection_cache() -> None:
    """Close and clear the per-thread cached connection.

    Call when ``SOC_DB_USE_JSON`` transitions to allow a fresh connection
    to be created on the next call in the current thread.
    """
    conn = getattr(_thread_local, "cached_connection", None)
    if conn is not None:
        conn.close()
        _thread_local.cached_connection = None
