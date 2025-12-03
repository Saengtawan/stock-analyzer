#!/usr/bin/env python3
"""
Simple test for institutional ownership data flow
"""
import sys
import os

# Set up paths
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from src.api.yahoo_finance_client import YahooFinanceClient
from src.api.data_manager import DataManager
from src.analysis.fundamental.fundamental_analyzer import FundamentalAnalyzer

def test():
    symbol = "FUFU"
    print(f"\n{'='*80}")
    print(f"Testing Institutional Ownership Data Pipeline for {symbol}")
    print(f"{'='*80}\n")

    # Step 1: Yahoo Finance API
    print("STEP 1: Yahoo Finance API")
    print("-" * 80)
    client = YahooFinanceClient()
    financial_data = client.get_financial_data(symbol)

    inst_pct = financial_data.get('held_percent_institutions')
    print(f"held_percent_institutions: {inst_pct}")
    if inst_pct:
        print(f"  → {inst_pct * 100:.2f}%")
    print()

    # Step 2: DataManager
    print("STEP 2: DataManager")
    print("-" * 80)
    dm = DataManager()
    financial_data_dm = dm.get_financial_data(symbol)

    inst_pct_dm = financial_data_dm.get('held_percent_institutions')
    print(f"held_percent_institutions: {inst_pct_dm}")
    if inst_pct_dm:
        print(f"  → {inst_pct_dm * 100:.2f}%")
    print()

    # Step 3: FundamentalAnalyzer
    print("STEP 3: FundamentalAnalyzer")
    print("-" * 80)

    # Get price
    price_data = client.get_price_data(symbol, period='1mo', interval='1d')
    current_price = float(price_data['Close'].iloc[-1]) if not price_data.empty else 0

    analyzer = FundamentalAnalyzer(financial_data_dm, current_price)
    fund_analysis = analyzer.analyze()

    inst_pct_fa = fund_analysis.get('held_percent_institutions')
    print(f"held_percent_institutions: {inst_pct_fa}")
    if inst_pct_fa:
        print(f"  → {inst_pct_fa * 100:.2f}%")
    print()

    # Results
    print(f"{'='*80}")
    print("RESULTS")
    print(f"{'='*80}")

    if inst_pct and inst_pct_dm and inst_pct_fa:
        if inst_pct == inst_pct_dm == inst_pct_fa:
            print(f"✅ SUCCESS! Data flows correctly: {inst_pct * 100:.2f}%")
            print(f"   API → DataManager → FundamentalAnalyzer")
        else:
            print(f"❌ Data mismatch!")
            print(f"   API: {inst_pct}")
            print(f"   DataManager: {inst_pct_dm}")
            print(f"   FundamentalAnalyzer: {inst_pct_fa}")
    elif not inst_pct:
        print(f"⚠️  No data from Yahoo Finance API")
    elif not inst_pct_dm:
        print(f"❌ Data lost at DataManager")
    elif not inst_pct_fa:
        print(f"❌ Data lost at FundamentalAnalyzer")

    print(f"{'='*80}\n")

if __name__ == "__main__":
    test()
