"""
Phase 5b-1: Feature Parity Audit for swing_filter.

Verify that live feature builder (`src/scan/swing_features.py`) produces
SAME values as training pipeline (`backtests/swing_phase2_features.py`)
for the same (symbol, date) inputs.

Process:
  1. Pick 10 symbols × 5 dates = 50 sample points
  2. Load training pkl value at each point
  3. Compute live value via build_today_features(target_date)
  4. Compare: relative diff < 1% per feature

Output: parity_audit.csv (failures highlighted)
"""
import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, '/home/saengtawan/work/project/cc/stock-analyzer/src')

from scan.swing_features import build_today_features

CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
RESULTS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing')

# Sample symbols (mix of mcap, sector)
SAMPLE_SYMBOLS = ['AAPL', 'NVDA', 'TSLA', 'AMD', 'MSFT', 'COIN', 'PLTR', 'CVNA', 'SHOP', 'XOM']

# Sample dates (post-2024 to avoid early-history issues)
SAMPLE_DATES = ['2025-12-15', '2026-01-20', '2026-02-18', '2026-03-17', '2026-04-21']

# Feature column subset (most important — top 30 + macro)
KEY_FEATURES = [
    'close', 'rsi_7', 'rsi_14', 'macd_hist', 'bb_pos', 'bb_width',
    'atr_14', 'atr_pct',
    'dist_ma5', 'dist_ma10', 'dist_ma20', 'dist_ma50', 'dist_ma100', 'dist_ma200',
    'ma_cross_5_20', 'ma_cross_20_50',
    'stoch_k_14', 'stoch_d_14', 'adx_proxy',
    'ret_1d', 'ret_3d', 'ret_5d', 'ret_10d', 'ret_20d', 'ret_60d',
    'vol_10d', 'vol_20d', 'vol_60d',
    'vol_ratio_20', 'vol_ratio_5', 'obv_ma20_dist', 'money_flow_14',
    'pct_52w_hi', 'pct_52w_lo', 'pct_20d_hi', 'pct_20d_lo',
    'range_exp', 'consol_20d',
    'days_to_next_earnings', 'has_earnings_nearby',
    'beta', 'mcap_log', 'sector_id',
    # macro (single value per date — should match)
    'vix_x', 'vix_5d_chg', 'spy_20d_chg', 'spy_dist_ma20',
]


def main():
    print("== Phase 5b-1: Feature Parity Audit ==", flush=True)

    print("\nLoading training pkl...", flush=True)
    train_df = pd.read_pickle(CACHE / 'phase2_features.pkl')
    print(f"  shape: {train_df.shape}", flush=True)

    audit_rows = []
    n_total = 0
    n_match = 0
    n_mismatch = 0
    n_missing = 0

    for date_str in SAMPLE_DATES:
        target_dt = pd.Timestamp(date_str)
        print(f"\n--- Date: {date_str} ---", flush=True)

        # Build live features for this date
        try:
            live_df = build_today_features(target_date=date_str, universe=SAMPLE_SYMBOLS)
        except Exception as e:
            print(f"  ❌ live build error: {e}", flush=True)
            continue
        if len(live_df) == 0:
            print(f"  ⚠️ no live features", flush=True)
            continue
        print(f"  live: {len(live_df)} symbols", flush=True)

        # Pull training values for same (sym, date)
        train_sub = train_df[
            (train_df['date'] == target_dt) &
            (train_df['symbol'].isin(SAMPLE_SYMBOLS))
        ]
        print(f"  training: {len(train_sub)} symbols", flush=True)

        # Compare each sym
        for sym in SAMPLE_SYMBOLS:
            live_row = live_df[live_df['symbol'] == sym]
            train_row = train_sub[train_sub['symbol'] == sym]
            if len(live_row) == 0 or len(train_row) == 0:
                n_missing += 1
                continue
            live_row = live_row.iloc[0]
            train_row = train_row.iloc[0]
            for feat in KEY_FEATURES:
                if feat not in live_row or feat not in train_row:
                    continue
                lv = live_row[feat]
                tv = train_row[feat]
                n_total += 1

                if pd.isna(lv) and pd.isna(tv):
                    n_match += 1
                    continue
                if pd.isna(lv) or pd.isna(tv):
                    n_mismatch += 1
                    audit_rows.append({'symbol': sym, 'date': date_str, 'feature': feat,
                                        'live': lv, 'train': tv, 'rel_diff': 'NaN_mismatch'})
                    continue

                # Compute relative diff
                if abs(tv) < 1e-6:
                    rel_diff = abs(lv - tv)
                else:
                    rel_diff = abs((lv - tv) / tv)

                if rel_diff < 0.01:  # < 1%
                    n_match += 1
                else:
                    n_mismatch += 1
                    audit_rows.append({'symbol': sym, 'date': date_str, 'feature': feat,
                                        'live': lv, 'train': tv, 'rel_diff': round(rel_diff, 4)})

    print(f"\n== Audit Results ==", flush=True)
    print(f"  Total compared: {n_total}", flush=True)
    print(f"  Match (<1% diff): {n_match} ({n_match/max(n_total,1)*100:.1f}%)", flush=True)
    print(f"  Mismatch: {n_mismatch}", flush=True)
    print(f"  Missing rows: {n_missing}", flush=True)

    if audit_rows:
        df = pd.DataFrame(audit_rows)
        df.to_csv(RESULTS / 'phase5b_parity_failures.csv', index=False)
        print(f"\n== Top 30 Mismatches ==", flush=True)
        print(df.head(30).to_string(index=False), flush=True)

        # Group by feature
        by_feat = df.groupby('feature').size().sort_values(ascending=False)
        print(f"\n== Mismatches by Feature (top 15) ==", flush=True)
        print(by_feat.head(15).to_string(), flush=True)

        # Pass if mismatch rate < 5%
        pass_pct = n_match / max(n_total, 1)
        verdict = "PASS" if pass_pct >= 0.95 else "FAIL"
        print(f"\n  Match rate: {pass_pct*100:.1f}% → {verdict}", flush=True)
    else:
        print(f"\n  ✅ PERFECT PARITY — no mismatches", flush=True)


if __name__ == '__main__':
    main()
