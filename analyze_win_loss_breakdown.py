#!/usr/bin/env python3
"""
Detailed Win/Loss Analysis: แพ้เพราะไม่ถึง target vs แพ้เพราะติดลบ
"""

import yfinance as yf
import pandas as pd
import numpy as np

# v7.1 Winners + some additional stocks
TEST_STOCKS = [
    'GOOGL', 'META', 'DASH', 'TEAM', 'ROKU', 'TSM', 'LRCX',  # v7.1 Winners
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'TSLA',  # Mega caps
    'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG',   # High growth
    'AMD', 'AVGO', 'QCOM', 'AMAT', 'KLAC',   # Semiconductors
    'UBER', 'ABNB', 'COIN', 'SHOP',          # Consumer tech
]


def detailed_analysis(symbol, timeframe_days, target_pct):
    """Detailed win/loss analysis for a single stock"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='6mo')

        if hist.empty or len(hist) < timeframe_days + 10:
            return None

        entry_price = hist['Close'].iloc[-timeframe_days]
        current_price = hist['Close'].iloc[-1]
        max_high = hist['High'].iloc[-timeframe_days:].max()
        min_low = hist['Low'].iloc[-timeframe_days:].min()

        actual_return = ((current_price - entry_price) / entry_price) * 100
        max_return = ((max_high - entry_price) / entry_price) * 100
        max_drawdown = ((min_low - entry_price) / entry_price) * 100

        reached_target = max_return >= target_pct

        # Categorize outcome
        if reached_target:
            outcome = 'WIN'
        elif actual_return > 0:
            outcome = 'MISS_POSITIVE'  # ไม่ถึง target แต่กำไร
        else:
            outcome = 'LOSS_NEGATIVE'  # ติดลบจริงๆ

        return {
            'symbol': symbol,
            'timeframe': timeframe_days,
            'target': target_pct,
            'entry': entry_price,
            'current': current_price,
            'actual_return': actual_return,
            'max_return': max_return,
            'max_drawdown': max_drawdown,
            'reached_target': reached_target,
            'outcome': outcome
        }

    except Exception as e:
        return None


def run_analysis():
    """Run detailed win/loss analysis"""

    print("=" * 100)
    print("🔍 DETAILED WIN/LOSS BREAKDOWN: แพ้เพราะไม่ถึง target vs แพ้เพราะติดลบ")
    print("=" * 100)

    configs = [
        (14, 5.0, '14 วัน @ 5%'),
        (30, 10.0, '30 วัน @ 10%'),
        (30, 5.0, '30 วัน @ 5% (baseline)'),
    ]

    for timeframe, target, name in configs:
        print(f"\n{'='*100}")
        print(f"📊 {name}")
        print(f"{'='*100}")

        results = []
        for symbol in TEST_STOCKS:
            result = detailed_analysis(symbol, timeframe, target)
            if result:
                results.append(result)

        if not results:
            continue

        # Categorize results
        wins = [r for r in results if r['outcome'] == 'WIN']
        miss_positive = [r for r in results if r['outcome'] == 'MISS_POSITIVE']
        loss_negative = [r for r in results if r['outcome'] == 'LOSS_NEGATIVE']

        total = len(results)
        win_rate = len(wins) / total * 100
        miss_positive_rate = len(miss_positive) / total * 100
        loss_negative_rate = len(loss_negative) / total * 100

        # Calculate averages
        avg_win = np.mean([r['max_return'] for r in wins]) if wins else 0
        avg_miss_positive = np.mean([r['actual_return'] for r in miss_positive]) if miss_positive else 0
        avg_loss_negative = np.mean([r['actual_return'] for r in loss_negative]) if loss_negative else 0

        # Print summary
        print(f"\n📈 Summary:")
        print(f"  Total: {total} stocks\n")

        print(f"  ✅ WIN (ถึง target):           {len(wins):2d} ({win_rate:5.1f}%)")
        print(f"     Average return: {avg_win:+.2f}%")
        if wins:
            print(f"     Range: {min(r['max_return'] for r in wins):+.1f}% to {max(r['max_return'] for r in wins):+.1f}%")
        print()

        print(f"  ⚠️  MISS (ไม่ถึง แต่กำไร):      {len(miss_positive):2d} ({miss_positive_rate:5.1f}%)")
        print(f"     Average return: {avg_miss_positive:+.2f}%")
        if miss_positive:
            print(f"     Range: {min(r['actual_return'] for r in miss_positive):+.1f}% to {max(r['actual_return'] for r in miss_positive):+.1f}%")
        print()

        print(f"  ❌ LOSS (ติดลบจริงๆ):          {len(loss_negative):2d} ({loss_negative_rate:5.1f}%)")
        print(f"     Average return: {avg_loss_negative:+.2f}%")
        if loss_negative:
            print(f"     Range: {min(r['actual_return'] for r in loss_negative):+.1f}% to {max(r['actual_return'] for r in loss_negative):+.1f}%")
        print()

        # Detailed breakdown
        print(f"\n📋 Detailed Breakdown:\n")

        if wins:
            print(f"  ✅ WINS ({len(wins)}):")
            for r in sorted(wins, key=lambda x: x['max_return'], reverse=True):
                print(f"     {r['symbol']:6s}: {r['max_return']:+6.1f}% max (current: {r['actual_return']:+5.1f}%)")

        if miss_positive:
            print(f"\n  ⚠️  MISS POSITIVE ({len(miss_positive)}) - ไม่ถึง target แต่ยังได้กำไร:")
            for r in sorted(miss_positive, key=lambda x: x['actual_return'], reverse=True):
                print(f"     {r['symbol']:6s}: {r['actual_return']:+6.1f}% current (max: {r['max_return']:+5.1f}%, target: {r['target']:.0f}%)")

        if loss_negative:
            print(f"\n  ❌ LOSS NEGATIVE ({len(loss_negative)}) - ติดลบจริงๆ:")
            for r in sorted(loss_negative, key=lambda x: x['actual_return']):
                print(f"     {r['symbol']:6s}: {r['actual_return']:+6.1f}% current (max DD: {r['max_drawdown']:+5.1f}%)")

        # Key insight
        print(f"\n💡 Key Insight:")
        total_negative = len(loss_negative)
        total_not_reached = len(miss_positive) + len(loss_negative)

        print(f"  • รวม 'แพ้' (ไม่ถึง target): {total_not_reached} ({(total_not_reached/total*100):.1f}%)")
        print(f"    - แต่ยังกำไร: {len(miss_positive)} ({miss_positive_rate:.1f}%)")
        print(f"    - ติดลบจริงๆ: {len(loss_negative)} ({loss_negative_rate:.1f}%)")

        if total_not_reached > 0:
            pct_positive_in_losers = len(miss_positive) / total_not_reached * 100
            print(f"\n  ⚠️  ในหุ้นที่ 'แพ้' {pct_positive_in_losers:.1f}% ยังได้กำไร!")

        # Real win rate (including positive misses as partial wins)
        real_wins = len(wins) + len(miss_positive)
        real_win_rate = real_wins / total * 100
        print(f"\n  ✅ 'Real Win Rate' (ถ้านับกำไรทุกแบบ): {real_win_rate:.1f}%")

    print("\n" + "=" * 100)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    run_analysis()
