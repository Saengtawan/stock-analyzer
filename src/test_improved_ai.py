#!/usr/bin/env python3
"""
Test improved AI universe generation
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

def test_improved_ai_universe():
    """Test the improved AI universe generation"""
    try:
        from ai_universe_generator import AIUniverseGenerator

        generator = AIUniverseGenerator()

        # Test with relaxed criteria
        criteria = {
            'max_stocks': 15,
            'screen_type': 'value',
            'max_pe_ratio': 20.0,
            'max_pb_ratio': 4.0,
            'min_roe': 8.0
        }

        print("🤖 Testing improved AI universe generation...")
        print(f"Criteria: {criteria}")

        symbols = generator.generate_value_universe(criteria)

        print(f"✅ Generated {len(symbols)} symbols:")
        print(f"Symbols: {symbols}")

        # Check if we got different types of stocks
        expected_value_stocks = ['T', 'VZ', 'XOM', 'CVX', 'COP', 'KEY', 'FITB', 'RF', 'CAT', 'MMM', 'BA', 'DOW', 'KHC', 'GIS']
        excluded_growth_stocks = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA']

        found_value = [s for s in symbols if s in expected_value_stocks]
        found_growth = [s for s in symbols if s in excluded_growth_stocks]

        print(f"\n📊 ANALYSIS:")
        print(f"Value stocks found: {found_value}")
        print(f"Growth stocks found: {found_growth}")

        if len(found_value) > len(found_growth):
            print("✅ Improvement: More value-oriented stocks than growth stocks")
            return True
        else:
            print("⚠️  Still generating more growth than value stocks")
            return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_full_value_screening():
    """Test complete value screening with improved AI"""
    try:
        from main import StockAnalyzer
        from screeners.value_screener import ValueStockScreener

        analyzer = StockAnalyzer()
        screener = ValueStockScreener(analyzer)

        print(f"\n🔍 Testing complete value screener with improved AI...")

        # Use very relaxed criteria to maximize chances of finding stocks
        results = screener.screen_value_opportunities(
            max_pe_ratio=25.0,  # Very relaxed
            max_pb_ratio=5.0,   # Very relaxed
            min_roe=5.0,        # Very relaxed
            max_debt_to_equity=1.5,  # Very relaxed
            min_fundamental_score=3.0,  # Very relaxed
            min_technical_score=2.0,    # Very relaxed
            max_stocks=20,
            screen_type='value',
            time_horizon='long'
        )

        print(f"✅ Value screener found {len(results)} opportunities")

        if results:
            print(f"\n📊 TOP VALUE OPPORTUNITIES:")
            for i, opp in enumerate(results[:3], 1):
                print(f"{i}. {opp['symbol']}: Score={opp['value_score']:.1f}, P/E={opp['pe_ratio']:.1f}, P/B={opp['pb_ratio']:.1f}, ROE={opp['roe']*100:.1f}%")

        return len(results) > 0

    except Exception as e:
        print(f"❌ Complete screening test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🔧 TESTING IMPROVED AI UNIVERSE GENERATION")
    print("=" * 60)

    # Test 1: Improved AI universe
    ai_improved = test_improved_ai_universe()

    # Test 2: Complete screening
    screening_works = test_full_value_screening()

    print(f"\n🎯 FINAL RESULTS:")
    print(f"AI generation improved: {'✅' if ai_improved else '❌'}")
    print(f"Value screening working: {'✅' if screening_works else '❌'}")

    if screening_works:
        print("\n🚀 SUCCESS: Value screener is now finding opportunities!")
    else:
        print("\n❌ Still need more fixes to get screening working")

if __name__ == "__main__":
    main()