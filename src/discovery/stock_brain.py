"""
Stock Brain — XGBoost-based per-stock classifier.
Replaces kernel regression with GradientBoosting for WR prediction.
Part of Discovery AI v7.0 Multi-Brain Council.

Walk-forward: trains on past data only, never uses future.
Target: outcome_5d > 0 (binary: will stock go up in 5 days?)
"""
import logging
import sqlite3
import pickle
import time
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'

# v9.0: Stock-only features + interaction terms (no macro — RegimeBrain handles macro)
# Redesigned after testing: macro features dominated (50% importance), stock-only
# with interactions gives WR=55% E[R]=+0.53% on 942 picks (vs macro-dominated 128 picks)
FEATURES = [
    'atr_pct',
    'momentum_5d',
    'distance_from_20d_high',
    'volume_ratio',
    # Interaction terms (data-validated, top features by importance)
    'mom_x_d20h',        # dip depth × momentum (0.146 importance)
    'atr_x_d20h',        # volatility × dip depth
    'vol_x_mom',          # volume confirmation of momentum
    'is_deep_dip',        # mom<-5 AND d20h<-15 (binary)
    'is_momentum',        # mom>3 AND d20h>-5 (binary)
    'dip_relative_atr',   # dip depth / ATR (normalized dip)
]

FEATURE_DEFAULTS = {
    'atr_pct': 3.0,
    'momentum_5d': 0.0,
    'distance_from_20d_high': -5.0,
    'volume_ratio': 1.0,
    'mom_x_d20h': 0.0,
    'atr_x_d20h': 0.0,
    'vol_x_mom': 0.0,
    'is_deep_dip': 0,
    'is_momentum': 0,
    'dip_relative_atr': 0.0,
}


class StockBrain:
    """XGBoost classifier for per-stock win probability."""

    def __init__(self):
        self.model = None
        self._fitted = False
        self._fit_date: Optional[str] = None
        self._n_train = 0
        self._feature_importance: dict = {}
        self._train_wr = 0.0
        self._last_fit_time = 0.0

    def fit(self, max_date: str = None) -> bool:
        """Load training data and fit GradientBoosting model.

        Args:
            max_date: Train on data up to this date (walk-forward).
                      None = use all available data.
        """
        from sklearn.ensemble import GradientBoostingClassifier

        X, y, outcomes = self._load_training_data(max_date)
        if len(X) < 500:
            logger.warning("StockBrain: insufficient data (%d rows)", len(X))
            return False

        self.model = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            min_samples_leaf=50,
            subsample=0.8,
            random_state=42,
        )
        self.model.fit(X, y)

        self._fitted = True
        self._fit_date = max_date or 'all'
        self._n_train = len(X)
        self._train_wr = float(y.mean()) * 100
        self._last_fit_time = time.time()

        # Feature importance
        self._feature_importance = {
            name: round(float(imp), 4)
            for name, imp in zip(FEATURES, self.model.feature_importances_)
        }

        # In-sample accuracy
        y_pred = self.model.predict(X)
        train_acc = float((y_pred == y).mean()) * 100

        logger.info(
            "StockBrain: fitted on %d rows (WR=%.1f%%), train_acc=%.1f%%, top features: %s",
            len(X), self._train_wr, train_acc,
            ', '.join(f'{k}={v:.3f}' for k, v in
                      sorted(self._feature_importance.items(), key=lambda x: -x[1])[:3]),
        )
        return True

    def predict(self, candidate: dict) -> dict:
        """Predict win probability for a stock candidate.

        Returns:
            dict with probability (0-1), predicted_class (0/1), confidence (0-100)
        """
        if not self._fitted or self.model is None:
            # Return below threshold (0.49) so arbiter defaults to SKIP, not TRADE
            return {'probability': 0.49, 'predicted_class': 0, 'confidence': 0}

        x = self._extract_features(candidate)
        prob = float(self.model.predict_proba(x.reshape(1, -1))[0, 1])
        pred_class = 1 if prob >= 0.5 else 0
        confidence = abs(prob - 0.5) * 200  # 0-100 scale

        return {
            'probability': round(prob, 4),
            'predicted_class': pred_class,
            'confidence': round(confidence, 1),
        }

    def predict_batch(self, candidates: list) -> list:
        """Predict for multiple candidates at once (faster)."""
        if not self._fitted or self.model is None:
            return [{'probability': 0.49, 'predicted_class': 0, 'confidence': 0}
                    for _ in candidates]

        X = np.array([self._extract_features(c) for c in candidates])
        probs = self.model.predict_proba(X)[:, 1]

        results = []
        for prob in probs:
            p = float(prob)
            results.append({
                'probability': round(p, 4),
                'predicted_class': 1 if p >= 0.5 else 0,
                'confidence': round(abs(p - 0.5) * 200, 1),
            })
        return results

    def get_feature_importance(self) -> dict:
        return dict(self._feature_importance)

    def get_stats(self) -> dict:
        return {
            'fitted': self._fitted,
            'fit_date': self._fit_date,
            'n_train': self._n_train,
            'train_wr': self._train_wr,
            'features': FEATURES,
            'feature_importance': self._feature_importance,
        }

    def needs_refit(self, days: int = 30) -> bool:
        """Check if model needs refitting (older than N days)."""
        if not self._fitted:
            return True
        return (time.time() - self._last_fit_time) > days * 86400

    def _extract_features(self, candidate: dict) -> np.ndarray:
        """Extract feature vector with interaction terms."""
        atr = float(candidate.get('atr_pct') or 3.0)
        mom = float(candidate.get('momentum_5d') or 0.0)
        d20h = float(candidate.get('distance_from_20d_high') or -5.0)
        vol = float(candidate.get('volume_ratio') or 1.0)

        vals = [
            atr,
            mom,
            d20h,
            vol,
            mom * d20h / 100,                          # interaction
            atr * abs(d20h) / 100,                     # interaction
            vol * abs(mom) / 10,                        # interaction
            1.0 if mom < -5 and d20h < -15 else 0.0,   # deep dip flag
            1.0 if mom > 3 and d20h > -5 else 0.0,     # momentum flag
            abs(d20h) / max(atr, 0.5),                  # normalized dip
        ]
        return np.array(vals, dtype=np.float64)

    def _load_training_data(self, max_date: str = None) -> tuple:
        """Load stock features + compute interactions for training."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            date_filter = f"AND b.scan_date <= '{max_date}'" if max_date else ""
            rows = conn.execute(f"""
                SELECT b.atr_pct, b.momentum_5d, b.distance_from_20d_high,
                       b.volume_ratio,
                       b.outcome_5d
                FROM backfill_signal_outcomes b
                WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0
                {date_filter}
                ORDER BY b.scan_date
            """).fetchall()
        finally:
            conn.close()

        if not rows:
            return np.array([]), np.array([]), np.array([])

        feat_rows = []
        labels = []
        outcomes = []
        for r in rows:
            atr = r[0] if r[0] is not None else 3.0
            mom = r[1] if r[1] is not None else 0.0
            d20h = r[2] if r[2] is not None else -5.0
            vol = r[3] if r[3] is not None else 1.0
            outcome = r[4]
            if outcome is None:
                continue
            # Compute same interaction features as _extract_features
            vals = [
                atr, mom, d20h, vol,
                mom * d20h / 100,
                atr * abs(d20h) / 100,
                vol * abs(mom) / 10,
                1.0 if mom < -5 and d20h < -15 else 0.0,
                1.0 if mom > 3 and d20h > -5 else 0.0,
                abs(d20h) / max(atr, 0.5),
            ]
            feat_rows.append(vals)
            labels.append(1 if outcome > 0 else 0)
            outcomes.append(outcome)

        return (np.array(feat_rows, dtype=np.float64),
                np.array(labels, dtype=np.int32),
                np.array(outcomes, dtype=np.float64))
