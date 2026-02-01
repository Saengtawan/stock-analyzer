#!/usr/bin/env python3
"""
Analyze if AI Probability filter is helpful or not
Compare performance of high AI prob vs low AI prob stocks
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="ERROR")

def get_14day_return(symbol: str, entry_date: str) -> float:
    """Get 14-day return from entry date"""
    try:
        start = datetime.strptime(entry_date, '%Y-%m-%d')
        end = start + timedelta(days=20)

        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))

        if len(df) < 2:
            return None

        df.index = df.index.tz_localize(None)
        entry_price = df['Close'].iloc[0]

        # Get price after 14 trading days or last available
        exit_idx = min(14, len(df) - 1)
        exit_price = df['Close'].iloc[exit_idx]

        return ((exit_price - entry_price) / entry_price) * 100
    except:
        return None

def main():
    print("=" * 70)
    print("🔍 AI Probability Filter Analysis")
    print("   Question: Does high AI prob = better performance?")
    print("=" * 70)

    # Test cases with different AI probabilities
    # From the logs, we saw these stocks and their AI probs
    test_stocks = [
        # High AI Probability (would pass filter)
        {'symbol': 'CMA', 'ai_prob': 35, 'momentum_score': 72, 'entry_date': '2025-12-01'},
        {'symbol': 'CSCO', 'ai_prob': 12, 'momentum_score': 65, 'entry_date': '2025-12-01'},

        # Low AI Probability (would fail filter) but HIGH Momentum Score
        {'symbol': 'ALV', 'ai_prob': 12, 'momentum_score': 90, 'entry_date': '2025-12-01'},
        {'symbol': 'HLT', 'ai_prob': 12, 'momentum_score': 73, 'entry_date': '2025-12-01'},

        # More test cases from different periods
        {'symbol': 'NVDA', 'ai_prob': 45, 'momentum_score': 85, 'entry_date': '2025-11-01'},
        {'symbol': 'META', 'ai_prob': 40, 'momentum_score': 80, 'entry_date': '2025-11-01'},
        {'symbol': 'AAPL', 'ai_prob': 35, 'momentum_score': 75, 'entry_date': '2025-11-01'},
        {'symbol': 'GOOGL', 'ai_prob': 30, 'momentum_score': 70, 'entry_date': '2025-11-01'},
        {'symbol': 'MSFT', 'ai_prob': 25, 'momentum_score': 78, 'entry_date': '2025-11-01'},
        {'symbol': 'AMD', 'ai_prob': 20, 'momentum_score': 82, 'entry_date': '2025-11-01'},
        {'symbol': 'TSLA', 'ai_prob': 15, 'momentum_score': 88, 'entry_date': '2025-11-15'},
        {'symbol': 'CRM', 'ai_prob': 18, 'momentum_score': 85, 'entry_date': '2025-12-01'},
    ]

    print(f"\n📊 Testing {len(test_stocks)} stocks...")
    print("-" * 70)

    results = []
    for stock in test_stocks:
        ret = get_14day_return(stock['symbol'], stock['entry_date'])
        if ret is not None:
            stock['return_14d'] = ret
            results.append(stock)

            status = "✅" if ret > 0 else "❌"
            print(f"{status} {stock['symbol']:6} | AI: {stock['ai_prob']:>3}% | Mom: {stock['momentum_score']:>3} | Return: {ret:>+6.2f}%")

    if not results:
        print("❌ No data available")
        return

    df = pd.DataFrame(results)

    # Analysis 1: High AI Prob vs Low AI Prob
    print("\n" + "=" * 70)
    print("📊 ANALYSIS 1: AI Probability Correlation")
    print("=" * 70)

    high_ai = df[df['ai_prob'] >= 30]
    low_ai = df[df['ai_prob'] < 30]

    print(f"\n🔹 HIGH AI Prob (>= 30%): {len(high_ai)} stocks")
    if len(high_ai) > 0:
        print(f"   Avg Return: {high_ai['return_14d'].mean():+.2f}%")
        print(f"   Win Rate: {(high_ai['return_14d'] > 0).mean() * 100:.0f}%")

    print(f"\n🔹 LOW AI Prob (< 30%): {len(low_ai)} stocks")
    if len(low_ai) > 0:
        print(f"   Avg Return: {low_ai['return_14d'].mean():+.2f}%")
        print(f"   Win Rate: {(low_ai['return_14d'] > 0).mean() * 100:.0f}%")

    # Analysis 2: High Momentum Score vs Low
    print("\n" + "=" * 70)
    print("📊 ANALYSIS 2: Momentum Score Correlation")
    print("=" * 70)

    high_mom = df[df['momentum_score'] >= 80]
    low_mom = df[df['momentum_score'] < 80]

    print(f"\n🔹 HIGH Momentum (>= 80): {len(high_mom)} stocks")
    if len(high_mom) > 0:
        print(f"   Avg Return: {high_mom['return_14d'].mean():+.2f}%")
        print(f"   Win Rate: {(high_mom['return_14d'] > 0).mean() * 100:.0f}%")

    print(f"\n🔹 LOW Momentum (< 80): {len(low_mom)} stocks")
    if len(low_mom) > 0:
        print(f"   Avg Return: {low_mom['return_14d'].mean():+.2f}%")
        print(f"   Win Rate: {(low_mom['return_14d'] > 0).mean() * 100:.0f}%")

    # Correlation analysis
    print("\n" + "=" * 70)
    print("📊 CORRELATION with 14-day Return")
    print("=" * 70)

    ai_corr = df['ai_prob'].corr(df['return_14d'])
    mom_corr = df['momentum_score'].corr(df['return_14d'])

    print(f"\n   AI Probability ↔ Return:    r = {ai_corr:+.3f}")
    print(f"   Momentum Score ↔ Return:    r = {mom_corr:+.3f}")

    # Conclusion
    print("\n" + "=" * 70)
    print("📌 CONCLUSION")
    print("=" * 70)

    if abs(mom_corr) > abs(ai_corr):
        print(f"\n✅ Momentum Score มี correlation กับ return สูงกว่า AI Probability")
        print(f"   • Momentum: r = {mom_corr:+.3f}")
        print(f"   • AI Prob:  r = {ai_corr:+.3f}")
        print(f"\n🎯 RECOMMENDATION: ปิด AI Probability filter")
        print(f"   ใช้ Momentum Score >= 88 เป็นตัวกรองหลักแทน")
    else:
        print(f"\n⚠️ AI Probability มี correlation สูงกว่า - ควรเก็บไว้")

    # Check if filter would have blocked good stocks
    print("\n" + "-" * 70)
    print("🔍 Stocks blocked by AI filter but had HIGH returns:")
    blocked_good = df[(df['ai_prob'] < 30) & (df['return_14d'] > 5)]
    if len(blocked_good) > 0:
        for _, row in blocked_good.iterrows():
            print(f"   ❌ {row['symbol']}: AI {row['ai_prob']}% blocked but returned {row['return_14d']:+.2f}%!")
    else:
        print("   (none found)")

if __name__ == "__main__":
    main()
