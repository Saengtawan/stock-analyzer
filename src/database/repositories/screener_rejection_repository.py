"""
screener_rejection_repository.py — v7.5

Log stocks rejected by screeners BEFORE reaching the engine.
Enables Dimension 3: "did we miss good opportunities at the screener level?"

Usage (single insert):
    repo = ScreenerRejectionRepository()
    repo.log_rejection(screener='pem', symbol='NVDA', reject_reason='gap_below_threshold',
                       scan_price=500.0, gap_pct=6.2)

Usage (bulk insert — for DIP which processes 987 stocks per scan):
    repo.bulk_insert(rows)  # rows = list of dicts
"""
import sqlite3
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

_DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'trade_history.db')
ET_ZONE  = ZoneInfo('America/New_York')

COLUMNS = (
    'scan_date', 'scan_time', 'screener', 'symbol', 'reject_reason',
    'scan_price', 'gap_pct', 'volume_ratio', 'rsi', 'momentum_5d',
    'atr_pct', 'distance_from_high', 'score',
    'sector', 'momentum_20d', 'distance_from_20d_high',
)


class ScreenerRejectionRepository:
    def __init__(self, db_path: str = None):
        self._db_path = db_path or _DB_PATH

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _et_now() -> tuple[str, str]:
        """Return (date_str, time_str) in ET timezone."""
        now = datetime.now(ET_ZONE)
        return now.strftime('%Y-%m-%d'), now.strftime('%H:%M')

    def log_rejection(self, screener: str, symbol: str, reject_reason: str, *,
                      scan_price: float = None, gap_pct: float = None,
                      volume_ratio: float = None, rsi: float = None,
                      momentum_5d: float = None, atr_pct: float = None,
                      distance_from_high: float = None, score: int = None,
                      sector: str = None, momentum_20d: float = None,
                      distance_from_20d_high: float = None,
                      new_score: float = None, catalyst_type: str = None,
                      insider_buy_30d_value: float = None,
                      insider_buy_days_ago: int = None,
                      scan_date: str = None, scan_time: str = None):
        """Insert a single screener rejection."""
        if scan_date is None or scan_time is None:
            scan_date, scan_time = self._et_now()
        row = {
            'scan_date': scan_date, 'scan_time': scan_time,
            'screener': screener, 'symbol': symbol, 'reject_reason': reject_reason,
            'scan_price': scan_price, 'gap_pct': gap_pct, 'volume_ratio': volume_ratio,
            'rsi': rsi, 'momentum_5d': momentum_5d, 'atr_pct': atr_pct,
            'distance_from_high': distance_from_high, 'score': score,
            'sector': sector, 'momentum_20d': momentum_20d,
            'distance_from_20d_high': distance_from_20d_high,
            'new_score': new_score, 'catalyst_type': catalyst_type,
            'insider_buy_30d_value': insider_buy_30d_value,
            'insider_buy_days_ago': insider_buy_days_ago,
        }
        self.bulk_insert([row])

    def bulk_insert(self, rows: list[dict]):
        """Bulk-insert screener rejections. Rows are dicts with keys matching COLUMNS."""
        if not rows:
            return
        date_str, time_str = self._et_now()
        conn = None
        try:
            conn = self._connect()
            conn.executemany("""
                INSERT INTO screener_rejections
                    (scan_date, scan_time, screener, symbol, reject_reason,
                     scan_price, gap_pct, volume_ratio, rsi, momentum_5d,
                     atr_pct, distance_from_high, score,
                     sector, momentum_20d, distance_from_20d_high, new_score,
                     catalyst_type, insider_buy_30d_value, insider_buy_days_ago,
                     created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
            """, [
                (
                    r.get('scan_date', date_str),
                    r.get('scan_time', time_str),
                    r.get('screener'),
                    r.get('symbol'),
                    r.get('reject_reason'),
                    r.get('scan_price'),
                    r.get('gap_pct'),
                    r.get('volume_ratio'),
                    r.get('rsi'),
                    r.get('momentum_5d'),
                    r.get('atr_pct'),
                    r.get('distance_from_high'),
                    r.get('score'),
                    r.get('sector'),
                    r.get('momentum_20d'),
                    r.get('distance_from_20d_high'),
                    r.get('new_score'),
                    r.get('catalyst_type'),
                    r.get('insider_buy_30d_value'),
                    r.get('insider_buy_days_ago'),
                )
                for r in rows
            ])
            conn.commit()
        except Exception as e:
            # Non-fatal — screener rejection logging must never break the screener
            import logging
            logging.getLogger(__name__).warning(f"ScreenerRejectionRepository.bulk_insert error: {e}")
        finally:
            if conn:
                conn.close()

    def get_unfilled(self, cutoff_date: str) -> list[dict]:
        """Return rows where outcome_1d IS NULL and scan_date <= cutoff_date."""
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT id, symbol, scan_date, scan_price
                FROM screener_rejections
                WHERE outcome_1d IS NULL
                  AND scan_price IS NOT NULL AND scan_price > 0
                  AND scan_date <= ?
                ORDER BY scan_date DESC, symbol
            """, (cutoff_date,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_outcomes(self, row_id: int, outcome_1d: float = None,
                        outcome_2d: float = None, outcome_3d: float = None,
                        outcome_4d: float = None, outcome_5d: float = None,
                        outcome_max_gain_5d: float = None,
                        outcome_max_dd_5d: float = None):
        """Fill outcome columns for a single row."""
        conn = self._connect()
        try:
            conn.execute("""
                UPDATE screener_rejections SET
                    outcome_1d = ?, outcome_2d = ?, outcome_3d = ?,
                    outcome_4d = ?, outcome_5d = ?,
                    outcome_max_gain_5d = ?, outcome_max_dd_5d = ?
                WHERE id = ?
            """, (outcome_1d, outcome_2d, outcome_3d, outcome_4d,
                  outcome_5d, outcome_max_gain_5d, outcome_max_dd_5d, row_id))
            conn.commit()
        finally:
            conn.close()
