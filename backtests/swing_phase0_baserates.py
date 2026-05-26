"""
Phase 0 — Compute base rates for swing label variants.

Loads daily OHLC, computes forward max/min returns for windows 3/5/7/14/30d,
then evaluates label variants. Outputs CSV with base rate per (label, year).

NO LOOKAHEAD: each row's label is computed from FUTURE bars (forward shift),
which means the label is what the FUTURE actually did — this is for training
purposes only. The features at scan time MUST NOT include future info.
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
OUT_CSV = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing/phase0_baserates.csv')
OUT_DIST = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing/phase0_forward_distribution.csv')


def load_daily():
    """Load daily OHLC + adjusted close."""
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
    print(f"Loaded {len(df):,} rows across {df['symbol'].nunique()} symbols")
    return df


def compute_forward_extremes(df, windows=(3, 5, 7, 14, 30)):
    """For each (symbol, date), compute:
       - fmax_Nd = max close gain within next N days (excluding today)
       - fmin_Nd = max close loss (DD) within next N days
       - fhigh_Nd = max(high) within next N days (intraday peak)
       - flow_Nd = min(low) within next N days (intraday trough)
       - fclose_Nd = close at exactly day N (or last available if shorter)
    """
    out = []
    n = len(df)
    for sym, g in df.groupby('symbol', sort=False):
        g = g.sort_values('date').reset_index(drop=True)
        closes = g['close'].values
        highs = g['high'].values
        lows = g['low'].values
        L = len(g)
        for w in windows:
            # forward window [i+1 .. i+w]
            fhigh = np.full(L, np.nan)
            flow = np.full(L, np.nan)
            fclose = np.full(L, np.nan)
            for i in range(L):
                end = min(i + w + 1, L)
                if end <= i + 1:
                    continue
                fhigh[i] = np.max(highs[i+1:end])
                flow[i] = np.min(lows[i+1:end])
                fclose[i] = closes[end-1]  # last available close in window
            entry = closes
            g[f'fhigh_pct_{w}d'] = (fhigh - entry) / entry * 100
            g[f'flow_pct_{w}d'] = (flow - entry) / entry * 100
            g[f'fclose_pct_{w}d'] = (fclose - entry) / entry * 100
        g['year'] = g['date'].dt.year
        out.append(g)
    return pd.concat(out, ignore_index=True)


def compute_labels(df):
    """Compute label variants. Each returns 0/1 series."""
    labels = {}

    # Group A: "touched +X% within Yd" (no DD constraint)
    for target, w in [(1.5, 3), (2.0, 3), (1.5, 5), (2.0, 5), (3.0, 5),
                       (2.0, 7), (3.0, 7), (5.0, 7),
                       (3.0, 14), (5.0, 14),
                       (5.0, 30), (7.0, 30), (10.0, 30)]:
        col = f'fhigh_pct_{w}d'
        if col in df.columns:
            labels[f'L_touch_{target:g}_in_{w}d'] = (df[col] >= target).astype(int)

    # Group B: "touched +X% AND DD better than -Y%" (risk-adjusted)
    for target, dd, w in [(2.0, -3.0, 5), (2.0, -5.0, 5),
                           (3.0, -3.0, 7), (3.0, -5.0, 7),
                           (5.0, -5.0, 14), (5.0, -7.0, 14),
                           (5.0, -10.0, 30), (7.0, -10.0, 30)]:
        h_col = f'fhigh_pct_{w}d'
        l_col = f'flow_pct_{w}d'
        if h_col in df.columns and l_col in df.columns:
            labels[f'L_touch_{target:g}_dd{dd:g}_in_{w}d'] = (
                (df[h_col] >= target) & (df[l_col] >= dd)
            ).astype(int)

    # Group C: "close +X% at exact day Y" (path independent)
    for target, w in [(3.0, 7), (5.0, 14), (5.0, 30), (10.0, 30)]:
        col = f'fclose_pct_{w}d'
        if col in df.columns:
            labels[f'L_close_{target:g}_at_{w}d'] = (df[col] >= target).astype(int)

    # Group D: "close green at day Y" (any positive)
    for w in [3, 5, 7, 14, 30]:
        col = f'fclose_pct_{w}d'
        if col in df.columns:
            labels[f'L_close_green_{w}d'] = (df[col] > 0).astype(int)

    # Group E: "first time touch +X% within Yd" → most reasonable
    # (same as touch — keep both for clarity; redundant)

    label_df = pd.DataFrame(labels)
    print(f"Computed {len(labels)} label variants")
    return label_df


def compute_base_rates(df, label_df):
    """Base rate per (label, year)."""
    out = []
    for lab in label_df.columns:
        valid = label_df[lab].notna() & df[label_df[lab].notna().index, ].index.notna() if False else label_df[lab].notna()
        # simpler: pair label with df['year']
        s = pd.DataFrame({'year': df['year'].values, 'label': label_df[lab].values})
        s = s.dropna()
        all_rate = s['label'].mean()
        by_year = s.groupby('year')['label'].agg(['mean', 'count']).reset_index()
        by_year['label_name'] = lab
        by_year['overall_rate'] = all_rate
        out.append(by_year)
    return pd.concat(out, ignore_index=True)


def main():
    print("== Phase 0: Base Rate Computation ==")
    df = load_daily()

    print("Computing forward extremes...")
    df = compute_forward_extremes(df, windows=(3, 5, 7, 14, 30))
    print(f"  → DataFrame: {df.shape}, cols: {[c for c in df.columns if c.startswith('f')]}")

    # Save forward distribution (raw fhigh/flow/fclose for visualization)
    dist_cols = ['symbol', 'date', 'year', 'close',
                 'fhigh_pct_3d', 'flow_pct_3d', 'fclose_pct_3d',
                 'fhigh_pct_5d', 'flow_pct_5d', 'fclose_pct_5d',
                 'fhigh_pct_7d', 'flow_pct_7d', 'fclose_pct_7d',
                 'fhigh_pct_14d', 'flow_pct_14d', 'fclose_pct_14d',
                 'fhigh_pct_30d', 'flow_pct_30d', 'fclose_pct_30d']
    dist_df = df[dist_cols].dropna(subset=['fhigh_pct_3d'])

    # Compute distribution percentiles per window
    dist_summary = []
    for w in [3, 5, 7, 14, 30]:
        for col in [f'fhigh_pct_{w}d', f'flow_pct_{w}d', f'fclose_pct_{w}d']:
            if col in dist_df.columns:
                vals = dist_df[col].dropna()
                if len(vals) > 0:
                    dist_summary.append({
                        'column': col,
                        'window_days': w,
                        'n': len(vals),
                        'mean': vals.mean(),
                        'median': vals.median(),
                        'p5': vals.quantile(0.05),
                        'p25': vals.quantile(0.25),
                        'p75': vals.quantile(0.75),
                        'p95': vals.quantile(0.95),
                        'p99': vals.quantile(0.99),
                    })
    dist_summ_df = pd.DataFrame(dist_summary)
    dist_summ_df.to_csv(OUT_DIST, index=False)
    print(f"Distribution summary → {OUT_DIST}")
    print(dist_summ_df.to_string(index=False))

    print("\nComputing labels...")
    label_df = compute_labels(df)

    print("\nComputing base rates...")
    base_rates = compute_base_rates(df, label_df)
    base_rates.to_csv(OUT_CSV, index=False)
    print(f"Base rates → {OUT_CSV}")

    # Print summary
    print("\n== Base Rate Summary (overall) ==")
    summary = base_rates.groupby('label_name').agg(
        overall=('overall_rate', 'first'),
        n_total=('count', 'sum'),
    ).reset_index()
    summary = summary.sort_values('overall', ascending=False)
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
