"""
Phase 2: Walk-forward verification of v9.1 system on 6 reference months.
Uses precomputed labels from /tmp/bt_labels_v91.pkl.
Retrain on data BEFORE each month, test with bar-by-bar trail simulation.
"""

import pandas as pd
import numpy as np
import sqlite3
import lightgbm as lgb
from collections import defaultdict
import time as _time
import warnings
warnings.filterwarnings('ignore')

DB_PATH = '/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db'
PKL_PATH = '/tmp/bt_features_v13_more_path.pkl'
LABELS_PATH = '/tmp/bt_labels_v91.pkl'

FEATURES_V7 = [
    'mins_from_open','gain_from_open','range_pct','from_peak_pct','vs_vwap',
    'vol_ratio','vol_accel','bars_since_hi','hh_count','consol','range_exp',
    'gap_from_prev','beta','mcap_bucket','spy_green','spy_intra','vix',
    'vix_5d_chg','ad_ratio','sec3d','mom5d','mom20d','dist_sma20',
    'pct_52w_hi','pct_52w_lo','dow','insider_net_30d','news_sentiment',
    'earnings_days','pm_vol_ratio','short_pct','btc_5d_chg','jpy_5d_chg',
    'skew','vvix','vix_term_spread','sec_rel_strength','gain_first30',
    'entry_vs_first30','pullback_depth','vol_trend','consec_green','time_since_peak'
]

FEATURES_V9 = FEATURES_V7 + [
    'path_r_squared','path_peak_diff','path_low_diff','path_consol_range',
    'path_max_drawdown','path_choppiness','path_speed_late','path_speed_accel',
    'path_momentum_accel','path_up_vol_ratio','path_speed_early',
    'path_support_touches','path_bar_size_trend','path_wick_ratio',
    'path_lower_wick_ratio','path_gap_ratio','path_time_at_high',
    'path_vol_at_peaks','path_vwap_slope','path_ret_skewness'
]

BUCKETS = [
    ('0930', 5, 25, FEATURES_V7, 0.30, 'decay'),
    ('1000', 30, 70, FEATURES_V9, 0.10, 'fixed3'),
    ('1045', 75, 115, FEATURES_V9, 0.10, 'fixed3'),
    ('1130', 120, 210, FEATURES_V9, 0.10, 'fixed3'),
]

CONFIG_0930 = dict(
    objective='huber', alpha=1.0, learning_rate=0.03, num_leaves=8,
    max_depth=3, min_child_samples=50, reg_alpha=1.0, reg_lambda=5.0,
    n_estimators=300, verbose=-1, n_jobs=4
)
CONFIG_TIGHT = dict(
    objective='huber', alpha=0.5, learning_rate=0.03, num_leaves=15,
    max_depth=4, min_child_samples=100, feature_fraction=0.6,
    reg_alpha=1.0, reg_lambda=5.0, n_estimators=300, verbose=-1, n_jobs=4
)

N_SEEDS = 3  # 3-seed ensemble (faster, still robust)

REFERENCE_MONTHS = ['2024-06', '2024-07', '2024-09', '2025-04', '2025-09', '2025-11']
TOP_N = 3


def mins_to_time(mins):
    h = 9 + (30 + mins) // 60
    m = (30 + mins) % 60
    return f"{h:02d}:{m:02d}"


def simulate_trail_from_bars(sym_bars, entry_price, entry_time, trail_mode, date):
    """Bar-by-bar trail exit. Returns (pnl, exit_time, exit_price, peak_pct, details)."""
    day_bars = sym_bars[(sym_bars['date'] == date) & (sym_bars['time_et'] >= entry_time)]
    day_bars = day_bars.sort_values('time_et')

    if len(day_bars) == 0:
        return 0.0, entry_time, entry_price, 0.0, []

    peak = entry_price
    details = []

    for _, bar in day_bars.iterrows():
        t = bar['time_et']
        if trail_mode == 'decay':
            trail_pct = 0.03 if t < '10:00' else (0.02 if t < '10:30' else 0.01)
        else:
            trail_pct = 0.03

        if bar['high'] > peak:
            peak = bar['high']
        trail_level = peak * (1 - trail_pct)

        details.append({
            'time': t, 'open': bar['open'], 'high': bar['high'],
            'low': bar['low'], 'close': bar['close'],
            'peak': peak, 'trail_pct': trail_pct, 'trail_level': trail_level
        })

        if bar['low'] <= trail_level:
            exit_price = trail_level
            pnl = (exit_price / entry_price - 1) * 100
            return pnl, t, exit_price, (peak / entry_price - 1) * 100, details

    exit_price = day_bars.iloc[-1]['close']
    pnl = (exit_price / entry_price - 1) * 100
    return pnl, day_bars.iloc[-1]['time_et'], exit_price, (peak / entry_price - 1) * 100, details


def main():
    t0 = _time.time()

    print("Loading features and precomputed labels...")
    df_all = pd.read_pickle(PKL_PATH)
    df_all['date'] = pd.to_datetime(df_all['date']).dt.strftime('%Y-%m-%d')
    labels = pd.read_pickle(LABELS_PATH)
    df_all['label_decay'] = labels['label_decay'].values
    df_all['label_fixed3'] = labels['label_fixed3'].values

    for f in FEATURES_V9:
        if f in df_all.columns:
            df_all[f] = pd.to_numeric(df_all[f], errors='coerce')

    print(f"Loaded {len(df_all)} rows with labels")

    all_results = []
    bucket_results = defaultdict(list)
    month_results = {}

    for month in REFERENCE_MONTHS:
        print(f"\n{'='*70}")
        print(f"MONTH: {month}")
        print(f"{'='*70}")

        # Load bars for test month
        print(f"  Loading 5-min bars for {month}...", flush=True)
        conn = sqlite3.connect(DB_PATH)
        bars_month = pd.read_sql(f"""
            SELECT symbol, date, time_et, open, high, low, close, volume
            FROM intraday_bars_5m
            WHERE date LIKE '{month}%'
              AND time_et >= '09:30' AND time_et <= '16:00'
            ORDER BY symbol, date, time_et
        """, conn)
        conn.close()
        print(f"  {len(bars_month)} bars loaded")

        # Build lookup
        bars_lookup = {}
        for (sym, date), grp in bars_month.groupby(['symbol', 'date']):
            bars_lookup[(sym, date)] = grp.sort_values('time_et')

        month_picks = []

        for bkt_name, mins_lo, mins_hi, features, threshold, trail_mode in BUCKETS:
            bkt_t0 = _time.time()

            # Label column
            label_col = 'label_decay' if trail_mode == 'decay' else 'label_fixed3'

            # Split
            test_mask = (df_all['date'] >= f'{month}-01') & (df_all['date'] <= f'{month}-31')
            test_mask &= (df_all['mins_from_open'] >= mins_lo) & (df_all['mins_from_open'] <= mins_hi)

            train_mask = (df_all['date'] < f'{month}-01')
            train_mask &= (df_all['mins_from_open'] >= mins_lo) & (df_all['mins_from_open'] <= mins_hi)

            df_test = df_all[test_mask].copy()
            df_train = df_all[train_mask].copy()

            if len(df_test) == 0 or len(df_train) < 100:
                print(f"  [{bkt_name}] Insufficient data (train={len(df_train)}, test={len(df_test)})")
                continue

            avail_features = [f for f in features if f in df_all.columns]

            print(f"  [{bkt_name}] Train: {len(df_train)}, Test: {len(df_test)}", flush=True)

            # Cap training to most recent 6 months for speed
            # (still captures seasonality, avoids slow training on 300K rows)
            from datetime import datetime, timedelta
            import calendar
            cutoff_date = (datetime.strptime(f'{month}-01', '%Y-%m-%d') - timedelta(days=180)).strftime('%Y-%m-%d')
            df_train = df_train[df_train['date'] >= cutoff_date]
            if len(df_train) < 100:
                print(f"  [{bkt_name}] Too few samples after 6-month cap ({len(df_train)})")
                continue

            # Train N_SEEDS-seed ensemble
            config = CONFIG_0930 if bkt_name == '0930' else CONFIG_TIGHT
            models = []
            X_train = df_train[avail_features].fillna(0).values
            y_train = df_train[label_col].values

            for seed in range(N_SEEDS):
                cfg = {**config, 'random_state': seed}
                model = lgb.LGBMRegressor(**cfg)
                model.fit(X_train, y_train)
                models.append(model)

            # Predict
            X_test = df_test[avail_features].fillna(0).values
            preds = np.mean([m.predict(X_test) for m in models], axis=0)
            df_test['pred'] = preds

            # Filter + dedup + top N
            df_pass = df_test[df_test['pred'] >= threshold].copy()
            df_pass = df_pass.sort_values('mins_from_open')
            df_pass = df_pass.drop_duplicates(subset=['sym', 'date'], keep='first')

            picks_list = []
            for date, grp in df_pass.groupby('date'):
                top = grp.nlargest(TOP_N, 'pred')
                picks_list.append(top)

            if not picks_list:
                print(f"  [{bkt_name}] 0 picks (max pred: {df_test['pred'].max():.4f}, "
                      f"threshold: {threshold}) [{_time.time()-bkt_t0:.1f}s]")
                continue

            df_picks = pd.concat(picks_list)

            # Simulate with actual bars
            for idx, row in df_picks.iterrows():
                sym = row['sym']
                date = row['date']
                entry_mins = int(row['mins_from_open'])
                entry_time = mins_to_time(entry_mins)

                key = (sym, date)
                if key not in bars_lookup:
                    continue

                sym_bars = bars_lookup[key]
                entry_bar = sym_bars[sym_bars['time_et'] >= entry_time]
                if len(entry_bar) == 0:
                    continue

                entry_price = entry_bar.iloc[0]['open']
                actual_entry_time = entry_bar.iloc[0]['time_et']
                if entry_price <= 0:
                    continue

                pnl, exit_time, exit_price, peak_pct, details = simulate_trail_from_bars(
                    sym_bars, entry_price, actual_entry_time, trail_mode, date)

                result = {
                    'month': month, 'bucket': bkt_name, 'date': date,
                    'sym': sym, 'entry_time': actual_entry_time,
                    'entry_price': entry_price, 'exit_time': exit_time,
                    'exit_price': exit_price, 'pnl': pnl, 'peak_pct': peak_pct,
                    'pred': row['pred'], 'trail_mode': trail_mode,
                    'trail_details': details
                }
                all_results.append(result)
                bucket_results[bkt_name].append(result)
                month_picks.append(result)

            elapsed = _time.time() - bkt_t0
            bkt_wins = sum(1 for r in bucket_results[bkt_name] if r['month'] == month and r['pnl'] > 0)
            bkt_month = [r for r in bucket_results[bkt_name] if r['month'] == month]
            bkt_wr = bkt_wins / len(bkt_month) * 100 if bkt_month else 0
            print(f"  [{bkt_name}] {len(df_picks)} picks, "
                  f"WR={bkt_wr:.0f}% [{elapsed:.1f}s]")

        # Month summary
        if month_picks:
            wins = sum(1 for r in month_picks if r['pnl'] > 0)
            wr = wins / len(month_picks) * 100
            avg_pnl = np.mean([r['pnl'] for r in month_picks])
            total_pnl = np.sum([r['pnl'] for r in month_picks])
            month_results[month] = {
                'picks': len(month_picks), 'wins': wins, 'wr': wr,
                'avg_pnl': avg_pnl, 'total_pnl': total_pnl
            }
            print(f"\n  >>> {month}: {len(month_picks)} picks, WR={wr:.1f}%, "
                  f"avg={avg_pnl:+.2f}%, total={total_pnl:+.2f}%")
        else:
            month_results[month] = {'picks': 0, 'wins': 0, 'wr': 0, 'avg_pnl': 0, 'total_pnl': 0}
            print(f"\n  >>> {month}: 0 picks")

    # ────────────────────────── FINAL REPORT ──────────────────────────
    print(f"\n{'='*70}")
    print("FINAL REPORT — Walk-Forward v9.1 Verification (OUT-OF-SAMPLE)")
    print(f"{'='*70}")
    print("Method: Rolling retrain on data BEFORE each test month")
    print("Labels: Computed from ACTUAL 5-min bars (not pkl trail3_pnl)")
    print(f"Training data: 2024-04 to 2026-04 (pkl)")

    print("\n--- PER MONTH ---")
    regimes = {'2024-06': 'MIXED', '2024-07': 'MIXED', '2024-09': 'MIXED',
               '2025-04': 'BEAR', '2025-09': 'MIXED', '2025-11': 'BULL'}
    print(f"{'Month':<12} {'Regime':<8} {'Picks':>6} {'Wins':>6} {'WR%':>8} {'AvgPnL':>9} {'TotalPnL':>10}")
    print("-" * 65)
    for month in REFERENCE_MONTHS:
        r = month_results[month]
        regime = regimes.get(month, '?')
        print(f"{month:<12} {regime:<8} {r['picks']:>6} {r['wins']:>6} {r['wr']:>7.1f}% "
              f"{r['avg_pnl']:>+8.2f}% {r['total_pnl']:>+9.2f}%")

    print("\n--- PER BUCKET ---")
    print(f"{'Bucket':<12} {'Window':<14} {'Picks':>6} {'Wins':>6} {'WR%':>8} {'AvgPnL':>9} {'TotalPnL':>10}")
    print("-" * 70)
    windows = {'0930': '09:30-10:00', '1000': '10:00-10:45', '1045': '10:45-11:30', '1130': '11:30-13:00'}
    for bkt in ['0930', '1000', '1045', '1130']:
        results = bucket_results[bkt]
        if results:
            wins = sum(1 for r in results if r['pnl'] > 0)
            wr = wins / len(results) * 100
            avg = np.mean([r['pnl'] for r in results])
            total = np.sum([r['pnl'] for r in results])
            print(f"{bkt:<12} {windows[bkt]:<14} {len(results):>6} {wins:>6} {wr:>7.1f}% "
                  f"{avg:>+8.2f}% {total:>+9.2f}%")
        else:
            print(f"{bkt:<12} {windows[bkt]:<14}      0      0    0.0%    +0.00%     +0.00%")

    print("\n--- OVERALL ---")
    if all_results:
        total_wins = sum(1 for r in all_results if r['pnl'] > 0)
        total_wr = total_wins / len(all_results) * 100
        overall_avg = np.mean([r['pnl'] for r in all_results])
        overall_total = np.sum([r['pnl'] for r in all_results])
        profitable_months = sum(1 for m in REFERENCE_MONTHS if month_results[m]['total_pnl'] > 0)

        print(f"Total picks:        {len(all_results)}")
        print(f"Overall WR:         {total_wr:.1f}% ({total_wins}/{len(all_results)})")
        print(f"Overall avg PnL:    {overall_avg:+.3f}%")
        print(f"Overall total PnL:  {overall_total:+.2f}%")
        print(f"Profitable months:  {profitable_months}/{len(REFERENCE_MONTHS)}")

        # Win/loss distribution
        pnls = [r['pnl'] for r in all_results]
        print(f"\nPnL distribution:")
        print(f"  Median:  {np.median(pnls):+.3f}%")
        print(f"  p25:     {np.percentile(pnls, 25):+.3f}%")
        print(f"  p75:     {np.percentile(pnls, 75):+.3f}%")
        print(f"  Best:    {max(pnls):+.3f}%")
        print(f"  Worst:   {min(pnls):+.3f}%")
    else:
        print("No picks generated.")

    # ────────────────────────── BAR-BY-BAR VERIFICATION ──────────────────────────
    print(f"\n{'='*70}")
    print("BAR-BY-BAR VERIFICATION")
    print(f"{'='*70}")

    winners = sorted([r for r in all_results if r['pnl'] > 0.3], key=lambda r: r['pnl'], reverse=True)
    losers = sorted([r for r in all_results if r['pnl'] < -0.3], key=lambda r: r['pnl'])

    verify_trades = []
    if winners:
        verify_trades.append(('WINNER', winners[min(2, len(winners)-1)]))
    if losers:
        verify_trades.append(('LOSER', losers[min(2, len(losers)-1)]))
    elif all_results:
        verify_trades.append(('WORST', min(all_results, key=lambda r: r['pnl'])))

    for label, trade in verify_trades:
        print(f"\n--- {label}: {trade['sym']} on {trade['date']} (bucket={trade['bucket']}) ---")
        print(f"Entry: {trade['entry_time']} @ ${trade['entry_price']:.2f}")
        print(f"Exit:  {trade['exit_time']} @ ${trade['exit_price']:.2f}")
        print(f"PnL:   {trade['pnl']:+.2f}%")
        print(f"Peak from entry: {trade['peak_pct']:+.2f}%")
        print(f"Trail mode: {trade['trail_mode']}, Pred score: {trade['pred']:.4f}")
        print()
        print(f"{'Bar#':>4} {'Time':<8} {'Open':>8} {'High':>8} {'Low':>8} {'Close':>8} "
              f"{'Peak':>8} {'Trail%':>7} {'TrailLvl':>9} {'Note'}")
        print("-" * 90)
        for i, d in enumerate(trade['trail_details'][:50]):
            note = ''
            if d['low'] <= d['trail_level']:
                note = '<-- TRAIL HIT (EXIT)'
            elif d['high'] == d['peak'] and d['high'] > trade['entry_price']:
                note = '<-- NEW PEAK'
            print(f"{i+1:>4} {d['time']:<8} {d['open']:>8.2f} {d['high']:>8.2f} {d['low']:>8.2f} "
                  f"{d['close']:>8.2f} {d['peak']:>8.2f} {d['trail_pct']*100:>6.1f}% "
                  f"{d['trail_level']:>9.2f} {note}")

    # ────────────────────────── SAMPLE PICKS ──────────────────────────
    print(f"\n{'='*70}")
    print("SAMPLE PICKS (first 5 per month)")
    print(f"{'='*70}")
    for month in REFERENCE_MONTHS:
        month_trades = [r for r in all_results if r['month'] == month]
        if not month_trades:
            print(f"\n{month}: no picks")
            continue
        print(f"\n{month} ({len(month_trades)} total picks):")
        print(f"  {'Date':<12} {'Sym':<8} {'Bucket':<8} {'Entry':<7} {'EntryP':>8} "
              f"{'Exit':<7} {'ExitP':>8} {'PnL':>8} {'Pred':>7}")
        for r in month_trades[:5]:
            print(f"  {r['date']:<12} {r['sym']:<8} {r['bucket']:<8} {r['entry_time']:<7} "
                  f"${r['entry_price']:>7.2f} {r['exit_time']:<7} ${r['exit_price']:>7.2f} "
                  f"{r['pnl']:>+7.2f}% {r['pred']:>6.3f}")

    elapsed = _time.time() - t0
    print(f"\nTotal elapsed: {elapsed:.0f}s ({elapsed/60:.1f} min)")


if __name__ == '__main__':
    main()
