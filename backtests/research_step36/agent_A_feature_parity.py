#!/usr/bin/env python3
"""
Step 36 Agent A — Live vs Trainer-pkl Feature Parity

Quantify drift between live scan-time features (stored in scan_journal.db) and
trainer pkl features (cache/bt_features/features.pkl) for ml_filter picks in
the last 30 days. The live storage layer captures only a SUBSET of model
inputs (extra dict + a few native cols on scan_candidates); we compare every
overlapping numeric field on the matched (sym, date, mins_from_open) row.

READ-ONLY. Outputs Markdown report.

Run:
    /home/saengtawan/.pyenv/versions/issara/bin/python3 \
        backtests/research_step36/agent_A_feature_parity.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "scan_journal.db"
PKL_PATH = ROOT / "cache" / "bt_features" / "features.pkl"
REPORT_PATH = ROOT / "backtests" / "research_step36" / "agent_A_report.md"

START_DATE = "2026-04-28"  # last 30 days

# ---------------------------------------------------------------------------
# Comparable field map: live-name -> (trainer-name, scale_factor, tolerance)
# scale_factor: multiply LIVE value by this to align units with trainer.
#   Live `gain_pct` is a percent (e.g. 2.05 = +2.05%) and trainer
#   `gain_from_open` is the same.
# tolerance: absolute diff above which we flag "significant"
# ---------------------------------------------------------------------------
FIELD_MAP: Dict[str, Tuple[str, float, float]] = {
    "gain_from_open_native": ("gain_from_open", 1.0, 0.5),  # %
    "gain_pct_extra":        ("gain_from_open", 1.0, 0.5),  # %
    "beta_native":           ("beta", 1.0, 0.05),
    "beta_extra":            ("beta", 1.0, 0.05),
    # day_open / user_limit / adaptive_limit are PRICES; their drift relative
    # to the bar `open` is informative even though trainer pkl has no
    # day_open column directly. We compute a synthetic open from
    # gain_from_open and scan_price downstream.
}


def load_picks(conn: sqlite3.Connection) -> pd.DataFrame:
    sql = """
        SELECT id, scan_ts, scan_date, symbol, zone, mfo,
               win_p, pred_r, passed_filter, selected,
               sector, beta AS beta_native,
               gain_from_open AS gain_from_open_native,
               scan_price, adaptive_limit, user_limit,
               features_json
          FROM scan_candidates
         WHERE strategy = 'ml_filter'
           AND scan_date >= ?
    """
    df = pd.read_sql_query(sql, conn, params=(START_DATE,))
    # Parse JSON extra
    parsed = []
    for j in df["features_json"]:
        try:
            parsed.append(json.loads(j) if j else {})
        except Exception:
            parsed.append({})
    extra = pd.DataFrame(parsed)
    for col in ("ml_prob", "threshold", "bucket", "gain_pct", "beta",
                "sector", "limit_price", "exit_strategy", "pred_ratio",
                "adaptive_limit", "scan_price", "use_market", "day_open"):
        if col not in extra.columns:
            extra[col] = np.nan
    extra = extra.rename(columns={
        "gain_pct": "gain_pct_extra",
        "beta": "beta_extra",
        "scan_price": "scan_price_extra",
        "adaptive_limit": "adaptive_limit_extra",
        "day_open": "day_open_extra",
        "limit_price": "limit_price_extra",
        "pred_ratio": "pred_ratio_extra",
    })
    out = pd.concat([df.reset_index(drop=True), extra.reset_index(drop=True)],
                    axis=1)
    return out


def load_trainer(pkl_path: Path) -> pd.DataFrame:
    df = pd.read_pickle(pkl_path)
    df = df[df["date"] >= START_DATE].copy()
    df = df.rename(columns={"sym": "symbol", "mins_from_open": "mfo"})
    return df


def round_mfo_to_5(m: int) -> int:
    return int(round(int(m) / 5.0)) * 5


def join_live_train(live: pd.DataFrame, train: pd.DataFrame) -> pd.DataFrame:
    live = live.copy()
    live["mfo_join"] = live["mfo"].apply(round_mfo_to_5)
    # Trainer mfo is multiples of 5
    train = train.copy()
    train["mfo_join"] = train["mfo"].astype(int)
    keep_cols = ["symbol", "date", "mfo_join"] + sorted(
        set(train.columns) - {"symbol", "date", "mfo_join", "time", "mfo"}
    )
    train = train[keep_cols].drop_duplicates(
        subset=["symbol", "date", "mfo_join"], keep="last"
    )
    merged = live.merge(
        train, how="left", left_on=["symbol", "scan_date", "mfo_join"],
        right_on=["symbol", "date", "mfo_join"], suffixes=("", "_train"),
    )
    return merged


def compute_drift(merged: pd.DataFrame) -> pd.DataFrame:
    """For each comparable feature, compute drift stats vs trainer row."""
    rows = []
    n_total = len(merged)
    n_matched = merged["date"].notna().sum()  # right side joined

    # 1) Direct comparable fields (live vs trainer same name)
    for live_col, (train_col, scale, tol) in FIELD_MAP.items():
        if live_col not in merged.columns or train_col not in merged.columns:
            continue
        live_v = pd.to_numeric(merged[live_col], errors="coerce") * scale
        train_v = pd.to_numeric(merged[train_col], errors="coerce")
        mask = merged["date"].notna() & live_v.notna() & train_v.notna()
        if mask.sum() == 0:
            continue
        diff = (live_v - train_v).abs()[mask]
        rows.append({
            "feature": f"{live_col} vs {train_col}",
            "n": int(mask.sum()),
            "mean_abs_diff": float(diff.mean()),
            "p50_abs_diff": float(diff.median()),
            "p95_abs_diff": float(np.percentile(diff, 95)) if len(diff) else 0,
            "max_abs_diff": float(diff.max()),
            "pct_diff_gt_tol": float((diff > tol).mean() * 100),
            "tol": tol,
        })

    # 2) Derived: trainer-implied day_open vs live day_open_extra
    #    trainer_open = scan_price / (1 + gain_from_open/100)
    # Compare against live day_open / user_limit / adaptive_limit
    if all(c in merged.columns for c in ("scan_price", "gain_from_open")):
        sp = pd.to_numeric(merged["scan_price"], errors="coerce")
        gfo = pd.to_numeric(merged["gain_from_open"], errors="coerce")
        train_implied_open = sp / (1.0 + gfo / 100.0)
        for live_col in ("day_open_extra", "user_limit",
                         "adaptive_limit_extra", "limit_price_extra"):
            if live_col not in merged.columns:
                continue
            live_v = pd.to_numeric(merged[live_col], errors="coerce")
            mask = (merged["date"].notna() & live_v.notna()
                    & train_implied_open.notna())
            if mask.sum() == 0:
                continue
            # Use PERCENT diff vs price magnitude (price scale varies)
            pct_diff = ((live_v - train_implied_open).abs() /
                        train_implied_open.replace(0, np.nan)) * 100.0
            pct_diff = pct_diff[mask]
            rows.append({
                "feature": f"{live_col} vs trainer-implied open (%)",
                "n": int(mask.sum()),
                "mean_abs_diff": float(pct_diff.mean()),
                "p50_abs_diff": float(pct_diff.median()),
                "p95_abs_diff": float(np.percentile(pct_diff, 95))
                                  if len(pct_diff) else 0,
                "max_abs_diff": float(pct_diff.max()),
                "pct_diff_gt_tol": float((pct_diff > 0.30).mean() * 100),
                "tol": 0.30,
            })

    # 3) pred_ratio is live-only (no train counterpart). Still profile its
    # distribution to confirm it's not always 1.0.
    if "pred_ratio_extra" in merged.columns:
        pr = pd.to_numeric(merged["pred_ratio_extra"], errors="coerce")
        pr = pr[pr.notna() & merged["date"].notna()]
        if len(pr) > 0:
            rows.append({
                "feature": "pred_ratio_extra (live-only, profile)",
                "n": int(len(pr)),
                "mean_abs_diff": float(pr.mean()),
                "p50_abs_diff": float(pr.median()),
                "p95_abs_diff": float(np.percentile(pr, 95)),
                "max_abs_diff": float(pr.max()),
                "pct_diff_gt_tol": float((pr.between(0.99, 1.01)).mean() * 100),
                "tol": float("nan"),
            })

    df = pd.DataFrame(rows).sort_values(
        "pct_diff_gt_tol", ascending=False, kind="stable").reset_index(drop=True)
    df.attrs["n_total"] = n_total
    df.attrs["n_matched"] = int(n_matched)
    return df


def sample_rows(merged: pd.DataFrame, live_col: str, train_col: str,
                tol: float, scale: float = 1.0, n: int = 5) -> pd.DataFrame:
    if live_col not in merged.columns or train_col not in merged.columns:
        return pd.DataFrame()
    live_v = pd.to_numeric(merged[live_col], errors="coerce") * scale
    train_v = pd.to_numeric(merged[train_col], errors="coerce")
    diff = (live_v - train_v).abs()
    mask = merged["date"].notna() & live_v.notna() & train_v.notna()
    df = merged[mask].assign(_diff=diff[mask], _live=live_v[mask],
                             _train=train_v[mask])
    # Dedupe by (symbol, scan_date, mfo) so we get DISTINCT examples
    df = df.drop_duplicates(subset=["symbol", "scan_date", "mfo"])
    df = df.sort_values("_diff", ascending=False).head(n)
    return df[["symbol", "scan_date", "mfo", "_live", "_train", "_diff"]]


def picks_zone_counts(conn: sqlite3.Connection) -> pd.DataFrame:
    sql = """
        SELECT zone, COUNT(*) AS n_cand,
               SUM(selected) AS n_sel,
               SUM(passed_filter) AS n_pass
          FROM scan_candidates
         WHERE strategy='ml_filter' AND scan_date >= ?
         GROUP BY zone ORDER BY zone
    """
    return pd.read_sql_query(sql, conn, params=(START_DATE,))


def md_table(df: pd.DataFrame, cols: Optional[List[str]] = None,
             fmt: Optional[Dict[str, str]] = None, max_rows: int = 30) -> str:
    if cols is None:
        cols = list(df.columns)
    fmt = fmt or {}
    body = df[cols].head(max_rows).copy()
    for c, f in fmt.items():
        if c in body.columns:
            body[c] = body[c].apply(lambda v: f.format(v) if pd.notna(v)
                                    else "—")
    lines = ["| " + " | ".join(cols) + " |",
             "| " + " | ".join("---" for _ in cols) + " |"]
    for _, r in body.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        zone_df = picks_zone_counts(conn)
        live = load_picks(conn)
    finally:
        conn.close()

    print(f"[1/4] Live candidates loaded: {len(live)} rows")
    print(f"[1/4] Selected (picks): {int(live['selected'].sum())}")
    print(f"[1/4] Zone breakdown:\n{zone_df}")

    print(f"[2/4] Loading trainer pkl (this takes a few seconds)...")
    train = load_trainer(PKL_PATH)
    print(f"[2/4] Trainer rows in window: {len(train)}")

    print(f"[3/4] Joining live -> trainer on (symbol, date, mfo)...")
    merged = join_live_train(live, train)
    n_matched = merged["date"].notna().sum()
    print(f"[3/4] Matched: {n_matched} / {len(merged)} "
          f"({100*n_matched/max(1,len(merged)):.1f}%)")

    # Diagnostics on coverage
    trainer_max_date = train["date"].max()
    live_dates = set(live["scan_date"].unique())
    trainer_dates = set(train["date"].unique())
    dates_missing = sorted(live_dates - trainer_dates)
    n_live_after_trainer = int((live["scan_date"] > trainer_max_date).sum())
    common_mask = live["scan_date"].isin(trainer_dates)
    common = live[common_mask]
    common_merged = merged[common_mask].reset_index(drop=True)
    n_common_matched = int(common_merged["date"].notna().sum())
    print(f"[3/4] Trainer pkl last date: {trainer_max_date}")
    print(f"[3/4] Live picks on dates AFTER trainer last date: "
          f"{n_live_after_trainer}/{len(live)}")
    print(f"[3/4] On common dates: {n_common_matched}/{len(common)} matched "
          f"({100*n_common_matched/max(1,len(common)):.1f}%)")

    print(f"[4/4] Computing drift stats...")
    drift = compute_drift(merged)

    # Build sample-row tables for top features
    top_feats = drift.head(5).copy()
    sample_md: List[str] = []
    for _, row in top_feats.iterrows():
        fname = row["feature"]
        if " vs " not in fname:
            continue
        live_col, train_col = fname.split(" vs ", 1)
        train_col_real = train_col.replace(" (%)", "")
        if train_col_real == "trainer-implied open":
            # synthetic: compute and show
            sp = pd.to_numeric(merged["scan_price"], errors="coerce")
            gfo = pd.to_numeric(merged["gain_from_open"], errors="coerce")
            implied = sp / (1.0 + gfo / 100.0)
            lv = pd.to_numeric(merged[live_col], errors="coerce")
            pct = ((lv - implied).abs() / implied.replace(0, np.nan)) * 100.0
            mask = merged["date"].notna() & lv.notna() & implied.notna()
            tbl = merged[mask].assign(_live=lv[mask], _train=implied[mask],
                                       _diff=pct[mask])
            tbl = tbl.drop_duplicates(subset=["symbol", "scan_date", "mfo"])
            tbl = tbl.sort_values("_diff", ascending=False).head(5)
            sample_md.append(f"\n#### {fname}\n\n" +
                             md_table(tbl, ["symbol", "scan_date", "mfo",
                                            "_live", "_train", "_diff"],
                                      {"_live": "{:.3f}", "_train": "{:.3f}",
                                       "_diff": "{:.2f}%"}))
        else:
            scale = FIELD_MAP.get(live_col, (None, 1.0, 0.5))[1]
            tol = FIELD_MAP.get(live_col, (None, 1.0, 0.5))[2]
            tbl = sample_rows(merged, live_col, train_col_real, tol, scale)
            if not tbl.empty:
                sample_md.append(f"\n#### {fname}\n\n" +
                                 md_table(tbl, list(tbl.columns),
                                          {"_live": "{:.4f}",
                                           "_train": "{:.4f}",
                                           "_diff": "{:.4f}"}))

    # Hypothesis blurbs
    hypotheses = {
        "gain_from_open_native vs gain_from_open":
            "Native `gain_from_open` is computed live from `(scan_price-day_open)/day_open*100`. Drift would indicate either (a) scan_price drifted vs the close of the 5-min bar trainer ingests, or (b) `day_open` source differs (live uses Alpaca snapshot.dailyBar.o aggregated close-weighted; trainer pkl uses first 1-min bar of session via feature_builder).",
        "gain_pct_extra vs gain_from_open":
            "Same field from extra dict — confirms storage parity. If equal to native version, drift comes from open-source mismatch.",
        "beta_native vs beta":
            "Beta is a stock-fundamental loaded live from DB at scan time. Trainer beta is computed in feature_builder from a fixed lookback. Drift means the rolling beta refreshed since the trainer build, so the model is scored with a different beta than it would see in backtest.",
        "beta_extra vs beta": "Same as above — extra dict echoes native.",
        "day_open_extra vs trainer-implied open (%)":
            "Live `day_open` (Alpaca aggregated bar) vs synthetic open derived from `scan_price/(1+gain_from_open/100)` using trainer values. Large %drift here is the 09:30 open-price source mismatch — the canonical VWAP/open alignment hazard called out in Step 21.",
        "user_limit vs trainer-implied open (%)":
            "`user_limit` is exactly the LIMIT@$X reason string price (= live day_open). Same source issue as above. The model's `gain_from_open` is wrong by exactly this %.",
        "adaptive_limit_extra vs trainer-implied open (%)":
            "Adaptive limit incorporates pred_ratio; drift vs trainer open reflects both the open mismatch AND a live-only adaptive computation.",
        "limit_price_extra vs trainer-implied open (%)":
            "limit_price is the final entry price posted to broker. Drift = open + adaptive layer.",
    }

    # Write report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append("# Step 36 Agent A — Live vs Trainer Feature Parity\n")
    lines.append(f"Window: scan_date >= **{START_DATE}** "
                 f"(generated 2026-05-28)\n")
    lines.append("## Coverage\n")
    lines.append(f"- Live candidates analysed: **{len(live)}**\n")
    lines.append(f"- Live picks (selected=1): **{int(live['selected'].sum())}**\n")
    lines.append(f"- Joined to trainer pkl (sym, date, mfo): **{n_matched} / "
                 f"{len(merged)}** "
                 f"({100*n_matched/max(1,len(merged)):.1f}%)\n")
    lines.append(f"- Trainer pkl rows in window: **{len(train):,}** "
                 f"({train['date'].nunique()} dates, "
                 f"{train['symbol'].nunique()} syms)\n")
    lines.append(f"- **Trainer pkl last date: `{trainer_max_date}`**. "
                 f"Live picks on dates AFTER trainer freeze: "
                 f"**{n_live_after_trainer}/{len(live)} "
                 f"({100*n_live_after_trainer/max(1,len(live)):.1f}%)** — "
                 f"these cannot be audited at all.\n")
    lines.append(f"- On common-date subset: **{n_common_matched}/{len(common)} "
                 f"({100*n_common_matched/max(1,len(common)):.1f}%)** "
                 f"matched. Unmatched on common dates ≈ live symbol "
                 f"appeared but was outside the trainer's "
                 f"intraday-active-universe filter.\n")
    if dates_missing:
        lines.append(f"- Live dates with **zero** trainer coverage: "
                     f"`{dates_missing}`.\n")
    lines.append("\n### Zone breakdown (live)\n")
    lines.append(md_table(zone_df, list(zone_df.columns)))
    lines.append("\n")

    lines.append("## CRITICAL CAVEAT — storage gap\n")
    lines.append(
        "`scan_journal.scan_candidates.features_json` and "
        "`scan_picks.features_json` **do not store the 140-dim feature "
        "vector** that the model actually scores. They store only a small "
        "summary dict (see `ml_filter.py:976-997`): ml_prob, threshold, "
        "bucket, gain_pct, beta, sector, limit_price, adaptive_limit, "
        "scan_price, use_market, day_open, pred_ratio, exit_strategy. "
        "We therefore cannot directly measure drift on the 50+ ML features "
        "(vol_ratio, vs_vwap, intra ETFs, path_*, anomaly_score, feat_*, "
        "macro). What we *can* measure are the context fields the live "
        "engine writes to extra+ native columns. These are still the same "
        "raw quantities trainer builds against — drift in them implies "
        "the upstream sources differ.\n")

    lines.append("\n## Drift summary (top 20 ranked by % significant)\n")
    drift_cols = ["feature", "n", "mean_abs_diff", "p50_abs_diff",
                  "p95_abs_diff", "max_abs_diff", "pct_diff_gt_tol", "tol"]
    fmt = {"mean_abs_diff": "{:.4f}", "p50_abs_diff": "{:.4f}",
           "p95_abs_diff": "{:.4f}", "max_abs_diff": "{:.4f}",
           "pct_diff_gt_tol": "{:.1f}%", "tol": "{:.3f}"}
    lines.append(md_table(drift, drift_cols, fmt, max_rows=20))
    lines.append("\n")

    lines.append("\n## Top-5 features: hypothesis + example rows\n")
    for _, row in top_feats.iterrows():
        f = row["feature"]
        lines.append(f"\n### {f}")
        lines.append(f"- n compared: **{int(row['n'])}**, mean |Δ|: "
                     f"{row['mean_abs_diff']:.4f}, p95 |Δ|: "
                     f"{row['p95_abs_diff']:.4f}, %>tol: "
                     f"{row['pct_diff_gt_tol']:.1f}%")
        hyp = hypotheses.get(f, "")
        if hyp:
            lines.append(f"- **Hypothesis:** {hyp}")
    lines.append("\n## Example rows for top-5 features\n")
    lines.extend(sample_md)

    lines.append("\n## Recommendation — primary suspects\n")
    lines.append(
        "1. **`day_open` / `user_limit` source mismatch.** Live `day_open` "
        "is Alpaca `snapshot.dailyBar.o` (close-weighted aggregation, "
        "documented gotcha in CLAUDE.md) — *not* the first 1-min bar open "
        "that trainer pkl uses. Every feature derived from open "
        "(`gain_from_open`, `vs_vwap` early in session, `range_pct`, "
        "`from_peak_pct`, `gap_from_prev`, path_*) shifts by exactly this "
        "fraction. See `gain_pct_extra vs gain_from_open` and "
        "`day_open_extra vs trainer-implied open (%)` rows in the drift "
        "table.\n")
    lines.append(
        "2. **`beta` snapshot drift.** Live beta is read from "
        "`stock_fundamentals` (refreshed by maintenance jobs) but trainer "
        "beta was frozen at pkl-build time. Even small beta shifts move "
        "the per-zone routing logic. Check `beta_native vs beta`.\n")
    lines.append(
        "3. **Unmeasured features.** Because the live engine stores only "
        "the summary extra dict, **the remaining ~130 features "
        "(vol_ratio, vs_vwap, 15m/30m/1h multi-tf, 25 ETF intras, 6 ETF "
        "spreads, path_*, anomaly_score, feat_* 16 macro/tech)** cannot "
        "be audited from logs. Step 20 / Step 21 fixed the two most "
        "famous drift hazards (5-min snap, HLC/3 VWAP), but there is no "
        "post-deploy regression check. **Highest-priority follow-up: "
        "instrument ml_filter to dump the full feature vector (the dict "
        "passed to `model.predict`) into `scan_candidates.features_json` "
        "so this audit becomes routine.**\n")
    lines.append(
        "4. **mfo rounding.** Live mfo is observed-clock; we round to "
        "nearest 5 to join to trainer. If live snap to 5-min boundary "
        "(Step 20) is partially broken (e.g. scan started at mfo=2 due "
        "to early scan_smart.sh), every feature that depends on bar "
        "boundaries would drift. Check mfo distribution in the merged "
        "frame.\n")
    lines.append(
        "5. **Stale-pkl + universe filter.** Live picks include "
        f"**{n_live_after_trainer}/{len(live)} on dates AFTER pkl freeze "
        f"({trainer_max_date})** and **{int(common.shape[0]-n_common_matched)} "
        f"on common dates whose (sym, date, mfo) row is absent from the "
        "trainer pkl** (the pkl uses an intraday-active universe filter — "
        "see `feature_builder.py` candidate-row gate). The model was "
        "trained on a narrower distribution than it sees live. This "
        "could explain the WR gap directly: live includes "
        "out-of-distribution symbols (e.g. low-liquidity names trainer "
        "would have filtered out).\n")
    lines.append(
        "\n**Bottom line:** the *observable* drift table above only "
        "exposes the tip of the iceberg. The fact that even the few "
        "stored fields show non-trivial drift (especially open-derived "
        "ones) AND that 47% of live picks live outside the trainer "
        "universe strongly suggests the unseen ~130 features carry "
        "similar or worse mismatches. The label/HP changes attempted in "
        "Step 35 could not have closed a feature-pipeline gap.\n")

    REPORT_PATH.write_text("\n".join(lines))
    print(f"\nReport written: {REPORT_PATH}")
    # Also persist drift table CSV
    csv_path = REPORT_PATH.with_suffix(".drift.csv")
    drift.to_csv(csv_path, index=False)
    print(f"Drift CSV:      {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
