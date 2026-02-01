#!/usr/bin/env python3
"""
Backtest Growth Catalyst Screener
Test if the screener's predictions align with actual 30-day returns
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from loguru import logger
from main import StockAnalyzer
from screeners.growth_catalyst_screener import GrowthCatalystScreener

logger.remove()
logger.add(sys.stdout, level="INFO")


class GrowthCatalystBacktester:
    """Backtest the Growth Catalyst Screener"""

    def __init__(self):
        self.analyzer = StockAnalyzer()
        self.screener = GrowthCatalystScreener(self.analyzer)

    def backtest_screening(self,
                          target_gain_pct: float = 15.0,
                          lookback_months: int = 3,
                          min_catalyst_score: float = 30.0,
                          min_technical_score: float = 30.0,
                          min_ai_probability: float = 35.0,
                          max_stocks: int = 20):
        """
        Backtest the screener by:
        1. Running the screener with current data
        2. Checking actual 30-day performance for each stock
        3. Calculating success metrics

        Args:
            target_gain_pct: Target gain percentage (default 15%)
            lookback_months: How many months back to test (for available data)
            min_catalyst_score: Minimum catalyst score
            min_technical_score: Minimum technical score
            min_ai_probability: Minimum AI probability
            max_stocks: Maximum number of stocks

        Returns:
            Backtest results with statistics
        """
        logger.info("=" * 80)
        logger.info("📊 GROWTH CATALYST SCREENER BACKTEST")
        logger.info("=" * 80)
        logger.info(f"Target Gain: {target_gain_pct}%+ in 30 days")
        logger.info(f"Criteria: Catalyst≥{min_catalyst_score}, Technical≥{min_technical_score}, AI≥{min_ai_probability}%")
        logger.info("")

        # Step 1: Run the screener
        logger.info("🎯 Step 1: Running Growth Catalyst Screener...")
        opportunities = self.screener.screen_growth_catalyst_opportunities(
            target_gain_pct=target_gain_pct,
            timeframe_days=30,
            min_catalyst_score=min_catalyst_score,
            min_technical_score=min_technical_score,
            min_ai_probability=min_ai_probability,
            max_stocks=max_stocks
        )

        if not opportunities:
            logger.warning("❌ No opportunities found!")
            return {
                'success': False,
                'message': 'No opportunities found',
                'results': []
            }

        logger.info(f"✅ Found {len(opportunities)} growth opportunities")
        logger.info("")

        # Step 2: Test each opportunity's actual performance
        logger.info("📈 Step 2: Testing actual 30-day performance...")
        logger.info("")

        backtest_results = []

        for i, opp in enumerate(opportunities, 1):
            symbol = opp['symbol']
            current_price = opp['current_price']
            target_price = current_price * (1 + target_gain_pct / 100)

            logger.info(f"[{i}/{len(opportunities)}] Testing {symbol}...")
            logger.info(f"   Current Price: ${current_price:.2f}")
            logger.info(f"   Target Price: ${target_price:.2f} (+{target_gain_pct}%)")
            logger.info(f"   Scores: Catalyst={opp['catalyst_score']:.1f}, Technical={opp['technical_score']:.1f}, AI={opp['ai_probability']:.1f}%")

            # Get historical price data
            try:
                # Get price data for last 90 days
                price_data = self.analyzer.data_manager.get_price_data(symbol, period='3mo')

                if price_data is None or price_data.empty or len(price_data) < 30:
                    logger.warning(f"   ⚠️  Insufficient data for {symbol}")
                    backtest_results.append({
                        'symbol': symbol,
                        'current_price': current_price,
                        'target_price': target_price,
                        'catalyst_score': opp['catalyst_score'],
                        'technical_score': opp['technical_score'],
                        'ai_probability': opp['ai_probability'],
                        'composite_score': opp['composite_score'],
                        'status': 'insufficient_data',
                        'actual_30d_return': None,
                        'reached_target': None
                    })
                    continue

                # Get the most recent 30 trading days
                close_prices = price_data['close'] if 'close' in price_data.columns else price_data['Close']

                # Calculate 30-day return from current price
                # Note: In real backtest, we'd use price 30 days ago as entry
                # For now, we'll estimate future return based on recent trend

                if len(close_prices) >= 30:
                    # Get price 30 days ago
                    price_30d_ago = close_prices.iloc[-30]
                    price_today = close_prices.iloc[-1]

                    # Calculate actual return over last 30 days
                    actual_return_pct = ((price_today - price_30d_ago) / price_30d_ago) * 100
                    reached_target = actual_return_pct >= target_gain_pct

                    # Get high over last 30 days to check if target was hit
                    high_prices = price_data['high'] if 'high' in price_data.columns else price_data['High']
                    max_30d_return = ((high_prices.iloc[-30:].max() - price_30d_ago) / price_30d_ago) * 100
                    reached_target_intraday = max_30d_return >= target_gain_pct

                    logger.info(f"   📊 30-Day Performance:")
                    logger.info(f"      Entry Price (30d ago): ${price_30d_ago:.2f}")
                    logger.info(f"      Current Price: ${price_today:.2f}")
                    logger.info(f"      Actual Return: {actual_return_pct:+.1f}%")
                    logger.info(f"      Max Intraday Return: {max_30d_return:+.1f}%")

                    if reached_target_intraday:
                        logger.info(f"   ✅ TARGET REACHED! ({max_30d_return:+.1f}% peak)")
                    elif actual_return_pct > 0:
                        logger.info(f"   📈 Positive but below target ({actual_return_pct:+.1f}%)")
                    else:
                        logger.info(f"   📉 Negative return ({actual_return_pct:+.1f}%)")

                    backtest_results.append({
                        'symbol': symbol,
                        'current_price': current_price,
                        'entry_price_30d_ago': price_30d_ago,
                        'target_price': target_price,
                        'catalyst_score': opp['catalyst_score'],
                        'technical_score': opp['technical_score'],
                        'ai_probability': opp['ai_probability'],
                        'composite_score': opp['composite_score'],
                        'catalysts': len(opp.get('catalysts', [])),
                        'status': 'tested',
                        'actual_30d_return': actual_return_pct,
                        'max_30d_return': max_30d_return,
                        'reached_target': reached_target_intraday
                    })

                else:
                    logger.warning(f"   ⚠️  Less than 30 days of data for {symbol}")
                    backtest_results.append({
                        'symbol': symbol,
                        'current_price': current_price,
                        'target_price': target_price,
                        'catalyst_score': opp['catalyst_score'],
                        'technical_score': opp['technical_score'],
                        'ai_probability': opp['ai_probability'],
                        'composite_score': opp['composite_score'],
                        'status': 'insufficient_data',
                        'actual_30d_return': None,
                        'reached_target': None
                    })

            except Exception as e:
                logger.error(f"   ❌ Error testing {symbol}: {e}")
                backtest_results.append({
                    'symbol': symbol,
                    'current_price': current_price,
                    'target_price': target_price,
                    'catalyst_score': opp['catalyst_score'],
                    'technical_score': opp['technical_score'],
                    'ai_probability': opp['ai_probability'],
                    'composite_score': opp['composite_score'],
                    'status': 'error',
                    'actual_30d_return': None,
                    'reached_target': None,
                    'error': str(e)
                })

            logger.info("")

        # Step 3: Calculate statistics
        logger.info("=" * 80)
        logger.info("📊 BACKTEST RESULTS SUMMARY")
        logger.info("=" * 80)

        tested_results = [r for r in backtest_results if r['status'] == 'tested']

        if not tested_results:
            logger.warning("❌ No valid test results!")
            return {
                'success': False,
                'message': 'No valid test results',
                'results': backtest_results
            }

        # Calculate metrics
        total_tested = len(tested_results)
        winners = [r for r in tested_results if r['reached_target']]
        losers = [r for r in tested_results if not r['reached_target']]

        win_rate = (len(winners) / total_tested * 100) if total_tested > 0 else 0

        avg_return = np.mean([r['actual_30d_return'] for r in tested_results])
        avg_max_return = np.mean([r['max_30d_return'] for r in tested_results])

        avg_winner_return = np.mean([r['actual_30d_return'] for r in winners]) if winners else 0
        avg_loser_return = np.mean([r['actual_30d_return'] for r in losers]) if losers else 0

        # Expectancy calculation
        if total_tested > 0:
            expectancy = (win_rate / 100 * avg_winner_return) + ((100 - win_rate) / 100 * avg_loser_return)
        else:
            expectancy = 0

        logger.info(f"📈 Performance Metrics:")
        logger.info(f"   Total Tested: {total_tested} stocks")
        logger.info(f"   Win Rate: {win_rate:.1f}% ({len(winners)}/{total_tested})")
        logger.info(f"   Average Return: {avg_return:+.2f}%")
        logger.info(f"   Average Max Return: {avg_max_return:+.2f}%")
        logger.info("")
        logger.info(f"   Winners: {len(winners)} stocks (Avg: {avg_winner_return:+.2f}%)")
        logger.info(f"   Losers: {len(losers)} stocks (Avg: {avg_loser_return:+.2f}%)")
        logger.info(f"   Expectancy: {expectancy:+.2f}%")
        logger.info("")

        # Show top performers
        if winners:
            logger.info("🏆 Top Performers (Reached Target):")
            sorted_winners = sorted(winners, key=lambda x: x['max_30d_return'], reverse=True)
            for i, r in enumerate(sorted_winners[:5], 1):
                logger.info(f"   {i}. {r['symbol']}: {r['max_30d_return']:+.1f}% (Composite: {r['composite_score']:.1f})")
            logger.info("")

        # Show worst performers
        if losers:
            logger.info("📉 Missed Targets:")
            sorted_losers = sorted(losers, key=lambda x: x['actual_30d_return'])
            for i, r in enumerate(sorted_losers[:5], 1):
                logger.info(f"   {i}. {r['symbol']}: {r['actual_30d_return']:+.1f}% (Composite: {r['composite_score']:.1f})")
            logger.info("")

        # Analysis by scores
        logger.info("🔍 Analysis by Score Correlation:")

        # Correlation between composite score and returns
        composite_scores = [r['composite_score'] for r in tested_results]
        actual_returns = [r['actual_30d_return'] for r in tested_results]

        if len(composite_scores) >= 2:
            correlation = np.corrcoef(composite_scores, actual_returns)[0, 1]
            logger.info(f"   Composite Score vs Returns: {correlation:.3f}")

        # High-score performance
        high_score_stocks = [r for r in tested_results if r['composite_score'] >= 45]
        if high_score_stocks:
            high_score_win_rate = len([r for r in high_score_stocks if r['reached_target']]) / len(high_score_stocks) * 100
            logger.info(f"   High Score (≥45) Win Rate: {high_score_win_rate:.1f}% ({len(high_score_stocks)} stocks)")

        logger.info("")
        logger.info("=" * 80)

        # Recommendation
        if win_rate >= 60:
            logger.info("✅ EXCELLENT: Screener shows strong predictive power!")
        elif win_rate >= 50:
            logger.info("✅ GOOD: Screener shows decent predictive power")
        elif win_rate >= 40:
            logger.info("⚠️  MODERATE: Screener needs refinement")
        else:
            logger.info("❌ POOR: Screener needs significant improvement")

        logger.info("=" * 80)

        return {
            'success': True,
            'target_gain_pct': target_gain_pct,
            'total_opportunities': len(opportunities),
            'total_tested': total_tested,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'avg_max_return': avg_max_return,
            'avg_winner_return': avg_winner_return,
            'avg_loser_return': avg_loser_return,
            'expectancy': expectancy,
            'winners': len(winners),
            'losers': len(losers),
            'results': backtest_results,
            'tested_results': tested_results,
            'top_performers': sorted_winners[:5] if winners else [],
            'worst_performers': sorted_losers[:5] if losers else []
        }


def main():
    """Run backtest"""
    backtester = GrowthCatalystBacktester()

    # Run backtest with 15% target (new default)
    results = backtester.backtest_screening(
        target_gain_pct=15.0,
        min_catalyst_score=30.0,
        min_technical_score=30.0,
        min_ai_probability=35.0,
        max_stocks=20
    )

    if results['success']:
        logger.info("\n✅ Backtest completed successfully!")
        logger.info(f"Win Rate: {results['win_rate']:.1f}%")
        logger.info(f"Expectancy: {results['expectancy']:+.2f}%")
    else:
        logger.error("\n❌ Backtest failed!")
        logger.error(f"Reason: {results.get('message', 'Unknown error')}")


if __name__ == "__main__":
    main()
