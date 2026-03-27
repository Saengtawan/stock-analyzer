#!/usr/bin/env python3
"""
Comprehensive backtest: 8-feature kernel vs lean 6-feature kernel.
Expanding-window walk-forward with Gaussian kernel regression.
Research script only — does NOT modify any production files.
"""

import sqlite3
import numpy as np
from collections import defaultdict
from datetime import datetime

DB_PATH = "data/trade_history.db"

# ─── Data Loading ────────────────────────────────────────────────────────────
LOAD_SQL = """
WITH breadth_lag AS (
    SELECT date, pct_above_20d_ma,
           pct_above_20d_ma - LAG(pct_above_20d_ma, 5) OVER (ORDER BY date) as breadth_delta_5d
    FROM market_breadth
),
combined AS (
    SELECT scan_date, symbol, outcome_5d, outcome_max_dd_5d,
           distance_from_20d_high, atr_pct, volume_ratio,
           momentum_20d, vix_at_signal, entry_rsi, momentum_5d,
           1 as priority
    FROM signal_outcomes
    WHERE outcome_5d IS NOT NULL
    UNION ALL
    SELECT scan_date, symbol, outcome_5d, outcome_max_dd_5d,
           distance_from_20d_high, atr_pct, volume_ratio,
           momentum_20d, vix_at_signal, entry_rsi, momentum_5d,
           2 as priority
    FROM backfill_signal_outcomes
    WHERE outcome_5d IS NOT NULL
),
deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY scan_date, symbol ORDER BY priority ASC) as rn
    FROM combined
)
SELECT d.scan_date, d.outcome_5d, d.outcome_max_dd_5d,
       d.distance_from_20d_high, d.atr_pct, d.volume_ratio,
       d.momentum_20d, d.vix_at_signal, d.entry_rsi, d.momentum_5d,
       m.crude_close, m.gold_close,
       bl.pct_above_20d_ma as breadth_above_20d,
       bl.breadth_delta_5d
FROM deduped d
LEFT JOIN macro_snapshots m
    ON m.date = CASE
        WHEN strftime('%w', d.scan_date) = '6' THEN date(d.scan_date, '-1 day')
        WHEN strftime('%w', d.scan_date) = '0' THEN date(d.scan_date, '-2 days')
        ELSE d.scan_date END
LEFT JOIN breadth_lag bl
    ON bl.date = CASE
        WHEN strftime('%w', d.scan_date) = '6' THEN date(d.scan_date, '-1 day')
        WHEN strftime('%w', d.scan_date) = '0' THEN date(d.scan_date, '-2 days')
        ELSE d.scan_date END
WHERE d.rn = 1
ORDER BY d.scan_date
"""


def load_data():
    conn = None  # via get_session()
    conn.row_factory = dict
    rows = conn.execute(LOAD_SQL).fetchall()
    conn.close()
    data = []
    for r in rows:
        data.append(dict(r))
    print(f"Loaded {len(data)} rows, dates {data[0]['scan_date']} to {data[-1]['scan_date']}")
    return data


# ─── Feature + Config Definitions ────────────────────────────────────────────

# All configs to test
CONFIGS = {
    # Group A — Current vs Lean
    "A1: 8feat bw=0.8 (prod)": {
        "features": ["distance_from_20d_high", "atr_pct", "volume_ratio", "momentum_20d",
                      "atr_risk", "crude_close", "gold_close", "breadth_above_20d"],
        "bw": 0.8,
    },
    "A2: 6feat bw=0.7 (lean)": {
        "features": ["atr_pct", "volume_ratio", "momentum_20d",
                      "crude_close", "gold_close", "breadth_above_20d"],
        "bw": 0.7,
    },
    "A3: 6feat bw=0.6": {
        "features": ["atr_pct", "volume_ratio", "momentum_20d",
                      "crude_close", "gold_close", "breadth_above_20d"],
        "bw": 0.6,
    },
    "A4: 6feat bw=0.8": {
        "features": ["atr_pct", "volume_ratio", "momentum_20d",
                      "crude_close", "gold_close", "breadth_above_20d"],
        "bw": 0.8,
    },
    # Group B — Lean + candidate additions
    "B5: 7feat +mom5d bw=0.7": {
        "features": ["atr_pct", "volume_ratio", "momentum_20d",
                      "crude_close", "gold_close", "breadth_above_20d",
                      "momentum_5d"],
        "bw": 0.7,
    },
    "B6: 7feat +bdelta bw=0.7": {
        "features": ["atr_pct", "volume_ratio", "momentum_20d",
                      "crude_close", "gold_close", "breadth_above_20d",
                      "breadth_delta_5d"],
        "bw": 0.7,
    },
    "B7: 8feat +mom5d+bdelta bw=0.7": {
        "features": ["atr_pct", "volume_ratio", "momentum_20d",
                      "crude_close", "gold_close", "breadth_above_20d",
                      "momentum_5d", "breadth_delta_5d"],
        "bw": 0.7,
    },
    # Group C — Minimal
    "C8: 4feat macro bw=0.5": {
        "features": ["atr_pct", "crude_close", "gold_close", "breadth_above_20d"],
        "bw": 0.5,
    },
}


def extract_features(row, feature_names):
    """Extract feature vector from a row. Returns None if any feature is missing."""
    vals = []
    for f in feature_names:
        if f == "atr_risk":
            atr = row.get("atr_pct")
            vix = row.get("vix_at_signal")
            if atr is None or vix is None:
                return None
            vals.append(atr * vix / 20.0)
        else:
            v = row.get(f)
            if v is None:
                return None
            vals.append(float(v))
    return np.array(vals)


# ─── Gaussian Kernel Walk-Forward ─────────────────────────────────────────────

def run_walk_forward(data, config_name, config):
    """
    Expanding-window walk-forward.
    For each test date D, train on ALL dates before D.
    Returns per-date results.
    """
    feature_names = config["features"]
    bw = config["bw"]
    min_er = 0.0

    # Group rows by date
    by_date = defaultdict(list)
    for row in data:
        by_date[row["scan_date"]].append(row)
    dates = sorted(by_date.keys())

    # Pre-extract features for all rows (skip None)
    # Build a list of (date, feature_vec, outcome_5d, outcome_max_dd_5d) per valid row
    valid_rows = []
    skipped = 0
    for row in data:
        fv = extract_features(row, feature_names)
        if fv is None:
            skipped += 1
            continue
        valid_rows.append({
            "date": row["scan_date"],
            "fv": fv,
            "outcome_5d": row["outcome_5d"],
            "max_dd": row["outcome_max_dd_5d"],
        })

    # Group valid rows by date
    valid_by_date = defaultdict(list)
    for vr in valid_rows:
        valid_by_date[vr["date"]].append(vr)
    valid_dates = sorted(valid_by_date.keys())

    # Minimum training: 20 dates
    MIN_TRAIN_DATES = 20

    # Accumulate training data as expanding window
    all_results = []  # per-date results
    train_fvs = []
    train_outcomes = []

    date_idx = 0
    for di, d in enumerate(valid_dates):
        test_cands = valid_by_date[d]

        # Add all previous dates to training (expanding window)
        # On first iteration, collect dates < d
        if di == 0:
            # Nothing to train on
            continue

        # Ensure we have enough training dates
        # Count distinct training dates
        if di < MIN_TRAIN_DATES:
            continue

        # Build training arrays from all dates before this one
        # (We build incrementally for efficiency)
        if di == MIN_TRAIN_DATES:
            # First real test date: build full training set from first MIN_TRAIN_DATES dates
            train_fvs = []
            train_outcomes = []
            for prev_d in valid_dates[:di]:
                for vr in valid_by_date[prev_d]:
                    train_fvs.append(vr["fv"])
                    train_outcomes.append(vr["outcome_5d"])
        else:
            # Add previous date's data
            prev_d = valid_dates[di - 1]
            for vr in valid_by_date[prev_d]:
                train_fvs.append(vr["fv"])
                train_outcomes.append(vr["outcome_5d"])

        if len(train_fvs) < 30:
            continue

        train_X = np.array(train_fvs)
        train_y = np.array(train_outcomes)

        # Z-score normalize using training stats
        mu = train_X.mean(axis=0)
        sigma = train_X.std(axis=0)
        sigma[sigma < 1e-10] = 1.0  # avoid div-by-zero
        train_X_norm = (train_X - mu) / sigma

        # For each test candidate: compute E[R]
        selected = []
        all_test = []
        for vr in test_cands:
            test_fv_norm = (vr["fv"] - mu) / sigma
            dists = np.sqrt(np.sum((train_X_norm - test_fv_norm) ** 2, axis=1))
            weights = np.exp(-0.5 * (dists / bw) ** 2)
            w_sum = weights.sum()
            if w_sum < 1e-15:
                continue
            er = np.dot(weights, train_y) / w_sum
            n_eff = w_sum ** 2 / np.sum(weights ** 2)

            entry = {
                "date": d,
                "er": er,
                "n_eff": n_eff,
                "outcome_5d": vr["outcome_5d"],
                "max_dd": vr["max_dd"],
            }
            all_test.append(entry)
            if er > min_er:
                selected.append(entry)

        # Top-5 by E[R]
        selected_sorted = sorted(selected, key=lambda x: x["er"], reverse=True)
        top5 = selected_sorted[:5]

        all_results.append({
            "date": d,
            "n_test": len(all_test),
            "n_selected": len(selected),
            "selected": selected,
            "top5": top5,
            "all_test": all_test,
        })

    return all_results, skipped


def compute_metrics(picks):
    """Compute WR, mean return, SL rate from a list of picks."""
    if not picks:
        return {"wr": 0, "mean_ret": 0, "sl_rate": 0, "n": 0}
    outcomes = [p["outcome_5d"] for p in picks]
    wins = sum(1 for o in outcomes if o > 0)
    sl_hits = sum(1 for p in picks if p["max_dd"] is not None and p["max_dd"] < -3.0)
    return {
        "wr": 100.0 * wins / len(outcomes),
        "mean_ret": np.mean(outcomes),
        "sl_rate": 100.0 * sl_hits / len(picks),
        "n": len(picks),
    }


def compute_monthly_breakdown(picks):
    """Group picks by YYYY-MM and compute metrics per month."""
    by_month = defaultdict(list)
    for p in picks:
        ym = p["date"][:7]
        by_month[ym].append(p)
    result = {}
    for ym in sorted(by_month.keys()):
        result[ym] = compute_metrics(by_month[ym])
    return result


def compute_risk_metrics(picks):
    """Worst month WR, worst month return, max consecutive losses."""
    monthly = compute_monthly_breakdown(picks)
    if not monthly:
        return {"worst_month_wr": 0, "worst_month_ret": 0, "max_consec_loss": 0}

    worst_wr = min(m["wr"] for m in monthly.values())
    worst_ret = min(m["mean_ret"] for m in monthly.values())

    # Max consecutive losses
    max_cl = 0
    cl = 0
    for p in sorted(picks, key=lambda x: x["date"]):
        if p["outcome_5d"] <= 0:
            cl += 1
            max_cl = max(max_cl, cl)
        else:
            cl = 0

    return {
        "worst_month_wr": worst_wr,
        "worst_month_ret": worst_ret,
        "max_consec_loss": max_cl,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    data = load_data()
    print(f"Total rows loaded: {len(data)}\n")

    results = {}
    for cname, cfg in CONFIGS.items():
        print(f"Running: {cname} ...")
        res, skipped = run_walk_forward(data, cname, cfg)
        all_selected = []
        all_top5 = []
        total_tested = 0
        for dr in res:
            all_selected.extend(dr["selected"])
            all_top5.extend(dr["top5"])
            total_tested += dr["n_test"]

        results[cname] = {
            "per_date": res,
            "all_selected": all_selected,
            "all_top5": all_top5,
            "total_tested": total_tested,
            "skipped": skipped,
        }
        m = compute_metrics(all_selected)
        t5 = compute_metrics(all_top5)
        print(f"  Selected: n={m['n']}, WR={m['wr']:.1f}%, meanR={m['mean_ret']:.3f}%, SL={m['sl_rate']:.1f}%")
        print(f"  Top-5:    n={t5['n']}, WR={t5['wr']:.1f}%, meanR={t5['mean_ret']:.3f}%, SL={t5['sl_rate']:.1f}%")
        print(f"  Skipped {skipped} rows (missing features), tested {total_tested}")
        print()

    # ══════════════════════════════════════════════════════════════════════
    # SUMMARY TABLE
    # ══════════════════════════════════════════════════════════════════════
    print("=" * 110)
    print("SUMMARY TABLE — All Configs (ranked by Top-5 WR, then mean return)")
    print("=" * 110)
    header = f"{'Config':<35} {'Sel-N':>6} {'Sel-WR':>7} {'Sel-MR':>8} {'Sel-SL':>7} | {'T5-N':>5} {'T5-WR':>7} {'T5-MR':>8} {'T5-SL':>7}"
    print(header)
    print("-" * 110)

    # Rank by Top-5 WR, then by mean return
    ranked = sorted(results.keys(),
                    key=lambda c: (compute_metrics(results[c]["all_top5"])["wr"],
                                   compute_metrics(results[c]["all_top5"])["mean_ret"]),
                    reverse=True)

    for cname in ranked:
        r = results[cname]
        m = compute_metrics(r["all_selected"])
        t5 = compute_metrics(r["all_top5"])
        print(f"{cname:<35} {m['n']:>6} {m['wr']:>6.1f}% {m['mean_ret']:>7.3f}% {m['sl_rate']:>6.1f}% | "
              f"{t5['n']:>5} {t5['wr']:>6.1f}% {t5['mean_ret']:>7.3f}% {t5['sl_rate']:>6.1f}%")

    # ══════════════════════════════════════════════════════════════════════
    # RISK METRICS
    # ══════════════════════════════════════════════════════════════════════
    print()
    print("=" * 100)
    print("RISK METRICS (Top-5 picks)")
    print("=" * 100)
    header2 = f"{'Config':<35} {'WorstMo-WR':>11} {'WorstMo-Ret':>12} {'MaxConsecLoss':>14}"
    print(header2)
    print("-" * 100)

    for cname in ranked:
        r = results[cname]
        risk = compute_risk_metrics(r["all_top5"])
        print(f"{cname:<35} {risk['worst_month_wr']:>10.1f}% {risk['worst_month_ret']:>11.3f}% {risk['max_consec_loss']:>14}")

    # ══════════════════════════════════════════════════════════════════════
    # HEAD-TO-HEAD: Baseline (A1) vs each lean config
    # ══════════════════════════════════════════════════════════════════════
    baseline_name = "A1: 8feat bw=0.8 (prod)"
    baseline = results[baseline_name]

    print()
    print("=" * 100)
    print(f"HEAD-TO-HEAD — {baseline_name} vs each config (per test date)")
    print("=" * 100)

    # Build per-date mean return for baseline (top-5)
    base_by_date = {}
    for dr in baseline["per_date"]:
        d = dr["date"]
        if dr["top5"]:
            base_by_date[d] = np.mean([p["outcome_5d"] for p in dr["top5"]])

    for cname in CONFIGS:
        if cname == baseline_name:
            continue
        alt = results[cname]
        alt_by_date = {}
        for dr in alt["per_date"]:
            d = dr["date"]
            if dr["top5"]:
                alt_by_date[d] = np.mean([p["outcome_5d"] for p in dr["top5"]])

        common_dates = set(base_by_date.keys()) & set(alt_by_date.keys())
        if not common_dates:
            print(f"  {cname}: no overlapping dates")
            continue
        alt_wins = sum(1 for d in common_dates if alt_by_date[d] > base_by_date[d])
        base_wins = sum(1 for d in common_dates if base_by_date[d] > alt_by_date[d])
        ties = len(common_dates) - alt_wins - base_wins
        alt_mean = np.mean([alt_by_date[d] for d in common_dates])
        base_mean = np.mean([base_by_date[d] for d in common_dates])
        print(f"  vs {cname:<33} | Alt wins: {alt_wins:>3} | Base wins: {base_wins:>3} | Ties: {ties:>3} | "
              f"Alt avg: {alt_mean:>+.3f}% | Base avg: {base_mean:>+.3f}%")

    # ══════════════════════════════════════════════════════════════════════
    # MONTHLY BREAKDOWN — Best config vs Baseline
    # ══════════════════════════════════════════════════════════════════════
    best_config_name = ranked[0]

    print()
    print("=" * 100)
    print(f"MONTHLY BREAKDOWN — Top-5 picks")
    print(f"  Baseline: {baseline_name}")
    print(f"  Best:     {best_config_name}")
    print("=" * 100)

    base_monthly = compute_monthly_breakdown(baseline["all_top5"])
    best_monthly = compute_monthly_breakdown(results[best_config_name]["all_top5"])

    all_months = sorted(set(list(base_monthly.keys()) + list(best_monthly.keys())))

    print(f"{'Month':<10} | {'Base-N':>6} {'Base-WR':>8} {'Base-MR':>9} {'Base-SL':>8} | "
          f"{'Best-N':>6} {'Best-WR':>8} {'Best-MR':>9} {'Best-SL':>8}")
    print("-" * 100)

    for ym in all_months:
        bm = base_monthly.get(ym, {"n": 0, "wr": 0, "mean_ret": 0, "sl_rate": 0})
        em = best_monthly.get(ym, {"n": 0, "wr": 0, "mean_ret": 0, "sl_rate": 0})
        print(f"{ym:<10} | {bm['n']:>6} {bm['wr']:>7.1f}% {bm['mean_ret']:>8.3f}% {bm['sl_rate']:>7.1f}% | "
              f"{em['n']:>6} {em['wr']:>7.1f}% {em['mean_ret']:>8.3f}% {em['sl_rate']:>7.1f}%")

    # ══════════════════════════════════════════════════════════════════════
    # ADDITIONAL: Selected-all monthly for baseline vs best
    # ══════════════════════════════════════════════════════════════════════
    print()
    print("=" * 100)
    print(f"MONTHLY BREAKDOWN — ALL selected (E[R]>0) picks")
    print(f"  Baseline: {baseline_name}")
    print(f"  Best:     {best_config_name}")
    print("=" * 100)

    base_monthly_all = compute_monthly_breakdown(baseline["all_selected"])
    best_monthly_all = compute_monthly_breakdown(results[best_config_name]["all_selected"])

    all_months2 = sorted(set(list(base_monthly_all.keys()) + list(best_monthly_all.keys())))

    print(f"{'Month':<10} | {'Base-N':>6} {'Base-WR':>8} {'Base-MR':>9} {'Base-SL':>8} | "
          f"{'Best-N':>6} {'Best-WR':>8} {'Best-MR':>9} {'Best-SL':>8}")
    print("-" * 100)

    for ym in all_months2:
        bm = base_monthly_all.get(ym, {"n": 0, "wr": 0, "mean_ret": 0, "sl_rate": 0})
        em = best_monthly_all.get(ym, {"n": 0, "wr": 0, "mean_ret": 0, "sl_rate": 0})
        print(f"{ym:<10} | {bm['n']:>6} {bm['wr']:>7.1f}% {bm['mean_ret']:>8.3f}% {bm['sl_rate']:>7.1f}% | "
              f"{em['n']:>6} {em['wr']:>7.1f}% {em['mean_ret']:>8.3f}% {em['sl_rate']:>7.1f}%")

    # ══════════════════════════════════════════════════════════════════════
    # Selectivity analysis
    # ══════════════════════════════════════════════════════════════════════
    print()
    print("=" * 100)
    print("SELECTIVITY — How many does each config pick vs total candidates")
    print("=" * 100)
    print(f"{'Config':<35} {'Tested':>8} {'Selected':>9} {'Sel%':>7} {'Top5':>6} {'Top5%':>7}")
    print("-" * 100)
    for cname in ranked:
        r = results[cname]
        sel_n = len(r["all_selected"])
        t5_n = len(r["all_top5"])
        tested = r["total_tested"]
        sel_pct = 100.0 * sel_n / tested if tested else 0
        t5_pct = 100.0 * t5_n / tested if tested else 0
        print(f"{cname:<35} {tested:>8} {sel_n:>9} {sel_pct:>6.1f}% {t5_n:>6} {t5_pct:>6.1f}%")

    # ══════════════════════════════════════════════════════════════════════
    # Baseline metrics on ALL candidates (no selection) for reference
    # ══════════════════════════════════════════════════════════════════════
    print()
    base_all = []
    for dr in baseline["per_date"]:
        base_all.extend(dr["all_test"])
    base_all_m = compute_metrics(base_all)
    print(f"BASELINE (no kernel, all candidates): n={base_all_m['n']}, WR={base_all_m['wr']:.1f}%, "
          f"meanR={base_all_m['mean_ret']:.3f}%, SL={base_all_m['sl_rate']:.1f}%")


if __name__ == "__main__":
    main()
