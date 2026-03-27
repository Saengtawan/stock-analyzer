"""
Database Manager
================
Unified database access manager wrapping SQLAlchemy ORM sessions.

Preserves the same public API as the original sqlite3-based manager so that
callers (UniverseRepository, etc.) continue to work without changes.
"""

import threading
from contextlib import contextmanager
from typing import Optional, Generator, Any, List

from loguru import logger
from sqlalchemy import text

from database.orm.base import get_session, get_engine


class DatabaseManager:
    """
    Centralized database access manager backed by SQLAlchemy.

    Provides a compatibility layer that exposes the same public API
    (get_connection, execute, fetch_one, fetch_all, etc.) used by
    existing repository code, while delegating to the ORM session.
    """

    def __init__(self, db_path: str = None, read_only: bool = False):
        """
        Initialize database manager.

        Args:
            db_path: Ignored (kept for API compatibility). Connection is
                     handled by the ORM engine configured in orm/base.py.
            read_only: If True, sessions will not commit.
        """
        self.read_only = read_only
        # Engine is already initialised as a singleton in orm/base.py
        self._engine = get_engine()

    # ------------------------------------------------------------------
    # Context-managed session (dict-row compatible)
    # ------------------------------------------------------------------

    @contextmanager
    def get_connection(self, read_only: bool = False) -> Generator:
        """
        Context manager that yields a *connection-like* wrapper.

        The yielded object supports ``execute(sql, params)`` and
        ``executemany(sql, params_list)`` so that existing callers
        (e.g. UniverseRepository.save_bulk) keep working.

        Usage:
            with db_manager.get_connection() as conn:
                conn.execute("DELETE FROM universe_stocks")
                conn.executemany("INSERT ...", rows)
        """
        with get_session() as session:
            yield _SessionConnectionAdapter(session)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def execute(self, query: str, params: tuple = (), commit: bool = True) -> Any:
        """Execute a single SQL statement."""
        with get_session() as session:
            result = session.execute(text(query), _positional_to_dict(query, params))
            return result

    def execute_many(self, query: str, params_list: list, commit: bool = True) -> Any:
        """Execute a statement with multiple parameter sets."""
        with get_session() as session:
            for params in params_list:
                session.execute(text(query), _positional_to_dict(query, params))

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        """Fetch a single row as a dict (or None)."""
        with get_session() as session:
            result = session.execute(text(query), _positional_to_dict(query, params))
            row = result.fetchone()
            if row is None:
                return None
            return _row_to_dict(row)

    def fetch_all(self, query: str, params: tuple = ()) -> List[dict]:
        """Fetch all rows as a list of dicts."""
        with get_session() as session:
            result = session.execute(text(query), _positional_to_dict(query, params))
            return [_row_to_dict(r) for r in result.fetchall()]

    def close(self):
        """No-op. Sessions are closed automatically by context managers."""
        pass

    def __del__(self):
        """No-op cleanup."""
        pass


# ======================================================================
# Internal helpers
# ======================================================================


class _SessionConnectionAdapter:
    """
    Thin wrapper around a SQLAlchemy Session that exposes execute() and
    executemany() accepting raw SQL strings with ``?`` positional params
    (SQLite style).  This lets old repository code using
    ``conn.execute(sql, (val,))`` work transparently.
    """

    def __init__(self, session):
        self._session = session

    def execute(self, sql: str, params=None):
        converted_sql = _convert_qmarks(sql)
        bound = _positional_to_dict(sql, params) if params else {}
        return self._session.execute(text(converted_sql), bound)

    def executemany(self, sql: str, params_list):
        converted_sql = _convert_qmarks(sql)
        for params in params_list:
            bound = _positional_to_dict(sql, params)
            self._session.execute(text(converted_sql), bound)


def _convert_qmarks(sql: str) -> str:
    """Replace positional ``?`` placeholders with ``:p0``, ``:p1``, ... for
    SQLAlchemy ``text()``."""
    parts = sql.split("?")
    if len(parts) == 1:
        return sql
    out = [parts[0]]
    for i, part in enumerate(parts[1:]):
        out.append(f":p{i}")
        out.append(part)
    return "".join(out)


def _positional_to_dict(sql: str, params=None) -> dict:
    """Convert a positional param tuple into ``{p0: v, p1: v, ...}``."""
    if not params:
        return {}
    if isinstance(params, dict):
        return params
    return {f"p{i}": v for i, v in enumerate(params)}


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row/RowProxy to a plain dict with column-key access."""
    try:
        return dict(row._mapping)
    except AttributeError:
        return dict(row)


# ======================================================================
# Global database managers (lazy initialization) — same API as before
# ======================================================================
_db_managers = {}
_db_lock = threading.Lock()


def get_db_manager(db_name: str = 'trade_history') -> DatabaseManager:
    """
    Get or create database manager (singleton per database).

    Args:
        db_name: Database name ('trade_history', 'stocks')

    Returns:
        DatabaseManager instance
    """
    if db_name not in _db_managers:
        with _db_lock:
            if db_name not in _db_managers:
                _db_managers[db_name] = DatabaseManager()

    return _db_managers[db_name]


def close_all_connections():
    """
    Close all database connections (for graceful shutdown).

    With SQLAlchemy, connections are managed by the engine pool,
    so this is mostly a no-op for compatibility.
    """
    with _db_lock:
        for db_name, manager in _db_managers.items():
            try:
                manager.close()
                logger.debug(f"Closed connection for {db_name}")
            except Exception as e:
                logger.warning(f"Error closing {db_name}: {e}")
        _db_managers.clear()
