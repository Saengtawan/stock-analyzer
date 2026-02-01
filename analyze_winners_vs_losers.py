#!/usr/bin/env python3
"""
Winners vs Losers Analysis
==========================

วิเคราะห์ความแตกต่างระหว่าง:
- Winners: LITE +15%, RIVN +12%, BCRX +9%, ATEC +8%, BILL +2%
- Losers: CRSP -4%, AI -4%, AZTA -4%, POWI -2%

เพื่อหาว่า:
1. อะไรทำให้ winners ชนะ
2. เราสามารถแยกแยะได้ตั้งแต่ต้นไหม
3. ถ้าลด threshold จะได้ winners มากขึ้นหรือได้ losers เพิ่ม
"""

import sys
sys.path.insert(0, 'src')

from screeners.growth_catalyst_screener import GrowthCatalystScreener
from main import StockAnalyzer
from loguru import logger
import yfinance as yf
from datetime import datetime, timedelta

logger.remove()
logger.add(sys.stderr, level="ERROR")

# Define groups
WINNERS = [
    ('LITE', 15.09),
    ('RIVN', 11.80),
    ('BCRX', 9.40),
    ('ATEC', 7.51),
    ('BILL', 2.38),
]

LOSERS = [
    ('CRSP', -4.20),
    ('AI', -4.06),
    ('AZTA', -3.79),
    ('POWI', -1.55),
]

print("=" * 80)
print("🔬 WINNERS vs LOSERS - Deep Dive Analysis")
print("=" * 80)

# Initialize
print("\n📦 Analyzing stocks...")
analyzer = StockAnalyzer()
screener = GrowthCatalystScreener(analyzer)

def analyze_stock_details(symbol, group_name):
    """Get detailed analysis for a stock"""
    try:
        # Get stock data
        stock = yf.Ticker(symbol)
        info = stock.info
        hist = stock.history(period='3mo')

        if hist.empty:
            return None

        current_price = hist['Close'].iloc[-1]
        volume = hist['Volume'].tail(20).mean()

        # Get technical analysis
        from analysis.technical_analyzer import TechnicalAnalyzer
        tech_analyzer = TechnicalAnalyzer()
        tech_analysis = tech_analyzer.analyze(hist)

        # Get alternative data signals
        from data_sources.alternative_data import AlternativeDataAggregator
        alt_data = AlternativeDataAggregator()
        alt_signals = alt_data.get_aggregated_signals(symbol)

        details = {
            'symbol': symbol,
            'group': group_name,
            'price': current_price,
            'sector': info.get('sector', 'Unknown'),
            'market_cap': info.get('marketCap', 0) / 1e9,
            'volume': volume,
            'rsi': tech_analysis.get('rsi', 0),
            'macd': tech_analysis.get('macd', {}).get('macd', 0),
            'ma20_distance': tech_analysis.get('ma_distance', {}).get('ma20', 0),
            'ma50_distance': tech_analysis.get('ma_distance', {}).get('ma50', 0),
            'alt_data_signals': alt_signals.get('total_signals', 0),
            'alt_data_list': alt_signals.get('signals_list', []),
            'insider_buying': alt_signals.get('insider_buying', False),
            'analyst_upgrades': alt_signals.get('analyst_upgrades', 0),
            'short_interest': alt_signals.get('short_interest', 0),
        }

        # Calculate momentum
        if len(hist) >= 10:
            price_10d_ago = hist['Close'].iloc[-10]
            details['momentum_10d'] = ((current_price - price_10d_ago) / price_10d_ago) * 100

        if len(hist) >= 30:
            price_30d_ago = hist['Close'].iloc[-30]
            details['momentum_30d'] = ((current_price - price_30d_ago) / price_30d_ago) * 100

        return details

    except Exception as e:
        print(f"   ❌ Error analyzing {symbol}: {e}")
        return None

# Analyze all stocks
print("\n🔍 Analyzing WINNERS...")
winners_data = []
for symbol, return_pct in WINNERS:
    print(f"   Analyzing {symbol}...", end=" ")
    data = analyze_stock_details(symbol, 'WINNER')
    if data:
        data['actual_return_10d'] = return_pct
        winners_data.append(data)
        print("✅")
    else:
        print("❌")

print("\n🔍 Analyzing LOSERS...")
losers_data = []
for symbol, return_pct in LOSERS:
    print(f"   Analyzing {symbol}...", end=" ")
    data = analyze_stock_details(symbol, 'LOSER')
    if data:
        data['actual_return_10d'] = return_pct
        losers_data.append(data)
        print("✅")
    else:
        print("❌")

# Comparison
print("\n" + "=" * 80)
print("📊 COMPARATIVE ANALYSIS")
print("=" * 80)

def print_comparison(metric_name, winners_data, losers_data, metric_key, is_list=False):
    """Print comparison of a metric between winners and losers"""
    if is_list:
        # For list metrics (like alt_data_list)
        winners_values = [item for d in winners_data for item in d.get(metric_key, [])]
        losers_values = [item for d in losers_data for item in d.get(metric_key, [])]

        print(f"\n{metric_name}:")
        print(f"  Winners: {', '.join(set(winners_values)) if winners_values else 'None'}")
        print(f"  Losers:  {', '.join(set(losers_values)) if losers_values else 'None'}")
    else:
        winners_values = [d.get(metric_key, 0) for d in winners_data if d.get(metric_key) is not None]
        losers_values = [d.get(metric_key, 0) for d in losers_data if d.get(metric_key) is not None]

        if winners_values and losers_values:
            winner_avg = sum(winners_values) / len(winners_values)
            loser_avg = sum(losers_values) / len(losers_values)

            diff = winner_avg - loser_avg
            diff_pct = (diff / abs(loser_avg)) * 100 if loser_avg != 0 else 0

            emoji = "✅" if abs(diff_pct) > 20 else "⚠️" if abs(diff_pct) > 10 else "➡️"

            print(f"\n{emoji} {metric_name}:")
            print(f"   Winners: {winner_avg:>8.2f}")
            print(f"   Losers:  {loser_avg:>8.2f}")
            print(f"   Diff:    {diff:>8.2f} ({diff_pct:+.1f}%)")

            if abs(diff_pct) > 20:
                print(f"   🎯 SIGNIFICANT DIFFERENCE - Good predictor!")
            elif abs(diff_pct) > 10:
                print(f"   ⚠️  Moderate difference")
            else:
                print(f"   ➡️  Minor difference - Not useful for filtering")

# Compare metrics
print_comparison("Price Range", winners_data, losers_data, 'price')
print_comparison("Market Cap ($B)", winners_data, losers_data, 'market_cap')
print_comparison("Volume (shares)", winners_data, losers_data, 'volume')
print_comparison("RSI", winners_data, losers_data, 'rsi')
print_comparison("Distance from MA20 (%)", winners_data, losers_data, 'ma20_distance')
print_comparison("Distance from MA50 (%)", winners_data, losers_data, 'ma50_distance')
print_comparison("Momentum 10d (%)", winners_data, losers_data, 'momentum_10d')
print_comparison("Momentum 30d (%)", winners_data, losers_data, 'momentum_30d')
print_comparison("Alt Data Signals", winners_data, losers_data, 'alt_data_signals')
print_comparison("Analyst Upgrades", winners_data, losers_data, 'analyst_upgrades')
print_comparison("Short Interest (%)", winners_data, losers_data, 'short_interest')

# Sector breakdown
print("\n📊 Sector Breakdown:")
print("\n  Winners:")
for d in winners_data:
    print(f"    {d['symbol']:6} - {d['sector']}")

print("\n  Losers:")
for d in losers_data:
    print(f"    {d['symbol']:6} - {d['sector']}")

# Insider buying
print("\n💼 Insider Buying:")
winners_with_insider = sum(1 for d in winners_data if d.get('insider_buying', False))
losers_with_insider = sum(1 for d in losers_data if d.get('insider_buying', False))

print(f"  Winners: {winners_with_insider}/{len(winners_data)} ({winners_with_insider/len(winners_data)*100:.0f}%)")
print(f"  Losers:  {losers_with_insider}/{len(losers_data)} ({losers_with_insider/len(losers_data)*100:.0f}%)")

# Alt data signals detail
print("\n🔍 Alternative Data Signals Detail:")
print_comparison("Alt Data Signals List", winners_data, losers_data, 'alt_data_list', is_list=True)

# Individual stock details
print("\n" + "=" * 80)
print("📋 INDIVIDUAL STOCK DETAILS")
print("=" * 80)

print("\n🏆 WINNERS:")
print(f"{'Symbol':<8} {'Price':>8} {'Sector':<20} {'RSI':>6} {'Alt':>4} {'Mom10d':>8} {'Insider':<8}")
print("-" * 80)
for d in winners_data:
    insider = "✓" if d.get('insider_buying') else "✗"
    print(f"{d['symbol']:<8} ${d['price']:>7.2f} {d['sector'][:18]:<20} {d.get('rsi', 0):>6.1f} {d.get('alt_data_signals', 0):>4}/6 {d.get('momentum_10d', 0):>7.2f}% {insider:<8}")

print("\n💔 LOSERS:")
print(f"{'Symbol':<8} {'Price':>8} {'Sector':<20} {'RSI':>6} {'Alt':>4} {'Mom10d':>8} {'Insider':<8}")
print("-" * 80)
for d in losers_data:
    insider = "✓" if d.get('insider_buying') else "✗"
    print(f"{d['symbol']:<8} ${d['price']:>7.2f} {d['sector'][:18]:<20} {d.get('rsi', 0):>6.1f} {d.get('alt_data_signals', 0):>4}/6 {d.get('momentum_10d', 0):>7.2f}% {insider:<8}")

# Key findings
print("\n" + "=" * 80)
print("🎯 KEY FINDINGS & DIFFERENTIATORS")
print("=" * 80)

findings = []

# Check momentum
winners_mom = [d.get('momentum_10d', 0) for d in winners_data if d.get('momentum_10d') is not None]
losers_mom = [d.get('momentum_10d', 0) for d in losers_data if d.get('momentum_10d') is not None]

if winners_mom and losers_mom:
    w_avg_mom = sum(winners_mom) / len(winners_mom)
    l_avg_mom = sum(losers_mom) / len(losers_mom)

    if w_avg_mom > l_avg_mom + 5:
        findings.append(f"✅ MOMENTUM: Winners had stronger recent momentum ({w_avg_mom:.1f}% vs {l_avg_mom:.1f}%)")

# Check alt data signals
winners_alt = [d.get('alt_data_signals', 0) for d in winners_data]
losers_alt = [d.get('alt_data_signals', 0) for d in losers_data]

w_avg_alt = sum(winners_alt) / len(winners_alt)
l_avg_alt = sum(losers_alt) / len(losers_alt)

if w_avg_alt > l_avg_alt + 0.5:
    findings.append(f"✅ ALT DATA: Winners had more signals ({w_avg_alt:.1f}/6 vs {l_avg_alt:.1f}/6)")
elif w_avg_alt < l_avg_alt - 0.5:
    findings.append(f"❌ ALT DATA: Losers actually had MORE signals ({l_avg_alt:.1f}/6 vs {w_avg_alt:.1f}/6) - NOT a good filter!")

# Check RSI
winners_rsi = [d.get('rsi', 50) for d in winners_data if d.get('rsi')]
losers_rsi = [d.get('rsi', 50) for d in losers_data if d.get('rsi')]

if winners_rsi and losers_rsi:
    w_avg_rsi = sum(winners_rsi) / len(winners_rsi)
    l_avg_rsi = sum(losers_rsi) / len(losers_rsi)

    if abs(w_avg_rsi - l_avg_rsi) > 5:
        findings.append(f"⚠️  RSI: Winners {w_avg_rsi:.1f} vs Losers {l_avg_rsi:.1f}")

# Check price
winners_price = [d.get('price', 0) for d in winners_data]
losers_price = [d.get('price', 0) for d in losers_data]

w_avg_price = sum(winners_price) / len(winners_price)
l_avg_price = sum(losers_price) / len(losers_price)

if w_avg_price < l_avg_price * 0.5:
    findings.append(f"✅ PRICE: Winners were lower-priced (${w_avg_price:.2f} vs ${l_avg_price:.2f})")
elif w_avg_price > l_avg_price * 2:
    findings.append(f"⚠️  PRICE: Winners were higher-priced (${w_avg_price:.2f} vs ${l_avg_price:.2f})")

# Print findings
if findings:
    for finding in findings:
        print(f"\n{finding}")
else:
    print("\n⚠️  NO CLEAR DIFFERENTIATORS FOUND!")
    print("   Winners and losers look similar on paper.")
    print("   This means current metrics may not be predictive enough.")

# Conclusion
print("\n" + "=" * 80)
print("💡 CONCLUSION & RECOMMENDATION")
print("=" * 80)

# Determine if we can safely lower thresholds
if len(findings) >= 2:
    print("""
✅ GOOD NEWS: We CAN identify differences!

Found {0} significant differentiators between winners and losers.

💡 Strategy:
1. Keep filters that show clear differences
2. Can safely lower thresholds for metrics that winners excel in
3. Add new filters based on findings above

Next steps:
- Implement momentum filter (recent price action)
- Adjust alt_data_signals based on findings
- Consider price range filters

✅ Safe to RELAX filters moderately
""".format(len(findings)))
else:
    print("""
⚠️  WARNING: Winners and Losers look very similar!

Found only {0} differentiator(s).

This means:
- Current metrics don't predict success well
- Lowering thresholds might let in MORE losers
- Need better predictive features

💡 Recommendations:
1. DO NOT blindly lower thresholds
2. Add new metrics (momentum, relative strength, etc.)
3. Consider machine learning approach
4. OR accept fewer opportunities but higher quality

⚠️  Risky to relax filters without better metrics
""".format(len(findings)))

print("\n" + "=" * 80)
print("✅ ANALYSIS COMPLETE")
print("=" * 80)
