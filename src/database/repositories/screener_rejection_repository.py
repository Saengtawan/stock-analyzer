"""
screener_rejection_repository.py -- v7.5

Log stocks rejected by screeners BEFORE reaching the engine.
Enables Dimension 3: "did we miss good opportunities at the screener level?"

Usage (single insert):
    repo = ScreenerRejectionRepository()
    repo.log_rejection(screener='pem', symbol='NVDA', reject_reason='gap_below_threshold',
                       scan_price=500.0, gap_pct=6.2)

Usage (bulk insert -- for DIP which processes 987 stocks per scan):
    repo.bulk_insert(rows)  # rows = list of dicts
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from database.orm.base import get_session
from database.orm.models import ScreenerRejection

ET_ZONE = ZoneInfo('America/New_York')

COLUMNS = (
    'scan_date', 'scan_time', 'screener', 'symbol', 'reject_reason',
    'scan_price', 'gap_pct', 'volume_ratio', 'rsi', 'momentum_5d',
    'atr_pct', 'distance_from_high', 'score',
    'sector', 'momentum_20d', 'distance_from_20d_high',
)


class ScreenerRejectionRepository:
    def __init__(self, db_path: str = None):
        # db_path kept for API compatibility; ignored (session handles connection)
        pass

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
        try:
            with get_session() as session:
                objects = []
                for r in rows:
                    objects.append(ScreenerRejection(
                        scan_date=r.get('scan_date', date_str),
                        scan_time=r.get('scan_time', time_str),
                        screener=r.get('screener'),
                        symbol=r.get('symbol'),
                        reject_reason=r.get('reject_reason'),
                        scan_price=r.get('scan_price'),
                        gap_pct=r.get('gap_pct'),
                        volume_ratio=r.get('volume_ratio'),
                        rsi=r.get('rsi'),
                        momentum_5d=r.get('momentum_5d'),
                        atr_pct=r.get('atr_pct'),
                        distance_from_high=r.get('distance_from_high'),
                        score=r.get('score'),
                        sector=r.get('sector'),
                        momentum_20d=r.get('momentum_20d'),
                        distance_from_20d_high=r.get('distance_from_20d_high'),
                        new_score=r.get('new_score'),
                        catalyst_type=r.get('catalyst_type'),
                        insider_buy_30d_value=r.get('insider_buy_30d_value'),
                        insider_buy_days_ago=r.get('insider_buy_days_ago'),
                        created_at=datetime.utcnow().isoformat(),
                    ))
                session.add_all(objects)
        except Exception as e:
            # Non-fatal -- screener rejection logging must never break the screener
            logging.getLogger(__name__).warning(f"ScreenerRejectionRepository.bulk_insert error: {e}")

    def get_unfilled(self, cutoff_date: str) -> list[dict]:
        """Return rows where outcome_1d IS NULL and scan_date <= cutoff_date."""
        with get_session() as session:
            rows = session.query(ScreenerRejection).filter(
                ScreenerRejection.outcome_1d.is_(None),
                ScreenerRejection.scan_price.isnot(None),
                ScreenerRejection.scan_price > 0,
                ScreenerRejection.scan_date <= cutoff_date,
            ).order_by(
                ScreenerRejection.scan_date.desc(),
                ScreenerRejection.symbol,
            ).all()
            return [
                {'id': r.id, 'symbol': r.symbol, 'scan_date': r.scan_date, 'scan_price': r.scan_price}
                for r in rows
            ]

    def update_outcomes(self, row_id: int, outcome_1d: float = None,
                        outcome_2d: float = None, outcome_3d: float = None,
                        outcome_4d: float = None, outcome_5d: float = None,
                        outcome_max_gain_5d: float = None,
                        outcome_max_dd_5d: float = None):
        """Fill outcome columns for a single row."""
        with get_session() as session:
            row = session.query(ScreenerRejection).filter(
                ScreenerRejection.id == row_id
            ).first()
            if row:
                row.outcome_1d = outcome_1d
                row.outcome_2d = outcome_2d
                row.outcome_3d = outcome_3d
                row.outcome_4d = outcome_4d
                row.outcome_5d = outcome_5d
                row.outcome_max_gain_5d = outcome_max_gain_5d
                row.outcome_max_dd_5d = outcome_max_dd_5d
