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
from database.orm.base import get_session
from sqlalchemy import text
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)



class OutcomeTracker:
    """Track prediction accuracy for Discovery picks."""

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        with get_session() as session:
            session.execute(text("""
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
            """))

    def track_expired_picks(self) -> int:
        """Find picks that have expired/completed and record their outcomes.

        Checks discovery_picks for picks with status != 'active' that don't
        yet have an entry in discovery_outcomes. Fetches actual price data
        to compute real returns.

        Returns number of new outcomes tracked.
        """
        with get_session() as session:
            # Find picks that completed (not active) and not yet tracked
            rows = session.execute(text("""
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
            """)).mappings().fetchall()

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

    def _compute_outcome(self, pick: dict) -> Optional[dict]:
        """Compute actual outcome for a pick using signal_daily_bars or yfinance fallback."""
        scan_date = pick['scan_date']
        symbol = pick['symbol']
        scan_price = pick['scan_price']
        sl_pct = pick['sl_pct'] or 3.0
        tp_pct = pick['tp1_pct'] or 3.0

        # Try signal_daily_bars first (most accurate — intraday OHLC)
        with get_session() as session:
            bars = session.execute(text("""
                SELECT day_offset, open, high, low, close
                FROM signal_daily_bars
                WHERE scan_date = :p0 AND symbol = :p1
                ORDER BY day_offset
            """), {'p0': scan_date, 'p1': symbol}).fetchall()

        if bars and len(bars) >= 4:
            return self._outcome_from_bars(pick, bars)

        # Fallback: use discovery_picks status + current_price
        return self._outcome_from_status(pick)

    def _outcome_from_bars(self, pick: dict, bars: list) -> dict:
        """Compute precise outcome from daily OHLC bars."""
        scan_price = pick['scan_price']
        sl_pct = pick['sl_pct'] or 3.0
        tp_pct = pick['tp1_pct'] or 3.0

        # v6.0: Use scan_price as entry (not D0 close) — matches pick creation
        d0_open = None
        max_high = 0
        min_low = float('inf')
        d3_close = None
        d5_close = None

        for offset, open_p, high, low, close in bars:
            if offset == 0:
                d0_open = open_p if open_p and open_p > 0 else scan_price
            if high and high > 0:
                max_high = max(max_high, high)
            if low and low > 0:
                min_low = min(min_low, low)
            if offset == 3 and close and close > 0:
                d3_close = close
            if offset == 5 and close and close > 0:
                d5_close = close

        entry = d0_open or scan_price
        if entry <= 0:
            return None

        max_gain_pct = ((max_high / entry) - 1) * 100 if max_high > 0 else 0
        max_dd_pct = ((min_low / entry) - 1) * 100 if min_low < float('inf') else 0

        # v6.0: Determine SL first, then TP (order matters — SL takes priority)
        # Check day-by-day to see which hit first
        tp_hit = 0
        sl_hit = 0
        for offset, open_p, high, low, close in bars:
            if offset == 0:
                continue  # skip scan day for TP/SL
            day_high_pct = ((high / entry) - 1) * 100 if high and high > 0 else 0
            day_low_pct = ((low / entry) - 1) * 100 if low and low > 0 else 0
            if day_low_pct <= -sl_pct:
                sl_hit = 1
                break  # SL hit first on this day
            if day_high_pct >= tp_pct:
                tp_hit = 1
                break  # TP hit first on this day

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

    def _outcome_from_status(self, pick: dict) -> dict:
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
        with get_session() as session:
            session.execute(text("""
                INSERT OR REPLACE INTO discovery_outcomes
                (scan_date, symbol, predicted_er, predicted_wr,
                 actual_return_d3, actual_return_d5, max_gain, max_dd,
                 tp_hit, sl_hit, regime, atr_pct, sector, vix_close,
                 scan_price, exit_price)
                VALUES (:p0, :p1, :p2, :p3, :p4, :p5, :p6, :p7, :p8, :p9, :p10, :p11, :p12, :p13, :p14, :p15)
            """), {
                'p0': outcome['scan_date'], 'p1': outcome['symbol'],
                'p2': outcome['predicted_er'], 'p3': outcome['predicted_wr'],
                'p4': outcome['actual_return_d3'], 'p5': outcome['actual_return_d5'],
                'p6': outcome['max_gain'], 'p7': outcome['max_dd'],
                'p8': outcome['tp_hit'], 'p9': outcome['sl_hit'],
                'p10': outcome['regime'], 'p11': outcome['atr_pct'],
                'p12': outcome['sector'], 'p13': outcome['vix_close'],
                'p14': outcome['scan_price'], 'p15': outcome['exit_price'],
            })

    def backfill_from_historical(self) -> int:
        """Backfill outcomes from backfill_signal_outcomes for historical calibration.

        Uses the large historical dataset (51K signals) to bootstrap the
        outcome tracker with predicted vs actual data. This gives the
        calibrator enough data to compute meaningful confidence scores.

        Returns number of outcomes inserted.
        """
        with get_session() as session:
            # Check how many we already have
            existing = session.execute(text("SELECT COUNT(*) FROM discovery_outcomes")).fetchone()[0]
            if existing > 1000:
                logger.info("OutcomeTracker: already have %d outcomes, skip backfill", existing)
                return 0

            # Pull from backfill_signal_outcomes with kernel-style features
            # We don't have predicted_er for historical, but we can reconstruct regime from VIX
            rows = session.execute(text("""
                SELECT scan_date, symbol, outcome_3d, outcome_5d,
                       outcome_max_gain_5d, outcome_max_dd_5d,
                       atr_pct, vix_at_signal, sector
                FROM backfill_signal_outcomes
                WHERE outcome_3d IS NOT NULL
                ORDER BY scan_date DESC
                LIMIT 5000
            """)).fetchall()

        if not rows:
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

            # v6.0: TP/SL matching production config (1.0×ATR uniform, SL regime-adaptive)
            atr_val = atr or 2.0
            tp_pct = max(0.5, 1.0 * atr_val)
            sl_mult = {'BULL': 2.0, 'STRESS': 1.5, 'CRISIS': 1.0}.get(regime, 1.5)
            sl_pct = max(1.5, min(5.0, sl_mult * atr_val))

            tp_hit = 1 if (mg or 0) >= tp_pct else 0
            sl_hit = 1 if (mdd or 0) <= -sl_pct else 0

            try:
                session.execute(text("""
                    INSERT OR IGNORE INTO discovery_outcomes
                    (scan_date, symbol, predicted_er, predicted_wr,
                     actual_return_d3, actual_return_d5, max_gain, max_dd,
                     tp_hit, sl_hit, regime, atr_pct, sector, vix_close,
                     scan_price, exit_price)
                    VALUES (:p0, :p1, NULL, NULL, :p2, :p3, :p4, :p5, :p6, :p7, :p8, :p9, :p10, :p11, NULL, NULL)
                """), {'p0': scan_date, 'p1': symbol, 'p2': o3d, 'p3': o5d, 'p4': mg, 'p5': mdd,
                       'p6': tp_hit, 'p7': sl_hit, 'p8': regime, 'p9': atr, 'p10': sector, 'p11': vix})
                inserted += 1
            except Exception:
                pass
        logger.info("OutcomeTracker: backfilled %d historical outcomes", inserted)
        return inserted
