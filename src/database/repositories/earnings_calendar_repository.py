"""
Earnings Calendar Repository

Stores next earnings date per symbol for PED screener.
Allows full-universe (987 stocks) scan without yfinance per-symbol API calls at scan time.

Schema:
    earnings_calendar (symbol PK, next_earnings_date, fetched_at)

Usage:
    repo = EarningsCalendarRepository()
    repo.ensure_table()
    repo.upsert("AAPL", "2026-05-01")
    days = repo.get_days_until("NVDA")   # None if no upcoming earnings
    stale = repo.get_stale_symbols(all_symbols, max_age_hours=26)
"""

import sqlite3
from datetime import datetime, date
from typing import List, Optional, Dict
from pathlib import Path

import pandas as pd


class EarningsCalendarRepository:

    def __init__(self, db_path: str = None):
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            db_path = str(project_root / 'data' / 'trade_history.db')
        self.db_path = db_path
        self.ensure_table()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_table(self):
        """Create table if not exists."""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS earnings_calendar (
                    symbol           TEXT PRIMARY KEY,
                    next_earnings_date TEXT,    -- ISO date "YYYY-MM-DD" or NULL
                    fetched_at       TEXT NOT NULL  -- ISO datetime of last fetch
                )
            """)
            conn.commit()

    # -------------------------------------------------------------------------
    # Write
    # -------------------------------------------------------------------------

    def upsert(self, symbol: str, next_earnings_date: Optional[str]) -> None:
        """Insert or update earnings date for a symbol."""
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO earnings_calendar (symbol, next_earnings_date, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    next_earnings_date = excluded.next_earnings_date,
                    fetched_at         = excluded.fetched_at
            """, (symbol, next_earnings_date, datetime.now().isoformat()))
            conn.commit()

    def upsert_batch(self, records: Dict[str, Optional[str]]) -> int:
        """
        Bulk upsert {symbol: next_earnings_date_or_None}.
        Returns number of rows written.
        """
        now = datetime.now().isoformat()
        rows = [(sym, dt, now) for sym, dt in records.items()]
        with self._conn() as conn:
            conn.executemany("""
                INSERT INTO earnings_calendar (symbol, next_earnings_date, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    next_earnings_date = excluded.next_earnings_date,
                    fetched_at         = excluded.fetched_at
            """, rows)
            conn.commit()
        return len(rows)

    # -------------------------------------------------------------------------
    # Read
    # -------------------------------------------------------------------------

    def get_days_until(self, symbol: str) -> Optional[int]:
        """
        Return trading days until next earnings for symbol.
        Returns None if no upcoming earnings in cache.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT next_earnings_date FROM earnings_calendar WHERE symbol = ?",
                (symbol,)
            ).fetchone()
        if not row or not row['next_earnings_date']:
            return None
        try:
            earnings_date = date.fromisoformat(row['next_earnings_date'])
            today = date.today()
            if earnings_date <= today:
                return None
            bdays = pd.bdate_range(start=today, end=earnings_date)
            return max(0, len(bdays) - 1)
        except Exception:
            return None

    def get_all(self) -> Dict[str, Optional[str]]:
        """Return full cache as {symbol: next_earnings_date_str_or_None}."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT symbol, next_earnings_date FROM earnings_calendar"
            ).fetchall()
        return {r['symbol']: r['next_earnings_date'] for r in rows}

    def get_days_until_all(self) -> Dict[str, Optional[int]]:
        """
        Return {symbol: days_until} for all cached symbols.
        Computed from today — use at scan time for instant lookup.
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
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT symbol, fetched_at FROM earnings_calendar"
            ).fetchall()
        fresh = set()
        for r in rows:
            try:
                ts = datetime.fromisoformat(r['fetched_at']).timestamp()
                if ts >= cutoff:
                    fresh.add(r['symbol'])
            except Exception:
                pass
        return [s for s in all_symbols if s not in fresh]

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM earnings_calendar").fetchone()[0]
