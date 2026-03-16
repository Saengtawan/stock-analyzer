"""
Outcome Repository - Database access for outcome tracking

Handles CRUD operations for:
- sell_outcomes
- signal_outcomes
- rejected_outcomes
"""

import sqlite3
import yaml
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path


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
        if db_path is None:
            project_root = Path(__file__).parent.parent.parent.parent
            db_path = str(project_root / 'data' / 'trade_history.db')
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

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
        conn = self._get_connection()
        try:
            # Check if already exists
            existing = conn.execute(
                "SELECT id FROM sell_outcomes WHERE trade_id = ?",
                (outcome['trade_id'],)
            ).fetchone()

            if existing:
                # Update existing
                conn.execute("""
                    UPDATE sell_outcomes SET
                        symbol = ?,
                        sell_date = ?,
                        sell_price = ?,
                        sell_reason = ?,
                        sell_pnl_pct = ?,
                        post_sell_close_1d = ?,
                        post_sell_close_3d = ?,
                        post_sell_close_5d = ?,
                        post_sell_max_5d = ?,
                        post_sell_min_5d = ?,
                        post_sell_pnl_pct_1d = ?,
                        post_sell_pnl_pct_5d = ?,
                        updated_at = ?
                    WHERE trade_id = ?
                """, (
                    outcome.get('symbol'),
                    outcome.get('sell_date'),
                    outcome.get('sell_price'),
                    outcome.get('sell_reason'),
                    outcome.get('sell_pnl_pct'),
                    outcome.get('post_sell_close_1d'),
                    outcome.get('post_sell_close_3d'),
                    outcome.get('post_sell_close_5d'),
                    outcome.get('post_sell_max_5d'),
                    outcome.get('post_sell_min_5d'),
                    outcome.get('post_sell_pnl_pct_1d'),
                    outcome.get('post_sell_pnl_pct_5d'),
                    datetime.now().isoformat(),
                    outcome['trade_id']
                ))
                conn.commit()
                return existing['id']
            else:
                # Insert new
                cursor = conn.execute("""
                    INSERT INTO sell_outcomes (
                        trade_id, symbol, sell_date, sell_price, sell_reason,
                        sell_pnl_pct, post_sell_close_1d, post_sell_close_3d,
                        post_sell_close_5d, post_sell_max_5d, post_sell_min_5d,
                        post_sell_pnl_pct_1d, post_sell_pnl_pct_5d, tracked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    outcome['trade_id'],
                    outcome.get('symbol'),
                    outcome.get('sell_date'),
                    outcome.get('sell_price'),
                    outcome.get('sell_reason'),
                    outcome.get('sell_pnl_pct'),
                    outcome.get('post_sell_close_1d'),
                    outcome.get('post_sell_close_3d'),
                    outcome.get('post_sell_close_5d'),
                    outcome.get('post_sell_max_5d'),
                    outcome.get('post_sell_min_5d'),
                    outcome.get('post_sell_pnl_pct_1d'),
                    outcome.get('post_sell_pnl_pct_5d'),
                    outcome.get('tracked_at', datetime.now().isoformat())
                ))
                conn.commit()
                return cursor.lastrowid
        finally:
            conn.close()

    def get_incomplete_sell_outcomes(self) -> List[Dict]:
        """Get sell outcomes where post_sell_close_5d is NULL (not yet complete)"""
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM sell_outcomes
                WHERE post_sell_close_5d IS NULL
                ORDER BY sell_date DESC
            """).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_complete_sell_outcome_ids(self) -> set:
        """Get set of trade_ids that have complete 5-day data"""
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT trade_id FROM sell_outcomes
                WHERE post_sell_close_5d IS NOT NULL
            """).fetchall()
            return {row['trade_id'] for row in rows}
        finally:
            conn.close()

    # ========================================================================
    # Signal Outcomes
    # ========================================================================

    def save_signal_outcome(self, outcome: Dict) -> int:
        """Save or update signal outcome"""
        # v7.5: Compute margin_to_threshold fields from raw values.
        # Thresholds read from trading.yaml at module load (_DIP_THRESHOLDS) so they track config changes.
        t = _DIP_THRESHOLDS
        if outcome.get('entry_rsi') is not None:
            outcome.setdefault('margin_to_rsi', round(outcome['entry_rsi'] - t['rsi'], 2))
        if outcome.get('atr_pct') is not None:
            outcome.setdefault('margin_to_atr', round(outcome['atr_pct'] - t['atr'], 2))
        if outcome.get('new_score') is not None and outcome['new_score'] > 0:
            outcome.setdefault('margin_to_score', round(outcome['new_score'] - t['score'], 2))
        if outcome.get('vix_at_signal') is not None:
            outcome.setdefault('margin_to_vix_skip', round(outcome['vix_at_signal'] - t['vix_skip'], 2))

        conn = self._get_connection()
        try:
            # v7.8: Dedup by (symbol, scan_date, signal_source) — prevents same-strategy dups.
            # Priority: BOUGHT=1 > QUEUED=2 > QUEUE_FULL=3 > SKIPPED_FILTER=4.
            # Allows DIP+OVN on same day; blocks duplicate QUEUE_FULL rows from continuous scans.
            ACTION_PRIORITY = {'BOUGHT': 1, 'QUEUED': 2, 'QUEUE_FULL': 3, 'SKIPPED_FILTER': 4}
            signal_source = outcome.get('signal_source')
            incoming_prio = ACTION_PRIORITY.get(outcome.get('action_taken'), 99)

            if signal_source:
                dup = conn.execute(
                    "SELECT id, outcome_5d, action_taken FROM signal_outcomes "
                    "WHERE symbol=? AND scan_date=? AND signal_source=?",
                    (outcome['symbol'], outcome.get('scan_date'), signal_source)
                ).fetchone()
            else:
                dup = conn.execute(
                    "SELECT id, outcome_5d, action_taken FROM signal_outcomes "
                    "WHERE symbol=? AND scan_date=? AND signal_source IS NULL AND action_taken=?",
                    (outcome['symbol'], outcome.get('scan_date'), outcome.get('action_taken'))
                ).fetchone()

            _update_id = None  # row id to UPDATE; None → INSERT new row

            if dup:
                existing_prio = ACTION_PRIORITY.get(dup['action_taken'], 99)
                if incoming_prio < existing_prio:
                    # Priority upgrade (e.g. BOUGHT replaces QUEUE_FULL) — overwrite full row
                    _update_id = dup['id']
                else:
                    # Same or lower priority — only fill NULL outcome_5d if we now have it
                    if dup['outcome_5d'] is None and outcome.get('outcome_5d') is not None:
                        conn.execute("""
                            UPDATE signal_outcomes SET
                                outcome_1d = ?, outcome_2d = ?, outcome_3d = ?,
                                outcome_4d = ?, outcome_5d = ?, outcome_max_gain_5d = ?,
                                outcome_max_dd_5d = ?, updated_at = ?
                            WHERE id = ?
                        """, (
                            outcome.get('outcome_1d'),
                            outcome.get('outcome_2d'),
                            outcome.get('outcome_3d'),
                            outcome.get('outcome_4d'),
                            outcome.get('outcome_5d'),
                            outcome.get('outcome_max_gain_5d'),
                            outcome.get('outcome_max_dd_5d'),
                            datetime.now().isoformat(),
                            dup['id']
                        ))
                        conn.commit()
                    return dup['id']

            if _update_id is None:
                # Check for same scan_id re-saving its own row (same scan re-ran, no source dup)
                row = conn.execute(
                    "SELECT id FROM signal_outcomes WHERE scan_id = ? AND symbol = ?",
                    (outcome['scan_id'], outcome['symbol'])
                ).fetchone()
                if row:
                    _update_id = row['id']

            if _update_id is not None:
                # Update
                conn.execute("""
                    UPDATE signal_outcomes SET
                        scan_date = ?, scan_type = ?, signal_rank = ?,
                        action_taken = ?, skip_reason = ?, score = ?, signal_source = ?,
                        scan_price = ?, days_until_earnings = ?, earnings_gap_pct = ?,
                        volume_ratio = ?, atr_pct = ?, entry_rsi = ?,
                        momentum_5d = ?, gap_pct = ?, gap_confidence = ?,
                        momentum_20d = ?, distance_from_high = ?,
                        vix_at_signal = ?, spy_pct_above_sma = ?,
                        new_score = ?, distance_from_20d_high = ?, sector_1d_change = ?,
                        timing = ?, eps_surprise_pct = ?, close_to_high_pct = ?,
                        spy_intraday_pct = ?, sector_5d_return = ?,
                        vix_1w_change = ?, entry_vs_open_pct = ?,
                        entry_vs_vwap_pct = ?, bounce_pct_from_lod = ?,
                        num_positions_open = ?, first_5min_return = ?,
                        intraday_spy_trend = ?, spy_rsi_at_scan = ?, pm_range_pct = ?,
                        catalyst_type = ?,
                        short_percent_of_float = COALESCE(short_percent_of_float, ?),
                        sector = ?, trade_id = COALESCE(trade_id, ?),
                        margin_to_rsi = ?, margin_to_atr = ?,
                        margin_to_score = ?, margin_to_vix_skip = ?,
                        outcome_1d = ?, outcome_2d = ?, outcome_3d = ?,
                        outcome_4d = ?, outcome_5d = ?, outcome_max_gain_5d = ?,
                        outcome_max_dd_5d = ?, updated_at = ?
                    WHERE id = ?
                """, (
                    outcome.get('scan_date'),
                    outcome.get('scan_type'),
                    outcome.get('signal_rank'),
                    outcome.get('action_taken'),
                    outcome.get('skip_reason'),
                    outcome.get('score'),
                    outcome.get('signal_source'),
                    outcome.get('scan_price'),
                    outcome.get('days_until_earnings'),
                    outcome.get('earnings_gap_pct'),
                    outcome.get('volume_ratio'),
                    outcome.get('atr_pct'),
                    outcome.get('entry_rsi'),
                    outcome.get('momentum_5d'),
                    outcome.get('gap_pct'),
                    outcome.get('gap_confidence'),
                    outcome.get('momentum_20d'),
                    outcome.get('distance_from_high'),
                    outcome.get('vix_at_signal'),
                    outcome.get('spy_pct_above_sma'),
                    outcome.get('new_score'),
                    outcome.get('distance_from_20d_high'),
                    outcome.get('sector_1d_change'),
                    outcome.get('timing'),
                    outcome.get('eps_surprise_pct'),
                    outcome.get('close_to_high_pct'),
                    outcome.get('spy_intraday_pct'),
                    outcome.get('sector_5d_return'),
                    outcome.get('vix_1w_change'),
                    outcome.get('entry_vs_open_pct'),
                    outcome.get('entry_vs_vwap_pct'),
                    outcome.get('bounce_pct_from_lod'),
                    outcome.get('num_positions_open'),
                    outcome.get('first_5min_return'),
                    outcome.get('intraday_spy_trend'),
                    outcome.get('spy_rsi_at_scan'),
                    outcome.get('pm_range_pct'),
                    outcome.get('catalyst_type'),
                    outcome.get('sector'),
                    outcome.get('trade_id'),
                    outcome.get('margin_to_rsi'),
                    outcome.get('margin_to_atr'),
                    outcome.get('margin_to_score'),
                    outcome.get('margin_to_vix_skip'),
                    outcome.get('outcome_1d'),
                    outcome.get('outcome_2d'),
                    outcome.get('outcome_3d'),
                    outcome.get('outcome_4d'),
                    outcome.get('outcome_5d'),
                    outcome.get('outcome_max_gain_5d'),
                    outcome.get('outcome_max_dd_5d'),
                    datetime.now().isoformat(),
                    _update_id
                ))
                conn.commit()
                return _update_id
            else:
                # Insert
                cursor = conn.execute("""
                    INSERT INTO signal_outcomes (
                        scan_id, symbol, scan_date, scan_type, signal_rank,
                        action_taken, skip_reason, score, signal_source, scan_price,
                        days_until_earnings, earnings_gap_pct,
                        volume_ratio, atr_pct, entry_rsi, momentum_5d, gap_pct, gap_confidence,
                        momentum_20d, distance_from_high, vix_at_signal, spy_pct_above_sma,
                        new_score, distance_from_20d_high, sector_1d_change,
                        timing, eps_surprise_pct, close_to_high_pct,
                        spy_intraday_pct, sector_5d_return, vix_1w_change, entry_vs_open_pct,
                        entry_vs_vwap_pct, bounce_pct_from_lod,
                        num_positions_open, first_5min_return,
                        intraday_spy_trend, spy_rsi_at_scan, pm_range_pct,
                        catalyst_type,
                        short_percent_of_float, sector, trade_id,
                        margin_to_rsi, margin_to_atr, margin_to_score, margin_to_vix_skip,
                        news_sentiment, news_impact_score,
                        insider_buy_30d_value, insider_buy_days_ago,
                        outcome_1d, outcome_2d, outcome_3d,
                        outcome_4d, outcome_5d,
                        outcome_max_gain_5d, outcome_max_dd_5d, tracked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    outcome['scan_id'],
                    outcome['symbol'],
                    outcome.get('scan_date'),
                    outcome.get('scan_type'),
                    outcome.get('signal_rank'),
                    outcome.get('action_taken'),
                    outcome.get('skip_reason'),
                    outcome.get('score'),
                    outcome.get('signal_source'),
                    outcome.get('scan_price'),
                    outcome.get('days_until_earnings'),
                    outcome.get('earnings_gap_pct'),
                    outcome.get('volume_ratio'),
                    outcome.get('atr_pct'),
                    outcome.get('entry_rsi'),
                    outcome.get('momentum_5d'),
                    outcome.get('gap_pct'),
                    outcome.get('gap_confidence'),
                    outcome.get('momentum_20d'),
                    outcome.get('distance_from_high'),
                    outcome.get('vix_at_signal'),
                    outcome.get('spy_pct_above_sma'),
                    outcome.get('new_score'),
                    outcome.get('distance_from_20d_high'),
                    outcome.get('sector_1d_change'),
                    outcome.get('timing'),
                    outcome.get('eps_surprise_pct'),
                    outcome.get('close_to_high_pct'),
                    outcome.get('spy_intraday_pct'),
                    outcome.get('sector_5d_return'),
                    outcome.get('vix_1w_change'),
                    outcome.get('entry_vs_open_pct'),
                    outcome.get('entry_vs_vwap_pct'),
                    outcome.get('bounce_pct_from_lod'),
                    outcome.get('num_positions_open'),
                    outcome.get('first_5min_return'),
                    outcome.get('intraday_spy_trend'),
                    outcome.get('spy_rsi_at_scan'),
                    outcome.get('pm_range_pct'),
                    outcome.get('catalyst_type'),
                    outcome.get('short_percent_of_float'),
                    outcome.get('sector'),
                    outcome.get('trade_id'),
                    outcome.get('margin_to_rsi'),
                    outcome.get('margin_to_atr'),
                    outcome.get('margin_to_score'),
                    outcome.get('margin_to_vix_skip'),
                    outcome.get('news_sentiment'),
                    outcome.get('news_impact_score'),
                    outcome.get('insider_buy_30d_value'),
                    outcome.get('insider_buy_days_ago'),
                    outcome.get('outcome_1d'),
                    outcome.get('outcome_2d'),
                    outcome.get('outcome_3d'),
                    outcome.get('outcome_4d'),
                    outcome.get('outcome_5d'),
                    outcome.get('outcome_max_gain_5d'),
                    outcome.get('outcome_max_dd_5d'),
                    outcome.get('tracked_at', datetime.now().isoformat())
                ))
                conn.commit()
                return cursor.lastrowid
        finally:
            conn.close()

    def get_incomplete_signal_outcomes(self, days: int = 10) -> List[Dict]:
        """Get signal outcomes where outcome_5d is NULL"""
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM signal_outcomes
                WHERE outcome_5d IS NULL
                ORDER BY scan_date DESC
                LIMIT ?
            """, (days * 100,)).fetchall()  # Approx 100 signals per day
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ========================================================================
    # Rejected Outcomes
    # ========================================================================

    def save_rejected_outcome(self, outcome: Dict) -> int:
        """Save or update rejected signal outcome"""
        conn = self._get_connection()
        try:
            existing = conn.execute(
                "SELECT id FROM rejected_outcomes WHERE scan_id = ? AND symbol = ?",
                (outcome['scan_id'], outcome['symbol'])
            ).fetchone()

            if existing:
                # Update
                conn.execute("""
                    UPDATE rejected_outcomes SET
                        scan_date = ?, scan_type = ?, signal_rank = ?,
                        rejection_reason = ?, score = ?, signal_source = ?,
                        scan_price = ?,
                        volume_ratio = ?, atr_pct = ?, entry_rsi = ?,
                        momentum_5d = ?, gap_pct = ?, gap_confidence = ?,
                        outcome_1d = ?, outcome_2d = ?,
                        outcome_3d = ?, outcome_4d = ?, outcome_5d = ?,
                        outcome_max_gain_5d = ?,
                        outcome_max_dd_5d = ?, updated_at = ?
                    WHERE scan_id = ? AND symbol = ?
                """, (
                    outcome.get('scan_date'),
                    outcome.get('scan_type'),
                    outcome.get('signal_rank'),
                    outcome.get('rejection_reason'),
                    outcome.get('score'),
                    outcome.get('signal_source'),
                    outcome.get('scan_price'),
                    outcome.get('volume_ratio'),
                    outcome.get('atr_pct'),
                    outcome.get('entry_rsi'),
                    outcome.get('momentum_5d'),
                    outcome.get('gap_pct'),
                    outcome.get('gap_confidence'),
                    outcome.get('outcome_1d'),
                    outcome.get('outcome_2d'),
                    outcome.get('outcome_3d'),
                    outcome.get('outcome_4d'),
                    outcome.get('outcome_5d'),
                    outcome.get('outcome_max_gain_5d'),
                    outcome.get('outcome_max_dd_5d'),
                    datetime.now().isoformat(),
                    outcome['scan_id'],
                    outcome['symbol']
                ))
                conn.commit()
                return existing['id']
            else:
                # Insert
                cursor = conn.execute("""
                    INSERT INTO rejected_outcomes (
                        scan_id, symbol, scan_date, scan_type, signal_rank,
                        rejection_reason, score, signal_source, scan_price,
                        volume_ratio, atr_pct, entry_rsi, momentum_5d, gap_pct, gap_confidence,
                        outcome_1d, outcome_2d, outcome_3d,
                        outcome_4d, outcome_5d,
                        outcome_max_gain_5d, outcome_max_dd_5d, tracked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    outcome['scan_id'],
                    outcome['symbol'],
                    outcome.get('scan_date'),
                    outcome.get('scan_type'),
                    outcome.get('signal_rank'),
                    outcome.get('rejection_reason'),
                    outcome.get('score'),
                    outcome.get('signal_source'),
                    outcome.get('scan_price'),
                    outcome.get('volume_ratio'),
                    outcome.get('atr_pct'),
                    outcome.get('entry_rsi'),
                    outcome.get('momentum_5d'),
                    outcome.get('gap_pct'),
                    outcome.get('gap_confidence'),
                    outcome.get('outcome_1d'),
                    outcome.get('outcome_2d'),
                    outcome.get('outcome_3d'),
                    outcome.get('outcome_4d'),
                    outcome.get('outcome_5d'),
                    outcome.get('outcome_max_gain_5d'),
                    outcome.get('outcome_max_dd_5d'),
                    outcome.get('tracked_at', datetime.now().isoformat())
                ))
                conn.commit()
                return cursor.lastrowid
        finally:
            conn.close()

    # ========================================================================
    # Analytics
    # ========================================================================

    def get_sell_decision_quality(self, days: int = 30) -> List[Dict]:
        """Get sell decision quality view"""
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM v_sell_decision_quality
                WHERE sell_date >= date('now', '-' || ? || ' days')
                ORDER BY sell_date DESC
            """, (days,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_signal_quality_by_source(self) -> List[Dict]:
        """Get signal quality aggregated by source"""
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM v_signal_quality_by_source
                ORDER BY avg_outcome_5d DESC
            """).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_rejection_analysis(self) -> List[Dict]:
        """Get rejection analysis (missed opportunities)"""
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM v_rejection_analysis
            """).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

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
