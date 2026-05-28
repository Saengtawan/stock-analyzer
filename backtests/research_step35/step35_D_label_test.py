"""Step 35-D: Real-outcome label test (sandbox, no prod touch).

Compares synthetic labels (label_z12_market_3dd / label_custom_dd / label_smart_v2)
vs real-outcome labels (label_real_pnl_pos / label_real_pnl_05) via walk-forward
training. Top-1-per-day picking, 6 months WF, monthly refit.

Out: /tmp/step35_D/label_comparison.csv + report.md
"""
import sys
from pathlib import Path
from datetime import timedelta
import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, '/home/saengtawan/work/project/cc/stock-analyzer/backtests')
from train_v22 import V7_FEATS, CROSS_FEATS, INTERACTIONS, add_interactions

PKL = '/home/saengtawan/work/project/cc/stock-analyzer/cache/bt_features/features.pkl'
OUT = Path('/tmp/step35_D')
OUT.mkdir(parents=True, exist_ok=True)

ZONES = [
    ('Z1', 0, 9, True),
    ('Z2', 10, 29, True),
    ('Z3', 30, 44, False),
    ('Z4', 45, 75, False),
]

# Per-zone HPs (copy of prod, kept simple/uniform for fairness — we test labels not HPs)
HP = dict(learning_rate=0.05, max_depth=4, num_leaves=31, min_child_samples=50,
          reg_alpha=1.0, reg_lambda=2.0, n_estimators=400,
          bagging_fraction=0.8, feature_fraction=0.8, bagging_freq=1,
          objective='binary', verbose=-1, n_jobs=4)

# Labels to test per zone — only use labels with non-NaN data in that zone
ZONE_LABELS = {
    'Z1': ['label_z12_market_3dd','label_custom_dd','label_real_pnl_pos','label_real_pnl_05'],
    'Z2': ['label_z12_market_3dd','label_custom_dd','label_real_pnl_pos','label_real_pnl_05'],
    'Z3': ['label_custom_dd','label_smart_v2','label_real_pnl_pos','label_real_pnl_05'],
    'Z4': ['label_custom_dd','label_smart_v2','label_real_pnl_pos','label_real_pnl_05'],
}

TRAIN_DAYS = 840
WF_END = pd.Timestamp('2026-05-15')  # last refit
WF_MONTHS = 6  # months to walk forward


def get_feats(use_inter):
    feats = V7_FEATS + CROSS_FEATS
    if use_inter:
        feats = feats + INTERACTIONS
    return feats


def train_one(df_train, df_test, feats, label_col):
    X_tr = df_train[feats].values
    y_tr = df_train[label_col].values
    X_te = df_test[feats].values

    # 3 seeds for noise smoothing; 5 felt heavy for sandbox
    preds = np.zeros(len(X_te))
    n_seeds = 3
    for seed in range(n_seeds):
        m = lgb.LGBMClassifier(random_state=seed, **HP)
        m.fit(X_tr, y_tr)
        preds += m.predict_proba(X_te)[:, 1]
    preds /= n_seeds
    return preds


def topk_per_day(df_test, preds, k=1):
    """Pick top-k by pred each day → return realized fwd_ret list."""
    d = df_test.copy()
    d['pred'] = preds
    picks = []
    for date, grp in d.groupby('date'):
        sel = grp.nlargest(k, 'pred')
        picks.extend(sel['fwd_ret'].tolist())
    return picks


def main():
    print('Loading pkl…')
    df = pd.read_pickle(PKL)
    df['date'] = pd.to_datetime(df['date'])

    # Build real-outcome labels
    df['label_real_pnl_pos'] = (df['fwd_ret'] > 0).astype(int)
    df['label_real_pnl_05']  = (df['fwd_ret'] > 0.5).astype(int)
    df['label_real_pnl_10']  = (df['fwd_ret'] > 1.0).astype(int)

    # Base-rate table
    base_rows = []
    for zname, lo, hi, _ in ZONES:
        mask = (df['mins_from_open']>=lo) & (df['mins_from_open']<=hi)
        sub = df[mask]
        for lab in ZONE_LABELS[zname]:
            s = sub[lab].dropna()
            base_rows.append({'zone':zname, 'label':lab, 'n':len(s), 'base_rate':float(s.mean()) if len(s) else np.nan})
    base_df = pd.DataFrame(base_rows)
    base_df.to_csv(OUT/'base_rates.csv', index=False)
    print(base_df.to_string(index=False))

    # WF: 6 monthly refits
    # Test windows: [WF_END - 6mo, WF_END - 5mo], …, [WF_END - 1mo, WF_END]
    rows = []
    for zname, lo, hi, use_inter in ZONES:
        feats = get_feats(use_inter)
        # Add interactions cols if needed
        df_z = df[(df['mins_from_open']>=lo) & (df['mins_from_open']<=hi)].copy()
        df_z = add_interactions(df_z)

        # drop NaN in features
        df_z = df_z.dropna(subset=feats + ['fwd_ret'])

        print(f'\n=== {zname} (mfo {lo}-{hi}) — {len(df_z)} rows ===')

        for lab in ZONE_LABELS[zname]:
            df_zl = df_z.dropna(subset=[lab]).copy()
            all_picks = []
            for m in range(WF_MONTHS):
                test_end   = WF_END - pd.DateOffset(months=m)
                test_start = test_end - pd.DateOffset(months=1)
                train_end  = test_start - pd.Timedelta(days=1)
                train_start = train_end - pd.Timedelta(days=TRAIN_DAYS)

                tr = df_zl[(df_zl['date']>=train_start)&(df_zl['date']<=train_end)]
                te = df_zl[(df_zl['date']>test_start)&(df_zl['date']<=test_end)]
                if len(tr)<1000 or len(te)<5:
                    continue
                # Need both classes in train
                if tr[lab].nunique()<2:
                    continue
                preds = train_one(tr, te, feats, lab)
                picks = topk_per_day(te, preds, k=1)
                all_picks.extend(picks)

            picks_arr = np.array(all_picks)
            if len(picks_arr)==0:
                rows.append({'zone':zname,'label':lab,'n':0,'wr':np.nan,'avg_pnl':np.nan,'total':np.nan,'worst':np.nan})
                continue
            wr = float((picks_arr>0).mean())
            avg = float(picks_arr.mean())
            tot = float(picks_arr.sum())
            worst = float(picks_arr.min())
            rows.append({'zone':zname,'label':lab,'n':len(picks_arr),
                         'wr':round(wr,4),'avg_pnl':round(avg,4),
                         'total':round(tot,2),'worst':round(worst,4)})
            print(f'  {lab:24s}  N={len(picks_arr):4d}  WR={wr*100:5.1f}%  avg={avg:+.3f}%  total={tot:+.1f}%  worst={worst:+.2f}%')

    res = pd.DataFrame(rows)
    # Merge base rate in
    out = res.merge(base_df.rename(columns={'n':'n_train_rows'}), on=['zone','label'], how='left')
    out = out[['zone','label','base_rate','n_train_rows','n','wr','avg_pnl','total','worst']]
    out.to_csv(OUT/'label_comparison.csv', index=False)
    print('\nWritten:', OUT/'label_comparison.csv')
    return out


if __name__ == '__main__':
    main()
