"""
Market-Level Signals — non-stock-specific trading opportunities.
Part of Discovery v9.0 Multi-Strategy System.

Data-validated signals:
  1. Sector Contrarian: buy worst 20d sector ETF → WR=58-60%
  2. SPY Drawdown: buy SPY when dd>7% → WR=64%
  3. VIX Spike: buy SPY when VIX spikes >30 → WR=76%
"""
import logging
import sqlite3
from pathlib import Path
from collections import defaultdict

import numpy as np

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


class MarketSignalEngine:
    """Generate market-level trading signals."""

    def __init__(self):
        self._sector_data = None
        self._spy_data = None

    def compute_signals(self, scan_date: str) -> list:
        """Compute all market-level signals for today.

        Returns list of signal dicts, each with:
          type, name, symbol/sector, entry, exit_rule, hold_days,
          wr, er, confidence, rationale
        """
        signals = []

        try:
            signals.extend(self._sector_contrarian(scan_date))
        except Exception as e:
            logger.error("MarketSignals sector error: %s", e)

        try:
            signals.extend(self._spy_drawdown(scan_date))
        except Exception as e:
            logger.error("MarketSignals SPY DD error: %s", e)

        try:
            signals.extend(self._vix_spike(scan_date))
        except Exception as e:
            logger.error("MarketSignals VIX error: %s", e)

        logger.info("MarketSignals: %d signals for %s", len(signals), scan_date)
        return signals

    def _sector_contrarian(self, scan_date: str) -> list:
        """Buy the worst-performing sector over last 20 days.
        WR=58-60%, E[R]=+0.40% (daily frequency).
        """
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                SELECT sector, pct_change, date FROM sector_etf_daily_returns
                WHERE date <= ? AND sector NOT IN ('S&P 500','US Dollar','Treasury Long','Gold')
                ORDER BY date DESC LIMIT 300
            """, (scan_date,)).fetchall()
        finally:
            conn.close()

        if len(rows) < 100:
            return []

        # Group by sector, compute 20d cumulative return
        sector_rets = defaultdict(list)
        for r in rows:
            sector_rets[r[0]].append(r[1] or 0)

        sector_20d = {}
        for sector, rets in sector_rets.items():
            if len(rets) >= 20:
                sector_20d[sector] = sum(rets[:20])  # most recent 20 days

        if not sector_20d:
            return []

        # Find worst and best
        worst = min(sector_20d, key=sector_20d.get)
        best = max(sector_20d, key=sector_20d.get)

        # Sector ETF mapping
        sector_etf = {
            'Technology': 'XLK', 'Healthcare': 'XLV', 'Financial Services': 'XLF',
            'Energy': 'XLE', 'Consumer Cyclical': 'XLY', 'Consumer Defensive': 'XLP',
            'Industrials': 'XLI', 'Utilities': 'XLU', 'Real Estate': 'XLRE',
            'Basic Materials': 'XLB', 'Communication Services': 'XLC',
        }

        signals = []
        etf = sector_etf.get(worst, '')
        if etf:
            signals.append({
                'type': 'SECTOR_CONTRARIAN',
                'name': f'Buy worst sector: {worst}',
                'symbol': etf,
                'sector': worst,
                'entry_rule': 'D1_OPEN',
                'exit_rule': 'FIXED_D5',
                'hold_days': 5,
                'sl_pct': 3.0,
                'sizing': 0.5,
                'wr': 58,
                'er': 0.40,
                'ret_20d': round(sector_20d[worst], 2),
                'rationale': f'{worst} worst 20d sector ({sector_20d[worst]:+.1f}%) → mean reversion WR=58%',
            })

        return signals

    def _spy_drawdown(self, scan_date: str) -> list:
        """Buy SPY when drawdown from 20d high exceeds threshold.
        DD>7%: WR=64%, DD>10%: WR=69%.
        """
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                SELECT spy_close FROM macro_snapshots
                WHERE date <= ? AND spy_close IS NOT NULL
                ORDER BY date DESC LIMIT 25
            """, (scan_date,)).fetchall()
        finally:
            conn.close()

        if len(rows) < 20:
            return []

        prices = [r[0] for r in rows]
        current = prices[0]
        high_20d = max(prices[:20])
        dd_pct = (current / high_20d - 1) * 100

        signals = []
        if dd_pct <= -10:
            signals.append({
                'type': 'SPY_DRAWDOWN',
                'name': f'SPY drawdown {dd_pct:.1f}% (extreme)',
                'symbol': 'SPY',
                'entry_rule': 'D1_OPEN',
                'exit_rule': 'FIXED_D5',
                'hold_days': 5,
                'sl_pct': 5.0,
                'sizing': 1.0,
                'wr': 69,
                'er': 2.08,
                'drawdown': round(dd_pct, 1),
                'rationale': f'SPY {dd_pct:.1f}% from 20d high → bounce WR=69% E[R]=+2.1%',
            })
        elif dd_pct <= -7:
            signals.append({
                'type': 'SPY_DRAWDOWN',
                'name': f'SPY drawdown {dd_pct:.1f}%',
                'symbol': 'SPY',
                'entry_rule': 'D1_OPEN',
                'exit_rule': 'FIXED_D5',
                'hold_days': 5,
                'sl_pct': 4.0,
                'sizing': 0.75,
                'wr': 64,
                'er': 0.94,
                'drawdown': round(dd_pct, 1),
                'rationale': f'SPY {dd_pct:.1f}% from 20d high → bounce WR=64% E[R]=+0.9%',
            })

        return signals

    def _vix_spike(self, scan_date: str) -> list:
        """Buy SPY when VIX spikes above 30.
        VIX>30: WR=76%, VIX>35: WR=83%.
        """
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                SELECT vix_close FROM macro_snapshots
                WHERE date <= ? AND vix_close IS NOT NULL
                ORDER BY date DESC LIMIT 10
            """, (scan_date,)).fetchall()
        finally:
            conn.close()

        if len(rows) < 6:
            return []

        vix_now = rows[0][0]
        vix_5d_ago = rows[5][0] if len(rows) > 5 else vix_now

        signals = []
        # Spike condition: VIX > threshold AND was lower 5 days ago
        if vix_now >= 35 and vix_5d_ago < 32:
            signals.append({
                'type': 'VIX_SPIKE',
                'name': f'VIX extreme spike {vix_now:.0f}',
                'symbol': 'SPY',
                'entry_rule': 'D1_OPEN',
                'exit_rule': 'FIXED_D5',
                'hold_days': 5,
                'sl_pct': 5.0,
                'sizing': 1.0,
                'wr': 83,
                'er': 3.95,
                'vix': round(vix_now, 1),
                'rationale': f'VIX={vix_now:.0f} spike → mean reversion WR=83% E[R]=+4.0%',
            })
        elif vix_now >= 30 and vix_5d_ago < 27:
            signals.append({
                'type': 'VIX_SPIKE',
                'name': f'VIX spike {vix_now:.0f}',
                'symbol': 'SPY',
                'entry_rule': 'D1_OPEN',
                'exit_rule': 'FIXED_D5',
                'hold_days': 5,
                'sl_pct': 4.0,
                'sizing': 0.75,
                'wr': 76,
                'er': 2.36,
                'vix': round(vix_now, 1),
                'rationale': f'VIX={vix_now:.0f} spike → mean reversion WR=76% E[R]=+2.4%',
            })

        return signals

    def get_stats(self) -> dict:
        return {
            'strategies': ['SECTOR_CONTRARIAN', 'SPY_DRAWDOWN', 'VIX_SPIKE'],
        }
