#!/usr/bin/env python3
"""
Gap Momentum Strategy - No Earnings Filter

Tests: buy at open after gap-up + volume spike, regardless of earnings date.
Compares against current PEM (which requires earnings date).

Parameters tested:
- Gap thresholds: 5%, 8%, 10%, 15%
- Volume thresholds: 1.5x, 2x, 3x, 5x
- Hold periods: intraday (0), 1d, 2d, 3d, 5d
- Universe: full universe from full_universe_cache.json (~987 stocks)
- Period: 2023-01-01 to 2025-12-31
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime
from typing import List, Dict
import json

CACHE_DIR = 'backtests/cache'
os.makedirs(CACHE_DIR, exist_ok=True)


def get_price_data(symbol: str, start: str, end: str) -> pd.DataFrame:
    cache_file = os.path.join(CACHE_DIR, f"{symbol}_{start}_{end}.csv")
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    try:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            df.to_csv(cache_file)
        return df
    except Exception:
        return pd.DataFrame()


def find_gap_events(df: pd.DataFrame, gap_min: float, vol_min: float) -> List[Dict]:
    """Find all gap-up events matching gap_min% + vol_min×20d_avg."""
    if len(df) < 25:
        return []
    df = df.copy()
    df['vol20'] = df['Volume'].rolling(20).mean().shift(1)  # exclude today
    df['gap_pct'] = (df['Open'] - df['Close'].shift(1)) / df['Close'].shift(1) * 100
    df['vol_ratio'] = df['Volume'] / df['vol20']

    events = []
    for i in range(21, len(df)):
        gap = df['gap_pct'].iloc[i]
        vr = df['vol_ratio'].iloc[i]
        if gap >= gap_min and vr >= vol_min:
            events.append({
                'i': i,
                'date': df.index[i],
                'gap_pct': gap,
                'vol_ratio': vr,
                'prev_close': df['Close'].iloc[i - 1],
                'open': df['Open'].iloc[i],
                'close': df['Close'].iloc[i],  # same-day close (intraday)
            })
    return events


def calc_returns(df: pd.DataFrame, events: List[Dict], hold_days: List[int]) -> List[Dict]:
    """For each event, calculate return for each hold period."""
    rows = []
    for ev in events:
        buy = ev['open']
        # intraday = same-day close
        intraday_ret = (ev['close'] - buy) / buy * 100
        row = {
            'date': ev['date'],
            'gap_pct': ev['gap_pct'],
            'vol_ratio': ev['vol_ratio'],
            'prev_close': ev['prev_close'],
            'open': buy,
            'ret_0d': intraday_ret,
        }
        for h in hold_days:
            sell_i = ev['i'] + h
            if sell_i < len(df):
                sell_price = df['Close'].iloc[sell_i]
                row[f'ret_{h}d'] = (sell_price - buy) / buy * 100
            else:
                row[f'ret_{h}d'] = None
        rows.append(row)
    return rows


def load_universe() -> List[str]:
    """Load full universe from cache, fallback to hardcoded list."""
    try:
        path = os.path.join(os.path.dirname(__file__), '..', 'data', 'full_universe_cache.json')
        with open(path) as f:
            syms = list(json.load(f).keys())
        print(f"Loaded {len(syms)} symbols from full_universe_cache.json")
        return syms
    except Exception as e:
        print(f"Could not load full universe ({e}), using fallback 100 stocks")
        return [
            'NVDA','AMD','TSLA','AAPL','MSFT','GOOGL','META','AMZN','NFLX','COIN',
            'SHOP','SNOW','CRWD','NET','DDOG','ZS','PLTR','HOOD','RBLX','SOFI',
            'UPST','MDB','OKTA','BILL','HUBS','TTD','AFRM','CFLT','U','RIVN',
            'LCID','MRNA','BNTX','VRTX','REGN','GME','AMC','PLUG','ROKU','PINS',
            'SNAP','LYFT','UBER','ABNB','DASH','PTON','ZM','DOCU','TWLO','SQ',
            'PYPL','ADBE','CRM','NOW','WDAY','VEEV','TEAM','ORCL','IBM','INTC',
            'QCOM','AVGO','TXN','MU','LRCX','KLAC','AMAT','ASML','ARM','SMCI',
            'TSMC','BABA','JD','PDD','NIO','XPEV','LI','BIDU','WB','IQ',
            'NTES','BILI','MCHI','EEM','FXI','KWEB','ARKK','ARKG','ARKF','ARKI',
            'SPY','QQQ','IWM','GLD','SLV','TLT','HYG','VIX','UVXY','SQQQ',
        ]


def run_backtest(
    universe: List[str],
    start: str = '2023-01-01',
    end: str = '2025-12-31',
    gap_thresholds: List[float] = [5.0, 8.0, 10.0, 15.0],
    vol_thresholds: List[float] = [1.5, 2.0, 3.0, 5.0],
    hold_days: List[int] = [1, 2, 3, 5],
) -> pd.DataFrame:
    all_rows = []
    n = len(universe)
    for idx, sym in enumerate(universe):
        if (idx + 1) % 50 == 0 or idx == 0:
            print(f"  [{idx+1}/{n}] {sym} ...")
        df = get_price_data(sym, start, end)
        if df.empty or len(df) < 25:
            continue
        # Use loosest threshold to collect all events once, filter later
        events = find_gap_events(df, gap_min=5.0, vol_min=1.5)
        if not events:
            continue
        rows = calc_returns(df, events, hold_days)
        for r in rows:
            r['symbol'] = sym
        all_rows.extend(rows)

    df_all = pd.DataFrame(all_rows)
    return df_all


def analyze(df: pd.DataFrame, gap_min: float, vol_min: float, hold: int) -> Dict:
    """Filter and compute stats for one parameter set."""
    sub = df[(df['gap_pct'] >= gap_min) & (df['vol_ratio'] >= vol_min)].copy()
    col = f'ret_{hold}d'
    sub = sub[sub[col].notna()]
    if len(sub) < 5:
        return None
    wr = (sub[col] > 0).mean() * 100
    avg = sub[col].mean()
    med = sub[col].median()
    p25 = sub[col].quantile(0.25)
    p75 = sub[col].quantile(0.75)
    best = sub[col].max()
    worst = sub[col].min()
    # events/month
    dates = pd.to_datetime(sub['date'])
    span_months = (dates.max() - dates.min()).days / 30
    epm = len(sub) / span_months if span_months > 0 else 0
    return {
        'gap_min': gap_min, 'vol_min': vol_min, 'hold': hold,
        'n': len(sub), 'wr': wr, 'avg': avg, 'median': med,
        'p25': p25, 'p75': p75, 'best': best, 'worst': worst,
        'epm': epm,
    }


def print_matrix(df_all: pd.DataFrame, hold: int, gap_thresholds, vol_thresholds):
    """Print WR% matrix for a given hold period."""
    print(f"\n--- Hold {hold}d: Win Rate % (rows=gap_min, cols=vol_min) ---")
    gap_vol_label = "gap/vol"
    header = f"{gap_vol_label:<8}" + "".join(f"{v:.1f}x{'':<5}" for v in vol_thresholds)
    print(header)
    for g in gap_thresholds:
        row = f"{g:.0f}%{'':<4}"
        for v in vol_thresholds:
            stats = analyze(df_all, g, v, hold)
            if stats:
                row += f"{stats['wr']:5.1f}%  "
            else:
                row += f"  n/a  "
        print(row)

    print(f"\n--- Hold {hold}d: Avg Return % ---")
    print(header)
    for g in gap_thresholds:
        row = f"{g:.0f}%{'':<4}"
        for v in vol_thresholds:
            stats = analyze(df_all, g, v, hold)
            if stats:
                row += f"{stats['avg']:+5.1f}%  "
            else:
                row += f"  n/a  "
        print(row)

    print(f"\n--- Hold {hold}d: Events/Month ---")
    print(header)
    for g in gap_thresholds:
        row = f"{g:.0f}%{'':<4}"
        for v in vol_thresholds:
            stats = analyze(df_all, g, v, hold)
            if stats:
                row += f"{stats['epm']:5.1f}   "
            else:
                row += f"  n/a  "
        print(row)


def main():
    print("=" * 70)
    print("GAP MOMENTUM BACKTEST — No Earnings Filter")
    print("=" * 70)

    universe = load_universe()

    START = '2023-01-01'
    END   = '2025-12-31'
    GAP_THRESHOLDS = [5.0, 8.0, 10.0, 15.0]
    VOL_THRESHOLDS = [1.5, 2.0, 3.0, 5.0]
    HOLD_DAYS      = [1, 2, 3, 5]

    print(f"\nCollecting all gap events ≥5% + ≥1.5×vol from {len(universe)} stocks ({START}→{END})...")
    df_all = run_backtest(universe, START, END, hold_days=HOLD_DAYS)
    print(f"\nTotal raw gap events: {len(df_all)}")

    if df_all.empty:
        print("No events found. Exiting.")
        return

    # Save raw
    df_all.to_csv('backtests/gap_momentum_no_earnings_raw.csv', index=False)
    print("Raw events saved → backtests/gap_momentum_no_earnings_raw.csv")

    # ── Summary tables ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESULTS MATRIX")
    print("=" * 70)

    for hold in HOLD_DAYS:
        print_matrix(df_all, hold, GAP_THRESHOLDS, VOL_THRESHOLDS)

    # ── PEM benchmark (gap≥8%, vol≥3x, hold=1d intraday) ────────────
    print("\n" + "=" * 70)
    print("COMPARISON: Current PEM params (gap≥8%, vol≥3x)")
    print("=" * 70)
    for hold in [0] + HOLD_DAYS:
        col = 'ret_0d' if hold == 0 else f'ret_{hold}d'
        sub = df_all[(df_all['gap_pct'] >= 8.0) & (df_all['vol_ratio'] >= 3.0)].copy()
        sub = sub[sub[col].notna()] if col in sub.columns else pd.DataFrame()
        if sub.empty:
            continue
        wr = (sub[col] > 0).mean() * 100
        avg = sub[col].mean()
        label = 'intraday' if hold == 0 else f'{hold}d hold'
        print(f"  {label:<12}: n={len(sub):4d} | WR={wr:5.1f}% | avg={avg:+5.2f}% | "
              f"median={sub[col].median():+.2f}% | worst={sub[col].min():+.1f}%")

    # ── Best parameter combos ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("TOP 10 PARAMETER COMBOS (by avg return, min 10 events)")
    print("=" * 70)

    all_stats = []
    for g in GAP_THRESHOLDS:
        for v in VOL_THRESHOLDS:
            for h in HOLD_DAYS:
                s = analyze(df_all, g, v, h)
                if s and s['n'] >= 10:
                    all_stats.append(s)

    if all_stats:
        top = sorted(all_stats, key=lambda x: x['avg'], reverse=True)[:10]
        print(f"  {'gap_min':<8} {'vol_min':<8} {'hold':<6} {'n':<6} {'WR%':<8} {'avg%':<8} {'epm':<6}")
        print("  " + "-" * 55)
        for s in top:
            print(f"  {s['gap_min']:.0f}%{'':<4} {s['vol_min']:.1f}x{'':<4} "
                  f"{s['hold']}d{'':<4} {s['n']:<6} {s['wr']:5.1f}%  "
                  f"{s['avg']:+5.2f}%  {s['epm']:4.1f}")

    # ── Gap size distribution ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("GAP SIZE DISTRIBUTION (all vol≥1.5x, hold 1d)")
    print("=" * 70)
    for lo, hi, label in [(5, 8, '5-8%'), (8, 10, '8-10%'), (10, 15, '10-15%'),
                          (15, 20, '15-20%'), (20, 999, '20%+')]:
        sub = df_all[
            (df_all['gap_pct'] >= lo) & (df_all['gap_pct'] < hi) &
            (df_all['vol_ratio'] >= 1.5) & df_all['ret_1d'].notna()
        ]
        if sub.empty:
            continue
        wr = (sub['ret_1d'] > 0).mean() * 100
        avg = sub['ret_1d'].mean()
        print(f"  {label:<8}: n={len(sub):4d} | WR={wr:5.1f}% | avg={avg:+5.2f}%")

    # ── Volume ratio effect ──────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VOLUME RATIO EFFECT (gap≥8%, hold 1d)")
    print("=" * 70)
    for lo, hi, label in [(1.5, 2, '1.5-2x'), (2, 3, '2-3x'), (3, 5, '3-5x'), (5, 999, '5x+')]:
        sub = df_all[
            (df_all['gap_pct'] >= 8.0) & (df_all['vol_ratio'] >= lo) &
            (df_all['vol_ratio'] < hi) & df_all['ret_1d'].notna()
        ]
        if sub.empty:
            continue
        wr = (sub['ret_1d'] > 0).mean() * 100
        avg = sub['ret_1d'].mean()
        print(f"  {label:<8}: n={len(sub):4d} | WR={wr:5.1f}% | avg={avg:+5.2f}%")

    # ── Intraday vs next-day ─────────────────────────────────────────
    print("\n" + "=" * 70)
    print("INTRADAY (open→close same day) vs NEXT-DAY (buy at open, sell D+1)")
    print("gap≥8%, vol≥3x")
    print("=" * 70)
    base = df_all[(df_all['gap_pct'] >= 8.0) & (df_all['vol_ratio'] >= 3.0)]
    for col, label in [('ret_0d', 'Intraday (D0)'), ('ret_1d', 'Next-day (D+1)')]:
        sub = base[base[col].notna()] if col in base.columns else pd.DataFrame()
        if sub.empty:
            continue
        wr = (sub[col] > 0).mean() * 100
        avg = sub[col].mean()
        med = sub[col].median()
        print(f"  {label:<18}: n={len(sub):4d} | WR={wr:5.1f}% | avg={avg:+5.2f}% | median={med:+.2f}%")

    # ── Save summary metrics ─────────────────────────────────────────
    metrics = {
        'total_raw_events': len(df_all),
        'symbols_with_events': df_all['symbol'].nunique(),
        'period': f'{START} to {END}',
        'pem_params_1d': {},
        'top_combos': [],
    }
    pem_sub = df_all[(df_all['gap_pct'] >= 8.0) & (df_all['vol_ratio'] >= 3.0) & df_all['ret_1d'].notna()]
    if not pem_sub.empty:
        metrics['pem_params_1d'] = {
            'n': len(pem_sub),
            'wr': round((pem_sub['ret_1d'] > 0).mean() * 100, 1),
            'avg': round(pem_sub['ret_1d'].mean(), 2),
            'median': round(pem_sub['ret_1d'].median(), 2),
        }
    if all_stats:
        metrics['top_combos'] = [
            {k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items()}
            for s in sorted(all_stats, key=lambda x: x['avg'], reverse=True)[:5]
        ]
    with open('backtests/gap_momentum_no_earnings_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2, default=str)
    print("\nMetrics saved → backtests/gap_momentum_no_earnings_metrics.json")
    print("=" * 70)


if __name__ == '__main__':
    main()
