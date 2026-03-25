"""
Discovery Engine v13.0 — Clean Architecture.
Background scanner for high-confidence stock picks.
Display-only, does NOT execute trades. Does NOT interfere with Rapid Trader.

Scan: daily at 20:00 ET (after market close)
Price refresh: every 5 min during market hours
Storage: discovery_picks table in trade_history.db

v13.0: Refactored from 2600→1200 lines. Scoring, filtering, and sizing
extracted into unified_scorer.py, filter.py, sizer.py.
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
from discovery.unified_scorer import UnifiedScorer
from discovery.filter import UnifiedFilter
from discovery.sizer import UnifiedSizer
from discovery.adaptive_params import AdaptiveParameterLearner
from discovery.multi_strategy import StrategySelector, detect_condition, STRATEGIES
from discovery.outcome_tracker import OutcomeTracker
from discovery.market_signals import MarketSignalEngine
from discovery.param_manager import ParamManager
from discovery.param_optimizer import ParamOptimizer
from discovery.performance_tracker import PerformanceTracker
from discovery.auto_refit import AutoRefitOrchestrator
from discovery.sector_scorer import SectorScorer
from discovery.adaptive_stock_selector import AdaptiveStockSelector
from discovery.signal_tracker import SignalTracker

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'
CONFIG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'discovery.yaml'


class DiscoveryEngine:
    """Scans universe for high-confidence, low-risk stock picks."""

    def __init__(self):
        self._picks: list[DiscoveryPick] = []
        self._last_scan: Optional[str] = None
        self._last_price_refresh: float = 0.0
        self._scan_progress: dict = {}
        self._last_validation: Optional[str] = None
        self._last_intraday_scan: Optional[str] = None

        with open(CONFIG_PATH) as f:
            self._config = yaml.safe_load(f)['discovery']

        # Infrastructure
        self._params = ParamManager()
        self._outcome_tracker = OutcomeTracker()
        self._market_signals = MarketSignalEngine()
        self._market_signal_picks: list = []

        # v13.1: Adaptive parameter learning
        self._adaptive_params = AdaptiveParameterLearner()
        if not self._adaptive_params.load_from_db():
            try:
                self._adaptive_params.fit()
            except Exception as e:
                logger.error("Discovery: adaptive params fit error: %s", e)

        # v13.0: Three core modules replace 16 scattered components
        self._scorer = UnifiedScorer(self._config, self._params)
        # v17: Wire adaptive params into strategy_router for learned VIX thresholds
        self._scorer._strategy_router._adaptive = self._adaptive_params
        self._filter = UnifiedFilter(adaptive_params=self._adaptive_params)
        self._sizer = UnifiedSizer(self._config, self._params,
                                    adaptive_params=self._adaptive_params)

        # v10.0: Auto-optimization + monitoring
        self._param_optimizer = ParamOptimizer(self._params)
        self._perf_tracker = PerformanceTracker()
        # v15.0: Multi-strategy selector (display-only suggestions)
        self._strategy_selector = StrategySelector(adaptive_params=self._adaptive_params)
        if not self._strategy_selector.load_from_db():
            try:
                self._strategy_selector.fit()
            except Exception as e:
                logger.error("Discovery: strategy selector fit error: %s", e)

        # v14.0: Build Neural Graph
        try:
            if not self._sizer.neural_graph.load_from_db():
                self._sizer.neural_graph.build_all()
        except Exception as e:
            logger.error("Discovery: neural graph init error: %s", e)

        # v17: Full Adaptive layers
        self._v17_enabled = self._config.get('v17', {}).get('enabled', False)
        self._sector_scorer = SectorScorer(adaptive_params=self._adaptive_params)
        self._stock_selector = AdaptiveStockSelector()
        self._signal_tracker = SignalTracker()

        if self._v17_enabled:
            for name, component in [
                ('SectorScorer', self._sector_scorer),
                ('StockSelector', self._stock_selector),
                ('SignalTracker', self._signal_tracker),
            ]:
                if not component.load_from_db():
                    try:
                        component.fit()
                    except Exception as e:
                        logger.error("Discovery v17: %s fit error: %s", name, e)
            # Wire v17 components into filter for learned weights/sectors
            self._filter._signal_tracker = self._signal_tracker
            self._filter._sector_scorer = self._sector_scorer
            logger.info("Discovery v17: enabled — SectorScorer=%s StockSelector=%s SignalTracker=%s",
                        self._sector_scorer._fitted, self._stock_selector._fitted,
                        self._signal_tracker._fitted)

        self._orchestrator = AutoRefitOrchestrator(
            self._scorer.regime_brain, self._scorer.stock_brain,
            self._param_optimizer, self._perf_tracker, self._params,
            adaptive_params=self._adaptive_params,
            knowledge_graph=self._sizer.knowledge_graph,
            neural_graph=self._sizer.neural_graph,
            strategy_selector=self._strategy_selector,
            sector_scorer=self._sector_scorer,
            stock_selector=self._stock_selector,
            signal_tracker=self._signal_tracker)

        # v2 fallback scorer (only used when kernel disabled)
        self._legacy_scorer = None
        if not self._config.get('v3', {}).get('enabled', False):
            from discovery.scorer import DiscoveryScorer
            self._legacy_scorer = DiscoveryScorer()

        self._ensure_table()
        self._load_picks_from_db()

    # === Compatibility properties (webapp accesses these directly) ===

    @property
    def _temporal_features(self):
        return self._scorer._temporal_features

    @property
    def _sequence_prediction(self):
        return {}

    @property
    def _leading_signals(self):
        return self._scorer._leading_signals

    @property
    def _regime_decision(self):
        return self._scorer._regime_decision

    @property
    def _current_strategy(self):
        return self._scorer._current_strategy

    @property
    def _multi_strategy(self):
        info = getattr(self, '_multi_strategy_info', {})
        loaded_at = getattr(self, '_multi_strategy_loaded_at', 0)
        # Refresh from DB if empty or stale (>5 min since last load)
        if not info or (time.monotonic() - loaded_at) > 300:
            info = self._load_multi_strategy()
            self._multi_strategy_info = info
            self._multi_strategy_loaded_at = time.monotonic()
        return info

    # === Public API ===

    def get_scan_progress(self) -> dict:
        return self._scan_progress.copy()

    def get_picks(self, auto_refresh: bool = True) -> list[dict]:
        """Return current picks as dicts for API. Applies sector diversification."""
        if auto_refresh:
            self._maybe_refresh_prices()
        max_display = self._config.get('schedule', {}).get('max_picks_display', 10)
        div_cfg = self._config.get('diversification', {})
        max_per_sector = div_cfg.get('max_per_sector', 3)

        def rank_fn(p):
            council = getattr(p, 'council', None)
            if council:
                return council.get('confidence', 0)
            return (p.layer2_score or 0)
        sorted_picks = sorted(self._picks, key=rank_fn, reverse=True)

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

    def get_current_regime(self) -> Optional[str]:
        return self._scorer.current_regime

    def get_confidence(self) -> dict:
        return self._sizer.get_confidence()

    def get_outcome_tracker(self) -> OutcomeTracker:
        return self._outcome_tracker

    def get_calibrator(self):
        return self._sizer._calibrator

    def get_last_validation(self) -> Optional[str]:
        return self._last_validation

    def get_last_intraday_scan(self) -> Optional[str]:
        return self._last_intraday_scan

    def get_stats(self) -> dict:
        """Historical performance statistics from picks with filled outcomes."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        stats_row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) as wins_5d,
                   SUM(CASE WHEN outcome_5d IS NOT NULL THEN 1 ELSE 0 END) as has_outcome,
                   AVG(outcome_1d) as avg_1d, AVG(outcome_5d) as avg_5d,
                   AVG(outcome_max_gain_5d) as avg_max_gain,
                   AVG(outcome_max_dd_5d) as avg_max_dd,
                   SUM(CASE WHEN status='hit_tp1' THEN 1 ELSE 0 END) as tp1_hits,
                   SUM(CASE WHEN status='hit_sl' THEN 1 ELSE 0 END) as sl_hits
            FROM discovery_picks
        """).fetchone()

        sector_rows = conn.execute("""
            SELECT sector, COUNT(*) as n,
                   SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) as wins,
                   AVG(outcome_5d) as avg_5d
            FROM discovery_picks WHERE outcome_5d IS NOT NULL
            GROUP BY sector ORDER BY n DESC
        """).fetchall()

        tier_rows = conn.execute("""
            SELECT CASE
                WHEN layer2_score < 10 THEN
                    CASE WHEN layer2_score >= 2.0 THEN 'A+'
                         WHEN layer2_score >= 1.0 THEN 'A'
                         WHEN layer2_score >= 0.5 THEN 'B' ELSE 'C' END
                ELSE
                    CASE WHEN layer2_score >= 80 THEN 'A+'
                         WHEN layer2_score >= 70 THEN 'A'
                         WHEN layer2_score >= 60 THEN 'B' ELSE 'C' END
                END as tier, COUNT(*) as n,
                SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) as wins,
                AVG(outcome_5d) as avg_5d
            FROM discovery_picks WHERE outcome_5d IS NOT NULL
            GROUP BY tier ORDER BY tier
        """).fetchall()

        active_sectors = conn.execute("""
            SELECT sector, COUNT(*) as n FROM discovery_picks
            WHERE status = 'active' GROUP BY sector ORDER BY n DESC
        """).fetchall()

        try:
            bench_row = conn.execute("""
                SELECT AVG(outcome_5d) as picks_avg,
                       AVG(benchmark_xlu_5d) as xlu_avg,
                       AVG(benchmark_xle_5d) as xle_avg,
                       AVG(benchmark_spy_5d) as spy_avg, COUNT(*) as n
                FROM discovery_picks
                WHERE outcome_5d IS NOT NULL AND benchmark_spy_5d IS NOT NULL
            """).fetchone()
        except Exception:
            bench_row = None

        conn.close()

        total = stats_row['total'] or 0
        has_outcome = stats_row['has_outcome'] or 0
        wins = stats_row['wins_5d'] or 0

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

    # === Regime detection (v16) ===

    def _detect_market_regime(self, macro: dict) -> tuple[str, str]:
        """Detect market regime from TREND × VOLATILITY.

        TREND: SPY vs 50MA + 20d return slope
        VOL: VIX level buckets

        Returns (trend, vol_regime) e.g. ('STRONG_UP', 'NORMAL_VOL')
        """
        vix = macro.get('vix_close') or 20

        # VOL regime from VIX
        if vix > 30:
            vol_regime = 'HIGH_VOL'
        elif vix > 22:
            vol_regime = 'ELEVATED'
        elif vix < 15:
            vol_regime = 'LOW_VOL'
        else:
            vol_regime = 'NORMAL_VOL'

        # TREND from SPY vs 50MA + 20d slope
        trend = 'CHOPPY'
        try:
            conn = sqlite3.connect(str(DB_PATH))
            rows = conn.execute(
                "SELECT close FROM stock_daily_ohlc "
                "WHERE symbol='SPY' ORDER BY date DESC LIMIT 50"
            ).fetchall()
            conn.close()

            if len(rows) >= 50:
                spy_now = rows[0][0]
                ma50 = sum(r[0] for r in rows) / len(rows)
                spy_20d_ago = rows[min(20, len(rows) - 1)][0]
                spy_20d_ret = ((spy_now / spy_20d_ago) - 1) * 100 if spy_20d_ago > 0 else 0

                if spy_now > ma50 and spy_20d_ret > 2:
                    trend = 'STRONG_UP'
                elif spy_now > ma50 and spy_20d_ret > 0:
                    trend = 'MILD_UP'
                elif spy_now < ma50 and spy_20d_ret < -2:
                    trend = 'STRONG_DOWN'
                elif spy_now < ma50 and spy_20d_ret < 0:
                    trend = 'MILD_DOWN'
                else:
                    trend = 'CHOPPY'
        except Exception as e:
            logger.debug("Regime detection SPY error: %s", e)

        return trend, vol_regime

    # === Main scan pipeline ===

    def run_scan(self) -> list[DiscoveryPick]:
        """Full scan: universe → score → filter → size → save."""
        from api.yfinance_utils import fetch_history

        scan_date = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
        logger.info(f"Discovery scan starting for {scan_date}")
        self._scan_progress = {'status': 'loading', 'pct': 0,
                               'stage': 'Loading universe...', 'l1': 0, 'l2': 0}

        # 1. Auto-refit orchestrator (every 30 days)
        try:
            if self._orchestrator.needs_run(days=30):
                self._orchestrator.run_cycle()
                logger.info("Discovery: auto-refit cycle complete")
        except Exception as e:
            logger.error("Discovery: auto-refit error: %s", e)

        # 2. Track outcomes for expired picks
        try:
            n_tracked = self._outcome_tracker.track_expired_picks()
            if n_tracked:
                logger.info(f"Discovery: tracked {n_tracked} expired pick outcomes")
        except Exception as e:
            logger.error(f"Discovery: outcome tracking error: {e}")

        # 3. Load universe + macro
        stocks = self._load_universe()
        logger.info(f"Discovery: {len(stocks)} stocks in universe")
        self._scan_progress.update(stage=f'Loaded {len(stocks)} stocks', pct=5)

        macro = self._load_macro(scan_date)
        vix = macro.get('vix_close', 0) or 0

        # 4. Retry kernel init if needed
        self._scorer.retry_kernel()

        if not self._scorer.is_ready:
            mode = 'v2 score'
        else:
            mode = 'v3 kernel'

        logger.info(f"Discovery: VIX={vix:.1f}, mode={mode}")

        # 5. Scorer scan setup (temporal, leading, regime, strategy)
        scan_info = self._scorer.scan_setup(scan_date, macro)

        # 5b. Consolidate all regime info into scan_info (computed once, shared)
        scan_info['market_regime'] = self._detect_market_regime(macro)
        scan_info['condition'] = detect_condition(vix or 20, macro.get('pct_above_20d_ma') or 50)
        logger.info("Discovery: regime consolidated — router=%s market=%s×%s condition=%s",
                     scan_info.get('strategy', {}).get('regime', '?'),
                     scan_info['market_regime'][0], scan_info['market_regime'][1],
                     scan_info['condition'])

        # 5c. v17: Compute sector scores
        sector_scores = {}
        allowed_sectors = None
        blocked_sectors = set()
        if self._v17_enabled and self._sector_scorer._fitted:
            try:
                sector_scores = self._sector_scorer.score(macro, scan_date)
                allowed_sectors, blocked_sectors = self._sector_scorer.get_allowed_sectors(
                    macro, scan_date)
                scan_info['sector_scores'] = sector_scores
                scan_info['allowed_sectors'] = allowed_sectors
                scan_info['blocked_sectors'] = blocked_sectors
                logger.info("Discovery v17: sector scores=%s",
                            {s: f"{v:+.3f}" for s, v in sorted(sector_scores.items(), key=lambda x: -x[1])})
                logger.info("Discovery v17: allowed=%s blocked=%s",
                            sorted(allowed_sectors), sorted(blocked_sectors))
            except Exception as e:
                logger.error("Discovery v17: SectorScorer error: %s — fallback to all sectors", e)

        # 6. Market-level signals (separate pipeline)
        try:
            self._market_signal_picks = self._market_signals.compute_signals(scan_date)
            if self._market_signal_picks:
                logger.info("Discovery: %d market signals: %s",
                            len(self._market_signal_picks),
                            ', '.join(s['name'][:30] for s in self._market_signal_picks))
        except Exception as e:
            logger.error("Discovery: market signals error: %s", e)
            self._market_signal_picks = []

        # 7. Fetch stock data (yfinance batches)
        candidates = self._fetch_candidates(stocks, macro, scan_date)
        logger.info(f"Discovery: {len(candidates)} passed Layer 1")
        self._scan_progress.update(status='scoring', pct=87,
                                   stage=f'L1 passed: {len(candidates)}',
                                   l1=len(candidates))

        # 8. Enrich candidates (includes smart boost data for filter)
        self._enrich_candidates(candidates, scan_date)
        self._scan_progress.update(pct=92,
                                   stage=f'Scoring {len(candidates)} candidates...')

        # 9-11. Score → Filter → Size
        # v17: SectorScorer + SignalTracker integrated into existing pipeline
        # (strategies remain DIP/OVERSOLD/etc. but with learned thresholds)
        scored_all = []
        regime_from_score = 'STRESS'
        macro_er_from_score = 0.0

        if self._scorer.is_ready:
            picks, scored_all, regime_from_score, macro_er_from_score = \
                self._run_v3_pipeline(candidates, macro, scan_date, scan_info)
        else:
            picks = self._score_v2(candidates, macro, scan_date)
            # v2 fallback: attach strategy info so picks have council
            strategy_info = scan_info.get('strategy', {})
            for p in picks:
                if not getattr(p, 'council', None):
                    p.council = {
                        'decision': 'TRADE', 'tier': 'LEAN', 'confidence': 0,
                        'position_size': 0.25, 'reasons': ['v2_fallback'],
                        'brains': {}, 'strategy': strategy_info,
                        'stock_signals': {}, 'stock_profile': {},
                        'context': {}, 'sensors': {},
                    }

        # 12. Log sector distribution
        pick_sectors: dict[str, int] = {}
        for p in picks:
            s = p.sector or 'Unknown'
            pick_sectors[s] = pick_sectors.get(s, 0) + 1
        sectors_summary = ', '.join(
            f"{s}:{n}" for s, n in sorted(pick_sectors.items(), key=lambda x: -x[1]))
        logger.info(f"Discovery: {len(picks)} total picks | sectors: {sectors_summary}")
        self._scan_progress.update(pct=97,
                                   stage=f'Scored: {len(picks)} picks',
                                   l2=len(picks))

        # 13. v16: Regime-adaptive multi-strategy (shared method)
        try:
            self._multi_strategy_info = self._build_multi_strategy(
                candidates, scored_all, regime_from_score, macro_er_from_score,
                macro, scan_info, scan_date)
            self._multi_strategy_loaded_at = time.monotonic()
        except Exception as e:
            import traceback
            tb = traceback.format_exc().replace('\n', ' | ')
            logger.error("Discovery: multi-strategy error: %s TB: %s", e, tb)
            self._multi_strategy_info = {}

        # 14. Persist multi-strategy info to DB (survives process restart)
        if self._multi_strategy_info:
            self._save_multi_strategy(scan_date, self._multi_strategy_info)

        # 15. Deactivate old + save new
        self._expire_old_picks(scan_date)
        self._deactivate_previous_picks(scan_date)
        self._save_picks(picks, scan_date)

        self._picks = picks
        self._last_scan = scan_date
        self._scan_progress = {'status': 'done', 'pct': 100,
                               'stage': f'Done: {len(picks)} picks',
                               'l1': len(candidates), 'l2': len(picks)}
        return picks

    def _run_v3_pipeline(self, candidates, macro, scan_date, scan_info):
        """v17 adaptive pipeline: Strategy ranking → Sector filter → Signal boost → Filter → Size.

        1. Kernel scoring for regime detection + base E[R]
        2. Strategy-ranked picks (learned thresholds) boost scores
        3. SectorScorer boosts/penalizes by sector quality
        4. SignalTracker applies learned signal boosts
        5. Existing filter pipeline (ATR, beta, PE, etc.) for safety
        6. Sizer creates picks with SL/TP + council

        Returns (picks, scored_all, regime, macro_er).
        """
        # 1. Kernel scoring — regime detection + per-stock base E[R]
        scored, regime, macro_er = self._scorer.score_batch(
            candidates, macro, scan_date)
        if not scored:
            return [], [], 'STRESS', 0.0

        # 2. v17: Boost scores using learned strategy ranking
        #    Stocks picked by learned strategies get a bonus
        scored = self._apply_strategy_boost(scored, candidates, macro, scan_info)

        # 3. v17: Boost/penalize by SectorScorer
        scored = self._apply_sector_boost(scored, scan_info)

        # 4. Weekend risk (Friday only)
        weekend_risk = None
        is_friday = datetime.now(ZoneInfo('America/New_York')).weekday() == 4
        if is_friday:
            try:
                weekend_risk = self._sizer.neural_graph.compute_weekend_risk(macro)
                self._weekend_risk = weekend_risk
                logger.info("Discovery: weekend risk=%+.2f action=%s factors=%s",
                            weekend_risk['weekend_score'],
                            weekend_risk['weekend_action'],
                            weekend_risk['weekend_factors'])
            except Exception as e:
                logger.error("Discovery: weekend risk error: %s", e)

        # 5. Filter (includes smart boost via SignalTracker)
        strategy_mode = scan_info['strategy'].get('strategy', 'SELECTIVE')
        filtered = self._filter.apply(
            scored, macro, regime, strategy_mode, self._config,
            unified_brain=self._scorer.unified_brain,
            sensors=self._scorer._sensors,
            temporal_features=scan_info.get('temporal_features', {}),
            scan_date=scan_date,
            context_scorer=self._sizer.context_scorer,
            regime_decision=scan_info.get('regime_decision', {}),
            weekend_risk=weekend_risk)

        if not filtered:
            logger.info("Filter: 0 picks passed — see multi-strategy suggestions")

        # 6. Size — create picks (max 2 per strategy, best E[R] first)
        max_per_strategy = self._config.get('v17', {}).get('max_per_strategy', 2)
        picks = []
        strat_counts = {}
        for score, candidate in filtered:
            strat_name = candidate.get('_matched_strategy')
            if not strat_name:
                strat_name = self._infer_strategy_label(candidate)
            # Enforce max per strategy
            if strat_counts.get(strat_name, 0) >= max_per_strategy:
                continue
            strat_info = dict(scan_info.get('strategy', {}))
            strat_info['strategy'] = strat_name
            pick = self._sizer.create_pick(
                candidate, score, macro, regime, macro_er,
                strat_info,
                scan_info.get('regime_decision', {}),
                scan_date, picks, self._scorer)
            if pick:
                picks.append(pick)
                strat_counts[strat_name] = strat_counts.get(strat_name, 0) + 1

        logger.info(
            "Discovery v17: %d picks [%s/%s] (macro E[R]=%+.2f%%, from %d candidates)",
            len(picks), regime, strategy_mode, macro_er, len(candidates))
        return picks, scored, regime, macro_er

    def _apply_strategy_boost(self, scored, candidates, macro, scan_info):
        """v17: Boost stocks that match learned strategies.

        Stocks selected by learned strategy functions get a score bonus.
        Higher-ranked strategy picks get bigger boost.
        """
        if not self._strategy_selector._fitted:
            return scored

        # Get ranked picks from all strategies (uses learned thresholds)
        market_regime = scan_info.get('market_regime')
        ranked = self._strategy_selector.get_ranked_picks(
            candidates, macro, market_regime=market_regime)

        # Build boost map: {symbol: (boost, strategy_name)}
        boost_map = {}
        for rank_idx, (strat_name, pick) in enumerate(ranked):
            sym = pick.get('symbol', '')
            # Higher rank = bigger boost (rank 0 = +1.0, rank 7 = +0.3)
            boost = max(0.3, 1.0 - rank_idx * 0.1)
            if sym not in boost_map:
                boost_map[sym] = (boost, strat_name)

        if not boost_map:
            return scored

        # Apply boosts to scored list
        boosted = []
        n_boosted = 0
        for er, c in scored:
            sym = c.get('symbol', '')
            if sym in boost_map:
                boost, strat_name = boost_map[sym]
                er += boost
                c['_matched_strategy'] = strat_name
                n_boosted += 1
            boosted.append((er, c))

        # Re-sort by boosted score
        boosted.sort(key=lambda x: x[0], reverse=True)

        if n_boosted:
            logger.info("Discovery v17: strategy boost applied to %d/%d candidates "
                        "(strategies: %s)",
                        n_boosted, len(scored),
                        {s: sum(1 for _, sn in boost_map.values() if sn == s)
                         for s in set(sn for _, sn in boost_map.values())})

        return boosted

    def _apply_sector_boost(self, scored, scan_info):
        """v17: Boost/penalize stocks by SectorScorer.

        Top sectors get bonus, blocked sectors are REMOVED (hard block).
        """
        sector_scores = scan_info.get('sector_scores', {})
        blocked = scan_info.get('blocked_sectors', set())
        if not sector_scores:
            return scored

        boosted = []
        n_blocked = 0
        for er, c in scored:
            sector = c.get('sector', '')
            # Hard block — remove entirely
            if sector in blocked:
                n_blocked += 1
                continue
            sect_score = sector_scores.get(sector, 0)
            # Normalize sector score to boost range [-0.3, +0.3]
            boost = max(-0.3, min(0.3, sect_score * 0.3))
            boosted.append((er + boost, c))

        if n_blocked:
            logger.info("Discovery v17: sector_boost removed %d stocks from blocked sectors %s",
                        n_blocked, sorted(blocked))

        boosted.sort(key=lambda x: x[0], reverse=True)
        return boosted

    @staticmethod
    def _infer_strategy_label(candidate):
        """Infer best-matching strategy label from stock features.

        Used when a stock passes filter via sector/kernel boost
        but wasn't directly matched by any strategy function.
        """
        mom5 = candidate.get('momentum_5d') or 0
        d20h = candidate.get('distance_from_20d_high') or 0
        vol = candidate.get('volume_ratio') or 1
        pe = candidate.get('pe_forward')

        # Check in priority order (most specific first)
        if mom5 < -5 and d20h < -10:
            return 'OVERSOLD'
        if -20 < mom5 < -1:
            return 'DIP'
        if mom5 > 0 and d20h > -10:
            return 'RS'
        if vol < 0.5 or vol > 2.0:
            return 'VOL_U'
        if pe is not None and 3 < pe < 15:
            return 'VALUE'
        return 'CONTRARIAN'

    def _build_multi_strategy(self, candidates, scored_all, regime, macro_er,
                              macro, scan_info, scan_date):
        """Build multi-strategy picks for display.

        v17: SectorScorer filters blocked sectors from strategy picks.
        Strategies (DIP/OVERSOLD/etc.) use learned thresholds via StrategySelector.
        Shared by run_scan() and run_intraday_scan().
        """
        from collections import defaultdict
        market_regime = scan_info.get('market_regime') or self._detect_market_regime(macro)
        condition = scan_info.get('condition') or detect_condition(
            macro.get('vix_close') or 20, macro.get('pct_above_20d_ma') or 50)

        strat_name, _ = self._strategy_selector.select(
            macro.get('vix_close') or 20, macro.get('pct_above_20d_ma') or 50)

        # v17: Filter blocked sectors from candidates before strategy functions
        blocked_sectors = scan_info.get('blocked_sectors', set())
        if blocked_sectors and self._sector_scorer._fitted:
            filtered_candidates = [c for c in candidates
                                   if c.get('sector', '') not in blocked_sectors]
            logger.info("Discovery multi-strategy: %d→%d after sector filter (blocked=%s)",
                        len(candidates), len(filtered_candidates), sorted(blocked_sectors))
        else:
            filtered_candidates = candidates

        ranked = self._strategy_selector.get_ranked_picks(
            filtered_candidates, macro, market_regime=market_regime)
        all_strat_picks = self._strategy_selector.get_all_picks(filtered_candidates, macro)

        logger.info("Discovery v15.2: %d ranked picks from %d candidates",
                    len(ranked), len(filtered_candidates))
        for sn, sp in all_strat_picks.items():
            logger.info("Discovery v15.2: %s=%d picks%s", sn, len(sp),
                        f" [{', '.join(p.get('symbol','?') for p in sp[:3])}]" if sp else "")

        scored_map = {c.get('symbol'): (sc, c) for sc, c in scored_all}

        strategy_full_picks = defaultdict(list)
        for s_name, cand in ranked:
            sym = cand.get('symbol', '')
            if sym in scored_map:
                score, scored_cand = scored_map[sym]
            else:
                score = 0.0
                scored_cand = cand

            strat_info = {
                'strategy': s_name,
                'regime': scan_info.get('strategy', {}).get('regime', 'NORMAL'),
                'sizing': scan_info.get('strategy', {}).get('sizing', 0.25),
            }
            pick = self._sizer.create_pick(
                scored_cand, score, macro, regime, macro_er,
                strat_info,
                scan_info.get('regime_decision', {}),
                scan_date, list(strategy_full_picks.get(s_name, [])), self._scorer)
            if pick:
                strategy_full_picks[s_name].append(pick)

        info = {
            'condition': condition,
            'selected': strat_name,
            'picks': {name: [p.to_dict() for p in pick_list]
                      for name, pick_list in strategy_full_picks.items()},
        }

        logger.info("Discovery v15.2: condition=%s selected=%s | %s",
                    condition, strat_name,
                    {k: len(v) for k, v in strategy_full_picks.items()})
        return info

    # === Data loading ===

    def _fetch_candidates(self, stocks, macro, scan_date):
        """Fetch stock data from yfinance and compute technical features."""
        candidates = []
        batch_size = 50
        symbols = list(stocks.keys())
        total_batches = (len(symbols) + batch_size - 1) // batch_size

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            batch_str = ' '.join(batch)
            batch_num = i // batch_size + 1
            pct = 5 + int(batch_num / total_batches * 80)
            self._scan_progress.update(
                status='scanning', pct=pct,
                stage=f'Batch {batch_num}/{total_batches}',
                l1=len(candidates))
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

                    # Layer 1 check (only for v2 fallback)
                    if not self._scorer.is_ready and self._legacy_scorer:
                        passed, reason = self._legacy_scorer.passes_layer1(features)
                        if not passed:
                            continue

                    features.update(macro)
                    candidates.append(features)
                except Exception as e:
                    logger.debug(f"Discovery: error processing {sym}: {e}")
                    continue

            if i + batch_size < len(symbols):
                time.sleep(1)

        return candidates

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
                rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 100
            else:
                rsi = 50

            # Momentum
            momentum_5d = (close[-1] / close[-6] - 1) * 100 if len(close) >= 6 else 0
            momentum_20d = (close[-1] / close[-21] - 1) * 100 if len(close) >= 21 else 0

            # Distance from highs
            high_52w = float(np.max(high[-252:])) if len(high) >= 252 else float(np.max(high))
            distance_from_high = (current / high_52w - 1) * 100 if high_52w > 0 else 0

            if len(high) >= 20:
                high_20d = float(np.max(high[-20:]))
                distance_from_20d_high = (current / high_20d - 1) * 100 if high_20d > 0 else 0
            else:
                distance_from_20d_high = 0

            # Volume ratio
            if len(volume) >= 21:
                avg_vol_20 = float(np.mean(volume[-21:-1]))
                volume_ratio = float(volume[-1]) / avg_vol_20 if avg_vol_20 > 0 else 1.0
            else:
                volume_ratio = 1.0

            # D0 OHLC
            d0_open = float(df['Open'].values[-1]) if 'Open' in df.columns else current
            d0_high = float(high[-1])
            d0_low = float(low[-1])

            return {
                'symbol': symbol,
                'close': current, 'open': d0_open,
                'day_high': d0_high, 'day_low': d0_low,
                'atr_pct': atr_pct, 'rsi': rsi,
                'momentum_5d': momentum_5d, 'momentum_20d': momentum_20d,
                'distance_from_high': distance_from_high,
                'distance_from_20d_high': distance_from_20d_high,
                'volume_ratio': volume_ratio,
                'beta': fund.get('beta'),
                'pe_forward': fund.get('pe_forward'),
                'sector': fund.get('sector', ''),
                'market_cap': fund.get('market_cap', 0),
                'mcap_log': math.log10(fund.get('market_cap', 1e9) + 1),
            }
        except Exception as e:
            logger.debug(f"Discovery: tech compute error for {symbol}: {e}")
            return None

    def _load_universe(self) -> dict:
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
            logger.warning("Discovery: no macro data found, using defaults")
            return {'vix_close': 20, 'spy_close': 500, 'pct_above_20d_ma': 50,
                    'crude_close': 75, 'yield_10y': 4, 'vix3m_close': 22}

        result = dict(macro_row)

        vix = result.get('vix_close', 20)
        vix3m = result.get('vix3m_close', 20)
        result['vix_term_structure'] = vix3m / vix if vix and vix > 0 else 1.0
        result['vix_term_spread'] = round(vix - vix3m, 4) if vix and vix3m else 0.0

        highs = result.get('new_52w_highs', 100)
        lows = result.get('new_52w_lows', 100)
        result['highs_lows_ratio'] = highs / max(lows, 1) if highs is not None and lows is not None else 1.0

        # 5-day deltas
        macro_5d = conn.execute("""
            SELECT vix_close, dxy_close, crude_close FROM macro_snapshots
            ORDER BY date DESC LIMIT 1 OFFSET 5
        """).fetchone()

        breadth_5d = conn.execute("""
            SELECT pct_above_20d_ma FROM market_breadth
            ORDER BY date DESC LIMIT 1 OFFSET 5
        """).fetchone()

        # v14.0: BTC 3-day ago for leading signal
        btc_3d_row = conn.execute("""
            SELECT btc_close FROM macro_snapshots
            WHERE btc_close IS NOT NULL ORDER BY date DESC LIMIT 1 OFFSET 3
        """).fetchone()

        conn.close()

        if macro_5d and macro_5d['vix_close'] and vix:
            result['vix_delta_5d'] = round(vix - macro_5d['vix_close'], 2)
        else:
            result['vix_delta_5d'] = 0.0

        dxy = result.get('dxy_close')
        if macro_5d and macro_5d['dxy_close'] and dxy:
            result['dxy_delta_5d'] = round(dxy - macro_5d['dxy_close'], 2)
        else:
            result['dxy_delta_5d'] = 0.0

        breadth_now = result.get('pct_above_20d_ma')
        if breadth_5d and breadth_5d['pct_above_20d_ma'] and breadth_now:
            result['breadth_delta_5d'] = round(breadth_now - breadth_5d['pct_above_20d_ma'], 2)
        else:
            result['breadth_delta_5d'] = 0.0

        crude_now = result.get('crude_close')
        crude_5d_ago = macro_5d['crude_close'] if macro_5d and macro_5d['crude_close'] else None
        if crude_now and crude_5d_ago and crude_5d_ago > 0:
            result['crude_delta_5d_pct'] = round((crude_now / crude_5d_ago - 1) * 100, 2)
        else:
            result['crude_delta_5d_pct'] = None

        # v14.0: BTC 3-day momentum (leading indicator for worst trades)
        btc_now = result.get('btc_close')
        if btc_now and btc_3d_row and btc_3d_row[0] and btc_3d_row[0] > 0:
            result['btc_momentum_3d'] = round((btc_now / btc_3d_row[0] - 1) * 100, 2)
        else:
            result['btc_momentum_3d'] = None

        # Market Stress Score (0-100)
        stress_components = []
        vix_d = result.get('vix_delta_5d', 0)
        stress_components.append(min(1.0, max(0.0, vix_d / 10.0)))
        breadth_d = result.get('breadth_delta_5d', 0)
        stress_components.append(min(1.0, max(0.0, -breadth_d / 20.0)))
        vts = result.get('vix_term_structure', 1.0)
        stress_components.append(min(1.0, max(0.0, (1.0 - vts) / 0.1)))
        stress_components.append(min(1.0, max(0.0, (vix - 20) / 15.0)) if vix else 0.0)
        dxy_d = result.get('dxy_delta_5d', 0)
        stress_components.append(min(1.0, max(0.0, dxy_d / 2.0)))
        if breadth_now and breadth_now > 0:
            stress_components.append(min(1.0, max(0.0, (50 - breadth_now) / 25.0)))
        else:
            stress_components.append(0.0)
        result['stress_score'] = round(sum(stress_components) / len(stress_components) * 100, 1)

        return result

    def _enrich_candidates(self, candidates: list, scan_date: str = None):
        """Add analyst/news/options/insider data from DB to candidates."""
        if not candidates:
            return

        symbols = [c['symbol'] for c in candidates]
        placeholders = ','.join('?' * len(symbols))
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        analyst = {r['symbol']: dict(r) for r in conn.execute(f"SELECT symbol, bull_score, upside_pct FROM analyst_consensus WHERE symbol IN ({placeholders})", symbols).fetchall()}
        news = {r['symbol']: dict(r) for r in conn.execute(f"SELECT symbol, AVG(sentiment_score) as avg_news_sentiment, COUNT(*) as news_count, SUM(CASE WHEN sentiment_label='positive' THEN 1 ELSE 0 END) as news_pos, SUM(CASE WHEN sentiment_label='negative' THEN 1 ELSE 0 END) as news_neg FROM news_events WHERE symbol IN ({placeholders}) AND symbol IS NOT NULL GROUP BY symbol", symbols).fetchall()}
        options = {r['symbol']: dict(r) for r in conn.execute(f"SELECT symbol, put_call_ratio FROM options_flow WHERE symbol IN ({placeholders}) GROUP BY symbol HAVING MAX(date)", symbols).fetchall()}

        today_str = date.today().isoformat()
        earnings = {}
        for r in conn.execute(f"SELECT symbol, MIN(report_date) as next_date FROM earnings_history WHERE symbol IN ({placeholders}) AND report_date >= ? GROUP BY symbol", symbols + [today_str]).fetchall():
            try:
                ed = datetime.strptime(r['next_date'][:10], '%Y-%m-%d').date()
                earnings[r['symbol']] = (ed - date.today()).days
            except Exception:
                pass

        short_data = {r['symbol']: r['short_pct_float'] for r in conn.execute(f"SELECT symbol, short_pct_float FROM short_interest WHERE symbol IN ({placeholders})", symbols).fetchall()}

        sector_rows = conn.execute("SELECT etf, sector, pct_change FROM sector_etf_daily_returns WHERE date = (SELECT MAX(date) FROM sector_etf_daily_returns)").fetchall()
        sector_returns_by_name = {r['sector']: r['pct_change'] for r in sector_rows if r['sector']}
        spy_return = next((r['pct_change'] for r in sector_rows if r['etf'] == 'SPY'), 0)

        # v16 smart boost: insider purchases + analyst target changes (90 days)
        # Queried here once instead of separately in filter._apply_smart_boost()
        insider_syms = set()
        analyst_up_syms = set()
        analyst_down_syms = set()
        ref_date = scan_date or today_str
        try:
            for r in conn.execute("""
                SELECT DISTINCT symbol FROM insider_transactions_history
                WHERE trade_date >= date(?, '-90 days') AND trade_date <= ?
                AND (transaction_type LIKE '%Purchase%'
                     OR transaction_type LIKE '%Buy%')
                AND value > 10000
            """, (ref_date, ref_date)):
                insider_syms.add(r['symbol'])
        except Exception:
            pass  # table may not exist yet
        try:
            for r in conn.execute("""
                SELECT symbol,
                       AVG((price_target / prior_price_target - 1) * 100) as chg
                FROM analyst_ratings_history
                WHERE date >= date(?, '-90 days') AND date <= ?
                AND price_target > 0 AND prior_price_target > 0
                GROUP BY symbol
            """, (ref_date, ref_date)):
                if r['chg'] and r['chg'] > 5:
                    analyst_up_syms.add(r['symbol'])
                elif r['chg'] and r['chg'] < -5:
                    analyst_down_syms.add(r['symbol'])
        except Exception:
            pass  # table may not exist yet

        # v17: Options bullish/bearish signals (from options_daily_summary)
        options_bullish_syms = set()
        options_bearish_syms = set()
        try:
            for r in conn.execute("""
                SELECT symbol, pc_volume_ratio FROM options_daily_summary
                WHERE collected_date >= date(?, '-3 days')
                AND pc_volume_ratio > 0
            """, (ref_date,)):
                pc = r['pc_volume_ratio']
                if pc < 0.7:
                    options_bullish_syms.add(r['symbol'])
                elif pc > 1.3:
                    options_bearish_syms.add(r['symbol'])
        except Exception:
            pass  # table may not exist yet

        conn.close()

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
            c['sector_1d_change'] = sector_returns_by_name.get(c.get('sector', ''), spy_return)
            if sym in earnings:
                c['days_to_earnings'] = earnings[sym]
            if sym in short_data:
                c['short_pct_float'] = short_data[sym]
            # Smart boost fields (used by filter._apply_smart_boost / SignalTracker)
            c['insider_bought'] = sym in insider_syms
            c['analyst_upgrade'] = sym in analyst_up_syms
            c['analyst_downgrade'] = sym in analyst_down_syms
            c['options_bullish'] = sym in options_bullish_syms
            c['options_bearish'] = sym in options_bearish_syms

    # === v2 fallback (when kernel disabled) ===

    def _score_v2(self, candidates, macro, scan_date):
        """v2: IC-weighted composite score + quality gates (fallback)."""
        if not self._legacy_scorer:
            return []

        qg = self._config.get('quality_gates', {})
        tp_sl_cfg = self._config.get('smart_tp_sl', {})
        adaptive_min_score = self._config.get('layer2', {}).get('min_score', 35)

        picks = []
        for c in candidates:
            score = self._legacy_scorer.compute_layer2_score(c)
            if score < adaptive_min_score:
                continue
            mom5d = c.get('momentum_5d', 0) or 0
            mom20d = c.get('momentum_20d', 0) or 0
            vol_ratio = c.get('volume_ratio', 0) or 0
            sector_1d = c.get('sector_1d_change')
            if sector_1d is None or sector_1d <= qg.get('min_sector_1d_change', 0.0):
                continue
            if mom20d <= qg.get('min_momentum_20d', 0.0):
                continue
            if qg.get('momentum_5d_reject_low', 0.0) <= mom5d < qg.get('momentum_5d_reject_high', 3.0):
                continue
            if mom5d >= qg.get('momentum_5d_max', 10.0):
                continue
            if vol_ratio < qg.get('min_volume_ratio', 0.4):
                continue

            price = c['close']
            atr_pct = c.get('atr_pct', 2.0)
            tp_pct = max(tp_sl_cfg.get('tp_floor', 2.5), tp_sl_cfg.get('tp_atr_mult', 1.2) * atr_pct)
            sl_pct = max(tp_sl_cfg.get('sl_floor', 2.0), tp_sl_cfg.get('sl_atr_mult', 0.8) * atr_pct)
            tp2_pct = tp_pct * tp_sl_cfg.get('tp2_multiplier', 2.0)

            pick = DiscoveryPick(
                symbol=c['symbol'], scan_date=scan_date, scan_price=price,
                current_price=price, layer2_score=score,
                beta=c.get('beta', 0), atr_pct=atr_pct,
                distance_from_high=c.get('distance_from_high', 0),
                distance_from_20d_high=c.get('distance_from_20d_high', 0),
                rsi=c.get('rsi', 0), momentum_5d=mom5d, momentum_20d=mom20d,
                volume_ratio=vol_ratio,
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

    # === DB operations ===

    def _ensure_table(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discovery_picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL, symbol TEXT NOT NULL,
                scan_price REAL NOT NULL, current_price REAL,
                layer2_score REAL, beta REAL, atr_pct REAL,
                distance_from_high REAL, rsi REAL, momentum_5d REAL,
                momentum_20d REAL, volume_ratio REAL,
                sl_price REAL, sl_pct REAL, tp1_price REAL, tp1_pct REAL,
                tp2_price REAL, tp2_pct REAL, sector TEXT, market_cap REAL,
                vix_close REAL, pct_above_20d_ma REAL,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(scan_date, symbol)
            )
        """)
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
            ('premarket_price', 'REAL'), ('gap_pct', 'REAL'),
            ('scan_type', "TEXT DEFAULT 'evening'"),
            ('limit_entry_price', 'REAL'), ('limit_pct', 'REAL'),
            ('entry_price', 'REAL'), ('entry_status', "TEXT DEFAULT 'pending'"),
            ('entry_filled_at', 'TEXT'),
            ('ensemble_json', 'TEXT'), ('council_json', 'TEXT'),
        ]
        for col_name, col_type in new_cols:
            try:
                conn.execute(f"ALTER TABLE discovery_picks ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()

    def _load_picks_from_db(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM discovery_picks WHERE status = 'active'
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
                breadth_delta_5d=r['breadth_delta_5d'],
                vix_delta_5d=r['vix_delta_5d'],
                crude_close=r['crude_close'], gold_close=r['gold_close'],
                dxy_delta_5d=r['dxy_delta_5d'], stress_score=r['stress_score'],
                premarket_price=r['premarket_price'], gap_pct=r['gap_pct'],
                scan_type=r['scan_type'] or 'evening',
                limit_entry_price=r['limit_entry_price'], limit_pct=r['limit_pct'],
                entry_price=r['entry_price'], entry_status=r['entry_status'] or 'pending',
                entry_filled_at=r['entry_filled_at'], status=r['status'] or 'active',
            ))
            for attr, col in [('tp_timeline', 'tp_timeline_json'), ('weekend_play', 'weekend_play_json'),
                              ('ensemble', 'ensemble_json'), ('council', 'council_json')]:
                raw = r[col] if col in r.keys() else None
                if raw:
                    try:
                        setattr(self._picks[-1], attr, json.loads(raw))
                    except (json.JSONDecodeError, TypeError):
                        pass

        if self._picks:
            self._last_scan = self._picks[0].scan_date
            logger.info(f"Discovery: loaded {len(self._picks)} active picks from {self._last_scan}")
            # Restore strategy from council of first pick (survives restart)
            for p in self._picks:
                council = getattr(p, 'council', None)
                if council and isinstance(council, dict) and council.get('strategy'):
                    self._scorer._current_strategy = council['strategy']
                    break

    def _save_picks(self, picks, scan_date):
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
                 tp_timeline_json, weekend_play_json, ensemble_json, council_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                  json.dumps(getattr(p, 'weekend_play', None)),
                  json.dumps(getattr(p, 'ensemble', None)),
                  json.dumps(getattr(p, 'council', None))))
        conn.commit()
        conn.close()
        logger.info(f"Discovery: saved {len(picks)} picks for {scan_date}")

    def _save_multi_strategy(self, scan_date, info):
        """Persist multi-strategy info to DB so webapp can read it after scan exits."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discovery_multi_strategy (
                scan_date TEXT PRIMARY KEY,
                info_json TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT OR REPLACE INTO discovery_multi_strategy (scan_date, info_json) VALUES (?, ?)",
            (scan_date, json.dumps(info, default=str)))
        conn.commit()
        conn.close()
        logger.info("Discovery: saved multi-strategy info for %s", scan_date)

    def _load_multi_strategy(self):
        """Load most recent multi-strategy info from DB."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            row = conn.execute(
                "SELECT scan_date, info_json, updated_at "
                "FROM discovery_multi_strategy ORDER BY scan_date DESC LIMIT 1"
            ).fetchone()
            conn.close()
            if row and row[1]:
                info = json.loads(row[1])
                info['_scan_date'] = row[0]
                info['_updated_at'] = row[2]
                return info
        except Exception:
            pass
        return {}

    def _deactivate_previous_picks(self, new_scan_date):
        conn = sqlite3.connect(str(DB_PATH))
        n = conn.execute("UPDATE discovery_picks SET status = 'replaced', updated_at = datetime('now') WHERE status = 'active'").rowcount
        conn.commit()
        conn.close()
        if n:
            logger.info(f"Discovery: deactivated {n} previous picks")

    def _expire_old_picks(self, current_date):
        max_age = self._config.get('schedule', {}).get('max_pick_age_days', 5)
        lb_cfg = self._config.get('limit_buy', {})
        max_hold = lb_cfg.get('max_hold_days', 2)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("UPDATE discovery_picks SET status = 'expired', updated_at = datetime('now') WHERE status = 'active' AND julianday(?) - julianday(scan_date) > ?", (current_date, max_age))
        if lb_cfg.get('enabled', False):
            conn.execute("UPDATE discovery_picks SET entry_status = 'missed', updated_at = datetime('now') WHERE status = 'active' AND entry_status = 'pending' AND julianday(?) - julianday(scan_date) > ?", (current_date, max_hold))
        conn.commit()
        conn.close()

    # === Price refresh ===

    def _maybe_refresh_prices(self):
        refresh_interval = self._config.get('schedule', {}).get('price_refresh_minutes', 5) * 60
        now = time.monotonic()
        if now - self._last_price_refresh < refresh_interval:
            return
        self._last_price_refresh = now
        self._load_picks_from_db()
        if not self._picks:
            return
        try:
            self.refresh_prices()
        except Exception as e:
            logger.error(f"Discovery: auto price refresh failed: {e}")

    def refresh_prices(self):
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
                        if (pick.entry_status == 'pending'
                                and pick.limit_entry_price is not None
                                and pick.current_price <= pick.limit_entry_price
                                and pick.status == 'active'):
                            pick.entry_status = 'filled'
                            pick.entry_price = pick.limit_entry_price
                            pick.entry_filled_at = datetime.now().strftime('%Y-%m-%d %H:%M')
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

    # === Pre-market validation ===

    def validate_premarket(self) -> dict:
        self._load_picks_from_db()
        active = [p for p in self._picks if p.status == 'active']
        if not active:
            return {'confirmed': 0, 'unconfirmed': 0, 'total': 0}

        symbols = [p.symbol for p in active]
        try:
            import yfinance as yf
            data = yf.download(' '.join(symbols), period='5d', interval='1h',
                               prepost=True, auto_adjust=True, progress=False, threads=False)
        except Exception as e:
            return {'confirmed': 0, 'unconfirmed': 0, 'total': len(active), 'error': str(e)}

        if data.empty:
            return {'confirmed': 0, 'unconfirmed': 0, 'total': len(active)}

        from datetime import time as dtime
        today = datetime.now(ZoneInfo('America/New_York')).date()
        threshold = self._config.get('schedule', {}).get('gap_confirm_threshold', 0.0)
        stp_cfg = self._config.get('v3', {}).get('smart_tp', {})
        gap_thresh = stp_cfg.get('gap_threshold', 0.5)
        gap_boost_mult = stp_cfg.get('gap_boost', 1.3)

        confirmed = unconfirmed = 0
        conn = sqlite3.connect(str(DB_PATH))

        for pick in active:
            try:
                if len(symbols) == 1:
                    sym_data = data
                else:
                    if pick.symbol not in data.columns.get_level_values(1):
                        continue
                    sym_data = data.xs(pick.symbol, axis=1, level=1)

                close_col = sym_data['Close'].dropna()
                if close_col.empty:
                    continue

                premarket_bars = close_col[
                    (close_col.index.date == today) & (close_col.index.time < dtime(9, 30))]
                pm_price = float(premarket_bars.iloc[-1]) if not premarket_bars.empty else float(close_col.iloc[-1])

                gap = (pm_price / pick.scan_price - 1) * 100 if pick.scan_price > 0 else 0.0
                pick.premarket_price = pm_price
                pick.gap_pct = round(gap, 2)

                if gap >= threshold:
                    confirmed += 1
                else:
                    unconfirmed += 1

                old_tp = pick.tp1_pct
                if gap >= gap_thresh and old_tp > 0:
                    new_tp = round(old_tp * gap_boost_mult, 1)
                    pick.tp1_pct = new_tp
                    pick.tp2_pct = new_tp
                    entry_ref = pick.limit_entry_price or pick.scan_price
                    if entry_ref and entry_ref > 0:
                        pick.tp1_price = round(entry_ref * (1 + new_tp / 100), 2)
                        pick.tp2_price = pick.tp1_price

                lb_cfg = self._config.get('limit_buy', {})
                if lb_cfg.get('enabled', False) and pick.limit_pct is not None:
                    limit_price = round(pm_price * (1 - pick.limit_pct / 100), 2)
                    pick.limit_entry_price = limit_price
                    lb_sl = lb_cfg.get('sl_pct', 2.5)
                    pick.sl_price = round(limit_price * (1 - lb_sl / 100), 2)
                    pick.sl_pct = round(lb_sl, 1)
                    pick.tp1_price = round(limit_price * (1 + pick.tp1_pct / 100), 2)
                    pick.tp2_price = pick.tp1_price

                conn.execute(
                    "UPDATE discovery_picks SET premarket_price=?, gap_pct=?, "
                    "limit_entry_price=?, sl_price=?, sl_pct=?, tp1_price=?, tp1_pct=?, "
                    "tp2_price=?, tp2_pct=?, updated_at=datetime('now') "
                    "WHERE symbol=? AND scan_date=? AND status='active'",
                    (pm_price, pick.gap_pct, getattr(pick, 'limit_entry_price', None),
                     pick.sl_price, pick.sl_pct, pick.tp1_price, pick.tp1_pct,
                     pick.tp2_price, pick.tp2_pct, pick.symbol, pick.scan_date))
            except Exception:
                continue

        conn.commit()
        conn.close()
        self._last_validation = datetime.now().strftime('%Y-%m-%d %H:%M')
        summary = {'confirmed': confirmed, 'unconfirmed': unconfirmed, 'total': len(active)}
        logger.info(f"Discovery premarket: {summary}")
        return summary

    # === Intraday re-scan ===

    def run_intraday_scan(self) -> list[DiscoveryPick]:
        sched = self._config.get('schedule', {})
        if not sched.get('intraday_scan_enabled', False):
            return []

        scan_date = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
        intraday_period = sched.get('intraday_period', '1mo')
        max_new = sched.get('intraday_max_new_picks', 3)

        if not self._scorer.is_ready:
            self._scorer.retry_kernel()
            if not self._scorer.is_ready:
                logger.warning("Discovery intraday: kernel not ready")
                return []

        # Refresh temporal/leading
        scan_info = self._scorer.scan_setup(scan_date, self._load_macro(scan_date))

        stocks = self._load_universe()
        macro = self._load_macro(scan_date)

        # Fetch with shorter period
        candidates = []
        batch_size = 50
        symbols = list(stocks.keys())
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            try:
                import yfinance as yf
                data = yf.download(' '.join(batch), period=intraday_period, interval='1d',
                                   auto_adjust=True, progress=False, threads=False)
            except Exception:
                continue
            for sym in batch:
                try:
                    df = data if len(batch) == 1 else (
                        data.xs(sym, axis=1, level=1) if sym in data.columns.get_level_values(1) else None)
                    if df is None or df.empty or len(df) < 20:
                        continue
                    features = self._compute_technical(df, sym, stocks.get(sym, {}))
                    if features:
                        features.update(macro)
                        candidates.append(features)
                except Exception:
                    continue
            if i + batch_size < len(symbols):
                time.sleep(1)

        # Lite enrichment
        self._enrich_candidates_lite(candidates, scan_date)

        # Score with refit=False (returns scored for multi-strategy reuse)
        scan_info['market_regime'] = self._detect_market_regime(macro)
        scan_info['condition'] = detect_condition(
            macro.get('vix_close') or 20, macro.get('pct_above_20d_ma') or 50)

        picks, scored_all, regime_s, macro_er_s = \
            self._run_v3_pipeline_intraday(candidates, macro, scan_date, scan_info)
        try:
            self._multi_strategy_info = self._build_multi_strategy(
                candidates, scored_all, regime_s, macro_er_s,
                macro, scan_info, scan_date)
            self._multi_strategy_loaded_at = time.monotonic()
        except Exception as e:
            logger.error("Discovery intraday: multi-strategy error: %s", e)

        # Merge with existing
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        existing_symbols = {r['symbol'] for r in conn.execute("SELECT symbol FROM discovery_picks WHERE status='active'").fetchall()}

        re_ranked = 0
        for p in picks:
            if p.symbol in existing_symbols:
                conn.execute("UPDATE discovery_picks SET layer2_score=?, current_price=?, updated_at=datetime('now') WHERE symbol=? AND status='active'",
                             (p.layer2_score, p.current_price, p.symbol))
                re_ranked += 1
        conn.commit()
        conn.close()

        new_intraday = [p for p in picks if p.symbol not in existing_symbols][:max_new]
        for p in new_intraday:
            p.scan_type = 'intraday'
        if new_intraday:
            self._save_picks(new_intraday, scan_date)

        self._load_picks_from_db()
        self._last_intraday_scan = datetime.now().strftime('%Y-%m-%d %H:%M')
        logger.info("Discovery intraday: re-ranked %d, added %d new", re_ranked, len(new_intraday))
        return new_intraday

    def _run_v3_pipeline_intraday(self, candidates, macro, scan_date, scan_info):
        """Intraday pipeline — same as _run_v3_pipeline but with refit=False.

        Returns (picks, scored_all, regime, macro_er) for reuse by multi-strategy.
        """
        scored, regime, macro_er = self._scorer.score_batch(
            candidates, macro, scan_date, refit=False)
        if not scored:
            return [], [], 'STRESS', 0.0
        strategy_mode = scan_info['strategy'].get('strategy', 'SELECTIVE')
        filtered = self._filter.apply(
            scored, macro, regime, strategy_mode, self._config,
            unified_brain=self._scorer.unified_brain,
            sensors=self._scorer._sensors,
            temporal_features=scan_info.get('temporal_features', {}),
            scan_date=scan_date,
            context_scorer=self._sizer.context_scorer,
            regime_decision=scan_info.get('regime_decision', {}))
        picks = []
        for score, candidate in filtered:
            pick = self._sizer.create_pick(
                candidate, score, macro, regime, macro_er,
                scan_info['strategy'], scan_info.get('regime_decision', {}),
                scan_date, picks, self._scorer)
            if pick:
                picks.append(pick)
        return picks, scored, regime, macro_er

    def _enrich_candidates_lite(self, candidates, scan_date: str = None):
        if not candidates:
            return
        symbols = [c['symbol'] for c in candidates]
        placeholders = ','.join('?' * len(symbols))
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        today_str = date.today().isoformat()
        ref_date = scan_date or today_str
        earnings = {}
        for r in conn.execute(f"SELECT symbol, MIN(report_date) as next_date FROM earnings_history WHERE symbol IN ({placeholders}) AND report_date >= ? GROUP BY symbol", symbols + [today_str]).fetchall():
            try:
                ed = datetime.strptime(r['next_date'][:10], '%Y-%m-%d').date()
                earnings[r['symbol']] = (ed - date.today()).days
            except Exception:
                pass
        sector_rows = conn.execute("SELECT etf, sector, pct_change FROM sector_etf_daily_returns WHERE date = (SELECT MAX(date) FROM sector_etf_daily_returns)").fetchall()
        sector_returns_by_name = {r['sector']: r['pct_change'] for r in sector_rows if r['sector']}
        spy_return = next((r['pct_change'] for r in sector_rows if r['etf'] == 'SPY'), 0)

        # Smart boost: insider purchases + analyst target changes (same as _enrich_candidates)
        insider_syms = set()
        analyst_up_syms = set()
        analyst_down_syms = set()
        try:
            for r in conn.execute("""
                SELECT DISTINCT symbol FROM insider_transactions_history
                WHERE trade_date >= date(?, '-90 days') AND trade_date <= ?
                AND (transaction_type LIKE '%Purchase%'
                     OR transaction_type LIKE '%Buy%')
                AND value > 10000
            """, (ref_date, ref_date)):
                insider_syms.add(r['symbol'])
        except Exception:
            pass
        try:
            for r in conn.execute("""
                SELECT symbol,
                       AVG((price_target / prior_price_target - 1) * 100) as chg
                FROM analyst_ratings_history
                WHERE date >= date(?, '-90 days') AND date <= ?
                AND price_target > 0 AND prior_price_target > 0
                GROUP BY symbol
            """, (ref_date, ref_date)):
                if r['chg'] and r['chg'] > 5:
                    analyst_up_syms.add(r['symbol'])
                elif r['chg'] and r['chg'] < -5:
                    analyst_down_syms.add(r['symbol'])
        except Exception:
            pass

        # v17: Options bullish/bearish signals
        options_bullish_syms = set()
        options_bearish_syms = set()
        try:
            for r in conn.execute("""
                SELECT symbol, pc_volume_ratio FROM options_daily_summary
                WHERE collected_date >= date(?, '-3 days')
                AND pc_volume_ratio > 0
            """, (ref_date,)):
                pc = r['pc_volume_ratio']
                if pc < 0.7:
                    options_bullish_syms.add(r['symbol'])
                elif pc > 1.3:
                    options_bearish_syms.add(r['symbol'])
        except Exception:
            pass

        conn.close()
        for c in candidates:
            sym = c['symbol']
            c['sector_1d_change'] = sector_returns_by_name.get(c.get('sector', ''), spy_return)
            if sym in earnings:
                c['days_to_earnings'] = earnings[sym]
            c['insider_bought'] = sym in insider_syms
            c['analyst_upgrade'] = sym in analyst_up_syms
            c['analyst_downgrade'] = sym in analyst_down_syms
            c['options_bullish'] = sym in options_bullish_syms
            c['options_bearish'] = sym in options_bearish_syms


# Singleton
_engine: Optional[DiscoveryEngine] = None


def get_discovery_engine() -> DiscoveryEngine:
    global _engine
    if _engine is None:
        _engine = DiscoveryEngine()
    return _engine
