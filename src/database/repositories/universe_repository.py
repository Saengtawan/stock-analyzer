"""
Universe Repository - DB-backed full stock universe storage (v6.72)

Replaces data/full_universe_cache.json with a universe_stocks table.
Written by maintain_universe_1000.py cron; read by pre_filter.py and ped_screener.py.
"""

import time
from datetime import datetime
from typing import Dict, List

from ..manager import get_db_manager
from loguru import logger


class UniverseRepository:
    """Repository for full stock universe (replaces full_universe_cache.json)."""

    def __init__(self, db_name: str = 'trade_history', _db=None):
        self.db = _db if _db is not None else get_db_manager(db_name)
        self._ensure_table()

    def _ensure_table(self):
        """Create universe_stocks table if it doesn't exist."""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS universe_stocks (
                symbol TEXT PRIMARY KEY,
                sector TEXT,
                status TEXT DEFAULT 'active',
                ts REAL,
                dollar_vol REAL,
                updated_at TEXT NOT NULL
            )
        """)

    def get_all(self) -> Dict[str, dict]:
        """
        Return full universe as dict matching full_universe_cache.json format.

        Returns:
            {symbol: {sector, ts, status, dollar_vol}}
        """
        try:
            rows = self.db.fetch_all(
                "SELECT symbol, sector, ts, status, dollar_vol FROM universe_stocks"
            )
            return {
                row['symbol']: {
                    'sector': row['sector'],
                    'ts': row['ts'],
                    'status': row['status'],
                    'dollar_vol': row['dollar_vol'],
                }
                for row in rows
            }
        except Exception as e:
            logger.error(f"UniverseRepository.get_all failed: {e}")
            return {}

    def save_bulk(self, universe: Dict[str, dict]) -> None:
        """
        Replace universe_stocks with all entries from universe dict.

        Runs DELETE + bulk INSERT in a single connection context (atomic).

        Args:
            universe: {symbol: {sector, ts, status, dollar_vol}}
        """
        try:
            now_str = datetime.now().isoformat()
            params_list = []
            for symbol, data in universe.items():
                if isinstance(data, dict):
                    sector = data.get('sector')
                    ts = data.get('ts', time.time())
                    status = data.get('status', 'active')
                    dollar_vol = data.get('dollar_vol')
                else:
                    sector = None
                    ts = time.time()
                    status = 'active'
                    dollar_vol = None
                params_list.append((symbol, sector, status, ts, dollar_vol, now_str))

            with self.db.get_connection() as conn:
                conn.execute("DELETE FROM universe_stocks")
                conn.executemany("""
                    INSERT INTO universe_stocks
                        (symbol, sector, status, ts, dollar_vol, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, params_list)

            logger.info(f"UniverseRepository: saved {len(params_list)} stocks to DB")
        except Exception as e:
            logger.error(f"UniverseRepository.save_bulk failed: {e}")

    def get_symbols(self) -> List[str]:
        """
        Return list of all symbol strings.

        Returns:
            Sorted list of symbols
        """
        try:
            rows = self.db.fetch_all(
                "SELECT symbol FROM universe_stocks ORDER BY symbol"
            )
            return [row['symbol'] for row in rows]
        except Exception as e:
            logger.error(f"UniverseRepository.get_symbols failed: {e}")
            return []
