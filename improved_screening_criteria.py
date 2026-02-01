#!/usr/bin/env python3
"""
Improved Screening Criteria v4.2
=================================

Based on diagnosis, the main problem is:
❌ OLD: Selected "extended" stocks (high RSI, high momentum, already up 30-40%)
✅ NEW: Select "healthy momentum" stocks (moderate RSI, sustainable momentum)

Key Changes:
1. ❌ Avoid overbought (RSI > 70)
2. ❌ Avoid over-extended (30d momentum > 25%)
3. ✅ Require volume support (volume ratio > 0.8)
4. ✅ Prefer moderate momentum (10-25% in 30d)
5. ✅ Prefer stocks not too far from MA50 (< 20%)

จะ backtest เปรียบเทียบ:
- OLD criteria (v4.1)
- NEW criteria (v4.2)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))


def calculate_indicators(hist: pd.DataFrame) -> Dict:
    """คำนวณ indicators"""

    if len(hist) < 50:
        return None

    close = hist['Close']
    high = hist['High']
    low = hist['Low']
    volume = hist['Volume']

    # MA
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
    mom_5d = ((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100) if len(close) > 5 else 0
    mom_10d = ((close.iloc[-1] - close.iloc[-11]) / close.iloc[-11] * 100) if len(close) > 10 else 0
    mom_30d = ((close.iloc[-1] - close.iloc[-31]) / close.iloc[-31] * 100) if len(close) > 30 else 0

    # Volume
    avg_volume = volume.rolling(window=20).mean().iloc[-1]
    current_volume = volume.iloc[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

    # ATR %
    high_low = high - low
    high_close = np.abs(high - close.shift())
    low_close = np.abs(low - close.shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=14).mean().iloc[-1]
    atr_pct = (atr / current_price * 100) if current_price > 0 else 0

    return {
        'price': current_price,
        'rsi': current_rsi,
        'price_vs_ma20': price_vs_ma20,
        'price_vs_ma50': price_vs_ma50,
        'ma20_vs_ma50': ma20_vs_ma50,
        'mom_5d': mom_5d,
        'mom_10d': mom_10d,
        'mom_30d': mom_30d,
        'volume_ratio': volume_ratio,
        'atr_pct': atr_pct,
    }


def passes_old_criteria(indicators: Dict) -> tuple[bool, str]:
    """
    OLD Criteria (v4.1) - เลือกหุ้นที่ขึ้นมามากแล้ว

    ปัญหา: ไม่มีการป้องกัน overbought และ over-extended
    """

    # Basic filters only
    if indicators['rsi'] < 30:
        return False, "RSI too low"

    if indicators['price_vs_ma20'] < -5:
        return False, "Below MA20"

    if indicators['mom_30d'] < 0:
        return False, "Negative momentum"

    return True, "PASS"


def passes_new_criteria(indicators: Dict) -> tuple[bool, str]:
    """
    NEW Criteria (v4.2) - ป้องกัน extended stocks

    Key changes:
    1. ❌ Avoid overbought (RSI > 70)
    2. ❌ Avoid over-extended (30d mom > 25%)
    3. ✅ Require volume support (volume ratio > 0.8)
    4. ✅ Prefer moderate momentum (10-25%)
    5. ✅ Not too extended from MA50 (< 20%)
    """

    # 1. RSI filter (avoid overbought)
    if indicators['rsi'] > 70:
        return False, f"RSI too high ({indicators['rsi']:.1f} > 70) - OVERBOUGHT"

    if indicators['rsi'] < 35:
        return False, f"RSI too low ({indicators['rsi']:.1f} < 35)"

    # 2. Momentum filter (avoid over-extended)
    if indicators['mom_30d'] > 25:
        return False, f"30d momentum too high ({indicators['mom_30d']:+.1f}% > 25%) - EXTENDED"

    if indicators['mom_30d'] < 5:
        return False, f"30d momentum too low ({indicators['mom_30d']:+.1f}% < 5%)"

    # 3. Volume support
    if indicators['volume_ratio'] < 0.8:
        return False, f"Volume too low ({indicators['volume_ratio']:.2f} < 0.8) - NO SUPPORT"

    # 4. Price position (not too extended from MA50)
    if indicators['price_vs_ma50'] > 20:
        return False, f"Too far above MA50 ({indicators['price_vs_ma50']:+.1f}% > 20%) - EXTENDED"

    if indicators['price_vs_ma50'] < -5:
        return False, f"Below MA50 ({indicators['price_vs_ma50']:+.1f}% < -5%)"

    # 5. Trend strength (MA20 above MA50)
    if indicators['ma20_vs_ma50'] < 2:
        return False, f"Weak trend (MA20 vs MA50: {indicators['ma20_vs_ma50']:+.1f}% < 2%)"

    # 6. Short-term momentum (not breaking down)
    if indicators['mom_5d'] < -3:
        return False, f"Breaking down ({indicators['mom_5d']:+.1f}% < -3%)"

    return True, "PASS"


def backtest_criteria(symbols: List[str], entry_date: str, criteria_func, criteria_name: str):
    """
    Backtest criteria

    Returns:
        List of results
    """
    print(f"\nTesting {criteria_name}...")
    print("-" * 80)

    results = []

    for symbol in symbols:
        try:
            # Get data
            ticker = yf.Ticker(symbol)
            entry_dt = datetime.strptime(entry_date, '%Y-%m-%d')
            start_date = entry_dt - timedelta(days=90)
            end_date = entry_dt + timedelta(days=35)

            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty or len(hist) < 50:
                continue

            # Find entry point
            entry_idx = None
            for i, idx in enumerate(hist.index):
                if idx.date() >= entry_dt.date():
                    entry_idx = i
                    break

            if entry_idx is None or entry_idx < 50:
                continue

            # Get indicators at entry
            hist_at_entry = hist.iloc[:entry_idx+1]
            indicators = calculate_indicators(hist_at_entry)

            if not indicators:
                continue

            # Test criteria
            passes, reason = criteria_func(indicators)

            # Get future performance
            future_data = hist.iloc[entry_idx:]
            days_available = min(30, len(future_data) - 1)

            if days_available < 5:
                continue

            entry_price = hist_at_entry['Close'].iloc[-1]
            exit_price = future_data['Close'].iloc[days_available]
            max_price = future_data['High'].iloc[:days_available+1].max()

            actual_return = ((exit_price - entry_price) / entry_price) * 100
            max_return = ((max_price - entry_price) / entry_price) * 100

            results.append({
                'symbol': symbol,
                'passes': passes,
                'reason': reason,
                'actual_return': actual_return,
                'max_return': max_return,
                'rsi': indicators['rsi'],
                'mom_30d': indicators['mom_30d'],
                'price_vs_ma50': indicators['price_vs_ma50'],
                'volume_ratio': indicators['volume_ratio']
            })

            status = "✅ PASS" if passes else "❌ FAIL"
            print(f"   {symbol:<6} {status:<10} {reason:<50} Return: {actual_return:+.1f}%")

        except Exception as e:
            print(f"   {symbol:<6} ❌ ERROR: {e}")
            continue

    return results


def main():
    print("=" * 100)
    print("🧪 TESTING OLD vs NEW SCREENING CRITERIA")
    print("=" * 100)
    print()

    # Test stocks
    test_stocks = [
        # Losers (selected but lost)
        'RIVN', 'LULU', 'ARWR', 'BAC',
        # Winners (missed)
        'SCCO', 'PATH', 'ILMN',
        # Other stocks
        'NVDA', 'TSLA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMD', 'MU', 'INTC',
        # Additional test
        'SHOP', 'ROKU', 'NET', 'COIN', 'AVGO', 'QCOM', 'LRCX'
    ]

    entry_date = '2025-12-20'

    # Test OLD criteria
    print("\n" + "=" * 100)
    print("1️⃣ OLD CRITERIA (v4.1) - Allow everything")
    print("=" * 100)

    old_results = backtest_criteria(test_stocks, entry_date, passes_old_criteria, "OLD v4.1")

    # Test NEW criteria
    print("\n" + "=" * 100)
    print("2️⃣ NEW CRITERIA (v4.2) - Avoid extended stocks")
    print("=" * 100)

    new_results = backtest_criteria(test_stocks, entry_date, passes_new_criteria, "NEW v4.2")

    # Compare results
    print("\n" + "=" * 100)
    print("📊 COMPARISON")
    print("=" * 100)

    old_df = pd.DataFrame(old_results)
    new_df = pd.DataFrame(new_results)

    # OLD criteria performance
    if not old_df.empty:
        old_selected = old_df[old_df['passes'] == True]

        print(f"\n📊 OLD Criteria (v4.1):")
        print(f"   Selected: {len(old_selected)}/{len(old_df)}")

        if not old_selected.empty:
            print(f"   Avg Return: {old_selected['actual_return'].mean():+.2f}%")
            print(f"   Win Rate: {(old_selected['actual_return'] > 0).sum() / len(old_selected) * 100:.1f}%")
            print(f"   Best: {old_selected['actual_return'].max():+.2f}%")
            print(f"   Worst: {old_selected['actual_return'].min():+.2f}%")

            # Show selected stocks
            print(f"\n   Selected stocks:")
            for _, row in old_selected.iterrows():
                print(f"   - {row['symbol']}: {row['actual_return']:+.2f}% (RSI: {row['rsi']:.0f}, Mom30d: {row['mom_30d']:+.0f}%)")

    # NEW criteria performance
    if not new_df.empty:
        new_selected = new_df[new_df['passes'] == True]

        print(f"\n📊 NEW Criteria (v4.2):")
        print(f"   Selected: {len(new_selected)}/{len(new_df)}")

        if not new_selected.empty:
            print(f"   Avg Return: {new_selected['actual_return'].mean():+.2f}%")
            print(f"   Win Rate: {(new_selected['actual_return'] > 0).sum() / len(new_selected) * 100:.1f}%")
            print(f"   Best: {new_selected['actual_return'].max():+.2f}%")
            print(f"   Worst: {new_selected['actual_return'].min():+.2f}%")

            # Show selected stocks
            print(f"\n   Selected stocks:")
            for _, row in new_selected.iterrows():
                print(f"   - {row['symbol']}: {row['actual_return']:+.2f}% (RSI: {row['rsi']:.0f}, Mom30d: {row['mom_30d']:+.0f}%)")

    # Show what changed
    print("\n" + "=" * 100)
    print("🔄 WHAT CHANGED?")
    print("=" * 100)

    if not old_df.empty and not new_df.empty:
        # Merge to compare
        comparison = old_df.merge(new_df, on='symbol', suffixes=('_old', '_new'))

        # Stocks filtered out by NEW criteria
        filtered_out = comparison[(comparison['passes_old'] == True) & (comparison['passes_new'] == False)]

        if not filtered_out.empty:
            print(f"\n❌ Stocks FILTERED OUT by new criteria ({len(filtered_out)}):")
            for _, row in filtered_out.iterrows():
                print(f"   - {row['symbol']}: Return {row['actual_return_old']:+.2f}% | Reason: {row['reason_new']}")

        # Stocks newly selected
        newly_selected = comparison[(comparison['passes_old'] == False) & (comparison['passes_new'] == True)]

        if not newly_selected.empty:
            print(f"\n✅ Stocks NEWLY SELECTED ({len(newly_selected)}):")
            for _, row in newly_selected.iterrows():
                print(f"   - {row['symbol']}: Return {row['actual_return_new']:+.2f}%")

    # Summary
    print("\n" + "=" * 100)
    print("🎯 SUMMARY & RECOMMENDATIONS")
    print("=" * 100)

    if not old_df.empty and not new_df.empty:
        old_selected = old_df[old_df['passes'] == True]
        new_selected = new_df[new_df['passes'] == True]

        if not old_selected.empty and not new_selected.empty:
            old_avg = old_selected['actual_return'].mean()
            new_avg = new_selected['actual_return'].mean()

            improvement = new_avg - old_avg

            print(f"\nPerformance improvement: {improvement:+.2f}%")
            print(f"   OLD: {old_avg:+.2f}% avg return")
            print(f"   NEW: {new_avg:+.2f}% avg return")

            if improvement > 3:
                print("\n✅ NEW criteria significantly better! (+3%)")
            elif improvement > 0:
                print("\n✅ NEW criteria slightly better")
            else:
                print("\n⚠️  NEW criteria needs more tuning")

    print("\n" + "=" * 100)
    print("\n💡 Recommended actions:")
    print("   1. ✅ Implement NEW criteria (v4.2) in screener")
    print("   2. ✅ Add filters:")
    print("      - RSI < 70 (avoid overbought)")
    print("      - 30d momentum < 25% (avoid extended)")
    print("      - Volume ratio > 0.8 (require support)")
    print("      - Price vs MA50 < 20% (not too extended)")
    print("   3. 🧪 Backtest on more dates to confirm")
    print()
    print("=" * 100)


if __name__ == "__main__":
    main()
