"""
Sensor Network — detects signals from every direction.
Part of Discovery v12.0 Unified Intelligence.

Computes ~20 normalized features per stock combining:
  Macro sensors (5): VIX, crude, breadth, yield, SPY state
  Sector sensors (4): relative strength, leadership, macro alignment, rotation
  Stock sensors (8): speculative, sensitivities, supply chain, earnings, analyst, candle
"""
import logging
from database.orm.base import get_session
from sqlalchemy import text
import json
import numpy as np
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)

# Sector-macro alignment rules
SECTOR_MACRO_RULES = {
    'Energy': {'crude_align': 'positive', 'vix_align': 'neutral'},
    'Financial Services': {'crude_align': 'neutral', 'yield_align': 'positive'},
    'Real Estate': {'yield_align': 'negative', 'vix_align': 'negative'},
    'Utilities': {'vix_align': 'positive', 'yield_align': 'negative'},
    'Technology': {'vix_align': 'negative', 'crude_align': 'negative'},
    'Consumer Cyclical': {'vix_align': 'negative', 'crude_align': 'negative'},
    'Healthcare': {'vix_align': 'neutral', 'crude_align': 'neutral'},
    'Consumer Defensive': {'vix_align': 'positive', 'crude_align': 'neutral'},
    'Industrials': {'crude_align': 'negative', 'vix_align': 'negative'},
    'Basic Materials': {'crude_align': 'mixed', 'vix_align': 'negative'},
    'Communication Services': {'vix_align': 'negative', 'crude_align': 'neutral'},
}


class SensorNetwork:
    """Compute all sensor readings for a stock."""

    def __init__(self):
        self._sector_ranks = {}
        self._sector_rank_date = None

    def compute_all(self, symbol: str, scan_date: str, macro: dict,
                    stock: dict, temporal: dict = None) -> dict:
        """Compute full signal vector for one stock.

        Returns dict of ~20 normalized features ready for ML.
        """
        signals = {}

        # === MACRO SENSORS (5) ===
        signals.update(self._macro_sensors(macro, temporal or {}))

        # === SECTOR SENSORS (4) ===
        sector = stock.get('sector', '')
        signals.update(self._sector_sensors(sector, scan_date, macro))

        # === STOCK SENSORS (8) ===
        signals.update(self._stock_sensors(symbol, stock, macro))

        return signals

    def _macro_sensors(self, macro: dict, temporal: dict) -> dict:
        """5 macro state sensors, each normalized -1 to +1."""
        vix = macro.get('vix_close') or 20
        crude = macro.get('crude_close') or 75
        breadth = macro.get('pct_above_20d_ma') or 50
        y10 = macro.get('yield_10y') or 4

        vix_trend = temporal.get('vix_trend_5d', 0)
        breadth_trend = temporal.get('breadth_trend_5d', 0)
        spy_dd = temporal.get('spy_drawdown_from_20d_high', 0)
        crude_trend = temporal.get('crude_trend_5d', 0)

        # VIX state: -1 (low/calm) to +1 (spike/panic)
        vix_state = min(1, max(-1, (vix - 20) / 15))
        # Adjust for trend: falling VIX = less scary
        vix_state += min(0.3, max(-0.3, -vix_trend * 0.1))

        # Crude state: -1 (crash) to +1 (surge)
        crude_state = min(1, max(-1, (crude - 75) / 25))
        crude_state += min(0.3, max(-0.3, crude_trend * 0.05))

        # Breadth: -1 (crash) to +1 (strong)
        breadth_state = min(1, max(-1, (breadth - 50) / 30))
        breadth_state += min(0.3, max(-0.3, breadth_trend * 0.1))

        # Yield: -1 (low/easing) to +1 (high/tightening)
        yield_state = min(1, max(-1, (y10 - 3.5) / 1.5))

        # SPY: -1 (crashing) to +1 (strong)
        spy_state = min(1, max(-1, -spy_dd / 10))  # dd is negative

        return {
            'sensor_vix': round(vix_state, 3),
            'sensor_crude': round(crude_state, 3),
            'sensor_breadth': round(breadth_state, 3),
            'sensor_yield': round(yield_state, 3),
            'sensor_spy': round(spy_state, 3),
        }

    def _sector_sensors(self, sector: str, scan_date: str, macro: dict) -> dict:
        """4 sector sensors."""
        # Compute sector ranks (cached per date)
        if self._sector_rank_date != scan_date:
            self._compute_sector_ranks(scan_date)

        rank = self._sector_ranks.get(sector, 6)  # 1=best, 11=worst
        is_leading = rank <= 3
        relative_strength = 1 - (rank - 1) / 10  # 1.0=best, 0.0=worst

        # Macro alignment
        alignment = 0
        rules = SECTOR_MACRO_RULES.get(sector, {})
        crude = macro.get('crude_close') or 75
        vix = macro.get('vix_close') or 20
        y10 = macro.get('yield_10y') or 4

        if rules.get('crude_align') == 'positive' and crude > 85:
            alignment += 0.3
        elif rules.get('crude_align') == 'negative' and crude > 85:
            alignment -= 0.3

        if rules.get('vix_align') == 'positive' and vix > 25:
            alignment += 0.3
        elif rules.get('vix_align') == 'negative' and vix > 25:
            alignment -= 0.3

        if rules.get('yield_align') == 'positive' and y10 > 4.5:
            alignment += 0.2
        elif rules.get('yield_align') == 'negative' and y10 > 4.5:
            alignment -= 0.2

        # Rotation: risk-on vs risk-off
        # If defensive sectors (Utilities, Consumer Def, Healthcare) lead → risk-off
        defensive = {'Utilities', 'Consumer Defensive', 'Healthcare'}
        top3 = [s for s, r in sorted(self._sector_ranks.items(), key=lambda x: x[1])[:3]]
        risk_off = sum(1 for s in top3 if s in defensive)
        rotation = -0.5 if risk_off >= 2 else 0.5 if risk_off == 0 else 0

        return {
            'sensor_sector_strength': round(relative_strength, 3),
            'sensor_sector_leading': 1.0 if is_leading else 0.0,
            'sensor_sector_aligned': round(min(1, max(-1, alignment)), 3),
            'sensor_rotation': round(rotation, 3),
        }

    def _stock_sensors(self, symbol: str, stock: dict, macro: dict) -> dict:
        """8 stock-level sensors."""
        # conn via get_session()
        try:
            # Speculative flag
            r = conn.execute("""
                SELECT score FROM stock_context
                WHERE symbol=? AND context_type='SPECULATIVE_FLAG'
            """, (symbol,)).fetchone()
            spec_score = r[0] if r else 0

            # Crude sensitivity
            r = conn.execute("""
                SELECT score FROM stock_context
                WHERE symbol=? AND context_type='CRUDE_SENSITIVE'
            """, (symbol,)).fetchone()
            crude_sens = r[0] if r else 0

            # VIX sensitivity
            r = conn.execute("""
                SELECT score FROM stock_context
                WHERE symbol=? AND context_type='VIX_SENSITIVE'
            """, (symbol,)).fetchone()
            vix_sens = r[0] if r else 0

            # Supply chain risk
            n_upstream = conn.execute("""
                SELECT COUNT(*) FROM stock_relationships
                WHERE symbol_to=? AND relationship_type='SUPPLY_CHAIN'
            """, (symbol,)).fetchone()[0]
            supply_risk = min(1, n_upstream / 5)  # normalize

            # Analyst signal
            r = conn.execute("""
                SELECT upside_pct, bull_score FROM analyst_consensus WHERE symbol=?
            """, (symbol,)).fetchone()
            if r and r[0] is not None:
                analyst = min(1, max(-1, r[0] / 30))  # normalize upside to -1..+1
            else:
                analyst = 0

            # Insider signal
            r = conn.execute("""
                SELECT COUNT(*) FROM insider_transactions
                WHERE symbol=? AND transaction_type='purchase'
                AND transaction_date >= date('now', '-30 days')
            """, (symbol,)).fetchone()
            insider = min(1, (r[0] or 0) / 3)  # 3+ buys = max signal

        finally:
            pass

        # D0 candle signal (from stock features)
        d0_lower = stock.get('d0_lower_shadow', 0)
        candle = 0.5 if d0_lower > 0.5 else 0  # hammer = positive signal

        # Earnings proximity
        dte = stock.get('days_to_earnings')
        earnings_risk = -0.5 if dte is not None and 0 <= dte <= 3 else 0

        return {
            'sensor_speculative': round(spec_score, 3),
            'sensor_crude_sens': round(crude_sens, 3),
            'sensor_vix_sens': round(vix_sens, 3),
            'sensor_supply_risk': round(supply_risk, 3),
            'sensor_analyst': round(analyst, 3),
            'sensor_insider': round(insider, 3),
            'sensor_candle': round(candle, 3),
            'sensor_earnings_risk': round(earnings_risk, 3),
        }

    def _compute_sector_ranks(self, scan_date: str):
        """Rank sectors by 10d return."""
        # conn via get_session()
        try:
            rows = conn.execute("""
                SELECT sector, SUM(pct_change) as ret_10d
                FROM sector_etf_daily_returns
                WHERE date <= ? AND date >= date(?, '-14 days')
                AND sector NOT IN ('S&P 500','US Dollar','Treasury Long','Gold')
                GROUP BY sector ORDER BY ret_10d DESC
            """, (scan_date, scan_date)).fetchall()
        finally:
            pass

        self._sector_ranks = {r[0]: i + 1 for i, r in enumerate(rows)}
        self._sector_rank_date = scan_date
