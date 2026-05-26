"""
Phase 1 — Deep label exploration.

For top 10 candidate labels:
  - Per-year base rate stability
  - Per-sector breakdown (Tech/Healthcare/Energy/etc.)
  - Per-mcap bucket (Large >$10B / Mid $2-10B / Small <$2B)
  - Earnings-day filter impact (skip earnings → improvement?)
  - Label correlation matrix
  - Vol-adjusted base rate (calm vs stress regime by VIX)

Also CACHES forward returns + labels to pkl for Phase 2/3 use.

Output: backtests/results_swing/phase1_*.csv + phase1_report.md
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

DB = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
RESULTS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing')
CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
RESULTS.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)

# Top 10 candidate labels from Phase 0
CANDIDATE_LABELS = {
    'L_touch_1.5_in_5d':       {'target': 1.5, 'window': 5,  'dd': None},
    'L_touch_2_in_7d':         {'target': 2.0, 'window': 7,  'dd': None},
    'L_touch_3_in_14d':        {'target': 3.0, 'window': 14, 'dd': None},
    'L_touch_5_in_30d':        {'target': 5.0, 'window': 30, 'dd': None},
    'L_touch_2_in_5d':         {'target': 2.0, 'window': 5,  'dd': None},
    'L_touch_3_in_7d':         {'target': 3.0, 'window': 7,  'dd': None},
    'L_touch_5_dd-10_in_30d':  {'target': 5.0, 'window': 30, 'dd': -10.0},
    'L_touch_2_dd-5_in_5d':    {'target': 2.0, 'window': 5,  'dd': -5.0},
    'L_touch_3_in_5d':         {'target': 3.0, 'window': 5,  'dd': None},
    'L_touch_7_in_30d':        {'target': 7.0, 'window': 30, 'dd': None},
}


def load_daily():
    con = sqlite3.connect(str(DB))
    df = pd.read_sql(
        "SELECT symbol, date, open, high, low, close, volume "
        "FROM stock_daily_ohlc "
        "WHERE date >= '2020-01-01' "
        "ORDER BY symbol, date",
        con
    )
    con.close()
    df['date'] = pd.to_datetime(df['date'])
    return df


def load_fundamentals():
    con = sqlite3.connect(str(DB))
    df = pd.read_sql(
        "SELECT symbol, beta, market_cap, sector, industry, avg_volume "
        "FROM stock_fundamentals",
        con
    )
    con.close()
    df['mcap_bucket'] = pd.cut(
        df['market_cap'].fillna(0),
        bins=[0, 2e9, 10e9, 50e9, 1e15],
        labels=['Small', 'Mid', 'Large', 'Mega'],
    ).astype(str)
    return df


def load_earnings():
    """earnings_history: (symbol, report_date)."""
    con = sqlite3.connect(str(DB))
    df = pd.read_sql(
        "SELECT symbol, report_date FROM earnings_history "
        "WHERE report_date >= '2020-01-01'",
        con
    )
    con.close()
    df['report_date'] = pd.to_datetime(df['report_date'])
    return df


def load_macro():
    """VIX daily for regime classification."""
    con = sqlite3.connect(str(DB))
    df = pd.read_sql(
        "SELECT date, vix_close as vix FROM macro_snapshots "
        "WHERE date >= '2020-01-01' ORDER BY date",
        con
    )
    con.close()
    df['date'] = pd.to_datetime(df['date'])
    df['vix_regime'] = pd.cut(
        df['vix'].fillna(20),
        bins=[0, 15, 20, 25, 30, 100],
        labels=['Calm', 'Normal', 'Elevated', 'Stress', 'Crisis'],
    ).astype(str)
    return df


def compute_forward_extremes(df, windows=(3, 5, 7, 14, 30)):
    """Vectorized: pre-compute rolling forward max/min/close."""
    out = []
    for sym, g in df.groupby('symbol', sort=False):
        g = g.sort_values('date').reset_index(drop=True)
        closes = g['close'].values.astype(float)
        highs = g['high'].values.astype(float)
        lows = g['low'].values.astype(float)
        L = len(g)
        entry = closes

        for w in windows:
            # Future high in [i+1, i+w]
            # Using rolling on reversed series
            rev_high = pd.Series(highs[::-1]).rolling(w, min_periods=1).max().values[::-1]
            # Shift forward by 1 (exclude today)
            shifted_h = np.roll(rev_high, -1)
            shifted_h[-w:] = np.nan  # mask invalid

            rev_low = pd.Series(lows[::-1]).rolling(w, min_periods=1).min().values[::-1]
            shifted_l = np.roll(rev_low, -1)
            shifted_l[-w:] = np.nan

            # Close at day i+w (or last available)
            shifted_c = np.roll(closes, -w)
            shifted_c[-w:] = np.nan

            g[f'fhigh_pct_{w}d'] = (shifted_h - entry) / entry * 100
            g[f'flow_pct_{w}d'] = (shifted_l - entry) / entry * 100
            g[f'fclose_pct_{w}d'] = (shifted_c - entry) / entry * 100

        out.append(g)
    return pd.concat(out, ignore_index=True)


def compute_labels(df, label_defs):
    """Compute labels per definition."""
    for name, d in label_defs.items():
        h_col = f'fhigh_pct_{d["window"]}d'
        if d['dd'] is None:
            df[name] = (df[h_col] >= d['target']).astype(int)
        else:
            l_col = f'flow_pct_{d["window"]}d'
            df[name] = ((df[h_col] >= d['target']) & (df[l_col] >= d['dd'])).astype(int)
        # Mask invalid where forward window not available
        df.loc[df[h_col].isna(), name] = np.nan
    return df


def add_earnings_flag(df, earn_df, window_days=2):
    """Flag rows where earnings is within +/- window_days. Fast: expand earnings dates → merge."""
    # Build set of (symbol, date) where any earnings happens within window
    expanded = []
    for offset in range(-window_days, window_days + 1):
        tmp = earn_df[['symbol', 'report_date']].copy()
        tmp['date'] = tmp['report_date'] + pd.Timedelta(days=offset)
        expanded.append(tmp[['symbol', 'date']])
    flagged = pd.concat(expanded, ignore_index=True).drop_duplicates()
    flagged['has_earnings_nearby'] = 1
    df = df.merge(flagged, on=['symbol', 'date'], how='left')
    df['has_earnings_nearby'] = df['has_earnings_nearby'].fillna(0).astype(int)
    return df


def main():
    print("== Phase 1: Label Exploration ==")
    start = datetime.now()

    print("Loading data...")
    df = load_daily()
    funda = load_fundamentals()
    earn = load_earnings()
    macro = load_macro()
    print(f"  Daily: {len(df):,} rows")
    print(f"  Funda: {len(funda):,} symbols")
    print(f"  Earnings: {len(earn):,} events")
    print(f"  Macro: {len(macro):,} days")

    print("Computing forward extremes (5 windows)...")
    df = compute_forward_extremes(df, windows=(3, 5, 7, 14, 30))

    print("Computing labels...")
    df = compute_labels(df, CANDIDATE_LABELS)
    df['year'] = df['date'].dt.year

    print("Adding sector/mcap...")
    df = df.merge(funda[['symbol', 'sector', 'mcap_bucket', 'beta']], on='symbol', how='left')

    print("Adding VIX regime...")
    df = df.merge(macro[['date', 'vix', 'vix_regime']], on='date', how='left')

    print("Adding earnings flag (slow)...")
    df = add_earnings_flag(df, earn, window_days=2)

    print(f"\nFinal df shape: {df.shape}")

    # Cache full data with labels for Phase 2/3
    cache_path = CACHE / 'phase1_labeled_daily.pkl'
    print(f"Caching to {cache_path} ...")
    df.to_pickle(cache_path)
    print(f"  size: {cache_path.stat().st_size / 1e6:.1f} MB")

    # ====================
    # Analysis 1: Per-year base rate stability
    # ====================
    print("\n== Analysis 1: Per-year base rate ==")
    per_year = []
    for lab in CANDIDATE_LABELS:
        valid = df[df[lab].notna()]
        by_year = valid.groupby('year')[lab].agg(['mean', 'count']).reset_index()
        by_year['label'] = lab
        per_year.append(by_year)
    per_year_df = pd.concat(per_year, ignore_index=True)
    pivot_year = per_year_df.pivot(index='label', columns='year', values='mean').round(3)
    pivot_year['stddev'] = pivot_year.std(axis=1).round(4)
    pivot_year['min'] = pivot_year.iloc[:, :-1].min(axis=1).round(3)
    pivot_year['max'] = pivot_year.iloc[:, :-1].max(axis=1).round(3)
    pivot_year['range'] = (pivot_year['max'] - pivot_year['min']).round(3)
    pivot_year.to_csv(RESULTS / 'phase1_baserate_per_year.csv')
    print(pivot_year.to_string())

    # ====================
    # Analysis 2: Per-sector
    # ====================
    print("\n== Analysis 2: Per-sector base rate (top labels only) ==")
    top3 = ['L_touch_2_in_7d', 'L_touch_5_dd-10_in_30d', 'L_touch_3_in_7d']
    for lab in top3:
        valid = df[df[lab].notna() & df['sector'].notna()]
        by_sector = valid.groupby('sector')[lab].agg(['mean', 'count']).reset_index().round(3)
        by_sector = by_sector.sort_values('mean', ascending=False)
        print(f"\n  {lab}:")
        print(by_sector.to_string(index=False))
        by_sector['label'] = lab
        by_sector.to_csv(RESULTS / f'phase1_sector_{lab}.csv', index=False)

    # ====================
    # Analysis 3: Per-mcap
    # ====================
    print("\n== Analysis 3: Per-mcap bucket (top 3 labels) ==")
    for lab in top3:
        valid = df[df[lab].notna() & (df['mcap_bucket'] != 'nan')]
        by_mcap = valid.groupby('mcap_bucket')[lab].agg(['mean', 'count']).reset_index().round(3)
        print(f"\n  {lab}:")
        print(by_mcap.to_string(index=False))

    # ====================
    # Analysis 4: Earnings filter impact
    # ====================
    print("\n== Analysis 4: Earnings-day filter impact ==")
    earn_impact = []
    for lab in CANDIDATE_LABELS:
        valid = df[df[lab].notna()]
        rate_all = valid[lab].mean()
        rate_no_earn = valid[valid['has_earnings_nearby'] == 0][lab].mean()
        rate_earn = valid[valid['has_earnings_nearby'] == 1][lab].mean()
        earn_impact.append({
            'label': lab,
            'rate_all': round(rate_all, 4),
            'rate_no_earnings': round(rate_no_earn, 4),
            'rate_with_earnings': round(rate_earn, 4),
            'lift_from_filter': round((rate_no_earn - rate_all) * 100, 3),
            'n_all': len(valid),
            'n_no_earn': (valid['has_earnings_nearby'] == 0).sum(),
        })
    earn_df = pd.DataFrame(earn_impact)
    earn_df = earn_df.sort_values('lift_from_filter', ascending=False)
    earn_df.to_csv(RESULTS / 'phase1_earnings_filter.csv', index=False)
    print(earn_df.to_string(index=False))

    # ====================
    # Analysis 5: VIX regime
    # ====================
    print("\n== Analysis 5: VIX regime base rate (top 3 labels) ==")
    for lab in top3:
        valid = df[df[lab].notna() & df['vix_regime'].notna()]
        by_vix = valid.groupby('vix_regime')[lab].agg(['mean', 'count']).reset_index().round(3)
        order = ['Calm', 'Normal', 'Elevated', 'Stress', 'Crisis']
        by_vix = by_vix.set_index('vix_regime').reindex(order).reset_index()
        print(f"\n  {lab}:")
        print(by_vix.to_string(index=False))

    # ====================
    # Analysis 6: Label correlation
    # ====================
    print("\n== Analysis 6: Label correlation matrix ==")
    label_cols = list(CANDIDATE_LABELS.keys())
    corr = df[label_cols].corr().round(2)
    corr.to_csv(RESULTS / 'phase1_label_correlation.csv')
    print(corr.to_string())

    # ====================
    # Final ranking for Phase 2/3
    # ====================
    print("\n== Phase 1 → Pick top 5 labels for Phase 3 training ==")
    pick = []
    for lab in CANDIDATE_LABELS:
        valid = df[df[lab].notna()]
        rate_all = valid[lab].mean()
        rate_no_earn = valid[valid['has_earnings_nearby'] == 0][lab].mean()
        per_year_stability = pivot_year.loc[lab, 'stddev']
        # Pick if: rate 40-75% (good range), stable across years (stddev < 0.06), earnings filter helps
        pick.append({
            'label': lab,
            'base_rate': round(rate_all, 3),
            'rate_no_earnings': round(rate_no_earn, 3),
            'stddev_per_year': round(per_year_stability, 4),
            'earnings_lift': round((rate_no_earn - rate_all) * 100, 3),
        })
    pick_df = pd.DataFrame(pick)
    pick_df.to_csv(RESULTS / 'phase1_label_ranking.csv', index=False)

    print("\nFinal label ranking:")
    print(pick_df.to_string(index=False))

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n✅ Phase 1 done in {elapsed:.1f}s")


if __name__ == '__main__':
    main()
