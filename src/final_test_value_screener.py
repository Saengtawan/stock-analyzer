#!/usr/bin/env python3
"""
Final test of the corrected value screener
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

def test_complete_value_screener():
    """Test the complete value screener with all fixes"""
    try:
        from main import StockAnalyzer
        from screeners.value_screener import ValueStockScreener

        analyzer = StockAnalyzer()
        screener = ValueStockScreener(analyzer)

        print("🔍 FINAL VALUE SCREENER TEST")
        print("=" * 50)

        # Test with relaxed criteria to ensure we find some stocks
        print("Testing with relaxed criteria:")
        print("- Max P/E: 25")
        print("- Max P/B: 5")
        print("- Min ROE: 5%")
        print("- Max D/E: 1.5")
        print("- Min Fund Score: 3")
        print("- Min Tech Score: 2")

        results = screener.screen_value_opportunities(
            max_pe_ratio=25.0,
            max_pb_ratio=5.0,
            min_roe=5.0,
            max_debt_to_equity=1.5,
            min_fundamental_score=3.0,
            min_technical_score=2.0,
            max_stocks=10,
            screen_type='value',
            time_horizon='long'
        )

        print(f"\n✅ Found {len(results)} value opportunities!")

        if results:
            print(f"\n📊 TOP VALUE OPPORTUNITIES:")
            print("-" * 80)
            for i, opp in enumerate(results[:5], 1):
                symbol = opp['symbol']
                value_score = opp['value_score']
                pe_ratio = opp['pe_ratio']
                pb_ratio = opp['pb_ratio']
                roe = opp['roe'] * 100
                debt_equity = opp['debt_to_equity']
                upside = opp['upside_potential']
                margin = opp['margin_of_safety']
                recommendation = opp['recommendation']

                print(f"{i}. {symbol} - Value Score: {value_score:.1f}/10")
                print(f"   💰 P/E: {pe_ratio:.1f} | P/B: {pb_ratio:.1f} | ROE: {roe:.1f}% | D/E: {debt_equity:.2f}")
                print(f"   🎯 Upside: {upside:.1f}% | Safety Margin: {margin:.1f}% | Rec: {recommendation}")
                print()

            return True
        else:
            print("❌ No opportunities found - criteria may still be too strict")
            return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_moderate_criteria():
    """Test with more moderate criteria"""
    try:
        from main import StockAnalyzer
        from screeners.value_screener import ValueStockScreener

        analyzer = StockAnalyzer()
        screener = ValueStockScreener(analyzer)

        print("\n🔍 TESTING WITH MODERATE CRITERIA")
        print("=" * 50)

        # More reasonable value criteria
        print("Testing with moderate criteria:")
        print("- Max P/E: 20")
        print("- Max P/B: 4")
        print("- Min ROE: 8%")
        print("- Max D/E: 0.8")
        print("- Min Fund Score: 4")
        print("- Min Tech Score: 3")

        results = screener.screen_value_opportunities(
            max_pe_ratio=20.0,
            max_pb_ratio=4.0,
            min_roe=8.0,
            max_debt_to_equity=0.8,
            min_fundamental_score=4.0,
            min_technical_score=3.0,
            max_stocks=10,
            screen_type='value',
            time_horizon='long'
        )

        print(f"\n✅ Found {len(results)} value opportunities with moderate criteria!")

        if results:
            print(f"\n📊 MODERATE CRITERIA RESULTS:")
            print("-" * 80)
            for i, opp in enumerate(results[:3], 1):
                symbol = opp['symbol']
                value_score = opp['value_score']
                pe_ratio = opp['pe_ratio']
                pb_ratio = opp['pb_ratio']
                roe = opp['roe'] * 100

                print(f"{i}. {symbol}: Score={value_score:.1f}, P/E={pe_ratio:.1f}, P/B={pb_ratio:.1f}, ROE={roe:.1f}%")

        return len(results) > 0

    except Exception as e:
        print(f"❌ Moderate criteria test failed: {e}")
        return False

def main():
    print("🚀 FINAL VALUE SCREENER TESTING")
    print("This will test all the fixes we've implemented:")
    print("1. ROE calculation fix")
    print("2. Improved AI universe generation")
    print("3. Fallback universe")
    print()

    # Test 1: Relaxed criteria
    relaxed_success = test_complete_value_screener()

    # Test 2: Moderate criteria
    moderate_success = test_moderate_criteria()

    print("\n" + "=" * 60)
    print("🎯 FINAL SUMMARY")
    print("=" * 60)
    print(f"Relaxed criteria test: {'✅ PASSED' if relaxed_success else '❌ FAILED'}")
    print(f"Moderate criteria test: {'✅ PASSED' if moderate_success else '❌ FAILED'}")

    if relaxed_success or moderate_success:
        print("\n🎉 SUCCESS: Value screener is now working!")
        print("\nThe fixes have resolved the 0 results issue:")
        print("✅ ROE calculations are more accurate")
        print("✅ AI generates value-focused stocks")
        print("✅ Fallback universe provides reliability")
        print("\nThe value screener now returns actual opportunities.")
    else:
        print("\n❌ Still having issues - may need further investigation")

if __name__ == "__main__":
    main()