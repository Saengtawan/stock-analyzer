#!/usr/bin/env python3
"""
Test Filter Effectiveness - Check how many AI-generated stocks actually pass filters
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

def test_multiple_stocks():
    """Test multiple stocks from AI universe to see pass rate"""
    try:
        from ai_universe_generator import AIUniverseGenerator
        from main import StockAnalyzer

        # Generate AI universe
        generator = AIUniverseGenerator()
        criteria = {
            'max_stocks': 15,
            'screen_type': 'value',
            'max_pe_ratio': 20.0,
            'max_pb_ratio': 4.0,
            'min_roe': 8.0
        }

        print("Generating AI universe...")
        symbols = generator.generate_value_universe(criteria)
        print(f"✅ Generated {len(symbols)} symbols: {symbols}")

        # Test filtering criteria
        max_pe_ratio = 20.0
        max_pb_ratio = 4.0
        min_roe = 8.0
        max_debt_to_equity = 0.8
        min_fundamental_score = 4.0
        min_technical_score = 3.0

        print(f"\nTesting with criteria:")
        print(f"Max P/E: {max_pe_ratio}")
        print(f"Max P/B: {max_pb_ratio}")
        print(f"Min ROE: {min_roe}%")
        print(f"Max D/E: {max_debt_to_equity}")
        print(f"Min Fund Score: {min_fundamental_score}")
        print(f"Min Tech Score: {min_technical_score}")

        # Initialize analyzer
        analyzer = StockAnalyzer()

        # Test first 10 symbols
        test_symbols = symbols[:10]
        results = []

        for symbol in test_symbols:
            print(f"\n🔍 Testing {symbol}...")

            try:
                # Quick analysis without AI
                result = analyzer.analyze_stock(symbol, include_ai_analysis=False)

                if 'error' in result:
                    print(f"   ❌ Analysis error: {result['error']}")
                    continue

                # Extract metrics
                fundamental = result.get('fundamental_analysis', {})
                ratios = fundamental.get('financial_ratios', {})
                technical = result.get('technical_analysis', {})

                pe_ratio = ratios.get('pe_ratio')
                pb_ratio = ratios.get('pb_ratio')
                roe = ratios.get('roe')
                debt_equity = ratios.get('debt_to_equity')
                fundamental_score = fundamental.get('overall_score', 0)
                technical_score = technical.get('technical_score', {}).get('total_score', 0)

                # Check if all metrics exist
                if not all([pe_ratio is not None, pb_ratio is not None,
                           roe is not None, debt_equity is not None]):
                    print(f"   ⚠️  Missing metrics")
                    continue

                print(f"   📊 P/E: {pe_ratio:.1f}, P/B: {pb_ratio:.1f}, ROE: {roe:.1f}%, D/E: {debt_equity:.2f}")
                print(f"   📊 Fund Score: {fundamental_score:.1f}, Tech Score: {technical_score:.1f}")

                # Test basic filter first (from _analyze_stock_for_value)
                basic_pass = True
                basic_reasons = []
                if pe_ratio > 50:
                    basic_pass = False
                    basic_reasons.append(f"P/E {pe_ratio:.1f} > 50")
                if pb_ratio > 10:
                    basic_pass = False
                    basic_reasons.append(f"P/B {pb_ratio:.1f} > 10")
                if debt_equity > 2.0:
                    basic_pass = False
                    basic_reasons.append(f"D/E {debt_equity:.2f} > 2.0")

                if not basic_pass:
                    print(f"   ❌ BASIC FAIL: {', '.join(basic_reasons)}")
                    continue

                # Test detailed filter
                detailed_pass = True
                detailed_reasons = []

                if pe_ratio > max_pe_ratio:
                    detailed_pass = False
                    detailed_reasons.append(f"P/E {pe_ratio:.1f} > {max_pe_ratio}")
                if pb_ratio > max_pb_ratio:
                    detailed_pass = False
                    detailed_reasons.append(f"P/B {pb_ratio:.1f} > {max_pb_ratio}")
                if roe < min_roe:
                    detailed_pass = False
                    detailed_reasons.append(f"ROE {roe:.1f}% < {min_roe}%")
                if debt_equity > max_debt_to_equity:
                    detailed_pass = False
                    detailed_reasons.append(f"D/E {debt_equity:.2f} > {max_debt_to_equity}")
                if fundamental_score < min_fundamental_score:
                    detailed_pass = False
                    detailed_reasons.append(f"Fund {fundamental_score:.1f} < {min_fundamental_score}")
                if technical_score < min_technical_score:
                    detailed_pass = False
                    detailed_reasons.append(f"Tech {technical_score:.1f} < {min_technical_score}")

                if detailed_pass:
                    print(f"   ✅ PASSED ALL FILTERS!")
                    results.append(symbol)
                else:
                    print(f"   ❌ DETAILED FAIL: {', '.join(detailed_reasons)}")

            except Exception as e:
                print(f"   ❌ Exception: {e}")

        print(f"\n📊 RESULTS:")
        print(f"Symbols tested: {len(test_symbols)}")
        print(f"Symbols passed: {len(results)}")
        print(f"Pass rate: {len(results)/len(test_symbols)*100:.1f}%")
        print(f"Passed symbols: {results}")

        return len(results) > 0

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def main():
    print("🔧 TESTING FILTER EFFECTIVENESS")
    print("=" * 50)

    success = test_multiple_stocks()

    print(f"\n🎯 CONCLUSION:")
    if success:
        print("✅ Some stocks pass filters - screener should work")
    else:
        print("❌ NO stocks pass filters - criteria too strict or AI universe issue")
        print("\n💡 RECOMMENDATIONS:")
        print("1. Relax filtering criteria further")
        print("2. Improve AI universe generation prompts")
        print("3. Add fallback stock universe")

if __name__ == "__main__":
    main()