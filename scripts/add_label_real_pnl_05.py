"""
Step 35: Add label_real_pnl_05 to EXISTING pkl without full rebuild.

Loads pkl, computes new label using fwd_ret column (already in pkl).
Saves back to same pkl.

label_real_pnl_05 = 1 if fwd_ret > 0.5%, else 0
(fwd_ret = EOD close / scan_p - 1, capped ±3% in pkl)
"""
import pandas as pd
import numpy as np
from pathlib import Path
import time

CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/cache/bt_features/features.pkl')

def main():
    t = time.time()
    print(f"Loading pkl ({CACHE})...")
    df = pd.read_pickle(CACHE)
    print(f"  shape: {df.shape}, elapsed {time.time()-t:.0f}s")

    if 'fwd_ret' not in df.columns:
        print("ERROR: fwd_ret column missing!")
        return

    print(f"\nComputing label_real_pnl_05 (fwd_ret > 0.5%)...")
    # NaN if fwd_ret missing
    df['label_real_pnl_05'] = np.where(
        df['fwd_ret'].isna(), np.nan,
        (df['fwd_ret'] > 0.5).astype(float)
    )

    valid = df['label_real_pnl_05'].dropna()
    print(f"  Total rows with label: {len(valid):,}")
    print(f"  Base rate: {valid.mean():.3f}")
    print(f"  Positive: {valid.sum():,.0f}")

    # Per-zone base rate
    print(f"\nPer-zone base rate:")
    for zone, (lo, hi) in [('Z1',(0,9)),('Z2',(10,29)),('Z3',(30,44)),('Z4',(45,75))]:
        zmask = (df['mins_from_open'] >= lo) & (df['mins_from_open'] <= hi)
        zsub = df[zmask]
        zvalid = zsub['label_real_pnl_05'].dropna()
        if len(zvalid) > 0:
            print(f"  {zone}: N={len(zvalid):,} base_rate={zvalid.mean():.3f}")

    print(f"\nSaving updated pkl...")
    t1 = time.time()
    df.to_pickle(CACHE)
    print(f"  Saved in {time.time()-t1:.0f}s")
    print(f"\nTotal: {time.time()-t:.0f}s")


if __name__ == '__main__':
    main()
