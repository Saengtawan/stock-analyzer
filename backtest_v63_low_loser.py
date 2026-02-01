#!/usr/bin/env python3
"""
v6.3 LOW LOSER - Based on root cause analysis

New discoveries:
1. ATR (volatility): Losers have higher ATR → Filter ATR <= 3%
2. Days above MA20: Winners more consistent → Filter >= 8 days
3. Mom 3d: Losers rush too fast → Filter <= 5%

v6.3 adds:
- ATR <= 3% (low volatility = fewer crashes)
- Days above MA20 >= 8 (trend consistency)
- Mom 3d <= 5% (not rushing)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from api.data_manager import DataManager

dm = DataManager()

# HUGE UNIVERSE
STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD',
    'ORCL', 'CRM', 'ADBE', 'NOW', 'IBM', 'CSCO', 'ACN', 'INTU', 'UBER',
    'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'NXPI', 'MCHP', 'ADI',
    'ON', 'SWKS', 'MPWR', 'MRVL', 'SNPS', 'CDNS',
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    'ZM', 'DOCU', 'TWLO', 'OKTA', 'TEAM', 'SPLK', 'WDAY', 'VEEV', 'HUBS', 'BILL',
    'NFLX', 'DIS', 'CMCSA', 'ROKU', 'SPOT',
    'SNAP', 'PINS', 'RBLX', 'EA', 'TTWO',
    'EBAY', 'ETSY', 'MELI',
    'V', 'MA', 'AXP', 'COIN', 'AFRM', 'SOFI',
    'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC', 'USB', 'PNC', 'TFC', 'SCHW',
    'BRK-B', 'MET', 'PRU', 'TRV', 'PGR',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'CVS', 'CI', 'HUM', 'GILD', 'REGN', 'VRTX', 'BIIB', 'MRNA', 'AMGN',
    'BMY', 'ZTS', 'SYK', 'BSX', 'MDT', 'EW', 'DXCM', 'IDXX',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'DG', 'DLTR', 'BBY',
    'LULU', 'ULTA', 'NKE', 'ORLY', 'AZO',
    'SBUX', 'MCD', 'CMG', 'DPZ', 'YUM',
    'KO', 'PEP', 'MNST',
    'PG', 'CL', 'KMB', 'EL',
    'CAT', 'DE', 'HON', 'GE', 'MMM', 'EMR', 'ETN', 'ITW',
    'RTX', 'LMT', 'NOC', 'BA', 'GD',
    'UPS', 'FDX',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX',
    'DVN', 'FANG', 'HES', 'MRO',
    'NEE', 'DUK', 'SO', 'D', 'AEP',
    'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'O', 'DLR',
    'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI',
    'ABNB', 'BKNG', 'EXPE', 'MAR', 'HLT',
    'F', 'GM', 'RIVN',
    'VZ', 'T', 'TMUS',
    'LIN', 'APD', 'SHW', 'ECL', 'NEM', 'FCX',
    'PATH', 'CFLT', 'GTLB', 'ESTC', 'DASH', 'LYFT', 'TTD',
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
    above_ma20 = ((price - ma20) / ma20) * 100

    # Volume
    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1

    # Momentum
    mom_3d = ((price / close.iloc[-4]) - 1) * 100
    mom_20d = ((price / close.iloc[-21]) - 1) * 100

    # 52w position
    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100

    # 20d position
    high_20d = high.iloc[-20:].max()
    low_20d = low.iloc[-20:].min()
    dist_from_20d_high = ((price - high_20d) / high_20d) * 100
    pos_20d = ((price - low_20d) / (high_20d - low_20d)) * 100 if high_20d > low_20d else 50

    # ATR
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    atr_pct = (atr / price) * 100

    # Days above MA20
    ma20_series = close.rolling(20).mean()
    days_above_ma20 = (close.iloc[-10:] > ma20_series.iloc[-10:]).sum()

    return {
        'price': price, 'rsi': rsi, 'above_ma20': above_ma20,
        'vol_ratio': vol_ratio, 'mom_3d': mom_3d, 'mom_20d': mom_20d,
        'pos_52w': pos_52w, 'dist_from_20d_high': dist_from_20d_high,
        'pos_20d': pos_20d, 'atr_pct': atr_pct, 'days_above_ma20': days_above_ma20,
    }


def passes_v62_balanced(m):
    """v6.2 BALANCED"""
    if m is None: return False
    if m['above_ma20'] <= 0: return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85: return False
    if m['mom_20d'] < 8 or m['mom_20d'] > 20: return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8: return False
    if m['rsi'] >= 68: return False
    if m['dist_from_20d_high'] < -5: return False
    if m['vol_ratio'] < 0.9: return False
    return True


def passes_v63_low_loser(m):
    """v6.3 LOW LOSER - adds ATR, days_above_ma20, tighter mom_3d"""
    if m is None: return False

    # Base v6.2 gates
    if m['above_ma20'] <= 0: return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85: return False
    if m['mom_20d'] < 8 or m['mom_20d'] > 20: return False
    if m['rsi'] >= 68: return False
    if m['dist_from_20d_high'] < -5: return False
    if m['vol_ratio'] < 0.9: return False

    # v6.3 NEW: Tighter Mom 3d (was 1-8%, now 1-5%)
    if m['mom_3d'] < 1 or m['mom_3d'] > 5: return False

    # v6.3 NEW: Low volatility (ATR <= 3%)
    if m['atr_pct'] > 3: return False

    # v6.3 NEW: Trend consistency (8+ days above MA20)
    if m['days_above_ma20'] < 8: return False

    return True


def passes_v63_ultra_strict(m):
    """v6.3 ULTRA STRICT - near zero losers"""
    if m is None: return False

    # All v6.3 gates
    if m['above_ma20'] <= 0: return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85: return False
    if m['mom_20d'] < 8 or m['mom_20d'] > 15: return False  # Tighter: was 20
    if m['mom_3d'] < 1 or m['mom_3d'] > 5: return False
    if m['rsi'] >= 65: return False  # Tighter: was 68
    if m['dist_from_20d_high'] < -3: return False  # Tighter: was -5
    if m['vol_ratio'] < 1.0: return False  # Tighter: was 0.9

    # v6.3 ULTRA: Very low volatility
    if m['atr_pct'] > 2.5: return False

    # v6.3 ULTRA: Strong trend consistency
    if m['days_above_ma20'] < 9: return False

    return True


def backtest(data, check_func, name, capital=200000, per_trade=50000):
    results = []

    for sym, df in data.items():
        for days_back in range(30, 180, 2):
            idx = len(df) - 1 - days_back
            if idx < 60 or idx + 14 >= len(df):
                continue

            m = get_metrics(df, idx)
            if not check_func(m):
                continue

            entry = df.iloc[idx]['close']
            entry_date = pd.to_datetime(df.iloc[idx]['date'])

            exit_reason = 'HOLD14'
            exit_price = df.iloc[min(idx + 14, len(df)-1)]['close']

            for i in range(1, min(15, len(df) - idx)):
                if (df.iloc[idx + i]['low'] - entry) / entry <= -0.06:
                    exit_price = entry * 0.94
                    exit_reason = 'STOP'
                    break
                if (df.iloc[idx + i]['high'] - entry) / entry >= 0.05:
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
        'monthly_profit': total_profit / 6,
        'avg_ret': df_res['ret'].mean(),
    }


# Load
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

# Test
print("="*90)
print("v6.2 vs v6.3 COMPARISON")
print("="*90)

versions = [
    (passes_v62_balanced, "v6.2 BALANCED"),
    (passes_v63_low_loser, "v6.3 LOW LOSER (ATR<=3%, 8d>MA20, Mom3d<=5%)"),
    (passes_v63_ultra_strict, "v6.3 ULTRA STRICT (ATR<=2.5%, 9d>MA20)"),
]

results = []
for func, name in versions:
    r = backtest(data, func, name)
    if r:
        results.append(r)

print(f"\n{'Version':<55} {'Trades':>8} {'Win%':>8} {'Losers':>8} {'MonthlyProfit':>15}")
print("-"*100)

for r in results:
    print(f"{r['name']:<55} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['losers']:>8} {r['monthly_profit']:>+14,.0f} บาท")

# Summary
print("\n" + "="*90)
print("SUMMARY: WHICH VERSION TO USE?")
print("="*90)

if len(results) >= 3:
    v62, v63, v63u = results[0], results[1], results[2]

    print(f"""
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ VERSION COMPARISON                                                                       │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                           v6.2 BALANCED    v6.3 LOW LOSER    v6.3 ULTRA STRICT          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ Trades (6 months)              {v62['trades']:<15} {v63['trades']:<17} {v63u['trades']:<15} │
│ Win Rate                       {v62['win_rate']:.1f}%{'':<11} {v63['win_rate']:.1f}%{'':<13} {v63u['win_rate']:.1f}%{'':<11} │
│ Losers                         {v62['losers']:<15} {v63['losers']:<17} {v63u['losers']:<15} │
│ Monthly Profit                 {v62['monthly_profit']:>+,.0f} บาท{'':<3} {v63['monthly_profit']:>+,.0f} บาท{'':<5} {v63u['monthly_profit']:>+,.0f} บาท{'':<3} │
└─────────────────────────────────────────────────────────────────────────────────────────┘

RECOMMENDATION:
""")

    # Choose best
    if v63['losers'] <= 10 and v63['win_rate'] >= 70 and v63['monthly_profit'] > v62['monthly_profit'] * 0.8:
        print(f"""
  → USE v6.3 LOW LOSER
    - Losers ลดลง: {v62['losers']} → {v63['losers']} ({v62['losers'] - v63['losers']:+d})
    - Win Rate: {v62['win_rate']:.1f}% → {v63['win_rate']:.1f}%
    - ยังมี trades เพียงพอ ({v63['trades']} ใน 6 เดือน = ~{v63['trades']/6:.0f}/เดือน)

  NEW FILTERS ADDED:
    + ATR <= 3% (low volatility = fewer crashes)
    + Days above MA20 >= 8 (trend consistency)
    + Mom 3d <= 5% (not rushing too fast)
""")
    elif v63u['losers'] <= 5 and v63u['trades'] >= 15:
        print(f"""
  → USE v6.3 ULTRA STRICT (if you want NEAR ZERO losers)
    - Losers: {v63u['losers']} only!
    - Win Rate: {v63u['win_rate']:.1f}%
    - Trades: {v63u['trades']} (selective but quality)
""")
    else:
        print(f"""
  → KEEP v6.2 BALANCED
    - v6.3 ลด trades มากเกินไป
    - v6.2 balance ดีกว่า
""")
