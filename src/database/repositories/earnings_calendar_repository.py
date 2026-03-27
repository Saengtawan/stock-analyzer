"""
Earnings Calendar Repository

Stores next earnings date per symbol for PED screener.
Allows full-universe (987 stocks) scan without yfinance per-symbol API calls at scan time.

Schema:
    earnings_calendar (symbol PK, next_earnings_date, fetched_at)

Usage:
    repo = EarningsCalendarRepository()
    days = repo.get_days_until("NVDA")   # None if no upcoming earnings
    stale = repo.get_stale_symbols(all_symbols, max_age_hours=26)
"""

from datetime import datetime, date
from typing import List, Optional, Dict

import pandas as pd

from database.orm.base import get_session
from database.orm.models import EarningsCalendar


class EarningsCalendarRepository:

    def __init__(self, db_path: str = None):
        # db_path kept for API compatibility; ignored (session handles connection)
        pass

    # -------------------------------------------------------------------------
    # Write
    # -------------------------------------------------------------------------

    def upsert(self, symbol: str, next_earnings_date: Optional[str]) -> None:
        """Insert or update earnings date for a symbol."""
        with get_session() as session:
            existing = session.query(EarningsCalendar).filter(
                EarningsCalendar.symbol == symbol
            ).first()
            now = datetime.now().isoformat()
            if existing:
                existing.next_earnings_date = next_earnings_date
                existing.fetched_at = now
            else:
                session.add(EarningsCalendar(
                    symbol=symbol,
                    next_earnings_date=next_earnings_date,
                    fetched_at=now,
                ))

    def upsert_batch(self, records: Dict[str, Optional[str]]) -> int:
        """
        Bulk upsert {symbol: next_earnings_date_or_None}.
        Returns number of rows written.
        """
        now = datetime.now().isoformat()
        with get_session() as session:
            # Load all existing symbols in one query
            existing_map = {
                ec.symbol: ec
                for ec in session.query(EarningsCalendar).filter(
                    EarningsCalendar.symbol.in_(list(records.keys()))
                ).all()
            }
            new_objects = []
            for sym, dt in records.items():
                if sym in existing_map:
                    existing_map[sym].next_earnings_date = dt
                    existing_map[sym].fetched_at = now
                else:
                    new_objects.append(EarningsCalendar(
                        symbol=sym,
                        next_earnings_date=dt,
                        fetched_at=now,
                    ))
            if new_objects:
                session.add_all(new_objects)
        return len(records)

    # -------------------------------------------------------------------------
    # Read
    # -------------------------------------------------------------------------

    def get_days_until(self, symbol: str) -> Optional[int]:
        """
        Return trading days until next earnings for symbol.
        Returns None if no upcoming earnings in cache.
        """
        with get_session() as session:
            row = session.query(EarningsCalendar).filter(
                EarningsCalendar.symbol == symbol
            ).first()
        if not row or not row.next_earnings_date:
            return None
        try:
            earnings_date = date.fromisoformat(row.next_earnings_date)
            today = date.today()
            if earnings_date <= today:
                return None
            bdays = pd.bdate_range(start=today, end=earnings_date)
            return max(0, len(bdays) - 1)
        except Exception:
            return None

    def get_all(self) -> Dict[str, Optional[str]]:
        """Return full cache as {symbol: next_earnings_date_str_or_None}."""
        with get_session() as session:
            rows = session.query(EarningsCalendar).all()
        return {r.symbol: r.next_earnings_date for r in rows}

    def get_days_until_all(self) -> Dict[str, Optional[int]]:
        """
        Return {symbol: days_until} for all cached symbols.
        Computed from today -- use at scan time for instant lookup.
        """
        today = date.today()
        result: Dict[str, Optional[int]] = {}
        for sym, dt_str in self.get_all().items():
            if not dt_str:
                result[sym] = None
                continue
            try:
                earnings_date = date.fromisoformat(dt_str)
                if earnings_date <= today:
                    result[sym] = None
                else:
                    bdays = pd.bdate_range(start=today, end=earnings_date)
                    result[sym] = max(0, len(bdays) - 1)
            except Exception:
                result[sym] = None
        return result

    def get_stale_symbols(self, all_symbols: List[str], max_age_hours: float = 26.0) -> List[str]:
        """
        Return symbols from all_symbols that are missing or stale (fetched_at older than max_age_hours).
        Used by refresh loop to know what to re-fetch.
        """
        cutoff = datetime.now().timestamp() - max_age_hours * 3600
        with get_session() as session:
            rows = session.query(EarningsCalendar).all()
        fresh = set()
        for r in rows:
            try:
                ts = datetime.fromisoformat(r.fetched_at).timestamp()
                if ts >= cutoff:
                    fresh.add(r.symbol)
            except Exception:
                pass
        return [s for s in all_symbols if s not in fresh]

    def count(self) -> int:
        with get_session() as session:
            return session.query(EarningsCalendar).count()

    def ensure_table(self):
        """No-op. Table is created by ORM model definition."""
        pass
