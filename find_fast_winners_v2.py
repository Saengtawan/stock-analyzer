#!/usr/bin/env python3
"""
หา combo ที่ให้ Fast Winners สูง + Losers ต่ำ
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

    # Volume
    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1

    # Gap
    if idx > 0:
        prev_close = close.iloc[-2]
        today_open = df['open'].iloc[idx]
        gap = ((today_open - prev_close) / prev_close) * 100
    else:
        gap = 0

    # ATR %
    atr = (high.iloc[-14:] - low.iloc[-14:]).mean()
    atr_pct = (atr / price) * 100

    # Consecutive up days
    up_days = 0
    for i in range(1, min(10, len(close))):
        if close.iloc[-i] > close.iloc[-i-1]:
            up_days += 1
        else:
            break

    # Above MA20
    above_ma20 = price > ma20

    # Price strength in range
    high_20d = high.iloc[-20:].max()
    low_20d = low.iloc[-20:].min()
    strength_20d = ((price - low_20d) / (high_20d - low_20d)) * 100 if high_20d > low_20d else 50

    return {
        'rsi': rsi, 'mom_3d': mom_3d, 'mom_5d': mom_5d,
        'mom_10d': mom_10d, 'mom_20d': mom_20d,
        'vol_ratio': vol_ratio, 'gap': gap, 'atr_pct': atr_pct,
        'up_days': up_days, 'above_ma20': above_ma20, 'strength_20d': strength_20d,
    }


def analyze_outcome(df, idx):
    entry = df['close'].iloc[idx]
    ret_7d = ((df['close'].iloc[min(idx+7, len(df)-1)] / entry) - 1) * 100
    ret_14d = ((df['close'].iloc[min(idx+14, len(df)-1)] / entry) - 1) * 100

    # Max drawdown in 7 days
    max_dd = 0
    for i in range(idx+1, min(idx+8, len(df))):
        dd = ((df['low'].iloc[i] / entry) - 1) * 100
        max_dd = min(max_dd, dd)

    return {
        'ret_7d': ret_7d, 'ret_14d': ret_14d, 'max_dd_7d': max_dd,
        'fast_winner': ret_7d >= 5,
        'loser': ret_14d < 0,
        'big_loser': max_dd < -6,  # Hit stop loss
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
    for days_back in range(30, 180, 3):
        idx = len(df) - 1 - days_back
        if idx < 60 or idx + 14 >= len(df):
            continue
        m = get_metrics(df, idx)
        if m is None:
            continue
        if not m['above_ma20']:
            continue
        if m['mom_10d'] <= 0:
            continue
        outcome = analyze_outcome(df, idx)
        trades.append({'sym': sym, **m, **outcome})

df_trades = pd.DataFrame(trades)
print(f"Total trades: {len(df_trades)}")
print(f"Baseline: Fast Winners {df_trades['fast_winner'].mean()*100:.1f}%, Losers {df_trades['loser'].mean()*100:.1f}%")

# Grid search for best combo
print("\n" + "="*70)
print("GRID SEARCH: Best Combo for Fast Winners + Low Losers")
print("="*70)

# Parameters to test
gap_thresholds = [0, 0.5, 1.0, 1.5]
vol_thresholds = [0.8, 1.0, 1.2, 1.5]
mom_3d_thresholds = [0, 1, 2, 3]
mom_20d_thresholds = [3, 5, 8, 10]
rsi_max = [60, 65, 70, 100]

results = []
tested = 0

for gap in gap_thresholds:
    for vol in vol_thresholds:
        for mom3 in mom_3d_thresholds:
            for mom20 in mom_20d_thresholds:
                for rsi_m in rsi_max:
                    mask = (
                        (df_trades['gap'] >= gap) &
                        (df_trades['vol_ratio'] >= vol) &
                        (df_trades['mom_3d'] >= mom3) &
                        (df_trades['mom_20d'] >= mom20) &
                        (df_trades['rsi'] <= rsi_m)
                    )
                    filtered = df_trades[mask]

                    if len(filtered) < 15:
                        continue

                    fast_pct = filtered['fast_winner'].mean() * 100
                    loser_pct = filtered['loser'].mean() * 100
                    big_loser_pct = filtered['big_loser'].mean() * 100
                    avg_7d = filtered['ret_7d'].mean()

                    # Score: maximize fast winners, minimize losers
                    score = fast_pct - loser_pct

                    results.append({
                        'gap': gap, 'vol': vol, 'mom3': mom3, 'mom20': mom20, 'rsi_max': rsi_m,
                        'trades': len(filtered),
                        'fast_pct': fast_pct, 'loser_pct': loser_pct, 'big_loser_pct': big_loser_pct,
                        'avg_7d': avg_7d, 'score': score,
                    })

                    tested += 1

print(f"Tested {tested} combinations\n")

df_results = pd.DataFrame(results)

# Best by score (fast - loser)
print("="*70)
print("TOP 10: Best (Fast% - Loser%)")
print("="*70)
top = df_results.sort_values('score', ascending=False).head(10)
print(f"\n{'Gap':>6} {'Vol':>6} {'Mom3':>6} {'Mom20':>6} {'RSI<':>6} {'Trades':>8} {'Fast%':>8} {'Lose%':>8} {'Ret7d':>10}")
print("-"*75)
for _, r in top.iterrows():
    print(f"{r['gap']:>6.1f} {r['vol']:>6.1f} {r['mom3']:>6.1f} {r['mom20']:>6.1f} {r['rsi_max']:>6.0f} {r['trades']:>8} {r['fast_pct']:>7.1f}% {r['loser_pct']:>7.1f}% {r['avg_7d']:>+9.2f}%")

# Best with at least 30 trades
print("\n" + "="*70)
print("TOP 10: Best Score with >= 30 Trades")
print("="*70)
top30 = df_results[df_results['trades'] >= 30].sort_values('score', ascending=False).head(10)
print(f"\n{'Gap':>6} {'Vol':>6} {'Mom3':>6} {'Mom20':>6} {'RSI<':>6} {'Trades':>8} {'Fast%':>8} {'Lose%':>8} {'Ret7d':>10}")
print("-"*75)
for _, r in top30.iterrows():
    print(f"{r['gap']:>6.1f} {r['vol']:>6.1f} {r['mom3']:>6.1f} {r['mom20']:>6.1f} {r['rsi_max']:>6.0f} {r['trades']:>8} {r['fast_pct']:>7.1f}% {r['loser_pct']:>7.1f}% {r['avg_7d']:>+9.2f}%")

# Best overall
print("\n" + "="*70)
print("RECOMMENDED: NEW FAST WINNER CRITERIA")
print("="*70)

if len(top30) > 0:
    best = top30.iloc[0]
    print(f"""
  ENTRY CRITERIA:
  ───────────────
  • Gap Up >= {best['gap']:.1f}%
  • Volume Ratio >= {best['vol']:.1f}x (vs 20d avg)
  • Momentum 3d >= {best['mom3']:.1f}%
  • Momentum 20d >= {best['mom20']:.1f}%
  • RSI <= {best['rsi_max']:.0f}
  • Above MA20 (baseline)
  • Momentum 10d > 0 (baseline)

  EXPECTED RESULTS:
  ─────────────────
  • Trades: {best['trades']:.0f}
  • Fast Winners (+5% in 7d): {best['fast_pct']:.1f}%
  • Losers (neg @ 14d): {best['loser_pct']:.1f}%
  • Avg 7-day Return: {best['avg_7d']:+.2f}%

  VS BASELINE:
  ────────────
  • Fast Winners: 17.0% → {best['fast_pct']:.1f}%
  • Losers: 38.0% → {best['loser_pct']:.1f}%
""")

# Show examples
print("\n" + "="*70)
print("EXAMPLE FAST WINNERS from this criteria")
print("="*70)

if len(top30) > 0:
    best = top30.iloc[0]
    mask = (
        (df_trades['gap'] >= best['gap']) &
        (df_trades['vol_ratio'] >= best['vol']) &
        (df_trades['mom_3d'] >= best['mom3']) &
        (df_trades['mom_20d'] >= best['mom20']) &
        (df_trades['rsi'] <= best['rsi_max'])
    )
    winners = df_trades[mask & df_trades['fast_winner']]

    print(f"\nSample fast winners (5%+ in 7 days):")
    for _, row in winners.head(10).iterrows():
        print(f"  {row['sym']:<6} Gap: {row['gap']:+.1f}%  Vol: {row['vol_ratio']:.1f}x  Mom3d: {row['mom_3d']:+.1f}%  Ret7d: {row['ret_7d']:+.1f}%")
