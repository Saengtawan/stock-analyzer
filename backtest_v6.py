#!/usr/bin/env python3
"""
Backtest v6.0 criteria
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
    """Calculate metrics at a specific index"""
    if idx < 50:
        return None

    close = df['close'].iloc[:idx+1]
    high = df['high'].iloc[:idx+1]
    open_p = df['open'].iloc[:idx+1]
    volume = df['volume'].iloc[:idx+1]
    price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 0.0001)))

    # MA20
    ma20 = close.rolling(20).mean().iloc[-1]
    above_ma20 = ((price - ma20) / ma20) * 100

    # Volume ratio
    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1

    # Gap
    prev_close = close.iloc[-2]
    today_open = open_p.iloc[-1]
    gap = ((today_open - prev_close) / prev_close) * 100

    # Momentum
    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    return {
        'rsi': rsi, 'above_ma20': above_ma20, 'vol_ratio': vol_ratio,
        'gap': gap, 'mom_3d': mom_3d, 'mom_20d': mom_20d,
    }


def passes_v6(m):
    """v6.0 criteria"""
    if m is None:
        return False
    if m['above_ma20'] <= 0:
        return False
    if m['vol_ratio'] < 1.0:
        return False
    if m['mom_20d'] < 5:
        return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 10:
        return False
    if m['rsi'] >= 70:
        return False
    return True


def passes_v54(m):
    """v5.4 criteria for comparison"""
    if m is None:
        return False
    if m['above_ma20'] <= 0:
        return False
    if m['mom_3d'] < 1.5:  # v5.5 had mom_3d > 1.5
        return False
    if m['mom_20d'] < 4:  # v5.5 had mom_20d > 4
        return False
    if m['rsi'] < 45 or m['rsi'] > 62:
        return False
    return True


def backtest(data, check_func, name, hold_days=14, stop_loss=-0.06):
    """Run backtest"""
    results = []

    for sym, df in data.items():
        for days_back in range(30, 180, 2):
            idx = len(df) - 1 - days_back
            if idx < 50 or idx + hold_days >= len(df):
                continue

            m = get_metrics(df, idx)
            if not check_func(m):
                continue

            entry = df.iloc[idx]['close']
            entry_date = pd.to_datetime(df.iloc[idx]['date'])

            # Check for stop loss or hold period
            exit_idx = idx + hold_days
            stopped = False

            for i in range(idx + 1, min(exit_idx + 1, len(df))):
                if (df.iloc[i]['low'] - entry) / entry <= stop_loss:
                    stopped = True
                    exit_idx = i
                    break

            exit_price = entry * (1 + stop_loss) if stopped else df.iloc[min(exit_idx, len(df)-1)]['close']
            ret = ((exit_price - entry) / entry) * 100

            # Also calculate 7-day return
            ret_7d = ((df.iloc[min(idx+7, len(df)-1)]['close'] - entry) / entry) * 100

            results.append({
                'sym': sym, 'date': entry_date, 'ret': ret, 'ret_7d': ret_7d,
                'win': ret > 0, 'fast_win': ret_7d >= 5, 'stopped': stopped,
                'gap': m['gap'],
            })

    if not results:
        return None

    df_res = pd.DataFrame(results)

    # Dedupe (same stock within 10 days)
    df_res = df_res.sort_values(['sym', 'date'])
    df_res['diff'] = df_res.groupby('sym')['date'].diff().dt.days
    df_res = df_res[(df_res['diff'].isna()) | (df_res['diff'] > 10)]

    n = len(df_res)
    wins = df_res['win'].sum()
    fast_wins = df_res['fast_win'].sum()
    stops = df_res['stopped'].sum()

    return {
        'name': name,
        'trades': n,
        'wins': wins,
        'win_rate': wins / n * 100 if n > 0 else 0,
        'fast_wins': fast_wins,
        'fast_win_rate': fast_wins / n * 100 if n > 0 else 0,
        'avg_ret': df_res['ret'].mean(),
        'avg_ret_7d': df_res['ret_7d'].mean(),
        'stops': stops,
        'losers': n - wins,
        'details': df_res,
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

# Run backtests
print("="*70)
print("BACKTEST RESULTS")
print("="*70)

results = []

# v5.4 baseline
r = backtest(data, passes_v54, "v5.4 (baseline)", hold_days=30, stop_loss=-0.06)
if r:
    results.append(r)

# v6.0 with 14-day hold
r = backtest(data, passes_v6, "v6.0 (14d hold)", hold_days=14, stop_loss=-0.06)
if r:
    results.append(r)

# v6.0 with 7-day hold
r = backtest(data, passes_v6, "v6.0 (7d hold)", hold_days=7, stop_loss=-0.06)
if r:
    results.append(r)

# v6.0 with gap filter
def passes_v6_gap(m):
    return passes_v6(m) and m['gap'] >= 1.0

r = backtest(data, passes_v6_gap, "v6.0 + Gap>=1%", hold_days=14, stop_loss=-0.06)
if r:
    results.append(r)

# Print results
print(f"\n{'Version':<25} {'Trades':>8} {'Win%':>8} {'Fast%':>8} {'AvgRet':>10} {'Losers':>8} {'Stops':>8}")
print("-"*80)

for r in results:
    print(f"{r['name']:<25} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['fast_win_rate']:>7.1f}% {r['avg_ret']:>+9.2f}% {r['losers']:>8} {r['stops']:>8}")

# Show trade examples
print("\n" + "="*70)
print("v6.0 TRADE EXAMPLES")
print("="*70)

v6_result = results[1] if len(results) > 1 else None
if v6_result:
    df = v6_result['details']

    print("\nFast Winners (+5% in 7 days):")
    winners = df[df['fast_win']].sort_values('ret_7d', ascending=False).head(8)
    for _, row in winners.iterrows():
        gap_mark = " GAP!" if row['gap'] >= 1 else ""
        print(f"  {row['sym']:<6} {row['date'].strftime('%Y-%m-%d')} → 7d: {row['ret_7d']:+.1f}%  14d: {row['ret']:+.1f}%{gap_mark}")

    print("\nLosers:")
    losers = df[~df['win']].sort_values('ret').head(8)
    for _, row in losers.iterrows():
        stop_mark = " STOP" if row['stopped'] else ""
        print(f"  {row['sym']:<6} {row['date'].strftime('%Y-%m-%d')} → 7d: {row['ret_7d']:+.1f}%  14d: {row['ret']:+.1f}%{stop_mark}")

# Summary
print("\n" + "="*70)
print("SUMMARY")
print("="*70)

if len(results) >= 2:
    baseline = results[0]
    v6 = results[1]

    print(f"""
  v5.4 → v6.0 Comparison:
  ───────────────────────
  Trades:      {baseline['trades']} → {v6['trades']}
  Win Rate:    {baseline['win_rate']:.1f}% → {v6['win_rate']:.1f}% ({v6['win_rate'] - baseline['win_rate']:+.1f}%)
  Fast Wins:   {baseline['fast_win_rate']:.1f}% → {v6['fast_win_rate']:.1f}% ({v6['fast_win_rate'] - baseline['fast_win_rate']:+.1f}%)
  Avg Return:  {baseline['avg_ret']:+.2f}% → {v6['avg_ret']:+.2f}%
  Losers:      {baseline['losers']} → {v6['losers']} ({v6['losers'] - baseline['losers']:+d})
  Stop Losses: {baseline['stops']} → {v6['stops']}
""")
