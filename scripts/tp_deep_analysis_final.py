#!/usr/bin/env python3
"""
Deep TP/Holding Period Analysis — Final Phase
1. TP=0.5x dominance: is it real or is it just "taking gains too early"?
2. Compare strategies with REALISTIC position count (2-3 trades/week, not all signals)
3. The "missed upside" problem: how much do we leave on the table with TP=0.5x?
4. Hybrid strategy: TP=0.5x with partial exit
5. Trailing stop with tight initial + ratchet
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB = Path("data/trade_history.db")
conn = sqlite3.connect(DB)

signals = pd.read_sql("""
    SELECT s.*,
           b0.open as d0_open, b0.high as d0_high, b0.low as d0_low, b0.close as d0_close,
           b1.open as d1_open, b1.high as d1_high, b1.low as d1_low, b1.close as d1_close,
           b2.open as d2_open, b2.high as d2_high, b2.low as d2_low, b2.close as d2_close,
           b3.open as d3_open, b3.high as d3_high, b3.low as d3_low, b3.close as d3_close,
           b4.open as d4_open, b4.high as d4_high, b4.low as d4_low, b4.close as d4_close,
           b5.open as d5_open, b5.high as d5_high, b5.low as d5_low, b5.close as d5_close
    FROM backfill_signal_outcomes s
    JOIN signal_daily_bars b0 ON s.scan_date=b0.scan_date AND s.symbol=b0.symbol AND b0.day_offset=0
    JOIN signal_daily_bars b1 ON s.scan_date=b1.scan_date AND s.symbol=b1.symbol AND b1.day_offset=1
    JOIN signal_daily_bars b2 ON s.scan_date=b2.scan_date AND s.symbol=b2.symbol AND b2.day_offset=2
    JOIN signal_daily_bars b3 ON s.scan_date=b3.scan_date AND s.symbol=b3.symbol AND b3.day_offset=3
    JOIN signal_daily_bars b4 ON s.scan_date=b4.scan_date AND s.symbol=b4.symbol AND b4.day_offset=4
    JOIN signal_daily_bars b5 ON s.scan_date=b5.scan_date AND s.symbol=b5.symbol AND b5.day_offset=5
""", conn)

print(f"Loaded {len(signals)} signals")
signals['entry'] = signals['scan_price']
signals['atr_dollar'] = signals['entry'] * signals['atr_pct'] / 100.0

def simulate_exit_vec(df, tp_ratio, hold_days):
    entry = df['entry'].values
    atr = df['atr_dollar'].values
    tp = entry + atr * tp_ratio
    sl = entry - atr * 1.0
    returns = np.zeros(len(df))
    exited = np.zeros(len(df), dtype=bool)
    for d in range(min(hold_days + 1, 6)):
        h = df[f'd{d}_high'].values
        l = df[f'd{d}_low'].values
        s = (l <= sl) & ~exited
        returns[s] = (sl[s] - entry[s]) / entry[s] * 100
        exited[s] = True
        t = (h >= tp) & ~exited
        returns[t] = (tp[t] - entry[t]) / entry[t] * 100
        exited[t] = True
    ne = ~exited
    c = f'd{min(hold_days, 5)}_close'
    returns[ne] = (df[c].values[ne] - entry[ne]) / entry[ne] * 100
    return returns

# ============================================================
# ANALYSIS 1: TP=0.5x — the "missed upside" problem
# ============================================================
print("\n" + "=" * 80)
print("ANALYSIS 1: TP=0.5x MISSED UPSIDE")
print("=" * 80)

# When TP=0.5x hits on D0, what would have happened if we held to D3?
entry = signals['entry'].values
atr = signals['atr_dollar'].values
tp05 = entry + atr * 0.5
sl = entry - atr

# Find signals where TP=0.5x hits on D0
tp_hit_d0 = signals['d0_high'].values >= tp05
sl_hit_d0 = signals['d0_low'].values <= sl

# TP hit on D0, SL didn't hit
tp_only_d0 = tp_hit_d0 & ~sl_hit_d0
sub = signals[tp_only_d0]
print(f"\nSignals where TP=0.5x hit on D0 (no SL): {len(sub):,} ({len(sub)/len(signals)*100:.1f}%)")
print(f"  If we took TP=0.5x: avg return = +{(atr[tp_only_d0]*0.5/entry[tp_only_d0]*100).mean():.3f}%")
print(f"  If we held to D1 close: avg return = {sub['outcome_1d'].mean():+.3f}%")
print(f"  If we held to D2 close: avg return = {sub['outcome_2d'].mean():+.3f}%")
print(f"  If we held to D3 close: avg return = {sub['outcome_3d'].mean():+.3f}%")
print(f"  Max gain D0-D5: avg = +{sub['outcome_max_gain_5d'].mean():.3f}%")
print(f"  Max DD D0-D5: avg = {sub['outcome_max_dd_5d'].mean():.3f}%")

# Among these, what % would have reached TP=1.5x by D5?
reached_15x = sub['outcome_max_gain_5d'].values >= (atr[tp_only_d0] * 1.5 / entry[tp_only_d0] * 100)
reached_20x = sub['outcome_max_gain_5d'].values >= (atr[tp_only_d0] * 2.0 / entry[tp_only_d0] * 100)
print(f"  Of these, {reached_15x.mean()*100:.1f}% would reach TP=1.5x by D5")
print(f"  Of these, {reached_20x.mean()*100:.1f}% would reach TP=2.0x by D5")

# ============================================================
# ANALYSIS 2: "Ratchet" trailing — TP=0.5x triggers tighter trail
# ============================================================
print("\n" + "=" * 80)
print("ANALYSIS 2: RATCHET TRAILING STOP")
print("=" * 80)
print("Logic: SL=1x ATR initially. Once gain reaches 0.5x ATR, tighten trail to 0.3x ATR from peak.")

for initial_sl_mult in [1.0]:
    for ratchet_trigger in [0.3, 0.5, 0.75]:
        for trail_after in [0.2, 0.3, 0.5]:
            entry = signals['entry'].values
            atr = signals['atr_dollar'].values
            sl = entry - atr * initial_sl_mult
            highest = entry.copy()
            ratcheted = np.zeros(len(signals), dtype=bool)
            returns = np.zeros(len(signals))
            exited = np.zeros(len(signals), dtype=bool)

            for d in range(6):
                h = signals[f'd{d}_high'].values
                l = signals[f'd{d}_low'].values

                # Update highest
                highest = np.maximum(highest, h)

                # Check ratchet trigger
                gain = (highest - entry) / atr
                newly_ratcheted = (gain >= ratchet_trigger) & ~ratcheted
                ratcheted |= newly_ratcheted

                # Update SL: ratcheted stocks get tight trail
                tight_sl = highest - atr * trail_after
                sl = np.where(ratcheted, np.maximum(sl, tight_sl), sl)

                # Check SL
                sl_hit = (l <= sl) & ~exited
                returns[sl_hit] = (sl[sl_hit] - entry[sl_hit]) / entry[sl_hit] * 100
                exited[sl_hit] = True

            # Time exit at D3 close
            ne = ~exited
            returns[ne] = (signals['d3_close'].values[ne] - entry[ne]) / entry[ne] * 100

            wr = (returns > 0).mean() * 100
            avg_r = returns.mean()
            monthly = avg_r / 100 * 1250 * len(signals) / 48
            ratcheted_pct = ratcheted.mean() * 100
            print(f"  Trigger={ratchet_trigger}x, Trail={trail_after}x: WR={wr:.1f}%, AvgR={avg_r:+.4f}%, ~${monthly:+.0f}/mo, ratcheted={ratcheted_pct:.0f}%")

# ============================================================
# ANALYSIS 3: Compare on FILTERED signals (Discovery-like top selection)
# ============================================================
print("\n" + "=" * 80)
print("ANALYSIS 3: FILTERED SIGNALS (TOP QUALITY ONLY)")
print("=" * 80)

# Simulate Discovery filter: near high, reasonable ATR, moderate dip
filtered = signals[
    (signals['distance_from_20d_high'] > -8) &
    (signals['atr_pct'] < 5) &
    (signals['atr_pct'] > 1) &
    (signals['momentum_5d'] < 2) &
    (signals['volume_ratio'] > 0.3) &
    (signals['volume_ratio'] < 2.0)
]
print(f"Filtered signals: {len(filtered):,} ({len(filtered)/len(signals)*100:.0f}%)")

strategies = [
    ("TP=0.5x, D3", 0.5, 3),
    ("TP=1.0x, D3", 1.0, 3),
    ("TP=1.5x, D3", 1.5, 3),
    ("TP=0.5x, D5", 0.5, 5),
    ("TP=1.0x, D5", 1.0, 5),
]

for name, tp_r, hd in strategies:
    r = simulate_exit_vec(filtered, tp_r, hd)
    wr = (r > 0).mean() * 100
    avg_r = r.mean()
    monthly = avg_r / 100 * 1250 * len(filtered) / 48
    print(f"  {name:20s}: WR={wr:.1f}%, AvgR={avg_r:+.4f}%, ~${monthly:+.0f}/mo")

# Ratchet on filtered
print("\n  Ratchet strategies on filtered:")
for ratchet_trigger, trail_after in [(0.5, 0.3), (0.3, 0.2)]:
    entry = filtered['entry'].values
    atr = filtered['atr_dollar'].values
    sl = entry - atr
    highest = entry.copy()
    ratcheted = np.zeros(len(filtered), dtype=bool)
    returns = np.zeros(len(filtered))
    exited = np.zeros(len(filtered), dtype=bool)

    for d in range(6):
        h = filtered[f'd{d}_high'].values
        l = filtered[f'd{d}_low'].values
        highest = np.maximum(highest, h)
        gain = (highest - entry) / atr
        ratcheted |= (gain >= ratchet_trigger)
        tight_sl = highest - atr * trail_after
        sl = np.where(ratcheted, np.maximum(sl, tight_sl), sl)
        sl_hit = (l <= sl) & ~exited
        returns[sl_hit] = (sl[sl_hit] - entry[sl_hit]) / entry[sl_hit] * 100
        exited[sl_hit] = True

    ne = ~exited
    returns[ne] = (filtered['d3_close'].values[ne] - entry[ne]) / entry[ne] * 100
    wr = (returns > 0).mean() * 100
    avg_r = returns.mean()
    monthly = avg_r / 100 * 1250 * len(filtered) / 48
    print(f"    Ratchet({ratchet_trigger}x→{trail_after}x trail): WR={wr:.1f}%, AvgR={avg_r:+.4f}%, ~${monthly:+.0f}/mo")

# ============================================================
# ANALYSIS 4: Walk-forward comparison of top 3 strategies
# ============================================================
print("\n" + "=" * 80)
print("ANALYSIS 4: WALK-FORWARD YEAR-BY-YEAR STABILITY")
print("=" * 80)

signals['year'] = pd.to_datetime(signals['scan_date']).dt.year

for yr in sorted(signals['year'].unique()):
    yrdata = signals[signals['year'] == yr]
    n = len(yrdata)

    r_05_d3 = simulate_exit_vec(yrdata, 0.5, 3)
    r_10_d3 = simulate_exit_vec(yrdata, 1.0, 3)

    # Ratchet 0.5x → 0.3x trail
    entry = yrdata['entry'].values
    atr = yrdata['atr_dollar'].values
    sl = entry - atr
    highest = entry.copy()
    ratcheted = np.zeros(n, dtype=bool)
    r_ratchet = np.zeros(n)
    exited = np.zeros(n, dtype=bool)
    for d in range(6):
        h = yrdata[f'd{d}_high'].values
        l = yrdata[f'd{d}_low'].values
        highest = np.maximum(highest, h)
        gain = (highest - entry) / atr
        ratcheted |= (gain >= 0.5)
        tight_sl = highest - atr * 0.3
        sl = np.where(ratcheted, np.maximum(sl, tight_sl), sl)
        sl_hit = (l <= sl) & ~exited
        r_ratchet[sl_hit] = (sl[sl_hit] - entry[sl_hit]) / entry[sl_hit] * 100
        exited[sl_hit] = True
    ne = ~exited
    r_ratchet[ne] = (yrdata['d3_close'].values[ne] - entry[ne]) / entry[ne] * 100

    print(f"\n{yr} (n={n:,}):")
    print(f"  TP=0.5x D3: WR={(r_05_d3>0).mean()*100:.1f}%, AvgR={r_05_d3.mean():+.4f}%")
    print(f"  TP=1.0x D3: WR={(r_10_d3>0).mean()*100:.1f}%, AvgR={r_10_d3.mean():+.4f}%")
    print(f"  Ratchet:    WR={(r_ratchet>0).mean()*100:.1f}%, AvgR={r_ratchet.mean():+.4f}%")

# ============================================================
# ANALYSIS 5: E[R] per trade in dollars (realistic position size)
# ============================================================
print("\n" + "=" * 80)
print("ANALYSIS 5: REALISTIC $ PER TRADE COMPARISON")
print("=" * 80)
print("Position size: $1,250 per trade (per discovery slot)")
print("Trades: ~2/day average from discovery = ~40/month")

position = 1250

for name, tp_r, hd in [("TP=0.5x D3", 0.5, 3), ("TP=1.0x D3", 1.0, 3), ("TP=1.5x D3", 1.5, 3)]:
    r = simulate_exit_vec(signals, tp_r, hd)
    avg_per_trade = r.mean() / 100 * position
    monthly_40 = avg_per_trade * 40
    yearly = monthly_40 * 12
    print(f"  {name:20s}: ${avg_per_trade:+.2f}/trade, ${monthly_40:+.0f}/mo, ${yearly:+.0f}/yr")

# Ratchet
entry = signals['entry'].values
atr = signals['atr_dollar'].values
sl = entry - atr
highest = entry.copy()
ratcheted = np.zeros(len(signals), dtype=bool)
r_ratchet = np.zeros(len(signals))
exited = np.zeros(len(signals), dtype=bool)
for d in range(6):
    h = signals[f'd{d}_high'].values
    l = signals[f'd{d}_low'].values
    highest = np.maximum(highest, h)
    gain = (highest - entry) / atr
    ratcheted |= (gain >= 0.5)
    tight_sl = highest - atr * 0.3
    sl = np.where(ratcheted, np.maximum(sl, tight_sl), sl)
    sl_hit = (l <= sl) & ~exited
    r_ratchet[sl_hit] = (sl[sl_hit] - entry[sl_hit]) / entry[sl_hit] * 100
    exited[sl_hit] = True
ne = ~exited
r_ratchet[ne] = (signals['d3_close'].values[ne] - entry[ne]) / entry[ne] * 100

avg_per_trade = r_ratchet.mean() / 100 * position
monthly_40 = avg_per_trade * 40
yearly = monthly_40 * 12
print(f"  {'Ratchet(0.5→0.3)':20s}: ${avg_per_trade:+.2f}/trade, ${monthly_40:+.0f}/mo, ${yearly:+.0f}/yr")

# Tight ratchet
sl = entry - atr
highest = entry.copy()
ratcheted = np.zeros(len(signals), dtype=bool)
r_ratchet2 = np.zeros(len(signals))
exited = np.zeros(len(signals), dtype=bool)
for d in range(6):
    h = signals[f'd{d}_high'].values
    l = signals[f'd{d}_low'].values
    highest = np.maximum(highest, h)
    gain = (highest - entry) / atr
    ratcheted |= (gain >= 0.3)
    tight_sl = highest - atr * 0.2
    sl = np.where(ratcheted, np.maximum(sl, tight_sl), sl)
    sl_hit = (l <= sl) & ~exited
    r_ratchet2[sl_hit] = (sl[sl_hit] - entry[sl_hit]) / entry[sl_hit] * 100
    exited[sl_hit] = True
ne = ~exited
r_ratchet2[ne] = (signals['d3_close'].values[ne] - entry[ne]) / entry[ne] * 100

avg_per_trade = r_ratchet2.mean() / 100 * position
monthly_40 = avg_per_trade * 40
yearly = monthly_40 * 12
print(f"  {'Ratchet(0.3→0.2)':20s}: ${avg_per_trade:+.2f}/trade, ${monthly_40:+.0f}/mo, ${yearly:+.0f}/yr")

# ============================================================
# ANALYSIS 6: The prediction question — can D0 intraday predict hold time?
# ============================================================
print("\n" + "=" * 80)
print("ANALYSIS 6: D0 CLOSE POSITION → OPTIMAL HOLD")
print("=" * 80)

# D0 close position in range: close near high → momentum, close near low → reversal needed
signals['d0_close_pos'] = (signals['d0_close'] - signals['d0_low']) / (signals['d0_high'] - signals['d0_low'] + 1e-8)

for q_label, q_lo, q_hi in [('D0 close near LOW (0-0.25)', 0, 0.25),
                              ('D0 close mid-low (0.25-0.5)', 0.25, 0.5),
                              ('D0 close mid-high (0.5-0.75)', 0.5, 0.75),
                              ('D0 close near HIGH (0.75-1)', 0.75, 1.01)]:
    sub = signals[(signals['d0_close_pos'] >= q_lo) & (signals['d0_close_pos'] < q_hi)]
    print(f"\n{q_label} (n={len(sub):,}):")
    for name, tp_r, hd in [("TP=0.5x D1", 0.5, 1), ("TP=0.5x D3", 0.5, 3), ("TP=1.0x D3", 1.0, 3)]:
        r = simulate_exit_vec(sub, tp_r, hd)
        wr = (r > 0).mean() * 100
        avg_r = r.mean()
        print(f"    {name:18s}: WR={wr:.1f}%, AvgR={avg_r:+.4f}%")

# ============================================================
# ANALYSIS 7: Summary statistics for final recommendation
# ============================================================
print("\n" + "=" * 80)
print("ANALYSIS 7: FINAL STRATEGY COMPARISON SUMMARY")
print("=" * 80)

strategies_final = {
    "TP=0.5x D3 (tight TP)": simulate_exit_vec(signals, 0.5, 3),
    "TP=1.0x D3 (current)": simulate_exit_vec(signals, 1.0, 3),
    "TP=1.5x D3": simulate_exit_vec(signals, 1.5, 3),
    "TP=2.0x D3": simulate_exit_vec(signals, 2.0, 3),
    "Ratchet(0.5x→0.3x)": r_ratchet,
    "Ratchet(0.3x→0.2x)": r_ratchet2,
    "No TP, D3 close only": (signals['d3_close'].values - signals['entry'].values) / signals['entry'].values * 100,
}

print(f"\n{'Strategy':30s} {'WR%':>7s} {'AvgR%':>9s} {'MedR%':>9s} {'Std%':>8s} {'Sharpe':>8s} {'p10':>8s} {'p90':>8s}")
print("-" * 100)

for name, returns in strategies_final.items():
    wr = (returns > 0).mean() * 100
    avg = returns.mean()
    med = np.median(returns)
    std = returns.std()
    sharpe = avg / std if std > 0 else 0
    p10 = np.percentile(returns, 10)
    p90 = np.percentile(returns, 90)
    print(f"{name:30s} {wr:7.1f} {avg:+9.4f} {med:+9.4f} {std:8.3f} {sharpe:8.4f} {p10:+8.3f} {p90:+8.3f}")

conn.close()
print("\n\nFinal analysis complete.")
