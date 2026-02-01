#!/usr/bin/env python3
"""
Fast v5.5 Optimization - using pre-computed data
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from api.data_manager import DataManager

dm = DataManager()

# Smaller test set for speed
TEST_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'GS', 'V', 'MA', 'AXP',
    'UNH', 'LLY', 'ABBV', 'MRK',
    'HD', 'LOW', 'COST', 'WMT', 'SBUX', 'MCD',
    'CAT', 'HON', 'NOC',
    'ASML', 'BABA', 'PDD', 'DDOG', 'SHOP',
    'PANW', 'CRWD', 'NFLX', 'NOW', 'MDB', 'SAP',
    'C', 'BAC', 'FDX', 'TM',
]


def get_metrics(df, idx):
    if df is None or idx < 252:
        return None

    close = df['close'].iloc[:idx+1]
    high = df['high'].iloc[:idx+1]
    lookback = min(252, len(close))
    close = close.iloc[-lookback:]
    high = high.iloc[-lookback:]

    price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain.iloc[-1] / loss.iloc[-1]))

    # MA20
    ma20 = close.rolling(20).mean().iloc[-1]
    above_ma20 = ((price - ma20) / ma20) * 100

    # Momentum
    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_5d = ((price / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_10d = ((price / close.iloc[-11]) - 1) * 100 if len(close) >= 11 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0
    mom_30d = ((price / close.iloc[-31]) - 1) * 100 if len(close) >= 31 else 0

    # 52w
    high_52w = high.max()
    low_52w = close.min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100 if high_52w != low_52w else 50
    days_from_high = close.index[-1] - high.idxmax()

    # BB
    bb_mid = close.rolling(20).mean().iloc[-1]
    bb_std = close.rolling(20).std().iloc[-1]
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_pos = ((price - bb_lower) / (bb_upper - bb_lower)) * 100 if bb_upper != bb_lower else 50

    return {
        'rsi': rsi, 'above_ma20': above_ma20,
        'mom_3d': mom_3d, 'mom_5d': mom_5d, 'mom_10d': mom_10d,
        'mom_20d': mom_20d, 'mom_30d': mom_30d,
        'pos_52w': pos_52w, 'days_high': days_from_high, 'bb': bb_pos
    }


def v54_filter(df):
    """Filter dataframe for v5.4 criteria"""
    mask = (
        (df['pos_52w'] >= 55) & (df['pos_52w'] <= 90) &
        (df['days_high'] >= 50) &
        (df['mom_30d'] >= 6) & (df['mom_30d'] <= 16) &
        (df['mom_10d'] > 0) &
        (df['mom_5d'] >= 0.5) & (df['mom_5d'] <= 12) &
        (df['rsi'] >= 45) & (df['rsi'] <= 62) &
        (df['above_ma20'] > 0)
    )
    return mask


def v55_filter(df, cfg):
    """Filter dataframe for v5.5 criteria"""
    mask = v54_filter(df)
    if cfg.get('mom_20d', 0) > 0:
        mask = mask & (df['mom_20d'] >= cfg['mom_20d'])
    if cfg.get('bb_max', 999) < 999:
        mask = mask & (df['bb'] <= cfg['bb_max'])
    if cfg.get('mom_3d', 0) > 0:
        mask = mask & (df['mom_3d'] >= cfg['mom_3d'])
    return mask


print("Loading data...")
data = {}
for s in TEST_STOCKS:
    try:
        df = dm.get_price_data(s, period="2y", interval="1d")
        if df is not None and len(df) >= 280:
            data[s] = df
    except: pass

print(f"Loaded {len(data)} stocks\n")

# Pre-compute all trade opportunities
print("Computing trades...")
trades = []
for sym, df in data.items():
    for days_back in range(30, 150, 5):  # Step by 5 for speed
        idx = len(df) - 1 - days_back
        if idx < 252: continue

        m = get_metrics(df, idx)
        if not m: continue

        entry = df.iloc[idx]['close']
        exit_idx = idx + 30
        stop = False

        for i in range(idx + 1, min(exit_idx + 1, len(df))):
            if (df.iloc[i]['low'] - entry) / entry <= -0.06:
                stop = True
                exit_idx = i
                break

        exit_p = entry * 0.94 if stop else df.iloc[min(exit_idx, len(df)-1)]['close']
        ret = ((exit_p - entry) / entry) * 100

        trades.append({
            'sym': sym, 'ret': ret, 'win': ret > 0,
            **m
        })

df_trades = pd.DataFrame(trades)
print(f"Total potential trades: {len(df_trades)}\n")

# Test configurations
print("="*70)
print("TESTING CONFIGURATIONS")
print("="*70)

configs = [
    {'name': 'v5.4 (baseline)', 'mom_20d': 0, 'bb_max': 999, 'mom_3d': 0},
    {'name': 'Mom20d > 5', 'mom_20d': 5, 'bb_max': 999, 'mom_3d': 0},
    {'name': 'Mom20d > 6', 'mom_20d': 6, 'bb_max': 999, 'mom_3d': 0},
    {'name': 'BB < 85', 'mom_20d': 0, 'bb_max': 85, 'mom_3d': 0},
    {'name': 'BB < 80', 'mom_20d': 0, 'bb_max': 80, 'mom_3d': 0},
    {'name': 'Mom3d > 1', 'mom_20d': 0, 'bb_max': 999, 'mom_3d': 1},
    {'name': 'Mom3d > 1.5', 'mom_20d': 0, 'bb_max': 999, 'mom_3d': 1.5},
    {'name': 'Mom20d>5 + BB<85', 'mom_20d': 5, 'bb_max': 85, 'mom_3d': 0},
    {'name': 'Mom20d>5 + BB<80', 'mom_20d': 5, 'bb_max': 80, 'mom_3d': 0},
    {'name': 'Mom20d>6 + BB<85', 'mom_20d': 6, 'bb_max': 85, 'mom_3d': 0},
    {'name': 'Mom20d>5 + Mom3d>1', 'mom_20d': 5, 'bb_max': 999, 'mom_3d': 1},
    {'name': 'BB<85 + Mom3d>1', 'mom_20d': 0, 'bb_max': 85, 'mom_3d': 1},
    {'name': 'All 3: M20>5 BB<85 M3>1', 'mom_20d': 5, 'bb_max': 85, 'mom_3d': 1},
    {'name': 'All 3: M20>6 BB<80 M3>1', 'mom_20d': 6, 'bb_max': 80, 'mom_3d': 1},
    {'name': 'All 3: M20>5 BB<80 M3>1.5', 'mom_20d': 5, 'bb_max': 80, 'mom_3d': 1.5},
]

print(f"\n{'Config':<30} {'Trades':>8} {'Win%':>8} {'AvgRet':>10} {'Losers':>8}")
print("-"*70)

results = []
for cfg in configs:
    # Filter trades
    mask = v55_filter(df_trades, cfg)
    filtered = df_trades[mask]

    if len(filtered) < 5:
        continue

    # Dedupe
    filtered = filtered.sort_values(['sym', 'ret'])
    filtered = filtered.drop_duplicates(subset=['sym'], keep='last')

    n = len(filtered)
    w = filtered['win'].sum()
    wr = w / n * 100
    ar = filtered['ret'].mean()
    los = n - w

    print(f"{cfg['name']:<30} {n:>8} {wr:>7.1f}% {ar:>+9.2f}% {los:>8}")

    results.append({
        'name': cfg['name'],
        'trades': n,
        'win_rate': wr,
        'avg_ret': ar,
        'losers': los,
        **cfg
    })

# Find best
print("\n" + "="*70)
print("🏆 BEST CONFIGURATIONS")
print("="*70)

df_results = pd.DataFrame(results)
best = df_results[df_results['trades'] >= 10].sort_values('win_rate', ascending=False).head(3)

for _, row in best.iterrows():
    print(f"\n  {row['name']}")
    print(f"    Trades: {row['trades']}, Win: {row['win_rate']:.1f}%, Avg: {row['avg_ret']:+.2f}%, Losers: {row['losers']}")

# Recommendation
print("\n" + "="*70)
print("💡 v5.5 RECOMMENDATION")
print("="*70)

# Best balanced
balanced = df_results[(df_results['win_rate'] >= 65) & (df_results['trades'] >= 10)]
if len(balanced) > 0:
    rec = balanced.sort_values('avg_ret', ascending=False).iloc[0]
    baseline = df_results[df_results['name'] == 'v5.4 (baseline)'].iloc[0]

    print(f"""
  NEW FILTERS for v5.5:
  ---------------------
  • momentum_20d > {rec['mom_20d']:.0f}%
  • bb_position < {rec['bb_max']:.0f}%
  • momentum_3d > {rec['mom_3d']:.1f}%

  RESULTS:
  --------
  Trades:     {rec['trades']:.0f}
  Win Rate:   {rec['win_rate']:.1f}% (was {baseline['win_rate']:.1f}%)
  Avg Return: {rec['avg_ret']:+.2f}% (was {baseline['avg_ret']:+.2f}%)
  Losers:     {rec['losers']:.0f} (was {baseline['losers']:.0f})

  IMPROVEMENT:
  ------------
  Win Rate:   {baseline['win_rate']:.1f}% → {rec['win_rate']:.1f}% ({rec['win_rate'] - baseline['win_rate']:+.1f}%)
  Losers:     {baseline['losers']:.0f} → {rec['losers']:.0f} ({rec['losers'] - baseline['losers']:+.0f})
""")
else:
    print("  No configuration meets criteria (Win >= 65%, Trades >= 10)")
    best = df_results.sort_values('win_rate', ascending=False).iloc[0]
    print(f"  Best available: {best['name']} - Win: {best['win_rate']:.1f}%")
