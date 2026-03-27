#!/usr/bin/env python3
"""
Walk-Forward Backtest: MacroKernel 6-feat vs 8-feat vs 9-feat Expansion.

Compares:
  v4.5       : Current production (6 macro, 11 stock)
  v4.5+2m    : +crude_close, +vix_term_spread (8 macro, 13 stock)
  v4.5+3m    : +crude_close, +vix_term_spread, +yield_spread (9 macro, 14 stock)

Walk-forward expanding window on 51K signals (Jan 2022 - Mar 2026).
"""
import datetime as _dt
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# === Kernel params ===
MACRO_BW = 0.6
STOCK_BW = 1.0
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

# === VERSION CONFIGS ===
MACRO_6 = ['new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
           'new_52w_highs', 'yield_10y', 'spy_close']

STOCK_11 = MACRO_6 + ['atr_pct', 'momentum_5d', 'volume_ratio',
                       'distance_from_20d_high', 'sector_1d_change']

VERSIONS = {
    'v4.5 (6M)': {
        'macro_features': MACRO_6,
        'stock_features': STOCK_11,
    },
    'v4.5+2m (8M)': {
        'macro_features': MACRO_6 + ['crude_close', 'vix_term_spread'],
        'stock_features': STOCK_11 + ['crude_close', 'vix_term_spread'],
    },
    'v4.5+3m (9M)': {
        'macro_features': MACRO_6 + ['crude_close', 'vix_term_spread', 'yield_spread'],
        'stock_features': STOCK_11 + ['crude_close', 'vix_term_spread', 'yield_spread'],
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
    conn = None  # via get_session())
    conn.row_factory = dict

    # Load live signal_outcomes
    live_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector,
               s.atr_pct, s.entry_rsi, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio, s.vix_at_signal,
               s.outcome_5d, s.outcome_max_gain_5d, s.outcome_max_dd_5d
        FROM signal_outcomes s
        WHERE s.outcome_5d IS NOT NULL AND s.atr_pct IS NOT NULL
          AND s.signal_source = 'dip_bounce'
    """).fetchall()

    # Load backfill
    backfill_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector,
               s.atr_pct, s.entry_rsi, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio, s.vix_at_signal,
               s.outcome_5d, s.outcome_max_gain_5d, s.outcome_max_dd_5d
        FROM backfill_signal_outcomes s
        WHERE s.outcome_5d IS NOT NULL
    """).fetchall()

    # Load macro data
    macro_rows = conn.execute("""
        SELECT date, crude_close, yield_10y, spy_close,
               vix_close, vix3m_close, yield_spread
        FROM macro_snapshots
        WHERE crude_close IS NOT NULL
    """).fetchall()

    # Load breadth
    breadth_rows = conn.execute("""
        SELECT date, pct_above_20d_ma, new_52w_lows, new_52w_highs
        FROM market_breadth
    """).fetchall()

    # Load sector ETF returns for sector_1d_change
    sector_rows = conn.execute("""
        SELECT date, sector, pct_change
        FROM sector_etf_daily_returns
        WHERE pct_change IS NOT NULL
    """).fetchall()

    conn.close()

    # Build lookup tables
    macro_by_date = {}
    for r in macro_rows:
        macro_by_date[r['date']] = dict(r)

    breadth_by_date = {}
    for r in breadth_rows:
        breadth_by_date[r['date']] = dict(r)

    sector_by_date_sector = {}
    for r in sector_rows:
        sector_by_date_sector[(r['date'], r['sector'])] = r['pct_change']

    # Compute crude_change_5d from crude series
    crude_series = sorted(
        [(r['date'], r['crude_close']) for r in macro_rows if r['crude_close']],
        key=lambda x: x[0]
    )
    crude_chg_by_date = {}
    for i, (d, c) in enumerate(crude_series):
        if i >= 5:
            c5 = crude_series[i - 5][1]
            if c5 and c5 > 0:
                crude_chg_by_date[d] = (c / c5 - 1) * 100

    # Compute vix_term_spread
    vix_spread_by_date = {}
    for r in macro_rows:
        if r['vix_close'] is not None and r['vix3m_close'] is not None:
            vix_spread_by_date[r['date']] = r['vix_close'] - r['vix3m_close']

    # Deduplicate: live > backfill
    combined = []
    for r in backfill_rows:
        d = dict(r); d['source'] = 'backfill'; combined.append(d)
    for r in live_rows:
        d = dict(r); d['source'] = 'live'; combined.append(d)

    seen = {}
    for row in combined:
        key = (row['scan_date'], row['symbol'])
        if key in seen:
            if row['source'] == 'live':
                seen[key] = row
        else:
            seen[key] = row
    combined = sorted(seen.values(), key=lambda r: r['scan_date'])

    # Enrich with macro/breadth/sector features
    enriched = 0
    dropped = 0
    for row in combined:
        sd = row['scan_date']
        d_obj = _dt.date.fromisoformat(sd)
        wd = d_obj.weekday()
        if wd == 5:
            macro_d = (d_obj - _dt.timedelta(days=1)).isoformat()
        elif wd == 6:
            macro_d = (d_obj - _dt.timedelta(days=2)).isoformat()
        else:
            macro_d = sd

        m = macro_by_date.get(macro_d, {})
        b = breadth_by_date.get(macro_d, {})

        row['crude_close'] = m.get('crude_close')
        row['yield_10y'] = m.get('yield_10y')
        row['spy_close'] = m.get('spy_close')
        row['yield_spread'] = m.get('yield_spread')
        row['pct_above_20d_ma'] = b.get('pct_above_20d_ma')
        row['new_52w_lows'] = b.get('new_52w_lows')
        row['new_52w_highs'] = b.get('new_52w_highs')
        row['crude_change_5d'] = crude_chg_by_date.get(macro_d)
        row['vix_term_spread'] = vix_spread_by_date.get(macro_d)

        # sector_1d_change
        sector = row.get('sector', '')
        row['sector_1d_change'] = sector_by_date_sector.get((macro_d, sector))

        if row['crude_close'] is not None and row['pct_above_20d_ma'] is not None:
            enriched += 1
        else:
            dropped += 1

    n_dates = len(set(r['scan_date'] for r in combined))
    print(f"Dataset: {len(combined)} rows, {n_dates} dates")
    print(f"  Enriched: {enriched}, Missing macro/breadth: {dropped}")

    # Check new feature coverage
    for feat in ['crude_close', 'vix_term_spread', 'yield_spread', 'sector_1d_change']:
        n = sum(1 for r in combined if r.get(feat) is not None)
        print(f"  {feat}: {n}/{len(combined)} ({n/len(combined)*100:.1f}%)")

    return combined


def run_backtest(data, cfg, label):
    macro_f = cfg['macro_features']
    stock_f = cfg['stock_features']

    dates = sorted(set(r['scan_date'] for r in data))
    results = []
    regime_counts = defaultdict(int)
    skipped = 0

    for test_date in dates:
        train = [r for r in data if r['scan_date'] < test_date]
        test = [r for r in data if r['scan_date'] == test_date]
        if not test:
            continue
        if len(set(r['scan_date'] for r in train)) < MIN_TRAIN_DAYS:
            skipped += 1
            continue

        # Stage 1: MacroKernel → regime
        macro_k = GaussianKernel(MACRO_BW, macro_f)
        macro_k.fit(train)
        macro_er, macro_neff = macro_k.estimate(test[0])
        if macro_neff < 3.0:
            skipped += 1
            continue

        if macro_er > BULL_ER:
            regime, max_picks, sl_pct = 'BULL', 5, 3.0
        elif macro_er > STRESS_ER:
            regime, max_picks, sl_pct = 'STRESS', 3, 2.0
        else:
            regime, max_picks, sl_pct = 'CRISIS', 2, 2.0
        regime_counts[regime] += 1

        # Stage 2: StockKernel → rank
        stock_k = GaussianKernel(STOCK_BW, stock_f)
        stock_k.fit(train)

        scored = []
        for row in test:
            stock_er, stock_neff = stock_k.estimate(row)
            if stock_neff < 3.0:
                stock_er = 0.0

            # STRESS filter
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
                stock_er += bonus * 0.5
            # CRISIS filter
            elif regime == 'CRISIS':
                mom5 = row.get('momentum_5d') or 0
                sector = row.get('sector') or ''
                bonus = 0
                if (row.get('atr_pct') or 99) < 2.5: bonus += 1
                if mom5 < -2: bonus += 1
                if (row.get('volume_ratio') or 0) > 1.5: bonus += 1
                if sector in CRISIS_DEFENSIVE: bonus += 1
                if bonus < 3: continue
                stock_er += bonus * 0.5

            scored.append((stock_er, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Dynamic SL
        for stock_er, row in scored[:max_picks]:
            atr = row.get('atr_pct') or 3.0
            if regime == 'BULL':
                dyn_sl = min(max(atr * 2.0, 1.5), 5.0)
            elif regime == 'STRESS':
                dyn_sl = min(max(atr * 1.5, 1.5), 5.0)
            else:
                dyn_sl = min(max(atr * 1.0, 1.5), 5.0)

            mg = row.get('outcome_max_gain_5d')
            md = row.get('outcome_max_dd_5d')
            if mg is not None and md is not None:
                if md <= -dyn_sl:
                    capped = -dyn_sl
                elif mg >= TP_PCT:
                    capped = TP_PCT
                else:
                    capped = row['outcome_5d']
            else:
                capped = row['outcome_5d']

            results.append({
                'date': test_date, 'symbol': row['symbol'],
                'regime': regime, 'capped_return': capped,
                'macro_er': macro_er, 'stock_er': stock_er,
                'sector': row.get('sector', ''),
            })

    return results, dict(regime_counts), skipped


def compute_metrics(results, label):
    if not results:
        return {'label': label, 'total_pnl': 0, 'win_rate': 0, 'n_picks': 0,
                'n_days': 0, 'avg_return': 0, 'sl_rate': 0, 'regimes': {}}

    n = len(results)
    capped = [r['capped_return'] for r in results]
    total_pnl = sum(capped)
    wins = sum(1 for c in capped if c > 0)
    losses = sum(1 for c in capped if c < -1.4)  # SL approximation
    wr = wins / n * 100
    sl_rate = losses / n * 100
    dates_set = set(r['date'] for r in results)

    regime_data = {}
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        rr = [r['capped_return'] for r in results if r['regime'] == regime]
        if rr:
            rw = sum(1 for c in rr if c > 0)
            rl = sum(1 for c in rr if c < -1.4)
            regime_data[regime] = {
                'pnl': sum(rr), 'wr': rw / len(rr) * 100,
                'sl': rl / len(rr) * 100, 'n': len(rr),
                'avg': np.mean(rr),
            }
        else:
            regime_data[regime] = {'pnl': 0, 'wr': 0, 'sl': 0, 'n': 0, 'avg': 0}

    # Monthly breakdown
    by_month = defaultdict(list)
    for r in results:
        by_month[r['date'][:7]].append(r['capped_return'])

    monthly_pnl = {m: sum(v) for m, v in sorted(by_month.items())}

    # $ PnL estimate ($1000/pick)
    dollar_pnl = total_pnl / 100 * 1000 * n  # rough
    monthly_avg_dollar = dollar_pnl / max(len(monthly_pnl), 1)

    return {
        'label': label, 'total_pnl': total_pnl, 'win_rate': wr,
        'sl_rate': sl_rate, 'n_picks': n, 'n_days': len(dates_set),
        'avg_return': np.mean(capped), 'median_return': np.median(capped),
        'regimes': regime_data, 'monthly_pnl': monthly_pnl,
        'dollar_total': dollar_pnl,
    }


def main():
    data = load_data()

    all_metrics = {}
    all_results = {}
    ver_keys = list(VERSIONS.keys())

    for ver, cfg in VERSIONS.items():
        print(f"\nRunning {ver}...")
        results, regimes, skipped = run_backtest(data, cfg, ver)
        m = compute_metrics(results, ver)
        all_metrics[ver] = m
        all_results[ver] = results
        print(f"  {m['n_picks']} picks, {m['n_days']} days, skipped {skipped}")
        print(f"  Regimes: {regimes}")

    # ===== COMPARISON TABLE =====
    print(f"\n{'=' * 80}")
    print(f"  WALK-FORWARD: MacroKernel 6-feat vs 8-feat vs 9-feat")
    print(f"  Dataset: {len(data)} signals, {len(set(r['scan_date'] for r in data))} dates")
    print(f"{'=' * 80}")

    header = f"{'Metric':<22}"
    for v in ver_keys:
        header += f" {v:>17}"
    print(header)
    print(f"{'─' * 80}")

    rows = [
        ('Total PnL (%)', 'total_pnl', '+.2f'),
        ('Avg Return (%)', 'avg_return', '+.4f'),
        ('Median Return (%)', 'median_return', '+.4f'),
        ('Win Rate (%)', 'win_rate', '.1f'),
        ('SL Rate (%)', 'sl_rate', '.1f'),
        ('Total Picks', 'n_picks', 'd'),
        ('Trading Days', 'n_days', 'd'),
        ('Picks/Day', None, '.1f'),
    ]

    for label, key, fmt in rows:
        line = f"  {label:<20}"
        for v in ver_keys:
            m = all_metrics[v]
            if key:
                val = m[key]
            else:  # picks/day
                val = m['n_picks'] / max(m['n_days'], 1)
            line += f" {format(val, fmt):>17}"
        print(line)

    # Per-regime breakdown
    print(f"\n{'─' * 80}")
    print(f"  PER-REGIME BREAKDOWN")
    print(f"{'─' * 80}")

    for regime in ['BULL', 'STRESS', 'CRISIS']:
        line = f"  {regime:<20}"
        for v in ver_keys:
            rd = all_metrics[v]['regimes'][regime]
            if rd['n'] > 0:
                line += f" {rd['pnl']:+6.1f}% W{rd['wr']:4.0f}% n={rd['n']:>4}"
            else:
                line += f" {'—':>17}"
        print(line)

    # Per-regime avg return
    print()
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        line = f"  {regime + ' avg':.<20}"
        for v in ver_keys:
            rd = all_metrics[v]['regimes'][regime]
            if rd['n'] > 0:
                line += f" {rd['avg']:>+17.4f}"
            else:
                line += f" {'—':>17}"
        print(line)

    # Monthly PnL comparison (last 12 months only)
    print(f"\n{'─' * 80}")
    print(f"  MONTHLY PnL (%) — last 24 months")
    print(f"{'─' * 80}")

    all_months = set()
    for v in ver_keys:
        all_months.update(all_metrics[v]['monthly_pnl'].keys())
    all_months = sorted(all_months)[-24:]

    header2 = f"  {'Month':<10}"
    for v in ver_keys:
        header2 += f" {v:>17}"
    print(header2)

    for month in all_months:
        line = f"  {month:<10}"
        for v in ver_keys:
            pnl = all_metrics[v]['monthly_pnl'].get(month, 0)
            line += f" {pnl:>+17.2f}"
        print(line)

    # WINNER determination
    print(f"\n{'─' * 80}")
    print(f"  WINNER")
    print(f"{'─' * 80}")

    pnls = {v: all_metrics[v]['total_pnl'] for v in ver_keys}
    best_pnl = max(pnls, key=pnls.get)
    print(f"  Total PnL:  {best_pnl} ({pnls[best_pnl]:+.2f}%)")

    wrs = {v: all_metrics[v]['win_rate'] for v in ver_keys}
    best_wr = max(wrs, key=wrs.get)
    print(f"  Win Rate:   {best_wr} ({wrs[best_wr]:.1f}%)")

    avgs = {v: all_metrics[v]['avg_return'] for v in ver_keys}
    best_avg = max(avgs, key=avgs.get)
    print(f"  Avg Return: {best_avg} ({avgs[best_avg]:+.4f}%)")

    # CRISIS regime winner
    crisis_pnl = {}
    for v in ver_keys:
        cd = all_metrics[v]['regimes']['CRISIS']
        if cd['n'] > 0:
            crisis_pnl[v] = cd['pnl']
    if crisis_pnl:
        best_crisis = max(crisis_pnl, key=crisis_pnl.get)
        print(f"  CRISIS PnL: {best_crisis} ({crisis_pnl[best_crisis]:+.1f}%)")

    # Delta analysis
    print(f"\n{'─' * 80}")
    print(f"  DELTA vs BASELINE ({ver_keys[0]})")
    print(f"{'─' * 80}")
    base = all_metrics[ver_keys[0]]
    for v in ver_keys[1:]:
        m = all_metrics[v]
        print(f"  {v}:")
        print(f"    PnL:      {m['total_pnl'] - base['total_pnl']:+.2f}%")
        print(f"    WR:       {m['win_rate'] - base['win_rate']:+.1f}pp")
        print(f"    Avg Ret:  {m['avg_return'] - base['avg_return']:+.4f}%")
        print(f"    SL Rate:  {m['sl_rate'] - base['sl_rate']:+.1f}pp")
        for regime in ['BULL', 'STRESS', 'CRISIS']:
            bd = base['regimes'][regime]
            md = m['regimes'][regime]
            if bd['n'] > 0 and md['n'] > 0:
                print(f"    {regime}: PnL {md['pnl'] - bd['pnl']:+.1f}%, "
                      f"WR {md['wr'] - bd['wr']:+.1f}pp, "
                      f"n={md['n']} vs {bd['n']}")

    print(f"\n{'=' * 80}")
    print(f"  DONE")
    print(f"{'=' * 80}")


if __name__ == '__main__':
    main()
