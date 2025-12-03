#!/usr/bin/env python3
"""
Test institutional ownership data pipeline fix (v7.3.1)
"""
import sys
sys.path.insert(0, '/home/saengtawan/work/project/cc/stock-analyzer')

from src.api.yahoo_finance_client import YahooFinanceClient
from src.analysis.fundamental.fundamental_analyzer import FundamentalAnalyzer

def test_institutional_data_flow():
    """Test that held_percent_institutions flows through the entire pipeline"""

    symbol = "FUFU"
    print(f"\n{'='*60}")
    print(f"Testing Institutional Ownership Data Pipeline for {symbol}")
    print(f"{'='*60}\n")

    # Step 1: Get data from Yahoo Finance API
    print("Step 1: Yahoo Finance API")
    print("-" * 60)
    client = YahooFinanceClient()
    financial_data = client.get_financial_data(symbol)

    institution_pct_raw = financial_data.get('held_percent_institutions')
    print(f"✅ Raw API data: held_percent_institutions = {institution_pct_raw}")
    if institution_pct_raw:
        print(f"   Percentage: {institution_pct_raw * 100:.2f}%")
    print()

    # Step 2: Process through FundamentalAnalyzer
    print("Step 2: FundamentalAnalyzer Processing")
    print("-" * 60)

    # Get current price
    price_data = client.get_price_data(symbol, period='1mo', interval='1d')
    current_price = float(price_data['Close'].iloc[-1]) if not price_data.empty else 0

    analyzer = FundamentalAnalyzer(financial_data, current_price)
    fundamental_analysis = analyzer.analyze()

    institution_pct_processed = fundamental_analysis.get('held_percent_institutions')
    print(f"✅ Processed data: held_percent_institutions = {institution_pct_processed}")
    if institution_pct_processed:
        print(f"   Percentage: {institution_pct_processed * 100:.2f}%")
    print()

    # Step 3: Verify data integrity
    print("Step 3: Data Pipeline Verification")
    print("-" * 60)

    if institution_pct_raw == institution_pct_processed:
        print("✅ SUCCESS: Data flows correctly through the pipeline!")
        print(f"   API → FundamentalAnalyzer: {institution_pct_raw} == {institution_pct_processed}")
    else:
        print("❌ FAILURE: Data lost in pipeline!")
        print(f"   API value: {institution_pct_raw}")
        print(f"   Processed value: {institution_pct_processed}")
    print()

    # Step 4: Check other fields
    print("Step 4: Other Financial Data Fields")
    print("-" * 60)

    fields_to_check = [
        'held_percent_insiders',
        'short_percent_of_float',
        'short_ratio',
        'fifty_two_week_high',
        'fifty_two_week_low',
        'trailing_eps',
        'operating_cash_flow',
        'revenue_growth',
        'debt_to_equity'
    ]

    all_passed = True
    for field in fields_to_check:
        raw_value = financial_data.get(field)
        processed_value = fundamental_analysis.get(field)

        if raw_value == processed_value:
            status = "✅"
        else:
            status = "❌"
            all_passed = False

        print(f"{status} {field}: {raw_value} → {processed_value}")

    print()

    # Final Result
    print(f"{'='*60}")
    print("FINAL RESULT")
    print(f"{'='*60}")

    if institution_pct_raw and institution_pct_raw == institution_pct_processed and all_passed:
        print("✅ ALL TESTS PASSED!")
        print(f"\n✅ Institutional ownership for {symbol}: {institution_pct_processed * 100:.2f}%")
        print("✅ Data pipeline is working correctly!")
        print("✅ Risk warnings will now display accurate institutional ownership data!")
    else:
        print("❌ SOME TESTS FAILED!")
        if not institution_pct_raw:
            print("⚠️  Yahoo Finance API returned None for institutional ownership")
        if institution_pct_raw != institution_pct_processed:
            print("⚠️  Data was lost or corrupted in the pipeline")
        if not all_passed:
            print("⚠️  Some fields are not flowing through correctly")

    print(f"{'='*60}\n")

if __name__ == "__main__":
    test_institutional_data_flow()
