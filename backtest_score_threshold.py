#!/usr/bin/env python3
"""
Backtest - Test different score thresholds

Hypothesis: Higher entry score = better win rate
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
    return {
        'close': close, 'ma20_pct': ma20_pct, 'pos_52w': pos_52w,
        'mom_20d': mom_20d, 'mom_3d': mom_3d, 'rsi': rsi_14,
        'atr_pct': atr_pct, 'vol_ratio': vol_ratio
    }


def passes_basic_gates(m):
    """Basic sanity gates only"""
    if m['ma20_pct'] < -5:
        return False
    if not (30 <= m['pos_52w'] <= 95):
        return False
    if m['mom_20d'] < 0 or m['mom_20d'] > 25:
        return False
    if m['mom_3d'] < -5:
        return False
    if m['rsi'] < 35 or m['rsi'] > 70:
        return False
    if m['atr_pct'] > 4:
        return False
    if m['vol_ratio'] < 0.5:
        return False
    return True


def calc_score(m):
    """Entry score - emphasize sweet spots"""
    # Momentum score (40%) - optimal 8-12%
    if 8 <= m['mom_20d'] <= 12:
        mom_score = 100
    elif 6 <= m['mom_20d'] <= 14:
        mom_score = 90
    elif 5 <= m['mom_20d'] <= 16:
        mom_score = 75
    else:
        mom_score = 50

    # RSI score (35%) - optimal 50-58
    if 50 <= m['rsi'] <= 58:
        rsi_score = 100
    elif 48 <= m['rsi'] <= 60:
        rsi_score = 90
    elif 45 <= m['rsi'] <= 62:
        rsi_score = 75
    else:
        rsi_score = 50

    # Position score (25%) - optimal 60-80%
    if 65 <= m['pos_52w'] <= 80:
        pos_score = 100
    elif 60 <= m['pos_52w'] <= 85:
        pos_score = 90
    elif 55 <= m['pos_52w'] <= 88:
        pos_score = 75
    else:
        pos_score = 50

    return mom_score * 0.4 + rsi_score * 0.35 + pos_score * 0.25


def sim_trade(df, idx, target=10, stop=7, maxhold=30):
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


def run_with_threshold(data, min_score):
    """Run backtest with a specific score threshold"""
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
                if m and passes_basic_gates(m):
                    score = calc_score(m)
                    if score >= min_score:
                        candidates.append({'s': s, 'score': score, 'idx': idx, **m})
            except:
                continue

        if not candidates:
            continue
        candidates.sort(key=lambda x: x['score'], reverse=True)
        for c in candidates[:5]:
            t = sim_trade(data[c['s']], c['idx'])
            trades.append({
                'symbol': c['s'],
                'score': c['score'],
                'mom': c['mom_20d'],
                'rsi': c['rsi'],
                **t
            })
            recent[c['s']] = d

    return trades


def run():
    print("=" * 70)
    print("BACKTEST - SCORE THRESHOLD ANALYSIS")
    print("=" * 70)
    print("Testing different minimum score thresholds")
    print("=" * 70)

    print("\nDownloading data...")
    data = {}
    for s in WORKING_UNIVERSE:
        df = download_data(s, '2025-07-01', '2026-01-30')
        if df is not None and len(df) >= 50:
            data[s] = df
    print(f"{len(data)} stocks loaded\n")

    thresholds = [70, 75, 80, 85, 88, 90, 92, 95]

    print(f"{'Score':>6} | {'Trades':>6} | {'Winners':>7} | {'Losers':>6} | {'WR%':>6} | {'PF':>5} | {'Total%':>8}")
    print("-" * 60)

    for thresh in thresholds:
        trades = run_with_threshold(data, thresh)
        if not trades:
            print(f"{thresh:>6} | {'N/A':>6}")
            continue

        df = pd.DataFrame(trades)
        total = len(df)
        win = len(df[df['ret'] > 0])
        lose = len(df[df['ret'] <= 0])
        wr = win / total * 100
        gp = df[df['ret'] > 0]['ret'].sum()
        gl = abs(df[df['ret'] <= 0]['ret'].sum())
        pf = gp / gl if gl > 0 else 0
        total_ret = df['ret'].sum()

        print(f"{thresh:>6} | {total:>6} | {win:>7} | {lose:>6} | {wr:>5.1f}% | {pf:>5.2f} | {total_ret:>+7.1f}%")

    # Best threshold for target 85% WR
    print("\n" + "=" * 70)
    print("ANALYSIS:")
    print("=" * 70)
    print("Looking for: 85% Win Rate + Maximum Trades")
    print("\nRun with score >= 90 for detailed results...")

    # Detailed results for best threshold
    trades = run_with_threshold(data, 90)
    if trades:
        df = pd.DataFrame(trades)
        print(f"\nScore >= 90 trades:")
        for _, row in df.iterrows():
            status = 'WIN' if row['ret'] > 0 else 'LOSE'
            print(f"  {row['symbol']:5} | score={row['score']:.0f} | mom={row['mom']:.1f}% | rsi={row['rsi']:.0f} | {status} {row['ret']:+.1f}%")

    return


if __name__ == "__main__":
    run()
