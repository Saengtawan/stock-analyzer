#!/usr/bin/env python3
"""
Verify ratchet trailing stop results — check for look-ahead bias.
Also check: does the ratchet work on daily bars where we only know OHLC?
Key issue: within a single day, we don't know if high or low came first.
Conservative: if both trigger and SL happen same bar, assume SL first.
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

# ============================================================
# CONSERVATIVE RATCHET: check SL BEFORE updating highest
# ============================================================
print("\n" + "=" * 80)
print("CONSERVATIVE RATCHET (check SL before high update each day)")
print("=" * 80)

for trigger, trail in [(0.3, 0.2), (0.3, 0.3), (0.5, 0.3), (0.5, 0.2)]:
    entry = signals['entry'].values
    atr = signals['atr_dollar'].values
    sl = entry - atr  # initial SL = 1x ATR
    highest = entry.copy()
    ratcheted = np.zeros(len(signals), dtype=bool)
    returns = np.zeros(len(signals))
    exited = np.zeros(len(signals), dtype=bool)
    exit_day = np.full(len(signals), 99)

    for d in range(6):
        h = signals[f'd{d}_high'].values
        l = signals[f'd{d}_low'].values
        o = signals[f'd{d}_open'].values

        # CONSERVATIVE: check SL FIRST using current SL level
        sl_hit = (l <= sl) & ~exited
        returns[sl_hit] = (sl[sl_hit] - entry[sl_hit]) / entry[sl_hit] * 100
        exited[sl_hit] = True
        exit_day[sl_hit] = d

        # THEN update highest and ratchet
        highest = np.where(~exited, np.maximum(highest, h), highest)
        gain = (highest - entry) / atr
        ratcheted |= (gain >= trigger) & ~exited
        tight_sl = highest - atr * trail
        sl = np.where(ratcheted & ~exited, np.maximum(sl, tight_sl), sl)

    # Time exit at D3
    ne = ~exited
    returns[ne] = (signals['d3_close'].values[ne] - entry[ne]) / entry[ne] * 100
    exit_day[ne] = 3

    wr = (returns > 0).mean() * 100
    avg_r = returns.mean()
    monthly = avg_r / 100 * 1250 * len(signals) / 48

    print(f"\nTrigger={trigger}x, Trail={trail}x (CONSERVATIVE):")
    print(f"  WR={wr:.1f}%, AvgR={avg_r:+.4f}%, ~${monthly:+.0f}/mo")
    print(f"  Exit day distribution: ", end="")
    for d in range(6):
        n_d = (exit_day == d).sum()
        print(f"D{d}={n_d:,} ", end="")
    print(f"TimeD3={(exit_day==3).sum() + (exit_day==99).sum():,}")

    # Return distribution
    for pct in [5, 10, 25, 50, 75, 90, 95]:
        print(f"  p{pct}={np.percentile(returns, pct):+.3f}%", end="")
    print()

# ============================================================
# ULTRA-CONSERVATIVE: same-day ratchet+SL assumed SL wins
# ============================================================
print("\n" + "=" * 80)
print("ULTRA-CONSERVATIVE: if trigger and new SL breach same day, SL wins at OLD level")
print("=" * 80)

for trigger, trail in [(0.3, 0.2), (0.5, 0.3)]:
    entry = signals['entry'].values
    atr = signals['atr_dollar'].values
    sl = entry - atr
    highest_prev = entry.copy()  # highest from PREVIOUS day
    ratcheted = np.zeros(len(signals), dtype=bool)
    returns = np.zeros(len(signals))
    exited = np.zeros(len(signals), dtype=bool)

    for d in range(6):
        h = signals[f'd{d}_high'].values
        l = signals[f'd{d}_low'].values

        # SL check uses yesterday's trailing level
        sl_hit = (l <= sl) & ~exited
        returns[sl_hit] = (sl[sl_hit] - entry[sl_hit]) / entry[sl_hit] * 100
        exited[sl_hit] = True

        # Update highest and ratchet AFTER this day
        highest_prev = np.where(~exited, np.maximum(highest_prev, h), highest_prev)
        gain = (highest_prev - entry) / atr
        ratcheted |= (gain >= trigger) & ~exited
        tight_sl = highest_prev - atr * trail
        sl = np.where(ratcheted & ~exited, np.maximum(sl, tight_sl), sl)

    ne = ~exited
    returns[ne] = (signals['d3_close'].values[ne] - entry[ne]) / entry[ne] * 100

    wr = (returns > 0).mean() * 100
    avg_r = returns.mean()
    monthly = avg_r / 100 * 1250 * len(signals) / 48
    print(f"  Trigger={trigger}x, Trail={trail}x (ULTRA-CONSERVATIVE): WR={wr:.1f}%, AvgR={avg_r:+.4f}%, ~${monthly:+.0f}/mo")

# ============================================================
# REALISTIC OPEN-BASED RATCHET: only update trail at next day's open
# ============================================================
print("\n" + "=" * 80)
print("REALISTIC: Trail updates at CLOSE, SL checks at next day's LOW")
print("(We monitor close price → set trailing order for next day)")
print("=" * 80)

for trigger, trail in [(0.3, 0.2), (0.3, 0.3), (0.5, 0.3), (0.5, 0.2)]:
    entry = signals['entry'].values
    atr = signals['atr_dollar'].values
    sl = entry - atr
    highest_close = entry.copy()  # track highest CLOSE (what we actually see)
    ratcheted = np.zeros(len(signals), dtype=bool)
    returns = np.zeros(len(signals))
    exited = np.zeros(len(signals), dtype=bool)

    for d in range(6):
        h = signals[f'd{d}_high'].values
        l = signals[f'd{d}_low'].values
        c = signals[f'd{d}_close'].values

        # SL check at this day's low (using yesterday's trail level)
        sl_hit = (l <= sl) & ~exited
        returns[sl_hit] = (sl[sl_hit] - entry[sl_hit]) / entry[sl_hit] * 100
        exited[sl_hit] = True

        # Update highest close and ratchet at end of day
        highest_close = np.where(~exited, np.maximum(highest_close, c), highest_close)
        gain = (highest_close - entry) / atr
        ratcheted |= (gain >= trigger) & ~exited
        tight_sl = highest_close - atr * trail
        sl = np.where(ratcheted & ~exited, np.maximum(sl, tight_sl), sl)

    ne = ~exited
    returns[ne] = (signals['d3_close'].values[ne] - entry[ne]) / entry[ne] * 100

    wr = (returns > 0).mean() * 100
    avg_r = returns.mean()
    monthly = avg_r / 100 * 1250 * len(signals) / 48
    per_trade = avg_r / 100 * 1250
    print(f"  Trigger={trigger}x, Trail={trail}x: WR={wr:.1f}%, AvgR={avg_r:+.4f}%, ${per_trade:+.2f}/trade, ~${monthly:+.0f}/mo")

# ============================================================
# COMPARISON: all approaches side by side
# ============================================================
print("\n" + "=" * 80)
print("FINAL COMPARISON — ALL APPROACHES")
print("=" * 80)

def run_strategy(df, name, func):
    returns = func(df)
    wr = (returns > 0).mean() * 100
    avg_r = returns.mean()
    sharpe = avg_r / returns.std() if returns.std() > 0 else 0
    per_trade = avg_r / 100 * 1250
    monthly = per_trade * 40  # ~40 trades/mo
    print(f"  {name:45s} WR={wr:5.1f}%  AvgR={avg_r:+.4f}%  Sharpe={sharpe:.4f}  ${per_trade:+.2f}/trade  ~${monthly:+.0f}/mo")

def tp_sl_strategy(df, tp_r, hd):
    entry = df['entry'].values
    atr = df['atr_dollar'].values
    tp = entry + atr * tp_r
    sl = entry - atr
    returns = np.zeros(len(df))
    exited = np.zeros(len(df), dtype=bool)
    for d in range(min(hd+1, 6)):
        h = df[f'd{d}_high'].values; l = df[f'd{d}_low'].values
        s = (l <= sl) & ~exited; returns[s] = (sl[s]-entry[s])/entry[s]*100; exited[s] = True
        t = (h >= tp) & ~exited; returns[t] = (tp[t]-entry[t])/entry[t]*100; exited[t] = True
    ne = ~exited; c = f'd{min(hd,5)}_close'; returns[ne] = (df[c].values[ne]-entry[ne])/entry[ne]*100
    return returns

def close_ratchet(df, trigger, trail):
    entry = df['entry'].values
    atr = df['atr_dollar'].values
    sl = entry - atr
    highest_close = entry.copy()
    ratcheted = np.zeros(len(df), dtype=bool)
    returns = np.zeros(len(df))
    exited = np.zeros(len(df), dtype=bool)
    for d in range(6):
        h = df[f'd{d}_high'].values; l = df[f'd{d}_low'].values; c = df[f'd{d}_close'].values
        s = (l <= sl) & ~exited; returns[s] = (sl[s]-entry[s])/entry[s]*100; exited[s] = True
        highest_close = np.where(~exited, np.maximum(highest_close, c), highest_close)
        gain = (highest_close-entry)/atr
        ratcheted |= (gain >= trigger) & ~exited
        tight = highest_close - atr * trail
        sl = np.where(ratcheted & ~exited, np.maximum(sl, tight), sl)
    ne = ~exited; returns[ne] = (df['d3_close'].values[ne]-entry[ne])/entry[ne]*100
    return returns

run_strategy(signals, "TP=0.5x D3", lambda df: tp_sl_strategy(df, 0.5, 3))
run_strategy(signals, "TP=1.0x D3 (CURRENT)", lambda df: tp_sl_strategy(df, 1.0, 3))
run_strategy(signals, "TP=1.5x D5", lambda df: tp_sl_strategy(df, 1.5, 5))
run_strategy(signals, "D3 close only (no TP)", lambda df: (df['d3_close'].values - df['entry'].values) / df['entry'].values * 100)
run_strategy(signals, "Ratchet CLOSE 0.3x→0.2x trail, D3 exit", lambda df: close_ratchet(df, 0.3, 0.2))
run_strategy(signals, "Ratchet CLOSE 0.5x→0.3x trail, D3 exit", lambda df: close_ratchet(df, 0.5, 0.3))
run_strategy(signals, "Ratchet CLOSE 0.3x→0.3x trail, D3 exit", lambda df: close_ratchet(df, 0.3, 0.3))

conn.close()
