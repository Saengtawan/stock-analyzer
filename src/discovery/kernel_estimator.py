"""
Discovery v3 — Gaussian Kernel Regression E[R] Estimator.

Replaces the v2 IC-weighted composite scorer with a data-driven
kernel regression that estimates Expected Return E[R] for each candidate.

Features (5):
  - distance_from_20d_high
  - atr_pct
  - volume_ratio
  - momentum_20d
  - atr_risk (= atr_pct * vix / 20)

Training data: backfill_signal_outcomes + signal_outcomes (expanding window).
"""
import logging
import math
import sqlite3
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'

FEATURES = [
    'distance_from_20d_high',
    'atr_pct',
    'volume_ratio',
    'momentum_20d',
    'atr_risk',
]


class KernelEstimator:
    """Gaussian Kernel Regression for estimating E[R] (expected 5-day return)."""

    def __init__(self, bandwidth: float = 1.0, min_train_dates: int = 20):
        self.bw = bandwidth
        self.min_train_dates = min_train_dates

        # Training state
        self.train_features: np.ndarray = np.array([])
        self.train_returns: np.ndarray = np.array([])
        self.feature_means: np.ndarray = np.zeros(len(FEATURES))
        self.feature_stds: np.ndarray = np.ones(len(FEATURES))
        self.n_rows = 0
        self.n_dates = 0
        self.date_range = ('', '')
        self._fitted = False

    def load_and_fit(self) -> bool:
        """Load training data from DB and fit the model. Returns True if successful."""
        rows = self._load_training_data()
        if not rows:
            logger.warning("KernelEstimator: no training data available")
            return False

        # Check min dates
        dates = set(r[0] for r in rows)
        if len(dates) < self.min_train_dates:
            logger.warning(f"KernelEstimator: only {len(dates)} dates, need {self.min_train_dates}")
            return False

        # Build feature matrix
        feat_rows = []
        returns = []
        for row in rows:
            # row: (scan_date, outcome_5d, distance_from_20d_high, atr_pct,
            #        volume_ratio, momentum_20d, vix_at_signal)
            scan_date, outcome, dist, atr, vol_ratio, mom20d, vix = row

            if any(v is None for v in [outcome, dist, atr, vol_ratio, mom20d, vix]):
                continue

            atr_risk = atr * vix / 20.0
            feat_rows.append([dist, atr, vol_ratio, mom20d, atr_risk])
            returns.append(outcome)

        if len(feat_rows) < 50:
            logger.warning(f"KernelEstimator: only {len(feat_rows)} valid rows after filtering")
            return False

        self.train_features = np.array(feat_rows, dtype=np.float64)
        self.train_returns = np.array(returns, dtype=np.float64)

        # Z-score normalization
        self.feature_means = self.train_features.mean(axis=0)
        self.feature_stds = self.train_features.std(axis=0)
        self.feature_stds[self.feature_stds == 0] = 1.0
        self.train_features = (self.train_features - self.feature_means) / self.feature_stds

        self.n_rows = len(feat_rows)
        self.n_dates = len(dates)
        sorted_dates = sorted(dates)
        self.date_range = (sorted_dates[0], sorted_dates[-1])
        self._fitted = True

        logger.info(
            f"KernelEstimator: fitted on {self.n_rows} rows, "
            f"{self.n_dates} dates ({self.date_range[0]} to {self.date_range[1]}), "
            f"bw={self.bw}"
        )
        return True

    def estimate(self, candidate: dict) -> tuple[float, float, float]:
        """
        Estimate E[R] for a candidate stock.

        Args:
            candidate: dict with keys matching FEATURES
                       (distance_from_20d_high, atr_pct, volume_ratio,
                        momentum_20d, vix_at_signal or vix_close)

        Returns:
            (er, se, n_eff) — expected return, standard error, effective sample size
        """
        if not self._fitted or len(self.train_features) == 0:
            return 0.0, 10.0, 0.0

        # Extract features
        dist = candidate.get('distance_from_20d_high')
        atr = candidate.get('atr_pct')
        vol_ratio = candidate.get('volume_ratio')
        mom20d = candidate.get('momentum_20d')
        vix = candidate.get('vix_at_signal') or candidate.get('vix_close') or 20.0

        if any(v is None for v in [dist, atr, vol_ratio, mom20d]):
            return 0.0, 10.0, 0.0

        atr_risk = atr * vix / 20.0
        x = np.array([dist, atr, vol_ratio, mom20d, atr_risk], dtype=np.float64)

        # Normalize using training stats
        x_norm = (x - self.feature_means) / self.feature_stds

        # Gaussian kernel weights
        dists = np.sqrt(np.sum((self.train_features - x_norm) ** 2, axis=1))
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)

        total_w = weights.sum()
        if total_w < 1e-10:
            return 0.0, 10.0, 0.0

        # Weighted mean = E[R]
        er = float(np.sum(weights * self.train_returns) / total_w)

        # Effective sample size
        n_eff = float(total_w ** 2 / np.sum(weights ** 2))

        # Weighted SE
        if n_eff > 1:
            residuals = self.train_returns - er
            weighted_var = float(np.sum(weights * residuals ** 2) / total_w)
            se = math.sqrt(weighted_var / n_eff)
        else:
            se = 10.0

        return er, se, n_eff

    def get_stats(self) -> dict:
        """Return training stats for logging/display."""
        return {
            'fitted': self._fitted,
            'n_rows': self.n_rows,
            'n_dates': self.n_dates,
            'date_range': self.date_range,
            'bandwidth': self.bw,
            'global_mean': float(np.mean(self.train_returns)) if self._fitted else None,
        }

    def _load_training_data(self) -> list:
        """Load from backfill_signal_outcomes + signal_outcomes, deduplicated."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            # Union both tables, prefer live (signal_outcomes) over backfill
            rows = conn.execute("""
                WITH combined AS (
                    SELECT scan_date, symbol, outcome_5d,
                           distance_from_20d_high, atr_pct, volume_ratio,
                           momentum_20d, vix_at_signal,
                           1 as priority
                    FROM signal_outcomes
                    WHERE outcome_5d IS NOT NULL
                      AND distance_from_20d_high IS NOT NULL
                      AND atr_pct IS NOT NULL
                      AND volume_ratio IS NOT NULL
                      AND momentum_20d IS NOT NULL
                      AND vix_at_signal IS NOT NULL

                    UNION ALL

                    SELECT scan_date, symbol, outcome_5d,
                           distance_from_20d_high, atr_pct, volume_ratio,
                           momentum_20d, vix_at_signal,
                           2 as priority
                    FROM backfill_signal_outcomes
                    WHERE outcome_5d IS NOT NULL
                      AND distance_from_20d_high IS NOT NULL
                      AND atr_pct IS NOT NULL
                      AND volume_ratio IS NOT NULL
                      AND momentum_20d IS NOT NULL
                      AND vix_at_signal IS NOT NULL
                ),
                deduped AS (
                    SELECT scan_date, outcome_5d,
                           distance_from_20d_high, atr_pct, volume_ratio,
                           momentum_20d, vix_at_signal,
                           ROW_NUMBER() OVER (
                               PARTITION BY scan_date, symbol
                               ORDER BY priority ASC
                           ) as rn
                    FROM combined
                )
                SELECT scan_date, outcome_5d,
                       distance_from_20d_high, atr_pct, volume_ratio,
                       momentum_20d, vix_at_signal
                FROM deduped WHERE rn = 1
                ORDER BY scan_date
            """).fetchall()
            return rows
        except Exception as e:
            logger.error(f"KernelEstimator: DB error loading training data: {e}")
            return []
        finally:
            conn.close()
