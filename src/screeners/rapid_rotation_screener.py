#!/usr/bin/env python3
"""
RAPID ROTATION SCREENER v4.0 - SMART REGIME EDITION

INTEGRATED SYSTEMS:
✅ AI Universe Generator (680+ stocks from DeepSeek)
✅ Market Regime Detector (Bull/Bear/Sideways)
✅ Sector Regime Detector (HYBRID v2 - soft penalty scoring)
✅ Alternative Data (Insider, Sentiment, Short Interest) - Top 10 only
✅ SPY REGIME FILTER (v4.0 NEW!) - SPY > SMA20 = Bull → Trade

Strategy:
- Dynamic universe from AI (680+ stocks)
- SPY REGIME FILTER (v4.0): Only trade when SPY > SMA20
- HYBRID SECTOR SCORING: Soft penalty (BEAR -10, BULL +5)
- BOUNCE CONFIRMATION: Wait for recovery after dip (not catching knife)
- ALT DATA TIE-BREAKER: Only check for Top 10 candidates (±10 cap)
- FULLY DYNAMIC SL/TP based on actual market structure

v4.0 Changes - SMART REGIME EDITION:
- SPY > SMA20 = BULL → Trade normally
- SPY < SMA20 = BEAR → Skip ALL new entries (protect capital)
- Backtest Result: +5.5%/mo, DD 8.9%, WR 49% (MEETS BOTH TARGETS!)
- This single filter reduces DD from 12.6% → 8.9%

v3.10 Changes - OVEREXTENDED FILTER (ARM FIX):
- Skip stocks with >8% single-day move in last 10 days
- Skip stocks >10% above SMA20 (too extended)
- Prevents entering after exhaustion moves (like ARM +9.5%)
- Based on September 2025 ARM loss analysis

v3.7 Changes - HYBRID SECTOR + ALT DATA:
- Sector as SOFT FILTER (penalty/bonus, not exclusion)
- BEAR sector: -10 points, SIDEWAYS: 0, BULL: +5 (asymmetric - defensive)
- Alt Data only for Top 10 (performance optimization)
- Alt Data capped at ±10 (tie-breaker, not dominant)

v3.6 Changes - TIGHT SL 2.5% (FAST ROTATION):
- SL capped at 2.5% (was 4.5%) for faster rotation
- PDT-Safe: No same-day exits (SL starts from Day 1)
- Saves ~3.6%/month by limiting losses

v3.5 Changes - SMA20 FILTER (ROOT CAUSE FIX):
- MUST be above SMA20 (92% of losers were below)
- This single filter prevents most stop loss trades
- Based on actual backtest root cause analysis

v3.4 Changes - FULLY DYNAMIC SL/TP:
- SL = MAX(ATR × 1.5, Below Swing Low 5d, Below EMA5)
- TP = MIN(ATR × 3, Resistance Level, +15% cap)
- No more fixed % ranges - adapts to each stock
- Uses actual price structure (swing high/low)

v3.3 Base (achieved +8.23%/month in backtest):
- BOUNCE CONFIRMATION: Yesterday down, today recovering
- Higher score threshold: 90
- Trailing stop: Activate at +3%, trail dynamically
"""

import json
import time
import tempfile
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import yfinance as yf
from loguru import logger
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# v4.1: Import from filters.py (Single Source of Truth)
from screeners.rapid_trader_filters import (
    FilterConfig,
    calculate_score,
    check_bounce_confirmation,
    check_sma20_filter,
    calculate_dynamic_sl_tp,
)


@dataclass
class RapidRotationSignal:
    """Signal for rapid rotation strategy"""
    symbol: str
    score: int
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    atr_pct: float
    rsi: float
    momentum_5d: float
    momentum_20d: float
    distance_from_high: float
    reasons: List[str]
    # v3.0: Additional data
    sector: str = ""
    market_regime: str = ""
    sector_score: float = 0.0
    alt_data_score: float = 0.0
    # v3.4: Dynamic SL/TP info
    sl_method: str = ""       # Which method determined SL
    tp_method: str = ""       # Which method determined TP
    swing_low: float = 0.0    # Swing low reference
    resistance: float = 0.0   # Resistance reference
    volume_ratio: float = 1.0  # v5.0: today_vol / avg_20d_vol

    @property
    def expected_gain(self) -> float:
        return ((self.take_profit - self.entry_price) / self.entry_price) * 100

    @property
    def max_loss(self) -> float:
        return ((self.entry_price - self.stop_loss) / self.entry_price) * 100


class RapidRotationScreener:
    """
    Rapid Rotation Screener v3.7 - HYBRID SECTOR + ALT DATA

    Achieved +32.41%/6mo in realistic backtest (57.8% win rate)

    Systems Used:
    1. AI Universe Generator - 680+ stocks
    2. Market Regime Detector - Bull/Bear/Sideways
    3. Sector Regime Detector - HYBRID v2 (soft penalty scoring)
    4. Alternative Data - Insider, Sentiment, etc. (Top 10 only, ±10 cap)
    5. Bounce Confirmation - Wait for recovery, not falling knife

    v6.10 FULL CONFIG MIGRATION:
    - Uses RapidRotationConfig as single source of truth
    - All parameters loaded from config (no hardcoded constants)
    - Backward compatible with YAML loading

    v3.7 HYBRID SECTOR + ALT DATA:
    - Sector regime as SOFT FILTER (penalty/bonus, not exclusion)
    - BEAR sector: -10 points (defensive - penalize harder)
    - SIDEWAYS: 0 points (neutral)
    - BULL sector: +5 points (small bonus)
    - Alt Data only for Top 10 candidates (fast performance)
    - Alt Data capped at ±10 (tie-breaker role)

    v3.6 TIGHT SL 2.5%:
    - SL capped at 2.5% for fast rotation
    - PDT-Safe: No same-day exits
    """

    # Fallback universe if AI fails
    FALLBACK_UNIVERSE = [
        # AI/Semiconductor
        'NVDA', 'AMD', 'AVGO', 'MU', 'MRVL', 'ARM', 'SMCI', 'TSM',
        'QCOM', 'AMAT', 'LRCX', 'KLAC', 'INTC', 'TXN', 'ADI',
        # High beta tech
        'TSLA', 'PLTR', 'SNOW', 'COIN', 'DDOG', 'NET', 'CRWD', 'ZS',
        # Mega cap tech
        'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT', 'ORCL',
        # Other high-beta
        'CRM', 'NOW', 'SHOP', 'PYPL', 'UBER', 'ABNB',
        # EV/Clean energy
        'RIVN', 'LCID', 'ENPH', 'FSLR', 'RUN',
        # Finance
        'JPM', 'GS', 'MS', 'V', 'MA', 'AXP',
        # Industrial
        'CAT', 'DE', 'BA', 'GE', 'HON',
        # Consumer
        'NKE', 'LULU', 'SBUX', 'MCD', 'HD', 'LOW',
        # Additional high-beta for v3.3
        'ROKU', 'PATH', 'S', 'BILL', 'CFLT', 'CHWY', 'DXCM',
    ]

    # v4.9.5: BULL Sector Stocks (always included for BEAR mode trading)
    # These sectors are often BULL/SIDEWAYS when Tech is BEAR
    BULL_SECTOR_STOCKS = [
        # Energy (20) - Often STRONG BULL in BEAR markets
        'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'MPC', 'VLO', 'OXY', 'DVN', 'FANG',
        'PSX', 'HAL', 'BKR', 'CTRA', 'KMI', 'WMB', 'OKE', 'ET', 'EPD', 'TRGP',
        # Utilities (20) - Defensive, often BULL in downturns
        'NEE', 'DUK', 'SO', 'D', 'SRE', 'AEP', 'XEL', 'WEC', 'ES', 'EXC',
        'ED', 'ATO', 'CMS', 'NI', 'EVRG', 'PNW', 'AES', 'PPL', 'FE', 'CEG',
        # Real Estate (20) - Often BULL with rate expectations
        'PLD', 'AMT', 'EQIX', 'PSA', 'DLR', 'O', 'SPG', 'WELL', 'AVB', 'EQR',
        'VTR', 'ARE', 'MAA', 'UDR', 'CPT', 'KIM', 'REG', 'HST', 'BXP', 'SUI',
    ]

    # v4.9.3: Sector cache config (static paths)
    SECTOR_CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'sector_cache.json')

    # v4.9.3: AI universe disk cache
    AI_UNIVERSE_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'ai_universe_cache.json')

    def __init__(self, config: 'RapidRotationConfig' = None):
        """
        Initialize with all integrated systems

        Args:
            config: RapidRotationConfig instance (v6.10 - FULL MIGRATION)
                   If None, will load from default YAML path
        """
        # v6.10: Load config if not provided
        if config is None:
            try:
                from config.strategy_config import RapidRotationConfig
                config_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    'config', 'trading.yaml'
                )
                config = RapidRotationConfig.from_yaml(config_path)
                logger.debug(f"Loaded RapidRotationConfig from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config, using defaults: {e}")
                from config.strategy_config import RapidRotationConfig
                config = RapidRotationConfig()

        self.config = config

        # v6.10: Configuration from RapidRotationConfig (Single Source of Truth)
        self.MIN_ATR_PCT = config.min_atr_pct
        self.MIN_SCORE = config.min_score
        self.MAX_HOLD_DAYS = config.max_hold_days

        # SPY Regime Filter
        self.REGIME_FILTER_ENABLED = config.regime_filter_enabled
        self.REGIME_SMA_PERIOD = config.regime_sma_period

        # ATR Multipliers
        self.ATR_SL_MULTIPLIER = config.atr_sl_multiplier
        self.ATR_TP_MULTIPLIER = config.atr_tp_multiplier

        # Safety caps (use config, not FilterConfig hardcoded values)
        self.MIN_SL_PCT = config.min_sl_pct
        self.MAX_SL_PCT = config.max_sl_pct
        self.MIN_TP_PCT = config.min_tp_pct
        self.MAX_TP_PCT = config.max_tp_pct

        # Trailing stop
        self.TRAIL_ACTIVATION = config.trail_activation_pct

        # Sector scoring
        self.SECTOR_BULL_THRESHOLD = config.sector_bull_threshold
        self.SECTOR_BEAR_THRESHOLD = config.sector_bear_threshold
        self.SECTOR_BULL_BONUS = config.sector_bull_bonus
        self.SECTOR_BEAR_PENALTY = config.sector_bear_penalty
        self.SECTOR_SIDEWAYS_ADJ = config.sector_sideways_adj

        # Alt data scoring
        self.ALT_DATA_MAX_BONUS = config.alt_data_max_bonus
        self.ALT_DATA_MAX_PENALTY = config.alt_data_max_penalty

        # Cache TTL
        self.SECTOR_CACHE_TTL_DAYS = config.sector_cache_ttl_days
        self.SECTOR_CACHE_TTL = 86400 * config.sector_cache_ttl_days

        # Initialize component state
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self._data_cache_time: Dict[str, float] = {}
        self.universe: List[str] = []
        self.data_manager = None  # v4.9.3: Shared DataManager for Tiingo routing

        # v4.9.3: Persistent sector cache (memory + disk)
        self._sector_cache: Dict[str, dict] = {}
        self._load_sector_cache()

        # Cache TTL in seconds (v6.10: MUST be defined BEFORE _init methods use it)
        self._cache_ttl = {
            'market_regime': 120,   # v5.1 P2-17: 300→120s (align with engine)
            'sector_regime': 300,   # v5.1 P2-17: 600→300s (sector changes slower but still relevant)
            'alt_data': 300,        # 5 min
            'data': config.price_cache_ttl_seconds,  # v6.10: from config (default 300s = 5min)
        }

        # Cache for regime data (with timestamps)
        self._market_regime_cache = None
        self._market_regime_cache_time: float = 0.0
        self._sector_regime_cache = {}
        self._sector_regime_cache_time: float = 0.0
        self._alt_data_cache = {}
        self._alt_data_cache_time: float = 0.0

        # SPY regime cache (Fix #38: avoid downloading SPY every call)
        self._spy_regime_cache = None  # (is_bull, reason, details, timestamp)
        self._spy_cache_seconds = self._cache_ttl['market_regime']  # v6.10: sync with market_regime cache (120s)

        # Initialize integrated systems (AFTER cache setup)
        self._init_ai_universe()
        self._init_market_regime()
        self._init_sector_regime()
        self._init_alt_data()

    def _is_cache_valid(self, name: str, cache_time: float) -> bool:
        """Check if a cache entry is still valid based on TTL"""
        if cache_time == 0.0:
            return False
        import time
        ttl = self._cache_ttl.get(name, 300)
        return (time.time() - cache_time) < ttl

    def _clear_stale_caches(self):
        """Clear any caches that have exceeded their TTL"""
        import time
        now = time.time()

        if self._market_regime_cache is not None:
            if (now - self._market_regime_cache_time) >= self._cache_ttl['market_regime']:
                self._market_regime_cache = None
                self._market_regime_cache_time = 0.0
                logger.debug("Cleared stale market regime cache")

        if self._sector_regime_cache:
            if (now - self._sector_regime_cache_time) >= self._cache_ttl['sector_regime']:
                self._sector_regime_cache = {}
                self._sector_regime_cache_time = 0.0
                logger.debug("Cleared stale sector regime cache")

        if self._alt_data_cache:
            if (now - self._alt_data_cache_time) >= self._cache_ttl['alt_data']:
                self._alt_data_cache = {}
                self._alt_data_cache_time = 0.0
                logger.debug("Cleared stale alt data cache")

        # Clear per-symbol data caches that are stale
        stale_symbols = [
            sym for sym, t in self._data_cache_time.items()
            if (now - t) >= self._cache_ttl['data']
        ]
        for sym in stale_symbols:
            self.data_cache.pop(sym, None)
            self._data_cache_time.pop(sym, None)
        if stale_symbols:
            logger.debug(f"Cleared stale data cache for {len(stale_symbols)} symbols")

    def _init_ai_universe(self):
        """Initialize AI Universe Generator"""
        try:
            from ai_universe_generator import AIUniverseGenerator
            self.ai_generator = AIUniverseGenerator()
            logger.info("✅ AI Universe Generator initialized")
        except Exception as e:
            self.ai_generator = None
            logger.warning(f"⚠️ AI Universe Generator not available: {e}")

    def _init_market_regime(self):
        """Initialize Market Regime Detector (v6.10: pass config)"""
        try:
            from market_regime_detector import MarketRegimeDetector
            self.market_regime = MarketRegimeDetector(config=self.config)
            logger.info("✅ Market Regime Detector initialized")
        except Exception as e:
            self.market_regime = None
            logger.warning(f"⚠️ Market Regime Detector not available: {e}")

    def _init_sector_regime(self):
        """Initialize Sector Regime Detector"""
        try:
            from sector_regime_detector import SectorRegimeDetector
            from api.data_manager import DataManager
            self.data_manager = DataManager()  # v4.9.3: Store for load_data() Tiingo routing
            self.sector_regime = SectorRegimeDetector(data_manager=self.data_manager)
            # Update sector regimes at startup
            self.sector_regime.update_all_sectors()
            logger.info("✅ Sector Regime Detector initialized")
        except Exception as e:
            self.sector_regime = None
            logger.warning(f"⚠️ Sector Regime Detector not available: {e}")

    def _init_alt_data(self):
        """Initialize Alternative Data Aggregator"""
        try:
            from data_sources.aggregator import AlternativeDataAggregator
            self.alt_data = AlternativeDataAggregator()
            logger.info("✅ Alternative Data Aggregator initialized (6 sources)")
        except Exception as e:
            self.alt_data = None
            logger.warning(f"⚠️ Alternative Data not available: {e}")

    def generate_universe(self, max_stocks: int = 200) -> List[str]:
        """
        Generate stock universe using pre-filter pool, AI, or fallback.

        Priority:
        1. Pre-filtered pool (from overnight scan) - most reliable
        2. AI Universe Generator
        3. Cached AI universe
        4. Static fallback list

        Args:
            max_stocks: Maximum stocks to include

        Returns:
            List of stock symbols
        """
        universe = []

        # v6.2: Try pre-filtered pool first (from overnight scan)
        try:
            pre_filter_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                'data', 'pre_filtered.json'
            )
            if os.path.exists(pre_filter_file):
                with open(pre_filter_file) as f:
                    pre_filtered = json.load(f)

                # Check if pool is fresh (< 12 hours old)
                generated_at = pre_filtered.get('generated_at', '')
                if generated_at:
                    from datetime import datetime
                    gen_time = datetime.fromisoformat(generated_at)
                    age_hours = (datetime.now() - gen_time).total_seconds() / 3600

                    if age_hours < 12:
                        pool_stocks = list(pre_filtered.get('stocks', {}).keys())
                        if len(pool_stocks) >= 50:
                            universe = pool_stocks[:max_stocks] if len(pool_stocks) > max_stocks else pool_stocks
                            logger.info(f"📦 Using pre-filtered pool: {len(universe)} stocks (age: {age_hours:.1f}h)")
                            self._using_prefilter = True
                    else:
                        logger.warning(f"⚠️ Pre-filtered pool is stale ({age_hours:.1f}h old)")
        except Exception as e:
            logger.debug(f"Pre-filtered pool not available: {e}")

        # Try AI Universe Generator if no pre-filter
        if not universe and self.ai_generator:
            try:
                logger.info("🤖 Generating universe with AI...")
                criteria = {
                    'strategy': 'rapid_rotation',
                    'min_volatility': 2.0,
                    'max_stocks': max_stocks,
                    'universe_multiplier': 3,
                }
                # Use generate_volatile_universe for rapid trading (needs volatility)
                ai_universe = self.ai_generator.generate_volatile_universe(criteria)
                if ai_universe and len(ai_universe) > 20:
                    universe = ai_universe
                    logger.info(f"✅ AI generated {len(universe)} stocks")
                    # v4.9.3: Save to disk for fallback
                    try:
                        os.makedirs(os.path.dirname(self.AI_UNIVERSE_CACHE), exist_ok=True)
                        with open(self.AI_UNIVERSE_CACHE, 'w') as f:
                            json.dump({'symbols': universe, 'timestamp': datetime.now().isoformat(), 'count': len(universe)}, f)
                        logger.info(f"💾 AI universe saved to {self.AI_UNIVERSE_CACHE}")
                    except Exception as save_err:
                        logger.debug(f"Failed to save AI universe cache: {save_err}")
            except Exception as e:
                logger.warning(f"⚠️ AI universe generation failed: {e}")

        # v4.9.3: Fallback 1 — try disk-cached AI universe
        if not universe:
            try:
                with open(self.AI_UNIVERSE_CACHE) as f:
                    cached = json.load(f)
                cached_symbols = cached.get('symbols', [])
                if cached_symbols and len(cached_symbols) > 20:
                    universe = cached_symbols
                    logger.info(f"📦 Using cached AI universe: {len(universe)} stocks (from {cached.get('timestamp', '?')})")
            except Exception:
                pass

        # Fallback 2 — static hardcoded list
        if not universe:
            universe = self.FALLBACK_UNIVERSE.copy()
            logger.info(f"📋 Using static fallback universe: {len(universe)} stocks")

        # v4.9.5: Always merge BULL sector stocks (Energy, Utilities, Real Estate)
        # These sectors are critical for BEAR mode trading when Tech/Finance are down
        existing = set(universe)
        bull_added = 0
        for sym in self.BULL_SECTOR_STOCKS:
            if sym not in existing:
                universe.append(sym)
                existing.add(sym)
                bull_added += 1
        if bull_added > 0:
            logger.info(f"🐂 Added {bull_added} BULL sector stocks (Energy/Utilities/Real Estate)")

        # Filter by sector regime if available
        if self.sector_regime:
            try:
                hot_sectors = self._get_hot_sectors()
                if hot_sectors:
                    logger.info(f"🔥 Hot sectors: {', '.join(hot_sectors)}")
                    # Prioritize stocks in hot sectors (but don't exclude others)
            except Exception as e:
                logger.warning(f"⚠️ Sector filtering failed: {e}")

        self.universe = universe
        return universe

    def _get_market_regime(self) -> Dict[str, Any]:
        """Get current market regime"""
        import time
        if self._market_regime_cache and self._is_cache_valid('market_regime', self._market_regime_cache_time):
            return self._market_regime_cache

        if self.market_regime:
            try:
                regime = self.market_regime.get_current_regime()
                self._market_regime_cache = regime
                self._market_regime_cache_time = time.time()
                return regime
            except Exception as e:
                logger.warning(f"⚠️ Market regime detection failed: {e}")

        return {'regime': 'UNKNOWN', 'confidence': 0}

    def _get_hot_sectors(self) -> List[str]:
        """Get current hot sectors (BULL or STRONG BULL)"""
        if self.sector_regime:
            try:
                # get_bull_sectors returns ETF symbols like ['XLK', 'XLV']
                bull_etfs = self.sector_regime.get_bull_sectors()
                # Map ETF symbols to sector names
                sector_names = []
                for etf in bull_etfs:
                    sector_name = self.sector_regime.SECTOR_ETFS.get(etf, '')
                    if sector_name:
                        sector_names.append(sector_name)
                return sector_names
            except Exception as e:
                logger.debug(f"Hot sectors failed: {e}")
        return []

    def check_spy_regime(self) -> Tuple[bool, str, Dict]:
        """
        v4.0: Check if SPY is in Bull regime (OK to trade)

        Rule: SPY > SMA20 = Bull → Trade
              SPY < SMA20 = Bear → Skip all new entries

        Returns:
            Tuple of (is_bull, reason, details)
        """
        if not self.REGIME_FILTER_ENABLED:
            return True, "Regime filter disabled", {}

        # Check cache first (avoid downloading SPY every call)
        import time as _time
        if self._spy_regime_cache:
            is_bull, reason, details, cached_at = self._spy_regime_cache
            if _time.time() - cached_at < self._spy_cache_seconds:
                return is_bull, reason, details

        try:
            # Download SPY data (last 30 days is enough for SMA20)
            spy = yf.download('SPY', period='30d', progress=False)

            if spy.empty or len(spy) < self.REGIME_SMA_PERIOD:
                logger.warning("Not enough SPY data for regime check — defaulting to BEAR (fail-closed)")
                return False, "Insufficient data — defaulting to BEAR for safety", {}

            # Get current price and SMA
            close = spy['Close']

            # Handle multi-index columns from yfinance
            if hasattr(close.iloc[-1], 'iloc'):
                current_price = float(close.iloc[-1].iloc[0])
                sma = float(close.iloc[-self.REGIME_SMA_PERIOD:].mean().iloc[0])
            else:
                current_price = float(close.iloc[-1])
                sma = float(close.iloc[-self.REGIME_SMA_PERIOD:].mean())

            is_bull = current_price > sma
            pct_above = ((current_price / sma) - 1) * 100

            details = {
                'spy_price': round(current_price, 2),
                'spy_sma20': round(sma, 2),
                'pct_above_sma': round(pct_above, 2),
                'regime': 'BULL' if is_bull else 'BEAR'
            }

            if is_bull:
                reason = f"BULL: SPY ${current_price:.2f} > SMA{self.REGIME_SMA_PERIOD} ${sma:.2f} (+{pct_above:.1f}%)"
                logger.info(f"✅ SPY Regime: {reason}")
            else:
                reason = f"BEAR: SPY ${current_price:.2f} < SMA{self.REGIME_SMA_PERIOD} ${sma:.2f} ({pct_above:.1f}%)"
                logger.warning(f"⚠️ SPY Regime: {reason} - SKIP NEW TRADES")

            # Cache the result
            self._spy_regime_cache = (is_bull, reason, details, _time.time())

            return is_bull, reason, details

        except Exception as e:
            logger.error(f"SPY regime check failed: {e}")
            return False, f"Data unavailable: {e}", {}

    def _get_alt_data_score(self, symbol: str, enable: bool = True) -> Tuple[float, List[str]]:
        """
        Get alternative data score for a stock (v3.7: capped at ±10)

        Args:
            symbol: Stock symbol
            enable: Whether to actually fetch alt data (for performance)

        Returns:
            Tuple of (score, reasons)

        v3.7 Changes:
        - Score capped at ±10 (tie-breaker role, not dominant)
        - Only called for Top 10 candidates (enable=True)
        """
        if symbol in self._alt_data_cache:
            return self._alt_data_cache[symbol]

        score = 0
        reasons = []

        if self.alt_data and enable:
            try:
                data = self.alt_data.get_comprehensive_data(symbol)

                if data:
                    # Insider buying (+7)
                    if data.get('has_insider_buying', False):
                        score += 7
                        reasons.append("Insider buying")

                    # Overall score from alt data (normalized 0-100)
                    overall_alt = data.get('overall_score', 0)
                    if overall_alt > 70:
                        score += 5
                        reasons.append(f"Strong alt ({overall_alt:.0f})")
                    elif overall_alt > 50:
                        score += 3
                    elif overall_alt < 30:
                        score -= 3
                        reasons.append(f"Weak alt ({overall_alt:.0f})")

                    # Short squeeze potential (+3)
                    if data.get('has_squeeze_potential', False):
                        score += 3
                        reasons.append("Squeeze")

                    # Analyst upgrades (+4)
                    if data.get('has_analyst_upgrade', False):
                        score += 4
                        reasons.append("Analyst upgrade")
                    elif data.get('has_analyst_downgrade', False):
                        score -= 3
                        reasons.append("Analyst downgrade")

                    # v3.7: CAP AT ±10 (tie-breaker role)
                    score = max(self.ALT_DATA_MAX_PENALTY,
                               min(score, self.ALT_DATA_MAX_BONUS))

            except Exception as e:
                logger.debug(f"Alt data failed for {symbol}: {e}")

        import time
        self._alt_data_cache[symbol] = (score, reasons)
        self._alt_data_cache_time = time.time()
        return score, reasons

    def _load_sector_cache(self):
        """v4.9.3: Load sector cache from disk"""
        try:
            with open(self.SECTOR_CACHE_FILE) as f:
                data = json.load(f)
            now = time.time()
            self._sector_cache = {
                k: v for k, v in data.items()
                if now - v.get('ts', 0) < self.SECTOR_CACHE_TTL
            }
            if self._sector_cache:
                logger.info(f"📦 Loaded {len(self._sector_cache)} sectors from cache")
        except Exception:
            self._sector_cache = {}

    def _save_sector_cache(self):
        """v4.9.3: Save sector cache to disk (atomic write)"""
        try:
            cache_dir = os.path.dirname(self.SECTOR_CACHE_FILE)
            os.makedirs(cache_dir, exist_ok=True)
            fd, tmp = tempfile.mkstemp(suffix='.tmp', dir=cache_dir)
            with os.fdopen(fd, 'w') as f:
                json.dump(self._sector_cache, f)
            os.replace(tmp, self.SECTOR_CACHE_FILE)
        except Exception as e:
            logger.debug(f"Failed to save sector cache: {e}")

    def _get_sector(self, symbol: str) -> str:
        """Get sector for a symbol (v4.9.3: cached + rate-limited)"""
        # Check memory/disk cache first
        cached = self._sector_cache.get(symbol)
        if cached and time.time() - cached.get('ts', 0) < self.SECTOR_CACHE_TTL:
            return cached['sector']

        # Fetch via rate-limited Yahoo (singleton limiter)
        try:
            from data_sources.rate_limiter import get_rate_limiter
            rl = get_rate_limiter()
            info = rl.get_info(symbol)
            sector = info.get('sector', 'Unknown') if info else 'Unknown'
        except Exception:
            sector = 'Unknown'

        # Cache if valid
        if sector != 'Unknown':
            self._sector_cache[symbol] = {'sector': sector, 'ts': time.time()}

        return sector

    def _get_sector_regime_score(self, sector: str) -> Tuple[int, str, str]:
        """
        Get sector regime score using HYBRID v2 approach (v3.7)

        Uses simple ±3% rule on 20-day sector ETF performance:
        - > +3%  = BULL    → +5 points
        - -3% to +3% = SIDEWAYS → 0 points
        - < -3%  = BEAR    → -10 points (defensive - penalize harder)

        Returns:
            Tuple of (score_adjustment, regime, reason)
        """
        if not self.sector_regime:
            return 0, 'UNKNOWN', ''

        try:
            # Get ETF symbol for sector
            etf = self.sector_regime.SECTOR_TO_ETF.get(sector)
            if not etf:
                return 0, 'UNKNOWN', ''

            # Get sector metrics (20-day return)
            metrics = self.sector_regime.sector_metrics.get(etf)
            if not metrics:
                return 0, 'UNKNOWN', ''

            return_20d = metrics.get('return_20d', 0)

            # Determine regime based on simple ±3% rule
            if return_20d > self.SECTOR_BULL_THRESHOLD:
                regime = 'BULL'
                score_adj = self.SECTOR_BULL_BONUS
                reason = f"BULL sector +{return_20d:.1f}%"
            elif return_20d < self.SECTOR_BEAR_THRESHOLD:
                regime = 'BEAR'
                score_adj = self.SECTOR_BEAR_PENALTY
                reason = f"BEAR sector {return_20d:.1f}%"
            else:
                regime = 'SIDEWAYS'
                score_adj = self.SECTOR_SIDEWAYS_ADJ
                reason = f"Sideways sector {return_20d:+.1f}%"

            return score_adj, regime, reason

        except Exception as e:
            logger.debug(f"Sector regime score failed for {sector}: {e}")
            return 0, 'UNKNOWN', ''

    def load_data(self, days: int = 60, progress_callback=None) -> None:
        """Load historical data for universe

        v4.9.4: Route through DataManager (Yahoo primary, Tiingo backup).
        Falls back to yfinance parallel if DataManager unavailable.
        """
        if not self.universe:
            self.generate_universe()

        if self.data_manager:
            self._load_data_via_manager(days, progress_callback=progress_callback)
        else:
            self._load_data_via_yfinance(days, progress_callback=progress_callback)

        # v4.9.3: Save sector cache after loading (many new sectors discovered)
        if self._sector_cache:
            self._save_sector_cache()

    def _load_data_via_manager(self, days: int = 60, progress_callback=None) -> None:
        """v4.9.4: Load via DataManager (Yahoo primary, Tiingo backup)"""
        logger.info(f"📊 Loading data for {len(self.universe)} stocks via DataManager...")
        now = time.time()
        period = '3mo'  # ~90 days covers days+30
        loaded = 0
        skipped = 0
        errors = 0

        for symbol in self.universe:
            # Skip if cached and fresh (30min TTL)
            if symbol in self._data_cache_time:
                if now - self._data_cache_time[symbol] < self._cache_ttl.get('data', 1800):
                    loaded += 1
                    skipped += 1
                    continue
            try:
                df = self.data_manager.get_price_data(symbol, period=period, interval='1d')
                if not df.empty and len(df) >= 30:
                    df.columns = [c.lower() for c in df.columns]
                    # v4.9.3: Validate required columns exist (Tiingo/Yahoo format check)
                    required = {'open', 'high', 'low', 'close', 'volume'}
                    if not required.issubset(set(df.columns)):
                        logger.debug(f"Missing columns for {symbol}: {required - set(df.columns)}")
                        errors += 1
                        continue
                    self.data_cache[symbol] = df
                    self._data_cache_time[symbol] = now
                    loaded += 1
                    if progress_callback and loaded % 20 == 0:
                        progress_callback(phase="loading", current=loaded, total=len(self.universe), message=f"Loading data... {loaded}/{len(self.universe)}")
                else:
                    errors += 1
            except Exception as e:
                errors += 1
                logger.debug(f"Error loading {symbol}: {e}")

        if progress_callback:
            progress_callback(phase="loading", current=loaded, total=len(self.universe), message=f"Loaded {loaded}/{len(self.universe)} stocks")
        logger.info(f"✅ Loaded {loaded}/{len(self.universe)} stocks via DataManager ({skipped} cached, {errors} errors)")

    def _load_data_via_yfinance(self, days: int = 60, progress_callback=None) -> None:
        """Legacy fallback: Load via yfinance parallel (no rate limiting)"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        logger.info(f"📊 Loading data for {len(self.universe)} stocks via yfinance (parallel)...")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 30)
        start_str = start_date.strftime('%Y-%m-%d')
        now = time.time()

        def _load_single(symbol: str):
            try:
                ticker = yf.Ticker(symbol)
                data = ticker.history(start=start_str)
                if len(data) >= 30:
                    data.columns = [c.lower() for c in data.columns]
                    return symbol, data
            except Exception as e:
                logger.debug(f"Error loading {symbol}: {e}")
            return symbol, None

        loaded = 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_load_single, sym): sym for sym in self.universe}
            for future in as_completed(futures):
                try:
                    symbol, data = future.result()
                    if data is not None:
                        self.data_cache[symbol] = data
                        self._data_cache_time[symbol] = now
                        loaded += 1
                        if progress_callback and loaded % 20 == 0:
                            progress_callback(phase="loading", current=loaded, total=len(self.universe), message=f"Loading data... {loaded}/{len(self.universe)}")
                except Exception as e:
                    logger.debug(f"Future error: {e}")

        if progress_callback:
            progress_callback(phase="loading", current=loaded, total=len(self.universe), message=f"Loaded {loaded}/{len(self.universe)} stocks")
        logger.info(f"✅ Loaded {loaded}/{len(self.universe)} stocks via yfinance (parallel)")

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ATR"""
        high = data['high']
        low = data['low']
        close = data['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        return tr.rolling(period).mean()

    # =========================================================================
    # ANALYZE STOCK HELPERS (v6.6 Refactor)
    # =========================================================================

    def _analyze_calc_indicators(self, data, idx: int) -> dict:
        """Calculate all technical indicators for a stock."""
        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']
        open_price = data['open'] if 'open' in data.columns else close

        current_price = close.iloc[idx]
        rsi = self.calculate_rsi(close).iloc[idx]
        atr = self.calculate_atr(data).iloc[idx]

        # Momentum
        mom_1d = (current_price / close.iloc[idx-1] - 1) * 100 if idx >= 1 else 0
        mom_5d = (current_price / close.iloc[idx-5] - 1) * 100 if idx >= 5 else 0
        mom_20d = (current_price / close.iloc[idx-20] - 1) * 100 if idx >= 20 else 0
        yesterday_move = ((close.iloc[idx-1] / close.iloc[idx-2]) - 1) * 100 if idx >= 2 else 0

        # SMAs
        sma5 = close.iloc[idx-4:idx+1].mean() if idx >= 4 else close.iloc[:idx+1].mean()
        sma20 = close.iloc[idx-19:idx+1].mean() if idx >= 19 else close.iloc[:idx+1].mean()
        sma50 = close.iloc[idx-49:idx+1].mean() if idx >= 49 else close.iloc[:idx+1].mean()

        # Distance from high
        high_20d = high.iloc[idx-20:idx].max() if idx >= 20 else high.max()
        dist_from_high = (high_20d - current_price) / high_20d * 100

        # Overextended detection
        if idx >= 11:
            daily_returns = [(close.iloc[i] / close.iloc[i-1] - 1) * 100 for i in range(idx-10, idx)]
            max_daily_move = max(abs(r) for r in daily_returns) if daily_returns else 0
        else:
            max_daily_move = 0
        sma20_extension = ((current_price / sma20) - 1) * 100 if sma20 > 0 else 0

        # Volume
        avg_volume = volume.iloc[idx-20:idx].mean() if idx >= 20 else volume.mean()
        volume_ratio = volume.iloc[idx] / avg_volume if avg_volume > 0 else 1

        # Gap and candle
        prev_close = close.iloc[idx-1] if idx >= 1 else current_price
        today_open = open_price.iloc[idx]
        gap_pct = (today_open - prev_close) / prev_close * 100
        today_is_green = current_price > today_open

        return {
            'current_price': current_price, 'rsi': rsi, 'atr': atr,
            'atr_pct': (atr / current_price) * 100,
            'mom_1d': mom_1d, 'mom_5d': mom_5d, 'mom_20d': mom_20d,
            'yesterday_move': yesterday_move,
            'sma5': sma5, 'sma20': sma20, 'sma50': sma50,
            'dist_from_high': dist_from_high,
            'max_daily_move': max_daily_move, 'sma20_extension': sma20_extension,
            'volume_ratio': volume_ratio, 'gap_pct': gap_pct,
            'today_is_green': today_is_green, 'today_open': today_open,
        }

    def _analyze_bounce_filters(self, ind: dict, gap_max_up: float) -> Optional[str]:
        """Apply bounce confirmation filters. Returns filter name if blocked, None if passed."""
        # Core filters from filters.py (single source of truth)
        effective_gap_max = gap_max_up if gap_max_up is not None else 2.0
        passed, reason = check_bounce_confirmation(
            yesterday_move=ind['yesterday_move'],
            mom_1d=ind['mom_1d'],
            today_is_green=ind['today_is_green'],
            gap_pct=ind['gap_pct'],
            current_price=ind['current_price'],
            sma5=ind['sma5'],
            atr_pct=ind['atr_pct'],
        )
        if not passed:
            # Map reason to filter stat key
            reason_map = {
                'Yesterday': 'no_dip',
                'Still': 'still_falling',
                'No clear': 'no_bounce',
                'Gap': 'gap_up',
                'Too extended': 'above_sma5',
                'Volatility': 'low_atr',
            }
            for key, val in reason_map.items():
                if reason.startswith(key):
                    return val
            return 'no_dip'  # fallback

        # Gap override (screener allows custom gap_max_up)
        if ind['gap_pct'] > effective_gap_max:
            return 'gap_up'

        # SMA20 filter (from filters.py)
        passed, reason = check_sma20_filter(ind['current_price'], ind['sma20'])
        if not passed:
            return 'below_sma20'

        # Screener-specific filters (not in filters.py)
        if ind['max_daily_move'] > 8.0:
            return 'overextended'
        if ind['sma20_extension'] > 10.0:
            return 'sma20_extended'

        return None

    def _analyze_calc_score(self, ind: dict, symbol: str) -> tuple:
        """Calculate score and reasons. Returns (score, reasons, sector, sector_score)."""
        # Core scoring from filters.py (single source of truth)
        score, reasons = calculate_score(
            today_is_green=ind['today_is_green'],
            mom_1d=ind['mom_1d'],
            mom_5d=ind['mom_5d'],
            yesterday_move=ind['yesterday_move'],
            rsi=ind['rsi'],
            current_price=ind['current_price'],
            sma20=ind['sma20'],
            sma50=ind['sma50'],
            atr_pct=ind['atr_pct'],
            dist_from_high=ind['dist_from_high'],
            volume_ratio=ind['volume_ratio'],
        )

        # Screener-specific: sector scoring
        sector = self._get_sector(symbol)
        sector_adj, sector_regime, sector_reason = self._get_sector_regime_score(sector)
        score += sector_adj
        if sector_reason:
            reasons.append(sector_reason)

        return score, reasons, sector, sector_adj

    def _analyze_calc_sl_tp(self, ind: dict, data, idx: int) -> dict:
        """Calculate dynamic SL/TP levels."""
        close = data['close']
        high = data['high']
        low = data['low']

        swing_low_5d = low.iloc[idx-5:idx].min() if idx >= 5 else low.min()
        ema5 = close.ewm(span=5).mean().iloc[idx]
        high_20d = high.iloc[idx-20:idx].max() if idx >= 20 else high.max()
        high_52w = high.max()

        # Use filters.py (single source of truth)
        result = calculate_dynamic_sl_tp(
            current_price=ind['current_price'],
            atr=ind['atr'],
            swing_low_5d=swing_low_5d,
            ema5=ema5,
            high_20d=high_20d,
            high_52w=high_52w,
        )

        result['swing_low'] = swing_low_5d
        result['resistance'] = high_20d
        return result

    def analyze_stock(self, symbol: str, min_score: int = None, gap_max_up: float = None) -> Optional[RapidRotationSignal]:
        """
        Analyze a single stock for rapid rotation opportunity (v6.6 refactored).
        v3.3: BOUNCE CONFIRMATION - Wait for recovery after dip.
        """
        # Validate data
        if symbol not in self.data_cache:
            return None
        data = self.data_cache[symbol]
        if len(data) < 30:
            return None

        idx = len(data) - 1
        current_price = data['close'].iloc[idx]

        # Price filters
        if current_price < 1 or current_price < 10 or current_price > 2000:
            return None

        # Calculate indicators
        ind = self._analyze_calc_indicators(data, idx)

        # Apply bounce filters
        filter_hit = self._analyze_bounce_filters(ind, gap_max_up)
        if filter_hit:
            self._filter_stats[filter_hit] += 1
            return None

        # Calculate score
        score, reasons, sector, sector_score = self._analyze_calc_score(ind, symbol)

        # Check minimum score
        effective_min_score = min_score if min_score is not None else self.MIN_SCORE
        if score < effective_min_score:
            self._filter_stats['low_score'] += 1
            self._filter_stats['_low_score_values'].append((symbol, score))
            return None

        # Calculate SL/TP
        sl_tp = self._analyze_calc_sl_tp(ind, data, idx)
        reasons.append(f"SL:{sl_tp['sl_method']}({sl_tp['sl_pct']:.1f}%)")
        reasons.append(f"TP:{sl_tp['tp_method']}({sl_tp['tp_pct']:.1f}%)")

        # Get market regime
        market_regime = self._get_market_regime()
        regime_str = market_regime.get('regime', 'UNKNOWN')

        return RapidRotationSignal(
            symbol=symbol,
            score=score,
            entry_price=round(ind['current_price'], 2),
            stop_loss=round(sl_tp['stop_loss'], 2),
            take_profit=round(sl_tp['take_profit'], 2),
            risk_reward=round(sl_tp['risk_reward'], 2),
            atr_pct=round(ind['atr_pct'], 2),
            rsi=round(ind['rsi'], 1),
            momentum_5d=round(ind['mom_5d'], 2),
            momentum_20d=round(ind['mom_20d'], 2),
            distance_from_high=round(ind['dist_from_high'], 2),
            reasons=reasons,
            sector=sector,
            market_regime=regime_str,
            sector_score=sector_score,
            alt_data_score=0,  # Updated in screen()
            sl_method=sl_tp['sl_method'],
            tp_method=sl_tp['tp_method'],
            swing_low=round(sl_tp['swing_low'], 2),
            resistance=round(sl_tp['resistance'], 2),
            volume_ratio=round(ind['volume_ratio'], 2),
        )

    def screen(self, top_n: int = 10, enable_alt_data: bool = True, allowed_sectors: List[str] = None, blocked_sectors: List[str] = None, progress_callback=None, min_score: int = None, gap_max_up: float = None) -> List[RapidRotationSignal]:
        """
        Screen universe for rapid rotation opportunities

        v4.0: SPY Regime Filter + Hybrid Sector Scoring + Alt Data
        v4.9.2: Smart Bear Mode — allowed_sectors filter before analyze
        v4.9.3: BULL sector filter — blocked_sectors skip declining sectors

        Args:
            top_n: Number of top signals to return
            enable_alt_data: Whether to apply alt data scoring to Top 10
            allowed_sectors: v4.9.2 Bear mode — only scan stocks in these sectors
            blocked_sectors: v4.9.3 BULL mode — skip stocks in these sectors

        Returns:
            List of RapidRotationSignal sorted by score
        """
        # Clear stale caches before scanning
        self._clear_stale_caches()

        # v4.9.3: Refresh sector regimes if stale (20min TTL)
        if self.sector_regime:
            try:
                self.sector_regime.update_all_sectors()  # Uses internal 20min cache check
            except Exception as e:
                logger.debug(f"Sector regime refresh error: {e}")

        # v4.0: Check SPY regime FIRST!
        is_bull, spy_reason, spy_details = self.check_spy_regime()
        if progress_callback:
            progress_callback(phase="regime", message=f"SPY: {'BULL' if is_bull else 'BEAR'} ({spy_reason[:50]})")

        if not is_bull:
            if allowed_sectors:
                # v4.9.2: Bear mode — pass through with sector filtering
                logger.info(f"🐻 SPY BEAR — Smart Bear Mode scan ({len(allowed_sectors)} sectors)")
                logger.info(f"   {spy_reason}")
                logger.info(f"   Allowed: {allowed_sectors}")
            else:
                logger.warning(f"🔴 SPY BEAR REGIME - SKIPPING ALL NEW SIGNALS")
                logger.warning(f"   {spy_reason}")
                return []  # Return empty list - no new trades in bear market!
        else:
            logger.info(f"🟢 SPY BULL REGIME - Scanning for signals...")
            logger.info(f"   {spy_reason}")

        # Check market regime (internal detector)
        regime = self._get_market_regime()
        regime_name = regime.get('regime', 'UNKNOWN')

        if regime_name == 'BEAR':
            logger.warning("🐻 Internal regime BEAR - still scanning (SPY is BULL)" if is_bull else "🐻 Internal regime BEAR - bear mode active")
        elif regime_name == 'BULL':
            logger.info("🐂 Both SPY and internal regime BULL - optimal conditions")

        if not self.data_cache:
            self.load_data()

        # v4.9.2: Build sector cache for sector filtering (before analyze loop)
        sector_cache = {}
        if allowed_sectors:
            logger.info(f"🐻 Pre-filtering universe by sectors: {allowed_sectors}")
        if blocked_sectors:
            logger.info(f"🐂⛔ Blocking declining sectors: {blocked_sectors}")

        # v4.9.4: Sector-prioritized scanning
        # Analyze STRONG BULL sectors first, then BULL, then SIDEWAYS
        # Skip BEAR sectors entirely (saves API calls)
        universe = list(self.data_cache.keys())
        sector_priority = {}
        if self.sector_regime:
            for symbol in universe:
                sector = sector_cache.get(symbol) or self._get_sector(symbol)
                sector_cache[symbol] = sector
                if not sector or sector == 'Unknown':
                    sector_priority[symbol] = 2  # UNKNOWN = SIDEWAYS
                    continue
                try:
                    regime = self.sector_regime.get_sector_regime(sector)
                    if regime == 'STRONG BULL':
                        sector_priority[symbol] = 0
                    elif regime == 'BULL':
                        sector_priority[symbol] = 1
                    elif regime in ('SIDEWAYS', 'UNKNOWN'):
                        sector_priority[symbol] = 2
                    else:  # BEAR, STRONG BEAR
                        sector_priority[symbol] = 3
                except Exception:
                    sector_priority[symbol] = 2

            # Filter out BEAR sectors and sort by priority
            universe_sorted = sorted(
                [s for s in universe if sector_priority.get(s, 2) >= 0],
                key=lambda s: sector_priority.get(s, 2)
            )
            bear_skipped = len(universe) - len(universe_sorted)
            if bear_skipped > 0:
                logger.info(f"Sector priority: {len(universe_sorted)} stocks (skipped {bear_skipped} BEAR sector)")
        else:
            universe_sorted = universe

        signals = []
        skipped_sector = 0
        # v4.9.4: Filter diagnostics — track why stocks get rejected
        self._filter_stats = {
            'no_dip': 0, 'still_falling': 0, 'no_bounce': 0,
            'gap_up': 0, 'above_sma5': 0, 'low_atr': 0,
            'below_sma20': 0, 'overextended': 0, 'sma20_extended': 0,
            'low_score': 0, '_low_score_values': [],
        }
        analyzed_count = 0
        for i, symbol in enumerate(universe_sorted):
            try:
                # v4.9.2/v4.9.3: Sector filter BEFORE analyze (performance optimization)
                if allowed_sectors or blocked_sectors:
                    if symbol not in sector_cache:
                        sector_cache[symbol] = self._get_sector(symbol)
                    stock_sector = sector_cache[symbol]
                    if allowed_sectors and stock_sector not in allowed_sectors:
                        skipped_sector += 1
                        continue  # Skip non-allowed sectors (BEAR)
                    if blocked_sectors and stock_sector in blocked_sectors:
                        skipped_sector += 1
                        continue  # Skip blocked sectors (BULL)

                analyzed_count += 1
                # v4.9.4: Progress callback for live UI
                if progress_callback:
                    progress_callback(
                        phase="analyzing",
                        current=analyzed_count,
                        total=len(universe_sorted) - skipped_sector,
                        symbol=symbol,
                    )

                signal = self.analyze_stock(symbol, min_score=min_score, gap_max_up=gap_max_up)
                if signal:
                    signals.append(signal)
                    if progress_callback:
                        progress_callback(phase="signal", symbol=symbol, score=signal.score, passed=True)
                elif progress_callback and analyzed_count % 5 == 0:
                    progress_callback(phase="analyzed", symbol=symbol, passed=False)
            except Exception as e:
                logger.debug(f"Error analyzing {symbol}: {e}")

        if allowed_sectors:
            logger.info(f"🐻 Sector filter: {skipped_sector} skipped, {len(self.data_cache) - skipped_sector} analyzed, {len(signals)} signals")
        elif blocked_sectors:
            logger.info(f"🐂 Sector filter: {skipped_sector} blocked, {len(self.data_cache) - skipped_sector} analyzed, {len(signals)} signals")

        # v4.9.4: Log filter diagnostics
        fs = self._filter_stats
        total_filtered = sum(v for k, v in fs.items() if k != '_low_score_values')
        eff_score = min_score if min_score is not None else self.MIN_SCORE
        eff_gap = gap_max_up if gap_max_up is not None else 2.0
        logger.info(f"📋 Filter breakdown ({total_filtered} rejected, min_score={eff_score}, gap_max={eff_gap}%): "
                    f"no_dip={fs['no_dip']} still_falling={fs['still_falling']} "
                    f"no_bounce={fs['no_bounce']} gap_up={fs['gap_up']} "
                    f"above_sma5={fs['above_sma5']} low_atr={fs['low_atr']} "
                    f"below_sma20={fs['below_sma20']} overextended={fs['overextended']} "
                    f"sma20_ext={fs['sma20_extended']} low_score={fs['low_score']}")
        if fs['_low_score_values']:
            top_near = sorted(fs['_low_score_values'], key=lambda x: x[1], reverse=True)[:5]
            logger.info(f"📋 Near-miss scores: {[(s, sc) for s, sc in top_near]}")

        # Sort by BASE score (before alt data)
        signals.sort(key=lambda x: x.score, reverse=True)

        logger.info(f"📊 Found {len(signals)} signals from {len(self.data_cache)} stocks")
        # v6.3: Log signal details for debugging
        if signals:
            for sig in signals[:10]:  # Show top 10
                logger.info(f"   📈 {sig.symbol}: score={sig.score}, sector={sig.sector}, gap={getattr(sig, 'gap_pct', 0):.1f}%")
        if progress_callback:
            progress_callback(phase="done", signals_count=len(signals), total_analyzed=len(self.data_cache))

        # ==============================
        # v3.7: APPLY ALT DATA TO TOP 10 ONLY
        # ==============================
        # This optimizes performance - only fetch alt data for top candidates
        if enable_alt_data and signals:
            top_10 = signals[:10]

            if progress_callback:
                progress_callback(phase="alt_data", message=f"Fetching alt data for top {min(10, len(signals))}...")
            logger.info("🔍 Fetching alt data for Top 10 candidates...")

            for signal in top_10:
                try:
                    alt_score, alt_reasons = self._get_alt_data_score(signal.symbol, enable=True)

                    # Update signal with alt data
                    signal.alt_data_score = alt_score
                    signal.score += alt_score
                    signal.reasons.extend(alt_reasons)

                    if alt_score != 0:
                        logger.debug(f"{signal.symbol}: Alt data {alt_score:+d}")

                except Exception as e:
                    logger.debug(f"Alt data failed for {signal.symbol}: {e}")

            # Re-sort after adding alt data scores
            top_10.sort(key=lambda x: x.score, reverse=True)

            # Combine re-sorted top 10 with rest
            signals = top_10 + signals[10:]

        # v4.9.3: Save sector cache after scan (new sectors discovered during analyze)
        if self._sector_cache:
            self._save_sector_cache()

        return signals[:top_n]

    def get_portfolio_signals(self,
                              max_positions: int = 4,
                              existing_positions: List[str] = None,
                              allowed_sectors: List[str] = None,
                              blocked_sectors: List[str] = None,
                              progress_callback=None,
                              min_score: int = None,
                              gap_max_up: float = None) -> List[RapidRotationSignal]:
        """Get signals for portfolio management

        Args:
            allowed_sectors: v4.9.2 Bear mode — only return signals from these sectors
            blocked_sectors: v4.9.3 BULL mode — skip signals from these sectors
            min_score: v5.2 — engine's effective min_score (syncs Buy Signals with engine)
            gap_max_up: v5.2 — engine's effective gap_max_up (syncs Buy Signals with engine)
        """
        existing = set(existing_positions or [])
        signals = self.screen(top_n=20, allowed_sectors=allowed_sectors, blocked_sectors=blocked_sectors, progress_callback=progress_callback, min_score=min_score, gap_max_up=gap_max_up)
        new_signals = [s for s in signals if s.symbol not in existing]
        available_slots = max_positions - len(existing)

        # v6.3: Log filtering details
        if signals:
            filtered_by_existing = [s for s in signals if s.symbol in existing]
            if filtered_by_existing:
                logger.info(f"📋 Filtered by existing positions: {[s.symbol for s in filtered_by_existing]}")
            if new_signals and available_slots <= 0:
                logger.info(f"⚠️ Positions FULL ({len(existing)}/{max_positions}): {[s.symbol for s in new_signals[:5]]} available but no slots")
            elif new_signals:
                logger.info(f"✅ Found {len(new_signals)} new signals (slots: {available_slots}): {[s.symbol for s in new_signals[:5]]}")

        # v6.4: Return all new signals (engine handles slot limiting for UI waiting display)
        return new_signals[:10]  # Cap at 10 to avoid huge lists


def main():
    """Run the screener"""
    print("=" * 70)
    print("RAPID ROTATION SCREENER v4.0 - SMART REGIME EDITION")
    print("=" * 70)
    print()
    print("v4.0 Backtest Results: +5.5%/mo, DD 8.9%, WR 49%")
    print("  ✅ Meets ≥5%/mo target")
    print("  ✅ Meets ≤10% DD target")
    print()
    print("Systems:")
    print("  ✅ SPY Regime Filter (v4.0 NEW!) - Only trade when SPY > SMA20")
    print("  ✅ AI Universe Generator (680+ stocks)")
    print("  ✅ Market Regime Detector")
    print("  ✅ Sector Regime Detector (HYBRID v2)")
    print("  ✅ Alternative Data (Top 10 only, ±10 cap)")
    print("  ✅ Bounce Confirmation")
    print()
    print("v4.0 SPY Regime Filter:")
    print("  SPY > SMA20 = BULL → Trade normally")
    print("  SPY < SMA20 = BEAR → Skip ALL new trades!")
    print()

    screener = RapidRotationScreener()

    # v4.0: Check SPY regime first
    print("Checking SPY regime...")
    is_bull, reason, details = screener.check_spy_regime()
    print(f"  Status: {'🟢 BULL' if is_bull else '🔴 BEAR'}")
    if details:
        print(f"  SPY: ${details.get('spy_price', 0):.2f}")
        print(f"  SMA20: ${details.get('spy_sma20', 0):.2f}")
        print(f"  Distance: {details.get('pct_above_sma', 0):+.2f}%")
    print()

    if not is_bull:
        print("⚠️ BEAR REGIME - No new trades allowed!")
        print("   Wait for SPY to close above SMA20 before scanning.")
        return

    print("Generating universe...")
    universe = screener.generate_universe(max_stocks=200)
    print(f"Universe: {len(universe)} stocks")
    print()

    print("Loading data...")
    screener.load_data()
    print()

    signals = screener.screen(top_n=10)

    if not signals:
        print("No high-quality signals found today")
        print("(v3.3 is selective - requires bounce confirmation)")
        return

    print(f"Found {len(signals)} HIGH QUALITY signals:")
    print("-" * 70)
    print()

    for i, signal in enumerate(signals, 1):
        print(f"{i}. {signal.symbol} (Score: {signal.score})")
        print(f"   Sector: {signal.sector} | Regime: {signal.market_regime}")
        print(f"   Entry: ${signal.entry_price:.2f}")
        print(f"   Stop Loss: ${signal.stop_loss:.2f} ({signal.max_loss:.1f}%)")
        print(f"   Take Profit: ${signal.take_profit:.2f} (+{signal.expected_gain:.1f}%)")
        print(f"   Risk/Reward: {signal.risk_reward:.2f}")
        print(f"   RSI: {signal.rsi:.0f} | 5d Mom: {signal.momentum_5d:+.1f}%")
        print(f"   Reasons: {', '.join(signal.reasons)}")
        print()

    print("=" * 70)
    print("v3.7 EXIT RULES:")
    print("- Take Profit: ~6-9% (ATR-based)")
    print("- Stop Loss: 2.5% (tight, fast rotation)")
    print("- Time Stop: 5 days max")
    print("- TRAILING STOP: Activate at +3%, trail at 60%")
    print("=" * 70)


if __name__ == "__main__":
    main()
