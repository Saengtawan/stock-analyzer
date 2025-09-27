#!/usr/bin/env python3
"""
Test TTD analysis with different time horizons
"""
import sys
from main import StockAnalyzer

def test_ttd_timeframes():
    """Test TTD with medium vs long-term analysis"""
    print("Testing TTD with different time horizons...")

    analyzer = StockAnalyzer()

    timeframes = [
        ('short', 'ระยะสั้น (1-4 สัปดาห์)'),
        ('medium', 'ระยะกลาง (1-6 เดือน)'),
        ('long', 'ระยะยาว (6+ เดือน)')
    ]

    for timeframe, description in timeframes:
        print(f"\n{'='*50}")
        print(f"Testing {description}")
        print(f"Time Horizon: {timeframe}")
        print('='*50)

        try:
            # Set time horizon in analyzer
            analyzer.config['time_horizon'] = timeframe

            results = analyzer.analyze_stock('TTD', time_horizon=timeframe)

            if 'error' in results:
                print(f"❌ Analysis failed: {results['error']}")
                continue

            # Extract key metrics
            signal_analysis = results.get('signal_analysis', {})
            final_score = signal_analysis.get('final_score', {})
            recommendation = signal_analysis.get('recommendation', {})

            print(f"📊 Results:")
            print(f"Overall Score: {final_score.get('total_score', 0):.2f}/10")
            print(f"Recommendation: {recommendation.get('recommendation', 'N/A')}")
            print(f"Confidence: {recommendation.get('confidence', 'N/A')}")

            # Show weight breakdown
            fund_contribution = final_score.get('fundamental_contribution', 0)
            tech_contribution = final_score.get('technical_contribution', 0)

            print(f"\n📈 Score Breakdown:")
            print(f"Fundamental Contribution: {fund_contribution:.2f}")
            print(f"Technical Contribution: {tech_contribution:.2f}")

            # Show fundamental details
            fundamental = results.get('fundamental_analysis', {})
            fund_score = fundamental.get('fundamental_score', {})
            component_scores = fund_score.get('component_scores', {})

            print(f"\n💰 Fundamental Scores:")
            print(f"Valuation: {component_scores.get('valuation', 0):.2f}/2")
            print(f"Total Fundamental: {fund_score.get('total_score', 0):.2f}/10")

        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()

    return True

if __name__ == "__main__":
    success = test_ttd_timeframes()
    sys.exit(0 if success else 1)