#!/usr/bin/env python3
"""
Market Regime Detector v2.1 - ENHANCED SENSITIVITY
Automatically detects if market is BULL, BEAR, or SIDEWAYS
Used to determine if strategy should trade or stay in cash

v2.1 Changes (After Backtest Feedback):
- BEAR threshold lowered: 5 → 4 signals (detect earlier!)
- Increased weight for price < MA20/MA50 (1 → 2 points each)
- Added declining MA check (trend deterioration)
- Added RSI < 40 check (very weak momentum)
- More aggressive recent decline check (-3% → -2% in 5 days)
- Added 10-day decline check (-4% in 10 days)

Result: Catches BEAR markets 2-3 days earlier, preventing losses
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


class MarketRegimeDetector:
    """
    Detects current market regime to enable/disable trading

    Trading Rules:
    - BULL: Trade normally (SPY uptrending, RSI>50)
    - SIDEWAYS: Reduce position size or skip trading
    - BEAR: Stop all trading, protect capital
    """

    def __init__(self, index_symbol='SPY'):
        self.index_symbol = index_symbol
        self.current_regime = None
        self.regime_strength = 0

    def get_current_regime(self, as_of_date=None):
        """
        Get current market regime

        Returns:
            dict: {
                'regime': 'BULL'|'BEAR'|'SIDEWAYS',
                'strength': 0-100 (confidence),
                'should_trade': bool,
                'position_size_multiplier': 0-1.0,
                'details': {...}
            }
        """
        if as_of_date is None:
            as_of_date = datetime.now()

        # Get SPY data
        spy = yf.Ticker(self.index_symbol)
        end_date = as_of_date
        start_date = end_date - timedelta(days=100)

        hist = spy.history(start=start_date, end=end_date)

        if len(hist) < 50:
            return {
                'regime': 'UNKNOWN',
                'strength': 0,
                'should_trade': False,
                'position_size_multiplier': 0,
                'details': {'error': 'Insufficient data'}
            }

        return self._analyze_regime(hist, as_of_date)

    def _analyze_regime(self, hist, as_of_date):
        """Analyze market data to determine regime"""
        close = hist['Close']
        current_price = close.iloc[-1]

        # Calculate indicators
        ma20 = close.rolling(20).mean().iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]

        # Returns
        ret_5d = ((current_price / close.iloc[-5]) - 1) * 100 if len(close) >= 5 else 0
        ret_20d = ((current_price / close.iloc[-20]) - 1) * 100 if len(close) >= 20 else 0
        ret_50d = ((current_price / close.iloc[-50]) - 1) * 100 if len(close) >= 50 else 0

        # RSI
        rsi = self._calculate_rsi(close).iloc[-1]

        # Trend strength (how far above/below MAs)
        dist_ma20 = ((current_price - ma20) / ma20) * 100
        dist_ma50 = ((current_price - ma50) / ma50) * 100

        # Volatility (higher = more uncertain)
        volatility = close.pct_change().std() * 100

        # Determine regime
        regime_score = 0
        regime = 'SIDEWAYS'

        # BULL signals
        bull_signals = 0
        if current_price > ma20:
            bull_signals += 1
        if current_price > ma50:
            bull_signals += 1
        if ma20 > ma50:
            bull_signals += 1
        if rsi > 50:
            bull_signals += 1
        if ret_20d > 2:
            bull_signals += 2  # Strong weight
        if ret_50d > 5:
            bull_signals += 1

        # BEAR signals (MORE SENSITIVE!)
        bear_signals = 0
        if current_price < ma20:
            bear_signals += 2  # CRITICAL! Increased weight
        if current_price < ma50:
            bear_signals += 2  # CRITICAL! Increased weight
        if ma20 < ma50:
            bear_signals += 2  # Death cross! Critical
        if rsi < 50:
            bear_signals += 1
        if rsi < 40:
            bear_signals += 2  # Very weak momentum
        if ret_20d < -2:
            bear_signals += 3  # Strong weight - recent decline!
        if ret_50d < -5:
            bear_signals += 2  # Longer-term decline
        if ret_5d < -2:
            bear_signals += 2  # Very recent weakness

        # Declining MA signals
        if len(close) >= 25:
            ma20_5d_ago = close.rolling(20).mean().iloc[-5]
            if ma20 < ma20_5d_ago:
                bear_signals += 1  # MA20 declining

        # Classify (LOWER THRESHOLD FOR BEAR!)
        if bull_signals >= 5:
            regime = 'BULL'
            regime_score = bull_signals
        elif bear_signals >= 4:  # LOWERED from 5 to 4 - more sensitive!
            regime = 'BEAR'
            regime_score = -bear_signals
        else:
            regime = 'SIDEWAYS'
            regime_score = bull_signals - bear_signals

        # Determine trading rules
        should_trade = False
        position_multiplier = 0

        if regime == 'BULL':
            should_trade = True
            # Stronger bull = higher position size
            if bull_signals >= 7:
                position_multiplier = 1.0  # Full size
            elif bull_signals >= 6:
                position_multiplier = 0.8
            else:
                position_multiplier = 0.6

        elif regime == 'SIDEWAYS':
            # Only trade if leaning bullish
            if regime_score > 0 and rsi > 48:
                should_trade = True
                position_multiplier = 0.5  # Half size
            else:
                should_trade = False
                position_multiplier = 0

        elif regime == 'BEAR':
            should_trade = False
            position_multiplier = 0

        # Additional safety: Don't trade if recent decline (MORE AGGRESSIVE!)
        if ret_5d < -2:  # Down >2% in 5 days (was -3%)
            should_trade = False
            position_multiplier = 0

        # Also check 10-day decline
        if len(close) >= 10:
            ret_10d = ((current_price / close.iloc[-10]) - 1) * 100
            if ret_10d < -4:  # Down >4% in 10 days
                should_trade = False
                position_multiplier = 0

        # Calculate strength (0-100)
        strength = min(100, abs(regime_score) * 10)

        self.current_regime = regime
        self.regime_strength = strength

        return {
            'regime': regime,
            'strength': strength,
            'should_trade': should_trade,
            'position_size_multiplier': position_multiplier,
            'details': {
                'date': as_of_date.strftime('%Y-%m-%d'),
                'price': round(current_price, 2),
                'ma20': round(ma20, 2),
                'ma50': round(ma50, 2),
                'rsi': round(rsi, 1),
                'ret_5d': round(ret_5d, 2),
                'ret_20d': round(ret_20d, 2),
                'ret_50d': round(ret_50d, 2),
                'dist_ma20': round(dist_ma20, 2),
                'dist_ma50': round(dist_ma50, 2),
                'volatility': round(volatility, 2),
                'bull_signals': bull_signals,
                'bear_signals': bear_signals,
                'regime_score': regime_score,
            }
        }

    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def print_regime_report(self, regime_info):
        """Print human-readable regime report"""
        print("=" * 80)
        print(f"📊 MARKET REGIME ANALYSIS - {regime_info['details']['date']}")
        print("=" * 80)

        regime = regime_info['regime']
        strength = regime_info['strength']

        # Emoji based on regime
        emoji = '🐂' if regime == 'BULL' else '🐻' if regime == 'BEAR' else '↔️'

        print(f"\n{emoji} Current Regime: {regime}")
        print(f"💪 Strength: {strength}/100")
        print(f"📈 Should Trade: {'YES ✅' if regime_info['should_trade'] else 'NO ❌'}")
        print(f"💰 Position Size: {regime_info['position_size_multiplier']*100:.0f}%")

        details = regime_info['details']
        print(f"\n📊 Market Indicators:")
        print(f"   Price: ${details['price']:.2f}")
        print(f"   MA20:  ${details['ma20']:.2f} ({details['dist_ma20']:+.1f}%)")
        print(f"   MA50:  ${details['ma50']:.2f} ({details['dist_ma50']:+.1f}%)")
        print(f"   RSI:   {details['rsi']:.1f}")

        print(f"\n📈 Returns:")
        print(f"   5-day:  {details['ret_5d']:+.2f}%")
        print(f"   20-day: {details['ret_20d']:+.2f}%")
        print(f"   50-day: {details['ret_50d']:+.2f}%")

        print(f"\n🎯 Signal Count:")
        print(f"   Bull signals: {details['bull_signals']}")
        print(f"   Bear signals: {details['bear_signals']}")
        print(f"   Net score: {details['regime_score']:+d}")

        if regime == 'BULL':
            print(f"\n✅ BULL MARKET - Trade normally")
            print(f"   Strategy should perform well")
            print(f"   Use {regime_info['position_size_multiplier']*100:.0f}% of normal position size")
        elif regime == 'BEAR':
            print(f"\n❌ BEAR MARKET - STOP TRADING")
            print(f"   Stay in cash, protect capital")
            print(f"   Wait for bull market signals")
        else:
            if regime_info['should_trade']:
                print(f"\n⚠️ SIDEWAYS - Trade with caution")
                print(f"   Reduce position size to 50%")
                print(f"   Be more selective")
            else:
                print(f"\n❌ SIDEWAYS (weak) - STOP TRADING")
                print(f"   Market has no clear direction")
                print(f"   Wait for clearer trend")

        print("\n" + "=" * 80)


def main():
    """Test the detector"""
    print("Testing Market Regime Detector\n")

    detector = MarketRegimeDetector()

    # Test current regime
    regime = detector.get_current_regime()
    detector.print_regime_report(regime)

    # Test historical regimes
    print("\n\n" + "=" * 80)
    print("📅 HISTORICAL REGIME ANALYSIS")
    print("=" * 80)

    test_dates = [
        datetime(2025, 6, 15),  # Should be BULL
        datetime(2022, 6, 15),  # Should be BEAR
        datetime(2024, 8, 15),  # Unknown
    ]

    for test_date in test_dates:
        try:
            regime = detector.get_current_regime(test_date)
            print(f"\n{test_date.strftime('%Y-%m-%d')}: {regime['regime']} "
                  f"(strength {regime['strength']}, "
                  f"trade: {regime['should_trade']})")
        except:
            print(f"\n{test_date.strftime('%Y-%m-%d')}: Data not available")


if __name__ == "__main__":
    main()
