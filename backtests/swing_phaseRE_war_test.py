"""
Phase Re-War Test: Test swing v2.0 during war/oil shock periods.

Historical analogs for "Iran war + oil" scenario:
  - 2022-02 to 2022-04: Russia-Ukraine war (oil $80→$130)
  - 2023-10 to 2023-11: Israel-Hamas (oil $85→$95)
  - 2024-04 to 2024-05: Iran-Israel direct missile attack
  - 2024-10 to 2024-11: Iran-Israel strikes escalation

For each period:
  - Train on data BEFORE crisis (no leak)
  - Predict on crisis period
  - Compute WR, EV, worst PnL, worst DD
  - Sector breakdown (which sectors hit hardest)
"""
import sqlite3
import pandas as pd
import numpy as np
import lightgbm as lgb
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

DB = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
RESULTS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing')

LGB_PARAMS = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 31, 'max_depth': 5, 'min_child_samples': 30,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 1.0, 'reg_lambda': 1.0,
    'n_estimators': 300, 'n_jobs': 4, 'verbose': -1,
}

# Test config: v2.0 (L_touch_2_dd-3_in_7d @ 0.75)
TP_PCT = 2.0
DD_PCT = -3.0
WINDOW = 7
THRESHOLD = 0.75

WAR_PERIODS = [
    {
        'name': '2022 Russia-Ukraine',
        'train_end': '2022-01-15',
        'test_start': '2022-02-15',
        'test_end': '2022-04-30',
        'note': 'War declared 2022-02-24. Oil $80→$130. VIX 30+. SPY -15%.',
    },
    {
        'name': '2022 Rate-Hike + War',
        'train_end': '2022-05-01',
        'test_start': '2022-05-15',
        'test_end': '2022-07-31',
        'note': 'Fed 75bp hikes + continued war. Tech crash. SPY -20%.',
    },
    {
        'name': '2023 Israel-Hamas',
        'train_end': '2023-09-15',
        'test_start': '2023-10-07',
        'test_end': '2023-12-15',
        'note': 'Oct 7 attack. Oil +12% short-term. SPY mixed.',
    },
    {
        'name': '2024 Iran-Israel-Apr',
        'train_end': '2024-03-15',
        'test_start': '2024-04-01',
        'test_end': '2024-05-31',
        'note': 'Apr 13 Iran missile attack on Israel. Oil spike. VIX 19.',
    },
    {
        'name': '2024 Iran-Israel-Oct',
        'train_end': '2024-09-15',
        'test_start': '2024-10-01',
        'test_end': '2024-11-30',
        'note': 'Iran missile barrage Oct 1. Strikes. Oil volatile.',
    },
]


def get_feature_cols(df):
    drop = {'symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year',
            'sector', 'mcap_bucket', 'vix_regime', 'industry', 'vix_y', 'beta_fund',
            'market_cap', 'avg_volume', 'avg_dollar_vol'}
    return [c for c in df.columns
            if c not in drop and not c.startswith(('fhigh_', 'flow_', 'fclose_', 'L_'))
            and df[c].dtype != 'object']


def test_period(df, feature_cols, period):
    """Train before, test during crisis period."""
    print(f"\n{'='*70}", flush=True)
    print(f"WAR PERIOD: {period['name']}", flush=True)
    print(f"  {period['note']}", flush=True)
    print(f"  Train: ≤ {period['train_end']} | Test: {period['test_start']} → {period['test_end']}", flush=True)
    print('='*70, flush=True)

    label_col = f"L_war_test"
    h = df[f'fhigh_pct_{WINDOW}d']
    l = df[f'flow_pct_{WINDOW}d']
    df[label_col] = ((h >= TP_PCT) & (l >= DD_PCT)).astype(float)
    df.loc[h.isna() | l.isna(), label_col] = np.nan

    df_l = df[df[label_col].notna()].copy()
    train_cutoff = pd.Timestamp(period['train_end'])
    test_start = pd.Timestamp(period['test_start'])
    test_end = pd.Timestamp(period['test_end'])
    train_mask = df_l['date'] < train_cutoff
    test_mask = (df_l['date'] >= test_start) & (df_l['date'] <= test_end)

    n_train = train_mask.sum()
    n_test = test_mask.sum()
    print(f"  Train samples: {n_train:,} | Test samples: {n_test:,}", flush=True)

    if n_train < 30000:
        print(f"  ❌ Insufficient training data (need ≥ 30K)", flush=True)
        return None
    if n_test < 100:
        print(f"  ❌ Insufficient test data", flush=True)
        return None

    X_train = df_l.loc[train_mask, feature_cols].fillna(-999).values
    y_train = df_l.loc[train_mask, label_col].astype(int).values
    X_test = df_l.loc[test_mask, feature_cols].fillna(-999).values

    print(f"  Train pos rate: {y_train.mean():.3f}", flush=True)
    model = lgb.LGBMClassifier(**LGB_PARAMS, random_state=42)
    model.fit(X_train, y_train)
    prob = model.predict_proba(X_test)[:, 1]

    sub = df_l.loc[test_mask, ['symbol', 'date', label_col,
                                f'fhigh_pct_{WINDOW}d', f'flow_pct_{WINDOW}d',
                                f'fclose_pct_{WINDOW}d', 'sector', 'vix_regime']].copy()
    sub['prob'] = prob
    picks = sub[sub['prob'] >= THRESHOLD].copy()
    if len(picks) == 0:
        print(f"  No picks above threshold {THRESHOLD}", flush=True)
        return None

    # Compute PnL
    fhigh = picks[f'fhigh_pct_{WINDOW}d'].values
    flow = picks[f'flow_pct_{WINDOW}d'].values
    fclose = picks[f'fclose_pct_{WINDOW}d'].values
    pnl = np.where(fhigh >= TP_PCT, TP_PCT, fclose)
    picks['pnl'] = pnl
    picks['actual_dd'] = flow

    wins = (pnl > 0).sum()
    wr = wins / len(picks)
    avg = pnl.mean()
    worst_pnl = pnl.min()
    worst_dd = flow.min()
    p5_dd = picks['actual_dd'].quantile(0.05)
    pct_safe_5 = (picks['actual_dd'] > -5).mean()

    print(f"\n  📊 Results:", flush=True)
    print(f"    Picks: {len(picks)}", flush=True)
    print(f"    WR: {wr*100:.1f}%", flush=True)
    print(f"    Avg PnL: {avg:+.2f}%", flush=True)
    print(f"    Worst exit: {worst_pnl:+.2f}%", flush=True)
    print(f"    Worst intraday DD: {worst_dd:+.2f}%", flush=True)
    print(f"    Safe<-5% DD: {pct_safe_5*100:.1f}%", flush=True)
    print(f"    Expected (backtest): WR 93%, EV +1.78%, Worst -2.27%", flush=True)
    print(f"    Performance: {'✅ pass' if (wr >= 0.80 and worst_pnl >= -5) else '⚠️ degraded'}", flush=True)

    # Sector breakdown
    if 'sector' in picks.columns and picks['sector'].notna().any():
        print(f"\n  📈 By sector (top 5):", flush=True)
        by_sec = picks.groupby('sector').agg(
            n=('pnl', 'count'),
            wr=('pnl', lambda x: (x > 0).mean()),
            avg=('pnl', 'mean'),
            worst=('pnl', 'min'),
        ).round(3).sort_values('n', ascending=False).head(5)
        print(by_sec.to_string(), flush=True)

    # Worst trades detail
    worst5 = picks.nsmallest(5, 'pnl')[['symbol', 'date', 'sector', 'pnl', 'actual_dd', 'prob']]
    print(f"\n  ⚠️ Worst 5 trades:", flush=True)
    print(worst5.to_string(index=False), flush=True)

    return {
        'period': period['name'],
        'n_picks': len(picks),
        'wr': round(wr, 3),
        'avg_pnl': round(avg, 3),
        'worst_pnl': round(worst_pnl, 2),
        'worst_dd': round(worst_dd, 2),
        'pct_safe_5': round(pct_safe_5, 3),
    }


def main():
    print("== Phase Re-War: Crisis Period Stress Test ==", flush=True)
    print(f"Testing v2.0 config: L_touch_2_dd-3_in_7d @ {THRESHOLD}", flush=True)

    print("\nLoading + filtering universe...", flush=True)
    df = pd.read_pickle(CACHE / 'phase2_features.pkl')
    con = sqlite3.connect(str(DB))
    funda = pd.read_sql("SELECT symbol, market_cap, avg_volume FROM stock_fundamentals", con)
    con.close()
    df = df.merge(funda, on='symbol', how='left')
    df['avg_dollar_vol'] = df['avg_volume'] * df['close']
    mask = (
        (df['close'] >= 5.0) &
        (df['market_cap'] >= 1e9) &
        (df['avg_dollar_vol'] >= 10e6)
    )
    df = df[mask].copy()
    feature_cols = get_feature_cols(df)
    print(f"  shape: {df.shape}, features: {len(feature_cols)}", flush=True)

    results = []
    for period in WAR_PERIODS:
        r = test_period(df, feature_cols, period)
        if r:
            results.append(r)

    if results:
        rdf = pd.DataFrame(results)
        rdf.to_csv(RESULTS / 'phaseRE_war_test.csv', index=False)
        print("\n\n" + "="*70, flush=True)
        print("WAR/OIL SHOCK STRESS TEST SUMMARY", flush=True)
        print("="*70, flush=True)
        print(rdf.to_string(index=False), flush=True)
        print(f"\nExpected (normal market): WR 93% / EV +1.78% / Worst -2.27%", flush=True)
        print(f"\nAggregate:", flush=True)
        print(f"  Avg WR across crises: {rdf['wr'].mean()*100:.1f}%", flush=True)
        print(f"  Avg EV: {rdf['avg_pnl'].mean():+.2f}%", flush=True)
        print(f"  Worst across all: {rdf['worst_pnl'].min():+.2f}%", flush=True)
        print(f"  Total picks: {rdf['n_picks'].sum()}", flush=True)


if __name__ == '__main__':
    main()
