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
from database.orm.base import get_session
from sqlalchemy import text
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
from discovery.multi_strategy import (StrategySelector, detect_condition, classify_regime,
                                      classify_strategy, STRATEGIES, PC_BULLISH, PC_BEARISH)
from discovery.outcome_tracker import OutcomeTracker
from discovery.market_signals import MarketSignalEngine
from discovery.param_manager import ParamManager
from discovery.param_optimizer import ParamOptimizer
from discovery.performance_tracker import PerformanceTracker
from discovery.auto_refit import AutoRefitOrchestrator
from discovery.sector_scorer import SectorScorer
from discovery.adaptive_stock_selector import AdaptiveStockSelector
from discovery.signal_tracker import SignalTracker
from discovery.gap_scanner import GapScanner
from discovery.trailing_tp_tracker import TrailingTPTracker

logger = logging.getLogger(__name__)

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
        # v17: Wire adaptive params into scorer + strategy_router
        self._scorer._adaptive_params = self._adaptive_params
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

        # v18: Gap Scanner — predict next-day gap-ups
        self._gap_scanner = GapScanner()
        if not self._gap_scanner.load_from_db():
            try:
                self._gap_scanner.fit()
                self._gap_scanner.save_to_db()
            except Exception as e:
                logger.error("Discovery: gap scanner fit error: %s", e)

        # v19: Discovery Ranker — ML ranking of picks by predicted d3 return
        from discovery.discovery_ranker import DiscoveryRanker
        self._discovery_ranker = DiscoveryRanker()
        if not self._discovery_ranker.load_from_db():
            try:
                self._discovery_ranker.fit()
            except Exception as e:
                logger.error("Discovery: ranker fit error: %s", e)

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

        # v20: Trailing TP tracker
        self._trailing_tp = TrailingTPTracker()

        # v20: Quality filters — consecutive loss pause + dynamic blacklist
        self._blacklist: set = set()
        self._blacklist_loaded_at: float = 0
        self._refresh_blacklist()

        self._ensure_table()
        self._load_picks_from_db()

    # === v20: Quality filters ===

    def _should_pause_discovery(self) -> bool:
        """Check if Discovery should pause due to loss regime.
        If last 1 day had WR < 50% (N>=5), pause for 2 days.
        Validated: skipped days avg WR=37.8%, improves overall WR +6.2%.
        """
        try:
            with get_session() as session:
                rows = session.execute(text("""
                    SELECT scan_date,
                           AVG(CASE WHEN actual_return_d3 > 0 THEN 1.0 ELSE 0.0 END) * 100 as wr,
                           COUNT(*) as n
                    FROM discovery_outcomes
                    WHERE actual_return_d3 IS NOT NULL
                      AND scan_date >= date('now', '-7 days')
                    GROUP BY scan_date
                    ORDER BY scan_date DESC
                    LIMIT 3
                """)).fetchall()

            if len(rows) < 1:
                return False

            # If last day WR < 50% → pause 2 days
            last_day_bad = rows[0][1] < 50 and rows[0][2] >= 5
            # Also pause if 2 days ago was bad (2-day pause duration)
            two_days_ago_bad = len(rows) >= 2 and rows[1][1] < 50 and rows[1][2] >= 5

            should_pause = last_day_bad or two_days_ago_bad
            if should_pause:
                logger.warning("Discovery: PAUSED — recent day WR < 50%% (%s)",
                               [(r[0], f"{r[1]:.0f}%", f"n={r[2]}") for r in rows[:2]])
            return should_pause
        except Exception as e:
            logger.error("Discovery: pause check error: %s", e)
            return False

    def _refresh_blacklist(self):
        """Refresh dynamic blacklist: symbols with WR < 40% and N >= 10 outcomes."""
        try:
            with get_session() as session:
                rows = session.execute(text("""
                    SELECT symbol FROM discovery_outcomes
                    WHERE actual_return_d3 IS NOT NULL
                    GROUP BY symbol
                    HAVING COUNT(*) >= 10
                    AND AVG(CASE WHEN actual_return_d3 > 0 THEN 1.0 ELSE 0.0 END) < 0.40
                """)).fetchall()
            self._blacklist = {r[0] for r in rows}
            self._blacklist_loaded_at = time.monotonic()
            if self._blacklist:
                logger.info("Discovery: blacklist refreshed — %d symbols: %s",
                            len(self._blacklist), sorted(self._blacklist))
        except Exception as e:
            logger.error("Discovery: blacklist refresh error: %s", e)
            self._blacklist = set()

    def _get_blacklist(self) -> set:
        """Get dynamic blacklist, refresh monthly (every 30 days)."""
        if time.monotonic() - self._blacklist_loaded_at > 30 * 86400:
            self._refresh_blacklist()
        return self._blacklist

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

    def get_trailing_tp_alerts(self) -> list[dict]:
        """Return current trailing TP alerts for API."""
        return self._trailing_tp.get_alerts()

    def get_trailing_tp_state(self) -> dict:
        """Return trailing state for all tracked symbols."""
        return self._trailing_tp.get_trailing_state()

    def get_stats(self) -> dict:
        """Historical performance statistics from picks with filled outcomes."""
        with get_session() as session:
            stats_row = session.execute(text("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) as wins_5d,
                       SUM(CASE WHEN outcome_5d IS NOT NULL THEN 1 ELSE 0 END) as has_outcome,
                       AVG(outcome_1d) as avg_1d, AVG(outcome_5d) as avg_5d,
                       AVG(outcome_max_gain_5d) as avg_max_gain,
                       AVG(outcome_max_dd_5d) as avg_max_dd,
                       SUM(CASE WHEN status='hit_tp1' THEN 1 ELSE 0 END) as tp1_hits,
                       SUM(CASE WHEN status='hit_sl' THEN 1 ELSE 0 END) as sl_hits
                FROM discovery_picks
            """)).fetchone()
            stats_row = dict(stats_row._mapping) if stats_row else {}

            sector_rows = session.execute(text("""
                SELECT sector, COUNT(*) as n,
                       SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) as wins,
                       AVG(outcome_5d) as avg_5d
                FROM discovery_picks WHERE outcome_5d IS NOT NULL
                GROUP BY sector ORDER BY n DESC
            """)).mappings().fetchall()

            tier_rows = session.execute(text("""
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
            """)).mappings().fetchall()

            active_sectors = session.execute(text("""
                SELECT sector, COUNT(*) as n FROM discovery_picks
                WHERE status = 'active' GROUP BY sector ORDER BY n DESC
            """)).mappings().fetchall()

            try:
                bench_row = session.execute(text("""
                    SELECT AVG(outcome_5d) as picks_avg,
                           AVG(benchmark_xlu_5d) as xlu_avg,
                           AVG(benchmark_xle_5d) as xle_avg,
                           AVG(benchmark_spy_5d) as spy_avg, COUNT(*) as n
                    FROM discovery_picks
                    WHERE outcome_5d IS NOT NULL AND benchmark_spy_5d IS NOT NULL
                """)).fetchone()
                bench_row = dict(bench_row._mapping) if bench_row else None
            except Exception:
                bench_row = None

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
            with get_session() as session:
                rows = session.execute(text(
                    "SELECT close FROM stock_daily_ohlc "
                    "WHERE symbol='SPY' ORDER BY date DESC LIMIT 50"
                )).fetchall()

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

        # v20: Consecutive loss pause — skip scan if last 2 days WR < 45%
        if self._should_pause_discovery():
            logger.info("Discovery: scan PAUSED due to consecutive losses — returning empty")
            self._scan_progress = {'status': 'done', 'pct': 100,
                                   'stage': 'PAUSED: consecutive loss days', 'l1': 0, 'l2': 0}
            return []

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
        scan_info['condition'] = detect_condition(vix or 20, macro.get('pct_above_20d_ma') or 50, adaptive=self._adaptive_params)
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

        # 13. v18: Gap Scanner — predict next-day gap-ups
        gap_picks = []
        try:
            gap_candidates = self._gap_scanner.scan(macro, scan_date)
            existing_syms = {p.symbol for p in picks}
            for gc in gap_candidates:
                if gc['symbol'] in existing_syms:
                    continue  # dedupe
                gap_pick = self._create_gap_pick(gc, macro, scan_date, regime_from_score)
                if gap_pick:
                    gap_picks.append(gap_pick)
                    existing_syms.add(gap_pick.symbol)
            if gap_picks:
                logger.info("Discovery v18: %d gap picks added [%s]",
                            len(gap_picks),
                            ', '.join(p.symbol for p in gap_picks))
        except Exception as e:
            logger.error("Discovery: gap scan error: %s", e)

        # Concat: max 3 gap + max 7 discovery = max 10 total
        all_picks = gap_picks[:3] + picks[:7]

        # 14. Deactivate old + save new
        self._expire_old_picks(scan_date)
        self._deactivate_previous_picks(scan_date)
        self._save_picks(all_picks, scan_date)

        self._picks = all_picks
        self._last_scan = scan_date
        self._scan_progress = {'status': 'done', 'pct': 100,
                               'stage': f'Done: {len(all_picks)} picks ({len(gap_picks)} gap)',
                               'l1': len(candidates), 'l2': len(all_picks)}
        return all_picks

    def _run_v3_pipeline(self, candidates, macro, scan_date, scan_info, refit=True):
        """v17 adaptive pipeline: Strategy ranking → Sector filter → Signal boost → Filter → Size.

        1. Kernel scoring for regime detection (macro E[R])
        2. v17 ranking: strategy×sector×regime Sharpe (replaces E[R] ranking)
           Data: Sharpe +0.088 vs E[R] +0.067 (+30% improvement)
           E[R] predicts regime but NOT individual stock ranking
        3. SectorScorer hard-blocks bad sectors
        4. Filter pipeline (ATR, beta, PE, etc.) for safety
        5. Sizer creates picks with SL/TP + council

        Returns (picks, scored_all, regime, macro_er).
        """
        # 1. Kernel scoring — regime detection only (E[R] NOT used for ranking)
        scored, regime, macro_er = self._scorer.score_batch(
            candidates, macro, scan_date, refit=refit)
        if not scored:
            return [], [], 'STRESS', 0.0

        # 1b. VIX<18 hard throttle — validated: VIX<18 WR ~50.6% (no edge)
        # VIX 18-20 has some edge, VIX<18 is dead zone
        vix_val = macro.get('vix_close', 20) or 20
        if vix_val < 18:
            scored = [(s, c) for s, c in scored if s > 0.8]
            logger.info("Discovery: VIX<18 throttle — %d candidates", len(scored))
        elif vix_val < 20:
            scored = [(s, c) for s, c in scored if s > 0.5]
            logger.info("Discovery: VIX 18-20 soft throttle — %d candidates", len(scored))

        # 1b2. VIX term structure gate — deep panic filter
        # VIX/VIX3M >= 1.1 = deep panic, WR 45.4% historically — raise threshold
        vix3m = macro.get('vix3m_close', 20) or 20
        if vix3m > 0 and vix_val / vix3m >= 1.1:
            logger.info("Discovery: VIX term inverted (%.2f) — reducing picks", vix_val / vix3m)
            scored = [(s, c) for s, c in scored if s > 1.0]

        # 1b3. Worst day+regime combo exclusion
        # Mon/Fri + VIX<20 + BULL = WR 48.6% (no edge) — raise threshold
        from datetime import datetime
        from zoneinfo import ZoneInfo
        et_now = datetime.now(ZoneInfo('America/New_York'))
        dow = et_now.weekday()  # 0=Mon, 4=Fri
        is_mon_fri = dow in (0, 4)
        if is_mon_fri and vix_val < 20 and regime == 'BULL':
            scored = [(s, c) for s, c in scored if s > 0.8]
            logger.info("Discovery: Mon/Fri+VIX<20+BULL throttle — %d candidates", len(scored))

        # 1b4. September throttle — WR 46.3% worst month consistently
        # Not hard skip — raise threshold so only strong picks survive
        if et_now.month == 9:
            scored = [(s, c) for s, c in scored if s > 1.0]
            logger.info("Discovery: September throttle — %d candidates (raised threshold)", len(scored))

        # 1c. Day-of-week enrichment for ML selector
        for _, c in scored:
            c['_day_of_week'] = dow
            c['_is_monday'] = 1 if dow == 0 else 0
            c['_is_friday'] = 1 if dow == 4 else 0

        # 1d. v20: Earnings proximity skip — skip stocks with earnings within 3 days
        pre_earnings_count = len(scored)
        scored = [(s, c) for s, c in scored
                  if not (c.get('days_to_earnings') is not None
                          and abs(c.get('days_to_earnings', 999)) <= 3)]
        if len(scored) < pre_earnings_count:
            logger.info("Discovery v20: earnings proximity skip removed %d candidates (within 3 days)",
                        pre_earnings_count - len(scored))

        # 1e2. v21: Beta/PE catastrophic risk filter
        # Beta > 1.8 OR PE extreme (<0 or >100) = 3.8x catastrophic rate
        # Removes 8.7% of picks, prevents 25% of -10%+ losses
        # Validated: stable across all 7 years, WR +0.36%
        pre_risk_count = len(scored)
        risk_removed = []
        filtered_scored = []
        for s, c in scored:
            beta = c.get('beta', 1.0) or 1.0
            pe = c.get('pe_forward', 20) or 20
            pe_extreme = pe < 0 or pe > 100
            if beta > 1.8 or pe_extreme:
                risk_removed.append(f"{c.get('symbol','')}(b={beta:.1f},pe={pe:.0f})")
            else:
                filtered_scored.append((s, c))
        scored = filtered_scored
        if risk_removed:
            logger.info("Discovery v21: Beta/PE risk filter removed %d: %s",
                        len(risk_removed), ', '.join(risk_removed[:5]))

        # 1e. v20: Dynamic blacklist — skip symbols with WR < 40% (N>=10)
        blacklist = self._get_blacklist()
        if blacklist:
            pre_bl_count = len(scored)
            bl_removed = [c.get('symbol') for _, c in scored if c.get('symbol', '') in blacklist]
            scored = [(s, c) for s, c in scored if c.get('symbol', '') not in blacklist]
            if bl_removed:
                logger.info("Discovery v20: blacklist removed %d candidates: %s",
                            len(bl_removed), bl_removed[:5])

        # 1f. v22: Strategy Router — match strategy to regime
        # Validated on 75K outcomes (unbiased per-strategy analysis):
        #   BULL (VIX<20): PF=1.00 all strategies → heavy throttle
        #   STRESS (VIX 20-25): MOMENTUM best (WR 56%, PF 1.35)
        #   CRISIS (VIX 25+): DIP/OVERSOLD best (WR 59%, PF 1.23)
        #   VALUE: best when SPY down + PE<10 + mcap>50B (WR 66%)
        #   VOL_U: WR 28% → remove entirely
        spy_ret_5d = macro.get('spy_5d_ret', 0) or 0
        spy_down = spy_ret_5d < -1

        pre_router_count = len(scored)
        routed_scored = []
        for s, c in scored:
            strategy = c.get('_matched_strategy', '')
            mom5d = c.get('momentum_5d', 0) or 0
            dist20h = c.get('distance_from_20d_high', c.get('d20h', -10)) or -10
            pe = c.get('pe_forward', 20) or 20
            mcap = c.get('market_cap', 0) or 0
            atr = c.get('atr_pct', 3) or 3

            # Classify pick type by characteristics (when strategy tag not available)
            is_momentum = mom5d > 3 and dist20h > -3
            is_dip = mom5d < -3 and dist20h < -10
            is_value = 0 < pe < 15 and dist20h < -15
            is_oversold = mom5d < -8 and dist20h < -20

            keep = True
            boost = 0

            # VOL_U removal (WR 28%, no fix)
            if strategy == 'VOL_U':
                keep = False

            # BULL regime: only keep momentum with low ATR, or value with cheap PE
            elif regime == 'BULL':
                if is_momentum and atr < 3:
                    boost = 0.1  # momentum OK in BULL if low vol
                elif is_value and pe < 10 and mcap > 50e9:
                    boost = 0.2  # value quality OK
                elif is_dip or is_oversold:
                    keep = s > 0.8  # dip in BULL needs high score to pass

            # STRESS regime: prefer momentum (stocks holding up = leaders)
            elif regime == 'STRESS':
                if is_momentum:
                    boost = 0.2  # STRESS + momentum = WR 56%
                elif is_value and spy_down:
                    boost = 0.3  # VALUE + SPY down = WR 66%

            # CRISIS regime: prefer dip/oversold (extreme bounce)
            elif regime == 'CRISIS':
                if is_dip or is_oversold:
                    boost = 0.2  # CRISIS + dip = WR 59%
                elif is_momentum:
                    boost = -0.1  # momentum in crisis = risky

            if keep:
                routed_scored.append((s + boost, c))

        scored = routed_scored
        if len(scored) < pre_router_count:
            logger.info("Discovery v22: strategy router — %d → %d candidates (regime=%s, spy_5d=%+.1f%%)",
                        pre_router_count, len(scored), regime, spy_ret_5d)

        # 2. v17: Re-rank by ML probability or context Sharpe
        if self._stock_selector._fitted and self._v17_enabled:
            scored = self._rank_by_ml_probability(scored, candidates, macro, scan_info, regime)
        else:
            scored = self._rank_by_context_sharpe(scored, candidates, macro, scan_info, regime)

        # 3. v17: Gap filter for evening scan + gap boost for intraday
        scored = self._apply_gap_filter(scored, scan_info)

        # 4. v17: Sector scores as soft signal
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

        # 7. v19: Discovery Ranker — soft re-rank by predicted d3 return
        if self._discovery_ranker and self._discovery_ranker._fitted and picks:
            try:
                self._discovery_ranker.rank(picks, macro)
                picks.sort(key=lambda p: getattr(p, '_rank_score', 0), reverse=True)
                logger.info("Discovery: ranker re-sorted %d picks", len(picks))
            except Exception as e:
                logger.warning("Discovery: ranker error: %s", e)

        logger.info(
            "Discovery v17: %d picks [%s/%s] (macro E[R]=%+.2f%%, from %d candidates)",
            len(picks), regime, strategy_mode, macro_er, len(candidates))
        return picks, scored, regime, macro_er

    def _rank_by_ml_probability(self, scored, candidates, macro, scan_info, regime):
        """v17: Rank by AdaptiveStockSelector ML probability.

        Uses smart E[R] + strategy×regime Sharpe + sector×regime Sharpe
        as features — model learns optimal combination automatically.
        Sharpe +0.185 vs +0.172 context-only (+8%).
        """
        sector_scores = scan_info.get('sector_scores', {})
        condition = scan_info.get('condition', 'NORMAL')

        # Get strategy assignments
        strat_map = {}
        if self._strategy_selector._fitted:
            market_regime = scan_info.get('market_regime')
            ranked = self._strategy_selector.get_ranked_picks(
                candidates, macro, market_regime=market_regime)
            for strat_name, pick in ranked:
                sym = pick.get('symbol', '')
                if sym not in strat_map:
                    strat_map[sym] = strat_name

        # Build context map — all raw features for 25-feature ML model
        context_map = {}

        # Pre-compute market-level features (same for all stocks)
        vix = macro.get('vix_close') or 20
        vix3m = macro.get('vix3m_close') or (vix * 1.05)
        vix_spread = vix - vix3m
        breadth_d5 = macro.get('breadth_delta_5d') or 0
        spy_5d = 0
        try:
            from database.orm.base import get_session as _gs; _sess = _gs().__enter__(); conn_tmp = type("C", (), {"execute": lambda self, sql, params=(): _sess.execute(text(sql.replace("?", ":p")), dict(enumerate(params)))})()
            spy_rows = conn_tmp.execute("SELECT spy_close FROM macro_snapshots WHERE spy_close IS NOT NULL ORDER BY date DESC LIMIT 6").fetchall()
            if len(spy_rows) >= 6:
                spy_5d = (spy_rows[0][0] / spy_rows[5][0] - 1) * 100 if spy_rows[5][0] > 0 else 0
            # N sectors up yesterday
            n_up_row = conn_tmp.execute("""
                SELECT SUM(CASE WHEN pct_change > 0 THEN 1 ELSE 0 END)
                FROM sector_etf_daily_returns
                WHERE date = (SELECT MAX(date) FROM sector_etf_daily_returns)
                AND sector NOT IN ('S&P 500','US Dollar','Treasury Long','Gold') AND sector IS NOT NULL
            """).fetchone()
            n_sectors_up = n_up_row[0] or 5 if n_up_row else 5
            # Sector mom 1d + news + analyst
            sector_mom_1d = {}
            for r in conn_tmp.execute("""
                SELECT sector, pct_change FROM sector_etf_daily_returns
                WHERE date = (SELECT MAX(date) FROM sector_etf_daily_returns)
                AND sector IS NOT NULL
            """).fetchall():
                sector_mom_1d[r[0]] = r[1] or 0
            sector_news = {}
            try:
                for r in conn_tmp.execute("""
                    SELECT sf.sector, AVG(ne.sentiment_score)
                    FROM news_events ne JOIN stock_fundamentals sf ON ne.symbol = sf.symbol
                    WHERE ne.published_at >= date('now', '-7 days') AND ne.sentiment_score IS NOT NULL
                    GROUP BY sf.sector
                """).fetchall():
                    sector_news[r[0]] = r[1] or 0
            except: pass
            sector_analyst = {}
            try:
                for r in conn_tmp.execute("""
                    SELECT sf.sector,
                        SUM(CASE WHEN arh.price_target > arh.prior_price_target*1.05 AND arh.prior_price_target>0 THEN 1 ELSE 0 END) -
                        SUM(CASE WHEN arh.price_target < arh.prior_price_target*0.95 AND arh.prior_price_target>0 THEN 1 ELSE 0 END)
                    FROM analyst_ratings_history arh JOIN stock_fundamentals sf ON arh.symbol = sf.symbol
                    WHERE arh.date >= date('now', '-7 days') AND arh.price_target > 0
                    GROUP BY sf.sector
                """).fetchall():
                    sector_analyst[r[0]] = r[1] or 0
            except: pass
            # Stock context (crude/VIX sensitivity)
            crude_sens = {}; vix_sens = {}
            for r in conn_tmp.execute("SELECT symbol, context_type, score FROM stock_context WHERE context_type IN ('CRUDE_SENSITIVE','VIX_SENSITIVE')").fetchall():
                if r[1] == 'CRUDE_SENSITIVE': crude_sens[r[0]] = r[2] or 0
                else: vix_sens[r[0]] = r[2] or 0
            # Stock news sentiment
            stock_news = {}
            try:
                for r in conn_tmp.execute("""
                    SELECT symbol, AVG(sentiment_score) FROM news_events
                    WHERE published_at >= date('now', '-7 days') AND symbol IS NOT NULL AND sentiment_score IS NOT NULL
                    GROUP BY symbol
                """).fetchall():
                    stock_news[r[0]] = r[1] or 0
            except: pass
            conn_tmp.close()
        except Exception as e:
            logger.error("ML context error: %s", e)
            n_sectors_up = 5; sector_mom_1d = {}; sector_news = {}; sector_analyst = {}
            crude_sens = {}; vix_sens = {}; stock_news = {}

        for er, c in scored:
            sym = c.get('symbol', '')
            sector = c.get('sector', '')
            strat = strat_map.get(sym) or self._infer_strategy_label(c)
            c['_matched_strategy'] = strat

            strat_sharpe = self._strategy_selector._fit_stats.get(
                (condition, strat), {}).get('sharpe', 0)

            context_map[sym] = {
                'stock_news_sent': stock_news.get(sym, 0),
                'crude_sensitivity': crude_sens.get(sym, 0),
                'vix_sensitivity': vix_sens.get(sym, 0),
                'sector_mom_1d': sector_mom_1d.get(sector, 0),
                'sector_news_sent': sector_news.get(sector, 0),
                'sector_analyst_net': sector_analyst.get(sector, 0),
                'vix_spread': vix_spread,
                'breadth_delta_5d': breadth_d5,
                'spy_5d_ret': spy_5d,
                'n_sectors_up': n_sectors_up,
                'strat_sharpe': strat_sharpe,
                'cluster_health': sector_scores.get(sector, 0),
            }

        # Get ML probabilities
        ml_results = self._stock_selector.predict(
            candidates, sector_scores, context_map=context_map)

        if not ml_results:
            logger.warning("Discovery v17: ML predict failed — fallback to context Sharpe")
            return self._rank_by_context_sharpe(scored, candidates, macro, scan_info, regime)

        # Build (score, candidate) list from ML probabilities
        ml_map = {c.get('symbol'): prob for prob, c in ml_results}
        re_scored = []
        for er, c in scored:
            sym = c.get('symbol', '')
            prob = ml_map.get(sym, 0.5)
            # Map probability to score scale: 0.5→0, 0.6→1.0, 0.7→2.0
            ml_score = (prob - 0.5) * 10
            re_scored.append((ml_score, c))

        re_scored.sort(key=lambda x: x[0], reverse=True)

        if re_scored:
            top3 = [(c.get('symbol'), c.get('_matched_strategy'), round(sc, 2))
                     for sc, c in re_scored[:3]]
            logger.info("Discovery v17: ranked by ML probability (condition=%s) top=%s",
                        condition, top3)

        return re_scored

    def _rank_by_context_sharpe(self, scored, candidates, macro, scan_info, regime):
        """v17: Rank stocks by strategy×sector×regime Sharpe.

        Instead of E[R] (which predicts regime, not individual stocks),
        rank by: "this strategy in this sector during this regime historically
        gave Sharpe X" — data-validated +30% improvement over E[R] ranking.

        Also assigns _matched_strategy label from strategy matching.
        """
        # Get strategy assignments from StrategySelector
        strat_map = {}  # {symbol: strategy_name}
        if self._strategy_selector._fitted:
            market_regime = scan_info.get('market_regime')
            ranked = self._strategy_selector.get_ranked_picks(
                candidates, macro, market_regime=market_regime)
            for strat_name, pick in ranked:
                sym = pick.get('symbol', '')
                if sym not in strat_map:
                    strat_map[sym] = strat_name

        # Load strategy×regime Sharpe from fit stats
        strat_sharpes = {}
        for (condition, strat_name), stats in self._strategy_selector._fit_stats.items():
            if stats.get('sharpe') is not None:
                strat_sharpes[(condition, strat_name)] = stats['sharpe']

        # Load sector scores for sector×regime signal
        sector_scores = scan_info.get('sector_scores', {})

        # Determine current condition
        condition = scan_info.get('condition', 'NORMAL')

        # Re-score each candidate
        re_scored = []
        for er, c in scored:
            sym = c.get('symbol', '')
            sector = c.get('sector', '')

            # Strategy label
            strat = strat_map.get(sym)
            if not strat:
                strat = self._infer_strategy_label(c)
            c['_matched_strategy'] = strat

            # Context Sharpe score:
            # = strategy Sharpe in current condition × 5
            # + sector score × 3
            strat_sh = strat_sharpes.get((condition, strat), 0)
            sect_sc = sector_scores.get(sector, 0)

            # v17: Learned ranking weights (default 5/3, learned per sector×regime)
            w_strat = 5
            w_sect = 3
            if self._adaptive_params:
                w_strat = self._adaptive_params.get(sector, regime, 'rank_w_strat')
                w_sect = self._adaptive_params.get(sector, regime, 'rank_w_sect')
            context_score = max(0, strat_sh) * w_strat + max(0, sect_sc) * w_sect

            re_scored.append((context_score, c))

        re_scored.sort(key=lambda x: x[0], reverse=True)

        # Log top picks
        if re_scored:
            top3 = [(c.get('symbol'), c.get('_matched_strategy'), round(sc, 2))
                     for sc, c in re_scored[:3]]
            logger.info("Discovery v17: ranked by context Sharpe (condition=%s) top=%s",
                        condition, top3)

        return re_scored

    def _apply_gap_filter(self, scored, scan_info):
        """v17: Gap handling — different for evening vs intraday.

        Evening scan (gap_pct=0): Use gap PREDICTOR to filter
          → keep only stocks with predicted gap_up probability > 50%
          → Sharpe +35% improvement vs no filter

        Intraday scan (gap_pct available): Use ACTUAL gap as boost
          → IC=+0.259, proportional boost
        """
        has_actual_gap = any(c.get('gap_pct', 0) != 0 for _, c in scored[:10])

        if has_actual_gap:
            # Intraday: use actual gap as boost
            boosted = []
            for er, c in scored:
                gap = c.get('gap_pct', 0)
                if gap != 0:
                    boosted.append((er + gap * 0.5, c))
                else:
                    boosted.append((er, c))
            boosted.sort(key=lambda x: x[0], reverse=True)
            return boosted

        # Evening: use gap predictor to filter
        if not (self._v17_enabled and self._stock_selector._gap_model is not None):
            return scored

        # v17: gap filter threshold learned per sector×regime
        gap_threshold = 0.5
        if self._adaptive_params:
            gap_threshold = self._adaptive_params.get('', 'BULL', 'gap_filter_prob')

        filtered = []
        n_removed = 0
        for er, c in scored:
            gap_prob = self._stock_selector.predict_gap(c)
            c['_gap_prob'] = round(gap_prob, 3)
            if gap_prob >= gap_threshold:
                filtered.append((er, c))
            else:
                n_removed += 1

        if n_removed:
            logger.info("Discovery v17: gap filter removed %d/%d stocks (gap_prob < 50%%)",
                        n_removed, len(scored))

        # Fallback: if filter removes too many, keep top by gap_prob
        if len(filtered) < 5 and scored:
            filtered = sorted(scored, key=lambda x: self._stock_selector.predict_gap(x[1]), reverse=True)[:len(scored)//2]

        return filtered

    def _apply_sector_boost(self, scored, scan_info):
        """v17: Sector score as SOFT signal — no hard-blocking.

        ML model already has sect_sharpe as feature (importance 0.132).
        Sector scores are passed through for ML to learn from,
        NOT used to hard-block sectors.

        Removed: hard-blocking (contrarian approach not validated from data)
        Data: bottom momentum sectors avg +0.040% vs top +0.042% → no edge
        """
        # No hard-blocking — ML decides via sect_sharpe feature
        # Sector scores are already in ML features via context_map
        return scored

    def _infer_strategy_label(self, candidate):
        """Infer strategy label from stock features. Uses shared classify_strategy()."""
        return classify_strategy(
            candidate.get('momentum_5d'),
            candidate.get('distance_from_20d_high'),
            candidate.get('volume_ratio'),
            candidate.get('pe_forward'),
            adaptive=self._adaptive_params)

    def _create_gap_pick(self, gc: dict, macro: dict, scan_date: str, regime: str) -> 'DiscoveryPick':
        """Create a DiscoveryPick from a gap scanner candidate."""
        try:
            price = gc['close']
            atr_pct = gc.get('atr_pct', 3.0) or 3.0
            gap_type = gc.get('_gap_type', 'COMMON')
            gap_score = gc.get('_gap_score', 0)
            reasons = gc.get('_gap_reasons', [])

            # SL/TP based on gap type
            if gap_type == 'SECTOR_BOUNCE':
                sl_pct = min(atr_pct * 1.5, 5.0)
                tp_pct = atr_pct * 2.0
            elif gap_type == 'BREAKAWAY':
                sl_pct = min(atr_pct * 2.0, 5.0)
                tp_pct = atr_pct * 3.0
            else:
                sl_pct = min(atr_pct * 1.5, 4.0)
                tp_pct = atr_pct * 2.0

            sl_price = round(price * (1 - sl_pct / 100), 2)
            tp_price = round(price * (1 + tp_pct / 100), 2)

            council = {
                'decision': 'TRADE',
                'tier': 'LEAN' if gap_score < 5 else 'FIRM',
                'confidence': min(int(gap_score * 10), 100),
                'position_size': 0.25,
                'reasons': reasons,
                'strategy': {
                    'regime': regime or 'BULL',
                    'strategy': 'GAP',
                    'sizing': 0.25,
                    'gap_type': gap_type,
                    'gap_score': gap_score,
                },
                'stock_signals': {},
                'stock_profile': {},
                'context': {
                    'gap_type': gap_type,
                    'gap_score': gap_score,
                    'reasons': reasons,
                    'sector_ret': gc.get('_sect_ret', 0),
                    'vix': gc.get('_vix', 20),
                    'breadth': gc.get('_breadth', 50),
                },
                'sensors': {},
                'exit_rules': {
                    'sl_pct': round(sl_pct, 1),
                    'tp_pct': round(tp_pct, 1),
                    'tp_schedule': {
                        'D0': round(tp_pct * 0.5, 1),
                        'D1': round(tp_pct * 0.7, 1),
                        'D2': round(tp_pct * 0.9, 1),
                        'D3': round(tp_pct, 1),
                    },
                    'max_hold_days': 5,
                },
            }

            pick = DiscoveryPick(
                symbol=gc['symbol'],
                scan_date=scan_date,
                scan_price=price,
                current_price=price,
                layer2_score=round(gap_score, 2),
                beta=gc.get('beta', 1.0) or 1.0,
                atr_pct=round(atr_pct, 2),
                distance_from_20d_high=gc.get('distance_from_20d_high', 0) or 0,
                momentum_5d=gc.get('momentum_5d', 0) or 0,
                momentum_20d=gc.get('momentum_20d', 0) or 0,
                volume_ratio=gc.get('volume_ratio', 1) or 1,
                sl_price=sl_price,
                sl_pct=round(sl_pct, 1),
                tp1_price=tp_price,
                tp1_pct=round(tp_pct, 1),
                expected_gain=round(tp_pct, 1),
                rr_ratio=round(tp_pct / sl_pct, 2) if sl_pct > 0 else 1.0,
                sector=gc.get('sector', ''),
                market_cap=gc.get('market_cap', 0) or 0,
                vix_close=macro.get('vix_close', 0) or 0,
                pct_above_20d_ma=macro.get('pct_above_20d_ma', 0) or 0,
                scan_type='evening',
                status='active',
            )
            pick.council = council
            return pick
        except Exception as e:
            logger.error("GapScanner: failed to create pick for %s: %s", gc.get('symbol'), e)
            return None

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
            macro.get('vix_close') or 20, macro.get('pct_above_20d_ma') or 50,
            adaptive=self._adaptive_params)

        strat_name, _ = self._strategy_selector.select(
            macro.get('vix_close') or 20, macro.get('pct_above_20d_ma') or 50)

        # v17: No sector hard-blocking — ML decides via sect_sharpe feature
        ranked = self._strategy_selector.get_ranked_picks(
            candidates, macro, market_regime=market_regime)
        all_strat_picks = self._strategy_selector.get_all_picks(candidates, macro)

        logger.info("Discovery v15.2: %d ranked picks from %d candidates",
                    len(ranked), len(candidates))
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

            # Gap: today's open vs yesterday's close (IC=+0.259)
            gap_pct = 0
            if len(close) >= 2 and d0_open > 0 and close[-2] > 0:
                gap_pct = (d0_open / float(close[-2]) - 1) * 100

            return {
                'symbol': symbol,
                'close': current, 'open': d0_open, 'gap_pct': gap_pct,
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
        with get_session() as session:
            rows = session.execute(text("""
                SELECT symbol, beta, pe_forward, market_cap, sector, avg_volume
                FROM stock_fundamentals
                WHERE market_cap > 1e9 AND avg_volume > 100000
            """)).mappings().fetchall()
            return {r['symbol']: dict(r) for r in rows}

    def _load_macro(self, scan_date: str) -> dict:
        """Load latest macro/breadth data + compute derived stress features."""
        with get_session() as session:
            macro_row = session.execute(text("""
                SELECT m.vix_close, m.vix3m_close, m.gold_close, m.crude_close, m.hyg_close,
                       m.dxy_close, m.yield_spread, m.yield_10y, m.spy_close,
                       b.pct_above_20d_ma, b.new_52w_highs, b.new_52w_lows, b.ad_ratio
                FROM macro_snapshots m
                LEFT JOIN market_breadth b ON m.date = b.date
                ORDER BY m.date DESC LIMIT 1
            """)).mappings().fetchone()

            if not macro_row:
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
            macro_5d = session.execute(text("""
                SELECT vix_close, dxy_close, crude_close FROM macro_snapshots
                ORDER BY date DESC LIMIT 1 OFFSET 5
            """)).mappings().fetchone()

            breadth_5d = session.execute(text("""
                SELECT pct_above_20d_ma FROM market_breadth
                ORDER BY date DESC LIMIT 1 OFFSET 5
            """)).mappings().fetchone()

            # v14.0: BTC 3-day ago for leading signal
            btc_3d_row = session.execute(text("""
                SELECT btc_close FROM macro_snapshots
                WHERE btc_close IS NOT NULL ORDER BY date DESC LIMIT 1 OFFSET 3
            """)).fetchone()

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
        sym_params = {f's{i}': s for i, s in enumerate(symbols)}
        sym_placeholders = ','.join(f':s{i}' for i in range(len(symbols)))

        with get_session() as session:
            analyst = {r['symbol']: dict(r) for r in session.execute(text(f"SELECT symbol, bull_score, upside_pct FROM analyst_consensus WHERE symbol IN ({sym_placeholders})"), sym_params).mappings().fetchall()}
            news = {r['symbol']: dict(r) for r in session.execute(text(f"SELECT symbol, AVG(sentiment_score) as avg_news_sentiment, COUNT(*) as news_count, SUM(CASE WHEN sentiment_label='positive' THEN 1 ELSE 0 END) as news_pos, SUM(CASE WHEN sentiment_label='negative' THEN 1 ELSE 0 END) as news_neg FROM news_events WHERE symbol IN ({sym_placeholders}) AND symbol IS NOT NULL GROUP BY symbol"), sym_params).mappings().fetchall()}
            options = {r['symbol']: dict(r) for r in session.execute(text(f"SELECT symbol, put_call_ratio FROM options_flow WHERE symbol IN ({sym_placeholders}) GROUP BY symbol HAVING MAX(date)"), sym_params).mappings().fetchall()}

            today_str = date.today().isoformat()
            earnings = {}
            earn_params = {**sym_params, 'today': today_str}
            for r in session.execute(text(f"SELECT symbol, MIN(report_date) as next_date FROM earnings_history WHERE symbol IN ({sym_placeholders}) AND report_date >= :today GROUP BY symbol"), earn_params).mappings().fetchall():
                try:
                    ed = datetime.strptime(r['next_date'][:10], '%Y-%m-%d').date()
                    earnings[r['symbol']] = (ed - date.today()).days
                except Exception:
                    pass

            short_data = {r['symbol']: r['short_pct_float'] for r in session.execute(text(f"SELECT symbol, short_pct_float FROM short_interest WHERE symbol IN ({sym_placeholders})"), sym_params).mappings().fetchall()}

            sector_rows = session.execute(text("SELECT etf, sector, pct_change FROM sector_etf_daily_returns WHERE date = (SELECT MAX(date) FROM sector_etf_daily_returns)")).mappings().fetchall()
            sector_returns_by_name = {r['sector']: r['pct_change'] for r in sector_rows if r['sector']}
            spy_return = next((r['pct_change'] for r in sector_rows if r['etf'] == 'SPY'), 0)

            # v16 smart boost: insider purchases + analyst target changes (90 days)
            # Queried here once instead of separately in filter._apply_smart_boost()
            insider_syms = set()
            analyst_up_syms = set()
            analyst_down_syms = set()
            ref_date = scan_date or today_str
            try:
                for r in session.execute(text("""
                    SELECT DISTINCT symbol FROM insider_transactions_history
                    WHERE trade_date >= date(:p0, '-90 days') AND trade_date <= :p1
                    AND (transaction_type LIKE '%Purchase%'
                         OR transaction_type LIKE '%Buy%')
                    AND value > 10000
                """), {'p0': ref_date, 'p1': ref_date}).mappings():
                    insider_syms.add(r['symbol'])
            except Exception:
                pass  # table may not exist yet
            try:
                for r in session.execute(text("""
                    SELECT symbol,
                           AVG((price_target / prior_price_target - 1) * 100) as chg
                    FROM analyst_ratings_history
                    WHERE date >= date(:p0, '-90 days') AND date <= :p1
                    AND price_target > 0 AND prior_price_target > 0
                    GROUP BY symbol
                """), {'p0': ref_date, 'p1': ref_date}).mappings():
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
                for r in session.execute(text("""
                    SELECT symbol, pc_volume_ratio FROM options_daily_summary
                    WHERE collected_date >= date(:p0, '-3 days')
                    AND pc_volume_ratio > 0
                """), {'p0': ref_date}).mappings():
                    pc = r['pc_volume_ratio']
                    if pc < PC_BULLISH:
                        options_bullish_syms.add(r['symbol'])
                    elif pc > PC_BEARISH:
                        options_bearish_syms.add(r['symbol'])
            except Exception:
                pass  # table may not exist yet

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
        with get_session() as session:
            session.execute(text("""
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
            """))
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
                ('peak_price', 'REAL'),
            ]
            for col_name, col_type in new_cols:
                try:
                    session.execute(text(f"ALTER TABLE discovery_picks ADD COLUMN {col_name} {col_type}"))
                except Exception:
                    pass

    def _load_picks_from_db(self):
        with get_session() as session:
            rows = session.execute(text("""
                SELECT * FROM discovery_picks WHERE status = 'active'
                ORDER BY layer2_score DESC
            """)).mappings().fetchall()

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
                peak_price=r['peak_price'] if 'peak_price' in r.keys() else None,
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
        with get_session() as session:
            for p in picks:
                session.execute(text("""
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
                    VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,:p13,:p14,:p15,:p16,:p17,:p18,:p19,:p20,:p21,:p22,:p23,:p24,:p25,:p26,:p27,:p28,:p29,:p30,:p31,:p32,:p33,:p34,:p35,:p36,:p37,:p38,:p39,:p40,:p41,:p42,:p43,:p44,:p45,:p46,:p47,:p48,:p49,:p50,:p51,:p52,:p53,:p54,:p55,:p56,:p57)
                """), {'p0': p.scan_date, 'p1': p.symbol, 'p2': p.scan_price, 'p3': p.current_price, 'p4': p.layer2_score,
                      'p5': p.beta, 'p6': p.atr_pct, 'p7': p.distance_from_high, 'p8': p.distance_from_20d_high, 'p9': p.rsi, 'p10': p.momentum_5d,
                      'p11': p.momentum_20d, 'p12': p.volume_ratio,
                      'p13': p.sl_price, 'p14': p.sl_pct, 'p15': p.tp1_price, 'p16': p.tp1_pct, 'p17': p.tp2_price, 'p18': p.tp2_pct,
                      'p19': p.expected_gain, 'p20': p.rr_ratio,
                      'p21': p.sector, 'p22': p.market_cap, 'p23': p.vix_close, 'p24': p.pct_above_20d_ma, 'p25': p.status,
                      'p26': p.vix_term_structure, 'p27': p.new_52w_highs, 'p28': p.bull_score, 'p29': p.news_count,
                      'p30': p.news_pos_ratio, 'p31': p.highs_lows_ratio, 'p32': p.ad_ratio, 'p33': p.mcap_log,
                      'p34': p.sector_1d_change, 'p35': p.vix3m_close, 'p36': p.upside_pct,
                      'p37': p.days_to_earnings, 'p38': p.put_call_ratio, 'p39': p.short_pct_float,
                      'p40': p.breadth_delta_5d, 'p41': p.vix_delta_5d, 'p42': p.crude_close, 'p43': p.gold_close,
                      'p44': p.dxy_delta_5d, 'p45': p.stress_score,
                      'p46': p.premarket_price, 'p47': p.gap_pct, 'p48': p.scan_type,
                      'p49': p.limit_entry_price, 'p50': p.limit_pct, 'p51': p.entry_price, 'p52': p.entry_status, 'p53': p.entry_filled_at,
                      'p54': json.dumps(getattr(p, 'tp_timeline', None)),
                      'p55': json.dumps(getattr(p, 'weekend_play', None)),
                      'p56': json.dumps(getattr(p, 'ensemble', None)),
                      'p57': json.dumps(getattr(p, 'council', None))})
        logger.info(f"Discovery: saved {len(picks)} picks for {scan_date}")

    def _save_multi_strategy(self, scan_date, info):
        """Persist multi-strategy info to DB so webapp can read it after scan exits."""
        with get_session() as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS discovery_multi_strategy (
                    scan_date TEXT PRIMARY KEY,
                    info_json TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """))
            session.execute(
                text("INSERT OR REPLACE INTO discovery_multi_strategy (scan_date, info_json) VALUES (:p0, :p1)"),
                {'p0': scan_date, 'p1': json.dumps(info, default=str)})
        logger.info("Discovery: saved multi-strategy info for %s", scan_date)

    def _load_multi_strategy(self):
        """Load most recent multi-strategy info from DB."""
        try:
            with get_session() as session:
                row = session.execute(text(
                    "SELECT scan_date, info_json, updated_at "
                    "FROM discovery_multi_strategy ORDER BY scan_date DESC LIMIT 1"
                )).fetchone()
            if row and row[1]:
                info = json.loads(row[1])
                info['_scan_date'] = row[0]
                info['_updated_at'] = row[2]
                return info
        except Exception:
            pass
        return {}

    def _deactivate_previous_picks(self, new_scan_date):
        with get_session() as session:
            n = session.execute(text("UPDATE discovery_picks SET status = 'replaced', updated_at = datetime('now') WHERE status = 'active'")).rowcount
        if n:
            logger.info(f"Discovery: deactivated {n} previous picks")

    def _expire_old_picks(self, current_date):
        max_age = self._config.get('schedule', {}).get('max_pick_age_days', 5)
        lb_cfg = self._config.get('limit_buy', {})
        max_hold = lb_cfg.get('max_hold_days', 2)
        with get_session() as session:
            session.execute(text("UPDATE discovery_picks SET status = 'expired', updated_at = datetime('now') WHERE status = 'active' AND julianday(:p0) - julianday(scan_date) > :p1"), {'p0': current_date, 'p1': max_age})
            if lb_cfg.get('enabled', False):
                session.execute(text("UPDATE discovery_picks SET entry_status = 'missed', updated_at = datetime('now') WHERE status = 'active' AND entry_status = 'pending' AND julianday(:p0) - julianday(scan_date) > :p1"), {'p0': current_date, 'p1': max_hold})

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
            with get_session() as session:
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
                            session.execute(
                                text("UPDATE discovery_picks SET current_price=:p0, status=:p1, "
                                     "entry_status=:p2, entry_price=:p3, entry_filled_at=:p4, "
                                     "updated_at=datetime('now') WHERE symbol=:p5 AND scan_date=:p6"),
                                {'p0': pick.current_price, 'p1': pick.status,
                                 'p2': pick.entry_status, 'p3': pick.entry_price, 'p4': pick.entry_filled_at,
                                 'p5': pick.symbol, 'p6': pick.scan_date})
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Discovery price refresh error: {e}")

        # v20: Trailing TP — update peak prices and check trailing stops
        try:
            active_picks = [p for p in self._picks if p.status == 'active']
            current_prices = {p.symbol: p.current_price for p in active_picks
                              if p.current_price and p.current_price > 0}
            if active_picks and current_prices:
                alerts = self._trailing_tp.update(active_picks, current_prices)
                if alerts:
                    logger.info("Discovery trailing TP: %d alerts — %s",
                                len(alerts),
                                ', '.join(f"{a.symbol} ({a.action})" for a in alerts))
        except Exception as e:
            logger.error("Discovery trailing TP error: %s", e)

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

        with get_session() as session:
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

                    session.execute(
                        text("UPDATE discovery_picks SET premarket_price=:p0, gap_pct=:p1, "
                             "limit_entry_price=:p2, sl_price=:p3, sl_pct=:p4, tp1_price=:p5, tp1_pct=:p6, "
                             "tp2_price=:p7, tp2_pct=:p8, updated_at=datetime('now') "
                             "WHERE symbol=:p9 AND scan_date=:p10 AND status='active'"),
                        {'p0': pm_price, 'p1': pick.gap_pct, 'p2': getattr(pick, 'limit_entry_price', None),
                         'p3': pick.sl_price, 'p4': pick.sl_pct, 'p5': pick.tp1_price, 'p6': pick.tp1_pct,
                         'p7': pick.tp2_price, 'p8': pick.tp2_pct, 'p9': pick.symbol, 'p10': pick.scan_date})
                except Exception:
                    continue
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

        # v17: Use same pipeline as main scan (ML ranking + adaptive filters)
        # Only difference: refit=False (reuse evening kernels)
        scan_info['market_regime'] = self._detect_market_regime(macro)
        scan_info['condition'] = detect_condition(
            macro.get('vix_close') or 20, macro.get('pct_above_20d_ma') or 50,
            adaptive=self._adaptive_params)
        scan_info['sector_scores'] = self._sector_scorer.score(macro, scan_date) if self._sector_scorer._fitted else {}

        picks, scored_all, regime_s, macro_er_s = \
            self._run_v3_pipeline(candidates, macro, scan_date, scan_info, refit=False)

        # Merge with existing
        with get_session() as session:
            existing_symbols = {r['symbol'] for r in session.execute(text("SELECT symbol FROM discovery_picks WHERE status='active'")).mappings().fetchall()}

            re_ranked = 0
            for p in picks:
                if p.symbol in existing_symbols:
                    session.execute(text("UPDATE discovery_picks SET layer2_score=:p0, current_price=:p1, updated_at=datetime('now') WHERE symbol=:p2 AND status='active'"),
                                 {'p0': p.layer2_score, 'p1': p.current_price, 'p2': p.symbol})
                re_ranked += 1

        new_intraday = [p for p in picks if p.symbol not in existing_symbols][:max_new]
        for p in new_intraday:
            p.scan_type = 'intraday'
        if new_intraday:
            self._save_picks(new_intraday, scan_date)

        self._load_picks_from_db()
        self._last_intraday_scan = datetime.now().strftime('%Y-%m-%d %H:%M')
        logger.info("Discovery intraday: re-ranked %d, added %d new", re_ranked, len(new_intraday))
        return new_intraday

    # _run_v3_pipeline_intraday REMOVED — intraday now uses _run_v3_pipeline(refit=False)

    def _enrich_candidates_lite(self, candidates, scan_date: str = None):
        if not candidates:
            return
        symbols = [c['symbol'] for c in candidates]
        sym_params = {f's{i}': s for i, s in enumerate(symbols)}
        sym_placeholders = ','.join(f':s{i}' for i in range(len(symbols)))
        today_str = date.today().isoformat()
        ref_date = scan_date or today_str

        with get_session() as session:
            earnings = {}
            earn_params = {**sym_params, 'today': today_str}
            for r in session.execute(text(f"SELECT symbol, MIN(report_date) as next_date FROM earnings_history WHERE symbol IN ({sym_placeholders}) AND report_date >= :today GROUP BY symbol"), earn_params).mappings().fetchall():
                try:
                    ed = datetime.strptime(r['next_date'][:10], '%Y-%m-%d').date()
                    earnings[r['symbol']] = (ed - date.today()).days
                except Exception:
                    pass
            sector_rows = session.execute(text("SELECT etf, sector, pct_change FROM sector_etf_daily_returns WHERE date = (SELECT MAX(date) FROM sector_etf_daily_returns)")).mappings().fetchall()
            sector_returns_by_name = {r['sector']: r['pct_change'] for r in sector_rows if r['sector']}
            spy_return = next((r['pct_change'] for r in sector_rows if r['etf'] == 'SPY'), 0)

            # Smart boost: insider purchases + analyst target changes (same as _enrich_candidates)
            insider_syms = set()
            analyst_up_syms = set()
            analyst_down_syms = set()
            try:
                for r in session.execute(text("""
                    SELECT DISTINCT symbol FROM insider_transactions_history
                    WHERE trade_date >= date(:p0, '-90 days') AND trade_date <= :p1
                    AND (transaction_type LIKE '%Purchase%'
                         OR transaction_type LIKE '%Buy%')
                    AND value > 10000
                """), {'p0': ref_date, 'p1': ref_date}).mappings():
                    insider_syms.add(r['symbol'])
            except Exception:
                pass
            try:
                for r in session.execute(text("""
                    SELECT symbol,
                           AVG((price_target / prior_price_target - 1) * 100) as chg
                    FROM analyst_ratings_history
                    WHERE date >= date(:p0, '-90 days') AND date <= :p1
                    AND price_target > 0 AND prior_price_target > 0
                    GROUP BY symbol
                """), {'p0': ref_date, 'p1': ref_date}).mappings():
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
                for r in session.execute(text("""
                    SELECT symbol, pc_volume_ratio FROM options_daily_summary
                    WHERE collected_date >= date(:p0, '-3 days')
                    AND pc_volume_ratio > 0
                """), {'p0': ref_date}).mappings():
                    pc = r['pc_volume_ratio']
                    if pc < PC_BULLISH:
                        options_bullish_syms.add(r['symbol'])
                    elif pc > PC_BEARISH:
                        options_bearish_syms.add(r['symbol'])
            except Exception:
                pass
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
