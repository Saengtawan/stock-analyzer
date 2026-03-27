#!/usr/bin/env python3
"""
Bandwidth Sensitivity Test for 9-Feature MacroKernel.

Optimized: pre-indexes data by date, uses numpy arrays for fast kernel ops.
Tests macro_bw × stock_bw grid + ablation + yearly stability.
"""
import datetime as _dt
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

BULL_ER = 0.5
STRESS_ER = -0.5
MIN_TRAIN_DAYS = 20
TP_PCT = 3.0

DEFENSIVE_SECTORS = frozenset({
    'Utilities', 'Healthcare', 'Basic Materials', 'Real Estate', 'Energy',
})
CRISIS_DEFENSIVE = frozenset({
    'Utilities', 'Real Estate', 'Energy',
})

MACRO_9 = ['new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
           'new_52w_highs', 'yield_10y', 'spy_close',
           'crude_close', 'vix_term_spread', 'yield_spread']

STOCK_14 = MACRO_9 + ['atr_pct', 'momentum_5d', 'volume_ratio',
                       'distance_from_20d_high', 'sector_1d_change']


def flush_print(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()


class FastKernel:
    """Optimized kernel: fits once, caches Z-scored matrix."""
    def __init__(self, bandwidth, features):
        self.bw = bandwidth
        self.features = features
        self.n_feat = len(features)
        self.X = None
        self.y = None
        self.mu = None
        self.sigma = None

    def fit(self, rows_array, rets_array):
        """Fit from pre-extracted numpy arrays (no dict lookups)."""
        if len(rows_array) < 10:
            self.X = None
            return
        self.X = rows_array.copy()
        self.y = rets_array.copy()
        self.mu = self.X.mean(axis=0)
        self.sigma = self.X.std(axis=0)
        self.sigma[self.sigma == 0] = 1.0
        self.X = (self.X - self.mu) / self.sigma

    def estimate(self, x_raw):
        """Estimate E[R] for a single point (raw, not Z-scored)."""
        if self.X is None:
            return 0.0, 0.0
        x = (x_raw - self.mu) / self.sigma
        dists = np.sqrt(np.sum((self.X - x) ** 2, axis=1))
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)
        total_w = weights.sum()
        if total_w < 1e-10:
            return 0.0, 0.0
        er = float(np.dot(weights, self.y) / total_w)
        n_eff = float(total_w ** 2 / np.sum(weights ** 2))
        return er, n_eff

    def estimate_batch(self, X_test):
        """Estimate E[R] for multiple points at once."""
        if self.X is None:
            return np.zeros(len(X_test)), np.zeros(len(X_test))
        X_z = (X_test - self.mu) / self.sigma
        # (n_test, 1, n_feat) - (1, n_train, n_feat)
        diffs = X_z[:, np.newaxis, :] - self.X[np.newaxis, :, :]
        dists = np.sqrt(np.sum(diffs ** 2, axis=2))  # (n_test, n_train)
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)
        total_w = weights.sum(axis=1)  # (n_test,)
        safe = total_w > 1e-10
        ers = np.zeros(len(X_test))
        n_effs = np.zeros(len(X_test))
        if safe.any():
            ers[safe] = np.dot(weights[safe], self.y) / total_w[safe]
            n_effs[safe] = total_w[safe] ** 2 / np.sum(weights[safe] ** 2, axis=1)
        return ers, n_effs


def load_data():
    conn = None  # via get_session())
    conn.row_factory = dict

    live_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector,
               s.atr_pct, s.entry_rsi, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio,
               s.outcome_5d, s.outcome_max_gain_5d, s.outcome_max_dd_5d
        FROM signal_outcomes s
        WHERE s.outcome_5d IS NOT NULL AND s.atr_pct IS NOT NULL
          AND s.signal_source = 'dip_bounce'
    """).fetchall()

    backfill_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector,
               s.atr_pct, s.entry_rsi, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio,
               s.outcome_5d, s.outcome_max_gain_5d, s.outcome_max_dd_5d
        FROM backfill_signal_outcomes s
        WHERE s.outcome_5d IS NOT NULL
    """).fetchall()

    macro_rows = conn.execute("""
        SELECT date, crude_close, yield_10y, spy_close,
               vix_close, vix3m_close, yield_spread
        FROM macro_snapshots WHERE crude_close IS NOT NULL
    """).fetchall()

    breadth_rows = conn.execute("""
        SELECT date, pct_above_20d_ma, new_52w_lows, new_52w_highs
        FROM market_breadth
    """).fetchall()

    sector_rows = conn.execute("""
        SELECT date, sector, pct_change
        FROM sector_etf_daily_returns WHERE pct_change IS NOT NULL
    """).fetchall()
    conn.close()

    macro_by_date = {r['date']: dict(r) for r in macro_rows}
    breadth_by_date = {r['date']: dict(r) for r in breadth_rows}
    sector_by_ds = {(r['date'], r['sector']): r['pct_change'] for r in sector_rows}

    crude_series = sorted(
        [(r['date'], r['crude_close']) for r in macro_rows if r['crude_close']],
        key=lambda x: x[0])
    crude_chg = {}
    for i, (d, c) in enumerate(crude_series):
        if i >= 5 and crude_series[i-5][1] > 0:
            crude_chg[d] = (c / crude_series[i-5][1] - 1) * 100

    vix_spread = {}
    for r in macro_rows:
        if r['vix_close'] is not None and r['vix3m_close'] is not None:
            vix_spread[r['date']] = r['vix_close'] - r['vix3m_close']

    combined = []
    for r in backfill_rows:
        d = dict(r); d['source'] = 'backfill'; combined.append(d)
    for r in live_rows:
        d = dict(r); d['source'] = 'live'; combined.append(d)

    seen = {}
    for row in combined:
        key = (row['scan_date'], row['symbol'])
        if key in seen:
            if row['source'] == 'live': seen[key] = row
        else: seen[key] = row
    combined = sorted(seen.values(), key=lambda r: r['scan_date'])

    for row in combined:
        sd = row['scan_date']
        d_obj = _dt.date.fromisoformat(sd)
        wd = d_obj.weekday()
        if wd == 5: macro_d = (d_obj - _dt.timedelta(days=1)).isoformat()
        elif wd == 6: macro_d = (d_obj - _dt.timedelta(days=2)).isoformat()
        else: macro_d = sd

        m = macro_by_date.get(macro_d, {})
        b = breadth_by_date.get(macro_d, {})
        row['crude_close'] = m.get('crude_close')
        row['yield_10y'] = m.get('yield_10y')
        row['spy_close'] = m.get('spy_close')
        row['yield_spread'] = m.get('yield_spread')
        row['pct_above_20d_ma'] = b.get('pct_above_20d_ma')
        row['new_52w_lows'] = b.get('new_52w_lows')
        row['new_52w_highs'] = b.get('new_52w_highs')
        row['crude_change_5d'] = crude_chg.get(macro_d)
        row['vix_term_spread'] = vix_spread.get(macro_d)
        row['sector_1d_change'] = sector_by_ds.get((macro_d, row.get('sector', '')))

    flush_print(f"Dataset: {len(combined)} rows, {len(set(r['scan_date'] for r in combined))} dates")
    return combined


def extract_features(data, features):
    """Pre-extract feature arrays indexed by date for fast kernel ops."""
    # Group by date
    by_date = defaultdict(list)
    for row in data:
        by_date[row['scan_date']].append(row)

    dates = sorted(by_date.keys())

    # For each date, extract feature matrix + returns
    date_data = {}
    for d in dates:
        rows = by_date[d]
        feat_rows = []
        ret_rows = []
        meta_rows = []
        for r in rows:
            vals = [r.get(f) for f in features]
            if any(v is None for v in vals):
                continue
            feat_rows.append(vals)
            ret_rows.append(r['outcome_5d'])
            meta_rows.append(r)
        if feat_rows:
            date_data[d] = {
                'X': np.array(feat_rows, dtype=float),
                'y': np.array(ret_rows, dtype=float),
                'meta': meta_rows,
            }

    return dates, date_data


def run_backtest_fast(data, macro_features, stock_features, macro_bw, stock_bw):
    """Optimized walk-forward using pre-indexed data + batch estimation."""
    # Pre-extract ALL features (superset)
    all_features = list(dict.fromkeys(stock_features))  # stock includes macro

    by_date = defaultdict(list)
    for row in data:
        by_date[row['scan_date']].append(row)
    dates = sorted(by_date.keys())

    # Build cumulative training arrays
    # Pre-extract feature indices
    macro_idx = [all_features.index(f) for f in macro_features]
    stock_idx = [all_features.index(f) for f in stock_features]

    results = []
    regime_counts = defaultdict(int)
    skipped = 0

    # Cumulative training data
    all_X = []
    all_y = []
    prev_dates = set()

    for di, test_date in enumerate(dates):
        test_rows = by_date[test_date]
        if not test_rows:
            continue

        # Check if enough training data
        can_test = len(prev_dates) >= MIN_TRAIN_DAYS and len(all_X) >= 50

        if can_test:
            train_X = np.array(all_X, dtype=float)
            train_y = np.array(all_y, dtype=float)

            # Stage 1: MacroKernel → regime
            macro_train_X = train_X[:, macro_idx]
            macro_k = FastKernel(macro_bw, macro_features)
            macro_k.fit(macro_train_X, train_y)

            # Find a test row with complete features for macro estimation
            test_vals_0 = None
            for r in test_rows:
                v = [r.get(f) for f in all_features]
                if not any(x is None for x in v):
                    test_vals_0 = v
                    break

            if test_vals_0 is not None:
                macro_x = np.array([test_vals_0[i] for i in macro_idx], dtype=float)
                macro_er, macro_neff = macro_k.estimate(macro_x)

                if macro_neff >= 3.0:
                    if macro_er > BULL_ER:
                        regime, max_picks = 'BULL', 5
                    elif macro_er > STRESS_ER:
                        regime, max_picks = 'STRESS', 3
                    else:
                        regime, max_picks = 'CRISIS', 2
                    regime_counts[regime] += 1

                    # Stage 2: StockKernel batch estimation
                    stock_train_X = train_X[:, stock_idx]
                    stock_k = FastKernel(stock_bw, stock_features)
                    stock_k.fit(stock_train_X, train_y)

                    test_feat = []
                    test_meta = []
                    for r in test_rows:
                        vals = [r.get(f) for f in all_features]
                        if any(v is None for v in vals):
                            continue
                        test_feat.append([vals[i] for i in stock_idx])
                        test_meta.append(r)

                    if test_feat:
                        test_X_arr = np.array(test_feat, dtype=float)
                        stock_ers, stock_neffs = stock_k.estimate_batch(test_X_arr)
                        stock_ers[stock_neffs < 3.0] = 0.0

                        scored = []
                        for i, row in enumerate(test_meta):
                            ser = stock_ers[i]
                            if regime == 'STRESS':
                                atr = row.get('atr_pct') or 99
                                mom5 = row.get('momentum_5d') or 0
                                sector = row.get('sector') or ''
                                bonus = 0
                                if atr < 2.5: bonus += 1
                                if mom5 < 0: bonus += 1
                                if (row.get('volume_ratio') or 0) > 1.2: bonus += 1
                                if sector in DEFENSIVE_SECTORS: bonus += 1
                                if bonus < 2: continue
                                ser += bonus * 0.5
                            elif regime == 'CRISIS':
                                mom5 = row.get('momentum_5d') or 0
                                sector = row.get('sector') or ''
                                bonus = 0
                                if (row.get('atr_pct') or 99) < 2.5: bonus += 1
                                if mom5 < -2: bonus += 1
                                if (row.get('volume_ratio') or 0) > 1.5: bonus += 1
                                if sector in CRISIS_DEFENSIVE: bonus += 1
                                if bonus < 3: continue
                                ser += bonus * 0.5
                            scored.append((ser, row))

                        scored.sort(key=lambda x: x[0], reverse=True)
                        for ser, row in scored[:max_picks]:
                            atr = row.get('atr_pct') or 3.0
                            if regime == 'BULL': dyn_sl = min(max(atr * 2.0, 1.5), 5.0)
                            elif regime == 'STRESS': dyn_sl = min(max(atr * 1.5, 1.5), 5.0)
                            else: dyn_sl = min(max(atr * 1.0, 1.5), 5.0)

                            mg = row.get('outcome_max_gain_5d')
                            md = row.get('outcome_max_dd_5d')
                            if mg is not None and md is not None:
                                if md <= -dyn_sl: capped = -dyn_sl
                                elif mg >= TP_PCT: capped = TP_PCT
                                else: capped = row['outcome_5d']
                            else:
                                capped = row['outcome_5d']

                            results.append({
                                'date': test_date, 'regime': regime,
                                'capped_return': capped,
                            })
                    else:
                        skipped += 1
                else:
                    skipped += 1
            else:
                skipped += 1
        else:
            skipped += 1

        # ALWAYS add test data to training pool (expanding window)
        for r in test_rows:
            vals = [r.get(f) for f in all_features]
            if any(v is None for v in vals):
                continue
            all_X.append(vals)
            all_y.append(r['outcome_5d'])
        prev_dates.add(test_date)

    return results, dict(regime_counts), skipped


def calc_metrics(results):
    if not results:
        return {'pnl': 0, 'wr': 0, 'sl': 0, 'n': 0, 'avg': 0, 'regimes': {}}
    n = len(results)
    cr = [r['capped_return'] for r in results]
    regime_data = {}
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        rr = [r['capped_return'] for r in results if r['regime'] == regime]
        if rr:
            regime_data[regime] = {
                'pnl': sum(rr), 'wr': sum(1 for c in rr if c > 0) / len(rr) * 100,
                'n': len(rr), 'avg': np.mean(rr),
            }
        else:
            regime_data[regime] = {'pnl': 0, 'wr': 0, 'n': 0, 'avg': 0}
    return {
        'pnl': sum(cr), 'wr': sum(1 for c in cr if c > 0) / n * 100,
        'sl': sum(1 for c in cr if c < -1.4) / n * 100,
        'n': n, 'avg': np.mean(cr), 'regimes': regime_data,
    }


def main():
    data = load_data()

    # ===== PART 1: BANDWIDTH GRID SEARCH =====
    flush_print(f"\n{'='*80}")
    flush_print(f"  PART 1: BANDWIDTH SENSITIVITY (9M MacroKernel)")
    flush_print(f"{'='*80}")

    macro_bws = [0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
    stock_bws = [0.8, 1.0, 1.2, 1.5]

    header = f"  {'macro_bw':<10}"
    for sb in stock_bws:
        header += f" {'sbw='+str(sb):>18}"
    flush_print(header)
    flush_print(f"  {'─'*78}")

    best_pnl = -999999
    best_combo = (0.6, 1.0)
    grid_results = {}

    for mbw in macro_bws:
        line = f"  mbw={mbw:<5.1f}"
        for sbw in stock_bws:
            flush_print(f"    Testing mbw={mbw} sbw={sbw}...")
            results, _, _ = run_backtest_fast(data, MACRO_9, STOCK_14, mbw, sbw)
            m = calc_metrics(results)
            grid_results[(mbw, sbw)] = m
            pnl_str = f"{m['pnl']:+.0f}% W{m['wr']:.0f}%"
            line += f" {pnl_str:>18}"
            if m['pnl'] > best_pnl:
                best_pnl = m['pnl']
                best_combo = (mbw, sbw)
        flush_print(line)

    flush_print(f"\n  Best: macro_bw={best_combo[0]}, stock_bw={best_combo[1]} "
                f"→ PnL={best_pnl:+.0f}%")

    ranked = sorted(grid_results.items(), key=lambda x: x[1]['pnl'], reverse=True)
    flush_print(f"\n  Top 5 combos:")
    flush_print(f"  {'macro_bw':>8} {'stock_bw':>8} {'PnL':>10} {'WR':>6} {'SL':>6} {'n':>6} "
                f"{'BULL PnL':>10} {'STRESS PnL':>12} {'CRISIS PnL':>12}")
    for (mbw, sbw), m in ranked[:5]:
        flush_print(f"  {mbw:>8.1f} {sbw:>8.1f} {m['pnl']:>+10.0f} {m['wr']:>5.1f}% "
                    f"{m['sl']:>5.1f}% {m['n']:>5d} "
                    f"{m['regimes'].get('BULL', {}).get('pnl', 0):>+10.0f} "
                    f"{m['regimes'].get('STRESS', {}).get('pnl', 0):>+12.0f} "
                    f"{m['regimes'].get('CRISIS', {}).get('pnl', 0):>+12.0f}")

    # ===== PART 2: ABLATION STUDY =====
    flush_print(f"\n{'='*80}")
    flush_print(f"  PART 2: ABLATION — Remove each new feature one-at-a-time")
    flush_print(f"{'='*80}")

    best_mbw, best_sbw = best_combo
    flush_print(f"  Using best bw: macro={best_mbw}, stock={best_sbw}\n")

    base_r, _, _ = run_backtest_fast(data, MACRO_9, STOCK_14, best_mbw, best_sbw)
    base_m = calc_metrics(base_r)

    ablation_configs = {
        'ALL 9 (baseline)': (MACRO_9, STOCK_14),
        'DROP crude_close': (
            [f for f in MACRO_9 if f != 'crude_close'],
            [f for f in STOCK_14 if f != 'crude_close']),
        'DROP vix_term_spread': (
            [f for f in MACRO_9 if f != 'vix_term_spread'],
            [f for f in STOCK_14 if f != 'vix_term_spread']),
        'DROP yield_spread': (
            [f for f in MACRO_9 if f != 'yield_spread'],
            [f for f in STOCK_14 if f != 'yield_spread']),
        'DROP crude_change_5d': (
            [f for f in MACRO_9 if f != 'crude_change_5d'],
            [f for f in STOCK_14 if f != 'crude_change_5d']),
        'ONLY +crude_close': (
            [f for f in MACRO_9 if f not in ('vix_term_spread', 'yield_spread')],
            [f for f in STOCK_14 if f not in ('vix_term_spread', 'yield_spread')]),
        'ONLY +vix_term_spread': (
            [f for f in MACRO_9 if f not in ('crude_close', 'yield_spread')],
            [f for f in STOCK_14 if f not in ('crude_close', 'yield_spread')]),
        'Original 6M': (
            [f for f in MACRO_9 if f not in ('crude_close', 'vix_term_spread', 'yield_spread')],
            [f for f in STOCK_14 if f not in ('crude_close', 'vix_term_spread', 'yield_spread')]),
    }

    flush_print(f"  {'Config':<25} {'PnL':>8} {'WR':>6} {'SL':>6} {'n':>5} "
                f"{'BULL':>8} {'STRESS':>8} {'CRISIS':>8} {'vs base':>10}")
    flush_print(f"  {'─'*90}")

    for label, (mf, sf) in ablation_configs.items():
        flush_print(f"    Running {label}...")
        r, _, _ = run_backtest_fast(data, mf, sf, best_mbw, best_sbw)
        m = calc_metrics(r)
        delta = m['pnl'] - base_m['pnl']
        flush_print(f"  {label:<25} {m['pnl']:>+7.0f}% {m['wr']:>5.1f}% {m['sl']:>5.1f}% "
                    f"{m['n']:>5d} "
                    f"{m['regimes']['BULL']['pnl']:>+7.0f}% "
                    f"{m['regimes']['STRESS']['pnl']:>+7.0f}% "
                    f"{m['regimes']['CRISIS']['pnl']:>+7.0f}% "
                    f"{delta:>+10.0f}")

    # ===== PART 3: YEARLY STABILITY =====
    flush_print(f"\n{'='*80}")
    flush_print(f"  PART 3: YEARLY STABILITY — 9M vs 6M at best bw")
    flush_print(f"{'='*80}")

    orig_6m = [f for f in MACRO_9 if f not in ('crude_close', 'vix_term_spread', 'yield_spread')]
    orig_6s = [f for f in STOCK_14 if f not in ('crude_close', 'vix_term_spread', 'yield_spread')]

    flush_print(f"    Running 6M baseline...")
    r6, _, _ = run_backtest_fast(data, orig_6m, orig_6s, best_mbw, best_sbw)
    flush_print(f"    Running 9M...")
    r9, _, _ = run_backtest_fast(data, MACRO_9, STOCK_14, best_mbw, best_sbw)

    years = sorted(set(r['date'][:4] for r in r9))
    flush_print(f"\n  {'Year':<6} {'6M PnL':>8} {'6M WR':>6} {'6M n':>5} "
                f"{'9M PnL':>8} {'9M WR':>6} {'9M n':>5} {'Delta':>8}")
    flush_print(f"  {'─'*60}")

    for year in years:
        r6y = [r for r in r6 if r['date'].startswith(year)]
        r9y = [r for r in r9 if r['date'].startswith(year)]
        m6 = calc_metrics(r6y)
        m9 = calc_metrics(r9y)
        flush_print(f"  {year:<6} {m6['pnl']:>+7.0f}% {m6['wr']:>5.1f}% {m6['n']:>5d} "
                    f"{m9['pnl']:>+7.0f}% {m9['wr']:>5.1f}% {m9['n']:>5d} "
                    f"{m9['pnl']-m6['pnl']:>+7.0f}%")

    flush_print(f"\n{'='*80}")
    flush_print(f"  DONE")
    flush_print(f"{'='*80}")


if __name__ == '__main__':
    main()
