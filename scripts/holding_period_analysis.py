#!/usr/bin/env python3
"""Comprehensive holding period analysis on backfill_signal_outcomes (5,850 rows)."""

import sqlite3
import numpy as np
from collections import defaultdict

DB = "data/trade_history.db"

def load_data():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM backfill_signal_outcomes").fetchall()
    conn.close()
    data = []
    for r in rows:
        data.append(dict(r))
    return data

def wr(vals):
    """Win rate: % of values > 0."""
    if not vals:
        return 0.0
    return 100.0 * sum(1 for v in vals if v > 0) / len(vals)

def avg(vals):
    if not vals:
        return 0.0
    return np.mean(vals)

def med(vals):
    if not vals:
        return 0.0
    return np.median(vals)

def p25(vals):
    if not vals:
        return 0.0
    return np.percentile(vals, 25)

def p75(vals):
    if not vals:
        return 0.0
    return np.percentile(vals, 75)

def cap_return(ret, tp=3.0, sl=-2.5):
    """Cap return at TP/SL."""
    return max(sl, min(tp, ret))

def section(title):
    print("\n" + "=" * 90)
    print(f"  {title}")
    print("=" * 90)

def subsection(title):
    print(f"\n--- {title} ---")

# ─────────────────────────────────────────────────────────
def main():
    data = load_data()
    N = len(data)
    print(f"Loaded {N} rows from backfill_signal_outcomes")

    days = ["outcome_1d", "outcome_2d", "outcome_3d", "outcome_4d", "outcome_5d"]
    day_labels = ["D1", "D2", "D3", "D4", "D5"]

    # =====================================================================
    # 1. RETURN PATH BY HOLDING PERIOD
    # =====================================================================
    section("1. RETURN PATH BY HOLDING PERIOD")

    print(f"\n{'Day':<6} {'N':>6} {'Avg%':>8} {'Med%':>8} {'P25%':>8} {'P75%':>8} {'WR%':>7} {'StdDev':>8}")
    print("-" * 65)
    prev_avg = 0.0
    for i, (col, label) in enumerate(zip(days, day_labels)):
        vals = [d[col] for d in data]
        a = avg(vals)
        print(f"{label:<6} {len(vals):>6} {a:>+8.3f} {med(vals):>+8.3f} {p25(vals):>+8.3f} {p75(vals):>+8.3f} {wr(vals):>7.1f} {np.std(vals):>8.3f}")
        prev_avg = a

    subsection("Marginal return each day (Day N avg - Day N-1 avg)")
    avgs = [avg([d[col] for d in data]) for col in days]
    print(f"{'Transition':<12} {'Marginal%':>10} {'Cumulative%':>12}")
    print("-" * 36)
    print(f"{'D0->D1':<12} {avgs[0]:>+10.3f} {avgs[0]:>+12.3f}")
    for i in range(1, len(avgs)):
        marginal = avgs[i] - avgs[i-1]
        print(f"D{i}->D{i+1}  {marginal:>+10.3f} {avgs[i]:>+12.3f}")

    peak_idx = np.argmax(avgs)
    print(f"\n>> Average return PEAKS at D{peak_idx+1} = {avgs[peak_idx]:+.3f}%")
    print(f"   After peak, returns {'decline' if avgs[-1] < avgs[peak_idx] else 'continue rising'} to D5 = {avgs[-1]:+.3f}%")

    # =====================================================================
    # 2. DAY-1 AS EARLY EXIT SIGNAL
    # =====================================================================
    section("2. DAY-1 AS EARLY EXIT SIGNAL")

    subsection("D1 > 0 vs D1 <= 0 split")
    d1_pos = [d for d in data if d["outcome_1d"] > 0]
    d1_neg = [d for d in data if d["outcome_1d"] <= 0]

    print(f"\n{'Group':<12} {'N':>6} {'D1 Avg':>8} {'D2 Avg':>8} {'D3 Avg':>8} {'D4 Avg':>8} {'D5 Avg':>8}")
    print("-" * 60)
    for label, grp in [("D1 > 0", d1_pos), ("D1 <= 0", d1_neg)]:
        vals = {col: [d[col] for d in grp] for col in days}
        row = f"{label:<12} {len(grp):>6}"
        for col in days:
            row += f" {avg(vals[col]):>+8.3f}"
        print(row)

    print(f"\n{'Group':<12} {'N':>6} {'D1 WR':>8} {'D2 WR':>8} {'D3 WR':>8} {'D4 WR':>8} {'D5 WR':>8}")
    print("-" * 60)
    for label, grp in [("D1 > 0", d1_pos), ("D1 <= 0", d1_neg)]:
        vals = {col: [d[col] for d in grp] for col in days}
        row = f"{label:<12} {len(grp):>6}"
        for col in days:
            row += f" {wr(vals[col]):>8.1f}"
        print(row)

    subsection("D1 bucket analysis (detailed)")
    buckets = [
        ("<-3%",    lambda d: d["outcome_1d"] < -3.0),
        ("-3 to -1%", lambda d: -3.0 <= d["outcome_1d"] < -1.0),
        ("-1 to 0%",  lambda d: -1.0 <= d["outcome_1d"] <= 0.0),
        ("0 to 1%",   lambda d: 0.0 < d["outcome_1d"] <= 1.0),
        ("1 to 3%",   lambda d: 1.0 < d["outcome_1d"] <= 3.0),
        (">3%",       lambda d: d["outcome_1d"] > 3.0),
    ]

    print(f"\n{'Bucket':<14} {'N':>6} {'D1 Avg':>8} {'D2 Avg':>8} {'D3 Avg':>8} {'D4 Avg':>8} {'D5 Avg':>8} {'MFE Avg':>8} {'MAE Avg':>8}")
    print("-" * 90)
    for label, filt in buckets:
        grp = [d for d in data if filt(d)]
        if not grp:
            continue
        row = f"{label:<14} {len(grp):>6}"
        for col in days:
            row += f" {avg([d[col] for d in grp]):>+8.3f}"
        row += f" {avg([d['outcome_max_gain_5d'] for d in grp]):>+8.3f}"
        row += f" {avg([d['outcome_max_dd_5d'] for d in grp]):>+8.3f}"
        print(row)

    print(f"\n{'Bucket':<14} {'N':>6} {'D1 WR':>8} {'D2 WR':>8} {'D3 WR':>8} {'D4 WR':>8} {'D5 WR':>8}")
    print("-" * 65)
    for label, filt in buckets:
        grp = [d for d in data if filt(d)]
        if not grp:
            continue
        row = f"{label:<14} {len(grp):>6}"
        for col in days:
            row += f" {wr([d[col] for d in grp]):>8.1f}"
        print(row)

    subsection("Optimal D1 cutoff for early exit (scan -5% to +3%)")
    print(f"\n{'Cutoff':<10} {'Exit N':>7} {'Exit Avg':>9} {'Hold N':>7} {'Hold D5':>9} {'Blend Avg':>10} {'Blend WR':>9}")
    print("-" * 68)
    for cutoff in np.arange(-5.0, 3.5, 0.5):
        exit_grp = [d for d in data if d["outcome_1d"] < cutoff]
        hold_grp = [d for d in data if d["outcome_1d"] >= cutoff]
        if not exit_grp or not hold_grp:
            continue
        exit_returns = [d["outcome_1d"] for d in exit_grp]
        hold_returns = [d["outcome_5d"] for d in hold_grp]
        blend = exit_returns + hold_returns
        print(f"{cutoff:>+8.1f}%  {len(exit_grp):>7} {avg(exit_returns):>+9.3f} {len(hold_grp):>7} {avg(hold_returns):>+9.3f} {avg(blend):>+10.3f} {wr(blend):>9.1f}")

    # =====================================================================
    # 3. BY VIX REGIME
    # =====================================================================
    section("3. BY VIX REGIME")

    vix_regimes = [
        ("LOW (<20)",  lambda d: d["vix_at_signal"] < 20),
        ("MED (20-25)", lambda d: 20 <= d["vix_at_signal"] <= 25),
        ("HIGH (>25)",  lambda d: d["vix_at_signal"] > 25),
    ]

    print(f"\n{'Regime':<14} {'N':>6} {'D1 Avg':>8} {'D2 Avg':>8} {'D3 Avg':>8} {'D4 Avg':>8} {'D5 Avg':>8} {'MFE':>8} {'MAE':>8}")
    print("-" * 85)
    for label, filt in vix_regimes:
        grp = [d for d in data if filt(d)]
        row = f"{label:<14} {len(grp):>6}"
        for col in days:
            row += f" {avg([d[col] for d in grp]):>+8.3f}"
        row += f" {avg([d['outcome_max_gain_5d'] for d in grp]):>+8.3f}"
        row += f" {avg([d['outcome_max_dd_5d'] for d in grp]):>+8.3f}"
        print(row)

    print(f"\n{'Regime':<14} {'N':>6} {'D1 WR':>8} {'D2 WR':>8} {'D3 WR':>8} {'D4 WR':>8} {'D5 WR':>8}")
    print("-" * 58)
    for label, filt in vix_regimes:
        grp = [d for d in data if filt(d)]
        row = f"{label:<14} {len(grp):>6}"
        for col in days:
            row += f" {wr([d[col] for d in grp]):>8.1f}"
        print(row)

    subsection("Optimal holding period per VIX regime")
    for label, filt in vix_regimes:
        grp = [d for d in data if filt(d)]
        avgs_v = [avg([d[col] for d in grp]) for col in days]
        peak = np.argmax(avgs_v)
        print(f"  {label}: peaks at D{peak+1} = {avgs_v[peak]:+.3f}%, D5 = {avgs_v[-1]:+.3f}%")

    # =====================================================================
    # 4. BY ATR BUCKET
    # =====================================================================
    section("4. BY ATR BUCKET")

    atr_buckets = [
        ("ATR <2.5%",   lambda d: d["atr_pct"] < 2.5),
        ("ATR 2.5-4%",  lambda d: 2.5 <= d["atr_pct"] < 4.0),
        ("ATR 4-6%",    lambda d: 4.0 <= d["atr_pct"] < 6.0),
        ("ATR >=6%",    lambda d: d["atr_pct"] >= 6.0),
    ]

    print(f"\n{'Bucket':<14} {'N':>6} {'D1 Avg':>8} {'D2 Avg':>8} {'D3 Avg':>8} {'D4 Avg':>8} {'D5 Avg':>8} {'MFE':>8} {'MAE':>8}")
    print("-" * 85)
    for label, filt in atr_buckets:
        grp = [d for d in data if filt(d)]
        if not grp:
            continue
        row = f"{label:<14} {len(grp):>6}"
        for col in days:
            row += f" {avg([d[col] for d in grp]):>+8.3f}"
        row += f" {avg([d['outcome_max_gain_5d'] for d in grp]):>+8.3f}"
        row += f" {avg([d['outcome_max_dd_5d'] for d in grp]):>+8.3f}"
        print(row)

    print(f"\n{'Bucket':<14} {'N':>6} {'D1 WR':>8} {'D2 WR':>8} {'D3 WR':>8} {'D4 WR':>8} {'D5 WR':>8}")
    print("-" * 58)
    for label, filt in atr_buckets:
        grp = [d for d in data if filt(d)]
        if not grp:
            continue
        row = f"{label:<14} {len(grp):>6}"
        for col in days:
            row += f" {wr([d[col] for d in grp]):>8.1f}"
        print(row)

    subsection("Optimal holding period per ATR bucket")
    for label, filt in atr_buckets:
        grp = [d for d in data if filt(d)]
        if not grp:
            continue
        avgs_a = [avg([d[col] for d in grp]) for col in days]
        peak = np.argmax(avgs_a)
        print(f"  {label}: peaks at D{peak+1} = {avgs_a[peak]:+.3f}%, D5 = {avgs_a[-1]:+.3f}%")

    subsection("ATR x D1 direction cross (high-ATR losers vs low-ATR winners)")
    for atr_label, atr_filt in atr_buckets:
        grp = [d for d in data if atr_filt(d)]
        if not grp:
            continue
        d1_up = [d for d in grp if d["outcome_1d"] > 0]
        d1_dn = [d for d in grp if d["outcome_1d"] <= 0]
        print(f"  {atr_label}:  D1>0 n={len(d1_up)} D5avg={avg([d['outcome_5d'] for d in d1_up]):+.3f}%  |  "
              f"D1<=0 n={len(d1_dn)} D5avg={avg([d['outcome_5d'] for d in d1_dn]):+.3f}%")

    # =====================================================================
    # 5. BY SECTOR (top 5)
    # =====================================================================
    section("5. BY SECTOR (top 5 by count)")

    sector_counts = defaultdict(int)
    for d in data:
        sector_counts[d["sector"]] += 1
    top5 = sorted(sector_counts, key=sector_counts.get, reverse=True)[:5]

    print(f"\n{'Sector':<22} {'N':>6} {'D1 Avg':>8} {'D2 Avg':>8} {'D3 Avg':>8} {'D4 Avg':>8} {'D5 Avg':>8}")
    print("-" * 72)
    for sec in top5:
        grp = [d for d in data if d["sector"] == sec]
        row = f"{sec:<22} {len(grp):>6}"
        for col in days:
            row += f" {avg([d[col] for d in grp]):>+8.3f}"
        print(row)

    print(f"\n{'Sector':<22} {'N':>6} {'D1 WR':>8} {'D2 WR':>8} {'D3 WR':>8} {'D4 WR':>8} {'D5 WR':>8}")
    print("-" * 68)
    for sec in top5:
        grp = [d for d in data if d["sector"] == sec]
        row = f"{sec:<22} {len(grp):>6}"
        for col in days:
            row += f" {wr([d[col] for d in grp]):>8.1f}"
        print(row)

    subsection("Optimal holding period per sector")
    for sec in top5:
        grp = [d for d in data if d["sector"] == sec]
        avgs_s = [avg([d[col] for d in grp]) for col in days]
        peak = np.argmax(avgs_s)
        print(f"  {sec:<22}: peaks at D{peak+1} = {avgs_s[peak]:+.3f}%, D5 = {avgs_s[-1]:+.3f}%")

    # =====================================================================
    # 6. MFE/MAE COMBINED WITH DAILY PATH
    # =====================================================================
    section("6. MFE/MAE ANALYSIS COMBINED WITH DAILY PATH")

    subsection("Stocks that hit MFE >= 3% at some point during 5-day window")
    mfe_high = [d for d in data if d["outcome_max_gain_5d"] >= 3.0]
    mfe_low  = [d for d in data if d["outcome_max_gain_5d"] < 3.0]
    print(f"  MFE >= 3%: n={len(mfe_high)}  ({100*len(mfe_high)/N:.1f}% of all)")
    print(f"  MFE <  3%: n={len(mfe_low)}   ({100*len(mfe_low)/N:.1f}% of all)")

    print(f"\n{'Group':<16} {'N':>6} {'D1 Avg':>8} {'D2 Avg':>8} {'D3 Avg':>8} {'D4 Avg':>8} {'D5 Avg':>8} {'MFE':>8} {'MAE':>8}")
    print("-" * 85)
    for label, grp in [("MFE >= 3%", mfe_high), ("MFE < 3%", mfe_low)]:
        row = f"{label:<16} {len(grp):>6}"
        for col in days:
            row += f" {avg([d[col] for d in grp]):>+8.3f}"
        row += f" {avg([d['outcome_max_gain_5d'] for d in grp]):>+8.3f}"
        row += f" {avg([d['outcome_max_dd_5d'] for d in grp]):>+8.3f}"
        print(row)

    print(f"\n  D1 distribution for MFE >= 3% group:")
    print(f"    D1 > 0:  {sum(1 for d in mfe_high if d['outcome_1d'] > 0)} ({100*sum(1 for d in mfe_high if d['outcome_1d'] > 0)/len(mfe_high):.1f}%)")
    print(f"    D1 > 1%: {sum(1 for d in mfe_high if d['outcome_1d'] > 1)} ({100*sum(1 for d in mfe_high if d['outcome_1d'] > 1)/len(mfe_high):.1f}%)")
    print(f"    D1 > 2%: {sum(1 for d in mfe_high if d['outcome_1d'] > 2)} ({100*sum(1 for d in mfe_high if d['outcome_1d'] > 2)/len(mfe_high):.1f}%)")

    subsection("Stocks with MAE <= -3% (deep drawdown) at some point during 5-day window")
    mae_deep = [d for d in data if d["outcome_max_dd_5d"] <= -3.0]
    mae_ok   = [d for d in data if d["outcome_max_dd_5d"] > -3.0]
    print(f"  MAE <= -3%: n={len(mae_deep)}  ({100*len(mae_deep)/N:.1f}% of all)")
    print(f"  MAE >  -3%: n={len(mae_ok)}    ({100*len(mae_ok)/N:.1f}% of all)")

    print(f"\n{'Group':<16} {'N':>6} {'D1 Avg':>8} {'D2 Avg':>8} {'D3 Avg':>8} {'D4 Avg':>8} {'D5 Avg':>8}")
    print("-" * 66)
    for label, grp in [("MAE <= -3%", mae_deep), ("MAE > -3%", mae_ok)]:
        row = f"{label:<16} {len(grp):>6}"
        for col in days:
            row += f" {avg([d[col] for d in grp]):>+8.3f}"
        print(row)

    print(f"\n  D1 distribution for MAE <= -3% group:")
    print(f"    D1 < 0:   {sum(1 for d in mae_deep if d['outcome_1d'] < 0)} ({100*sum(1 for d in mae_deep if d['outcome_1d'] < 0)/len(mae_deep):.1f}%)")
    print(f"    D1 < -1%: {sum(1 for d in mae_deep if d['outcome_1d'] < -1)} ({100*sum(1 for d in mae_deep if d['outcome_1d'] < -1)/len(mae_deep):.1f}%)")
    print(f"    D1 < -2%: {sum(1 for d in mae_deep if d['outcome_1d'] < -2)} ({100*sum(1 for d in mae_deep if d['outcome_1d'] < -2)/len(mae_deep):.1f}%)")

    subsection("Can we detect winners/losers from D1?")
    # Big winners = D5 >= 3%, Big losers = D5 <= -3%
    winners = [d for d in data if d["outcome_5d"] >= 3.0]
    losers  = [d for d in data if d["outcome_5d"] <= -3.0]
    middle  = [d for d in data if -3.0 < d["outcome_5d"] < 3.0]

    print(f"\n{'Group':<18} {'N':>6} {'D1 Avg':>8} {'D1 WR':>8} {'D1 Med':>8} {'D1>1% pct':>10}")
    print("-" * 55)
    for label, grp in [("Winners (D5>=3%)", winners), ("Losers (D5<=-3%)", losers), ("Middle", middle)]:
        d1s = [d["outcome_1d"] for d in grp]
        pct_above1 = 100 * sum(1 for v in d1s if v > 1.0) / len(d1s) if d1s else 0
        print(f"{label:<18} {len(grp):>6} {avg(d1s):>+8.3f} {wr(d1s):>8.1f} {med(d1s):>+8.3f} {pct_above1:>10.1f}%")

    # Confusion matrix: D1 > 0 predicting D5 > 0
    tp = sum(1 for d in data if d["outcome_1d"] > 0 and d["outcome_5d"] > 0)
    fp = sum(1 for d in data if d["outcome_1d"] > 0 and d["outcome_5d"] <= 0)
    fn = sum(1 for d in data if d["outcome_1d"] <= 0 and d["outcome_5d"] > 0)
    tn = sum(1 for d in data if d["outcome_1d"] <= 0 and d["outcome_5d"] <= 0)
    print(f"\n  D1>0 predicting D5>0 confusion matrix:")
    print(f"    TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    accuracy = (tp + tn) / N
    print(f"    Precision={precision:.3f}  Recall={recall:.3f}  Accuracy={accuracy:.3f}")

    # =====================================================================
    # 7. SIMULATE EARLY EXIT STRATEGIES
    # =====================================================================
    section("7. SIMULATE EARLY EXIT STRATEGIES")

    def sim_strategy(name, exit_fn, data):
        """
        exit_fn(d) -> return value at exit, or None to hold to D5.
        Returns list of (raw_return, capped_return) for each trade.
        """
        results_raw = []
        results_capped = []
        exit_days = []
        for d in data:
            raw = exit_fn(d)
            if raw is None:
                raw = d["outcome_5d"]
                exit_days.append(5)
            else:
                # Determine which day we exited
                if raw == d["outcome_1d"]:
                    exit_days.append(1)
                elif raw == d["outcome_2d"]:
                    exit_days.append(2)
                elif raw == d["outcome_3d"]:
                    exit_days.append(3)
                elif raw == d["outcome_4d"]:
                    exit_days.append(4)
                else:
                    exit_days.append(5)
            results_raw.append(raw)
            results_capped.append(cap_return(raw))
        return results_raw, results_capped, exit_days

    # Baseline: always hold to D5
    def baseline_fn(d):
        return None  # hold to D5

    # Strategy A: Exit D1 if D1 < 0%
    def strat_a(d):
        if d["outcome_1d"] < 0:
            return d["outcome_1d"]
        return None

    # Strategy B: Exit D1 if D1 < -1%
    def strat_b(d):
        if d["outcome_1d"] < -1.0:
            return d["outcome_1d"]
        return None

    # Strategy C: Exit D2 if D2 < 0%
    def strat_c(d):
        if d["outcome_2d"] < 0:
            return d["outcome_2d"]
        return None

    # Strategy D: Always exit at D3
    def strat_d(d):
        return d["outcome_3d"]

    # Strategy E: Exit D1 if D1 < 0%, then exit D3 if D3 < D1 (adaptive)
    def strat_e(d):
        if d["outcome_1d"] < 0:
            return d["outcome_1d"]
        if d["outcome_3d"] < d["outcome_1d"]:
            return d["outcome_3d"]
        return None

    strategies = [
        ("BASELINE (hold D5)",           baseline_fn),
        ("A: Exit D1 if D1<0%",          strat_a),
        ("B: Exit D1 if D1<-1%",         strat_b),
        ("C: Exit D2 if D2<0%",          strat_c),
        ("D: Always exit D3",            strat_d),
        ("E: D1<0->exit, D3<D1->exit",   strat_e),
    ]

    subsection("Raw returns (no TP/SL cap)")
    print(f"\n{'Strategy':<32} {'N':>5} {'TotPnL%':>9} {'AvgRet%':>9} {'MedRet%':>9} {'WR%':>7} {'AvgDays':>8}")
    print("-" * 85)
    for name, fn in strategies:
        raw, capped, edays = sim_strategy(name, fn, data)
        print(f"{name:<32} {len(raw):>5} {sum(raw):>+9.1f} {avg(raw):>+9.3f} {med(raw):>+9.3f} {wr(raw):>7.1f} {avg(edays):>8.2f}")

    subsection("Capped returns (TP=+3%, SL=-2.5%)")
    print(f"\n{'Strategy':<32} {'N':>5} {'TotPnL%':>9} {'AvgRet%':>9} {'MedRet%':>9} {'WR%':>7} {'AvgDays':>8}")
    print("-" * 85)
    for name, fn in strategies:
        raw, capped, edays = sim_strategy(name, fn, data)
        print(f"{name:<32} {len(capped):>5} {sum(capped):>+9.1f} {avg(capped):>+9.3f} {med(capped):>+9.3f} {wr(capped):>7.1f} {avg(edays):>8.2f}")

    subsection("Strategy improvement vs baseline (capped)")
    base_raw, base_capped, base_days = sim_strategy("baseline", baseline_fn, data)
    base_total = sum(base_capped)
    base_avg = avg(base_capped)
    base_wr = wr(base_capped)

    print(f"\n{'Strategy':<32} {'dTotPnL%':>10} {'dAvgRet%':>10} {'dWR%':>8}")
    print("-" * 65)
    for name, fn in strategies[1:]:
        raw, capped, edays = sim_strategy(name, fn, data)
        d_total = sum(capped) - base_total
        d_avg = avg(capped) - base_avg
        d_wr = wr(capped) - base_wr
        print(f"{name:<32} {d_total:>+10.1f} {d_avg:>+10.3f} {d_wr:>+8.1f}")

    subsection("Strategy breakdown: how many early exits vs holds")
    for name, fn in strategies:
        raw, capped, edays = sim_strategy(name, fn, data)
        day_dist = defaultdict(int)
        for ed in edays:
            day_dist[ed] += 1
        dist_str = "  ".join(f"D{k}:{v}" for k, v in sorted(day_dist.items()))
        print(f"  {name:<32} {dist_str}")

    # =====================================================================
    # BONUS: Key cross-tabs
    # =====================================================================
    section("BONUS: KEY CROSS-TABS")

    subsection("VIX regime x D1 direction -> D5 outcome")
    print(f"\n{'VIX Regime':<14} {'D1 Dir':<10} {'N':>6} {'D5 Avg':>8} {'D5 WR':>8}")
    print("-" * 52)
    for vl, vf in vix_regimes:
        for d1_label, d1_filt in [("D1 > 0", lambda d: d["outcome_1d"] > 0), ("D1 <= 0", lambda d: d["outcome_1d"] <= 0)]:
            grp = [d for d in data if vf(d) and d1_filt(d)]
            if not grp:
                continue
            print(f"{vl:<14} {d1_label:<10} {len(grp):>6} {avg([d['outcome_5d'] for d in grp]):>+8.3f} {wr([d['outcome_5d'] for d in grp]):>8.1f}")

    subsection("ATR bucket x D1 direction -> best exit day")
    print(f"\n{'ATR Bucket':<14} {'D1 Dir':<10} {'N':>6} {'D1':>8} {'D2':>8} {'D3':>8} {'D4':>8} {'D5':>8} {'Peak':>6}")
    print("-" * 82)
    for al, af in atr_buckets:
        for d1_label, d1_filt in [("D1 > 0", lambda d: d["outcome_1d"] > 0), ("D1 <= 0", lambda d: d["outcome_1d"] <= 0)]:
            grp = [d for d in data if af(d) and d1_filt(d)]
            if not grp:
                continue
            avgs_x = [avg([d[col] for d in grp]) for col in days]
            peak = np.argmax(avgs_x)
            row = f"{al:<14} {d1_label:<10} {len(grp):>6}"
            for a in avgs_x:
                row += f" {a:>+8.3f}"
            row += f"    D{peak+1}"
            print(row)

    subsection("D1 bucket x ATR -> D5 avg return")
    atr_labels = ["ATR<2.5", "ATR2.5-4", "ATR4-6", "ATR>=6"]
    atr_filters = [
        lambda d: d["atr_pct"] < 2.5,
        lambda d: 2.5 <= d["atr_pct"] < 4.0,
        lambda d: 4.0 <= d["atr_pct"] < 6.0,
        lambda d: d["atr_pct"] >= 6.0,
    ]
    d1_buckets_simple = [
        ("D1<-1%", lambda d: d["outcome_1d"] < -1.0),
        ("-1<=D1<=0", lambda d: -1.0 <= d["outcome_1d"] <= 0),
        ("D1>0", lambda d: d["outcome_1d"] > 0),
    ]
    header = f"{'D1 Bucket':<14}"
    for al in atr_labels:
        header += f" {al:>12}"
    print(f"\n{header}")
    print("-" * (14 + 13 * len(atr_labels)))
    for d1l, d1f in d1_buckets_simple:
        row = f"{d1l:<14}"
        for af in atr_filters:
            grp = [d for d in data if d1f(d) and af(d)]
            if grp:
                row += f" {avg([d['outcome_5d'] for d in grp]):>+10.3f}  "
            else:
                row += f" {'n/a':>10}  "
        print(row)

    print("\n" + "=" * 90)
    print("  ANALYSIS COMPLETE")
    print("=" * 90)

if __name__ == "__main__":
    main()
