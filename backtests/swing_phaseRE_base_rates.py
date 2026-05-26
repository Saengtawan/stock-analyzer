"""
Phase Re-A: Universe filter + new strict DD labels — base rate study.

Test multiple "+X% touch in 30d AND max DD ≥ -Y%" label variants
under filtered universe (price>$5, mcap>$1B, avg_volume>$10M).

Goal: find label with:
  - Base rate 25-45% (enough samples)
  - When picks, virtually no DD beyond -5%
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
RESULTS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing')


def main():
    print("== Phase Re-A: Base Rate Study (filtered universe + DD-strict labels) ==", flush=True)

    print("\nLoading pkl + fundamentals...", flush=True)
    df = pd.read_pickle(CACHE / 'phase1_labeled_daily.pkl')
    con = sqlite3.connect(str(DB))
    funda = pd.read_sql(
        "SELECT symbol, market_cap, avg_volume FROM stock_fundamentals", con
    )
    con.close()

    # Filter universe
    df = df.merge(funda, on='symbol', how='left')
    n_raw = len(df)
    print(f"  Raw rows: {n_raw:,}", flush=True)

    # Apply liquidity filter
    df['avg_dollar_vol'] = df['avg_volume'] * df['close']
    mask = (
        (df['close'] >= 5.0) &
        (df['market_cap'] >= 1e9) &
        (df['avg_dollar_vol'] >= 10e6)
    )
    df_f = df[mask].copy()
    n_filtered = len(df_f)
    print(f"  After filter (price>$5, mcap>$1B, ADV>$10M): {n_filtered:,} ({n_filtered/n_raw*100:.1f}%)", flush=True)
    print(f"  Unique symbols: {df_f['symbol'].nunique()}", flush=True)

    # Apply same filter to GOEV check
    goev_rows = df[(df['symbol'] == 'GOEV') & (df['date'] >= '2024-11-01')][['symbol', 'date', 'close', 'market_cap', 'avg_volume']].head(5)
    print(f"\n  GOEV check (sample): would be filtered? close avg ${goev_rows['close'].mean():.2f}, mcap ${goev_rows['market_cap'].mean()/1e6:.0f}M", flush=True)

    # ============================================
    # New label variants: touch X% AND max DD ≥ -Y%
    # ============================================
    print("\n== New DD-Strict Labels (filtered universe) ==", flush=True)

    label_configs = [
        # Format: (touch_pct, max_dd_pct, window_days)
        (3.0, -3.0, 30),  # +3% touch, no DD below -3%
        (3.0, -5.0, 30),  # +3% touch, no DD below -5%
        (5.0, -3.0, 30),  # +5% touch, no DD below -3% — STRICTEST
        (5.0, -5.0, 30),  # +5% touch, no DD below -5%
        (5.0, -7.0, 30),  # +5% touch, no DD below -7%
        (5.0, -10.0, 30), # +5% touch, no DD below -10%
        (7.0, -5.0, 30),  # +7% touch, no DD below -5%
        (10.0, -5.0, 30), # +10% touch, no DD below -5%
        # Shorter windows
        (3.0, -3.0, 14),
        (3.0, -5.0, 14),
        (5.0, -5.0, 14),
        (3.0, -3.0, 7),
        (3.0, -5.0, 7),
    ]

    results = []
    for tp, dd, w in label_configs:
        h_col = f'fhigh_pct_{w}d'
        l_col = f'flow_pct_{w}d'
        if h_col not in df_f.columns or l_col not in df_f.columns:
            continue
        valid = df_f[h_col].notna() & df_f[l_col].notna()
        label = ((df_f[h_col] >= tp) & (df_f[l_col] >= dd)).astype(int)
        sub = df_f[valid].copy()
        sub['label'] = label[valid].values
        base_rate = sub['label'].mean()
        n_pos = sub['label'].sum()
        n_total = len(sub)
        name = f"+{tp}_dd{dd:g}_{w}d"
        results.append({
            'label': name,
            'tp': tp, 'dd': dd, 'window': w,
            'base_rate': round(base_rate, 4),
            'n_positive': int(n_pos),
            'n_total': int(n_total),
        })

    rdf = pd.DataFrame(results).sort_values('base_rate', ascending=False)
    print(rdf.to_string(index=False), flush=True)

    rdf.to_csv(RESULTS / 'phaseRE_base_rates.csv', index=False)

    # ============================================
    # Show distribution of fhigh/flow under filter
    # ============================================
    print("\n== Forward Return Distribution (filtered universe) ==", flush=True)
    for w in [7, 14, 30]:
        h = df_f[f'fhigh_pct_{w}d'].dropna()
        l = df_f[f'flow_pct_{w}d'].dropna()
        print(f"\n  Window {w}d:", flush=True)
        print(f"    fhigh: median +{h.median():.2f}%, p75 +{h.quantile(0.75):.2f}%, p95 +{h.quantile(0.95):.2f}%", flush=True)
        print(f"    flow:  median {l.median():.2f}%, p25 {l.quantile(0.25):.2f}%, p5 {l.quantile(0.05):.2f}%", flush=True)
        print(f"    % of stocks with flow > -3%:  {(l > -3).mean()*100:.1f}%", flush=True)
        print(f"    % of stocks with flow > -5%:  {(l > -5).mean()*100:.1f}%", flush=True)
        print(f"    % of stocks with flow > -10%: {(l > -10).mean()*100:.1f}%", flush=True)

    print("\n== Recommendation ==", flush=True)
    print("  Pick label where base rate 25-45% (enough signal, model needs to discriminate)", flush=True)


if __name__ == '__main__':
    main()
