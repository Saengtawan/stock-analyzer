#!/usr/bin/env python3
"""
Deep analysis: Compare NFLX (Gap & Trap) vs TSLA (Gap & Go)
To find signals that predict success vs failure
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

from api.yahoo_finance_client import YahooFinanceClient
from screeners.premarket_scanner import PremarketScanner
import pandas as pd
import numpy as np

def analyze_stock_detailed(symbol, scanner):
    """Detailed analysis of a stock's pre-market behavior"""

    print("=" * 80)
    print(f"🔍 DEEP ANALYSIS: {symbol}")
    print("=" * 80)

    # Get pre-market data
    pm_data = scanner.client.get_premarket_data(symbol, interval="5m")

    if not pm_data.get('has_premarket_data'):
        print(f"❌ No pre-market data available")
        return None

    # Basic metrics
    print(f"\n📊 BASIC METRICS:")
    print(f"   Previous Close: ${pm_data['previous_close']:.2f}")
    print(f"   Current PM Price: ${pm_data['current_premarket_price']:.2f}")
    print(f"   Gap: {pm_data['gap_percent']:.2f}% ({pm_data['gap_direction']})")
    print(f"   PM High: ${pm_data['premarket_high']:.2f}")
    print(f"   PM Low: ${pm_data['premarket_low']:.2f}")

    # Price position analysis
    pm_high = pm_data['premarket_high']
    pm_low = pm_data['premarket_low']
    current = pm_data['current_premarket_price']
    prev_close = pm_data['previous_close']

    if pm_high > pm_low:
        price_range = pm_high - pm_low
        position_in_range = (current - pm_low) / price_range * 100
        fade_from_high = (pm_high - current) / pm_high * 100

        print(f"\n📍 PRICE POSITION:")
        print(f"   PM Range: ${pm_low:.2f} - ${pm_high:.2f} (${price_range:.2f})")
        print(f"   Position: {position_in_range:.1f}% from low")
        print(f"   Fade from high: {fade_from_high:.1f}%")

        if position_in_range >= 90:
            print(f"   ✅ STRONG - Near PM high (top 10%)")
        elif position_in_range >= 70:
            print(f"   ⚠️  MODERATE - Upper half")
        elif position_in_range >= 50:
            print(f"   ⚠️  WEAK - Middle range")
        else:
            print(f"   ❌ VERY WEAK - Lower half")

        if fade_from_high > 3.0:
            print(f"   🚨 GAP & TRAP RISK: Faded >{fade_from_high:.1f}% from high!")
        elif fade_from_high > 1.5:
            print(f"   ⚠️  CAUTION: Faded {fade_from_high:.1f}% from high")

    # Pre-market bars analysis
    bars = pm_data['premarket_bars']
    if not bars.empty:
        print(f"\n📈 PRICE ACTION ({len(bars)} bars):")

        # Calculate momentum
        price_changes = bars['close'].pct_change().dropna()
        positive_bars = (price_changes > 0).sum()
        negative_bars = (price_changes < 0).sum()
        total_bars = len(price_changes)

        if total_bars > 0:
            consistency_ratio = positive_bars / total_bars
            print(f"   Positive bars: {positive_bars}/{total_bars} ({consistency_ratio*100:.1f}%)")

            if consistency_ratio >= 0.8:
                print(f"   ✅ VERY CONSISTENT - Strong uptrend")
            elif consistency_ratio >= 0.6:
                print(f"   ✅ CONSISTENT - Good momentum")
            elif consistency_ratio >= 0.5:
                print(f"   ⚠️  MIXED - Choppy action")
            else:
                print(f"   ❌ WEAK - More down bars than up")

        # Recent trend (last 5 bars)
        if len(bars) >= 5:
            recent_closes = bars['close'].tail(5).values
            if len(recent_closes) >= 3:
                if recent_closes[-1] > recent_closes[-2] > recent_closes[-3]:
                    print(f"   ✅ RECENT TREND: Accelerating up (last 3 bars)")
                elif recent_closes[-1] < recent_closes[-2] < recent_closes[-3]:
                    print(f"   🚨 RECENT TREND: Declining (last 3 bars) - REVERSAL RISK!")
                else:
                    print(f"   ⚠️  RECENT TREND: Mixed")

        # Volatility
        avg_price = (pm_high + pm_low) / 2
        if avg_price > 0:
            volatility_pct = (price_range / avg_price) * 100
            print(f"   Volatility: {volatility_pct:.2f}%")
            if volatility_pct > 5.0:
                print(f"   🚨 HIGH VOLATILITY - Risky!")
            elif volatility_pct > 3.0:
                print(f"   ⚠️  MODERATE VOLATILITY")
            else:
                print(f"   ✅ LOW VOLATILITY - Stable")

    # Get company info
    try:
        company_info = scanner.client.get_company_info(symbol)
        print(f"\n🏢 COMPANY INFO:")
        print(f"   Sector: {company_info.get('sector', 'Unknown')}")
        print(f"   Market Cap: ${company_info.get('market_cap', 0)/1e9:.2f}B")
        print(f"   Beta: {company_info.get('beta', 'N/A')}")
        print(f"   Short %: {company_info.get('short_percent_of_float', 0)*100:.2f}%")
    except:
        pass

    # Run scanner analysis
    result = scanner._analyze_premarket_stock(
        symbol,
        min_gap_pct=2.0,
        min_volume_ratio=2.0,
        demo_mode=True
    )

    if result:
        print(f"\n🎯 SCANNER ANALYSIS:")
        print(f"   Gap Score: {result['gap_score']:.1f}/10")
        print(f"   Trade Confidence: {result['trade_confidence']}/100")
        print(f"   Recommendation: {result['recommendation']}")

        print(f"\n⚠️  RISK INDICATORS:")
        risks = result['risk_indicators']
        for risk_type, level in risks.items():
            emoji = "🚨" if level in ['High', 'Extreme'] else "⚠️" if level == 'Moderate' else "✅"
            print(f"   {emoji} {risk_type.replace('_', ' ').title()}: {level}")

    return result

def compare_stocks(symbol1, symbol2):
    """Compare two stocks side by side"""

    print("\n\n")
    print("=" * 80)
    print(f"⚔️  COMPARISON: {symbol1} vs {symbol2}")
    print("=" * 80)

    client = YahooFinanceClient()
    scanner = PremarketScanner(client)

    print(f"\n{'Metric':<30} {symbol1:<20} {symbol2:<20}")
    print("-" * 80)

    result1 = scanner._analyze_premarket_stock(symbol1, 2.0, 2.0, True)
    result2 = scanner._analyze_premarket_stock(symbol2, 2.0, 2.0, True)

    if result1 and result2:
        # Gap comparison
        print(f"{'Gap %':<30} {result1['gap_percent']:>18.2f}% {result2['gap_percent']:>18.2f}%")

        # Position comparison
        pm1_high = result1['premarket_high']
        pm1_low = result1['premarket_low']
        pm1_curr = result1['current_price']
        pos1 = (pm1_curr - pm1_low) / (pm1_high - pm1_low) * 100 if pm1_high > pm1_low else 0

        pm2_high = result2['premarket_high']
        pm2_low = result2['premarket_low']
        pm2_curr = result2['current_price']
        pos2 = (pm2_curr - pm2_low) / (pm2_high - pm2_low) * 100 if pm2_high > pm2_low else 0

        print(f"{'Position in PM Range':<30} {pos1:>17.1f}% {pos2:>17.1f}%")

        # Fade from high
        fade1 = (pm1_high - pm1_curr) / pm1_high * 100 if pm1_high > 0 else 0
        fade2 = (pm2_high - pm2_curr) / pm2_high * 100 if pm2_high > 0 else 0
        print(f"{'Fade from PM High':<30} {fade1:>17.1f}% {fade2:>17.1f}%")

        # Scores
        print(f"{'Gap Score':<30} {result1['gap_score']:>17.1f}/10 {result2['gap_score']:>17.1f}/10")
        print(f"{'Trade Confidence':<30} {result1['trade_confidence']:>16}/100 {result2['trade_confidence']:>16}/100")
        print(f"{'Recommendation':<30} {result1['recommendation']:>20} {result2['recommendation']:>20}")

        # Risk comparison
        print(f"\n{'Risk Indicator':<30} {symbol1:<20} {symbol2:<20}")
        print("-" * 80)

        risks1 = result1['risk_indicators']
        risks2 = result2['risk_indicators']

        for risk_type in risks1.keys():
            r1 = risks1[risk_type]
            r2 = risks2[risk_type]

            # Highlight differences
            if r1 != r2:
                marker1 = "🚨" if r1 in ['High', 'Extreme'] else "⚠️" if r1 == 'Moderate' else "✅"
                marker2 = "🚨" if r2 in ['High', 'Extreme'] else "⚠️" if r2 == 'Moderate' else "✅"
                print(f"{risk_type.replace('_', ' ').title():<30} {marker1} {r1:<18} {marker2} {r2:<18}")

    print("\n" + "=" * 80)
    print("🎯 KEY DIFFERENCES:")
    print("=" * 80)

    if result1 and result2:
        # Analyze key differences
        if fade1 > 3.0 and fade2 < 1.5:
            print(f"1. 🚨 {symbol1} FADED {fade1:.1f}% from high (Gap & Trap signal!)")
            print(f"   ✅ {symbol2} stayed near high (only {fade2:.1f}% fade)")

        if pos1 < 70 and pos2 >= 90:
            print(f"2. ⚠️  {symbol1} weak position ({pos1:.1f}% in range)")
            print(f"   ✅ {symbol2} strong position ({pos2:.1f}% in range)")

        if risks1['gap_and_trap_risk'] in ['High', 'Moderate'] and risks2['gap_and_trap_risk'] == 'Low':
            print(f"3. 🚨 {symbol1} has {risks1['gap_and_trap_risk']} Gap & Trap Risk")
            print(f"   ✅ {symbol2} has Low Gap & Trap Risk")

        if result1['gap_percent'] < 2.0 and result2['gap_percent'] >= 2.0:
            print(f"4. ⚠️  {symbol1} gap too small ({result1['gap_percent']:.2f}% < 2% threshold)")
            print(f"   ✅ {symbol2} gap in good range ({result2['gap_percent']:.2f}%)")

if __name__ == '__main__':
    client = YahooFinanceClient()
    scanner = PremarketScanner(client)

    # Analyze each stock
    analyze_stock_detailed('NFLX', scanner)
    print("\n\n")
    analyze_stock_detailed('TSLA', scanner)

    # Side-by-side comparison
    compare_stocks('NFLX', 'TSLA')

    print("\n\n" + "=" * 80)
    print("💡 CONCLUSION:")
    print("=" * 80)
    print("Key signals that predicted NFLX would fail (Gap & Trap):")
    print("1. Faded >3% from pre-market high")
    print("2. Price in lower range (not near PM high)")
    print("3. Gap too small (<2%)")
    print("4. Declining recent bars (reversal pattern)")
    print("\nKey signals that predicted TSLA would succeed (Gap & Go):")
    print("1. Stayed near pre-market high")
    print("2. Strong position in PM range (>90%)")
    print("3. Gap in sweet spot (2-3%)")
    print("4. Consistent uptrend in pre-market")
    print("=" * 80)
