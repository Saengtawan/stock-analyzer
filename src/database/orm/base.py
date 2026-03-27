"""
SQLAlchemy engine + session factory.

SQLite now, PostgreSQL later — change DATABASE_URL to switch.
"""

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------
# Default: SQLite at data/trade_history.db (relative to project root).
# Override with DATABASE_URL env var for PostgreSQL:
#   export DATABASE_URL="postgresql://user:pass@host:5432/stock_analyzer"
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # src/database/orm -> project root
_DEFAULT_SQLITE_PATH = _PROJECT_ROOT / "data" / "trade_history.db"
_DEFAULT_URL = f"sqlite:///{_DEFAULT_SQLITE_PATH}"

DATABASE_URL: str = os.environ.get("DATABASE_URL", _DEFAULT_URL)


# ---------------------------------------------------------------------------
# Base class for all models
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Engine (singleton)
# ---------------------------------------------------------------------------
_engine = None


def get_engine(url: str | None = None):
    """Return the singleton engine (created on first call)."""
    global _engine
    if _engine is None:
        db_url = url or DATABASE_URL
        is_sqlite = db_url.startswith("sqlite")

        connect_args = {}
        if is_sqlite:
            # Allow multi-thread access (SQLite check_same_thread).
            connect_args["check_same_thread"] = False

        _engine = create_engine(
            db_url,
            connect_args=connect_args,
            # Pool settings — tuned for SQLite; adjust for PostgreSQL.
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            # Echo SQL for debugging (set via env).
            echo=os.environ.get("SQLALCHEMY_ECHO", "").lower() in ("1", "true"),
        )

        # SQLite-specific: enable WAL mode for concurrent reads.
        if is_sqlite:
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

    return _engine


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
_SessionFactory = None


def get_session_factory() -> sessionmaker[Session]:
    """Return the singleton sessionmaker."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
        )
    return _SessionFactory


@contextmanager
def get_session():
    """Context-managed session with auto-commit / rollback.

    Usage:
        with get_session() as session:
            session.add(obj)
            # auto-commits on exit, rolls back on exception
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
