"""H12-A — Generate cell rating JSON from backtest predictions.

For each (zone, sector), compute:
  - cell_WR: win rate of top-1/day picks above WIN_THR
  - cell_avg: average pnl_EOD of those picks
  - cell_N: count

Output: configs/h12a_cell_ratings.json
Used at serving time to filter cells (S2 for Z1, S7 for Z2/Z3, none for Z4).
"""
import json, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WIN_THR = 0.75

# Use existing research predictions (from /tmp)
PRED_FILES = {
    'Z1': '/tmp/finetune_v2_predictions.csv',           # V-2 Z1
    'Z2': '/tmp/p2_z2_pred_z12_market_3dd.csv',         # V-C Z2 with z12_3dd label
    'Z3': '/tmp/finetune_v3_predictions.csv',           # V-C Z3
    'Z4': '/tmp/c_z4_pred_z34_market_current.csv',      # V-C Z4
}


def compute_cells(pred_df, zone):
    """Compute per-sector ratings for this zone."""
    z = pred_df[pred_df.zone == zone].copy()
    z['wp_use'] = z['wp_ft'].fillna(z['wp_prod'])
    above = z[z.wp_use >= WIN_THR]
    top1 = above.sort_values('wp_use', ascending=False).groupby('date').head(1)
    cells = {}
    for sec in top1.sector.unique():
        sub = top1[top1.sector == sec]
        if len(sub) < 3: continue
        cells[sec] = {
            'N': int(len(sub)),
            'WR': float((sub.pnl_EOD > 0).mean() * 100),
            'avg': float(sub.pnl_EOD.mean()),
        }
    return cells


def main():
    import os as _os; out_path = Path(_os.environ.get('H12A_CELLS_OUT', str(ROOT / 'configs/h12a_cell_ratings.json')))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[generate cell ratings] WIN_THR={WIN_THR}")
    all_cells = {}
    for zone, pred_file in PRED_FILES.items():
        p = Path(pred_file)
        if not p.exists():
            print(f"  [skip] {zone}: {pred_file} not found")
            continue
        df = pd.read_csv(p)
        cells = compute_cells(df, zone)
        all_cells[zone] = cells
        print(f"\n  {zone}: {len(cells)} sectors")
        for sec, m in sorted(cells.items(), key=lambda x: -x[1]['avg']):
            star = ' ⭐' if (m['WR'] >= 50 and m['avg'] > 0) else ''
            print(f"    {sec:<25} N={m['N']:>3d} WR={m['WR']:+5.1f}% avg={m['avg']:+5.2f}%{star}")

    meta = {
        'win_thr': WIN_THR,
        'cells_by_zone': all_cells,
        'cell_filters': {
            'Z1': 'S2 — (avg>0) OR (WR>=50)',
            'Z2': 'S7 — (avg>0) AND (WR>=50)',
            'Z3': 'S7 — (avg>0) AND (WR>=50)',
            'Z4': 'none — Option E* handles selection',
        },
        'usage_note': 'At serving time, for a (zone, sector) lookup the cells_by_zone[zone][sector] — if missing or fails filter, skip the pick.',
    }
    with open(out_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"\n[done] saved {out_path}")


if __name__ == '__main__':
    main()
