"""
Phase Re-H: Train swing v2.1 with EXTENDED macro features.

Adds ~25 new macro features on top of existing 61:

Sector momentum (5d returns):
  xlf_5d, xle_5d, xlk_5d, xlv_5d, xlu_5d, xli_5d, xly_5d, xlp_5d, xlb_5d, xlre_5d, xlc_5d

Sector dispersion:
  sector_dispersion_5d (max - min of sector 5d returns)
  sector_top1_5d, sector_bottom1_5d
  defensive_minus_cyclical_5d (XLU+XLP avg minus XLK+XLY avg)

Volatility family:
  vix3m, vvix, skew (already in DB, add changes)
  vix3m_5d_chg, vvix_5d_chg
  vix_vix3m_ratio (term structure inversion = panic)
  move_change (bond vol)

Commodity:
  gold_5d_chg, oil_5d_chg, copper_5d_chg
  gold_spy_ratio_5d_chg (safe haven flow)
  oil_5d_pct (energy shock detector)

Cross-asset:
  iwm_spy_ratio_5d_chg (small vs large)
  tlt_spy_ratio_5d_chg (bonds vs stocks)
  eem_spy_ratio_5d_chg (EM stress)

Test on war periods + normal F3 OOS.
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
MODELS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/models_swing')

LGB_PARAMS = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 31, 'max_depth': 5, 'min_child_samples': 30,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 1.0, 'reg_lambda': 1.0,
    'n_estimators': 300, 'n_jobs': 4, 'verbose': -1,
}

TP_PCT = 2.0
DD_PCT = -3.0
WINDOW = 7


def build_extended_macro_features():
    """Build daily macro feature DF from existing macro_snapshots + extended_macro.pkl."""
    print("  Loading macro sources...", flush=True)

    # Source 1: macro_snapshots (already-pulled core macro)
    con = sqlite3.connect(str(DB))
    macro_db = pd.read_sql("""
        SELECT date, vix_close, vix3m_close, vvix_close, skew_close,
               spy_close, dxy_close, gold_close, crude_close, copper_close,
               hyg_close, tlt_close, lqd_close, ief_close, eem_close,
               yield_10y, yield_3m, yield_spread, usdjpy_close, btc_close
        FROM macro_snapshots
        WHERE date >= '2019-01-01' ORDER BY date
    """, con)
    con.close()
    macro_db['date'] = pd.to_datetime(macro_db['date'])

    # Source 2: extended_macro.pkl (sector ETFs from yfinance)
    ext = pd.read_pickle(CACHE / 'extended_macro.pkl')
    ext['date'] = pd.to_datetime(ext['date'])
    ext_pivot = ext.pivot_table(index='date', columns='symbol', values='close').reset_index()
    print(f"    macro_db: {len(macro_db)} | ext_pivot: {len(ext_pivot)}", flush=True)

    # Merge
    df = macro_db.merge(ext_pivot, on='date', how='outer').sort_values('date').reset_index(drop=True)
    df = df.ffill(limit=5)  # forward fill up to 5 days for stale weekend data

    # === Build features ===
    # Sector 5d returns
    for sector in ['XLF', 'XLE', 'XLK', 'XLV', 'XLU', 'XLI', 'XLY', 'XLP', 'XLB', 'XLRE', 'XLC']:
        if sector in df.columns:
            df[f'{sector.lower()}_5d_pct'] = df[sector].pct_change(5) * 100

    # Sector dispersion
    sec_5d_cols = [c for c in df.columns if c.endswith('_5d_pct') and c.startswith('xl')]
    if sec_5d_cols:
        df['sector_dispersion_5d'] = df[sec_5d_cols].max(axis=1) - df[sec_5d_cols].min(axis=1)
        df['sector_max_5d'] = df[sec_5d_cols].max(axis=1)
        df['sector_min_5d'] = df[sec_5d_cols].min(axis=1)
        # Defensive (XLU + XLP) minus Cyclical (XLK + XLY)
        defensive = df[['xlu_5d_pct', 'xlp_5d_pct']].mean(axis=1)
        cyclical = df[['xlk_5d_pct', 'xly_5d_pct']].mean(axis=1)
        df['defensive_minus_cyclical_5d'] = defensive - cyclical

    # Volatility family
    if 'vix3m_close' in df.columns:
        df['vix3m_5d_chg'] = df['vix3m_close'].pct_change(5) * 100
        if 'vix_close' in df.columns:
            df['vix_vix3m_ratio'] = df['vix_close'] / df['vix3m_close']
            df['vix_term_inv_5d'] = df['vix_vix3m_ratio'].pct_change(5) * 100
    if 'vvix_close' in df.columns:
        df['vvix_5d_chg'] = df['vvix_close'].pct_change(5) * 100
    if '^MOVE' in df.columns:
        df['move_5d_chg'] = df['^MOVE'].pct_change(5) * 100
        df['move_level'] = df['^MOVE']

    # Commodity
    if 'gold_close' in df.columns:
        df['gold_5d_chg'] = df['gold_close'].pct_change(5) * 100
    if 'crude_close' in df.columns:
        df['oil_5d_chg'] = df['crude_close'].pct_change(5) * 100
        df['oil_20d_chg'] = df['crude_close'].pct_change(20) * 100
    if 'copper_close' in df.columns:
        df['copper_5d_chg'] = df['copper_close'].pct_change(5) * 100

    # Safe haven ratios
    if 'gold_close' in df.columns and 'spy_close' in df.columns:
        df['gold_spy_ratio'] = df['gold_close'] / df['spy_close']
        df['gold_spy_5d_chg'] = df['gold_spy_ratio'].pct_change(5) * 100
    if 'IWM' in df.columns and 'spy_close' in df.columns:
        df['iwm_spy_ratio'] = df['IWM'] / df['spy_close']
        df['iwm_spy_5d_chg'] = df['iwm_spy_ratio'].pct_change(5) * 100
    if 'EEM' in df.columns and 'spy_close' in df.columns:
        df['eem_spy_5d_chg'] = (df['EEM'] / df['spy_close']).pct_change(5) * 100

    # SPY drawdown from 20d high
    if 'spy_close' in df.columns:
        df['spy_dd_20d_high'] = (df['spy_close'] / df['spy_close'].rolling(20).max() - 1) * 100

    extended_feats = [c for c in df.columns if any(c.endswith(suf) for suf in
                       ['_5d_pct', '_5d_chg', '_20d_chg', 'dispersion_5d',
                        '_max_5d', '_min_5d', 'cyclical_5d', 'inv_5d',
                        'spy_ratio', 'spy_5d_chg', 'move_level', 'vvix_5d_chg',
                        'dd_20d_high', 'vix_vix3m_ratio'])]
    extended_feats = list(set(extended_feats))
    print(f"  Extended features built: {len(extended_feats)}", flush=True)
    return df[['date'] + extended_feats], extended_feats


def get_feature_cols(df, extra_feats):
    drop = {'symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year',
            'sector', 'mcap_bucket', 'vix_regime', 'industry', 'vix_y', 'beta_fund',
            'market_cap', 'avg_volume', 'avg_dollar_vol'}
    base = [c for c in df.columns
            if c not in drop and not c.startswith(('fhigh_', 'flow_', 'fclose_', 'L_'))
            and df[c].dtype != 'object']
    # Avoid dup
    return base


def main():
    print("== Phase Re-H: v2.1 with Extended Macro Features ==", flush=True)

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

    # Build extended macro features
    print("\nBuilding extended macro features...", flush=True)
    ext_df, ext_feats = build_extended_macro_features()

    # Merge extended onto main
    df = df.merge(ext_df, on='date', how='left')
    print(f"  Merged shape: {df.shape}", flush=True)

    # Build label
    h = df[f'fhigh_pct_{WINDOW}d']
    l = df[f'flow_pct_{WINDOW}d']
    df['L_main'] = ((h >= TP_PCT) & (l >= DD_PCT)).astype(float)
    df.loc[h.isna() | l.isna(), 'L_main'] = np.nan
    df = df[df['L_main'].notna()]

    feature_cols = get_feature_cols(df, ext_feats)
    # Check what new features got added
    base_count = 61  # v2.0 baseline
    new_feats = [f for f in feature_cols if f in ext_feats]
    print(f"  Total features: {len(feature_cols)} (baseline 61 + {len(new_feats)} new)", flush=True)
    print(f"  New features: {new_feats}", flush=True)

    # Test periods
    periods = [
        ('Normal-2026-MarMay', '2026-02-15', '2026-03-01', '2026-05-15', False),
        ('Russia-Ukraine-2022', '2022-01-15', '2022-02-15', '2022-04-30', True),
        ('Rate-Hike-2022',       '2022-05-01', '2022-05-15', '2022-07-31', True),
        ('Israel-Hamas-2023',   '2023-09-15', '2023-10-07', '2023-12-15', True),
        ('Iran-Israel-Apr-2024', '2024-03-15', '2024-04-01', '2024-05-31', True),
        ('Iran-Israel-Oct-2024', '2024-09-15', '2024-10-01', '2024-11-30', True),
    ]

    all_results = []
    for name, train_end, test_start, test_end, is_crisis in periods:
        print(f"\n--- {name} {'[CRISIS]' if is_crisis else '[NORMAL]'} ---", flush=True)
        train_cutoff = pd.Timestamp(train_end)
        test_mask = (df['date'] >= pd.Timestamp(test_start)) & (df['date'] <= pd.Timestamp(test_end))
        train_mask = df['date'] < train_cutoff

        if train_mask.sum() < 30000 or test_mask.sum() < 100:
            print(f"  insufficient data", flush=True)
            continue

        X_train = df.loc[train_mask, feature_cols].fillna(-999).values
        y_train = df.loc[train_mask, 'L_main'].astype(int).values
        X_test = df.loc[test_mask, feature_cols].fillna(-999).values

        model = lgb.LGBMClassifier(**LGB_PARAMS, random_state=42)
        model.fit(X_train, y_train)
        prob = model.predict_proba(X_test)[:, 1]

        for thr in [0.75, 0.85]:
            mask_thr = prob >= thr
            n = mask_thr.sum()
            if n < 5:
                continue
            sub = df.loc[test_mask].iloc[mask_thr]
            fhigh = sub[f'fhigh_pct_{WINDOW}d'].values
            flow = sub[f'flow_pct_{WINDOW}d'].values
            fclose = sub[f'fclose_pct_{WINDOW}d'].values
            pnl = np.where(fhigh >= TP_PCT, TP_PCT, fclose)
            wins = (pnl > 0).sum()
            wr = wins / n
            avg = pnl.mean()
            worst = pnl.min()
            worst_dd = flow.min()
            pct_safe5 = (flow > -5).mean()
            row = {
                'period': name, 'is_crisis': is_crisis, 'thr': thr,
                'n': int(n), 'wr': round(wr, 3),
                'avg_pnl': round(avg, 3),
                'worst_pnl': round(worst, 2),
                'worst_dd': round(worst_dd, 2),
                'pct_safe_5': round(pct_safe5, 3),
            }
            all_results.append(row)
            print(f"  thr={thr}: N={n:5d} WR={wr*100:.1f}% EV={avg:+.2f}% worst={worst:+.2f}% safe5={pct_safe5*100:.0f}%", flush=True)

    if all_results:
        rdf = pd.DataFrame(all_results)
        rdf.to_csv(RESULTS / 'phaseRE_v21_war_test.csv', index=False)

        print(f"\n{'='*70}", flush=True)
        print(f"AVERAGE — v2.1 (extended features) vs v2.0", flush=True)
        print('='*70, flush=True)
        crisis = rdf[rdf['is_crisis']]
        normal = rdf[~rdf['is_crisis']]

        for thr in [0.75, 0.85]:
            c = crisis[crisis['thr'] == thr]
            n = normal[normal['thr'] == thr]
            print(f"\n  thr={thr}:", flush=True)
            print(f"    CRISIS avg: WR={c['wr'].mean()*100:.1f}% EV={c['avg_pnl'].mean():+.2f}% worst={c['worst_pnl'].min():+.2f}%", flush=True)
            print(f"    NORMAL:     WR={n['wr'].mean()*100:.1f}% EV={n['avg_pnl'].mean():+.2f}% worst={n['worst_pnl'].min():+.2f}%", flush=True)

        # Feature importance
        print(f"\n== Top 20 Features (v2.1) ==", flush=True)
        importance = model.booster_.feature_importance(importance_type='gain')
        fi = pd.DataFrame({'feature': feature_cols, 'gain': importance}).sort_values('gain', ascending=False)
        new_feat_set = set(new_feats)
        fi['is_new'] = fi['feature'].apply(lambda x: '⭐NEW' if x in new_feat_set else '')
        print(fi.head(20).to_string(index=False), flush=True)


if __name__ == '__main__':
    main()
