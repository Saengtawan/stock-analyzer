#!/usr/bin/env python3
"""
Comprehensive Feature IC Analysis across all horizons (1d-5d).
Uses backfill_signal_outcomes (n=5,850) joined with macro_snapshots + market_breadth.
"""

import sqlite3
import numpy as np
import pandas as pd
from scipy import stats

DB_PATH = "data/trade_history.db"

# ─────────────────────────────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)

bso = pd.read_sql_query("""
    SELECT scan_date, symbol, sector, scan_price,
           atr_pct, entry_rsi, distance_from_20d_high,
           momentum_5d, momentum_20d, volume_ratio, vix_at_signal,
           outcome_1d, outcome_2d, outcome_3d, outcome_4d, outcome_5d,
           outcome_max_gain_5d, outcome_max_dd_5d
    FROM backfill_signal_outcomes
    WHERE outcome_1d IS NOT NULL
""", conn)

macro = pd.read_sql_query("""
    SELECT date, vix_close, vix3m_close, spy_close, yield_10y,
           yield_spread, crude_close, gold_close, hyg_close, dxy_close
    FROM macro_snapshots
""", conn)

breadth = pd.read_sql_query("""
    SELECT date, pct_above_20d_ma, pct_above_50d_ma,
           new_52w_highs, new_52w_lows, ad_ratio
    FROM market_breadth
""", conn)

conn.close()

# Merge
merged = bso.merge(macro, left_on="scan_date", right_on="date", how="left").drop(columns=["date"])
merged = merged.merge(breadth, left_on="scan_date", right_on="date", how="left").drop(columns=["date"])

print(f"Total rows: {len(bso)}")
print(f"After macro join: {merged['vix_close'].notna().sum()} have macro data")
print(f"After breadth join: {merged['pct_above_20d_ma'].notna().sum()} have breadth data")
print(f"Date range: {bso['scan_date'].min()} to {bso['scan_date'].max()}")
print()

OUTCOMES = ["outcome_1d", "outcome_2d", "outcome_3d", "outcome_4d", "outcome_5d",
            "outcome_max_gain_5d", "outcome_max_dd_5d"]

STOCK_FEATURES = ["atr_pct", "entry_rsi", "momentum_5d", "momentum_20d",
                  "volume_ratio", "distance_from_20d_high", "scan_price", "vix_at_signal"]

MACRO_FEATURES = ["vix_close", "vix3m_close", "spy_close", "yield_10y",
                  "yield_spread", "crude_close", "gold_close", "hyg_close", "dxy_close",
                  "pct_above_20d_ma", "pct_above_50d_ma", "new_52w_highs", "new_52w_lows", "ad_ratio"]


def compute_ic(df, features, outcomes):
    """Compute Spearman IC + p-value for each feature × outcome."""
    results = []
    for feat in features:
        for out in outcomes:
            mask = df[feat].notna() & df[out].notna()
            n = mask.sum()
            if n < 30:
                results.append({"feature": feat, "outcome": out, "IC": np.nan,
                                "p_value": np.nan, "n": n})
                continue
            r, p = stats.spearmanr(df.loc[mask, feat], df.loc[mask, out])
            results.append({"feature": feat, "outcome": out, "IC": r,
                            "p_value": p, "n": n})
    return pd.DataFrame(results)


# ═════════════════════════════════════════════════════════════════════
# PART 1: Stock Features IC across all horizons
# ═════════════════════════════════════════════════════════════════════
print("=" * 100)
print("PART 1: STOCK FEATURES IC ACROSS ALL HORIZONS (n=5,850)")
print("=" * 100)

ic_stock = compute_ic(bso, STOCK_FEATURES, OUTCOMES)

# Pivot: features as rows, outcomes as columns
pivot_ic = ic_stock.pivot(index="feature", columns="outcome", values="IC")
pivot_p = ic_stock.pivot(index="feature", columns="outcome", values="p_value")

# Reorder columns
col_order = OUTCOMES
pivot_ic = pivot_ic[col_order]
pivot_p = pivot_p[col_order]

print("\nSpearman IC values:")
print("-" * 100)
# Format with significance markers
def format_ic_with_sig(ic_val, p_val):
    if pd.isna(ic_val):
        return "   ---  "
    sig = ""
    if p_val < 0.001:
        sig = "***"
    elif p_val < 0.01:
        sig = "** "
    elif p_val < 0.05:
        sig = "*  "
    else:
        sig = "   "
    return f"{ic_val:+.4f}{sig}"

header = f"{'Feature':<25s}"
for c in col_order:
    short = c.replace("outcome_", "")
    header += f"  {short:>10s}"
print(header)
print("-" * 100)

for feat in STOCK_FEATURES:
    row = f"{feat:<25s}"
    for out in col_order:
        ic_val = pivot_ic.loc[feat, out]
        p_val = pivot_p.loc[feat, out]
        row += f"  {format_ic_with_sig(ic_val, p_val):>10s}"
    print(row)

print("\n*** p<0.001  ** p<0.01  * p<0.05")

# Best horizon per feature
print("\nBest horizon per stock feature (by |IC|):")
print("-" * 70)
horizon_cols = ["outcome_1d", "outcome_2d", "outcome_3d", "outcome_4d", "outcome_5d"]
for feat in STOCK_FEATURES:
    best_out = None
    best_ic = 0
    for out in horizon_cols:
        ic_val = pivot_ic.loc[feat, out]
        if pd.notna(ic_val) and abs(ic_val) > abs(best_ic):
            best_ic = ic_val
            best_out = out
    print(f"  {feat:<25s} -> {best_out.replace('outcome_', ''):>3s}  IC={best_ic:+.4f}")


# ═════════════════════════════════════════════════════════════════════
# PART 2: Macro Features IC across all horizons
# ═════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 100)
print("PART 2: MACRO FEATURES IC ACROSS ALL HORIZONS")
print("=" * 100)

ic_macro = compute_ic(merged, MACRO_FEATURES, OUTCOMES)

pivot_ic_m = ic_macro.pivot(index="feature", columns="outcome", values="IC")
pivot_p_m = ic_macro.pivot(index="feature", columns="outcome", values="p_value")
pivot_n_m = ic_macro.pivot(index="feature", columns="outcome", values="n")

pivot_ic_m = pivot_ic_m.reindex(columns=col_order)
pivot_p_m = pivot_p_m.reindex(columns=col_order)

print(f"\nMacro data coverage: {merged['vix_close'].notna().sum()} / {len(merged)} rows")

print("\nSpearman IC values:")
print("-" * 100)
header = f"{'Feature':<25s}"
for c in col_order:
    short = c.replace("outcome_", "")
    header += f"  {short:>10s}"
print(header)
print("-" * 100)

for feat in MACRO_FEATURES:
    row = f"{feat:<25s}"
    for out in col_order:
        ic_val = pivot_ic_m.loc[feat, out] if feat in pivot_ic_m.index else np.nan
        p_val = pivot_p_m.loc[feat, out] if feat in pivot_p_m.index else np.nan
        row += f"  {format_ic_with_sig(ic_val, p_val):>10s}"
    print(row)

print("\n*** p<0.001  ** p<0.01  * p<0.05")

# Best horizon per macro feature
print("\nBest horizon per macro feature (by |IC|):")
print("-" * 70)
for feat in MACRO_FEATURES:
    best_out = None
    best_ic = 0
    for out in horizon_cols:
        if feat not in pivot_ic_m.index:
            continue
        ic_val = pivot_ic_m.loc[feat, out]
        if pd.notna(ic_val) and abs(ic_val) > abs(best_ic):
            best_ic = ic_val
            best_out = out
    if best_out:
        print(f"  {feat:<25s} -> {best_out.replace('outcome_', ''):>3s}  IC={best_ic:+.4f}")
    else:
        print(f"  {feat:<25s} -> no data")


# ═════════════════════════════════════════════════════════════════════
# PART 3: IC Stability Over Time (Quarterly)
# ═════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 100)
print("PART 3: IC STABILITY OVER TIME (QUARTERLY)")
print("=" * 100)

# Define quarters
merged["scan_date_dt"] = pd.to_datetime(merged["scan_date"])

def assign_quarter(dt):
    if dt < pd.Timestamp("2025-11-01"):
        return "Q1:Sep-Oct25"
    elif dt < pd.Timestamp("2026-01-01"):
        return "Q2:Nov-Dec25"
    elif dt < pd.Timestamp("2026-02-01"):
        return "Q3:Jan26"
    else:
        return "Q4:Feb-Mar26"

merged["quarter"] = merged["scan_date_dt"].apply(assign_quarter)

print("\nRows per quarter:")
for q in ["Q1:Sep-Oct25", "Q2:Nov-Dec25", "Q3:Jan26", "Q4:Feb-Mar26"]:
    n = (merged["quarter"] == q).sum()
    print(f"  {q}: {n} rows")

# Top 10 features by overall |IC| across outcome_5d
ALL_FEATURES = STOCK_FEATURES + MACRO_FEATURES
ic_all = compute_ic(merged, ALL_FEATURES, ["outcome_5d"])
ic_all["abs_IC"] = ic_all["IC"].abs()
top10 = ic_all.nlargest(10, "abs_IC")["feature"].tolist()

print(f"\nTop 10 features by overall |IC| vs outcome_5d: {top10}")

# Compute IC per quarter for top features, all horizons (use 5d as main)
quarters = ["Q1:Sep-Oct25", "Q2:Nov-Dec25", "Q3:Jan26", "Q4:Feb-Mar26"]

# For each horizon, show quarterly IC
for horizon in ["outcome_1d", "outcome_3d", "outcome_5d"]:
    h_short = horizon.replace("outcome_", "")
    print(f"\n--- Quarterly IC for {horizon} ---")
    print("-" * 90)
    header = f"{'Feature':<25s}"
    for q in quarters:
        header += f"  {q:>14s}"
    header += "   Sign-Flip?"
    print(header)
    print("-" * 90)

    for feat in top10:
        row = f"{feat:<25s}"
        ics = []
        for q in quarters:
            qdf = merged[merged["quarter"] == q]
            mask = qdf[feat].notna() & qdf[horizon].notna()
            n = mask.sum()
            if n < 20:
                row += f"  {'n<20':>14s}"
                ics.append(np.nan)
            else:
                r, p = stats.spearmanr(qdf.loc[mask, feat], qdf.loc[mask, horizon])
                sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else ""))
                row += f"  {r:+.4f}{sig:>4s} n={n:<4d}"
                ics.append(r)

        # Check sign flip
        valid = [x for x in ics if not np.isnan(x)]
        if len(valid) >= 2:
            signs = [np.sign(x) for x in valid if x != 0]
            if len(set(signs)) > 1:
                row += "   *** FLIP ***"
            else:
                row += "   stable"
        else:
            row += "   ---"
        print(row)


# ═════════════════════════════════════════════════════════════════════
# PART 4: Optimal Feature Set per Horizon
# ═════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 100)
print("PART 4: OPTIMAL FEATURE SET PER HORIZON")
print("=" * 100)

ic_full = compute_ic(merged, ALL_FEATURES, horizon_cols)
ic_full["abs_IC"] = ic_full["IC"].abs()

for horizon in horizon_cols:
    h_short = horizon.replace("outcome_", "")
    sub = ic_full[ic_full["outcome"] == horizon].nlargest(5, "abs_IC")
    print(f"\n--- Top 5 features for {horizon} ---")
    print(f"  {'Rank':<6s}{'Feature':<25s}{'IC':>10s}{'p-value':>12s}{'n':>8s}")
    for i, (_, r) in enumerate(sub.iterrows(), 1):
        sig = "***" if r.p_value < 0.001 else ("**" if r.p_value < 0.01 else ("*" if r.p_value < 0.05 else ""))
        print(f"  {i:<6d}{r.feature:<25s}{r.IC:>+10.4f}{r.p_value:>12.6f}{int(r.n):>8d}  {sig}")

# Summary: does top-5 change across horizons?
print("\n--- Feature presence across horizons (Top-5) ---")
print("-" * 70)
feat_horizons = {}
for horizon in horizon_cols:
    sub = ic_full[ic_full["outcome"] == horizon].nlargest(5, "abs_IC")
    for feat in sub["feature"].tolist():
        if feat not in feat_horizons:
            feat_horizons[feat] = []
        feat_horizons[feat].append(horizon.replace("outcome_", ""))

header = f"{'Feature':<25s}  {'Horizons in Top-5':<40s}  {'Count':>5s}"
print(header)
for feat, horizons in sorted(feat_horizons.items(), key=lambda x: -len(x[1])):
    print(f"  {feat:<25s}  {', '.join(horizons):<40s}  {len(horizons):>5d}")


# ═════════════════════════════════════════════════════════════════════
# PART 5: Sector as a Feature
# ═════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 100)
print("PART 5: SECTOR AS A FEATURE")
print("=" * 100)

# Per-sector average return at each horizon
sector_returns = bso.groupby("sector")[horizon_cols].agg(["mean", "count"])

print("\n--- Per-Sector Mean Return (%) by Horizon ---")
print("-" * 110)
header = f"{'Sector':<30s}  {'n':>5s}"
for h in horizon_cols:
    header += f"  {h.replace('outcome_', ''):>8s}"
print(header)
print("-" * 110)

for sector in sorted(bso["sector"].dropna().unique()):
    n = int(sector_returns.loc[sector, (horizon_cols[0], "count")])
    row = f"{sector:<30s}  {n:>5d}"
    for h in horizon_cols:
        mean_ret = sector_returns.loc[sector, (h, "mean")]
        row += f"  {mean_ret:>+8.3f}"
    print(row)

# Rank sectors by horizon
print("\n--- Sector Rankings by Horizon ---")
print("-" * 90)
for h in horizon_cols:
    h_short = h.replace("outcome_", "")
    means = bso.groupby("sector")[h].mean().dropna().sort_values(ascending=False)
    print(f"\n  {h} (best to worst):")
    for i, (sec, val) in enumerate(means.items(), 1):
        n_sec = (bso["sector"] == sec).sum()
        marker = " <-- best" if i == 1 else (" <-- worst" if i == len(means) else "")
        print(f"    {i:>2d}. {sec:<28s} {val:>+8.3f}%  (n={n_sec}){marker}")

# Sector × horizon interaction: which sectors improve / deteriorate over time?
print("\n--- Sector x Horizon Interaction (5d - 1d spread) ---")
print("-" * 60)
print(f"  {'Sector':<30s}  {'1d':>8s}  {'5d':>8s}  {'Spread':>8s}")
print("-" * 60)

sector_spread = []
for sector in sorted(bso["sector"].dropna().unique()):
    m1 = bso[bso["sector"] == sector]["outcome_1d"].mean()
    m5 = bso[bso["sector"] == sector]["outcome_5d"].mean()
    n = (bso["sector"] == sector).sum()
    if n >= 20:
        spread = m5 - m1
        sector_spread.append((sector, m1, m5, spread, n))

sector_spread.sort(key=lambda x: -x[3])
for sec, m1, m5, spread, n in sector_spread:
    arrow = "IMPROVES" if spread > 0.3 else ("DETERIORATES" if spread < -0.3 else "flat")
    print(f"  {sec:<30s}  {m1:>+8.3f}  {m5:>+8.3f}  {spread:>+8.3f}  {arrow} (n={n})")

# ANOVA: is sector a significant predictor?
print("\n--- ANOVA: Sector Effect on Returns ---")
for h in horizon_cols:
    groups = [g[h].dropna().values for _, g in bso.groupby("sector") if len(g[h].dropna()) >= 10]
    if len(groups) >= 2:
        f_stat, p_val = stats.f_oneway(*groups)
        sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < 0.05 else "ns"))
        print(f"  {h.replace('outcome_', ''):>3s}: F={f_stat:.3f}, p={p_val:.6f}  {sig}")

print("\n" + "=" * 100)
print("ANALYSIS COMPLETE")
print("=" * 100)
