#!/usr/bin/env python3
"""
Test B: Volume Confirmation
- ซื้อเมื่อ volume เพิ่มขึ้น (volume > avg * 1.2)
- Volume on up days > Volume on down days (accumulation)
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')
from concurrent.futures import ThreadPoolExecutor, as_completed

from screeners.growth_catalyst_screener import GrowthCatalystScreener
FULL_UNIVERSE = GrowthCatalystScreener.STATIC_UNIVERSE


def download_data(symbol):
    try:
        df = yf.Ticker(symbol).history(start='2025-07-01', end='2026-01-30', auto_adjust=True)
        if df.empty or len(df) < 20:
            return symbol, None
        df.index = df.index.tz_localize(None)
        return symbol, df
    except:
        return symbol, None


def download_all_parallel(symbols, max_workers=25):
    data = {}
    total = len(symbols)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_data, s): s for s in symbols}
        done = 0
        for future in as_completed(futures):
            done += 1
            symbol, df = future.result()
            if df is not None and len(df) >= 50:
                data[symbol] = df
            if done % 100 == 0:
                print(f"  Downloaded {done}/{total}...")
    return data


def calc_metrics_with_volume(df, idx):
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

    # === NEW: Volume Analysis ===
    # Recent 5-day average volume vs 20-day average
    vol_5 = df['Volume'].iloc[idx-5:idx].mean()
    vol_trend = vol_5 / vol_20 if vol_20 > 0 else 1  # > 1 = volume increasing

    # Accumulation: Volume on up days vs down days (last 10 days)
    price_change = df['Close'].diff().iloc[idx-10:idx]
    volume = df['Volume'].iloc[idx-10:idx]
    up_volume = volume[price_change > 0].sum()
    down_volume = volume[price_change <= 0].sum()
    accumulation_ratio = up_volume / down_volume if down_volume > 0 else 2.0

    # Volume spike (today vs avg)
    vol_spike = df['Volume'].iloc[idx] / vol_20 if vol_20 > 0 else 1

    return {
        'close': close, 'ma20_pct': ma20_pct, 'pos_52w': pos_52w,
        'mom_20d': mom_20d, 'rsi': rsi_14, 'atr_pct': atr_pct, 'vol_ratio': vol_ratio,
        # New volume metrics
        'vol_trend': vol_trend,
        'accumulation_ratio': accumulation_ratio,
        'vol_spike': vol_spike
    }


def calc_score_original(m):
    """Original scoring"""
    score = 0
    if 8 <= m['mom_20d'] <= 12:
        score += 40
    elif 5 <= m['mom_20d'] <= 15:
        score += 30
    else:
        score += 15

    if 50 <= m['rsi'] <= 58:
        score += 35
    elif 45 <= m['rsi'] <= 62:
        score += 28
    else:
        score += 15

    if 65 <= m['pos_52w'] <= 80:
        score += 25
    elif 55 <= m['pos_52w'] <= 85:
        score += 20
    else:
        score += 10

    return score


def sim_trade(df, idx, stop_loss=5, target=10, maxhold=30):
    entry = df.iloc[idx]['Close']
    tp = entry * (1 + target/100)
    sl = entry * (1 - stop_loss/100)

    for i in range(1, min(maxhold+1, len(df)-idx)):
        cidx = idx + i
        if cidx >= len(df):
            break
        h, l = df.iloc[cidx]['High'], df.iloc[cidx]['Low']
        if l <= sl:
            return {'ret': -stop_loss, 'days': i, 'exit': 'STOP'}
        if h >= tp:
            return {'ret': target, 'days': i, 'exit': 'TARGET'}

    fidx = min(idx + maxhold, len(df)-1)
    ret = ((df.iloc[fidx]['Close'] - entry) / entry) * 100
    return {'ret': ret, 'days': fidx-idx, 'exit': 'MAX_HOLD'}


def run_config(data, min_score, top_n, atr_max, vol_filter='none'):
    """
    vol_filter options:
    - 'none': no volume filter (original)
    - 'trend': volume trend > 1.0 (5-day avg > 20-day avg)
    - 'accumulation': accumulation_ratio > 1.2 (up volume > down volume)
    - 'spike': vol_spike > 1.2 (today's volume > 20-day avg)
    - 'all': all volume filters combined
    """
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
                    if len(vd) == 0: continue
                    idx = df.index.get_loc(vd[-1])
                else:
                    idx = df.index.get_loc(d)
                if idx < 25: continue

                m = calc_metrics_with_volume(df, idx)
                if m is None: continue

                # Basic Gates
                if m['ma20_pct'] < -5: continue
                if not (30 <= m['pos_52w'] <= 95): continue
                if m['mom_20d'] < 0 or m['mom_20d'] > 25: continue
                if m['rsi'] < 35 or m['rsi'] > 70: continue
                if m['atr_pct'] > atr_max: continue
                if m['vol_ratio'] < 0.5: continue

                # Volume Filters
                if vol_filter == 'trend' and m['vol_trend'] < 1.0:
                    continue
                if vol_filter == 'accumulation' and m['accumulation_ratio'] < 1.2:
                    continue
                if vol_filter == 'spike' and m['vol_spike'] < 1.2:
                    continue
                if vol_filter == 'all':
                    if m['vol_trend'] < 1.0 or m['accumulation_ratio'] < 1.2:
                        continue

                score = calc_score_original(m)
                if score >= min_score:
                    candidates.append({
                        's': s, 'score': score, 'idx': idx, 'atr': m['atr_pct'],
                        'vol_trend': m['vol_trend'], 'accum': m['accumulation_ratio']
                    })
            except:
                continue

        if not candidates:
            continue

        candidates.sort(key=lambda x: x['score'], reverse=True)
        selected = candidates[:top_n]

        for c in selected:
            t = sim_trade(data[c['s']], c['idx'])
            trades.append({
                'symbol': c['s'], 'score': c['score'], 'atr': c['atr'],
                'vol_trend': c['vol_trend'], 'accum': c['accum'],
                **t
            })
            recent[c['s']] = d

    return trades


def run():
    print("=" * 70)
    print("TEST B: Volume Confirmation")
    print("=" * 70)

    print("\nกำลังโหลดข้อมูล...")
    data = download_all_parallel(FULL_UNIVERSE)
    print(f"โหลดสำเร็จ {len(data)} หุ้น\n")

    vol_filters = ['none', 'trend', 'accumulation', 'spike', 'all']
    filter_names = {
        'none': 'No Volume Filter (Original)',
        'trend': 'Volume Trend > 1.0',
        'accumulation': 'Accumulation > 1.2',
        'spike': 'Volume Spike > 1.2',
        'all': 'Trend + Accumulation'
    }

    all_results = {}

    for vol_filter in vol_filters:
        print(f"Testing {filter_names[vol_filter]}...")
        results = []

        for min_score in [88, 90, 92]:
            for top_n in [1, 2]:
                trades = run_config(data, min_score, top_n, 4.0, vol_filter)
                if len(trades) >= 3:
                    df = pd.DataFrame(trades)
                    wins = len(df[df['ret'] > 0])
                    wr = wins / len(df) * 100
                    results.append({
                        'score': min_score, 'top_n': top_n,
                        'trades': len(df), 'wins': wins, 'losses': len(df)-wins,
                        'wr': wr, 'total': df['ret'].sum()
                    })

        results.sort(key=lambda x: (-x['wr'], x['losses']))
        all_results[vol_filter] = results

    # Display results for each filter
    for vol_filter, results in all_results.items():
        print("\n" + "=" * 70)
        print(f"{filter_names[vol_filter]}")
        print("=" * 70)
        print(f"{'Score':>5} | {'Top':>3} | {'Trades':>6} | {'Win':>4} | {'Lose':>4} | {'WR%':>6} | {'Total':>7}")
        print("-" * 55)
        for r in results[:5]:
            print(f"{r['score']:>5} | {r['top_n']:>3} | {r['trades']:>6} | {r['wins']:>4} | {r['losses']:>4} | {r['wr']:>5.1f}% | {r['total']:>+6.1f}%")

    # Summary comparison
    print("\n" + "=" * 70)
    print("SUMMARY: Best of Each Volume Filter")
    print("=" * 70)
    print(f"{'Filter':<30} | {'Score':>5} | {'Trades':>6} | {'WR%':>6} | {'Losers':>6}")
    print("-" * 65)

    for vol_filter, results in all_results.items():
        if results:
            best = results[0]
            print(f"{filter_names[vol_filter]:<30} | {best['score']:>5} | {best['trades']:>6} | {best['wr']:>5.1f}% | {best['losses']:>6}")

    # Show example trades from best volume filter
    best_filter = None
    best_wr = 0
    for vol_filter, results in all_results.items():
        if results and results[0]['wr'] > best_wr:
            best_wr = results[0]['wr']
            best_filter = vol_filter

    if best_filter and all_results[best_filter]:
        best = all_results[best_filter][0]
        trades = run_config(data, best['score'], best['top_n'], 4.0, best_filter)
        if trades:
            print("\n" + "=" * 70)
            print(f"Example Trades (Best: {filter_names[best_filter]}, Score >= {best['score']}):")
            print("=" * 70)
            df = pd.DataFrame(trades)
            print(f"\nWinners ({len(df[df['ret'] > 0])}):")
            for _, t in df[df['ret'] > 0].head(8).iterrows():
                print(f"  {t['symbol']:6} | Score {t['score']:.0f} | VolTrend {t['vol_trend']:.2f} | Accum {t['accum']:.2f} | {t['ret']:+.1f}%")
            print(f"\nLosers ({len(df[df['ret'] <= 0])}):")
            for _, t in df[df['ret'] <= 0].head(5).iterrows():
                print(f"  {t['symbol']:6} | Score {t['score']:.0f} | VolTrend {t['vol_trend']:.2f} | Accum {t['accum']:.2f} | {t['ret']:+.1f}%")


if __name__ == "__main__":
    run()
