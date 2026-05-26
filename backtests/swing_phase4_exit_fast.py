"""
Phase 4 (FAST) — Exit Rule Optimization using vectorized Phase 3 preds.

Instead of bar-by-bar simulation (slow), use forward arrays:
  - fhigh_pct: max % gain in window
  - flow_pct: max % loss (DD) in window
  - fclose_pct: % at end of window

For each (TP, SL, time_stop) combo:
  Conservative exit logic (assume worst case if both touch):
    1. If flow <= SL → exit at SL%
    2. Else if fhigh >= TP → exit at TP%
    3. Else → exit at fclose%

This gives LOWER BOUND on Sharpe (since real path could be favorable).
Real Sharpe ≈ (conservative + optimistic) / 2.

Only evaluates top 5 survivors by Sharpe (not all 22).
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import sys

CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
RESULTS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing')
MODELS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/models_swing')

LABEL_DEFS = {
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

TP_VARIANTS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0]
SL_VARIANTS = [-2.0, -2.5, -3.0, -4.0, -5.0, -7.0, None]


def eval_exit_combo(preds_df, label_def, tp, sl):
    """Vectorized exit P&L using forward arrays + conservative exit logic."""
    w = label_def['window']
    fhigh = preds_df[f'fhigh_pct_{w}d'].values
    flow = preds_df[f'flow_pct_{w}d'].values
    fclose = preds_df[f'fclose_pct_{w}d'].values

    # Mask invalid
    valid = ~np.isnan(fhigh) & ~np.isnan(flow)
    n_valid = valid.sum()

    # Conservative: SL hit first if flow <= sl
    sl_hit = np.zeros(len(preds_df), dtype=bool)
    tp_hit = np.zeros(len(preds_df), dtype=bool)
    if sl is not None:
        sl_hit = (flow <= sl) & valid
    tp_hit = (fhigh >= tp) & valid & ~sl_hit  # only TP if SL didn't hit

    # Optimistic: TP hit first if both touch
    tp_hit_opt = (fhigh >= tp) & valid
    sl_hit_opt = np.zeros(len(preds_df), dtype=bool)
    if sl is not None:
        sl_hit_opt = (flow <= sl) & valid & ~tp_hit_opt

    # Conservative pnl
    pnl_cons = np.where(sl_hit, sl if sl is not None else np.nan,
                np.where(tp_hit, tp,
                  np.where(valid, fclose, np.nan)))

    # Optimistic pnl
    pnl_opt = np.where(tp_hit_opt, tp,
                np.where(sl_hit_opt, sl if sl is not None else np.nan,
                  np.where(valid, fclose, np.nan)))

    # Mid-point (realistic estimate)
    pnl_mid = (pnl_cons + pnl_opt) / 2

    return pnl_cons[valid], pnl_opt[valid], pnl_mid[valid]


def evaluate_survivor(label_name, thr, preds_df, label_def):
    """For one survivor, grid over TP × SL and compute metrics."""
    picks = preds_df[preds_df['prob'] >= thr].copy()
    if len(picks) < 30:
        return None

    rows = []
    w = label_def['window']
    days_test = (picks['date'].max() - picks['date'].min()).days
    for tp in TP_VARIANTS:
        for sl in SL_VARIANTS:
            if sl is not None and abs(sl) <= tp:
                pnl_c, pnl_o, pnl_m = eval_exit_combo(picks, label_def, tp, sl)
                if len(pnl_m) == 0:
                    continue
                wr_c = (pnl_c > 0).mean()
                wr_m = (pnl_m > 0).mean()
                avg_c = pnl_c.mean()
                avg_o = pnl_o.mean()
                avg_m = pnl_m.mean()
                std_m = pnl_m.std()
                sharpe_m = avg_m / std_m * np.sqrt(252 / max(w, 1)) if std_m > 0 else 0
                n = len(pnl_m)
                rows.append({
                    'label': label_name,
                    'threshold': thr,
                    'tp': tp,
                    'sl': sl if sl is not None else 'none',
                    'window': w,
                    'n': n,
                    'n_per_year': round(n * 365 / max(days_test, 1), 0),
                    'wr_cons': round(wr_c, 3),
                    'wr_mid': round(wr_m, 3),
                    'avg_cons': round(avg_c, 3),
                    'avg_mid': round(avg_m, 3),
                    'avg_opt': round(avg_o, 3),
                    'std': round(std_m, 3),
                    'sharpe_mid': round(sharpe_m, 2),
                })
            elif sl is None:
                # No SL — same as original Phase 3 logic
                pnl_c, pnl_o, pnl_m = eval_exit_combo(picks, label_def, tp, None)
                if len(pnl_m) == 0:
                    continue
                wr_m = (pnl_m > 0).mean()
                avg_m = pnl_m.mean()
                std_m = pnl_m.std()
                sharpe_m = avg_m / std_m * np.sqrt(252 / max(w, 1)) if std_m > 0 else 0
                rows.append({
                    'label': label_name,
                    'threshold': thr,
                    'tp': tp,
                    'sl': 'none',
                    'window': w,
                    'n': len(pnl_m),
                    'n_per_year': round(len(pnl_m) * 365 / max(days_test, 1), 0),
                    'wr_cons': round(wr_m, 3),
                    'wr_mid': round(wr_m, 3),
                    'avg_cons': round(avg_m, 3),
                    'avg_mid': round(avg_m, 3),
                    'avg_opt': round(avg_m, 3),
                    'std': round(std_m, 3),
                    'sharpe_mid': round(sharpe_m, 2),
                })
    return pd.DataFrame(rows)


def main():
    print("== Phase 4 (FAST): Exit Rule Optimization ==", flush=True)
    start = datetime.now()

    # Top 5 by Sharpe from Phase 3
    grid = pd.read_csv(RESULTS / 'phase3_grid_results.csv')
    grid = grid.sort_values('sharpe_est', ascending=False)

    top_survivors = []
    seen_labels = set()
    for _, row in grid.iterrows():
        # Limit to top 1 per label for diversity
        if row['label'] in seen_labels:
            continue
        if row['wr'] < 0.80 or row['avg_pnl_pct'] <= 0:
            continue
        top_survivors.append(row)
        seen_labels.add(row['label'])
        if len(top_survivors) >= 5:
            break

    print(f"Top 5 candidates:", flush=True)
    for s in top_survivors:
        print(f"  {s['label']} @ {s['threshold']} — WR {s['wr']} EV {s['avg_pnl_pct']} Sharpe {s['sharpe_est']}", flush=True)

    all_results = []
    for s in top_survivors:
        label = s['label']
        thr = s['threshold']
        label_def = LABEL_DEFS[label]
        preds_path = MODELS / f'preds_{label}.pkl'
        if not preds_path.exists():
            print(f"  ⚠️ {preds_path} missing", flush=True)
            continue
        print(f"\nEvaluating {label} @ thr={thr} ...", flush=True)
        preds = pd.read_pickle(preds_path)
        result = evaluate_survivor(label, thr, preds, label_def)
        if result is not None:
            result = result.sort_values('sharpe_mid', ascending=False)
            print(result.head(10).to_string(index=False), flush=True)
            all_results.append(result)

    if all_results:
        final = pd.concat(all_results, ignore_index=True)
        final.to_csv(RESULTS / 'phase4_exit_grid.csv', index=False)

        print("\n== TOP 20 across all (label, thr, TP, SL) by mid Sharpe ==", flush=True)
        top = final.sort_values('sharpe_mid', ascending=False).head(20)
        print(top.to_string(index=False), flush=True)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n✅ Phase 4 done in {elapsed:.1f}s", flush=True)


if __name__ == '__main__':
    main()
