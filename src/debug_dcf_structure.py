#!/usr/bin/env python3
"""
Debug DCF data structure in web interface
"""
import sys
from main import StockAnalyzer

def debug_dcf_structure():
    """Debug DCF data structure"""
    print("Debugging DCF data structure...")

    # Initialize analyzer
    analyzer = StockAnalyzer()

    try:
        # Get analysis results
        results = analyzer.analyze_stock('CWAN', time_horizon='short')

        # Check fundamental analysis
        fund_analysis = results.get('fundamental_analysis', {})
        print("=== Fundamental Analysis Keys ===")
        print(list(fund_analysis.keys()))

        # Check DCF analysis location
        print("\n=== DCF Analysis Locations ===")

        # Direct dcf_analysis key
        if 'dcf_analysis' in fund_analysis:
            dcf_data = fund_analysis['dcf_analysis']
            print(f"Found dcf_analysis: {dcf_data.get('intrinsic_value_per_share', 'N/A')}")

        # dcf_valuation key
        if 'dcf_valuation' in fund_analysis:
            dcf_data = fund_analysis['dcf_valuation']
            print(f"Found dcf_valuation: {dcf_data.get('intrinsic_value_per_share', 'N/A')}")

            # Calculate upside/downside
            intrinsic_value = dcf_data.get('intrinsic_value_per_share', 0)
            current_price = results.get('current_price', 0)
            if intrinsic_value > 0 and current_price > 0:
                upside_downside = ((intrinsic_value - current_price) / current_price) * 100
                print(f"Calculated Upside/Downside: {upside_downside:.2f}%")

        # Check if we need to add dcf_analysis key
        print(f"\n=== Need to Add DCF Analysis Key ===")
        if 'dcf_valuation' in fund_analysis and 'dcf_analysis' not in fund_analysis:
            print("✅ Need to add dcf_analysis key pointing to dcf_valuation data")

        return True

    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = debug_dcf_structure()
    sys.exit(0 if success else 1)