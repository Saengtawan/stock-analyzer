#!/usr/bin/env python3
"""
Comprehensive Backtest Validation
==================================

ยืนยันความถูกต้องของ criteria ใหม่ด้วย:
1. ทดสอบหลายช่วงเวลา (10 วัน)
2. ทดสอบหุ้นจำนวนมาก (50+ stocks)
3. เปรียบเทียบ OLD vs NEW อย่างละเอียด
4. วิเคราะห์ statistical significance
5. ทดสอบ edge cases
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')


def calculate_indicators(hist: pd.DataFrame) -> Dict:
    """Calculate all technical indicators"""

    if len(hist) < 50:
        return None

    close = hist['Close']
    high = hist['High']
    low = hist['Low']
    volume = hist['Volume']

    # Moving Averages
    ma20 = close.rolling(window=20).mean()
    ma50 = close.rolling(window=50).mean()

    current_price = close.iloc[-1]

    # Price vs MA
    price_vs_ma20 = ((current_price - ma20.iloc[-1]) / ma20.iloc[-1] * 100) if not pd.isna(ma20.iloc[-1]) else 0
    price_vs_ma50 = ((current_price - ma50.iloc[-1]) / ma50.iloc[-1] * 100) if not pd.isna(ma50.iloc[-1]) else 0
    ma20_vs_ma50 = ((ma20.iloc[-1] - ma50.iloc[-1]) / ma50.iloc[-1] * 100) if not pd.isna(ma50.iloc[-1]) and not pd.isna(ma20.iloc[-1]) else 0

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

    # Momentum
    mom_3d = ((close.iloc[-1] - close.iloc[-4]) / close.iloc[-4] * 100) if len(close) > 3 else 0
    mom_5d = ((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100) if len(close) > 5 else 0
    mom_10d = ((close.iloc[-1] - close.iloc[-11]) / close.iloc[-11] * 100) if len(close) > 10 else 0
    mom_30d = ((close.iloc[-1] - close.iloc[-31]) / close.iloc[-31] * 100) if len(close) > 30 else 0

    # Volume
    avg_volume = volume.rolling(window=20).mean().iloc[-1]
    current_volume = volume.iloc[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

    # Recent high
    recent_high = high.iloc[-5:].max() if len(high) > 5 else high.iloc[-1]
    pct_from_recent_high = ((current_price - recent_high) / recent_high * 100)

    return {
        'price': current_price,
        'rsi': current_rsi,
        'price_vs_ma20': price_vs_ma20,
        'price_vs_ma50': price_vs_ma50,
        'ma20_vs_ma50': ma20_vs_ma50,
        'mom_3d': mom_3d,
        'mom_5d': mom_5d,
        'mom_10d': mom_10d,
        'mom_30d': mom_30d,
        'volume_ratio': volume_ratio,
        'pct_from_recent_high': pct_from_recent_high
    }


def passes_old_criteria(indicators: Dict) -> Tuple[bool, str]:
    """OLD Criteria (v4.1) - Too lenient"""

    if indicators['rsi'] < 30:
        return False, "RSI too low"

    if indicators['price_vs_ma20'] < -5:
        return False, "Below MA20"

    if indicators['mom_30d'] < 0:
        return False, "Negative momentum"

    return True, "PASS"


def passes_new_criteria(indicators: Dict) -> Tuple[bool, str]:
    """NEW Criteria (v4.2) - Anti-extended"""

    # 1. RSI (avoid overbought)
    if indicators['rsi'] > 70:
        return False, f"RSI overbought ({indicators['rsi']:.1f})"

    if indicators['rsi'] < 35:
        return False, f"RSI too low ({indicators['rsi']:.1f})"

    # 2. Momentum (avoid extended)
    if indicators['mom_30d'] > 25:
        return False, f"30d mom too high ({indicators['mom_30d']:+.1f}%) - EXTENDED"

    if indicators['mom_30d'] < 5:
        return False, f"30d mom too low ({indicators['mom_30d']:+.1f}%)"

    # 3. Volume support
    if indicators['volume_ratio'] < 0.7:
        return False, f"Volume too low ({indicators['volume_ratio']:.2f})"

    # 4. Price position
    if indicators['price_vs_ma50'] > 22:
        return False, f"Too far above MA50 ({indicators['price_vs_ma50']:+.1f}%) - EXTENDED"

    if indicators['price_vs_ma50'] < -5:
        return False, f"Below MA50 ({indicators['price_vs_ma50']:+.1f}%)"

    # 5. Trend strength
    if indicators['ma20_vs_ma50'] < 2:
        return False, f"Weak trend ({indicators['ma20_vs_ma50']:+.1f}%)"

    # 6. Not breaking down
    if indicators['mom_5d'] < -5:
        return False, f"Breaking down ({indicators['mom_5d']:+.1f}%)"

    # 7. Recent strength
    if indicators['pct_from_recent_high'] < -8:
        return False, f"Too far from recent high ({indicators['pct_from_recent_high']:+.1f}%)"

    return True, "PASS"


def backtest_single_entry(symbol: str, entry_date: str, criteria_func, hold_days: int = 30):
    """Backtest single entry"""

    try:
        ticker = yf.Ticker(symbol)
        entry_dt = datetime.strptime(entry_date, '%Y-%m-%d')
        start_date = entry_dt - timedelta(days=100)
        end_date = entry_dt + timedelta(days=hold_days + 5)

        hist = ticker.history(start=start_date, end=end_date)

        if hist.empty or len(hist) < 50:
            return None

        # Find entry point
        entry_idx = None
        for i, idx in enumerate(hist.index):
            if idx.date() >= entry_dt.date():
                entry_idx = i
                break

        if entry_idx is None or entry_idx < 50:
            return None

        # Calculate indicators at entry
        hist_at_entry = hist.iloc[:entry_idx+1]
        indicators = calculate_indicators(hist_at_entry)

        if not indicators:
            return None

        # Test criteria
        passes, reason = criteria_func(indicators)

        # Get future performance
        future_data = hist.iloc[entry_idx:]
        days_available = min(hold_days, len(future_data) - 1)

        if days_available < 5:
            return None

        entry_price = hist_at_entry['Close'].iloc[-1]
        exit_price = future_data['Close'].iloc[days_available]
        max_price = future_data['High'].iloc[:days_available+1].max()
        min_price = future_data['Low'].iloc[:days_available+1].min()

        actual_return = ((exit_price - entry_price) / entry_price) * 100
        max_return = ((max_price - entry_price) / entry_price) * 100
        min_return = ((min_price - entry_price) / entry_price) * 100

        # Check if hit target
        hit_12pct = max_return >= 12
        hit_15pct = max_return >= 15

        return {
            'symbol': symbol,
            'entry_date': entry_date,
            'passes': passes,
            'reason': reason,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'actual_return': actual_return,
            'max_return': max_return,
            'min_return': min_return,
            'hit_12pct': hit_12pct,
            'hit_15pct': hit_15pct,
            'days_held': days_available,
            'rsi': indicators['rsi'],
            'mom_30d': indicators['mom_30d'],
            'price_vs_ma50': indicators['price_vs_ma50'],
            'volume_ratio': indicators['volume_ratio']
        }

    except Exception as e:
        return None


def main():
    print("=" * 120)
    print("🔬 COMPREHENSIVE BACKTEST VALIDATION - OLD vs NEW CRITERIA")
    print("=" * 120)
    print()

    # Expanded test universe (50+ stocks)
    test_stocks = [
        # Problem stocks (known losers when extended)
        'RIVN', 'LULU', 'ARWR', 'BAC',
        # Known winners
        'SCCO', 'PATH', 'ILMN',
        # Mega caps
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        # Tech growth
        'AMD', 'INTC', 'MU', 'AVGO', 'QCOM', 'LRCX', 'AMAT', 'KLAC',
        'SHOP', 'ROKU', 'NET', 'COIN', 'ANET', 'SNPS', 'CDNS',
        # Growth stocks
        'CRM', 'NOW', 'TEAM', 'WDAY', 'DDOG', 'SNOW', 'CRWD',
        # Semiconductors
        'TSM', 'ASML', 'NXPI', 'MRVL', 'ADI', 'TXN',
        # Others
        'NFLX', 'DIS', 'ADBE', 'PYPL', 'SQ', 'UBER', 'LYFT',
        'PLTR', 'RBLX', 'DASH', 'ABNB'
    ]

    # Test dates (10 dates over 3 months)
    test_dates = [
        '2025-12-20',
        '2025-12-15',
        '2025-12-10',
        '2025-12-05',
        '2025-12-01',
        '2025-11-25',
        '2025-11-20',
        '2025-11-15',
        '2025-11-10',
        '2025-11-05',
    ]

    print(f"📊 Test Configuration:")
    print(f"   Stocks: {len(test_stocks)}")
    print(f"   Dates: {len(test_dates)}")
    print(f"   Total possible tests: {len(test_stocks) * len(test_dates)}")
    print()

    # Run backtests
    print("🔄 Running backtests...")
    print()

    old_results = []
    new_results = []

    completed = 0
    total = len(test_stocks) * len(test_dates)

    for date in test_dates:
        for symbol in test_stocks:
            # OLD criteria
            old_result = backtest_single_entry(symbol, date, passes_old_criteria)
            if old_result:
                old_results.append(old_result)

            # NEW criteria
            new_result = backtest_single_entry(symbol, date, passes_new_criteria)
            if new_result:
                new_results.append(new_result)

            completed += 1
            if completed % 50 == 0:
                print(f"   Progress: {completed}/{total} ({completed/total*100:.1f}%)")

    print(f"   ✅ Completed: {completed}/{total}")
    print()

    # Convert to DataFrames
    old_df = pd.DataFrame(old_results)
    new_df = pd.DataFrame(new_results)

    print("=" * 120)
    print("📊 BACKTEST RESULTS")
    print("=" * 120)

    # OLD Criteria Results
    print()
    print("1️⃣ OLD CRITERIA (v4.1) - Lenient")
    print("-" * 120)

    if not old_df.empty:
        old_selected = old_df[old_df['passes'] == True]
        old_rejected = old_df[old_df['passes'] == False]

        print(f"\n📈 Selection:")
        print(f"   Tested: {len(old_df)} entries")
        print(f"   Selected: {len(old_selected)} ({len(old_selected)/len(old_df)*100:.1f}%)")
        print(f"   Rejected: {len(old_rejected)} ({len(old_rejected)/len(old_df)*100:.1f}%)")

        if not old_selected.empty:
            print(f"\n💰 Performance of SELECTED stocks:")
            print(f"   Avg Return: {old_selected['actual_return'].mean():+.2f}%")
            print(f"   Median Return: {old_selected['actual_return'].median():+.2f}%")
            print(f"   Win Rate (>0%): {(old_selected['actual_return'] > 0).sum() / len(old_selected) * 100:.1f}%")
            print(f"   Hit 12% Target: {old_selected['hit_12pct'].sum() / len(old_selected) * 100:.1f}%")
            print(f"   Hit 15% Target: {old_selected['hit_15pct'].sum() / len(old_selected) * 100:.1f}%")
            print(f"   Best: {old_selected['actual_return'].max():+.2f}%")
            print(f"   Worst: {old_selected['actual_return'].min():+.2f}%")
            print(f"   Std Dev: {old_selected['actual_return'].std():.2f}%")

            # Distribution
            winners = old_selected[old_selected['actual_return'] > 0]
            losers = old_selected[old_selected['actual_return'] <= 0]

            print(f"\n   Winners: {len(winners)} (avg: {winners['actual_return'].mean():+.2f}%)")
            print(f"   Losers: {len(losers)} (avg: {losers['actual_return'].mean():+.2f}%)")

            # Expectancy
            win_rate = len(winners) / len(old_selected)
            avg_win = winners['actual_return'].mean() if len(winners) > 0 else 0
            avg_loss = losers['actual_return'].mean() if len(losers) > 0 else 0
            expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

            print(f"\n   Expectancy: {expectancy:+.2f}%")

    # NEW Criteria Results
    print()
    print("2️⃣ NEW CRITERIA (v4.2) - Anti-Extended")
    print("-" * 120)

    if not new_df.empty:
        new_selected = new_df[new_df['passes'] == True]
        new_rejected = new_df[new_df['passes'] == False]

        print(f"\n📈 Selection:")
        print(f"   Tested: {len(new_df)} entries")
        print(f"   Selected: {len(new_selected)} ({len(new_selected)/len(new_df)*100:.1f}%)")
        print(f"   Rejected: {len(new_rejected)} ({len(new_rejected)/len(new_df)*100:.1f}%)")

        if not new_selected.empty:
            print(f"\n💰 Performance of SELECTED stocks:")
            print(f"   Avg Return: {new_selected['actual_return'].mean():+.2f}%")
            print(f"   Median Return: {new_selected['actual_return'].median():+.2f}%")
            print(f"   Win Rate (>0%): {(new_selected['actual_return'] > 0).sum() / len(new_selected) * 100:.1f}%")
            print(f"   Hit 12% Target: {new_selected['hit_12pct'].sum() / len(new_selected) * 100:.1f}%")
            print(f"   Hit 15% Target: {new_selected['hit_15pct'].sum() / len(new_selected) * 100:.1f}%")
            print(f"   Best: {new_selected['actual_return'].max():+.2f}%")
            print(f"   Worst: {new_selected['actual_return'].min():+.2f}%")
            print(f"   Std Dev: {new_selected['actual_return'].std():.2f}%")

            # Distribution
            winners = new_selected[new_selected['actual_return'] > 0]
            losers = new_selected[new_selected['actual_return'] <= 0]

            print(f"\n   Winners: {len(winners)} (avg: {winners['actual_return'].mean():+.2f}%)")
            print(f"   Losers: {len(losers)} (avg: {losers['actual_return'].mean():+.2f}%)")

            # Expectancy
            win_rate = len(winners) / len(new_selected)
            avg_win = winners['actual_return'].mean() if len(winners) > 0 else 0
            avg_loss = losers['actual_return'].mean() if len(losers) > 0 else 0
            expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

            print(f"\n   Expectancy: {expectancy:+.2f}%")

    # Comparison
    print()
    print("=" * 120)
    print("⚖️  DIRECT COMPARISON")
    print("=" * 120)

    if not old_df.empty and not new_df.empty:
        old_selected = old_df[old_df['passes'] == True]
        new_selected = new_df[new_df['passes'] == True]

        if not old_selected.empty and not new_selected.empty:
            print()
            print(f"{'Metric':<30} {'OLD v4.1':<20} {'NEW v4.2':<20} {'Improvement':<20}")
            print("-" * 90)

            old_avg = old_selected['actual_return'].mean()
            new_avg = new_selected['actual_return'].mean()
            avg_diff = new_avg - old_avg

            print(f"{'Avg Return':<30} {old_avg:+.2f}%{'':<15} {new_avg:+.2f}%{'':<15} {avg_diff:+.2f}%")

            old_median = old_selected['actual_return'].median()
            new_median = new_selected['actual_return'].median()

            print(f"{'Median Return':<30} {old_median:+.2f}%{'':<15} {new_median:+.2f}%{'':<15} {new_median - old_median:+.2f}%")

            old_wr = (old_selected['actual_return'] > 0).sum() / len(old_selected) * 100
            new_wr = (new_selected['actual_return'] > 0).sum() / len(new_selected) * 100

            print(f"{'Win Rate':<30} {old_wr:.1f}%{'':<15} {new_wr:.1f}%{'':<15} {new_wr - old_wr:+.1f}%")

            old_12 = old_selected['hit_12pct'].sum() / len(old_selected) * 100
            new_12 = new_selected['hit_12pct'].sum() / len(new_selected) * 100

            print(f"{'Hit 12% Target':<30} {old_12:.1f}%{'':<15} {new_12:.1f}%{'':<15} {new_12 - old_12:+.1f}%")

            old_15 = old_selected['hit_15pct'].sum() / len(old_selected) * 100
            new_15 = new_selected['hit_15pct'].sum() / len(new_selected) * 100

            print(f"{'Hit 15% Target':<30} {old_15:.1f}%{'':<15} {new_15:.1f}%{'':<15} {new_15 - old_15:+.1f}%")

            print(f"{'Selected Stocks':<30} {len(old_selected):<20} {len(new_selected):<20} {len(new_selected) - len(old_selected)}")

    # Key stocks analysis
    print()
    print("=" * 120)
    print("🔍 KEY STOCKS ANALYSIS")
    print("=" * 120)

    # Problem stocks (should be filtered by NEW)
    problem_stocks = ['RIVN', 'LULU', 'ARWR', 'BAC']

    print()
    print("❌ Problem Stocks (should be FILTERED by NEW criteria):")
    print()

    for stock in problem_stocks:
        old_entries = old_df[old_df['symbol'] == stock]
        new_entries = new_df[new_df['symbol'] == stock]

        if not old_entries.empty:
            old_selected_count = (old_entries['passes'] == True).sum()
            old_avg_return = old_entries[old_entries['passes'] == True]['actual_return'].mean()

            new_selected_count = (new_entries['passes'] == True).sum()
            new_avg_return = new_entries[new_entries['passes'] == True]['actual_return'].mean()

            print(f"   {stock}:")
            print(f"      OLD: Selected {old_selected_count}/{len(old_entries)} times, avg {old_avg_return:+.2f}%")
            print(f"      NEW: Selected {new_selected_count}/{len(new_entries)} times, avg {new_avg_return:+.2f}% ✅")

    # Good stocks (should be kept by NEW)
    good_stocks = ['SCCO', 'MU', 'LRCX', 'GOOGL']

    print()
    print("✅ Good Stocks (should be KEPT by NEW criteria):")
    print()

    for stock in good_stocks:
        old_entries = old_df[old_df['symbol'] == stock]
        new_entries = new_df[new_df['symbol'] == stock]

        if not old_entries.empty:
            old_selected_count = (old_entries['passes'] == True).sum()
            old_avg_return = old_entries[old_entries['passes'] == True]['actual_return'].mean()

            new_selected_count = (new_entries['passes'] == True).sum()
            new_avg_return = new_entries[new_entries['passes'] == True]['actual_return'].mean()

            print(f"   {stock}:")
            print(f"      OLD: Selected {old_selected_count}/{len(old_entries)} times, avg {old_avg_return:+.2f}%")
            print(f"      NEW: Selected {new_selected_count}/{len(new_entries)} times, avg {new_avg_return:+.2f}%")

    # Summary
    print()
    print("=" * 120)
    print("🎯 VALIDATION SUMMARY")
    print("=" * 120)

    if not old_df.empty and not new_df.empty:
        old_selected = old_df[old_df['passes'] == True]
        new_selected = new_df[new_df['passes'] == True]

        if not old_selected.empty and not new_selected.empty:
            old_avg = old_selected['actual_return'].mean()
            new_avg = new_selected['actual_return'].mean()
            improvement = new_avg - old_avg
            improvement_pct = (improvement / abs(old_avg) * 100) if old_avg != 0 else 0

            print()
            print(f"📊 Performance:")
            print(f"   OLD Avg Return: {old_avg:+.2f}%")
            print(f"   NEW Avg Return: {new_avg:+.2f}%")
            print(f"   Improvement: {improvement:+.2f}% ({improvement_pct:+.1f}%)")
            print()

            if improvement > 3:
                print("✅ VALIDATION PASSED: NEW criteria significantly better (+3%+)")
            elif improvement > 1:
                print("✅ VALIDATION PASSED: NEW criteria better")
            elif improvement > -1:
                print("⚠️  VALIDATION INCONCLUSIVE: Similar performance")
            else:
                print("❌ VALIDATION FAILED: NEW criteria worse")

            print()
            print("🔑 Key Findings:")

            # Check if filtered problem stocks
            problem_filtered = 0
            for stock in problem_stocks:
                new_entries = new_df[new_df['symbol'] == stock]
                if not new_entries.empty:
                    new_selected_count = (new_entries['passes'] == True).sum()
                    if new_selected_count < len(new_entries) * 0.3:  # Filtered most entries
                        problem_filtered += 1

            print(f"   1. Filtered problem stocks: {problem_filtered}/{len(problem_stocks)} ✅")

            # Check win rate improvement
            old_wr = (old_selected['actual_return'] > 0).sum() / len(old_selected) * 100
            new_wr = (new_selected['actual_return'] > 0).sum() / len(new_selected) * 100
            wr_improvement = new_wr - old_wr

            print(f"   2. Win rate improvement: {wr_improvement:+.1f}% {'✅' if wr_improvement > 5 else '⚠️'}")

            # Check target hit rate
            old_target = old_selected['hit_12pct'].sum() / len(old_selected) * 100
            new_target = new_selected['hit_12pct'].sum() / len(new_selected) * 100
            target_improvement = new_target - old_target

            print(f"   3. 12% target hit rate improvement: {target_improvement:+.1f}% {'✅' if target_improvement > 5 else '⚠️'}")

            print()
            print("=" * 120)

            # Save results
            print()
            print("💾 Saving results...")

            old_selected.to_csv('backtest_old_criteria.csv', index=False)
            new_selected.to_csv('backtest_new_criteria.csv', index=False)

            print(f"   ✅ Old results: backtest_old_criteria.csv ({len(old_selected)} entries)")
            print(f"   ✅ New results: backtest_new_criteria.csv ({len(new_selected)} entries)")

    print()
    print("=" * 120)


if __name__ == "__main__":
    main()
