#!/usr/bin/env python3
"""
Backtest v6.4: Volume Confirmation + Entry Score >= 110

Filters:
- Volume Trend >= 1.0 (5d avg > 20d avg)
- Accumulation >= 1.2 (up vol > down vol)
- Entry Score >= 110 (high quality)
- All existing momentum gates

Exit Rules:
- Stop Loss: -6%
- Target: +5%
- Max Hold: 14 days
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

from screeners.growth_catalyst_screener import GrowthCatalystScreener
FULL_UNIVERSE = GrowthCatalystScreener.STATIC_UNIVERSE

# Settings
MIN_ENTRY_SCORE = 110
STOP_LOSS = 6  # -6%
TARGET = 5     # +5%
MAX_HOLD = 14  # days


def download_batch(symbols, start, end):
    """Batch download"""
    print(f"  Downloading {len(symbols)} stocks...")
    raw = yf.download(symbols, start=start, end=end, group_by='ticker', threads=True, progress=False)

    data = {}
    for symbol in symbols:
        try:
            if len(symbols) == 1:
                df = raw.copy()
            else:
                df = raw[symbol].copy()
            df = df.dropna()
            df.columns = [c.lower() for c in df.columns]
            if len(df) >= 50:
                data[symbol] = df
        except:
            continue
    return data


def calc_metrics(df, idx):
    """Calculate all metrics including Volume Confirmation"""
    if idx < 30:
        return None

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    current_price = close.iloc[idx]

    # MA20, MA50
    ma20 = close.iloc[idx-20:idx].mean()
    ma50 = close.iloc[idx-50:idx].mean()
    ma20_pct = ((current_price - ma20) / ma20) * 100
    ma50_pct = ((current_price - ma50) / ma50) * 100

    # 52-week position
    lookback = min(252, idx)
    high_52w = high.iloc[idx-lookback:idx].max()
    low_52w = low.iloc[idx-lookback:idx].min()
    pos_52w = ((current_price - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

    # Momentum
    mom_3d = ((current_price - close.iloc[idx-3]) / close.iloc[idx-3]) * 100 if idx >= 3 else 0
    mom_20d = ((current_price - close.iloc[idx-20]) / close.iloc[idx-20]) * 100 if idx >= 20 else 0
    mom_30d = ((current_price - close.iloc[idx-30]) / close.iloc[idx-30]) * 100 if idx >= 30 else 0

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain.iloc[idx]/loss.iloc[idx])) if loss.iloc[idx] > 0 else 50

    # ATR%
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr_pct = (tr.rolling(14).mean().iloc[idx] / current_price) * 100

    # Volume Ratio
    vol_20 = volume.iloc[idx-20:idx].mean()
    vol_ratio = volume.iloc[idx] / vol_20 if vol_20 > 0 else 1

    # === Volume Confirmation (87.5% WR!) ===
    vol_5 = volume.iloc[idx-5:idx].mean()
    vol_trend = vol_5 / vol_20 if vol_20 > 0 else 1

    price_change = close.diff().iloc[idx-10:idx]
    vol_10 = volume.iloc[idx-10:idx]
    up_vol = vol_10[price_change > 0].sum()
    down_vol = vol_10[price_change <= 0].sum()
    accumulation = up_vol / down_vol if down_vol > 0 else 2.0

    return {
        'close': current_price,
        'ma20_pct': ma20_pct,
        'ma50_pct': ma50_pct,
        'pos_52w': pos_52w,
        'mom_3d': mom_3d,
        'mom_20d': mom_20d,
        'mom_30d': mom_30d,
        'rsi': rsi,
        'atr_pct': atr_pct,
        'vol_ratio': vol_ratio,
        'vol_trend': vol_trend,
        'accumulation': accumulation
    }


def passes_gates(m):
    """Check all gates including Volume Confirmation"""
    # Gate 1: Above MA20
    if m['ma20_pct'] < -5:
        return False, "Below MA20"

    # Gate 2: 52-week position
    if m['pos_52w'] < 30 or m['pos_52w'] > 95:
        return False, "52w position extreme"

    # Gate 3: Momentum 20d
    if m['mom_20d'] < 0 or m['mom_20d'] > 25:
        return False, "Mom 20d out of range"

    # Gate 4: Momentum 3d
    if m['mom_3d'] < -5:
        return False, "Mom 3d too negative"

    # Gate 5: RSI
    if m['rsi'] < 35 or m['rsi'] > 70:
        return False, "RSI extreme"

    # Gate 6: ATR
    if m['atr_pct'] > 4:
        return False, "ATR too high"

    # Gate 7: Volume ratio
    if m['vol_ratio'] < 0.5:
        return False, "Volume too low"

    # Gate 8: Volume Trend (v6.4)
    if m['vol_trend'] < 1.0:
        return False, "Vol trend < 1.0"

    # Gate 9: Accumulation (v6.4)
    if m['accumulation'] < 1.2:
        return False, "Accumulation < 1.2"

    return True, ""


def calc_entry_score(m):
    """Calculate Entry Score (simplified version)"""
    score = 0

    # Momentum component (70%)
    # Sweet spot: Mom 8-12%
    if 8 <= m['mom_20d'] <= 12:
        score += 50
    elif 5 <= m['mom_20d'] <= 15:
        score += 40
    elif 0 <= m['mom_20d'] <= 25:
        score += 25

    # RSI sweet spot: 50-58
    if 50 <= m['rsi'] <= 58:
        score += 30
    elif 45 <= m['rsi'] <= 62:
        score += 25
    else:
        score += 15

    # Position sweet spot: 65-80%
    if 65 <= m['pos_52w'] <= 80:
        score += 25
    elif 55 <= m['pos_52w'] <= 85:
        score += 20
    else:
        score += 10

    # Volume Confirmation bonus
    if m['vol_trend'] >= 1.2:
        score += 10
    if m['accumulation'] >= 1.5:
        score += 10

    # MA50 bonus
    if m['ma50_pct'] > 5:
        score += 10

    # Low ATR bonus
    if m['atr_pct'] < 2.5:
        score += 5

    return score


def sim_trade(df, idx, stop_loss=STOP_LOSS, target=TARGET, max_hold=MAX_HOLD):
    """Simulate trade"""
    entry = df['close'].iloc[idx]
    tp = entry * (1 + target/100)
    sl = entry * (1 - stop_loss/100)

    for i in range(1, min(max_hold+1, len(df)-idx)):
        cidx = idx + i
        if cidx >= len(df):
            break
        h, l = df['high'].iloc[cidx], df['low'].iloc[cidx]

        if l <= sl:
            return {'ret': -stop_loss, 'days': i, 'exit': 'STOP'}
        if h >= tp:
            return {'ret': target, 'days': i, 'exit': 'TARGET'}

    # Max hold exit
    fidx = min(idx + max_hold, len(df)-1)
    ret = ((df['close'].iloc[fidx] - entry) / entry) * 100
    return {'ret': ret, 'days': fidx-idx, 'exit': 'MAX_HOLD'}


def run_backtest():
    print("=" * 70)
    print("BACKTEST v6.4: Volume Confirmation + Entry Score >= 110")
    print("=" * 70)
    print(f"Filters: Vol Trend >= 1.0, Accumulation >= 1.2, Entry Score >= {MIN_ENTRY_SCORE}")
    print(f"Exit: Stop -{STOP_LOSS}%, Target +{TARGET}%, Max Hold {MAX_HOLD} days")
    print(f"Universe: {len(FULL_UNIVERSE)} stocks")
    print("=" * 70)

    print("\nDownloading data (batch)...")
    data = download_batch(FULL_UNIVERSE, '2025-07-01', '2026-01-30')
    print(f"Downloaded {len(data)} stocks\n")

    # Test dates (weekly, 4 months)
    dates = pd.date_range('2025-10-01', '2026-01-25', freq='W-MON')

    trades = []
    recent = {}  # Avoid duplicate trades

    print("Running backtest...")
    for d in dates:
        cutoff = d - timedelta(days=14)
        recent = {k: v for k, v in recent.items() if v > cutoff}

        candidates = []

        for symbol, df in data.items():
            if symbol in recent:
                continue

            try:
                # Find index for this date
                if d not in df.index:
                    valid_dates = df.index[df.index <= d]
                    if len(valid_dates) == 0:
                        continue
                    idx = df.index.get_loc(valid_dates[-1])
                else:
                    idx = df.index.get_loc(d)

                if idx < 30:
                    continue

                m = calc_metrics(df, idx)
                if m is None:
                    continue

                # Check gates
                passes, reason = passes_gates(m)
                if not passes:
                    continue

                # Calculate entry score
                score = calc_entry_score(m)

                if score >= MIN_ENTRY_SCORE:
                    candidates.append({
                        'symbol': symbol,
                        'score': score,
                        'idx': idx,
                        'date': d,
                        'price': m['close'],
                        'vol_trend': m['vol_trend'],
                        'accum': m['accumulation'],
                        'mom_20d': m['mom_20d'],
                        'rsi': m['rsi']
                    })
            except Exception as e:
                continue

        if not candidates:
            continue

        # Sort by score, take top 3
        candidates.sort(key=lambda x: x['score'], reverse=True)
        selected = candidates[:3]

        for c in selected:
            t = sim_trade(data[c['symbol']], c['idx'])
            trades.append({
                'date': c['date'].strftime('%Y-%m-%d'),
                'symbol': c['symbol'],
                'score': c['score'],
                'price': c['price'],
                'vol_trend': c['vol_trend'],
                'accum': c['accum'],
                'mom_20d': c['mom_20d'],
                'rsi': c['rsi'],
                **t
            })
            recent[c['symbol']] = c['date']

    # Results
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS v6.4")
    print("=" * 70)

    if not trades:
        print("No trades found!")
        return

    df = pd.DataFrame(trades)
    wins = df[df['ret'] > 0]
    losses = df[df['ret'] <= 0]

    win_rate = len(wins) / len(df) * 100
    avg_win = wins['ret'].mean() if len(wins) > 0 else 0
    avg_loss = losses['ret'].mean() if len(losses) > 0 else 0
    total_ret = df['ret'].sum()

    print(f"\nTotal Trades: {len(df)}")
    print(f"Winners: {len(wins)}")
    print(f"Losers: {len(losses)}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Avg Win: +{avg_win:.1f}%")
    print(f"Avg Loss: {avg_loss:.1f}%")
    print(f"Total Return: {total_ret:+.1f}%")
    print(f"Trades/Month: {len(df)/4:.1f}")

    # Show trades
    print("\n" + "=" * 70)
    print(f"WINNERS ({len(wins)}):")
    print("-" * 70)
    for _, t in wins.iterrows():
        print(f"  {t['date']} | {t['symbol']:6} | Score {t['score']:3.0f} | VolTr {t['vol_trend']:.2f} | Accum {t['accum']:.2f} | {t['ret']:+.1f}% in {t['days']}d ({t['exit']})")

    print(f"\nLOSERS ({len(losses)}):")
    print("-" * 70)
    for _, t in losses.iterrows():
        print(f"  {t['date']} | {t['symbol']:6} | Score {t['score']:3.0f} | VolTr {t['vol_trend']:.2f} | Accum {t['accum']:.2f} | {t['ret']:+.1f}% in {t['days']}d ({t['exit']})")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"""
    📊 v6.4 Backtest Results:

    Filters Applied:
    - Volume Trend >= 1.0
    - Accumulation >= 1.2
    - Entry Score >= {MIN_ENTRY_SCORE}
    - All momentum gates

    Results:
    - {len(df)} trades in 4 months ({len(df)/4:.1f}/month)
    - {win_rate:.1f}% Win Rate
    - {len(losses)} losers only
    - {total_ret:+.1f}% total return

    Exit Rules:
    - Stop Loss: -{STOP_LOSS}%
    - Target: +{TARGET}%
    - Max Hold: {MAX_HOLD} days
    """)


if __name__ == "__main__":
    run_backtest()
