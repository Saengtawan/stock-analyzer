#!/usr/bin/env python3
"""
Diagnose Backtest Issues
========================

Check why:
1. Macro data returns UNKNOWN in July-August
2. Fundamental screener finds 0 stocks in June
"""

import sys
from datetime import datetime
from src.complete_growth_system import CompleteGrowthSystem
from src.macro_regime_detector import MacroRegimeDetector
from src.fundamental_screener import FundamentalScreener

print("="*80)
print("🔍 DIAGNOSING BACKTEST ISSUES")
print("="*80)

# Test dates that had issues
test_dates = [
    ('2025-06-02', 'June 2 - Found 0 fundamental passes'),
    ('2025-07-09', 'July 9 - Macro returned UNKNOWN'),
    ('2025-09-28', 'Sept 28 - Should work (winning date)'),
]

macro_detector = MacroRegimeDetector()
fundamental_screener = FundamentalScreener()
system = CompleteGrowthSystem()

for date_str, desc in test_dates:
    date = datetime.strptime(date_str, '%Y-%m-%d')

    print(f"\n{'='*80}")
    print(f"📅 {desc}")
    print(f"{'='*80}")

    # Test macro detection
    print("\n1️⃣ Testing Macro Detection:")
    try:
        macro = macro_detector.get_macro_regime(date)
        print(f"   Fed: {macro['fed_stance']}")
        print(f"   Breadth: {macro['market_health']}")
        print(f"   Sector: {macro['sector_stage']}")
        print(f"   Risk Score: {macro['risk_score']}/3")
        print(f"   Risk On: {macro['risk_on']}")

        if macro['fed_stance'] == 'UNKNOWN' or macro['market_health'] == 'UNKNOWN':
            print("   ❌ ISSUE: Macro data UNKNOWN!")
            print(f"   Fed details: {macro['details']['fed']}")
            print(f"   Breadth details: {macro['details']['breadth']}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

    # Test fundamental screening
    print("\n2️⃣ Testing Fundamental Screening:")
    try:
        # Test a few key stocks
        test_stocks = ['PLTR', 'NVDA', 'GOOGL', 'META', 'AAPL']

        for symbol in test_stocks:
            result = fundamental_screener.screen_stock(symbol, date)

            if result['pass']:
                print(f"   ✅ {symbol}: PASS ({result['total_score']}/200)")
            else:
                print(f"   ❌ {symbol}: FAIL ({result['total_score']}/200) - "
                      f"Fund: {result['fundamental']['quality_score']}, "
                      f"Cat: {result['catalyst']['catalyst_score']}")

                # Show why it failed
                if 'error' in result['fundamental']:
                    print(f"      Fund Error: {result['fundamental']['error']}")
                if 'error' in result['catalyst']:
                    print(f"      Catalyst Error: {result['catalyst']['error']}")

    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

    # Test complete system
    print("\n3️⃣ Testing Complete System:")
    try:
        candidates = system.screen_for_entries(date)
        print(f"   Result: {len(candidates)} stocks ready to buy")

        if candidates:
            for stock in candidates:
                print(f"   - {stock['symbol']}: Score {stock['total_score']}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "="*80)
print("🎯 DIAGNOSIS COMPLETE")
print("="*80)
