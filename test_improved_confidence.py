#!/usr/bin/env python3
"""
Test improved confidence calculation based on backtest findings
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

import yfinance as yf
import pandas as pd

def calculate_old_confidence(gap_pct, consistency_ratio):
    """OLD confidence calculation (current)"""
    confidence = 50

    # Gap factor
    if 2.0 <= gap_pct <= 3.5:
        confidence += 15
    elif 1.5 <= gap_pct < 2.0 or 3.5 < gap_pct <= 4.5:
        confidence += 8
    elif gap_pct > 7.0:
        confidence -= 15

    # Consistency factor
    if consistency_ratio >= 0.8:
        confidence += 15  # PROBLEM: Too high for 100% consistency!
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

def calculate_improved_confidence(gap_pct, consistency_ratio):
    """
    IMPROVED confidence calculation

    Key changes:
    1. Narrower gap sweet spot (2.0-3.0% instead of 2.0-3.5%)
    2. Penalty for very high consistency (>90% = overbought)
    3. Lower bonus for high consistency (max +10 instead of +15)
    4. More conservative overall
    """
    confidence = 50  # Start neutral

    # Gap factor (IMPROVED - narrower sweet spot)
    if 2.0 <= gap_pct <= 3.0:
        confidence += 12  # Sweet spot (reduced from 15)
    elif 3.0 < gap_pct <= 3.5:
        confidence += 5   # Still okay but not as good
    elif 1.5 <= gap_pct < 2.0:
        confidence += 3   # Too small
    elif 3.5 < gap_pct <= 4.5:
        confidence += 0   # Getting risky
    elif 4.5 < gap_pct <= 7.0:
        confidence -= 10  # High fade risk
    elif gap_pct > 7.0:
        confidence -= 20  # Very high fade risk (increased penalty)

    # Consistency factor (IMPROVED - penalize overbought)
    if consistency_ratio >= 0.95:
        # CRITICAL FIX: Very high consistency = overbought = reversal risk!
        confidence -= 5   # Overbought warning
    elif consistency_ratio >= 0.8:
        confidence += 8   # Good but not too hot (reduced from +15)
    elif consistency_ratio >= 0.6:
        confidence += 10  # Sweet spot for consistency
    elif consistency_ratio >= 0.5:
        confidence += 5   # Moderate
    elif consistency_ratio >= 0.4:
        confidence += 0   # Neutral
    elif consistency_ratio >= 0.3:
        confidence -= 15  # Weak
    else:
        confidence -= 30  # Very weak

    return max(0, min(100, int(confidence)))

def test_confidence_improvements(symbols, days=60):
    """Test improved confidence on same data"""

    print("=" * 100)
    print("🔧 TESTING IMPROVED CONFIDENCE CALCULATION")
    print("=" * 100)
    print(f"\nTesting {len(symbols)} stocks over {days} trading days\n")

    all_trades = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{days+10}d", interval="1d")

            if df.empty or len(df) < 5:
                continue

            df['PrevClose'] = df['Close'].shift(1)
            df['Gap'] = ((df['Open'] - df['PrevClose']) / df['PrevClose'] * 100)
            df['DayReturn'] = ((df['Close'] - df['Open']) / df['Open'] * 100)

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

                old_conf = calculate_old_confidence(row['Gap'], consistency)
                new_conf = calculate_improved_confidence(row['Gap'], consistency)

                trade = {
                    'symbol': symbol,
                    'date': idx.strftime('%Y-%m-%d'),
                    'gap': row['Gap'],
                    'consistency': consistency * 100,
                    'old_confidence': old_conf,
                    'new_confidence': new_conf,
                    'conf_change': new_conf - old_conf,
                    'day_return': row['DayReturn'],
                    'success': row['DayReturn'] > 0
                }
                all_trades.append(trade)

        except Exception as e:
            continue

    if not all_trades:
        print("❌ No trades found")
        return

    df = pd.DataFrame(all_trades)
    total_trades = len(df)

    # Compare overall performance
    print("=" * 100)
    print("📊 OVERALL COMPARISON")
    print("=" * 100)

    print(f"\nTotal Trades: {total_trades}")
    print(f"Overall Win Rate: {df['success'].sum()/total_trades*100:.1f}%")
    print(f"Overall Avg Return: {df['day_return'].mean():+.2f}%")

    # Performance by confidence - OLD
    print("\n" + "=" * 100)
    print("📉 OLD CONFIDENCE SCORING")
    print("=" * 100)

    confidence_bins = [
        (80, 100, "80-100 (HIGH)"),
        (70, 80, "70-79 (GOOD)"),
        (60, 70, "60-69 (MOD)"),
        (50, 60, "50-59 (LOW-MOD)"),
        (0, 50, "0-49 (LOW)")
    ]

    print(f"{'Confidence':<20} {'Trades':<10} {'Win Rate':<15} {'Avg Return':<15}")
    print("-" * 100)

    for min_conf, max_conf, label in confidence_bins:
        subset = df[(df['old_confidence'] >= min_conf) & (df['old_confidence'] < max_conf)]
        if len(subset) > 0:
            wr = (subset['success'].sum() / len(subset) * 100)
            avg_ret = subset['day_return'].mean()
            print(f"{label:<20} {len(subset):<10} {wr:>6.1f}% ({subset['success'].sum()}/{len(subset)})  {avg_ret:>+7.2f}%")
        else:
            print(f"{label:<20} {0:<10} {'N/A':<15} {'N/A':<15}")

    # Performance by confidence - NEW
    print("\n" + "=" * 100)
    print("📈 NEW IMPROVED CONFIDENCE SCORING")
    print("=" * 100)

    print(f"{'Confidence':<20} {'Trades':<10} {'Win Rate':<15} {'Avg Return':<15}")
    print("-" * 100)

    for min_conf, max_conf, label in confidence_bins:
        subset = df[(df['new_confidence'] >= min_conf) & (df['new_confidence'] < max_conf)]
        if len(subset) > 0:
            wr = (subset['success'].sum() / len(subset) * 100)
            avg_ret = subset['day_return'].mean()
            print(f"{label:<20} {len(subset):<10} {wr:>6.1f}% ({subset['success'].sum()}/{len(subset)})  {avg_ret:>+7.2f}%")
        else:
            print(f"{label:<20} {0:<10} {'N/A':<15} {'N/A':<15}")

    # Show trades that changed significantly
    print("\n" + "=" * 100)
    print("🔄 BIGGEST CONFIDENCE CHANGES")
    print("=" * 100)

    print("\n❌ Trades downgraded (OLD high → NEW lower):")
    downgraded = df[(df['old_confidence'] >= 70) & (df['new_confidence'] < 70)].sort_values('conf_change')
    if len(downgraded) > 0:
        print(f"{'Date':<12} {'Symbol':<8} {'Gap%':<8} {'Cons%':<8} {'OLD':<8} {'NEW':<8} {'Return%':<10} {'Correct?':<10}")
        print("-" * 100)
        for _, trade in downgraded.head(10).iterrows():
            was_loss = not trade['success']
            correct = "✅ YES" if was_loss else "❌ NO"
            print(f"{trade['date']:<12} {trade['symbol']:<8} {trade['gap']:>6.2f}% {trade['consistency']:>6.1f}% {trade['old_confidence']:>5}/100 {trade['new_confidence']:>5}/100 {trade['day_return']:>+8.2f}% {correct:<10}")
    else:
        print("   None")

    print("\n⬆️  Trades upgraded (OLD lower → NEW higher):")
    upgraded = df[(df['old_confidence'] < 70) & (df['new_confidence'] >= 70)].sort_values('conf_change', ascending=False)
    if len(upgraded) > 0:
        print(f"{'Date':<12} {'Symbol':<8} {'Gap%':<8} {'Cons%':<8} {'OLD':<8} {'NEW':<8} {'Return%':<10} {'Correct?':<10}")
        print("-" * 100)
        for _, trade in upgraded.head(10).iterrows():
            was_win = trade['success']
            correct = "✅ YES" if was_win else "❌ NO"
            print(f"{trade['date']:<12} {trade['symbol']:<8} {trade['gap']:>6.2f}% {trade['consistency']:>6.1f}% {trade['old_confidence']:>5}/100 {trade['new_confidence']:>5}/100 {trade['day_return']:>+8.2f}% {correct:<10}")
    else:
        print("   None")

    # Show the problematic 100% consistency trades
    print("\n" + "=" * 100)
    print("🚨 THE 100% CONSISTENCY PROBLEM (All 4 Failed!)")
    print("=" * 100)

    perfect_cons = df[df['consistency'] >= 95]
    if len(perfect_cons) > 0:
        print(f"\n{'Date':<12} {'Symbol':<8} {'Gap%':<8} {'Cons%':<8} {'OLD Conf':<10} {'NEW Conf':<10} {'Return%':<10} {'Result':<10}")
        print("-" * 100)
        for _, trade in perfect_cons.iterrows():
            result = "✅ WIN" if trade['success'] else "❌ LOSS"
            print(f"{trade['date']:<12} {trade['symbol']:<8} {trade['gap']:>6.2f}% {trade['consistency']:>6.1f}% {trade['old_confidence']:>8}/100 {trade['new_confidence']:>8}/100 {trade['day_return']:>+8.2f}% {result:<10}")

        print(f"\nOLD scoring: Avg confidence {perfect_cons['old_confidence'].mean():.1f}")
        print(f"NEW scoring: Avg confidence {perfect_cons['new_confidence'].mean():.1f}")
        print(f"Win rate: {perfect_cons['success'].sum()}/{len(perfect_cons)} ({perfect_cons['success'].sum()/len(perfect_cons)*100:.1f}%)")

    print("\n" + "=" * 100)
    print("💡 VERDICT")
    print("=" * 100)

    # Compare 70+ confidence win rates
    old_70_plus = df[df['old_confidence'] >= 70]
    new_70_plus = df[df['new_confidence'] >= 70]

    if len(old_70_plus) > 0:
        old_wr = old_70_plus['success'].sum() / len(old_70_plus) * 100
        print(f"\nOLD: Confidence ≥70: {len(old_70_plus)} trades, {old_wr:.1f}% win rate")

    if len(new_70_plus) > 0:
        new_wr = new_70_plus['success'].sum() / len(new_70_plus) * 100
        print(f"NEW: Confidence ≥70: {len(new_70_plus)} trades, {new_wr:.1f}% win rate")

    if len(old_70_plus) > 0 and len(new_70_plus) > 0:
        if new_wr > old_wr:
            print(f"\n✅ IMPROVEMENT: Win rate increased by {new_wr - old_wr:.1f}%")
        elif new_wr < old_wr:
            print(f"\n⚠️  Win rate decreased by {old_wr - new_wr:.1f}%")
            print(f"   (But with {len(new_70_plus) - len(old_70_plus):+d} trades - more selective)")

    print("\n" + "=" * 100)

if __name__ == '__main__':
    test_symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'META', 'NVDA', 'AMD', 'TSLA',
        'NFLX', 'AMZN', 'INTC', 'QCOM', 'AVGO',
        'DIS', 'NKE', 'SBUX', 'MCD', 'COST', 'WMT', 'TGT',
        'JNJ', 'PFE', 'MRNA', 'UNH', 'CVS',
        'JPM', 'BAC', 'GS', 'MS', 'V', 'MA',
        'BA', 'CAT', 'GE', 'F', 'GM'
    ]

    test_confidence_improvements(test_symbols, days=60)
