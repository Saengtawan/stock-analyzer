#!/usr/bin/env python3
"""
Analyze MAR (Marriott) and MCD (McDonald's)
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

from api.yahoo_finance_client import YahooFinanceClient
from screeners.premarket_scanner import PremarketScanner
import yfinance as yf
from datetime import datetime
import pytz

def analyze_stock(symbol, scanner):
    """Analyze a stock in detail"""

    print("\n" + "=" * 80)
    print(f"🔍 ANALYSIS: {symbol}")
    print("=" * 80)

    # Get current time
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)

    # Get ticker info
    ticker = yf.Ticker(symbol)
    info = ticker.info

    print(f"\n💰 CURRENT PRICE:")
    prev_close = info.get('previousClose', 0)
    current_price = info.get('regularMarketPrice', 0)

    print(f"   Previous Close: ${prev_close:.2f}")
    print(f"   Regular Market: ${current_price:.2f}")

    if prev_close > 0:
        current_change = ((current_price - prev_close) / prev_close) * 100
        print(f"   Change: {current_change:+.2f}% ({'UP ⬆️' if current_change > 0 else 'DOWN ⬇️'})")

    # Get pre-market data
    pm_data = scanner.client.get_premarket_data(symbol, interval="5m")

    if not pm_data.get('has_premarket_data'):
        print(f"\n❌ No pre-market data: {pm_data.get('error', 'Unknown')}")
        return None

    # Pre-market metrics
    print(f"\n📊 PRE-MARKET:")
    print(f"   PM Price: ${pm_data['current_premarket_price']:.2f}")
    print(f"   Gap: {pm_data['gap_percent']:.2f}% ({pm_data['gap_direction']})")
    print(f"   PM High: ${pm_data['premarket_high']:.2f}")
    print(f"   PM Low: ${pm_data['premarket_low']:.2f}")

    # Price position
    pm_high = pm_data['premarket_high']
    pm_low = pm_data['premarket_low']
    current_pm = pm_data['current_premarket_price']

    if pm_high > pm_low:
        price_range = pm_high - pm_low
        position = (current_pm - pm_low) / price_range * 100
        fade = (pm_high - current_pm) / pm_high * 100

        print(f"\n📍 POSITION:")
        print(f"   Range: ${pm_low:.2f} - ${pm_high:.2f}")
        print(f"   Position: {position:.1f}% from low")
        print(f"   Fade: {fade:.1f}% from high")

        if position >= 90:
            print(f"   ✅ STRONG")
        elif position >= 70:
            print(f"   ⚠️  MODERATE")
        else:
            print(f"   ❌ WEAK")

    # Price action
    bars = pm_data['premarket_bars']
    if not bars.empty:
        price_changes = bars['close'].pct_change().dropna()
        if len(price_changes) > 0:
            positive_bars = (price_changes > 0).sum()
            total_bars = len(price_changes)
            consistency = positive_bars / total_bars * 100

            print(f"\n📈 PRICE ACTION:")
            print(f"   Total bars: {total_bars}")
            print(f"   Positive bars: {positive_bars} ({consistency:.1f}%)")

            if consistency >= 80:
                print(f"   ✅ VERY STRONG momentum")
            elif consistency >= 60:
                print(f"   ✅ STRONG momentum")
            elif consistency >= 50:
                print(f"   ⚠️  MODERATE momentum")
            elif consistency >= 40:
                print(f"   ⚠️  WEAK - mixed action")
            else:
                print(f"   🚨 VERY WEAK - mostly down bars")

            # Recent trend
            if len(bars) >= 3:
                recent = bars['close'].tail(3).values
                if recent[-1] > recent[-2] > recent[-3]:
                    print(f"   ✅ Recent: Accelerating UP")
                elif recent[-1] < recent[-2] < recent[-3]:
                    print(f"   🚨 Recent: Declining (reversal risk!)")
                else:
                    print(f"   ⚠️  Recent: Mixed")

    # Scanner analysis
    result = scanner._analyze_premarket_stock(symbol, 2.0, 2.0, True)

    if result:
        print(f"\n🎯 SCANNER:")
        print(f"   Gap Score: {result['gap_score']:.1f}/10")
        print(f"   Confidence: {result['trade_confidence']}/100")
        print(f"   Recommendation: {result['recommendation']}")

        if result['trade_confidence'] >= 70:
            print(f"   ✅ HIGH confidence")
        elif result['trade_confidence'] >= 50:
            print(f"   ⚠️  MODERATE confidence")
        else:
            print(f"   🚨 LOW confidence")

        # Risks
        risks = result['risk_indicators']
        high_risk = [k for k, v in risks.items() if v in ['High', 'Extreme']]
        if high_risk:
            print(f"\n   🚨 HIGH RISKS:")
            for risk in high_risk:
                print(f"      - {risk.replace('_', ' ').title()}")

    # Reality check
    if current_price > 0 and prev_close > 0:
        print(f"\n📊 REALITY CHECK:")
        print(f"   Pre-market: {pm_data['gap_direction'].upper()} {pm_data['gap_percent']:.2f}%")
        print(f"   Current: {'+UP' if current_change > 0 else 'DOWN'} {current_change:+.2f}%")

        if pm_data['gap_direction'] == 'up' and current_change > 0:
            print(f"   ✅ SUCCESS - Gap & Go!")
        elif pm_data['gap_direction'] == 'up' and current_change < 0:
            print(f"   ❌ FAILED - Gap & Trap!")

    return result

def compare_mar_mcd():
    """Compare MAR and MCD"""

    client = YahooFinanceClient()
    scanner = PremarketScanner(client)

    results = {}

    # Analyze both
    for symbol in ['MAR', 'MCD']:
        result = analyze_stock(symbol, scanner)
        if result:
            # Get consistency
            pm_data = scanner.client.get_premarket_data(symbol, interval="5m")
            if pm_data.get('has_premarket_data'):
                bars = pm_data['premarket_bars']
                if not bars.empty:
                    price_changes = bars['close'].pct_change().dropna()
                    if len(price_changes) > 0:
                        positive = (price_changes > 0).sum()
                        result['consistency_ratio'] = positive / len(price_changes)
            results[symbol] = result

    if len(results) == 2:
        print("\n\n" + "=" * 80)
        print("⚔️  MAR vs MCD COMPARISON")
        print("=" * 80)

        print(f"\n{'Metric':<30} {'MAR':<25} {'MCD':<25}")
        print("-" * 80)

        mar = results['MAR']
        mcd = results['MCD']

        print(f"{'Gap %':<30} {mar['gap_percent']:>23.2f}% {mcd['gap_percent']:>23.2f}%")

        mar_cons = mar.get('consistency_ratio', 0) * 100
        mcd_cons = mcd.get('consistency_ratio', 0) * 100
        print(f"{'Positive Bars %':<30} {mar_cons:>22.1f}% {mcd_cons:>22.1f}%")

        def calc_pos(res):
            h, l, c = res['premarket_high'], res['premarket_low'], res['current_price']
            return (c - l) / (h - l) * 100 if h > l else 0

        mar_pos = calc_pos(mar)
        mcd_pos = calc_pos(mcd)
        print(f"{'Position':<30} {mar_pos:>22.1f}% {mcd_pos:>22.1f}%")

        print(f"{'Gap Score':<30} {mar['gap_score']:>21.1f}/10 {mcd['gap_score']:>21.1f}/10")
        print(f"{'Confidence':<30} {mar['trade_confidence']:>21}/100 {mcd['trade_confidence']:>21}/100")
        print(f"{'Recommendation':<30} {mar['recommendation']:>25} {mcd['recommendation']:>25}")

        print("\n" + "=" * 80)
        print("💡 VERDICT:")
        print("=" * 80)

        better = 'MAR' if mar['trade_confidence'] > mcd['trade_confidence'] else 'MCD'
        print(f"\n{better} has higher confidence ({results[better]['trade_confidence']}/100)")

        if mar['trade_confidence'] >= 70 or mcd['trade_confidence'] >= 70:
            print(f"\n✅ Good trading opportunities found!")
        elif mar['trade_confidence'] >= 50 or mcd['trade_confidence'] >= 50:
            print(f"\n⚠️  Moderate setups - trade with caution")
        else:
            print(f"\n❌ Both are risky - consider avoiding")

if __name__ == '__main__':
    compare_mar_mcd()
