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

    # Configuration (v4.0: Smart Regime Edition)
    MIN_ATR_PCT = 2.5  # Minimum volatility
    MIN_SCORE = 85     # v4.0: 90 → 85 (regime filter compensates)
    MAX_HOLD_DAYS = 5  # Max hold days

    # v4.0: SPY Regime Filter
    REGIME_FILTER_ENABLED = True
    REGIME_SMA_PERIOD = 20

    # v3.4: ATR Multipliers for FULLY DYNAMIC SL/TP
    ATR_SL_MULTIPLIER = 1.5   # SL = ATR × 1.5 (gives room to breathe)
    ATR_TP_MULTIPLIER = 3.0   # TP = ATR × 3 (good risk/reward)

    # Safety caps (prevent extreme values)
    # v4.9.3: Synced with Engine caps (SL_MIN/MAX_PCT, TP_MIN/MAX_PCT)
    MIN_SL_PCT = 2.0   # Minimum SL 2%  (= Engine SL_MIN_PCT)
    MAX_SL_PCT = 4.0   # Maximum SL 4%  (= Engine SL_MAX_PCT, was 2.5%)
    MIN_TP_PCT = 4.0   # Minimum TP 4%  (= Engine TP_MIN_PCT)
    MAX_TP_PCT = 8.0   # Maximum TP 8%  (= Engine TP_MAX_PCT, was 15%)

    # Trailing stop parameters
    TRAIL_ACTIVATION = 3.0  # Activate trailing at +3%

    # v3.7: HYBRID SECTOR SCORING (asymmetric - defensive approach)
    # Based on 20-day sector ETF performance (±3% threshold)
    SECTOR_BULL_THRESHOLD = 3.0    # > +3% = BULL
    SECTOR_BEAR_THRESHOLD = -3.0   # < -3% = BEAR
    SECTOR_BULL_BONUS = 5          # BULL sector: +5 points (small bonus)
    SECTOR_BEAR_PENALTY = -10      # BEAR sector: -10 points (defensive - penalize harder)
    SECTOR_SIDEWAYS_ADJ = 0        # SIDEWAYS: 0 points

    # v3.7: ALT DATA SCORING (tie-breaker role, not dominant)
    ALT_DATA_MAX_BONUS = 15        # v4.9.4: Max +15 points (was 10)
    ALT_DATA_MAX_PENALTY = -15     # v4.9.4: Max -15 points (was -10)

    # v4.9.3: Sector cache config
    SECTOR_CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'sector_cache.json')
    SECTOR_CACHE_TTL_DAYS = 3     # หุ้นอาจเปลี่ยน sector (M&A, reclassification)
    SECTOR_CACHE_TTL = 86400 * 3  # computed from SECTOR_CACHE_TTL_DAYS

    # v4.9.3: AI universe disk cache
    AI_UNIVERSE_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'ai_universe_cache.json')

    def __init__(self):
        """Initialize with all integrated systems"""
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self._data_cache_time: Dict[str, float] = {}
        self.universe: List[str] = []
        self.data_manager = None  # v4.9.3: Shared DataManager for Tiingo routing

        # v4.9.3: Persistent sector cache (memory + disk)
        self._sector_cache: Dict[str, dict] = {}
        self._load_sector_cache()

        # Initialize integrated systems
        self._init_ai_universe()
        self._init_market_regime()
        self._init_sector_regime()
        self._init_alt_data()

        # SPY regime cache (Fix #38: avoid downloading SPY every call)
        self._spy_regime_cache = None  # (is_bull, reason, details, timestamp)
        self._spy_cache_seconds = 300  # 5 minutes

        # Cache for regime data (with timestamps)
        self._market_regime_cache = None
        self._market_regime_cache_time: float = 0.0
        self._sector_regime_cache = {}
        self._sector_regime_cache_time: float = 0.0
        self._alt_data_cache = {}
        self._alt_data_cache_time: float = 0.0

        # Cache TTL in seconds
        self._cache_ttl = {
            'market_regime': 300,   # 5 min
            'sector_regime': 600,   # 10 min
            'alt_data': 300,        # 5 min
            'data': 1800,           # 30 min
        }

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
        """Initialize Market Regime Detector"""
        try:
            from market_regime_detector import MarketRegimeDetector
            self.market_regime = MarketRegimeDetector()
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
        Generate stock universe using AI or fallback to default

        Args:
            max_stocks: Maximum stocks to include

        Returns:
            List of stock symbols
        """
        universe = []

        # Try AI Universe Generator first
        if self.ai_generator:
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
                logger.warning("Not enough SPY data for regime check")
                return True, "Insufficient data", {}

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

    def load_data(self, days: int = 60) -> None:
        """Load historical data for universe

        v4.9.4: Route through DataManager (Yahoo primary, Tiingo backup).
        Falls back to yfinance parallel if DataManager unavailable.
        """
        if not self.universe:
            self.generate_universe()

        if self.data_manager:
            self._load_data_via_manager(days)
        else:
            self._load_data_via_yfinance(days)

        # v4.9.3: Save sector cache after loading (many new sectors discovered)
        if self._sector_cache:
            self._save_sector_cache()

    def _load_data_via_manager(self, days: int = 60) -> None:
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
                else:
                    errors += 1
            except Exception as e:
                errors += 1
                logger.debug(f"Error loading {symbol}: {e}")

        logger.info(f"✅ Loaded {loaded}/{len(self.universe)} stocks via DataManager ({skipped} cached, {errors} errors)")

    def _load_data_via_yfinance(self, days: int = 60) -> None:
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
                except Exception as e:
                    logger.debug(f"Future error: {e}")

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

    def analyze_stock(self, symbol: str) -> Optional[RapidRotationSignal]:
        """
        Analyze a single stock for rapid rotation opportunity

        v3.3: BOUNCE CONFIRMATION - Wait for recovery after dip
        Key change: Don't catch falling knife, wait for bounce
        """
        if symbol not in self.data_cache:
            return None

        data = self.data_cache[symbol]
        if len(data) < 30:
            return None

        idx = len(data) - 1
        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']
        open_price = data['open'] if 'open' in data.columns else close

        current_price = close.iloc[idx]

        # Skip penny stocks and very expensive stocks
        if current_price < 10 or current_price > 2000:
            return None

        # Calculate indicators
        rsi = self.calculate_rsi(close).iloc[idx]
        atr = self.calculate_atr(data).iloc[idx]
        atr_pct = (atr / current_price) * 100

        # Momentum
        mom_1d = (current_price / close.iloc[idx-1] - 1) * 100 if idx >= 1 else 0
        mom_5d = (current_price / close.iloc[idx-5] - 1) * 100 if idx >= 5 else 0
        mom_20d = (current_price / close.iloc[idx-20] - 1) * 100 if idx >= 20 else 0

        # Yesterday's move (key for bounce confirmation)
        yesterday_move = ((close.iloc[idx-1] / close.iloc[idx-2]) - 1) * 100 if idx >= 2 else 0

        # SMAs (include current bar: idx-N+1 to idx+1)
        sma5 = close.iloc[idx-4:idx+1].mean() if idx >= 4 else close.iloc[:idx+1].mean()
        sma20 = close.iloc[idx-19:idx+1].mean() if idx >= 19 else close.iloc[:idx+1].mean()
        sma50 = close.iloc[idx-49:idx+1].mean() if idx >= 49 else close.iloc[:idx+1].mean()

        # Distance from recent high
        high_20d = high.iloc[idx-20:idx].max() if idx >= 20 else high.max()
        dist_from_high = (high_20d - current_price) / high_20d * 100

        # v3.10: Overextended detection
        # Calculate max single-day move in last 10 days (extended window)
        if idx >= 11:
            daily_returns = [(close.iloc[i] / close.iloc[i-1] - 1) * 100 for i in range(idx-10, idx)]
            max_daily_move = max(abs(r) for r in daily_returns) if daily_returns else 0
        else:
            max_daily_move = 0

        # Distance from SMA20 (how far price is above SMA20)
        sma20_extension = ((current_price / sma20) - 1) * 100 if sma20 > 0 else 0

        # Volume
        avg_volume = volume.iloc[idx-20:idx].mean() if idx >= 20 else volume.mean()
        volume_ratio = volume.iloc[idx] / avg_volume if avg_volume > 0 else 1

        # Support level
        support = low.iloc[idx-10:idx].min() if idx >= 10 else low.min()

        # Gap calculation
        prev_close = close.iloc[idx-1] if idx >= 1 else current_price
        today_open = open_price.iloc[idx]
        gap_pct = (today_open - prev_close) / prev_close * 100

        # Today's candle color (for bounce confirmation)
        today_is_green = current_price > today_open

        # ==============================
        # v3.3: BOUNCE CONFIRMATION FILTERS
        # ==============================
        # Key insight: Don't catch falling knife, wait for bounce

        # FILTER 1: Yesterday MUST be down (the dip day)
        if yesterday_move > -1.0:
            self._filter_stats['no_dip'] += 1
            return None  # Need yesterday to be a dip

        # FILTER 2: Today should show recovery (not falling further)
        if mom_1d < -1.0:
            self._filter_stats['still_falling'] += 1
            return None  # Still falling hard, wait

        # FILTER 3: Strong preference for green candle (bounce signal)
        if not today_is_green and mom_1d < 0.5:
            self._filter_stats['no_bounce'] += 1
            return None  # No clear bounce yet

        # FILTER 4: Skip big gap ups (exhaustion risk)
        if gap_pct > 2.0:
            self._filter_stats['gap_up'] += 1
            return None

        # FILTER 5: Still in oversold zone (room to recover)
        if current_price > sma5 * 1.02:
            self._filter_stats['above_sma5'] += 1
            return None

        # FILTER 6: Minimum volatility
        if atr_pct < self.MIN_ATR_PCT:
            self._filter_stats['low_atr'] += 1
            return None

        # ==============================
        # v3.5: SMA20 FILTER (ROOT CAUSE FIX)
        # ==============================
        # Based on root cause analysis: 92% of stop loss trades
        # were below SMA20 (downtrend). This filter prevents most losers.
        if current_price < sma20:
            self._filter_stats['below_sma20'] += 1
            return None  # Must be above SMA20 (uptrend)

        # ==============================
        # v3.10: OVEREXTENDED FILTER (ARM FIX)
        # ==============================
        # Prevents entering after big moves (like ARM +17% in 1 day)
        # These often lead to mean reversion and stop loss hits

        # FILTER 7: No big single-day moves in last 5 days
        MAX_SINGLE_DAY_MOVE = 8.0  # Skip if any day had >8% move
        if max_daily_move > MAX_SINGLE_DAY_MOVE:
            self._filter_stats['overextended'] += 1
            return None  # Overextended - wait for consolidation

        # FILTER 8: Price not too far above SMA20
        MAX_SMA20_EXTENSION = 10.0  # Skip if >10% above SMA20
        if sma20_extension > MAX_SMA20_EXTENSION:
            self._filter_stats['sma20_extended'] += 1
            return None  # Too extended above SMA20

        # ==============================
        # v3.3 SCORING - Quality over quantity
        # ==============================
        score = 0
        reasons = []

        # 1. BOUNCE CONFIRMATION (key differentiator - doubled weight)
        if today_is_green and mom_1d > 0.5:
            score += 40
            reasons.append("Strong bounce")
        elif today_is_green or mom_1d > 0.3:
            score += 25
            reasons.append("Bounce confirmed")

        # 2. Prior dip magnitude (5-day)
        if -12 <= mom_5d <= -5:
            score += 40
            reasons.append(f"Deep dip {mom_5d:.1f}%")
        elif -5 < mom_5d <= -3:
            score += 30
            reasons.append(f"Good dip {mom_5d:.1f}%")
        elif -3 < mom_5d < 0:
            score += 15
            reasons.append(f"Mild dip {mom_5d:.1f}%")

        # 3. Yesterday's dip (entry catalyst)
        if yesterday_move <= -3:
            score += 30
            reasons.append(f"Big dip yesterday {yesterday_move:.1f}%")
        elif yesterday_move <= -1.5:
            score += 20
            reasons.append(f"Dip yesterday {yesterday_move:.1f}%")
        elif yesterday_move <= -1:
            score += 10

        # 4. RSI scoring
        if 25 <= rsi <= 40:
            score += 35
            reasons.append(f"Very oversold RSI={rsi:.0f}")
        elif 40 < rsi <= 50:
            score += 20
            reasons.append(f"Low RSI={rsi:.0f}")

        # 5. Trend context (important for bounce success)
        if current_price > sma50 and current_price > sma20 * 0.98:
            score += 25
            reasons.append("Strong uptrend")
        elif current_price > sma20:
            score += 15
            reasons.append("Above SMA20")

        # 6. Volatility bonus
        if atr_pct > 5:
            score += 20
            reasons.append(f"Very volatile {atr_pct:.1f}%")
        elif atr_pct > 4:
            score += 15
            reasons.append(f"High vol {atr_pct:.1f}%")
        elif atr_pct > 3:
            score += 10

        # 7. Room to recover
        if 10 <= dist_from_high <= 25:
            score += 20
            reasons.append(f"Great room {dist_from_high:.0f}%")
        elif 6 <= dist_from_high < 10:
            score += 10
            reasons.append(f"Some room {dist_from_high:.0f}%")

        # 8. Volume confirmation
        if volume_ratio > 1.5:
            score += 15
            reasons.append("High vol bounce")
        elif volume_ratio > 1.2:
            score += 5

        # ==============================
        # v3.7: HYBRID SECTOR SCORING (replaces old hot sector bonus)
        # ==============================
        # Uses simple ±3% rule on 20-day sector ETF performance
        # BEAR: -10 | SIDEWAYS: 0 | BULL: +5 (asymmetric - defensive)
        sector = self._get_sector(symbol)
        sector_adj, sector_regime, sector_reason = self._get_sector_regime_score(sector)
        sector_score = sector_adj  # For signal object
        score += sector_adj
        if sector_reason:
            reasons.append(sector_reason)

        # ==============================
        # v3.7: ALT DATA DEFERRED TO screen() FOR TOP 10 ONLY
        # ==============================
        # Alt data is applied only to Top 10 candidates for performance
        # See screen() method - alt_data_score will be added there
        alt_score = 0  # Placeholder - will be updated in screen()

        # Check minimum score (v3.3: Higher threshold = 90)
        if score < self.MIN_SCORE:
            self._filter_stats['low_score'] += 1
            self._filter_stats['_low_score_values'].append((symbol, score))
            return None

        # ==============================
        # v3.4: FULLY DYNAMIC SL/TP
        # ==============================

        # --- DYNAMIC STOP LOSS ---
        # Method 1: ATR-based (adapts to volatility)
        atr_sl_distance = atr * self.ATR_SL_MULTIPLIER
        atr_based_sl = current_price - atr_sl_distance

        # Method 2: Swing Low based (structure)
        swing_low_5d = low.iloc[idx-5:idx].min() if idx >= 5 else low.min()
        swing_low_sl = swing_low_5d * 0.995  # 0.5% below swing low

        # Method 3: EMA based (trend)
        ema5 = close.ewm(span=5).mean().iloc[idx]
        ema_based_sl = ema5 * 0.99  # 1% below EMA5

        # Choose HIGHEST SL = best protection + track method
        sl_options = {
            'ATR': atr_based_sl,
            'SwingLow': swing_low_sl,
            'EMA5': ema_based_sl
        }
        sl_method = max(sl_options, key=sl_options.get)
        stop_loss = sl_options[sl_method]

        # Apply safety caps
        sl_pct_raw = (current_price - stop_loss) / current_price * 100
        sl_pct = max(self.MIN_SL_PCT, min(sl_pct_raw, self.MAX_SL_PCT))
        stop_loss = current_price * (1 - sl_pct / 100)

        # --- DYNAMIC TAKE PROFIT ---
        # Method 1: ATR-based (scales with volatility)
        atr_tp_distance = atr * self.ATR_TP_MULTIPLIER
        atr_based_tp = current_price + atr_tp_distance

        # Method 2: Resistance based (structure)
        resistance = high.iloc[idx-20:idx].max() if idx >= 20 else high.max()
        resistance_tp = resistance * 0.995  # Just below resistance

        # Method 3: 52-week high consideration
        high_52w = high.max()
        high_52w_tp = high_52w * 0.98  # 2% below 52w high

        # Choose LOWEST TP = most realistic target + track method
        tp_options = {
            'ATR': atr_based_tp,
            'Resistance': resistance_tp,
            '52wHigh': high_52w_tp
        }
        tp_method = min(tp_options, key=tp_options.get)
        take_profit = tp_options[tp_method]

        # Apply safety caps
        tp_pct_raw = (take_profit - current_price) / current_price * 100
        tp_pct = max(self.MIN_TP_PCT, min(tp_pct_raw, self.MAX_TP_PCT))
        take_profit = current_price * (1 + tp_pct / 100)
        risk_reward = tp_pct / sl_pct

        # Get market regime
        market_regime = self._get_market_regime()
        regime_str = market_regime.get('regime', 'UNKNOWN')

        # Add SL/TP method info to reasons
        reasons.append(f"SL:{sl_method}({sl_pct:.1f}%)")
        reasons.append(f"TP:{tp_method}({tp_pct:.1f}%)")

        return RapidRotationSignal(
            symbol=symbol,
            score=score,
            entry_price=round(current_price, 2),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            risk_reward=round(risk_reward, 2),
            atr_pct=round(atr_pct, 2),
            rsi=round(rsi, 1),
            momentum_5d=round(mom_5d, 2),
            momentum_20d=round(mom_20d, 2),
            distance_from_high=round(dist_from_high, 2),
            reasons=reasons,
            sector=sector,
            market_regime=regime_str,
            sector_score=sector_score,
            alt_data_score=alt_score,
            # v3.4: Dynamic SL/TP info
            sl_method=sl_method,
            tp_method=tp_method,
            swing_low=round(swing_low_5d, 2),
            resistance=round(resistance, 2)
        )

    def screen(self, top_n: int = 10, enable_alt_data: bool = True, allowed_sectors: List[str] = None, blocked_sectors: List[str] = None) -> List[RapidRotationSignal]:
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
                        sector_priority[symbol] = -1
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
        for symbol in universe_sorted:
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

                signal = self.analyze_stock(symbol)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"Error analyzing {symbol}: {e}")

        if allowed_sectors:
            logger.info(f"🐻 Sector filter: {skipped_sector} skipped, {len(self.data_cache) - skipped_sector} analyzed, {len(signals)} signals")
        elif blocked_sectors:
            logger.info(f"🐂 Sector filter: {skipped_sector} blocked, {len(self.data_cache) - skipped_sector} analyzed, {len(signals)} signals")

        # v4.9.4: Log filter diagnostics
        fs = self._filter_stats
        total_filtered = sum(v for k, v in fs.items() if k != '_low_score_values')
        logger.info(f"📋 Filter breakdown ({total_filtered} rejected): "
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

        # ==============================
        # v3.7: APPLY ALT DATA TO TOP 10 ONLY
        # ==============================
        # This optimizes performance - only fetch alt data for top candidates
        if enable_alt_data and signals:
            top_10 = signals[:10]

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
                              blocked_sectors: List[str] = None) -> List[RapidRotationSignal]:
        """Get signals for portfolio management

        Args:
            allowed_sectors: v4.9.2 Bear mode — only return signals from these sectors
            blocked_sectors: v4.9.3 BULL mode — skip signals from these sectors
        """
        existing = set(existing_positions or [])
        signals = self.screen(top_n=20, allowed_sectors=allowed_sectors, blocked_sectors=blocked_sectors)
        new_signals = [s for s in signals if s.symbol not in existing]
        available_slots = max_positions - len(existing)
        return new_signals[:available_slots]


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
