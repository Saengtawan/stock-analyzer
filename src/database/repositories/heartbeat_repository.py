"""
Heartbeat Repository - DB-backed engine liveness tracking (v6.72)

Replaces data/heartbeat.json with a single-row engine_heartbeat table.
Single-row upsert pattern: always id=1.
"""

from datetime import datetime
from typing import Optional

from ..manager import get_db_manager
from loguru import logger


class HeartbeatRepository:
    """Repository for engine heartbeat (single-row, upsert pattern)."""

    def __init__(self, db_name: str = 'trade_history', _db=None):
        self.db = _db if _db is not None else get_db_manager(db_name)
        self._ensure_table()

    def _ensure_table(self):
        """Create engine_heartbeat table if it doesn't exist."""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS engine_heartbeat (
                id INTEGER PRIMARY KEY DEFAULT 1,
                timestamp TEXT NOT NULL,
                alive INTEGER NOT NULL DEFAULT 1,
                state TEXT,
                positions INTEGER DEFAULT 0,
                running INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL
            )
        """)

    def write(self, state: str, positions: int, running: bool) -> bool:
        """
        Write (upsert) heartbeat row id=1.

        Args:
            state: Engine state string (e.g. 'MONITORING')
            positions: Number of open positions
            running: Whether engine is running

        Returns:
            True if successful
        """
        try:
            now = datetime.now().isoformat()
            self.db.execute("""
                INSERT OR REPLACE INTO engine_heartbeat
                    (id, timestamp, alive, state, positions, running, updated_at)
                VALUES (1, ?, 1, ?, ?, ?, ?)
            """, (now, state, positions, 1 if running else 0, now))
            return True
        except Exception as e:
            logger.error(f"HeartbeatRepository.write failed: {e}")
            return False

    def read(self, max_age_seconds: int = 120) -> dict:
        """
        Read heartbeat row and compute liveness.

        Args:
            max_age_seconds: Age threshold; older = stale

        Returns:
            dict with keys: alive, stale, age_seconds, timestamp, state, positions, running
        """
        _dead = {
            'alive': False,
            'stale': True,
            'age_seconds': None,
            'timestamp': None,
            'state': None,
            'positions': 0,
            'running': False,
        }
        try:
            row = self.db.fetch_one(
                "SELECT * FROM engine_heartbeat WHERE id = 1"
            )
            if not row:
                return _dead

            ts = datetime.fromisoformat(row['timestamp'])
            age_seconds = (datetime.now() - ts).total_seconds()
            stale = age_seconds > max_age_seconds
            alive = not stale and bool(row['running'])

            return {
                'alive': alive,
                'stale': stale,
                'age_seconds': round(age_seconds, 1),
                'timestamp': row['timestamp'],
                'state': row['state'],
                'positions': row['positions'],
                'running': bool(row['running']),
            }
        except Exception as e:
            logger.error(f"HeartbeatRepository.read failed: {e}")
            return _dead
