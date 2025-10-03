#!/usr/bin/env python3
"""
Test script to check what data is actually available from each API
"""
import yfinance as yf
import requests
import pandas as pd
import json
from datetime import datetime

def test_yahoo_finance(symbol="AAPL"):
    """Test what data Yahoo Finance actually provides"""
    print(f"\n{'='*50}")
    print(f"TESTING YAHOO FINANCE FOR {symbol}")
    print(f"{'='*50}")

    try:
        ticker = yf.Ticker(symbol)

        # Test price data
        print("\n1. PRICE DATA:")
        hist = ticker.history(period="1y")
        if not hist.empty:
            print(f"  ✅ Available columns: {list(hist.columns)}")
            print(f"  ✅ Rows: {len(hist)}")
            print(f"  ✅ Latest close: ${hist['Close'].iloc[-1]:.2f}")
        else:
            print("  ❌ No price data")

        # Test financial data
        print("\n2. FINANCIAL DATA:")
        try:
            info = ticker.info
            print(f"  ✅ Info keys: {len(info.keys())} fields available")

            # Key financial metrics
            key_metrics = ['marketCap', 'trailingPE', 'forwardPE', 'priceToSalesTrailing12Months',
                          'pegRatio', 'bookValue', 'priceToBook', 'enterpriseValue']
            available_metrics = {k: v for k, v in info.items() if k in key_metrics and v is not None}
            print(f"  ✅ Key metrics available: {list(available_metrics.keys())}")

        except Exception as e:
            print(f"  ❌ Info error: {e}")

        # Test income statement
        print("\n3. INCOME STATEMENT:")
        try:
            income_stmt = ticker.income_stmt
            if not income_stmt.empty:
                print(f"  ✅ Income statement rows: {len(income_stmt)}")
                print(f"  ✅ Available fields: {list(income_stmt.index[:10])}")
            else:
                print("  ❌ No income statement")
        except Exception as e:
            print(f"  ❌ Income statement error: {e}")

        # Test balance sheet
        print("\n4. BALANCE SHEET:")
        try:
            balance_sheet = ticker.balance_sheet
            if not balance_sheet.empty:
                print(f"  ✅ Balance sheet rows: {len(balance_sheet)}")
                print(f"  ✅ Available fields: {list(balance_sheet.index[:10])}")
            else:
                print("  ❌ No balance sheet")
        except Exception as e:
            print(f"  ❌ Balance sheet error: {e}")

        # Test analyst recommendations
        print("\n5. ANALYST RECOMMENDATIONS:")
        try:
            recommendations = ticker.recommendations
            if recommendations is not None and not recommendations.empty:
                print(f"  ✅ Recommendations rows: {len(recommendations)}")
                print(f"  ✅ Latest recommendation: {recommendations.iloc[-1].to_dict()}")
            else:
                print("  ❌ No recommendations")
        except Exception as e:
            print(f"  ❌ Recommendations error: {e}")

        # Test earnings data
        print("\n6. EARNINGS DATA:")
        try:
            earnings = ticker.earnings
            if earnings is not None and not earnings.empty:
                print(f"  ✅ Earnings rows: {len(earnings)}")
                print(f"  ✅ Latest earnings: {earnings.iloc[-1].to_dict()}")
            else:
                print("  ❌ No earnings data")
        except Exception as e:
            print(f"  ❌ Earnings error: {e}")

    except Exception as e:
        print(f"❌ Yahoo Finance test failed: {e}")

def test_sec_edgar(symbol="AAPL"):
    """Test SEC EDGAR API"""
    print(f"\n{'='*50}")
    print(f"TESTING SEC EDGAR FOR {symbol}")
    print(f"{'='*50}")

    try:
        # Test company tickers endpoint
        print("\n1. COMPANY TICKERS:")
        tickers_url = "https://www.sec.gov/files/company_tickers.json"
        headers = {
            'User-Agent': 'Stock Analyzer (contact@example.com)',
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'www.sec.gov'
        }

        response = requests.get(tickers_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Company tickers loaded: {len(data)} companies")

            # Find AAPL CIK
            aapl_data = None
            for key, company in data.items():
                if company.get('ticker') == symbol:
                    aapl_data = company
                    break

            if aapl_data:
                print(f"  ✅ Found {symbol}: CIK {aapl_data['cik_str']}")
            else:
                print(f"  ❌ {symbol} not found in SEC database")
        else:
            print(f"  ❌ SEC API error: {response.status_code}")

    except Exception as e:
        print(f"❌ SEC EDGAR test failed: {e}")

def test_free_apis(symbol="AAPL"):
    """Test other free APIs"""
    print(f"\n{'='*50}")
    print(f"TESTING FREE APIS FOR {symbol}")
    print(f"{'='*50}")

    # Test Alpha Vantage (free tier)
    print("\n1. ALPHA VANTAGE (without API key):")
    try:
        # This will show what happens without API key
        av_url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={symbol}&apikey=demo"
        response = requests.get(av_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'Information' in data:
                print(f"  ❌ {data['Information']}")
            elif 'Error Message' in data:
                print(f"  ❌ {data['Error Message']}")
            else:
                print(f"  ✅ Data available: {list(data.keys())[:5]}")
        else:
            print(f"  ❌ Alpha Vantage error: {response.status_code}")
    except Exception as e:
        print(f"  ❌ Alpha Vantage error: {e}")

    # Test Financial Modeling Prep (free tier)
    print("\n2. FINANCIAL MODELING PREP (without API key):")
    try:
        fmp_url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
        response = requests.get(fmp_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                print(f"  ✅ Profile data available: {list(data[0].keys())[:5]}")
            elif isinstance(data, dict) and 'Error Message' in data:
                print(f"  ❌ {data['Error Message']}")
            else:
                print(f"  ❌ Unexpected response format")
        else:
            print(f"  ❌ FMP error: {response.status_code}")
    except Exception as e:
        print(f"  ❌ FMP error: {e}")

def main():
    print("🔍 STOCK DATA API TESTING")
    print("This script tests what data is actually available from free APIs")

    test_yahoo_finance("AAPL")
    test_sec_edgar("AAPL")
    test_free_apis("AAPL")

    print(f"\n{'='*50}")
    print("SUMMARY & RECOMMENDATIONS")
    print(f"{'='*50}")
    print("Based on the test results above:")
    print("1. Use Yahoo Finance for: Price data, basic financials, analyst recommendations")
    print("2. Remove sections that depend on unavailable data")
    print("3. Use AI to fill gaps where no free API exists")
    print("4. Focus on what actually works instead of mock data")

if __name__ == "__main__":
    main()