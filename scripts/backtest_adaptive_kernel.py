#!/usr/bin/env python3
"""
Adaptive Kernel with Time Decay + Outcome Feedback — Walk-Forward Backtest

Tests whether REAL LEARNING (time decay + feedback from trade outcomes) beats
the current "flat memory" kernel that weights all 51K signals equally.

Experimental conditions:
  A. FLAT    — Current production kernel (equal weight, no decay)
  B. DECAY   — Exponential time decay only (recent data weighted more)
  C. FEEDBACK — Decay + outcome feedback (boost correct, punish wrong)

Walk-forward protocol:
  - For each test month M: train on ALL data before M (expanding window)
  - Apply time decay from test month's start date
  - Apply feedback weighting from known outcomes
  - Measure: WR, E[R], $/mo, picks/day

Tests half_lives: 60, 90, 180, 365 days
Tests feedback strengths: mild (1.2/0.8), moderate (1.5/0.7), strong (2.0/0.5)
"""
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# ── Production feature lists (must match kernel_estimator.py) ──
STOCK_FEATURES = [
    'new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
    'new_52w_highs', 'yield_10y', 'spy_close',
    'crude_close', 'vix_term_spread',
    'atr_pct', 'momentum_5d', 'volume_ratio',
    'distance_from_20d_high', 'sector_1d_change',
]
MACRO_FEATURES = STOCK_FEATURES[:8]

COST = 0.003  # 0.3% round-trip cost
CAPITAL = 5000
PER_TRADE = 500

# ── Regime thresholds (match production) ──
BULL_ER = 0.5
STRESS_ER = -0.5
ELITE_SIGMA = 0.8

# SL by regime
SL_BY_REGIME = {'BULL': 3.0, 'STRESS': 2.0, 'CRISIS': 2.0}


# ════════════════════════════════════════════════════════════════
# Data Loading
# ════════════════════════════════════════════════════════════════
def load_all_data():
    """Load combined dataset with all 13 stock kernel features."""
    conn = None  # via get_session())
    conn.row_factory = dict

    rows = conn.execute("""
        WITH crude_lag AS (
            SELECT date, crude_close,
                   LAG(crude_close, 5) OVER (ORDER BY date) as crude_5d_ago
            FROM macro_snapshots WHERE crude_close IS NOT NULL
        ),
        combined AS (
            SELECT scan_date, symbol, outcome_5d, sector,
                   atr_pct, momentum_5d, volume_ratio,
                   distance_from_20d_high, outcome_max_gain_5d, outcome_max_dd_5d,
                   1 as priority
            FROM signal_outcomes
            WHERE outcome_5d IS NOT NULL AND atr_pct IS NOT NULL

            UNION ALL

            SELECT scan_date, symbol, outcome_5d, sector,
                   atr_pct, momentum_5d, volume_ratio,
                   distance_from_20d_high, outcome_max_gain_5d, outcome_max_dd_5d,
                   2 as priority
            FROM backfill_signal_outcomes
            WHERE outcome_5d IS NOT NULL AND atr_pct IS NOT NULL
        ),
        deduped AS (
            SELECT scan_date, symbol, outcome_5d, sector,
                   atr_pct, momentum_5d, volume_ratio,
                   distance_from_20d_high, outcome_max_gain_5d, outcome_max_dd_5d,
                   ROW_NUMBER() OVER (PARTITION BY scan_date, symbol ORDER BY priority) as rn
            FROM combined
        ),
        trading_date AS (
            SELECT d.*,
                   CASE
                       WHEN strftime('%w', d.scan_date) = '6' THEN date(d.scan_date, '-1 day')
                       WHEN strftime('%w', d.scan_date) = '0' THEN date(d.scan_date, '-2 days')
                       ELSE d.scan_date
                   END as macro_date
            FROM deduped d WHERE d.rn = 1
        )
        SELECT t.scan_date, t.symbol, t.outcome_5d, t.sector,
               t.atr_pct, t.momentum_5d, t.volume_ratio,
               t.distance_from_20d_high,
               t.outcome_max_gain_5d, t.outcome_max_dd_5d,
               b.new_52w_lows,
               CASE WHEN cl.crude_5d_ago > 0
                    THEN (cl.crude_close / cl.crude_5d_ago - 1) * 100
                    ELSE NULL END as crude_change_5d,
               b.pct_above_20d_ma, b.new_52w_highs,
               m.yield_10y, m.spy_close, m.crude_close,
               m.vix_close - m.vix3m_close as vix_term_spread,
               ser.pct_change as sector_1d_change
        FROM trading_date t
        LEFT JOIN macro_snapshots m ON m.date = t.macro_date
        LEFT JOIN market_breadth b ON b.date = t.macro_date
        LEFT JOIN crude_lag cl ON cl.date = t.macro_date
        LEFT JOIN sector_etf_daily_returns ser
            ON ser.sector = t.sector AND ser.date = t.macro_date
        ORDER BY t.scan_date
    """).fetchall()
    conn.close()

    data = []
    for r in rows:
        d = dict(r)
        # Check all 13 features present
        feats = [d.get(f) for f in STOCK_FEATURES]
        if any(v is None for v in feats) or d['outcome_5d'] is None:
            continue
        data.append(d)

    # Deduplicate
    seen = {}
    for row in data:
        key = (row['scan_date'], row['symbol'])
        seen[key] = row  # later = live priority
    data = sorted(seen.values(), key=lambda r: r['scan_date'])

    dates = sorted(set(r['scan_date'] for r in data))
    print(f"Loaded {len(data)} signals, {len(dates)} unique dates")
    print(f"Date range: {dates[0]} to {dates[-1]}")
    return data


# ════════════════════════════════════════════════════════════════
# Adaptive Kernel Estimator
# ════════════════════════════════════════════════════════════════
class AdaptiveStockKernel:
    """StockKernel with time decay and outcome feedback weighting.

    Three modes:
      FLAT     — equal weights (current production baseline)
      DECAY    — exp(-days_ago / half_life) time decay
      FEEDBACK — decay + outcome-based weight boost/penalty
    """

    def __init__(self, bandwidth=1.0, half_life=None,
                 feedback_correct=1.0, feedback_wrong=1.0,
                 mode='FLAT'):
        self.bw = bandwidth
        self.half_life = half_life  # days for 50% decay
        self.fb_correct = feedback_correct
        self.fb_wrong = feedback_wrong
        self.mode = mode

        self.train_features = None
        self.train_returns = None
        self.sample_weights = None  # pre-computed time+feedback weights
        self.feature_means = None
        self.feature_stds = None
        self._fitted = False

    def fit(self, train_data, reference_date=None):
        """Fit on training data with optional time decay and feedback.

        Args:
            train_data: list of dicts with STOCK_FEATURES + outcome_5d + scan_date
            reference_date: str, the date we're predicting from (for decay calc)
        """
        if len(train_data) < 50:
            self._fitted = False
            return False

        feat_rows = []
        returns = []
        sample_w = []

        if reference_date:
            ref = date.fromisoformat(reference_date)
        else:
            ref = date.fromisoformat(train_data[-1]['scan_date'])

        for row in train_data:
            feats = [row[f] for f in STOCK_FEATURES]
            outcome = row['outcome_5d']
            feat_rows.append(feats)
            returns.append(outcome)

            # Time decay weight
            if self.mode in ('DECAY', 'FEEDBACK') and self.half_life:
                days_ago = (ref - date.fromisoformat(row['scan_date'])).days
                decay = math.exp(-0.693 * days_ago / self.half_life)  # ln(2) ≈ 0.693
            else:
                decay = 1.0

            # Feedback weight
            if self.mode == 'FEEDBACK':
                # "Correct" = positive outcome (DIP signal → stock went up)
                if outcome > 0:
                    fb = self.fb_correct
                else:
                    fb = self.fb_wrong
            else:
                fb = 1.0

            sample_w.append(decay * fb)

        self.train_features = np.array(feat_rows, dtype=np.float64)
        self.train_returns = np.array(returns, dtype=np.float64)
        self.sample_weights = np.array(sample_w, dtype=np.float64)

        # Weighted normalization (use sample weights for mean/std)
        w_norm = self.sample_weights / self.sample_weights.sum()
        self.feature_means = np.average(self.train_features, axis=0, weights=w_norm)
        diff = self.train_features - self.feature_means
        self.feature_stds = np.sqrt(np.average(diff ** 2, axis=0, weights=w_norm))
        self.feature_stds[self.feature_stds == 0] = 1.0

        self.train_features = (self.train_features - self.feature_means) / self.feature_stds
        self._fitted = True
        return True

    def estimate(self, candidate):
        """Estimate E[R] for candidate dict. Returns (er, se, n_eff)."""
        if not self._fitted:
            return 0.0, 10.0, 0.0

        vals = [candidate[f] for f in STOCK_FEATURES]
        x = np.array(vals, dtype=np.float64)
        x_norm = (x - self.feature_means) / self.feature_stds

        # Gaussian kernel distance weights
        dists = np.sqrt(np.sum((self.train_features - x_norm) ** 2, axis=1))
        kernel_w = np.exp(-0.5 * (dists / self.bw) ** 2)

        # Combined weight = kernel × sample_weight (time decay × feedback)
        weights = kernel_w * self.sample_weights

        total_w = weights.sum()
        if total_w < 1e-10:
            return 0.0, 10.0, 0.0

        er = float(np.sum(weights * self.train_returns) / total_w)
        n_eff = float(total_w ** 2 / np.sum(weights ** 2))

        if n_eff > 1:
            residuals = self.train_returns - er
            weighted_var = float(np.sum(weights * residuals ** 2) / total_w)
            se = math.sqrt(max(weighted_var / n_eff, 1e-10))
        else:
            se = 10.0

        return er, se, n_eff


class AdaptiveMacroKernel:
    """MacroKernel (8 features) with time decay + feedback for regime detection."""

    def __init__(self, bandwidth=0.4, half_life=None,
                 feedback_correct=1.0, feedback_wrong=1.0,
                 mode='FLAT'):
        self.bw = bandwidth
        self.half_life = half_life
        self.fb_correct = feedback_correct
        self.fb_wrong = feedback_wrong
        self.mode = mode
        self.train_features = None
        self.train_returns = None
        self.sample_weights = None
        self.feature_means = None
        self.feature_stds = None
        self._fitted = False

    def fit(self, train_data, reference_date=None):
        if len(train_data) < 50:
            self._fitted = False
            return False

        # Aggregate to per-date macro returns (mean outcome per date)
        date_outcomes = defaultdict(list)
        date_feats = {}
        for row in train_data:
            d = row['scan_date']
            date_outcomes[d].append(row['outcome_5d'])
            if d not in date_feats:
                date_feats[d] = [row[f] for f in MACRO_FEATURES]

        feat_rows, returns, sample_w = [], [], []
        if reference_date:
            ref = date.fromisoformat(reference_date)
        else:
            ref = date.fromisoformat(max(date_outcomes.keys()))

        for d in sorted(date_outcomes.keys()):
            mean_ret = np.mean(date_outcomes[d])
            feat_rows.append(date_feats[d])
            returns.append(mean_ret)

            if self.mode in ('DECAY', 'FEEDBACK') and self.half_life:
                days_ago = (ref - date.fromisoformat(d)).days
                decay = math.exp(-0.693 * days_ago / self.half_life)
            else:
                decay = 1.0

            if self.mode == 'FEEDBACK':
                fb = self.fb_correct if mean_ret > 0 else self.fb_wrong
            else:
                fb = 1.0

            sample_w.append(decay * fb)

        self.train_features = np.array(feat_rows, dtype=np.float64)
        self.train_returns = np.array(returns, dtype=np.float64)
        self.sample_weights = np.array(sample_w, dtype=np.float64)

        w_norm = self.sample_weights / self.sample_weights.sum()
        self.feature_means = np.average(self.train_features, axis=0, weights=w_norm)
        diff = self.train_features - self.feature_means
        self.feature_stds = np.sqrt(np.average(diff ** 2, axis=0, weights=w_norm))
        self.feature_stds[self.feature_stds == 0] = 1.0
        self.train_features = (self.train_features - self.feature_means) / self.feature_stds
        self._fitted = True
        return True

    def estimate(self, candidate):
        if not self._fitted:
            return 0.0, 10.0, 0.0

        vals = [candidate[f] for f in MACRO_FEATURES]
        x = np.array(vals, dtype=np.float64)
        x_norm = (x - self.feature_means) / self.feature_stds

        dists = np.sqrt(np.sum((self.train_features - x_norm) ** 2, axis=1))
        kernel_w = np.exp(-0.5 * (dists / self.bw) ** 2)
        weights = kernel_w * self.sample_weights
        total_w = weights.sum()
        if total_w < 1e-10:
            return 0.0, 10.0, 0.0

        er = float(np.sum(weights * self.train_returns) / total_w)
        n_eff = float(total_w ** 2 / np.sum(weights ** 2))
        if n_eff > 1:
            residuals = self.train_returns - er
            weighted_var = float(np.sum(weights * residuals ** 2) / total_w)
            se = math.sqrt(max(weighted_var / n_eff, 1e-10))
        else:
            se = 10.0
        return er, se, n_eff


# ════════════════════════════════════════════════════════════════
# Walk-Forward Backtest Engine
# ════════════════════════════════════════════════════════════════
def run_walkforward(data, mode='FLAT', half_life=None,
                    fb_correct=1.0, fb_wrong=1.0,
                    min_train_months=6, label=''):
    """Walk-forward backtest with adaptive kernels.

    For each test month: train on all prior data, predict, measure.
    Returns dict of monthly results + overall summary.
    """
    # Group by month
    by_month = defaultdict(list)
    for row in data:
        ym = row['scan_date'][:7]  # YYYY-MM
        by_month[ym].append(row)

    months = sorted(by_month.keys())
    if len(months) < min_train_months + 1:
        print(f"  Not enough months ({len(months)})")
        return None

    results = []
    all_picks = []

    for i in range(min_train_months, len(months)):
        test_month = months[i]
        train_months = months[:i]
        train_data = []
        for m in train_months:
            train_data.extend(by_month[m])
        test_data = by_month[test_month]

        if len(train_data) < 100 or len(test_data) < 5:
            continue

        # Reference date = first day of test month
        ref_date = test_data[0]['scan_date']

        # Fit macro kernel
        macro_k = AdaptiveMacroKernel(
            bandwidth=0.4, half_life=half_life,
            feedback_correct=fb_correct, feedback_wrong=fb_wrong,
            mode=mode
        )
        macro_k.fit(train_data, reference_date=ref_date)

        # Fit stock kernel
        stock_k = AdaptiveStockKernel(
            bandwidth=1.0, half_life=half_life,
            feedback_correct=fb_correct, feedback_wrong=fb_wrong,
            mode=mode
        )
        stock_k.fit(train_data, reference_date=ref_date)

        if not macro_k._fitted or not stock_k._fitted:
            continue

        # Test each day in test month
        test_by_day = defaultdict(list)
        for row in test_data:
            test_by_day[row['scan_date']].append(row)

        month_picks = []
        for day_date in sorted(test_by_day.keys()):
            day_signals = test_by_day[day_date]

            # Macro regime detection (use first signal's macro features)
            macro_er, _, _ = macro_k.estimate(day_signals[0])

            if macro_er > BULL_ER:
                regime = 'BULL'
            elif macro_er < STRESS_ER:
                regime = 'CRISIS'
            else:
                regime = 'STRESS'

            sl_pct = SL_BY_REGIME[regime]

            # Score each stock with stock kernel
            scored = []
            for sig in day_signals:
                er, se, n_eff = stock_k.estimate(sig)
                if n_eff >= 3.0:
                    scored.append((sig, er, se, n_eff))

            if not scored:
                continue

            # Elite filter: keep stocks > mean + k*sigma
            ers = [s[1] for s in scored]
            mean_er = np.mean(ers)
            std_er = np.std(ers) if len(ers) > 1 else 0.01
            threshold = mean_er + ELITE_SIGMA * std_er

            elite = [(sig, er, se, n_eff) for sig, er, se, n_eff in scored
                     if er > threshold]

            if not elite:
                # Take top 1 as fallback
                elite = [max(scored, key=lambda x: x[1])]

            # Cap at 5 picks/day
            elite.sort(key=lambda x: -x[1])
            elite = elite[:5]

            for sig, er, se, n_eff in elite:
                outcome = sig['outcome_5d']
                net_ret = outcome - COST * 100  # outcome already in %

                # Check SL hit
                max_dd = sig.get('outcome_max_dd_5d')
                sl_hit = max_dd is not None and max_dd <= -sl_pct

                if sl_hit:
                    realized = -sl_pct - COST * 100
                else:
                    realized = net_ret

                month_picks.append({
                    'date': day_date,
                    'symbol': sig['symbol'],
                    'er': er,
                    'outcome': outcome,
                    'realized': realized,
                    'regime': regime,
                    'sl_hit': sl_hit,
                    'n_eff': n_eff,
                })

        if not month_picks:
            continue

        # Monthly stats
        n = len(month_picks)
        wins = sum(1 for p in month_picks if p['realized'] > 0)
        wr = wins / n * 100 if n else 0
        avg_ret = np.mean([p['realized'] for p in month_picks])
        total_ret = sum(p['realized'] for p in month_picks)
        sl_rate = sum(1 for p in month_picks if p['sl_hit']) / n * 100
        avg_er = np.mean([p['er'] for p in month_picks])

        # Approx $/mo (each pick = $500 position)
        dollar_pnl = sum(p['realized'] / 100 * PER_TRADE for p in month_picks)

        n_days = len(set(p['date'] for p in month_picks))
        picks_per_day = n / n_days if n_days else 0

        regime_counts = defaultdict(int)
        for p in month_picks:
            regime_counts[p['regime']] += 1

        results.append({
            'month': test_month,
            'n_picks': n,
            'n_days': n_days,
            'picks_per_day': picks_per_day,
            'wr': wr,
            'avg_ret': avg_ret,
            'total_ret': total_ret,
            'sl_rate': sl_rate,
            'avg_er': avg_er,
            'dollar_pnl': dollar_pnl,
            'regimes': dict(regime_counts),
        })
        all_picks.extend(month_picks)

    if not results:
        return None

    # Overall summary
    total_picks = sum(r['n_picks'] for r in results)
    total_wins = sum(r['n_picks'] * r['wr'] / 100 for r in results)
    overall_wr = total_wins / total_picks * 100 if total_picks else 0
    overall_avg_ret = np.mean([p['realized'] for p in all_picks])
    total_dollar = sum(r['dollar_pnl'] for r in results)
    avg_dollar_mo = total_dollar / len(results)
    overall_sl = sum(1 for p in all_picks if p['sl_hit']) / len(all_picks) * 100
    avg_n_eff = np.mean([p['n_eff'] for p in all_picks])

    # Correlation: predicted E[R] vs actual outcome
    pred = [p['er'] for p in all_picks]
    actual = [p['outcome'] for p in all_picks]
    if len(pred) > 10:
        corr = np.corrcoef(pred, actual)[0, 1]
    else:
        corr = 0.0

    summary = {
        'label': label,
        'mode': mode,
        'half_life': half_life,
        'fb_correct': fb_correct,
        'fb_wrong': fb_wrong,
        'n_months': len(results),
        'total_picks': total_picks,
        'overall_wr': overall_wr,
        'overall_avg_ret': overall_avg_ret,
        'overall_sl_rate': overall_sl,
        'total_dollar': total_dollar,
        'avg_dollar_mo': avg_dollar_mo,
        'pred_actual_corr': corr,
        'avg_n_eff': avg_n_eff,
        'monthly': results,
        'all_picks': all_picks,
    }
    return summary


# ════════════════════════════════════════════════════════════════
# Analysis & Reporting
# ════════════════════════════════════════════════════════════════
def print_summary(s):
    """Print one experiment's summary."""
    if not s:
        print("  (no results)")
        return
    print(f"\n{'='*70}")
    print(f"  {s['label']}")
    print(f"  Mode={s['mode']}  half_life={s['half_life']}  "
          f"feedback={s['fb_correct']:.1f}/{s['fb_wrong']:.1f}")
    print(f"{'='*70}")
    print(f"  Months tested: {s['n_months']}")
    print(f"  Total picks:   {s['total_picks']}")
    print(f"  Win Rate:      {s['overall_wr']:.1f}%")
    print(f"  Avg Return:    {s['overall_avg_ret']:+.3f}%")
    print(f"  SL Rate:       {s['overall_sl_rate']:.1f}%")
    print(f"  Total $:       ${s['total_dollar']:+,.0f}")
    print(f"  Avg $/month:   ${s['avg_dollar_mo']:+,.0f}")
    print(f"  Pred↔Actual r: {s['pred_actual_corr']:.3f}")
    print(f"  Avg N_eff:     {s['avg_n_eff']:.1f}")

    # Monthly breakdown
    print(f"\n  {'Month':<10} {'Picks':>5} {'WR%':>6} {'AvgRet':>8} "
          f"{'SL%':>5} {'$/mo':>8} {'Regime':>20}")
    print(f"  {'-'*65}")
    for m in s['monthly']:
        regime_str = ' '.join(f"{k}:{v}" for k, v in sorted(m['regimes'].items()))
        print(f"  {m['month']:<10} {m['n_picks']:>5} {m['wr']:>5.1f}% "
              f"{m['avg_ret']:>+7.3f}% {m['sl_rate']:>4.1f}% "
              f"${m['dollar_pnl']:>+7.0f} {regime_str:>20}")


def print_comparison_table(results):
    """Side-by-side comparison of all experiments."""
    print(f"\n{'='*90}")
    print(f"  COMPARISON TABLE — All Experiments")
    print(f"{'='*90}")
    print(f"  {'Label':<30} {'WR%':>6} {'AvgRet':>8} {'SL%':>5} "
          f"{'$/mo':>8} {'Total$':>9} {'r':>6} {'Neff':>5}")
    print(f"  {'-'*80}")

    # Sort by avg $/mo
    ranked = sorted(results, key=lambda x: x['avg_dollar_mo'], reverse=True)
    for s in ranked:
        print(f"  {s['label']:<30} {s['overall_wr']:>5.1f}% "
              f"{s['overall_avg_ret']:>+7.3f}% {s['overall_sl_rate']:>4.1f}% "
              f"${s['avg_dollar_mo']:>+7.0f} ${s['total_dollar']:>+8.0f} "
              f"{s['pred_actual_corr']:>5.3f} {s['avg_n_eff']:>5.1f}")


def analyze_adaptation(flat_result, best_decay_result):
    """Show how predictions change between FLAT and adaptive in different market regimes."""
    if not flat_result or not best_decay_result:
        return

    print(f"\n{'='*70}")
    print(f"  ADAPTATION ANALYSIS — Does the model actually adapt?")
    print(f"{'='*70}")

    # Compare regime detection per month
    flat_months = {m['month']: m for m in flat_result['monthly']}
    adapt_months = {m['month']: m for m in best_decay_result['monthly']}

    common = sorted(set(flat_months.keys()) & set(adapt_months.keys()))

    print(f"\n  {'Month':<10} {'FLAT WR':>8} {'ADAPT WR':>9} {'Delta':>7} "
          f"{'FLAT $/mo':>10} {'ADAPT $/mo':>11} {'Delta$':>8}")
    print(f"  {'-'*65}")

    for m in common:
        f = flat_months[m]
        a = adapt_months[m]
        dwr = a['wr'] - f['wr']
        dd = a['dollar_pnl'] - f['dollar_pnl']
        print(f"  {m:<10} {f['wr']:>7.1f}% {a['wr']:>8.1f}% {dwr:>+6.1f}% "
              f"  ${f['dollar_pnl']:>+8.0f}  ${a['dollar_pnl']:>+8.0f} ${dd:>+7.0f}")

    # Count months where adaptive won
    adapt_wins = sum(1 for m in common
                     if adapt_months[m]['dollar_pnl'] > flat_months[m]['dollar_pnl'])
    print(f"\n  Adaptive wins {adapt_wins}/{len(common)} months "
          f"({adapt_wins/len(common)*100:.0f}%)")

    # Analyze by year
    print(f"\n  Per-Year Breakdown:")
    for year in sorted(set(m[:4] for m in common)):
        year_months = [m for m in common if m.startswith(year)]
        flat_yr = sum(flat_months[m]['dollar_pnl'] for m in year_months)
        adapt_yr = sum(adapt_months[m]['dollar_pnl'] for m in year_months)
        print(f"    {year}: FLAT=${flat_yr:+,.0f}  ADAPT=${adapt_yr:+,.0f}  "
              f"Delta=${adapt_yr - flat_yr:+,.0f}")


def analyze_n_eff_impact(flat_result, best_decay_result):
    """Check how time decay affects effective sample size."""
    if not flat_result or not best_decay_result:
        return

    print(f"\n{'='*70}")
    print(f"  EFFECTIVE SAMPLE SIZE ANALYSIS")
    print(f"{'='*70}")

    flat_neffs = [p['n_eff'] for p in flat_result['all_picks']]
    adapt_neffs = [p['n_eff'] for p in best_decay_result['all_picks']]

    print(f"  FLAT:     mean={np.mean(flat_neffs):.1f}  "
          f"median={np.median(flat_neffs):.1f}  "
          f"p10={np.percentile(flat_neffs, 10):.1f}  "
          f"p90={np.percentile(flat_neffs, 90):.1f}")
    print(f"  ADAPTIVE: mean={np.mean(adapt_neffs):.1f}  "
          f"median={np.median(adapt_neffs):.1f}  "
          f"p10={np.percentile(adapt_neffs, 10):.1f}  "
          f"p90={np.percentile(adapt_neffs, 90):.1f}")

    # N_eff vs accuracy
    print(f"\n  N_eff vs Win Rate (FLAT):")
    for lo, hi, label in [(0, 5, '<5'), (5, 20, '5-20'), (20, 100, '20-100'), (100, 99999, '>100')]:
        bucket = [p for p in flat_result['all_picks'] if lo <= p['n_eff'] < hi]
        if bucket:
            wr = sum(1 for p in bucket if p['realized'] > 0) / len(bucket) * 100
            print(f"    N_eff {label:>6}: n={len(bucket):>4}, WR={wr:.1f}%")


def analyze_regime_shift_response(all_picks_flat, all_picks_adapt):
    """Check if adaptive kernel responds faster to regime shifts."""
    if not all_picks_flat or not all_picks_adapt:
        return

    print(f"\n{'='*70}")
    print(f"  REGIME SHIFT RESPONSE — Does adaptive react faster?")
    print(f"{'='*70}")

    # Group by month and compare E[R] predictions
    def by_month(picks):
        m = defaultdict(list)
        for p in picks:
            m[p['date'][:7]].append(p)
        return m

    flat_m = by_month(all_picks_flat)
    adapt_m = by_month(all_picks_adapt)

    common = sorted(set(flat_m.keys()) & set(adapt_m.keys()))

    print(f"\n  {'Month':<10} {'Flat E[R]':>10} {'Adapt E[R]':>11} "
          f"{'Actual':>8} {'F err':>7} {'A err':>7}")
    print(f"  {'-'*60}")

    for m in common:
        f_er = np.mean([p['er'] for p in flat_m[m]])
        a_er = np.mean([p['er'] for p in adapt_m[m]])
        actual = np.mean([p['outcome'] for p in flat_m[m]])
        f_err = abs(f_er - actual)
        a_err = abs(a_er - actual)
        better = '<--' if a_err < f_err else ''
        print(f"  {m:<10} {f_er:>+9.3f}% {a_er:>+10.3f}% "
              f"{actual:>+7.3f}% {f_err:>6.3f} {a_err:>6.3f} {better}")

    # MAE comparison
    flat_errs = []
    adapt_errs = []
    for m in common:
        for p in flat_m[m]:
            flat_errs.append(abs(p['er'] - p['outcome']))
        for p in adapt_m[m]:
            adapt_errs.append(abs(p['er'] - p['outcome']))

    print(f"\n  Mean Abs Error:  FLAT={np.mean(flat_errs):.4f}  "
          f"ADAPT={np.mean(adapt_errs):.4f}")


# ════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("  ADAPTIVE KERNEL BACKTEST — Time Decay + Outcome Feedback")
    print("  Walk-Forward: train on months 1..N, test on month N+1")
    print("=" * 70)

    data = load_all_data()

    all_results = []

    # ── 1. BASELINE: Flat kernel (current production) ──
    print("\n>>> Running FLAT baseline (current production)...")
    flat = run_walkforward(data, mode='FLAT', label='FLAT (production)')
    if flat:
        print_summary(flat)
        all_results.append(flat)

    # ── 2. DECAY ONLY: Test half_lives ──
    half_lives = [60, 90, 180, 365]
    decay_results = {}
    for hl in half_lives:
        print(f"\n>>> Running DECAY half_life={hl}d...")
        r = run_walkforward(data, mode='DECAY', half_life=hl,
                            label=f'DECAY hl={hl}d')
        if r:
            print_summary(r)
            all_results.append(r)
            decay_results[hl] = r

    # ── 3. FEEDBACK: Test feedback strengths with best decay ──
    # Find best decay half_life
    if decay_results:
        best_hl = max(decay_results.keys(),
                      key=lambda k: decay_results[k]['avg_dollar_mo'])
        print(f"\n>>> Best decay half_life: {best_hl}d")
    else:
        best_hl = 180

    feedback_configs = [
        (1.2, 0.8, 'mild'),
        (1.5, 0.7, 'moderate'),
        (2.0, 0.5, 'strong'),
    ]
    feedback_results = {}
    for fc, fw, name in feedback_configs:
        print(f"\n>>> Running FEEDBACK ({name}: correct={fc}, wrong={fw}) "
              f"hl={best_hl}d...")
        r = run_walkforward(data, mode='FEEDBACK', half_life=best_hl,
                            fb_correct=fc, fb_wrong=fw,
                            label=f'FEEDBACK {name} hl={best_hl}d')
        if r:
            print_summary(r)
            all_results.append(r)
            feedback_results[name] = r

    # ── 4. Comparison table ──
    if all_results:
        print_comparison_table(all_results)

    # ── 5. Adaptation analysis ──
    if flat and decay_results:
        best_decay = decay_results[best_hl]
        analyze_adaptation(flat, best_decay)
        analyze_n_eff_impact(flat, best_decay)

    if flat and all_results:
        # Find overall best
        best_overall = max(all_results, key=lambda x: x['avg_dollar_mo'])
        if best_overall['mode'] != 'FLAT':
            analyze_regime_shift_response(flat['all_picks'],
                                          best_overall['all_picks'])
        else:
            # Adaptive didn't win — check closest
            if len(all_results) > 1:
                non_flat = [r for r in all_results if r['mode'] != 'FLAT']
                if non_flat:
                    best_non_flat = max(non_flat, key=lambda x: x['avg_dollar_mo'])
                    analyze_regime_shift_response(flat['all_picks'],
                                                  best_non_flat['all_picks'])

    # ── 6. Honest Conclusion ──
    print(f"\n{'='*70}")
    print(f"  CONCLUSION")
    print(f"{'='*70}")

    if all_results:
        best = max(all_results, key=lambda x: x['avg_dollar_mo'])
        worst = min(all_results, key=lambda x: x['avg_dollar_mo'])

        print(f"\n  Best:  {best['label']} — ${best['avg_dollar_mo']:+,.0f}/mo, "
              f"WR={best['overall_wr']:.1f}%")
        print(f"  Worst: {worst['label']} — ${worst['avg_dollar_mo']:+,.0f}/mo, "
              f"WR={worst['overall_wr']:.1f}%")

        flat_pnl = flat['avg_dollar_mo'] if flat else 0
        best_adaptive = max([r for r in all_results if r['mode'] != 'FLAT'],
                            key=lambda x: x['avg_dollar_mo'],
                            default=None)

        if best_adaptive:
            delta = best_adaptive['avg_dollar_mo'] - flat_pnl
            pct = (delta / abs(flat_pnl) * 100) if flat_pnl else 0

            if delta > 5:  # > $5/mo improvement
                print(f"\n  VERDICT: Adaptive kernel WINS by ${delta:+,.0f}/mo "
                      f"({pct:+.1f}%)")
                print(f"  Best config: {best_adaptive['label']}")
                print(f"  Recommendation: Implement in production.")
            elif delta > -5:
                print(f"\n  VERDICT: DRAW — adaptive is within ${abs(delta):.0f}/mo "
                      f"of flat.")
                print(f"  The extra complexity is NOT justified.")
                print(f"  Keep current flat kernel.")
            else:
                print(f"\n  VERDICT: Adaptive kernel LOSES by ${delta:+,.0f}/mo "
                      f"({pct:+.1f}%)")
                print(f"  Time decay HURTS because older data provides valuable "
                      f"regime diversity.")
                print(f"  Keep current flat kernel.")

            # Why?
            print(f"\n  WHY:")
            if flat and best_adaptive:
                print(f"    Flat pred-actual correlation:     "
                      f"r={flat['pred_actual_corr']:.3f}")
                print(f"    Adaptive pred-actual correlation: "
                      f"r={best_adaptive['pred_actual_corr']:.3f}")
                print(f"    Flat N_eff:     "
                      f"{flat['avg_n_eff']:.1f}")
                print(f"    Adaptive N_eff: "
                      f"{best_adaptive['avg_n_eff']:.1f}")


if __name__ == '__main__':
    main()
