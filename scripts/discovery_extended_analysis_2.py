#!/usr/bin/env python3
"""
Discovery Engine Extended Analysis — Part 2
=============================================
Deeper dives based on Part 1 findings:

1. Sector-restricted strategies (Utilities, Materials, Real Estate, Industrials)
2. The "random beats ranked" puzzle — investigate why
3. ATR <= 2.0 + sector-restricted deep analysis
4. Multi-day hold analysis (outcomes at day 1,2,3,4,5 separately)
5. Relaxed target: best WR>=65% + TP_hit(2%)>=60% + freq>=50% combos
6. Final recommendation with realistic constraints
"""

import sys
import os
import pickle
import sqlite3
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, '..'))
sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

DB_PATH = os.path.join(_PROJECT_ROOT, 'data', 'trade_history.db')
CACHE_PATH = os.path.join(_PROJECT_ROOT, 'data', 'discovery_backtest_cache.pkl')


def load_cache():
    with open(CACHE_PATH, 'rb') as f:
        data = pickle.load(f)
    return data


def load_sectors():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall()
    conn.close()
    return {r[0]: r[1] or 'Unknown' for r in rows}


def compute_rsi_series(close_df, period=14):
    delta = close_df.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_features(raw_data, sectors_map):
    """Compute all features and return flat DataFrame."""
    close_df = raw_data['Close']
    high_df = raw_data['High']
    low_df = raw_data['Low']
    vol_df = raw_data['Volume']

    symbols = [s for s in close_df.columns.tolist() if s != 'SPY']

    # RSI
    rsi_df = compute_rsi_series(close_df[symbols])

    # ATR%
    prev_close = close_df[symbols].shift(1)
    tr1 = high_df[symbols] - low_df[symbols]
    tr2 = (high_df[symbols] - prev_close).abs()
    tr3 = (low_df[symbols] - prev_close).abs()
    tr = tr1.copy()
    tr = tr.where(tr >= tr2, tr2)
    tr = tr.where(tr >= tr3, tr3)
    atr = tr.rolling(window=14, min_periods=14).mean()
    atr_pct_df = (atr / close_df[symbols]) * 100

    # Momentum
    mom5d_df = (close_df[symbols] / close_df[symbols].shift(5) - 1) * 100
    mom10d_df = (close_df[symbols] / close_df[symbols].shift(10) - 1) * 100
    mom20d_df = (close_df[symbols] / close_df[symbols].shift(20) - 1) * 100

    # Distance from 20d MA
    ma20 = close_df[symbols].rolling(20).mean()
    dist_from_20d_ma = (close_df[symbols] / ma20 - 1) * 100

    # Distance from 20d high
    high_20d = close_df[symbols].rolling(20).max()
    dist_from_20d_high = (close_df[symbols] / high_20d - 1) * 100

    # Volume ratio
    vol_ma20 = vol_df[symbols].rolling(20).mean()
    vol_ratio = vol_df[symbols] / vol_ma20.replace(0, np.nan)

    # Forward outcomes at each day
    fwd = {}
    for d in range(1, 6):
        fwd[d] = (close_df[symbols].shift(-d) / close_df[symbols] - 1) * 100

    # max_gain and max_dd over 5d
    fwd_stack = np.stack([fwd[d].values for d in range(1, 6)], axis=0)
    max_gain_5d_vals = np.nanmax(fwd_stack, axis=0)
    max_dd_5d_vals = np.nanmin(fwd_stack, axis=0)
    max_gain_5d = pd.DataFrame(max_gain_5d_vals, index=close_df.index, columns=symbols)
    max_dd_5d = pd.DataFrame(max_dd_5d_vals, index=close_df.index, columns=symbols)

    # Stack into flat DataFrame
    dates = close_df.index[40:-6]
    records = []

    for dt in dates:
        for sym in symbols:
            c = close_df.loc[dt, sym] if sym in close_df.columns else np.nan
            if pd.isna(c) or c <= 0:
                continue

            atr_v = atr_pct_df.loc[dt, sym] if sym in atr_pct_df.columns else np.nan
            if pd.isna(atr_v):
                continue

            rsi_v = rsi_df.loc[dt, sym] if sym in rsi_df.columns else np.nan
            m5d = mom5d_df.loc[dt, sym]
            m10d = mom10d_df.loc[dt, sym]
            m20d = mom20d_df.loc[dt, sym]
            d20ma = dist_from_20d_ma.loc[dt, sym]
            d20h = dist_from_20d_high.loc[dt, sym]
            vr = vol_ratio.loc[dt, sym]
            o5d = fwd[5].loc[dt, sym]
            mg5d = max_gain_5d.loc[dt, sym]
            md5d = max_dd_5d.loc[dt, sym]

            if pd.isna(rsi_v) or pd.isna(m5d) or pd.isna(o5d):
                continue

            rec = {
                'date': dt, 'symbol': sym, 'close': c,
                'atr_pct': atr_v, 'rsi': rsi_v,
                'mom5d': m5d, 'mom10d': m10d, 'mom20d': m20d,
                'dist_from_20d_ma': d20ma, 'dist_from_20d_high': d20h,
                'volume_ratio': vr,
                'outcome_5d': o5d, 'max_gain_5d': mg5d, 'max_dd_5d': md5d,
                'sector': sectors_map.get(sym, 'Unknown'),
            }

            # Per-day outcomes
            for d in range(1, 6):
                rec[f'outcome_{d}d'] = fwd[d].loc[dt, sym]

            records.append(rec)

    return pd.DataFrame(records)


# ══════════════════════════════════════════════════════════
# ANALYSIS A: Sector-restricted strategies
# ══════════════════════════════════════════════════════════

def analysis_sector_restricted(df):
    print("\n" + "#"*120)
    print("#  ANALYSIS A: SECTOR-RESTRICTED STRATEGIES")
    print("#  Test best filters on top-WR sector groups")
    print("#"*120)

    total_days = df['date'].nunique()

    # Define sector groups based on Part 1 findings
    broad_map = {}
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
    for broad, subs in sector_groups.items():
        for s in subs:
            broad_map[s] = broad

    df['broad_sector'] = df['sector'].map(broad_map).fillna('Other')

    # Best sector groups from Part 1: Utilities (WR=71.4%), Materials (63.5%), Real_Estate (63.5%), Industrial (62.5%)
    sector_combos = [
        ("Utilities only", ['Utilities']),
        ("Utilities + Materials", ['Utilities', 'Materials']),
        ("Utilities + Materials + Real_Estate", ['Utilities', 'Materials', 'Real_Estate']),
        ("Utilities + Materials + Real_Estate + Industrial", ['Utilities', 'Materials', 'Real_Estate', 'Industrial']),
        ("Utilities + Materials + Industrial", ['Utilities', 'Materials', 'Industrial']),
        ("Utilities + Real_Estate", ['Utilities', 'Real_Estate']),
        ("Utilities + Industrial", ['Utilities', 'Industrial']),
        ("Top 6 (Util+Mat+RE+Ind+Other+HC)", ['Utilities', 'Materials', 'Real_Estate', 'Industrial', 'Other', 'Healthcare']),
        ("Top 8 (excl Tech+Media)", ['Utilities', 'Materials', 'Real_Estate', 'Industrial', 'Other', 'Healthcare', 'Energy', 'Consumer_Defensive']),
        ("ALL sectors", list(sector_groups.keys()) + ['Other']),
    ]

    filter_configs = [
        ("mom5d<-3", lambda d: d['mom5d'] < -3),
        ("mom5d<-5", lambda d: d['mom5d'] < -5),
        ("mom5d<-3 + rsi<45", lambda d: (d['mom5d'] < -3) & (d['rsi'] < 45)),
        ("mom5d<-5 + rsi<45", lambda d: (d['mom5d'] < -5) & (d['rsi'] < 45)),
        ("mom5d<-3 + rsi<40", lambda d: (d['mom5d'] < -3) & (d['rsi'] < 40)),
        ("mom5d<-5 + rsi<40", lambda d: (d['mom5d'] < -5) & (d['rsi'] < 40)),
        ("mom5d<-3 + dist20ma<-3", lambda d: (d['mom5d'] < -3) & (d['dist_from_20d_ma'] < -3)),
    ]

    for atr_max in [2.5, 3.0]:
        print(f"\n  === ATR <= {atr_max}% ===")
        print(f"  {'Sectors':<50} {'Filter':<30} {'n':>6} {'days':>5} {'freq%':>6} {'#stk':>5} {'WR%':>6} {'TP2%':>6} {'TP1.5':>6} {'E[pnl]':>7}")
        print(f"  {'-'*50} {'-'*30} {'-'*6} {'-'*5} {'-'*6} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*7}")

        for sec_name, sec_list in sector_combos:
            base = df[(df['atr_pct'] <= atr_max) & (df['broad_sector'].isin(sec_list))]
            if len(base) < 20:
                continue

            for filt_name, filt_fn in filter_configs:
                subset = base[filt_fn(base)]
                n = len(subset)
                if n < 20:
                    continue
                n_days = subset['date'].nunique()
                freq = n_days / total_days * 100
                n_stocks = subset['symbol'].nunique()
                wr = (subset['outcome_5d'] > 0).mean() * 100
                tp2 = (subset['max_gain_5d'] >= 2.0).mean() * 100
                tp15 = (subset['max_gain_5d'] >= 1.5).mean() * 100
                epnl = subset['outcome_5d'].mean()

                # Only print interesting ones
                if wr >= 60 or (sec_name == "ALL sectors" and filt_name in ["mom5d<-3", "mom5d<-5"]):
                    marker = " ***" if wr >= 70 else (" **" if wr >= 65 else "")
                    print(
                        f"  {sec_name:<50} {filt_name:<30} {n:>6} {n_days:>5} {freq:>5.1f}% {n_stocks:>5} "
                        f"{wr:>5.1f}% {tp2:>5.1f}% {tp15:>5.1f}% {epnl:>+6.2f}%{marker}"
                    )


# ══════════════════════════════════════════════════════════
# ANALYSIS B: Why does random beat ranked?
# ══════════════════════════════════════════════════════════

def analysis_random_vs_ranked(df):
    print("\n" + "#"*120)
    print("#  ANALYSIS B: WHY RANDOM BEATS RANKED")
    print("#  Investigating the anti-predictive ranking phenomenon")
    print("#"*120)

    base = df[(df['atr_pct'] <= 3.0) & (df['mom5d'] < -3)].copy()
    total_days = base['date'].nunique()

    # Bucket by mom5d quintiles within each day
    print(f"\n  Within filter (ATR<=3.0 + mom5d<-3), performance by mom5d quintile:")
    print(f"  (Q1=most negative mom5d, Q5=least negative)")

    # Assign quintile within each day
    def assign_quintile(group, col, ascending=True):
        n = len(group)
        if n < 5:
            group['quintile'] = 3
            return group
        ranks = group[col].rank(ascending=ascending, method='first')
        group['quintile'] = pd.cut(ranks, bins=5, labels=[1,2,3,4,5]).astype(int)
        return group

    base_q = base.groupby('date', group_keys=False).apply(lambda g: assign_quintile(g, 'mom5d', ascending=True))

    print(f"\n  Mom5d quintiles (Q1=deepest dip):")
    print(f"  {'Q':>3} {'n':>6} {'mean_mom5d':>12} {'mean_rsi':>10} {'mean_atr':>10} {'WR%':>6} {'TP2%':>6} {'E[pnl]':>7}")
    for q in range(1, 6):
        qdata = base_q[base_q['quintile'] == q]
        n = len(qdata)
        if n < 10:
            continue
        m5d = qdata['mom5d'].mean()
        rsi = qdata['rsi'].mean()
        atr = qdata['atr_pct'].mean()
        wr = (qdata['outcome_5d'] > 0).mean() * 100
        tp2 = (qdata['max_gain_5d'] >= 2.0).mean() * 100
        epnl = qdata['outcome_5d'].mean()
        print(f"  Q{q:1d} {n:>6} {m5d:>+11.2f}% {rsi:>9.1f} {atr:>9.2f}% {wr:>5.1f}% {tp2:>5.1f}% {epnl:>+6.2f}%")

    # Same for RSI quintiles
    base_r = base.groupby('date', group_keys=False).apply(lambda g: assign_quintile(g, 'rsi', ascending=True))

    print(f"\n  RSI quintiles (Q1=lowest RSI):")
    print(f"  {'Q':>3} {'n':>6} {'mean_rsi':>10} {'mean_mom5d':>12} {'WR%':>6} {'TP2%':>6} {'E[pnl]':>7}")
    for q in range(1, 6):
        qdata = base_r[base_r['quintile'] == q]
        n = len(qdata)
        if n < 10:
            continue
        rsi = qdata['rsi'].mean()
        m5d = qdata['mom5d'].mean()
        wr = (qdata['outcome_5d'] > 0).mean() * 100
        tp2 = (qdata['max_gain_5d'] >= 2.0).mean() * 100
        epnl = qdata['outcome_5d'].mean()
        print(f"  Q{q:1d} {n:>6} {rsi:>9.1f} {m5d:>+11.2f}% {wr:>5.1f}% {tp2:>5.1f}% {epnl:>+6.2f}%")

    # Same for ATR% quintiles
    base_a = base.groupby('date', group_keys=False).apply(lambda g: assign_quintile(g, 'atr_pct', ascending=True))

    print(f"\n  ATR% quintiles (Q1=lowest ATR):")
    print(f"  {'Q':>3} {'n':>6} {'mean_atr':>10} {'mean_mom5d':>12} {'WR%':>6} {'TP2%':>6} {'E[pnl]':>7}")
    for q in range(1, 6):
        qdata = base_a[base_a['quintile'] == q]
        n = len(qdata)
        if n < 10:
            continue
        atr = qdata['atr_pct'].mean()
        m5d = qdata['mom5d'].mean()
        wr = (qdata['outcome_5d'] > 0).mean() * 100
        tp2 = (qdata['max_gain_5d'] >= 2.0).mean() * 100
        epnl = qdata['outcome_5d'].mean()
        print(f"  Q{q:1d} {n:>6} {atr:>9.2f}% {m5d:>+11.2f}% {wr:>5.1f}% {tp2:>5.1f}% {epnl:>+6.2f}%")

    # Key insight: the deepest dips might be falling knives
    print(f"\n  --- Falling knife analysis ---")
    print(f"  mom5d < -10: is it a bounce or more fall?")
    deep = base[base['mom5d'] < -10]
    mod = base[(base['mom5d'] >= -10) & (base['mom5d'] < -5)]
    light = base[(base['mom5d'] >= -5) & (base['mom5d'] < -3)]

    for label, data in [("Deep dip (mom5d<-10)", deep), ("Moderate (-10 to -5)", mod), ("Light (-5 to -3)", light)]:
        n = len(data)
        if n < 10:
            continue
        wr = (data['outcome_5d'] > 0).mean() * 100
        tp2 = (data['max_gain_5d'] >= 2.0).mean() * 100
        epnl = data['outcome_5d'].mean()
        sl3 = (data['max_dd_5d'] <= -3.0).mean() * 100
        sl5 = (data['max_dd_5d'] <= -5.0).mean() * 100
        print(f"  {label:<30}: n={n:>5}, WR={wr:>5.1f}%, TP2={tp2:>5.1f}%, E[pnl]={epnl:>+5.2f}%, SL3hit={sl3:>5.1f}%, SL5hit={sl5:>5.1f}%")


# ══════════════════════════════════════════════════════════
# ANALYSIS C: Multi-day hold analysis
# ══════════════════════════════════════════════════════════

def analysis_hold_period(df):
    print("\n" + "#"*120)
    print("#  ANALYSIS C: OPTIMAL HOLD PERIOD")
    print("#  Performance at day 1, 2, 3, 4, 5 for best filter")
    print("#"*120)

    filters = [
        ("ATR<=3.0 + mom5d<-5 (all sectors)", (df['atr_pct'] <= 3.0) & (df['mom5d'] < -5)),
        ("ATR<=3.0 + mom5d<-3 (all sectors)", (df['atr_pct'] <= 3.0) & (df['mom5d'] < -3)),
        ("ATR<=2.5 + mom5d<-5 (all sectors)", (df['atr_pct'] <= 2.5) & (df['mom5d'] < -5)),
        ("ATR<=2.0 + mom5d<-5 (all sectors)", (df['atr_pct'] <= 2.0) & (df['mom5d'] < -5)),
    ]

    for label, mask in filters:
        subset = df[mask]
        n = len(subset)
        if n < 20:
            continue

        print(f"\n  {label} (n={n})")
        print(f"  {'Day':>5} {'WR%':>6} {'Mean':>7} {'Median':>7} {'TP1.5%':>7} {'TP2.0%':>7} {'TP2.5%':>7} {'SL2%':>5} {'SL3%':>5}")

        for d in range(1, 6):
            col = f'outcome_{d}d'
            if col not in subset.columns:
                continue
            valid = subset[col].dropna()
            wr = (valid > 0).mean() * 100
            mean = valid.mean()
            med = valid.median()
            tp15 = (valid >= 1.5).mean() * 100
            tp20 = (valid >= 2.0).mean() * 100
            tp25 = (valid >= 2.5).mean() * 100
            sl2 = (valid <= -2.0).mean() * 100
            sl3 = (valid <= -3.0).mean() * 100
            print(f"  Day {d} {wr:>5.1f}% {mean:>+6.2f}% {med:>+6.2f}% {tp15:>6.1f}% {tp20:>6.1f}% {tp25:>6.1f}% {sl2:>4.1f}% {sl3:>4.1f}%")

        # Also show max_gain within different windows
        print(f"\n  Max gain within N days (cumulative):")
        for d in range(1, 6):
            cols = [f'outcome_{i}d' for i in range(1, d+1)]
            vals = subset[cols].values
            max_gain = np.nanmax(vals, axis=1)
            tp15 = (max_gain >= 1.5).mean() * 100
            tp20 = (max_gain >= 2.0).mean() * 100
            tp25 = (max_gain >= 2.5).mean() * 100
            mean_mg = np.nanmean(max_gain)
            print(f"    Within {d}d: TP1.5hit={tp15:>5.1f}%, TP2.0hit={tp20:>5.1f}%, TP2.5hit={tp25:>5.1f}%, mean_max_gain={mean_mg:>+5.2f}%")


# ══════════════════════════════════════════════════════════
# ANALYSIS D: Realistic signal count per day
# ══════════════════════════════════════════════════════════

def analysis_daily_breakdown(df):
    print("\n" + "#"*120)
    print("#  ANALYSIS D: DAILY SIGNAL COUNTS + ZERO-SIGNAL DAYS INVESTIGATION")
    print("#"*120)

    total_days = df['date'].nunique()
    all_dates = sorted(df['date'].unique())

    filter_configs = [
        ("ATR<=3.0 + mom5d<-5", (df['atr_pct'] <= 3.0) & (df['mom5d'] < -5)),
        ("ATR<=3.0 + mom5d<-3", (df['atr_pct'] <= 3.0) & (df['mom5d'] < -3)),
        ("ATR<=3.0 + mom5d<-2", (df['atr_pct'] <= 3.0) & (df['mom5d'] < -2)),
        ("ATR<=3.0 + mom5d<-1", (df['atr_pct'] <= 3.0) & (df['mom5d'] < -1)),
    ]

    for label, mask in filter_configs:
        subset = df[mask]
        daily = subset.groupby('date').size()
        full = pd.Series(0, index=all_dates)
        full.update(daily)

        zero_days = (full == 0).sum()
        low_days = ((full >= 1) & (full <= 3)).sum()
        med_days = ((full >= 4) & (full <= 10)).sum()
        high_days = (full > 10).sum()

        mean_sig = full.mean()
        median_sig = full.median()

        # When zero, what was the market doing?
        zero_dates = full[full == 0].index
        if len(zero_dates) > 0:
            # Check what mom5d looks like on zero days
            zero_data = df[df['date'].isin(zero_dates)]
            avg_mom5d_all = zero_data['mom5d'].mean()
        else:
            avg_mom5d_all = 0

        print(f"\n  {label}:")
        print(f"    Mean={mean_sig:.1f}/day, Median={median_sig:.0f}/day")
        print(f"    Zero-signal days: {zero_days} ({zero_days/total_days*100:.1f}%)")
        print(f"    1-3 signals: {low_days} ({low_days/total_days*100:.1f}%), 4-10: {med_days} ({med_days/total_days*100:.1f}%), 10+: {high_days} ({high_days/total_days*100:.1f}%)")
        if zero_days > 0:
            print(f"    Zero-signal days avg mom5d (all stocks): {avg_mom5d_all:+.2f}% (strong rally days where nothing dipped)")

    # For the recommended filter, show week-by-week signal counts
    print(f"\n  --- Weekly signal counts for ATR<=3.0 + mom5d<-3 ---")
    mask = (df['atr_pct'] <= 3.0) & (df['mom5d'] < -3)
    subset = df[mask]
    subset_wk = subset.copy()
    subset_wk['week'] = subset_wk['date'].apply(lambda x: x.isocalendar()[:2])
    weekly = subset_wk.groupby('week').agg(
        n=('symbol', 'size'),
        days=('date', 'nunique'),
        wr=('outcome_5d', lambda x: (x > 0).mean() * 100),
        epnl=('outcome_5d', 'mean'),
    )
    print(f"  {'Week':>15} {'Signals':>8} {'Days':>5} {'Avg/day':>8} {'WR%':>6} {'E[pnl]':>7}")
    for idx, row in weekly.iterrows():
        avg_d = row['n'] / row['days'] if row['days'] > 0 else 0
        wk_str = f"{idx[0]}-W{idx[1]:02d}"
        print(f"  {wk_str:>15} {row['n']:>8.0f} {row['days']:>5.0f} {avg_d:>7.1f} {row['wr']:>5.1f}% {row['epnl']:>+6.2f}%")


# ══════════════════════════════════════════════════════════
# FINAL RECOMMENDATION
# ══════════════════════════════════════════════════════════

def final_recommendation(df):
    print("\n" + "#"*120)
    print("#  FINAL RECOMMENDATION: COMPREHENSIVE SWEEP")
    print("#  Realistic targets: WR>=62%, TP_hit(2%)>=50%, freq>=50%")
    print("#"*120)

    total_days = df['date'].nunique()

    # Broad sector groups
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
    broad_map = {}
    for broad, subs in sector_groups.items():
        for s in subs:
            broad_map[s] = broad
    df['broad_sector'] = df['sector'].map(broad_map).fillna('Other')

    # Sector sets to test
    sector_sets = {
        'ALL': list(sector_groups.keys()) + ['Other'],
        'NO_TECH_MEDIA': [s for s in sector_groups.keys() if s not in ['Technology', 'Media_Telecom']] + ['Other'],
        'TOP6': ['Utilities', 'Materials', 'Real_Estate', 'Industrial', 'Other', 'Healthcare'],
        'TOP4': ['Utilities', 'Materials', 'Real_Estate', 'Industrial'],
        'DEFENSIVE': ['Utilities', 'Consumer_Defensive', 'Real_Estate', 'Healthcare'],
    }

    all_configs = []

    for sec_name, sec_list in sector_sets.items():
        sec_data = df[df['broad_sector'].isin(sec_list)]

        for atr_max in [2.0, 2.5, 3.0, 3.5]:
            for mom5d_max in [-1, -2, -3, -4, -5, -7]:
                for rsi_max in [35, 40, 45, 50, 55, 60, 999]:  # 999 = no RSI filter
                    mask = (sec_data['atr_pct'] <= atr_max) & (sec_data['mom5d'] < mom5d_max)
                    if rsi_max < 999:
                        mask = mask & (sec_data['rsi'] < rsi_max)

                    subset = sec_data[mask]
                    n = len(subset)
                    if n < 30:
                        continue

                    n_days = subset['date'].nunique()
                    freq = n_days / total_days * 100
                    avg_per_day = n / n_days if n_days > 0 else 0
                    wr = (subset['outcome_5d'] > 0).mean() * 100
                    epnl = subset['outcome_5d'].mean()
                    n_stocks = subset['symbol'].nunique()

                    for tp in [1.5, 2.0, 2.5]:
                        tp_hit = (subset['max_gain_5d'] >= tp).mean() * 100
                        sl_hit_3 = (subset['max_dd_5d'] <= -3.0).mean() * 100

                        rsi_label = f"rsi<{rsi_max}" if rsi_max < 999 else "no_rsi"

                        all_configs.append({
                            'sectors': sec_name,
                            'atr_max': atr_max,
                            'mom5d_max': mom5d_max,
                            'rsi_filter': rsi_label,
                            'tp': tp,
                            'n': n, 'n_days': n_days, 'freq': freq,
                            'avg_per_day': avg_per_day,
                            'wr': wr, 'tp_hit': tp_hit, 'epnl': epnl,
                            'sl3_hit': sl_hit_3,
                            'n_stocks': n_stocks,
                        })

    # Apply SL-adjusted E[pnl] estimate:
    # E[adj_pnl] = tp_hit * TP - sl_hit * SL + (1 - tp_hit/100 - (1-wr/100)*sl_adjust) * remaining_avg
    # Simplified: use raw E[pnl]

    # Find best configs meeting different thresholds
    print(f"\n  Total configs tested: {len(all_configs):,}")

    # Sort by composite: freq * wr * epnl
    for target_name, wr_min, tp_hit_min, tp_val, freq_min in [
        ("STRICT (WR>=70, TP2hit>=70, freq>=30)", 70, 70, 2.0, 30),
        ("HIGH-WR (WR>=65, TP2hit>=55, freq>=50)", 65, 55, 2.0, 50),
        ("BALANCED (WR>=62, TP2hit>=50, freq>=70)", 62, 50, 2.0, 70),
        ("HIGH-FREQ (WR>=60, TP2hit>=45, freq>=90)", 60, 45, 2.0, 90),
        ("BEST E[pnl] (WR>=60, TP1.5hit>=60, freq>=40)", 60, 60, 1.5, 40),
    ]:
        filtered = [c for c in all_configs
                    if c['wr'] >= wr_min and c['tp_hit'] >= tp_hit_min
                    and c['tp'] == tp_val and c['freq'] >= freq_min]

        if not filtered:
            print(f"\n  {target_name}: NO CONFIG FOUND")
            continue

        # Sort by freq * epnl
        filtered.sort(key=lambda x: x['freq'] * max(x['epnl'], 0.01), reverse=True)

        print(f"\n  {target_name}: Top 5")
        print(f"  {'#':>3} {'Sectors':<20} {'ATR':>5} {'Mom5d':>6} {'RSI':>8} {'TP':>5} {'n':>6} {'days':>5} {'freq%':>6} {'avg/d':>6} {'WR%':>6} {'TPhit':>6} {'E[pnl]':>7} {'SL3%':>5} {'#stk':>5}")
        print(f"  {'-'*3} {'-'*20} {'-'*5} {'-'*6} {'-'*8} {'-'*5} {'-'*6} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*5} {'-'*5}")

        for i, c in enumerate(filtered[:5]):
            print(
                f"  {i+1:3d} {c['sectors']:<20} <={c['atr_max']:<4} <{c['mom5d_max']:>4} {c['rsi_filter']:>8} "
                f"{c['tp']:>4.1f}% {c['n']:>6} {c['n_days']:>5} {c['freq']:>5.1f}% {c['avg_per_day']:>5.1f} "
                f"{c['wr']:>5.1f}% {c['tp_hit']:>5.1f}% {c['epnl']:>+6.2f}% {c['sl3_hit']:>4.1f}% {c['n_stocks']:>5}"
            )

    # ABSOLUTE BEST by different optimization goals
    print(f"\n  {'='*100}")
    print(f"  OPTIMAL CONFIGS BY OPTIMIZATION GOAL (TP=2.0%)")
    print(f"  {'='*100}")

    tp2_configs = [c for c in all_configs if c['tp'] == 2.0 and c['n'] >= 50]

    for goal_name, sort_key in [
        ("Max E[pnl]", lambda x: x['epnl']),
        ("Max WR", lambda x: x['wr']),
        ("Max TP2 hit", lambda x: x['tp_hit']),
        ("Max frequency", lambda x: x['freq']),
        ("Max freq*WR product", lambda x: x['freq'] * x['wr']),
        ("Max freq*epnl product", lambda x: x['freq'] * max(x['epnl'], 0)),
        ("Max WR with freq>=80%", lambda x: x['wr'] if x['freq'] >= 80 else -999),
        ("Max WR with freq>=50%", lambda x: x['wr'] if x['freq'] >= 50 else -999),
    ]:
        best = max(tp2_configs, key=sort_key)
        if sort_key(best) <= -999:
            print(f"\n  {goal_name}: NO VALID CONFIG")
            continue
        print(
            f"\n  {goal_name}:"
            f"\n    {best['sectors']}, ATR<={best['atr_max']}, mom5d<{best['mom5d_max']}, {best['rsi_filter']}"
            f"\n    n={best['n']}, days={best['n_days']}/{total_days} ({best['freq']:.1f}%), avg/day={best['avg_per_day']:.1f}"
            f"\n    WR={best['wr']:.1f}%, TP2hit={best['tp_hit']:.1f}%, E[pnl]={best['epnl']:+.2f}%, SL3hit={best['sl3_hit']:.1f}%, #stocks={best['n_stocks']}"
        )

    # FINAL RECOMMENDED
    print(f"\n\n  {'*'*100}")
    print(f"  FINAL RECOMMENDED STRATEGY")
    print(f"  {'*'*100}")

    # The user wants: max frequency while keeping WR>=70% and TP_hit>=70% with TP>=2%
    # If impossible, find the Pareto front

    strict = [c for c in all_configs if c['wr'] >= 70 and c['tp_hit'] >= 70 and c['tp'] >= 2.0]
    if strict:
        strict.sort(key=lambda x: x['freq'], reverse=True)
        c = strict[0]
        print(f"\n  FOUND: meets WR>=70% + TP_hit(2%)>=70%")
    else:
        print(f"\n  IMPOSSIBLE to achieve WR>=70% + TP_hit(2%)>=70% simultaneously in this data.")
        print(f"  The fundamental tradeoff: deeper dips have higher TP_hit but include falling knives that lower WR.")
        print(f"")
        print(f"  PRACTICAL RECOMMENDATION (best Pareto-optimal config):")

        # Find Pareto front: maximize composite = freq * (wr/100) * (tp_hit/100)
        tp2_all = [c for c in all_configs if c['tp'] == 2.0 and c['n'] >= 50 and c['wr'] >= 60]
        tp2_all.sort(key=lambda x: x['freq'] * (x['wr']/100) * (x['tp_hit']/100) * max(x['epnl'], 0.01), reverse=True)
        c = tp2_all[0]

    filter_parts = [f"ATR <= {c['atr_max']}%", f"mom5d < {c['mom5d_max']}%"]
    if 'no_rsi' not in c['rsi_filter']:
        filter_parts.append(c['rsi_filter'].upper())
    filter_str = ' + '.join(filter_parts)

    sec_desc = c['sectors']
    if sec_desc == 'ALL':
        sec_desc = 'ALL sectors, ~' + str(c['n_stocks']) + ' stocks'
    elif sec_desc == 'NO_TECH_MEDIA':
        sec_desc = 'All excl Technology & Media, ~' + str(c['n_stocks']) + ' stocks'
    else:
        sec_desc += f', ~{c["n_stocks"]} stocks'

    print(f"""
RECOMMENDED STRATEGY:
  Universe: {sec_desc}
  Filter: {filter_str}
  TP: {c['tp']:.1f}%
  SL: 3.0% (SL3 hit rate = {c['sl3_hit']:.1f}%)
  WR: {c['wr']:.1f}%
  TP hit: {c['tp_hit']:.1f}%
  Signal frequency: {c['freq']:.1f}% of trading days
  Avg signals/day: {c['avg_per_day']:.1f}
  E[pnl]: {c['epnl']:+.2f}%
  n: {c['n']}
""")

    # Also show alternatives
    tp2_all = [c2 for c2 in all_configs if c2['tp'] == 2.0 and c2['n'] >= 50 and c2['wr'] >= 60]
    tp2_all.sort(key=lambda x: x['freq'] * (x['wr']/100) * (x['tp_hit']/100) * max(x['epnl'], 0.01), reverse=True)

    print(f"  ALTERNATIVES (TP=2.0%, WR>=60%, n>=50, sorted by freq*WR*TP*E[pnl] composite):")
    print(f"  {'#':>3} {'Sectors':<20} {'Filter':<35} {'freq%':>6} {'WR%':>6} {'TP2%':>6} {'E[pnl]':>7} {'n':>6}")
    print(f"  {'-'*3} {'-'*20} {'-'*35} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*6}")

    shown = set()
    count = 0
    for c2 in tp2_all[:50]:
        key = (c2['sectors'], c2['atr_max'], c2['mom5d_max'], c2['rsi_filter'])
        if key in shown:
            continue
        shown.add(key)
        count += 1
        if count > 15:
            break

        filt = f"atr<={c2['atr_max']} m5d<{c2['mom5d_max']} {c2['rsi_filter']}"
        print(
            f"  {count:3d} {c2['sectors']:<20} {filt:<35} {c2['freq']:>5.1f}% "
            f"{c2['wr']:>5.1f}% {c2['tp_hit']:>5.1f}% {c2['epnl']:>+6.2f}% {c2['n']:>6}"
        )


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    print("="*120)
    print("  DISCOVERY ENGINE EXTENDED ANALYSIS — PART 2")
    print("="*120)

    raw_data = load_cache()
    sectors_map = load_sectors()
    df = compute_features(raw_data, sectors_map)

    print(f"\n  Dataset: {len(df):,} observations, {df['symbol'].nunique()} stocks, {df['date'].nunique()} days")

    analysis_sector_restricted(df)
    analysis_random_vs_ranked(df)
    analysis_hold_period(df)
    analysis_daily_breakdown(df)
    final_recommendation(df)

    print("\n" + "="*120)
    print("  PART 2 ANALYSIS COMPLETE")
    print("="*120)


if __name__ == '__main__':
    main()
