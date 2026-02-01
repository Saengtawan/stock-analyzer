#!/usr/bin/env python3
"""
Test v6 criteria - Volume-based fast winner approach
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from api.data_manager import DataManager

dm = DataManager()

STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD', 'ORCL',
    'CRM', 'ADBE', 'NOW', 'NFLX', 'QCOM', 'MU', 'PANW', 'CRWD', 'SNOW', 'DDOG',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'UNH', 'LLY', 'ABBV', 'MRK', 'TMO', 'HD', 'LOW', 'COST', 'WMT', 'SBUX', 'MCD',
    'CAT', 'HON', 'NOC', 'FDX', 'ASML', 'BABA', 'PDD', 'SHOP', 'SAP', 'TM',
]


def get_metrics(df, idx):
    if idx < 60:
        return None

    close = df['close'].iloc[:idx+1]
    high = df['high'].iloc[:idx+1]
    low = df['low'].iloc[:idx+1]
    volume = df['volume'].iloc[:idx+1]
    price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 0.0001)))

    # MA
    ma20 = close.rolling(20).mean().iloc[-1]

    # Momentum
    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_5d = ((price / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_10d = ((price / close.iloc[-11]) - 1) * 100 if len(close) >= 11 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    # Volume - KEY!
    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1

    # Gap
    if idx > 0:
        prev_close = close.iloc[-2]
        today_open = df['open'].iloc[idx]
        gap = ((today_open - prev_close) / prev_close) * 100
    else:
        gap = 0

    # Above MA20
    above_ma20 = price > ma20

    return {
        'rsi': rsi, 'mom_3d': mom_3d, 'mom_5d': mom_5d,
        'mom_10d': mom_10d, 'mom_20d': mom_20d,
        'vol_ratio': vol_ratio, 'gap': gap, 'above_ma20': above_ma20,
    }


def analyze_outcome(df, idx):
    entry = df['close'].iloc[idx]
    ret_7d = ((df['close'].iloc[min(idx+7, len(df)-1)] / entry) - 1) * 100
    ret_14d = ((df['close'].iloc[min(idx+14, len(df)-1)] / entry) - 1) * 100

    max_dd = 0
    for i in range(idx+1, min(idx+8, len(df))):
        dd = ((df['low'].iloc[i] / entry) - 1) * 100
        max_dd = min(max_dd, dd)

    return {
        'ret_7d': ret_7d, 'ret_14d': ret_14d, 'max_dd_7d': max_dd,
        'fast_winner': ret_7d >= 5,
        'winner_14d': ret_14d >= 5,
        'loser': ret_14d < 0,
    }


print("Loading data...")
data = {}
for s in STOCKS:
    try:
        df = dm.get_price_data(s, period="2y", interval="1d")
        if df is not None and len(df) >= 280:
            data[s] = df
    except:
        pass

print(f"Loaded {len(data)} stocks\n")

# Collect trades
print("Analyzing...")
trades = []
for sym, df in data.items():
    for days_back in range(30, 180, 2):  # Every 2 days
        idx = len(df) - 1 - days_back
        if idx < 60 or idx + 14 >= len(df):
            continue
        m = get_metrics(df, idx)
        if m is None:
            continue
        outcome = analyze_outcome(df, idx)
        trades.append({'sym': sym, **m, **outcome})

df_trades = pd.DataFrame(trades)
print(f"Total trades: {len(df_trades)}\n")

# Test different criteria
print("="*70)
print("COMPARING CRITERIA")
print("="*70)

criteria = [
    # v5.4 style
    ("v5.4 style (mom gates only)",
     (df_trades['above_ma20']) &
     (df_trades['mom_10d'] > 0) &
     (df_trades['mom_5d'] >= 0.5) & (df_trades['mom_5d'] <= 12) &
     (df_trades['rsi'] >= 45) & (df_trades['rsi'] <= 62)),

    # v6.0 - Volume focused (relaxed)
    ("v6.0 Vol>=1.2 + Mom20d>=3",
     (df_trades['above_ma20']) &
     (df_trades['vol_ratio'] >= 1.2) &
     (df_trades['mom_20d'] >= 3) &
     (df_trades['rsi'] <= 70)),

    # v6.1 - Volume + short-term momentum
    ("v6.1 Vol>=1.2 + Mom3d>=1",
     (df_trades['above_ma20']) &
     (df_trades['vol_ratio'] >= 1.2) &
     (df_trades['mom_3d'] >= 1) &
     (df_trades['mom_20d'] >= 3) &
     (df_trades['rsi'] <= 70)),

    # v6.2 - Volume + gap
    ("v6.2 Vol>=1.2 + Gap>=0.5",
     (df_trades['above_ma20']) &
     (df_trades['vol_ratio'] >= 1.2) &
     (df_trades['gap'] >= 0.5) &
     (df_trades['mom_20d'] >= 3) &
     (df_trades['rsi'] <= 70)),

    # v6.3 - Best combo from grid search
    ("v6.3 Gap>=1 + Vol>=1.2 + Mom3>=1 + Mom20>=5",
     (df_trades['above_ma20']) &
     (df_trades['gap'] >= 1.0) &
     (df_trades['vol_ratio'] >= 1.2) &
     (df_trades['mom_3d'] >= 1) &
     (df_trades['mom_20d'] >= 5)),

    # v6.4 - Slightly relaxed
    ("v6.4 Gap>=0.5 + Vol>=1.1 + Mom3>=0.5 + Mom20>=4",
     (df_trades['above_ma20']) &
     (df_trades['gap'] >= 0.5) &
     (df_trades['vol_ratio'] >= 1.1) &
     (df_trades['mom_3d'] >= 0.5) &
     (df_trades['mom_20d'] >= 4)),
]

print(f"\n{'Criteria':<45} {'Trades':>8} {'Fast%':>8} {'Win14%':>8} {'Lose%':>8} {'Ret7d':>10}")
print("-"*90)

results = []
for name, mask in criteria:
    filtered = df_trades[mask]
    if len(filtered) < 5:
        continue

    fast_pct = filtered['fast_winner'].mean() * 100
    win14_pct = filtered['winner_14d'].mean() * 100
    loser_pct = filtered['loser'].mean() * 100
    avg_7d = filtered['ret_7d'].mean()

    print(f"{name:<45} {len(filtered):>8} {fast_pct:>7.1f}% {win14_pct:>7.1f}% {loser_pct:>7.1f}% {avg_7d:>+9.2f}%")

    results.append({
        'name': name, 'trades': len(filtered),
        'fast_pct': fast_pct, 'win14_pct': win14_pct,
        'loser_pct': loser_pct, 'avg_7d': avg_7d,
    })

# Best recommendation
print("\n" + "="*70)
print("RECOMMENDATION")
print("="*70)

df_res = pd.DataFrame(results)
# Balance: good fast%, low losers, reasonable trades
df_res['score'] = df_res['fast_pct'] - df_res['loser_pct']
best = df_res.sort_values('score', ascending=False).iloc[0]

print(f"""
  BEST APPROACH: {best['name']}

  Results:
  ────────
  • Trades: {best['trades']:.0f}
  • Fast Winners (+5% in 7d): {best['fast_pct']:.1f}%
  • Winners (+5% in 14d): {best['win14_pct']:.1f}%
  • Losers (neg @ 14d): {best['loser_pct']:.1f}%
  • Avg 7-day Return: {best['avg_7d']:+.2f}%

  KEY CHANGE FROM v5.x:
  ─────────────────────
  • ADD: Volume Ratio >= 1.2x (หุ้นต้องมีคนสนใจ!)
  • ADD: Gap up >= 0.5-1% (มี catalyst)
  • SIMPLIFY: ลด rules จาก 10+ เหลือ 4-5 ตัว
""")

# Show trade examples
print("\n" + "="*70)
print("TRADE EXAMPLES")
print("="*70)

# Use best criteria
best_mask = (
    (df_trades['above_ma20']) &
    (df_trades['gap'] >= 0.5) &
    (df_trades['vol_ratio'] >= 1.1) &
    (df_trades['mom_3d'] >= 0.5) &
    (df_trades['mom_20d'] >= 4)
)

filtered = df_trades[best_mask]

print("\nFast Winners (5%+ in 7 days):")
winners = filtered[filtered['fast_winner']].head(8)
for _, r in winners.iterrows():
    print(f"  {r['sym']:<6} Vol: {r['vol_ratio']:.1f}x  Gap: {r['gap']:+.1f}%  Mom3d: {r['mom_3d']:+.1f}%  → Ret7d: {r['ret_7d']:+.1f}%")

print("\nLosers (if any):")
losers = filtered[filtered['loser']].head(5)
for _, r in losers.iterrows():
    print(f"  {r['sym']:<6} Vol: {r['vol_ratio']:.1f}x  Gap: {r['gap']:+.1f}%  Mom3d: {r['mom_3d']:+.1f}%  → Ret14d: {r['ret_14d']:+.1f}%")
