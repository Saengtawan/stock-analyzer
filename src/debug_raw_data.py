#!/usr/bin/env python3
"""
Debug Raw Financial Data - Check what's coming from data sources
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

def test_raw_financial_data():
    """Check raw financial data from different sources"""
    try:
        from api.data_manager import DataManager

        data_manager = DataManager()

        # Test with a known stock
        symbol = 'AAPL'
        print(f"🔍 Testing raw financial data for {symbol}")

        # Get financial data from primary source
        financial_data = data_manager.get_financial_data(symbol)

        if not financial_data or 'error' in financial_data:
            print(f"❌ Failed to get financial data: {financial_data}")
            return

        print(f"\n📊 Raw Financial Data for {symbol}:")
        print("=" * 50)

        # Check key metrics
        key_metrics = ['roe', 'pe_ratio', 'pb_ratio', 'debt_to_equity', 'profit_margin', 'revenue_growth']

        for metric in key_metrics:
            value = financial_data.get(metric)
            print(f"{metric:15}: {value} (type: {type(value).__name__})")

        # Check if there are nested structures
        print(f"\n📋 All available keys:")
        for key in sorted(financial_data.keys()):
            if key not in ['error']:
                value = financial_data[key]
                if isinstance(value, dict):
                    print(f"{key:20}: <dict with {len(value)} keys>")
                else:
                    print(f"{key:20}: {value}")

        return financial_data

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_processed_data():
    """Test how the data gets processed in fundamental analyzer"""
    try:
        from main import StockAnalyzer

        analyzer = StockAnalyzer()
        symbol = 'AAPL'

        print(f"\n🔍 Testing processed data for {symbol}")

        # Get just the fundamental analysis
        result = analyzer.analyze_stock(symbol, include_ai_analysis=False)

        if 'error' in result:
            print(f"❌ Analysis failed: {result['error']}")
            return

        fundamental = result.get('fundamental_analysis', {})
        ratios = fundamental.get('financial_ratios', {})

        print(f"\n📊 Processed Financial Ratios for {symbol}:")
        print("=" * 50)

        key_ratios = ['roe', 'pe_ratio', 'pb_ratio', 'debt_to_equity', 'profit_margin', 'revenue_growth']

        for ratio in key_ratios:
            value = ratios.get(ratio)
            print(f"{ratio:15}: {value}")

        # Check intermediate calculation data
        raw_data = fundamental.get('raw_data', {})
        if raw_data:
            print(f"\n📋 Raw Data (before processing):")
            for key in key_ratios:
                if key in raw_data:
                    value = raw_data[key]
                    print(f"{key:15}: {value}")

        return ratios

    except Exception as e:
        print(f"❌ Processed data test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("🔧 DEBUGGING RAW VS PROCESSED FINANCIAL DATA")
    print("=" * 60)

    # Test 1: Raw data from data manager
    raw_data = test_raw_financial_data()

    # Test 2: Processed data from analyzer
    processed_data = test_processed_data()

    # Compare
    if raw_data and processed_data:
        print(f"\n🔍 COMPARISON:")
        print("=" * 30)

        key_metrics = ['roe', 'pe_ratio', 'pb_ratio']
        for metric in key_metrics:
            raw_val = raw_data.get(metric)
            proc_val = processed_data.get(metric)
            print(f"{metric:12}: Raw={raw_val} -> Processed={proc_val}")

            # Check if normalization is causing issues
            if raw_val is not None and proc_val is not None:
                try:
                    raw_float = float(raw_val)
                    proc_float = float(proc_val)
                    if abs(raw_float) > 1 and abs(proc_float) < 1:
                        print(f"             -> LIKELY NORMALIZED: {raw_float} / 100 = {proc_float}")
                except:
                    pass

if __name__ == "__main__":
    main()