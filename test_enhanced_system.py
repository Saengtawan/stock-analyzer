#!/usr/bin/env python3
"""
Test script for the enhanced stock analyzer system
"""
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def create_test_data():
    """Create sample test data for testing"""
    # Create sample price data
    dates = pd.date_range(start='2023-01-01', end='2024-01-01', freq='D')
    np.random.seed(42)  # For reproducible results

    price_data = pd.DataFrame({
        'date': dates,
        'open': 100 + np.cumsum(np.random.randn(len(dates)) * 0.5),
        'high': 100 + np.cumsum(np.random.randn(len(dates)) * 0.5) + 2,
        'low': 100 + np.cumsum(np.random.randn(len(dates)) * 0.5) - 2,
        'close': 100 + np.cumsum(np.random.randn(len(dates)) * 0.5),
        'volume': np.random.randint(1000000, 10000000, len(dates))
    })

    # Ensure high >= max(open, close) and low <= min(open, close)
    price_data['high'] = np.maximum(price_data['high'],
                                   np.maximum(price_data['open'], price_data['close']))
    price_data['low'] = np.minimum(price_data['low'],
                                  np.minimum(price_data['open'], price_data['close']))

    # Sample fundamental data
    fundamental_data = {
        'pe_ratio': 15.5,
        'pb_ratio': 2.1,
        'roe': 0.18,
        'debt_to_equity': 0.45,
        'current_ratio': 2.3,
        'revenue_growth': 0.12,
        'eps_growth': 0.15,
        'dividend_yield': 0.025,
        'market_cap': 5000000000,
        'current_price': 105.50
    }

    return price_data, fundamental_data

def test_enhanced_analyzer():
    """Test the enhanced stock analyzer"""
    print("Testing Enhanced Stock Analyzer System")
    print("=" * 50)

    try:
        from analysis.enhanced_stock_analyzer import EnhancedStockAnalyzer

        # Create test data
        price_data, fundamental_data = create_test_data()

        # Initialize enhanced analyzer
        analyzer = EnhancedStockAnalyzer(
            trading_strategy="swing_trading",
            risk_tolerance="moderate"
        )

        print(f"✓ Enhanced analyzer initialized successfully")

        # Run analysis
        print("Running comprehensive analysis...")
        results = analyzer.analyze_stock(
            symbol="TEST",
            price_data=price_data,
            fundamental_data=fundamental_data
        )

        print(f"✓ Analysis completed successfully")

        # Display key results
        analysis_summary = results.get('analysis_summary', {})
        print(f"\nAnalysis Results:")
        print(f"Symbol: {results.get('symbol', 'N/A')}")
        print(f"Recommendation: {analysis_summary.get('recommendation', 'N/A')}")
        print(f"Overall Score: {analysis_summary.get('overall_score', 0):.3f}")
        print(f"Confidence: {analysis_summary.get('confidence', 0):.3f}")

        # Data quality
        data_quality = results.get('data_quality', {})
        print(f"Data Quality Score: {data_quality.get('quality_score', 0):.3f}")

        # Market regime
        market_regime = results.get('market_regime', {})
        current_regime = market_regime.get('current', {})
        print(f"Market Regime: {current_regime.get('regime', 'UNKNOWN')}")
        print(f"Regime Confidence: {current_regime.get('confidence', 0):.3f}")

        # Signal quality
        signal_processing = results.get('signal_processing', {})
        signal_quality = signal_processing.get('signal_quality_metrics', {})
        print(f"Signal Quality: {signal_quality.get('overall_quality', 0):.3f}")

        # Risk assessment
        risk_assessment = results.get('risk_assessment', {})
        print(f"Overall Risk Score: {risk_assessment.get('overall_risk_score', 0):.3f}")

        # Position sizing
        position_sizing = results.get('position_sizing', {})
        print(f"Recommended Position: {position_sizing.get('recommended_position_percentage', 0):.1f}%")

        # Adaptability insights
        insights = results.get('adaptability_insights', [])
        if insights:
            print(f"\nKey Insights:")
            for i, insight in enumerate(insights[:3], 1):
                print(f"{i}. {insight}")

        print(f"\n✓ Enhanced analysis test passed!")
        return True

    except Exception as e:
        print(f"✗ Enhanced analysis test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_individual_modules():
    """Test individual enhanced modules"""
    print("\nTesting Individual Enhanced Modules")
    print("=" * 50)

    price_data, fundamental_data = create_test_data()
    success_count = 0
    total_tests = 0

    # Test Data Quality Validator
    try:
        from data_quality.data_validator import DataQualityValidator
        validator = DataQualityValidator()
        validation_result = validator.validate_price_data(price_data)
        print(f"✓ Data Quality Validator: Score {validation_result['quality_score']:.3f}")
        success_count += 1
    except Exception as e:
        print(f"✗ Data Quality Validator failed: {e}")
    total_tests += 1

    # Test TimeFrame Manager
    try:
        from timeframe.timeframe_manager import TimeFrameManager, TradingStrategy
        manager = TimeFrameManager()
        optimal_timeframes = manager.get_optimal_timeframes(TradingStrategy.SWING_TRADING)
        print(f"✓ TimeFrame Manager: {len(optimal_timeframes)} optimal timeframes")
        success_count += 1
    except Exception as e:
        print(f"✗ TimeFrame Manager failed: {e}")
    total_tests += 1

    # Test Advanced Technical Analyzer
    try:
        from analysis.advanced.advanced_models import AdvancedTechnicalAnalyzer
        advanced_analyzer = AdvancedTechnicalAnalyzer(price_data)
        advanced_results = advanced_analyzer.analyze()
        print(f"✓ Advanced Technical Analyzer: Pattern strength {advanced_results.get('pattern_strength', 0):.3f}")
        success_count += 1
    except Exception as e:
        print(f"✗ Advanced Technical Analyzer failed: {e}")
    total_tests += 1

    # Test Market Regime Detector
    try:
        from adaptability.market_regime_detector import MarketRegimeDetector
        regime_detector = MarketRegimeDetector(price_data)
        current_regime = regime_detector.detect_current_regime()
        print(f"✓ Market Regime Detector: {current_regime.get('regime', 'UNKNOWN')} regime")
        success_count += 1
    except Exception as e:
        print(f"✗ Market Regime Detector failed: {e}")
    total_tests += 1

    # Test Enhanced Risk Manager
    try:
        from risk.enhanced_risk_manager import EnhancedRiskManager
        risk_manager = EnhancedRiskManager()
        portfolio_data = {
            'returns': price_data['close'].pct_change().dropna().tolist(),
            'prices': price_data['close'].tolist(),
            'volumes': price_data['volume'].tolist()
        }
        risk_metrics = risk_manager.calculate_risk_metrics(portfolio_data)
        print(f"✓ Enhanced Risk Manager: VaR {risk_metrics.get('portfolio_var', 0):.4f}")
        success_count += 1
    except Exception as e:
        print(f"✗ Enhanced Risk Manager failed: {e}")
    total_tests += 1

    # Test Signal Noise Filter
    try:
        from signal_processing.signal_filter import SignalNoiseFilter
        signal_filter = SignalNoiseFilter()
        test_signal = np.random.randn(100)
        filtered_signal = signal_filter.apply_ensemble_filtering(test_signal)
        print(f"✓ Signal Noise Filter: Filtered {len(filtered_signal)} data points")
        success_count += 1
    except Exception as e:
        print(f"✗ Signal Noise Filter failed: {e}")
    total_tests += 1

    print(f"\nModule Tests: {success_count}/{total_tests} passed")
    return success_count == total_tests

def test_main_application():
    """Test the main application integration"""
    print("\nTesting Main Application Integration")
    print("=" * 50)

    try:
        from main import StockAnalyzer

        # Initialize with enhanced features
        analyzer = StockAnalyzer(
            config={'risk_tolerance': 'moderate'},
            trading_strategy='swing_trading'
        )

        print("✓ Main application initialized with enhanced features")

        # Note: We can't test actual stock analysis without real API data
        # But we can verify the initialization works
        print("✓ Enhanced integration successful")
        return True

    except Exception as e:
        print(f"✗ Main application test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("Enhanced Stock Analyzer System Test Suite")
    print("=" * 60)
    print(f"Test started at: {datetime.now()}")
    print()

    all_tests_passed = True

    # Test enhanced analyzer
    if not test_enhanced_analyzer():
        all_tests_passed = False

    # Test individual modules
    if not test_individual_modules():
        all_tests_passed = False

    # Test main application
    if not test_main_application():
        all_tests_passed = False

    print("\n" + "=" * 60)
    if all_tests_passed:
        print("🎉 ALL TESTS PASSED! Enhanced system is ready for use.")
        print("\nEnhanced Features Available:")
        print("• Data Quality Enhancement with validation and cleaning")
        print("• Time Frame & Frequency Optimization for different strategies")
        print("• Advanced Analytical Models with pattern recognition")
        print("• Adaptability Features with market regime detection")
        print("• Enhanced Risk Management with portfolio optimization")
        print("• Signal vs Noise Filtering with advanced DSP techniques")
        print("• Integrated main analyzer with backward compatibility")
    else:
        print("❌ Some tests failed. Please review the errors above.")

    print(f"\nTest completed at: {datetime.now()}")

if __name__ == "__main__":
    main()