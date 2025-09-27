#!/usr/bin/env python3
"""
Debug Value Screener - Test each component step by step
"""
import sys
import os
import json
from datetime import datetime
from loguru import logger

# Add src to path
sys.path.append(os.path.dirname(__file__))

def test_ai_universe_generation():
    """Test if AI universe generator is working"""
    print("=" * 60)
    print("1. TESTING AI UNIVERSE GENERATION")
    print("=" * 60)

    try:
        from ai_universe_generator import AIUniverseGenerator

        generator = AIUniverseGenerator()

        # Test with simple criteria
        criteria = {
            'max_stocks': 25,
            'time_horizon': 'long',
            'screen_type': 'value',
            'max_pe_ratio': 20.0,
            'max_pb_ratio': 4.0,
            'min_roe': 8.0
        }

        print(f"🤖 Testing AI universe generation with criteria: {criteria}")

        # Call the generate_value_universe method
        symbols = generator.generate_value_universe(criteria)

        print(f"✅ AI Generator returned {len(symbols)} symbols")
        print(f"First 10 symbols: {symbols[:10]}")

        return symbols

    except Exception as e:
        print(f"❌ AI Universe Generation FAILED: {e}")
        return []

def test_stock_analysis(symbols):
    """Test individual stock analysis"""
    print("\n" + "=" * 60)
    print("2. TESTING INDIVIDUAL STOCK ANALYSIS")
    print("=" * 60)

    if not symbols:
        print("❌ No symbols to test - AI generation failed")
        return []

    try:
        from main import StockAnalyzer

        analyzer = StockAnalyzer()

        # Test first few symbols
        test_symbols = symbols[:5]
        results = []

        for symbol in test_symbols:
            print(f"\n🔍 Testing analysis for {symbol}...")

            try:
                # Analyze stock without AI recommendations for faster testing
                result = analyzer.analyze_stock(
                    symbol,
                    time_horizon='long',
                    account_value=100000,
                    include_ai_analysis=False
                )

                if 'error' in result:
                    print(f"   ❌ {symbol}: Error - {result['error']}")
                    continue

                # Extract key metrics
                fundamental = result.get('fundamental_analysis', {})
                ratios = fundamental.get('financial_ratios', {})

                pe_ratio = ratios.get('pe_ratio', None)
                pb_ratio = ratios.get('pb_ratio', None)
                roe = ratios.get('roe', None)
                debt_equity = ratios.get('debt_to_equity', None)

                print(f"   📊 {symbol}: P/E={pe_ratio}, P/B={pb_ratio}, ROE={roe}%, D/E={debt_equity}")

                # Check if metrics exist
                if all([pe_ratio, pb_ratio, roe, debt_equity]):
                    print(f"   ✅ {symbol}: All key metrics available")
                    results.append({
                        'symbol': symbol,
                        'pe_ratio': pe_ratio,
                        'pb_ratio': pb_ratio,
                        'roe': roe,
                        'debt_to_equity': debt_equity,
                        'result': result
                    })
                else:
                    print(f"   ⚠️  {symbol}: Missing metrics - PE={pe_ratio}, PB={pb_ratio}, ROE={roe}, DE={debt_equity}")

            except Exception as e:
                print(f"   ❌ {symbol}: Analysis failed - {e}")

        print(f"\n✅ Successfully analyzed {len(results)} out of {len(test_symbols)} symbols")
        return results

    except Exception as e:
        print(f"❌ Stock Analysis FAILED: {e}")
        return []

def test_value_filtering(analysis_results):
    """Test the value filtering logic"""
    print("\n" + "=" * 60)
    print("3. TESTING VALUE FILTERING LOGIC")
    print("=" * 60)

    if not analysis_results:
        print("❌ No analysis results to test")
        return []

    # Current relaxed criteria
    max_pe_ratio = 20.0
    max_pb_ratio = 4.0
    min_roe = 8.0
    max_debt_to_equity = 0.8
    min_fundamental_score = 4.0
    min_technical_score = 3.0

    print(f"📋 Filtering criteria:")
    print(f"   Max P/E: {max_pe_ratio}")
    print(f"   Max P/B: {max_pb_ratio}")
    print(f"   Min ROE: {min_roe}%")
    print(f"   Max Debt/Equity: {max_debt_to_equity}")
    print(f"   Min Fundamental Score: {min_fundamental_score}")
    print(f"   Min Technical Score: {min_technical_score}")

    passed_basic = []
    passed_all = []

    for data in analysis_results:
        symbol = data['symbol']
        pe_ratio = data['pe_ratio']
        pb_ratio = data['pb_ratio']
        roe = data['roe']
        debt_equity = data['debt_to_equity']
        result = data['result']

        print(f"\n🔍 Testing {symbol}:")
        print(f"   P/E: {pe_ratio} (max {max_pe_ratio})")
        print(f"   P/B: {pb_ratio} (max {max_pb_ratio})")
        print(f"   ROE: {roe}% (min {min_roe}%)")
        print(f"   D/E: {debt_equity} (max {max_debt_to_equity})")

        # Test basic value filtering (the hard filter in _analyze_stock_for_value)
        basic_fail_reasons = []
        if pe_ratio > 50:
            basic_fail_reasons.append(f"P/E too high: {pe_ratio} > 50")
        if pb_ratio > 10:
            basic_fail_reasons.append(f"P/B too high: {pb_ratio} > 10")
        if debt_equity > 2.0:
            basic_fail_reasons.append(f"D/E too high: {debt_equity} > 2.0")

        if basic_fail_reasons:
            print(f"   ❌ BASIC FILTER FAIL: {', '.join(basic_fail_reasons)}")
            continue
        else:
            print(f"   ✅ PASSED BASIC FILTER")
            passed_basic.append(symbol)

        # Test detailed filtering
        fail_reasons = []

        if pe_ratio > max_pe_ratio:
            fail_reasons.append(f"P/E: {pe_ratio} > {max_pe_ratio}")
        if pb_ratio > max_pb_ratio:
            fail_reasons.append(f"P/B: {pb_ratio} > {max_pb_ratio}")
        if roe < min_roe:
            fail_reasons.append(f"ROE: {roe}% < {min_roe}%")
        if debt_equity > max_debt_to_equity:
            fail_reasons.append(f"D/E: {debt_equity} > {max_debt_to_equity}")

        # Get scores
        fundamental = result.get('fundamental_analysis', {})
        fundamental_score = fundamental.get('overall_score', 0)

        technical = result.get('technical_analysis', {})
        technical_score = technical.get('technical_score', {}).get('total_score', 0)

        print(f"   Fundamental Score: {fundamental_score} (min {min_fundamental_score})")
        print(f"   Technical Score: {technical_score} (min {min_technical_score})")

        if fundamental_score < min_fundamental_score:
            fail_reasons.append(f"Fund Score: {fundamental_score} < {min_fundamental_score}")
        if technical_score < min_technical_score:
            fail_reasons.append(f"Tech Score: {technical_score} < {min_technical_score}")

        if fail_reasons:
            print(f"   ❌ DETAILED FILTER FAIL: {', '.join(fail_reasons)}")
        else:
            print(f"   ✅ PASSED ALL FILTERS")
            passed_all.append(symbol)

    print(f"\n📊 FILTERING RESULTS:")
    print(f"   Symbols tested: {len(analysis_results)}")
    print(f"   Passed basic filter: {len(passed_basic)} ({passed_basic})")
    print(f"   Passed all filters: {len(passed_all)} ({passed_all})")

    return passed_all

def test_full_value_screener():
    """Test the complete value screener"""
    print("\n" + "=" * 60)
    print("4. TESTING COMPLETE VALUE SCREENER")
    print("=" * 60)

    try:
        from main import StockAnalyzer
        from screeners.value_screener import ValueStockScreener

        analyzer = StockAnalyzer()
        screener = ValueStockScreener(analyzer)

        # Use relaxed criteria
        print("🔍 Running complete value screener with relaxed criteria...")

        results = screener.screen_value_opportunities(
            max_pe_ratio=20.0,
            max_pb_ratio=4.0,
            min_roe=8.0,
            max_debt_to_equity=0.8,
            min_fundamental_score=4.0,
            min_technical_score=3.0,
            max_stocks=25,
            screen_type='value',
            time_horizon='long'
        )

        print(f"✅ Value screener returned {len(results)} opportunities")

        if results:
            print("\n📊 Top opportunities:")
            for i, opp in enumerate(results[:5], 1):
                print(f"{i}. {opp['symbol']}: Value Score={opp['value_score']:.1f}, P/E={opp['pe_ratio']:.1f}, P/B={opp['pb_ratio']:.1f}")
        else:
            print("❌ No opportunities found")

        return results

    except Exception as e:
        print(f"❌ Complete Value Screener FAILED: {e}")
        import traceback
        traceback.print_exc()
        return []

def main():
    """Run all debug tests"""
    print("🔧 DEBUGGING VALUE SCREENER - STEP BY STEP")
    print("Current time:", datetime.now().isoformat())

    # Step 1: Test AI universe generation
    symbols = test_ai_universe_generation()

    # Step 2: Test individual stock analysis
    analysis_results = test_stock_analysis(symbols)

    # Step 3: Test filtering logic
    passed_symbols = test_value_filtering(analysis_results)

    # Step 4: Test complete screener
    final_results = test_full_value_screener()

    # Summary
    print("\n" + "=" * 60)
    print("🎯 DEBUGGING SUMMARY")
    print("=" * 60)
    print(f"AI Universe Generated: {len(symbols)} symbols")
    print(f"Successfully Analyzed: {len(analysis_results)} symbols")
    print(f"Passed All Filters: {len(passed_symbols)} symbols")
    print(f"Final Screener Results: {len(final_results)} opportunities")

    if len(final_results) == 0:
        print("\n🚨 ROOT CAUSE ANALYSIS:")
        if len(symbols) == 0:
            print("   ❌ ISSUE: AI Universe Generator is not returning any symbols")
            print("   🔧 FIX: Check DeepSeek API connection and response parsing")
        elif len(analysis_results) == 0:
            print("   ❌ ISSUE: Stock analysis is failing for all symbols")
            print("   🔧 FIX: Check data availability and API connections")
        elif len(passed_symbols) == 0:
            print("   ❌ ISSUE: All stocks are being filtered out")
            print("   🔧 FIX: Relax filtering criteria or check metric calculations")
        else:
            print("   ❌ ISSUE: Unknown problem in final screener integration")
            print("   🔧 FIX: Check screener logic and error handling")

if __name__ == "__main__":
    main()