#!/usr/bin/env python3
"""
Walk-Forward Replay: v4.3 vs v4.2 Discovery Comparison

v4.3 changes:
  - MacroKernel: crude_close replaces crude_change_5d (6 features, bw=0.6)
  - StockKernel: 9 features (drops entry_rsi), bw=1.0

v4.2 baseline:
  - MacroKernel: crude_change_5d (6 features, bw=0.6)
  - StockKernel: 10 features (includes entry_rsi), bw=1.0

Both use identical regime rules, bonus logic, TP/SL capping.
Expanding window, min 20 training dates.
"""
import datetime as _dt
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# ──────────────────────────────────────────────────────────────
# Config shared by both versions
# ──────────────────────────────────────────────────────────────
MACRO_BW = 0.6
STOCK_BW = 1.0
BULL_ER = 0.5    # macro E[R] > 0.5% → BULL
STRESS_ER = -0.5 # macro E[R] > -0.5% → STRESS, else CRISIS

DEFENSIVE_SECTORS = frozenset({
    'Utilities', 'Healthcare', 'Basic Materials', 'Real Estate', 'Energy',
})
CRISIS_DEFENSIVE = frozenset({
    'Utilities', 'Real Estate', 'Energy',
})

MIN_TRAIN_DAYS = 20
TP_PCT = 3.0   # take profit for all regimes

# v4.4 feature sets (HYBRID: macro=crude_change_5d, stock=crude_close)
MACRO_FEATURES_V44 = [
    'new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
    'new_52w_highs', 'yield_10y', 'spy_close',
]
STOCK_FEATURES_V44 = [
    'new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
    'new_52w_highs', 'yield_10y', 'spy_close',
    'atr_pct', 'momentum_5d', 'volume_ratio', 'entry_rsi',
]

# v4.2 feature sets
MACRO_FEATURES_V42 = [
    'new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
    'new_52w_highs', 'yield_10y', 'spy_close',
]
STOCK_FEATURES_V42 = [
    'new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
    'new_52w_highs', 'yield_10y', 'spy_close',
    'atr_pct', 'momentum_5d', 'volume_ratio', 'entry_rsi',  # 10 features
]


# ──────────────────────────────────────────────────────────────
# Gaussian Kernel Regression (manual implementation)
# ──────────────────────────────────────────────────────────────
class GaussianKernel:
    """Gaussian kernel regression: z-score normalize, Euclidean distance, weighted mean."""

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
            self.y = np.array([])
            return

        self.X = np.array(rows, dtype=float)
        self.y = np.array(rets, dtype=float)

        self.mu = self.X.mean(axis=0)
        self.sigma = self.X.std(axis=0)
        self.sigma[self.sigma == 0] = 1.0
        self.X = (self.X - self.mu) / self.sigma

    def estimate(self, row):
        """Return (E[R], n_eff). Impute missing features with training mean (z=0)."""
        if len(self.X) == 0:
            return 0.0, 0.0

        vals = []
        for i, f in enumerate(self.features):
            v = row.get(f)
            if v is None:
                v = self.mu[i]  # impute → z=0 after normalization
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


# ──────────────────────────────────────────────────────────────
# Data Loading
# ──────────────────────────────────────────────────────────────
def load_data():
    """Load combined backfill + live data, JOIN macro + breadth."""
    conn = None  # via get_session())
    conn.row_factory = dict

    # Live signal_outcomes (DIP)
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
        WHERE s.outcome_5d IS NOT NULL
          AND s.atr_pct IS NOT NULL
          AND s.signal_source = 'dip_bounce'
    """).fetchall()

    # Backfill
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

    # Load crude_close series for crude_change_5d computation
    crude_series = conn.execute("""
        SELECT date, crude_close FROM macro_snapshots
        WHERE crude_close IS NOT NULL ORDER BY date
    """).fetchall()
    conn.close()

    # Build crude_change_5d lookup
    crude_by_date = {r['date']: r['crude_close'] for r in crude_series}
    crude_dates = sorted(crude_by_date.keys())
    crude_chg_by_date = {}
    for i, d in enumerate(crude_dates):
        if i >= 5:
            d5 = crude_dates[i - 5]
            c5 = crude_by_date[d5]
            if c5 and c5 > 0:
                crude_chg_by_date[d] = (crude_by_date[d] / c5 - 1) * 100

    # Convert to dicts
    live_data = []
    for r in live_rows:
        d = dict(r)
        d['source'] = 'live'
        live_data.append(d)

    backfill_data = []
    for r in backfill_rows:
        d = dict(r)
        d['source'] = 'backfill'
        backfill_data.append(d)

    combined = backfill_data + live_data

    # Deduplicate: same (scan_date, symbol) → keep live
    seen = {}
    for row in combined:
        key = (row['scan_date'], row['symbol'])
        if key in seen:
            if row['source'] == 'live':
                seen[key] = row
        else:
            seen[key] = row
    combined = sorted(seen.values(), key=lambda r: r['scan_date'])

    # Attach crude_change_5d to each row
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
        row['crude_change_5d'] = crude_chg_by_date.get(macro_d)

    live_count = sum(1 for r in combined if r['source'] == 'live')
    bf_count = sum(1 for r in combined if r['source'] == 'backfill')
    dates = sorted(set(r['scan_date'] for r in combined))

    print(f"Combined dataset: {len(combined)} rows ({live_count} live + {bf_count} backfill)")
    print(f"Date range: {dates[0]} to {dates[-1]} ({len(dates)} unique dates)")

    # Check feature coverage
    for feat in ['crude_close', 'crude_change_5d', 'yield_10y', 'spy_close',
                 'pct_above_20d_ma', 'new_52w_lows', 'new_52w_highs',
                 'atr_pct', 'momentum_5d', 'volume_ratio', 'entry_rsi']:
        non_null = sum(1 for r in combined if r.get(feat) is not None)
        print(f"  {feat}: {non_null}/{len(combined)} non-null")

    return combined


# ──────────────────────────────────────────────────────────────
# Walk-Forward Regime Backtest (shared logic for both versions)
# ──────────────────────────────────────────────────────────────
def run_regime_backtest(data, macro_features, stock_features, label,
                        crisis_block_positive_mom=False, require_positive_er=False):
    """Walk-forward expanding-window regime backtest.

    Returns list of result dicts with per-pick outcomes.
    """
    dates = sorted(set(r['scan_date'] for r in data))
    if not dates:
        return []

    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    print(f"Dates: {len(dates)} ({dates[0]} to {dates[-1]})")
    print(f"Macro features: {macro_features}")
    print(f"Stock features: {stock_features}")
    print(f"Macro BW={MACRO_BW}, Stock BW={STOCK_BW}")
    print(f"Regimes: BULL(>{BULL_ER}%) STRESS({STRESS_ER} to {BULL_ER}%) CRISIS(<{STRESS_ER}%)")

    results = []
    regime_counts = defaultdict(int)
    skipped_dates = 0

    for test_date in dates:
        train = [r for r in data if r['scan_date'] < test_date]
        test = [r for r in data if r['scan_date'] == test_date]
        if not test:
            continue

        train_dates = set(r['scan_date'] for r in train)
        if len(train_dates) < MIN_TRAIN_DAYS:
            skipped_dates += 1
            continue

        # --- Stage 1: Macro kernel → regime ---
        macro_kernel = GaussianKernel(MACRO_BW, macro_features)
        macro_kernel.fit(train)

        macro_er, macro_neff = macro_kernel.estimate(test[0])
        if macro_neff < 3.0:
            skipped_dates += 1
            continue

        # Determine regime
        if macro_er > BULL_ER:
            regime = 'BULL'
            max_picks = 5
            sl_pct = 3.0
        elif macro_er > STRESS_ER:
            regime = 'STRESS'
            max_picks = 3
            sl_pct = 2.0
        else:
            regime = 'CRISIS'
            max_picks = 2
            sl_pct = 2.0

        regime_counts[regime] += 1

        # --- Stage 2: Stock kernel → per-stock ranking ---
        stock_kernel = GaussianKernel(STOCK_BW, stock_features)
        stock_kernel.fit(train)

        scored = []
        for row in test:
            stock_er, stock_neff = stock_kernel.estimate(row)
            if stock_neff < 3.0:
                stock_er = 0.0

            # Regime-specific filtering
            if regime == 'STRESS':
                atr = row.get('atr_pct') or 99
                mom5 = row.get('momentum_5d') or 0
                vol = row.get('volume_ratio') or 0
                sector = row.get('sector') or ''
                bonus = 0
                if atr < 2.5:
                    bonus += 1
                if mom5 < 0:
                    bonus += 1
                if vol > 1.2:
                    bonus += 1
                if sector in DEFENSIVE_SECTORS:
                    bonus += 1
                if bonus < 2:
                    continue
                stock_er += bonus * 0.5

            elif regime == 'CRISIS':
                atr = row.get('atr_pct') or 99
                mom5 = row.get('momentum_5d') or 0
                vol = row.get('volume_ratio') or 0
                sector = row.get('sector') or ''
                # v4.4: block overbought stocks in CRISIS
                if crisis_block_positive_mom and mom5 >= 0:
                    continue
                bonus = 0
                if atr < 2.5:
                    bonus += 1
                if mom5 < -2:
                    bonus += 1
                if vol > 1.5:
                    bonus += 1
                if sector in CRISIS_DEFENSIVE:
                    bonus += 1
                if bonus < 3:
                    continue
                stock_er += bonus * 0.5

            # v4.4: never pick negative E[R]
            if require_positive_er and stock_er < 0:
                continue

            scored.append((stock_er, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        scored = scored[:max_picks]

        for stock_er, row in scored:
            # TP/SL capping using max_gain and max_dd
            mg = row.get('outcome_max_gain_5d')
            md = row.get('outcome_max_dd_5d')
            if mg is not None and md is not None:
                if md <= -sl_pct:
                    capped = -sl_pct
                elif mg >= TP_PCT:
                    capped = TP_PCT
                else:
                    capped = row['outcome_5d']
            else:
                capped = row['outcome_5d']

            results.append({
                'date': test_date,
                'symbol': row['symbol'],
                'er': stock_er,
                'macro_er': macro_er,
                'regime': regime,
                'sl_pct': sl_pct,
                'outcome_5d': row['outcome_5d'],
                'capped_return': capped,
                'max_gain': mg,
                'max_dd': md,
                'sector': row.get('sector', ''),
                'atr_pct': row.get('atr_pct'),
                'momentum_5d': row.get('momentum_5d'),
                'volume_ratio': row.get('volume_ratio'),
            })

    print(f"Skipped {skipped_dates} dates (< {MIN_TRAIN_DAYS} train days or low macro n_eff)")
    print(f"Regime distribution: {dict(regime_counts)}")
    print(f"Total picks: {len(results)}")
    return results, dict(regime_counts)


# ──────────────────────────────────────────────────────────────
# Metrics
# ──────────────────────────────────────────────────────────────
def compute_metrics(results, label):
    """Compute and print all metrics for a backtest run."""
    if not results:
        print(f"\n  {label}: NO PICKS")
        return

    print(f"\n{'─'*70}")
    print(f"  {label} — RESULTS")
    print(f"{'─'*70}")

    # Overall
    n = len(results)
    capped = [r['capped_return'] for r in results]
    raw = [r['outcome_5d'] for r in results]
    total_pnl = sum(capped)
    avg_return = np.mean(capped)
    wins = sum(1 for c in capped if c > 0)
    wr = wins / n * 100
    avg_win = np.mean([c for c in capped if c > 0]) if wins > 0 else 0
    losses = n - wins
    avg_loss = np.mean([c for c in capped if c <= 0]) if losses > 0 else 0
    expectancy = avg_return
    dates_set = sorted(set(r['date'] for r in results))
    picks_per_day = n / len(dates_set) if dates_set else 0

    print(f"\n  OVERALL:")
    print(f"    Total picks: {n}")
    print(f"    Trading days: {len(dates_set)}")
    print(f"    Picks/day: {picks_per_day:.1f}")
    print(f"    Total PnL (capped): {total_pnl:+.2f}%")
    print(f"    Avg return (capped): {avg_return:+.3f}%")
    print(f"    Win Rate: {wr:.1f}% ({wins}/{n})")
    print(f"    Avg Win: +{avg_win:.2f}% | Avg Loss: {avg_loss:.2f}%")
    print(f"    Expectancy: {expectancy:+.3f}% per pick")
    print(f"    Total raw PnL (no TP/SL): {sum(raw):+.2f}%")

    # Per-regime breakdown
    print(f"\n  PER-REGIME BREAKDOWN:")
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        rr = [r for r in results if r['regime'] == regime]
        if not rr:
            print(f"    {regime}: 0 picks")
            continue
        rc = [r['capped_return'] for r in rr]
        rw = sum(1 for c in rc if c > 0)
        rdates = len(set(r['date'] for r in rr))
        print(f"    {regime}: {len(rr)} picks over {rdates} days | "
              f"PnL={sum(rc):+.2f}% | Avg={np.mean(rc):+.3f}% | "
              f"WR={rw/len(rr)*100:.1f}% ({rw}/{len(rr)}) | "
              f"SL={rr[0]['sl_pct']:.0f}%")

    # Monthly breakdown
    print(f"\n  MONTHLY BREAKDOWN:")
    monthly = defaultdict(list)
    for r in results:
        month = r['date'][:7]  # YYYY-MM
        monthly[month].append(r['capped_return'])

    for month in sorted(monthly.keys()):
        mc = monthly[month]
        mw = sum(1 for c in mc if c > 0)
        print(f"    {month}: {len(mc):3d} picks | PnL={sum(mc):+7.2f}% | "
              f"Avg={np.mean(mc):+.3f}% | WR={mw/len(mc)*100:.1f}%")

    # Per-day detail (top-level)
    print(f"\n  DAILY PnL (top 5 best / worst):")
    daily = defaultdict(list)
    for r in results:
        daily[r['date']].append(r['capped_return'])
    daily_pnl = [(d, sum(v), len(v)) for d, v in daily.items()]
    daily_pnl.sort(key=lambda x: x[1], reverse=True)
    for d, pnl, n_picks in daily_pnl[:5]:
        regime = [r['regime'] for r in results if r['date'] == d][0]
        print(f"    + {d} ({regime}): {pnl:+.2f}% ({n_picks} picks)")
    print(f"    ...")
    for d, pnl, n_picks in daily_pnl[-5:]:
        regime = [r['regime'] for r in results if r['date'] == d][0]
        print(f"    - {d} ({regime}): {pnl:+.2f}% ({n_picks} picks)")

    return {
        'total_pnl': total_pnl,
        'avg_return': avg_return,
        'win_rate': wr,
        'n_picks': n,
        'n_days': len(dates_set),
        'picks_per_day': picks_per_day,
    }


# ──────────────────────────────────────────────────────────────
# Comparison
# ──────────────────────────────────────────────────────────────
def compare(m_new, m42):
    """Print side-by-side comparison."""
    if not m_new or not m42:
        print("\nCannot compare — one or both runs produced no results.")
        return

    print(f"\n{'='*70}")
    print(f"  HEAD-TO-HEAD COMPARISON: v4.4 vs v4.2")
    print(f"{'='*70}")
    print(f"{'Metric':<30} {'v4.4':>12} {'v4.2':>12} {'Delta':>12}")
    print(f"{'─'*66}")

    rows = [
        ('Total PnL (%)',    m_new['total_pnl'],      m42['total_pnl'],      '.2f'),
        ('Avg Return (%)',   m_new['avg_return'],      m42['avg_return'],     '.3f'),
        ('Win Rate (%)',     m_new['win_rate'],        m42['win_rate'],       '.1f'),
        ('Total Picks',     m_new['n_picks'],         m42['n_picks'],        'd'),
        ('Trading Days',    m_new['n_days'],          m42['n_days'],         'd'),
        ('Picks / Day',     m_new['picks_per_day'],   m42['picks_per_day'],  '.1f'),
    ]
    for label, vnew, v42, fmt in rows:
        delta = vnew - v42
        vnew_s = format(vnew, fmt)
        v42_s = format(v42, fmt)
        if fmt == 'd':
            delta_s = f"{int(delta):+d}"
        else:
            delta_s = format(delta, '+' + fmt)
        print(f"  {label:<28} {vnew_s:>12} {v42_s:>12} {delta_s:>12}")

    # Verdict
    pnl_diff = m_new['total_pnl'] - m42['total_pnl']
    wr_diff = m_new['win_rate'] - m42['win_rate']
    print(f"\n  Verdict: v4.4 {'BETTER' if pnl_diff > 0 else 'WORSE'} by "
          f"{abs(pnl_diff):.2f}% total PnL, "
          f"{'higher' if wr_diff > 0 else 'lower'} WR by {abs(wr_diff):.1f}pp")


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
def main():
    data = load_data()

    # Run v4.4: HYBRID macro=crude_change_5d, stock=crude_close + filters
    results_v44, regimes_v44 = run_regime_backtest(
        data,
        macro_features=MACRO_FEATURES_V44,
        stock_features=STOCK_FEATURES_V44,
        label="v4.4b: v4.2 kernel + CRISIS mom gate + ER>=0 (filter-only change)",
        crisis_block_positive_mom=True,
        require_positive_er=True,
    )
    metrics_v44 = compute_metrics(results_v44, "v4.4")

    # Run v4.2: crude_change_5d, 10 stock features (with entry_rsi)
    results_v42, regimes_v42 = run_regime_backtest(
        data,
        macro_features=MACRO_FEATURES_V42,
        stock_features=STOCK_FEATURES_V42,
        label="v4.2: crude_change_5d + 10 stock features (baseline)",
    )
    metrics_v42 = compute_metrics(results_v42, "v4.2")

    # Head-to-head comparison
    compare(metrics_v44, metrics_v42)

    # Per-regime comparison
    print(f"\n{'='*70}")
    print(f"  PER-REGIME COMPARISON")
    print(f"{'='*70}")
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        r44 = [r for r in results_v44 if r['regime'] == regime]
        r42 = [r for r in results_v42 if r['regime'] == regime]
        print(f"\n  {regime}:")
        for lbl, rr in [('v4.4', r44), ('v4.2', r42)]:
            if not rr:
                print(f"    {lbl}: 0 picks")
                continue
            rc = [r['capped_return'] for r in rr]
            w = sum(1 for c in rc if c > 0)
            print(f"    {lbl}: {len(rr)} picks | PnL={sum(rc):+.2f}% | "
                  f"Avg={np.mean(rc):+.3f}% | WR={w/len(rr)*100:.1f}%")

    print(f"\n{'='*70}")
    print(f"  DONE")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
