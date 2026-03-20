"""
Discovery Self-Calibrator — computes rolling accuracy and confidence scores.

Reads discovery_outcomes and computes:
1. Rolling prediction accuracy: correlation(predicted_er, actual_return)
2. Rolling WR accuracy: TP hit rate vs predicted
3. Regime accuracy: WR by regime
4. Overall confidence score (0-100%) that reflects current system reliability

This is NOT parameter tuning. It's a diagnostic that tells us:
- Is the kernel's E[R] actually predictive right now?
- Which regimes are we accurate in?
- Has something drifted (new market condition the kernel hasn't seen)?
"""
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


class Calibrator:
    """Compute rolling accuracy and confidence from outcome data."""

    def __init__(self):
        self._cache: Optional[dict] = None
        self._cache_time: float = 0

    def compute_confidence(self, window_days: int = 30) -> dict:
        """Compute overall confidence score and diagnostic breakdown.

        Returns dict with:
        - confidence: 0-100 overall score
        - er_correlation: Spearman rank corr of predicted E[R] vs actual
        - directional_accuracy: % of picks where sign(predicted) == sign(actual)
        - win_rate: actual TP hit rate in window
        - by_regime: {BULL: {...}, STRESS: {...}, CRISIS: {...}}
        - n_outcomes: number of outcomes in window
        - rolling_7d, rolling_14d, rolling_30d: WR at different windows
        """
        import time
        now = time.monotonic()
        if self._cache and (now - self._cache_time) < 300:  # 5-min cache
            return self._cache

        result = self._compute_inner(window_days)
        self._cache = result
        self._cache_time = now
        return result

    def _compute_inner(self, window_days: int) -> dict:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Get recent outcomes
        cutoff = (datetime.now() - timedelta(days=window_days)).strftime('%Y-%m-%d')
        rows = conn.execute("""
            SELECT scan_date, symbol, predicted_er, actual_return_d3,
                   actual_return_d5, max_gain, max_dd, tp_hit, sl_hit,
                   regime, atr_pct, sector, vix_close
            FROM discovery_outcomes
            WHERE scan_date >= ?
            ORDER BY scan_date DESC
        """, (cutoff,)).fetchall()

        # Also get rolling windows (7d, 14d)
        cutoff_7d = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        cutoff_14d = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')

        rows_7d = [r for r in rows if r['scan_date'] >= cutoff_7d]
        rows_14d = [r for r in rows if r['scan_date'] >= cutoff_14d]

        # All-time stats for context
        all_rows = conn.execute("""
            SELECT COUNT(*) as n,
                   AVG(CASE WHEN tp_hit = 1 THEN 1.0 ELSE 0.0 END) as tp_rate,
                   AVG(actual_return_d3) as avg_ret
            FROM discovery_outcomes
        """).fetchone()

        conn.close()

        if not rows:
            return {
                'confidence': 50,  # neutral when no data
                'er_correlation': None,
                'directional_accuracy': None,
                'win_rate': None,
                'n_outcomes': 0,
                'rolling_7d': self._compute_window_stats(rows_7d),
                'rolling_14d': self._compute_window_stats(rows_14d),
                'rolling_30d': self._compute_window_stats(rows),
                'by_regime': {},
                'all_time': {
                    'n': all_rows['n'] or 0,
                    'tp_rate': round((all_rows['tp_rate'] or 0) * 100, 1),
                    'avg_ret': round(all_rows['avg_ret'] or 0, 3),
                },
            }

        # 1. E[R] correlation (rank correlation, robust to outliers)
        er_corr = self._compute_er_correlation(rows)

        # 2. Directional accuracy: did we get the sign right?
        dir_acc = self._compute_directional_accuracy(rows)

        # 3. Win rate (TP hit rate)
        tp_hits = sum(1 for r in rows if r['tp_hit'])
        sl_hits = sum(1 for r in rows if r['sl_hit'])
        n = len(rows)
        win_rate = tp_hits / n * 100 if n > 0 else 0

        # 4. By regime
        by_regime = self._compute_regime_stats(rows)

        # 5. Compute confidence score (0-100)
        confidence = self._compute_confidence_score(
            er_corr, dir_acc, win_rate, n, by_regime
        )

        return {
            'confidence': confidence,
            'er_correlation': er_corr,
            'directional_accuracy': round(dir_acc, 1) if dir_acc is not None else None,
            'win_rate': round(win_rate, 1),
            'tp_hits': tp_hits,
            'sl_hits': sl_hits,
            'n_outcomes': n,
            'rolling_7d': self._compute_window_stats(rows_7d),
            'rolling_14d': self._compute_window_stats(rows_14d),
            'rolling_30d': self._compute_window_stats(rows),
            'by_regime': by_regime,
            'all_time': {
                'n': all_rows['n'] or 0,
                'tp_rate': round((all_rows['tp_rate'] or 0) * 100, 1),
                'avg_ret': round(all_rows['avg_ret'] or 0, 3),
            },
        }

    def _compute_er_correlation(self, rows: list) -> Optional[float]:
        """Spearman rank correlation between predicted E[R] and actual return."""
        pairs = [(r['predicted_er'], r['actual_return_d3'])
                 for r in rows
                 if r['predicted_er'] is not None and r['actual_return_d3'] is not None]

        if len(pairs) < 10:
            return None

        predicted = np.array([p[0] for p in pairs])
        actual = np.array([p[1] for p in pairs])

        # Spearman rank correlation (more robust than Pearson for E[R])
        from scipy.stats import spearmanr
        corr, p_value = spearmanr(predicted, actual)

        if np.isnan(corr):
            return None

        return round(float(corr), 3)

    def _compute_directional_accuracy(self, rows: list) -> Optional[float]:
        """% of picks where sign(predicted_er) matches sign(actual_return)."""
        pairs = [(r['predicted_er'], r['actual_return_d3'])
                 for r in rows
                 if r['predicted_er'] is not None and r['actual_return_d3'] is not None]

        if len(pairs) < 5:
            return None

        correct = sum(1 for pred, act in pairs
                      if (pred > 0 and act > 0) or (pred <= 0 and act <= 0))
        return correct / len(pairs) * 100

    def _compute_regime_stats(self, rows: list) -> dict:
        """WR and avg return by regime."""
        regimes = {}
        for r in rows:
            regime = r['regime'] or 'UNKNOWN'
            if regime not in regimes:
                regimes[regime] = {'n': 0, 'tp': 0, 'sl': 0, 'returns': []}
            regimes[regime]['n'] += 1
            if r['tp_hit']:
                regimes[regime]['tp'] += 1
            if r['sl_hit']:
                regimes[regime]['sl'] += 1
            if r['actual_return_d3'] is not None:
                regimes[regime]['returns'].append(r['actual_return_d3'])

        result = {}
        for regime, data in regimes.items():
            n = data['n']
            avg_ret = float(np.mean(data['returns'])) if data['returns'] else 0
            result[regime] = {
                'n': n,
                'win_rate': round(data['tp'] / n * 100, 1) if n > 0 else 0,
                'sl_rate': round(data['sl'] / n * 100, 1) if n > 0 else 0,
                'avg_return': round(avg_ret, 3),
            }
        return result

    def _compute_window_stats(self, rows: list) -> dict:
        """Compute basic stats for a time window."""
        if not rows:
            return {'n': 0, 'win_rate': None, 'avg_return': None}

        n = len(rows)
        tp = sum(1 for r in rows if r['tp_hit'])
        returns = [r['actual_return_d3'] for r in rows if r['actual_return_d3'] is not None]
        avg_ret = float(np.mean(returns)) if returns else None

        return {
            'n': n,
            'win_rate': round(tp / n * 100, 1) if n > 0 else None,
            'avg_return': round(avg_ret, 3) if avg_ret is not None else None,
        }

    def _compute_confidence_score(self, er_corr: Optional[float],
                                   dir_acc: Optional[float],
                                   win_rate: float,
                                   n: int,
                                   by_regime: dict) -> int:
        """Compute confidence 0-100 from multiple signals.

        Components (weighted):
        - E[R] correlation: 30% weight (is ranking predictive?)
        - Directional accuracy: 20% weight (are we getting the sign right?)
        - Win rate: 30% weight (are we making money?)
        - Sample size: 20% weight (do we have enough data?)

        Baseline: 50 = neutral (no data or perfectly random).
        """
        score = 50.0  # start neutral

        # E[R] correlation contribution (±15 points)
        if er_corr is not None:
            # corr of 0.3+ is excellent for finance, -0.1 is bad
            corr_score = np.clip(er_corr * 50, -15, 15)
            score += corr_score

        # Directional accuracy contribution (±10 points)
        if dir_acc is not None:
            # 60% = good, 50% = random, 40% = anti-predictive
            dir_score = (dir_acc - 50) * 0.5  # maps 40-60% to -5..+5
            score += np.clip(dir_score, -10, 10)

        # Win rate contribution (±15 points)
        if n >= 5:
            # 60% = good, 50% = breakeven, 40% = bad
            wr_score = (win_rate - 50) * 0.5
            score += np.clip(wr_score, -15, 15)

        # Sample size contribution (0-10 points)
        # More data = more confidence in the above signals
        n_score = min(10, n / 5)  # maxes at n=50
        score += n_score

        return int(np.clip(score, 0, 100))

    def get_regime_recommendation(self) -> dict:
        """Based on recent accuracy, recommend regime confidence adjustments.

        Returns per-regime recommendations:
        - confidence_mult: 0.5-1.5 multiplier for pick count
        - reason: why this adjustment
        """
        stats = self.compute_confidence()
        by_regime = stats.get('by_regime', {})

        recommendations = {}
        for regime, data in by_regime.items():
            n = data['n']
            if n < 5:
                recommendations[regime] = {
                    'confidence_mult': 1.0,
                    'reason': f'Insufficient data (n={n})',
                }
                continue

            wr = data['win_rate']
            if wr >= 60:
                mult = 1.2
                reason = f'Strong WR={wr}%'
            elif wr >= 50:
                mult = 1.0
                reason = f'Adequate WR={wr}%'
            elif wr >= 40:
                mult = 0.7
                reason = f'Below breakeven WR={wr}%'
            else:
                mult = 0.5
                reason = f'Poor WR={wr}%, reduce exposure'

            recommendations[regime] = {
                'confidence_mult': mult,
                'reason': reason,
            }

        return recommendations
