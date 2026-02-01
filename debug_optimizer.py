#!/usr/bin/env python3
"""Deep debug of optimizer data"""

import sys
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from api.data_manager import DataManager

START_DATE = datetime(2025, 10, 1)
END_DATE = datetime(2026, 1, 30)

print("=" * 60)
print("  DEEP DIAGNOSTIC")
print("=" * 60)

dm = DataManager()

# Test with single stock
test_symbols = ['AAPL', 'TSLA', 'NVDA']

for sym in test_symbols:
    print(f"\n--- {sym} ---")
    df = dm.get_price_data(sym, period='6mo')

    if df is None:
        print(f"  ERROR: No data for {sym}")
        continue

    print(f"  Shape: {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Index type: {type(df.index)}")
    print(f"  Date range: {df.index[0]} to {df.index[-1]}")
    print(f"  Index[0] type: {type(df.index[0])}")

    # Check if dates are in range
    in_range = 0
    for date in df.index:
        ts = pd.Timestamp(date)
        if ts >= pd.Timestamp(START_DATE) and ts <= pd.Timestamp(END_DATE):
            in_range += 1
    print(f"  Dates in range: {in_range}")

    # Sample data
    print(f"\n  Sample row:")
    row = df.iloc[-1]
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in df.columns:
            val = row[col]
            print(f"    {col}: {val} (type: {type(val).__name__})")

    # Check if values can be converted to float
    try:
        close = float(df.iloc[-1]['Close'])
        print(f"\n  Close as float: {close}")
    except Exception as e:
        print(f"\n  ERROR converting close: {e}")

    # Add indicators
    print(f"\n  Adding indicators...")
    df_copy = df.copy()

    # Check column types
    for col in ['Close', 'High', 'Low', 'Open', 'Volume']:
        if col in df_copy.columns:
            if isinstance(df_copy[col], pd.DataFrame):
                print(f"    {col} is DataFrame, flattening...")
                df_copy[col] = df_copy[col].iloc[:, 0]

    c = df_copy['Close']
    print(f"  Close series type: {type(c)}")
    print(f"  Close dtype: {c.dtype}")

    # Calculate momentum
    mom_1d = c.pct_change(1) * 100
    print(f"\n  mom_1d head: {mom_1d.head()}")
    print(f"  mom_1d NaN count: {mom_1d.isna().sum()}")

    # Check index for dates in range
    print(f"\n  Checking filtered dates...")
    count = 0
    for i in range(50, len(df) - 10):
        date = df.index[i]
        ts = pd.Timestamp(date)
        if ts >= pd.Timestamp(START_DATE) and ts <= pd.Timestamp(END_DATE):
            count += 1
    print(f"  Valid entries (after 50 warmup): {count}")

print("\n" + "=" * 60)
print("  CONCLUSION")
print("=" * 60)
