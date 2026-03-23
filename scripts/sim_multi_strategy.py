#!/usr/bin/env python3
"""Walk-forward: v14.0 DIP-only vs v15.0 Multi-Strategy auto-switch."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import sqlite3, numpy as np
from collections import defaultdict
from discovery.multi_strategy import (
    StrategySelector, STRATEGIES, detect_condition, strategy_dip,
    strategy_oversold, strategy_momentum, strategy_value, strategy_contrarian,
)
from discovery.adaptive_params import AdaptiveParameterLearner, _classify_regime

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'trade_history.db')
conn = sqlite3.connect(DB)

# Load signals with OHLC for SL/TP sim
rows = conn.execute("""
    SELECT b.scan_date, b.symbol, b.sector, b.atr_pct, b.momentum_5d,
           b.distance_from_20d_high, b.volume_ratio, b.outcome_5d,
           COALESCE(m.vix_close,20), COALESCE(mb.pct_above_20d_ma,50),
           sf.beta, sf.pe_forward, sf.market_cap,
           d1.open, d1.high, d1.low, d3.high, d3.low, d3.close
    FROM backfill_signal_outcomes b
    LEFT JOIN macro_snapshots m ON b.scan_date = m.date
    LEFT JOIN market_breadth mb ON b.scan_date = mb.date
    LEFT JOIN stock_fundamentals sf ON b.symbol = sf.symbol
    JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
    JOIN signal_daily_bars d3 ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
    WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0 AND d1.open > 0
    AND b.sector IS NOT NULL AND m.vix_close IS NOT NULL
    ORDER BY b.scan_date
""").fetchall()
conn.close()

def sim_trade(d1o,d1h,d1l,d3h,d3l,d3c,atr,tp_r,sl_m):
    sl = max(1.5, min(5.0, sl_m*atr))
    tp = max(0.5, tp_r*atr)
    if tp <= sl: tp = sl * 1.5
    for h,l in [(d1h,d1l),(d3h,d3l)]:
        if (l/d1o-1)*100<=-sl: return -sl
        if (h/d1o-1)*100>=tp: return tp
    return (d3c/d1o-1)*100

# Build stock pool per date (with mom_5d, d20h, etc.)
monthly = defaultdict(list)
by_date = defaultdict(list)
for r in rows:
    monthly[r[0][:7]].append(r)
    by_date[r[0]].append({
        'symbol': r[1], 'sector': r[2], 'atr_pct': r[3],
        'mom_5d': r[4] or 0, 'd20h': r[5] or -5, 'vol_ratio': r[6] or 1,
        'o5d': r[7], 'vix': r[8], 'breadth': r[9],
        'beta': r[10] or 1, 'pe_forward': r[11], 'market_cap': r[12] or 1e9,
        'd1o': r[13], 'd1h': r[14], 'd1l': r[15],
        'd3h': r[16], 'd3l': r[17], 'd3c': r[18],
    })

months = sorted(monthly.keys())
print(f"Data: {len(rows):,} signals, {len(months)} months")

# Walk-forward
print(f"\n{'Mo':8s} {'Cond':8s} {'Strat':12s} {'v14$':>7s} {'v15$':>7s} {'Δ':>7s}")
print("-"*55)

v14_mo, v15_mo = [], []

for mi in range(12, len(months)):
    test_sigs = monthly[months[mi]]
    if len(test_sigs) < 10: continue
    train_end = months[mi-1]+'-28'

    # v14: adaptive DIP
    learner = AdaptiveParameterLearner()
    learner.fit(max_date=train_end)

    # v15: multi-strategy selector (train on same period)
    selector = StrategySelector()
    selector.fit(max_date=train_end)

    # Group test by date
    test_by_date = defaultdict(list)
    for s in test_sigs:
        test_by_date[s[0]].append(s)

    v14_pnl, v15_pnl = [], []
    month_cond = 'NORMAL'
    month_strat = 'DIP'

    for dt, sigs in test_by_date.items():
        vix = sigs[0][8]
        breadth = sigs[0][9]
        regime = _classify_regime(vix, breadth)
        condition = detect_condition(vix, breadth)
        month_cond = condition

        # v14: adaptive DIP + beta + PE
        for s in sigs:
            atr, mom = s[3], s[4] or 0
            sector = s[2]
            beta = s[10] or 1
            pe = s[11]
            d1o,d1h,d1l,d3h,d3l,d3c = s[13],s[14],s[15],s[16],s[17],s[18]

            atr_max = learner.get(sector, regime, 'atr_max')
            mom_cut = learner.get(sector, regime, 'mom_cut')
            tp_r = learner.get(sector, regime, 'tp_ratio')
            sl_m = learner.get(sector, regime, 'sl_mult')
            if atr > atr_max or mom > mom_cut: continue
            if beta > 1.5: continue
            if pe is not None and pe > 35: continue
            v14_pnl.append(sim_trade(d1o,d1h,d1l,d3h,d3l,d3c,atr,tp_r,sl_m))

        # v15: multi-strategy
        strat_name, _ = selector.select(vix, breadth)
        month_strat = strat_name

        # Build stock pool for strategy selection
        pool = []
        for s in sigs:
            pool.append({
                'symbol': s[1], 'sector': s[2], 'beta': s[10] or 1,
                'pe_forward': s[11], 'market_cap': s[12] or 1e9,
                'mom_5d': s[4] or 0, 'd20h': s[5] or -5,
                'mom_20d': (s[4] or 0) * 2,  # rough proxy
                'vol_ratio': s[6] or 1,
                # trade data
                'atr': s[3], 'd1o': s[13], 'd1h': s[14], 'd1l': s[15],
                'd3h': s[16], 'd3l': s[17], 'd3c': s[18],
            })

        picks = selector.get_picks(strat_name, pool)
        if not picks:
            # Fallback to DIP
            picks = strategy_dip(pool)

        sltp = selector.get_sltp(strat_name)
        for p in picks:
            atr = p.get('atr', 3)
            beta = p.get('beta', 1)
            pe = p.get('pe_forward')
            if beta > 1.5: continue
            if pe is not None and pe > 35 and strat_name != 'VALUE': continue
            tp_r = sltp['tp_ratio']
            sl_m = sltp['sl_mult']
            v15_pnl.append(sim_trade(
                p['d1o'], p['d1h'], p['d1l'],
                p['d3h'], p['d3l'], p['d3c'],
                atr, tp_r, sl_m))

    v14_sum = sum(v14_pnl)*5
    v15_sum = sum(v15_pnl)*5
    delta = v15_sum - v14_sum
    v14_mo.append(v14_sum)
    v15_mo.append(v15_sum)

    print(f"{months[mi]:8s} {month_cond:8s} {month_strat:12s} "
          f"{v14_sum:>+6.0f}$ {v15_sum:>+6.0f}$ {delta:>+6.0f}$")

print("="*55)
v14 = np.array(v14_mo)
v15 = np.array(v15_mo)

print(f"\n{'Metric':<20s} {'v14.0 DIP':>12s} {'v15.0 Multi':>12s} {'Δ':>8s}")
print("-"*55)
print(f"{'$/mo avg':<20s} {'${:+,.0f}'.format(v14.mean()):>12s} {'${:+,.0f}'.format(v15.mean()):>12s} {'${:+,.0f}'.format(v15.mean()-v14.mean()):>8s}")
print(f"{'Worst month':<20s} {'${:+,.0f}'.format(v14.min()):>12s} {'${:+,.0f}'.format(v15.min()):>12s}")
print(f"{'Best month':<20s} {'${:+,.0f}'.format(v14.max()):>12s} {'${:+,.0f}'.format(v15.max()):>12s}")
print(f"{'Win months':<20s} {'{}/{}'.format((v14>0).sum(),len(v14)):>12s} {'{}/{}'.format((v15>0).sum(),len(v15)):>12s}")
print(f"{'Total PnL':<20s} {'${:+,.0f}'.format(v14.sum()):>12s} {'${:+,.0f}'.format(v15.sum()):>12s}")
