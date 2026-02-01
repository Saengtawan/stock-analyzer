#!/usr/bin/env python3
"""
Simple Winners vs Losers Comparison
===================================
ใช้ข้อมูลที่มีอยู่แล้วจาก screening results
"""

import sys
sys.path.insert(0, 'src')

import yfinance as yf
import pandas as pd

# Winners and Losers with their screening scores from earlier debug
STOCKS = {
    # Winners (10d return positive)
    'LITE': {'return_10d': 15.09, 'composite': 29.0, 'group': 'WINNER'},
    'RIVN': {'return_10d': 11.80, 'composite': 38.7, 'group': 'WINNER'},
    'BCRX': {'return_10d': 9.40, 'composite': 45.8, 'group': 'WINNER'},
    'ATEC': {'return_10d': 7.51, 'composite': 37.6, 'group': 'WINNER'},
    'BILL': {'return_10d': 2.38, 'composite': 49.2, 'group': 'WINNER'},
    'PATH': {'return_10d': 2.69, 'composite': 41.1, 'group': 'WINNER'},

    # Losers (10d return negative)
    'CRSP': {'return_10d': -4.20, 'composite': 52.7, 'group': 'LOSER'},
    'AI': {'return_10d': -4.06, 'composite': 44.3, 'group': 'LOSER'},
    'AZTA': {'return_10d': -3.79, 'composite': 36.7, 'group': 'LOSER'},
    'POWI': {'return_10d': -1.55, 'composite': 39.0, 'group': 'LOSER'},
}

print("=" * 80)
print("🔬 WINNERS vs LOSERS - Simple Comparison")
print("=" * 80)

# Collect data
all_data = []

print("\n📊 Collecting stock data...")
for symbol, info in STOCKS.items():
    print(f"   {symbol}...", end=" ")
    try:
        stock = yf.Ticker(symbol)
        yf_info = stock.info
        hist = stock.history(period='90d')

        if hist.empty:
            print("❌ No data")
            continue

        current_price = hist['Close'].iloc[-1]
        volume_20d = hist['Volume'].tail(20).mean()

        # Calculate technical indicators
        rsi = None
        if len(hist) >= 14:
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs.iloc[-1]))

        # Moving averages
        ma20_dist = None
        ma50_dist = None
        if len(hist) >= 50:
            ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
            ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            ma20_dist = ((current_price - ma20) / ma20) * 100
            ma50_dist = ((current_price - ma50) / ma50) * 100

        # Momentum
        momentum_10d = None
        momentum_30d = None
        if len(hist) >= 10:
            price_10d = hist['Close'].iloc[-10]
            momentum_10d = ((current_price - price_10d) / price_10d) * 100
        if len(hist) >= 30:
            price_30d = hist['Close'].iloc[-30]
            momentum_30d = ((current_price - price_30d) / price_30d) * 100

        # Volatility
        volatility = hist['Close'].pct_change().tail(20).std() * 100

        all_data.append({
            'symbol': symbol,
            'group': info['group'],
            'return_10d': info['return_10d'],
            'composite_score': info['composite'],
            'price': current_price,
            'market_cap': yf_info.get('marketCap', 0) / 1e9 if yf_info.get('marketCap') else 0,
            'sector': yf_info.get('sector', 'Unknown'),
            'volume_20d': volume_20d,
            'rsi': rsi,
            'ma20_dist': ma20_dist,
            'ma50_dist': ma50_dist,
            'momentum_10d': momentum_10d,
            'momentum_30d': momentum_30d,
            'volatility': volatility,
        })

        print("✅")

    except Exception as e:
        print(f"❌ {str(e)[:30]}")

if not all_data:
    print("\n❌ No data collected!")
    sys.exit(1)

df = pd.DataFrame(all_data)
winners = df[df['group'] == 'WINNER']
losers = df[df['group'] == 'LOSER']

# Analysis
print("\n" + "=" * 80)
print("📊 COMPARATIVE ANALYSIS")
print("=" * 80)

def compare_metric(metric, desc, format_str=".2f"):
    """Compare a metric between winners and losers"""
    w_values = winners[metric].dropna()
    l_values = losers[metric].dropna()

    if len(w_values) == 0 or len(l_values) == 0:
        return

    w_avg = w_values.mean()
    l_avg = l_values.mean()
    diff = w_avg - l_avg
    diff_pct = (diff / abs(l_avg)) * 100 if l_avg != 0 else 0

    emoji = "✅" if abs(diff_pct) > 20 else "⚠️" if abs(diff_pct) > 10 else "➡️"

    print(f"\n{emoji} {desc}:")
    print(f"   Winners: {w_avg:{format_str}}")
    print(f"   Losers:  {l_avg:{format_str}}")
    print(f"   Diff:    {diff:{format_str}} ({diff_pct:+.1f}%)")

    if abs(diff_pct) > 20:
        print(f"   🎯 SIGNIFICANT - Good predictor!")
        return True
    return False

significant_metrics = []

if compare_metric('composite_score', 'Composite Score'):
    significant_metrics.append('Composite Score')

if compare_metric('price', 'Stock Price ($)'):
    significant_metrics.append('Price')

if compare_metric('market_cap', 'Market Cap ($B)'):
    significant_metrics.append('Market Cap')

if compare_metric('rsi', 'RSI'):
    significant_metrics.append('RSI')

if compare_metric('ma20_dist', 'Distance from MA20 (%)'):
    significant_metrics.append('MA20 Distance')

if compare_metric('ma50_dist', 'Distance from MA50 (%)'):
    significant_metrics.append('MA50 Distance')

if compare_metric('momentum_10d', 'Momentum 10d (%)'):
    significant_metrics.append('Momentum 10d')

if compare_metric('momentum_30d', 'Momentum 30d (%)'):
    significant_metrics.append('Momentum 30d')

if compare_metric('volatility', 'Volatility (%)'):
    significant_metrics.append('Volatility')

# Sector comparison
print("\n📊 Sector Analysis:")
print("\nWinners:")
for sector, group in winners.groupby('sector'):
    symbols = ', '.join(group['symbol'].tolist())
    print(f"  {sector}: {symbols}")

print("\nLosers:")
for sector, group in losers.groupby('sector'):
    symbols = ', '.join(group['symbol'].tolist())
    print(f"  {sector}: {symbols}")

# Individual details
print("\n" + "=" * 80)
print("📋 DETAILED BREAKDOWN")
print("=" * 80)

print(f"\n🏆 WINNERS ({len(winners)} stocks):")
print(f"{'Symbol':<8} {'Return':>8} {'Comp':>6} {'Price':>8} {'RSI':>6} {'Mom10d':>8} {'Sector':<20}")
print("-" * 85)
for _, row in winners.iterrows():
    print(f"{row['symbol']:<8} {row['return_10d']:>+7.2f}% {row['composite_score']:>6.1f} "
          f"${row['price']:>7.2f} {row['rsi']:>6.1f} {row.get('momentum_10d', 0):>+7.2f}% {row['sector'][:18]:<20}")

print(f"\n💔 LOSERS ({len(losers)} stocks):")
print(f"{'Symbol':<8} {'Return':>8} {'Comp':>6} {'Price':>8} {'RSI':>6} {'Mom10d':>8} {'Sector':<20}")
print("-" * 85)
for _, row in losers.iterrows():
    print(f"{row['symbol']:<8} {row['return_10d']:>+7.2f}% {row['composite_score']:>6.1f} "
          f"${row['price']:>7.2f} {row['rsi']:>6.1f} {row.get('momentum_10d', 0):>+7.2f}% {row['sector'][:18]:<20}")

# Key findings
print("\n" + "=" * 80)
print("🎯 KEY FINDINGS")
print("=" * 80)

# Check composite score paradox
w_comp_avg = winners['composite_score'].mean()
l_comp_avg = losers['composite_score'].mean()

if l_comp_avg > w_comp_avg:
    print(f"\n❌ COMPOSITE SCORE PARADOX!")
    print(f"   Losers had HIGHER composite scores than winners!")
    print(f"   Winners: {w_comp_avg:.1f}")
    print(f"   Losers:  {l_comp_avg:.1f}")
    print(f"   → Composite score is NOT a good predictor!")

if significant_metrics:
    print(f"\n✅ Found {len(significant_metrics)} significant differentiators:")
    for i, metric in enumerate(significant_metrics, 1):
        print(f"   {i}. {metric}")
else:
    print(f"\n⚠️  NO significant differentiators found!")

# Recommendations
print("\n" + "=" * 80)
print("💡 CONCLUSION & RECOMMENDATION")
print("=" * 80)

if len(significant_metrics) >= 2:
    print(f"""
✅ GOOD NEWS: Found {len(significant_metrics)} predictive metrics!

We CAN distinguish winners from losers.

Recommended approach:
1. Focus on metrics that showed >20% difference
2. Add these as PRIMARY filters
3. Can safely lower other thresholds moderately

✅ Safe to adjust filters based on findings
""")
elif len(significant_metrics) == 1:
    print(f"""
⚠️  MIXED: Only 1 clear differentiator found

Found: {significant_metrics[0]}

This is risky:
- Not enough signal to reliably predict
- Lowering thresholds might let in losers
- Need more predictive features

Recommendation:
- Add momentum/trend filters
- Keep current thresholds OR
- Relax ONLY slightly (20 → 25)

⚠️  Proceed with caution
""")
else:
    print("""
❌ WARNING: No clear differentiators!

Winners and losers look VERY similar on paper.
Current metrics are NOT predictive.

DO NOT lower thresholds! You will get:
- More losers
- Same (or worse) win rate
- More losses

Instead:
1. Add NEW metrics (momentum, relative strength)
2. Improve scoring algorithm
3. OR accept fewer but higher-quality opportunities

❌ Keep current strict filters
""")

print("\n" + "=" * 80)
print("✅ ANALYSIS COMPLETE")
print("=" * 80)
