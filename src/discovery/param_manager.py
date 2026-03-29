"""
Parameter Manager — stores/loads all system parameters from DB.
Replaces hardcoded values with auto-optimizable parameters.
Part of Discovery v10.0 Full Autonomous System.
"""
import logging
from database.orm.base import get_session
from sqlalchemy import text
import json
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULTS = {
    'market_signals': {
        'crude_threshold_pct': 3.0,
        'crude_strong_threshold_pct': 5.0,
        'vix_spike_threshold': 30.0,
        'vix_extreme_threshold': 35.0,
        'spy_dd_threshold': -7.0,
        'spy_dd_extreme_threshold': -10.0,
        'sector_lookback_days': 20,
    },
    'arbiter': {
        'trade_threshold': 0.50,
        'cautious_threshold': 0.35,
        'calibrator_low_threshold': 30.0,
    },
    'filters': {
        'elite_sigma': 0.8,
        'd0_close_min_calm': 0.2,
        'd0_close_min_default': 0.3,
        'atr_max_calm': 5.0,
        'atr_max_fear': 8.0,
    },
    'tp_sl': {
        'tp_ratio': 1.0,
        'sl_mult_bull': 2.0,
        'sl_mult_stress': 1.5,
        'sl_mult_crisis': 1.0,
        'sl_floor': 1.5,
        'sl_cap': 5.0,
    },
    'strategy': {
        'calm_vix': 18.0,
        'fear_vix': 25.0,
    },
}


class ParamManager:
    """Load/save system parameters from DB. Seed defaults on first run."""

    def __init__(self):
        self._cache = {}
        self._ensure_tables()
        self._seed_defaults()
        self._load_all()

    def get(self, group: str, name: str, default: float = 0.0) -> float:
        """Get parameter value. Returns from cache (loaded from DB)."""
        key = f'{group}.{name}'
        return self._cache.get(key, default)

    def get_group(self, group: str) -> dict:
        """Get all params in a group."""
        prefix = f'{group}.'
        return {k[len(prefix):]: v for k, v in self._cache.items() if k.startswith(prefix)}

    def update(self, group: str, name: str, value: float, reason: str = 'manual') -> bool:
        """Update a parameter and log history."""
        key = f'{group}.{name}'
        old_value = self._cache.get(key)

        with get_session() as session:
            session.execute(text("""
                INSERT INTO system_parameters (param_group, param_name, param_value, updated_by)
                VALUES (:p0, :p1, :p2, :p3)
                ON CONFLICT(param_group, param_name)
                DO UPDATE SET param_value=:p4, updated_at=datetime('now'), updated_by=:p5
            """), {'p0': group, 'p1': name, 'p2': value, 'p3': reason, 'p4': value, 'p5': reason})

            session.execute(text("""
                INSERT INTO parameter_history
                (param_group, param_name, old_value, new_value, reason)
                VALUES (:p0, :p1, :p2, :p3, :p4)
            """), {'p0': group, 'p1': name, 'p2': old_value, 'p3': value, 'p4': reason})

        self._cache[key] = value
        logger.info("Param updated: %s.%s = %.4f (was %.4f) reason=%s",
                     group, name, value, old_value or 0, reason)
        return True

    def get_history(self, group: str = None, name: str = None, limit: int = 20) -> list:
        """Get parameter change history."""
        with get_session() as session:
            if group and name:
                rows = session.execute(text("""
                    SELECT * FROM parameter_history
                    WHERE param_group=:p0 AND param_name=:p1
                    ORDER BY changed_at DESC LIMIT :p2
                """), {'p0': group, 'p1': name, 'p2': limit}).fetchall()
            else:
                rows = session.execute(text("""
                    SELECT * FROM parameter_history
                    ORDER BY changed_at DESC LIMIT :p0
                """), {'p0': limit}).fetchall()
            return [dict(r._mapping) for r in rows]

    def get_all(self) -> dict:
        """Get all parameters as nested dict."""
        result = {}
        for key, val in self._cache.items():
            group, name = key.split('.', 1)
            if group not in result:
                result[group] = {}
            result[group][name] = val
        return result

    def _ensure_tables(self):
        with get_session() as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS system_parameters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    param_group TEXT NOT NULL,
                    param_name TEXT NOT NULL,
                    param_value REAL NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now')),
                    updated_by TEXT DEFAULT 'manual',
                    UNIQUE(param_group, param_name)
                )
            """))
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS parameter_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    param_group TEXT NOT NULL,
                    param_name TEXT NOT NULL,
                    old_value REAL,
                    new_value REAL,
                    reason TEXT,
                    sharpe_before REAL,
                    sharpe_after REAL,
                    changed_at TEXT DEFAULT (datetime('now'))
                )
            """))

    def _seed_defaults(self):
        """Seed default params if table is empty."""
        with get_session() as session:
            n = session.execute(text('SELECT COUNT(*) FROM system_parameters')).fetchone()[0]
            if n > 0:
                return

            for group, params in DEFAULTS.items():
                for name, value in params.items():
                    session.execute(text("""
                        INSERT OR IGNORE INTO system_parameters
                        (param_group, param_name, param_value, updated_by)
                        VALUES (:p0, :p1, :p2, 'seed')
                    """), {'p0': group, 'p1': name, 'p2': value})
            logger.info("ParamManager: seeded %d default parameters",
                         sum(len(v) for v in DEFAULTS.values()))

    def _load_all(self):
        """Load all params from DB into cache."""
        with get_session() as session:
            rows = session.execute(text('SELECT param_group, param_name, param_value FROM system_parameters')).fetchall()
            self._cache = {f'{r[0]}.{r[1]}': r[2] for r in rows}
            logger.debug("ParamManager: loaded %d parameters", len(self._cache))
