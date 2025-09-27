#!/usr/bin/env python3
"""
Test ROE Fix - Check if ROE calculation is now correct
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

def test_roe_fix():
    """Test if ROE is now calculated correctly"""
    try:
        from main import StockAnalyzer

        analyzer = StockAnalyzer()

        # Test with AAPL
        print("🔍 Testing AAPL with ROE fix...")
        result = analyzer.analyze_stock('AAPL', include_ai_analysis=False)

        if 'error' in result:
            print(f"❌ Analysis failed: {result['error']}")
            return

        fundamental = result.get('fundamental_analysis', {})
        ratios = fundamental.get('financial_ratios', {})

        roe = ratios.get('roe')
        pe_ratio = ratios.get('pe_ratio')
        pb_ratio = ratios.get('pb_ratio')
        debt_equity = ratios.get('debt_to_equity')

        print(f"📊 CORRECTED METRICS:")
        print(f"   ROE: {roe:.3f} ({roe*100:.1f}%)")
        print(f"   P/E: {pe_ratio:.1f}")
        print(f"   P/B: {pb_ratio:.1f}")
        print(f"   D/E: {debt_equity:.2f}")

        # Check if ROE is reasonable (should be around 15-25% for AAPL)
        if roe is not None:
            roe_percent = roe * 100
            if 10 <= roe_percent <= 30:
                print(f"✅ ROE looks reasonable: {roe_percent:.1f}%")
                return True
            else:
                print(f"⚠️  ROE still seems off: {roe_percent:.1f}%")
                return False
        else:
            print("❌ ROE is None")
            return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_multiple_stocks():
    """Test multiple stocks to see pass rate"""
    try:
        from main import StockAnalyzer

        analyzer = StockAnalyzer()

        # Test some known value-ish stocks
        test_symbols = ['T', 'VZ', 'IBM', 'F', 'GE']
        passed = 0
        total = 0

        for symbol in test_symbols:
            print(f"\n🔍 Testing {symbol}...")

            try:
                result = analyzer.analyze_stock(symbol, include_ai_analysis=False)

                if 'error' in result:
                    print(f"   ❌ Analysis failed")
                    continue

                fundamental = result.get('fundamental_analysis', {})
                ratios = fundamental.get('financial_ratios', {})

                roe = ratios.get('roe')
                pe_ratio = ratios.get('pe_ratio')
                pb_ratio = ratios.get('pb_ratio')
                debt_equity = ratios.get('debt_to_equity')

                print(f"   📊 ROE: {roe*100:.1f}%, P/E: {pe_ratio:.1f}, P/B: {pb_ratio:.1f}, D/E: {debt_equity:.2f}")

                # Check if it would pass relaxed value criteria
                total += 1
                if (roe is not None and roe >= 0.05 and  # 5% ROE minimum
                    pe_ratio is not None and pe_ratio <= 25 and  # P/E ≤ 25
                    pb_ratio is not None and pb_ratio <= 5 and   # P/B ≤ 5
                    debt_equity is not None and debt_equity <= 1.5):  # D/E ≤ 1.5
                    print(f"   ✅ PASSES relaxed value criteria")
                    passed += 1
                else:
                    print(f"   ❌ FAILS value criteria")

            except Exception as e:
                print(f"   ❌ Exception: {e}")

        print(f"\n📊 RESULTS: {passed}/{total} stocks passed relaxed criteria ({passed/total*100:.1f}%)")
        return passed > 0

    except Exception as e:
        print(f"❌ Multiple stock test failed: {e}")
        return False

def main():
    print("🔧 TESTING ROE FIX")
    print("=" * 40)

    # Test 1: Single stock detailed test
    roe_fixed = test_roe_fix()

    # Test 2: Multiple stocks
    some_pass = test_multiple_stocks()

    print(f"\n🎯 SUMMARY:")
    print(f"ROE calculation fixed: {'✅' if roe_fixed else '❌'}")
    print(f"Some stocks pass criteria: {'✅' if some_pass else '❌'}")

if __name__ == "__main__":
    main()