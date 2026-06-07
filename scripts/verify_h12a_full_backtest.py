"""H12-A full 3-year backtest verification.

Apply the EXACT integrated H12-A pipeline (using same logic as production:
scorer + cell filter + regime gates + Option E* + entry_filter v2-h12a)
on the FULL 3-year period 2023-05 to 2026-05.

Reports per-zone WR/avg/total and compares to H12-A spec expectations.

Usage:
  python3 scripts/verify_h12a_full_backtest.py
"""
import os, json, sys, sqlite3
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scan.h12a_picker import get_zone
from src.entry_filter.rules import evaluate as ef_evaluate

WIN_THR = 0.75
TRAIN_END = '2025-05-01'  # holdout 1yr after this

PRED_FILES = {
    'Z1': '/tmp/finetune_v2_predictions.csv',
    'Z2': '/tmp/p2_z2_pred_z12_market_3dd.csv',
    'Z3': '/tmp/finetune_v3_predictions.csv',
    'Z4': '/tmp/c_z4_pred_z34_market_current.csv',
}


def load_cells():
    with open(ROOT / 'configs/h12a_cell_ratings.json') as f:
        return json.load(f)['cells_by_zone']


def pass_cell_filter(zone, sector, cells):
    if zone == 'Z4':
        return True
    c = cells.get(zone, {}).get(sector)
    if c is None:
        return True
    if zone == 'Z1':
        return (c['avg'] > 0) or (c['WR'] >= 50)
    return (c['avg'] > 0) and (c['WR'] >= 50)


def pass_regime_gate(zone, vix, vix_5d, sec_str, spy, dow, sector):
    if zone == 'Z1':
        if vix is not None and vix >= 20: return False
        if sec_str is not None and sec_str <= 0: return False
        return True
    if zone == 'Z2':
        if vix_5d is not None and vix_5d >= 0: return False
        return True
    if zone == 'Z3':
        if sec_str is not None and sec_str <= 0: return False
        if dow == 4: return False
        return True
    if zone == 'Z4':
        GOOD = {'Consumer Defensive', 'Basic Materials', 'Technology'}
        if vix is None or spy is None: return True
        if vix < 25:
            if sector in GOOD:
                if spy <= 0.2: return False
            else:
                if spy <= 0.5: return False
        else:
            if spy <= 0.5: return False
        return True
    return True


def main():
    print(f"[H12-A full 3yr backtest verification]")
    cells = load_cells()

    df = pd.read_pickle(ROOT / 'cache/bt_features/features_5yr_noleak.pkl')
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    df = df.loc[:, ~df.columns.duplicated()]
    market_cols = ['vix', 'vix_5d_chg', 'spy_intra', 'sec_rel_strength', 'beta',
                    'mom20d', 'gain_from_open']
    market_cols = [c for c in market_cols if c in df.columns]

    os.environ['ENTRY_FILTER_SPEC'] = 'v2-h12a'

    # Run H12-A pipeline per zone
    all_picks = []
    rejections = []

    for zone, pred_file in PRED_FILES.items():
        if not Path(pred_file).exists():
            print(f"  [skip] {zone}: {pred_file} missing"); continue
        zdf = pd.read_csv(pred_file)
        zdf = zdf[zdf.zone == zone]
        zdf['date'] = zdf['date'].astype(str)
        zdf['wp_use'] = zdf['wp_ft'].fillna(zdf['wp_prod'])
        zdf = zdf.merge(df[['sym','date','mins_from_open']+market_cols],
                         on=['sym','date','mins_from_open'], how='left')
        zdf['dow'] = pd.to_datetime(zdf['date']).dt.dayofweek

        # Above WIN_THR
        above = zdf[zdf.wp_use >= WIN_THR].copy()
        print(f"  [{zone}] {len(above)} candidates above WIN_THR=0.75 (3yr)")

        # Apply H12-A pipeline
        kept = []
        for _, row in above.iterrows():
            sec = row['sector']
            # Cell filter
            if not pass_cell_filter(zone, sec, cells):
                rejections.append({'reason': 'cell', 'zone': zone})
                continue
            # Regime gate
            if not pass_regime_gate(
                zone,
                row.get('vix'),
                row.get('vix_5d_chg'),
                row.get('sec_rel_strength'),
                row.get('spy_intra'),
                int(row['dow']),
                sec,
            ):
                rejections.append({'reason': 'regime', 'zone': zone})
                continue
            # Entry Filter v2-h12a
            ef_pass, _ = ef_evaluate(
                zone=zone,
                beta=row.get('beta'),
                sector=sec,
                vix=row.get('vix'),
                dow=int(row['dow']),
                gain_from_open=row.get('gain_from_open'),
                spy_intra=row.get('spy_intra'),
                mom20d=row.get('mom20d'),
            )
            if not ef_pass:
                rejections.append({'reason': 'ef', 'zone': zone})
                continue
            kept.append(row.to_dict())

        # Top-1/day per zone
        if kept:
            kept_df = pd.DataFrame(kept)
            top1 = kept_df.sort_values('wp_use', ascending=False).groupby('date').head(1)
            all_picks.append(top1)
            print(f"    → {len(top1)} top-1/day picks kept after pipeline")

    if not all_picks:
        print("0 picks — abort")
        return

    final = pd.concat(all_picks, ignore_index=True)
    final = final.dropna(subset=['pnl_EOD'])

    # === Per zone stats (3yr full + holdout) ===
    print(f"\n{'='*80}")
    print(f"H12-A FULL 3YR (flat 1x)")
    print(f"{'='*80}")
    print(f"\n{'Zone':<6} {'N':<5} {'WR':<8} {'avg':<8} {'3yr total':<10} {'Holdout total':<12}")

    total = 0; total_h = 0; total_n = 0
    for z in ['Z1','Z2','Z3','Z4']:
        zp = final[final.zone == z]
        if len(zp) == 0: print(f"  {z}: N=0"); continue
        zh = zp[zp.date >= TRAIN_END]
        t = zp.pnl_EOD.sum(); th = zh.pnl_EOD.sum() if len(zh) else 0
        wr = (zp.pnl_EOD > 0).mean() * 100
        avg = zp.pnl_EOD.mean()
        total += t; total_h += th; total_n += len(zp)
        print(f"  {z:<6} {len(zp):<5d} {wr:<+6.1f}% {avg:<+6.2f}% {t:<+7.1f}%  {th:<+7.1f}%")

    print(f"  {'TOTAL':<6} {total_n:<5d}                        {total:<+7.1f}%  {total_h:<+7.1f}%")

    # Overall stats
    wr_total = (final.pnl_EOD > 0).mean() * 100
    avg_total = final.pnl_EOD.mean()
    import numpy as np
    sharpe = final.pnl_EOD.mean() / final.pnl_EOD.std() * np.sqrt(252) if final.pnl_EOD.std() > 0 else 0

    print(f"\n[Overall]")
    print(f"  N total: {total_n}")
    print(f"  WR: {wr_total:+.1f}%")
    print(f"  avg/pick: {avg_total:+.2f}%")
    print(f"  3yr total: {total:+.1f}%")
    print(f"  Holdout total: {total_h:+.1f}%")
    print(f"  Sharpe (annualized): {sharpe:+.2f}")

    # Kelly sizing 2x
    w = 2 * final.wp_use / final.wp_use.mean()
    t_kelly = (final.pnl_EOD * w).sum()
    h_kelly = (final[final.date >= TRAIN_END].pnl_EOD * (
        2 * final[final.date >= TRAIN_END].wp_use / final[final.date >= TRAIN_END].wp_use.mean()
    )).sum() if len(final[final.date >= TRAIN_END]) else 0
    print(f"\n[With Kelly 2x sizing]")
    print(f"  3yr total: {t_kelly:+.1f}%")
    print(f"  Holdout total: {h_kelly:+.1f}%")

    # Compare to spec
    print(f"\n{'='*80}")
    print(f"COMPARE TO H12-A SPEC")
    print(f"{'='*80}")
    spec = {
        '3yr_flat_pct': 150.6,
        '3yr_kelly_pct': 297,
        'holdout_flat_pct': 109.3,
        'holdout_kelly_pct': 214,
        'sharpe': 2.84,
        'wr': 58.6,
        'avg_per_pick': 0.39,
        'n_picks': 391,
    }
    actual = {
        '3yr_flat_pct': total,
        '3yr_kelly_pct': t_kelly,
        'holdout_flat_pct': total_h,
        'holdout_kelly_pct': h_kelly,
        'sharpe': sharpe,
        'wr': wr_total,
        'avg_per_pick': avg_total,
        'n_picks': total_n,
    }
    print(f"\n  {'Metric':<25} {'Spec':<12} {'Actual':<12} {'Delta':<10}")
    for k in ['3yr_flat_pct','holdout_flat_pct','sharpe','wr','avg_per_pick','n_picks',
              '3yr_kelly_pct','holdout_kelly_pct']:
        s = spec[k]; a = actual[k]
        delta = a - s
        sign = '✅' if abs(delta) / max(abs(s), 1) < 0.1 else '⚠️'
        print(f"  {k:<25} {s:<12.2f} {a:<12.2f} {delta:<+8.2f}  {sign}")

    # Rejection stats
    print(f"\n[Rejections]")
    rej_df = pd.DataFrame(rejections)
    if len(rej_df) > 0:
        for r in ['cell','regime','ef']:
            n = (rej_df.reason == r).sum()
            print(f"  {r}: {n}")


if __name__ == '__main__':
    main()
