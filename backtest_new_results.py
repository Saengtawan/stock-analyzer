#!/usr/bin/env python3
"""
Backtest New Screening Results
Check if these 17 stocks will hit 15% target
"""

import yfinance as yf
import numpy as np

# New screening results
STOCKS = [
    {'rank': 1, 'symbol': 'AMZN', 'composite': 48.8, 'catalyst': 60.0, 'technical': 30.0, 'ai_prob': 45.0},
    {'rank': 2, 'symbol': 'AMD', 'composite': 48.5, 'catalyst': 60.0, 'technical': 35.0, 'ai_prob': 40.0},
    {'rank': 3, 'symbol': 'MSFT', 'composite': 48.2, 'catalyst': 60.0, 'technical': 40.0, 'ai_prob': 35.0},
    {'rank': 4, 'symbol': 'TEAM', 'composite': 44.5, 'catalyst': 50.0, 'technical': 40.0, 'ai_prob': 35.0},
    {'rank': 5, 'symbol': 'DASH', 'composite': 44.5, 'catalyst': 50.0, 'technical': 40.0, 'ai_prob': 35.0},
    {'rank': 6, 'symbol': 'WDAY', 'composite': 44.2, 'catalyst': 45.0, 'technical': 45.0, 'ai_prob': 35.0},
    {'rank': 7, 'symbol': 'HUBS', 'composite': 44.2, 'catalyst': 45.0, 'technical': 45.0, 'ai_prob': 35.0},
    {'rank': 8, 'symbol': 'NET', 'composite': 44.0, 'catalyst': 45.0, 'technical': 35.0, 'ai_prob': 40.0},
    {'rank': 9, 'symbol': 'COIN', 'composite': 44.0, 'catalyst': 45.0, 'technical': 35.0, 'ai_prob': 40.0},
    {'rank': 10, 'symbol': 'NVDA', 'composite': 43.8, 'catalyst': 45.0, 'technical': 40.0, 'ai_prob': 35.0},
    {'rank': 11, 'symbol': 'SHOP', 'composite': 43.5, 'catalyst': 35.0, 'technical': 45.0, 'ai_prob': 40.0},
    {'rank': 12, 'symbol': 'PANW', 'composite': 43.5, 'catalyst': 40.0, 'technical': 45.0, 'ai_prob': 35.0},
    {'rank': 13, 'symbol': 'HOOD', 'composite': 43.0, 'catalyst': 45.0, 'technical': 40.0, 'ai_prob': 35.0},
    {'rank': 14, 'symbol': 'QCOM', 'composite': 43.0, 'catalyst': 45.0, 'technical': 40.0, 'ai_prob': 35.0},
    {'rank': 15, 'symbol': 'UBER', 'composite': 41.2, 'catalyst': 45.0, 'technical': 30.0, 'ai_prob': 35.0},
    {'rank': 16, 'symbol': 'ROKU', 'composite': 41.0, 'catalyst': 35.0, 'technical': 35.0, 'ai_prob': 40.0},
    {'rank': 17, 'symbol': 'DOCU', 'composite': 38.5, 'catalyst': 30.0, 'technical': 40.0, 'ai_prob': 35.0},
]

TARGET = 15.0

print("="*80)
print("📊 BACKTESTING NEW SCREENING RESULTS")
print("="*80)
print(f"Target: {TARGET}%+ in 30 days")
print(f"Total stocks: {len(STOCKS)}")
print("")

results = []
extended_stocks = []  # Track stocks that are already up a lot

for stock_data in STOCKS:
    symbol = stock_data['symbol']
    rank = stock_data['rank']

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='3mo')

        if hist.empty or len(hist) < 30:
            print(f"#{rank} {symbol}: ⚠️  Insufficient data")
            continue

        # 30-day performance
        price_30d_ago = hist['Close'].iloc[-30]
        price_now = hist['Close'].iloc[-1]
        actual_return = ((price_now - price_30d_ago) / price_30d_ago) * 100

        # Max return (including intraday)
        high_30d = hist['High'].iloc[-30:].max()
        max_return = ((high_30d - price_30d_ago) / price_30d_ago) * 100

        reached_target = max_return >= TARGET

        # Check if already extended (up >15% in last 2 weeks)
        if len(hist) >= 10:
            price_10d_ago = hist['Close'].iloc[-10]
            recent_move = ((price_now - price_10d_ago) / price_10d_ago) * 100
            is_extended = recent_move > 15
        else:
            recent_move = 0
            is_extended = False

        # Get additional info
        info = ticker.info
        target_price = info.get('targetMeanPrice', 0)
        upside_to_target = ((target_price - price_now) / price_now * 100) if target_price > 0 else 0

        status = "✅ WINNER" if reached_target else "❌ MISS"
        extended_flag = "⚠️ EXTENDED" if is_extended else ""

        print(f"#{rank} {symbol}: {status} {extended_flag}")
        print(f"    Entry (30d ago): ${price_30d_ago:.2f}")
        print(f"    Current: ${price_now:.2f}")
        print(f"    Return: {actual_return:+.1f}% | Max: {max_return:+.1f}%")
        print(f"    Recent 2W: {recent_move:+.1f}%")
        print(f"    Analyst Target Upside: {upside_to_target:+.1f}%")
        print(f"    Scores: Composite={stock_data['composite']}, Catalyst={stock_data['catalyst']}, Tech={stock_data['technical']}")
        print()

        results.append({
            'rank': rank,
            'symbol': symbol,
            'reached_target': reached_target,
            'actual_return': actual_return,
            'max_return': max_return,
            'recent_move': recent_move,
            'is_extended': is_extended,
            'composite': stock_data['composite'],
            'catalyst': stock_data['catalyst'],
            'technical': stock_data['technical']
        })

        if is_extended:
            extended_stocks.append(symbol)

    except Exception as e:
        print(f"#{rank} {symbol}: ❌ Error - {e}")
        print()

# Calculate metrics
print("="*80)
print("📊 BACKTEST SUMMARY")
print("="*80)

if results:
    total = len(results)
    winners = [r for r in results if r['reached_target']]
    losers = [r for r in results if not r['reached_target']]

    win_rate = len(winners) / total * 100
    avg_return = np.mean([r['actual_return'] for r in results])
    avg_max = np.mean([r['max_return'] for r in results])

    print(f"\n📈 Performance:")
    print(f"   Win Rate: {win_rate:.1f}% ({len(winners)}/{total})")
    print(f"   Average Return: {avg_return:+.2f}%")
    print(f"   Average Max: {avg_max:+.2f}%")
    print(f"   Extended Stocks: {len(extended_stocks)} ({', '.join(extended_stocks)})")

    if winners:
        print(f"\n🏆 Winners ({len(winners)}):")
        for r in sorted(winners, key=lambda x: x['max_return'], reverse=True):
            print(f"   #{r['rank']} {r['symbol']}: {r['max_return']:+.1f}% (Composite: {r['composite']:.1f})")

    if losers:
        print(f"\n📉 Misses ({len(losers)}):")
        for r in sorted(losers, key=lambda x: x['actual_return'])[:5]:
            print(f"   #{r['rank']} {r['symbol']}: {r['actual_return']:+.1f}% (Composite: {r['composite']:.1f})")

    # Analyze top 5 vs rest
    top5 = [r for r in results if r['rank'] <= 5]
    rest = [r for r in results if r['rank'] > 5]

    if top5:
        top5_win_rate = len([r for r in top5 if r['reached_target']]) / len(top5) * 100
        print(f"\n🎯 Top 5 Win Rate: {top5_win_rate:.1f}%")

    if rest:
        rest_win_rate = len([r for r in rest if r['reached_target']]) / len(rest) * 100
        print(f"   Rest Win Rate: {rest_win_rate:.1f}%")

    print("\n" + "="*80)

    if win_rate >= 50:
        print("✅ GOOD: Screener is working!")
    elif win_rate >= 30:
        print("⚠️  MODERATE: Needs improvement")
    else:
        print("❌ POOR: Major issues detected")

    print("="*80)

print("\n💡 Next Steps:")
print("   1. Check why top picks failed (if any)")
print("   2. Identify patterns in winners vs losers")
print("   3. Adjust scoring if needed")
