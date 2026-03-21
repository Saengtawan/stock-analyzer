"""
Sequence Pattern Matcher — finds similar historical market sequences
and similar stock profiles, predicts what happens next based on past outcomes.
Part of Discovery AI v6.0.
"""
import sqlite3
import logging
import numpy as np
from pathlib import Path
from discovery.temporal import TemporalFeatureBuilder

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'

# Features for per-stock profile matching (from backfill_signal_outcomes)
STOCK_PROFILE_FEATURES = ['atr_pct', 'momentum_5d', 'volume_ratio', 'distance_from_20d_high']

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
        self._stock_profiles_fitted = False
        self._stock_profiles = None

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

    def predict_stock_profile(self, atr: float, mom5: float, vol: float,
                              d20h: float, sector: str = '', top_n: int = 100) -> dict:
        """Find historically similar stock profiles and predict outcome.

        Uses backfill_signal_outcomes to find stocks with similar ATR, momentum,
        volume, distance_from_20d_high. Returns WR and E[R] from those similar stocks.
        This is PER-STOCK, not market-level.
        """
        if not self._stock_profiles_fitted:
            self._fit_stock_profiles()
        if self._stock_profiles is None:
            return {}

        sp = self._stock_profiles
        # Normalize current stock features
        vec = np.array([atr, mom5, vol, d20h], dtype=float)
        vec_norm = (vec - sp['means']) / sp['stds']

        # Kernel-weighted: Gaussian distance in feature space
        diffs = sp['features_norm'] - vec_norm  # (N, 4)
        dist_sq = (diffs ** 2).sum(axis=1)
        weights = np.exp(-dist_sq / (2 * 0.5 ** 2))  # bw=0.5

        # If sector matches, boost weight 1.5x
        if sector:
            sector_match = sp['sectors'] == sector
            weights[sector_match] *= 1.5

        ws = weights.sum()
        if ws < 1e-10:
            return {}
        # neff BEFORE normalization (correct formula: ws² / Σwi²)
        neff = float(ws ** 2 / (weights ** 2).sum())
        weights /= ws

        # Weighted outcomes
        rets = sp['outcomes']
        wr = float((weights * (rets > 0)).sum()) * 100
        er = float((weights * rets).sum())

        # Score: normalize to 0-100 (center at 50)
        # E[R] range typically -5% to +5%, slope=10 per 1%
        score = 50 + er * 10
        score = max(0, min(100, score))

        return {
            'score': round(score, 1),
            'wr': round(wr, 1),
            'er': round(er, 3),
            'neff': round(neff),
            'n_total': len(rets),
        }

    def _fit_stock_profiles(self):
        """Load historical stock profiles from backfill_signal_outcomes."""
        self._stock_profiles_fitted = True
        self._stock_profiles = None

        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                SELECT atr_pct, momentum_5d, volume_ratio, distance_from_20d_high,
                       sector, outcome_5d
                FROM backfill_signal_outcomes
                WHERE outcome_5d IS NOT NULL AND atr_pct > 0
                  AND distance_from_20d_high IS NOT NULL
            """).fetchall()
        finally:
            conn.close()

        if len(rows) < 500:
            logger.warning("StockProfile: insufficient data (%d)", len(rows))
            return

        features = np.array([[r[0], r[1] or 0, r[2] or 1, r[3] or -5] for r in rows], dtype=float)
        means = features.mean(axis=0)
        stds = features.std(axis=0)
        stds[stds == 0] = 1.0
        features_norm = (features - means) / stds

        self._stock_profiles = {
            'features_norm': features_norm,
            'means': means,
            'stds': stds,
            'sectors': np.array([r[4] or '' for r in rows]),
            'outcomes': np.array([r[5] for r in rows], dtype=float),
        }
        logger.info("StockProfile: fitted on %d signals", len(rows))
