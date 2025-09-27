#!/usr/bin/env python3
"""
Test script to verify TTD analysis improvements
"""
import sys
from main import StockAnalyzer

def test_ttd_analysis():
    """Test the updated analysis logic with TTD"""
    print("Testing TTD analysis with improved scoring...")

    # Initialize analyzer
    analyzer = StockAnalyzer()

    # Analyze TTD
    symbol = 'TTD'

    print(f"Analyzing {symbol}...")
    try:
        results = analyzer.analyze_stock(symbol)

        if 'error' in results:
            print(f"❌ Analysis failed: {results['error']}")
            return False

        # Extract key metrics
        fundamental = results.get('fundamental_analysis', {})
        technical = results.get('technical_analysis', {})
        signal_analysis = results.get('signal_analysis', {})

        print(f"\n📊 Fundamental Analysis:")
        fund_score = fundamental.get('fundamental_score', {})
        print(f"Overall Score: {fund_score.get('total_score', 0):.2f}/10")
        print(f"Rating: {fund_score.get('rating', 'N/A')}")

        component_scores = fund_score.get('component_scores', {})
        print(f"  - Valuation: {component_scores.get('valuation', 0):.2f}/2")
        print(f"  - Profitability: {component_scores.get('profitability', 0):.2f}/2")
        print(f"  - Financial Health: {component_scores.get('financial_health', 0):.2f}/2")
        print(f"  - Growth: {component_scores.get('growth', 0):.2f}/2")

        # DCF Analysis
        dcf = fundamental.get('dcf_valuation', {})
        ratios = fundamental.get('financial_ratios', {})
        current_price = ratios.get('current_price', 0)
        intrinsic_value = dcf.get('intrinsic_value_per_share', 0)

        if current_price and intrinsic_value:
            upside = ((intrinsic_value - current_price) / current_price) * 100
            print(f"\n💰 DCF Analysis:")
            print(f"Current Price: ${current_price:.2f}")
            print(f"Intrinsic Value: ${intrinsic_value:.2f}")
            print(f"Upside/Downside: {upside:.2f}%")

        print(f"\n📈 Technical Analysis:")
        tech_score = technical.get('score', {})
        print(f"Score: {tech_score.get('total_score', 0):.2f}/10")

        print(f"\n🎯 Final Recommendation:")
        final_score = signal_analysis.get('final_score', {})
        recommendation = signal_analysis.get('recommendation', {})
        print(f"Overall Score: {final_score.get('total_score', 0):.2f}/10")
        print(f"Recommendation: {recommendation.get('action', 'N/A')}")
        print(f"Confidence: {recommendation.get('confidence', 'N/A')}")

        print("\n✅ Analysis completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_ttd_analysis()
    sys.exit(0 if success else 1)