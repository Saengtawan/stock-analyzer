"""
Discovery Engine — background scanner for high-confidence stock picks.
Display-only, does NOT execute trades. Does NOT interfere with Rapid Trader.

Scan: daily at 20:00 ET (after market close)
Price refresh: every 5 min during market hours
Storage: discovery_picks table in trade_history.db
"""
import sqlite3
import logging
import json
import math
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional

try:
    from loguru import logger as _loguru
    # Bridge standard logging → loguru so Discovery logs appear in web_app.log
    class _InterceptHandler(logging.Handler):
        def emit(self, record):
            _loguru.opt(depth=6, exception=record.exc_info).log(record.levelname, record.getMessage())
    logging.getLogger('discovery').addHandler(_InterceptHandler())
    logging.getLogger('discovery').setLevel(logging.DEBUG)
except ImportError:
    pass

import numpy as np
import pandas as pd
import yaml

from discovery.models import DiscoveryPick
from discovery.scorer import DiscoveryScorer
from discovery.kernel_estimator import KernelEstimator, StockKernelEstimator
from discovery.outcome_tracker import OutcomeTracker
from discovery.calibrator import Calibrator
from discovery.temporal import TemporalFeatureBuilder
from discovery.sequence_matcher import SequencePatternMatcher
from discovery.leading_indicators import LeadingIndicatorEngine
from discovery.ensemble import EnsembleBrain

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'
CONFIG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'discovery.yaml'


class DiscoveryEngine:
    """Scans universe for high-confidence, low-risk stock picks."""

    def __init__(self):
        self.scorer = DiscoveryScorer()
        self._picks: list[DiscoveryPick] = []
        self._last_scan: Optional[str] = None
        self._last_price_refresh: float = 0.0
        self._scan_progress: dict = {}  # live progress for UI polling
        self._last_validation: Optional[str] = None
        self._last_intraday_scan: Optional[str] = None
        self._current_regime: Optional[str] = None
        self._smart_tp_coeffs: Optional[dict] = None  # v5.2: auto-fitted TP coefficients
        self._hold_data: Optional[dict] = None  # v5.2: hold kernel data for P(TP) timeline
        self._advice_thresholds: dict = {'risky': 1.0, 'caution': 1.2}  # safe_ratio thresholds (legacy)
        self._advice_er_thresholds: dict = {'buy': 0.3, 'hold': 0.05, 'caution': -0.1}  # auto-learned each scan
        self._outcome_tracker = OutcomeTracker()
        self._calibrator = Calibrator()
        # v6.0: Ensemble components
        self._temporal = TemporalFeatureBuilder()
        self._sequence_matcher = SequencePatternMatcher()
        self._leading_indicators = LeadingIndicatorEngine()
        self._ensemble = EnsembleBrain()
        self._v6_fitted = False
        self._temporal_features: dict = {}
        self._sequence_prediction: dict = {}
        self._leading_signals: dict = {}
        self._ensure_table()
        self._load_picks_from_db()

        with open(CONFIG_PATH) as f:
            self._config = yaml.safe_load(f)['discovery']

        # v3: Initialize kernel estimators (retries on each scan if init fails)
        v3_cfg = self._config.get('v3', {})
        self._v3_config_enabled = v3_cfg.get('enabled', False)
        self._v3_enabled = False
        self.kernel = None
        self.stock_kernel = None
        if self._v3_config_enabled:
            self._init_kernel(v3_cfg)

    def _init_kernel(self, v3_cfg: dict = None):
        """Initialize or retry kernel estimators. Safe to call multiple times."""
        if self._v3_enabled:
            return True  # Already ready
        if v3_cfg is None:
            v3_cfg = self._config.get('v3', {})
        bw = v3_cfg.get('bandwidth', 1.0)
        stock_bw = v3_cfg.get('stock_bandwidth', 1.0)
        min_dates = v3_cfg.get('min_train_dates', 20)
        if self.kernel is None:
            self.kernel = KernelEstimator(bandwidth=bw, min_train_dates=min_dates)
        if self.stock_kernel is None:
            self.stock_kernel = StockKernelEstimator(bandwidth=stock_bw, min_train_dates=min_dates)
        if self.kernel.load_and_fit():
            stats = self.kernel.get_stats()
            logger.info(f"Discovery v4.3: macro kernel ready — {stats['n_rows']} rows, {stats['n_dates']} dates")
            self.stock_kernel.load_and_fit()  # stock kernel is optional, log only
            # Smart TP coefficients removed — TP=ATR×ratio is simpler and equally effective
            self._fit_hold_kernel()  # v5.2: P(TP hit) per day for UI
            self._init_v6_components()  # v6.0: ensemble components
            self._v3_enabled = True
            return True
        logger.warning("Discovery v4.3: kernel fit failed, will retry next scan")
        return False

    def _fit_smart_tp_coefficients(self):
        """v5.2: Auto-learn Smart TP coefficients from historical data.

        For each historical signal that has max_gain data:
        1. Compute stock kernel E[R]
        2. Get ATR and outcome_max_gain_5d
        3. Group by (E[R] quartile, ATR quartile)
        4. Compute p35 of max_gain per group (= TP at 65% hit rate)
        5. Regress: TP_optimal = a × E[R] + b × ATR + c

        Runs every scan (~0.5s). Coefficients stored in self._smart_tp_coeffs.
        """
        self._smart_tp_coeffs = None  # reset

        if not self.stock_kernel or not self.stock_kernel._fitted:
            return

        # Use signal_daily_bars for precise max gain (intraday high)
        # Filter: only signals with positive outcome (proxy for elite-quality)
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                WITH combined AS (
                    SELECT b.scan_date, b.symbol, b.atr_pct, b.outcome_5d,
                           MAX(d1.high, d2.high, d3.high, d4.high, d5.high) as max_high,
                           d0.close as entry_close,
                           1 as priority
                    FROM signal_outcomes b
                    JOIN signal_daily_bars d0 ON b.scan_date=d0.scan_date AND b.symbol=d0.symbol AND d0.day_offset=0
                    JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
                    JOIN signal_daily_bars d2 ON b.scan_date=d2.scan_date AND b.symbol=d2.symbol AND d2.day_offset=2
                    JOIN signal_daily_bars d3 ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
                    JOIN signal_daily_bars d4 ON b.scan_date=d4.scan_date AND b.symbol=d4.symbol AND d4.day_offset=4
                    JOIN signal_daily_bars d5 ON b.scan_date=d5.scan_date AND b.symbol=d5.symbol AND d5.day_offset=5
                    WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0 AND d0.close > 0

                    UNION ALL

                    SELECT b.scan_date, b.symbol, b.atr_pct, b.outcome_5d,
                           MAX(d1.high, d2.high, d3.high, d4.high, d5.high) as max_high,
                           d0.close as entry_close,
                           2 as priority
                    FROM backfill_signal_outcomes b
                    JOIN signal_daily_bars d0 ON b.scan_date=d0.scan_date AND b.symbol=d0.symbol AND d0.day_offset=0
                    JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
                    JOIN signal_daily_bars d2 ON b.scan_date=d2.scan_date AND b.symbol=d2.symbol AND d2.day_offset=2
                    JOIN signal_daily_bars d3 ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
                    JOIN signal_daily_bars d4 ON b.scan_date=d4.scan_date AND b.symbol=d4.symbol AND d4.day_offset=4
                    JOIN signal_daily_bars d5 ON b.scan_date=d5.scan_date AND b.symbol=d5.symbol AND d5.day_offset=5
                    WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0 AND d0.close > 0
                ),
                deduped AS (
                    SELECT *, ROW_NUMBER() OVER (PARTITION BY scan_date, symbol ORDER BY priority) as rn
                    FROM combined
                )
                SELECT atr_pct, (max_high / entry_close - 1) * 100 as max_gain_pct, outcome_5d
                FROM deduped
                WHERE rn = 1 AND outcome_5d > -5
            """).fetchall()
        finally:
            conn.close()

        if len(rows) < 500:
            logger.warning("Smart TP: not enough data (%d rows), using config defaults", len(rows))
            return

        atrs = np.array([r[0] for r in rows])
        gains = np.array([r[1] for r in rows])

        # Group by ATR deciles, compute p35 of max_gain (= TP for 65% hit rate)
        atr_pcts = np.percentile(atrs, [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        X_reg, y_reg = [], []

        for i in range(len(atr_pcts) - 1):
            mask = (atrs >= atr_pcts[i]) & (atrs < atr_pcts[i + 1])
            if mask.sum() < 30:
                continue
            tp_p35 = float(np.percentile(gains[mask], 35))
            X_reg.append([atrs[mask].mean()])
            y_reg.append(tp_p35)

        if len(X_reg) < 4:
            return

        X_reg = np.array(X_reg)
        y_reg = np.array(y_reg)

        # Regression: TP_p35 = atr_coeff × ATR + intercept
        A = np.column_stack([X_reg, np.ones(len(X_reg))])
        coeffs, _, _, _ = np.linalg.lstsq(A, y_reg, rcond=None)
        atr_coeff = max(0.1, float(coeffs[0]))  # sanity floor
        intercept = float(coeffs[1])

        # E[R] coefficient: scale from baseline ratio (validated r=0.377)
        stp_cfg = self._config.get('v3', {}).get('smart_tp', {})
        base_atr_coeff = stp_cfg.get('atr_coeff', 0.475)
        base_er_coeff = stp_cfg.get('er_coeff', 1.032)
        er_coeff = base_er_coeff * (atr_coeff / base_atr_coeff) if base_atr_coeff > 0 else base_er_coeff

        self._smart_tp_coeffs = {
            'er_coeff': round(er_coeff, 4),
            'atr_coeff': round(atr_coeff, 4),
            'intercept': round(intercept, 4),
            'n_rows': len(atrs),
        }

        logger.info(
            "Smart TP auto-fit: er=%.3f atr=%.3f int=%.3f (n=%d signals)",
            er_coeff, atr_coeff, intercept, len(atrs),
        )

    def _fit_hold_kernel(self):
        """v5.2: Build lookup for P(TP hit by Dx) per ATR×volume bucket.

        For each historical signal with daily OHLC, compute whether TP
        was hit by D0/D1/D2/D3 and whether SL was hit by D3.
        Store as bucket lookup for fast per-pick prediction.
        """
        self._hold_data = None
        self._weekend_data = None  # v5.2: Friday→Monday kernel
        try:
            self._fit_hold_kernel_inner()
        except Exception as e:
            logger.error("HoldKernel: fit failed: %s", e)

    def _fit_hold_kernel_inner(self):
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                SELECT b.atr_pct, b.volume_ratio, b.momentum_5d, b.distance_from_20d_high,
                       d0.open as d0o, d0.high as d0h, d0.low as d0l,
                       d1.high as h1, d1.low as l1,
                       d2.high as h2, d2.low as l2,
                       d3.high as h3, d3.low as l3, d3.close as c3
                FROM backfill_signal_outcomes b
                JOIN signal_daily_bars d0 ON b.scan_date=d0.scan_date AND b.symbol=d0.symbol AND d0.day_offset=0
                JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
                JOIN signal_daily_bars d2 ON b.scan_date=d2.scan_date AND b.symbol=d2.symbol AND d2.day_offset=2
                JOIN signal_daily_bars d3 ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
                WHERE d0.open > 0 AND b.atr_pct > 0
            """).fetchall()
        finally:
            conn.close()

        if len(rows) < 500:
            logger.warning("HoldKernel: not enough data (%d rows)", len(rows))
            return

        # Store raw arrays for kernel-weighted lookup
        n = len(rows)
        self._hold_data = {
            'atr': np.array([r[0] for r in rows]),
            'vol': np.array([r[1] or 1 for r in rows]),
            'mom': np.array([r[2] or 0 for r in rows]),
            'd20h': np.array([r[3] or -5 for r in rows]),
            'n': n,
        }

        # Pre-compute % gains from D0 open for each day
        d0o = np.array([r[4] for r in rows])
        d0h = np.array([r[5] for r in rows])
        d0l = np.array([r[6] for r in rows])
        h1 = np.array([r[7] for r in rows])
        l1 = np.array([r[8] for r in rows])
        h2 = np.array([r[9] for r in rows])
        l2 = np.array([r[10] for r in rows])
        h3 = np.array([r[11] for r in rows])
        l3 = np.array([r[12] for r in rows])
        c3 = np.array([r[13] for r in rows])

        # Cumulative max high from D0 open
        self._hold_data['cum_high_d0'] = (d0h / d0o - 1) * 100
        self._hold_data['cum_high_d1'] = np.maximum(self._hold_data['cum_high_d0'], (h1 / d0o - 1) * 100)
        self._hold_data['cum_high_d2'] = np.maximum(self._hold_data['cum_high_d1'], (h2 / d0o - 1) * 100)
        self._hold_data['cum_high_d3'] = np.maximum(self._hold_data['cum_high_d2'], (h3 / d0o - 1) * 100)

        # Cumulative min low from D0 open
        self._hold_data['cum_low_d3'] = np.minimum(
            np.minimum((d0l / d0o - 1) * 100, (l1 / d0o - 1) * 100),
            np.minimum((l2 / d0o - 1) * 100, (l3 / d0o - 1) * 100),
        )

        # D3 close return (for actual E[R] calculation)
        self._hold_data['d3_ret'] = (c3 / d0o - 1) * 100

        # Auto-learn advice thresholds: find safe_ratio cutoffs from actual WR
        # For each signal, compute bucket safe_ratio → actual P&L → find where WR < 50%
        atr_arr = self._hold_data['atr']
        vol_arr = self._hold_data['vol']
        cum_h3 = self._hold_data['cum_high_d3']
        cum_l3 = self._hold_data['cum_low_d3']

        # Compute per-signal TP/SL and actual result
        tp_arr = np.maximum(1.5, 0.70 * (0.86 * atr_arr + 0.18))
        sl_arr = np.maximum(1.5, np.minimum(5.0, 1.5 * atr_arr))
        tp_hit = cum_h3 >= tp_arr
        sl_hit = cum_l3 <= -sl_arr

        # Bucket by ATR quintile to compute safe_ratio per signal
        safe_ratios = np.zeros(n)
        for pct_lo in range(0, 100, 20):
            lo = np.percentile(atr_arr, pct_lo)
            hi = np.percentile(atr_arr, min(pct_lo + 20, 100))
            mask = (atr_arr >= lo) & (atr_arr <= hi)
            if mask.sum() < 50:
                continue
            p_tp = tp_hit[mask].mean()
            p_sl = max(sl_hit[mask].mean(), 0.01)
            safe_ratios[mask] = p_tp / p_sl

        # Find thresholds: scan safe_ratio from 0.5 to 2.0, find where WR crosses 50% and 55%
        # Use close-to-close D3 return as P&L proxy (no TP/SL sim needed)
        # We don't have outcome in hold_data, so use tp_hit/sl_hit as proxy:
        # "profitable" ≈ tp_hit AND NOT sl_hit_first
        profitable = tp_hit & ~sl_hit  # simplified: TP hit and SL didn't hit

        risky_thresh = 1.0   # default
        caution_thresh = 1.2  # default

        for thresh in np.arange(0.5, 2.5, 0.1):
            below = safe_ratios < thresh
            above = safe_ratios >= thresh
            if below.sum() < 50 or above.sum() < 50:
                continue
            wr_below = profitable[below].mean()
            wr_above = profitable[above].mean()
            # RISKY threshold: where WR drops below 50%
            if wr_below < 0.50 and risky_thresh == 1.0:
                risky_thresh = round(float(thresh), 1)
            # CAUTION threshold: where WR drops below 55%
            if wr_below < 0.55 and caution_thresh == 1.2:
                caution_thresh = round(float(thresh), 1)

        self._advice_thresholds = {
            'risky': risky_thresh,
            'caution': max(caution_thresh, risky_thresh + 0.1),
        }

        # Auto-learn advice E[R] thresholds from simulated returns
        # For each signal, simulate TP/SL, bucket by return, find where WR crosses key levels
        tp_arr = np.maximum(0.5, np.where(atr_arr < 4.0, 0.5, 0.75) * atr_arr)
        sl_arr_sim = np.maximum(1.5, np.minimum(5.0, 1.0 * atr_arr))

        cum_low_d3 = self._hold_data['cum_low_d3']
        sl_hit_sim = cum_low_d3 <= -sl_arr_sim
        tp_hit_sim = (~sl_hit_sim) & (self._hold_data['cum_high_d3'] >= tp_arr)
        sim_rets = np.where(sl_hit_sim, -sl_arr_sim, np.where(tp_hit_sim, tp_arr, self._hold_data['d3_ret']))

        # Auto-learn advice E[R] thresholds from simulated return distribution
        # Percentile-based: top 20% = BUY, top 50% = HOLD, top 70% = CAUTION, rest RISKY
        p80 = float(np.percentile(sim_rets, 80))  # top 20% → BUY
        p50 = float(np.percentile(sim_rets, 50))  # above median → HOLD
        p30 = float(np.percentile(sim_rets, 30))  # above 30th → CAUTION

        self._advice_er_thresholds = {
            'buy': round(p80, 2),
            'hold': round(p50, 2),
            'caution': round(p30, 2),
        }

        logger.info(
            "HoldKernel: fitted on %d signals, advice E[R]: buy>=%.2f hold>=%.2f caution>=%.2f",
            n, p80, p50, p30,
        )

        # v5.2: Weekend kernel — Friday→Monday data
        try:
            self._fit_weekend_kernel()
        except Exception as e:
            logger.error("WeekendKernel: fit failed: %s", e)

    def _fit_weekend_kernel(self):
        """Fit kernel for Friday buy → Monday outcome prediction."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                SELECT b.atr_pct, b.volume_ratio, b.momentum_5d,
                       b.distance_from_20d_high, b.vix_at_signal,
                       d0.close as fri_close,
                       d1.open as mon_open, d1.high as mon_high,
                       d1.low as mon_low, d1.close as mon_close
                FROM backfill_signal_outcomes b
                JOIN signal_daily_bars d0 ON b.scan_date=d0.scan_date AND b.symbol=d0.symbol AND d0.day_offset=0
                JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
                WHERE d0.close > 0 AND d1.open > 0 AND b.atr_pct > 0
                  AND strftime('%w', b.scan_date) = '5'
            """).fetchall()
        finally:
            conn.close()

        if len(rows) < 200:
            logger.warning("WeekendKernel: not enough Friday data (%d rows)", len(rows))
            return

        n = len(rows)
        atr_arr = np.array([r[0] for r in rows])
        vol_arr = np.array([r[1] or 1 for r in rows])
        mom_arr = np.array([r[2] or 0 for r in rows])
        d20h_arr = np.array([r[3] or -5 for r in rows])
        vix_arr = np.array([r[4] or 20 for r in rows])
        fri_close = np.array([r[5] for r in rows])
        mon_open = np.array([r[6] for r in rows])
        mon_high = np.array([r[7] for r in rows])
        mon_low = np.array([r[8] for r in rows])
        mon_close = np.array([r[9] for r in rows])

        self._weekend_data = {
            'atr': atr_arr, 'vol': vol_arr, 'mom': mom_arr,
            'd20h': d20h_arr, 'vix': vix_arr,
            'mon_gap': (mon_open / fri_close - 1) * 100,
            'mon_ret': (mon_close / fri_close - 1) * 100,
            'mon_high': (mon_high / fri_close - 1) * 100,
            'mon_low': (mon_low / fri_close - 1) * 100,
            'n': n,
        }

        avg_ret = self._weekend_data['mon_ret'].mean()
        avg_wr = (self._weekend_data['mon_ret'] > 0).mean()

        # Auto-learn weekend display threshold: show only above-average WR
        self._weekend_wr_threshold = round(avg_wr * 100 + 3, 0)  # overall WR + 3pp

        logger.info("WeekendKernel: fitted on %d Friday signals, avg Monday WR=%.1f%%, display threshold=%.0f%%",
                     n, avg_wr * 100, self._weekend_wr_threshold)

    def predict_weekend(self, atr: float, vol: float, mom5: float,
                        d20h: float, vix: float) -> dict:
        """Predict Monday outcome if bought Friday, using kernel-weighted similar Fridays.

        Returns: mon_wr (%), mon_ret (%), mon_high (%), mon_low (%),
                 advice (str), safe_ratio (float)
        """
        if not self._weekend_data:
            return {}

        wd = self._weekend_data
        # Kernel weights: 5 features normalized
        atr_d = (wd['atr'] - atr) / max(atr, 1)
        vol_d = (wd['vol'] - vol) / max(vol, 0.5)
        mom_d = (wd['mom'] - mom5) / 10  # scale momentum
        d20h_d = (wd['d20h'] - d20h) / 10
        vix_d = (wd['vix'] - vix) / 10

        dist_sq = atr_d**2 + vol_d**2 + 0.5*mom_d**2 + 0.3*d20h_d**2 + 0.5*vix_d**2
        w = np.exp(-dist_sq / (2 * 0.2**2))
        ws = w.sum()
        if ws < 1e-10:
            return {}
        w /= ws
        neff = float(ws**2 / (w**2).sum())

        mon_ret = float((w * wd['mon_ret']).sum())
        mon_wr = float((w * (wd['mon_ret'] > 0)).sum()) * 100
        mon_high = float((w * wd['mon_high']).sum())
        mon_low = float((w * wd['mon_low']).sum())
        mon_gap = float((w * wd['mon_gap']).sum())

        # Safe ratio: P(up) / P(down)
        p_up = mon_wr / 100
        p_down = 1 - p_up
        safe_ratio = round(p_up / max(p_down, 0.01), 1)

        # Advice: auto-learned WR threshold (overall FRI→MON WR + 3pp)
        wk_thresh = getattr(self, '_weekend_wr_threshold', 55)
        if mon_wr >= wk_thresh:
            advice = 'buy_fri'
        elif mon_wr >= wk_thresh - 5:
            advice = 'caution'
        else:
            advice = 'risky'

        return {
            'mon_wr': round(mon_wr, 0),
            'mon_ret': round(mon_ret, 3),
            'mon_high': round(mon_high, 2),
            'mon_low': round(mon_low, 2),
            'mon_gap': round(mon_gap, 2),
            'safe_ratio': safe_ratio,
            'advice': advice,
            'neff': round(neff),
        }

    def predict_tp_timeline(self, atr: float, vol: float, tp_pct: float, sl_pct: float,
                            stock_er: float = 0.0, mom5: float = 0.0, d20h: float = -5.0) -> dict:
        """Predict P(TP hit by D0/D1/D2/D3), actual WR and E[R] for a specific stock.

        Uses kernel-weighted lookup: 4 features (ATR, volume, momentum, distance from high).
        """
        if not self._hold_data:
            return {}

        hd = self._hold_data
        # Kernel weights: 4 features — each normalized by its typical range
        atr_diff = (hd['atr'] - atr) / max(atr, 1)
        vol_diff = (hd['vol'] - vol) / max(vol, 0.5)
        mom_diff = (hd['mom'] - mom5) / 10   # mom range ~20%
        d20h_diff = (hd['d20h'] - d20h) / 15  # d20h range ~30%
        dist_sq = atr_diff**2 + vol_diff**2 + 0.5 * mom_diff**2 + 0.5 * d20h_diff**2
        w = np.exp(-dist_sq / (2 * 0.2**2))
        ws = w.sum()
        if ws < 1e-10:
            return {}
        w /= ws

        # P(TP hit by Dx) = weighted fraction where cum_high >= tp_pct
        p_tp_d0 = float((w * (hd['cum_high_d0'] >= tp_pct)).sum()) * 100
        p_tp_d1 = float((w * (hd['cum_high_d1'] >= tp_pct)).sum()) * 100
        p_tp_d2 = float((w * (hd['cum_high_d2'] >= tp_pct)).sum()) * 100
        p_tp_d3 = float((w * (hd['cum_high_d3'] >= tp_pct)).sum()) * 100

        # P(SL hit by D3)
        p_sl_d3 = float((w * (hd['cum_low_d3'] <= -sl_pct)).sum()) * 100

        # Kernel-weighted ACTUAL return (simulating TP/SL + D3 close exit)
        # This is the TRUE expected profit, not just TP/SL ratio
        sl_mask = hd['cum_low_d3'] <= -sl_pct
        tp_mask = (~sl_mask) & (hd['cum_high_d3'] >= tp_pct)
        time_mask = ~sl_mask & ~tp_mask
        sim_returns = np.where(sl_mask, -sl_pct,
                      np.where(tp_mask, tp_pct, hd['d3_ret']))
        actual_er = float((w * sim_returns).sum())
        actual_wr = float((w * (sim_returns > 0)).sum()) * 100

        # v5.3: Show D0 + D3 — day-trade chance + swing total
        show_days = [(p_tp_d0, 0), (p_tp_d3, 3)]

        # Advice based on auto-learned E[R] thresholds
        at = getattr(self, '_advice_er_thresholds', {'buy': 0.3, 'hold': 0.05, 'caution': -0.1})
        if actual_er >= at['buy']:
            advice = 'buy'
        elif actual_er >= at['hold']:
            advice = 'hold'
        elif actual_er >= at['caution']:
            advice = 'caution'
        else:
            advice = 'risky'

        return {
            'tp_d0': round(p_tp_d0, 0), 'tp_d1': round(p_tp_d1, 0),
            'tp_d2': round(p_tp_d2, 0), 'tp_d3': round(p_tp_d3, 0),
            'sl_d3': round(p_sl_d3, 0),
            'actual_wr': round(actual_wr, 0), 'actual_er': round(actual_er, 3),
            'show_day1': show_days[0][1], 'show_pct1': round(show_days[0][0], 0),
            'show_day2': show_days[1][1], 'show_pct2': round(show_days[1][0], 0),
            'advice': advice,
        }

    def _init_v6_components(self):
        """v6.0: Initialize ensemble components (sequence matcher, leading indicators).
        Safe to call multiple times — skips if already fitted.
        """
        if self._v6_fitted:
            return
        try:
            ok = self._sequence_matcher.fit()
            if ok:
                logger.info("Discovery v6.0: SequenceMatcher fitted (%d sequences)",
                            len(self._sequence_matcher._historical or []))
            else:
                logger.warning("Discovery v6.0: SequenceMatcher fit failed")
        except Exception as e:
            logger.error("Discovery v6.0: SequenceMatcher error: %s", e)

        try:
            ok = self._leading_indicators.fit()
            if ok:
                logger.info("Discovery v6.0: LeadingIndicators fitted")
            else:
                logger.warning("Discovery v6.0: LeadingIndicators fit failed")
        except Exception as e:
            logger.error("Discovery v6.0: LeadingIndicators error: %s", e)

        # Optimize ensemble weights from recent outcomes
        try:
            opt = self._ensemble.optimize_weights(90)
            logger.info("Discovery v6.0: Ensemble weights: %s", opt.get('new_weights', 'N/A'))
        except Exception as e:
            logger.error("Discovery v6.0: Ensemble weight optimization error: %s", e)

        self._v6_fitted = True

    def get_scan_progress(self) -> dict:
        return self._scan_progress.copy()

    def _ensure_table(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discovery_picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                scan_price REAL NOT NULL,
                current_price REAL,
                layer2_score REAL,
                beta REAL,
                atr_pct REAL,
                distance_from_high REAL,
                rsi REAL,
                momentum_5d REAL,
                momentum_20d REAL,
                volume_ratio REAL,
                sl_price REAL,
                sl_pct REAL,
                tp1_price REAL,
                tp1_pct REAL,
                tp2_price REAL,
                tp2_pct REAL,
                sector TEXT,
                market_cap REAL,
                vix_close REAL,
                pct_above_20d_ma REAL,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(scan_date, symbol)
            )
        """)
        # Add columns for L2 features, outcomes, and enrichment (safe if already exist)
        new_cols = [
            ('distance_from_20d_high', 'REAL'),
            ('vix_term_structure', 'REAL'), ('new_52w_highs', 'REAL'),
            ('bull_score', 'REAL'), ('news_count', 'REAL'), ('news_pos_ratio', 'REAL'),
            ('highs_lows_ratio', 'REAL'), ('ad_ratio', 'REAL'), ('mcap_log', 'REAL'),
            ('sector_1d_change', 'REAL'), ('vix3m_close', 'REAL'), ('upside_pct', 'REAL'),
            ('outcome_1d', 'REAL'), ('outcome_2d', 'REAL'), ('outcome_3d', 'REAL'),
            ('outcome_5d', 'REAL'), ('outcome_max_gain_5d', 'REAL'), ('outcome_max_dd_5d', 'REAL'),
            ('days_to_earnings', 'INTEGER'), ('put_call_ratio', 'REAL'), ('short_pct_float', 'REAL'),
            ('benchmark_xlu_5d', 'REAL'), ('benchmark_xle_5d', 'REAL'), ('benchmark_spy_5d', 'REAL'),
            ('breadth_delta_5d', 'REAL'), ('vix_delta_5d', 'REAL'),
            ('crude_close', 'REAL'), ('gold_close', 'REAL'), ('hyg_close', 'REAL'),
            ('dxy_delta_5d', 'REAL'), ('stress_score', 'REAL'),
            ('expected_gain', 'REAL'), ('rr_ratio', 'REAL'),
            # Pre-market validation + intraday (v4.5)
            ('premarket_price', 'REAL'),
            ('gap_pct', 'REAL'),
            ('scan_type', "TEXT DEFAULT 'evening'"),
            # Limit-buy strategy (v4.6)
            ('limit_entry_price', 'REAL'),
            ('limit_pct', 'REAL'),
            ('entry_price', 'REAL'),
            ('entry_status', "TEXT DEFAULT 'pending'"),
            ('entry_filled_at', 'TEXT'),
        ]
        for col_name, col_type in new_cols:
            try:
                conn.execute(f"ALTER TABLE discovery_picks ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
        conn.close()

    def _load_picks_from_db(self):
        """Load active picks from DB."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM discovery_picks
            WHERE status = 'active'
            ORDER BY layer2_score DESC
        """).fetchall()
        conn.close()

        self._picks = []
        for r in rows:
            self._picks.append(DiscoveryPick(
                symbol=r['symbol'], scan_date=r['scan_date'],
                scan_price=r['scan_price'], current_price=r['current_price'] or r['scan_price'],
                layer2_score=r['layer2_score'] or 0,
                beta=r['beta'] or 0, atr_pct=r['atr_pct'] or 0,
                distance_from_high=r['distance_from_high'] or 0,
                distance_from_20d_high=r['distance_from_20d_high'] or 0,
                rsi=r['rsi'] or 0, momentum_5d=r['momentum_5d'] or 0,
                momentum_20d=r['momentum_20d'] or 0, volume_ratio=r['volume_ratio'] or 0,
                sl_price=r['sl_price'] or 0, sl_pct=r['sl_pct'] or 0,
                tp1_price=r['tp1_price'] or 0, tp1_pct=r['tp1_pct'] or 0,
                tp2_price=r['tp2_price'] or 0, tp2_pct=r['tp2_pct'] or 0,
                expected_gain=r['expected_gain'] or 0, rr_ratio=r['rr_ratio'] or 0,
                sector=r['sector'] or '', market_cap=r['market_cap'] or 0,
                vix_close=r['vix_close'] or 0, pct_above_20d_ma=r['pct_above_20d_ma'] or 0,
                vix_term_structure=r['vix_term_structure'] or 0,
                new_52w_highs=r['new_52w_highs'] or 0,
                bull_score=r['bull_score'], news_count=r['news_count'] or 0,
                news_pos_ratio=r['news_pos_ratio'],
                highs_lows_ratio=r['highs_lows_ratio'] or 0,
                ad_ratio=r['ad_ratio'] or 0, mcap_log=r['mcap_log'] or 0,
                sector_1d_change=r['sector_1d_change'] or 0,
                vix3m_close=r['vix3m_close'] or 0, upside_pct=r['upside_pct'],
                days_to_earnings=r['days_to_earnings'],
                put_call_ratio=r['put_call_ratio'],
                short_pct_float=r['short_pct_float'],
                # Macro stress (v1.2)
                breadth_delta_5d=r['breadth_delta_5d'],
                vix_delta_5d=r['vix_delta_5d'],
                crude_close=r['crude_close'],
                gold_close=r['gold_close'],
                dxy_delta_5d=r['dxy_delta_5d'],
                stress_score=r['stress_score'],
                # Pre-market validation (v4.5)
                premarket_price=r['premarket_price'],
                gap_pct=r['gap_pct'],
                scan_type=r['scan_type'] or 'evening',
                # Limit-buy (v4.6)
                limit_entry_price=r['limit_entry_price'],
                limit_pct=r['limit_pct'],
                entry_price=r['entry_price'],
                entry_status=r['entry_status'] or 'pending',
                entry_filled_at=r['entry_filled_at'],
                status=r['status'] or 'active',
            ))
            # v5.2: restore tp_timeline + weekend_play from DB
            for attr, col in [('tp_timeline', 'tp_timeline_json'), ('weekend_play', 'weekend_play_json')]:
                raw = r[col] if col in r.keys() else None
                if raw:
                    try:
                        setattr(self._picks[-1], attr, json.loads(raw))
                    except (json.JSONDecodeError, TypeError):
                        pass

        if self._picks:
            self._last_scan = self._picks[0].scan_date
            logger.info(f"Discovery: loaded {len(self._picks)} active picks from {self._last_scan}")

    def get_picks(self, auto_refresh: bool = True) -> list[dict]:
        """Return current picks as dicts for API. Applies sector diversification."""
        if auto_refresh:
            self._maybe_refresh_prices()
        max_display = self._config.get('schedule', {}).get('max_picks_display', 10)
        div_cfg = self._config.get('diversification', {})
        max_per_sector = div_cfg.get('max_per_sector', 3)

        # v5.3: sort by E[R] only — validated best ranking across all years (R²=0.0003 for other factors)
        rank_fn = lambda p: (p.layer2_score or 0)
        sorted_picks = sorted(self._picks, key=rank_fn, reverse=True)

        # Apply sector diversification
        sector_counts: dict[str, int] = {}
        diversified = []
        for p in sorted_picks:
            sector = p.sector or 'Unknown'
            cnt = sector_counts.get(sector, 0)
            if cnt >= max_per_sector:
                continue
            sector_counts[sector] = cnt + 1
            diversified.append(p)
            if len(diversified) >= max_display:
                break

        return [p.to_dict() for p in diversified]

    def get_last_scan(self) -> Optional[str]:
        return self._last_scan

    def get_stats(self) -> dict:
        """Historical performance statistics from picks with filled outcomes."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Overall stats (picks with outcome data)
        stats_row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) as wins_5d,
                   SUM(CASE WHEN outcome_5d IS NOT NULL THEN 1 ELSE 0 END) as has_outcome,
                   AVG(outcome_1d) as avg_1d,
                   AVG(outcome_5d) as avg_5d,
                   AVG(outcome_max_gain_5d) as avg_max_gain,
                   AVG(outcome_max_dd_5d) as avg_max_dd,
                   SUM(CASE WHEN status='hit_tp1' THEN 1 ELSE 0 END) as tp1_hits,
                   SUM(CASE WHEN status='hit_sl' THEN 1 ELSE 0 END) as sl_hits
            FROM discovery_picks
        """).fetchone()

        # Sector breakdown
        sector_rows = conn.execute("""
            SELECT sector, COUNT(*) as n,
                   SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) as wins,
                   AVG(outcome_5d) as avg_5d
            FROM discovery_picks
            WHERE outcome_5d IS NOT NULL
            GROUP BY sector ORDER BY n DESC
        """).fetchall()

        # Score tier breakdown (handles both v2 score 0-100 and v3 E[R] 0-5 ranges)
        tier_rows = conn.execute("""
            SELECT CASE
                WHEN layer2_score < 10 THEN
                    CASE WHEN layer2_score >= 2.0 THEN 'A+'
                         WHEN layer2_score >= 1.0 THEN 'A'
                         WHEN layer2_score >= 0.5 THEN 'B'
                         ELSE 'C' END
                ELSE
                    CASE WHEN layer2_score >= 80 THEN 'A+'
                         WHEN layer2_score >= 70 THEN 'A'
                         WHEN layer2_score >= 60 THEN 'B'
                         ELSE 'C' END
                END as tier,
                COUNT(*) as n,
                SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) as wins,
                AVG(outcome_5d) as avg_5d
            FROM discovery_picks
            WHERE outcome_5d IS NOT NULL
            GROUP BY tier ORDER BY tier
        """).fetchall()

        # Active picks sector distribution
        active_sectors = conn.execute("""
            SELECT sector, COUNT(*) as n FROM discovery_picks
            WHERE status = 'active' GROUP BY sector ORDER BY n DESC
        """).fetchall()

        # Benchmark comparison (Marcus test: does L2 beat sector beta?)
        try:
            bench_row = conn.execute("""
                SELECT AVG(outcome_5d) as picks_avg,
                       AVG(benchmark_xlu_5d) as xlu_avg,
                       AVG(benchmark_xle_5d) as xle_avg,
                       AVG(benchmark_spy_5d) as spy_avg,
                       COUNT(*) as n
                FROM discovery_picks
                WHERE outcome_5d IS NOT NULL AND benchmark_spy_5d IS NOT NULL
            """).fetchone()
        except Exception:
            bench_row = None  # benchmark columns not yet created

        conn.close()

        total = stats_row['total'] or 0
        has_outcome = stats_row['has_outcome'] or 0
        wins = stats_row['wins_5d'] or 0

        # Benchmark data
        bench_n = bench_row['n'] or 0 if bench_row else 0
        benchmark = None
        if bench_n > 0:
            picks_avg = bench_row['picks_avg'] or 0
            basket_avg = ((bench_row['xlu_avg'] or 0) + (bench_row['xle_avg'] or 0)) / 2
            benchmark = {
                'n': bench_n,
                'picks_avg_5d': round(picks_avg, 3),
                'xlu_avg_5d': round(bench_row['xlu_avg'] or 0, 3),
                'xle_avg_5d': round(bench_row['xle_avg'] or 0, 3),
                'spy_avg_5d': round(bench_row['spy_avg'] or 0, 3),
                'basket_avg_5d': round(basket_avg, 3),
                'alpha_vs_basket': round(picks_avg - basket_avg, 3),
                'alpha_vs_spy': round(picks_avg - (bench_row['spy_avg'] or 0), 3),
            }

        return {
            'total_picks': total,
            'has_outcome': has_outcome,
            'win_rate_5d': round(wins / has_outcome * 100, 1) if has_outcome > 0 else None,
            'avg_return_1d': round(stats_row['avg_1d'], 2) if stats_row['avg_1d'] else None,
            'avg_return_5d': round(stats_row['avg_5d'], 2) if stats_row['avg_5d'] else None,
            'avg_max_gain': round(stats_row['avg_max_gain'], 2) if stats_row['avg_max_gain'] else None,
            'avg_max_dd': round(stats_row['avg_max_dd'], 2) if stats_row['avg_max_dd'] else None,
            'tp1_hits': stats_row['tp1_hits'] or 0,
            'sl_hits': stats_row['sl_hits'] or 0,
            'by_sector': [{'sector': r['sector'], 'n': r['n'], 'wr': round(r['wins'] / r['n'] * 100, 0) if r['n'] else 0, 'avg': round(r['avg_5d'], 2) if r['avg_5d'] else 0} for r in sector_rows],
            'by_tier': [{'tier': r['tier'], 'n': r['n'], 'wr': round(r['wins'] / r['n'] * 100, 0) if r['n'] else 0, 'avg': round(r['avg_5d'], 2) if r['avg_5d'] else 0} for r in tier_rows],
            'active_sectors': [{'sector': r['sector'], 'n': r['n']} for r in active_sectors],
            'benchmark': benchmark,
        }

    def _maybe_refresh_prices(self):
        """Reload picks from DB + refresh prices if >5 min since last refresh."""
        refresh_interval = self._config.get('schedule', {}).get('price_refresh_minutes', 5) * 60
        now = time.monotonic()
        if now - self._last_price_refresh < refresh_interval:
            return
        self._last_price_refresh = now
        # Always reload from DB (cron scan writes to DB in separate process)
        self._load_picks_from_db()
        if not self._picks:
            return
        try:
            self.refresh_prices()
        except Exception as e:
            logger.error(f"Discovery: auto price refresh failed: {e}")

    def run_scan(self) -> list[DiscoveryPick]:
        """Full scan: load universe → Layer 1 → Layer 2 → compute SL/TP → save."""
        from api.yfinance_utils import fetch_history

        scan_date = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
        logger.info(f"Discovery scan starting for {scan_date}")
        self._scan_progress = {'status': 'loading', 'pct': 0, 'stage': 'Loading universe...', 'l1': 0, 'l2': 0}

        # Track outcomes for expired picks before new scan
        try:
            n_tracked = self._outcome_tracker.track_expired_picks()
            if n_tracked:
                logger.info(f"Discovery: tracked {n_tracked} expired pick outcomes")
        except Exception as e:
            logger.error(f"Discovery: outcome tracking error: {e}")

        # v6.0: Build temporal features + sequence prediction + leading signals
        try:
            self._temporal_features = self._temporal.build_features(scan_date)
            logger.info("Discovery v6.0: temporal features built (%d)", len(self._temporal_features))
        except Exception as e:
            logger.error("Discovery v6.0: temporal build error: %s", e)
            self._temporal_features = {}

        try:
            if self._sequence_matcher._fitted:
                self._sequence_prediction = self._sequence_matcher.predict(self._temporal_features)
                logger.info("Discovery v6.0: sequence prediction: %s", self._sequence_prediction.get('pattern', 'N/A'))
            else:
                self._sequence_prediction = {}
        except Exception as e:
            logger.error("Discovery v6.0: sequence predict error: %s", e)
            self._sequence_prediction = {}

        try:
            self._leading_signals = self._leading_indicators.compute_signals(scan_date)
            logger.info("Discovery v6.0: leading signals: %s",
                        self._leading_signals.get('regime_forecast', {}).get('forecast', 'N/A'))
        except Exception as e:
            logger.error("Discovery v6.0: leading signals error: %s", e)
            self._leading_signals = {}

        # 1. Load universe + fundamentals
        stocks = self._load_universe()
        logger.info(f"Discovery: {len(stocks)} stocks in universe")
        self._scan_progress.update(stage=f'Loaded {len(stocks)} stocks', pct=5)

        # 2. Load macro/breadth (market-wide, same for all stocks today)
        macro = self._load_macro(scan_date)

        vix = macro.get('vix_close', 0) or 0
        qg = self._config.get('quality_gates', {})
        tp_sl_cfg = self._config.get('smart_tp_sl', {})
        adaptive_min_score = self._config.get('layer2', {}).get('min_score', 35)

        # Retry kernel init if config says v3 but kernel wasn't ready
        if self._v3_config_enabled and not self._v3_enabled:
            self._init_kernel()

        mode = 'v3 kernel' if self._v3_enabled else 'v2 score'
        logger.info(f"Discovery: VIX={vix:.1f}, mode={mode}")

        # 3. Compute per-stock technical features via yfinance
        candidates = []
        batch_size = 50
        symbols = list(stocks.keys())
        total_batches = (len(symbols) + batch_size - 1) // batch_size

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            batch_str = ' '.join(batch)
            batch_num = i // batch_size + 1
            pct = 5 + int(batch_num / total_batches * 80)
            self._scan_progress.update(status='scanning', pct=pct, stage=f'Batch {batch_num}/{total_batches}', l1=len(candidates))
            logger.info(f"Discovery: fetching batch {batch_num}/{total_batches}")

            try:
                import yfinance as yf
                data = yf.download(batch_str, period='1y', interval='1d',
                                   auto_adjust=True, progress=False, threads=False)
            except Exception as e:
                logger.error(f"Discovery: yfinance batch error: {e}")
                continue

            for sym in batch:
                try:
                    if len(batch) == 1:
                        df = data
                    else:
                        df = data.xs(sym, axis=1, level=1) if sym in data.columns.get_level_values(1) else None

                    if df is None or df.empty or len(df) < 20:
                        continue

                    features = self._compute_technical(df, sym, stocks.get(sym, {}))
                    if features is None:
                        continue

                    # Layer 1 check (v4: skipped — kernel learns from data)
                    if not self._v3_enabled:
                        passed, reason = self.scorer.passes_layer1(features)
                        if not passed:
                            continue

                    # Merge macro features
                    features.update(macro)
                    candidates.append(features)

                except Exception as e:
                    logger.debug(f"Discovery: error processing {sym}: {e}")
                    continue

            # Rate limit between batches
            if i + batch_size < len(symbols):
                time.sleep(1)

        logger.info(f"Discovery: {len(candidates)} passed Layer 1")
        self._scan_progress.update(status='scoring', pct=87, stage=f'L1 passed: {len(candidates)}', l1=len(candidates))

        # 4. Load per-stock sentiment/analyst/options/news
        self._enrich_candidates(candidates)
        self._scan_progress.update(pct=92, stage=f'Scoring {len(candidates)} candidates...')

        # 5. Scoring: v3 Kernel E[R] or v2 composite score
        v3_cfg = self._config.get('v3', {})

        if self._v3_enabled and self.kernel:
            picks = self._score_v3(candidates, macro, scan_date, v3_cfg)
        else:
            picks = self._score_v2(candidates, macro, scan_date, qg, tp_sl_cfg, adaptive_min_score)

        # Log sector distribution
        pick_sectors: dict[str, int] = {}
        for p in picks:
            s = p.sector or 'Unknown'
            pick_sectors[s] = pick_sectors.get(s, 0) + 1
        sectors_summary = ', '.join(f"{s}:{n}" for s, n in sorted(pick_sectors.items(), key=lambda x: -x[1]))
        logger.info(f"Discovery: {len(picks)} total picks | sectors: {sectors_summary}")
        self._scan_progress.update(pct=97, stage=f'Scored: {len(picks)} picks', l2=len(picks))

        # 6. Deactivate all previous active picks + save new scan to DB
        #    Each scan replaces the full active set. Old picks kept as 'replaced' for calibration.
        self._expire_old_picks(scan_date)
        self._deactivate_previous_picks(scan_date)
        self._save_picks(picks, scan_date)

        self._picks = picks
        self._last_scan = scan_date
        self._scan_progress = {'status': 'done', 'pct': 100, 'stage': f'Done: {len(picks)} picks', 'l1': len(candidates), 'l2': len(picks)}
        return picks

    def refresh_prices(self):
        """Refresh current prices for active picks (called every 5 min)."""
        if not self._picks:
            return

        symbols = [p.symbol for p in self._picks]
        try:
            import yfinance as yf
            data = yf.download(' '.join(symbols), period='1d', interval='1m',
                               auto_adjust=True, progress=False, threads=False)
            if data.empty:
                return

            conn = sqlite3.connect(str(DB_PATH))
            for pick in self._picks:
                try:
                    if len(symbols) == 1:
                        close_col = data['Close']
                    else:
                        if pick.symbol not in data.columns.get_level_values(1):
                            continue
                        close_col = data['Close'][pick.symbol]

                    latest = close_col.dropna().iloc[-1] if not close_col.dropna().empty else None
                    if latest and latest > 0:
                        pick.current_price = float(latest)

                        # Limit-buy fill detection (v4.6)
                        if (pick.entry_status == 'pending'
                                and pick.limit_entry_price is not None
                                and pick.current_price <= pick.limit_entry_price
                                and pick.status == 'active'):
                            pick.entry_status = 'filled'
                            pick.entry_price = pick.limit_entry_price
                            pick.entry_filled_at = datetime.now().strftime('%Y-%m-%d %H:%M')
                            logger.info(
                                "Discovery LIMIT FILLED: %s at $%.2f (limit=$%.2f, current=$%.2f)",
                                pick.symbol, pick.entry_price, pick.limit_entry_price, pick.current_price,
                            )

                        # Check SL/TP hits (only after entry filled)
                        if pick.status == 'active' and pick.entry_status == 'filled':
                            if pick.current_price <= pick.sl_price:
                                pick.status = 'hit_sl'
                            elif pick.current_price >= pick.tp1_price:
                                pick.status = 'hit_tp1'

                        conn.execute(
                            "UPDATE discovery_picks SET current_price=?, status=?, "
                            "entry_status=?, entry_price=?, entry_filled_at=?, "
                            "updated_at=datetime('now') WHERE symbol=? AND scan_date=?",
                            (pick.current_price, pick.status,
                             pick.entry_status, pick.entry_price, pick.entry_filled_at,
                             pick.symbol, pick.scan_date))
                except Exception:
                    continue

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Discovery price refresh error: {e}")

    def _compute_technical(self, df: pd.DataFrame, symbol: str, fund: dict) -> Optional[dict]:
        """Compute technical features from daily OHLCV bars."""
        try:
            df = df.dropna(subset=['Close'])
            if len(df) < 20:
                return None

            close = df['Close'].values
            high = df['High'].values
            low = df['Low'].values
            volume = df['Volume'].values
            current = float(close[-1])

            if current <= 0:
                return None

            # ATR (14-period)
            tr = []
            for i in range(1, len(df)):
                tr.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
            atr_14 = float(np.mean(tr[-14:])) if len(tr) >= 14 else float(np.mean(tr))
            atr_pct = atr_14 / current * 100

            # RSI (14-period)
            deltas = np.diff(close)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            if len(gains) >= 14:
                avg_gain = float(np.mean(gains[-14:]))
                avg_loss = float(np.mean(losses[-14:]))
                if avg_loss > 0:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                else:
                    rsi = 100
            else:
                rsi = 50

            # Momentum
            if len(close) >= 6:
                momentum_5d = (close[-1] / close[-6] - 1) * 100
            else:
                momentum_5d = 0

            if len(close) >= 21:
                momentum_20d = (close[-1] / close[-21] - 1) * 100
            else:
                momentum_20d = 0

            # Distance from 52-week high (negative convention: 0=at high)
            high_52w = float(np.max(high[-252:])) if len(high) >= 252 else float(np.max(high))
            distance_from_high = (current / high_52w - 1) * 100 if high_52w > 0 else 0

            # Distance from 20-day high (v3 kernel feature) — use High prices, not Close
            if len(high) >= 20:
                high_20d = float(np.max(high[-20:]))
                distance_from_20d_high = (current / high_20d - 1) * 100 if high_20d > 0 else 0
            else:
                distance_from_20d_high = 0

            # Volume ratio (today vs 20d avg)
            if len(volume) >= 21:
                avg_vol_20 = float(np.mean(volume[-21:-1]))
                volume_ratio = float(volume[-1]) / avg_vol_20 if avg_vol_20 > 0 else 1.0
            else:
                volume_ratio = 1.0

            # Distance from 20d MA (%) — mean-reversion signal (v1.7)
            if len(close) >= 20:
                ma_20 = float(np.mean(close[-20:]))
                dist_from_20d_ma = (current / ma_20 - 1) * 100 if ma_20 > 0 else 0
            else:
                dist_from_20d_ma = 0

            # ROC 10d (%) — rate of change (v1.7)
            if len(close) >= 11:
                roc_10d = (close[-1] / close[-11] - 1) * 100
            else:
                roc_10d = 0

            # D0 OHLC for close position filter (v5.3)
            d0_open = float(df['Open'].values[-1]) if 'Open' in df.columns else current
            d0_high = float(high[-1])
            d0_low = float(low[-1])

            return {
                'symbol': symbol,
                'close': current,
                'open': d0_open,
                'day_high': d0_high,
                'day_low': d0_low,
                'atr_pct': atr_pct,
                'rsi': rsi,
                'momentum_5d': momentum_5d,
                'momentum_20d': momentum_20d,
                'distance_from_high': distance_from_high,
                'distance_from_20d_high': distance_from_20d_high,
                'volume_ratio': volume_ratio,
                'dist_from_20d_ma': dist_from_20d_ma,
                'roc_10d': roc_10d,
                'beta': fund.get('beta'),
                'sector': fund.get('sector', ''),
                'market_cap': fund.get('market_cap', 0),
                'mcap_log': math.log10(fund.get('market_cap', 1e9) + 1),
            }
        except Exception as e:
            logger.debug(f"Discovery: tech compute error for {symbol}: {e}")
            return None

    def _load_universe(self) -> dict:
        """Load stock universe with fundamentals from DB."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT symbol, beta, pe_forward, market_cap, sector, avg_volume
            FROM stock_fundamentals
            WHERE market_cap > 1e9 AND avg_volume > 100000
        """).fetchall()
        conn.close()
        return {r['symbol']: dict(r) for r in rows}

    def _load_macro(self, scan_date: str) -> dict:
        """Load latest macro/breadth data + compute derived stress features."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        macro_row = conn.execute("""
            SELECT m.vix_close, m.vix3m_close, m.gold_close, m.crude_close, m.hyg_close,
                   m.dxy_close, m.yield_spread, m.yield_10y, m.spy_close,
                   b.pct_above_20d_ma, b.new_52w_highs, b.new_52w_lows, b.ad_ratio
            FROM macro_snapshots m
            LEFT JOIN market_breadth b ON m.date = b.date
            ORDER BY m.date DESC LIMIT 1
        """).fetchone()

        if not macro_row:
            conn.close()
            return {}

        result = dict(macro_row)

        # Derived: VIX term structure
        vix = result.get('vix_close', 20)
        vix3m = result.get('vix3m_close', 20)
        result['vix_term_structure'] = vix3m / vix if vix and vix > 0 else 1.0
        # v5.0: VIX term spread (vix - vix3m) for kernel feature
        result['vix_term_spread'] = round(vix - vix3m, 4) if vix and vix3m else 0.0

        highs = result.get('new_52w_highs', 100)
        lows = result.get('new_52w_lows', 100)
        result['highs_lows_ratio'] = highs / max(lows, 1) if highs is not None and lows is not None else 1.0

        # --- Derived delta features (5-day rate of change) ---
        # Get macro 6 days ago for delta computation
        macro_5d = conn.execute("""
            SELECT vix_close, dxy_close, crude_close FROM macro_snapshots
            ORDER BY date DESC LIMIT 1 OFFSET 5
        """).fetchone()

        breadth_5d = conn.execute("""
            SELECT pct_above_20d_ma FROM market_breadth
            ORDER BY date DESC LIMIT 1 OFFSET 5
        """).fetchone()

        conn.close()

        # VIX delta 5d
        if macro_5d and macro_5d['vix_close'] and vix:
            result['vix_delta_5d'] = round(vix - macro_5d['vix_close'], 2)
        else:
            result['vix_delta_5d'] = 0.0

        # DXY delta 5d
        dxy = result.get('dxy_close')
        if macro_5d and macro_5d['dxy_close'] and dxy:
            result['dxy_delta_5d'] = round(dxy - macro_5d['dxy_close'], 2)
        else:
            result['dxy_delta_5d'] = 0.0

        # Breadth delta 5d
        breadth_now = result.get('pct_above_20d_ma')
        if breadth_5d and breadth_5d['pct_above_20d_ma'] and breadth_now:
            result['breadth_delta_5d'] = round(breadth_now - breadth_5d['pct_above_20d_ma'], 2)
        else:
            result['breadth_delta_5d'] = 0.0

        # Crude oil delta 5d (% change) — used for Energy sector gate
        crude_now = result.get('crude_close')
        crude_5d_ago = macro_5d['crude_close'] if macro_5d and macro_5d['crude_close'] else None
        if crude_now and crude_5d_ago and crude_5d_ago > 0:
            crude_chg = round((crude_now / crude_5d_ago - 1) * 100, 2)
            result['crude_delta_5d_pct'] = crude_chg
        else:
            result['crude_delta_5d_pct'] = None

        # Market Stress Score (0-100, higher = more stress)
        # Combines 6 symptoms that appear in ANY crisis
        stress_components = []

        # 1. VIX acceleration: +10 in 5 days = max stress
        vix_d = result.get('vix_delta_5d', 0)
        stress_components.append(min(1.0, max(0.0, vix_d / 10.0)))

        # 2. Breadth collapse: -20 in 5 days = max stress
        breadth_d = result.get('breadth_delta_5d', 0)
        stress_components.append(min(1.0, max(0.0, -breadth_d / 20.0)))

        # 3. VIX backwardation: VIX > VIX3M = panic
        vts = result.get('vix_term_structure', 1.0)
        stress_components.append(min(1.0, max(0.0, (1.0 - vts) / 0.1)))

        # 4. VIX level: >30 = high stress
        stress_components.append(min(1.0, max(0.0, (vix - 20) / 15.0)) if vix else 0.0)

        # 5. DXY surge: +2 in 5 days = risk-off flow
        dxy_d = result.get('dxy_delta_5d', 0)
        stress_components.append(min(1.0, max(0.0, dxy_d / 2.0)))

        # 6. Breadth level: <30% = capitulation
        if breadth_now and breadth_now > 0:
            stress_components.append(min(1.0, max(0.0, (50 - breadth_now) / 25.0)))
        else:
            stress_components.append(0.0)

        result['stress_score'] = round(sum(stress_components) / len(stress_components) * 100, 1)

        return result

    def _enrich_candidates(self, candidates: list):
        """Add analyst/news/options data from DB to candidates."""
        if not candidates:
            return

        symbols = [c['symbol'] for c in candidates]
        placeholders = ','.join('?' * len(symbols))
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Analyst consensus
        rows = conn.execute(f"SELECT symbol, bull_score, upside_pct FROM analyst_consensus WHERE symbol IN ({placeholders})", symbols).fetchall()
        analyst = {r['symbol']: dict(r) for r in rows}

        # News sentiment
        rows = conn.execute(f"""
            SELECT symbol, AVG(sentiment_score) as avg_news_sentiment, COUNT(*) as news_count,
                   SUM(CASE WHEN sentiment_label='positive' THEN 1 ELSE 0 END) as news_pos,
                   SUM(CASE WHEN sentiment_label='negative' THEN 1 ELSE 0 END) as news_neg
            FROM news_events WHERE symbol IN ({placeholders}) AND symbol IS NOT NULL
            GROUP BY symbol
        """, symbols).fetchall()
        news = {r['symbol']: dict(r) for r in rows}

        # Options flow
        rows = conn.execute(f"SELECT symbol, put_call_ratio FROM options_flow WHERE symbol IN ({placeholders}) GROUP BY symbol HAVING MAX(date)", symbols).fetchall()
        options = {r['symbol']: dict(r) for r in rows}

        # Earnings proximity — use earnings_history (richer data than earnings_calendar)
        today_str = date.today().isoformat()
        rows = conn.execute(f"""
            SELECT symbol, MIN(report_date) as next_date
            FROM earnings_history
            WHERE symbol IN ({placeholders}) AND report_date >= ?
            GROUP BY symbol
        """, symbols + [today_str]).fetchall()
        earnings = {}
        for r in rows:
            try:
                ed = datetime.strptime(r['next_date'][:10], '%Y-%m-%d').date()
                earnings[r['symbol']] = (ed - date.today()).days
            except Exception:
                pass

        # Short interest
        rows = conn.execute(f"SELECT symbol, short_pct_float FROM short_interest WHERE symbol IN ({placeholders})", symbols).fetchall()
        short_data = {r['symbol']: r['short_pct_float'] for r in rows}

        # Sector ETF returns (by sector name → ETF ticker)
        rows = conn.execute("""
            SELECT etf, sector, pct_change FROM sector_etf_daily_returns
            WHERE date = (SELECT MAX(date) FROM sector_etf_daily_returns)
        """).fetchall()
        sector_returns_by_name = {r['sector']: r['pct_change'] for r in rows if r['sector']}
        spy_return = next((r['pct_change'] for r in rows if r['etf'] == 'SPY'), 0)

        conn.close()

        # Merge into candidates
        for c in candidates:
            sym = c['symbol']

            if sym in analyst:
                c['bull_score'] = analyst[sym].get('bull_score')
                c['upside_pct'] = analyst[sym].get('upside_pct')

            if sym in news:
                n = news[sym]
                c['avg_news_sentiment'] = n.get('avg_news_sentiment')
                c['news_count'] = n.get('news_count')
                pos = n.get('news_pos', 0) or 0
                neg = n.get('news_neg', 0) or 0
                c['news_pos_ratio'] = pos / (pos + neg) if (pos + neg) > 0 else None

            if sym in options:
                c['put_call_ratio'] = options[sym].get('put_call_ratio')

            # Sector 1d change — map stock sector name to ETF return
            stock_sector = c.get('sector', '')
            c['sector_1d_change'] = sector_returns_by_name.get(stock_sector, spy_return)

            # Earnings proximity
            if sym in earnings:
                c['days_to_earnings'] = earnings[sym]

            # Short interest
            if sym in short_data:
                c['short_pct_float'] = short_data[sym]

    # v5.1: Dynamic sector selection — replaces static CRISIS_DEFENSIVE
    # Based on 51K signal analysis: crude_5d_chg is #1 predictor of per-sector
    # crisis returns (IC=-0.209). Different crisis types have different winners.
    #
    # Crisis type classification:
    #   Energy crisis (crude spike >5%): Only Basic Materials + Utilities survive
    #   Moderate crude stress (3-5%): Block Tech, Comms, Consumer Cyc, Healthcare
    #   General panic (VIX spike, crude not spiking): ALL sectors profitable (mean reversion)
    #   VIX backwardation + crude falling: Aggressive — all sectors, Tech best (+3.6%)
    ALL_SECTORS = frozenset({
        'Technology', 'Healthcare', 'Financial Services', 'Consumer Cyclical',
        'Consumer Defensive', 'Industrials', 'Energy', 'Utilities',
        'Basic Materials', 'Real Estate', 'Communication Services',
    })
    # Sectors that get destroyed when crude spikes (IC < -0.25 with crude_5d_chg)
    CRUDE_SENSITIVE = frozenset({
        'Technology', 'Communication Services', 'Consumer Cyclical', 'Healthcare',
    })

    @staticmethod
    def _get_crisis_sectors(macro: dict) -> frozenset:
        """Dynamic sector selection for CRISIS regime based on macro signals.

        Uses crude_5d_chg (IC=-0.209) and vix_term_spread to classify crisis type
        and select appropriate sectors. Replaces static CRISIS_DEFENSIVE.

        Returns frozenset of allowed sector names.
        """
        crude_5d = macro.get('crude_delta_5d_pct') or 0
        vix_spread = macro.get('vix_term_spread') or 0  # vix - vix3m, positive = backwardation

        # Energy crisis: crude spiking hard → only commodity-linked survive
        if crude_5d > 5:
            return frozenset({'Basic Materials', 'Utilities'})

        # Moderate crude stress: block crude-sensitive sectors
        if crude_5d > 3:
            return DiscoveryEngine.ALL_SECTORS - DiscoveryEngine.CRUDE_SENSITIVE

        # VIX backwardation (peak fear) + crude NOT spiking → broad mean reversion
        if vix_spread > 2 and crude_5d <= 0:
            return DiscoveryEngine.ALL_SECTORS

        # General panic (crude flat/falling) → all sectors bounce
        if crude_5d <= 0:
            return DiscoveryEngine.ALL_SECTORS

        # Mild crude rise (0-3%) → slightly defensive, drop worst performers
        return DiscoveryEngine.ALL_SECTORS - frozenset({'Communication Services'})

    @staticmethod
    def _get_stress_sectors(macro: dict) -> frozenset:
        """Dynamic sector selection for STRESS regime.

        More permissive than CRISIS — only restrict in energy stress.
        """
        crude_5d = macro.get('crude_delta_5d_pct') or 0

        if crude_5d > 5:
            return DiscoveryEngine.ALL_SECTORS - DiscoveryEngine.CRUDE_SENSITIVE

        return DiscoveryEngine.ALL_SECTORS

    def _score_v3(self, candidates: list, macro: dict, scan_date: str, v3_cfg: dict, refit: bool = True) -> list[DiscoveryPick]:
        """v5.1: Regime-Adaptive dual-kernel scoring with dynamic sector selection.

        Stage 1: Macro kernel → E[R] → regime (BULL/STRESS/CRISIS)
        Stage 2: Stock kernel → per-stock E[R] → rank within regime rules

        Regime rules:
          BULL   (E[R]>0.5%):  top 5, stock kernel rank, SL=3%
          STRESS (-0.5-0.5%):  top 3, defensive filter (bonus>=2) + stock kernel, SL=2%
          CRISIS (<-0.5%):     top 2, capitulation filter (bonus>=3) + stock kernel, SL=2%

        v5.1: Dynamic sector selection replaces static CRISIS_DEFENSIVE.
          Uses crude_5d_chg (IC=-0.209) to classify crisis type:
          - Energy crisis (crude>5%): Basic Materials + Utilities only
          - Moderate crude (3-5%): Block Tech, Comms, Consumer Cyc, Healthcare
          - General panic (crude<=0): ALL sectors allowed (mean reversion)

        Args:
            refit: If True, reload training data and refit kernels. False for intraday
                   scans that reuse evening-fitted kernels.
        """
        # Refit both kernels (skip for intraday — reuse evening fit)
        if refit:
            self.kernel.load_and_fit()
            if self.stock_kernel:
                self.stock_kernel.load_and_fit()

        tp_pct = v3_cfg.get('tp_pct', 3.0)
        tp2_mult = v3_cfg.get('tp2_multiplier', 2.0)
        tp2_pct = tp_pct * tp2_mult

        # --- Stage 1: Macro kernel → regime detection ---
        from discovery.kernel_estimator import MIN_N_EFF
        macro_candidate = {
            'new_52w_lows': macro.get('new_52w_lows'),
            'crude_change_5d': macro.get('crude_delta_5d_pct'),
            'pct_above_20d_ma': macro.get('pct_above_20d_ma'),
            'new_52w_highs': macro.get('new_52w_highs'),
            'yield_10y': macro.get('yield_10y'),
            'spy_close': macro.get('spy_close'),
            'crude_close': macro.get('crude_close'),               # v5.0
            'vix_term_spread': macro.get('vix_term_spread'),       # v5.0
        }
        macro_er, se, n_eff = self.kernel.estimate(macro_candidate)

        if n_eff < MIN_N_EFF:
            logger.warning("Discovery v4.4b: n_eff=%.1f < %.1f — insufficient data", n_eff, MIN_N_EFF)
            return []

        # Determine regime
        regime_cfg = v3_cfg.get('regimes', {})
        bull_threshold = regime_cfg.get('bull_er', 0.5)
        stress_threshold = regime_cfg.get('stress_er', -0.5)

        if macro_er > bull_threshold:
            regime = 'BULL'
            sl_pct = tp_pct  # SL = TP = 3%
        elif macro_er > stress_threshold:
            regime = 'STRESS'
            sl_pct = regime_cfg.get('stress_sl_pct', 2.0)
        else:
            regime = 'CRISIS'
            sl_pct = regime_cfg.get('crisis_sl_pct', 2.0)

        self._current_regime = regime

        # v5.1: Dynamic sector selection based on crisis type
        crisis_sectors = self._get_crisis_sectors(macro)
        stress_sectors = self._get_stress_sectors(macro)

        logger.info(
            "Discovery v5.2: E[R]=%+.2f%% regime=%s SL=%.1f%% | "
            "macro: lows=%s crude_chg=%s breadth=%s highs=%s y10=%s spy=%s crude=%s vix_spread=%s | "
            "sectors: %s",
            macro_er, regime, sl_pct,
            macro.get('new_52w_lows'), macro.get('crude_delta_5d_pct'),
            macro.get('pct_above_20d_ma'), macro.get('new_52w_highs'),
            macro.get('yield_10y'), macro.get('spy_close'),
            macro.get('crude_close'), macro.get('vix_term_spread'),
            'ALL' if crisis_sectors == self.ALL_SECTORS else ','.join(sorted(crisis_sectors)),
        )

        # --- Stage 2: Stock kernel ranking with regime-adaptive selection ---
        vix = macro.get('vix_close', 20) or 20
        use_stock_kernel = self.stock_kernel and self.stock_kernel._fitted

        scored = []
        for c in candidates:
            c['vix_at_signal'] = vix
            # Inject all macro features for StockKernel (v5.0)
            for k, v in macro_candidate.items():
                c[k] = v

            # Stock kernel E[R] (per-stock, varies by stock features)
            if use_stock_kernel:
                stock_er, _, stock_neff = self.stock_kernel.estimate(c)
                if stock_neff < MIN_N_EFF:
                    stock_er = 0.0
            else:
                stock_er = 0.0

            # Regime-specific filtering
            if regime == 'STRESS':
                # v5.1: Dynamic defensive filter
                atr = c.get('atr_pct') or 99
                mom5 = c.get('momentum_5d') or 0
                sector = c.get('sector') or ''
                bonus = 0
                if atr < 3.0:
                    bonus += 2
                elif atr < 4.0:
                    bonus += 1
                if mom5 < 0:
                    bonus += 1
                if sector in stress_sectors:
                    bonus += 2
                if bonus < 2:
                    continue  # skip non-defensive stocks in STRESS
                stock_er += bonus * 0.5

            elif regime == 'CRISIS':
                # v5.1: Dynamic crisis filter — sector selection based on crisis type
                atr = c.get('atr_pct') or 99
                mom5 = c.get('momentum_5d') or 0
                vol = c.get('volume_ratio') or 0
                sector = c.get('sector') or ''
                # Block overbought stocks in CRISIS
                if mom5 >= 0:
                    continue
                bonus = 0
                if mom5 < -5:
                    bonus += 2
                if vol > 1.0:
                    bonus += 1
                if atr < 3.0:
                    bonus += 1
                if sector in crisis_sectors:
                    bonus += 2
                if bonus < 3:
                    continue  # skip non-capitulation stocks in CRISIS
                stock_er += bonus * 0.5

            # v4.4: never pick stocks with negative E[R]
            if stock_er < 0:
                continue

            scored.append((stock_er, c))

        scored.sort(key=lambda x: x[0], reverse=True)

        # v5.2: Elite filter — keep only statistical outliers (mean + k*σ)
        # Backtested on 39K signals: k=1.5 → 2-3 picks/day, WR=58.2%, ret=+1.87%
        # (vs no filter: 37/day, WR=54.1%, ret=+0.30%)
        # Fallback: if all filtered out, keep top 1
        elite_k = regime_cfg.get('elite_sigma', 1.5)
        pre_elite = len(scored)
        if len(scored) >= 3:
            ers = np.array([e for e, _ in scored])
            elite_threshold = ers.mean() + elite_k * ers.std()
            elite = [(e, c) for e, c in scored if e >= elite_threshold]
            scored = elite if elite else scored[:1]

        logger.info("Discovery v5.2: %d→%d elite picks [%s] (mean+%.1fσ)", pre_elite, len(scored), regime, elite_k)

        # Dynamic ATR-based SL config (v4.5)
        dsl_cfg = self._config.get('dynamic_sl', {})
        dsl_enabled = dsl_cfg.get('enabled', False)
        dsl_mult = {
            'BULL': dsl_cfg.get('bull_mult', 2.0),
            'STRESS': dsl_cfg.get('stress_mult', 1.5),
            'CRISIS': dsl_cfg.get('crisis_mult', 1.0),
        }
        dsl_floor = dsl_cfg.get('floor', 1.5)
        dsl_cap = dsl_cfg.get('cap', 5.0)

        # v5.3 Smart TP config — ATR-adaptive ratio
        stp_cfg = v3_cfg.get('smart_tp', {})
        stp_gap_threshold = stp_cfg.get('gap_threshold', 0.5)
        stp_gap_boost = stp_cfg.get('gap_boost', 1.3)

        # Limit-buy config (v4.6)
        lb_cfg = self._config.get('limit_buy', {})
        lb_enabled = lb_cfg.get('enabled', False)
        lb_pullback_mult = lb_cfg.get('pullback_atr_mult', 0.3)
        lb_max_atr = lb_cfg.get('max_atr_pct', 3.5)
        lb_sl_pct = lb_cfg.get('sl_pct', 2.5)

        # v5.3: Market breadth for divergence signal
        breadth = macro.get('pct_above_20d_ma') or 50

        picks = []
        for stock_er, c in scored:
            price = c['close']
            atr = c.get('atr_pct', 0) or 0
            raw_er = stock_er

            # v5.3: D0 close position filter — remove weak candles
            # D0 close near low = stock weak, WR=34% → skip
            # D0 close near high = momentum, WR=70% → keep
            d0_high = c.get('day_high') or c.get('high') or price
            d0_low = c.get('day_low') or c.get('low') or price
            d0_range = d0_high - d0_low
            if d0_range > 0:
                d0_close_pos = (price - d0_low) / d0_range
            else:
                d0_close_pos = 0.5
            c['d0_close_position'] = round(d0_close_pos, 2)

            # Filter: skip weak D0 candles + overly volatile stocks
            if d0_close_pos < 0.3:
                continue
            # ATR > 5%: SL cap=5% can't protect → SL hit > TP hit for swing
            # Exception: Friday → allow through for weekend play (hold 1 day only)
            is_friday = datetime.now(ZoneInfo('America/New_York')).weekday() == 4
            if atr > 5.0 and not is_friday:
                continue
            c['_weekend_only'] = atr > 5.0  # mark for UI

            # v5.3: Divergence boost — stock UP while market weak
            d0_ret = ((price / c.get('open', price)) - 1) * 100 if c.get('open') else 0
            if d0_ret > 0.5 and breadth < 40:
                stock_er += 0.5  # boost E[R] for strong-in-weak-market
                c['divergence_boost'] = True

            # Limit-buy: SL = max(config SL, 1×ATR) — never tighter than daily range
            if lb_enabled and atr < lb_max_atr:
                pick_sl_pct = round(max(lb_sl_pct, atr), 1)
                pick_limit_pct = round(lb_pullback_mult * atr, 2)
            else:
                # Dynamic ATR-based SL: SL = clamp(mult[regime] × ATR, floor, cap)
                if dsl_enabled and atr > 0:
                    pick_sl_pct = max(dsl_floor, min(dsl_cap, dsl_mult[regime] * atr))
                    pick_sl_pct = round(pick_sl_pct, 1)
                else:
                    pick_sl_pct = sl_pct
                pick_limit_pct = None

            # v5.3 Smart TP: regime-based ratio (validated 2022-2025)
            # BULL: 1.0×ATR (ride winners, E[R]=+0.10%, stable 2023-2025)
            # STRESS: 0.75×ATR (moderate)
            # CRISIS: 0.5×ATR (mean reversion, best in 2022 bear)
            tp_ratios = stp_cfg.get('tp_regime_ratios', {'BULL': 1.0, 'STRESS': 0.75, 'CRISIS': 0.5})
            tp_ratio = tp_ratios.get(regime, 0.75)
            pick_tp_pct = round(max(0.5, tp_ratio * atr), 1)
            pick_tp2_pct = pick_tp_pct

            sl_price = price * (1 - pick_sl_pct / 100)
            tp1_price = price * (1 + pick_tp_pct / 100)
            tp2_price = price * (1 + pick_tp2_pct / 100)

            logger.info(
                "Discovery v5.2 [%s]: %s sER=%+.2f%% TP=%.1f%% SL=%.1f%% "
                "atr=%.1f vol=%.2f mom5d=%.1f sector=%s",
                regime, c['symbol'], stock_er, pick_tp_pct, pick_sl_pct,
                c.get('atr_pct', 0),
                c.get('volume_ratio', 0) or 0, c.get('momentum_5d', 0) or 0,
                c.get('sector', ''),
            )

            pick = DiscoveryPick(
                symbol=c['symbol'], scan_date=scan_date, scan_price=price,
                current_price=price, layer2_score=round(stock_er, 2),
                beta=c.get('beta', 0), atr_pct=c.get('atr_pct', 0),
                distance_from_high=c.get('distance_from_high', 0),
                distance_from_20d_high=c.get('distance_from_20d_high', 0),
                rsi=c.get('rsi', 0), momentum_5d=c.get('momentum_5d', 0),
                momentum_20d=c.get('momentum_20d', 0),
                volume_ratio=c.get('volume_ratio', 0),
                sl_price=round(sl_price, 2), sl_pct=round(pick_sl_pct, 1),
                tp1_price=round(tp1_price, 2), tp1_pct=round(pick_tp_pct, 1),
                tp2_price=round(tp2_price, 2), tp2_pct=round(pick_tp2_pct, 1),
                expected_gain=round(macro_er, 2),
                rr_ratio=round(pick_tp_pct / pick_sl_pct, 2) if pick_sl_pct > 0 else 0,
                limit_pct=pick_limit_pct,
                entry_status='pending' if pick_limit_pct else 'filled',
                sector=c.get('sector', ''), market_cap=c.get('market_cap', 0),
                vix_close=macro.get('vix_close', 0),
                pct_above_20d_ma=macro.get('pct_above_20d_ma', 0),
                vix_term_structure=c.get('vix_term_structure', 0),
                new_52w_highs=c.get('new_52w_highs', 0),
                bull_score=c.get('bull_score'),
                news_count=c.get('news_count', 0),
                news_pos_ratio=c.get('news_pos_ratio'),
                highs_lows_ratio=c.get('highs_lows_ratio', 0),
                ad_ratio=c.get('ad_ratio', 0),
                mcap_log=c.get('mcap_log', 0),
                sector_1d_change=c.get('sector_1d_change', 0),
                vix3m_close=c.get('vix3m_close', 0),
                upside_pct=c.get('upside_pct'),
                days_to_earnings=c.get('days_to_earnings'),
                put_call_ratio=c.get('put_call_ratio'),
                short_pct_float=c.get('short_pct_float'),
                breadth_delta_5d=macro.get('breadth_delta_5d'),
                vix_delta_5d=macro.get('vix_delta_5d'),
                crude_close=macro.get('crude_close'),
                gold_close=macro.get('gold_close'),
                dxy_delta_5d=macro.get('dxy_delta_5d'),
                stress_score=macro.get('stress_score'),
            )

            # v5.2: P(TP hit) timeline for UI
            timeline = self.predict_tp_timeline(
                atr, c.get('volume_ratio') or 1, pick_tp_pct, pick_sl_pct,
                stock_er=stock_er, mom5=c.get('momentum_5d') or 0,
                d20h=c.get('distance_from_20d_high') or -5)
            if timeline:
                pick.tp_timeline = timeline

            # v5.2: Weekend play — Friday→Monday prediction
            is_friday = datetime.now(ZoneInfo('America/New_York')).weekday() == 4
            if is_friday and self._weekend_data:
                weekend = self.predict_weekend(
                    atr, c.get('volume_ratio') or 1, c.get('momentum_5d') or 0,
                    c.get('distance_from_20d_high') or -5, macro.get('vix_close') or 20,
                )
                if weekend:
                    pick.weekend_play = weekend

            # v6.0: Ensemble score — combine kernel + temporal + sequence + leading
            try:
                cal_conf = self._calibrator.compute_confidence()
                ensemble_result = self._ensemble.score(
                    kernel_er=stock_er,
                    temporal_features=self._temporal_features,
                    sequence_prediction=self._sequence_prediction,
                    leading_signals=self._leading_signals,
                    calibrator_confidence=cal_conf.get('confidence', 50),
                )
                pick.ensemble = ensemble_result
            except Exception as e:
                logger.error("Discovery v6.0: ensemble score error for %s: %s", c['symbol'], e)
                pick.ensemble = None

            picks.append(pick)

        logger.info(
            "Discovery v4.3: %d picks [%s] (macro E[R]=%+.2f%%, SL=%.1f%%, from %d candidates)",
            len(picks), regime, macro_er, sl_pct, len(candidates),
        )
        return picks

    def _score_v2(self, candidates: list, macro: dict, scan_date: str,
                   qg: dict, tp_sl_cfg: dict, adaptive_min_score: float) -> list[DiscoveryPick]:
        """v2: IC-weighted composite score + quality gates + smart TP/SL (fallback)."""
        min_sector_1d = qg.get('min_sector_1d_change', 0.0)
        min_mom20d = qg.get('min_momentum_20d', 0.0)
        mom5d_rej_lo = qg.get('momentum_5d_reject_low', 0.0)
        mom5d_rej_hi = qg.get('momentum_5d_reject_high', 3.0)
        mom5d_max = qg.get('momentum_5d_max', 10.0)
        min_vol = qg.get('min_volume_ratio', 0.4)

        tp_atr_mult = tp_sl_cfg.get('tp_atr_mult', 1.20)
        tp_floor = tp_sl_cfg.get('tp_floor', 2.5)
        sl_atr_mult = tp_sl_cfg.get('sl_atr_mult', 0.80)
        sl_floor = tp_sl_cfg.get('sl_floor', 2.0)
        tp2_mult = tp_sl_cfg.get('tp2_multiplier', 2.0)

        picks = []
        for c in candidates:
            score = self.scorer.compute_layer2_score(c)
            if score < adaptive_min_score:
                continue

            mom5d = c.get('momentum_5d', 0) or 0
            mom20d = c.get('momentum_20d', 0) or 0
            vol_ratio = c.get('volume_ratio', 0) or 0
            sector_1d = c.get('sector_1d_change')

            if sector_1d is None or sector_1d <= min_sector_1d:
                continue
            if mom20d <= min_mom20d:
                continue
            if mom5d_rej_lo <= mom5d < mom5d_rej_hi:
                continue
            if mom5d >= mom5d_max:
                continue
            if vol_ratio < min_vol:
                continue

            price = c['close']
            atr_pct = c.get('atr_pct', 2.0)
            tp_pct = max(tp_floor, tp_atr_mult * atr_pct)
            sl_pct = max(sl_floor, sl_atr_mult * atr_pct)
            tp2_pct = tp_pct * tp2_mult

            pick = DiscoveryPick(
                symbol=c['symbol'], scan_date=scan_date, scan_price=price,
                current_price=price, layer2_score=score,
                beta=c.get('beta', 0), atr_pct=c['atr_pct'],
                distance_from_high=c.get('distance_from_high', 0),
                distance_from_20d_high=c.get('distance_from_20d_high', 0),
                rsi=c.get('rsi', 0), momentum_5d=c.get('momentum_5d', 0),
                momentum_20d=c.get('momentum_20d', 0),
                volume_ratio=c.get('volume_ratio', 0),
                sl_price=round(price * (1 - sl_pct / 100), 2), sl_pct=round(sl_pct, 1),
                tp1_price=round(price * (1 + tp_pct / 100), 2), tp1_pct=round(tp_pct, 1),
                tp2_price=round(price * (1 + tp2_pct / 100), 2), tp2_pct=round(tp2_pct, 1),
                expected_gain=round(tp_pct, 1),
                rr_ratio=round(tp_pct / sl_pct, 2) if sl_pct > 0 else 0,
                sector=c.get('sector', ''), market_cap=c.get('market_cap', 0),
                vix_close=macro.get('vix_close', 0),
                pct_above_20d_ma=macro.get('pct_above_20d_ma', 0),
                vix_term_structure=c.get('vix_term_structure', 0),
                new_52w_highs=c.get('new_52w_highs', 0),
                bull_score=c.get('bull_score'),
                news_count=c.get('news_count', 0),
                news_pos_ratio=c.get('news_pos_ratio'),
                highs_lows_ratio=c.get('highs_lows_ratio', 0),
                ad_ratio=c.get('ad_ratio', 0),
                mcap_log=c.get('mcap_log', 0),
                sector_1d_change=c.get('sector_1d_change', 0),
                vix3m_close=c.get('vix3m_close', 0),
                upside_pct=c.get('upside_pct'),
                days_to_earnings=c.get('days_to_earnings'),
                put_call_ratio=c.get('put_call_ratio'),
                short_pct_float=c.get('short_pct_float'),
                breadth_delta_5d=macro.get('breadth_delta_5d'),
                vix_delta_5d=macro.get('vix_delta_5d'),
                crude_close=macro.get('crude_close'),
                gold_close=macro.get('gold_close'),
                dxy_delta_5d=macro.get('dxy_delta_5d'),
                stress_score=macro.get('stress_score'),
            )
            picks.append(pick)

        picks.sort(key=lambda p: p.layer2_score, reverse=True)
        logger.info(f"Discovery v2: {len(picks)} picks passed L2 (score >= {adaptive_min_score:.0f})")
        return picks

    def _save_picks(self, picks: list[DiscoveryPick], scan_date: str):
        """Save picks to DB with all L2 features for future calibration."""
        conn = sqlite3.connect(str(DB_PATH))
        for p in picks:
            conn.execute("""
                INSERT OR REPLACE INTO discovery_picks
                (scan_date, symbol, scan_price, current_price, layer2_score,
                 beta, atr_pct, distance_from_high, distance_from_20d_high, rsi, momentum_5d, momentum_20d, volume_ratio,
                 sl_price, sl_pct, tp1_price, tp1_pct, tp2_price, tp2_pct,
                 expected_gain, rr_ratio,
                 sector, market_cap, vix_close, pct_above_20d_ma, status,
                 vix_term_structure, new_52w_highs, bull_score, news_count, news_pos_ratio,
                 highs_lows_ratio, ad_ratio, mcap_log, sector_1d_change, vix3m_close, upside_pct,
                 days_to_earnings, put_call_ratio, short_pct_float,
                 breadth_delta_5d, vix_delta_5d, crude_close, gold_close, dxy_delta_5d, stress_score,
                 premarket_price, gap_pct, scan_type,
                 limit_entry_price, limit_pct, entry_price, entry_status, entry_filled_at,
                 tp_timeline_json, weekend_play_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (p.scan_date, p.symbol, p.scan_price, p.current_price, p.layer2_score,
                  p.beta, p.atr_pct, p.distance_from_high, p.distance_from_20d_high, p.rsi, p.momentum_5d,
                  p.momentum_20d, p.volume_ratio,
                  p.sl_price, p.sl_pct, p.tp1_price, p.tp1_pct, p.tp2_price, p.tp2_pct,
                  p.expected_gain, p.rr_ratio,
                  p.sector, p.market_cap, p.vix_close, p.pct_above_20d_ma, p.status,
                  p.vix_term_structure, p.new_52w_highs, p.bull_score, p.news_count,
                  p.news_pos_ratio, p.highs_lows_ratio, p.ad_ratio, p.mcap_log,
                  p.sector_1d_change, p.vix3m_close, p.upside_pct,
                  p.days_to_earnings, p.put_call_ratio, p.short_pct_float,
                  p.breadth_delta_5d, p.vix_delta_5d, p.crude_close, p.gold_close,
                  p.dxy_delta_5d, p.stress_score,
                  p.premarket_price, p.gap_pct, p.scan_type,
                  p.limit_entry_price, p.limit_pct, p.entry_price, p.entry_status, p.entry_filled_at,
                  json.dumps(getattr(p, 'tp_timeline', None)),
                  json.dumps(getattr(p, 'weekend_play', None))))
        conn.commit()
        conn.close()
        logger.info(f"Discovery: saved {len(picks)} picks for {scan_date}")

    def _deactivate_previous_picks(self, new_scan_date: str):
        """Deactivate ALL active picks before saving new scan results."""
        conn = sqlite3.connect(str(DB_PATH))
        n = conn.execute("""
            UPDATE discovery_picks SET status = 'replaced', updated_at = datetime('now')
            WHERE status = 'active'
        """).rowcount
        conn.commit()
        conn.close()
        if n:
            logger.info(f"Discovery: deactivated {n} previous picks")

    def _expire_old_picks(self, current_date: str):
        """Expire picks older than max_pick_age_days.
        Also marks unfilled limit orders as 'missed' after max_hold_days.
        """
        max_age = self._config.get('schedule', {}).get('max_pick_age_days', 5)
        lb_cfg = self._config.get('limit_buy', {})
        max_hold = lb_cfg.get('max_hold_days', 2)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            UPDATE discovery_picks SET status = 'expired', updated_at = datetime('now')
            WHERE status = 'active' AND julianday(?) - julianday(scan_date) > ?
        """, (current_date, max_age))
        # Mark unfilled limit orders as 'missed' after max_hold_days
        if lb_cfg.get('enabled', False):
            conn.execute("""
                UPDATE discovery_picks SET entry_status = 'missed', updated_at = datetime('now')
                WHERE status = 'active' AND entry_status = 'pending'
                AND julianday(?) - julianday(scan_date) > ?
            """, (current_date, max_hold))
        conn.commit()
        conn.close()

    # --- State getters (v4.5) ---

    def get_last_validation(self) -> Optional[str]:
        return self._last_validation

    def get_last_intraday_scan(self) -> Optional[str]:
        return self._last_intraday_scan

    def get_current_regime(self) -> Optional[str]:
        return self._current_regime

    def get_confidence(self) -> dict:
        """Get calibrator confidence score and diagnostics."""
        try:
            return self._calibrator.compute_confidence()
        except Exception as e:
            logger.error(f"Discovery: calibrator error: {e}")
            return {'confidence': 50, 'error': str(e)}

    def get_outcome_tracker(self) -> OutcomeTracker:
        return self._outcome_tracker

    def get_calibrator(self) -> Calibrator:
        return self._calibrator

    # --- Pre-market validation (v4.5) ---

    def validate_premarket(self) -> dict:
        """Validate active picks against pre-market prices.

        Fetches pre-market data via yfinance (prepost=True), computes gap_pct
        (premarket_price / scan_price - 1), and updates DB.
        Returns summary: {confirmed: N, unconfirmed: N, total: N}.
        """
        self._load_picks_from_db()
        active = [p for p in self._picks if p.status == 'active']
        if not active:
            logger.info("Discovery premarket: no active picks to validate")
            return {'confirmed': 0, 'unconfirmed': 0, 'total': 0}

        symbols = [p.symbol for p in active]
        logger.info(f"Discovery premarket: validating {len(symbols)} picks: {symbols}")

        try:
            import yfinance as yf
            data = yf.download(
                ' '.join(symbols), period='5d', interval='1h',
                prepost=True, auto_adjust=True, progress=False, threads=False,
            )
        except Exception as e:
            logger.error(f"Discovery premarket: yfinance error: {e}")
            return {'confirmed': 0, 'unconfirmed': 0, 'total': len(active), 'error': str(e)}

        if data.empty:
            logger.warning("Discovery premarket: no data returned")
            return {'confirmed': 0, 'unconfirmed': 0, 'total': len(active)}

        from datetime import time as dtime
        today = datetime.now(ZoneInfo('America/New_York')).date()
        threshold = self._config.get('schedule', {}).get('gap_confirm_threshold', 0.0)

        confirmed = 0
        unconfirmed = 0
        conn = sqlite3.connect(str(DB_PATH))

        for pick in active:
            try:
                # Extract this symbol's data
                if len(symbols) == 1:
                    sym_data = data
                else:
                    if pick.symbol not in data.columns.get_level_values(1):
                        continue
                    sym_data = data.xs(pick.symbol, axis=1, level=1)

                close_col = sym_data['Close'].dropna()
                if close_col.empty:
                    continue

                # Filter pre-market bars: before 9:30 ET on today
                premarket_bars = close_col[
                    (close_col.index.date == today) &
                    (close_col.index.time < dtime(9, 30))
                ]

                if premarket_bars.empty:
                    # Fallback: use latest available price
                    pm_price = float(close_col.iloc[-1])
                else:
                    pm_price = float(premarket_bars.iloc[-1])

                gap = (pm_price / pick.scan_price - 1) * 100 if pick.scan_price > 0 else 0.0
                pick.premarket_price = pm_price
                pick.gap_pct = round(gap, 2)

                if gap >= threshold:
                    confirmed += 1
                else:
                    unconfirmed += 1

                # v5.2 Smart TP gap boost: widen TP if D1 gap confirms momentum
                stp_cfg = self._config.get('v3', {}).get('smart_tp', {})
                gap_thresh = stp_cfg.get('gap_threshold', 0.5)
                gap_boost_mult = stp_cfg.get('gap_boost', 1.3)
                old_tp = pick.tp1_pct

                if gap >= gap_thresh and old_tp > 0:
                    new_tp = round(old_tp * gap_boost_mult, 1)
                    pick.tp1_pct = new_tp
                    pick.tp2_pct = new_tp  # single TP
                    entry_ref = pick.limit_entry_price if pick.limit_entry_price else pick.scan_price
                    if entry_ref and entry_ref > 0:
                        pick.tp1_price = round(entry_ref * (1 + new_tp / 100), 2)
                        pick.tp2_price = pick.tp1_price

                # Limit-buy (v4.6): compute limit_entry_price from pre-market
                lb_cfg = self._config.get('limit_buy', {})
                if lb_cfg.get('enabled', False) and pick.limit_pct is not None:
                    limit_price = round(pm_price * (1 - pick.limit_pct / 100), 2)
                    pick.limit_entry_price = limit_price
                    lb_sl = lb_cfg.get('sl_pct', 2.5)
                    pick.sl_price = round(limit_price * (1 - lb_sl / 100), 2)
                    pick.sl_pct = round(lb_sl, 1)
                    # Recalculate TP prices from limit entry
                    pick.tp1_price = round(limit_price * (1 + pick.tp1_pct / 100), 2)
                    pick.tp2_price = pick.tp1_price

                conn.execute(
                    "UPDATE discovery_picks SET premarket_price=?, gap_pct=?, "
                    "limit_entry_price=?, sl_price=?, sl_pct=?, tp1_price=?, tp1_pct=?, "
                    "tp2_price=?, tp2_pct=?, updated_at=datetime('now') "
                    "WHERE symbol=? AND scan_date=? AND status='active'",
                    (pm_price, pick.gap_pct,
                     getattr(pick, 'limit_entry_price', None),
                     pick.sl_price, pick.sl_pct, pick.tp1_price, pick.tp1_pct,
                     pick.tp2_price, pick.tp2_pct,
                     pick.symbol, pick.scan_date),
                )

                gap_tag = ''
                if gap >= gap_thresh:
                    gap_tag = f' GAP_BOOST TP {old_tp}→{pick.tp1_pct}%'
                logger.info(
                    "Discovery premarket: %s gap=%+.2f%% pm=$%.2f TP=%.1f%% SL=%.1f%%%s → %s",
                    pick.symbol, gap, pm_price, pick.tp1_pct, pick.sl_pct, gap_tag,
                    'CONFIRMED' if gap >= threshold else 'UNCONFIRMED',
                )
            except Exception as e:
                logger.debug(f"Discovery premarket: error for {pick.symbol}: {e}")
                continue

        conn.commit()
        conn.close()

        self._last_validation = datetime.now().strftime('%Y-%m-%d %H:%M')
        summary = {'confirmed': confirmed, 'unconfirmed': unconfirmed, 'total': len(active)}
        logger.info(f"Discovery premarket: {summary}")
        return summary

    # --- Intraday re-scan (v4.5) ---

    def _enrich_candidates_lite(self, candidates: list):
        """Lightweight enrichment for intraday scans.

        Only adds: sector ETF 1d returns + earnings proximity.
        Skips: analyst, news, options, short interest (slow DB queries).
        """
        if not candidates:
            return

        symbols = [c['symbol'] for c in candidates]
        placeholders = ','.join('?' * len(symbols))
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Earnings proximity
        today_str = date.today().isoformat()
        rows = conn.execute(f"""
            SELECT symbol, MIN(report_date) as next_date
            FROM earnings_history
            WHERE symbol IN ({placeholders}) AND report_date >= ?
            GROUP BY symbol
        """, symbols + [today_str]).fetchall()
        earnings = {}
        for r in rows:
            try:
                ed = datetime.strptime(r['next_date'][:10], '%Y-%m-%d').date()
                earnings[r['symbol']] = (ed - date.today()).days
            except Exception:
                pass

        # Sector ETF returns
        rows = conn.execute("""
            SELECT etf, sector, pct_change FROM sector_etf_daily_returns
            WHERE date = (SELECT MAX(date) FROM sector_etf_daily_returns)
        """).fetchall()
        sector_returns_by_name = {r['sector']: r['pct_change'] for r in rows if r['sector']}
        spy_return = next((r['pct_change'] for r in rows if r['etf'] == 'SPY'), 0)

        conn.close()

        for c in candidates:
            sym = c['symbol']
            stock_sector = c.get('sector', '')
            c['sector_1d_change'] = sector_returns_by_name.get(stock_sector, spy_return)
            if sym in earnings:
                c['days_to_earnings'] = earnings[sym]

    def run_intraday_scan(self) -> list[DiscoveryPick]:
        """Lightweight intraday re-scan: reuse evening kernels, shorter data, lite enrichment.

        1. Re-rank existing evening picks with fresh prices
        2. Find up to N new intraday discoveries
        Does NOT deactivate evening picks.
        """
        sched = self._config.get('schedule', {})
        if not sched.get('intraday_scan_enabled', False):
            logger.info("Discovery intraday: disabled in config")
            return []

        scan_date = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
        intraday_period = sched.get('intraday_period', '1mo')
        max_new = sched.get('intraday_max_new_picks', 3)

        logger.info(f"Discovery intraday scan starting for {scan_date}")

        # Must have fitted kernels from evening scan
        if not self._v3_enabled or not self.kernel:
            if self._v3_config_enabled:
                self._init_kernel()
            if not self._v3_enabled:
                logger.warning("Discovery intraday: kernel not ready, skipping")
                return []

        # 1. Load universe + macro (macro = yesterday EOD, correct for intraday)
        stocks = self._load_universe()
        macro = self._load_macro(scan_date)

        # 2. Fetch stock data with shorter period (1mo vs 1y)
        candidates = []
        batch_size = 50
        symbols = list(stocks.keys())

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            batch_str = ' '.join(batch)
            batch_num = i // batch_size + 1

            try:
                import yfinance as yf
                data = yf.download(batch_str, period=intraday_period, interval='1d',
                                   auto_adjust=True, progress=False, threads=False)
            except Exception as e:
                logger.error(f"Discovery intraday: yfinance batch error: {e}")
                continue

            for sym in batch:
                try:
                    if len(batch) == 1:
                        df = data
                    else:
                        df = data.xs(sym, axis=1, level=1) if sym in data.columns.get_level_values(1) else None

                    if df is None or df.empty or len(df) < 20:
                        continue

                    features = self._compute_technical(df, sym, stocks.get(sym, {}))
                    if features is None:
                        continue

                    features.update(macro)
                    candidates.append(features)
                except Exception as e:
                    logger.debug(f"Discovery intraday: error processing {sym}: {e}")
                    continue

            if i + batch_size < len(symbols):
                time.sleep(1)

        logger.info(f"Discovery intraday: {len(candidates)} candidates from {len(symbols)} universe")

        # 3. Lite enrichment (sector ETF + earnings only)
        self._enrich_candidates_lite(candidates)

        # 4. Score with refit=False (reuse evening kernels)
        v3_cfg = self._config.get('v3', {})
        picks = self._score_v3(candidates, macro, scan_date, v3_cfg, refit=False)

        # 5. Merge: re-rank existing active picks + add new intraday discoveries
        #    Active picks may be from a previous scan_date (e.g. evening scan yesterday),
        #    so we check ALL active picks, not just today's.
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        existing_rows = conn.execute(
            "SELECT symbol FROM discovery_picks WHERE status='active'"
        ).fetchall()
        existing_symbols = {r['symbol'] for r in existing_rows}

        # Update scores for existing active picks (preserve gap_pct/premarket_price)
        re_ranked = 0
        for p in picks:
            if p.symbol in existing_symbols:
                conn.execute(
                    "UPDATE discovery_picks SET layer2_score=?, current_price=?, updated_at=datetime('now') "
                    "WHERE symbol=? AND status='active'",
                    (p.layer2_score, p.current_price, p.symbol),
                )
                re_ranked += 1

        # Commit re-rank UPDATEs before _save_picks (avoids SQLite lock contention)
        conn.commit()
        conn.close()

        # New intraday discoveries (not already active from any scan)
        new_intraday = [p for p in picks if p.symbol not in existing_symbols][:max_new]
        for p in new_intraday:
            p.scan_type = 'intraday'

        if new_intraday:
            self._save_picks(new_intraday, scan_date)

        # Reload all picks from DB
        self._load_picks_from_db()
        self._last_intraday_scan = datetime.now().strftime('%Y-%m-%d %H:%M')

        logger.info(
            "Discovery intraday: re-ranked %d evening picks, added %d new intraday picks",
            re_ranked, len(new_intraday),
        )
        return new_intraday


# Singleton
_engine: Optional[DiscoveryEngine] = None


def get_discovery_engine() -> DiscoveryEngine:
    global _engine
    if _engine is None:
        _engine = DiscoveryEngine()
    return _engine
