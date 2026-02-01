#!/usr/bin/env python3
"""
Test Yahoo Finance previousClose for TSLA
Check if it's returning Dec 15 close (475.31) or stale Dec 12 close (458.96)
"""

import yfinance as yf
import pandas as pd
from datetime import datetime
import pytz

print("=" * 80)
print("Testing TSLA Previous Close Data")
print("=" * 80)

ticker = yf.Ticker("TSLA")

# Method 1: Get from ticker.info
print("\n1. From ticker.info:")
info = ticker.info
prev_close_info = info.get('previousClose')
reg_prev_close = info.get('regularMarketPreviousClose')
print(f"   previousClose: ${prev_close_info}")
print(f"   regularMarketPreviousClose: ${reg_prev_close}")

# Method 2: Get from 1d history
print("\n2. From history(period='1d'):")
data_1d = ticker.history(period="1d", interval="5m", prepost=True)
print(f"   Data shape: {data_1d.shape}")
if not data_1d.empty:
    print(f"   First timestamp: {data_1d.index[0]}")
    print(f"   Last timestamp: {data_1d.index[-1]}")
    print(f"   First close: ${data_1d['Close'].iloc[0]:.2f}")
    print(f"   Last close: ${data_1d['Close'].iloc[-1]:.2f}")

# Method 3: Get from 2d history to find actual previous day close
print("\n3. From history(period='2d') - to get real previous close:")
data_2d = ticker.history(period="2d", interval="1h", prepost=False)
print(f"   Data shape: {data_2d.shape}")
if not data_2d.empty:
    print(f"   Index type: {type(data_2d.index)}")
    print(f"   Columns: {list(data_2d.columns)}")
    print(f"   First few rows:")
    print(data_2d.head())

# Method 4: Get from 5d history to see more context
print("\n4. From history(period='5d') - Last 5 trading days:")
data_5d = ticker.history(period="5d", interval="1d", prepost=False)
if not data_5d.empty:
    print(f"   Index: {data_5d.index}")
    for idx in data_5d.index:
        close_price = data_5d.loc[idx, 'Close']
        date_str = idx.strftime('%Y-%m-%d (%a)') if hasattr(idx, 'strftime') else str(idx)
        print(f"   {date_str}: Close = ${close_price:.2f}")

print("\n" + "=" * 80)
print("EXPECTED RESULTS:")
print("  Dec 12 (Thu): $458.96")
print("  Dec 13 (Fri): ???")
print("  Dec 14 (Sat): Market closed")
print("  Dec 15 (Sun): Market closed")
print("  Dec 16 (Mon): Pre-market now")
print("  -> Previous Close should be latest trading day close")
print("=" * 80)

# Get current time
eastern = pytz.timezone('US/Eastern')
now_et = datetime.now(eastern)
print(f"\nCurrent ET time: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
