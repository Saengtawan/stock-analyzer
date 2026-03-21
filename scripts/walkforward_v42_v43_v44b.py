#!/usr/bin/env python3
"""Walk-Forward Replay: v4.2 vs v4.3 vs v4.4b — 3-way comparison."""
import datetime as _dt
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

MACRO_BW = 0.6
STOCK_BW = 1.0
BULL_ER = 0.5
STRESS_ER = -0.5

DEFENSIVE_SECTORS = frozenset({
    'Utilities', 'Healthcare', 'Basic Materials', 'Real Estate', 'Energy',
})
CRISIS_DEFENSIVE = frozenset({
    'Utilities', 'Real Estate', 'Energy',
})

MIN_TRAIN_DAYS = 20
TP_PCT = 3.0

# === VERSION CONFIGS ===
VERSIONS = {
    'v4.2': {
        'macro_features': ['new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
                           'new_52w_highs', 'yield_10y', 'spy_close'],
        'stock_features': ['new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
                           'new_52w_highs', 'yield_10y', 'spy_close',
                           'atr_pct', 'momentum_5d', 'volume_ratio', 'entry_rsi'],
        'crisis_block_pos_mom': False,
        'require_pos_er': False,
    },
    'v4.3': {
        'macro_features': ['new_52w_lows', 'crude_close', 'pct_above_20d_ma',
                           'new_52w_highs', 'yield_10y', 'spy_close'],
        'stock_features': ['new_52w_lows', 'crude_close', 'pct_above_20d_ma',
                           'new_52w_highs', 'yield_10y', 'spy_close',
                           'atr_pct', 'momentum_5d', 'volume_ratio', 'entry_rsi'],
        'crisis_block_pos_mom': False,
        'require_pos_er': False,
    },
    'v4.4b': {
        'macro_features': ['new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
                           'new_52w_highs', 'yield_10y', 'spy_close'],
        'stock_features': ['new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
                           'new_52w_highs', 'yield_10y', 'spy_close',
                           'atr_pct', 'momentum_5d', 'volume_ratio', 'entry_rsi'],
        'crisis_block_pos_mom': True,
        'require_pos_er': True,
    },
}


class GaussianKernel:
    def __init__(self, bandwidth, features):
        self.bw = bandwidth
        self.features = features
        self.X = np.array([])
        self.y = np.array([])
        self.mu = np.zeros(len(features))
        self.sigma = np.ones(len(features))

    def fit(self, data):
        rows, rets = [], []
        for r in data:
            vals = [r.get(f) for f in self.features]
            if any(v is None for v in vals):
                continue
            rows.append(vals)
            rets.append(r['outcome_5d'])
        if len(rows) < 10:
            self.X = np.array([])
            return
        self.X = np.array(rows, dtype=float)
        self.y = np.array(rets, dtype=float)
        self.mu = self.X.mean(axis=0)
        self.sigma = self.X.std(axis=0)
        self.sigma[self.sigma == 0] = 1.0
        self.X = (self.X - self.mu) / self.sigma

    def estimate(self, row):
        if len(self.X) == 0:
            return 0.0, 0.0
        vals = []
        for i, f in enumerate(self.features):
            v = row.get(f)
            if v is None:
                v = self.mu[i]
            vals.append(v)
        x = (np.array(vals, dtype=float) - self.mu) / self.sigma
        dists = np.sqrt(np.sum((self.X - x) ** 2, axis=1))
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)
        total_w = weights.sum()
        if total_w < 1e-10:
            return 0.0, 0.0
        er = float(np.sum(weights * self.y) / total_w)
        n_eff = float(total_w ** 2 / np.sum(weights ** 2))
        return er, n_eff


def load_data():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    live_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector,
               s.atr_pct, s.entry_rsi, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio, s.vix_at_signal,
               s.outcome_5d, s.outcome_max_gain_5d, s.outcome_max_dd_5d,
               m.crude_close, m.yield_10y, m.spy_close,
               b.pct_above_20d_ma, b.new_52w_lows, b.new_52w_highs
        FROM signal_outcomes s
        LEFT JOIN macro_snapshots m
            ON m.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        LEFT JOIN market_breadth b
            ON b.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        WHERE s.outcome_5d IS NOT NULL AND s.atr_pct IS NOT NULL
          AND s.signal_source = 'dip_bounce'
    """).fetchall()

    backfill_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector,
               s.atr_pct, s.entry_rsi, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio, s.vix_at_signal,
               s.outcome_5d, s.outcome_max_gain_5d, s.outcome_max_dd_5d,
               m.crude_close, m.yield_10y, m.spy_close,
               b.pct_above_20d_ma, b.new_52w_lows, b.new_52w_highs
        FROM backfill_signal_outcomes s
        LEFT JOIN macro_snapshots m
            ON m.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        LEFT JOIN market_breadth b
            ON b.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        WHERE s.outcome_5d IS NOT NULL
    """).fetchall()

    crude_series = conn.execute("""
        SELECT date, crude_close FROM macro_snapshots
        WHERE crude_close IS NOT NULL ORDER BY date
    """).fetchall()
    conn.close()

    crude_by_date = {r['date']: r['crude_close'] for r in crude_series}
    crude_dates = sorted(crude_by_date.keys())
    crude_chg_by_date = {}
    for i, d in enumerate(crude_dates):
        if i >= 5:
            c5 = crude_by_date[crude_dates[i - 5]]
            if c5 and c5 > 0:
                crude_chg_by_date[d] = (crude_by_date[d] / c5 - 1) * 100

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
        else:
            seen[key] = row
    combined = sorted(seen.values(), key=lambda r: r['scan_date'])

    for row in combined:
        sd = row['scan_date']
        d_obj = _dt.date.fromisoformat(sd)
        wd = d_obj.weekday()
        if wd == 5: macro_d = (d_obj - _dt.timedelta(days=1)).isoformat()
        elif wd == 6: macro_d = (d_obj - _dt.timedelta(days=2)).isoformat()
        else: macro_d = sd
        row['crude_change_5d'] = crude_chg_by_date.get(macro_d)

    print(f"Dataset: {len(combined)} rows, {len(set(r['scan_date'] for r in combined))} dates")
    return combined


def run_backtest(data, cfg, label):
    macro_f = cfg['macro_features']
    stock_f = cfg['stock_features']
    crisis_mom = cfg['crisis_block_pos_mom']
    pos_er = cfg['require_pos_er']

    dates = sorted(set(r['scan_date'] for r in data))
    results = []
    regime_counts = defaultdict(int)
    skipped = 0

    for test_date in dates:
        train = [r for r in data if r['scan_date'] < test_date]
        test = [r for r in data if r['scan_date'] == test_date]
        if not test: continue
        if len(set(r['scan_date'] for r in train)) < MIN_TRAIN_DAYS:
            skipped += 1; continue

        macro_k = GaussianKernel(MACRO_BW, macro_f)
        macro_k.fit(train)
        macro_er, macro_neff = macro_k.estimate(test[0])
        if macro_neff < 3.0:
            skipped += 1; continue

        if macro_er > BULL_ER:
            regime, max_picks, sl_pct = 'BULL', 5, 3.0
        elif macro_er > STRESS_ER:
            regime, max_picks, sl_pct = 'STRESS', 3, 2.0
        else:
            regime, max_picks, sl_pct = 'CRISIS', 2, 2.0
        regime_counts[regime] += 1

        stock_k = GaussianKernel(STOCK_BW, stock_f)
        stock_k.fit(train)

        scored = []
        for row in test:
            stock_er, stock_neff = stock_k.estimate(row)
            if stock_neff < 3.0: stock_er = 0.0

            if regime == 'STRESS':
                atr = row.get('atr_pct') or 99
                mom5 = row.get('momentum_5d') or 0
                sector = row.get('sector') or ''
                bonus = 0
                if atr < 2.5: bonus += 1
                if mom5 < 0: bonus += 1
                if row.get('volume_ratio', 0) > 1.2: bonus += 1
                if sector in DEFENSIVE_SECTORS: bonus += 1
                if bonus < 2: continue
                stock_er += bonus * 0.5
            elif regime == 'CRISIS':
                mom5 = row.get('momentum_5d') or 0
                sector = row.get('sector') or ''
                if crisis_mom and mom5 >= 0: continue
                bonus = 0
                if (row.get('atr_pct') or 99) < 2.5: bonus += 1
                if mom5 < -2: bonus += 1
                if (row.get('volume_ratio') or 0) > 1.5: bonus += 1
                if sector in CRISIS_DEFENSIVE: bonus += 1
                if bonus < 3: continue
                stock_er += bonus * 0.5

            if pos_er and stock_er < 0: continue
            scored.append((stock_er, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        for stock_er, row in scored[:max_picks]:
            mg = row.get('outcome_max_gain_5d')
            md = row.get('outcome_max_dd_5d')
            if mg is not None and md is not None:
                if md <= -sl_pct: capped = -sl_pct
                elif mg >= TP_PCT: capped = TP_PCT
                else: capped = row['outcome_5d']
            else:
                capped = row['outcome_5d']
            results.append({
                'date': test_date, 'symbol': row['symbol'], 'regime': regime,
                'capped_return': capped, 'sl_pct': sl_pct,
            })

    return results, dict(regime_counts)


def print_metrics(results, label):
    if not results:
        print(f"  {label}: NO PICKS"); return {}
    n = len(results)
    capped = [r['capped_return'] for r in results]
    total_pnl = sum(capped)
    wins = sum(1 for c in capped if c > 0)
    wr = wins / n * 100
    dates_set = sorted(set(r['date'] for r in results))

    regime_data = {}
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        rr = [r['capped_return'] for r in results if r['regime'] == regime]
        if rr:
            rw = sum(1 for c in rr if c > 0)
            regime_data[regime] = {'pnl': sum(rr), 'wr': rw/len(rr)*100, 'n': len(rr)}
        else:
            regime_data[regime] = {'pnl': 0, 'wr': 0, 'n': 0}

    return {
        'label': label, 'total_pnl': total_pnl, 'win_rate': wr,
        'n_picks': n, 'n_days': len(dates_set),
        'avg_return': np.mean(capped),
        'regimes': regime_data,
    }


def main():
    data = load_data()

    all_metrics = {}
    for ver, cfg in VERSIONS.items():
        results, regimes = run_backtest(data, cfg, ver)
        m = print_metrics(results, ver)
        all_metrics[ver] = m

    # === 3-WAY COMPARISON TABLE ===
    print(f"\n{'='*75}")
    print(f"  3-WAY COMPARISON: v4.2 vs v4.3 vs v4.4b")
    print(f"{'='*75}")
    print(f"{'Metric':<25} {'v4.2':>14} {'v4.3':>14} {'v4.4b':>14}")
    print(f"{'─'*67}")

    for label, key, fmt in [
        ('Total PnL (%)', 'total_pnl', '.2f'),
        ('Avg Return (%)', 'avg_return', '.3f'),
        ('Win Rate (%)', 'win_rate', '.1f'),
        ('Total Picks', 'n_picks', 'd'),
        ('Trading Days', 'n_days', 'd'),
    ]:
        vals = [all_metrics[v][key] for v in ['v4.2', 'v4.3', 'v4.4b']]
        strs = [format(v, fmt) for v in vals]
        print(f"  {label:<23} {strs[0]:>14} {strs[1]:>14} {strs[2]:>14}")

    # Per-regime
    print(f"\n{'─'*67}")
    print(f"  {'PER-REGIME':<23} {'v4.2':>14} {'v4.3':>14} {'v4.4b':>14}")
    print(f"{'─'*67}")
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        vals = []
        for v in ['v4.2', 'v4.3', 'v4.4b']:
            rd = all_metrics[v]['regimes'][regime]
            if rd['n'] > 0:
                vals.append(f"{rd['pnl']:+.1f}% W{rd['wr']:.0f}% n={rd['n']}")
            else:
                vals.append("—")
        print(f"  {regime:<23} {vals[0]:>14} {vals[1]:>14} {vals[2]:>14}")

    # Best version per metric
    print(f"\n{'─'*67}")
    print(f"  WINNER:")
    pnls = {v: all_metrics[v]['total_pnl'] for v in VERSIONS}
    best_pnl = max(pnls, key=pnls.get)
    print(f"    Total PnL: {best_pnl} ({pnls[best_pnl]:+.2f}%)")

    wrs = {v: all_metrics[v]['win_rate'] for v in VERSIONS}
    best_wr = max(wrs, key=wrs.get)
    print(f"    Win Rate: {best_wr} ({wrs[best_wr]:.1f}%)")

    # CRISIS quality
    crisis_wrs = {}
    for v in VERSIONS:
        cd = all_metrics[v]['regimes']['CRISIS']
        if cd['n'] > 0:
            crisis_wrs[v] = cd['wr']
    if crisis_wrs:
        best_crisis = max(crisis_wrs, key=crisis_wrs.get)
        print(f"    CRISIS WR: {best_crisis} ({crisis_wrs[best_crisis]:.1f}%)")

    # STRESS
    stress_pnl = {}
    for v in VERSIONS:
        sd = all_metrics[v]['regimes']['STRESS']
        if sd['n'] > 0:
            stress_pnl[v] = sd['pnl']
    if stress_pnl:
        best_stress = max(stress_pnl, key=stress_pnl.get)
        print(f"    STRESS PnL: {best_stress} ({stress_pnl[best_stress]:+.1f}%)")

    print(f"\n{'='*75}")
    print(f"  DONE")
    print(f"{'='*75}")


if __name__ == '__main__':
    main()
