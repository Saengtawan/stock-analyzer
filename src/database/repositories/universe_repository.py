"""
Universe Repository - DB-backed full stock universe storage (v6.72)

Replaces data/full_universe_cache.json with a universe_stocks table.
Written by maintain_universe_1000.py cron; read by pre_filter.py and ped_screener.py.
"""

import time
from datetime import datetime
from typing import Dict, List

from loguru import logger

from database.orm.base import get_session
from database.orm.models import UniverseStock


class UniverseRepository:
    """Repository for full stock universe (replaces full_universe_cache.json)."""

    def __init__(self, db_name: str = 'trade_history', _db=None):
        # db_name and _db kept for API compatibility; ignored (session handles connection)
        pass

    def _ensure_table(self):
        """No-op. Table is created by ORM model definition."""
        pass

    def get_all(self) -> Dict[str, dict]:
        """
        Return full universe as dict matching full_universe_cache.json format.

        Returns:
            {symbol: {sector, ts, status, dollar_vol}}
        """
        try:
            with get_session() as session:
                rows = session.query(UniverseStock).all()
                return {
                    row.symbol: {
                        'sector': row.sector,
                        'ts': row.ts,
                        'status': row.status,
                        'dollar_vol': row.dollar_vol,
                    }
                    for row in rows
                }
        except Exception as e:
            logger.error(f"UniverseRepository.get_all failed: {e}")
            return {}

    def save_bulk(self, universe: Dict[str, dict]) -> None:
        """
        Replace universe_stocks with all entries from universe dict.

        Runs DELETE + bulk INSERT in a single session (atomic).

        Args:
            universe: {symbol: {sector, ts, status, dollar_vol}}
        """
        try:
            now_str = datetime.now().isoformat()
            with get_session() as session:
                session.query(UniverseStock).delete()
                objects = []
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
                    objects.append(UniverseStock(
                        symbol=symbol,
                        sector=sector,
                        status=status,
                        ts=ts,
                        dollar_vol=dollar_vol,
                        updated_at=now_str,
                    ))
                session.add_all(objects)

            logger.info(f"UniverseRepository: saved {len(objects)} stocks to DB")
        except Exception as e:
            logger.error(f"UniverseRepository.save_bulk failed: {e}")

    def get_symbols(self) -> List[str]:
        """
        Return list of all symbol strings.

        Returns:
            Sorted list of symbols
        """
        try:
            with get_session() as session:
                rows = session.query(UniverseStock.symbol).order_by(
                    UniverseStock.symbol
                ).all()
                return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"UniverseRepository.get_symbols failed: {e}")
            return []
