"""H12-A fast dry-run — verify end-to-end pipeline using pre-computed predictions.

Reuses /tmp/finetune_v2_predictions.csv etc (already have wp_use computed),
then applies H12-A cell filter + regime gates + entry_filter v2-h12a + top-1/zone.

This is the OFFLINE equivalent of what production scan() will produce when
ML_FILTER_VARIANT=h12a is set.

Usage:
  python3 scripts/dryrun_h12a_fast.py [--month 2026-05]
"""
import argparse, json, os, sys, sqlite3
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scan.h12a_picker import get_zone
from src.entry_filter.rules import evaluate as ef_evaluate


WIN_THR = 0.75
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
        return True  # graceful
    if zone == 'Z1':
        return (c['avg'] > 0) or (c['WR'] >= 50)
    return (c['avg'] > 0) and (c['WR'] >= 50)


def pass_regime_gate(zone, vix, vix_5d, sec_str, spy, dow, sector):
    if zone == 'Z1':
        if vix is not None and vix >= 20: return False, f'VIX={vix:.1f}>=20'
        if sec_str is not None and sec_str <= 0: return False, f'sec={sec_str:.2f}<=0'
        return True, 'Z1 OK'
    if zone == 'Z2':
        if vix_5d is not None and vix_5d >= 0: return False, f'vix_5d_chg={vix_5d:.2f}>=0'
        return True, 'Z2 OK'
    if zone == 'Z3':
        if sec_str is not None and sec_str <= 0: return False, f'sec={sec_str:.2f}<=0'
        if dow == 4: return False, 'DOW=Fri'
        return True, 'Z3 OK'
    if zone == 'Z4':
        GOOD = {'Consumer Defensive', 'Basic Materials', 'Technology'}
        if vix is None or spy is None: return True, 'Z4 missing data'
        if vix < 25:
            if sector in GOOD:
                if spy <= 0.2: return False, f'Z4 good_sec SPY={spy:.2f}<=0.2'
            else:
                if spy <= 0.5: return False, f'Z4 other_sec SPY={spy:.2f}<=0.5'
        else:
            if spy <= 0.5: return False, f'Z4 crisis SPY={spy:.2f}<=0.5'
        return True, 'Z4 Option E* OK'
    return True, ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--month', default='2026-05')
    args = parser.parse_args()
    month = args.month

    print(f"[H12-A dry-run] month={month}")

    cells = load_cells()
    print(f"  Cell ratings: {sum(len(v) for v in cells.values())} (zone, sector) pairs")

    # Load market features (vix, spy_intra, etc) — we need these for regime gates
    df = pd.read_pickle(ROOT / 'cache/bt_features/features_5yr_noleak.pkl')
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    df = df.loc[:, ~df.columns.duplicated()]
    market_cols = ['vix', 'vix_5d_chg', 'spy_intra', 'sec_rel_strength', 'beta',
                    'mom20d', 'gain_from_open']
    market_cols = [c for c in market_cols if c in df.columns]

    # Load each zone's predictions
    all_zone_picks = {}
    all_rejects = []
    for zone, pred_file in PRED_FILES.items():
        if not Path(pred_file).exists():
            print(f"  [skip] {zone}: {pred_file} missing"); continue
        zdf = pd.read_csv(pred_file)
        zdf = zdf[zdf.zone == zone]
        zdf['date'] = zdf['date'].astype(str)
        zdf = zdf[zdf.date.str.startswith(month)].copy()
        if len(zdf) == 0: continue
        zdf['wp_use'] = zdf['wp_ft'].fillna(zdf['wp_prod'])

        # Merge market features
        zdf = zdf.merge(df[['sym','date','mins_from_open']+market_cols],
                         on=['sym','date','mins_from_open'], how='left')
        zdf['dow'] = pd.to_datetime(zdf['date']).dt.dayofweek

        # Apply WIN_THR
        above = zdf[zdf.wp_use >= WIN_THR].copy()
        print(f"\n  [{zone}] {len(above)} candidates above WIN_THR=0.75 in {month}")

        # For each row, apply H12-A pipeline
        kept = []
        os.environ['ENTRY_FILTER_SPEC'] = 'v2-h12a'
        for _, row in above.iterrows():
            sec = row['sector']
            # 1) Cell filter
            if not pass_cell_filter(zone, sec, cells):
                c = cells.get(zone, {}).get(sec, {})
                all_rejects.append({
                    'date': row['date'], 'zone': zone, 'sym': row['sym'],
                    'sector': sec, 'reason': f'cell_bad (WR={c.get("WR",0):.0f}% avg={c.get("avg",0):+.2f}%)',
                    'pnl_EOD': row.get('pnl_EOD'),
                })
                continue
            # 2) Regime gate
            passes, reason = pass_regime_gate(
                zone,
                row.get('vix'),
                row.get('vix_5d_chg'),
                row.get('sec_rel_strength'),
                row.get('spy_intra'),
                int(row['dow']),
                sec,
            )
            if not passes:
                all_rejects.append({
                    'date': row['date'], 'zone': zone, 'sym': row['sym'],
                    'sector': sec, 'reason': f'regime: {reason}',
                    'pnl_EOD': row.get('pnl_EOD'),
                })
                continue
            # 3) Entry Filter v2-h12a (Z1 gain<=4.5 only)
            ef_pass, ef_reason = ef_evaluate(
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
                all_rejects.append({
                    'date': row['date'], 'zone': zone, 'sym': row['sym'],
                    'sector': sec, 'reason': f'EF: {ef_reason}',
                    'pnl_EOD': row.get('pnl_EOD'),
                })
                continue
            kept.append(row.to_dict())

        # Top-1/day per zone by wp_use
        if kept:
            kept_df = pd.DataFrame(kept)
            top1 = kept_df.sort_values('wp_use', ascending=False).groupby('date').head(1)
            all_zone_picks[zone] = top1
            print(f"    → {len(top1)} picks kept after pipeline")

    # === Results ===
    all_picks = pd.concat(all_zone_picks.values(), ignore_index=True) if all_zone_picks else pd.DataFrame()
    if len(all_picks) == 0:
        print("\n[result] 0 picks — gates too strict for this month, or no signal")
        return

    print(f"\n[H12-A picks for {month}]")
    print(f"  {'Date':<11} {'Zone':<4} {'Sym':<6} {'Sector':<22} {'wp':<6} {'PnL_EOD':<10}")
    for _, r in all_picks.sort_values(['date', 'zone']).iterrows():
        pnl = r.get('pnl_EOD')
        pnl_str = f"{pnl:+.2f}%" if pd.notna(pnl) else "?"
        emoji = "✅" if (pd.notna(pnl) and pnl > 0) else ("❌" if pd.notna(pnl) else "")
        print(f"  {r['date']:<11} {r['zone']:<4} {r['sym']:<6} {r['sector'][:22]:<22} "
              f"{r['wp_use']:<5.3f} {pnl_str:<10} {emoji}")

    # Stats
    pnl = all_picks['pnl_EOD'].dropna()
    if len(pnl) > 0:
        print(f"\n[stats {month}]")
        print(f"  N picks: {len(all_picks)} (with pnl: {len(pnl)})")
        print(f"  WR: {(pnl > 0).mean() * 100:.1f}%")
        print(f"  avg/pick: {pnl.mean():+.2f}%")
        print(f"  total: {pnl.sum():+.2f}%")
        print(f"\n  Per zone:")
        for z in ['Z1','Z2','Z3','Z4']:
            zp = all_picks[all_picks.zone == z]['pnl_EOD'].dropna()
            if len(zp) == 0: print(f"    {z}: 0 picks"); continue
            print(f"    {z}: N={len(zp)} WR={(zp>0).mean()*100:+.1f}% "
                  f"avg={zp.mean():+.2f}% total={zp.sum():+.2f}%")

    # Reject summary
    if all_rejects:
        rej_df = pd.DataFrame(all_rejects)
        print(f"\n[rejections] {len(rej_df)} candidates filtered out")
        by_reason = rej_df['reason'].apply(lambda s: s.split(':')[0].split('(')[0].strip()).value_counts().head(8)
        for r, c in by_reason.items():
            print(f"    {r}: {c}")


if __name__ == '__main__':
    main()
