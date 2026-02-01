#!/usr/bin/env python3
"""
Final Criteria Backtest - Multiple Dates
=========================================

จะทดสอบ criteria ใหม่กับหลายวันเพื่อให้มั่นใจว่าใช้ได้จริง

Test dates:
1. 2025-12-20 (เดิม)
2. 2025-12-01
3. 2025-11-15
4. 2025-11-01
5. 2025-10-15

และปรับ criteria เล็กน้อย:
- Volume ratio: 0.8 → 0.7 (ไม่เข้มเกินไป, ไม่พลาด GOOGL)
- Price vs MA50: 20% → 22% (ไม่เข้มเกินไป, ไม่พลาด MU)
- เพิ่มการตรวจ short-term breakdown
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List


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
    mom_3d = ((close.iloc[-1] - close.iloc[-4]) / close.iloc[-4] * 100) if len(close) > 3 else 0
    mom_5d = ((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100) if len(close) > 5 else 0
    mom_10d = ((close.iloc[-1] - close.iloc[-11]) / close.iloc[-11] * 100) if len(close) > 10 else 0
    mom_30d = ((close.iloc[-1] - close.iloc[-31]) / close.iloc[-31] * 100) if len(close) > 30 else 0

    # Volume
    avg_volume = volume.rolling(window=20).mean().iloc[-1]
    current_volume = volume.iloc[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

    # Recent price action
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


def passes_final_criteria(indicators: Dict) -> tuple[bool, str]:
    """
    FINAL Criteria (v4.2 Refined)

    Key filters:
    1. RSI: 35-70 (avoid overbought)
    2. 30d momentum: 5-25% (avoid extended)
    3. Volume ratio: > 0.7 (slightly relaxed)
    4. Price vs MA50: < 22% (slightly relaxed)
    5. Trend strength: MA20 vs MA50 > 2%
    6. Not breaking down: 5d momentum > -5%
    7. Not too far from recent high: > -8%
    """

    # 1. RSI filter
    if indicators['rsi'] > 70:
        return False, f"RSI overbought ({indicators['rsi']:.1f} > 70)"

    if indicators['rsi'] < 35:
        return False, f"RSI too low ({indicators['rsi']:.1f} < 35)"

    # 2. Momentum filter (avoid extended)
    if indicators['mom_30d'] > 25:
        return False, f"30d momentum too high ({indicators['mom_30d']:+.1f}% > 25%) - EXTENDED"

    if indicators['mom_30d'] < 5:
        return False, f"30d momentum too low ({indicators['mom_30d']:+.1f}% < 5%)"

    # 3. Volume support (relaxed)
    if indicators['volume_ratio'] < 0.7:
        return False, f"Volume too low ({indicators['volume_ratio']:.2f} < 0.7)"

    # 4. Price position (relaxed)
    if indicators['price_vs_ma50'] > 22:
        return False, f"Too far above MA50 ({indicators['price_vs_ma50']:+.1f}% > 22%) - EXTENDED"

    if indicators['price_vs_ma50'] < -5:
        return False, f"Below MA50 ({indicators['price_vs_ma50']:+.1f}% < -5%)"

    # 5. Trend strength
    if indicators['ma20_vs_ma50'] < 2:
        return False, f"Weak trend (MA20 vs MA50: {indicators['ma20_vs_ma50']:+.1f}% < 2%)"

    # 6. Short-term momentum (not breaking down)
    if indicators['mom_5d'] < -5:
        return False, f"Breaking down ({indicators['mom_5d']:+.1f}% < -5%)"

    # 7. Not too far from recent high (catching TSLA problem)
    if indicators['pct_from_recent_high'] < -8:
        return False, f"Too far from recent high ({indicators['pct_from_recent_high']:+.1f}% < -8%) - WEAKENING"

    return True, "PASS"


def backtest_single_date(symbols: List[str], entry_date: str):
    """Backtest for single date"""

    results = []

    for symbol in symbols:
        try:
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
            passes, reason = passes_final_criteria(indicators)

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
                'entry_date': entry_date,
                'passes': passes,
                'reason': reason,
                'actual_return': actual_return,
                'max_return': max_return,
            })

        except Exception as e:
            continue

    return results


def main():
    print("=" * 100)
    print("🧪 FINAL CRITERIA BACKTEST - MULTIPLE DATES")
    print("=" * 100)
    print()

    # Test stocks
    test_stocks = [
        # Problematic stocks
        'RIVN', 'LULU', 'ARWR', 'BAC',  # Losers
        'SCCO', 'PATH', 'ILMN',  # Winners (should select)
        # Big tech
        'NVDA', 'TSLA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMD', 'MU', 'INTC',
        # Growth stocks
        'SHOP', 'ROKU', 'NET', 'COIN', 'AVGO', 'QCOM', 'LRCX', 'ANET',
    ]

    # Test dates
    test_dates = [
        '2025-12-20',
        '2025-12-01',
        '2025-11-15',
        '2025-11-01',
        '2025-10-15',
    ]

    all_results = []

    for date in test_dates:
        print(f"\n📅 Testing date: {date}")
        print("-" * 100)

        results = backtest_single_date(test_stocks, date)

        if not results:
            print("   No results")
            continue

        # Analyze results
        df = pd.DataFrame(results)
        selected = df[df['passes'] == True]

        print(f"   Total analyzed: {len(df)}")
        print(f"   Selected: {len(selected)}")

        if not selected.empty:
            avg_return = selected['actual_return'].mean()
            win_rate = (selected['actual_return'] > 0).sum() / len(selected) * 100
            print(f"   Avg Return: {avg_return:+.2f}%")
            print(f"   Win Rate: {win_rate:.1f}%")

            # Show top picks
            print(f"\n   Top picks:")
            top_picks = selected.nlargest(5, 'actual_return')
            for _, row in top_picks.iterrows():
                print(f"   - {row['symbol']}: {row['actual_return']:+.2f}%")

        all_results.extend(results)

    # Overall summary
    print("\n" + "=" * 100)
    print("📊 OVERALL SUMMARY (All Dates)")
    print("=" * 100)

    if all_results:
        all_df = pd.DataFrame(all_results)
        all_selected = all_df[all_df['passes'] == True]

        print(f"\nTotal tests: {len(all_df)}")
        print(f"Total selected: {len(all_selected)}")

        if not all_selected.empty:
            avg_return = all_selected['actual_return'].mean()
            median_return = all_selected['actual_return'].median()
            win_rate = (all_selected['actual_return'] > 0).sum() / len(all_selected) * 100

            print(f"\nPerformance:")
            print(f"   Avg Return: {avg_return:+.2f}%")
            print(f"   Median Return: {median_return:+.2f}%")
            print(f"   Win Rate: {win_rate:.1f}%")
            print(f"   Best: {all_selected['actual_return'].max():+.2f}%")
            print(f"   Worst: {all_selected['actual_return'].min():+.2f}%")

            # By stock performance
            print(f"\nBest performing stocks (across all dates):")
            stock_perf = all_selected.groupby('symbol')['actual_return'].agg(['count', 'mean']).sort_values('mean', ascending=False)
            for symbol, row in stock_perf.head(10).iterrows():
                print(f"   {symbol}: {row['mean']:+.2f}% avg ({int(row['count'])} times selected)")

    print()
    print("=" * 100)
    print("🎯 FINAL RECOMMENDATIONS")
    print("=" * 100)
    print()

    if all_results and not all_selected.empty:
        avg_return = all_selected['actual_return'].mean()
        win_rate = (all_selected['actual_return'] > 0).sum() / len(all_selected) * 100

        print("Criteria Performance:")
        print(f"   Avg Return: {avg_return:+.2f}%")
        print(f"   Win Rate: {win_rate:.1f}%")
        print()

        if avg_return > 5 and win_rate > 55:
            print("✅ EXCELLENT: Criteria are working well!")
            print("   → Implement in production screener")
        elif avg_return > 3 and win_rate > 50:
            print("✅ GOOD: Criteria show promise")
            print("   → Consider implementing with monitoring")
        else:
            print("⚠️  NEEDS IMPROVEMENT")
            print("   → Review and adjust thresholds")

    print()
    print("Key Filters to Implement:")
    print("   1. RSI: 35-70 (avoid overbought)")
    print("   2. 30d Momentum: 5-25% (avoid extended)")
    print("   3. Volume Ratio: > 0.7")
    print("   4. Price vs MA50: < 22%")
    print("   5. Trend: MA20 vs MA50 > 2%")
    print("   6. Not breaking down: 5d momentum > -5%")
    print("   7. Not far from recent high: > -8%")
    print()
    print("=" * 100)


if __name__ == "__main__":
    main()
