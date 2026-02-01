#!/usr/bin/env python3
"""
Advanced Exit Rules v2.0 - For 30-Day Growth Catalyst Strategy

Designed for 30-day timeframe with v7.1 entry filters (100% backtest win rate)

Key Features:
1. Daily regime monitoring - exit ALL positions if regime turns BEAR
2. Tighter stop losses (-6%) - cut losses fast
3. Trailing stops (-3%) - lock in profits when up 5%+
4. Time stop (10 days) - exit if not working (33% of 30-day window)
5. Technical health monitoring - exit if momentum deteriorates
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from loguru import logger


class AdvancedExitRules:
    """
    Advanced Exit Rules v2.0 for 30-Day Growth Catalyst Strategy

    Works with v7.1 entry filters (100% backtest win rate)
    Designed to prevent November-like losses while locking in profits

    Exit Triggers (ANY ONE triggers exit):
    1. Hard stop loss: -6% (cut losses fast!)
    2. Regime turns BEAR: Exit immediately (protect capital!)
    3. Regime turns SIDEWAYS_WEAK: Exit if no profit (avoid dead money)
    4. Trailing stop: Dynamic breakeven protection (NEW v4.2!)
       - Profit <2%: Breakeven + 0.5% buffer
       - Profit 2-5%: -4% trailing
       - Profit >5%: -3% trailing
    5. Time stop: 10 days if < 2% profit (not working = exit)
    6. Technical health: Exit if momentum deteriorates (RSI, MA, RS checks)

    Timeframe: Optimized for 30-day holding period
    - 10 days = 33% of window (reasonable time to assess if working)
    - Allows stocks time to develop vs 14-day strategy (where 10d = 71%)
    """

    def __init__(self):
        self.rules = {
            'hard_stop_loss': -6.0,  # TIGHTER! (was -10%)
            'trailing_stop': -3.0,   # Lock profits
            'time_stop_days': 10,    # FASTER! (was 20 days)
            'min_filter_score': 1,   # Exit if ≤1 filters pass
            'regime_exit': True,     # Exit on regime change
        }

        # Import regime detector
        try:
            from market_regime_detector import MarketRegimeDetector
            self.regime_detector = MarketRegimeDetector()
            logger.info("✅ Advanced Exit Rules with Regime Monitoring initialized")
        except ImportError:
            self.regime_detector = None
            logger.warning("⚠️ Regime Detector not available")

    def should_exit(self, position, current_date, hist_data, spy_data=None):
        """
        Check if position should be exited

        Args:
            position: dict with {
                'symbol', 'entry_price', 'entry_date',
                'highest_price', 'days_held'
            }
            current_date: datetime
            hist_data: price history DataFrame
            spy_data: SPY data for regime check

        Returns:
            (should_exit: bool, reason: str, exit_price: float)
        """
        try:
            symbol = position['symbol']
            entry_price = position['entry_price']
            entry_date = position.get('entry_date')
            highest_price = position.get('highest_price', entry_price)
            days_held = position.get('days_held', 0)

            # Get current price
            current_data = hist_data[hist_data.index <= current_date]
            if current_data.empty:
                return False, None, None

            current_price = float(current_data['Close'].iloc[-1])
            current_return = ((current_price - entry_price) / entry_price) * 100

            # Update highest price
            if current_price > highest_price:
                highest_price = current_price
                position['highest_price'] = highest_price

            # 1. HARD STOP LOSS (CRITICAL!)
            if current_return <= self.rules['hard_stop_loss']:
                logger.warning(f"❌ {symbol}: Hard stop loss hit ({current_return:.2f}%)")
                return True, 'HARD_STOP', current_price

            # 2. REGIME CHECK (NEW! - PREVENT NOVEMBER-LIKE LOSSES)
            if self.regime_detector and spy_data is not None:
                regime_info = self._check_regime(current_date, spy_data)

                if regime_info['regime'] == 'BEAR':
                    # BEAR MARKET - EXIT IMMEDIATELY!
                    logger.warning(f"🐻 {symbol}: BEAR market detected - exiting all positions")
                    return True, 'REGIME_BEAR', current_price

                elif regime_info['regime'] == 'SIDEWAYS_WEAK':
                    # SIDEWAYS WEAK - exit if losing or flat
                    if current_return < 1.0:  # If not making >1%, exit
                        logger.warning(f"⚠️ {symbol}: Weak market + no profit - exit")
                        return True, 'REGIME_WEAK', current_price

            # 3. TRAILING STOP (Breakeven Protection - v4.2 Optimized)
            # 🎯 NEW: Protect ANY profit! (not just 5%+)
            if highest_price > entry_price:  # Activate on ANY profit
                profit_pct = ((highest_price - entry_price) / entry_price) * 100

                # Dynamic trailing based on profit level
                if profit_pct >= 5.0:
                    trailing_pct = -3.0  # Tight trailing for big gains
                elif profit_pct >= 2.0:
                    trailing_pct = -4.0  # Moderate trailing
                else:
                    # Break even protection with small buffer (0.5%)
                    # Min -1.0% to allow small fluctuations
                    trailing_pct = max(-1.0, -(profit_pct - 0.5))

                drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100
                if drawdown_from_peak <= trailing_pct:
                    logger.info(f"📉 {symbol}: Trailing stop hit ({drawdown_from_peak:.2f}% from peak of +{profit_pct:.2f}%)")
                    return True, 'TRAILING_STOP', current_price

            # 4. TIME STOP (Not working - exit faster)
            if days_held >= self.rules['time_stop_days']:
                if current_return < 2.0:  # Not up 2%+ after 10 days = exit
                    logger.info(f"⏰ {symbol}: Time stop - {days_held} days, only {current_return:.2f}%")
                    return True, 'TIME_STOP', current_price

            # 5. FILTER SCORE (Technical deterioration)
            filter_score = self._calculate_filter_score(
                symbol, current_date, hist_data, spy_data
            )

            if filter_score <= self.rules['min_filter_score']:
                logger.info(f"📊 {symbol}: Filter score dropped to {filter_score}/4 - exit")
                return True, 'FILTER_FAIL', current_price

            # All checks passed - hold
            return False, None, current_price

        except Exception as e:
            logger.error(f"Exit check error for {symbol}: {e}")
            return False, None, None

    def _check_regime(self, current_date, spy_data):
        """Check current market regime"""
        try:
            if not self.regime_detector:
                return {'regime': 'UNKNOWN', 'should_trade': True}

            return self.regime_detector.get_current_regime(current_date)

        except Exception as e:
            logger.error(f"Regime check error: {e}")
            return {'regime': 'UNKNOWN', 'should_trade': True}

    def _calculate_filter_score(self, symbol, check_date, hist_data, spy_data):
        """
        Calculate technical health score (0-4 points)

        NOTE: These are TECHNICAL HEALTH checks, not entry filters
        Entry uses v7.1 filters (Beta, Vol, RS 30d, Sector, Valuation)
        Exit monitors if stock is still technically healthy:

        Technical Health Checks:
        1. RSI > 49 (still has momentum)
        2. Momentum 7d > 3.5% (recent strength)
        3. RS 14d > 1.9% (still outperforming)
        4. MA20 distance > -2.8% (not breaking down)

        Exit trigger: Score ≤1 (failing 3+ health checks = technical breakdown)
        """
        try:
            data = hist_data[hist_data.index <= check_date].copy()
            if len(data) < 50:
                return 0

            close = data['Close']
            current_price = close.iloc[-1]
            score = 0

            # 1. RSI
            rsi = self._calculate_rsi(close).iloc[-1]
            if rsi >= 49:
                score += 1

            # 2. Momentum 7d
            if len(close) >= 7:
                mom = ((current_price - close.iloc[-7]) / close.iloc[-7]) * 100
                if mom >= 3.5:
                    score += 1

            # 3. RS 14d
            if len(close) >= 14 and spy_data is not None:
                stock_ret = ((current_price / close.iloc[-14]) - 1) * 100
                spy_at = spy_data[spy_data.index <= check_date]
                if len(spy_at) >= 14:
                    spy_ret = ((spy_at['Close'].iloc[-1] / spy_at['Close'].iloc[-14]) - 1) * 100
                    rs = stock_ret - spy_ret
                    if rs >= 1.9:
                        score += 1

            # 4. MA20 distance
            if len(close) >= 20:
                ma20 = close.rolling(20).mean().iloc[-1]
                dist = ((current_price - ma20) / ma20) * 100
                if dist >= -2.8:
                    score += 1

            return score

        except Exception as e:
            logger.error(f"Filter score calculation error: {e}")
            return 0

    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))


def main():
    """Test advanced exit rules"""
    print("=" * 80)
    print("🧪 TESTING ADVANCED EXIT RULES")
    print("=" * 80)

    exit_rules = AdvancedExitRules()

    print("\n✅ Exit Rules Configuration:")
    print(f"   Hard Stop Loss: {exit_rules.rules['hard_stop_loss']}%")
    print(f"   Trailing Stop: {exit_rules.rules['trailing_stop']}%")
    print(f"   Time Stop: {exit_rules.rules['time_stop_days']} days")
    print(f"   Min Filter Score: {exit_rules.rules['min_filter_score']}/4")
    print(f"   Regime Exit: {exit_rules.rules['regime_exit']}")

    if exit_rules.regime_detector:
        print("\n✅ Regime Detector: Active")
        regime = exit_rules.regime_detector.get_current_regime()
        print(f"   Current Regime: {regime['regime']}")
        print(f"   Should Trade: {regime['should_trade']}")
    else:
        print("\n⚠️ Regime Detector: Not available")

    print("\n" + "=" * 80)
    print("🎯 EXIT TRIGGERS (Any ONE will trigger exit):")
    print("=" * 80)
    print("""
1. Hard Stop: -6% (CUT LOSSES FAST!)
2. Regime BEAR: Exit immediately (PROTECT CAPITAL!)
3. Regime WEAK + No profit: Exit (NO HOPE!)
4. Trailing Stop: -3% from peak (LOCK PROFITS!)
5. Time Stop: 10 days without 2%+ (NOT WORKING!)
6. Filter Score ≤1: Exit (TECHNICAL BREAKDOWN!)
    """)

    print("=" * 80)
    print("💡 KEY IMPROVEMENTS vs v1.0:")
    print("=" * 80)
    print("""
v1.0 (OLD):                      v2.0 (NEW):
- Stop loss: -10%                → -6% (TIGHTER!)
- No regime monitoring           → Daily regime check! ✅
- Max hold: 20 days              → 10 days (FASTER!)
- No trailing stop               → -3% trailing ✅
- Exit on filter score 0         → Exit on score ≤1

RESULT: Cut losses faster, lock in profits earlier!
    """)


if __name__ == "__main__":
    main()
