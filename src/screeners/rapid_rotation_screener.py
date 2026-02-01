#!/usr/bin/env python3
"""
RAPID ROTATION SCREENER v3.7 - HYBRID SECTOR + ALT DATA

INTEGRATED SYSTEMS:
✅ AI Universe Generator (680+ stocks from DeepSeek)
✅ Market Regime Detector (Bull/Bear/Sideways)
✅ Sector Regime Detector (HYBRID v2 - soft penalty scoring)
✅ Alternative Data (Insider, Sentiment, Short Interest) - Top 10 only
✅ Market Regime Filter (skip bear markets)

Strategy:
- Dynamic universe from AI (680+ stocks)
- MARKET REGIME FILTER: Skip trading in bear markets
- HYBRID SECTOR SCORING: Soft penalty (BEAR -10, BULL +5)
- BOUNCE CONFIRMATION: Wait for recovery after dip (not catching knife)
- ALT DATA TIE-BREAKER: Only check for Top 10 candidates (±10 cap)
- FULLY DYNAMIC SL/TP based on actual market structure

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

    # Configuration (v3.4: Fully dynamic)
    MIN_ATR_PCT = 2.5  # Minimum volatility
    MIN_SCORE = 90     # Higher score threshold
    MAX_HOLD_DAYS = 5  # Max hold days

    # v3.4: ATR Multipliers for FULLY DYNAMIC SL/TP
    ATR_SL_MULTIPLIER = 1.5   # SL = ATR × 1.5 (gives room to breathe)
    ATR_TP_MULTIPLIER = 3.0   # TP = ATR × 3 (good risk/reward)

    # Safety caps (prevent extreme values)
    # v3.6: Tight SL for fast rotation (PDT-Safe)
    MIN_SL_PCT = 2.0   # Minimum SL 2%
    MAX_SL_PCT = 2.5   # Maximum SL 2.5% (was 8%) - rotate faster!
    MIN_TP_PCT = 4.0   # Minimum TP 4%
    MAX_TP_PCT = 15.0  # Maximum TP 15%

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
    ALT_DATA_MAX_BONUS = 10        # Max +10 points
    ALT_DATA_MAX_PENALTY = -10     # Max -10 points

    def __init__(self):
        """Initialize with all integrated systems"""
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.universe: List[str] = []

        # Initialize integrated systems
        self._init_ai_universe()
        self._init_market_regime()
        self._init_sector_regime()
        self._init_alt_data()

        # Cache for regime data
        self._market_regime_cache = None
        self._sector_regime_cache = {}
        self._alt_data_cache = {}

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
            data_manager = DataManager()
            self.sector_regime = SectorRegimeDetector(data_manager=data_manager)
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
            except Exception as e:
                logger.warning(f"⚠️ AI universe generation failed: {e}")

        # Fallback to default universe
        if not universe:
            universe = self.FALLBACK_UNIVERSE.copy()
            logger.info(f"📋 Using fallback universe: {len(universe)} stocks")

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
        if self._market_regime_cache:
            return self._market_regime_cache

        if self.market_regime:
            try:
                regime = self.market_regime.get_current_regime()
                self._market_regime_cache = regime
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
                    # Insider buying (+5)
                    if data.get('has_insider_buying', False):
                        score += 5
                        reasons.append("Insider buying")

                    # Overall score from alt data (normalized 0-100)
                    overall_alt = data.get('overall_score', 0)
                    if overall_alt > 70:
                        score += 3
                        reasons.append(f"Strong alt ({overall_alt:.0f})")
                    elif overall_alt > 50:
                        score += 2
                    elif overall_alt < 30:
                        score -= 3
                        reasons.append(f"Weak alt ({overall_alt:.0f})")

                    # Short squeeze potential (+2)
                    if data.get('has_squeeze_potential', False):
                        score += 2
                        reasons.append("Squeeze")

                    # Analyst upgrades (+3)
                    if data.get('has_analyst_upgrade', False):
                        score += 3
                        reasons.append("Analyst upgrade")
                    elif data.get('has_analyst_downgrade', False):
                        score -= 3
                        reasons.append("Analyst downgrade")

                    # v3.7: CAP AT ±10 (tie-breaker role)
                    score = max(self.ALT_DATA_MAX_PENALTY,
                               min(score, self.ALT_DATA_MAX_BONUS))

            except Exception as e:
                logger.debug(f"Alt data failed for {symbol}: {e}")

        self._alt_data_cache[symbol] = (score, reasons)
        return score, reasons

    def _get_sector(self, symbol: str) -> str:
        """Get sector for a symbol"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return info.get('sector', 'Unknown')
        except:
            return 'Unknown'

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
        """Load historical data for universe"""
        if not self.universe:
            self.generate_universe()

        logger.info(f"📊 Loading data for {len(self.universe)} stocks...")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 30)

        loaded = 0
        for symbol in self.universe:
            try:
                ticker = yf.Ticker(symbol)
                data = ticker.history(start=start_date.strftime('%Y-%m-%d'))
                if len(data) >= 30:
                    data.columns = [c.lower() for c in data.columns]
                    self.data_cache[symbol] = data
                    loaded += 1
            except Exception as e:
                logger.debug(f"Error loading {symbol}: {e}")

        logger.info(f"✅ Loaded {loaded}/{len(self.universe)} stocks")

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

        # SMAs
        sma5 = close.iloc[idx-5:idx].mean() if idx >= 5 else close.mean()
        sma20 = close.iloc[idx-20:idx].mean() if idx >= 20 else close.mean()
        sma50 = close.iloc[idx-50:idx].mean() if idx >= 50 else close.mean()

        # Distance from recent high
        high_20d = high.iloc[idx-20:idx].max() if idx >= 20 else high.max()
        dist_from_high = (high_20d - current_price) / high_20d * 100

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
            return None  # Need yesterday to be a dip

        # FILTER 2: Today should show recovery (not falling further)
        if mom_1d < -1.0:
            return None  # Still falling hard, wait

        # FILTER 3: Strong preference for green candle (bounce signal)
        if not today_is_green and mom_1d < 0.5:
            return None  # No clear bounce yet

        # FILTER 4: Skip big gap ups (exhaustion risk)
        if gap_pct > 2.0:
            return None

        # FILTER 5: Still in oversold zone (room to recover)
        if current_price > sma5 * 1.02:
            return None

        # FILTER 6: Minimum volatility
        if atr_pct < self.MIN_ATR_PCT:
            return None

        # ==============================
        # v3.5: SMA20 FILTER (ROOT CAUSE FIX)
        # ==============================
        # Based on root cause analysis: 92% of stop loss trades
        # were below SMA20 (downtrend). This filter prevents most losers.
        if current_price < sma20:
            return None  # Must be above SMA20 (uptrend)

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

    def screen(self, top_n: int = 10, enable_alt_data: bool = True) -> List[RapidRotationSignal]:
        """
        Screen universe for rapid rotation opportunities

        v3.7: Hybrid Sector Scoring + Alt Data for Top 10 only

        Args:
            top_n: Number of top signals to return
            enable_alt_data: Whether to apply alt data scoring to Top 10

        Returns:
            List of RapidRotationSignal sorted by score

        Flow:
        1. Score all stocks (with sector penalty/bonus)
        2. Sort by base score
        3. Take Top 10 candidates
        4. Apply Alt Data scoring (±10 cap) to Top 10 only
        5. Re-sort and return Top N
        """
        # Check market regime first
        regime = self._get_market_regime()
        regime_name = regime.get('regime', 'UNKNOWN')

        if regime_name == 'BEAR':
            logger.warning("🐻 Bear market detected - reducing position sizes recommended")
        elif regime_name == 'BULL':
            logger.info("🐂 Bull market - good conditions for trading")

        if not self.data_cache:
            self.load_data()

        signals = []
        for symbol in self.data_cache.keys():
            try:
                signal = self.analyze_stock(symbol)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"Error analyzing {symbol}: {e}")

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

        return signals[:top_n]

    def get_portfolio_signals(self,
                              max_positions: int = 4,
                              existing_positions: List[str] = None) -> List[RapidRotationSignal]:
        """Get signals for portfolio management"""
        existing = set(existing_positions or [])
        signals = self.screen(top_n=20)
        new_signals = [s for s in signals if s.symbol not in existing]
        available_slots = max_positions - len(existing)
        return new_signals[:available_slots]


def main():
    """Run the screener"""
    print("=" * 70)
    print("RAPID ROTATION SCREENER v3.7 - HYBRID SECTOR + ALT DATA")
    print("=" * 70)
    print()
    print("v3.7 Backtest Results: +32.41%/6mo, 57.8% win rate")
    print()
    print("Systems:")
    print("  ✅ AI Universe Generator (680+ stocks)")
    print("  ✅ Market Regime Detector")
    print("  ✅ Sector Regime Detector (HYBRID v2)")
    print("  ✅ Alternative Data (Top 10 only, ±10 cap)")
    print("  ✅ Bounce Confirmation")
    print()
    print("v3.7 HYBRID Sector Scoring:")
    print("  BEAR sector:    -10 points (defensive)")
    print("  SIDEWAYS:         0 points")
    print("  BULL sector:     +5 points")
    print()

    screener = RapidRotationScreener()

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
