#!/usr/bin/env python3
"""
Backtest: v5.3 kernel vs v7.0 Council — walk-forward comparison.
Uses backfill_signal_outcomes + signal_daily_bars.
Council: Regime Brain (daily TRADE/SKIP) + Stock Brain (per-stock prob) + Risk Brain.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import sqlite3
import numpy as np
from pathlib import Path
from collections import defaultdict
from sklearn.ensemble import GradientBoostingClassifier

DB_PATH = Path(__file__).resolve().parent.parent / 'data' / 'trade_history.db'


def load_all_data():
    conn = None  # via get_session())
    # Per-signal data with macro
    signals = conn.execute("""
        SELECT b.scan_date, b.symbol, b.atr_pct, b.momentum_5d,
               b.distance_from_20d_high, b.volume_ratio, b.vix_at_signal,
               b.outcome_5d, b.sector,
               COALESCE(m.vix_close, b.vix_at_signal) as vix_close,
               m.spy_close, m.crude_close, m.yield_10y,
               COALESCE(m.vix3m_close, 22) as vix3m,
               mb.pct_above_20d_ma, mb.new_52w_lows, mb.new_52w_highs,
               d0.open as d0o, d1.high as h1, d1.low as l1,
               d2.high as h2, d2.low as l2,
               d3.high as h3, d3.low as l3, d3.close as c3
        FROM backfill_signal_outcomes b
        LEFT JOIN macro_snapshots m ON b.scan_date = m.date
        LEFT JOIN market_breadth mb ON b.scan_date = mb.date
        JOIN signal_daily_bars d0 ON b.scan_date=d0.scan_date AND b.symbol=d0.symbol AND d0.day_offset=0
        JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
        JOIN signal_daily_bars d2 ON b.scan_date=d2.scan_date AND b.symbol=d2.symbol AND d2.day_offset=2
        JOIN signal_daily_bars d3 ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
        WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0 AND d0.open > 0
        AND m.spy_close IS NOT NULL AND mb.pct_above_20d_ma IS NOT NULL
        ORDER BY b.scan_date
    """).fetchall()
    conn.close()
    return signals


def simulate_trade(atr, d0o, h1, l1, h2, l2, h3, l3, c3, tp_ratio=1.0):
    sl_pct = max(1.5, min(5.0, 1.5 * atr))
    tp_pct = max(0.5, tp_ratio * atr)
    for h, l in [(h1, l1), (h2, l2), (h3, l3)]:
        if (l / d0o - 1) * 100 <= -sl_pct:
            return -sl_pct
        if (h / d0o - 1) * 100 >= tp_pct:
            return tp_pct
    return (c3 / d0o - 1) * 100


def run_backtest():
    print("Loading data...")
    signals = load_all_data()
    print(f"  {len(signals)} signals loaded")

    # Group by month
    monthly_data = defaultdict(list)
    for s in signals:
        monthly_data[s[0][:7]].append(s)
    months = sorted(monthly_data.keys())
    print(f"  {len(months)} months: {months[0]} to {months[-1]}")

    # Group by date for regime brain
    daily_data = defaultdict(list)
    for s in signals:
        daily_data[s[0]].append(s)
    dates = sorted(daily_data.keys())

    # Walk-forward: 12-month rolling train, test each month
    print("\nWalk-forward backtest...")
    print()
    print(f"{'Month':<10} {'v5.3 Tr':>7} {'v5.3 WR':>7} {'v5.3 $':>7} "
          f"{'SB Tr':>7} {'SB WR':>7} {'SB $':>7} "
          f"{'Council':>7} {'Cncl WR':>7} {'Cncl $':>7}")
    print("-" * 85)

    results = {'v53': [], 'sb': [], 'council': []}
    total = {'v53': {'trades': 0, 'pnl': 0, 'wins': 0},
             'sb': {'trades': 0, 'pnl': 0, 'wins': 0},
             'council': {'trades': 0, 'pnl': 0, 'wins': 0}}

    for mi, month in enumerate(months):
        if mi < 12:  # need 12 months training
            continue

        # Training window: last 12 months
        train_months = months[mi - 12:mi]
        train_signals = []
        for m in train_months:
            train_signals.extend(monthly_data[m])

        test_signals = monthly_data[month]
        if len(train_signals) < 500 or len(test_signals) < 10:
            continue

        # --- Build features ---
        def sig_features(s):
            return [s[2], s[3] or 0, s[4] or -5, s[5] or 1, s[6] or 20,
                    s[9] or 20, s[10] or 550, s[11] or 75, s[14] or 50, s[15] or 30]

        def macro_features(s):
            return [s[9] or 20, s[13] or 22, s[10] or 550, s[11] or 75,
                    s[12] or 4, s[14] or 50, s[15] or 30, s[16] or 50]

        # --- Train Stock Brain ---
        X_train_sb = np.array([sig_features(s) for s in train_signals])
        y_train_sb = np.array([1 if s[7] > 0 else 0 for s in train_signals])

        sb_clf = GradientBoostingClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            min_samples_leaf=50, subsample=0.8, random_state=42)
        sb_clf.fit(X_train_sb, y_train_sb)

        # --- Train Regime Brain ---
        train_daily = defaultdict(list)
        for s in train_signals:
            train_daily[s[0]].append(s)

        X_train_rb, y_train_rb = [], []
        for dt, sigs in train_daily.items():
            daily_wr = np.mean([1 if s[7] > 0 else 0 for s in sigs])
            X_train_rb.append(macro_features(sigs[0]))
            y_train_rb.append(1 if daily_wr > 0.55 else 0)

        X_train_rb = np.array(X_train_rb)
        y_train_rb = np.array(y_train_rb)

        rb_clf = GradientBoostingClassifier(
            n_estimators=200, max_depth=3, learning_rate=0.05,
            min_samples_leaf=10, subsample=0.8, random_state=42)
        rb_clf.fit(X_train_rb, y_train_rb)

        # --- Test ---
        v53_pnl, v53_trades, v53_wins = 0, 0, 0
        sb_pnl, sb_trades, sb_wins = 0, 0, 0
        cncl_pnl, cncl_trades, cncl_wins = 0, 0, 0

        test_daily = defaultdict(list)
        for s in test_signals:
            test_daily[s[0]].append(s)

        for dt, sigs in test_daily.items():
            # Regime Brain decision
            regime_prob = rb_clf.predict_proba(
                np.array(macro_features(sigs[0])).reshape(1, -1))[0, 1]
            regime_trade = regime_prob >= 0.50

            # Sort by depth of dip (proxy for kernel ranking)
            sigs_sorted = sorted(sigs, key=lambda s: s[4] or 0)
            top8 = sigs_sorted[:8]

            for s in top8:
                pnl = simulate_trade(s[2], s[17], s[18], s[19], s[20], s[21], s[22], s[23], s[24])

                # v5.3: trade all
                v53_pnl += pnl
                v53_trades += 1
                if pnl > 0: v53_wins += 1

                # Stock Brain: trade if prob >= 0.50
                sb_prob = sb_clf.predict_proba(
                    np.array(sig_features(s)).reshape(1, -1))[0, 1]
                if sb_prob >= 0.50:
                    sb_pnl += pnl
                    sb_trades += 1
                    if pnl > 0: sb_wins += 1

                # Council: regime + stock brain
                if regime_trade and sb_prob >= 0.50:
                    cncl_pnl += pnl
                    cncl_trades += 1
                    if pnl > 0: cncl_wins += 1

        v53_wr = v53_wins / v53_trades * 100 if v53_trades else 0
        sb_wr = sb_wins / sb_trades * 100 if sb_trades else 0
        cncl_wr = cncl_wins / cncl_trades * 100 if cncl_trades else 0

        v53_d = v53_pnl * 5
        sb_d = sb_pnl * 5
        cncl_d = cncl_pnl * 5

        print(f"{month:<10} {v53_trades:>7} {v53_wr:>6.1f}% {v53_d:>+6.0f} "
              f"{sb_trades:>7} {sb_wr:>6.1f}% {sb_d:>+6.0f} "
              f"{cncl_trades:>7} {cncl_wr:>6.1f}% {cncl_d:>+6.0f}")

        results['v53'].append(v53_d)
        results['sb'].append(sb_d)
        results['council'].append(cncl_d)
        for k, v in [('v53', (v53_trades, v53_pnl, v53_wins)),
                      ('sb', (sb_trades, sb_pnl, sb_wins)),
                      ('council', (cncl_trades, cncl_pnl, cncl_wins))]:
            total[k]['trades'] += v[0]
            total[k]['pnl'] += v[1]
            total[k]['wins'] += v[2]

    # Summary
    n_months = len(results['v53'])
    print("=" * 85)
    print(f"\n{'SUMMARY':=^85}")
    print(f"{'Metric':<25} {'v5.3 (kernel)':>20} {'Stock Brain':>20} {'Council':>20}")
    print(f"{'-'*25} {'-'*20} {'-'*20} {'-'*20}")

    for k, label in [('v53', 'v5.3'), ('sb', 'Stock Brain'), ('council', 'Council')]:
        t = total[k]
        wr = t['wins'] / t['trades'] * 100 if t['trades'] else 0
        er = t['pnl'] / t['trades'] if t['trades'] else 0
        monthly = np.mean(results[k]) if results[k] else 0
        worst = min(results[k]) if results[k] else 0
        win_months = sum(1 for x in results[k] if x > 0)

    for metric, fn in [
        ('Total trades', lambda k: total[k]['trades']),
        ('Win rate', lambda k: f"{total[k]['wins']/total[k]['trades']*100:.1f}%" if total[k]['trades'] else 'N/A'),
        ('E[R]/trade', lambda k: f"{total[k]['pnl']/total[k]['trades']:+.3f}%" if total[k]['trades'] else 'N/A'),
        ('Total PnL', lambda k: f"${total[k]['pnl']*5:,.0f}"),
        ('Monthly avg', lambda k: f"${np.mean(results[k]):,.0f}" if results[k] else 'N/A'),
        ('Worst month', lambda k: f"${min(results[k]):,.0f}" if results[k] else 'N/A'),
        ('Win months', lambda k: f"{sum(1 for x in results[k] if x>0)}/{len(results[k])}"),
    ]:
        vals = [fn(k) for k in ['v53', 'sb', 'council']]
        print(f"{metric:<25} {str(vals[0]):>20} {str(vals[1]):>20} {str(vals[2]):>20}")

    # Verdict
    v53_mo = np.mean(results['v53']) if results['v53'] else 0
    cncl_mo = np.mean(results['council']) if results['council'] else 0
    delta = cncl_mo - v53_mo

    print(f"\n{'VERDICT':=^85}")
    if delta > 20:
        print(f"  Council BEATS kernel by ${delta:.0f}/mo")
    elif delta < -20:
        print(f"  Council UNDERPERFORMS kernel by ${-delta:.0f}/mo")
    else:
        print(f"  Council ≈ kernel (delta=${delta:.0f}/mo)")

    # Council value
    cncl_wr = total['council']['wins'] / total['council']['trades'] * 100 if total['council']['trades'] else 0
    v53_wr = total['v53']['wins'] / total['v53']['trades'] * 100 if total['v53']['trades'] else 0
    print(f"  WR improvement: {v53_wr:.1f}% → {cncl_wr:.1f}% ({cncl_wr-v53_wr:+.1f}%)")
    print(f"  Trade reduction: {total['v53']['trades']} → {total['council']['trades']} "
          f"(-{(1-total['council']['trades']/total['v53']['trades'])*100:.0f}%)")


if __name__ == '__main__':
    run_backtest()
