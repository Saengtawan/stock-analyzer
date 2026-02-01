#!/usr/bin/env python3
"""
Momentum-Based Growth Screener v1.0
===================================

Based on analysis showing that MOMENTUM & TREND are the real predictors,
NOT composite scores!

Key Filters (from Winners vs Losers analysis):
1. RSI 40-60 (healthy momentum, not oversold)
2. Price > MA20 (short-term uptrend)
3. Price > MA50 (long-term uptrend)
4. Momentum 10d > 0% (positive recent movement)
5. Momentum 30d > 10% (strong trend)

This replaces the failed composite score approach.
"""

from typing import List, Dict, Any
import pandas as pd
import numpy as np
from loguru import logger
from datetime import datetime, timedelta


class MomentumGrowthScreener:
    """
    Momentum-based screener that uses PROVEN filters

    Filters based on actual performance analysis:
    - Winners had RSI ~48 vs Losers ~27
    - Winners were +12% above MA50 vs Losers -5%
    - Winners had +8% momentum 10d vs Losers -3%
    - Winners had +22% momentum 30d vs Losers +5%
    """

    def __init__(self, stock_analyzer):
        self.analyzer = stock_analyzer
        logger.info("✅ Momentum Growth Screener v1.0 initialized")
        logger.info("   Using momentum & trend filters (NOT composite scores)")

    def screen_opportunities(self,
                           min_rsi: float = 40.0,          # Winners had 48
                           max_rsi: float = 70.0,          # Not overbought
                           min_price_above_ma20: float = 0.0,  # Must be above MA20
                           min_price_above_ma50: float = 0.0,  # Must be above MA50
                           min_momentum_10d: float = 0.0,      # Must be rising
                           min_momentum_30d: float = 10.0,     # Strong trend
                           min_market_cap: float = 1_000_000_000,  # $1B min
                           min_price: float = 5.0,
                           max_price: float = 500.0,
                           min_volume: float = 500_000,
                           max_stocks: int = 20,
                           universe_size: int = 100) -> List[Dict[str, Any]]:
        """
        Screen for momentum-based growth opportunities

        Args:
            min_rsi: Minimum RSI (40 = not oversold)
            max_rsi: Maximum RSI (70 = not overbought)
            min_price_above_ma20: Min % above MA20 (0 = must be above)
            min_price_above_ma50: Min % above MA50 (0 = must be above)
            min_momentum_10d: Min 10-day momentum % (0 = must be positive)
            min_momentum_30d: Min 30-day momentum % (10 = strong trend)
            min_market_cap: Minimum market cap
            min_price: Minimum stock price
            max_price: Maximum stock price
            min_volume: Minimum average volume
            max_stocks: Maximum stocks to return
            universe_size: Size of initial universe

        Returns:
            List of opportunities with momentum scores
        """

        logger.info("🎯 Starting Momentum-Based Growth Screening v1.0")
        logger.info(f"   Filters: RSI {min_rsi}-{max_rsi}, Mom10d>{min_momentum_10d}%, Mom30d>{min_momentum_30d}%")

        opportunities = []

        # Generate universe (reuse from growth catalyst screener)
        from ai_universe_generator import AIUniverseGenerator

        universe_gen = AIUniverseGenerator()
        logger.info(f"\n📋 Generating universe of {universe_size} stocks...")

        universe = universe_gen.generate_growth_catalyst_universe(
            criteria={
                'target_gain_pct': 10.0,
                'timeframe_days': 30,
                'max_stocks': max_stocks,
                'universe_multiplier': universe_size // max_stocks
            }
        )

        if not universe:
            logger.warning("❌ Failed to generate universe")
            return []

        logger.info(f"✅ Generated {len(universe)} stocks")

        # Screen each stock
        logger.info(f"\n🔍 Screening {len(universe)} stocks...")

        analyzed = 0
        passed = 0

        for symbol in universe:
            try:
                analyzed += 1

                # Get price data
                price_data = self.analyzer.data_manager.get_price_data(symbol, period='3mo')

                if price_data is None or price_data.empty:
                    continue

                # Get basic info
                info = self.analyzer.data_manager.get_stock_info(symbol)
                if not info:
                    continue

                current_price = float(price_data['Close'].iloc[-1])
                market_cap = info.get('marketCap', 0)
                sector = info.get('sector', 'Unknown')

                # Filter by price and market cap
                if current_price < min_price or current_price > max_price:
                    continue

                if market_cap < min_market_cap:
                    continue

                # Calculate volume
                avg_volume = float(price_data['Volume'].tail(20).mean())
                if avg_volume < min_volume:
                    continue

                # Calculate momentum indicators
                close = price_data['Close']

                # RSI
                rsi = self._calculate_rsi(close)
                if rsi is None or rsi < min_rsi or rsi > max_rsi:
                    continue

                # Moving averages
                if len(close) < 50:
                    continue

                ma20 = close.rolling(window=20).mean().iloc[-1]
                ma50 = close.rolling(window=50).mean().iloc[-1]

                price_above_ma20 = ((current_price - ma20) / ma20) * 100
                price_above_ma50 = ((current_price - ma50) / ma50) * 100

                if price_above_ma20 < min_price_above_ma20:
                    continue

                if price_above_ma50 < min_price_above_ma50:
                    continue

                # Momentum
                if len(close) < 30:
                    continue

                price_10d_ago = close.iloc[-10]
                price_30d_ago = close.iloc[-30]

                momentum_10d = ((current_price - price_10d_ago) / price_10d_ago) * 100
                momentum_30d = ((current_price - price_30d_ago) / price_30d_ago) * 100

                if momentum_10d < min_momentum_10d:
                    continue

                if momentum_30d < min_momentum_30d:
                    continue

                # Calculate volatility
                volatility = close.pct_change().tail(20).std() * 100

                # Calculate trend strength
                trend_strength = self._calculate_trend_strength(close)

                # Momentum score (based on actual predictive metrics)
                momentum_score = self._calculate_momentum_score(
                    rsi=rsi,
                    price_above_ma20=price_above_ma20,
                    price_above_ma50=price_above_ma50,
                    momentum_10d=momentum_10d,
                    momentum_30d=momentum_30d,
                    trend_strength=trend_strength,
                    volatility=volatility
                )

                # Calculate entry score (replaces composite score)
                entry_score = self._calculate_entry_score(
                    momentum_score=momentum_score,
                    rsi=rsi,
                    price_above_ma50=price_above_ma50,
                    momentum_30d=momentum_30d,
                    market_cap=market_cap
                )

                passed += 1

                opportunity = {
                    'symbol': symbol,
                    'current_price': current_price,
                    'sector': sector,
                    'market_cap': market_cap,
                    'avg_volume': avg_volume,

                    # Momentum metrics
                    'rsi': rsi,
                    'price_above_ma20': price_above_ma20,
                    'price_above_ma50': price_above_ma50,
                    'momentum_10d': momentum_10d,
                    'momentum_30d': momentum_30d,
                    'volatility': volatility,
                    'trend_strength': trend_strength,

                    # Scores
                    'momentum_score': momentum_score,
                    'entry_score': entry_score,

                    # Additional info
                    'screened_date': datetime.now().strftime('%Y-%m-%d'),
                    'screener_version': 'MomentumGrowth_v1.0'
                }

                opportunities.append(opportunity)

                if passed % 5 == 0:
                    logger.info(f"   Analyzed {analyzed}, Passed {passed}...")

            except Exception as e:
                logger.debug(f"   Error screening {symbol}: {e}")
                continue

        logger.info(f"\n✅ Screening complete: {passed}/{analyzed} passed filters")

        # Sort by entry score
        opportunities.sort(key=lambda x: x['entry_score'], reverse=True)

        # Limit results
        opportunities = opportunities[:max_stocks]

        logger.info(f"\n📊 Top {len(opportunities)} opportunities found")

        return opportunities

    def _calculate_rsi(self, close_prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI"""
        try:
            delta = close_prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

            rs = gain / loss
            rsi = 100 - (100 / (1 + rs.iloc[-1]))

            return float(rsi)
        except:
            return None

    def _calculate_trend_strength(self, close_prices: pd.Series) -> float:
        """
        Calculate trend strength (0-100)
        Higher = stronger uptrend
        """
        try:
            # Calculate slope of 30-day linear regression
            y = close_prices.tail(30).values
            x = np.arange(len(y))

            # Linear regression
            slope, intercept = np.polyfit(x, y, 1)

            # Normalize slope to percentage
            avg_price = y.mean()
            trend_pct = (slope / avg_price) * 100 * 30  # 30-day trend

            # Convert to 0-100 scale
            # Strong uptrend (+30% over 30 days) = 100
            # Flat (0%) = 50
            # Strong downtrend (-30%) = 0

            trend_strength = 50 + (trend_pct * 50 / 30)
            trend_strength = max(0, min(100, trend_strength))

            return float(trend_strength)
        except:
            return 50.0

    def _calculate_momentum_score(self,
                                  rsi: float,
                                  price_above_ma20: float,
                                  price_above_ma50: float,
                                  momentum_10d: float,
                                  momentum_30d: float,
                                  trend_strength: float,
                                  volatility: float) -> float:
        """
        Calculate momentum score (0-100)

        Based on weights from actual performance:
        - RSI: High weight (80% diff between winners/losers)
        - MA50 distance: Very high weight (326% diff)
        - Momentum 10d: Very high weight (340% diff)
        - Momentum 30d: Very high weight (299% diff)
        """

        score = 0.0

        # RSI component (20 points)
        # Ideal RSI: 45-55 (healthy momentum)
        if 45 <= rsi <= 55:
            rsi_score = 20
        elif 40 <= rsi <= 60:
            rsi_score = 15
        elif 35 <= rsi <= 65:
            rsi_score = 10
        else:
            rsi_score = 5

        score += rsi_score

        # MA50 distance (25 points)
        # Winners: +12%, Losers: -5%
        if price_above_ma50 > 15:
            ma50_score = 25
        elif price_above_ma50 > 10:
            ma50_score = 20
        elif price_above_ma50 > 5:
            ma50_score = 15
        elif price_above_ma50 > 0:
            ma50_score = 10
        else:
            ma50_score = 0

        score += ma50_score

        # MA20 distance (15 points)
        if price_above_ma20 > 5:
            ma20_score = 15
        elif price_above_ma20 > 2:
            ma20_score = 12
        elif price_above_ma20 > 0:
            ma20_score = 8
        else:
            ma20_score = 0

        score += ma20_score

        # Momentum 10d (20 points)
        # Winners: +8%, Losers: -3%
        if momentum_10d > 10:
            mom10_score = 20
        elif momentum_10d > 5:
            mom10_score = 15
        elif momentum_10d > 2:
            mom10_score = 10
        elif momentum_10d > 0:
            mom10_score = 5
        else:
            mom10_score = 0

        score += mom10_score

        # Momentum 30d (20 points)
        # Winners: +22%, Losers: +5%
        if momentum_30d > 25:
            mom30_score = 20
        elif momentum_30d > 15:
            mom30_score = 15
        elif momentum_30d > 10:
            mom30_score = 10
        elif momentum_30d > 5:
            mom30_score = 5
        else:
            mom30_score = 0

        score += mom30_score

        return score

    def _calculate_entry_score(self,
                               momentum_score: float,
                               rsi: float,
                               price_above_ma50: float,
                               momentum_30d: float,
                               market_cap: float) -> float:
        """
        Calculate entry score for ranking (0-100)

        This is the PRIMARY ranking metric (replaces composite score)
        """

        score = momentum_score  # Base score (0-100)

        # Bonus for ideal RSI range
        if 45 <= rsi <= 55:
            score += 5

        # Bonus for strong position above MA50
        if price_above_ma50 > 15:
            score += 5

        # Bonus for very strong 30d momentum
        if momentum_30d > 20:
            score += 5

        # Bonus for larger market cap (more liquid)
        if market_cap > 10_000_000_000:  # $10B
            score += 3
        elif market_cap > 5_000_000_000:  # $5B
            score += 2

        return min(100, score)


def test_screener():
    """Quick test of the momentum screener"""
    from main import StockAnalyzer

    print("=" * 80)
    print("🧪 Testing Momentum Growth Screener v1.0")
    print("=" * 80)

    analyzer = StockAnalyzer()
    screener = MomentumGrowthScreener(analyzer)

    print("\nScreening with PROVEN filters:")
    print("  ✓ RSI 40-70 (not oversold/overbought)")
    print("  ✓ Price > MA20 (uptrend)")
    print("  ✓ Price > MA50 (strong uptrend)")
    print("  ✓ Momentum 10d > 0% (rising)")
    print("  ✓ Momentum 30d > 10% (strong trend)")

    results = screener.screen_opportunities(
        min_rsi=40,
        max_rsi=70,
        min_momentum_10d=0,
        min_momentum_30d=10,
        max_stocks=20,
        universe_size=100
    )

    print(f"\n📊 Results: {len(results)} stocks")

    if results:
        print(f"\nTop 10 opportunities:")
        print(f"{'Rank':<5} {'Symbol':<8} {'Price':>8} {'RSI':>6} {'MA50':>7} {'Mom10d':>8} {'Mom30d':>8} {'Score':>6}")
        print("-" * 75)

        for i, opp in enumerate(results[:10], 1):
            print(f"{i:<5} {opp['symbol']:<8} ${opp['current_price']:>7.2f} "
                  f"{opp['rsi']:>6.1f} {opp['price_above_ma50']:>6.1f}% "
                  f"{opp['momentum_10d']:>7.1f}% {opp['momentum_30d']:>7.1f}% "
                  f"{opp['entry_score']:>6.1f}")

        print(f"\n✅ These stocks match the WINNER profile!")
        print(f"   (High RSI, above MAs, positive momentum)")
    else:
        print(f"\n⚠️  No stocks found matching criteria")
        print(f"   Try lowering momentum requirements or checking market conditions")


if __name__ == '__main__':
    test_screener()
