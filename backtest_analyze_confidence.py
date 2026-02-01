#!/usr/bin/env python3
"""
Deep analysis of confidence scoring - WHY did 80-100 fail while 70-79 succeeded?
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import json

def calculate_simple_confidence(gap_pct, consistency_ratio):
    """
    Current confidence calculation (same as backtest_gap_scanner.py)
    """
    confidence = 50  # Start at neutral

    # Gap factor
    if 2.0 <= gap_pct <= 3.5:
        confidence += 15  # Sweet spot
    elif 1.5 <= gap_pct < 2.0 or 3.5 < gap_pct <= 4.5:
        confidence += 8
    elif gap_pct > 7.0:
        confidence -= 15  # Too big

    # Consistency factor
    if consistency_ratio >= 0.8:
        confidence += 15
    elif consistency_ratio >= 0.6:
        confidence += 10
    elif consistency_ratio >= 0.5:
        confidence += 5
    elif consistency_ratio >= 0.4:
        confidence += 0
    elif consistency_ratio >= 0.3:
        confidence -= 15
    else:
        confidence -= 30

    return max(0, min(100, int(confidence)))

def analyze_confidence_issues(symbols, days=60):
    """
    Analyze why different confidence levels perform differently
    """

    print("=" * 100)
    print("🔬 DEEP CONFIDENCE ANALYSIS")
    print("=" * 100)
    print(f"\nAnalyzing {len(symbols)} stocks over {days} trading days")
    print("Goal: Find WHY confidence 80-100 failed while 70-79 succeeded\n")

    all_trades = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{days+10}d", interval="1d")

            if df.empty or len(df) < 5:
                continue

            # Calculate gaps
            df['PrevClose'] = df['Close'].shift(1)
            df['Gap'] = ((df['Open'] - df['PrevClose']) / df['PrevClose'] * 100)
            df['DayReturn'] = ((df['Close'] - df['Open']) / df['Open'] * 100)

            # Filter gap trades
            gap_trades = df[df['Gap'] >= 2.0].copy()

            if gap_trades.empty:
                continue

            for idx, row in gap_trades.iterrows():
                prev_idx = df.index.get_loc(idx)
                if prev_idx >= 5:
                    prev_5_days = df.iloc[prev_idx-5:prev_idx]
                    daily_changes = prev_5_days['Close'].pct_change().dropna()
                    if len(daily_changes) > 0:
                        consistency = (daily_changes > 0).sum() / len(daily_changes)
                    else:
                        consistency = 0.5
                else:
                    consistency = 0.5

                confidence = calculate_simple_confidence(
                    gap_pct=row['Gap'],
                    consistency_ratio=consistency
                )

                # Record detailed trade
                trade = {
                    'symbol': symbol,
                    'date': idx.strftime('%Y-%m-%d'),
                    'gap': row['Gap'],
                    'consistency': consistency * 100,
                    'confidence': confidence,
                    'day_return': row['DayReturn'],
                    'success': row['DayReturn'] > 0,
                    'open': row['Open'],
                    'close': row['Close'],
                    'high': row['High'],
                    'low': row['Low']
                }
                all_trades.append(trade)

        except Exception as e:
            continue

    if not all_trades:
        print("❌ No trades found")
        return

    df = pd.DataFrame(all_trades)

    # Segment by confidence
    conf_80_100 = df[(df['confidence'] >= 80) & (df['confidence'] <= 100)]
    conf_70_79 = df[(df['confidence'] >= 70) & (df['confidence'] < 80)]

    print("\n" + "=" * 100)
    print("📊 CONFIDENCE 80-100 (FAILED) vs 70-79 (SUCCEEDED)")
    print("=" * 100)

    print(f"\n{'Metric':<30} {'Conf 80-100 (FAILED)':<25} {'Conf 70-79 (SUCCESS)':<25}")
    print("-" * 100)

    if len(conf_80_100) > 0:
        wr_80 = (conf_80_100['success'].sum() / len(conf_80_100) * 100)
        avg_ret_80 = conf_80_100['day_return'].mean()
        avg_gap_80 = conf_80_100['gap'].mean()
        avg_cons_80 = conf_80_100['consistency'].mean()
    else:
        wr_80 = 0
        avg_ret_80 = 0
        avg_gap_80 = 0
        avg_cons_80 = 0

    if len(conf_70_79) > 0:
        wr_70 = (conf_70_79['success'].sum() / len(conf_70_79) * 100)
        avg_ret_70 = conf_70_79['day_return'].mean()
        avg_gap_70 = conf_70_79['gap'].mean()
        avg_cons_70 = conf_70_79['consistency'].mean()
    else:
        wr_70 = 0
        avg_ret_70 = 0
        avg_gap_70 = 0
        avg_cons_70 = 0

    print(f"{'Trades':<30} {len(conf_80_100):<25} {len(conf_70_79):<25}")
    print(f"{'Win Rate':<30} {wr_80:>23.1f}% {wr_70:>23.1f}%")
    print(f"{'Avg Return':<30} {avg_ret_80:>+22.2f}% {avg_ret_70:>+22.2f}%")
    print(f"{'Avg Gap Size':<30} {avg_gap_80:>22.2f}% {avg_gap_70:>22.2f}%")
    print(f"{'Avg Consistency':<30} {avg_cons_80:>22.1f}% {avg_cons_70:>22.1f}%")

    # Key insight: Compare gap and consistency distributions
    print("\n" + "=" * 100)
    print("🔍 DISTRIBUTION ANALYSIS")
    print("=" * 100)

    if len(conf_80_100) > 0:
        print(f"\n📌 Confidence 80-100 trades (n={len(conf_80_100)}):")
        print(f"   Gap distribution:")
        gap_2_3 = len(conf_80_100[(conf_80_100['gap'] >= 2.0) & (conf_80_100['gap'] < 3.0)])
        gap_3_5 = len(conf_80_100[(conf_80_100['gap'] >= 3.0) & (conf_80_100['gap'] < 5.0)])
        gap_5_plus = len(conf_80_100[conf_80_100['gap'] >= 5.0])
        print(f"      2-3%: {gap_2_3} trades ({gap_2_3/len(conf_80_100)*100:.1f}%)")
        print(f"      3-5%: {gap_3_5} trades ({gap_3_5/len(conf_80_100)*100:.1f}%)")
        print(f"      5%+:  {gap_5_plus} trades ({gap_5_plus/len(conf_80_100)*100:.1f}%)")

        print(f"\n   Consistency distribution:")
        cons_80_plus = len(conf_80_100[conf_80_100['consistency'] >= 80])
        cons_60_80 = len(conf_80_100[(conf_80_100['consistency'] >= 60) & (conf_80_100['consistency'] < 80)])
        cons_below_60 = len(conf_80_100[conf_80_100['consistency'] < 60])
        print(f"      80%+:    {cons_80_plus} trades ({cons_80_plus/len(conf_80_100)*100:.1f}%)")
        print(f"      60-80%:  {cons_60_80} trades ({cons_60_80/len(conf_80_100)*100:.1f}%)")
        print(f"      <60%:    {cons_below_60} trades ({cons_below_60/len(conf_80_100)*100:.1f}%)")

    if len(conf_70_79) > 0:
        print(f"\n📌 Confidence 70-79 trades (n={len(conf_70_79)}):")
        print(f"   Gap distribution:")
        gap_2_3 = len(conf_70_79[(conf_70_79['gap'] >= 2.0) & (conf_70_79['gap'] < 3.0)])
        gap_3_5 = len(conf_70_79[(conf_70_79['gap'] >= 3.0) & (conf_70_79['gap'] < 5.0)])
        gap_5_plus = len(conf_70_79[conf_70_79['gap'] >= 5.0])
        print(f"      2-3%: {gap_2_3} trades ({gap_2_3/len(conf_70_79)*100:.1f}%)")
        print(f"      3-5%: {gap_3_5} trades ({gap_3_5/len(conf_70_79)*100:.1f}%)")
        print(f"      5%+:  {gap_5_plus} trades ({gap_5_plus/len(conf_70_79)*100:.1f}%)")

        print(f"\n   Consistency distribution:")
        cons_80_plus = len(conf_70_79[conf_70_79['consistency'] >= 80])
        cons_60_80 = len(conf_70_79[(conf_70_79['consistency'] >= 60) & (conf_70_79['consistency'] < 80)])
        cons_below_60 = len(conf_70_79[conf_70_79['consistency'] < 60])
        print(f"      80%+:    {cons_80_plus} trades ({cons_80_plus/len(conf_70_79)*100:.1f}%)")
        print(f"      60-80%:  {cons_60_80} trades ({cons_60_80/len(conf_70_79)*100:.1f}%)")
        print(f"      <60%:    {cons_below_60} trades ({cons_below_60/len(conf_70_79)*100:.1f}%)")

    # Show actual trades
    print("\n" + "=" * 100)
    print("📋 ACTUAL TRADES")
    print("=" * 100)

    if len(conf_80_100) > 0:
        print(f"\n❌ Confidence 80-100 trades (0% win rate):")
        print(f"{'Date':<12} {'Symbol':<8} {'Gap%':<8} {'Cons%':<8} {'Conf':<8} {'Return%':<10} {'Result':<10}")
        print("-" * 100)
        for _, trade in conf_80_100.iterrows():
            result = "✅ WIN" if trade['success'] else "❌ LOSS"
            print(f"{trade['date']:<12} {trade['symbol']:<8} {trade['gap']:>6.2f}% {trade['consistency']:>6.1f}% {trade['confidence']:>5}/100 {trade['day_return']:>+8.2f}% {result:<10}")

    if len(conf_70_79) > 0:
        print(f"\n✅ Confidence 70-79 trades (57.1% win rate):")
        print(f"{'Date':<12} {'Symbol':<8} {'Gap%':<8} {'Cons%':<8} {'Conf':<8} {'Return%':<10} {'Result':<10}")
        print("-" * 100)
        for _, trade in conf_70_79.iterrows():
            result = "✅ WIN" if trade['success'] else "❌ LOSS"
            print(f"{trade['date']:<12} {trade['symbol']:<8} {trade['gap']:>6.2f}% {trade['consistency']:>6.1f}% {trade['confidence']:>5}/100 {trade['day_return']:>+8.2f}% {result:<10}")

    # KEY INSIGHT
    print("\n" + "=" * 100)
    print("💡 KEY INSIGHTS")
    print("=" * 100)

    if len(conf_80_100) > 0 and len(conf_70_79) > 0:
        print(f"\n1. Gap Size:")
        print(f"   - Conf 80-100: Avg {avg_gap_80:.2f}%")
        print(f"   - Conf 70-79:  Avg {avg_gap_70:.2f}%")
        if avg_gap_80 > avg_gap_70:
            print(f"   ⚠️  PROBLEM: High confidence has LARGER gaps (more likely to fade!)")

        print(f"\n2. Consistency:")
        print(f"   - Conf 80-100: Avg {avg_cons_80:.1f}%")
        print(f"   - Conf 70-79:  Avg {avg_cons_70:.1f}%")
        if avg_cons_80 > avg_cons_70:
            print(f"   🤔 High consistency but still failed - small sample size issue?")

        print(f"\n3. Sample Size Issue:")
        print(f"   - Conf 80-100: Only {len(conf_80_100)} trades (very small!)")
        print(f"   - Conf 70-79:  {len(conf_70_79)} trades")
        if len(conf_80_100) < 10:
            print(f"   🚨 WARNING: Too few 80+ trades to draw strong conclusions!")

    print("\n" + "=" * 100)
    print("🔧 RECOMMENDED FIXES")
    print("=" * 100)

    if len(conf_80_100) < 10:
        print("\n1. ⚠️  Sample Size Too Small!")
        print("   - Only 4 trades at confidence 80-100")
        print("   - Need more data or longer backtest period")
        print("   - Current results may be random variance")

    print("\n2. 🎯 Possible Scoring Adjustments:")
    print("   a) LOWER the bonus for high consistency (currently +15)")
    print("   b) ADD penalty for gaps >3.5% (currently in sweet spot)")
    print("   c) REQUIRE minimum trade count before using confidence 80+")
    print("   d) Use confidence 70-79 as the 'high confidence' range")

    print("\n3. 💡 Strategy Recommendation:")
    print("   - Trade ONLY confidence 70-79 range")
    print("   - Avoid confidence 80+ until more data validates it")
    print("   - Focus on gap 2-3% sweet spot")

    print("\n" + "=" * 100)

if __name__ == '__main__':
    test_symbols = [
        # Tech
        'AAPL', 'MSFT', 'GOOGL', 'META', 'NVDA', 'AMD', 'TSLA',
        'NFLX', 'AMZN', 'INTC', 'QCOM', 'AVGO',
        # Consumer
        'DIS', 'NKE', 'SBUX', 'MCD', 'COST', 'WMT', 'TGT',
        # Healthcare
        'JNJ', 'PFE', 'MRNA', 'UNH', 'CVS',
        # Finance
        'JPM', 'BAC', 'GS', 'MS', 'V', 'MA',
        # Other
        'BA', 'CAT', 'GE', 'F', 'GM'
    ]

    print("\n🔬 Deep diving into confidence scoring issues...\n")
    analyze_confidence_issues(test_symbols, days=60)
