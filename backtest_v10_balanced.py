#!/usr/bin/env python3
"""
Backtest v10 BALANCED - More trades while keeping low losers

Entry score: 75 (between v9's 55 and strict's 80)
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

WORKING_UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD',
    'ORCL', 'CRM', 'ADBE', 'NOW', 'IBM', 'CSCO', 'ACN', 'INTU', 'UBER', 'QCOM',
    'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'NXPI', 'MCHP', 'ADI', 'INTC', 'ON',
    'MRVL', 'SNPS', 'CDNS', 'ASML', 'TSM', 'ARM', 'SMCI',
    'PANW', 'CRWD', 'ZS', 'NET', 'DDOG', 'SNOW', 'MDB', 'PLTR', 'SHOP', 'WDAY',
    'VEEV', 'HUBS', 'TTD', 'ZM', 'DOCU', 'TEAM', 'OKTA', 'FTNT',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'USB', 'PNC', 'SCHW', 'COIN', 'AFRM', 'SOFI', 'HOOD', 'PYPL',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'CVS', 'GILD', 'REGN', 'VRTX', 'MRNA', 'AMGN', 'BMY', 'DXCM',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    'CMG', 'LULU', 'DECK', 'CROX', 'RH', 'ULTA',
    'CAT', 'DE', 'HON', 'GE', 'BA', 'RTX', 'LMT', 'NOC', 'UPS', 'FDX',
    'WM', 'URI', 'PWR', 'EMR', 'ETN',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX', 'DVN',
    'NFLX', 'DIS', 'CMCSA', 'T', 'VZ', 'TMUS',
    'RIVN', 'LCID', 'F', 'GM', 'APTV',
    'ABNB', 'BKNG', 'EXPE', 'MAR', 'HLT', 'RCL', 'CCL', 'UAL', 'DAL', 'LUV',
    'DKNG', 'MGM', 'LVS', 'WYNN',
    'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'DLR', 'SPG', 'O',
    'ENPH', 'SEDG', 'FSLR', 'PLUG', 'BE',
    'AXON', 'CAVA', 'DUOL', 'TOST', 'HIMS', 'IONQ', 'APP', 'RKLB',
    'FCX', 'NEM', 'NUE', 'STLD', 'CLF', 'AA',
]


def download_data(symbol, start, end):
    try:
        df = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=True)
        if df.empty or len(df) < 20:
            return None
        df.index = df.index.tz_localize(None)
        return df
    except:
        return None


def calc_metrics(df, idx):
    if idx < 25:
        return None
    close = df.iloc[idx]['Close']
    ma20 = df['Close'].iloc[idx-20:idx].mean()
    ma20_pct = ((close - ma20) / ma20) * 100
    lookback = min(252, idx)
    high_52w = df['High'].iloc[idx-lookback:idx].max()
    low_52w = df['Low'].iloc[idx-lookback:idx].min()
    pos_52w = ((close - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50
    mom_20d = ((close - df['Close'].iloc[idx-20]) / df['Close'].iloc[idx-20]) * 100
    mom_3d = ((close - df['Close'].iloc[idx-3]) / df['Close'].iloc[idx-3]) * 100
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain/loss))
    rsi_14 = rsi.iloc[idx] if not pd.isna(rsi.iloc[idx]) else 50
    tr = pd.DataFrame({
        'hl': df['High'] - df['Low'],
        'hc': abs(df['High'] - df['Close'].shift(1)),
        'lc': abs(df['Low'] - df['Close'].shift(1))
    }).max(axis=1)
    atr_pct = (tr.rolling(14).mean().iloc[idx] / close) * 100
    vol_20 = df['Volume'].iloc[idx-20:idx].mean()
    vol_ratio = df['Volume'].iloc[idx] / vol_20 if vol_20 > 0 else 1
    high_20d = df['High'].iloc[idx-20:idx].max()
    dist_high = ((close - high_20d) / high_20d) * 100
    return {
        'close': close, 'ma20_pct': ma20_pct, 'pos_52w': pos_52w,
        'mom_20d': mom_20d, 'mom_3d': mom_3d, 'rsi': rsi_14,
        'atr_pct': atr_pct, 'vol_ratio': vol_ratio, 'dist_high': dist_high
    }


def passes_gates(m):
    """Balanced gates"""
    if m['ma20_pct'] < -5: return False
    if not (35 <= m['pos_52w'] <= 90): return False
    if m['mom_20d'] < -5 or m['mom_20d'] > 30: return False
    if m['mom_3d'] < -4: return False
    if not (38 <= m['rsi'] <= 68): return False
    if m['atr_pct'] > 3.8: return False
    if m['vol_ratio'] < 0.55: return False
    return True


def calc_score(m):
    # Momentum 35%
    if 8 <= m['mom_20d'] <= 18:
        mom = 100
    elif 3 <= m['mom_20d'] <= 25:
        mom = 75
    else:
        mom = max(0, 50 - abs(m['mom_20d'] - 13) * 2)
    # RSI 30%
    rsi_s = 100 - abs(m['rsi'] - 53) * 2
    # Position 20%
    pos_s = 100 - abs(m['pos_52w'] - 65) * 1.2
    # Near high 15%
    high_s = 100 + m['dist_high'] * 8
    return mom * 0.35 + rsi_s * 0.30 + pos_s * 0.20 + high_s * 0.15


def sim_trade(df, idx, target=10, stop=8, maxhold=30):
    entry = df.iloc[idx]['Close']
    tp = entry * (1 + target/100)
    sl = entry * (1 - stop/100)
    for i in range(1, min(maxhold+1, len(df)-idx)):
        cidx = idx + i
        if cidx >= len(df): break
        h, l = df.iloc[cidx]['High'], df.iloc[cidx]['Low']
        if l <= sl:
            return {'ret': -stop, 'days': i, 'exit': 'STOP'}
        if h >= tp:
            return {'ret': target, 'days': i, 'exit': 'TARGET'}
    fidx = min(idx + maxhold, len(df)-1)
    ret = ((df.iloc[fidx]['Close'] - entry) / entry) * 100
    return {'ret': ret, 'days': fidx-idx, 'exit': 'MAX_HOLD'}


def run():
    print("=" * 70)
    print("BACKTEST v10 BALANCED")
    print("Entry score >= 75, Stop -8%, Target +10%")
    print("=" * 70)

    print("\n📥 Downloading...")
    data = {}
    for s in WORKING_UNIVERSE:
        df = download_data(s, '2025-07-01', '2026-01-30')
        if df is not None and len(df) >= 50:
            data[s] = df
    print(f"✅ {len(data)} stocks")

    dates = pd.date_range('2025-10-01', '2026-01-25', freq='W-MON')
    trades = []
    recent = {}

    for d in dates:
        cutoff = d - timedelta(days=14)
        recent = {k: v for k, v in recent.items() if v > cutoff}

        cands = []
        for s, df in data.items():
            if s in recent: continue
            try:
                if d not in df.index:
                    vd = df.index[df.index <= d]
                    if len(vd) == 0: continue
                    idx = df.index.get_loc(vd[-1])
                else:
                    idx = df.index.get_loc(d)
                if idx < 25: continue
                m = calc_metrics(df, idx)
                if m and passes_gates(m):
                    score = calc_score(m)
                    if score >= 75:
                        cands.append({'s': s, 'score': score, 'idx': idx, **m})
            except: continue

        if not cands: continue
        cands.sort(key=lambda x: x['score'], reverse=True)
        sel = cands[:5]
        sel_str = [f"{c['s']}({c['score']:.0f})" for c in sel]
        print(f"{d.strftime('%Y-%m-%d')}: {len(cands)} passed, sel: {sel_str}")

        for c in sel:
            t = sim_trade(data[c['s']], c['idx'])
            trades.append({
                'symbol': c['s'], 'score': c['score'],
                'mom': c['mom_20d'], 'rsi': c['rsi'],
                **t
            })
            recent[c['s']] = d

    print("\n" + "=" * 70)
    print("📊 RESULTS")
    print("=" * 70)

    if not trades:
        print("No trades!")
        return

    df = pd.DataFrame(trades)
    total = len(df)
    win = df[df['ret'] > 0]
    lose = df[df['ret'] <= 0]
    wr = len(win)/total*100

    print(f"\n🎯 STATISTICS:")
    print(f"   Trades: {total}")
    print(f"   Winners: {len(win)} ({wr:.1f}%)")
    print(f"   Losers: {len(lose)} ({100-wr:.1f}%)")

    print(f"\n💰 RETURNS:")
    print(f"   Avg: {df['ret'].mean():.2f}%")
    print(f"   Avg winner: +{win['ret'].mean():.2f}%")
    print(f"   Avg loser: {lose['ret'].mean():.2f}%")
    print(f"   Best: +{df['ret'].max():.2f}%")
    print(f"   Worst: {df['ret'].min():.2f}%")

    print(f"\n🚪 EXITS:")
    for ex in df['exit'].unique():
        sub = df[df['exit'] == ex]
        print(f"   {ex}: {len(sub)} ({len(sub)/total*100:.1f}%) avg: {sub['ret'].mean():+.1f}%")

    print(f"\n❌ LOSERS:")
    big = len(lose[lose['ret'] <= -8])
    med = len(lose[(lose['ret'] > -8) & (lose['ret'] <= -4)])
    small = len(lose[lose['ret'] > -4])
    print(f"   Big (≤-8%): {big} ({big/total*100:.1f}%)")
    print(f"   Med (-8% to -4%): {med} ({med/total*100:.1f}%)")
    print(f"   Small (>-4%): {small} ({small/total*100:.1f}%)")

    gross_p = win['ret'].sum() if len(win) > 0 else 0
    gross_l = abs(lose['ret'].sum()) if len(lose) > 0 else 1
    pf = gross_p / gross_l if gross_l > 0 else 0

    print(f"\n📈 PERFORMANCE:")
    print(f"   Total Return: {df['ret'].sum():+.1f}%")
    print(f"   Profit Factor: {pf:.2f}")

    print(f"\n📊 COMPARISON:")
    print(f"   v9:       80 trades, 62.5% WR, 37.5% losers, PF 2.34")
    print(f"   v10-str:  35 trades, 74.3% WR, 25.7% losers, PF 3.17")
    print(f"   v10-bal:  {total} trades, {wr:.1f}% WR, {100-wr:.1f}% losers, PF {pf:.2f}")

    return df


if __name__ == "__main__":
    run()
