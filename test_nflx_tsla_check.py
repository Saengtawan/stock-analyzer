#!/usr/bin/env python3
"""
Check NFLX and TSLA pre-market data to verify gap calculations
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

from api.yahoo_finance_client import YahooFinanceClient
import yfinance as yf
from datetime import datetime
import pytz

def check_stock(symbol):
    """Check detailed stock data"""
    print("=" * 80)
    print(f"Checking {symbol}")
    print("=" * 80)

    client = YahooFinanceClient()
    ticker = yf.Ticker(symbol)

    # Get current time
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    print(f"\nCurrent Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # Get basic info
    info = ticker.info
    print(f"\n📊 Basic Info:")
    print(f"   Previous Close: ${info.get('previousClose', 'N/A'):.2f}")
    print(f"   Regular Market Price: ${info.get('regularMarketPrice', 'N/A'):.2f}")
    print(f"   Open: ${info.get('open', 'N/A'):.2f}")
    print(f"   Current Price: ${info.get('currentPrice', 'N/A'):.2f}")

    # Get pre-market data using our client
    pm_data = client.get_premarket_data(symbol, interval="5m")

    if pm_data.get('has_premarket_data'):
        print(f"\n📈 Pre-market Data (from our scanner):")
        print(f"   Previous Close: ${pm_data['previous_close']:.2f}")
        print(f"   Current PM Price: ${pm_data['current_premarket_price']:.2f}")
        print(f"   Gap: {pm_data['gap_percent']:.2f}% ({pm_data['gap_direction']})")
        print(f"   PM High: ${pm_data['premarket_high']:.2f}")
        print(f"   PM Low: ${pm_data['premarket_low']:.2f}")
        print(f"   PM Volume: {pm_data['premarket_volume']:,}")

        # Calculate actual change
        prev_close = pm_data['previous_close']
        current_pm = pm_data['current_premarket_price']
        change = current_pm - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0

        print(f"\n✅ Verification:")
        print(f"   Change: ${change:+.2f} ({change_pct:+.2f}%)")
        print(f"   Direction: {'UP ⬆️' if change > 0 else 'DOWN ⬇️'}")
    else:
        print(f"\n❌ No pre-market data: {pm_data.get('error', 'Unknown')}")

    # Get latest intraday data
    print(f"\n📊 Latest Intraday Data:")
    data = ticker.history(period="1d", interval="1m", prepost=True)
    if not data.empty:
        latest = data.iloc[-1]
        first = data.iloc[0]
        print(f"   First bar: ${first['Close']:.2f} at {data.index[0]}")
        print(f"   Latest bar: ${latest['Close']:.2f} at {data.index[-1]}")
        print(f"   Change: ${latest['Close'] - first['Close']:+.2f}")

    print()

if __name__ == '__main__':
    check_stock('NFLX')
    print("\n")
    check_stock('TSLA')
