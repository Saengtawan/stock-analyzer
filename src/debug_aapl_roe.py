#!/usr/bin/env python3
"""
Debug AAPL ROE calculation
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

def debug_aapl_roe():
    """Debug AAPL ROE calculation step by step"""
    try:
        from api.data_manager import DataManager

        data_manager = DataManager()
        financial_data = data_manager.get_financial_data('AAPL')

        if not financial_data or 'error' in financial_data:
            print(f"❌ Failed to get financial data")
            return

        print("📊 AAPL Financial Data for ROE calculation:")
        print("=" * 50)

        net_income = financial_data.get('net_income')
        shareholders_equity = financial_data.get('shareholders_equity')
        return_on_equity_raw = financial_data.get('return_on_equity')

        print(f"Net Income: {net_income:,}")
        print(f"Shareholders Equity: {shareholders_equity:,}")
        print(f"Return on Equity (raw): {return_on_equity_raw}")

        if net_income and shareholders_equity and shareholders_equity > 0:
            calculated_roe = net_income / shareholders_equity
            print(f"\nDirect calculation: {net_income:,} / {shareholders_equity:,} = {calculated_roe:.6f}")
            print(f"As percentage: {calculated_roe * 100:.2f}%")

            # Check if calculation makes sense
            if calculated_roe > 1.0:
                print(f"⚠️  ROE > 100% suggests calculation issue")

                # Maybe net_income is already in different units?
                roe_millions = (net_income / 1_000_000) / (shareholders_equity / 1_000_000)
                print(f"Same units check: {roe_millions:.6f} ({roe_millions*100:.2f}%)")

                # Check if shareholders_equity is too small
                if shareholders_equity < net_income:
                    print(f"⚠️  Shareholders equity ({shareholders_equity:,}) < Net income ({net_income:,})")
                    print("This suggests potential data inconsistency")

        # Compare with raw return_on_equity
        if return_on_equity_raw:
            print(f"\nFallback value: {return_on_equity_raw} ({return_on_equity_raw}%)")

            # Apple's actual ROE should be around 15-25%
            print(f"\nExpected ROE for AAPL: ~15-25%")
            print(f"Raw value seems reasonable: {return_on_equity_raw}%")

    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_aapl_roe()