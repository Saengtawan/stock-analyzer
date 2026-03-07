"""
Outcome Repository - Database access for outcome tracking

Handles CRUD operations for:
- sell_outcomes
- signal_outcomes
- rejected_outcomes
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path


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
        conn = self._get_connection()
        try:
            # v7.02: Skip dup — same symbol+date+action already recorded (continuous scans re-see same blocked signal)
            dup = conn.execute(
                "SELECT id FROM signal_outcomes WHERE symbol = ? AND scan_date = ? AND action_taken = ?",
                (outcome['symbol'], outcome.get('scan_date'), outcome.get('action_taken'))
            ).fetchone()
            if dup:
                return dup['id']

            existing = conn.execute(
                "SELECT id FROM signal_outcomes WHERE scan_id = ? AND symbol = ?",
                (outcome['scan_id'], outcome['symbol'])
            ).fetchone()

            if existing:
                # Update
                conn.execute("""
                    UPDATE signal_outcomes SET
                        scan_date = ?, scan_type = ?, signal_rank = ?,
                        action_taken = ?, skip_reason = ?, score = ?, signal_source = ?,
                        scan_price = ?, days_until_earnings = ?, earnings_gap_pct = ?,
                        volume_ratio = ?, atr_pct = ?, entry_rsi = ?,
                        momentum_5d = ?, gap_pct = ?, gap_confidence = ?,
                        momentum_20d = ?, distance_from_high = ?,
                        outcome_1d = ?, outcome_2d = ?, outcome_3d = ?,
                        outcome_4d = ?, outcome_5d = ?, outcome_max_gain_5d = ?,
                        outcome_max_dd_5d = ?, updated_at = ?
                    WHERE scan_id = ? AND symbol = ?
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
                    INSERT INTO signal_outcomes (
                        scan_id, symbol, scan_date, scan_type, signal_rank,
                        action_taken, skip_reason, score, signal_source, scan_price,
                        days_until_earnings, earnings_gap_pct,
                        volume_ratio, atr_pct, entry_rsi, momentum_5d, gap_pct, gap_confidence,
                        momentum_20d, distance_from_high,
                        outcome_1d, outcome_2d, outcome_3d,
                        outcome_4d, outcome_5d,
                        outcome_max_gain_5d, outcome_max_dd_5d, tracked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
