#!/usr/bin/env python3
"""
Grid search for optimal v6 criteria
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
    'CRM', 'ADBE', 'NOW', 'NFLX', 'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX',
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    'CAT', 'DE', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'BA', 'UPS', 'FDX',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX',
]


def get_metrics(df, idx):
    if idx < 50:
        return None

    close = df['close'].iloc[:idx+1]
    high = df['high'].iloc[:idx+1]
    open_p = df['open'].iloc[:idx+1]
    volume = df['volume'].iloc[:idx+1]
    price = close.iloc[-1]

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 0.0001)))

    ma20 = close.rolling(20).mean().iloc[-1]
    above_ma20 = ((price - ma20) / ma20) * 100

    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1

    prev_close = close.iloc[-2]
    today_open = open_p.iloc[-1]
    gap = ((today_open - prev_close) / prev_close) * 100

    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_5d = ((price / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_10d = ((price / close.iloc[-11]) - 1) * 100 if len(close) >= 11 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    # 52w position
    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

    return {
        'rsi': rsi, 'above_ma20': above_ma20, 'vol_ratio': vol_ratio,
        'gap': gap, 'mom_3d': mom_3d, 'mom_5d': mom_5d, 'mom_10d': mom_10d,
        'mom_20d': mom_20d, 'pos_52w': pos_52w,
    }


# Load data
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

# Pre-compute all trades
print("Computing trades...")
trades = []
for sym, df in data.items():
    for days_back in range(30, 180, 2):
        idx = len(df) - 1 - days_back
        if idx < 50 or idx + 14 >= len(df):
            continue

        m = get_metrics(df, idx)
        if m is None:
            continue
        if m['above_ma20'] <= 0:  # Base filter
            continue

        entry = df.iloc[idx]['close']

        # 7d return
        ret_7d = ((df.iloc[idx+7]['close'] - entry) / entry) * 100

        # 14d return with stop loss
        exit_idx = idx + 14
        stopped = False
        for i in range(idx + 1, exit_idx + 1):
            if (df.iloc[i]['low'] - entry) / entry <= -0.06:
                stopped = True
                exit_idx = i
                break
        exit_p = entry * 0.94 if stopped else df.iloc[exit_idx]['close']
        ret_14d = ((exit_p - entry) / entry) * 100

        trades.append({
            'sym': sym, **m,
            'ret_7d': ret_7d, 'ret_14d': ret_14d,
            'win': ret_14d > 0, 'fast_win': ret_7d >= 5,
        })

df_trades = pd.DataFrame(trades)
print(f"Total trades (above MA20): {len(df_trades)}\n")

# Grid search
print("="*70)
print("GRID SEARCH")
print("="*70)

results = []

# Parameters to test
vol_options = [0.8, 1.0, 1.2]
rsi_max_options = [60, 65, 70, 80]
mom_20d_min_options = [3, 5, 8]
mom_3d_range_options = [(0, 20), (1, 8), (1, 10), (2, 8)]
pos_52w_options = [(0, 100), (50, 90), (60, 85)]

for vol in vol_options:
    for rsi_max in rsi_max_options:
        for mom_20d in mom_20d_min_options:
            for mom_3d_min, mom_3d_max in mom_3d_range_options:
                for pos_min, pos_max in pos_52w_options:
                    mask = (
                        (df_trades['vol_ratio'] >= vol) &
                        (df_trades['rsi'] < rsi_max) &
                        (df_trades['mom_20d'] >= mom_20d) &
                        (df_trades['mom_3d'] >= mom_3d_min) &
                        (df_trades['mom_3d'] <= mom_3d_max) &
                        (df_trades['pos_52w'] >= pos_min) &
                        (df_trades['pos_52w'] <= pos_max)
                    )
                    filtered = df_trades[mask]

                    if len(filtered) < 30:
                        continue

                    win_rate = filtered['win'].mean() * 100
                    fast_rate = filtered['fast_win'].mean() * 100
                    avg_ret = filtered['ret_14d'].mean()

                    results.append({
                        'vol': vol, 'rsi_max': rsi_max, 'mom_20d': mom_20d,
                        'mom_3d_range': f"{mom_3d_min}-{mom_3d_max}",
                        'pos_52w': f"{pos_min}-{pos_max}",
                        'trades': len(filtered),
                        'win_rate': win_rate,
                        'fast_rate': fast_rate,
                        'avg_ret': avg_ret,
                    })

df_results = pd.DataFrame(results)

# Sort by win rate
print(f"\nTested {len(results)} configurations\n")

print("TOP 10 by WIN RATE (>= 30 trades):")
print(f"{'Vol':>5} {'RSI<':>5} {'M20>':>5} {'M3d':>8} {'52w':>10} {'Trades':>8} {'Win%':>8} {'Fast%':>8} {'AvgRet':>10}")
print("-"*80)

top = df_results.sort_values('win_rate', ascending=False).head(10)
for _, r in top.iterrows():
    print(f"{r['vol']:>5.1f} {r['rsi_max']:>5.0f} {r['mom_20d']:>5.0f} {r['mom_3d_range']:>8} {r['pos_52w']:>10} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['fast_rate']:>7.1f}% {r['avg_ret']:>+9.2f}%")

# Best balanced (high win rate + reasonable trades)
print("\n" + "="*70)
print("BEST BALANCED (Win% > 55% AND Trades >= 50)")
print("="*70)

balanced = df_results[(df_results['win_rate'] > 55) & (df_results['trades'] >= 50)]
if len(balanced) > 0:
    balanced = balanced.sort_values('avg_ret', ascending=False).head(5)
    print(f"\n{'Vol':>5} {'RSI<':>5} {'M20>':>5} {'M3d':>8} {'52w':>10} {'Trades':>8} {'Win%':>8} {'Fast%':>8} {'AvgRet':>10}")
    print("-"*80)
    for _, r in balanced.iterrows():
        print(f"{r['vol']:>5.1f} {r['rsi_max']:>5.0f} {r['mom_20d']:>5.0f} {r['mom_3d_range']:>8} {r['pos_52w']:>10} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['fast_rate']:>7.1f}% {r['avg_ret']:>+9.2f}%")
else:
    print("No configuration meets criteria")
    # Show best available
    best = df_results[df_results['trades'] >= 40].sort_values('win_rate', ascending=False).head(5)
    print("\nBest available (>= 40 trades):")
    print(f"\n{'Vol':>5} {'RSI<':>5} {'M20>':>5} {'M3d':>8} {'52w':>10} {'Trades':>8} {'Win%':>8} {'Fast%':>8} {'AvgRet':>10}")
    print("-"*80)
    for _, r in best.iterrows():
        print(f"{r['vol']:>5.1f} {r['rsi_max']:>5.0f} {r['mom_20d']:>5.0f} {r['mom_3d_range']:>8} {r['pos_52w']:>10} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['fast_rate']:>7.1f}% {r['avg_ret']:>+9.2f}%")
