#!/usr/bin/env python3
"""
Analyze LCID (Lucid Motors) for pre-market behavior
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

from api.yahoo_finance_client import YahooFinanceClient
from screeners.premarket_scanner import PremarketScanner
import yfinance as yf
from datetime import datetime
import pytz

def analyze_lcid():
    """Deep analysis of LCID"""

    symbol = 'LCID'
    print("=" * 80)
    print(f"🔍 DEEP ANALYSIS: {symbol}")
    print("=" * 80)

    client = YahooFinanceClient()
    scanner = PremarketScanner(client)

    # Get current time
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    print(f"\nCurrent Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # Get ticker info
    ticker = yf.Ticker(symbol)
    info = ticker.info

    print(f"\n💰 CURRENT PRICE INFO:")
    print(f"   Previous Close: ${info.get('previousClose', 0):.2f}")
    print(f"   Regular Market Price: ${info.get('regularMarketPrice', 0):.2f}")
    print(f"   Open: ${info.get('open', 0):.2f}")

    current_price = info.get('regularMarketPrice', 0)
    prev_close = info.get('previousClose', 0)
    if prev_close > 0:
        current_change = ((current_price - prev_close) / prev_close) * 100
        print(f"   Current Change: {current_change:+.2f}% ({'+UP' if current_change > 0 else 'DOWN'})")

    # Get pre-market data
    pm_data = client.get_premarket_data(symbol, interval="5m")

    if not pm_data.get('has_premarket_data'):
        print(f"\n❌ No pre-market data available: {pm_data.get('error', 'Unknown')}")
        return

    # Basic metrics
    print(f"\n📊 PRE-MARKET METRICS:")
    print(f"   Previous Close: ${pm_data['previous_close']:.2f}")
    print(f"   PM Price: ${pm_data['current_premarket_price']:.2f}")
    print(f"   Gap: {pm_data['gap_percent']:.2f}% ({pm_data['gap_direction']})")
    print(f"   PM High: ${pm_data['premarket_high']:.2f}")
    print(f"   PM Low: ${pm_data['premarket_low']:.2f}")
    print(f"   PM Volume: {pm_data['premarket_volume']:,}")

    # Price position analysis
    pm_high = pm_data['premarket_high']
    pm_low = pm_data['premarket_low']
    current_pm = pm_data['current_premarket_price']
    prev_close = pm_data['previous_close']

    if pm_high > pm_low:
        price_range = pm_high - pm_low
        position_in_range = (current_pm - pm_low) / price_range * 100
        fade_from_high = (pm_high - current_pm) / pm_high * 100

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
            print(f"   🚨 GAP & TRAP RISK: Faded {fade_from_high:.1f}% from high!")
        elif fade_from_high > 1.5:
            print(f"   ⚠️  CAUTION: Faded {fade_from_high:.1f}% from high")
        else:
            print(f"   ✅ HOLDING STRONG: Only {fade_from_high:.1f}% fade")

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
            print(f"\n   Last 5 bars trend:")
            for i in range(len(recent_closes)-1, 0, -1):
                change = recent_closes[i] - recent_closes[i-1]
                emoji = "📈" if change > 0 else "📉"
                print(f"   {emoji} ${recent_closes[i]:.4f} ({change:+.4f})")

            if len(recent_closes) >= 3:
                if recent_closes[-1] > recent_closes[-2] > recent_closes[-3]:
                    print(f"\n   ✅ RECENT TREND: Accelerating up (last 3 bars)")
                elif recent_closes[-1] < recent_closes[-2] < recent_closes[-3]:
                    print(f"\n   🚨 RECENT TREND: Declining (last 3 bars) - REVERSAL RISK!")
                else:
                    print(f"\n   ⚠️  RECENT TREND: Mixed")

        # Volatility
        avg_price = (pm_high + pm_low) / 2
        if avg_price > 0:
            volatility_pct = (price_range / avg_price) * 100
            print(f"\n   Volatility: {volatility_pct:.2f}%")
            if volatility_pct > 5.0:
                print(f"   🚨 HIGH VOLATILITY - Very risky!")
            elif volatility_pct > 3.0:
                print(f"   ⚠️  MODERATE VOLATILITY")
            else:
                print(f"   ✅ LOW VOLATILITY - Stable")

    # Get company info
    try:
        company_info = client.get_company_info(symbol)
        print(f"\n🏢 COMPANY INFO:")
        print(f"   Name: {company_info.get('long_name', 'Unknown')}")
        print(f"   Sector: {company_info.get('sector', 'Unknown')}")
        print(f"   Industry: {company_info.get('industry', 'Unknown')}")
        print(f"   Market Cap: ${company_info.get('market_cap', 0)/1e9:.2f}B")
        print(f"   Beta: {company_info.get('beta', 'N/A')}")
        print(f"   Short %: {company_info.get('short_percent_of_float', 0)*100:.2f}%")
        print(f"   Float: {company_info.get('float_shares', 0)/1e6:.1f}M shares")
    except Exception as e:
        print(f"   ⚠️  Could not get company info: {e}")

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

        # Confidence breakdown
        if result['trade_confidence'] >= 70:
            print(f"   ✅ HIGH CONFIDENCE - Good setup")
        elif result['trade_confidence'] >= 50:
            print(f"   ⚠️  MODERATE CONFIDENCE - Proceed with caution")
        else:
            print(f"   🚨 LOW CONFIDENCE - High risk")

        print(f"\n⚠️  RISK INDICATORS:")
        risks = result['risk_indicators']
        high_risks = []
        for risk_type, level in risks.items():
            if level in ['High', 'Extreme']:
                emoji = "🚨"
                high_risks.append(risk_type)
            elif level in ['Moderate', 'Moderate-High']:
                emoji = "⚠️"
            else:
                emoji = "✅"
            print(f"   {emoji} {risk_type.replace('_', ' ').title()}: {level}")

        if high_risks:
            print(f"\n   🚨 WARNING: {len(high_risks)} HIGH RISK factors detected!")
            for risk in high_risks:
                print(f"      - {risk.replace('_', ' ').title()}")

    # Compare to current reality
    if current_price > 0 and prev_close > 0:
        print(f"\n📊 REALITY CHECK (Current Market):")
        print(f"   Pre-market predicted: {pm_data['gap_direction'].upper()} {pm_data['gap_percent']:.2f}%")
        print(f"   Current result: {'+UP' if current_change > 0 else 'DOWN'} {current_change:+.2f}%")

        if pm_data['gap_direction'] == 'up' and current_change > 0:
            print(f"   ✅ SUCCESS - Gap & Go!")
        elif pm_data['gap_direction'] == 'up' and current_change < 0:
            print(f"   ❌ FAILED - Gap & Trap!")
        elif pm_data['gap_direction'] == 'down' and current_change < 0:
            print(f"   ✅ Correctly predicted down")
        else:
            print(f"   🔄 Reversed direction")

    print("\n" + "=" * 80)
    print("💡 TRADING DECISION:")
    print("=" * 80)

    if result:
        conf = result['trade_confidence']
        gap = result['gap_percent']
        rec = result['recommendation']

        print(f"\nBased on analysis:")
        print(f"  Gap: {gap:.2f}%")
        print(f"  Confidence: {conf}/100")
        print(f"  Recommendation: {rec}")

        if conf >= 70 and position_in_range >= 90 and fade_from_high < 1.5:
            print(f"\n✅ TRADE: High probability setup")
            print(f"   - Strong position near PM high")
            print(f"   - High confidence score")
            print(f"   - Low fade risk")
        elif conf >= 50 and position_in_range >= 70:
            print(f"\n⚠️  WATCH: Moderate setup, trade with caution")
            print(f"   - Use tight stop loss")
            print(f"   - Watch for reversal signals")
        else:
            print(f"\n❌ AVOID: Too risky")
            reasons = []
            if conf < 50:
                reasons.append(f"Low confidence ({conf}/100)")
            if position_in_range < 70:
                reasons.append(f"Weak position ({position_in_range:.1f}%)")
            if fade_from_high > 3.0:
                reasons.append(f"High fade risk ({fade_from_high:.1f}%)")
            if gap < 2.0:
                reasons.append(f"Gap too small ({gap:.2f}%)")

            for reason in reasons:
                print(f"   - {reason}")

    print("=" * 80)

if __name__ == '__main__':
    analyze_lcid()
