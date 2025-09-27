#!/usr/bin/env python3
"""
Debug actual TTD data from API
"""
import sys
from main import StockAnalyzer

def debug_ttd_data():
    """Debug the actual TTD data from API"""
    print("Debugging actual TTD data from API...")

    # Initialize analyzer
    analyzer = StockAnalyzer()

    try:
        # Get fundamental analysis
        from analysis.fundamental.fundamental_analyzer import FundamentalAnalyzer

        # Get financial data
        financial_data = analyzer.data_manager.get_financial_data('TTD')

        print("Raw Financial Data:")
        print(f"ROE: {financial_data.get('roe')} (type: {type(financial_data.get('roe'))})")
        print(f"ROA: {financial_data.get('roa')} (type: {type(financial_data.get('roa'))})")
        print(f"Profit Margin: {financial_data.get('profit_margin')} (type: {type(financial_data.get('profit_margin'))})")

        # Initialize fundamental analyzer
        current_price = financial_data.get('current_price', 44.47)
        fund_analyzer = FundamentalAnalyzer('TTD', current_price, financial_data)

        # Get calculated ratios
        ratios = fund_analyzer._calculate_financial_ratios(financial_data, current_price)

        print("\nCalculated Ratios:")
        print(f"ROE: {ratios.get('roe')} (type: {type(ratios.get('roe'))})")
        print(f"ROA: {ratios.get('roa')} (type: {type(ratios.get('roa'))})")
        print(f"Profit Margin: {ratios.get('profit_margin')} (type: {type(ratios.get('profit_margin'))})")

        # Test profitability scoring
        profitability_score = fund_analyzer._score_profitability(ratios)
        print(f"\nProfitability Score: {profitability_score}/2")

        return True

    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = debug_ttd_data()
    sys.exit(0 if success else 1)