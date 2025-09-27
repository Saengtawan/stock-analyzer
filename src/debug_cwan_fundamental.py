#!/usr/bin/env python3
"""
Debug CWAN fundamental analysis data flow
"""
import sys
from main import StockAnalyzer

def debug_cwan_fundamental():
    """Debug CWAN fundamental analysis data flow"""
    print("Debugging CWAN fundamental analysis data flow...")

    # Initialize analyzer
    analyzer = StockAnalyzer()

    try:
        # Get full analysis results
        results = analyzer.analyze_stock('CWAN', time_horizon='short')

        print("=== Main Analysis Results ===")
        print(f"Overall Score: {results.get('signal_analysis', {}).get('final_score', {}).get('total_score', 0):.1f}/10")
        print(f"Current Price: ${results.get('current_price', 0):.2f}")

        # Check fundamental analysis section
        fund_analysis = results.get('fundamental_analysis', {})
        print(f"\n=== Fundamental Analysis Section ===")
        print(f"Overall Score: {fund_analysis.get('overall_score', 'N/A')}")
        print(f"Has Error: {'error' in fund_analysis}")
        if 'error' in fund_analysis:
            print(f"Error: {fund_analysis['error']}")

        # Check DCF section specifically
        dcf_analysis = fund_analysis.get('dcf_analysis', {}) if 'dcf_analysis' in fund_analysis else fund_analysis.get('dcf_valuation', {})
        print(f"\n=== DCF Analysis Section ===")
        print(f"DCF Keys: {list(dcf_analysis.keys())}")
        if dcf_analysis:
            print(f"Intrinsic Value: {dcf_analysis.get('intrinsic_value_per_share', 'N/A')}")
            print(f"Enterprise Value: {dcf_analysis.get('enterprise_value', 'N/A')}")
            print(f"Has Error: {'error' in dcf_analysis}")

        # Check enhanced analysis section
        enhanced_analysis = results.get('enhanced_analysis', {})
        enhanced_fund = enhanced_analysis.get('fundamental_analysis', {})
        print(f"\n=== Enhanced Analysis - Fundamental Section ===")
        print(f"Enhanced Fund Keys: {list(enhanced_fund.keys())}")
        print(f"Enhanced Overall Score: {enhanced_fund.get('overall_score', 'N/A')}")

        enhanced_dcf = enhanced_fund.get('dcf_analysis', {}) if 'dcf_analysis' in enhanced_fund else enhanced_fund.get('dcf_valuation', {})
        print(f"Enhanced DCF Keys: {list(enhanced_dcf.keys())}")
        if enhanced_dcf:
            print(f"Enhanced DCF Intrinsic Value: {enhanced_dcf.get('intrinsic_value_per_share', 'N/A')}")

        return True

    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = debug_cwan_fundamental()
    sys.exit(0 if success else 1)