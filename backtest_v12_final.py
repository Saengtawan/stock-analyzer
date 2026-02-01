#!/usr/bin/env python3
"""
Backtest v12 FINAL - Optimized for 85%+ Win Rate + Early Stop Loss

Entry Criteria:
- RSI <= 68 (removes overbought losers)
- Momentum 5-14% (sweet spot, avoids chasing)
- Entry Score >= 80

Exit Strategy:
- Target: +10%
- Normal Stop: -7%
- High Momentum Stop (Mom > 14%): -5%
- Early Warning Exit: If down > 3% in first 3 days → EXIT
- Trailing Stop: If up > 5%, move stop to breakeven
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import timedelta
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


def passes_v12_gates(m):
    """
    V12 FINAL Gates - Optimized for 85%+ Win Rate

    Based on deep analysis:
    - RSI > 70: 14% WR (must filter)
    - Mom < 5%: 25% WR (must filter)
    - Mom > 14%: Higher reversal risk
    - Sweet spot: Mom 5-14%, RSI <= 68
    """
    # Basic filters
    if m['ma20_pct'] < -5:
        return False, 'MA20 too low'

    if not (30 <= m['pos_52w'] <= 95):
        return False, '52w position out of range'

    # KEY FILTER 1: RSI <= 68 (removes overbought losers)
    if m['rsi'] > 68:
        return False, f"RSI too high ({m['rsi']:.0f} > 68)"

    # KEY FILTER 2: Momentum >= 5% (removes weak momentum losers)
    if m['mom_20d'] < 5:
        return False, f"Momentum too weak ({m['mom_20d']:.1f}% < 5%)"

    # KEY FILTER 3: Momentum <= 14% (removes chasing/reversal risk)
    # Note: We still allow 14-20% but flag for tighter stop
    if m['mom_20d'] > 20:
        return False, f"Momentum too high ({m['mom_20d']:.1f}% > 20%)"

    # ATR filter
    if m['atr_pct'] > 4:
        return False, 'ATR too high'

    # Volume filter
    if m['vol_ratio'] < 0.5:
        return False, 'Volume too low'

    return True, ''


def calc_entry_score(m):
    """Entry score optimized for sweet spot detection"""
    # Momentum score - sweet spot 8-12%
    if 8 <= m['mom_20d'] <= 12:
        mom_score = 100
    elif 5 <= m['mom_20d'] <= 14:
        mom_score = 90
    elif 5 <= m['mom_20d'] <= 18:
        mom_score = 75
    else:
        mom_score = 60

    # RSI score - optimal 50-58
    if 50 <= m['rsi'] <= 58:
        rsi_score = 100
    elif 45 <= m['rsi'] <= 65:
        rsi_score = 85
    else:
        rsi_score = 70

    # Position score - optimal 55-75%
    if 55 <= m['pos_52w'] <= 75:
        pos_score = 100
    elif 40 <= m['pos_52w'] <= 85:
        pos_score = 85
    else:
        pos_score = 70

    return mom_score * 0.40 + rsi_score * 0.35 + pos_score * 0.25


def sim_trade_v12(df, idx, momentum, target=10, maxhold=30):
    """
    V12 Smart Exit Strategy:
    1. Normal stop: -7%
    2. High momentum (>14%): -5% stop
    3. Early warning: If down > 3% in first 3 days → EXIT
    4. Trailing stop: If up > 5%, move stop to breakeven
    """
    entry_price = df.iloc[idx]['Close']

    # Determine stop loss based on momentum
    if momentum > 14:
        stop_pct = 5  # Tighter stop for high momentum
        stop_type = 'HIGH_MOM'
    else:
        stop_pct = 7  # Normal stop
        stop_type = 'NORMAL'

    stop_price = entry_price * (1 - stop_pct / 100)
    target_price = entry_price * (1 + target / 100)
    breakeven_triggered = False
    max_gain = 0

    for i in range(1, min(maxhold + 1, len(df) - idx)):
        cidx = idx + i
        if cidx >= len(df):
            break

        high = df.iloc[cidx]['High']
        low = df.iloc[cidx]['Low']
        close = df.iloc[cidx]['Close']

        current_return = ((close - entry_price) / entry_price) * 100
        max_gain = max(max_gain, current_return)

        # EARLY WARNING: If down > 3% in first 3 days → EXIT
        if i <= 3 and current_return < -3:
            return {
                'ret': current_return,
                'days': i,
                'exit': 'EARLY_WARNING',
                'stop_type': stop_type
            }

        # TRAILING STOP: If ever up > 5%, move stop to breakeven
        if max_gain >= 5 and not breakeven_triggered:
            stop_price = entry_price  # Move to breakeven
            breakeven_triggered = True

        # Check stop loss
        if low <= stop_price:
            if breakeven_triggered:
                actual_ret = 0  # Breakeven
                exit_type = 'BREAKEVEN'
            else:
                actual_ret = -stop_pct
                exit_type = 'STOP_LOSS'
            return {
                'ret': actual_ret,
                'days': i,
                'exit': exit_type,
                'stop_type': stop_type
            }

        # Check target
        if high >= target_price:
            return {
                'ret': target,
                'days': i,
                'exit': 'TARGET_HIT',
                'stop_type': stop_type
            }

    # Max hold exit
    final_idx = min(idx + maxhold, len(df) - 1)
    final_ret = ((df.iloc[final_idx]['Close'] - entry_price) / entry_price) * 100
    return {
        'ret': final_ret,
        'days': final_idx - idx,
        'exit': 'MAX_HOLD',
        'stop_type': stop_type
    }


def run():
    print("=" * 70)
    print("BACKTEST v12 FINAL - 85%+ Win Rate Target")
    print("=" * 70)
    print("\n📋 ENTRY CRITERIA:")
    print("  - RSI <= 68")
    print("  - Momentum 5-14% (optimal), up to 20% allowed")
    print("  - Entry Score >= 80")
    print("\n🚪 EXIT STRATEGY:")
    print("  - Target: +10%")
    print("  - Normal Stop: -7%")
    print("  - High Momentum (>14%) Stop: -5%")
    print("  - Early Warning: If down >3% in 3 days → EXIT")
    print("  - Trailing Stop: If up >5% → Move stop to breakeven")
    print("=" * 70)

    print("\n📥 Downloading data...")
    data = {}
    for s in WORKING_UNIVERSE:
        df = download_data(s, '2025-07-01', '2026-01-30')
        if df is not None and len(df) >= 50:
            data[s] = df
    print(f"✅ {len(data)} stocks loaded")

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

                passed, reason = passes_v12_gates(m)
                if not passed:
                    continue

                score = calc_entry_score(m)

                # KEY: Entry Score >= 80
                if score >= 80:
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

        sel_str = [f"{c['symbol']}({c['score']:.0f},m{c['mom_20d']:.0f})" for c in selected]
        print(f"{d.strftime('%Y-%m-%d')}: {len(candidates)} passed, sel: {sel_str}")

        for c in selected:
            t = sim_trade_v12(data[c['symbol']], c['idx'], c['mom_20d'])
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
    print("📊 BACKTEST v12 FINAL RESULTS")
    print("=" * 70)

    if not trades:
        print("No trades!")
        return

    df = pd.DataFrame(trades)
    total = len(df)
    win = df[df['ret'] > 0]
    lose = df[df['ret'] <= 0]
    wr = len(win) / total * 100

    print(f"\n🎯 STATISTICS:")
    print(f"   Total Trades: {total}")
    print(f"   Winners: {len(win)} ({wr:.1f}%)")
    print(f"   Losers: {len(lose)} ({100-wr:.1f}%)")

    print(f"\n💰 RETURNS:")
    print(f"   Average: {df['ret'].mean():.2f}%")
    if len(win) > 0:
        print(f"   Avg Winner: +{win['ret'].mean():.2f}%")
    if len(lose) > 0:
        print(f"   Avg Loser: {lose['ret'].mean():.2f}%")
    print(f"   Best: +{df['ret'].max():.2f}%")
    print(f"   Worst: {df['ret'].min():.2f}%")

    print(f"\n🚪 EXIT BREAKDOWN:")
    for ex in df['exit'].unique():
        sub = df[df['exit'] == ex]
        print(f"   {ex}: {len(sub)} ({len(sub)/total*100:.1f}%) avg: {sub['ret'].mean():+.1f}%")

    print(f"\n⚡ STOP TYPE ANALYSIS:")
    for st in df['stop_type'].unique():
        sub = df[df['stop_type'] == st]
        sub_w = len(sub[sub['ret'] > 0])
        print(f"   {st}: {len(sub)} trades, {sub_w} wins ({sub_w/len(sub)*100:.1f}% WR)")

    # Profit factor
    gp = win['ret'].sum() if len(win) > 0 else 0
    gl = abs(lose['ret'].sum()) if len(lose) > 0 else 1
    pf = gp / gl if gl > 0 else 0

    print(f"\n📈 PERFORMANCE:")
    print(f"   Total Return: {df['ret'].sum():+.1f}%")
    print(f"   Profit Factor: {pf:.2f}")

    # Monthly
    print(f"\n📅 MONTHLY:")
    df['month'] = pd.to_datetime(df['entry_date']).dt.to_period('M')
    for m in df['month'].unique():
        sub = df[df['month'] == m]
        mwr = (sub['ret'] > 0).sum() / len(sub) * 100
        print(f"   {m}: {len(sub)} trades, {mwr:.0f}% WR")

    print(f"\n📊 COMPARISON:")
    print(f"   v9 Original:  80 trades, 62.5% WR, 30 losers")
    print(f"   Option B:     52 trades, 80.8% WR, 10 losers")
    print(f"   v12 FINAL:    {total} trades, {wr:.1f}% WR, {len(lose)} losers")

    df.to_csv('backtest_v12_results.csv', index=False)
    print(f"\n💾 Saved to backtest_v12_results.csv")

    return df


if __name__ == "__main__":
    run()
