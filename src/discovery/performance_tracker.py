"""
Performance Tracker — records daily P&L and detects model drift.
Part of Discovery v10.0 Full Autonomous System.
"""
import logging
import sqlite3
import json
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


class PerformanceTracker:
    """Track daily P&L and detect model drift."""

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discovery_performance (
                date TEXT PRIMARY KEY,
                n_picks INTEGER,
                n_wins INTEGER,
                wr REAL,
                total_pnl REAL,
                avg_pnl REAL,
                strategy_breakdown TEXT,
                params_snapshot TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()

    def track_daily(self, scan_date: str = None) -> dict:
        """Record P&L for picks that expired (scan_date + 5 days)."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            # Find dates with outcomes but no performance record
            dates = conn.execute("""
                SELECT DISTINCT scan_date FROM discovery_outcomes
                WHERE actual_return_d3 IS NOT NULL
                AND scan_date NOT IN (SELECT date FROM discovery_performance)
                ORDER BY scan_date
            """).fetchall()

            recorded = 0
            for dt_row in dates:
                dt = dt_row['scan_date']
                outcomes = conn.execute("""
                    SELECT actual_return_d3, regime, predicted_er
                    FROM discovery_outcomes
                    WHERE scan_date = ? AND actual_return_d3 IS NOT NULL
                """, (dt,)).fetchall()

                if not outcomes:
                    continue

                rets = [r['actual_return_d3'] for r in outcomes]
                n = len(rets)
                n_wins = sum(1 for r in rets if r > 0)
                wr = n_wins / n * 100 if n > 0 else 0
                total_pnl = sum(rets)
                avg_pnl = total_pnl / n if n > 0 else 0

                # Strategy breakdown by regime
                regime_map = {}
                for r in outcomes:
                    regime = r['regime'] or 'UNKNOWN'
                    if regime not in regime_map:
                        regime_map[regime] = {'n': 0, 'wins': 0, 'pnl': 0}
                    regime_map[regime]['n'] += 1
                    if r['actual_return_d3'] > 0:
                        regime_map[regime]['wins'] += 1
                    regime_map[regime]['pnl'] += r['actual_return_d3']

                conn.execute("""
                    INSERT OR IGNORE INTO discovery_performance
                    (date, n_picks, n_wins, wr, total_pnl, avg_pnl, strategy_breakdown)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (dt, n, n_wins, round(wr, 1), round(total_pnl, 4),
                      round(avg_pnl, 4), json.dumps(regime_map)))
                recorded += 1

            conn.commit()
            if recorded:
                logger.info("PerformanceTracker: recorded %d days", recorded)
            return {'recorded': recorded}
        finally:
            conn.close()

    def detect_drift(self) -> dict:
        """Compare recent accuracy vs historical."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            # Last 30 days
            r30 = conn.execute("""
                SELECT AVG(wr), AVG(avg_pnl), COUNT(*) FROM discovery_performance
                WHERE date >= date('now', '-30 days')
            """).fetchone()

            # Last 90 days
            r90 = conn.execute("""
                SELECT AVG(wr), AVG(avg_pnl), COUNT(*) FROM discovery_performance
                WHERE date >= date('now', '-90 days')
            """).fetchone()

            # All time
            r_all = conn.execute("""
                SELECT AVG(wr), AVG(avg_pnl), COUNT(*) FROM discovery_performance
            """).fetchone()
        finally:
            conn.close()

        wr_30 = r30[0] or 50
        wr_90 = r90[0] or 50
        wr_all = r_all[0] or 50
        n_30 = r30[2]

        drift = 'NORMAL'
        if n_30 >= 5:
            if wr_30 < wr_90 - 5:
                drift = 'MODEL_DRIFT'
            if wr_30 < 45:
                drift = 'MODEL_FAILING'

        result = {
            'drift': drift,
            'wr_30d': round(wr_30, 1),
            'wr_90d': round(wr_90, 1),
            'wr_all': round(wr_all, 1),
            'n_30d': n_30,
            'pnl_30d': round((r30[1] or 0) * n_30, 2),
        }

        if drift != 'NORMAL':
            logger.warning("PerformanceTracker: %s detected! 30d WR=%.1f%% vs 90d WR=%.1f%%",
                           drift, wr_30, wr_90)

        return result

    def get_summary(self, days: int = 30) -> dict:
        """Get performance summary for UI."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                SELECT date, n_picks, n_wins, wr, total_pnl, avg_pnl
                FROM discovery_performance
                WHERE date >= date('now', ? || ' days')
                ORDER BY date DESC
            """, (f'-{days}',)).fetchall()
        finally:
            conn.close()

        if not rows:
            return {'days': days, 'n_days': 0, 'wr': 0, 'pnl': 0}

        return {
            'days': days,
            'n_days': len(rows),
            'total_picks': sum(r[1] for r in rows),
            'total_wins': sum(r[2] for r in rows),
            'wr': round(sum(r[2] for r in rows) / max(sum(r[1] for r in rows), 1) * 100, 1),
            'total_pnl': round(sum(r[4] for r in rows), 3),
            'avg_daily_pnl': round(sum(r[4] for r in rows) / len(rows), 3),
            'best_day': max(rows, key=lambda r: r[4])[0] if rows else None,
            'worst_day': min(rows, key=lambda r: r[4])[0] if rows else None,
        }
