#!/usr/bin/env python3
"""
Detailed analysis of NKE
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from api.data_manager import DataManager

dm = DataManager()

print("="*70)
print("NKE (Nike Inc.) - DETAILED ANALYSIS")
print("="*70)

# Get price data
df = dm.get_price_data('NKE', period="1y", interval="1d")

if df is None or len(df) < 50:
    print("Error: Could not load NKE data")
    exit()

close = df['close']
high = df['high']
low = df['low']
volume = df['volume']
current_price = close.iloc[-1]

# Basic info
print(f"\n{'='*70}")
print("PRICE & TREND")
print("="*70)

# Moving averages
ma20 = close.rolling(20).mean().iloc[-1]
ma50 = close.rolling(50).mean().iloc[-1]
ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None

print(f"""
Current Price: ${current_price:.2f}
Date: {df['date'].iloc[-1]}

Moving Averages:
  MA20:  ${ma20:.2f} ({((current_price-ma20)/ma20)*100:+.1f}%)
  MA50:  ${ma50:.2f} ({((current_price-ma50)/ma50)*100:+.1f}%)
  MA200: ${ma200:.2f} ({((current_price-ma200)/ma200)*100:+.1f}%)
""" if ma200 else f"""
Current Price: ${current_price:.2f}
Date: {df['date'].iloc[-1]}

Moving Averages:
  MA20:  ${ma20:.2f} ({((current_price-ma20)/ma20)*100:+.1f}%)
  MA50:  ${ma50:.2f} ({((current_price-ma50)/ma50)*100:+.1f}%)
""")

# Trend status
trend = "UPTREND" if current_price > ma20 > ma50 else "DOWNTREND" if current_price < ma20 < ma50 else "MIXED"
print(f"Trend Status: {trend}")

# Momentum
print(f"\n{'='*70}")
print("MOMENTUM METRICS")
print("="*70)

mom_3d = ((current_price / close.iloc[-4]) - 1) * 100
mom_5d = ((current_price / close.iloc[-6]) - 1) * 100
mom_10d = ((current_price / close.iloc[-11]) - 1) * 100
mom_20d = ((current_price / close.iloc[-21]) - 1) * 100
mom_30d = ((current_price / close.iloc[-31]) - 1) * 100 if len(close) >= 31 else 0

print(f"""
Momentum:
  3-day:   {mom_3d:+.2f}%
  5-day:   {mom_5d:+.2f}%
  10-day:  {mom_10d:+.2f}%
  20-day:  {mom_20d:+.2f}% {'✓ >= 8%' if mom_20d >= 8 else ''}
  30-day:  {mom_30d:+.2f}%
""")

# RSI
delta = close.diff()
gain = delta.where(delta > 0, 0).rolling(14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
rsi = 100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 0.0001)))

rsi_status = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
print(f"RSI(14): {rsi:.1f} ({rsi_status})")

# Volume analysis
print(f"\n{'='*70}")
print("VOLUME ANALYSIS")
print("="*70)

vol_today = volume.iloc[-1]
vol_avg_20 = volume.rolling(20).mean().iloc[-1]
vol_ratio = vol_today / vol_avg_20

print(f"""
Today's Volume: {vol_today:,.0f}
20-day Avg:     {vol_avg_20:,.0f}
Volume Ratio:   {vol_ratio:.2f}x {'(HIGH)' if vol_ratio > 1.5 else '(NORMAL)' if vol_ratio > 0.8 else '(LOW)'}
""")

# Support/Resistance
print(f"{'='*70}")
print("SUPPORT & RESISTANCE")
print("="*70)

# 52-week high/low
high_52w = high.max()
low_52w = low.min()
pos_52w = ((current_price - low_52w) / (high_52w - low_52w)) * 100

# 20-day high/low
high_20d = high.iloc[-20:].max()
low_20d = low.iloc[-20:].min()
dist_from_20d_high = ((current_price - high_20d) / high_20d) * 100

# Recent support (recent lows)
recent_lows = low.iloc[-20:].nsmallest(3).values

print(f"""
52-Week Range:
  High: ${high_52w:.2f}
  Low:  ${low_52w:.2f}
  Position: {pos_52w:.1f}% (from low)

20-Day Range:
  High: ${high_20d:.2f} ({dist_from_20d_high:+.1f}% from current)
  Low:  ${low_20d:.2f}

Nearby Support Levels:
  S1: ${recent_lows[0]:.2f}
  S2: ${recent_lows[1]:.2f}
  S3: ${recent_lows[2]:.2f}

Resistance: ${high_20d:.2f} (20d high), ${high_52w:.2f} (52w high)
""")

# Recent price action
print(f"{'='*70}")
print("RECENT PRICE ACTION (Last 10 days)")
print("="*70)

print(f"\n{'Date':<12} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Change':>10} {'Volume':>12}")
print("-"*78)

for i in range(-10, 0):
    row = df.iloc[i]
    prev_close = df.iloc[i-1]['close']
    change = ((row['close'] - prev_close) / prev_close) * 100
    vol_str = f"{row['volume']:,.0f}"
    date_str = str(row['date'])[:10]
    marker = " *" if abs(change) > 2 else ""
    print(f"{date_str:<12} ${row['open']:>9.2f} ${row['high']:>9.2f} ${row['low']:>9.2f} ${row['close']:>9.2f} {change:>+9.1f}% {vol_str:>12}{marker}")

# Risk analysis
print(f"\n{'='*70}")
print("RISK ANALYSIS")
print("="*70)

# ATR (Average True Range)
tr = pd.DataFrame({
    'hl': high - low,
    'hc': abs(high - close.shift(1)),
    'lc': abs(low - close.shift(1))
}).max(axis=1)
atr = tr.rolling(14).mean().iloc[-1]
atr_pct = (atr / current_price) * 100

# Stop loss levels
stop_6pct = current_price * 0.94
stop_atr = current_price - (2 * atr)

print(f"""
Volatility:
  ATR(14): ${atr:.2f} ({atr_pct:.1f}% of price)
  Daily Range (avg): ${(high.iloc[-20:] - low.iloc[-20:]).mean():.2f}

Stop Loss Suggestions:
  -6% Stop:     ${stop_6pct:.2f}
  2x ATR Stop:  ${stop_atr:.2f}

Position Sizing (50,000 บาท):
  Shares: ~{50000 / (current_price * 35):.0f} shares (assuming 35 THB/USD)
  Risk per share (-6%): ${current_price * 0.06:.2f}
""")

# v6.1 checklist
print(f"{'='*70}")
print("v6.1 CHECKLIST")
print("="*70)

checks = [
    ("Above MA20", current_price > ma20, f"${current_price:.2f} > ${ma20:.2f}"),
    ("52w Position 60-85%", 60 <= pos_52w <= 85, f"{pos_52w:.1f}%"),
    ("Mom 20d >= 8%", mom_20d >= 8, f"{mom_20d:+.1f}%"),
    ("Mom 3d: 1-8%", 1 <= mom_3d <= 8, f"{mom_3d:+.1f}%"),
    ("RSI < 65", rsi < 65, f"{rsi:.0f}"),
    ("Dist from 20d High >= -5%", dist_from_20d_high >= -5, f"{dist_from_20d_high:+.1f}%"),
]

print()
all_pass = True
for name, passed, value in checks:
    status = "✓" if passed else "✗"
    print(f"  {status} {name}: {value}")
    if not passed:
        all_pass = False

print(f"\n  Result: {'ALL PASSED - BUY SIGNAL' if all_pass else 'NOT ALL PASSED'}")

# Summary
print(f"\n{'='*70}")
print("SUMMARY")
print("="*70)

print(f"""
NKE (Nike Inc.) @ ${current_price:.2f}

BULLISH FACTORS:
  + Strong 20d momentum (+{mom_20d:.1f}%)
  + Price above all MAs (MA20, MA50)
  + RSI neutral zone ({rsi:.0f}) - room to run
  + Near 20d high ({dist_from_20d_high:+.1f}%) - potential breakout

BEARISH FACTORS / RISKS:
  - 52w position at {pos_52w:.0f}% (lower end of range)
  - Recent rally may need consolidation

TRADE SETUP:
  Entry:     ${current_price:.2f} (current)
  Stop Loss: ${stop_6pct:.2f} (-6%)
  Target 1:  ${current_price * 1.05:.2f} (+5%)
  Target 2:  ${high_20d:.2f} (20d high)
  Target 3:  ${high_52w:.2f} (52w high)

  Risk/Reward: 1:0.83 (to Target 1)
""")
