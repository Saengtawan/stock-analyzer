#!/usr/bin/env python3
"""
Simple Backtest for Growth Catalyst Screener (15% target)
Tests if the stocks from the screener can achieve 15% gain in 30 days

This is a simplified version that:
1. Uses the current screening results
2. Checks historical 30-day performance
3. Doesn't require full StockAnalyzer dependencies
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


# Sample stocks from the current screening results (from your screenshot)
# These are the top 20 stocks found by the screener
SCREENED_STOCKS = [
    {'symbol': 'HOOD', 'composite_score': 49.8, 'catalyst_score': 45.0, 'technical_score': 40.0, 'ai_probability': 55.0},
    {'symbol': 'HUBS', 'composite_score': 49.8, 'catalyst_score': 45.0, 'technical_score': 40.0, 'ai_probability': 55.0},
    {'symbol': 'ANET', 'composite_score': 48.5, 'catalyst_score': 45.0, 'technical_score': 35.0, 'ai_probability': 55.0},
    {'symbol': 'AMZN', 'composite_score': 47.2, 'catalyst_score': 45.0, 'technical_score': 30.0, 'ai_probability': 55.0},
    {'symbol': 'TEAM', 'composite_score': 47.0, 'catalyst_score': 40.0, 'technical_score': 35.0, 'ai_probability': 55.0},
    {'symbol': 'NOW', 'composite_score': 44.0, 'catalyst_score': 45.0, 'technical_score': 35.0, 'ai_probability': 40.0},
    {'symbol': 'AMD', 'composite_score': 44.0, 'catalyst_score': 45.0, 'technical_score': 35.0, 'ai_probability': 40.0},
    {'symbol': 'NET', 'composite_score': 44.0, 'catalyst_score': 45.0, 'technical_score': 35.0, 'ai_probability': 40.0},
    {'symbol': 'COIN', 'composite_score': 44.0, 'catalyst_score': 45.0, 'technical_score': 35.0, 'ai_probability': 40.0},
    {'symbol': 'TSM', 'composite_score': 44.0, 'catalyst_score': 45.0, 'technical_score': 35.0, 'ai_probability': 40.0},
    {'symbol': 'QCOM', 'composite_score': 43.8, 'catalyst_score': 35.0, 'technical_score': 40.0, 'ai_probability': 45.0},
    {'symbol': 'LRCX', 'composite_score': 43.8, 'catalyst_score': 35.0, 'technical_score': 40.0, 'ai_probability': 45.0},
    {'symbol': 'MSFT', 'composite_score': 43.0, 'catalyst_score': 45.0, 'technical_score': 40.0, 'ai_probability': 35.0},
    {'symbol': 'SHOP', 'composite_score': 42.5, 'catalyst_score': 35.0, 'technical_score': 35.0, 'ai_probability': 45.0},
    {'symbol': 'ROKU', 'composite_score': 42.5, 'catalyst_score': 35.0, 'technical_score': 35.0, 'ai_probability': 45.0},
    {'symbol': 'AVGO', 'composite_score': 42.2, 'catalyst_score': 30.0, 'technical_score': 40.0, 'ai_probability': 45.0},
    {'symbol': 'UBER', 'composite_score': 41.7, 'catalyst_score': 45.0, 'technical_score': 30.0, 'ai_probability': 39.0},
    {'symbol': 'PLTR', 'composite_score': 41.2, 'catalyst_score': 35.0, 'technical_score': 30.0, 'ai_probability': 45.0},
    {'symbol': 'GOOGL', 'composite_score': 41.0, 'catalyst_score': 35.0, 'technical_score': 35.0, 'ai_probability': 40.0},
    {'symbol': 'DASH', 'composite_score': 41.0, 'catalyst_score': 35.0, 'technical_score': 35.0, 'ai_probability': 40.0},
]

TARGET_GAIN_PCT = 15.0  # New default


def backtest_stock(symbol, target_gain_pct=15.0):
    """Test a single stock's 30-day performance"""
    try:
        print(f"\nTesting {symbol}...")

        # Get 3 months of data
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='3mo')

        if hist.empty or len(hist) < 30:
            print(f"  ⚠️  Insufficient data")
            return None

        # Get prices 30 trading days ago and today
        price_30d_ago = hist['Close'].iloc[-30]
        price_today = hist['Close'].iloc[-1]

        # Calculate return
        actual_return = ((price_today - price_30d_ago) / price_30d_ago) * 100

        # Check if target was reached (including intraday highs)
        high_30d = hist['High'].iloc[-30:].max()
        max_return = ((high_30d - price_30d_ago) / price_30d_ago) * 100

        reached_target = max_return >= target_gain_pct

        print(f"  Entry (30d ago): ${price_30d_ago:.2f}")
        print(f"  Current: ${price_today:.2f}")
        print(f"  Return: {actual_return:+.1f}%")
        print(f"  Max Return: {max_return:+.1f}%")
        print(f"  Target Reached: {'✅ YES' if reached_target else '❌ NO'}")

        return {
            'symbol': symbol,
            'entry_price': price_30d_ago,
            'current_price': price_today,
            'actual_return': actual_return,
            'max_return': max_return,
            'reached_target': reached_target
        }

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def main():
    """Run backtest on all screened stocks"""
    print("="*80)
    print("📊 GROWTH CATALYST SCREENER BACKTEST (15% Target)")
    print("="*80)
    print(f"Testing {len(SCREENED_STOCKS)} stocks from recent screening")
    print(f"Target: {TARGET_GAIN_PCT}%+ gain in 30 days")
    print("")

    results = []

    for stock_data in SCREENED_STOCKS:
        symbol = stock_data['symbol']
        result = backtest_stock(symbol, TARGET_GAIN_PCT)

        if result:
            result.update({
                'composite_score': stock_data['composite_score'],
                'catalyst_score': stock_data['catalyst_score'],
                'technical_score': stock_data['technical_score'],
                'ai_probability': stock_data['ai_probability']
            })
            results.append(result)

    # Calculate statistics
    print("\n" + "="*80)
    print("📊 BACKTEST RESULTS SUMMARY")
    print("="*80)

    if not results:
        print("❌ No valid results")
        return

    total = len(results)
    winners = [r for r in results if r['reached_target']]
    losers = [r for r in results if not r['reached_target']]

    win_rate = (len(winners) / total * 100) if total > 0 else 0

    avg_return = np.mean([r['actual_return'] for r in results])
    avg_max_return = np.mean([r['max_return'] for r in results])

    avg_winner_return = np.mean([r['max_return'] for r in winners]) if winners else 0
    avg_loser_return = np.mean([r['actual_return'] for r in losers]) if losers else 0

    # Expectancy
    expectancy = (win_rate / 100 * avg_winner_return) + ((100 - win_rate) / 100 * avg_loser_return)

    print(f"\n📈 Performance Metrics:")
    print(f"   Total Tested: {total} stocks")
    print(f"   Win Rate: {win_rate:.1f}% ({len(winners)}/{total})")
    print(f"   Average Return: {avg_return:+.2f}%")
    print(f"   Average Max Return: {avg_max_return:+.2f}%")
    print("")
    print(f"   Winners: {len(winners)} stocks (Avg: {avg_winner_return:+.2f}%)")
    print(f"   Losers: {len(losers)} stocks (Avg: {avg_loser_return:+.2f}%)")
    print(f"   Expectancy: {expectancy:+.2f}%")
    print("")

    # Top performers
    if winners:
        print("🏆 Top Performers (Reached 15%+ Target):")
        sorted_winners = sorted(winners, key=lambda x: x['max_return'], reverse=True)
        for i, r in enumerate(sorted_winners[:5], 1):
            print(f"   {i}. {r['symbol']}: {r['max_return']:+.1f}% (Score: {r['composite_score']:.1f})")
        print("")

    # Missed targets
    if losers:
        print("📉 Missed Targets:")
        sorted_losers = sorted(losers, key=lambda x: x['actual_return'])
        for i, r in enumerate(sorted_losers[:5], 1):
            print(f"   {i}. {r['symbol']}: {r['actual_return']:+.1f}% (Score: {r['composite_score']:.1f})")
        print("")

    # Score correlation
    print("🔍 Score vs Performance Correlation:")
    composite_scores = [r['composite_score'] for r in results]
    actual_returns = [r['actual_return'] for r in results]

    if len(composite_scores) >= 2:
        correlation = np.corrcoef(composite_scores, actual_returns)[0, 1]
        print(f"   Composite Score vs Returns: {correlation:.3f}")

    # High-score performance
    high_score_stocks = [r for r in results if r['composite_score'] >= 45]
    if high_score_stocks:
        high_score_win_rate = len([r for r in high_score_stocks if r['reached_target']]) / len(high_score_stocks) * 100
        print(f"   High Score (≥45) Win Rate: {high_score_win_rate:.1f}% ({len(high_score_stocks)} stocks)")

    print("")
    print("="*80)

    # Recommendation
    if win_rate >= 60:
        print("✅ EXCELLENT: Screener shows strong predictive power!")
    elif win_rate >= 50:
        print("✅ GOOD: Screener shows decent predictive power")
    elif win_rate >= 40:
        print("⚠️  MODERATE: Screener needs refinement")
    else:
        print("❌ POOR: Screener needs significant improvement")

    print("="*80)
    print(f"\n💡 Insight: {'' if win_rate >= 50 else 'Consider adjusting thresholds or criteria.'}")


if __name__ == "__main__":
    main()
