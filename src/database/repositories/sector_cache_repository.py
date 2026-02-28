"""
Sector Cache Repository - DB-backed yfinance sector lookup cache (v6.72)

Replaces data/sector_cache.json with a sector_cache table.
Stores per-symbol sector and timestamp for TTL-based expiry.
"""

import time
from datetime import datetime
from typing import Dict

from ..manager import get_db_manager
from loguru import logger


class SectorCacheRepository:
    """Repository for persistent sector cache (replaces sector_cache.json)."""

    def __init__(self, db_name: str = 'trade_history', _db=None):
        self.db = _db if _db is not None else get_db_manager(db_name)
        self._ensure_table()

    def _ensure_table(self):
        """Create sector_cache table if it doesn't exist."""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS sector_cache (
                symbol TEXT PRIMARY KEY,
                sector TEXT NOT NULL,
                ts REAL NOT NULL,
                status TEXT DEFAULT 'active',
                updated_at TEXT NOT NULL
            )
        """)

    def load_all(self, ttl_seconds: float) -> Dict[str, dict]:
        """
        Load all sector cache entries that are within TTL.

        Args:
            ttl_seconds: Maximum age in seconds (entries older are excluded)

        Returns:
            Dict mapping symbol -> {sector, ts, status}
        """
        try:
            rows = self.db.fetch_all(
                "SELECT symbol, sector, ts, status FROM sector_cache"
            )
            now = time.time()
            result = {}
            for row in rows:
                if now - row['ts'] < ttl_seconds:
                    result[row['symbol']] = {
                        'sector': row['sector'],
                        'ts': row['ts'],
                        'status': row['status'],
                    }
            if result:
                logger.info(f"📦 Loaded {len(result)} sectors from sector_cache DB")
            return result
        except Exception as e:
            logger.error(f"SectorCacheRepository.load_all failed: {e}")
            return {}

    def save_bulk(self, cache: Dict[str, dict]) -> None:
        """
        Upsert all entries from in-memory sector cache dict.

        Args:
            cache: Dict mapping symbol -> {sector, ts, status}
        """
        if not cache:
            return
        try:
            now_str = datetime.now().isoformat()
            params_list = []
            for symbol, data in cache.items():
                if isinstance(data, dict):
                    sector = data.get('sector', 'Unknown')
                    ts = data.get('ts', time.time())
                    status = data.get('status', 'active')
                else:
                    sector = str(data)
                    ts = time.time()
                    status = 'active'
                params_list.append((symbol, sector, ts, status, now_str))

            self.db.execute_many("""
                INSERT OR REPLACE INTO sector_cache
                    (symbol, sector, ts, status, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, params_list)
        except Exception as e:
            logger.error(f"SectorCacheRepository.save_bulk failed: {e}")
