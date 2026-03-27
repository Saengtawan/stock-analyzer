"""
Unified Scorer — single scoring interface for all Discovery models.
Part of Discovery v13.0 Clean Architecture.

Wraps: KernelEstimator, StockKernelEstimator, UnifiedBrain, RegimeBrain,
       StockBrain, SensorNetwork, TemporalFeatureBuilder,
       SequencePatternMatcher, LeadingIndicatorEngine, StrategyRouter.

Provides: fit(), scan_setup(), score_batch(), predict_tp_timeline(),
          predict_weekend().
"""
import logging
import math
from database.orm.base import get_session
from sqlalchemy import text
import time
import numpy as np
from pathlib import Path
from typing import Optional

from discovery.kernel_estimator import KernelEstimator, StockKernelEstimator, MIN_N_EFF
from discovery.unified_brain import UnifiedBrain
from discovery.regime_brain import RegimeBrain
from discovery.stock_brain import StockBrain
from discovery.sensors import SensorNetwork
from discovery.temporal import TemporalFeatureBuilder
from discovery.sequence_matcher import SequencePatternMatcher
from discovery.leading_indicators import LeadingIndicatorEngine
from discovery.strategy_router import StrategyRouter

logger = logging.getLogger(__name__)


class UnifiedScorer:
    """Single scoring interface for all Discovery models."""

    def __init__(self, config, param_manager):
        self._config = config
        self._params = param_manager
        self._adaptive_params = None  # v17: wired from engine.__init__

        v3_cfg = config.get('v3', {})
        self._kernel_config_enabled = v3_cfg.get('enabled', False)
        self._kernel_ready = False

        # Kernel estimators
        self.kernel = None
        self.stock_kernel = None

        # ML brains
        self._regime_brain = RegimeBrain(
            trade_threshold=param_manager.get('arbiter', 'trade_threshold', 0.50))
        self._stock_brain = StockBrain()
        self._unified_brain = UnifiedBrain()

        # Feature builders
        self._sensors = SensorNetwork()
        self._temporal = TemporalFeatureBuilder()
        self._sequence_matcher = SequencePatternMatcher()
        self._leading_indicators = LeadingIndicatorEngine()
        self._strategy_router = StrategyRouter()  # adaptive_params wired in engine.__init__

        # Fitting state
        self._council_fitted = False
        self._v6_fitted = False

        # Hold kernel / weekend kernel state
        self._hold_data = None
        self._weekend_data = None
        self._smart_tp_coeffs = None
        self._advice_thresholds = {'risky': 1.0, 'caution': 1.2}
        self._advice_er_thresholds = {'buy': 0.3, 'hold': 0.05, 'caution': -0.1}
        self._weekend_wr_threshold = 55

        # Scan-level state (populated by scan_setup)
        self._temporal_features = {}
        self._leading_signals = {}
        self._regime_decision = {}
        self._current_strategy = {}
        self._current_regime = None

        # Init kernel if config says so
        if self._kernel_config_enabled:
            self._fit_kernel()

    # === Public properties ===

    @property
    def regime_brain(self):
        return self._regime_brain

    @property
    def stock_brain(self):
        return self._stock_brain

    @property
    def unified_brain(self):
        return self._unified_brain

    @property
    def is_ready(self):
        return self._kernel_ready

    @property
    def current_regime(self):
        return self._current_regime

    # === Fitting ===

    def _fit_kernel(self, v3_cfg=None):
        """Initialize or retry kernel estimators. Safe to call multiple times."""
        if self._kernel_ready:
            return True
        if v3_cfg is None:
            v3_cfg = self._config.get('v3', {})

        bw = v3_cfg.get('bandwidth', 1.0)
        stock_bw = v3_cfg.get('stock_bandwidth', 1.0)
        min_dates = v3_cfg.get('min_train_dates', 20)

        if self.kernel is None:
            self.kernel = KernelEstimator(bandwidth=bw, min_train_dates=min_dates)
        if self.stock_kernel is None:
            self.stock_kernel = StockKernelEstimator(
                bandwidth=stock_bw, min_train_dates=min_dates)

        if self.kernel.load_and_fit():
            stats = self.kernel.get_stats()
            logger.info("Scorer: macro kernel ready — %d rows, %d dates",
                        stats['n_rows'], stats['n_dates'])
            self.stock_kernel.load_and_fit()
            self._fit_hold_kernel()
            self._fit_models()
            self._kernel_ready = True
            return True

        logger.warning("Scorer: kernel fit failed, will retry next scan")
        return False

    def _fit_models(self):
        """Fit all ML models (v6.0+). Safe to call multiple times."""
        if not self._v6_fitted:
            try:
                ok = self._sequence_matcher.fit()
                if ok:
                    logger.info("Scorer: SequenceMatcher fitted (%d sequences)",
                                len(self._sequence_matcher._historical or []))
            except Exception as e:
                logger.error("Scorer: SequenceMatcher error: %s", e)

            try:
                ok = self._leading_indicators.fit()
                if ok:
                    logger.info("Scorer: LeadingIndicators fitted")
            except Exception as e:
                logger.error("Scorer: LeadingIndicators error: %s", e)

            self._v6_fitted = True

        # Regime brain
        if not self._council_fitted:
            rb_ok = False
            try:
                rb_ok = self._regime_brain.fit()
                if rb_ok:
                    logger.info("Scorer: RegimeBrain fitted (%d days)",
                                self._regime_brain._n_train)
            except Exception as e:
                logger.error("Scorer: RegimeBrain fit error: %s", e)
            try:
                sb_ok = self._stock_brain.fit()
                if sb_ok:
                    logger.info("Scorer: StockBrain fitted (%d signals)",
                                self._stock_brain._n_train)
            except Exception as e:
                logger.error("Scorer: StockBrain fit error: %s", e)
            if rb_ok:
                self._council_fitted = True

        # Unified brain
        if not self._unified_brain._fitted:
            try:
                self._unified_brain.fit()
                logger.info("Scorer: UnifiedBrain fitted (%d signals)",
                            self._unified_brain._n_train)
            except Exception as e:
                logger.error("Scorer: UnifiedBrain fit error: %s", e)

    def retry_kernel(self):
        """Retry kernel init if it failed previously."""
        if self._kernel_config_enabled and not self._kernel_ready:
            self._fit_kernel()

    # === Scan-level setup ===

    def scan_setup(self, scan_date, macro):
        """Per-scan setup: temporal, leading, regime, strategy.

        Returns dict with regime info for use by filter and sizer.
        """
        # Temporal features
        try:
            self._temporal_features = self._temporal.build_features(scan_date)
            logger.info("Scorer: temporal features built (%d)",
                        len(self._temporal_features))
        except Exception as e:
            logger.error("Scorer: temporal build error: %s", e)
            self._temporal_features = {}

        # Sequence prediction (market-level proven useless, skipped)
        # Stock profile matching still available via predict_stock_profile()

        # Leading signals
        try:
            self._leading_signals = self._leading_indicators.compute_signals(scan_date)
            logger.info("Scorer: leading signals: %s",
                        self._leading_signals.get('regime_forecast', {}).get('forecast', 'N/A'))
        except Exception as e:
            logger.error("Scorer: leading signals error: %s", e)
            self._leading_signals = {}

        # Regime Brain — should we trade today?
        try:
            macro_for_regime = dict(macro)
            macro_for_regime.update(self._temporal_features)
            self._regime_decision = self._regime_brain.predict(macro_for_regime)
            logger.info("Scorer: RegimeBrain → %s (conf=%.0f%% regime=%s)",
                        'TRADE' if self._regime_decision.get('trade_today') else 'SKIP',
                        self._regime_decision.get('confidence', 0),
                        self._regime_decision.get('regime', '?'))
        except Exception as e:
            logger.error("Scorer: RegimeBrain error: %s", e)
            self._regime_decision = {
                'trade_today': True, 'confidence': 0, 'regime': 'UNKNOWN'}

        # Strategy routing
        try:
            self._current_strategy = self._strategy_router.route(macro_for_regime)
            logger.info("Scorer: Strategy → %s/%s (size=%.0f%%)",
                        self._current_strategy.get('regime'),
                        self._current_strategy.get('strategy'),
                        self._current_strategy.get('sizing', 1) * 100)
        except Exception as e:
            logger.error("Scorer: Strategy router error: %s", e)
            self._current_strategy = {
                'regime': 'NORMAL', 'strategy': 'SELECTIVE', 'sizing': 0.25}

        return {
            'regime_decision': self._regime_decision,
            'strategy': self._current_strategy,
            'temporal_features': self._temporal_features,
            'leading_signals': self._leading_signals,
        }

    # === Scoring ===

    def score_batch(self, candidates, macro, scan_date, refit=True):
        """Score all candidates. Returns list of (score, candidate) sorted desc.

        Also returns regime info dict.

        Returns: (scored_list, regime, macro_er)
        """
        v3_cfg = self._config.get('v3', {})

        # Refit kernels (skip for intraday — reuse evening fit)
        if refit:
            if self.kernel:
                self.kernel.load_and_fit()
            if self.stock_kernel:
                self.stock_kernel.load_and_fit()

        # --- Stage 1: Macro kernel → regime detection ---
        macro_candidate = {
            'new_52w_lows': macro.get('new_52w_lows'),
            'crude_change_5d': macro.get('crude_delta_5d_pct'),
            'pct_above_20d_ma': macro.get('pct_above_20d_ma'),
            'new_52w_highs': macro.get('new_52w_highs'),
            'yield_10y': macro.get('yield_10y'),
            'spy_close': macro.get('spy_close'),
            'crude_close': macro.get('crude_close'),
            'vix_term_spread': macro.get('vix_term_spread'),
        }
        macro_er, se, n_eff = self.kernel.estimate(macro_candidate)

        if n_eff < MIN_N_EFF:
            logger.warning("Scorer: n_eff=%.1f < %.1f — insufficient data, defaulting to STRESS",
                           n_eff, MIN_N_EFF)
            return [], 'STRESS', 0.0

        # Determine regime — v17: boundaries from adaptive_params when available
        if self._adaptive_params:
            bull_threshold = self._adaptive_params.get('', 'BULL', 'score_bull_er')
            stress_threshold = self._adaptive_params.get('', 'CRISIS', 'score_crisis_er')
        else:
            regime_cfg = v3_cfg.get('regimes', {})
            bull_threshold = regime_cfg.get('bull_er', 0.5)
            stress_threshold = regime_cfg.get('stress_er', -0.5)

        if macro_er > bull_threshold:
            regime = 'BULL'
        elif macro_er > stress_threshold:
            regime = 'STRESS'
        else:
            regime = 'CRISIS'

        self._current_regime = regime

        from discovery.filter import get_crisis_sectors, ALL_SECTORS
        crisis_sectors = get_crisis_sectors(macro)

        logger.info(
            "Scorer: E[R]=%+.2f%% regime=%s | "
            "lows=%s crude_chg=%s breadth=%s highs=%s y10=%s spy=%s crude=%s vix_spread=%s | "
            "sectors: %s",
            macro_er, regime,
            macro.get('new_52w_lows'), macro.get('crude_delta_5d_pct'),
            macro.get('pct_above_20d_ma'), macro.get('new_52w_highs'),
            macro.get('yield_10y'), macro.get('spy_close'),
            macro.get('crude_close'), macro.get('vix_term_spread'),
            'ALL' if crisis_sectors == ALL_SECTORS else ','.join(sorted(crisis_sectors)),
        )

        # --- Stage 2: Per-stock scoring ---
        vix = macro.get('vix_close', 20) or 20
        use_stock_kernel = self.stock_kernel and self.stock_kernel._fitted

        scored = []
        for c in candidates:
            c['vix_at_signal'] = vix
            for k, v in macro_candidate.items():
                c[k] = v

            if use_stock_kernel:
                stock_er, _, stock_neff = self.stock_kernel.estimate(c)
                if stock_neff < MIN_N_EFF:
                    stock_er = 0.0
            else:
                stock_er = 0.0

            scored.append((stock_er, c))

        # Blend with UnifiedBrain (for filter pipeline compatibility)
        # v17: Also store RAW values on candidate for ML model (no double-blend)
        if self._unified_brain._fitted:
            blended_scored = []
            for er, c in scored:
                sens = self._sensors.compute_all(
                    c['symbol'], scan_date, macro, c, self._temporal_features)
                rp = self._regime_decision.get('probability', 0.5)
                ub = self._unified_brain.predict(c, sens, rp)
                ub_prob = ub.get('probability', 0.5)
                ub_contrib = (ub_prob - 0.5) * 5
                blended = er * 0.6 + ub_contrib * 0.4
                # v17: Store raw values — ML reads these instead of blended
                c['_kernel_er'] = round(er, 4)
                c['_ubrain_prob'] = round(ub_prob, 4)
                blended_scored.append((blended, c))
            scored = blended_scored
        else:
            for er, c in scored:
                c['_kernel_er'] = round(er, 4)
                c['_ubrain_prob'] = 0.5

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored, regime, macro_er

    # === Predictions for UI ===

    def predict_tp_timeline(self, atr, vol, tp_pct, sl_pct,
                            stock_er=0.0, mom5=0.0, d20h=-5.0):
        """Predict P(TP hit by Dx), actual WR and E[R] for a stock.

        Uses kernel-weighted lookup from hold kernel data.
        """
        if not self._hold_data:
            return {}

        hd = self._hold_data
        atr_diff = (hd['atr'] - atr) / max(atr, 1)
        vol_diff = (hd['vol'] - vol) / max(vol, 0.5)
        mom_diff = (hd['mom'] - mom5) / 10
        d20h_diff = (hd['d20h'] - d20h) / 15
        dist_sq = atr_diff**2 + vol_diff**2 + 0.5 * mom_diff**2 + 0.5 * d20h_diff**2
        w = np.exp(-dist_sq / (2 * 0.2**2))
        ws = w.sum()
        if ws < 1e-10:
            return {}
        w /= ws

        p_tp_d0 = float((w * (hd['cum_high_d0'] >= tp_pct)).sum()) * 100
        p_tp_d1 = float((w * (hd['cum_high_d1'] >= tp_pct)).sum()) * 100
        p_tp_d2 = float((w * (hd['cum_high_d2'] >= tp_pct)).sum()) * 100
        p_tp_d3 = float((w * (hd['cum_high_d3'] >= tp_pct)).sum()) * 100
        p_sl_d3 = float((w * (hd['cum_low_d3'] <= -sl_pct)).sum()) * 100

        sl_mask = hd['cum_low_d3'] <= -sl_pct
        tp_mask = (~sl_mask) & (hd['cum_high_d3'] >= tp_pct)
        sim_returns = np.where(sl_mask, -sl_pct,
                      np.where(tp_mask, tp_pct, hd['d3_ret']))
        actual_er = float((w * sim_returns).sum())
        actual_wr = float((w * (sim_returns > 0)).sum()) * 100

        show_days = [(p_tp_d0, 0), (p_tp_d3, 3)]

        at = self._advice_er_thresholds
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

    def has_weekend_data(self):
        return self._weekend_data is not None

    def predict_weekend(self, atr, vol, mom5, d20h, vix):
        """Predict Monday outcome if bought Friday."""
        if not self._weekend_data:
            return {}

        wd = self._weekend_data
        atr_d = (wd['atr'] - atr) / max(atr, 1)
        vol_d = (wd['vol'] - vol) / max(vol, 0.5)
        mom_d = (wd['mom'] - mom5) / 10
        d20h_d = (wd['d20h'] - d20h) / 10
        vix_d = (wd['vix'] - vix) / 10

        dist_sq = atr_d**2 + vol_d**2 + 0.5*mom_d**2 + 0.3*d20h_d**2 + 0.5*vix_d**2
        w = np.exp(-dist_sq / (2 * 0.2**2))
        ws = w.sum()
        if ws < 1e-10:
            return {}
        w /= ws

        mon_ret = float((w * wd['mon_ret']).sum())
        mon_wr = float((w * (wd['mon_ret'] > 0)).sum()) * 100
        mon_high = float((w * wd['mon_high']).sum())
        mon_low = float((w * wd['mon_low']).sum())
        mon_gap = float((w * wd['mon_gap']).sum())

        p_up = mon_wr / 100
        safe_ratio = round(p_up / max(1 - p_up, 0.01), 1)

        wk_thresh = self._weekend_wr_threshold
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
            'neff': round(float(ws**2 / (w**2).sum())),
        }

    # === Delegated predictions for sizer ===

    def compute_stock_signals(self, symbol, scan_date):
        """Per-stock leading signals."""
        return self._leading_indicators.compute_stock_signals(symbol, scan_date)

    def predict_stock_profile(self, atr, mom5, vol, d20h, sector=''):
        """Historical stock profile matching."""
        return self._sequence_matcher.predict_stock_profile(
            atr, mom5, vol, d20h, sector=sector)

    def compute_sensors(self, symbol, scan_date, macro, candidate):
        """Compute sensor signals for a stock."""
        return self._sensors.compute_all(
            symbol, scan_date, macro, candidate, self._temporal_features)

    def predict_stock(self, candidate, sensor_signals, regime_prob):
        """Brain prediction (UnifiedBrain or StockBrain fallback)."""
        if self._unified_brain._fitted:
            return self._unified_brain.predict(candidate, sensor_signals, regime_prob)
        return self._stock_brain.predict(candidate)

    # === Hold kernel fitting (moved from engine.py) ===

    def _fit_hold_kernel(self):
        """Build lookup for P(TP hit by Dx) and weekend prediction."""
        self._hold_data = None
        self._weekend_data = None
        try:
            self._fit_hold_kernel_inner()
        except Exception as e:
            logger.error("HoldKernel: fit failed: %s", e)

    def _fit_hold_kernel_inner(self):
        # conn via get_session()
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
            pass

        if len(rows) < 500:
            logger.warning("HoldKernel: not enough data (%d rows)", len(rows))
            return

        n = len(rows)
        self._hold_data = {
            'atr': np.array([r[0] for r in rows]),
            'vol': np.array([r[1] or 1 for r in rows]),
            'mom': np.array([r[2] or 0 for r in rows]),
            'd20h': np.array([r[3] or -5 for r in rows]),
            'n': n,
        }

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

        self._hold_data['cum_high_d0'] = (d0h / d0o - 1) * 100
        self._hold_data['cum_high_d1'] = np.maximum(self._hold_data['cum_high_d0'], (h1 / d0o - 1) * 100)
        self._hold_data['cum_high_d2'] = np.maximum(self._hold_data['cum_high_d1'], (h2 / d0o - 1) * 100)
        self._hold_data['cum_high_d3'] = np.maximum(self._hold_data['cum_high_d2'], (h3 / d0o - 1) * 100)
        self._hold_data['cum_low_d3'] = np.minimum(
            np.minimum((d0l / d0o - 1) * 100, (l1 / d0o - 1) * 100),
            np.minimum((l2 / d0o - 1) * 100, (l3 / d0o - 1) * 100),
        )
        self._hold_data['d3_ret'] = (c3 / d0o - 1) * 100

        # Auto-learn advice E[R] thresholds
        atr_arr = self._hold_data['atr']
        tp_ratio = self._config.get('v3', {}).get('smart_tp', {}).get(
            'tp_regime_ratios', {}).get('BULL', 1.0)
        dsl = self._config.get('dynamic_sl', {})
        sl_mult = dsl.get('bull_mult', 2.0)
        sl_floor = dsl.get('floor', 1.5)
        sl_cap = dsl.get('cap', 5.0)
        tp_arr = np.maximum(0.5, tp_ratio * atr_arr)
        sl_arr = np.maximum(sl_floor, np.minimum(sl_cap, sl_mult * atr_arr))

        cum_low_d3 = self._hold_data['cum_low_d3']
        sl_hit_sim = cum_low_d3 <= -sl_arr
        tp_hit_sim = (~sl_hit_sim) & (self._hold_data['cum_high_d3'] >= tp_arr)
        sim_rets = np.where(sl_hit_sim, -sl_arr,
                   np.where(tp_hit_sim, tp_arr, self._hold_data['d3_ret']))

        p80 = float(np.percentile(sim_rets, 80))
        p50 = float(np.percentile(sim_rets, 50))
        p30 = float(np.percentile(sim_rets, 30))

        self._advice_er_thresholds = {
            'buy': round(p80, 2), 'hold': round(p50, 2), 'caution': round(p30, 2),
        }

        logger.info("HoldKernel: fitted on %d signals, advice E[R]: buy>=%.2f hold>=%.2f caution>=%.2f",
                     n, p80, p50, p30)

        # Weekend kernel
        try:
            self._fit_weekend_kernel()
        except Exception as e:
            logger.error("WeekendKernel: fit failed: %s", e)

    def _fit_weekend_kernel(self):
        """Fit kernel for Friday buy → Monday outcome prediction."""
        # conn via get_session()
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
            pass

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

        avg_wr = (self._weekend_data['mon_ret'] > 0).mean()
        self._weekend_wr_threshold = round(avg_wr * 100 + 3, 0)

        logger.info("WeekendKernel: fitted on %d Friday signals, avg Monday WR=%.1f%%",
                     n, avg_wr * 100)

    # === Stats ===

    def get_stats(self):
        return {
            'kernel_ready': self._kernel_ready,
            'kernel': self.kernel.get_stats() if self.kernel else None,
            'regime_brain': self._regime_brain.get_stats(),
            'stock_brain': self._stock_brain.get_stats(),
            'unified_brain': self._unified_brain.get_stats(),
            'strategy_router': self._strategy_router.get_stats(),
        }

    def needs_refit(self, days=30):
        return (self._regime_brain.needs_refit(days) or
                self._stock_brain.needs_refit(days) or
                self._unified_brain.needs_refit(days))
