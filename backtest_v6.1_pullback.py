#!/usr/bin/env python3
"""
Backtest v6.0 vs v6.1 - ดูว่า dist_from_20d_high filter ช่วยป้องกัน DDOG problem หรือไม่
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

    # Momentum
    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    # 52-week position
    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

    # v6.1: Distance from 20d high
    high_20d = high.iloc[-20:].max()
    dist_from_20d_high = ((price - high_20d) / high_20d) * 100

    return {
        'rsi': rsi, 'above_ma20': above_ma20, 'vol_ratio': vol_ratio,
        'mom_3d': mom_3d, 'mom_20d': mom_20d, 'pos_52w': pos_52w,
        'dist_from_20d_high': dist_from_20d_high,
    }


def passes_v6(m):
    """v6.0 criteria (without dist_from_20d_high)"""
    if m is None:
        return False
    if m['above_ma20'] <= 0:
        return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85:
        return False
    if m['mom_20d'] < 8:
        return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8:
        return False
    if m['rsi'] >= 65:
        return False
    return True


def passes_v61(m):
    """v6.1 criteria (with dist_from_20d_high)"""
    if not passes_v6(m):
        return False
    # NEW: Gate 6 - ราคาต้องใกล้ 20d high (ไม่ใช่ pullback)
    if m['dist_from_20d_high'] < -5:
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

            results.append({
                'sym': sym, 'date': entry_date, 'ret': ret,
                'win': ret > 0, 'stopped': stopped,
                'dist_20d': m['dist_from_20d_high'],
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
    stops = df_res['stopped'].sum()

    return {
        'name': name,
        'trades': n,
        'wins': wins,
        'win_rate': wins / n * 100 if n > 0 else 0,
        'avg_ret': df_res['ret'].mean(),
        'losers': n - wins,
        'stops': stops,
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
print("BACKTEST: v6.0 vs v6.1 (with pullback protection)")
print("="*70)

r_v6 = backtest(data, passes_v6, "v6.0 (no pullback filter)", hold_days=14)
r_v61 = backtest(data, passes_v61, "v6.1 (dist_20d >= -5%)", hold_days=14)

# Print results
print(f"\n{'Version':<30} {'Trades':>8} {'Win%':>8} {'AvgRet':>10} {'Losers':>8}")
print("-"*70)

for r in [r_v6, r_v61]:
    if r:
        print(f"{r['name']:<30} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['avg_ret']:>+9.2f}% {r['losers']:>8}")

# Show trades that v6.1 filtered out (pullback stocks)
print("\n" + "="*70)
print("TRADES FILTERED OUT BY v6.1 (dist_from_20d_high < -5%)")
print("="*70)

if r_v6:
    v6_trades = r_v6['details']
    pullback_trades = v6_trades[v6_trades['dist_20d'] < -5]

    if len(pullback_trades) > 0:
        print(f"\nTotal filtered: {len(pullback_trades)} trades")
        pullback_losers = pullback_trades[~pullback_trades['win']]
        pullback_winners = pullback_trades[pullback_trades['win']]
        print(f"- Winners: {len(pullback_winners)} ({len(pullback_winners)/len(pullback_trades)*100:.1f}%)")
        print(f"- Losers: {len(pullback_losers)} ({len(pullback_losers)/len(pullback_trades)*100:.1f}%)")
        print(f"- Avg Return: {pullback_trades['ret'].mean():+.2f}%")

        print("\nSample pullback trades (losers):")
        print(f"{'Symbol':<8} {'Date':<12} {'Dist20d':>10} {'Return':>10}")
        print("-"*50)
        for _, row in pullback_losers.head(10).iterrows():
            print(f"{row['sym']:<8} {row['date'].strftime('%Y-%m-%d'):<12} {row['dist_20d']:>+9.1f}% {row['ret']:>+9.1f}%")

# DDOG specific check
print("\n" + "="*70)
print("DDOG SPECIFIC CHECK")
print("="*70)

if 'DDOG' in data:
    ddog = data['DDOG']
    print(f"\nDDOG trades in backtest period:")

    ddog_v6 = r_v6['details'][r_v6['details']['sym'] == 'DDOG'] if r_v6 else pd.DataFrame()
    ddog_v61 = r_v61['details'][r_v61['details']['sym'] == 'DDOG'] if r_v61 else pd.DataFrame()

    print(f"\nv6.0 DDOG trades: {len(ddog_v6)}")
    if len(ddog_v6) > 0:
        for _, row in ddog_v6.iterrows():
            status = "WIN" if row['win'] else "LOSS"
            print(f"  {row['date'].strftime('%Y-%m-%d')}: dist={row['dist_20d']:+.1f}% → {row['ret']:+.1f}% [{status}]")

    print(f"\nv6.1 DDOG trades: {len(ddog_v61)}")
    if len(ddog_v61) > 0:
        for _, row in ddog_v61.iterrows():
            status = "WIN" if row['win'] else "LOSS"
            print(f"  {row['date'].strftime('%Y-%m-%d')}: dist={row['dist_20d']:+.1f}% → {row['ret']:+.1f}% [{status}]")
    else:
        print("  (No trades - pullback trades filtered out!)")

# Summary
print("\n" + "="*70)
print("SUMMARY")
print("="*70)

if r_v6 and r_v61:
    print(f"""
  v6.0 → v6.1 Comparison:
  ───────────────────────
  Trades:      {r_v6['trades']} → {r_v61['trades']} ({r_v61['trades'] - r_v6['trades']:+d})
  Win Rate:    {r_v6['win_rate']:.1f}% → {r_v61['win_rate']:.1f}% ({r_v61['win_rate'] - r_v6['win_rate']:+.1f}%)
  Avg Return:  {r_v6['avg_ret']:+.2f}% → {r_v61['avg_ret']:+.2f}% ({r_v61['avg_ret'] - r_v6['avg_ret']:+.2f}%)
  Losers:      {r_v6['losers']} → {r_v61['losers']} ({r_v61['losers'] - r_v6['losers']:+d})

  ✓ dist_from_20d_high >= -5% ป้องกันซื้อหุ้นที่กำลังตกจาก peak
""")
