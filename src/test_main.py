#!/usr/bin/env python3
"""
Direct test for the main StockAnalyzer class
"""
import sys
import os

def test_data_manager():
    """Test data manager functionality"""
    print("\n=== Testing Data Manager ===")
    try:
        from api.data_manager import DataManager
        dm = DataManager()
        print("✓ DataManager imported and initialized")

        # Test basic data fetching
        data = dm.get_price_data('AAPL', period='5d')
        if data is not None and not data.empty:
            print(f"✓ Price data retrieved: {len(data)} rows")
            print(f"  Latest close: ${data['Close'].iloc[-1]:.2f}")
        else:
            print("⚠ Data retrieved but empty")
        return True
    except Exception as e:
        print(f"✗ Data manager test failed: {e}")
        return False

def test_analyzers():
    """Test analyzer components"""
    print("\n=== Testing Analyzers ===")
    try:
        from analysis.fundamental.fundamental_analyzer import FundamentalAnalyzer
        from analysis.technical.technical_analyzer import TechnicalAnalyzer

        fa = FundamentalAnalyzer()
        ta = TechnicalAnalyzer()
        print("✓ Fundamental and Technical analyzers initialized")
        return True
    except Exception as e:
        print(f"✗ Analyzer test failed: {e}")
        return False

def test_signal_generator():
    """Test signal generation"""
    print("\n=== Testing Signal Generator ===")
    try:
        from signals.signal_generator import SignalGenerator
        from signals.scoring_system import AdvancedScoringSystem

        sg = SignalGenerator()
        ss = AdvancedScoringSystem()
        print("✓ Signal generator and scoring system initialized")
        return True
    except Exception as e:
        print(f"✗ Signal generator test failed: {e}")
        return False

def test_risk_manager():
    """Test risk management"""
    print("\n=== Testing Risk Manager ===")
    try:
        from risk.risk_manager import AdvancedRiskManager

        rm = AdvancedRiskManager()
        print("✓ Risk manager initialized")
        return True
    except Exception as e:
        print(f"✗ Risk manager test failed: {e}")
        return False

def test_backtest_engine():
    """Test backtesting engine"""
    print("\n=== Testing Backtest Engine ===")
    try:
        from backtesting.backtest_engine import BacktestEngine

        be = BacktestEngine()
        print("✓ Backtest engine initialized")
        return True
    except Exception as e:
        print(f"✗ Backtest engine test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=== Stock Analyzer Component Tests ===")

    # Test individual components
    tests = [
        test_data_manager,
        test_analyzers,
        test_signal_generator,
        test_risk_manager,
        test_backtest_engine
    ]

    passed = 0
    total = len(tests)

    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"✗ Test {test_func.__name__} crashed: {e}")

    print(f"\n=== Test Summary ===")
    print(f"Passed: {passed}/{total} tests")

    if passed == total:
        print("✓ All component tests passed!")

        # Try to test main StockAnalyzer
        print("\n=== Testing Main StockAnalyzer ===")
        try:
            from main import StockAnalyzer
            analyzer = StockAnalyzer()
            print("✓ StockAnalyzer initialized successfully")

            # Try a quick analysis
            print("Testing quick analysis...")
            results = analyzer.analyze_stock('AAPL', time_horizon='medium', account_value=100000)
            if results:
                print("✓ Analysis completed successfully")
                print(f"  Symbol: {results.get('symbol', 'N/A')}")
                print(f"  Recommendation: {results.get('final_recommendation', {}).get('recommendation', 'N/A')}")
            else:
                print("⚠ Analysis returned empty results")

        except Exception as e:
            print(f"✗ Main analyzer test failed: {e}")
    else:
        print("⚠ Some component tests failed")

if __name__ == "__main__":
    main()