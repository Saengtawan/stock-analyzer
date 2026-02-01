#!/usr/bin/env python3
"""
Debug why insider buying is always returning 55.0 (neutral)
Test with actual stocks from screener
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

import yfinance as yf
from data_sources.insider_trading import InsiderTradingTracker
from datetime import datetime, timedelta
import pandas as pd

def test_yfinance_direct(symbol):
    """Test yfinance directly to see what data is available"""
    print(f"\n{'='*80}")
    print(f"Testing {symbol} - Direct yfinance")
    print('='*80)

    try:
        ticker = yf.Ticker(symbol)

        # Try to get insider purchases
        print("\n1. Trying ticker.insider_purchases:")
        try:
            insider_purchases = ticker.insider_purchases
            if insider_purchases is not None and not insider_purchases.empty:
                print(f"  ✓ Found {len(insider_purchases)} insider purchase records")
                print(f"\n  Recent purchases (last 5):")
                print(insider_purchases.head())
            else:
                print("  ❌ No insider_purchases data (None or empty)")
        except Exception as e:
            print(f"  ❌ Error: {e}")

        # Try to get all insider transactions
        print("\n2. Trying ticker.insider_transactions:")
        try:
            insider_transactions = ticker.insider_transactions
            if insider_transactions is not None and not insider_transactions.empty:
                print(f"  ✓ Found {len(insider_transactions)} insider transaction records")

                # Filter for purchases
                cutoff_30d = datetime.now() - timedelta(days=30)
                if hasattr(insider_transactions, 'index'):
                    recent = insider_transactions[insider_transactions.index >= pd.Timestamp(cutoff_30d)]
                    if not recent.empty:
                        print(f"\n  Recent transactions (last 30 days): {len(recent)}")
                        print(recent.head())
            else:
                print("  ❌ No insider_transactions data (None or empty)")
        except Exception as e:
            print(f"  ❌ Error: {e}")

        # Try institutional holders
        print("\n3. Trying ticker.institutional_holders:")
        try:
            institutional = ticker.institutional_holders
            if institutional is not None and not institutional.empty:
                print(f"  ✓ Found {len(institutional)} institutional holders")
                print(institutional.head())
            else:
                print("  ❌ No institutional_holders data")
        except Exception as e:
            print(f"  ❌ Error: {e}")

    except Exception as e:
        print(f"  ❌ Overall error: {e}")


def test_tracker(symbol):
    """Test our insider tracker"""
    print(f"\n{'='*80}")
    print(f"Testing {symbol} - InsiderTradingTracker")
    print('='*80)

    tracker = InsiderTradingTracker()
    data = tracker.get_insider_activity(symbol)

    if data:
        print(f"  Buys (30d): {data['insider_buys_30d']}")
        print(f"  Score: {data['insider_score']:.1f}/100")
        print(f"  Sentiment: {data['insider_sentiment']}")
        print(f"  Has Recent Buying: {data['has_recent_buying']}")
    else:
        print("  ❌ No data returned")


def main():
    print("\n" + "="*80)
    print("🔍 INSIDER BUYING DEBUG")
    print("="*80)

    # Test with stocks from screener
    test_symbols = ['IRTC', 'HEI', 'SNOW']

    for symbol in test_symbols:
        test_yfinance_direct(symbol)
        test_tracker(symbol)

    print("\n" + "="*80)
    print("✅ Debug complete!")
    print("="*80)

if __name__ == "__main__":
    main()
