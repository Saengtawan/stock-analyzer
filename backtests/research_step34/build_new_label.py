"""
Step 34 Stage 2: Build new Z3/Z4 label candidates.

READ-ONLY on prod files. Outputs to backtests/research_step34/.

Hypothesis: Current label_smart_v2 (touch-based) lets model pick stocks
that touch +5% then fade. Need label that requires EOD ACTUAL GAIN.

Candidate labels to test (Z3/Z4 only):
  L1: EOD > scan × 1.005  (min 0.5% gain at close)
  L2: EOD > scan × 1.01   (min 1.0% gain)
  L3: EOD > scan × 1.005 AND max_dd > -3%  (gain + DD constraint)
  L4: EOD > scan × 1.005 AND gain_from_open <= 2.5  (avoid pumped)
  L5: EOD > scan × 1.005 AND gain_from_open <= 2.0
  L6: fwd_ret > 0.5  (using existing fwd_ret feature)

Outputs:
  - base rate per zone per label
  - correlation with current label_smart_v2
  - distribution analysis
  - recommendation
"""
import pandas as pd
import numpy as np
from pathlib import Path

CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/cache/bt_features/features.pkl')
OUT_DIR = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/research_step34')
OUT_DIR.mkdir(exist_ok=True)


def get_zone(mfo):
    if 0 <= mfo <= 9: return 'Z1'
    if 10 <= mfo <= 29: return 'Z2'
    if 30 <= mfo <= 44: return 'Z3'
    if 45 <= mfo <= 75: return 'Z4'
    return 'OOR'


def main():
    print("== Step 34 Stage 2: New Label Research ==", flush=True)

    print("\nLoading pkl...", flush=True)
    df = pd.read_pickle(CACHE)
    print(f"  shape: {df.shape}", flush=True)

    # Filter to test period (avoid look-ahead — use older data for label exploration)
    df = df[(df['date'] >= '2024-01-01') & (df['date'] <= '2026-04-30')].copy()
    print(f"  filtered shape: {df.shape}", flush=True)

    # Add zone column
    df['zone'] = df['mins_from_open'].apply(get_zone)
    df = df[df['zone'].isin(['Z3', 'Z4'])].copy()
    print(f"  Z3/Z4 rows: {len(df):,}", flush=True)

    # === Check what we have ===
    # fwd_ret = forward return to EOD (capped ±3% in pkl)
    # Need to detect: did stock GAIN >= X% at EOD?

    # Label candidates
    print("\n=== Building Label Candidates ===", flush=True)

    # L_eod_05: fwd_ret >= 0.5%  (min EOD gain)
    df['L1_eod_gain_05'] = (df['fwd_ret'] >= 0.5).astype(int)

    # L_eod_10: fwd_ret >= 1.0%
    df['L2_eod_gain_10'] = (df['fwd_ret'] >= 1.0).astype(int)

    # L_eod_15: fwd_ret >= 1.5%
    df['L3_eod_gain_15'] = (df['fwd_ret'] >= 1.5).astype(int)

    # L_eod_20: fwd_ret >= 2.0%
    df['L4_eod_gain_20'] = (df['fwd_ret'] >= 2.0).astype(int)

    # L_eod05_nopump: EOD gain >= 0.5% AND gain_from_open <= 2.5%
    df['L5_eod05_nopump'] = ((df['fwd_ret'] >= 0.5) & (df['gain_from_open'] <= 2.5)).astype(int)

    # L_eod10_nopump: EOD gain >= 1% AND gain_from_open <= 2%
    df['L6_eod10_nopump'] = ((df['fwd_ret'] >= 1.0) & (df['gain_from_open'] <= 2.0)).astype(int)

    # === Base rate per zone ===
    print("\n=== Base Rate per Zone ===", flush=True)

    label_cols = [
        'label_smart_v2',  # CURRENT
        'label_custom_dd',  # Z3 current alt
        'label_z12_market_3dd',  # Z1 current
        'label_eod_green_v2',  # baseline EOD green
        'L1_eod_gain_05',
        'L2_eod_gain_10',
        'L3_eod_gain_15',
        'L4_eod_gain_20',
        'L5_eod05_nopump',
        'L6_eod10_nopump',
    ]

    results = []
    for zone in ['Z3', 'Z4']:
        z_df = df[df['zone'] == zone]
        for label in label_cols:
            if label not in z_df.columns:
                continue
            valid = z_df[z_df[label].notna()][label]
            if len(valid) < 100:
                continue
            base_rate = valid.mean()
            n = len(valid)
            results.append({
                'zone': zone,
                'label': label,
                'base_rate': round(base_rate, 3),
                'n_positive': int(valid.sum()),
                'n_total': n,
            })

    rdf = pd.DataFrame(results)
    print(rdf.to_string(index=False), flush=True)

    # === Correlation between labels ===
    print("\n=== Label Correlation (Z3) ===", flush=True)
    z3 = df[df['zone'] == 'Z3'].copy()
    corr_labels = ['label_smart_v2', 'L1_eod_gain_05', 'L2_eod_gain_10', 'L3_eod_gain_15', 'L5_eod05_nopump']
    corr_labels = [l for l in corr_labels if l in z3.columns]
    print(z3[corr_labels].corr().round(2).to_string(), flush=True)

    # === Check overlap: when smart_v2 = 1, do new labels also = 1? ===
    print("\n=== When smart_v2 = 1 (predicts touch), what % of new labels also = 1? ===", flush=True)
    smart_true = z3[z3['label_smart_v2'] == 1]
    if len(smart_true) > 0:
        for label in ['L1_eod_gain_05', 'L2_eod_gain_10', 'L3_eod_gain_15', 'L5_eod05_nopump']:
            if label in smart_true.columns:
                pct = smart_true[label].mean()
                print(f"  {label}: {pct*100:.1f}% (of {len(smart_true)} smart_v2=1 rows)", flush=True)

    # === Check fade pattern: when smart_v2 = 1 AND gain_from_open > 2.5%, what's fwd_ret? ===
    print("\n=== Fade pattern: smart_v2=1 AND gain>2.5% ===", flush=True)
    hot = z3[(z3['label_smart_v2'] == 1) & (z3['gain_from_open'] > 2.5)]
    cool = z3[(z3['label_smart_v2'] == 1) & (z3['gain_from_open'] <= 2.5)]
    if len(hot) > 0 and len(cool) > 0:
        print(f"  Hot picks (gain>2.5%, n={len(hot):,}):", flush=True)
        print(f"    Avg fwd_ret: {hot['fwd_ret'].mean():+.3f}%", flush=True)
        print(f"    % positive:  {(hot['fwd_ret'] > 0).mean()*100:.1f}%", flush=True)
        print(f"  Cool picks (gain≤2.5%, n={len(cool):,}):", flush=True)
        print(f"    Avg fwd_ret: {cool['fwd_ret'].mean():+.3f}%", flush=True)
        print(f"    % positive:  {(cool['fwd_ret'] > 0).mean()*100:.1f}%", flush=True)
        print(f"  Δ: hot-cool = {hot['fwd_ret'].mean() - cool['fwd_ret'].mean():+.3f}%", flush=True)

    # Save
    rdf.to_csv(OUT_DIR / 'base_rates.csv', index=False)
    print(f"\n✅ Saved to {OUT_DIR / 'base_rates.csv'}", flush=True)


if __name__ == '__main__':
    main()
