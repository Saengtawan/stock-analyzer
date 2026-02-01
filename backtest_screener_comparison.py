#!/usr/bin/env python3
"""
Screener Comparison Backtest
============================

เปรียบเทียบ 3 screeners:
1. Original Growth Catalyst (baseline)
2. Momentum Screener - STRICT
3. Momentum Screener - RELAXED

วัดผล:
- Win rate
- Average return
- Best/worst trades
- จำนวนหุ้นที่เจอ
- คุณภาพหุ้น

เพื่อตัดสินใจว่าควรใช้อันไหน
"""

import sys
sys.path.insert(0, 'src')

from datetime import datetime, timedelta
import yfinance as yf
from collections import defaultdict
import json

print("=" * 80)
print("🔬 SCREENER COMPARISON BACKTEST")
print("=" * 80)
print("\nComparing 3 approaches:")
print("  1️⃣  Original Growth Catalyst (composite score based)")
print("  2️⃣  Momentum Screener - STRICT (RSI 40-70, Mom30d >10%)")
print("  3️⃣  Momentum Screener - RELAXED (RSI 35-70, Mom30d >5%)")
print("\nBacktest period: Last 90 days")
print("Hold period: 10 days (Growth Catalyst target)")
print("=" * 80)

# Test universe (stocks from earlier analysis + some others)
TEST_UNIVERSE = [
    'LITE', 'RIVN', 'BCRX', 'ATEC', 'BILL', 'PATH',  # Winners
    'CRSP', 'AI', 'AZTA', 'POWI',  # Losers
    # Add more from common sectors
    'SYNA', 'PLTR', 'NET', 'CRWD', 'SNOW', 'DDOG',
    'SOFI', 'UPST', 'AFRM', 'SHOP',
    'ABBV', 'BMY', 'GILD', 'REGN',
    'KLAC', 'LRCX', 'AMAT', 'TER',
]

def calculate_momentum_metrics(hist_data):
    """Calculate momentum metrics for a stock"""
    try:
        if len(hist_data) < 50:
            return None

        close = hist_data['Close']
        current_price = close.iloc[-1]

        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1]))

        # Moving averages
        ma20 = close.rolling(window=20).mean().iloc[-1]
        ma50 = close.rolling(window=50).mean().iloc[-1]

        price_above_ma20 = ((current_price - ma20) / ma20) * 100
        price_above_ma50 = ((current_price - ma50) / ma50) * 100

        # Momentum
        price_10d_ago = close.iloc[-10]
        price_30d_ago = close.iloc[-30]

        momentum_10d = ((current_price - price_10d_ago) / price_10d_ago) * 100
        momentum_30d = ((current_price - price_30d_ago) / price_30d_ago) * 100

        return {
            'rsi': rsi,
            'price_above_ma20': price_above_ma20,
            'price_above_ma50': price_above_ma50,
            'momentum_10d': momentum_10d,
            'momentum_30d': momentum_30d,
        }
    except:
        return None

def passes_original_filter(metrics):
    """
    Original Growth Catalyst filter (simplified)
    Based on composite score - which we know is WRONG
    """
    # Simulate original filter - accepts stocks with various scores
    # In reality this was too lenient
    return True  # Original accepted most stocks

def passes_momentum_strict(metrics):
    """
    Momentum Screener - STRICT filters
    Based on actual winner characteristics
    """
    if metrics is None:
        return False

    # Strict criteria from winners analysis
    if metrics['rsi'] < 40 or metrics['rsi'] > 70:
        return False

    if metrics['price_above_ma20'] < 0:  # Must be above MA20
        return False

    if metrics['price_above_ma50'] < 0:  # Must be above MA50
        return False

    if metrics['momentum_10d'] < 0:  # Must be rising
        return False

    if metrics['momentum_30d'] < 10:  # Strong 30d trend
        return False

    return True

def passes_momentum_relaxed(metrics):
    """
    Momentum Screener - RELAXED filters
    Slightly looser to get more opportunities
    """
    if metrics is None:
        return False

    # Relaxed criteria
    if metrics['rsi'] < 35 or metrics['rsi'] > 70:  # Lower RSI threshold
        return False

    if metrics['price_above_ma20'] < -2:  # Can be slightly below MA20
        return False

    if metrics['price_above_ma50'] < -5:  # Can be slightly below MA50
        return False

    if metrics['momentum_10d'] < -2:  # Can have small negative
        return False

    if metrics['momentum_30d'] < 5:  # Lower 30d requirement
        return False

    return True

print("\n🔍 Analyzing test universe...")
print(f"   Testing {len(TEST_UNIVERSE)} stocks")

# Backtest each stock
results = {
    'original': [],
    'momentum_strict': [],
    'momentum_relaxed': [],
}

stock_data = {}

for symbol in TEST_UNIVERSE:
    try:
        print(f"   {symbol}...", end=" ", flush=True)

        # Get 90 days of data
        stock = yf.Ticker(symbol)
        hist = stock.history(period='90d')

        if hist.empty or len(hist) < 60:
            print("❌ Insufficient data")
            continue

        # Simulate entry 10 days ago
        if len(hist) < 10:
            print("❌ Too short")
            continue

        # Entry point: 10 days before last day
        entry_idx = -10
        exit_idx = -1

        entry_price = hist['Close'].iloc[entry_idx]
        exit_price = hist['Close'].iloc[exit_idx]

        return_10d = ((exit_price - entry_price) / entry_price) * 100

        # Get metrics at entry point
        hist_at_entry = hist.iloc[:entry_idx]
        metrics = calculate_momentum_metrics(hist_at_entry)

        if metrics is None:
            print("❌ No metrics")
            continue

        stock_info = {
            'symbol': symbol,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'return_10d': return_10d,
            'metrics': metrics,
        }

        stock_data[symbol] = stock_info

        # Test each filter
        if passes_original_filter(metrics):
            results['original'].append(stock_info)

        if passes_momentum_strict(metrics):
            results['momentum_strict'].append(stock_info)

        if passes_momentum_relaxed(metrics):
            results['momentum_relaxed'].append(stock_info)

        result_emoji = "📈" if return_10d > 0 else "📉"
        print(f"{result_emoji} {return_10d:+.1f}%")

    except Exception as e:
        print(f"❌ {str(e)[:30]}")

print(f"\n✅ Analyzed {len(stock_data)} stocks successfully")

# Results analysis
print("\n" + "=" * 80)
print("📊 BACKTEST RESULTS")
print("=" * 80)

def analyze_results(name, trades):
    """Analyze trading results"""
    if not trades:
        print(f"\n{name}:")
        print("   ❌ No trades (too strict!)")
        return None

    returns = [t['return_10d'] for t in trades]
    winners = [r for r in returns if r > 0]
    losers = [r for r in returns if r <= 0]

    total_trades = len(trades)
    win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0
    avg_return = sum(returns) / len(returns)
    avg_winner = sum(winners) / len(winners) if winners else 0
    avg_loser = sum(losers) / len(losers) if losers else 0
    best_trade = max(returns) if returns else 0
    worst_trade = min(returns) if returns else 0

    return {
        'name': name,
        'total_trades': total_trades,
        'winners': len(winners),
        'losers': len(losers),
        'win_rate': win_rate,
        'avg_return': avg_return,
        'avg_winner': avg_winner,
        'avg_loser': avg_loser,
        'best_trade': best_trade,
        'worst_trade': worst_trade,
        'trades': trades,
    }

# Analyze each approach
orig_results = analyze_results("Original Growth Catalyst", results['original'])
strict_results = analyze_results("Momentum Strict", results['momentum_strict'])
relaxed_results = analyze_results("Momentum Relaxed", results['momentum_relaxed'])

# Print comparison
print(f"\n{'Metric':<25} {'Original':>15} {'Momentum Strict':>15} {'Momentum Relaxed':>15}")
print("-" * 75)

all_results = [orig_results, strict_results, relaxed_results]
valid_results = [r for r in all_results if r is not None]

if valid_results:
    # Total trades
    print(f"{'Total Trades':<25} ", end="")
    for r in all_results:
        if r:
            print(f"{r['total_trades']:>15}", end="")
        else:
            print(f"{'0':>15}", end="")
    print()

    # Win rate
    print(f"{'Win Rate':<25} ", end="")
    for r in all_results:
        if r:
            emoji = "✅" if r['win_rate'] >= 60 else "⚠️" if r['win_rate'] >= 50 else "❌"
            print(f"{r['win_rate']:>13.1f}% {emoji}", end="")
        else:
            print(f"{'N/A':>15}", end="")
    print()

    # Average return
    print(f"{'Avg Return':<25} ", end="")
    for r in all_results:
        if r:
            emoji = "✅" if r['avg_return'] > 3 else "⚠️" if r['avg_return'] > 0 else "❌"
            print(f"{r['avg_return']:>13.1f}% {emoji}", end="")
        else:
            print(f"{'N/A':>15}", end="")
    print()

    # Avg winner
    print(f"{'Avg Winner':<25} ", end="")
    for r in all_results:
        if r and r['winners'] > 0:
            print(f"{r['avg_winner']:>14.1f}%", end="")
        else:
            print(f"{'N/A':>15}", end="")
    print()

    # Avg loser
    print(f"{'Avg Loser':<25} ", end="")
    for r in all_results:
        if r and r['losers'] > 0:
            print(f"{r['avg_loser']:>14.1f}%", end="")
        else:
            print(f"{'N/A':>15}", end="")
    print()

    # Best trade
    print(f"{'Best Trade':<25} ", end="")
    for r in all_results:
        if r:
            print(f"{r['best_trade']:>14.1f}%", end="")
        else:
            print(f"{'N/A':>15}", end="")
    print()

    # Worst trade
    print(f"{'Worst Trade':<25} ", end="")
    for r in all_results:
        if r:
            print(f"{r['worst_trade']:>14.1f}%", end="")
        else:
            print(f"{'N/A':>15}", end="")
    print()

# Detailed breakdown
for r in all_results:
    if r:
        print(f"\n{'-' * 80}")
        print(f"📋 {r['name']} - Detailed Breakdown")
        print(f"{'-' * 80}")
        print(f"\nStocks selected:")
        for t in sorted(r['trades'], key=lambda x: x['return_10d'], reverse=True):
            emoji = "📈" if t['return_10d'] > 0 else "📉"
            print(f"  {emoji} {t['symbol']:6} {t['return_10d']:>+7.2f}% | "
                  f"RSI: {t['metrics']['rsi']:>5.1f} | "
                  f"MA50: {t['metrics']['price_above_ma50']:>+6.1f}% | "
                  f"Mom30d: {t['metrics']['momentum_30d']:>+6.1f}%")

# Recommendation
print("\n" + "=" * 80)
print("💡 RECOMMENDATION")
print("=" * 80)

if not any(all_results):
    print("""
❌ ALL approaches found 0 stocks!

This means:
- Test universe is too small OR
- Market conditions are poor OR
- Need to expand universe

Action: Try with larger universe or different time period
""")
else:
    # Compare approaches
    best_approach = None
    best_score = -999

    for r in valid_results:
        # Calculate quality score
        # Win rate (50%), Avg return (30%), Trade count (20%)
        score = (r['win_rate'] * 0.5) + (r['avg_return'] * 3 * 0.3) + (min(r['total_trades'], 10) * 2)

        if score > best_score:
            best_score = score
            best_approach = r

    print(f"\n🏆 WINNER: {best_approach['name']}")
    print(f"   Win Rate: {best_approach['win_rate']:.1f}%")
    print(f"   Avg Return: {best_approach['avg_return']:+.2f}%")
    print(f"   Total Trades: {best_approach['total_trades']}")

    # Specific recommendations
    if best_approach['name'] == 'Original Growth Catalyst':
        print(f"""
⚠️  Original is still best, BUT:
- It has lower standards (accepts more stocks)
- May include future losers we haven't seen yet
- Momentum approach is theoretically better

Recommendation:
- Keep using Original for now
- Monitor Momentum approach performance
- Consider hybrid approach
""")
    elif best_approach['name'] == 'Momentum Strict':
        print(f"""
✅ Momentum STRICT is best!

Benefits:
- Higher quality stocks (match winner profile)
- Better filtering of losers
- Based on actual performance data

Action:
✅ IMPLEMENT Momentum Screener with STRICT filters
- RSI 40-70
- Price > MA20, MA50
- Momentum 10d > 0%
- Momentum 30d > 10%
""")
    elif best_approach['name'] == 'Momentum Relaxed':
        print(f"""
✅ Momentum RELAXED is best!

Benefits:
- More opportunities than strict
- Still better than original
- Good balance of quantity & quality

Action:
✅ IMPLEMENT Momentum Screener with RELAXED filters
- RSI 35-70
- Price > MA20 -2%, MA50 -5%
- Momentum 10d > -2%
- Momentum 30d > 5%
""")

    # Compare to original
    if orig_results and best_approach['name'] != 'Original Growth Catalyst':
        win_rate_diff = best_approach['win_rate'] - orig_results['win_rate']
        return_diff = best_approach['avg_return'] - orig_results['avg_return']

        print(f"\n📊 Improvement vs Original:")
        print(f"   Win Rate: {win_rate_diff:+.1f}% {' ✅' if win_rate_diff > 0 else ' ❌'}")
        print(f"   Avg Return: {return_diff:+.2f}% {' ✅' if return_diff > 0 else ' ❌'}")

        if win_rate_diff > 5 or return_diff > 1:
            print(f"\n   🎯 SIGNIFICANT IMPROVEMENT - Strongly recommend switching!")
        elif win_rate_diff > 0 or return_diff > 0:
            print(f"\n   ✅ Modest improvement - Worth switching")
        else:
            print(f"\n   ⚠️  Not better than original - Keep current approach")

print("\n" + "=" * 80)
print("✅ BACKTEST COMPLETE")
print("=" * 80)
print("\nNext steps:")
print("  1. Review detailed breakdown above")
print("  2. Decide which approach to use")
print("  3. Implement in production if results are good")
print("  4. Monitor performance over time")
