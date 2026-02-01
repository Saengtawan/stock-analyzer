#!/usr/bin/env python3
"""
Test v5.5 candidate filters with FULL backtest
Based on findings:
- Mom20d > 5 → 100% win rate
- BB < 80 → 100% win rate
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from api.data_manager import DataManager

dm = DataManager()

# Full universe
TEST_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD', 'ORCL',
    'CRM', 'ADBE', 'NOW', 'NFLX', 'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX',
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    'CAT', 'DE', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'BA', 'UPS', 'FDX',
    'NVO', 'ASML', 'TSM', 'BABA', 'PDD', 'JD', 'TCEHY', 'SAP', 'TM', 'UL',
]


def get_metrics(df, idx):
    if idx < 252:
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

    # MA
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
    bb = ((price - bb_lower) / (bb_upper - bb_lower)) * 100 if bb_upper != bb_lower else 50

    return {
        'rsi': rsi, 'above_ma20': above_ma20,
        'mom_3d': mom_3d, 'mom_5d': mom_5d, 'mom_10d': mom_10d,
        'mom_20d': mom_20d, 'mom_30d': mom_30d,
        'pos_52w': pos_52w, 'days_high': days_from_high, 'bb': bb
    }


def passes_v54(m):
    if m is None: return False
    if m['pos_52w'] < 55 or m['pos_52w'] > 90: return False
    if m['days_high'] < 50: return False
    if m['mom_30d'] < 6 or m['mom_30d'] > 16: return False
    if m['mom_10d'] <= 0: return False
    if m['mom_5d'] < 0.5 or m['mom_5d'] > 12: return False
    if m['rsi'] < 45 or m['rsi'] > 62: return False
    if m['above_ma20'] <= 0: return False
    return True


def passes_v55a(m):
    """v5.5a: v5.4 + Mom20d > 5"""
    if not passes_v54(m): return False
    if m['mom_20d'] < 5: return False
    return True


def passes_v55b(m):
    """v5.5b: v5.4 + BB < 80"""
    if not passes_v54(m): return False
    if m['bb'] > 80: return False
    return True


def passes_v55c(m):
    """v5.5c: v5.4 + Mom20d > 5 + BB < 85"""
    if not passes_v54(m): return False
    if m['mom_20d'] < 5: return False
    if m['bb'] > 85: return False
    return True


def backtest(data, check_func, name):
    """Backtest a filter function"""
    results = []

    for sym, df in data.items():
        for days_back in range(30, 180):
            idx = len(df) - 1 - days_back
            if idx < 252: continue

            m = get_metrics(df, idx)
            if not check_func(m): continue

            entry = df.iloc[idx]['close']
            entry_date = pd.to_datetime(df.iloc[idx]['date'])

            exit_idx = idx + 30
            stop = False

            for i in range(idx + 1, min(exit_idx + 1, len(df))):
                if (df.iloc[i]['low'] - entry) / entry <= -0.06:
                    stop = True
                    exit_idx = i
                    break

            exit_p = entry * 0.94 if stop else df.iloc[min(exit_idx, len(df)-1)]['close']
            ret = ((exit_p - entry) / entry) * 100

            results.append({
                'sym': sym, 'date': entry_date, 'ret': ret,
                'win': ret > 0, 'stop': stop, **m
            })

    if not results:
        return None

    df_res = pd.DataFrame(results)
    # Dedupe
    df_res = df_res.sort_values(['sym', 'date'])
    df_res['diff'] = df_res.groupby('sym')['date'].diff().dt.days
    df_res = df_res[(df_res['diff'].isna()) | (df_res['diff'] > 10)]

    n = len(df_res)
    wins = df_res['win'].sum()
    stops = df_res['stop'].sum()

    return {
        'name': name,
        'trades': n,
        'wins': wins,
        'losers': n - wins,
        'win_rate': wins / n * 100 if n > 0 else 0,
        'avg_ret': df_res['ret'].mean(),
        'total_ret': df_res['ret'].sum(),
        'stops': stops,
        'details': df_res
    }


# Main
print("Loading data...")
data = {}
for s in TEST_STOCKS:
    try:
        df = dm.get_price_data(s, period="2y", interval="1d")
        if df is not None and len(df) >= 280:
            data[s] = df
    except: pass

print(f"Loaded {len(data)} stocks\n")

# Run backtests
print("Running backtests...")
results = []

r = backtest(data, passes_v54, "v5.4 (baseline)")
if r: results.append(r)

r = backtest(data, passes_v55a, "v5.5a (Mom20d > 5)")
if r: results.append(r)

r = backtest(data, passes_v55b, "v5.5b (BB < 80)")
if r: results.append(r)

r = backtest(data, passes_v55c, "v5.5c (Mom20d>5 + BB<85)")
if r: results.append(r)

# Display results
print("\n" + "="*80)
print("BACKTEST RESULTS COMPARISON")
print("="*80)
print(f"\n{'Version':<25} {'Trades':>8} {'Win%':>8} {'AvgRet':>10} {'Losers':>8} {'Stops':>8}")
print("-"*75)

for r in results:
    print(f"{r['name']:<25} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['avg_ret']:>+9.2f}% {r['losers']:>8} {r['stops']:>8}")

# Show losers for each version
for r in results:
    df = r['details']
    losers = df[df['win'] == False]
    if len(losers) > 0:
        print(f"\n--- {r['name']} LOSERS ---")
        for _, row in losers.sort_values('ret').head(5).iterrows():
            print(f"  {row['sym']:<6} {row['date'].strftime('%Y-%m-%d')} Ret: {row['ret']:+.1f}%  Mom20d: {row['mom_20d']:+.1f}%  BB: {row['bb']:.0f}%")

# Best recommendation
print("\n" + "="*80)
print("🏆 RECOMMENDATION")
print("="*80)

# Find best with >= 15 trades
valid = [r for r in results if r['trades'] >= 15]
if valid:
    best = max(valid, key=lambda x: x['win_rate'])
    baseline = results[0]

    print(f"""
  BEST: {best['name']}

  Trades:     {best['trades']}
  Win Rate:   {best['win_rate']:.1f}% (was {baseline['win_rate']:.1f}%)
  Avg Return: {best['avg_ret']:+.2f}% (was {baseline['avg_ret']:+.2f}%)
  Losers:     {best['losers']} (was {baseline['losers']})
  Stop Losses: {best['stops']} (was {baseline['stops']})

  IMPROVEMENT:
  Win Rate:   {baseline['win_rate']:.1f}% → {best['win_rate']:.1f}% ({best['win_rate'] - baseline['win_rate']:+.1f}%)
  Losers:     {baseline['losers']} → {best['losers']} ({best['losers'] - baseline['losers']:+d})
""")
else:
    print("  No configuration has enough trades (>= 15)")
    best = max(results, key=lambda x: x['win_rate'])
    print(f"  Best available: {best['name']} - {best['trades']} trades, {best['win_rate']:.1f}% win rate")
