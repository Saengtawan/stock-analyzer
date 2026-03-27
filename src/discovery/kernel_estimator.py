"""
Discovery v5.0 — Regime-Adaptive Dual Kernel E[R] System.

Two kernels working together:
  1. MacroKernel (8 macro features, bw=0.4) — DAY SELECTOR / regime detection
  2. StockKernel (13 features: macro+stock, bw=1.0) — per-stock E[R] RANKER

MacroKernel determines regime from E[R]:
  BULL (>0.5%): aggressive, top 5, SL=3%
  STRESS (-0.5-0.5%): defensive selection, top 3, SL=2%
  CRISIS (<-0.5%): capitulation only, top 2, SL=2%

v5.0 feature expansion (walk-forward validated on 52K signals, 2026-03-19):
  - Added crude_close (IC=-0.155, p<0.0001 — strongest new feature)
  - Added vix_term_spread (IC=+0.101, p=0.005 — VIX backwardation = bounce)
  - Bandwidth 0.6→0.4 (51K data allows tighter local estimation)
  - yield_spread rejected by ablation (+26 PnL when removed = noise)
  Walk-forward: +831% PnL, WR=59.6% (vs v4.5: +439%, WR=58.4%)
"""
import logging
import math

import numpy as np

from database.orm.base import get_session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# All features are macro/breadth — kernel learns market regime
# v5.0: 6→8 features (+crude_close IC=-0.155, +vix_term_spread IC=+0.101)
FEATURES = [
    'new_52w_lows',       # market stress
    'crude_change_5d',    # 5-day crude change
    'pct_above_20d_ma',   # market breadth
    'new_52w_highs',      # market optimism
    'yield_10y',          # rate environment
    'spy_close',          # equity level
    'crude_close',        # v5.0: crude oil level (IC=-0.155, lower=better DIP)
    'vix_term_spread',    # v5.0: VIX - VIX3M (IC=+0.101, backwardation=bounce)
]

# Stock kernel: macro + stock-level features for per-stock E[R]
# v5.0: 11→13 features (macro expanded 6→8, stock unchanged at 5)
STOCK_FEATURES = [
    'new_52w_lows',           # macro
    'crude_change_5d',        # macro: 5-day crude change
    'pct_above_20d_ma',       # macro
    'new_52w_highs',          # macro
    'yield_10y',              # macro
    'spy_close',              # macro
    'crude_close',            # macro: crude oil level (v5.0)
    'vix_term_spread',        # macro: VIX term structure (v5.0)
    'atr_pct',                # stock: volatility
    'momentum_5d',            # stock: recent momentum
    'volume_ratio',           # stock: volume confirmation
    'distance_from_20d_high', # stock: proximity to 20d high (IC=0.521)
    'sector_1d_change',       # stock: sector ETF 1d return
]

# Minimum effective sample size for reliable estimates
MIN_N_EFF = 3.0


class KernelEstimator:
    """Gaussian Kernel Regression for estimating E[R] (expected 5-day return)."""

    def __init__(self, bandwidth: float = 0.6, min_train_dates: int = 20):
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
            # row: (scan_date, outcome_5d, new_52w_lows, crude_change_5d,
            #        pct_above_20d_ma, new_52w_highs, yield_10y, spy_close,
            #        crude_close, vix_term_spread)
            scan_date, outcome, lows, crude, breadth, \
                highs, y10, spy, crude_lvl, vix_spread = row

            if any(v is None for v in [outcome, lows, crude, breadth,
                                        highs, y10, spy, crude_lvl,
                                        vix_spread]):
                continue

            feat_rows.append([lows, crude, breadth, highs, y10, spy,
                              crude_lvl, vix_spread])
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
            f"KernelEstimator v5.0: fitted on {self.n_rows} rows, "
            f"{self.n_dates} dates ({self.date_range[0]} to {self.date_range[1]}), "
            f"bw={self.bw}"
        )
        return True

    def estimate(self, candidate: dict) -> tuple[float, float, float]:
        """
        Estimate E[R] for a candidate stock.

        All features are macro — passed via candidate dict from engine.
        Missing features imputed with training mean (z=0, no information).

        Returns:
            (er, se, n_eff) — expected return, standard error, effective sample size
        """
        if not self._fitted or len(self.train_features) == 0:
            return 0.0, 10.0, 0.0

        vals = []
        for i, feat in enumerate(FEATURES):
            v = candidate.get(feat)
            if v is None:
                v = self.feature_means[i]  # impute with training mean
            vals.append(v)

        x = np.array(vals, dtype=np.float64)

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
        """Load from backfill_signal_outcomes + signal_outcomes, deduplicated.

        JOINs with macro_snapshots + market_breadth for all features.
        Weekend scan_dates mapped to previous Friday.
        Returns rows of: (scan_date, outcome_5d, new_52w_lows, crude_change_5d,
                          pct_above_20d_ma, new_52w_highs, yield_10y, spy_close,
                          crude_close, vix_term_spread)
        """
        try:
            with get_session() as session:
                rows = session.execute(text("""
                    WITH crude_lag AS (
                        SELECT date, crude_close,
                               LAG(crude_close, 5) OVER (ORDER BY date) as crude_5d_ago
                        FROM macro_snapshots
                        WHERE crude_close IS NOT NULL
                    ),
                    combined AS (
                        SELECT scan_date, symbol, outcome_5d,
                               1 as priority
                        FROM signal_outcomes
                        WHERE outcome_5d IS NOT NULL

                        UNION ALL

                        SELECT scan_date, symbol, outcome_5d,
                               2 as priority
                        FROM backfill_signal_outcomes
                        WHERE outcome_5d IS NOT NULL
                    ),
                    deduped AS (
                        SELECT scan_date, symbol, outcome_5d,
                               ROW_NUMBER() OVER (
                                   PARTITION BY scan_date, symbol
                                   ORDER BY priority ASC
                               ) as rn
                        FROM combined
                    ),
                    trading_date AS (
                        SELECT d.scan_date, d.outcome_5d,
                               CASE
                                   WHEN strftime('%w', d.scan_date) = '6'
                                       THEN date(d.scan_date, '-1 day')
                                   WHEN strftime('%w', d.scan_date) = '0'
                                       THEN date(d.scan_date, '-2 days')
                                   ELSE d.scan_date
                               END as macro_date
                        FROM deduped d
                        WHERE d.rn = 1
                    )
                    SELECT t.scan_date, t.outcome_5d,
                           b.new_52w_lows,
                           CASE WHEN cl.crude_5d_ago > 0
                                THEN (cl.crude_close / cl.crude_5d_ago - 1) * 100
                                ELSE NULL END as crude_change_5d,
                           b.pct_above_20d_ma,
                           b.new_52w_highs,
                           m.yield_10y,
                           m.spy_close,
                           m.crude_close,
                           m.vix_close - m.vix3m_close as vix_term_spread
                    FROM trading_date t
                    LEFT JOIN macro_snapshots m ON m.date = t.macro_date
                    LEFT JOIN market_breadth b ON b.date = t.macro_date
                    LEFT JOIN crude_lag cl ON cl.date = t.macro_date
                    ORDER BY t.scan_date
                """)).fetchall()
                return rows
        except Exception as e:
            logger.error(f"KernelEstimator: DB error loading training data: {e}")
            return []


class StockKernelEstimator:
    """13-feature kernel (8 macro + 5 stock) for per-stock E[R] ranking.

    Uses same Gaussian kernel regression but with stock-level features added,
    giving different E[R] per stock. Higher bandwidth (1.0) to handle 13D space.

    v5.0: MacroKernel expanded 6→8 features (+crude_close, +vix_term_spread).
    StockKernel inherits same 8 macro + 5 stock = 13 features.
    Walk-forward: +831% PnL, WR=59.6% (vs v4.5: +439%, WR=58.4%).
    """

    def __init__(self, bandwidth: float = 1.0, min_train_dates: int = 20):
        self.bw = bandwidth
        self.min_train_dates = min_train_dates
        self.train_features: np.ndarray = np.array([])
        self.train_returns: np.ndarray = np.array([])
        self.feature_means: np.ndarray = np.zeros(len(STOCK_FEATURES))
        self.feature_stds: np.ndarray = np.ones(len(STOCK_FEATURES))
        self.n_rows = 0
        self._fitted = False

    def load_and_fit(self) -> bool:
        """Load training data with stock features and fit."""
        rows = self._load_training_data()
        if not rows:
            return False

        dates = set(r[0] for r in rows)
        if len(dates) < self.min_train_dates:
            return False

        feat_rows, returns = [], []
        for row in rows:
            # (scan_date, outcome_5d, lows, crude_change_5d, breadth, highs, y10, spy,
            #  crude_close, vix_term_spread,
            #  atr_pct, momentum_5d, volume_ratio, distance_from_20d_high, sector_1d_change)
            vals = list(row[2:])  # skip scan_date, outcome_5d
            outcome = row[1]
            if any(v is None for v in vals) or outcome is None:
                continue
            feat_rows.append(vals)
            returns.append(outcome)

        if len(feat_rows) < 50:
            return False

        self.train_features = np.array(feat_rows, dtype=np.float64)
        self.train_returns = np.array(returns, dtype=np.float64)
        self.feature_means = self.train_features.mean(axis=0)
        self.feature_stds = self.train_features.std(axis=0)
        self.feature_stds[self.feature_stds == 0] = 1.0
        self.train_features = (self.train_features - self.feature_means) / self.feature_stds
        self.n_rows = len(feat_rows)
        self._fitted = True

        logger.info(
            "StockKernel v5.0: fitted on %d rows, %d dates, bw=%.1f, features=%d",
            self.n_rows, len(dates), self.bw, len(STOCK_FEATURES),
        )
        return True

    def estimate(self, candidate: dict) -> tuple[float, float, float]:
        """Estimate per-stock E[R]. Missing macro features imputed, missing stock → skip."""
        if not self._fitted or len(self.train_features) == 0:
            return 0.0, 10.0, 0.0

        vals = []
        for i, feat in enumerate(STOCK_FEATURES):
            v = candidate.get(feat)
            if v is None:
                if feat in FEATURES:
                    v = self.feature_means[i]  # macro: impute
                else:
                    return 0.0, 10.0, 0.0  # stock feature missing: can't estimate
            vals.append(v)

        x = np.array(vals, dtype=np.float64)
        x_norm = (x - self.feature_means) / self.feature_stds

        dists = np.sqrt(np.sum((self.train_features - x_norm) ** 2, axis=1))
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)
        total_w = weights.sum()
        if total_w < 1e-10:
            return 0.0, 10.0, 0.0

        er = float(np.sum(weights * self.train_returns) / total_w)
        n_eff = float(total_w ** 2 / np.sum(weights ** 2))

        if n_eff > 1:
            residuals = self.train_returns - er
            weighted_var = float(np.sum(weights * residuals ** 2) / total_w)
            se = math.sqrt(weighted_var / n_eff)
        else:
            se = 10.0

        return er, se, n_eff

    def _load_training_data(self) -> list:
        """Load training data with macro + stock features.
        v5.0: 8 macro (6 original + crude_close + vix_term_spread) + 5 stock = 13 features.
        sector_1d_change JOINed from sector_etf_daily_returns.
        """
        try:
            with get_session() as session:
                return session.execute(text("""
                    WITH crude_lag AS (
                        SELECT date, crude_close,
                               LAG(crude_close, 5) OVER (ORDER BY date) as crude_5d_ago
                        FROM macro_snapshots
                        WHERE crude_close IS NOT NULL
                    ),
                    combined AS (
                        SELECT scan_date, symbol, outcome_5d, sector,
                               atr_pct, momentum_5d, volume_ratio,
                               distance_from_20d_high,
                               1 as priority
                        FROM signal_outcomes
                        WHERE outcome_5d IS NOT NULL AND atr_pct IS NOT NULL

                        UNION ALL

                        SELECT scan_date, symbol, outcome_5d, sector,
                               atr_pct, momentum_5d, volume_ratio,
                               distance_from_20d_high,
                               2 as priority
                        FROM backfill_signal_outcomes
                        WHERE outcome_5d IS NOT NULL AND atr_pct IS NOT NULL
                    ),
                    deduped AS (
                        SELECT scan_date, symbol, outcome_5d, sector,
                               atr_pct, momentum_5d, volume_ratio,
                               distance_from_20d_high,
                               ROW_NUMBER() OVER (
                                   PARTITION BY scan_date, symbol ORDER BY priority
                               ) as rn
                        FROM combined
                    ),
                    trading_date AS (
                        SELECT d.*,
                               CASE
                                   WHEN strftime('%w', d.scan_date) = '6'
                                       THEN date(d.scan_date, '-1 day')
                                   WHEN strftime('%w', d.scan_date) = '0'
                                       THEN date(d.scan_date, '-2 days')
                                   ELSE d.scan_date
                               END as macro_date
                        FROM deduped d WHERE d.rn = 1
                    )
                    SELECT t.scan_date, t.outcome_5d,
                           b.new_52w_lows,
                           CASE WHEN cl.crude_5d_ago > 0
                                THEN (cl.crude_close / cl.crude_5d_ago - 1) * 100
                                ELSE NULL END as crude_change_5d,
                           b.pct_above_20d_ma,
                           b.new_52w_highs, m.yield_10y, m.spy_close,
                           m.crude_close,
                           m.vix_close - m.vix3m_close as vix_term_spread,
                           t.atr_pct, t.momentum_5d, t.volume_ratio,
                           t.distance_from_20d_high,
                           ser.pct_change as sector_1d_change
                    FROM trading_date t
                    LEFT JOIN macro_snapshots m ON m.date = t.macro_date
                    LEFT JOIN market_breadth b ON b.date = t.macro_date
                    LEFT JOIN crude_lag cl ON cl.date = t.macro_date
                    LEFT JOIN sector_etf_daily_returns ser
                        ON ser.sector = t.sector AND ser.date = t.macro_date
                    ORDER BY t.scan_date
                """)).fetchall()
        except Exception as e:
            logger.error(f"StockKernel: DB error: {e}")
            return []
