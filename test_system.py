#!/usr/bin/env python3
"""
System test script for Stock Analyzer
"""
import sys
import os
sys.path.append('src')

def main():
    print('=== Stock Analyzer System Test ===\n')

    # Test 1: Import test
    print('1. Testing imports...')
    try:
        from main import StockAnalyzer
        print('✓ Main module imported successfully')
    except Exception as e:
        print(f'✗ Import failed: {e}')
        return False

    # Test 2: Initialization test
    print('\n2. Testing StockAnalyzer initialization...')
    try:
        analyzer = StockAnalyzer()
        print('✓ StockAnalyzer initialized successfully')
    except Exception as e:
        print(f'✗ Initialization failed: {e}')
        return False

    # Test 3: Data manager test
    print('\n3. Testing data manager...')
    try:
        data = analyzer.data_manager.get_price_data('AAPL', period='5d')
        if data is not None and not data.empty:
            print(f'✓ Price data retrieved successfully ({len(data)} rows)')
            print(f'  Latest price: ${data["Close"].iloc[-1]:.2f}')
        else:
            print('⚠ Price data retrieved but empty or None')
    except Exception as e:
        print(f'✗ Data retrieval failed: {e}')

    # Test 4: Basic analysis test
    print('\n4. Testing basic stock analysis...')
    try:
        results = analyzer.analyze_stock('AAPL', time_horizon='medium', account_value=100000)
        if results:
            rec = results.get('final_recommendation', {}).get('recommendation', 'N/A')
            score = results.get('signal_analysis', {}).get('final_score', {}).get('total_score', 0)
            print(f'✓ Analysis completed successfully')
            print(f'  Symbol: {results.get("symbol", "N/A")}')
            print(f'  Recommendation: {rec}')
            print(f'  Score: {score:.1f}/10')
        else:
            print('⚠ Analysis completed but returned empty results')
    except Exception as e:
        print(f'✗ Analysis failed: {e}')

    print('\n=== Test Summary ===')
    print('System testing completed. Check results above.')
    return True

if __name__ == '__main__':
    main()