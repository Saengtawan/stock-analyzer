#!/usr/bin/env python3
"""Walk-forward backtest: Uniform params vs Adaptive per-sector params.

Train on 12-month rolling window, test on next month.
Compares $/mo, WR, E[R] between:
  1. UNIFORM: tp=1.0×ATR, sl=1.5×ATR, atr≤5, mom≤3  (current production)
  2. ADAPTIVE: per-sector learned tp/sl/atr/mom from AdaptiveParameterLearner
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import sqlite3, numpy as np
from collections import defaultdict
from discovery.adaptive_params import (
    AdaptiveParameterLearner, _classify_regime, _sim_trade, DEFAULTS
)

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'trade_history.db')
conn = None  # via get_session()

# Load all data
rows = conn.execute('''
    SELECT b.scan_date, b.symbol, b.sector,
           b.atr_pct, b.momentum_5d, b.distance_from_20d_high,
           b.volume_ratio, b.outcome_5d, b.vix_at_signal,
           COALESCE(m.vix_close, 20), COALESCE(mb.pct_above_20d_ma, 50),
           d0.high, d0.low, d0.close, d0.open,
           d1.open, d1.high, d1.low,
           d3.high, d3.low, d3.close
    FROM backfill_signal_outcomes b
    LEFT JOIN macro_snapshots m ON b.scan_date = m.date
    LEFT JOIN market_breadth mb ON b.scan_date = mb.date
    LEFT JOIN signal_daily_bars d0 ON b.scan_date=d0.scan_date AND b.symbol=d0.symbol AND d0.day_offset=0
    JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
    JOIN signal_daily_bars d3 ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
    WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0 AND d1.open > 0
    AND b.sector IS NOT NULL
    AND m.vix_close IS NOT NULL AND mb.pct_above_20d_ma IS NOT NULL
    ORDER BY b.scan_date
''').fetchall()
conn.close()

# Parse into dicts
signals = []
for r in rows:
    d0h = r[11] or 0
    d0l = r[12] or 0
    d0c = r[13] or 0
    d0_range = d0h - d0l
    d0_pos = (d0c - d0l) / d0_range if d0_range > 0 else 0.5

    signals.append({
        'scan_date': r[0], 'symbol': r[1], 'sector': r[2],
        'atr': r[3], 'mom': r[4] or 0, 'd20h': r[5] or -5,
        'vol': r[6] or 1, 'o5d': r[7], 'vix': r[9], 'breadth': r[10],
        'd0_pos': d0_pos,
        'd1o': r[15], 'd1h': r[16], 'd1l': r[17],
        'd3h': r[18], 'd3l': r[19], 'd3c': r[20],
    })

# Group by month
monthly = defaultdict(list)
for s in signals:
    monthly[s['scan_date'][:7]].append(s)
months = sorted(monthly.keys())

print(f"Data: {len(signals)} signals, {len(months)} months ({months[0]} to {months[-1]})")
print()

# Simulation
def sim_month_uniform(test_sigs):
    """Current production: tp=1.0×ATR, sl=1.5×ATR, atr≤5, mom≤3."""
    pnls = []
    for s in test_sigs:
        if s['atr'] > 5.0: continue
        if s['mom'] > 3: continue
        if s['mom'] > 0 and s['d20h'] > -8: continue
        if s['d0_pos'] < 0.3: continue
        pnl = _sim_trade(s['d1o'], s['d1h'], s['d1l'],
                         s['d3h'], s['d3l'], s['d3c'],
                         s['atr'], 1.0, 1.5)
        pnls.append(pnl)
    return pnls


def sim_month_adaptive(test_sigs, learner):
    """Per-sector adaptive params from learner. v15.1: hybrid SL/TP."""
    pnls = []
    for s in test_sigs:
        sector = s['sector']
        regime = _classify_regime(s['vix'], s['breadth'])

        atr_max = learner.get(sector, regime, 'atr_max')
        mom_cut = learner.get(sector, regime, 'mom_cut')
        d0_min = learner.get(sector, regime, 'd0_close_min')

        # v15.1: Hybrid — SL from ATR, TP from adaptive absolute %
        sl_pct = max(1.5, min(3.5, 1.0 * s['atr']))  # ATR-based SL
        tp_pct = learner.get(sector, regime, 'tp_pct')  # absolute TP
        tp_pct = max(2.0, min(10.0, tp_pct))
        if tp_pct <= sl_pct: tp_pct = sl_pct * 2.0

        if s['atr'] > atr_max: continue
        if s['mom'] > mom_cut: continue
        if s['d0_pos'] < d0_min: continue

        # v15.1: simulate with absolute SL/TP %
        d1o = s['d1o']
        for h, l in [(s['d1h'], s['d1l']), (s['d3h'], s['d3l'])]:
            if (l/d1o-1)*100 <= -sl_pct:
                pnls.append(-sl_pct); break
            if (h/d1o-1)*100 >= tp_pct:
                pnls.append(tp_pct); break
        else:
            pnls.append((s['d3c']/d1o-1)*100)
    return pnls


print(f"{'Mo':8s} {'Uni$':>7s} {'UniWR':>6s} {'UniN':>5s}  {'Adp$':>7s} {'AdpWR':>6s} {'AdpN':>5s}  {'Δ$/mo':>7s}")
print("-" * 65)

uni_all, adp_all = [], []
uni_monthly, adp_monthly = [], []

for mi in range(12, len(months)):
    # Build training data for adaptive learner
    train_months = months[mi-12:mi]
    train_end = train_months[-1] + '-28'  # approximate end of month

    # Fit adaptive learner on training period
    learner = AdaptiveParameterLearner()
    learner.fit(max_date=train_end)

    # Test month
    test_sigs = monthly[months[mi]]
    if len(test_sigs) < 10:
        continue

    # Simulate both
    uni_pnls = sim_month_uniform(test_sigs)
    adp_pnls = sim_month_adaptive(test_sigs, learner)

    uni_sum = sum(uni_pnls) * 5  # $5K capital scaling
    adp_sum = sum(adp_pnls) * 5
    uni_wr = (sum(1 for p in uni_pnls if p > 0) / len(uni_pnls) * 100) if uni_pnls else 0
    adp_wr = (sum(1 for p in adp_pnls if p > 0) / len(adp_pnls) * 100) if adp_pnls else 0

    delta = adp_sum - uni_sum

    print(f"{months[mi]:8s} {uni_sum:>+6.0f}$ {uni_wr:>5.1f}% {len(uni_pnls):>5d}  "
          f"{adp_sum:>+6.0f}$ {adp_wr:>5.1f}% {len(adp_pnls):>5d}  {delta:>+6.0f}$")

    uni_all.extend(uni_pnls)
    adp_all.extend(adp_pnls)
    uni_monthly.append(uni_sum)
    adp_monthly.append(adp_sum)

print("=" * 65)
print()

# Summary
u = np.array(uni_all)
a = np.array(adp_all)
n_months = len(uni_monthly)

print(f"{'Metric':<20s} {'Uniform':>12s} {'Adaptive':>12s} {'Δ':>10s}")
print("-" * 56)
print(f"{'Trades':<20s} {len(u):>12d} {len(a):>12d} {len(a)-len(u):>+10d}")
print(f"{'WR':<20s} {(u>0).mean()*100:>11.1f}% {(a>0).mean()*100:>11.1f}% {((a>0).mean()-(u>0).mean())*100:>+9.1f}%")
print(f"{'E[R]/trade':<20s} {u.mean():>+11.3f}% {a.mean():>+11.3f}% {a.mean()-u.mean():>+9.3f}%")
print(f"{'Total PnL':<20s} {u.sum()*5:>+11.0f}$ {a.sum()*5:>+11.0f}$ {(a.sum()-u.sum())*5:>+9.0f}$")
print(f"{'$/mo avg':<20s} {np.mean(uni_monthly):>+11.0f}$ {np.mean(adp_monthly):>+11.0f}$ {np.mean(adp_monthly)-np.mean(uni_monthly):>+9.0f}$")
print(f"{'Worst month':<20s} {min(uni_monthly):>+11.0f}$ {min(adp_monthly):>+11.0f}$")
print(f"{'Best month':<20s} {max(uni_monthly):>+11.0f}$ {max(adp_monthly):>+11.0f}$")
print(f"{'Win months':<20s} {sum(1 for x in uni_monthly if x>0):>8d}/{n_months} {sum(1 for x in adp_monthly if x>0):>8d}/{n_months}")
