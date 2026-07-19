"""SQLite connection management.

Provides synchronous connection opening with WAL mode, Row factory,
and a per-thread cached connection for reuse within a process.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from pathlib import Path

import aiosqlite

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


# ---------------------------------------------------------------------------
# Async connection pool (aiosqlite)
# ---------------------------------------------------------------------------


class AsyncConnectionPool:
    """Async SQLite connection pool using aiosqlite.

    Maintains up to *max_size* idle connections.  Connections are
    created lazily on first ``acquire()`` and reused until the pool
    is closed.  WAL journal mode and ``aiosqlite.Row`` row factory
    are set on each new connection.

    Args:
        db_path: Path to the SQLite database file.
        max_size: Maximum number of idle connections to retain.
    """

    def __init__(self, db_path: Path, max_size: int = 5) -> None:
        self._db_path = db_path
        self._max_size = max_size
        self._sem = asyncio.Semaphore(max_size)
        self._connections: list[aiosqlite.Connection] = []
        self._closed = False

    async def acquire(self) -> aiosqlite.Connection:
        """Acquire a connection from the pool (or create one).

        Blocks (asynchronously) if the pool has reached *max_size*
        and all connections are currently in use.
        """
        await self._sem.acquire()
        if self._connections:
            conn = self._connections.pop()
        else:
            conn = await aiosqlite.connect(str(self._db_path))
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
        return conn

    async def release(self, conn: aiosqlite.Connection) -> None:
        """Return a connection to the pool.

        If the pool has been closed the connection is discarded.
        """
        if self._closed:
            await conn.close()
        else:
            self._connections.append(conn)
        self._sem.release()

    async def close(self) -> None:
        """Close all idle connections in the pool and prevent reuse."""
        self._closed = True
        for conn in self._connections:
            await conn.close()
        self._connections.clear()

    @property
    def size(self) -> int:
        """Number of connections currently idle in the pool."""
        return len(self._connections)


_async_pool: AsyncConnectionPool | None = None


def get_async_connection() -> AsyncConnectionPool:
    """Return the global async connection pool singleton.

    The pool is created on first call with the database path and
    max size from ``settings``.
    """
    global _async_pool
    if _async_pool is None:
        _async_pool = AsyncConnectionPool(get_db_path(), settings.async_pool_size)
    return _async_pool
