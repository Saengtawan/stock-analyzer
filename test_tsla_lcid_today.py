#!/usr/bin/env python3
"""
Test v6.0 system with TSLA and LCID today
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

from api.yahoo_finance_client import YahooFinanceClient
from screeners.premarket_scanner import PremarketScanner
import yfinance as yf
from datetime import datetime
import pytz

def test_stock_today(symbol, scanner):
    """Test a stock with v6.0 system"""

    print("\n" + "=" * 100)
    print(f"🔍 วิเคราะห์ {symbol} ด้วยระบบ v6.0")
    print("=" * 100)

    # Get current time
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    print(f"\nเวลาปัจจุบัน: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # Get current price
    ticker = yf.Ticker(symbol)
    info = ticker.info

    prev_close = info.get('previousClose', 0)
    current_price = info.get('regularMarketPrice') or info.get('currentPrice', 0)

    print(f"\n💰 ราคา:")
    print(f"   Previous Close: ${prev_close:.2f}")
    print(f"   Current Price: ${current_price:.2f}")

    if prev_close > 0 and current_price > 0:
        current_change = ((current_price - prev_close) / prev_close) * 100
        print(f"   การเปลี่ยนแปลง: {current_change:+.2f}%")
        if current_change > 0:
            print(f"   📈 UP (ถ้า pre-market gap up แล้ว → GAP & GO!)")
        else:
            print(f"   📉 DOWN (ถ้า pre-market gap up แล้ว → GAP & TRAP!)")

    # Get pre-market data
    pm_data = scanner.client.get_premarket_data(symbol, interval="5m")

    if not pm_data.get('has_premarket_data'):
        print(f"\n❌ ไม่มีข้อมูล pre-market: {pm_data.get('error', 'Unknown')}")
        print(f"   (อาจจะเป็นเพราะตลาดปิดแล้ว หรือยังไม่เปิด)")
        return None

    # Pre-market metrics
    print(f"\n📊 PRE-MARKET:")
    print(f"   Gap: {pm_data['gap_percent']:.2f}% ({pm_data['gap_direction']})")
    print(f"   PM Price: ${pm_data['current_premarket_price']:.2f}")
    print(f"   PM High: ${pm_data['premarket_high']:.2f}")
    print(f"   PM Low: ${pm_data['premarket_low']:.2f}")

    # Price position
    pm_high = pm_data['premarket_high']
    pm_low = pm_data['premarket_low']
    current_pm = pm_data['current_premarket_price']

    if pm_high > pm_low:
        position = (current_pm - pm_low) / (pm_high - pm_low) * 100
        print(f"\n📍 ตำแหน่ง: {position:.1f}% จากต่ำสุด")
        if position >= 90:
            print(f"   ✅ แข็งแกร่ง (ใกล้จุดสูงสุด)")
        elif position >= 70:
            print(f"   ⚠️  ปานกลาง")
        else:
            print(f"   ❌ อ่อนแอ")

    # Consistency
    bars = pm_data['premarket_bars']
    consistency_ratio = None

    if not bars.empty:
        price_changes = bars['close'].pct_change().dropna()
        if len(price_changes) > 0:
            positive_bars = (price_changes > 0).sum()
            consistency_ratio = positive_bars / len(price_changes)
            consistency_pct = consistency_ratio * 100

            print(f"\n📈 PRICE ACTION:")
            print(f"   Positive bars: {positive_bars}/{len(price_changes)} ({consistency_pct:.1f}%)")

            if consistency_ratio >= 0.95:
                print(f"   🚨 OVERBOUGHT WARNING! (ระบบ v6.0 จะลด Confidence)")
            elif consistency_ratio >= 0.8:
                print(f"   ✅ แข็งแกร่ง (แต่ไม่ร้อนเกินไป)")
            elif consistency_ratio >= 0.6:
                print(f"   ✅ ดีมาก (SWEET SPOT!)")
            elif consistency_ratio >= 0.5:
                print(f"   ⚠️  ปานกลาง")
            else:
                print(f"   ❌ อ่อนแอ")

    # Run scanner with v6.0
    result = scanner._analyze_premarket_stock(symbol, 2.0, 2.0, True)

    if result:
        print(f"\n🎯 ผลการวิเคราะห์ (ระบบ v6.0):")
        print(f"   Gap Score: {result['gap_score']:.1f}/10")
        print(f"   Confidence: {result['trade_confidence']}/100")
        print(f"   Recommendation: {result['recommendation']}")

        conf = result['trade_confidence']

        # v6.0 ranges
        if 60 <= conf <= 75:
            print(f"\n   ✅ SWEET SPOT v6.0 (60-75): ควรเทรด!")
            print(f"      Win rate คาด: ~59%")
        elif conf >= 70:
            print(f"\n   ✅ ความมั่นใจสูง: เทรดได้")
        elif conf >= 50:
            print(f"\n   ⚠️  ความมั่นใจปานกลาง: ระวัง")
        else:
            print(f"\n   ❌ ความมั่นใจต่ำ: หลีกเลี่ยง")

        # Risk warnings
        risks = result['risk_indicators']
        high_risks = [k for k, v in risks.items() if v in ['High', 'Extreme']]
        if high_risks:
            print(f"\n   🚨 ความเสี่ยงสูง:")
            for risk in high_risks:
                print(f"      - {risk.replace('_', ' ')}")

        return result

    return None

def compare_tsla_lcid():
    """Compare TSLA and LCID with v6.0 system"""

    print("=" * 100)
    print("🧪 ทดสอบระบบ v6.0 กับ TSLA และ LCID")
    print("=" * 100)

    client = YahooFinanceClient()
    scanner = PremarketScanner(client)

    results = {}

    for symbol in ['TSLA', 'LCID']:
        result = test_stock_today(symbol, scanner)
        if result:
            results[symbol] = result

    # Compare
    if len(results) == 2:
        print("\n\n" + "=" * 100)
        print("⚔️  TSLA vs LCID (ระบบ v6.0)")
        print("=" * 100)

        print(f"\n{'Metric':<30} {'TSLA':<25} {'LCID':<25}")
        print("-" * 100)

        tsla = results['TSLA']
        lcid = results['LCID']

        print(f"{'Gap %':<30} {tsla['gap_percent']:>23.2f}% {lcid['gap_percent']:>23.2f}%")
        print(f"{'Gap Score':<30} {tsla['gap_score']:>21.1f}/10 {lcid['gap_score']:>21.1f}/10")
        print(f"{'Confidence (v6.0)':<30} {tsla['trade_confidence']:>21}/100 {lcid['trade_confidence']:>21}/100")
        print(f"{'Recommendation':<30} {tsla['recommendation']:>25} {lcid['recommendation']:>25}")

        print("\n" + "=" * 100)
        print("💡 VERDICT (ระบบ v6.0):")
        print("=" * 100)

        better = 'TSLA' if tsla['trade_confidence'] > lcid['trade_confidence'] else 'LCID'
        print(f"\n{better} มี Confidence สูงกว่า ({results[better]['trade_confidence']}/100)")

        # Check if in v6.0 sweet spot (60-75)
        tsla_in_sweet = 60 <= tsla['trade_confidence'] <= 75
        lcid_in_sweet = 60 <= lcid['trade_confidence'] <= 75

        if tsla_in_sweet:
            print(f"\n✅ TSLA อยู่ใน Sweet Spot v6.0 (60-75) - เทรดได้!")
        if lcid_in_sweet:
            print(f"\n✅ LCID อยู่ใน Sweet Spot v6.0 (60-75) - เทรดได้!")

        if not tsla_in_sweet and not lcid_in_sweet:
            print(f"\n⚠️  ทั้ง 2 ตัวไม่อยู่ใน Sweet Spot (60-75)")
            if tsla['trade_confidence'] >= 50 or lcid['trade_confidence'] >= 50:
                print(f"   แต่มี Confidence ≥50 - เทรดได้แต่ระวัง")
            else:
                print(f"   Confidence ต่ำ - ควรหลีกเลี่ยง")

    print("\n" + "=" * 100)

if __name__ == '__main__':
    compare_tsla_lcid()
