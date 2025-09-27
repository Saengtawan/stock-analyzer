#!/usr/bin/env python3
"""
Debug TSM DCF calculation assumptions
"""
import sys
from main import StockAnalyzer

def debug_tsm_dcf_assumptions():
    """Debug TSM DCF calculation assumptions step by step"""
    print("Debugging TSM DCF calculation assumptions...")

    # Initialize analyzer
    analyzer = StockAnalyzer()

    try:
        # Get financial data
        financial_data = analyzer.data_manager.get_financial_data('TSM')
        current_price = analyzer.data_manager.get_real_time_price('TSM')['current_price']

        print("=== TSM Raw Financial Data ===")
        print(f"Symbol: TSM")
        print(f"Current Price: ${current_price:.2f}")
        print(f"Market Cap: ${financial_data.get('market_cap', 0):,.0f}")
        print(f"Shares Outstanding: {financial_data.get('shares_outstanding', 0):,.0f}")
        print(f"Enterprise Value: ${financial_data.get('enterprise_value', 0):,.0f}")

        print(f"\n=== Cash Flow Data ===")
        print(f"Free Cash Flow: ${financial_data.get('free_cash_flow', 0):,.0f}")
        print(f"Operating Cash Flow: ${financial_data.get('operating_cash_flow', 0):,.0f}")
        print(f"Capital Expenditure: ${financial_data.get('capital_expenditure', 0):,.0f}")
        print(f"Net Income: ${financial_data.get('net_income', 0):,.0f}")
        print(f"Revenue: ${financial_data.get('revenue', 0):,.0f}")

        print(f"\n=== Growth Rates ===")
        print(f"Revenue Growth: {financial_data.get('revenue_growth', 0):.2%}")
        print(f"Earnings Growth: {financial_data.get('earnings_growth', 0):.2%}")
        print(f"EPS Growth: {financial_data.get('eps_growth', 0):.2%}")

        print(f"\n=== Debt & Cash ===")
        print(f"Total Debt: ${financial_data.get('total_debt', 0):,.0f}")
        print(f"Cash & Equivalents: ${financial_data.get('cash_and_equivalents', 0):,.0f}")
        print(f"Beta: {financial_data.get('beta', 'N/A')}")

        # Initialize DCF calculator
        from analysis.fundamental.dcf_valuation import DCFValuation
        dcf_calculator = DCFValuation(financial_data)

        print(f"\n=== DCF Calculation Steps ===")

        # Step 1: Current FCF
        current_fcf = dcf_calculator._calculate_current_fcf()
        print(f"Current FCF: ${current_fcf:,.0f}")

        # Step 2: Growth rate
        growth_rate = dcf_calculator._estimate_fcf_growth_rate()
        print(f"FCF Growth Rate: {growth_rate:.2%}")

        # Step 3: WACC
        wacc = dcf_calculator._calculate_wacc(0.03, 0.06)
        print(f"WACC: {wacc:.2%}")

        # Step 4: Projected FCF
        projected_fcf = dcf_calculator._project_free_cash_flows(5)
        print(f"\nProjected FCF (5 years):")
        for i, fcf in enumerate(projected_fcf, 1):
            print(f"  Year {i}: ${fcf:,.0f}")

        # Step 5: Terminal value
        terminal_value = dcf_calculator._calculate_terminal_value(projected_fcf[-1], 0.025, wacc)
        print(f"\nTerminal Value: ${terminal_value:,.0f}")

        # Step 6: Present values
        pv_fcf = dcf_calculator._discount_cash_flows(projected_fcf, wacc)
        pv_terminal = terminal_value / ((1 + wacc) ** 5)

        print(f"\nPresent Values:")
        print(f"PV of Projected FCF: ${sum(pv_fcf):,.0f}")
        print(f"PV of Terminal Value: ${pv_terminal:,.0f}")

        # Step 7: Enterprise value
        enterprise_value = sum(pv_fcf) + pv_terminal
        print(f"Enterprise Value: ${enterprise_value:,.0f}")

        # Step 8: Equity value
        net_debt = financial_data.get('total_debt', 0) - financial_data.get('cash_and_equivalents', 0)
        equity_value = enterprise_value - net_debt
        print(f"Net Debt: ${net_debt:,.0f}")
        print(f"Equity Value: ${equity_value:,.0f}")

        # Step 9: Per-share value
        shares_outstanding = financial_data.get('shares_outstanding', 0)
        if not shares_outstanding:
            shares_outstanding = financial_data.get('market_cap', 0) / current_price

        intrinsic_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0
        print(f"\nShares Outstanding: {shares_outstanding:,.0f}")
        print(f"Intrinsic Value per Share: ${intrinsic_value_per_share:.2f}")

        # Check for unusual values
        print(f"\n=== Sanity Check ===")
        if intrinsic_value_per_share > current_price * 10:
            print("⚠️  WARNING: Intrinsic value is >10x current price - check assumptions!")

            # Check problematic assumptions
            if current_fcf > financial_data.get('revenue', 0) * 0.5:
                print("⚠️  FCF seems too high relative to revenue")

            if growth_rate > 0.3:
                print(f"⚠️  Growth rate {growth_rate:.1%} seems too optimistic")

            if terminal_value > enterprise_value * 0.9:
                print(f"⚠️  Terminal value dominates enterprise value ({terminal_value/enterprise_value:.1%})")

        return True

    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = debug_tsm_dcf_assumptions()
    sys.exit(0 if success else 1)