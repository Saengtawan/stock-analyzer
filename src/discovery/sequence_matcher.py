"""
Sequence Pattern Matcher — finds similar historical market sequences
and predicts what happens next based on past outcomes.
Part of Discovery AI v6.0.
"""
import sqlite3
import logging
import numpy as np
from pathlib import Path
from discovery.temporal import TemporalFeatureBuilder

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'

# Features used for sequence matching (subset of temporal features)
SEQUENCE_FEATURES = [
    'vix_trend_5d', 'vix_acceleration', 'vix_regime_duration',
    'vix_term_spread_trend', 'breadth_trend_5d',
    'spy_consecutive_red', 'spy_consecutive_green',
    'spy_drawdown_from_20d_high', 'crude_trend_5d',
    'yield_spread_trend', 'vix_current', 'breadth_current',
]


class SequencePatternMatcher:
    """Match current market sequence against historical patterns."""

    def __init__(self):
        self.temporal = TemporalFeatureBuilder()
        self._historical = None  # list of (date, feature_vector, spy_d1, spy_d2, spy_d3)
        self._means = None
        self._stds = None
        self._fitted = False

    def fit(self, lookback_days: int = 730) -> bool:
        """Load historical sequences from DB and precompute feature vectors."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            # Get all dates with SPY data
            rows = conn.execute("""
                SELECT date, spy_close FROM macro_snapshots
                WHERE spy_close IS NOT NULL
                ORDER BY date
            """).fetchall()
        finally:
            conn.close()

        if len(rows) < 100:
            logger.warning("SequenceMatcher: insufficient data (%d rows)", len(rows))
            return False

        dates = [r[0] for r in rows]
        spy = {r[0]: r[1] for r in rows}

        # Build temporal features for each date
        historical = []
        for i, dt in enumerate(dates):
            if i < 30:  # need 30 days history
                continue

            feats = self.temporal.build_features(dt)
            if not feats:
                continue

            # Extract feature vector
            vec = [feats.get(f, 0) for f in SEQUENCE_FEATURES]
            if any(v is None for v in vec):
                continue

            # Compute forward SPY returns (D+1, D+2, D+3)
            spy_now = spy.get(dt, 0)
            if spy_now <= 0:
                continue

            # Find next 1, 2, 3 trading days
            future_dates = [d for d in dates if d > dt]
            if len(future_dates) < 3:
                continue

            spy_d1 = (spy.get(future_dates[0], spy_now) / spy_now - 1) * 100
            spy_d2 = (spy.get(future_dates[1], spy_now) / spy_now - 1) * 100
            spy_d3 = (spy.get(future_dates[2], spy_now) / spy_now - 1) * 100

            historical.append((dt, vec, spy_d1, spy_d2, spy_d3))

        if len(historical) < 50:
            logger.warning("SequenceMatcher: too few sequences (%d)", len(historical))
            return False

        self._historical = historical

        # Normalize features
        all_vecs = np.array([h[1] for h in historical])
        self._means = all_vecs.mean(axis=0)
        self._stds = all_vecs.std(axis=0)
        self._stds[self._stds == 0] = 1.0

        self._fitted = True
        logger.info("SequenceMatcher: fitted on %d sequences (%s to %s)",
                     len(historical), historical[0][0], historical[-1][0])
        return True

    def match(self, current_features: dict, top_n: int = 50) -> list:
        """Find most similar historical sequences to current."""
        if not self._fitted or not self._historical:
            return []

        # Build current feature vector
        vec = np.array([current_features.get(f, 0) for f in SEQUENCE_FEATURES], dtype=float)
        vec_norm = (vec - self._means) / self._stds

        # Compute distances to all historical
        matches = []
        for dt, hist_vec, d1, d2, d3 in self._historical:
            hist_norm = (np.array(hist_vec) - self._means) / self._stds
            dist = np.sqrt(np.sum((vec_norm - hist_norm) ** 2))
            matches.append((dist, dt, d1, d2, d3))

        matches.sort(key=lambda x: x[0])
        return matches[:top_n]

    def predict(self, current_features: dict) -> dict:
        """Predict future market move from similar historical sequences."""
        if not self._fitted:
            return {}

        matches = self.match(current_features, top_n=50)
        if not matches:
            return {}

        d1_rets = [m[2] for m in matches]
        d2_rets = [m[3] for m in matches]
        d3_rets = [m[4] for m in matches]

        d1_arr = np.array(d1_rets)
        d2_arr = np.array(d2_rets)
        d3_arr = np.array(d3_rets)

        # Determine pattern type
        avg_d3 = d3_arr.mean()
        wr_d3 = float(np.mean(d3_arr > 0))

        if avg_d3 > 0.3 and wr_d3 > 0.6:
            pattern = 'BOUNCE'
        elif avg_d3 < -0.3 and wr_d3 < 0.4:
            pattern = 'DECLINE'
        else:
            pattern = 'NEUTRAL'

        # Confidence based on agreement among matches
        confidence = abs(wr_d3 - 0.5) * 200  # 0-100 scale
        confidence = min(100, max(0, confidence))

        # Best timing
        avg_d1 = d1_arr.mean()
        avg_d2 = d2_arr.mean()
        if abs(avg_d1) > abs(avg_d2) and abs(avg_d1) > abs(avg_d3):
            timing = 'D1'
        elif abs(avg_d2) > abs(avg_d3):
            timing = 'D2'
        else:
            timing = 'D3'

        # Closest match dates for context
        closest_dates = [m[1] for m in matches[:5]]

        result = {
            'expected_d1': round(avg_d1, 3),
            'expected_d2': round(avg_d2, 3),
            'expected_d3': round(avg_d3, 3),
            'wr_d3': round(wr_d3 * 100, 1),
            'pattern': pattern,
            'confidence': round(confidence, 0),
            'timing': timing,
            'n_matches': len(matches),
            'closest_dates': closest_dates,
            'avg_distance': round(np.mean([m[0] for m in matches[:10]]), 2),
        }

        logger.info(
            "SequenceMatcher: pattern=%s d3=%+.2f%% wr=%.0f%% conf=%.0f%% timing=%s",
            pattern, avg_d3, wr_d3 * 100, confidence, timing,
        )
        return result
