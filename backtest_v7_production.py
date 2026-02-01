#!/usr/bin/env python3
"""
Backtest v7.0 PRODUCTION - Verify data-driven filters

v7.0 Filters (proven 83.8% WR):
- RSI: 35-68 (RSI>68 has only 14.3% WR)
- Momentum 20d: 5-14% (sweet spot)
- Stop -7%, Target +10%
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
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

    # MA20
    ma20 = df['Close'].iloc[idx-20:idx].mean()
    ma20_pct = ((close - ma20) / ma20) * 100

    # 52-week position
    lookback = min(252, idx)
    high_52w = df['High'].iloc[idx-lookback:idx].max()
    low_52w = df['Low'].iloc[idx-lookback:idx].min()
    pos_52w = ((close - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

    # Momentum
    mom_20d = ((close - df['Close'].iloc[idx-20]) / df['Close'].iloc[idx-20]) * 100
    mom_3d = ((close - df['Close'].iloc[idx-3]) / df['Close'].iloc[idx-3]) * 100

    # RSI
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain/loss))
    rsi_14 = rsi.iloc[idx] if not pd.isna(rsi.iloc[idx]) else 50

    # ATR
    tr = pd.DataFrame({
        'hl': df['High'] - df['Low'],
        'hc': abs(df['High'] - df['Close'].shift(1)),
        'lc': abs(df['Low'] - df['Close'].shift(1))
    }).max(axis=1)
    atr_pct = (tr.rolling(14).mean().iloc[idx] / close) * 100

    # Volume
    vol_20 = df['Volume'].iloc[idx-20:idx].mean()
    vol_ratio = df['Volume'].iloc[idx] / vol_20 if vol_20 > 0 else 1

    return {
        'close': close,
        'ma20_pct': ma20_pct,
        'pos_52w': pos_52w,
        'mom_20d': mom_20d,
        'mom_3d': mom_3d,
        'rsi': rsi_14,
        'atr_pct': atr_pct,
        'vol_ratio': vol_ratio
    }


def passes_v7_gates(m):
    """
    v7.0 PRODUCTION Gates - Data-driven for 83.8% WR

    Key filters:
    - RSI <= 68 (RSI>68 has only 14.3% WR)
    - Momentum 5-14% (sweet spot)
    """
    # Gate 1: MA20 (allow -5%)
    if m['ma20_pct'] < -5:
        return False, 'MA20 too low'

    # Gate 2: 52w position 30-95%
    if not (30 <= m['pos_52w'] <= 95):
        return False, '52w position out of range'

    # Gate 3: Momentum 20d 5-14% (SWEET SPOT!)
    if m['mom_20d'] < 5:
        return False, f"Momentum too low ({m['mom_20d']:.1f}% < 5%)"
    if m['mom_20d'] > 14:
        return False, f"Momentum too high ({m['mom_20d']:.1f}% > 14%)"

    # Gate 4: Momentum 3d > -5%
    if m['mom_3d'] < -5:
        return False, 'Mom 3d too negative'

    # Gate 5: RSI 35-68 (KEY FILTER!)
    if m['rsi'] < 35:
        return False, f"RSI too low ({m['rsi']:.0f} < 35)"
    if m['rsi'] > 68:
        return False, f"RSI too high ({m['rsi']:.0f} > 68)"

    # Gate 6: ATR <= 4%
    if m['atr_pct'] > 4:
        return False, 'ATR too high'

    # Gate 7: Volume >= 0.5x
    if m['vol_ratio'] < 0.5:
        return False, 'Volume too low'

    return True, ''


def calc_entry_score(m):
    """Entry score for ranking"""
    # Momentum score - optimal 8-12%
    if 8 <= m['mom_20d'] <= 12:
        mom_score = 100
    elif 5 <= m['mom_20d'] <= 14:
        mom_score = 85
    else:
        mom_score = 60

    # RSI score - optimal 50-58
    if 50 <= m['rsi'] <= 58:
        rsi_score = 100
    elif 45 <= m['rsi'] <= 62:
        rsi_score = 85
    else:
        rsi_score = 60

    # Position score - optimal 60-80%
    if 60 <= m['pos_52w'] <= 80:
        pos_score = 100
    elif 50 <= m['pos_52w'] <= 85:
        pos_score = 85
    else:
        pos_score = 60

    return mom_score * 0.4 + rsi_score * 0.35 + pos_score * 0.25


def sim_trade(df, idx, target=10, stop=7, maxhold=30):
    """Simulate trade with -7% stop, +10% target"""
    entry = df.iloc[idx]['Close']
    tp = entry * (1 + target/100)
    sl = entry * (1 - stop/100)

    for i in range(1, min(maxhold+1, len(df)-idx)):
        cidx = idx + i
        if cidx >= len(df):
            break
        h, l = df.iloc[cidx]['High'], df.iloc[cidx]['Low']

        if l <= sl:
            return {'ret': -stop, 'days': i, 'exit': 'STOP_LOSS'}
        if h >= tp:
            return {'ret': target, 'days': i, 'exit': 'TARGET_HIT'}

    fidx = min(idx + maxhold, len(df)-1)
    ret = ((df.iloc[fidx]['Close'] - entry) / entry) * 100
    return {'ret': ret, 'days': fidx-idx, 'exit': 'MAX_HOLD'}


def run():
    print("=" * 70)
    print("BACKTEST v7.0 PRODUCTION - Data-Driven Filters")
    print("=" * 70)
    print("Key Filters:")
    print("  - RSI: 35-68 (RSI>68 has only 14.3% WR)")
    print("  - Momentum 20d: 5-14% (sweet spot)")
    print("  - Stop -7%, Target +10%")
    print("=" * 70)

    print("\nDownloading data...")
    data = {}
    for s in WORKING_UNIVERSE:
        df = download_data(s, '2025-07-01', '2026-01-30')
        if df is not None and len(df) >= 50:
            data[s] = df
    print(f"{len(data)} stocks loaded")

    dates = pd.date_range('2025-10-01', '2026-01-25', freq='W-MON')
    trades = []
    recent = {}

    for d in dates:
        cutoff = d - timedelta(days=14)
        recent = {k: v for k, v in recent.items() if v > cutoff}

        candidates = []

        for s, df in data.items():
            if s in recent:
                continue

            try:
                if d not in df.index:
                    vd = df.index[df.index <= d]
                    if len(vd) == 0:
                        continue
                    idx = df.index.get_loc(vd[-1])
                else:
                    idx = df.index.get_loc(d)

                if idx < 25:
                    continue

                m = calc_metrics(df, idx)
                if m is None:
                    continue

                passed, reason = passes_v7_gates(m)
                if not passed:
                    continue

                score = calc_entry_score(m)
                candidates.append({
                    'symbol': s,
                    'score': score,
                    'idx': idx,
                    **m
                })
            except:
                continue

        if not candidates:
            print(f"{d.strftime('%Y-%m-%d')}: 0 passed")
            continue

        candidates.sort(key=lambda x: x['score'], reverse=True)
        selected = candidates[:5]

        sel_str = [f"{c['symbol']}({c['score']:.0f},m{c['mom_20d']:.0f},r{c['rsi']:.0f})" for c in selected]
        print(f"{d.strftime('%Y-%m-%d')}: {len(candidates)} passed, sel: {sel_str}")

        for c in selected:
            t = sim_trade(data[c['symbol']], c['idx'])
            trades.append({
                'symbol': c['symbol'],
                'entry_date': d,
                'score': c['score'],
                'mom': c['mom_20d'],
                'rsi': c['rsi'],
                **t
            })
            recent[c['symbol']] = d

    # Results
    print("\n" + "=" * 70)
    print("v7.0 PRODUCTION RESULTS")
    print("=" * 70)

    if not trades:
        print("No trades!")
        return

    df = pd.DataFrame(trades)
    total = len(df)
    win = df[df['ret'] > 0]
    lose = df[df['ret'] <= 0]
    wr = len(win) / total * 100

    print(f"\nSTATISTICS:")
    print(f"   Total Trades: {total}")
    print(f"   Winners: {len(win)} ({wr:.1f}%)")
    print(f"   Losers: {len(lose)} ({100-wr:.1f}%)")

    print(f"\nRETURNS:")
    print(f"   Average: {df['ret'].mean():.2f}%")
    if len(win) > 0:
        print(f"   Avg Winner: +{win['ret'].mean():.2f}%")
    if len(lose) > 0:
        print(f"   Avg Loser: {lose['ret'].mean():.2f}%")

    print(f"\nEXIT BREAKDOWN:")
    for ex in df['exit'].unique():
        sub = df[df['exit'] == ex]
        print(f"   {ex}: {len(sub)} ({len(sub)/total*100:.1f}%) avg: {sub['ret'].mean():+.1f}%")

    # Profit factor
    gp = win['ret'].sum() if len(win) > 0 else 0
    gl = abs(lose['ret'].sum()) if len(lose) > 0 else 1
    pf = gp / gl if gl > 0 else 0

    print(f"\nPERFORMANCE:")
    print(f"   Total Return: {df['ret'].sum():+.1f}%")
    print(f"   Profit Factor: {pf:.2f}")

    print(f"\nCOMPARISON:")
    print(f"   v6.5 (old):     80 trades, 62.5% WR, 30 losers, PF 2.34")
    print(f"   v7.0 EXPECTED:  37 trades, 83.8% WR, 6 losers, PF 7.14")
    print(f"   v7.0 ACTUAL:    {total} trades, {wr:.1f}% WR, {len(lose)} losers, PF {pf:.2f}")

    # Save results
    df.to_csv('backtest_v7_results.csv', index=False)
    print(f"\nSaved to backtest_v7_results.csv")

    return df


if __name__ == "__main__":
    run()
