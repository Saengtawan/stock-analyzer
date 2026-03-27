"""
SQLAlchemy ORM layer for stock-analyzer.

Usage:
    from database.orm import get_session, Base
    from database.orm.models import Trade, ActivePosition, MacroSnapshot

    with get_session() as session:
        trades = session.execute(select(Trade).where(Trade.symbol == 'AAPL')).scalars().all()
"""

from database.orm.base import Base, get_engine, get_session, get_session_factory

__all__ = [
    "Base",
    "get_engine",
    "get_session",
    "get_session_factory",
]
