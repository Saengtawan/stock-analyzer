#!/usr/bin/env python3
"""
Quick Debug - Test just the key components
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

def test_ai_generation():
    """Quick test of AI universe generation"""
    try:
        from ai_universe_generator import AIUniverseGenerator

        generator = AIUniverseGenerator()
        criteria = {
            'max_stocks': 10,  # Small test
            'screen_type': 'value'
        }

        symbols = generator.generate_value_universe(criteria)
        print(f"✅ AI generated {len(symbols)} symbols: {symbols[:10]}")
        return symbols

    except Exception as e:
        print(f"❌ AI generation failed: {e}")
        return []

def test_basic_analysis():
    """Test basic stock analysis on a known stock"""
    try:
        from main import StockAnalyzer

        analyzer = StockAnalyzer()

        # Test with Apple - known to have good data
        result = analyzer.analyze_stock('AAPL', include_ai_analysis=False)

        if 'error' in result:
            print(f"❌ Analysis failed: {result['error']}")
            return None

        fundamental = result.get('fundamental_analysis', {})
        ratios = fundamental.get('financial_ratios', {})

        pe = ratios.get('pe_ratio')
        pb = ratios.get('pb_ratio')
        roe = ratios.get('roe')
        de = ratios.get('debt_to_equity')

        print(f"✅ AAPL analysis: P/E={pe}, P/B={pb}, ROE={roe}, D/E={de}")

        # Check missing metrics
        if not all([pe, pb, roe, de]):
            print(f"⚠️  Missing metrics: PE={pe is not None}, PB={pb is not None}, ROE={roe is not None}, DE={de is not None}")

        return result

    except Exception as e:
        print(f"❌ Basic analysis failed: {e}")
        return None

def test_filtering():
    """Test the filtering with known values"""
    # Simulate a good value stock
    test_stock = {
        'pe_ratio': 15.0,  # Good
        'pb_ratio': 2.5,   # Good
        'roe': 12.0,       # Good
        'debt_to_equity': 0.6,  # Good
        'fundamental_score': 6.0,
        'technical_score': 5.0
    }

    # Test basic filter (in _analyze_stock_for_value)
    if test_stock['pe_ratio'] > 50 or test_stock['pb_ratio'] > 10 or test_stock['debt_to_equity'] > 2.0:
        print("❌ Failed basic filter")
        return False
    else:
        print("✅ Passed basic filter")

    # Test detailed filter
    max_pe = 20.0
    max_pb = 4.0
    min_roe = 8.0
    max_de = 0.8
    min_fund = 4.0
    min_tech = 3.0

    fails = []
    if test_stock['pe_ratio'] > max_pe:
        fails.append(f"P/E {test_stock['pe_ratio']} > {max_pe}")
    if test_stock['pb_ratio'] > max_pb:
        fails.append(f"P/B {test_stock['pb_ratio']} > {max_pb}")
    if test_stock['roe'] < min_roe:
        fails.append(f"ROE {test_stock['roe']} < {min_roe}")
    if test_stock['debt_to_equity'] > max_de:
        fails.append(f"D/E {test_stock['debt_to_equity']} > {max_de}")
    if test_stock['fundamental_score'] < min_fund:
        fails.append(f"Fund {test_stock['fundamental_score']} < {min_fund}")
    if test_stock['technical_score'] < min_tech:
        fails.append(f"Tech {test_stock['technical_score']} < {min_tech}")

    if fails:
        print(f"❌ Failed detailed filter: {fails}")
        return False
    else:
        print("✅ Passed detailed filter")
        return True

def main():
    print("🔧 QUICK DEBUG TEST")
    print("=" * 40)

    # Test 1: AI Generation
    print("\n1. Testing AI generation...")
    symbols = test_ai_generation()

    # Test 2: Basic Analysis
    print("\n2. Testing basic analysis...")
    result = test_basic_analysis()

    # Test 3: Filtering Logic
    print("\n3. Testing filtering logic...")
    filter_ok = test_filtering()

    # Summary
    print("\n📊 SUMMARY:")
    print(f"AI Generation: {'✅' if symbols else '❌'}")
    print(f"Basic Analysis: {'✅' if result else '❌'}")
    print(f"Filter Logic: {'✅' if filter_ok else '❌'}")

    if not symbols:
        print("\n🚨 LIKELY ISSUE: AI universe generation is failing")
    elif not result:
        print("\n🚨 LIKELY ISSUE: Stock analysis is failing")
    else:
        print("\n✅ Core components working - issue may be in integration or criteria")

if __name__ == "__main__":
    main()