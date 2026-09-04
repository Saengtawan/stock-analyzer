"""H12-A parity test — verify serving models match research predictions.

For Z1 only (cheapest test):
  1. Load serving models (backtests/models_prod_v23_h12a/Z1/)
  2. For each row in /tmp/finetune_v2_predictions.csv (last month):
     - Compute features same way
     - Score with serving model
     - Compare to CSV's wp_final
  3. Report avg/max delta

Pass criteria:
  - Mean delta < 0.01 (probabilities)
  - Max delta < 0.05
  - Top-1/day picks match >= 80%

Usage:
  python3 scripts/parity_h12a.py
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scan.ml_scorer_h12a import get_scorer_h12a

# Use recent month for the parity test (fastest)
TEST_MONTH = '2026-05'


def main():
    print(f"[parity test] H12-A serving vs research predictions ({TEST_MONTH})")

    # Load research predictions
    csv_path = '/tmp/finetune_v2_predictions.csv'
    if not Path(csv_path).exists():
        print(f"  ERROR: {csv_path} not found"); return
    df = pd.read_csv(csv_path)
    df = df[df.zone == 'Z1']
    df['month'] = df['date'].astype(str).str[:7]
    test = df[df.month == TEST_MONTH].copy()
    test['wp_research'] = test['wp_ft'].fillna(test['wp_prod'])
    print(f"  Loaded {len(test)} Z1 rows for {TEST_MONTH}")

    # Load features pkl (need to match the same features)
    print(f"  Loading features pkl...")
    feats_pkl = pd.read_pickle(ROOT / 'cache/bt_features/features_5yr_noleak.pkl')
    feats_pkl['date'] = pd.to_datetime(feats_pkl['date']).dt.strftime('%Y-%m-%d')
    # Apply interactions
    sys.path.insert(0, str(ROOT / 'backtests'))
    from train_v22 import add_interactions
    feats_pkl = add_interactions(feats_pkl)

    # Load scorer
    scorer = get_scorer_h12a()
    feat_list = scorer.features['Z1']

    # Dedupe columns if any
    feats_pkl = feats_pkl.loc[:, ~feats_pkl.columns.duplicated()]
    # Pick only features we actually need + merge keys
    cols_needed = ['sym','date','mins_from_open'] + [c for c in feat_list if c in feats_pkl.columns]
    cols_needed = list(dict.fromkeys(cols_needed))  # dedupe order-preserving
    # Merge features into test
    test = test.merge(feats_pkl[cols_needed],
                      on=['sym','date','mins_from_open'], how='left')
    print(f"  Merged features: {len(test)} rows")

    # Score each row
    print(f"  Scoring {len(test)} rows...")
    serving_scores = []
    for _, row in test.iterrows():
        feats_dict = {f: row.get(f, 0.0) for f in feat_list}
        score = scorer.score(feats_dict, int(row.mins_from_open), str(row.sector))
        serving_scores.append(score)
    test['wp_serving'] = serving_scores

    # Compare
    test['delta'] = (test.wp_serving - test.wp_research).abs()
    mean_delta = test.delta.mean()
    max_delta = test.delta.max()
    correlation = test[['wp_serving','wp_research']].corr().iloc[0, 1]

    print(f"\n[results]")
    print(f"  Mean |delta|: {mean_delta:.4f}")
    print(f"  Max |delta|:  {max_delta:.4f}")
    print(f"  Correlation:  {correlation:.4f}")
    print(f"  Top-5 worst deltas:")
    for _, r in test.nlargest(5, 'delta').iterrows():
        print(f"    {r.date} {r['sym']:<6} sector={r.sector[:20]:<20} "
              f"research={r.wp_research:.4f} serving={r.wp_serving:.4f} "
              f"delta={r.delta:.4f}")

    # Top-1/day match check
    research_top1 = test.sort_values('wp_research', ascending=False).groupby('date').head(1)
    serving_top1 = test.sort_values('wp_serving', ascending=False).groupby('date').head(1)
    match_count = 0
    for date in research_top1.date.unique():
        r = research_top1[research_top1.date == date].iloc[0]
        s = serving_top1[serving_top1.date == date]
        if len(s) == 0: continue
        s = s.iloc[0]
        if r['sym'] == s['sym']:
            match_count += 1
    total = len(research_top1.date.unique())
    print(f"\n  Top-1/day match: {match_count}/{total} ({match_count/total*100:.0f}%)")

    # Verdict
    print(f"\n[verdict]")
    ok = mean_delta < 0.01 and max_delta < 0.05 and match_count / total >= 0.8
    print(f"  Mean delta < 0.01: {'✓' if mean_delta < 0.01 else '✗'} ({mean_delta:.4f})")
    print(f"  Max delta < 0.05:  {'✓' if max_delta < 0.05 else '✗'} ({max_delta:.4f})")
    print(f"  Top-1 match >=80%: {'✓' if match_count/total >= 0.8 else '✗'} ({match_count/total*100:.0f}%)")
    print(f"  Overall: {'✓ PARITY PASSED' if ok else '✗ PARITY FAILED'}")


if __name__ == '__main__':
    main()
