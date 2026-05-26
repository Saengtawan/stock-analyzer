"""
Phase Re-I (FIXED): Comprehensive Ensemble Grid.

Bug fix: properly construct feature sets for v2.0, v2.1, v2.2.
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

LGB_BASELINE = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 31, 'max_depth': 5, 'min_child_samples': 30,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 1.0, 'reg_lambda': 1.0,
    'n_estimators': 300, 'n_jobs': 4, 'verbose': -1,
}

LGB_DISCIPLINED = {
    'objective': 'binary', 'metric': 'auc', 'learning_rate': 0.05,
    'num_leaves': 15, 'max_depth': 4, 'min_child_samples': 50,
    'subsample': 0.8, 'colsample_bytree': 0.8,
    'reg_alpha': 3.0, 'reg_lambda': 3.0,
    'n_estimators': 200, 'n_jobs': 4, 'verbose': -1,
}

V22_NEW_FEATURES = [
    'iwm_spy_ratio', 'gold_spy_ratio', 'move_level', 'vix_vix3m_ratio',
    'defensive_minus_cyclical_5d', 'oil_20d_chg', 'vvix_5d_chg', 'sector_dispersion_5d',
]

ALL_NEW_EXTENDED_FEATS = [
    # Sector 5d
    'xlf_5d_pct', 'xle_5d_pct', 'xlk_5d_pct', 'xlv_5d_pct', 'xlu_5d_pct',
    'xli_5d_pct', 'xly_5d_pct', 'xlp_5d_pct', 'xlb_5d_pct', 'xlre_5d_pct', 'xlc_5d_pct',
    # Sector dispersion
    'sector_dispersion_5d', 'sector_max_5d', 'sector_min_5d', 'defensive_minus_cyclical_5d',
    # Vol family
    'vix3m_5d_chg', 'vix_vix3m_ratio', 'vix_term_inv_5d', 'vvix_5d_chg',
    'move_level', 'move_5d_chg',
    # Commodity
    'gold_5d_chg', 'oil_5d_chg', 'oil_20d_chg', 'copper_5d_chg',
    # Safe haven
    'gold_spy_ratio', 'gold_spy_5d_chg', 'iwm_spy_ratio', 'iwm_spy_5d_chg', 'eem_spy_5d_chg',
    'spy_dd_20d_high',
]

TP_PCT = 2.0
DD_PCT = -3.0
WINDOW = 7

PERIODS = [
    ('Normal-2026', '2026-02-15', '2026-03-01', '2026-05-15', False),
    ('RussiaUkr22', '2022-01-15', '2022-02-15', '2022-04-30', True),
    ('RateHike22',   '2022-05-01', '2022-05-15', '2022-07-31', True),
    ('Israel23',     '2023-09-15', '2023-10-07', '2023-12-15', True),
    ('IranApr24',    '2024-03-15', '2024-04-01', '2024-05-31', True),
    ('IranOct24',    '2024-09-15', '2024-10-01', '2024-11-30', True),
]


def build_extended_macro():
    con = sqlite3.connect(str(DB))
    macro_db = pd.read_sql("""
        SELECT date, vix_close, vix3m_close, vvix_close, skew_close,
               spy_close, dxy_close, gold_close, crude_close, copper_close,
               hyg_close, tlt_close, lqd_close, ief_close, eem_close,
               yield_10y, yield_3m, yield_spread, usdjpy_close, btc_close
        FROM macro_snapshots WHERE date >= '2019-01-01' ORDER BY date
    """, con)
    con.close()
    macro_db['date'] = pd.to_datetime(macro_db['date'])
    ext = pd.read_pickle(CACHE / 'extended_macro.pkl')
    ext['date'] = pd.to_datetime(ext['date'])
    ext_pivot = ext.pivot_table(index='date', columns='symbol', values='close').reset_index()
    df = macro_db.merge(ext_pivot, on='date', how='outer').sort_values('date').reset_index(drop=True)
    df = df.ffill(limit=5)

    for sector in ['XLF', 'XLE', 'XLK', 'XLV', 'XLU', 'XLI', 'XLY', 'XLP', 'XLB', 'XLRE', 'XLC']:
        if sector in df.columns:
            df[f'{sector.lower()}_5d_pct'] = df[sector].pct_change(5) * 100

    sec_5d_cols = [c for c in df.columns if c.endswith('_5d_pct') and c.startswith('xl')]
    if sec_5d_cols:
        df['sector_dispersion_5d'] = df[sec_5d_cols].max(axis=1) - df[sec_5d_cols].min(axis=1)
        df['sector_max_5d'] = df[sec_5d_cols].max(axis=1)
        df['sector_min_5d'] = df[sec_5d_cols].min(axis=1)
        defensive = df[['xlu_5d_pct', 'xlp_5d_pct']].mean(axis=1)
        cyclical = df[['xlk_5d_pct', 'xly_5d_pct']].mean(axis=1)
        df['defensive_minus_cyclical_5d'] = defensive - cyclical

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
    if 'gold_close' in df.columns:
        df['gold_5d_chg'] = df['gold_close'].pct_change(5) * 100
    if 'crude_close' in df.columns:
        df['oil_5d_chg'] = df['crude_close'].pct_change(5) * 100
        df['oil_20d_chg'] = df['crude_close'].pct_change(20) * 100
    if 'copper_close' in df.columns:
        df['copper_5d_chg'] = df['copper_close'].pct_change(5) * 100
    if 'gold_close' in df.columns and 'spy_close' in df.columns:
        df['gold_spy_ratio'] = df['gold_close'] / df['spy_close']
        df['gold_spy_5d_chg'] = df['gold_spy_ratio'].pct_change(5) * 100
    if 'IWM' in df.columns and 'spy_close' in df.columns:
        df['iwm_spy_ratio'] = df['IWM'] / df['spy_close']
        df['iwm_spy_5d_chg'] = df['iwm_spy_ratio'].pct_change(5) * 100
    if 'EEM' in df.columns and 'spy_close' in df.columns:
        df['eem_spy_5d_chg'] = (df['EEM'] / df['spy_close']).pct_change(5) * 100
    if 'spy_close' in df.columns:
        df['spy_dd_20d_high'] = (df['spy_close'] / df['spy_close'].rolling(20).max() - 1) * 100

    keep_cols = ['date'] + [c for c in ALL_NEW_EXTENDED_FEATS if c in df.columns]
    return df[keep_cols]


def evaluate_picks(picks):
    if len(picks) < 3:
        return None
    fhigh = picks[f'fhigh_pct_{WINDOW}d'].values
    flow = picks[f'flow_pct_{WINDOW}d'].values
    fclose = picks[f'fclose_pct_{WINDOW}d'].values
    pnl = np.where(fhigh >= TP_PCT, TP_PCT, fclose)
    n = len(pnl)
    wins = (pnl > 0).sum()
    wr = wins / n
    avg = pnl.mean()
    std = pnl.std()
    worst = pnl.min()
    sharpe = avg / std * np.sqrt(252 / WINDOW) if std > 0 else 0
    return {'n': n, 'wr': round(wr, 3), 'avg_pnl': round(avg, 3),
            'worst_pnl': round(worst, 2), 'worst_dd': round(flow.min(), 2),
            'sharpe': round(sharpe, 2)}


def main():
    print("== Phase Re-I (FIXED): Comprehensive Ensemble Grid ==", flush=True)

    df = pd.read_pickle(CACHE / 'phase2_features.pkl')
    con = sqlite3.connect(str(DB))
    funda = pd.read_sql("SELECT symbol, market_cap, avg_volume FROM stock_fundamentals", con)
    con.close()
    df = df.merge(funda, on='symbol', how='left')
    df['avg_dollar_vol'] = df['avg_volume'] * df['close']
    mask = (df['close'] >= 5.0) & (df['market_cap'] >= 1e9) & (df['avg_dollar_vol'] >= 10e6)
    df = df[mask].copy()
    print(f"  Filtered: {df.shape}", flush=True)

    # Define BASE features (v2.0 set — 61)
    drop_cols = {'symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year',
                 'sector', 'mcap_bucket', 'vix_regime', 'industry', 'vix_y', 'beta_fund',
                 'market_cap', 'avg_volume', 'avg_dollar_vol'}
    base_feats = [c for c in df.columns
                   if c not in drop_cols and not c.startswith(('fhigh_', 'flow_', 'fclose_', 'L_'))
                   and df[c].dtype != 'object']
    print(f"  Base v2.0 features: {len(base_feats)}", flush=True)

    # Merge extended macro
    ext_df = build_extended_macro()
    print(f"  Extended macro feats available: {len(ext_df.columns) - 1}", flush=True)
    df = df.merge(ext_df, on='date', how='left')

    # Now define v2.1 (base + all extended) and v2.2 (base + selected 8)
    extended_cols_available = [c for c in ALL_NEW_EXTENDED_FEATS if c in df.columns]
    v21_feats = base_feats + extended_cols_available
    v22_feats = base_feats + [f for f in V22_NEW_FEATURES if f in df.columns]
    print(f"  v2.0: {len(base_feats)} features", flush=True)
    print(f"  v2.1: {len(v21_feats)} features (base + {len(extended_cols_available)} extended)", flush=True)
    print(f"  v2.2: {len(v22_feats)} features (base + 8 selected)", flush=True)

    # Label
    h = df[f'fhigh_pct_{WINDOW}d']
    l = df[f'flow_pct_{WINDOW}d']
    df['L_main'] = ((h >= TP_PCT) & (l >= DD_PCT)).astype(float)
    df.loc[h.isna() | l.isna(), 'L_main'] = np.nan
    df = df[df['L_main'].notna()]

    all_results = []
    for name, train_end, test_start, test_end, is_crisis in PERIODS:
        print(f"\n--- {name} {'[CRISIS]' if is_crisis else '[NORMAL]'} ---", flush=True)
        train_cutoff = pd.Timestamp(train_end)
        test_mask = (df['date'] >= pd.Timestamp(test_start)) & (df['date'] <= pd.Timestamp(test_end))
        train_mask = df['date'] < train_cutoff
        if train_mask.sum() < 30000 or test_mask.sum() < 100:
            continue

        y_train = df.loc[train_mask, 'L_main'].astype(int).values

        # v2.0
        X_tr = df.loc[train_mask, base_feats].fillna(-999).values
        X_te = df.loc[test_mask, base_feats].fillna(-999).values
        m20 = lgb.LGBMClassifier(**LGB_BASELINE, random_state=42); m20.fit(X_tr, y_train)
        p20 = m20.predict_proba(X_te)[:, 1]

        # v2.1
        X_tr = df.loc[train_mask, v21_feats].fillna(-999).values
        X_te = df.loc[test_mask, v21_feats].fillna(-999).values
        m21 = lgb.LGBMClassifier(**LGB_BASELINE, random_state=42); m21.fit(X_tr, y_train)
        p21 = m21.predict_proba(X_te)[:, 1]

        # v2.2 disciplined
        X_tr = df.loc[train_mask, v22_feats].fillna(-999).values
        X_te = df.loc[test_mask, v22_feats].fillna(-999).values
        m22 = lgb.LGBMClassifier(**LGB_DISCIPLINED, random_state=42); m22.fit(X_tr, y_train)
        p22 = m22.predict_proba(X_te)[:, 1]

        test_df = df.loc[test_mask].copy()
        test_df['p20'] = p20
        test_df['p21'] = p21
        test_df['p22'] = p22

        combos = {
            # Pure
            'v20_t075': test_df['p20'] >= 0.75,
            'v20_t085': test_df['p20'] >= 0.85,
            'v20_t090': test_df['p20'] >= 0.90,
            'v21_t075': test_df['p21'] >= 0.75,
            'v21_t085': test_df['p21'] >= 0.85,
            'v22_t075': test_df['p22'] >= 0.75,
            'v22_t085': test_df['p22'] >= 0.85,
            # Weighted avg
            'avg73_t075': (0.7*test_df['p20'] + 0.3*test_df['p21']) >= 0.75,
            'avg73_t085': (0.7*test_df['p20'] + 0.3*test_df['p21']) >= 0.85,
            'avg55_t075': (0.5*test_df['p20'] + 0.5*test_df['p21']) >= 0.75,
            'avg333_t075': ((test_df['p20']+test_df['p21']+test_df['p22'])/3) >= 0.75,
            'avg333_t085': ((test_df['p20']+test_df['p21']+test_df['p22'])/3) >= 0.85,
            # Strict AND
            'AND_v20_v21_75': (test_df['p20'] >= 0.75) & (test_df['p21'] >= 0.75),
            'AND_v20_v21_85': (test_df['p20'] >= 0.85) & (test_df['p21'] >= 0.85),
            'AND_v20_v22_75': (test_df['p20'] >= 0.75) & (test_df['p22'] >= 0.75),
            'AND_v20_v22_85': (test_df['p20'] >= 0.85) & (test_df['p22'] >= 0.85),
            'AND_all3_75': (test_df['p20'] >= 0.75) & (test_df['p21'] >= 0.75) & (test_df['p22'] >= 0.75),
            'AND_all3_85': (test_df['p20'] >= 0.85) & (test_df['p21'] >= 0.85) & (test_df['p22'] >= 0.85),
            # Majority
            'maj2of3_75': ((test_df['p20']>=0.75).astype(int) + (test_df['p21']>=0.75).astype(int) + (test_df['p22']>=0.75).astype(int)) >= 2,
            'maj2of3_85': ((test_df['p20']>=0.85).astype(int) + (test_df['p21']>=0.85).astype(int) + (test_df['p22']>=0.85).astype(int)) >= 2,
        }

        for combo_name, mask_c in combos.items():
            sub = test_df[mask_c]
            r = evaluate_picks(sub)
            if r is None:
                continue
            r.update({'period': name, 'is_crisis': is_crisis, 'combo': combo_name})
            all_results.append(r)
            crisis_flag = '🔴' if is_crisis else '🟢'
            print(f"  {crisis_flag} {combo_name:18s} N={r['n']:4d} WR={r['wr']*100:.0f}% EV={r['avg_pnl']:+.2f}% worst={r['worst_pnl']:+.2f}% Sharpe={r['sharpe']:.2f}", flush=True)

    rdf = pd.DataFrame(all_results)
    rdf.to_csv(RESULTS / 'phaseRE_ensemble_v2_grid.csv', index=False)

    print(f"\n{'='*80}", flush=True)
    print("ANALYSIS — Aggregated by combo", flush=True)
    print('='*80, flush=True)

    # Group crisis and normal separately
    crisis_summary = rdf[rdf['is_crisis']].groupby('combo').agg(
        n_total=('n', 'sum'),
        avg_wr=('wr', 'mean'),
        avg_ev=('avg_pnl', 'mean'),
        worst_pnl=('worst_pnl', 'min'),
        avg_sharpe=('sharpe', 'mean'),
    ).round(3)

    normal_summary = rdf[~rdf['is_crisis']].groupby('combo').agg(
        n=('n', 'sum'),
        wr=('wr', 'first'),
        ev=('avg_pnl', 'first'),
        worst=('worst_pnl', 'first'),
        sharpe=('sharpe', 'first'),
    ).round(3)

    combined = crisis_summary.join(normal_summary, how='outer', lsuffix='_crisis', rsuffix='_normal')
    combined = combined.fillna({'n_total': 0, 'n': 0})

    # Quality score
    combined['quality'] = (
        combined['avg_wr'].fillna(0) * 0.3 +
        combined['wr'].fillna(0) * 0.3 +
        (combined['worst_pnl'].fillna(-20) + 20) / 20 * 0.2 +
        (combined['worst'].fillna(-20) + 20) / 20 * 0.2
    )

    combined = combined.sort_values('quality', ascending=False)
    print(f"\n🏆 TOP 15 BY QUALITY SCORE:", flush=True)
    cols = ['n_total', 'avg_wr', 'avg_ev', 'worst_pnl', 'n', 'wr', 'ev', 'worst', 'quality']
    print(combined[cols].head(15).to_string(), flush=True)

    # Strict: worst >= -5 in both
    strict = combined[(combined['worst_pnl'] >= -5) & (combined['worst'] >= -5) &
                       (combined['n_total'] >= 30) & (combined['n'] >= 5)]
    print(f"\n⭐ STRICT FILTER (worst >= -5 both regimes, n >= 30 crisis, 5 normal):", flush=True)
    if len(strict) > 0:
        print(strict[cols].head(10).to_string(), flush=True)
    else:
        print("  (none)", flush=True)

    # Ultra strict
    ultra = combined[(combined['worst_pnl'] >= -3) & (combined['worst'] >= -3) &
                      (combined['avg_wr'] >= 0.80) & (combined['wr'] >= 0.80)]
    print(f"\n⭐⭐ ULTRA STRICT (worst >= -3, WR >= 0.80 both):", flush=True)
    if len(ultra) > 0:
        print(ultra[cols].head(10).to_string(), flush=True)
    else:
        print("  (none — too strict)", flush=True)

    combined.to_csv(RESULTS / 'phaseRE_ensemble_v2_summary.csv')


if __name__ == '__main__':
    main()
