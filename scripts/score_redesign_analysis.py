#!/usr/bin/env python3
"""
Score Redesign Analysis — v7.4
IC-weighted composite score for DIP_BOUNCE signals.

Features (from IC analysis):
  distance_from_20d_high  IC=+0.521  (negative conv: 0=at high, -5=-5% below)
  atr_pct                 IC=-0.312  (higher vol → worse)
  momentum_5d             IC=+0.141  (higher mom → better)
  entry_rsi               IC=-0.110  (higher RSI → worse)
  score (old)             IC=-0.040  → drop

Usage:
  python3 scripts/score_redesign_analysis.py
"""

import sqlite3
import numpy as np
import pandas as pd
from scipy import stats

DB_PATH = "data/trade_history.db"

# ── IC weights (absolute) ──────────────────────────────────────────────────
FEATURES = [
    ("distance_from_20d_high", +1, 0.521),  # (col, direction +1=higher better, abs_IC)
    ("atr_pct",                -1, 0.312),
    ("momentum_5d",            +1, 0.141),
    ("entry_rsi",              -1, 0.110),
]
TOTAL_IC = sum(abs_ic for _, _, abs_ic in FEATURES)  # 1.084


# ── Load data ─────────────────────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    cols = ", ".join([f[0] for f in FEATURES] + ["score", "outcome_5d", "outcome_1d", "outcome_3d", "scan_date", "symbol"])
    df = pd.read_sql_query(f"""
        SELECT {cols}
        FROM signal_outcomes
        WHERE signal_source = 'dip_bounce'
          AND outcome_5d IS NOT NULL
          AND atr_pct IS NOT NULL
          AND entry_rsi IS NOT NULL
          AND momentum_5d IS NOT NULL
        ORDER BY scan_date
    """, conn)
    conn.close()
    return df


# ── Compute IC (Spearman) ─────────────────────────────────────────────────
def compute_ic(df: pd.DataFrame):
    print("\n=== IC Analysis (Spearman rank correlation with outcome_5d) ===")
    for col, direction, expected_ic in FEATURES:
        sub = df[[col, "outcome_5d"]].dropna()
        if len(sub) < 10:
            print(f"  {col:30s}  n={len(sub):4d}  SKIP (too few)")
            continue
        ic, pval = stats.spearmanr(sub[col], sub["outcome_5d"])
        stars = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
        print(f"  {col:30s}  IC={ic:+.3f}  p={pval:.4f}{stars:3s}  n={len(sub):4d}  (expected {direction*expected_ic:+.3f})")


# ── Normalize feature to [0,1] where 1=best ───────────────────────────────
def normalize_feature(series: pd.Series, direction: int, clip_lo=None, clip_hi=None) -> pd.Series:
    """Clip outliers then min-max normalize. direction=+1: higher→1. direction=-1: lower→1."""
    s = series.copy()
    if clip_lo is not None:
        s = s.clip(lower=clip_lo)
    if clip_hi is not None:
        s = s.clip(upper=clip_hi)
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(0.5, index=series.index)
    normed = (s - lo) / (hi - lo)
    if direction == -1:
        normed = 1.0 - normed
    return normed.fillna(0.5)


# ── Build new score ────────────────────────────────────────────────────────
def build_new_score(df: pd.DataFrame) -> pd.Series:
    """IC-weighted composite score [0, 100]."""
    # Clip params (conservative percentiles to handle outliers)
    clips = {
        "distance_from_20d_high": (-25.0, 0.0),   # 0=at high, -25=extreme downtrend
        "atr_pct":                (0.5,   12.0),   # cap extreme vol at 12%
        "momentum_5d":            (-20.0, 5.0),    # -20 to +5%
        "entry_rsi":              (20.0,  80.0),
    }
    score = pd.Series(0.0, index=df.index)
    for col, direction, abs_ic in FEATURES:
        w = abs_ic / TOTAL_IC
        lo, hi = clips[col]
        norm = normalize_feature(df[col], direction, clip_lo=lo, clip_hi=hi)
        score += w * norm
    return (score * 100).round(1)


# ── Compute WR by bucket ───────────────────────────────────────────────────
def wr_by_bucket(df: pd.DataFrame, col: str, n_buckets: int = 5):
    df = df.copy()
    df["bucket"] = pd.qcut(df[col], n_buckets, duplicates="drop")
    tbl = df.groupby("bucket", observed=True)["win"].agg(
        WR=lambda x: f"{x.mean()*100:.1f}%",
        n="count",
        avg_ret=lambda x: f"{df.loc[x.index,'outcome_5d'].mean():+.2f}%",
    )
    return tbl


# ── Threshold analysis ─────────────────────────────────────────────────────
def threshold_analysis(df: pd.DataFrame, col: str, thresholds: list):
    print(f"\n{'Threshold':>12}  {'n_pass':>6}  {'pass%':>6}  {'WR_pass':>8}  {'AvgRet_pass':>12}  {'WR_skip':>8}  {'AvgRet_skip':>12}")
    for t in thresholds:
        passed = df[df[col] >= t]
        skipped = df[df[col] < t]
        if len(passed) == 0:
            continue
        wr_p = passed["win"].mean() * 100
        ret_p = passed["outcome_5d"].mean()
        wr_s = skipped["win"].mean() * 100 if len(skipped) > 0 else float("nan")
        ret_s = skipped["outcome_5d"].mean() if len(skipped) > 0 else float("nan")
        pct = len(passed) / len(df) * 100
        print(f"  score>={t:5.0f}  {len(passed):>6d}  {pct:>5.1f}%  {wr_p:>7.1f}%  {ret_p:>+11.2f}%  {wr_s:>7.1f}%  {ret_s:>+11.2f}%")


# ── Old score analysis ─────────────────────────────────────────────────────
def old_score_analysis(df: pd.DataFrame):
    old = df.dropna(subset=["score"])
    if len(old) == 0:
        print("  No old score data.")
        return
    ic, pval = stats.spearmanr(old["score"], old["outcome_5d"])
    wr = (old["win"].mean() * 100)
    print(f"\n=== Old Score Baseline ===")
    print(f"  n={len(old)}  IC={ic:+.3f}  p={pval:.4f}  WR_all={wr:.1f}%  AvgRet={old['outcome_5d'].mean():+.2f}%")
    # by decile
    print("\n  Old score decile breakdown:")
    print(wr_by_bucket(old, "score", n_buckets=5).to_string())


# ── New score vs old comparison ────────────────────────────────────────────
def compare_scores(df: pd.DataFrame):
    df = df.copy()
    df["new_score"] = build_new_score(df)

    ic_new, pnew = stats.spearmanr(df["new_score"], df["outcome_5d"])
    ic_old, pold = stats.spearmanr(df["score"].fillna(df["score"].median()), df["outcome_5d"])

    print(f"\n=== Score Comparison ===")
    print(f"  Old score  IC={ic_old:+.3f}  p={pold:.4f}")
    print(f"  New score  IC={ic_new:+.3f}  p={pnew:.4f}  {'✅ BETTER' if abs(ic_new) > abs(ic_old) else '❌ WORSE'}")

    # Quintile WR table
    print("\n  New score quintile breakdown:")
    print(wr_by_bucket(df, "new_score", n_buckets=5).to_string())

    return df


# ── Feature contribution sanity check ─────────────────────────────────────
def feature_contributions(df: pd.DataFrame):
    print("\n=== Per-Feature IC Recalculated on This Dataset ===")
    cols = [f[0] for f in FEATURES]
    for col in cols:
        sub = df[[col, "outcome_5d"]].dropna()
        ic, pval = stats.spearmanr(sub[col], sub["outcome_5d"])
        stars = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
        print(f"  {col:30s}  IC={ic:+.3f}  p={pval:.4f}{stars}  n={len(sub)}")


# ── Additive value of each feature ────────────────────────────────────────
def ablation_study(df: pd.DataFrame):
    """Drop each feature, see IC drop."""
    df = df.copy()
    full_score = build_new_score(df)
    full_ic, _ = stats.spearmanr(full_score, df["outcome_5d"])
    print(f"\n=== Ablation Study (drop-one-feature) — Full IC={full_ic:+.3f} ===")
    for i, (col, direction, abs_ic) in enumerate(FEATURES):
        subset = [f for j, f in enumerate(FEATURES) if j != i]
        subset_w = sum(f[2] for f in subset)
        s = pd.Series(0.0, index=df.index)
        clips = {
            "distance_from_20d_high": (-25.0, 0.0),
            "atr_pct":                (0.5,   12.0),
            "momentum_5d":            (-20.0, 5.0),
            "entry_rsi":              (20.0,  80.0),
        }
        for c, d, w in subset:
            lo, hi = clips[c]
            norm = normalize_feature(df[c], d, clip_lo=lo, clip_hi=hi)
            s += (w / subset_w) * norm
        s = (s * 100).round(1)
        ic_sub, _ = stats.spearmanr(s, df["outcome_5d"])
        delta = ic_sub - full_ic
        print(f"  Drop {col:30s}  IC={ic_sub:+.3f}  delta={delta:+.3f}")


# ── Extended bucket analysis (5-point bands) ──────────────────────────────
def extended_bucket_analysis(df: pd.DataFrame):
    """Fine-grained WR/return breakdown by 5-pt score bands."""
    df = df.copy()
    df["new_score"] = build_new_score(df)

    # Define buckets
    def bucket(s):
        if s >= 80: return "80+"
        if s >= 75: return "75-80"
        if s >= 70: return "70-75"
        if s >= 65: return "65-70"
        if s >= 60: return "60-65"
        return "<60"

    df["bucket"] = df["new_score"].apply(bucket)
    order = ["80+", "75-80", "70-75", "65-70", "60-65", "<60"]

    total_n = len(df)
    print(f"\n=== Extended Bucket Analysis (n={total_n}) ===")
    print(f"{'Bucket':>8}  {'n':>5}  {'% total':>8}  {'WR':>7}  {'AvgRet':>9}  {'cumPass%':>9}  {'cumWR':>7}  {'cumAvgRet':>10}")
    print("-" * 80)

    cum_n = 0
    cum_wins = 0
    cum_ret = 0.0

    for b in order:
        sub = df[df["bucket"] == b]
        n = len(sub)
        if n == 0:
            continue
        wr = sub["win"].mean() * 100
        avg_ret = sub["outcome_5d"].mean()
        pct = n / total_n * 100

        cum_n += n
        cum_wins += sub["win"].sum()
        cum_ret += sub["outcome_5d"].sum()
        cum_wr = cum_wins / cum_n * 100
        cum_avg_ret = cum_ret / cum_n
        cum_pct = cum_n / total_n * 100

        marker = " ⬅ top quintile" if b == "80+" else ""
        print(f"  {b:>6}  {n:>5}  {pct:>7.1f}%  {wr:>6.1f}%  {avg_ret:>+8.2f}%  {cum_pct:>8.1f}%  {cum_wr:>6.1f}%  {cum_avg_ret:>+9.2f}%{marker}")

    # Also show "if threshold = X, what % of live signals pass?"
    print(f"\n  Trade-off summary (live signal rate per day ≈ {total_n / 26:.0f} signals/day):")
    for thresh in [60, 65, 70, 75, 80]:
        passed = df[df["new_score"] >= thresh]
        skipped = df[df["new_score"] < thresh]
        n_pass = len(passed)
        wr_pass = passed["win"].mean() * 100 if n_pass > 0 else 0
        ret_pass = passed["outcome_5d"].mean() if n_pass > 0 else 0
        wr_skip = skipped["win"].mean() * 100 if len(skipped) > 0 else 0
        ret_skip = skipped["outcome_5d"].mean() if len(skipped) > 0 else 0
        daily_pass = n_pass / 26
        wr_lift = wr_pass - wr_skip
        print(f"    threshold>={thresh}: pass {n_pass:>4} ({n_pass/total_n*100:>4.1f}%)  "
              f"~{daily_pass:.1f}/day  WR={wr_pass:.1f}%  ret={ret_pass:+.2f}%  "
              f"[skip: WR={wr_skip:.1f}% ret={ret_skip:+.2f}%]  lift={wr_lift:+.1f}pp")

    return df


# ── 75-80 band weekly breakdown ───────────────────────────────────────────
def band_75_80_weekly(df: pd.DataFrame):
    """Weekly WR breakdown for the suspicious 75-80 band vs neighbours."""
    df = df.copy()
    df["new_score"] = build_new_score(df)
    df["scan_date"] = pd.to_datetime(df["scan_date"])
    df["week"] = df["scan_date"].dt.to_period("W")

    bands = {
        "70-75": (70, 75),
        "75-80": (75, 80),   # ← suspicious band
        "80+":   (80, 999),
    }

    print(f"\n=== 75-80 Weekly Breakdown (vs neighbours) ===")
    weeks = sorted(df["week"].unique())
    for b_name, (lo, hi) in bands.items():
        mask = (df["new_score"] >= lo) & (df["new_score"] < hi)
        sub = df[mask]
        print(f"\n  Band {b_name} (n={len(sub)} total):")
        print(f"  {'Week':>20}  {'n':>5}  {'WR':>7}  {'AvgRet':>9}  {'min_ret':>8}  {'max_ret':>8}")
        for week in weeks:
            w = sub[sub["week"] == week]
            if len(w) == 0:
                continue
            wr = w["win"].mean() * 100
            avg = w["outcome_5d"].mean()
            mn = w["outcome_5d"].min()
            mx = w["outcome_5d"].max()
            flag = " ⚠️" if b_name == "75-80" and wr < 45 else ""
            print(f"  {str(week):>20}  {len(w):>5}  {wr:>6.1f}%  {avg:>+8.2f}%  {mn:>+7.2f}%  {mx:>+7.2f}%{flag}")

    # Cross-week correlation: does 75-80 WR track 80+ WR?
    print(f"\n  Correlation check — does 75-80 WR track 80+?")
    rows = []
    for week in weeks:
        r = {"week": str(week)}
        for b_name, (lo, hi) in bands.items():
            mask = (df["new_score"] >= lo) & (df["new_score"] < hi) & (df["week"] == week)
            w = df[mask]
            r[b_name] = w["win"].mean() * 100 if len(w) >= 5 else float("nan")
        rows.append(r)
    corr_df = pd.DataFrame(rows).set_index("week")
    print(corr_df.round(1).to_string())


# ── Feature breakdown per band — diagnose 75-80 anomaly ──────────────────
def band_feature_breakdown(df: pd.DataFrame):
    df = df.copy()
    df["new_score"] = build_new_score(df)

    bands = {"70-75": (70,75), "75-80": (75,80), "80+": (80,999)}
    feat_cols = [f[0] for f in FEATURES]

    print(f"\n=== Feature Profile per Band (why is 75-80 bad?) ===")
    print(f"  {'Feature':30s}  {'70-75':>10}  {'75-80':>10}  {'80+':>10}  {'75-80 vs 80+':>14}")
    rows = {}
    for b, (lo, hi) in bands.items():
        mask = (df["new_score"] >= lo) & (df["new_score"] < hi)
        rows[b] = df[mask]

    for col in feat_cols + ["win", "outcome_5d"]:
        vals = {b: rows[b][col].mean() for b in bands}
        diff = vals["75-80"] - vals["80+"]
        fmt = "  {:30s}  {:>+10.2f}  {:>+10.2f}  {:>+10.2f}  {:>+14.2f}"
        print(fmt.format(col, vals["70-75"], vals["75-80"], vals["80+"], diff))

    # RSI distribution within each band
    print(f"\n  RSI percentile breakdown:")
    print(f"  {'Band':>8}  {'p10':>6}  {'p25':>6}  {'median':>8}  {'p75':>6}  {'p90':>6}  {'mean':>7}")
    for b, (lo, hi) in bands.items():
        mask = (df["new_score"] >= lo) & (df["new_score"] < hi)
        rsi = df[mask]["entry_rsi"]
        print(f"  {b:>8}  {rsi.quantile(.10):>6.1f}  {rsi.quantile(.25):>6.1f}"
              f"  {rsi.quantile(.50):>8.1f}  {rsi.quantile(.75):>6.1f}"
              f"  {rsi.quantile(.90):>6.1f}  {rsi.mean():>7.1f}")

    # dist_from_20d_high distribution — is 75-80 somehow at a local peak?
    print(f"\n  distance_from_20d_high percentile breakdown:")
    print(f"  {'Band':>8}  {'p10':>7}  {'p25':>7}  {'median':>8}  {'p75':>7}  {'p90':>7}  {'mean':>8}")
    for b, (lo, hi) in bands.items():
        mask = (df["new_score"] >= lo) & (df["new_score"] < hi)
        d = df[mask]["distance_from_20d_high"]
        print(f"  {b:>8}  {d.quantile(.10):>+7.2f}  {d.quantile(.25):>+7.2f}"
              f"  {d.quantile(.50):>+8.2f}  {d.quantile(.75):>+7.2f}"
              f"  {d.quantile(.90):>+7.2f}  {d.mean():>+8.2f}")

    # Hypothesis test: within 75-80, do high-RSI stocks perform worse?
    band = rows["75-80"]
    median_rsi = band["entry_rsi"].median()
    hi_rsi = band[band["entry_rsi"] >= median_rsi]
    lo_rsi = band[band["entry_rsi"] < median_rsi]
    print(f"\n  Within 75-80 band — RSI split (median={median_rsi:.1f}):")
    print(f"    RSI >= {median_rsi:.1f}  n={len(hi_rsi):>4}  WR={hi_rsi['win'].mean()*100:.1f}%  AvgRet={hi_rsi['outcome_5d'].mean():+.2f}%")
    print(f"    RSI <  {median_rsi:.1f}  n={len(lo_rsi):>4}  WR={lo_rsi['win'].mean()*100:.1f}%  AvgRet={lo_rsi['outcome_5d'].mean():+.2f}%")

    # momentum_5d split within 75-80
    median_mom = band["momentum_5d"].median()
    hi_mom = band[band["momentum_5d"] >= median_mom]
    lo_mom = band[band["momentum_5d"] < median_mom]
    print(f"\n  Within 75-80 band — momentum_5d split (median={median_mom:.2f}%):")
    print(f"    mom >= {median_mom:.2f}%  n={len(hi_mom):>4}  WR={hi_mom['win'].mean()*100:.1f}%  AvgRet={hi_mom['outcome_5d'].mean():+.2f}%")
    print(f"    mom <  {median_mom:.2f}%  n={len(lo_mom):>4}  WR={lo_mom['win'].mean()*100:.1f}%  AvgRet={lo_mom['outcome_5d'].mean():+.2f}%")


# ── Per-week stability check ───────────────────────────────────────────────
def per_week_stability(df: pd.DataFrame):
    """Check if the score pattern holds week-over-week."""
    df = df.copy()
    df["new_score"] = build_new_score(df)
    df["scan_date"] = pd.to_datetime(df["scan_date"])
    df["week"] = df["scan_date"].dt.to_period("W")

    print(f"\n=== Per-Week Score Stability ===")
    print(f"  (High = new_score >= 70, Low = new_score < 60)")
    print(f"  {'Week':>12}  {'n_total':>7}  {'n_high':>6}  {'WR_high':>8}  {'WR_low':>7}  {'spread':>7}")
    print("-" * 65)

    for week in sorted(df["week"].unique()):
        sub = df[df["week"] == week]
        high = sub[sub["new_score"] >= 70]
        low = sub[sub["new_score"] < 60]
        wr_h = high["win"].mean() * 100 if len(high) > 0 else float("nan")
        wr_l = low["win"].mean() * 100 if len(low) > 0 else float("nan")
        spread = wr_h - wr_l if not (np.isnan(wr_h) or np.isnan(wr_l)) else float("nan")
        n_h = len(high)
        print(f"  {str(week):>12}  {len(sub):>7}  {n_h:>6}  {wr_h:>7.1f}%  {wr_l:>6.1f}%  {spread:>+6.1f}pp")


# ── Feature distribution within each bucket ────────────────────────────────
def feature_profiles(df: pd.DataFrame):
    """Show avg feature values in top vs bottom bucket."""
    df = df.copy()
    df["new_score"] = build_new_score(df)

    top = df[df["new_score"] >= 75]
    bot = df[df["new_score"] < 60]

    print(f"\n=== Feature Profile: Top (>=75, n={len(top)}) vs Bottom (<60, n={len(bot)}) ===")
    print(f"  {'Feature':30s}  {'Top avg':>10}  {'Bot avg':>10}  {'diff':>10}")
    for col, direction, _ in FEATURES:
        t_avg = top[col].mean()
        b_avg = bot[col].mean()
        print(f"  {col:30s}  {t_avg:>+10.2f}  {b_avg:>+10.2f}  {t_avg-b_avg:>+10.2f}")

    print(f"\n  WR:      Top={top['win'].mean()*100:.1f}%  Bot={bot['win'].mean()*100:.1f}%")
    print(f"  AvgRet:  Top={top['outcome_5d'].mean():+.2f}%  Bot={bot['outcome_5d'].mean():+.2f}%")


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    print("Loading data from signal_outcomes...")
    df = load_data()
    print(f"  Loaded {len(df)} DIP_BOUNCE signals with outcome_5d")
    print(f"  Date range: {df['scan_date'].min()} → {df['scan_date'].max()}")
    print(f"  distance_from_20d_high coverage: {df['distance_from_20d_high'].notna().sum()}/{len(df)}")
    print(f"  Score (old) non-null: {df['score'].notna().sum()}/{len(df)}")

    # Win = outcome_5d > 0
    df["win"] = (df["outcome_5d"] > 0).astype(int)
    overall_wr = df["win"].mean() * 100
    print(f"\n  Overall WR={overall_wr:.1f}%  AvgRet={df['outcome_5d'].mean():+.2f}%  n={len(df)}")

    # Filter to rows with distance_from_20d_high
    df_full = df.dropna(subset=["distance_from_20d_high"]).copy()
    print(f"  With distance_from_20d_high: {len(df_full)} rows")

    # ── Analysis steps ──
    feature_contributions(df_full)
    compute_ic(df_full)
    old_score_analysis(df_full)

    df_scored = compare_scores(df_full)

    # ── Threshold analysis for new score ──
    thresholds = [30, 35, 40, 45, 50, 55, 60]
    print(f"\n=== Threshold Analysis (new_score) — pass/skip WR/return ===")
    threshold_analysis(df_scored, "new_score", thresholds)

    ablation_study(df_full)

    # ── Extended analysis ──
    extended_bucket_analysis(df_full)
    band_75_80_weekly(df_full)
    band_feature_breakdown(df_full)
    per_week_stability(df_full)
    feature_profiles(df_full)

    # ── Final recommendation ──
    df_scored["new_score"] = build_new_score(df_full)
    best_t = None
    best_lift = -999
    for t in thresholds:
        passed = df_scored[df_scored["new_score"] >= t]
        skipped = df_scored[df_scored["new_score"] < t]
        if len(passed) < 20:
            continue
        lift = passed["outcome_5d"].mean() - skipped["outcome_5d"].mean() if len(skipped) > 0 else 0
        if lift > best_lift:
            best_lift = lift
            best_t = t

    print(f"\n=== Recommendation ===")
    print(f"  IC-weighted formula (weights normalized to 1.0):")
    for col, direction, abs_ic in FEATURES:
        w = abs_ic / TOTAL_IC
        sense = "higher→better" if direction == +1 else "lower→better"
        print(f"    {w:.3f} × norm({col})  [{sense}]")
    print(f"\n  Suggested threshold: new_score >= {best_t}  (best return lift vs skip)")
    print(f"    Lift vs below-threshold: {best_lift:+.2f}%")
    print(f"\n  Formula string for engine:")
    print(f"    score = (0.481 × norm_dist20d + 0.288 × norm_atr_inv + 0.130 × norm_mom5d + 0.102 × norm_rsi_inv) × 100")
    print(f"    where each norm_* ∈ [0,1], 1=best")


if __name__ == "__main__":
    main()
