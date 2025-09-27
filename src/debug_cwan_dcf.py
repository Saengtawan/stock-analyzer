#!/usr/bin/env python3
"""
Debug CWAN DCF calculation
"""
import sys
from main import StockAnalyzer

def debug_cwan_dcf():
    """Debug CWAN DCF calculation step by step"""
    print("Debugging CWAN DCF calculation...")

    # Initialize analyzer
    analyzer = StockAnalyzer()

    try:
        # Get financial data
        financial_data = analyzer.data_manager.get_financial_data('CWAN')
        current_price = analyzer.data_manager.get_real_time_price('CWAN')['current_price']

        print("Raw Financial Data for CWAN:")
        for key, value in financial_data.items():
            if isinstance(value, (int, float)):
                print(f"{key}: {value}")

        print(f"\nCurrent Price: ${current_price:.2f}")

        # Initialize fundamental analyzer
        from analysis.fundamental.fundamental_analyzer import FundamentalAnalyzer
        fund_analyzer = FundamentalAnalyzer(financial_data, current_price)

        # Test DCF calculation directly
        from analysis.fundamental.dcf_valuation import DCFValuation
        dcf_calculator = DCFValuation(financial_data)

        print("\nDCF Calculation Steps:")

        # Test current FCF calculation
        current_fcf = dcf_calculator._calculate_current_fcf()
        print(f"Current FCF: ${current_fcf:,.2f}")

        # Test growth rate
        growth_rate = dcf_calculator._estimate_fcf_growth_rate()
        print(f"FCF Growth Rate: {growth_rate:.2%}")

        # Test WACC calculation
        wacc = dcf_calculator._calculate_wacc(0.03, 0.06)
        print(f"WACC: {wacc:.2%}")

        # Test full DCF calculation
        dcf_results = dcf_calculator.calculate_dcf_value()
        print(f"\nDCF Results:")
        print(f"Intrinsic Value per Share: ${dcf_results.get('intrinsic_value_per_share', 0):.2f}")
        print(f"Enterprise Value: ${dcf_results.get('enterprise_value', 0):,.2f}")
        print(f"Equity Value: ${dcf_results.get('equity_value', 0):,.2f}")
        print(f"Shares Outstanding: {dcf_results.get('shares_outstanding', 0):,.0f}")

        if 'error' in dcf_results:
            print(f"DCF Error: {dcf_results['error']}")

        # Compare with current price
        intrinsic_value = dcf_results.get('intrinsic_value_per_share', 0)
        if intrinsic_value > 0:
            upside_downside = ((intrinsic_value - current_price) / current_price) * 100
            print(f"\nPrice vs Intrinsic Value:")
            print(f"Current Price: ${current_price:.2f}")
            print(f"Intrinsic Value: ${intrinsic_value:.2f}")
            print(f"Upside/Downside: {upside_downside:.2f}%")

        return True

    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = debug_cwan_dcf()
    sys.exit(0 if success else 1)