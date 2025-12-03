#!/usr/bin/env python3
"""
Test v7.3.2 Fixes:
1. Minimum R/R threshold (1.2:1) for BUY
2. Dynamic volatility classification
3. Entry timing guidance
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from src.main import StockAnalyzer

def test_v7_3_2():
    print("\n" + "="*80)
    print("Testing v7.3.2 Fixes")
    print("="*80 + "\n")

    analyzer = StockAnalyzer()

    # Test stocks: PLTR (high vol, good R/R) and JNJ (low vol, poor R/R)
    test_stocks = [
        ('PLTR', 'swing'),  # Should get BUY with good R/R
        ('JNJ', 'swing'),   # May get HOLD due to poor R/R
    ]

    for symbol, time_horizon in test_stocks:
        print(f"\n{'='*60}")
        print(f"Testing: {symbol} ({time_horizon})")
        print(f"{'='*60}\n")

        try:
            result = analyzer.analyze_stock(symbol, time_horizon, 100000)

            if not result or result.get('error'):
                print(f"❌ Error analyzing {symbol}")
                continue

            unified = result.get('unified_recommendation', {})
            trading_plan = unified.get('trading_plan', {})

            # Extract key metrics
            recommendation = unified.get('recommendation', 'UNKNOWN')
            score = unified.get('score', 0)
            rr_ratio = trading_plan.get('rr_ratio_value', 0)
            volatility = trading_plan.get('volatility_class', 'UNKNOWN')
            entry_timing = trading_plan.get('entry_timing', 'UNKNOWN')
            entry_timing_reason = trading_plan.get('entry_timing_reason', '')

            # Display results
            print(f"✅ {symbol} Analysis:")
            print(f"   Recommendation: {recommendation}")
            print(f"   Score: {score:.1f}/10")
            print(f"   R/R Ratio: {rr_ratio:.2f}:1 {'✅ (>= 1.2)' if rr_ratio >= 1.2 else '⚠️ (< 1.2)'}")
            print(f"   Volatility: {volatility}")
            print(f"   Entry Timing: {entry_timing}")
            print(f"   Timing Reason: {entry_timing_reason[:100]}...")

            # Check Fix #1: Minimum R/R threshold
            if recommendation in ['BUY', 'STRONG_BUY']:
                if rr_ratio < 1.2:
                    print(f"\n❌ FIX #1 FAILED: BUY with R/R {rr_ratio:.2f} < 1.2")
                else:
                    print(f"\n✅ FIX #1 PASSED: BUY with R/R {rr_ratio:.2f} >= 1.2")

            # Check Fix #2: Volatility classification present
            if volatility in ['HIGH', 'MEDIUM', 'LOW']:
                print(f"✅ FIX #2 PASSED: Volatility classified as {volatility}")
            else:
                print(f"❌ FIX #2 FAILED: Volatility = {volatility}")

            # Check Fix #3: Entry timing present
            if entry_timing in ['IMMEDIATE', 'WAIT_FOR_PULLBACK', 'ON_BREAKOUT']:
                print(f"✅ FIX #3 PASSED: Entry timing = {entry_timing}")
            else:
                print(f"❌ FIX #3 FAILED: Entry timing = {entry_timing}")

        except Exception as e:
            print(f"❌ Exception testing {symbol}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*80)
    print("Testing Complete")
    print("="*80 + "\n")

if __name__ == "__main__":
    test_v7_3_2()
