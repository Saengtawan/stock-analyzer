"""
Discovery Outcome Tracker — records predicted vs actual outcomes for every pick.

After each pick expires/completes (D3+), records:
- predicted E[R] vs actual return
- TP hit / SL hit
- Regime at scan time

Runs as part of the scan cycle: before new scan, check expired picks for outcomes.
Data stored in `discovery_outcomes` table.
"""
import logging
import sqlite3
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


class OutcomeTracker:
    """Track prediction accuracy for Discovery picks."""

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discovery_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                predicted_er REAL,
                predicted_wr REAL,
                actual_return_d3 REAL,
                actual_return_d5 REAL,
                max_gain REAL,
                max_dd REAL,
                tp_hit INTEGER,
                sl_hit INTEGER,
                regime TEXT,
                atr_pct REAL,
                sector TEXT,
                vix_close REAL,
                scan_price REAL,
                exit_price REAL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(scan_date, symbol)
            )
        """)
        conn.commit()
        conn.close()

    def track_expired_picks(self) -> int:
        """Find picks that have expired/completed and record their outcomes.

        Checks discovery_picks for picks with status != 'active' that don't
        yet have an entry in discovery_outcomes. Fetches actual price data
        to compute real returns.

        Returns number of new outcomes tracked.
        """
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Find picks that completed (not active) and not yet tracked
        rows = conn.execute("""
            SELECT p.scan_date, p.symbol, p.layer2_score, p.scan_price,
                   p.current_price, p.sl_pct, p.tp1_pct, p.sl_price, p.tp1_price,
                   p.status, p.sector, p.vix_close, p.atr_pct,
                   p.expected_gain
            FROM discovery_picks p
            LEFT JOIN discovery_outcomes o ON p.scan_date = o.scan_date AND p.symbol = o.symbol
            WHERE p.status IN ('replaced', 'expired', 'hit_tp1', 'hit_sl')
              AND o.id IS NULL
              AND p.scan_price > 0
            ORDER BY p.scan_date
        """).fetchall()
        conn.close()

        if not rows:
            return 0

        tracked = 0
        for row in rows:
            outcome = self._compute_outcome(row)
            if outcome:
                self._save_outcome(outcome)
                tracked += 1

        if tracked:
            logger.info("OutcomeTracker: recorded %d new outcomes (from %d candidates)", tracked, len(rows))

        return tracked

    def _compute_outcome(self, pick: sqlite3.Row) -> Optional[dict]:
        """Compute actual outcome for a pick using signal_daily_bars or yfinance fallback."""
        scan_date = pick['scan_date']
        symbol = pick['symbol']
        scan_price = pick['scan_price']
        sl_pct = pick['sl_pct'] or 3.0
        tp_pct = pick['tp1_pct'] or 3.0

        # Try signal_daily_bars first (most accurate — intraday OHLC)
        conn = sqlite3.connect(str(DB_PATH))
        bars = conn.execute("""
            SELECT day_offset, open, high, low, close
            FROM signal_daily_bars
            WHERE scan_date = ? AND symbol = ?
            ORDER BY day_offset
        """, (scan_date, symbol)).fetchall()
        conn.close()

        if bars and len(bars) >= 4:
            return self._outcome_from_bars(pick, bars)

        # Fallback: use discovery_picks status + current_price
        return self._outcome_from_status(pick)

    def _outcome_from_bars(self, pick: sqlite3.Row, bars: list) -> dict:
        """Compute precise outcome from daily OHLC bars."""
        scan_price = pick['scan_price']
        sl_pct = pick['sl_pct'] or 3.0
        tp_pct = pick['tp1_pct'] or 3.0

        # D0 is scan day, D1+ are post-scan
        d0_close = None
        max_high = 0
        min_low = float('inf')
        d3_close = None
        d5_close = None

        for offset, open_p, high, low, close in bars:
            if offset == 0:
                d0_close = close if close and close > 0 else scan_price
                entry = d0_close
            if high and high > 0:
                max_high = max(max_high, high)
            if low and low > 0:
                min_low = min(min_low, low)
            if offset == 3 and close and close > 0:
                d3_close = close
            if offset == 5 and close and close > 0:
                d5_close = close

        entry = d0_close or scan_price
        if entry <= 0:
            return None

        max_gain_pct = ((max_high / entry) - 1) * 100 if max_high > 0 else 0
        max_dd_pct = ((min_low / entry) - 1) * 100 if min_low < float('inf') else 0

        tp_hit = 1 if max_gain_pct >= tp_pct else 0
        sl_hit = 1 if max_dd_pct <= -sl_pct else 0

        d3_ret = ((d3_close / entry) - 1) * 100 if d3_close else None
        d5_ret = ((d5_close / entry) - 1) * 100 if d5_close else None

        # Determine regime from expected_gain (macro E[R] stored at scan time)
        macro_er = pick['expected_gain'] or 0
        if macro_er > 0.5:
            regime = 'BULL'
        elif macro_er > -0.5:
            regime = 'STRESS'
        else:
            regime = 'CRISIS'

        return {
            'scan_date': pick['scan_date'],
            'symbol': pick['symbol'],
            # v6.0: Guard against v2 composite scores (>10) polluting outcomes
            # v3 E[R] is always < 10%, v2 composite is 0-100
            'predicted_er': pick['layer2_score'] if (pick['layer2_score'] or 0) < 10 else None,
            'predicted_wr': None,  # HoldKernel WR not stored per-pick yet
            'actual_return_d3': round(d3_ret, 4) if d3_ret is not None else None,
            'actual_return_d5': round(d5_ret, 4) if d5_ret is not None else None,
            'max_gain': round(max_gain_pct, 4),
            'max_dd': round(max_dd_pct, 4),
            'tp_hit': tp_hit,
            'sl_hit': sl_hit,
            'regime': regime,
            'atr_pct': pick['atr_pct'],
            'sector': pick['sector'],
            'vix_close': pick['vix_close'],
            'scan_price': pick['scan_price'],
            'exit_price': d3_close or pick['current_price'],
        }

    def _outcome_from_status(self, pick: sqlite3.Row) -> dict:
        """Fallback: estimate outcome from pick status + current_price."""
        scan_price = pick['scan_price']
        current_price = pick['current_price'] or scan_price
        if scan_price <= 0:
            return None

        actual_ret = ((current_price / scan_price) - 1) * 100

        tp_hit = 1 if pick['status'] == 'hit_tp1' else 0
        sl_hit = 1 if pick['status'] == 'hit_sl' else 0

        macro_er = pick['expected_gain'] or 0
        if macro_er > 0.5:
            regime = 'BULL'
        elif macro_er > -0.5:
            regime = 'STRESS'
        else:
            regime = 'CRISIS'

        return {
            'scan_date': pick['scan_date'],
            'symbol': pick['symbol'],
            'predicted_er': pick['layer2_score'] if (pick['layer2_score'] or 0) < 10 else None,
            'predicted_wr': None,
            'actual_return_d3': round(actual_ret, 4),
            'actual_return_d5': None,
            'max_gain': round(actual_ret, 4) if actual_ret > 0 else 0,
            'max_dd': round(actual_ret, 4) if actual_ret < 0 else 0,
            'tp_hit': tp_hit,
            'sl_hit': sl_hit,
            'regime': regime,
            'atr_pct': pick['atr_pct'],
            'sector': pick['sector'],
            'vix_close': pick['vix_close'],
            'scan_price': pick['scan_price'],
            'exit_price': current_price,
        }

    def _save_outcome(self, outcome: dict):
        """Insert outcome into DB (UPSERT)."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute("""
                INSERT OR REPLACE INTO discovery_outcomes
                (scan_date, symbol, predicted_er, predicted_wr,
                 actual_return_d3, actual_return_d5, max_gain, max_dd,
                 tp_hit, sl_hit, regime, atr_pct, sector, vix_close,
                 scan_price, exit_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                outcome['scan_date'], outcome['symbol'],
                outcome['predicted_er'], outcome['predicted_wr'],
                outcome['actual_return_d3'], outcome['actual_return_d5'],
                outcome['max_gain'], outcome['max_dd'],
                outcome['tp_hit'], outcome['sl_hit'],
                outcome['regime'], outcome['atr_pct'],
                outcome['sector'], outcome['vix_close'],
                outcome['scan_price'], outcome['exit_price'],
            ))
            conn.commit()
        finally:
            conn.close()

    def backfill_from_historical(self) -> int:
        """Backfill outcomes from backfill_signal_outcomes for historical calibration.

        Uses the large historical dataset (51K signals) to bootstrap the
        outcome tracker with predicted vs actual data. This gives the
        calibrator enough data to compute meaningful confidence scores.

        Returns number of outcomes inserted.
        """
        conn = sqlite3.connect(str(DB_PATH))

        # Check how many we already have
        existing = conn.execute("SELECT COUNT(*) FROM discovery_outcomes").fetchone()[0]
        if existing > 1000:
            logger.info("OutcomeTracker: already have %d outcomes, skip backfill", existing)
            conn.close()
            return 0

        # Pull from backfill_signal_outcomes with kernel-style features
        # We don't have predicted_er for historical, but we can reconstruct regime from VIX
        rows = conn.execute("""
            SELECT scan_date, symbol, outcome_3d, outcome_5d,
                   outcome_max_gain_5d, outcome_max_dd_5d,
                   atr_pct, vix_at_signal, sector
            FROM backfill_signal_outcomes
            WHERE outcome_3d IS NOT NULL
            ORDER BY scan_date DESC
            LIMIT 5000
        """).fetchall()

        if not rows:
            conn.close()
            return 0

        inserted = 0
        for r in rows:
            scan_date, symbol, o3d, o5d, mg, mdd, atr, vix, sector = r

            # Reconstruct regime from VIX
            vix = vix or 20
            if vix < 20:
                regime = 'BULL'
            elif vix < 30:
                regime = 'STRESS'
            else:
                regime = 'CRISIS'

            tp_pct = max(0.5, 0.75 * (atr or 2.0))  # approximate TP
            sl_pct = max(1.5, 1.5 * (atr or 2.0))    # approximate SL

            tp_hit = 1 if (mg or 0) >= tp_pct else 0
            sl_hit = 1 if (mdd or 0) <= -sl_pct else 0

            try:
                conn.execute("""
                    INSERT OR IGNORE INTO discovery_outcomes
                    (scan_date, symbol, predicted_er, predicted_wr,
                     actual_return_d3, actual_return_d5, max_gain, max_dd,
                     tp_hit, sl_hit, regime, atr_pct, sector, vix_close,
                     scan_price, exit_price)
                    VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """, (scan_date, symbol, o3d, o5d, mg, mdd,
                      tp_hit, sl_hit, regime, atr, sector, vix))
                inserted += 1
            except sqlite3.IntegrityError:
                pass

        conn.commit()
        conn.close()
        logger.info("OutcomeTracker: backfilled %d historical outcomes", inserted)
        return inserted
