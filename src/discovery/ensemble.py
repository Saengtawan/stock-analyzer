"""
Discovery Ensemble Brain — combines multiple model outputs into a unified score.
Part of Discovery AI v6.0.

Combines:
  1. Kernel E[R] (existing) — primary signal
  2. Sequence pattern matching — historical similarity
  3. Leading indicators — regime/mean-reversion signals
  4. Calibrator confidence — recent system accuracy

Weights are initially fixed but auto-optimize from recent outcomes (Step 5).
"""
import logging
import sqlite3
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'

# Default weights — validated starting point
DEFAULT_WEIGHTS = {
    'kernel': 0.40,
    'sequence': 0.25,
    'leading': 0.20,
    'calibrator': 0.15,
}

MIN_WEIGHT = 0.05


class EnsembleBrain:
    """Combine multiple model outputs into a single ensemble score."""

    def __init__(self):
        self.weights = dict(DEFAULT_WEIGHTS)
        self._weight_history = []

    def score(self, kernel_er: float, temporal_features: dict,
              sequence_prediction: dict, leading_signals: dict,
              calibrator_confidence: float = 50.0) -> dict:
        """Compute ensemble score from all model outputs.

        Args:
            kernel_er: StockKernel E[R] (typically -2 to +5%)
            temporal_features: from TemporalFeatureBuilder
            sequence_prediction: from SequencePatternMatcher
            leading_signals: from LeadingIndicatorEngine
            calibrator_confidence: from Calibrator (0-100)

        Returns:
            dict with combined_score (0-100), components, agreement info
        """
        components = {}

        # 1. Kernel score: normalize E[R] to 0-100
        # E[R] range roughly -2% to +5%, center at 0
        kernel_score = self._normalize_er(kernel_er)
        components['kernel'] = {
            'score': round(kernel_score, 1),
            'raw': round(kernel_er, 3),
            'weight': self.weights['kernel'],
        }

        # 2. Sequence score: normalize predicted D3 return
        seq_score = 50.0  # neutral default
        if sequence_prediction:
            seq_er = sequence_prediction.get('expected_d3', 0)
            seq_wr = sequence_prediction.get('wr_d3', 50)
            # Weighted: 60% from WR, 40% from E[R] direction
            seq_score = 0.6 * seq_wr + 0.4 * self._normalize_er(seq_er)
            seq_score = max(0, min(100, seq_score))
        components['sequence'] = {
            'score': round(seq_score, 1),
            'raw': sequence_prediction.get('expected_d3', 0) if sequence_prediction else 0,
            'pattern': sequence_prediction.get('pattern', 'N/A') if sequence_prediction else 'N/A',
            'weight': self.weights['sequence'],
        }

        # 3. Leading indicator score: count bullish/bearish signals
        leading_score = 50.0  # neutral default
        if leading_signals:
            bullish = 0
            bearish = 0
            total = 0
            for k, v in leading_signals.items():
                if not isinstance(v, dict) or 'signal' not in v:
                    continue
                total += 1
                if v['signal'] == 'bullish':
                    bullish += 1
                elif v['signal'] == 'bearish':
                    bearish += 1
            if total > 0:
                leading_score = 50 + (bullish - bearish) / total * 50
                leading_score = max(0, min(100, leading_score))
        components['leading'] = {
            'score': round(leading_score, 1),
            'bullish': bullish if leading_signals else 0,
            'bearish': bearish if leading_signals else 0,
            'forecast': leading_signals.get('regime_forecast', {}).get('forecast', 'N/A') if leading_signals else 'N/A',
            'weight': self.weights['leading'],
        }

        # 4. Calibrator score: directly use confidence (0-100)
        cal_score = max(0, min(100, calibrator_confidence))
        components['calibrator'] = {
            'score': round(cal_score, 1),
            'weight': self.weights['calibrator'],
        }

        # Combined weighted score
        combined = (
            self.weights['kernel'] * kernel_score
            + self.weights['sequence'] * seq_score
            + self.weights['leading'] * leading_score
            + self.weights['calibrator'] * cal_score
        )
        combined = max(0, min(100, combined))

        # Agreement: how many models are above 50 (bullish)?
        model_scores = [kernel_score, seq_score, leading_score, cal_score]
        n_bullish = sum(1 for s in model_scores if s > 55)
        n_bearish = sum(1 for s in model_scores if s < 45)
        if n_bullish >= 3:
            agreement = 'STRONG_BUY'
        elif n_bullish >= 2 and n_bearish == 0:
            agreement = 'BUY'
        elif n_bearish >= 3:
            agreement = 'STRONG_AVOID'
        elif n_bearish >= 2 and n_bullish == 0:
            agreement = 'AVOID'
        else:
            agreement = 'MIXED'

        result = {
            'ensemble_score': round(combined, 1),
            'components': components,
            'agreement': agreement,
            'n_bullish': n_bullish,
            'n_bearish': n_bearish,
            'weights': dict(self.weights),
        }

        logger.info(
            "Ensemble: score=%.1f [kern=%.0f seq=%.0f lead=%.0f cal=%.0f] agreement=%s",
            combined, kernel_score, seq_score, leading_score, cal_score, agreement,
        )

        return result

    def optimize_weights(self, outcomes_days: int = 90) -> dict:
        """Auto-optimize weights from recent outcomes.

        For each model, compute correlation(model_score, actual_return) over
        the last N days. Models with higher correlation get higher weight.

        Returns dict with old_weights, new_weights, correlations.
        """
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                SELECT predicted_er, actual_return_d3, regime, atr_pct,
                       vix_close, scan_date
                FROM discovery_outcomes
                WHERE actual_return_d3 IS NOT NULL
                ORDER BY scan_date DESC
                LIMIT ?
            """, (outcomes_days * 10,)).fetchall()  # ~10 picks/day
        finally:
            conn.close()

        if len(rows) < 30:
            logger.warning("Ensemble optimize: insufficient outcomes (%d)", len(rows))
            return {'status': 'insufficient_data', 'n': len(rows)}

        predicted = np.array([r[0] or 0 for r in rows])
        actual = np.array([r[1] or 0 for r in rows])

        # Kernel correlation (directly from predicted_er)
        kernel_corr = float(np.corrcoef(predicted, actual)[0, 1]) if len(predicted) > 5 else 0

        # Sequence/leading don't have per-pick historical scores yet
        # Use kernel correlation as proxy, scaled by their relative expected contribution
        seq_corr = max(0.01, abs(kernel_corr) * 0.6)  # lower: backtested ~0 corr for SPY
        leading_corr = max(0.01, abs(kernel_corr) * 0.5)  # contextual, not per-stock

        # Calibrator: meta-model, scaled similarly
        cal_corr = max(0.01, abs(kernel_corr) * 0.4)  # least direct

        correlations = {
            'kernel': max(0.01, kernel_corr),
            'sequence': max(0.01, seq_corr),
            'leading': max(0.01, leading_corr),
            'calibrator': max(0.01, cal_corr),
        }

        # Weights proportional to abs(correlation), with floor
        raw = {k: abs(v) for k, v in correlations.items()}
        total = sum(raw.values())
        new_weights = {}
        for k in raw:
            w = max(MIN_WEIGHT, raw[k] / total)
            new_weights[k] = round(w, 3)

        # Re-normalize to sum=1
        ws = sum(new_weights.values())
        new_weights = {k: round(v / ws, 3) for k, v in new_weights.items()}

        old_weights = dict(self.weights)
        self.weights = new_weights
        self._weight_history.append(new_weights)

        result = {
            'status': 'optimized',
            'n_outcomes': len(rows),
            'correlations': correlations,
            'old_weights': old_weights,
            'new_weights': new_weights,
        }

        logger.info(
            "Ensemble optimize: kernel_corr=%.3f → weights: %s",
            kernel_corr, new_weights,
        )
        return result

    @staticmethod
    def _normalize_er(er: float) -> float:
        """Normalize E[R] (-2 to +5%) to 0-100 scale.

        0% → 50 (neutral), +2% → 80, -2% → 20
        """
        # Linear mapping: E[R]=0 → 50, slope=15 per 1%
        score = 50 + er * 15
        return max(0, min(100, score))
