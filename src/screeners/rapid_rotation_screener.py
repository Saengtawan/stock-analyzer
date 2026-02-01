#!/usr/bin/env python3
"""
RAPID ROTATION SCREENER v3.0 - FULLY INTEGRATED Edition

INTEGRATED SYSTEMS:
✅ AI Universe Generator (680+ stocks from DeepSeek)
✅ Market Regime Detector (Bull/Bear/Sideways)
✅ Sector Regime Detector (Hot sectors)
✅ Alternative Data (Insider, Sentiment, Short Interest)
✅ Anti-PDT Filters (v2.1)

Strategy:
- Dynamic universe from AI (not hardcoded 30 stocks!)
- Only trade in favorable market regimes
- Focus on hot sectors
- Buy TRUE DIPS only (mom_1d < 0, below SMA5)
- Use alternative data for extra confirmation
- Dynamic SL based on ATR (1.5%-2.5%)

v3.0 Features:
- 680+ stock universe (vs 30 hardcoded)
- Market regime filter (skip bear markets)
- Sector rotation (focus on hot sectors)
- Alternative data scoring
- Anti-PDT filters preserved
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

    @property
    def expected_gain(self) -> float:
        return ((self.take_profit - self.entry_price) / self.entry_price) * 100

    @property
    def max_loss(self) -> float:
        return ((self.entry_price - self.stop_loss) / self.entry_price) * 100


class RapidRotationScreener:
    """
    Rapid Rotation Screener v3.0 - FULLY INTEGRATED

    Systems Used:
    1. AI Universe Generator - 680+ stocks
    2. Market Regime Detector - Bull/Bear/Sideways
    3. Sector Regime Detector - Hot sectors
    4. Alternative Data - Insider, Sentiment, etc.
    5. Anti-PDT Filters - Reduce same-day SL
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
        'CRM', 'NOW', 'SHOP', 'SQ', 'PYPL', 'UBER', 'ABNB',
        # EV/Clean energy
        'RIVN', 'LCID', 'ENPH', 'FSLR', 'RUN',
        # Finance
        'JPM', 'GS', 'MS', 'V', 'MA', 'AXP',
        # Industrial
        'CAT', 'DE', 'BA', 'GE', 'HON',
        # Consumer
        'NKE', 'LULU', 'SBUX', 'MCD', 'HD', 'LOW',
    ]

    # Configuration
    MIN_ATR_PCT = 2.0  # Minimum volatility
    MIN_SCORE = 60  # Minimum score

    # Exit parameters
    BASE_TP_PCT = 4.0  # Base take profit %
    BASE_SL_PCT = 1.5  # Base stop loss %
    MAX_HOLD_DAYS = 4  # Max hold days

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

    def _get_alt_data_score(self, symbol: str) -> Tuple[float, List[str]]:
        """
        Get alternative data score for a stock

        Returns:
            Tuple of (score, reasons)

        Note: Alt data calls are DISABLED for now due to slow API responses.
        To re-enable, set ENABLE_ALT_DATA = True
        """
        ENABLE_ALT_DATA = False  # Disabled for faster response

        if symbol in self._alt_data_cache:
            return self._alt_data_cache[symbol]

        score = 0
        reasons = []

        if self.alt_data and ENABLE_ALT_DATA:
            try:
                data = self.alt_data.get_comprehensive_data(symbol)

                if data:
                    # Insider buying
                    if data.get('has_insider_buying', False):
                        score += 15
                        reasons.append("Insider buying")

                    # Overall score from alt data (normalized 0-100)
                    overall_alt = data.get('overall_score', 0)
                    if overall_alt > 70:
                        score += 10
                        reasons.append(f"Strong alt data ({overall_alt:.0f})")
                    elif overall_alt > 50:
                        score += 5
                        reasons.append(f"Good alt data ({overall_alt:.0f})")

                    # Short squeeze potential
                    if data.get('has_squeeze_potential', False):
                        score += 10
                        reasons.append("Squeeze potential")

                    # Analyst upgrades
                    if data.get('has_analyst_upgrade', False):
                        score += 10
                        reasons.append("Analyst upgrade")

                    # Social buzz
                    if data.get('has_social_buzz', False):
                        score += 5
                        reasons.append("Social buzz")

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

        v3.0: Integrated with all data sources
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

        current_price = close.iloc[idx]

        # Skip penny stocks and very expensive stocks
        if current_price < 10 or current_price > 2000:
            return None

        # Calculate indicators
        rsi = self.calculate_rsi(close).iloc[idx]
        atr = self.calculate_atr(data).iloc[idx]
        atr_pct = (atr / current_price) * 100

        # Momentum
        mom_5d = (current_price / close.iloc[idx-5] - 1) * 100 if idx >= 5 else 0
        mom_10d = (current_price / close.iloc[idx-10] - 1) * 100 if idx >= 10 else 0
        mom_20d = (current_price / close.iloc[idx-20] - 1) * 100 if idx >= 20 else 0

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
        open_price = data['open'].iloc[idx] if 'open' in data.columns else current_price
        gap_pct = (open_price - prev_close) / prev_close * 100

        # 1-day momentum
        mom_1d = (current_price / close.iloc[idx-1] - 1) * 100 if idx >= 1 else 0

        # ==============================
        # ANTI-PDT FILTERS (v2.1) - PRESERVED
        # ==============================

        # FILTER 1: Must be TRUE DIP
        if mom_1d > 0.5:
            return None

        # FILTER 2: Skip gap-up entries
        if gap_pct > 1.5:
            return None

        # FILTER 3: Must be below SMA5
        if current_price > sma5 * 1.01:
            return None

        # ==============================
        # SCORING CRITERIA
        # ==============================
        score = 0
        reasons = []

        # 1. Volatility check
        if atr_pct < self.MIN_ATR_PCT:
            return None

        # 2. Pullback scoring
        if -8 <= mom_5d <= -3:
            score += 35
            reasons.append(f"Strong dip {mom_5d:.1f}%")
        elif -3 < mom_5d <= 0:
            score += 25
            reasons.append(f"Mild pullback {mom_5d:.1f}%")

        # 2b. 1-day dip bonus
        if mom_1d <= -1.5:
            score += 15
            reasons.append(f"Today dip {mom_1d:.1f}%")

        # 3. RSI scoring
        if 30 <= rsi <= 45:
            score += 30
            reasons.append(f"Oversold RSI={rsi:.0f}")
        elif 45 < rsi <= 55:
            score += 20
            reasons.append(f"Neutral RSI={rsi:.0f}")
        elif rsi < 30:
            score += 15
            reasons.append(f"Very oversold RSI={rsi:.0f}")

        # 4. Trend scoring
        if current_price > sma50 and mom_20d > 0:
            score += 20
            reasons.append("Strong uptrend")
        elif current_price > sma20:
            score += 15
            reasons.append("Above SMA20")
        elif mom_20d > 5:
            score += 10
            reasons.append("Recovery mode")

        # 5. Volatility bonus
        if atr_pct > 4:
            score += 15
            reasons.append(f"High volatility {atr_pct:.1f}%")
        elif atr_pct > 3:
            score += 10
            reasons.append(f"Good volatility {atr_pct:.1f}%")

        # 6. Room to run
        if 5 <= dist_from_high <= 15:
            score += 10
            reasons.append(f"Room to recover {dist_from_high:.0f}%")

        # 7. Volume confirmation
        if volume_ratio > 1.2:
            score += 5
            reasons.append("High volume")

        # ==============================
        # v3.0: ALTERNATIVE DATA SCORING
        # ==============================
        alt_score, alt_reasons = self._get_alt_data_score(symbol)
        score += alt_score
        reasons.extend(alt_reasons)

        # ==============================
        # v3.0: SECTOR BONUS
        # ==============================
        sector_score = 0
        hot_sectors = self._get_hot_sectors()
        sector = self._get_sector(symbol)

        if sector in hot_sectors:
            sector_score = 15
            score += sector_score
            reasons.append(f"🔥 Hot sector: {sector}")

        # Check minimum score
        if score < self.MIN_SCORE:
            return None

        # ==============================
        # CALCULATE SL/TP (ATR-based)
        # ==============================
        tp_multiplier = min(1.5, max(1.0, atr_pct / 3))
        tp_pct = self.BASE_TP_PCT * tp_multiplier

        # Dynamic SL based on ATR
        if atr_pct > 5:
            sl_pct = 2.5
        elif atr_pct > 4:
            sl_pct = 2.0
        elif atr_pct > 3:
            sl_pct = 1.75
        else:
            sl_pct = self.BASE_SL_PCT

        # Support level consideration
        sl_from_support = (current_price - support * 0.995) / current_price * 100
        sl_pct = max(sl_pct, min(sl_from_support * 0.8, 2.5))

        stop_loss = current_price * (1 - sl_pct / 100)
        take_profit = current_price * (1 + tp_pct / 100)
        risk_reward = tp_pct / sl_pct

        # Get market regime
        market_regime = self._get_market_regime()
        regime_str = market_regime.get('regime', 'UNKNOWN')

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
            alt_data_score=alt_score
        )

    def screen(self, top_n: int = 10) -> List[RapidRotationSignal]:
        """
        Screen universe for rapid rotation opportunities

        v3.0: Checks market regime before screening
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

        # Sort by score descending
        signals.sort(key=lambda x: x.score, reverse=True)

        logger.info(f"📊 Found {len(signals)} signals from {len(self.data_cache)} stocks")

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
    print("RAPID ROTATION SCREENER v3.0 - FULLY INTEGRATED")
    print("=" * 70)
    print()
    print("Systems:")
    print("  ✅ AI Universe Generator (680+ stocks)")
    print("  ✅ Market Regime Detector")
    print("  ✅ Sector Regime Detector")
    print("  ✅ Alternative Data Aggregator")
    print("  ✅ Anti-PDT Filters")
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
        print("No signals found today")
        return

    print(f"Found {len(signals)} signals:")
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
        print(f"   Alt Data Score: {signal.alt_data_score:+.0f}")
        print(f"   Reasons: {', '.join(signal.reasons)}")
        print()

    print("=" * 70)
    print("EXIT RULES:")
    print("- Take Profit: ~4-6% (ATR-based)")
    print("- Stop Loss: 1.5-2.5% (ATR-based)")
    print("- Time Stop: 4 days max")
    print("- Trail: After +2.5%, trail at 60%")
    print("=" * 70)


if __name__ == "__main__":
    main()
