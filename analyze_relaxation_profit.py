#!/usr/bin/env python3
"""
Final analysis: Which version gives best PROFIT?
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
    'COIN', 'ROKU', 'SNAP', 'PINS', 'UBER', 'LYFT', 'ABNB', 'DASH',
    'ZM', 'DOCU', 'TWLO', 'OKTA', 'U', 'RBLX', 'PATH', 'CFLT', 'MQ',
    'BILL', 'HUBS', 'VEEV', 'WDAY', 'ESTC', 'GTLB', 'DOMO',
    'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI',
    'GOOG', 'DIS', 'CMCSA', 'VZ', 'T', 'PG', 'KO', 'PEP',
    'IBM', 'CSCO', 'HPQ', 'DELL', 'KEYS', 'KLAC', 'SNPS', 'CDNS',
    'SCHW', 'USB', 'PNC', 'TFC', 'COF', 'MET', 'PRU',
    'CVS', 'CI', 'HUM', 'GILD', 'REGN', 'VRTX', 'BIIB', 'MRNA',
    'LULU', 'ULTA', 'BBY', 'DG', 'DLTR', 'ORLY', 'AZO',
    'ON', 'MCHP', 'ADI', 'NXPI', 'SWKS', 'MPWR', 'MRVL',
    'TEAM', 'SPLK', 'RNG', 'PAYC', 'TTD',
]


def get_metrics(df, idx):
    if idx < 50:
        return None
    close = df['close'].iloc[:idx+1]
    high = df['high'].iloc[:idx+1]
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

    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

    high_20d = high.iloc[-20:].max()
    dist_from_20d_high = ((price - high_20d) / high_20d) * 100

    return {
        'rsi': rsi, 'above_ma20': above_ma20, 'vol_ratio': vol_ratio,
        'mom_3d': mom_3d, 'mom_20d': mom_20d, 'pos_52w': pos_52w,
        'dist_from_20d_high': dist_from_20d_high,
    }


def passes_v62_strict(m):
    if m is None: return False
    if m['above_ma20'] <= 0: return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85: return False
    if m['mom_20d'] < 8 or m['mom_20d'] > 20: return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8: return False
    if m['rsi'] >= 65: return False
    if m['dist_from_20d_high'] < -5: return False
    if m['vol_ratio'] < 1.0: return False
    return True


def passes_v62_balanced(m):
    """v6.2 BALANCED - slight relaxation"""
    if m is None: return False
    if m['above_ma20'] <= 0: return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85: return False
    if m['mom_20d'] < 8 or m['mom_20d'] > 20: return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8: return False
    if m['rsi'] >= 68: return False  # Slightly relaxed from 65
    if m['dist_from_20d_high'] < -5: return False
    if m['vol_ratio'] < 0.9: return False  # Slightly relaxed from 1.0
    return True


def backtest_with_portfolio(data, check_func, name, capital=200000, per_trade=50000):
    """Simulate actual portfolio trading"""
    results = []

    for sym, df in data.items():
        for days_back in range(30, 180, 2):
            idx = len(df) - 1 - days_back
            if idx < 50 or idx + 14 >= len(df):
                continue

            m = get_metrics(df, idx)
            if not check_func(m):
                continue

            entry = df.iloc[idx]['close']
            entry_date = pd.to_datetime(df.iloc[idx]['date'])

            exit_reason = 'HOLD14'
            exit_price = df.iloc[min(idx + 14, len(df)-1)]['close']

            for i in range(1, min(15, len(df) - idx)):
                day_low = df.iloc[idx + i]['low']
                day_high = df.iloc[idx + i]['high']

                if (day_low - entry) / entry <= -0.06:
                    exit_price = entry * 0.94
                    exit_reason = 'STOP'
                    break

                if (day_high - entry) / entry >= 0.05:
                    exit_price = entry * 1.05
                    exit_reason = 'TARGET'
                    break

            ret = ((exit_price - entry) / entry) * 100
            profit = per_trade * (ret / 100)

            results.append({
                'sym': sym, 'date': entry_date, 'ret': ret,
                'profit': profit, 'win': ret > 0, 'exit_reason': exit_reason,
            })

    if not results:
        return None

    df_res = pd.DataFrame(results)
    df_res = df_res.sort_values(['sym', 'date'])
    df_res['diff'] = df_res.groupby('sym')['date'].diff().dt.days
    df_res = df_res[(df_res['diff'].isna()) | (df_res['diff'] > 10)]

    n = len(df_res)
    wins = df_res['win'].sum()
    total_profit = df_res['profit'].sum()

    return {
        'name': name,
        'trades': n,
        'wins': wins,
        'losers': n - wins,
        'win_rate': wins / n * 100 if n > 0 else 0,
        'total_profit': total_profit,
        'avg_profit': total_profit / n if n > 0 else 0,
        'monthly_profit': total_profit / 6,  # 6 months
        'monthly_roi': (total_profit / 6) / capital * 100,
    }


# Load data
print("Loading data...")
data = {}
for s in STOCKS:
    try:
        df = dm.get_price_data(s, period="1y", interval="1d")
        if df is not None and len(df) >= 200:
            data[s] = df
    except:
        pass

print(f"Loaded {len(data)} stocks\n")

# Run
print("="*80)
print("v6.2 PROFIT COMPARISON (200,000 บาท, 50,000/trade)")
print("="*80)

strict = backtest_with_portfolio(data, passes_v62_strict, "v6.2 STRICT")
balanced = backtest_with_portfolio(data, passes_v62_balanced, "v6.2 BALANCED (RSI<68, Vol>=0.9x)")

print(f"\n{'Version':<45} {'Trades':>8} {'Win%':>8} {'Losers':>8} {'Total Profit':>15}")
print("-"*90)

for r in [strict, balanced]:
    if r:
        print(f"{r['name']:<45} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['losers']:>8} {r['total_profit']:>+14,.0f} บาท")

print("\n" + "="*80)
print("MONTHLY BREAKDOWN")
print("="*80)

for r in [strict, balanced]:
    if r:
        print(f"""
{r['name']}:
  - Trades: {r['trades']} (6 เดือน) = ~{r['trades']/6:.1f}/เดือน
  - Win Rate: {r['win_rate']:.1f}%
  - Losers: {r['losers']} total = ~{r['losers']/6:.1f}/เดือน
  - Monthly Profit: {r['monthly_profit']:+,.0f} บาท
  - Monthly ROI: {r['monthly_roi']:+.2f}%
""")

print("="*80)
print("CONCLUSION")
print("="*80)

if strict and balanced:
    print(f"""
STRICT vs BALANCED:
  Trades:         {strict['trades']} → {balanced['trades']} ({balanced['trades'] - strict['trades']:+d})
  Win Rate:       {strict['win_rate']:.1f}% → {balanced['win_rate']:.1f}% ({balanced['win_rate'] - strict['win_rate']:+.1f}%)
  Losers:         {strict['losers']} → {balanced['losers']} ({balanced['losers'] - strict['losers']:+d})
  Monthly Profit: {strict['monthly_profit']:+,.0f} → {balanced['monthly_profit']:+,.0f} บาท

RECOMMENDATION:
""")
    if balanced['monthly_profit'] > strict['monthly_profit'] and balanced['win_rate'] >= 65:
        print(f"  → ใช้ v6.2 BALANCED (RSI<68, Vol>=0.9x)")
        print(f"     ได้กำไรมากกว่า {balanced['monthly_profit'] - strict['monthly_profit']:,.0f} บาท/เดือน")
        print(f"     Loser เพิ่มแค่ {balanced['losers'] - strict['losers']} ตัว")
    else:
        print(f"  → ใช้ v6.2 STRICT")
        print(f"     Loser น้อยกว่า")
