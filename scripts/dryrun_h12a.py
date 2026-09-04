"""H12-A dry-run on recent month — verify end-to-end without trading.

Loads V-2/V-C raw predictions + features, applies H12-A serving pipeline
(scorer + cell filter + regime gates + Option E* + entry filter v2-h12a),
reports picks per zone, compares vs production v22 baseline.

Usage:
  python3 scripts/dryrun_h12a.py [--month 2026-05]
"""
import argparse, sys, sqlite3, os
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scan.ml_scorer_h12a import get_scorer_h12a
from src.scan.h12a_picker import score_and_filter_h12a, get_zone
from src.entry_filter.rules import evaluate as ef_evaluate, zone_of_mfo


def load_data(month):
    """Load features + research predictions for the given month."""
    df = pd.read_pickle(ROOT / 'cache/bt_features/features_5yr_noleak.pkl')
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    df = df[df.date.str.startswith(month)].copy()

    # Sector
    con = sqlite3.connect(str(ROOT / 'data/trade_history.db'))
    SEC = {s:sec for s, sec in con.execute(
        "SELECT symbol, sector FROM stock_fundamentals WHERE sector IS NOT NULL").fetchall()}
    con.close()
    df['sector_full'] = df['sym'].map(SEC).fillna('Other')

    # Labels for pnl_EOD (to evaluate picks ex-post)
    lab = pd.read_pickle('/tmp/phase0_labels_5yr.pkl')
    lab['date'] = pd.to_datetime(lab['date']).dt.strftime('%Y-%m-%d')
    df = df.merge(lab[['sym','date','mins_from_open','pnl_EOD']],
                  on=['sym','date','mins_from_open'], how='left')

    # Add interactions
    sys.path.insert(0, str(ROOT / 'backtests'))
    from train_v22 import add_interactions
    df = add_interactions(df)
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--month', default='2026-05')
    args = parser.parse_args()
    month = args.month

    print(f"[dryrun H12-A] month={month}")
    print(f"  Load scorer + cell ratings...")
    scorer = get_scorer_h12a()
    print()

    print(f"[load] features + labels for {month}")
    df = load_data(month)
    print(f"  Loaded {len(df):,} rows for {month}")

    # Per-day scan: for each (date, mfo), find candidates above threshold,
    # apply H12-A scoring + filter, pick top-1 per zone.
    WIN_THR = 0.75
    EF_SPEC = 'v2-h12a'  # H12-A minimal EF (only Z1 gain<=4.5)

    all_picks = []  # rows with full info
    all_rejects = []  # rejected candidates with reason

    for (date, mfo), group in df.groupby(['date', 'mins_from_open']):
        zone = get_zone(mfo)
        if not zone: continue

        # Pre-filter: skip out-of-band candidates
        # (Production uses MIN_PRICE, MIN_GAIN — emulate roughly)
        cands = group[(group.get('gain_from_open', 0) >= 0)].copy()
        if len(cands) == 0: continue

        # Score + filter each candidate
        zone_eligible = []
        for _, row in cands.iterrows():
            feats = {f: row.get(f, 0.0) for f in scorer.features.get(zone, [])}
            sec = row['sector_full']

            vix = row.get('vix', 17.0)
            vix_5d = row.get('vix_5d_chg', 0.0)
            spy = row.get('spy_intra', 0.0)
            sec_str = row.get('sec_rel_strength', 0.0)
            dow = pd.to_datetime(row['date']).dayofweek

            # H12-A score + filter
            score, reason = score_and_filter_h12a(
                scorer, feats, mfo, sec,
                vix=vix, vix_5d_chg=vix_5d,
                sec_rel_strength=sec_str, spy_intra=spy, dow=dow,
            )

            if score <= 0:
                all_rejects.append({
                    'date': date, 'mfo': mfo, 'zone': zone,
                    'sym': row['sym'], 'sector': sec, 'reason': reason,
                    'pnl_EOD': row.get('pnl_EOD'),
                })
                continue

            # WIN_THR threshold
            if score < WIN_THR:
                continue

            # Entry Filter v2-h12a
            os.environ['ENTRY_FILTER_SPEC'] = 'v2-h12a'
            passes, ef_reason = ef_evaluate(
                zone=zone,
                beta=row.get('beta'),
                sector=sec,
                vix=vix,
                dow=dow,
                gain_from_open=row.get('gain_from_open'),
                spy_intra=spy,
                mom20d=row.get('mom20d'),
            )
            if not passes:
                all_rejects.append({
                    'date': date, 'mfo': mfo, 'zone': zone,
                    'sym': row['sym'], 'sector': sec, 'reason': f'EF: {ef_reason}',
                    'pnl_EOD': row.get('pnl_EOD'),
                })
                continue

            zone_eligible.append({
                'date': date, 'mfo': mfo, 'zone': zone,
                'sym': row['sym'], 'sector': sec, 'score': score,
                'beta': row.get('beta'), 'vix': vix, 'spy_intra': spy,
                'gain_from_open': row.get('gain_from_open'),
                'pnl_EOD': row.get('pnl_EOD'),
            })

        if zone_eligible:
            # Top-1 by score
            top = max(zone_eligible, key=lambda x: x['score'])
            all_picks.append(top)

    # Aggregate per-zone (top-1/day per zone)
    picks_df = pd.DataFrame(all_picks)
    if len(picks_df) == 0:
        print("\n[result] 0 picks produced (gates may be too strict for this month)")
        return

    # Some zones may have multiple picks per day across different mfo — pick top-1 per (date, zone)
    final = picks_df.sort_values('score', ascending=False).groupby(['date', 'zone']).head(1)
    print(f"\n[picks] H12-A produced {len(final)} top-1/zone picks across {month}")
    print()
    print(f"  {'Date':<11} {'Zone':<4} {'Sym':<6} {'Sector':<22} {'Score':<8} {'PnL_EOD':<10}")
    for _, r in final.sort_values(['date', 'zone']).iterrows():
        pnl_str = f"{r['pnl_EOD']:+.2f}%" if pd.notna(r.get('pnl_EOD')) else "?"
        print(f"  {r['date']:<11} {r['zone']:<4} {r['sym']:<6} {r['sector'][:22]:<22} "
              f"{r['score']:<7.3f} {pnl_str:<10}")

    print(f"\n[stats]")
    pnl = final['pnl_EOD'].dropna()
    if len(pnl) > 0:
        print(f"  N picks: {len(final)}")
        print(f"  N with pnl available: {len(pnl)}")
        print(f"  WR: {(pnl > 0).mean() * 100:.1f}%")
        print(f"  avg/pick: {pnl.mean():+.2f}%")
        print(f"  total: {pnl.sum():+.2f}%")
        print(f"  Per zone:")
        for z in ['Z1','Z2','Z3','Z4']:
            zp = final[final.zone == z]['pnl_EOD'].dropna()
            if len(zp) == 0: print(f"    {z}: 0 picks"); continue
            print(f"    {z}: N={len(zp)} WR={(zp>0).mean()*100:+.1f}% avg={zp.mean():+.2f}% total={zp.sum():+.2f}%")

    # Reject summary
    print(f"\n[rejections] {len(all_rejects)} candidates rejected")
    rej_df = pd.DataFrame(all_rejects)
    if len(rej_df) > 0:
        # Most common reasons
        by_reason = rej_df['reason'].apply(lambda s: s.split(':')[0] if ':' in s else s).value_counts().head(8)
        print(f"  Top reject categories:")
        for r, c in by_reason.items():
            print(f"    {r}: {c}")


if __name__ == '__main__':
    main()
