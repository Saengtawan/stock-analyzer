"""
Agent B — day_open mismatch quantification (Step 36 research)

Compares three sources of "day_open" used by ml_filter:
  1. LIVE     : value used by scanner at pick time (back-computed from
                scan_candidates.scan_price / (1 + gain_from_open/100));
                cross-checked against reason text 'LIMIT@$X' when present.
  2. BAR5M    : open of first 5-min bar with time_et == '09:30' in
                data/trade_history.db / intraday_bars_5m  (production source
                used by feature_builder.py during training).
  3. BAR1M    : open of em=570 bar (09:30 ET) in cache/wf_1min_bars.db.
  4. (Trainer pkl 'day_open' not stored directly; cache/bt_features/features.pkl
     stores gain_from_open which derives from the bar_0930 open per
     feature_builder.py:343-347 — i.e. BAR5M is the trainer source of truth.)

Outputs CSV + summary dict to stdout for the markdown report.
READ-ONLY against all databases. Saves no DB changes.
"""

import sqlite3
import json
import os
import sys
import math
import re
from collections import defaultdict
from statistics import mean, median

import pandas as pd

ROOT = "/home/saengtawan/work/project/cc/stock-analyzer"
SCAN_DB = f"{ROOT}/data/scan_journal.db"
TRADE_DB = f"{ROOT}/data/trade_history.db"
ONE_MIN_DB = f"{ROOT}/cache/wf_1min_bars.db"
PKL = f"{ROOT}/cache/bt_features/features.pkl"
OUT_CSV = f"{ROOT}/backtests/research_step36/agent_B_day_open.csv"

START_DATE = "2026-04-28"
DRIFT_THRESHOLD_PP = 0.2  # pp diff considered "material"


def fetch_picks():
    con = sqlite3.connect(SCAN_DB)
    con.row_factory = sqlite3.Row
    # Join picks → candidates (selected=1) for zone + scan_price + gain_from_open
    # Then LEFT JOIN pick_outcomes for win/loss correlation.
    sql = """
    SELECT
      p.id           AS pick_id,
      p.scan_ts      AS scan_ts,
      p.scan_date    AS scan_date,
      p.symbol       AS symbol,
      p.entry        AS entry,
      p.ml_prob      AS ml_prob,
      p.reason       AS reason,
      c.zone         AS zone,
      c.mfo          AS mfo,
      c.gain_from_open  AS gain_from_open,
      c.scan_price   AS scan_price,
      c.user_limit   AS user_limit,
      o.pnl_pct      AS pnl_pct,
      o.outcome_label AS outcome_label,
      o.exit_reason  AS exit_reason
    FROM scan_picks p
    LEFT JOIN scan_candidates c
      ON c.pick_id = p.id AND c.selected = 1
    LEFT JOIN pick_outcomes o
      ON o.pick_id = p.id
    WHERE p.strategy = 'ml_filter'
      AND p.scan_date >= ?
    ORDER BY p.scan_date, p.scan_ts, p.symbol
    """
    rows = [dict(r) for r in con.execute(sql, (START_DATE,))]
    con.close()
    return rows


_LIMIT_RE = re.compile(r"LIMIT@\$([0-9]+\.?[0-9]*)")


def parse_limit_from_reason(reason):
    if not reason:
        return None
    m = _LIMIT_RE.search(reason)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def fetch_bar5m_open(sym, date):
    """Open of first 5-min bar at time_et == '09:30'."""
    con = sqlite3.connect(TRADE_DB)
    cur = con.execute(
        "SELECT open FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et='09:30' LIMIT 1",
        (sym, date),
    )
    r = cur.fetchone()
    con.close()
    return r[0] if r else None


def fetch_bar1m_open(sym, date):
    """Open at em=570 (09:30 ET)."""
    con = sqlite3.connect(ONE_MIN_DB)
    cur = con.execute(
        "SELECT o FROM bars WHERE sym=? AND date=? AND em=570 LIMIT 1",
        (sym, date),
    )
    r = cur.fetchone()
    con.close()
    return r[0] if r else None


def load_pkl_index():
    """Return dict {(sym,date,mins_from_open) → first matching gain_from_open}
    used to derive trainer-side day_open.

    For training, day_open = bar5m_RTH open by construction
    (feature_builder.py:343-347). So this is mainly a sanity reference, not a
    third independent value. We still load it to confirm gain_from_open matches
    what live scanner thought.
    """
    print("[pkl] loading features.pkl (slow once) ...", file=sys.stderr)
    df = pd.read_pickle(PKL)
    # narrow to date >= START_DATE for speed
    df = df[df["date"] >= START_DATE].copy()
    df = df[["sym", "date", "mins_from_open", "gain_from_open", "range_pct", "gap_from_prev"]]
    df = df.rename(columns={"sym": "symbol"})
    # key by (symbol, date, mins_from_open)
    idx = {}
    for r in df.itertuples(index=False):
        idx[(r.symbol, r.date, int(r.mins_from_open))] = (
            r.gain_from_open,
            r.range_pct,
            r.gap_from_prev,
        )
    print(f"[pkl] loaded {len(idx):,} rows from {df['date'].min()}..{df['date'].max()}", file=sys.stderr)
    return idx


def main():
    picks = fetch_picks()
    print(f"Total picks since {START_DATE}: {len(picks)}", file=sys.stderr)

    # zone counts
    by_zone = defaultdict(int)
    for p in picks:
        by_zone[p["zone"] or "UNKNOWN"] += 1
    print("Per-zone counts:", dict(by_zone), file=sys.stderr)

    pkl_idx = load_pkl_index()

    rows = []
    for p in picks:
        sym = p["symbol"]
        date = p["scan_date"]
        gfo = p["gain_from_open"]  # %
        # scan_candidates.scan_price column is unpopulated (0/561 rows have it).
        # Use scan_picks.entry as the live scan price proxy (limit order entry,
        # which is the close of the last 5-min bar at scan time, ie a few cents
        # off the actual scan-time price but close enough for drift sign/mag).
        sp = p["scan_price"] if p.get("scan_price") else p["entry"]
        ul = p["user_limit"]  # often None for older rows; live "day_open"
        limit_from_reason = parse_limit_from_reason(p["reason"])

        # Derive LIVE day_open
        live_day_open = None
        if ul and ul > 0:
            live_day_open = float(ul)
        elif limit_from_reason:
            live_day_open = limit_from_reason
        elif sp and sp > 0 and gfo is not None:
            try:
                live_day_open = sp / (1.0 + gfo / 100.0)
            except Exception:
                live_day_open = None

        bar5m = fetch_bar5m_open(sym, date)
        bar1m = fetch_bar1m_open(sym, date)

        # Trainer pkl gain_from_open at same mfo as candidate
        mfo = p["mfo"]
        pkl_row = pkl_idx.get((sym, date, int(mfo) if mfo is not None else -1))
        if pkl_row is None:
            pkl_gfo = pkl_rng = pkl_gap = None
        else:
            pkl_gfo, pkl_rng, pkl_gap = pkl_row

        # Pairwise diffs in pp (relative to live)
        def pp_diff(a, b):
            if a is None or b is None or a <= 0:
                return None
            return (b - a) / a * 100.0

        d_live_vs_5m = pp_diff(live_day_open, bar5m) if live_day_open and bar5m else None
        d_live_vs_1m = pp_diff(live_day_open, bar1m) if live_day_open and bar1m else None
        d_5m_vs_1m = pp_diff(bar5m, bar1m) if bar5m and bar1m else None

        # What gain_from_open SHOULD have been using bar5m_RTH.
        # Method: implied_scan_price = live_day_open × (1 + live_gfo/100)
        #         corrected_gfo     = (implied_scan_price / bar5m - 1) × 100
        if (
            bar5m and bar5m > 0
            and live_day_open and live_day_open > 0
            and gfo is not None
        ):
            implied_scan_price = live_day_open * (1.0 + gfo / 100.0)
            corrected_gfo = (implied_scan_price / bar5m - 1.0) * 100.0
        else:
            corrected_gfo = None

        # Drift in gain_from_open feature (live − trainer correct view) in pp
        if corrected_gfo is not None and gfo is not None:
            gfo_drift_pp = gfo - corrected_gfo
        else:
            gfo_drift_pp = None

        # Most direct measure: live gfo vs pkl gfo at same (sym, date, mfo).
        # pkl gfo is computed using bar5m_RTH (training source of truth).
        if pkl_gfo is not None and gfo is not None:
            live_vs_pkl_gfo_pp = gfo - pkl_gfo
        else:
            live_vs_pkl_gfo_pp = None

        # Outcome label
        pnl = p["pnl_pct"]
        outcome_lbl = p["outcome_label"]
        if pnl is None:
            outcome = "no_data"
        elif pnl > 0:
            outcome = "winner"
        else:
            outcome = "loser"

        rows.append({
            "pick_id": p["pick_id"],
            "scan_date": date,
            "symbol": sym,
            "zone": p["zone"],
            "mfo": mfo,
            "ml_prob": p["ml_prob"],
            "live_day_open": live_day_open,
            "bar5m_open": bar5m,
            "bar1m_open": bar1m,
            "live_vs_5m_pp": d_live_vs_5m,
            "live_vs_1m_pp": d_live_vs_1m,
            "bar5m_vs_1m_pp": d_5m_vs_1m,
            "live_gain_from_open": gfo,
            "corrected_gfo_using_bar5m": corrected_gfo,
            "gfo_drift_pp": gfo_drift_pp,
            "pkl_gain_from_open": pkl_gfo,
            "pkl_range_pct": pkl_rng,
            "pkl_gap_from_prev": pkl_gap,
            "live_vs_pkl_gfo_pp": live_vs_pkl_gfo_pp,
            "scan_price": sp,
            "pnl_pct": pnl,
            "outcome": outcome,
            "outcome_label": outcome_lbl,
            "exit_reason": p["exit_reason"],
        })

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {len(df)} rows → {OUT_CSV}\n", file=sys.stderr)

    # ---- Summaries ----
    def pct_above(series, thr):
        s = series.dropna()
        if len(s) == 0:
            return None
        return (s.abs() > thr).mean() * 100.0

    summary = {
        "total_picks": len(df),
        "zone_counts": dict(df["zone"].value_counts(dropna=False)),
        "pairwise": {
            "live_vs_bar5m": {
                "N": int(df["live_vs_5m_pp"].notna().sum()),
                "median_pp": float(df["live_vs_5m_pp"].median()) if df["live_vs_5m_pp"].notna().any() else None,
                "mean_abs_pp": float(df["live_vs_5m_pp"].abs().mean()) if df["live_vs_5m_pp"].notna().any() else None,
                "p90_abs_pp": float(df["live_vs_5m_pp"].abs().quantile(0.90)) if df["live_vs_5m_pp"].notna().any() else None,
                "p99_abs_pp": float(df["live_vs_5m_pp"].abs().quantile(0.99)) if df["live_vs_5m_pp"].notna().any() else None,
                "pct_pick_abs_gt_0.2pp": pct_above(df["live_vs_5m_pp"], DRIFT_THRESHOLD_PP),
                "pct_pick_abs_gt_1pp": pct_above(df["live_vs_5m_pp"], 1.0),
            },
            "live_vs_bar1m": {
                "N": int(df["live_vs_1m_pp"].notna().sum()),
                "median_pp": float(df["live_vs_1m_pp"].median()) if df["live_vs_1m_pp"].notna().any() else None,
                "mean_abs_pp": float(df["live_vs_1m_pp"].abs().mean()) if df["live_vs_1m_pp"].notna().any() else None,
                "pct_pick_abs_gt_0.2pp": pct_above(df["live_vs_1m_pp"], DRIFT_THRESHOLD_PP),
            },
            "bar5m_vs_bar1m": {
                "N": int(df["bar5m_vs_1m_pp"].notna().sum()),
                "median_pp": float(df["bar5m_vs_1m_pp"].median()) if df["bar5m_vs_1m_pp"].notna().any() else None,
                "mean_abs_pp": float(df["bar5m_vs_1m_pp"].abs().mean()) if df["bar5m_vs_1m_pp"].notna().any() else None,
                "pct_pick_abs_gt_0.2pp": pct_above(df["bar5m_vs_1m_pp"], DRIFT_THRESHOLD_PP),
            },
        },
    }

    # Per-zone breakdown of drift
    summary["per_zone_live_vs_bar5m"] = {}
    for z, g in df.groupby(df["zone"].fillna("UNK")):
        s = g["live_vs_5m_pp"].dropna()
        if len(s) == 0:
            continue
        summary["per_zone_live_vs_bar5m"][z] = {
            "N": int(len(s)),
            "mean_abs_pp": float(s.abs().mean()),
            "median_pp": float(s.median()),
            "p90_abs_pp": float(s.abs().quantile(0.90)),
            "pct_abs_gt_0.2pp": float((s.abs() > 0.2).mean() * 100.0),
            "pct_abs_gt_1pp": float((s.abs() > 1.0).mean() * 100.0),
        }

    # Drift vs outcome correlation
    sub = df.dropna(subset=["live_vs_5m_pp"]).copy()
    sub["abs_drift"] = sub["live_vs_5m_pp"].abs()
    by_outcome = sub.groupby("outcome")["abs_drift"].agg(["count", "mean", "median"])
    summary["drift_by_outcome"] = by_outcome.to_dict(orient="index")

    # Winner/loser WR split by drift magnitude
    sub_outcomes = sub[sub["outcome"].isin(["winner", "loser"])]
    if len(sub_outcomes) > 0:
        # Buckets
        bins = [(-0.001, 0.2), (0.2, 0.5), (0.5, 1.0), (1.0, 100)]
        rows_bk = []
        for lo, hi in bins:
            mask = (sub_outcomes["abs_drift"] > lo) & (sub_outcomes["abs_drift"] <= hi)
            sl = sub_outcomes[mask]
            if len(sl) == 0:
                continue
            wr = (sl["outcome"] == "winner").mean() * 100.0
            rows_bk.append({
                "bucket": f"{lo:.2f}<drift<={hi:.2f}",
                "N": int(len(sl)),
                "WR_pct": round(float(wr), 1),
                "avg_pnl": round(float(sl["pnl_pct"].mean()), 2),
            })
        summary["wr_by_drift_bucket"] = rows_bk

    # gfo drift correlation (more direct: feature value drift)
    sub2 = df.dropna(subset=["gfo_drift_pp"]).copy()
    sub2["abs_gfo_drift"] = sub2["gfo_drift_pp"].abs()
    summary["gfo_drift_overall"] = {
        "N": int(len(sub2)),
        "median_pp": float(sub2["gfo_drift_pp"].median()),
        "mean_abs_pp": float(sub2["abs_gfo_drift"].mean()),
        "p90_abs_pp": float(sub2["abs_gfo_drift"].quantile(0.90)),
        "pct_abs_gt_0.2pp": float((sub2["abs_gfo_drift"] > 0.2).mean() * 100.0),
        "pct_abs_gt_1pp": float((sub2["abs_gfo_drift"] > 1.0).mean() * 100.0),
    }

    # Outcome split by gfo drift
    sub2_out = sub2[sub2["outcome"].isin(["winner", "loser"])]
    if len(sub2_out) > 0:
        bins = [(-0.001, 0.2), (0.2, 0.5), (0.5, 1.0), (1.0, 100)]
        rows_bk = []
        for lo, hi in bins:
            mask = (sub2_out["abs_gfo_drift"] > lo) & (sub2_out["abs_gfo_drift"] <= hi)
            sl = sub2_out[mask]
            if len(sl) == 0:
                continue
            wr = (sl["outcome"] == "winner").mean() * 100.0
            rows_bk.append({
                "bucket": f"|gfo_drift| {lo:.2f}<x<={hi:.2f}",
                "N": int(len(sl)),
                "WR_pct": round(float(wr), 1),
                "avg_pnl": round(float(sl["pnl_pct"].mean()), 2),
            })
        summary["wr_by_gfo_drift_bucket"] = rows_bk

    # live vs pkl gfo (most direct feature drift measurement)
    sub3 = df.dropna(subset=["live_vs_pkl_gfo_pp"]).copy()
    sub3["abs_pkl_drift"] = sub3["live_vs_pkl_gfo_pp"].abs()
    summary["live_vs_pkl_gfo"] = {
        "N": int(len(sub3)),
        "median_pp": float(sub3["live_vs_pkl_gfo_pp"].median()) if len(sub3) else None,
        "mean_abs_pp": float(sub3["abs_pkl_drift"].mean()) if len(sub3) else None,
        "p90_abs_pp": float(sub3["abs_pkl_drift"].quantile(0.90)) if len(sub3) else None,
        "pct_abs_gt_0.2pp": float((sub3["abs_pkl_drift"] > 0.2).mean() * 100.0) if len(sub3) else None,
        "pct_abs_gt_1pp": float((sub3["abs_pkl_drift"] > 1.0).mean() * 100.0) if len(sub3) else None,
    }
    sub3_out = sub3[sub3["outcome"].isin(["winner", "loser"])]
    if len(sub3_out):
        bins = [(-0.001, 0.2), (0.2, 0.5), (0.5, 1.0), (1.0, 100)]
        rows_bk = []
        for lo, hi in bins:
            sl = sub3_out[(sub3_out["abs_pkl_drift"] > lo) & (sub3_out["abs_pkl_drift"] <= hi)]
            if len(sl) == 0:
                continue
            wr = (sl["outcome"] == "winner").mean() * 100.0
            rows_bk.append({
                "bucket": f"|live-pkl gfo| {lo:.2f}<x<={hi:.2f}",
                "N": int(len(sl)),
                "WR_pct": round(float(wr), 1),
                "avg_pnl": round(float(sl["pnl_pct"].mean()), 2),
            })
        summary["wr_by_live_vs_pkl_gfo"] = rows_bk

    # Worst offenders (largest drift)
    worst = df.dropna(subset=["live_vs_5m_pp"]).copy()
    worst["abs_drift"] = worst["live_vs_5m_pp"].abs()
    worst = worst.sort_values("abs_drift", ascending=False).head(15)
    summary["worst_15"] = worst[[
        "scan_date", "symbol", "zone", "live_day_open", "bar5m_open",
        "live_vs_5m_pp", "gfo_drift_pp", "outcome", "pnl_pct"
    ]].to_dict(orient="records")

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
