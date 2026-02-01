#!/usr/bin/env python3
"""
หาลักษณะหุ้นที่ขึ้นเร็วใน 7 วัน vs หุ้นที่ต้องรอนาน
โจทย์: ทำกำไรใน 7-14 วัน ไม่ใช่ 30 วัน
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
    """คำนวณ metrics ณ วันที่ idx"""
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

    # Moving averages
    ma5 = close.rolling(5).mean().iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else ma20

    # Momentum (different timeframes)
    mom_1d = ((price / close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0
    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_5d = ((price / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_10d = ((price / close.iloc[-11]) - 1) * 100 if len(close) >= 11 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    # Volume
    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1
    vol_3d_avg = volume.iloc[-3:].mean() / vol_avg if vol_avg > 0 else 1

    # Volatility
    atr = (high.iloc[-14:] - low.iloc[-14:]).mean()
    atr_pct = (atr / price) * 100

    # Range position
    high_5d = high.iloc[-5:].max()
    low_5d = low.iloc[-5:].min()
    range_pos_5d = ((price - low_5d) / (high_5d - low_5d)) * 100 if high_5d > low_5d else 50

    high_20d = high.iloc[-20:].max()
    low_20d = low.iloc[-20:].min()
    range_pos_20d = ((price - low_20d) / (high_20d - low_20d)) * 100 if high_20d > low_20d else 50

    # Distance from highs
    high_52w = high.max()
    dist_from_high = ((price - high_52w) / high_52w) * 100

    # Gap up (today open vs yesterday close)
    if idx > 0:
        prev_close = close.iloc[-2]
        today_open = df['open'].iloc[idx]
        gap = ((today_open - prev_close) / prev_close) * 100
    else:
        gap = 0

    # Consecutive up days
    up_days = 0
    for i in range(1, min(10, len(close))):
        if close.iloc[-i] > close.iloc[-i-1]:
            up_days += 1
        else:
            break

    # Price vs MAs
    above_ma5 = price > ma5
    above_ma10 = price > ma10
    above_ma20 = price > ma20
    above_ma50 = price > ma50
    ma_alignment = int(above_ma5) + int(above_ma10) + int(above_ma20) + int(above_ma50)

    # Breakout signals
    near_5d_high = (price >= high_5d * 0.99)  # within 1% of 5d high
    near_20d_high = (price >= high_20d * 0.99)

    return {
        'rsi': rsi,
        'mom_1d': mom_1d, 'mom_3d': mom_3d, 'mom_5d': mom_5d,
        'mom_10d': mom_10d, 'mom_20d': mom_20d,
        'vol_ratio': vol_ratio, 'vol_3d_avg': vol_3d_avg,
        'atr_pct': atr_pct,
        'range_pos_5d': range_pos_5d, 'range_pos_20d': range_pos_20d,
        'dist_from_high': dist_from_high,
        'gap': gap, 'up_days': up_days,
        'ma_alignment': ma_alignment,
        'near_5d_high': near_5d_high, 'near_20d_high': near_20d_high,
        'above_ma20': above_ma20,
    }


def analyze_outcome(df, idx):
    """วิเคราะห์ผลลัพธ์หลัง entry"""
    entry = df['close'].iloc[idx]

    # Return at day 3, 5, 7, 14
    ret_3d = ((df['close'].iloc[min(idx+3, len(df)-1)] / entry) - 1) * 100
    ret_5d = ((df['close'].iloc[min(idx+5, len(df)-1)] / entry) - 1) * 100
    ret_7d = ((df['close'].iloc[min(idx+7, len(df)-1)] / entry) - 1) * 100
    ret_14d = ((df['close'].iloc[min(idx+14, len(df)-1)] / entry) - 1) * 100

    # Max gain in first 7 days
    max_gain_7d = 0
    for i in range(idx+1, min(idx+8, len(df))):
        gain = ((df['high'].iloc[i] / entry) - 1) * 100
        max_gain_7d = max(max_gain_7d, gain)

    # Max drawdown in first 7 days
    max_dd_7d = 0
    for i in range(idx+1, min(idx+8, len(df))):
        dd = ((df['low'].iloc[i] / entry) - 1) * 100
        max_dd_7d = min(max_dd_7d, dd)

    # Days to reach +5%
    days_to_5pct = None
    for i in range(idx+1, min(idx+30, len(df))):
        if ((df['high'].iloc[i] / entry) - 1) * 100 >= 5:
            days_to_5pct = i - idx
            break

    return {
        'ret_3d': ret_3d, 'ret_5d': ret_5d, 'ret_7d': ret_7d, 'ret_14d': ret_14d,
        'max_gain_7d': max_gain_7d, 'max_dd_7d': max_dd_7d,
        'days_to_5pct': days_to_5pct,
        'fast_winner': ret_7d >= 5,  # +5% in 7 days
        'slow_winner': ret_7d < 5 and ret_14d >= 5,  # +5% in 14d but not 7d
        'loser': ret_14d < 0,  # negative after 14 days
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

# Collect all trade entries
print("Analyzing trades...")
trades = []

for sym, df in data.items():
    for days_back in range(30, 180, 3):  # Every 3 days for speed
        idx = len(df) - 1 - days_back
        if idx < 60 or idx + 14 >= len(df):
            continue

        m = get_metrics(df, idx)
        if m is None:
            continue

        # Basic filter: above MA20 and some momentum
        if not m['above_ma20']:
            continue
        if m['mom_10d'] <= 0:
            continue

        outcome = analyze_outcome(df, idx)

        trades.append({
            'sym': sym,
            **m,
            **outcome,
        })

df_trades = pd.DataFrame(trades)
print(f"Total trades: {len(df_trades)}\n")

# Categorize
fast_winners = df_trades[df_trades['fast_winner'] == True]
slow_winners = df_trades[df_trades['slow_winner'] == True]
losers = df_trades[df_trades['loser'] == True]

print("="*70)
print("TRADE CATEGORIES")
print("="*70)
print(f"Fast Winners (+5% in 7d):  {len(fast_winners)} ({len(fast_winners)/len(df_trades)*100:.1f}%)")
print(f"Slow Winners (+5% in 14d): {len(slow_winners)} ({len(slow_winners)/len(df_trades)*100:.1f}%)")
print(f"Losers (negative @ 14d):   {len(losers)} ({len(losers)/len(df_trades)*100:.1f}%)")

# Compare metrics between groups
print("\n" + "="*70)
print("WHAT MAKES FAST WINNERS DIFFERENT?")
print("="*70)

metrics_to_compare = [
    'mom_1d', 'mom_3d', 'mom_5d', 'mom_10d', 'mom_20d',
    'vol_ratio', 'vol_3d_avg',
    'rsi', 'atr_pct',
    'range_pos_5d', 'range_pos_20d',
    'gap', 'up_days', 'ma_alignment',
    'dist_from_high',
]

print(f"\n{'Metric':<20} {'Fast Win':>12} {'Slow Win':>12} {'Losers':>12} {'Diff F-L':>12}")
print("-"*70)

significant_diffs = []

for metric in metrics_to_compare:
    fw = fast_winners[metric].mean()
    sw = slow_winners[metric].mean()
    lo = losers[metric].mean()
    diff = fw - lo

    # Mark significant differences
    sig = ""
    if abs(diff) > abs(lo) * 0.3 and abs(diff) > 0.5:  # >30% difference
        sig = " ***"
        significant_diffs.append((metric, fw, lo, diff))
    elif abs(diff) > abs(lo) * 0.15:  # >15% difference
        sig = " *"

    print(f"{metric:<20} {fw:>+11.2f} {sw:>+11.2f} {lo:>+11.2f} {diff:>+11.2f}{sig}")

# Near highs analysis
print("\n" + "="*70)
print("BREAKOUT SIGNALS")
print("="*70)

for col in ['near_5d_high', 'near_20d_high']:
    fw_pct = fast_winners[col].mean() * 100
    lo_pct = losers[col].mean() * 100
    print(f"{col}: Fast Winners {fw_pct:.1f}% vs Losers {lo_pct:.1f}%")

# Find the best filters
print("\n" + "="*70)
print("FINDING FAST WINNER FILTERS")
print("="*70)

# Test different filter combinations
filter_tests = [
    ("mom_3d > 2%", df_trades['mom_3d'] > 2),
    ("mom_3d > 3%", df_trades['mom_3d'] > 3),
    ("mom_5d > 3%", df_trades['mom_5d'] > 3),
    ("mom_5d > 4%", df_trades['mom_5d'] > 4),
    ("vol_ratio > 1.2", df_trades['vol_ratio'] > 1.2),
    ("vol_ratio > 1.5", df_trades['vol_ratio'] > 1.5),
    ("vol_3d_avg > 1.2", df_trades['vol_3d_avg'] > 1.2),
    ("gap > 1%", df_trades['gap'] > 1),
    ("gap > 2%", df_trades['gap'] > 2),
    ("up_days >= 2", df_trades['up_days'] >= 2),
    ("up_days >= 3", df_trades['up_days'] >= 3),
    ("near_5d_high", df_trades['near_5d_high'] == True),
    ("near_20d_high", df_trades['near_20d_high'] == True),
    ("range_pos_5d > 80", df_trades['range_pos_5d'] > 80),
    ("range_pos_5d > 90", df_trades['range_pos_5d'] > 90),
    ("rsi 50-65", (df_trades['rsi'] >= 50) & (df_trades['rsi'] <= 65)),
    ("rsi 55-70", (df_trades['rsi'] >= 55) & (df_trades['rsi'] <= 70)),
    ("ma_alignment = 4", df_trades['ma_alignment'] == 4),
    ("dist_from_high > -5%", df_trades['dist_from_high'] > -5),
    ("dist_from_high > -3%", df_trades['dist_from_high'] > -3),
]

print(f"\n{'Filter':<25} {'Trades':>8} {'Fast%':>8} {'Slow%':>8} {'Lose%':>8} {'7d Ret':>10}")
print("-"*70)

results = []
for name, mask in filter_tests:
    filtered = df_trades[mask]
    if len(filtered) < 10:
        continue

    fast_pct = filtered['fast_winner'].mean() * 100
    slow_pct = filtered['slow_winner'].mean() * 100
    lose_pct = filtered['loser'].mean() * 100
    avg_7d = filtered['ret_7d'].mean()

    print(f"{name:<25} {len(filtered):>8} {fast_pct:>7.1f}% {slow_pct:>7.1f}% {lose_pct:>7.1f}% {avg_7d:>+9.2f}%")
    results.append({'name': name, 'trades': len(filtered), 'fast_pct': fast_pct, 'avg_7d': avg_7d})

# Combined filters
print("\n" + "="*70)
print("COMBINED FILTERS FOR FAST WINNERS")
print("="*70)

combos = [
    ("mom_3d>2 + vol>1.2", (df_trades['mom_3d'] > 2) & (df_trades['vol_ratio'] > 1.2)),
    ("mom_3d>2 + near_5d_high", (df_trades['mom_3d'] > 2) & (df_trades['near_5d_high'])),
    ("mom_5d>3 + vol>1.2", (df_trades['mom_5d'] > 3) & (df_trades['vol_ratio'] > 1.2)),
    ("mom_5d>3 + near_5d_high", (df_trades['mom_5d'] > 3) & (df_trades['near_5d_high'])),
    ("gap>1 + vol>1.2", (df_trades['gap'] > 1) & (df_trades['vol_ratio'] > 1.2)),
    ("gap>1 + mom_3d>2", (df_trades['gap'] > 1) & (df_trades['mom_3d'] > 2)),
    ("up_days>=2 + mom_3d>2", (df_trades['up_days'] >= 2) & (df_trades['mom_3d'] > 2)),
    ("near_5d_high + vol>1.2", (df_trades['near_5d_high']) & (df_trades['vol_ratio'] > 1.2)),
    ("near_5d_high + rsi<70", (df_trades['near_5d_high']) & (df_trades['rsi'] < 70)),
    ("mom_3d>2 + rsi<65 + vol>1.2", (df_trades['mom_3d'] > 2) & (df_trades['rsi'] < 65) & (df_trades['vol_ratio'] > 1.2)),
    ("dist>-3% + mom_3d>2", (df_trades['dist_from_high'] > -3) & (df_trades['mom_3d'] > 2)),
    ("dist>-3% + vol>1.2", (df_trades['dist_from_high'] > -3) & (df_trades['vol_ratio'] > 1.2)),
]

print(f"\n{'Combo':<35} {'Trades':>8} {'Fast%':>8} {'Lose%':>8} {'7d Ret':>10}")
print("-"*70)

for name, mask in combos:
    filtered = df_trades[mask]
    if len(filtered) < 10:
        continue

    fast_pct = filtered['fast_winner'].mean() * 100
    lose_pct = filtered['loser'].mean() * 100
    avg_7d = filtered['ret_7d'].mean()

    marker = " <-- GOOD" if fast_pct > 40 and lose_pct < 25 else ""
    print(f"{name:<35} {len(filtered):>8} {fast_pct:>7.1f}% {lose_pct:>7.1f}% {avg_7d:>+9.2f}%{marker}")

# Best recommendation
print("\n" + "="*70)
print("RECOMMENDATION: FAST WINNER CRITERIA")
print("="*70)

# Find best combo with at least 20 trades
df_results = pd.DataFrame(results)
if len(df_results) > 0:
    best = df_results[df_results['trades'] >= 15].sort_values('fast_pct', ascending=False).head(3)

    print("\nTop filters for catching fast winners (+5% in 7 days):")
    for _, row in best.iterrows():
        print(f"  {row['name']}: {row['fast_pct']:.1f}% fast winners, avg 7d return: {row['avg_7d']:+.2f}%")
