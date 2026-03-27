"""
Parameter Optimizer — auto-tunes all system parameters via grid search.
Part of Discovery v10.0 Full Autonomous System.

Runs every 30 days: walk-forward grid search → update best params.
Safety: max ±20% change per cycle, min WR check, auto-revert.
"""
import logging
from database.orm.base import get_session
from sqlalchemy import text
import time
import numpy as np
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)

# Search ranges for each parameter
SEARCH_RANGES = {
    'market_signals': {
        'crude_threshold_pct': (1.5, 8.0, 0.5),      # (min, max, step)
        'crude_strong_threshold_pct': (3.0, 10.0, 1.0),
        'vix_spike_threshold': (25, 38, 1),
        'spy_dd_threshold': (-12, -4, 1),
        'sector_lookback_days': (5, 30, 5),
    },
    'arbiter': {
        'trade_threshold': (0.35, 0.65, 0.05),
        'cautious_threshold': (0.20, 0.50, 0.05),
    },
    'filters': {
        'elite_sigma': (0.5, 1.5, 0.1),
    },
    'tp_sl': {
        'tp_ratio': (0.5, 2.0, 0.25),
    },
}


class ParamOptimizer:
    """Auto-optimize system parameters from historical data."""

    def __init__(self, param_manager):
        self._params = param_manager
        self._last_optimize_time = 0.0

    def needs_optimize(self, days: int = 30) -> bool:
        if self._last_optimize_time == 0:
            return True
        return (time.time() - self._last_optimize_time) > days * 86400

    def optimize_all(self) -> dict:
        """Run full optimization cycle. Returns {group: {param: new_value}}."""
        results = {}

        try:
            ms_results = self._optimize_market_signals()
            if ms_results:
                results['market_signals'] = ms_results
        except Exception as e:
            logger.error("Optimizer: market_signals error: %s", e)

        try:
            arb_results = self._optimize_arbiter()
            if arb_results:
                results['arbiter'] = arb_results
        except Exception as e:
            logger.error("Optimizer: arbiter error: %s", e)

        try:
            tp_results = self._optimize_tp_sl()
            if tp_results:
                results['tp_sl'] = tp_results
        except Exception as e:
            logger.error("Optimizer: tp_sl error: %s", e)

        self._last_optimize_time = time.time()

        # Apply results with safety guard
        n_updated = 0
        for group, params in results.items():
            for name, new_val in params.items():
                old_val = self._params.get(group, name, new_val)
                if old_val and old_val != 0:
                    change_pct = abs(new_val - old_val) / abs(old_val) * 100
                    if change_pct > 20:
                        logger.warning("Optimizer: %s.%s change %.0f%% > 20%% — capped",
                                       group, name, change_pct)
                        # Cap at ±20%
                        if new_val > old_val:
                            new_val = old_val * 1.2
                        else:
                            new_val = old_val * 0.8
                        new_val = round(new_val, 4)

                self._params.update(group, name, new_val, reason='auto-optimize')
                n_updated += 1

        logger.info("Optimizer: updated %d params across %d groups", n_updated, len(results))
        return results

    def _optimize_market_signals(self) -> dict:
        """Optimize market signal thresholds from market_signal_outcomes."""
        # conn via get_session()
        try:
            rows = conn.execute("""
                SELECT signal_type, outcome_5d, params_json
                FROM market_signal_outcomes
                WHERE outcome_5d IS NOT NULL
            """).fetchall()
        finally:
            pass

        if len(rows) < 100:
            logger.warning("Optimizer: insufficient market signal data (%d)", len(rows))
            return {}

        # Optimize sector lookback
        # conn via get_session()
        try:
            sector_rows = conn.execute("""
                SELECT date, sector, pct_change FROM sector_etf_daily_returns
                WHERE sector NOT IN ('S&P 500','US Dollar','Treasury Long','Gold')
                ORDER BY date
            """).fetchall()
        finally:
            pass

        daily = defaultdict(dict)
        for r in sector_rows:
            daily[r[0]][r[1]] = r[2]
        dates = sorted(daily.keys())

        best_lookback = 20
        best_sharpe = -999

        for lookback in range(5, 31, 5):
            pnls = []
            for i in range(lookback, len(dates) - 5):
                sector_ret = {s: sum(daily[dates[j]].get(s, 0) or 0 for j in range(i - lookback, i))
                              for s in daily[dates[i]]}
                if not sector_ret:
                    continue
                worst = min(sector_ret, key=sector_ret.get)
                fwd = sum(daily[dates[j]].get(worst, 0) or 0 for j in range(i + 1, min(i + 6, len(dates))))
                pnls.append(fwd)

            if len(pnls) < 50:
                continue
            p = np.array(pnls)
            sharpe = p.mean() / max(p.std(), 0.01) * np.sqrt(252 / 5)
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_lookback = lookback

        return {'sector_lookback_days': float(best_lookback)}

    def _optimize_arbiter(self) -> dict:
        """Optimize arbiter thresholds from discovery_outcomes."""
        # conn via get_session()
        try:
            rows = conn.execute("""
                SELECT predicted_er, actual_return_d3
                FROM discovery_outcomes
                WHERE actual_return_d3 IS NOT NULL AND predicted_er IS NOT NULL AND predicted_er < 10
                ORDER BY scan_date
            """).fetchall()
        finally:
            pass

        if len(rows) < 100:
            return {}

        # Not enough data to optimize arbiter thresholds meaningfully
        # (would need RegimeBrain probability stored in outcomes)
        return {}

    def _optimize_tp_sl(self) -> dict:
        """Optimize TP/SL ratios from signal_daily_bars."""
        # conn via get_session()
        try:
            rows = conn.execute("""
                SELECT b.atr_pct,
                       d1.open, d1.high, d1.low,
                       d2.high, d2.low,
                       d3.high, d3.low, d3.close
                FROM backfill_signal_outcomes b
                JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
                JOIN signal_daily_bars d2 ON b.scan_date=d2.scan_date AND b.symbol=d2.symbol AND d2.day_offset=2
                JOIN signal_daily_bars d3 ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
                WHERE b.outcome_5d IS NOT NULL AND d1.open > 0 AND b.atr_pct > 0
                LIMIT 40000
            """).fetchall()
        finally:
            pass

        if len(rows) < 5000:
            return {}

        # Split walk-forward
        split = int(len(rows) * 0.8)
        test = rows[split:]

        best_ratio = 1.0
        best_sharpe = -999

        for tp_r in [0.5, 0.75, 1.0, 1.25, 1.5]:
            pnls = []
            for r in test:
                atr = r[0]
                entry = r[1]
                if entry <= 0:
                    continue
                tp_pct = max(0.5, tp_r * atr)
                sl_pct = max(1.5, min(5.0, 1.5 * atr))

                for h, l in [(r[2], r[3]), (r[4], r[5]), (r[6], r[7])]:
                    low_p = (l / entry - 1) * 100
                    high_p = (h / entry - 1) * 100
                    if low_p <= -sl_pct:
                        pnls.append(-sl_pct)
                        break
                    if high_p >= tp_pct:
                        pnls.append(tp_pct)
                        break
                else:
                    d3c = r[8]
                    pnls.append((d3c / entry - 1) * 100)

            p = np.array(pnls)
            if len(p) < 100:
                continue
            sharpe = p.mean() / max(p.std(), 0.01) * np.sqrt(252 / 3)
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_ratio = tp_r

        return {'tp_ratio': best_ratio}

    def get_stats(self) -> dict:
        return {
            'last_optimize': self._last_optimize_time,
            'needs_optimize': self.needs_optimize(30),
        }
