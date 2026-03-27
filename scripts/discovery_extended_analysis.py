#!/usr/bin/env python3
"""
Discovery Engine Extended Analysis
===================================
6 analyses to find the optimal mean-reversion strategy across all sectors.

Uses cached OHLCV data (1000 stocks, 288 days) + universe_stocks for sectors.
"""

import sys
import os
import pickle
import sqlite3
import warnings
from datetime import datetime
from collections import defaultdict
from itertools import combinations

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, '..'))
sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

DB_PATH = os.path.join(_PROJECT_ROOT, 'data', 'trade_history.db')
CACHE_PATH = os.path.join(_PROJECT_ROOT, 'data', 'discovery_backtest_cache.pkl')

# ══════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════

def load_cache():
    with open(CACHE_PATH, 'rb') as f:
        data = pickle.load(f)
    print(f"[Cache] Loaded {data.shape[0]} days x {data.shape[1]} cols")
    return data

def load_sectors():
    conn = None  # via get_session()
    rows = conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall()
    conn.close()
    return {r[0]: r[1] or 'Unknown' for r in rows}

# ══════════════════════════════════════════════════════════
# FEATURE COMPUTATION (vectorized)
# ══════════════════════════════════════════════════════════

def compute_rsi_series(close_df, period=14):
    """Compute RSI for all stocks at once."""
    delta = close_df.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_atr_pct_series(high_df, low_df, close_df, period=14):
    """Compute ATR% for all stocks at once."""
    prev_close = close_df.shift(1)
    tr1 = high_df - low_df
    tr2 = (high_df - prev_close).abs()
    tr3 = (low_df - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=0).groupby(level=0).max()
    # Simpler: element-wise max
    tr = tr1.copy()
    tr = tr.where(tr >= tr2, tr2)
    tr = tr.where(tr >= tr3, tr3)
    atr = tr.rolling(window=period, min_periods=period).mean()
    atr_pct = (atr / close_df) * 100
    return atr_pct

def compute_all_features(raw_data):
    """Compute all technical features for all stocks, all days. Returns a big DataFrame."""

    print("[Features] Extracting price data...")
    close_df = raw_data['Close']
    high_df = raw_data['High']
    low_df = raw_data['Low']
    vol_df = raw_data['Volume']

    symbols = close_df.columns.tolist()
    if 'SPY' in symbols:
        symbols.remove('SPY')

    print(f"[Features] Computing for {len(symbols)} stocks over {len(close_df)} days...")

    # RSI
    print("  Computing RSI...")
    rsi_df = compute_rsi_series(close_df[symbols])

    # ATR%
    print("  Computing ATR%...")
    atr_pct_df = compute_atr_pct_series(high_df[symbols], low_df[symbols], close_df[symbols])

    # Momentum 5d
    print("  Computing momentum features...")
    mom5d_df = (close_df[symbols] / close_df[symbols].shift(5) - 1) * 100
    mom10d_df = (close_df[symbols] / close_df[symbols].shift(10) - 1) * 100
    mom20d_df = (close_df[symbols] / close_df[symbols].shift(20) - 1) * 100

    # ROC 10d (same as mom10d but commonly named differently)
    roc10d_df = mom10d_df

    # Distance from 20d MA
    print("  Computing moving average distances...")
    ma20 = close_df[symbols].rolling(20).mean()
    dist_from_20d_ma = (close_df[symbols] / ma20 - 1) * 100

    # Distance from 20d high
    high_20d = close_df[symbols].rolling(20).max()
    dist_from_20d_high = (close_df[symbols] / high_20d - 1) * 100

    # Distance from 52w (252d) high
    high_252d = close_df[symbols].rolling(252, min_periods=60).max()
    dist_from_52w_high = (close_df[symbols] / high_252d - 1) * 100

    # Volume ratio
    print("  Computing volume ratio...")
    vol_ma20 = vol_df[symbols].rolling(20).mean()
    vol_ratio = vol_df[symbols] / vol_ma20.replace(0, np.nan)

    # Forward outcomes
    print("  Computing forward outcomes (5d)...")
    # outcome_5d = return from close today to close 5 days later
    fwd_1d = (close_df[symbols].shift(-1) / close_df[symbols] - 1) * 100
    fwd_2d = (close_df[symbols].shift(-2) / close_df[symbols] - 1) * 100
    fwd_3d = (close_df[symbols].shift(-3) / close_df[symbols] - 1) * 100
    fwd_4d = (close_df[symbols].shift(-4) / close_df[symbols] - 1) * 100
    fwd_5d = (close_df[symbols].shift(-5) / close_df[symbols] - 1) * 100

    # max_gain_5d and max_dd_5d
    fwd_stack = np.stack([fwd_1d.values, fwd_2d.values, fwd_3d.values, fwd_4d.values, fwd_5d.values], axis=0)
    max_gain_5d_vals = np.nanmax(fwd_stack, axis=0)
    max_dd_5d_vals = np.nanmin(fwd_stack, axis=0)

    max_gain_5d = pd.DataFrame(max_gain_5d_vals, index=close_df.index, columns=symbols)
    max_dd_5d = pd.DataFrame(max_dd_5d_vals, index=close_df.index, columns=symbols)
    outcome_5d = fwd_5d

    # Now stack everything into a flat DataFrame: (date, symbol) -> features
    print("  Stacking into flat DataFrame...")
    records = []
    dates = close_df.index[40:-6]  # skip first 40 (need lookback) and last 6 (need forward)

    for dt in dates:
        for sym in symbols:
            c = close_df.loc[dt, sym] if sym in close_df.columns else np.nan
            if pd.isna(c) or c <= 0:
                continue

            atr_v = atr_pct_df.loc[dt, sym] if sym in atr_pct_df.columns else np.nan
            if pd.isna(atr_v):
                continue

            rsi_v = rsi_df.loc[dt, sym] if sym in rsi_df.columns else np.nan
            m5d = mom5d_df.loc[dt, sym] if sym in mom5d_df.columns else np.nan
            m10d = mom10d_df.loc[dt, sym] if sym in mom10d_df.columns else np.nan
            m20d = mom20d_df.loc[dt, sym] if sym in mom20d_df.columns else np.nan
            d20ma = dist_from_20d_ma.loc[dt, sym] if sym in dist_from_20d_ma.columns else np.nan
            d20h = dist_from_20d_high.loc[dt, sym] if sym in dist_from_20d_high.columns else np.nan
            d52w = dist_from_52w_high.loc[dt, sym] if sym in dist_from_52w_high.columns else np.nan
            vr = vol_ratio.loc[dt, sym] if sym in vol_ratio.columns else np.nan
            o5d = outcome_5d.loc[dt, sym] if sym in outcome_5d.columns else np.nan
            mg5d = max_gain_5d.loc[dt, sym] if sym in max_gain_5d.columns else np.nan
            md5d = max_dd_5d.loc[dt, sym] if sym in max_dd_5d.columns else np.nan

            if pd.isna(rsi_v) or pd.isna(m5d) or pd.isna(o5d):
                continue

            records.append({
                'date': dt,
                'symbol': sym,
                'close': c,
                'atr_pct': atr_v,
                'rsi': rsi_v,
                'mom5d': m5d,
                'mom10d': m10d,
                'mom20d': m20d,
                'roc10d': m10d,
                'dist_from_20d_ma': d20ma,
                'dist_from_20d_high': d20h,
                'dist_from_52w_high': d52w,
                'volume_ratio': vr,
                'outcome_5d': o5d,
                'max_gain_5d': mg5d,
                'max_dd_5d': md5d,
            })

    df = pd.DataFrame(records)
    print(f"[Features] Built {len(df):,} stock-day observations")
    return df

# ══════════════════════════════════════════════════════════
# ANALYSIS HELPERS
# ══════════════════════════════════════════════════════════

def eval_filter(df, mask, tp_levels=[1.5, 2.0, 2.5, 3.0], label=""):
    """Evaluate a filter. Returns dict with stats for each TP level."""
    subset = df[mask].copy()
    n = len(subset)
    if n < 20:
        return None

    # How many unique days
    n_days = subset['date'].nunique()
    total_days = df['date'].nunique()
    freq_pct = n_days / total_days * 100
    avg_per_day = n / n_days if n_days > 0 else 0

    wr = (subset['outcome_5d'] > 0).mean() * 100
    epnl = subset['outcome_5d'].mean()

    results = {
        'label': label,
        'n': n,
        'n_days': n_days,
        'total_days': total_days,
        'freq_pct': freq_pct,
        'avg_per_day': avg_per_day,
        'wr': wr,
        'epnl': epnl,
        'avg_max_gain': subset['max_gain_5d'].mean(),
        'avg_max_dd': subset['max_dd_5d'].mean(),
    }

    for tp in tp_levels:
        tp_hit = (subset['max_gain_5d'] >= tp).mean() * 100
        results[f'tp_hit_{tp}'] = tp_hit

    # SL analysis
    for sl in [2.0, 3.0, 4.0]:
        sl_hit = (subset['max_dd_5d'] <= -sl).mean() * 100
        results[f'sl_hit_{sl}'] = sl_hit

    return results

def print_filter_results(results_list, sort_by='tp_hit_2.0', top_n=20, title=""):
    """Pretty-print filter results table."""
    if not results_list:
        print(f"\n  No results for {title}")
        return

    # Sort
    valid = [r for r in results_list if r is not None]
    valid.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

    print(f"\n{'='*120}")
    print(f"  {title}")
    print(f"  Sorted by {sort_by}, showing top {top_n}")
    print(f"{'='*120}")
    print(f"  {'#':>3} {'Filter':<55} {'n':>6} {'days':>5} {'freq%':>6} {'avg/d':>6} {'WR%':>6} {'TP1.5':>6} {'TP2.0':>6} {'TP2.5':>6} {'TP3.0':>6} {'E[pnl]':>7} {'SL2%':>5} {'SL3%':>5}")
    print(f"  {'-'*3} {'-'*55} {'-'*6} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*5} {'-'*5}")

    for i, r in enumerate(valid[:top_n]):
        print(
            f"  {i+1:3d} {r['label']:<55} {r['n']:>6} {r['n_days']:>5} {r['freq_pct']:>5.1f}% "
            f"{r['avg_per_day']:>5.1f} {r['wr']:>5.1f}% "
            f"{r.get('tp_hit_1.5',0):>5.1f}% {r.get('tp_hit_2.0',0):>5.1f}% "
            f"{r.get('tp_hit_2.5',0):>5.1f}% {r.get('tp_hit_3.0',0):>5.1f}% "
            f"{r['epnl']:>+6.2f}% {r.get('sl_hit_2.0',0):>4.1f}% {r.get('sl_hit_3.0',0):>4.1f}%"
        )

# ══════════════════════════════════════════════════════════
# ANALYSIS 1: Expand to ALL sectors, ATR <= 3.0%
# ══════════════════════════════════════════════════════════

def analysis_1(df):
    print("\n" + "#"*120)
    print("#  ANALYSIS 1: ALL SECTORS, ATR <= 3.0%")
    print("#  Find filter combos with WR >= 75% AND TP_hit(2%) >= 75%")
    print("#"*120)

    base = df[df['atr_pct'] <= 3.0].copy()
    print(f"\n  Base universe (ATR<=3.0%): {len(base):,} stock-day observations, {base['symbol'].nunique()} unique stocks")

    results = []

    # Single feature filters
    single_filters = [
        ("mom5d < -5", base['mom5d'] < -5),
        ("mom5d < -3", base['mom5d'] < -3),
        ("mom5d < -7", base['mom5d'] < -7),
        ("mom5d < -10", base['mom5d'] < -10),
        ("mom10d < -5", base['mom10d'] < -5),
        ("mom10d < -8", base['mom10d'] < -8),
        ("mom10d < -10", base['mom10d'] < -10),
        ("mom20d < -10", base['mom20d'] < -10),
        ("mom20d < -15", base['mom20d'] < -15),
        ("dist_20d_ma < -3", base['dist_from_20d_ma'] < -3),
        ("dist_20d_ma < -5", base['dist_from_20d_ma'] < -5),
        ("dist_20d_ma < -7", base['dist_from_20d_ma'] < -7),
        ("dist_20d_high < -5", base['dist_from_20d_high'] < -5),
        ("dist_20d_high < -8", base['dist_from_20d_high'] < -8),
        ("dist_20d_high < -10", base['dist_from_20d_high'] < -10),
        ("rsi < 30", base['rsi'] < 30),
        ("rsi < 35", base['rsi'] < 35),
        ("rsi < 40", base['rsi'] < 40),
        ("rsi < 45", base['rsi'] < 45),
        ("volume_ratio > 1.5", base['volume_ratio'] > 1.5),
        ("volume_ratio > 2.0", base['volume_ratio'] > 2.0),
        ("volume_ratio > 2.5", base['volume_ratio'] > 2.5),
        # Combination: dip + not in freefall
        ("mom5d [-5,-1] (bounce zone)", (base['mom5d'] >= -5) & (base['mom5d'] < -1)),
        ("mom5d [-8,-3] (deeper dip)", (base['mom5d'] >= -8) & (base['mom5d'] < -3)),
        ("rsi [25,40] + mom5d<-3", (base['rsi'] >= 25) & (base['rsi'] <= 40) & (base['mom5d'] < -3)),
        ("rsi [30,45] + mom5d<-3", (base['rsi'] >= 30) & (base['rsi'] <= 45) & (base['mom5d'] < -3)),
    ]

    for label, mask in single_filters:
        r = eval_filter(base, mask, label=label)
        if r:
            results.append(r)

    # Two-feature combos
    combo_filters = [
        # Dip + oversold
        ("mom5d<-5 + rsi<40", (base['mom5d'] < -5) & (base['rsi'] < 40)),
        ("mom5d<-5 + rsi<45", (base['mom5d'] < -5) & (base['rsi'] < 45)),
        ("mom5d<-3 + rsi<35", (base['mom5d'] < -3) & (base['rsi'] < 35)),
        ("mom5d<-3 + rsi<40", (base['mom5d'] < -3) & (base['rsi'] < 40)),
        ("mom5d<-3 + rsi<45", (base['mom5d'] < -3) & (base['rsi'] < 45)),
        ("mom5d<-7 + rsi<45", (base['mom5d'] < -7) & (base['rsi'] < 45)),

        # Dip + below MA
        ("mom5d<-5 + dist_20d_ma<-3", (base['mom5d'] < -5) & (base['dist_from_20d_ma'] < -3)),
        ("mom5d<-3 + dist_20d_ma<-3", (base['mom5d'] < -3) & (base['dist_from_20d_ma'] < -3)),
        ("mom5d<-5 + dist_20d_ma<-5", (base['mom5d'] < -5) & (base['dist_from_20d_ma'] < -5)),
        ("mom5d<-3 + dist_20d_ma<-5", (base['mom5d'] < -3) & (base['dist_from_20d_ma'] < -5)),

        # Dip + volume spike
        ("mom5d<-5 + vol>1.5", (base['mom5d'] < -5) & (base['volume_ratio'] > 1.5)),
        ("mom5d<-3 + vol>1.5", (base['mom5d'] < -3) & (base['volume_ratio'] > 1.5)),
        ("mom5d<-5 + vol>2.0", (base['mom5d'] < -5) & (base['volume_ratio'] > 2.0)),

        # RSI oversold + below MA
        ("rsi<35 + dist_20d_ma<-3", (base['rsi'] < 35) & (base['dist_from_20d_ma'] < -3)),
        ("rsi<40 + dist_20d_ma<-3", (base['rsi'] < 40) & (base['dist_from_20d_ma'] < -3)),
        ("rsi<40 + dist_20d_ma<-5", (base['rsi'] < 40) & (base['dist_from_20d_ma'] < -5)),
        ("rsi<45 + dist_20d_ma<-5", (base['rsi'] < 45) & (base['dist_from_20d_ma'] < -5)),

        # Distance from high combinations
        ("dist_20d_high<-8 + rsi<45", (base['dist_from_20d_high'] < -8) & (base['rsi'] < 45)),
        ("dist_20d_high<-5 + mom5d<-3", (base['dist_from_20d_high'] < -5) & (base['mom5d'] < -3)),
        ("dist_20d_high<-8 + mom5d<-5", (base['dist_from_20d_high'] < -8) & (base['mom5d'] < -5)),

        # ATR tighter
        ("atr<=2.0 + mom5d<-5", (base['atr_pct'] <= 2.0) & (base['mom5d'] < -5)),
        ("atr<=2.5 + mom5d<-5", (base['atr_pct'] <= 2.5) & (base['mom5d'] < -5)),
        ("atr<=2.0 + mom5d<-3", (base['atr_pct'] <= 2.0) & (base['mom5d'] < -3)),
        ("atr<=2.5 + mom5d<-3", (base['atr_pct'] <= 2.5) & (base['mom5d'] < -3)),
        ("atr<=1.5 + mom5d<-3", (base['atr_pct'] <= 1.5) & (base['mom5d'] < -3)),
    ]

    for label, mask in combo_filters:
        r = eval_filter(base, mask, label=label)
        if r:
            results.append(r)

    # Three-feature combos
    triple_filters = [
        ("mom5d<-5 + rsi<45 + atr<=2.5", (base['mom5d'] < -5) & (base['rsi'] < 45) & (base['atr_pct'] <= 2.5)),
        ("mom5d<-5 + rsi<45 + atr<=2.0", (base['mom5d'] < -5) & (base['rsi'] < 45) & (base['atr_pct'] <= 2.0)),
        ("mom5d<-3 + rsi<40 + atr<=2.5", (base['mom5d'] < -3) & (base['rsi'] < 40) & (base['atr_pct'] <= 2.5)),
        ("mom5d<-3 + rsi<40 + atr<=2.0", (base['mom5d'] < -3) & (base['rsi'] < 40) & (base['atr_pct'] <= 2.0)),
        ("mom5d<-5 + rsi<40 + dist_20d_ma<-3", (base['mom5d'] < -5) & (base['rsi'] < 40) & (base['dist_from_20d_ma'] < -3)),
        ("mom5d<-5 + rsi<45 + dist_20d_ma<-3", (base['mom5d'] < -5) & (base['rsi'] < 45) & (base['dist_from_20d_ma'] < -3)),
        ("mom5d<-3 + rsi<40 + dist_20d_ma<-3", (base['mom5d'] < -3) & (base['rsi'] < 40) & (base['dist_from_20d_ma'] < -3)),
        ("mom5d<-5 + rsi<45 + vol>1.5", (base['mom5d'] < -5) & (base['rsi'] < 45) & (base['volume_ratio'] > 1.5)),
        ("mom5d<-3 + rsi<40 + vol>1.5", (base['mom5d'] < -3) & (base['rsi'] < 40) & (base['volume_ratio'] > 1.5)),
        ("mom5d<-5 + atr<=2.5 + dist_20d_ma<-3", (base['mom5d'] < -5) & (base['atr_pct'] <= 2.5) & (base['dist_from_20d_ma'] < -3)),
        ("mom5d<-3 + atr<=2.5 + dist_20d_ma<-3", (base['mom5d'] < -3) & (base['atr_pct'] <= 2.5) & (base['dist_from_20d_ma'] < -3)),
        ("mom5d<-3 + atr<=2.0 + dist_20d_ma<-3", (base['mom5d'] < -3) & (base['atr_pct'] <= 2.0) & (base['dist_from_20d_ma'] < -3)),
        # Looser combos for frequency
        ("mom5d<-2 + rsi<45 + atr<=3.0", (base['mom5d'] < -2) & (base['rsi'] < 45) & (base['atr_pct'] <= 3.0)),
        ("mom5d<-2 + rsi<50 + atr<=2.5", (base['mom5d'] < -2) & (base['rsi'] < 50) & (base['atr_pct'] <= 2.5)),
        ("mom5d<-1 + rsi<45 + atr<=2.5", (base['mom5d'] < -1) & (base['rsi'] < 45) & (base['atr_pct'] <= 2.5)),
        ("mom5d<-1 + rsi<40 + atr<=2.5", (base['mom5d'] < -1) & (base['rsi'] < 40) & (base['atr_pct'] <= 2.5)),
        ("dist_20d_ma<-3 + rsi<40 + atr<=2.5", (base['dist_from_20d_ma'] < -3) & (base['rsi'] < 40) & (base['atr_pct'] <= 2.5)),
        ("dist_20d_ma<-2 + rsi<40 + atr<=2.5", (base['dist_from_20d_ma'] < -2) & (base['rsi'] < 40) & (base['atr_pct'] <= 2.5)),
        ("dist_20d_ma<-2 + rsi<45 + atr<=2.5", (base['dist_from_20d_ma'] < -2) & (base['rsi'] < 45) & (base['atr_pct'] <= 2.5)),
    ]

    for label, mask in triple_filters:
        r = eval_filter(base, mask, label=label)
        if r:
            results.append(r)

    # Print sorted by TP_hit 2.0%
    print_filter_results(results, sort_by='tp_hit_2.0', top_n=20,
                         title="ANALYSIS 1: ALL SECTORS ATR<=3.0% — Top 20 by TP_hit(2%)")

    # Also show those meeting BOTH WR>=75% AND TP_hit>=75% at TP=2%
    both_met = [r for r in results if r and r['wr'] >= 75 and r.get('tp_hit_2.0', 0) >= 75]
    if both_met:
        print_filter_results(both_met, sort_by='tp_hit_2.0', top_n=20,
                             title="ANALYSIS 1: Filters with WR>=75% AND TP_hit(2%)>=75%")
    else:
        print("\n  *** NO filter achieves BOTH WR>=75% AND TP_hit(2%)>=75% ***")
        # Show closest
        close_match = [r for r in results if r and r['wr'] >= 70 and r.get('tp_hit_2.0', 0) >= 70]
        if close_match:
            print_filter_results(close_match, sort_by='tp_hit_2.0', top_n=20,
                                 title="ANALYSIS 1: Closest — WR>=70% AND TP_hit(2%)>=70%")
        # Relax further
        close_match2 = [r for r in results if r and r['wr'] >= 65 and r.get('tp_hit_2.0', 0) >= 65]
        if close_match2:
            print_filter_results(close_match2, sort_by='tp_hit_2.0', top_n=20,
                                 title="ANALYSIS 1: Relaxed — WR>=65% AND TP_hit(2%)>=65%")

    return results, base

# ══════════════════════════════════════════════════════════
# ANALYSIS 2: TP sensitivity
# ══════════════════════════════════════════════════════════

def analysis_2(results):
    print("\n" + "#"*120)
    print("#  ANALYSIS 2: TP SENSITIVITY (1.5%, 2.0%, 2.5%, 3.0%)")
    print("#  Best filters from Analysis 1 — how TP_hit changes across TP levels")
    print("#"*120)

    # Pick top 15 by TP_hit 2.0 that have WR >= 60%
    valid = [r for r in results if r and r['wr'] >= 60]
    valid.sort(key=lambda x: x.get('tp_hit_2.0', 0), reverse=True)
    top = valid[:15]

    print(f"\n  {'Filter':<55} {'n':>6} {'WR%':>6}  {'TP1.5%':>7} {'TP2.0%':>7} {'TP2.5%':>7} {'TP3.0%':>7}  {'SL2%':>5} {'SL3%':>5} {'E[pnl]':>7}")
    print(f"  {'-'*55} {'-'*6} {'-'*6}  {'-'*7} {'-'*7} {'-'*7} {'-'*7}  {'-'*5} {'-'*5} {'-'*7}")

    for r in top:
        print(
            f"  {r['label']:<55} {r['n']:>6} {r['wr']:>5.1f}%  "
            f"{r.get('tp_hit_1.5',0):>6.1f}% {r.get('tp_hit_2.0',0):>6.1f}% "
            f"{r.get('tp_hit_2.5',0):>6.1f}% {r.get('tp_hit_3.0',0):>6.1f}%  "
            f"{r.get('sl_hit_2.0',0):>4.1f}% {r.get('sl_hit_3.0',0):>4.1f}% "
            f"{r['epnl']:>+6.2f}%"
        )

    # If no filter reaches TP_hit(2%)>=75%, try TP=1.5%
    best_tp2 = max(r.get('tp_hit_2.0', 0) for r in valid) if valid else 0
    if best_tp2 < 75:
        print(f"\n  NOTE: Best TP_hit(2.0%) = {best_tp2:.1f}% — below 75% target")
        best_tp15 = max(r.get('tp_hit_1.5', 0) for r in valid) if valid else 0
        print(f"  Best TP_hit(1.5%) = {best_tp15:.1f}%")

        # Show filters where TP_hit(1.5%)>=75% and WR>=70%
        tp15_good = [r for r in valid if r.get('tp_hit_1.5', 0) >= 75 and r['wr'] >= 70]
        if tp15_good:
            print_filter_results(tp15_good, sort_by='tp_hit_1.5', top_n=10,
                                 title="ANALYSIS 2: TP=1.5% with TP_hit>=75% and WR>=70%")

# ══════════════════════════════════════════════════════════
# ANALYSIS 3: Per-sector analysis
# ══════════════════════════════════════════════════════════

def analysis_3(df, sectors_map):
    print("\n" + "#"*120)
    print("#  ANALYSIS 3: PER-SECTOR MEAN-REVERSION PERFORMANCE")
    print("#  Which sectors have the best dip-bounce WR?")
    print("#"*120)

    # Add sector column
    df_sec = df.copy()
    df_sec['sector'] = df_sec['symbol'].map(sectors_map).fillna('Unknown')

    # Group sectors into broader categories for analysis
    sector_groups = {
        'Technology': ['Technology', 'Semiconductors'],
        'Healthcare': ['Healthcare_Pharma', 'Healthcare_Services', 'Healthcare_MedDevices', 'Healthcare'],
        'Finance': ['Finance_Banks', 'Finance_Insurance', 'Finance_Payments', 'Finance_Asset_Mgmt', 'Finance_Exchanges', 'Financial Services'],
        'Consumer_Cyclical': ['Consumer_Retail', 'Consumer_Travel', 'Consumer_Auto', 'Consumer Cyclical'],
        'Consumer_Defensive': ['Consumer_Staples', 'Consumer_Food', 'Consumer Defensive'],
        'Industrial': ['Industrial_Transport', 'Industrial_Conglomerate', 'Industrial_Machinery', 'Industrial_Aerospace', 'Industrials'],
        'Utilities': ['Utilities_Electric', 'Utilities_Gas', 'Utilities_Water', 'Utilities'],
        'Energy': ['Energy_Oil', 'Energy_Services', 'Energy_Midstream', 'Energy_Refining'],
        'Materials': ['Materials_Metals', 'Materials_Chemicals', 'Materials_Packaging', 'Materials_Construction', 'Basic Materials'],
        'Real_Estate': ['Real_Estate_Residential', 'Real_Estate_Retail', 'Real_Estate_Office', 'Real_Estate_Healthcare',
                       'Real_Estate_Data', 'Real_Estate_Industrial', 'Real_Estate_Storage'],
        'Media_Telecom': ['Media', 'Telecom', 'Communication Services'],
    }

    # Create broad sector mapping
    broad_map = {}
    for broad, subs in sector_groups.items():
        for s in subs:
            broad_map[s] = broad

    df_sec['broad_sector'] = df_sec['sector'].map(broad_map).fillna('Other')

    # Base filter: ATR <= 3.0% + mom5d < -3 (loose dip)
    base_mask = (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -3)
    dip_data = df_sec[base_mask].copy()

    print(f"\n  Using filter: ATR<=3.0% + mom5d<-3 (base dip)")
    print(f"  Total observations: {len(dip_data):,}")

    # Per broad-sector analysis
    print(f"\n  {'Broad Sector':<25} {'n':>6} {'WR%':>6} {'TP2%hit':>8} {'E[pnl]':>8} {'AvgGn':>7} {'AvgDD':>7} {'#stocks':>8}")
    print(f"  {'-'*25} {'-'*6} {'-'*6} {'-'*8} {'-'*8} {'-'*7} {'-'*7} {'-'*8}")

    sector_results = []
    for sec in sorted(dip_data['broad_sector'].unique()):
        sec_data = dip_data[dip_data['broad_sector'] == sec]
        n = len(sec_data)
        if n < 10:
            continue
        wr = (sec_data['outcome_5d'] > 0).mean() * 100
        tp2_hit = (sec_data['max_gain_5d'] >= 2.0).mean() * 100
        epnl = sec_data['outcome_5d'].mean()
        avg_gain = sec_data['max_gain_5d'].mean()
        avg_dd = sec_data['max_dd_5d'].mean()
        n_stocks = sec_data['symbol'].nunique()

        print(f"  {sec:<25} {n:>6} {wr:>5.1f}% {tp2_hit:>7.1f}% {epnl:>+7.2f}% {avg_gain:>+6.2f}% {avg_dd:>+6.2f}% {n_stocks:>8}")
        sector_results.append({
            'sector': sec,
            'n': n,
            'wr': wr,
            'tp2_hit': tp2_hit,
            'epnl': epnl,
            'n_stocks': n_stocks,
        })

    # Also per fine-grained sector (top 15 by WR)
    print(f"\n  Fine-grained sectors (top 15 by WR, n>=20):")
    print(f"  {'Sector':<30} {'n':>6} {'WR%':>6} {'TP2%hit':>8} {'E[pnl]':>8} {'#stocks':>8}")
    print(f"  {'-'*30} {'-'*6} {'-'*6} {'-'*8} {'-'*8} {'-'*8}")

    fine_results = []
    for sec in dip_data['sector'].unique():
        sec_data = dip_data[dip_data['sector'] == sec]
        n = len(sec_data)
        if n < 20:
            continue
        wr = (sec_data['outcome_5d'] > 0).mean() * 100
        tp2_hit = (sec_data['max_gain_5d'] >= 2.0).mean() * 100
        epnl = sec_data['outcome_5d'].mean()
        fine_results.append({'sector': sec, 'n': n, 'wr': wr, 'tp2_hit': tp2_hit, 'epnl': epnl, 'n_stocks': sec_data['symbol'].nunique()})

    fine_results.sort(key=lambda x: x['wr'], reverse=True)
    for r in fine_results[:15]:
        print(f"  {r['sector']:<30} {r['n']:>6} {r['wr']:>5.1f}% {r['tp2_hit']:>7.1f}% {r['epnl']:>+7.2f}% {r['n_stocks']:>8}")

    # Find optimal sector set
    print(f"\n  --- Finding optimal sector set ---")
    # Sort sectors by WR, greedily add sectors as long as combined WR stays above thresholds
    sorted_sectors = sorted(sector_results, key=lambda x: x['wr'], reverse=True)

    print(f"\n  Greedy sector accumulation (adding best WR first):")
    print(f"  {'Added Sector':<25} {'Cum n':>7} {'Cum WR':>7} {'Cum TP2':>8} {'Cum E[pnl]':>10}")

    included = []
    for sr in sorted_sectors:
        test_sectors = included + [sr['sector']]
        mask = dip_data['broad_sector'].isin(test_sectors)
        combo = dip_data[mask]
        n = len(combo)
        if n < 20:
            continue
        wr = (combo['outcome_5d'] > 0).mean() * 100
        tp2_hit = (combo['max_gain_5d'] >= 2.0).mean() * 100
        epnl = combo['outcome_5d'].mean()
        included.append(sr['sector'])
        print(f"  + {sr['sector']:<23} {n:>7} {wr:>6.1f}% {tp2_hit:>7.1f}% {epnl:>+9.2f}%")

    return df_sec, sector_results

# ══════════════════════════════════════════════════════════
# ANALYSIS 4: Signal frequency
# ══════════════════════════════════════════════════════════

def analysis_4(df, sectors_map):
    print("\n" + "#"*120)
    print("#  ANALYSIS 4: SIGNAL FREQUENCY")
    print("#  For various strategies, how many days per year have >= 1 signal?")
    print("#"*120)

    df_sec = df.copy()
    df_sec['sector'] = df_sec['symbol'].map(sectors_map).fillna('Unknown')

    strategies = [
        ("TIGHT: atr<=2.5 + mom5d<-5", (df_sec['atr_pct'] <= 2.5) & (df_sec['mom5d'] < -5)),
        ("MED:   atr<=3.0 + mom5d<-5", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -5)),
        ("MED:   atr<=3.0 + mom5d<-3", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -3)),
        ("LOOSE: atr<=3.0 + mom5d<-2", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -2)),
        ("LOOSE: atr<=3.0 + mom5d<-1", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -1)),
        ("TIGHT: atr<=2.5 + mom5d<-5 + rsi<45", (df_sec['atr_pct'] <= 2.5) & (df_sec['mom5d'] < -5) & (df_sec['rsi'] < 45)),
        ("MED:   atr<=3.0 + mom5d<-5 + rsi<45", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -5) & (df_sec['rsi'] < 45)),
        ("MED:   atr<=3.0 + mom5d<-3 + rsi<40", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -3) & (df_sec['rsi'] < 40)),
        ("MED:   atr<=3.0 + mom5d<-3 + rsi<45", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -3) & (df_sec['rsi'] < 45)),
        ("LOOSE: atr<=3.0 + mom5d<-2 + rsi<45", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -2) & (df_sec['rsi'] < 45)),
        ("LOOSE: atr<=3.0 + mom5d<-2 + rsi<50", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -2) & (df_sec['rsi'] < 50)),
        ("LOOSE: atr<=3.0 + mom5d<-1 + rsi<45", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -1) & (df_sec['rsi'] < 45)),
        ("WIDE:  atr<=3.0 + dist_20d_ma<-2", (df_sec['atr_pct'] <= 3.0) & (df_sec['dist_from_20d_ma'] < -2)),
        ("WIDE:  atr<=3.0 + dist_20d_ma<-3", (df_sec['atr_pct'] <= 3.0) & (df_sec['dist_from_20d_ma'] < -3)),
        ("MIX:   atr<=3.0 + (mom5d<-3 | dist_20d_ma<-3)", (df_sec['atr_pct'] <= 3.0) & ((df_sec['mom5d'] < -3) | (df_sec['dist_from_20d_ma'] < -3))),
        ("MIX:   atr<=3.0 + (mom5d<-2 | dist_20d_ma<-2)", (df_sec['atr_pct'] <= 3.0) & ((df_sec['mom5d'] < -2) | (df_sec['dist_from_20d_ma'] < -2))),
    ]

    total_days = df_sec['date'].nunique()

    print(f"\n  Total trading days in dataset: {total_days}")
    print(f"\n  {'Strategy':<55} {'n':>6} {'days':>5} {'freq%':>6} {'avg/d':>6} {'WR%':>6} {'TP2%':>6} {'E[pnl]':>7}")
    print(f"  {'-'*55} {'-'*6} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*7}")

    for label, mask in strategies:
        subset = df_sec[mask]
        n = len(subset)
        if n < 20:
            continue
        n_days = subset['date'].nunique()
        freq = n_days / total_days * 100
        avg_per_day = n / n_days if n_days > 0 else 0
        wr = (subset['outcome_5d'] > 0).mean() * 100
        tp2_hit = (subset['max_gain_5d'] >= 2.0).mean() * 100
        epnl = subset['outcome_5d'].mean()

        print(f"  {label:<55} {n:>6} {n_days:>5} {freq:>5.1f}% {avg_per_day:>5.1f} {wr:>5.1f}% {tp2_hit:>5.1f}% {epnl:>+6.2f}%")

    # Show daily signal count histogram for the medium strategy
    print(f"\n  --- Daily signal count distribution (atr<=3.0 + mom5d<-3) ---")
    mask_med = (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -3)
    med_data = df_sec[mask_med]
    daily_counts = med_data.groupby('date').size()

    all_dates = df_sec['date'].unique()
    full_daily = pd.Series(0, index=all_dates)
    full_daily.update(daily_counts)

    print(f"  Min: {full_daily.min()}, Max: {full_daily.max()}, Mean: {full_daily.mean():.1f}, Median: {full_daily.median():.0f}")

    for bucket_lo, bucket_hi in [(0,0), (1,2), (3,5), (6,10), (11,20), (21,50), (51,999)]:
        count = ((full_daily >= bucket_lo) & (full_daily <= bucket_hi)).sum()
        pct = count / len(full_daily) * 100
        label = f"{bucket_lo}-{bucket_hi}" if bucket_hi < 999 else f"{bucket_lo}+"
        print(f"    {label:>8} signals: {count:>4} days ({pct:>5.1f}%)")

# ══════════════════════════════════════════════════════════
# ANALYSIS 5: Ranking within signals
# ══════════════════════════════════════════════════════════

def analysis_5(df, sectors_map):
    print("\n" + "#"*120)
    print("#  ANALYSIS 5: RANKING WITHIN SIGNALS")
    print("#  When multiple stocks trigger, which ranking gives best WR for top picks?")
    print("#"*120)

    df_sec = df.copy()
    df_sec['sector'] = df_sec['symbol'].map(sectors_map).fillna('Unknown')

    # Use medium filter
    mask = (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -3)
    signals = df_sec[mask].copy()

    print(f"\n  Base filter: ATR<=3.0% + mom5d<-3")
    print(f"  Total signals: {len(signals):,}")

    # For each ranking method, pick top N per day
    ranking_methods = {
        'by mom5d (most negative first)': 'mom5d',
        'by dist_from_20d_ma (most negative)': 'dist_from_20d_ma',
        'by dist_from_20d_high (most negative)': 'dist_from_20d_high',
        'by RSI (lowest first)': 'rsi',
        'by ATR% (lowest first)': 'atr_pct',
        'by volume_ratio (highest first)': 'volume_ratio',
    }

    ascending_map = {
        'mom5d': True,
        'dist_from_20d_ma': True,
        'dist_from_20d_high': True,
        'rsi': True,
        'atr_pct': True,
        'volume_ratio': False,
    }

    # Also compute a composite score
    # Normalize each feature to [0,1] where 1=most dip-like
    signals['z_mom5d'] = (signals['mom5d'].max() - signals['mom5d']) / (signals['mom5d'].max() - signals['mom5d'].min() + 1e-6)
    signals['z_dist20ma'] = (signals['dist_from_20d_ma'].max() - signals['dist_from_20d_ma']) / (signals['dist_from_20d_ma'].max() - signals['dist_from_20d_ma'].min() + 1e-6)
    signals['z_rsi'] = (signals['rsi'].max() - signals['rsi']) / (signals['rsi'].max() - signals['rsi'].min() + 1e-6)
    signals['z_atr'] = (signals['atr_pct'].max() - signals['atr_pct']) / (signals['atr_pct'].max() - signals['atr_pct'].min() + 1e-6)
    signals['composite_rank'] = signals['z_mom5d'] * 0.4 + signals['z_dist20ma'] * 0.3 + signals['z_rsi'] * 0.2 + signals['z_atr'] * 0.1

    ranking_methods['by composite (mom40%+dist30%+rsi20%+atr10%)'] = 'composite_rank'
    ascending_map['composite_rank'] = False  # higher = better

    for top_n in [1, 3, 5, 10]:
        print(f"\n  === Top {top_n} picks per day ===")
        print(f"  {'Ranking Method':<55} {'n':>6} {'WR%':>6} {'TP2%':>6} {'E[pnl]':>7} {'AvgGn':>7} {'AvgDD':>7}")
        print(f"  {'-'*55} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*7}")

        for method_name, col in ranking_methods.items():
            asc = ascending_map[col]
            top_picks = signals.sort_values(['date', col], ascending=[True, asc]).groupby('date').head(top_n)

            n = len(top_picks)
            wr = (top_picks['outcome_5d'] > 0).mean() * 100
            tp2 = (top_picks['max_gain_5d'] >= 2.0).mean() * 100
            epnl = top_picks['outcome_5d'].mean()
            avg_gain = top_picks['max_gain_5d'].mean()
            avg_dd = top_picks['max_dd_5d'].mean()

            print(f"  {method_name:<55} {n:>6} {wr:>5.1f}% {tp2:>5.1f}% {epnl:>+6.2f}% {avg_gain:>+6.2f}% {avg_dd:>+6.2f}%")

        # Random baseline
        np.random.seed(42)
        random_picks = signals.groupby('date').apply(
            lambda x: x.sample(n=min(top_n, len(x)), random_state=42)
        ).reset_index(drop=True)
        n = len(random_picks)
        wr = (random_picks['outcome_5d'] > 0).mean() * 100
        tp2 = (random_picks['max_gain_5d'] >= 2.0).mean() * 100
        epnl = random_picks['outcome_5d'].mean()
        avg_gain = random_picks['max_gain_5d'].mean()
        avg_dd = random_picks['max_dd_5d'].mean()
        print(f"  {'RANDOM BASELINE':<55} {n:>6} {wr:>5.1f}% {tp2:>5.1f}% {epnl:>+6.2f}% {avg_gain:>+6.2f}% {avg_dd:>+6.2f}%")

# ══════════════════════════════════════════════════════════
# ANALYSIS 6: Two-tier system design
# ══════════════════════════════════════════════════════════

def analysis_6(df, sectors_map):
    print("\n" + "#"*120)
    print("#  ANALYSIS 6: TWO-TIER SYSTEM DESIGN")
    print("#"*120)

    df_sec = df.copy()
    df_sec['sector'] = df_sec['symbol'].map(sectors_map).fillna('Unknown')

    total_days = df_sec['date'].nunique()

    # ── Tier A: Strict mean-reversion ──
    print("\n  ═══ TIER A: Strict Mean-Reversion (target WR>=75%) ═══")

    tier_a_configs = [
        ("A1: atr<=2.5 + mom5d<-5 + rsi<40", (df_sec['atr_pct'] <= 2.5) & (df_sec['mom5d'] < -5) & (df_sec['rsi'] < 40)),
        ("A2: atr<=2.5 + mom5d<-7", (df_sec['atr_pct'] <= 2.5) & (df_sec['mom5d'] < -7)),
        ("A3: atr<=3.0 + mom5d<-5 + rsi<35", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -5) & (df_sec['rsi'] < 35)),
        ("A4: atr<=2.0 + mom5d<-5", (df_sec['atr_pct'] <= 2.0) & (df_sec['mom5d'] < -5)),
        ("A5: atr<=2.5 + mom5d<-5 + dist_20dma<-3", (df_sec['atr_pct'] <= 2.5) & (df_sec['mom5d'] < -5) & (df_sec['dist_from_20d_ma'] < -3)),
        ("A6: atr<=3.0 + mom5d<-7 + rsi<45", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -7) & (df_sec['rsi'] < 45)),
        ("A7: atr<=2.5 + mom5d<-5 + rsi<45", (df_sec['atr_pct'] <= 2.5) & (df_sec['mom5d'] < -5) & (df_sec['rsi'] < 45)),
        ("A8: atr<=3.0 + mom5d<-5 + rsi<40 + dist_20dma<-3", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -5) & (df_sec['rsi'] < 40) & (df_sec['dist_from_20d_ma'] < -3)),
        ("A9: atr<=3.0 + dist_20dh<-8 + rsi<40", (df_sec['atr_pct'] <= 3.0) & (df_sec['dist_from_20d_high'] < -8) & (df_sec['rsi'] < 40)),
        ("A10: atr<=3.0 + dist_20dma<-5 + rsi<40", (df_sec['atr_pct'] <= 3.0) & (df_sec['dist_from_20d_ma'] < -5) & (df_sec['rsi'] < 40)),
    ]

    print(f"\n  {'Config':<55} {'n':>6} {'days':>5} {'freq%':>6} {'WR%':>6} {'TP2%':>6} {'E[pnl]':>7}")
    print(f"  {'-'*55} {'-'*6} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7}")

    best_a = None
    for label, mask in tier_a_configs:
        subset = df_sec[mask]
        n = len(subset)
        if n < 20:
            continue
        n_days = subset['date'].nunique()
        freq = n_days / total_days * 100
        wr = (subset['outcome_5d'] > 0).mean() * 100
        tp2 = (subset['max_gain_5d'] >= 2.0).mean() * 100
        epnl = subset['outcome_5d'].mean()
        print(f"  {label:<55} {n:>6} {n_days:>5} {freq:>5.1f}% {wr:>5.1f}% {tp2:>5.1f}% {epnl:>+6.2f}%")

        if wr >= 70 and (best_a is None or epnl > best_a['epnl']):
            best_a = {'label': label, 'n': n, 'n_days': n_days, 'freq': freq, 'wr': wr, 'tp2': tp2, 'epnl': epnl, 'mask': mask}

    # ── Tier B: Looser quality scan ──
    print("\n  ═══ TIER B: Lighter Quality Scan (target WR>=60%, high frequency) ═══")

    tier_b_configs = [
        ("B1: atr<=3.0 + mom5d<-1 + rsi<50", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -1) & (df_sec['rsi'] < 50)),
        ("B2: atr<=3.0 + mom5d<-2 + rsi<50", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -2) & (df_sec['rsi'] < 50)),
        ("B3: atr<=3.0 + mom5d<-1 + rsi<45", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -1) & (df_sec['rsi'] < 45)),
        ("B4: atr<=3.0 + dist_20dma<-1 + rsi<50", (df_sec['atr_pct'] <= 3.0) & (df_sec['dist_from_20d_ma'] < -1) & (df_sec['rsi'] < 50)),
        ("B5: atr<=3.0 + dist_20dma<-2 + rsi<50", (df_sec['atr_pct'] <= 3.0) & (df_sec['dist_from_20d_ma'] < -2) & (df_sec['rsi'] < 50)),
        ("B6: atr<=3.0 + (mom5d<-1 | dist_20dma<-1) + rsi<50", (df_sec['atr_pct'] <= 3.0) & ((df_sec['mom5d'] < -1) | (df_sec['dist_from_20d_ma'] < -1)) & (df_sec['rsi'] < 50)),
        ("B7: atr<=3.0 + mom5d<-2", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -2)),
        ("B8: atr<=3.0 + dist_20dma<-2", (df_sec['atr_pct'] <= 3.0) & (df_sec['dist_from_20d_ma'] < -2)),
        ("B9: atr<=3.0 + mom5d<-1", (df_sec['atr_pct'] <= 3.0) & (df_sec['mom5d'] < -1)),
        ("B10: atr<=3.0 + dist_20dma<-1", (df_sec['atr_pct'] <= 3.0) & (df_sec['dist_from_20d_ma'] < -1)),
    ]

    print(f"\n  {'Config':<55} {'n':>6} {'days':>5} {'freq%':>6} {'WR%':>6} {'TP2%':>6} {'E[pnl]':>7}")
    print(f"  {'-'*55} {'-'*6} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7}")

    best_b = None
    for label, mask in tier_b_configs:
        subset = df_sec[mask]
        n = len(subset)
        if n < 20:
            continue
        n_days = subset['date'].nunique()
        freq = n_days / total_days * 100
        wr = (subset['outcome_5d'] > 0).mean() * 100
        tp2 = (subset['max_gain_5d'] >= 2.0).mean() * 100
        epnl = subset['outcome_5d'].mean()
        print(f"  {label:<55} {n:>6} {n_days:>5} {freq:>5.1f}% {wr:>5.1f}% {tp2:>5.1f}% {epnl:>+6.2f}%")

        if wr >= 60 and freq >= 70 and (best_b is None or epnl > best_b['epnl']):
            best_b = {'label': label, 'n': n, 'n_days': n_days, 'freq': freq, 'wr': wr, 'tp2': tp2, 'epnl': epnl, 'mask': mask}

    # ── Combined projection ──
    print("\n  ═══ COMBINED TWO-TIER PROJECTION ═══")
    if best_a:
        print(f"\n  Tier A (strict): {best_a['label']}")
        print(f"    n={best_a['n']}, days={best_a['n_days']}/{total_days} ({best_a['freq']:.1f}%), WR={best_a['wr']:.1f}%, TP2hit={best_a['tp2']:.1f}%, E[pnl]={best_a['epnl']:+.2f}%")
    else:
        print(f"\n  Tier A: No config meets WR>=70%")

    if best_b:
        print(f"\n  Tier B (quality): {best_b['label']}")
        print(f"    n={best_b['n']}, days={best_b['n_days']}/{total_days} ({best_b['freq']:.1f}%), WR={best_b['wr']:.1f}%, TP2hit={best_b['tp2']:.1f}%, E[pnl]={best_b['epnl']:+.2f}%")
    else:
        print(f"\n  Tier B: No config meets WR>=60%+freq>=70%")

    if best_a and best_b:
        # When both fire on same day, prefer Tier A
        a_days = set(df_sec[best_a['mask']]['date'].unique())
        b_days = set(df_sec[best_b['mask']]['date'].unique())
        overlap = a_days & b_days
        combined_days = a_days | b_days
        print(f"\n  Overlap: {len(overlap)} days where both tiers fire")
        print(f"  Combined coverage: {len(combined_days)}/{total_days} = {len(combined_days)/total_days*100:.1f}% of trading days")

    return best_a, best_b

# ══════════════════════════════════════════════════════════
# FINAL: Recommended strategy
# ══════════════════════════════════════════════════════════

def find_recommended(df, sectors_map):
    print("\n" + "#"*120)
    print("#  FINAL: RECOMMENDED STRATEGY")
    print("#  Maximize signal frequency while keeping WR>=70% and TP_hit>=70% with TP>=2%")
    print("#"*120)

    df_sec = df.copy()
    df_sec['sector'] = df_sec['symbol'].map(sectors_map).fillna('Unknown')
    total_days = df_sec['date'].nunique()

    # Systematic sweep of parameter space
    best = None
    all_results = []

    for atr_max in [2.0, 2.5, 3.0, 3.5]:
        for mom5d_max in [-1, -2, -3, -4, -5, -7]:
            for rsi_max in [35, 40, 45, 50, 55, 60]:
                mask = (df_sec['atr_pct'] <= atr_max) & (df_sec['mom5d'] < mom5d_max) & (df_sec['rsi'] < rsi_max)
                subset = df_sec[mask]
                n = len(subset)
                if n < 30:
                    continue
                n_days = subset['date'].nunique()
                freq = n_days / total_days * 100
                avg_per_day = n / n_days if n_days > 0 else 0
                wr = (subset['outcome_5d'] > 0).mean() * 100

                for tp in [1.5, 2.0, 2.5, 3.0]:
                    tp_hit = (subset['max_gain_5d'] >= tp).mean() * 100
                    epnl = subset['outcome_5d'].mean()

                    config = {
                        'atr_max': atr_max, 'mom5d_max': mom5d_max, 'rsi_max': rsi_max,
                        'tp': tp, 'n': n, 'n_days': n_days, 'freq': freq, 'avg_per_day': avg_per_day,
                        'wr': wr, 'tp_hit': tp_hit, 'epnl': epnl,
                        'n_stocks': subset['symbol'].nunique(),
                    }
                    all_results.append(config)

                    # Check if meets criteria: WR>=70, TP_hit>=70, TP>=2
                    if wr >= 70 and tp_hit >= 70 and tp >= 2.0:
                        if best is None or freq > best['freq'] or (freq == best['freq'] and epnl > best['epnl']):
                            best = config

    # Also try dist_from_20d_ma based filters
    for atr_max in [2.0, 2.5, 3.0, 3.5]:
        for dist_max in [-1, -2, -3, -4, -5]:
            for rsi_max in [35, 40, 45, 50, 55]:
                mask = (df_sec['atr_pct'] <= atr_max) & (df_sec['dist_from_20d_ma'] < dist_max) & (df_sec['rsi'] < rsi_max)
                subset = df_sec[mask]
                n = len(subset)
                if n < 30:
                    continue
                n_days = subset['date'].nunique()
                freq = n_days / total_days * 100
                avg_per_day = n / n_days if n_days > 0 else 0
                wr = (subset['outcome_5d'] > 0).mean() * 100

                for tp in [1.5, 2.0, 2.5, 3.0]:
                    tp_hit = (subset['max_gain_5d'] >= tp).mean() * 100
                    epnl = subset['outcome_5d'].mean()

                    config = {
                        'atr_max': atr_max, 'dist_max': dist_max, 'rsi_max': rsi_max,
                        'tp': tp, 'n': n, 'n_days': n_days, 'freq': freq, 'avg_per_day': avg_per_day,
                        'wr': wr, 'tp_hit': tp_hit, 'epnl': epnl,
                        'n_stocks': subset['symbol'].nunique(),
                        'filter_type': 'dist_20d_ma',
                    }

                    if wr >= 70 and tp_hit >= 70 and tp >= 2.0:
                        if best is None or freq > best['freq'] or (freq == best['freq'] and epnl > best['epnl']):
                            best = config

    # Also try combined mom5d OR dist_from_20d_ma
    for atr_max in [2.5, 3.0, 3.5]:
        for mom5d_max in [-2, -3, -4, -5]:
            for dist_max in [-2, -3, -4, -5]:
                for rsi_max in [40, 45, 50, 55]:
                    mask = (df_sec['atr_pct'] <= atr_max) & ((df_sec['mom5d'] < mom5d_max) | (df_sec['dist_from_20d_ma'] < dist_max)) & (df_sec['rsi'] < rsi_max)
                    subset = df_sec[mask]
                    n = len(subset)
                    if n < 30:
                        continue
                    n_days = subset['date'].nunique()
                    freq = n_days / total_days * 100
                    avg_per_day = n / n_days if n_days > 0 else 0
                    wr = (subset['outcome_5d'] > 0).mean() * 100

                    for tp in [1.5, 2.0, 2.5]:
                        tp_hit = (subset['max_gain_5d'] >= tp).mean() * 100
                        epnl = subset['outcome_5d'].mean()

                        config = {
                            'atr_max': atr_max, 'mom5d_max': mom5d_max, 'dist_max': dist_max, 'rsi_max': rsi_max,
                            'tp': tp, 'n': n, 'n_days': n_days, 'freq': freq, 'avg_per_day': avg_per_day,
                            'wr': wr, 'tp_hit': tp_hit, 'epnl': epnl,
                            'n_stocks': subset['symbol'].nunique(),
                            'filter_type': 'combined_or',
                        }

                        if wr >= 70 and tp_hit >= 70 and tp >= 2.0:
                            if best is None or freq > best['freq'] or (freq == best['freq'] and epnl > best['epnl']):
                                best = config

    if best:
        print(f"\n  FOUND strategy meeting WR>=70% + TP_hit>=70% + TP>=2.0%:")
        _print_recommended(best, total_days, df_sec)
    else:
        print(f"\n  NO strategy meets WR>=70% + TP_hit(>=2%)>=70% simultaneously.")
        print(f"\n  Relaxing constraints...")

        # Relax: WR>=65 + TP_hit>=65 + TP>=2.0
        best_relaxed = None
        for r in all_results:
            if r['wr'] >= 65 and r['tp_hit'] >= 65 and r['tp'] >= 2.0:
                if best_relaxed is None or r['freq'] > best_relaxed['freq']:
                    best_relaxed = r

        if best_relaxed:
            print(f"\n  Best with WR>=65% + TP_hit>=65% + TP>=2.0%:")
            _print_recommended(best_relaxed, total_days, df_sec)

        # Also show best for TP=2% with highest freq*wr*tp_hit
        candidates = [r for r in all_results if r['tp'] == 2.0 and r['wr'] >= 60 and r['tp_hit'] >= 60]
        if candidates:
            candidates.sort(key=lambda x: x['freq'] * x['wr'] * x['tp_hit'] / 10000, reverse=True)
            print(f"\n  Best by composite score (freq*WR*TP_hit) with WR>=60%+TP_hit>=60%+TP=2%:")
            _print_recommended(candidates[0], total_days, df_sec)

        # Show best for WR>=70 at any TP
        best_wr70 = None
        for r in all_results:
            if r['wr'] >= 70 and r['tp_hit'] >= 70:
                if best_wr70 is None or r['freq'] > best_wr70['freq']:
                    best_wr70 = r

        if best_wr70:
            print(f"\n  Best with WR>=70% + TP_hit>=70% (any TP):")
            _print_recommended(best_wr70, total_days, df_sec)

        # Show top 10 balanced strategies
        print(f"\n  --- Top 10 balanced strategies (TP=2.0%, sorted by freq*WR*TP_hit composite) ---")
        tp2_results = [r for r in all_results if r['tp'] == 2.0 and r['n'] >= 50]
        tp2_results.sort(key=lambda x: x['freq'] * x['wr'] * x['tp_hit'] / 10000, reverse=True)

        print(f"  {'#':>3} {'ATR':>5} {'Mom5d':>6} {'RSI':>5} {'n':>6} {'days':>5} {'freq%':>6} {'avg/d':>6} {'WR%':>6} {'TP2%':>6} {'E[pnl]':>7} {'Score':>7}")
        print(f"  {'-'*3} {'-'*5} {'-'*6} {'-'*5} {'-'*6} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7}")

        for i, r in enumerate(tp2_results[:10]):
            score = r['freq'] * r['wr'] * r['tp_hit'] / 10000
            mom_label = f"<{r.get('mom5d_max','?')}" if 'mom5d_max' in r else f"d<{r.get('dist_max','?')}"
            print(
                f"  {i+1:3d} <={r['atr_max']:<4} {mom_label:>6} <{r['rsi_max']:<4} "
                f"{r['n']:>6} {r['n_days']:>5} {r['freq']:>5.1f}% {r['avg_per_day']:>5.1f} "
                f"{r['wr']:>5.1f}% {r['tp_hit']:>5.1f}% {r['epnl']:>+6.2f}% {score:>6.1f}"
            )

        # Show top 10 with WR>=70 sorted by freq
        print(f"\n  --- Top 10 high-WR strategies (WR>=70%, any TP, sorted by frequency) ---")
        wr70 = [r for r in all_results if r['wr'] >= 70 and r['tp_hit'] >= 60 and r['n'] >= 30]
        wr70.sort(key=lambda x: x['freq'], reverse=True)

        print(f"  {'#':>3} {'ATR':>5} {'Filter':>10} {'RSI':>5} {'TP':>5} {'n':>6} {'days':>5} {'freq%':>6} {'WR%':>6} {'TP%':>6} {'E[pnl]':>7}")
        print(f"  {'-'*3} {'-'*5} {'-'*10} {'-'*5} {'-'*5} {'-'*6} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7}")

        for i, r in enumerate(wr70[:10]):
            if 'mom5d_max' in r:
                filt = f"m5d<{r['mom5d_max']}"
            elif 'dist_max' in r:
                filt = f"d20<{r['dist_max']}"
            else:
                filt = "?"
            print(
                f"  {i+1:3d} <={r['atr_max']:<4} {filt:>10} <{r['rsi_max']:<4} {r['tp']:>4.1f}% "
                f"{r['n']:>6} {r['n_days']:>5} {r['freq']:>5.1f}% "
                f"{r['wr']:>5.1f}% {r['tp_hit']:>5.1f}% {r['epnl']:>+6.2f}%"
            )

def _print_recommended(cfg, total_days, df_sec):
    ftype = cfg.get('filter_type', 'mom5d')
    if ftype == 'dist_20d_ma':
        filter_str = f"ATR <= {cfg['atr_max']}% + dist_from_20d_ma < {cfg['dist_max']}% + RSI < {cfg['rsi_max']}"
    elif ftype == 'combined_or':
        filter_str = f"ATR <= {cfg['atr_max']}% + (mom5d < {cfg['mom5d_max']}% OR dist_20d_ma < {cfg['dist_max']}%) + RSI < {cfg['rsi_max']}"
    else:
        filter_str = f"ATR <= {cfg['atr_max']}% + mom5d < {cfg['mom5d_max']}% + RSI < {cfg['rsi_max']}"

    # Compute SL stats
    sl2_hit = 0  # placeholder

    print(f"""
  ┌─────────────────────────────────────────────────────────────────┐
  │  RECOMMENDED STRATEGY                                          │
  ├─────────────────────────────────────────────────────────────────┤
  │  Universe: ALL sectors, ~{cfg['n_stocks']} stocks (from 1000)            │
  │  Filter:   {filter_str:<52}│
  │  TP:       {cfg['tp']:.1f}%                                              │
  │  WR:       {cfg['wr']:.1f}%                                              │
  │  TP hit:   {cfg['tp_hit']:.1f}%                                          │
  │  Signal frequency: {cfg['freq']:.1f}% of trading days                    │
  │  Avg signals/day:  {cfg['avg_per_day']:.1f}                              │
  │  E[pnl]:   {cfg['epnl']:+.2f}%                                          │
  │  n:        {cfg['n']}                                                    │
  └─────────────────────────────────────────────────────────────────┘""")

# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    print("="*120)
    print("  DISCOVERY ENGINE EXTENDED ANALYSIS")
    print("  Data: 1000 stocks, 288 trading days, all sectors")
    print("="*120)

    raw_data = load_cache()
    sectors_map = load_sectors()

    # Compute all features
    df = compute_all_features(raw_data)

    # Add sector
    df['sector'] = df['symbol'].map(sectors_map).fillna('Unknown')

    # Quick dataset stats
    print(f"\n  Dataset: {len(df):,} observations, {df['symbol'].nunique()} stocks, {df['date'].nunique()} days")
    print(f"  Date range: {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}")
    print(f"  ATR% range: {df['atr_pct'].min():.2f} to {df['atr_pct'].max():.2f}")
    print(f"  RSI range: {df['rsi'].min():.1f} to {df['rsi'].max():.1f}")

    # Run all analyses
    results_1, base = analysis_1(df)
    analysis_2(results_1)
    analysis_3(df, sectors_map)
    analysis_4(df, sectors_map)
    analysis_5(df, sectors_map)
    analysis_6(df, sectors_map)
    find_recommended(df, sectors_map)

    print("\n" + "="*120)
    print("  ANALYSIS COMPLETE")
    print("="*120)

if __name__ == '__main__':
    main()
