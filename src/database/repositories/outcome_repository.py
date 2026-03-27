"""
Outcome Repository - Database access for outcome tracking

Handles CRUD operations for:
- sell_outcomes
- signal_outcomes
- rejected_outcomes
"""

import yaml
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from sqlalchemy import text

from database.orm.base import get_session
from database.orm.models import SellOutcome, SignalOutcome, RejectedOutcome


def _load_dip_thresholds() -> dict:
    """Load DIP filter thresholds from trading.yaml. Returns hardcoded defaults as fallback."""
    try:
        config_path = Path(__file__).parent.parent.parent.parent / 'config' / 'trading.yaml'
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        return {
            'rsi':       float(cfg.get('max_rsi_entry',    60.0)),
            'atr':       float(cfg.get('low_risk_max_atr_pct', 4.0)),
            'score':     float(cfg.get('dip_score_min',    70.0)),
            'vix_skip':  float(cfg.get('vix_skip_zone_high', 24.0)),
        }
    except Exception:
        return {'rsi': 60.0, 'atr': 4.0, 'score': 70.0, 'vix_skip': 24.0}


_DIP_THRESHOLDS = _load_dip_thresholds()


class OutcomeRepository:
    """Repository for outcome tracking data"""

    def __init__(self, db_path: str = None):
        # db_path kept for API compatibility; ignored (session handles connection)
        pass

    # ========================================================================
    # Sell Outcomes
    # ========================================================================

    def save_sell_outcome(self, outcome: Dict) -> int:
        """
        Save or update sell outcome.

        Args:
            outcome: Dict with keys matching sell_outcomes table columns

        Returns:
            ID of inserted/updated row
        """
        with get_session() as session:
            existing = session.query(SellOutcome).filter(
                SellOutcome.trade_id == outcome['trade_id']
            ).first()

            if existing:
                existing.symbol = outcome.get('symbol')
                existing.sell_date = outcome.get('sell_date')
                existing.sell_price = outcome.get('sell_price')
                existing.sell_reason = outcome.get('sell_reason')
                existing.sell_pnl_pct = outcome.get('sell_pnl_pct')
                existing.post_sell_close_1d = outcome.get('post_sell_close_1d')
                existing.post_sell_close_3d = outcome.get('post_sell_close_3d')
                existing.post_sell_close_5d = outcome.get('post_sell_close_5d')
                existing.post_sell_max_5d = outcome.get('post_sell_max_5d')
                existing.post_sell_min_5d = outcome.get('post_sell_min_5d')
                existing.post_sell_pnl_pct_1d = outcome.get('post_sell_pnl_pct_1d')
                existing.post_sell_pnl_pct_5d = outcome.get('post_sell_pnl_pct_5d')
                existing.updated_at = datetime.now().isoformat()
                session.flush()
                return existing.id
            else:
                obj = SellOutcome(
                    trade_id=outcome['trade_id'],
                    symbol=outcome.get('symbol'),
                    sell_date=outcome.get('sell_date'),
                    sell_price=outcome.get('sell_price'),
                    sell_reason=outcome.get('sell_reason'),
                    sell_pnl_pct=outcome.get('sell_pnl_pct'),
                    post_sell_close_1d=outcome.get('post_sell_close_1d'),
                    post_sell_close_3d=outcome.get('post_sell_close_3d'),
                    post_sell_close_5d=outcome.get('post_sell_close_5d'),
                    post_sell_max_5d=outcome.get('post_sell_max_5d'),
                    post_sell_min_5d=outcome.get('post_sell_min_5d'),
                    post_sell_pnl_pct_1d=outcome.get('post_sell_pnl_pct_1d'),
                    post_sell_pnl_pct_5d=outcome.get('post_sell_pnl_pct_5d'),
                    tracked_at=outcome.get('tracked_at', datetime.now().isoformat()),
                )
                session.add(obj)
                session.flush()
                return obj.id

    def get_incomplete_sell_outcomes(self) -> List[Dict]:
        """Get sell outcomes where post_sell_close_5d is NULL (not yet complete)"""
        with get_session() as session:
            rows = session.query(SellOutcome).filter(
                SellOutcome.post_sell_close_5d.is_(None)
            ).order_by(SellOutcome.sell_date.desc()).all()
            return [_sell_outcome_to_dict(r) for r in rows]

    def get_complete_sell_outcome_ids(self) -> set:
        """Get set of trade_ids that have complete 5-day data"""
        with get_session() as session:
            rows = session.query(SellOutcome.trade_id).filter(
                SellOutcome.post_sell_close_5d.isnot(None)
            ).all()
            return {r[0] for r in rows}

    # ========================================================================
    # Signal Outcomes
    # ========================================================================

    def save_signal_outcome(self, outcome: Dict) -> int:
        """Save or update signal outcome"""
        # v7.5: Compute margin_to_threshold fields from raw values.
        t = _DIP_THRESHOLDS
        if outcome.get('entry_rsi') is not None:
            outcome.setdefault('margin_to_rsi', round(outcome['entry_rsi'] - t['rsi'], 2))
        if outcome.get('atr_pct') is not None:
            outcome.setdefault('margin_to_atr', round(outcome['atr_pct'] - t['atr'], 2))
        if outcome.get('new_score') is not None and outcome['new_score'] > 0:
            outcome.setdefault('margin_to_score', round(outcome['new_score'] - t['score'], 2))
        if outcome.get('vix_at_signal') is not None:
            outcome.setdefault('margin_to_vix_skip', round(outcome['vix_at_signal'] - t['vix_skip'], 2))

        with get_session() as session:
            # v7.8: Dedup by (symbol, scan_date, signal_source)
            ACTION_PRIORITY = {'BOUGHT': 1, 'QUEUED': 2, 'QUEUE_FULL': 3, 'SKIPPED_FILTER': 4}
            signal_source = outcome.get('signal_source')
            incoming_prio = ACTION_PRIORITY.get(outcome.get('action_taken'), 99)

            if signal_source:
                dup = session.query(SignalOutcome).filter(
                    SignalOutcome.symbol == outcome['symbol'],
                    SignalOutcome.scan_date == outcome.get('scan_date'),
                    SignalOutcome.signal_source == signal_source,
                ).first()
            else:
                dup = session.query(SignalOutcome).filter(
                    SignalOutcome.symbol == outcome['symbol'],
                    SignalOutcome.scan_date == outcome.get('scan_date'),
                    SignalOutcome.signal_source.is_(None),
                    SignalOutcome.action_taken == outcome.get('action_taken'),
                ).first()

            _update_obj = None  # ORM object to UPDATE; None -> INSERT new row

            if dup:
                existing_prio = ACTION_PRIORITY.get(dup.action_taken, 99)
                if incoming_prio < existing_prio:
                    _update_obj = dup
                else:
                    # Same or lower priority -- only fill NULL outcome_5d if we now have it
                    if dup.outcome_5d is None and outcome.get('outcome_5d') is not None:
                        dup.outcome_1d = outcome.get('outcome_1d')
                        dup.outcome_2d = outcome.get('outcome_2d')
                        dup.outcome_3d = outcome.get('outcome_3d')
                        dup.outcome_4d = outcome.get('outcome_4d')
                        dup.outcome_5d = outcome.get('outcome_5d')
                        dup.outcome_max_gain_5d = outcome.get('outcome_max_gain_5d')
                        dup.outcome_max_dd_5d = outcome.get('outcome_max_dd_5d')
                        dup.updated_at = datetime.now().isoformat()
                    return dup.id

            if _update_obj is None:
                # Check for same scan_id re-saving its own row
                existing_by_scan = session.query(SignalOutcome).filter(
                    SignalOutcome.scan_id == outcome['scan_id'],
                    SignalOutcome.symbol == outcome['symbol'],
                ).first()
                if existing_by_scan:
                    _update_obj = existing_by_scan

            if _update_obj is not None:
                # Update -- use raw SQL for COALESCE semantics on short_percent_of_float and trade_id
                _apply_signal_outcome_update(_update_obj, outcome)
                session.flush()
                return _update_obj.id
            else:
                # Insert
                obj = SignalOutcome(
                    scan_id=outcome['scan_id'],
                    symbol=outcome['symbol'],
                    scan_date=outcome.get('scan_date'),
                    scan_type=outcome.get('scan_type'),
                    signal_rank=outcome.get('signal_rank'),
                    action_taken=outcome.get('action_taken'),
                    skip_reason=outcome.get('skip_reason'),
                    score=outcome.get('score'),
                    signal_source=outcome.get('signal_source'),
                    scan_price=outcome.get('scan_price'),
                    days_until_earnings=outcome.get('days_until_earnings'),
                    earnings_gap_pct=outcome.get('earnings_gap_pct'),
                    volume_ratio=outcome.get('volume_ratio'),
                    atr_pct=outcome.get('atr_pct'),
                    entry_rsi=outcome.get('entry_rsi'),
                    momentum_5d=outcome.get('momentum_5d'),
                    gap_pct=outcome.get('gap_pct'),
                    gap_confidence=outcome.get('gap_confidence'),
                    momentum_20d=outcome.get('momentum_20d'),
                    distance_from_high=outcome.get('distance_from_high'),
                    vix_at_signal=outcome.get('vix_at_signal'),
                    spy_pct_above_sma=outcome.get('spy_pct_above_sma'),
                    new_score=outcome.get('new_score'),
                    distance_from_20d_high=outcome.get('distance_from_20d_high'),
                    sector_1d_change=outcome.get('sector_1d_change'),
                    timing=outcome.get('timing'),
                    eps_surprise_pct=outcome.get('eps_surprise_pct'),
                    close_to_high_pct=outcome.get('close_to_high_pct'),
                    spy_intraday_pct=outcome.get('spy_intraday_pct'),
                    sector_5d_return=outcome.get('sector_5d_return'),
                    vix_1w_change=outcome.get('vix_1w_change'),
                    entry_vs_open_pct=outcome.get('entry_vs_open_pct'),
                    entry_vs_vwap_pct=outcome.get('entry_vs_vwap_pct'),
                    bounce_pct_from_lod=outcome.get('bounce_pct_from_lod'),
                    num_positions_open=outcome.get('num_positions_open'),
                    first_5min_return=outcome.get('first_5min_return'),
                    intraday_spy_trend=outcome.get('intraday_spy_trend'),
                    spy_rsi_at_scan=outcome.get('spy_rsi_at_scan'),
                    pm_range_pct=outcome.get('pm_range_pct'),
                    catalyst_type=outcome.get('catalyst_type'),
                    short_percent_of_float=outcome.get('short_percent_of_float'),
                    sector=outcome.get('sector'),
                    trade_id=outcome.get('trade_id'),
                    margin_to_rsi=outcome.get('margin_to_rsi'),
                    margin_to_atr=outcome.get('margin_to_atr'),
                    margin_to_score=outcome.get('margin_to_score'),
                    margin_to_vix_skip=outcome.get('margin_to_vix_skip'),
                    news_sentiment=outcome.get('news_sentiment'),
                    news_impact_score=outcome.get('news_impact_score'),
                    insider_buy_30d_value=outcome.get('insider_buy_30d_value'),
                    insider_buy_days_ago=outcome.get('insider_buy_days_ago'),
                    outcome_1d=outcome.get('outcome_1d'),
                    outcome_2d=outcome.get('outcome_2d'),
                    outcome_3d=outcome.get('outcome_3d'),
                    outcome_4d=outcome.get('outcome_4d'),
                    outcome_5d=outcome.get('outcome_5d'),
                    outcome_max_gain_5d=outcome.get('outcome_max_gain_5d'),
                    outcome_max_dd_5d=outcome.get('outcome_max_dd_5d'),
                    tracked_at=outcome.get('tracked_at', datetime.now().isoformat()),
                )
                session.add(obj)
                session.flush()
                return obj.id

    def get_incomplete_signal_outcomes(self, days: int = 10) -> List[Dict]:
        """Get signal outcomes where outcome_5d is NULL"""
        with get_session() as session:
            rows = session.query(SignalOutcome).filter(
                SignalOutcome.outcome_5d.is_(None)
            ).order_by(
                SignalOutcome.scan_date.desc()
            ).limit(days * 100).all()
            return [_signal_outcome_to_dict(r) for r in rows]

    # ========================================================================
    # Rejected Outcomes
    # ========================================================================

    def save_rejected_outcome(self, outcome: Dict) -> int:
        """Save or update rejected signal outcome"""
        with get_session() as session:
            existing = session.query(RejectedOutcome).filter(
                RejectedOutcome.scan_id == outcome['scan_id'],
                RejectedOutcome.symbol == outcome['symbol'],
            ).first()

            if existing:
                existing.scan_date = outcome.get('scan_date')
                existing.scan_type = outcome.get('scan_type')
                existing.signal_rank = outcome.get('signal_rank')
                existing.rejection_reason = outcome.get('rejection_reason')
                existing.score = outcome.get('score')
                existing.signal_source = outcome.get('signal_source')
                existing.scan_price = outcome.get('scan_price')
                existing.volume_ratio = outcome.get('volume_ratio')
                existing.atr_pct = outcome.get('atr_pct')
                existing.entry_rsi = outcome.get('entry_rsi')
                existing.momentum_5d = outcome.get('momentum_5d')
                existing.gap_pct = outcome.get('gap_pct')
                existing.gap_confidence = outcome.get('gap_confidence')
                existing.outcome_1d = outcome.get('outcome_1d')
                existing.outcome_2d = outcome.get('outcome_2d')
                existing.outcome_3d = outcome.get('outcome_3d')
                existing.outcome_4d = outcome.get('outcome_4d')
                existing.outcome_5d = outcome.get('outcome_5d')
                existing.outcome_max_gain_5d = outcome.get('outcome_max_gain_5d')
                existing.outcome_max_dd_5d = outcome.get('outcome_max_dd_5d')
                existing.updated_at = datetime.now().isoformat()
                session.flush()
                return existing.id
            else:
                obj = RejectedOutcome(
                    scan_id=outcome['scan_id'],
                    symbol=outcome['symbol'],
                    scan_date=outcome.get('scan_date'),
                    scan_type=outcome.get('scan_type'),
                    signal_rank=outcome.get('signal_rank'),
                    rejection_reason=outcome.get('rejection_reason'),
                    score=outcome.get('score'),
                    signal_source=outcome.get('signal_source'),
                    scan_price=outcome.get('scan_price'),
                    volume_ratio=outcome.get('volume_ratio'),
                    atr_pct=outcome.get('atr_pct'),
                    entry_rsi=outcome.get('entry_rsi'),
                    momentum_5d=outcome.get('momentum_5d'),
                    gap_pct=outcome.get('gap_pct'),
                    gap_confidence=outcome.get('gap_confidence'),
                    outcome_1d=outcome.get('outcome_1d'),
                    outcome_2d=outcome.get('outcome_2d'),
                    outcome_3d=outcome.get('outcome_3d'),
                    outcome_4d=outcome.get('outcome_4d'),
                    outcome_5d=outcome.get('outcome_5d'),
                    outcome_max_gain_5d=outcome.get('outcome_max_gain_5d'),
                    outcome_max_dd_5d=outcome.get('outcome_max_dd_5d'),
                    tracked_at=outcome.get('tracked_at', datetime.now().isoformat()),
                )
                session.add(obj)
                session.flush()
                return obj.id

    # ========================================================================
    # Analytics
    # ========================================================================

    def get_sell_decision_quality(self, days: int = 30) -> List[Dict]:
        """Get sell decision quality view"""
        with get_session() as session:
            result = session.execute(
                text("SELECT * FROM v_sell_decision_quality "
                     "WHERE sell_date >= date('now', '-' || :days || ' days') "
                     "ORDER BY sell_date DESC"),
                {'days': days}
            )
            return [dict(row._mapping) for row in result.fetchall()]

    def get_signal_quality_by_source(self) -> List[Dict]:
        """Get signal quality aggregated by source"""
        with get_session() as session:
            result = session.execute(
                text("SELECT * FROM v_signal_quality_by_source ORDER BY avg_outcome_5d DESC")
            )
            return [dict(row._mapping) for row in result.fetchall()]

    def get_rejection_analysis(self) -> List[Dict]:
        """Get rejection analysis (missed opportunities)"""
        with get_session() as session:
            result = session.execute(
                text("SELECT * FROM v_rejection_analysis")
            )
            return [dict(row._mapping) for row in result.fetchall()]

    # ========================================================================
    # Batch Operations
    # ========================================================================

    def save_sell_outcomes_batch(self, outcomes: List[Dict]) -> int:
        """Save multiple sell outcomes (returns count saved)"""
        count = 0
        for outcome in outcomes:
            try:
                self.save_sell_outcome(outcome)
                count += 1
            except Exception as e:
                print(f"Warning: Failed to save sell outcome {outcome.get('trade_id')}: {e}")
        return count

    def save_signal_outcomes_batch(self, outcomes: List[Dict]) -> int:
        """Save multiple signal outcomes (returns count saved)"""
        count = 0
        for outcome in outcomes:
            try:
                self.save_signal_outcome(outcome)
                count += 1
            except Exception as e:
                print(f"Warning: Failed to save signal outcome {outcome.get('scan_id')}/{outcome.get('symbol')}: {e}")
        return count

    def save_rejected_outcomes_batch(self, outcomes: List[Dict]) -> int:
        """Save multiple rejected outcomes (returns count saved)"""
        count = 0
        for outcome in outcomes:
            try:
                self.save_rejected_outcome(outcome)
                count += 1
            except Exception as e:
                print(f"Warning: Failed to save rejected outcome {outcome.get('scan_id')}/{outcome.get('symbol')}: {e}")
        return count


# ==========================================================================
# Internal helpers
# ==========================================================================


def _apply_signal_outcome_update(obj: SignalOutcome, outcome: Dict):
    """Apply update fields to an existing SignalOutcome ORM object.
    Preserves COALESCE semantics for short_percent_of_float and trade_id."""
    obj.scan_date = outcome.get('scan_date')
    obj.scan_type = outcome.get('scan_type')
    obj.signal_rank = outcome.get('signal_rank')
    obj.action_taken = outcome.get('action_taken')
    obj.skip_reason = outcome.get('skip_reason')
    obj.score = outcome.get('score')
    obj.signal_source = outcome.get('signal_source')
    obj.scan_price = outcome.get('scan_price')
    obj.days_until_earnings = outcome.get('days_until_earnings')
    obj.earnings_gap_pct = outcome.get('earnings_gap_pct')
    obj.volume_ratio = outcome.get('volume_ratio')
    obj.atr_pct = outcome.get('atr_pct')
    obj.entry_rsi = outcome.get('entry_rsi')
    obj.momentum_5d = outcome.get('momentum_5d')
    obj.gap_pct = outcome.get('gap_pct')
    obj.gap_confidence = outcome.get('gap_confidence')
    obj.momentum_20d = outcome.get('momentum_20d')
    obj.distance_from_high = outcome.get('distance_from_high')
    obj.vix_at_signal = outcome.get('vix_at_signal')
    obj.spy_pct_above_sma = outcome.get('spy_pct_above_sma')
    obj.new_score = outcome.get('new_score')
    obj.distance_from_20d_high = outcome.get('distance_from_20d_high')
    obj.sector_1d_change = outcome.get('sector_1d_change')
    obj.timing = outcome.get('timing')
    obj.eps_surprise_pct = outcome.get('eps_surprise_pct')
    obj.close_to_high_pct = outcome.get('close_to_high_pct')
    obj.spy_intraday_pct = outcome.get('spy_intraday_pct')
    obj.sector_5d_return = outcome.get('sector_5d_return')
    obj.vix_1w_change = outcome.get('vix_1w_change')
    obj.entry_vs_open_pct = outcome.get('entry_vs_open_pct')
    obj.entry_vs_vwap_pct = outcome.get('entry_vs_vwap_pct')
    obj.bounce_pct_from_lod = outcome.get('bounce_pct_from_lod')
    obj.num_positions_open = outcome.get('num_positions_open')
    obj.first_5min_return = outcome.get('first_5min_return')
    obj.intraday_spy_trend = outcome.get('intraday_spy_trend')
    obj.spy_rsi_at_scan = outcome.get('spy_rsi_at_scan')
    obj.pm_range_pct = outcome.get('pm_range_pct')
    obj.catalyst_type = outcome.get('catalyst_type')
    # COALESCE: only overwrite if currently None
    if obj.short_percent_of_float is None:
        obj.short_percent_of_float = outcome.get('short_percent_of_float')
    obj.sector = outcome.get('sector')
    # COALESCE: only overwrite trade_id if currently None
    if obj.trade_id is None:
        obj.trade_id = outcome.get('trade_id')
    obj.margin_to_rsi = outcome.get('margin_to_rsi')
    obj.margin_to_atr = outcome.get('margin_to_atr')
    obj.margin_to_score = outcome.get('margin_to_score')
    obj.margin_to_vix_skip = outcome.get('margin_to_vix_skip')
    obj.outcome_1d = outcome.get('outcome_1d')
    obj.outcome_2d = outcome.get('outcome_2d')
    obj.outcome_3d = outcome.get('outcome_3d')
    obj.outcome_4d = outcome.get('outcome_4d')
    obj.outcome_5d = outcome.get('outcome_5d')
    obj.outcome_max_gain_5d = outcome.get('outcome_max_gain_5d')
    obj.outcome_max_dd_5d = outcome.get('outcome_max_dd_5d')
    obj.updated_at = datetime.now().isoformat()


def _sell_outcome_to_dict(obj: SellOutcome) -> Dict:
    """Convert SellOutcome ORM object to dict."""
    return {
        'id': obj.id,
        'trade_id': obj.trade_id,
        'symbol': obj.symbol,
        'sell_date': obj.sell_date,
        'sell_price': obj.sell_price,
        'sell_reason': obj.sell_reason,
        'sell_pnl_pct': obj.sell_pnl_pct,
        'post_sell_close_1d': obj.post_sell_close_1d,
        'post_sell_close_3d': obj.post_sell_close_3d,
        'post_sell_close_5d': obj.post_sell_close_5d,
        'post_sell_max_5d': obj.post_sell_max_5d,
        'post_sell_min_5d': obj.post_sell_min_5d,
        'post_sell_pnl_pct_1d': obj.post_sell_pnl_pct_1d,
        'post_sell_pnl_pct_5d': obj.post_sell_pnl_pct_5d,
        'tracked_at': obj.tracked_at,
        'updated_at': obj.updated_at,
        'buy_trade_id': obj.buy_trade_id,
    }


def _signal_outcome_to_dict(obj: SignalOutcome) -> Dict:
    """Convert SignalOutcome ORM object to dict."""
    d = {}
    for col in obj.__table__.columns:
        d[col.name] = getattr(obj, col.name)
    return d
