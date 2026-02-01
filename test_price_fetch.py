#!/usr/bin/env python3
"""Test price fetching"""

import yfinance as yf
from datetime import datetime, timedelta

symbol = 'AAPL'
entry_date = datetime.now() - timedelta(days=30)
exit_date = datetime.now()

print(f"Testing {symbol}")
print(f"Entry: {entry_date.date()}")
print(f"Exit: {exit_date.date()}")

ticker = yf.Ticker(symbol)
hist = ticker.history(start=entry_date, end=exit_date)

print(f"\nData points: {len(hist)}")
if not hist.empty:
    print(f"\nFirst date: {hist.index[0].date()}")
    print(f"Last date: {hist.index[-1].date()}")
    print(f"\nFirst Close: ${hist.iloc[0]['Close']:.2f}")
    print(f"Last Close: ${hist.iloc[-1]['Close']:.2f}")

    entry_price = hist.iloc[0]['Close']
    exit_price = hist.iloc[-1]['Close']
    perf = ((exit_price - entry_price) / entry_price) * 100

    print(f"\nPerformance: {perf:+.2f}%")
