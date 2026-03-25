"""
Strategy Router — selects the best strategy for current market regime.
Part of Discovery AI v8.0 Multi-Strategy Adaptive System.

Three strategies:
  CALM (VIX<18, 51% of time): Index pullback — buy broad market after 2 red days
  NORMAL (VIX 18-25, 33%):    Selective — reduced size, only strong signals
  FEAR (VIX>25, 15%):         Deep dip bounce — existing kernel system

Data validation (51K signals + 1096 trading days):
  CALM:   SPY after 2 red → WR=66%, E[R]=+0.50%
  CALM:   Random SPY 5d → WR=60%
  NORMAL: No strategy has edge → minimal exposure
  FEAR:   Deep dip VIX>25 + d20h<-15 → WR=61%
"""
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


class StrategyRouter:
    """Route to the best strategy based on current VIX regime.
    v17: VIX thresholds learned per sector×regime via AdaptiveParams.
    """

    # Defaults (overridden by adaptive_params when available)
    CALM_VIX = 18.0
    FEAR_VIX = 25.0

    def __init__(self, adaptive_params=None):
        self._adaptive = adaptive_params
        self._last_regime = None
        self._last_strategy = None

    def route(self, macro: dict) -> dict:
        """Determine which strategy to use today.

        Args:
            macro: dict with vix_close, spy_close, pct_above_20d_ma, etc.

        Returns:
            dict with strategy, regime, sizing, rationale
        """
        vix = macro.get('vix_close') or 20
        breadth = macro.get('pct_above_20d_ma') or 50
        spy = macro.get('spy_close') or 500

        # v17: Use learned VIX thresholds if available
        if self._adaptive:
            calm_vix = self._adaptive.get('', 'BULL', 'vix_calm')
            fear_vix = self._adaptive.get('', 'BULL', 'vix_fear')
        else:
            calm_vix = self.CALM_VIX
            fear_vix = self.FEAR_VIX

        # Check SPY pullback (2+ red days)
        spy_pullback = self._check_spy_pullback()

        if vix < calm_vix:
            regime = 'CALM'
            if spy_pullback:
                strategy = 'CALM_PULLBACK'
                sizing = 1.0
                rationale = f'VIX={vix:.0f}<{calm_vix} + SPY pullback → buy dip (WR=66%)'
            else:
                strategy = 'CALM_TREND'
                sizing = 0.5
                rationale = f'VIX={vix:.0f}<{calm_vix}, market calm → trend follow (WR=60%)'

        elif vix < fear_vix:
            regime = 'NORMAL'
            strategy = 'SELECTIVE'
            sizing = 0.25
            rationale = f'VIX={vix:.0f} ({calm_vix}-{fear_vix}) → no clear edge, minimal exposure'

        else:
            regime = 'FEAR'
            # v17: washout breadth threshold learned
            washout_b = 20
            if self._adaptive:
                washout_b = self._adaptive.get('', 'CRISIS', 'washout_breadth')
            if breadth < washout_b:
                strategy = 'WASHOUT'
                sizing = 1.0
                rationale = f'VIX={vix:.0f}>{fear_vix} + breadth={breadth:.0f}<{washout_b} → washout bounce (WR=69%)'
            else:
                strategy = 'DIP_BOUNCE'
                sizing = 0.75
                rationale = f'VIX={vix:.0f}>25 → deep dip bounce (WR=61%)'

        self._last_regime = regime
        self._last_strategy = strategy

        result = {
            'regime': regime,
            'strategy': strategy,
            'sizing': sizing,
            'rationale': rationale,
            'vix': round(vix, 1),
            'breadth': round(breadth, 1),
            'spy_pullback': spy_pullback,
        }

        logger.info(
            "StrategyRouter: %s/%s (size=%.0f%%) VIX=%.1f breadth=%.0f | %s",
            regime, strategy, sizing * 100, vix, breadth, rationale,
        )
        return result

    def get_pick_mode(self, strategy: str) -> dict:
        """How should picks be generated for this strategy?

        Returns:
            dict with mode, max_picks, target, description
        """
        modes = {
            'CALM_PULLBACK': {
                'mode': 'index_and_leaders',
                'max_picks': 5,
                'target': 'Broad market + sector leaders after pullback',
                'tp_ratio': 1.0,  # 1×ATR
                'sl_ratio': 1.5,  # 1.5×ATR
                'prefer_low_atr': True,
                'min_d20h': -10,  # shallow dips OK in calm
            },
            'CALM_TREND': {
                'mode': 'momentum',
                'max_picks': 3,
                'target': 'Stocks near 20d high with momentum',
                'tp_ratio': 1.0,
                'sl_ratio': 1.5,
                'prefer_low_atr': True,
                'min_d20h': -5,  # near high = momentum
            },
            'SELECTIVE': {
                'mode': 'selective',
                'max_picks': 2,
                'target': 'Only strongest signals',
                'tp_ratio': 1.0,
                'sl_ratio': 1.5,
                'prefer_low_atr': True,
                'min_d20h': -15,
            },
            'DIP_BOUNCE': {
                'mode': 'dip_bounce',
                'max_picks': 5,
                'target': 'Deep dip stocks in fear regime',
                'tp_ratio': 1.0,
                'sl_ratio': 1.5,
                'prefer_low_atr': False,  # high ATR OK if deep dip
                'min_d20h': -15,  # deep dips only
            },
            'WASHOUT': {
                'mode': 'washout',
                'max_picks': 5,
                'target': 'Maximum conviction — washout bounce',
                'tp_ratio': 1.25,  # wider TP in washout
                'sl_ratio': 1.0,   # tighter SL
                'prefer_low_atr': False,
                'min_d20h': -20,  # very deep dips
            },
        }
        return modes.get(strategy, modes['SELECTIVE'])

    def _check_spy_pullback(self) -> bool:
        """Check if SPY had 2+ consecutive red days recently."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            rows = conn.execute("""
                SELECT spy_close FROM macro_snapshots
                WHERE spy_close IS NOT NULL
                ORDER BY date DESC LIMIT 3
            """).fetchall()
            conn.close()

            if len(rows) >= 3:
                # rows[0]=today, rows[1]=yesterday, rows[2]=day before
                return rows[0][0] < rows[1][0] and rows[1][0] < rows[2][0]
            return False
        except Exception:
            return False

    def get_stats(self) -> dict:
        return {
            'last_regime': self._last_regime,
            'last_strategy': self._last_strategy,
            'thresholds': {'calm': self.CALM_VIX, 'fear': self.FEAR_VIX},
        }
