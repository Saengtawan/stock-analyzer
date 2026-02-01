#!/usr/bin/env python3
"""
วิเคราะห์ว่า losers ใน v6.3 มีลักษณะอะไรต่างจาก winners
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
    above_ma20 = price > ma20
    pct_above_ma20 = ((price - ma20) / ma20) * 100

    # Momentum
    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_5d = ((price / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_10d = ((price / close.iloc[-11]) - 1) * 100 if len(close) >= 11 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    # Volume
    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1

    # Gap
    prev_close = close.iloc[-2]
    today_open = df['open'].iloc[idx]
    gap = ((today_open - prev_close) / prev_close) * 100

    # Bollinger
    bb_std = close.rolling(20).std().iloc[-1]
    bb_upper = ma20 + 2 * bb_std
    bb_lower = ma20 - 2 * bb_std
    bb_pos = ((price - bb_lower) / (bb_upper - bb_lower)) * 100 if bb_upper > bb_lower else 50

    # ATR
    atr = (high.iloc[-14:] - low.iloc[-14:]).mean()
    atr_pct = (atr / price) * 100

    # Days since 20d high
    high_20d = high.iloc[-20:].max()
    at_20d_high = price >= high_20d * 0.99

    # Range position
    low_20d = low.iloc[-20:].min()
    range_pos = ((price - low_20d) / (high_20d - low_20d)) * 100 if high_20d > low_20d else 50

    # Consecutive up/down days
    up_days = 0
    for i in range(1, min(10, len(close))):
        if close.iloc[-i] > close.iloc[-i-1]:
            up_days += 1
        else:
            break

    return {
        'rsi': rsi, 'bb_pos': bb_pos, 'pct_above_ma20': pct_above_ma20,
        'mom_3d': mom_3d, 'mom_5d': mom_5d, 'mom_10d': mom_10d, 'mom_20d': mom_20d,
        'vol_ratio': vol_ratio, 'gap': gap, 'atr_pct': atr_pct,
        'at_20d_high': at_20d_high, 'range_pos': range_pos, 'up_days': up_days,
        'above_ma20': above_ma20,
    }


def analyze_outcome(df, idx):
    entry = df['close'].iloc[idx]
    ret_7d = ((df['close'].iloc[min(idx+7, len(df)-1)] / entry) - 1) * 100
    ret_14d = ((df['close'].iloc[min(idx+14, len(df)-1)] / entry) - 1) * 100

    return {
        'ret_7d': ret_7d, 'ret_14d': ret_14d,
        'fast_winner': ret_7d >= 5,
        'loser': ret_14d < 0,
    }


print("Loading...")
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
trades = []
for sym, df in data.items():
    for days_back in range(30, 180, 2):
        idx = len(df) - 1 - days_back
        if idx < 60 or idx + 14 >= len(df):
            continue
        m = get_metrics(df, idx)
        if m is None:
            continue
        outcome = analyze_outcome(df, idx)
        trades.append({'sym': sym, **m, **outcome})

df_trades = pd.DataFrame(trades)

# Apply v6.3 filter
v6_mask = (
    (df_trades['above_ma20']) &
    (df_trades['gap'] >= 1.0) &
    (df_trades['vol_ratio'] >= 1.2) &
    (df_trades['mom_3d'] >= 1) &
    (df_trades['mom_20d'] >= 5)
)

df_v6 = df_trades[v6_mask].copy()
print(f"v6.3 trades: {len(df_v6)}")
print(f"Fast winners: {df_v6['fast_winner'].sum()} ({df_v6['fast_winner'].mean()*100:.1f}%)")
print(f"Losers: {df_v6['loser'].sum()} ({df_v6['loser'].mean()*100:.1f}%)")

# Compare winners vs losers
winners = df_v6[df_v6['fast_winner']]
losers = df_v6[df_v6['loser']]

print("\n" + "="*60)
print("WHAT'S DIFFERENT: FAST WINNERS vs LOSERS")
print("="*60)

metrics = ['rsi', 'bb_pos', 'pct_above_ma20', 'mom_3d', 'mom_5d', 'mom_10d',
           'mom_20d', 'gap', 'atr_pct', 'range_pos', 'up_days']

print(f"\n{'Metric':<20} {'Winners':>12} {'Losers':>12} {'Diff':>12}")
print("-"*60)

diffs = []
for m in metrics:
    w = winners[m].mean()
    l = losers[m].mean()
    d = w - l
    sig = " ***" if abs(d) > abs(l) * 0.25 else ""
    print(f"{m:<20} {w:>11.2f} {l:>11.2f} {d:>+11.2f}{sig}")
    diffs.append({'metric': m, 'winners': w, 'losers': l, 'diff': d})

# At 20d high
print(f"\n{'at_20d_high':<20} {winners['at_20d_high'].mean()*100:>10.1f}% {losers['at_20d_high'].mean()*100:>10.1f}%")

# Test additional filters on v6.3
print("\n" + "="*60)
print("TESTING ADDITIONAL FILTERS ON v6.3")
print("="*60)

additional_filters = [
    ("rsi < 70", df_v6['rsi'] < 70),
    ("rsi < 65", df_v6['rsi'] < 65),
    ("rsi < 60", df_v6['rsi'] < 60),
    ("bb_pos < 90", df_v6['bb_pos'] < 90),
    ("bb_pos < 80", df_v6['bb_pos'] < 80),
    ("mom_3d < 8", df_v6['mom_3d'] < 8),
    ("mom_3d < 6", df_v6['mom_3d'] < 6),
    ("mom_5d < 10", df_v6['mom_5d'] < 10),
    ("gap < 5", df_v6['gap'] < 5),
    ("gap < 3", df_v6['gap'] < 3),
    ("pct_above_ma20 < 5", df_v6['pct_above_ma20'] < 5),
    ("up_days <= 3", df_v6['up_days'] <= 3),
    ("not at_20d_high", ~df_v6['at_20d_high']),
]

print(f"\n{'Filter':<25} {'Trades':>8} {'Fast%':>8} {'Lose%':>8} {'Score':>8}")
print("-"*60)

# Baseline
print(f"{'(baseline v6.3)':<25} {len(df_v6):>8} {df_v6['fast_winner'].mean()*100:>7.1f}% {df_v6['loser'].mean()*100:>7.1f}%")

for name, mask in additional_filters:
    filtered = df_v6[mask]
    if len(filtered) < 10:
        continue

    fast_pct = filtered['fast_winner'].mean() * 100
    lose_pct = filtered['loser'].mean() * 100
    score = fast_pct - lose_pct

    marker = " <-- BETTER" if score > (df_v6['fast_winner'].mean()*100 - df_v6['loser'].mean()*100) + 5 else ""
    print(f"{name:<25} {len(filtered):>8} {fast_pct:>7.1f}% {lose_pct:>7.1f}% {score:>+7.1f}{marker}")

# Combined filters
print("\n" + "="*60)
print("COMBINED FILTERS")
print("="*60)

combos = [
    ("rsi<65 + bb<90", (df_v6['rsi'] < 65) & (df_v6['bb_pos'] < 90)),
    ("rsi<65 + mom3d<8", (df_v6['rsi'] < 65) & (df_v6['mom_3d'] < 8)),
    ("rsi<70 + gap<5", (df_v6['rsi'] < 70) & (df_v6['gap'] < 5)),
    ("bb<90 + mom3d<8", (df_v6['bb_pos'] < 90) & (df_v6['mom_3d'] < 8)),
    ("rsi<65 + bb<90 + gap<5", (df_v6['rsi'] < 65) & (df_v6['bb_pos'] < 90) & (df_v6['gap'] < 5)),
    ("bb<85 + mom3d<6", (df_v6['bb_pos'] < 85) & (df_v6['mom_3d'] < 6)),
]

print(f"\n{'Combo':<35} {'Trades':>8} {'Fast%':>8} {'Lose%':>8}")
print("-"*60)

for name, mask in combos:
    filtered = df_v6[mask]
    if len(filtered) < 5:
        continue

    fast_pct = filtered['fast_winner'].mean() * 100
    lose_pct = filtered['loser'].mean() * 100

    marker = " <--" if lose_pct < 25 else ""
    print(f"{name:<35} {len(filtered):>8} {fast_pct:>7.1f}% {lose_pct:>7.1f}%{marker}")
