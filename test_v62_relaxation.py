#!/usr/bin/env python3
"""
Test: จะปรับ v6.2 อย่างไรให้ BABA, TXN ผ่าน โดยไม่เพิ่ม loser มาก?
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from api.data_manager import DataManager

dm = DataManager()

# LARGE UNIVERSE - 150+ stocks
STOCKS = [
    # Tech Giants
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD', 'ORCL',
    'CRM', 'ADBE', 'NOW', 'NFLX', 'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX',
    # Cloud/SaaS
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    # Fintech/Finance
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    # Healthcare
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    # Consumer
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    # Industrial
    'CAT', 'DE', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'BA', 'UPS', 'FDX',
    # Energy
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX',
    # Growth/Speculative
    'COIN', 'ROKU', 'SNAP', 'PINS', 'UBER', 'LYFT', 'ABNB', 'DASH',
    'ZM', 'DOCU', 'TWLO', 'OKTA', 'U', 'RBLX', 'PATH', 'CFLT', 'MQ',
    'BILL', 'HUBS', 'VEEV', 'WDAY', 'ESTC', 'GTLB', 'DOMO',
    # China ADR
    'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI',
    # Additional Large Caps
    'GOOG', 'BRK-B', 'XLK', 'SPY', 'QQQ', 'DIS', 'CMCSA', 'VZ', 'T',
    'PG', 'KO', 'PEP', 'PM', 'MO', 'CL', 'EL', 'MDLZ',
    # More Tech
    'IBM', 'CSCO', 'HPQ', 'DELL', 'HPE', 'KEYS', 'KLAC', 'SNPS', 'CDNS',
    # More Finance
    'SCHW', 'USB', 'PNC', 'TFC', 'COF', 'AIG', 'MET', 'PRU', 'ALL',
    # More Healthcare
    'CVS', 'CI', 'HUM', 'ELV', 'GILD', 'REGN', 'VRTX', 'BIIB', 'MRNA',
    # More Consumer
    'AMGN', 'LULU', 'ULTA', 'BBY', 'DG', 'DLTR', 'FIVE', 'ORLY', 'AZO',
    # Semiconductors
    'ON', 'MCHP', 'ADI', 'NXPI', 'SWKS', 'MPWR', 'MRVL', 'WOLF',
    # Software
    'TEAM', 'ZEN', 'SPLK', 'RNG', 'FIVN', 'PAYC', 'PCTY', 'TTD', 'APPS',
]


def get_metrics(df, idx):
    """Calculate all metrics at index"""
    if idx < 50:
        return None

    close = df['close'].iloc[:idx+1]
    high = df['high'].iloc[:idx+1]
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

    # Distance from 20d high
    high_20d = high.iloc[-20:].max()
    dist_from_20d_high = ((price - high_20d) / high_20d) * 100

    return {
        'price': price,
        'rsi': rsi,
        'above_ma20': above_ma20,
        'vol_ratio': vol_ratio,
        'mom_3d': mom_3d,
        'mom_20d': mom_20d,
        'pos_52w': pos_52w,
        'dist_from_20d_high': dist_from_20d_high,
    }


def passes_v62_strict(m):
    """v6.2 STRICT"""
    if m is None: return False
    if m['above_ma20'] <= 0: return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85: return False
    if m['mom_20d'] < 8 or m['mom_20d'] > 20: return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8: return False
    if m['rsi'] >= 65: return False
    if m['dist_from_20d_high'] < -5: return False
    if m['vol_ratio'] < 1.0: return False
    return True


def passes_v62_relaxed_rsi(m):
    """v6.2 with RSI relaxed to 70 (for TXN)"""
    if m is None: return False
    if m['above_ma20'] <= 0: return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85: return False
    if m['mom_20d'] < 8 or m['mom_20d'] > 20: return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8: return False
    if m['rsi'] >= 70: return False  # Relaxed from 65
    if m['dist_from_20d_high'] < -5: return False
    if m['vol_ratio'] < 1.0: return False
    return True


def passes_v62_relaxed_vol(m):
    """v6.2 with Volume relaxed to 0.8x (for BABA)"""
    if m is None: return False
    if m['above_ma20'] <= 0: return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85: return False
    if m['mom_20d'] < 8 or m['mom_20d'] > 20: return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8: return False
    if m['rsi'] >= 65: return False
    if m['dist_from_20d_high'] < -5: return False
    if m['vol_ratio'] < 0.8: return False  # Relaxed from 1.0
    return True


def passes_v62_both_relaxed(m):
    """v6.2 with both RSI and Volume relaxed"""
    if m is None: return False
    if m['above_ma20'] <= 0: return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85: return False
    if m['mom_20d'] < 8 or m['mom_20d'] > 20: return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8: return False
    if m['rsi'] >= 70: return False  # Relaxed
    if m['dist_from_20d_high'] < -5: return False
    if m['vol_ratio'] < 0.8: return False  # Relaxed
    return True


def backtest(data, check_func, name, hold_days=14, stop_loss=-0.06, target=0.05):
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

            # Simulate trade
            exit_reason = 'HOLD14'
            exit_price = df.iloc[min(idx + hold_days, len(df)-1)]['close']

            for i in range(1, min(hold_days + 1, len(df) - idx)):
                day_low = df.iloc[idx + i]['low']
                day_high = df.iloc[idx + i]['high']

                if (day_low - entry) / entry <= stop_loss:
                    exit_price = entry * (1 + stop_loss)
                    exit_reason = 'STOP'
                    break

                if (day_high - entry) / entry >= target:
                    exit_price = entry * (1 + target)
                    exit_reason = 'TARGET'
                    break

            ret = ((exit_price - entry) / entry) * 100

            results.append({
                'sym': sym,
                'date': entry_date,
                'ret': ret,
                'win': ret > 0,
                'exit_reason': exit_reason,
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

    return {
        'name': name,
        'trades': n,
        'wins': wins,
        'win_rate': wins / n * 100 if n > 0 else 0,
        'avg_ret': df_res['ret'].mean(),
        'losers': n - wins,
    }


# Load data
print("Loading data from LARGE universe...")
data = {}
for s in STOCKS:
    try:
        df = dm.get_price_data(s, period="1y", interval="1d")
        if df is not None and len(df) >= 200:
            data[s] = df
    except:
        pass

print(f"Loaded {len(data)} stocks\n")

# Run backtests
print("="*80)
print("TESTING v6.2 RELAXATION OPTIONS")
print("="*80)

tests = [
    (passes_v62_strict, "v6.2 STRICT (RSI<65, Vol>=1.0x)"),
    (passes_v62_relaxed_rsi, "v6.2 RSI<70 (for TXN)"),
    (passes_v62_relaxed_vol, "v6.2 Vol>=0.8x (for BABA)"),
    (passes_v62_both_relaxed, "v6.2 BOTH RELAXED (RSI<70, Vol>=0.8x)"),
]

results = []
for check_func, name in tests:
    r = backtest(data, check_func, name)
    if r:
        results.append(r)

print(f"\n{'Version':<45} {'Trades':>8} {'Win%':>8} {'Losers':>8} {'AvgRet':>10}")
print("-"*85)

baseline = results[0] if results else None
for r in results:
    loser_diff = ""
    if baseline and r['name'] != baseline['name']:
        diff = r['losers'] - baseline['losers']
        loser_diff = f" ({diff:+d})"
    print(f"{r['name']:<45} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['losers']:>8}{loser_diff} {r['avg_ret']:>+9.2f}%")

# Analysis
print("\n" + "="*80)
print("ANALYSIS: WHICH RELAXATION IS SAFE?")
print("="*80)

if len(results) >= 4:
    strict = results[0]
    rsi_relax = results[1]
    vol_relax = results[2]
    both_relax = results[3]

    print(f"""
1. RSI Relaxation (65 → 70):
   - Trades: {strict['trades']} → {rsi_relax['trades']} (+{rsi_relax['trades'] - strict['trades']})
   - Losers: {strict['losers']} → {rsi_relax['losers']} ({rsi_relax['losers'] - strict['losers']:+d})
   - Win Rate: {strict['win_rate']:.1f}% → {rsi_relax['win_rate']:.1f}% ({rsi_relax['win_rate'] - strict['win_rate']:+.1f}%)
   → {'✓ SAFE' if rsi_relax['losers'] <= strict['losers'] + 2 and rsi_relax['win_rate'] >= 70 else '⚠️ CAUTION'}

2. Volume Relaxation (1.0x → 0.8x):
   - Trades: {strict['trades']} → {vol_relax['trades']} (+{vol_relax['trades'] - strict['trades']})
   - Losers: {strict['losers']} → {vol_relax['losers']} ({vol_relax['losers'] - strict['losers']:+d})
   - Win Rate: {strict['win_rate']:.1f}% → {vol_relax['win_rate']:.1f}% ({vol_relax['win_rate'] - strict['win_rate']:+.1f}%)
   → {'✓ SAFE' if vol_relax['losers'] <= strict['losers'] + 2 and vol_relax['win_rate'] >= 70 else '⚠️ CAUTION'}

3. Both Relaxed:
   - Trades: {strict['trades']} → {both_relax['trades']} (+{both_relax['trades'] - strict['trades']})
   - Losers: {strict['losers']} → {both_relax['losers']} ({both_relax['losers'] - strict['losers']:+d})
   - Win Rate: {strict['win_rate']:.1f}% → {both_relax['win_rate']:.1f}% ({both_relax['win_rate'] - strict['win_rate']:+.1f}%)
   → {'✓ SAFE' if both_relax['losers'] <= strict['losers'] + 3 and both_relax['win_rate'] >= 70 else '⚠️ CAUTION'}
""")

    # Recommendation
    print("="*80)
    print("RECOMMENDATION")
    print("="*80)

    best = strict
    for r in [rsi_relax, vol_relax, both_relax]:
        if r['win_rate'] >= 72 and r['losers'] <= strict['losers'] + 3:
            if r['trades'] > best['trades']:
                best = r

    if best == strict:
        print("\n→ Keep v6.2 STRICT - relaxation increases losers too much")
    else:
        print(f"\n→ Use {best['name']}")
        print(f"   More trades ({best['trades']} vs {strict['trades']})")
        print(f"   Acceptable losers ({best['losers']} vs {strict['losers']})")
        print(f"   Good win rate ({best['win_rate']:.1f}%)")
