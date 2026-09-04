"""resonance / features / cluster_fit.py — refit the correlation-cluster table.

`stock_clusters` (data/trade_history.db) groups the active universe into correlation clusters so
`resonance.data.access.cluster()` can answer "who moves WITH this name?" for rotation / sympathy
context. It is a slowly-varying snapshot keyed by `fit_date`; the table KEEPS HISTORY (one batch per
fit_date), and `cluster()` reads the latest fit_date <= asof. This script appends a FRESH batch.

Method (point-in-time as of ASOF, a static snapshot — no look-ahead concern since it isn't a signal):
  1. Daily CLOSE returns for every active universe symbol over the last ~90 trading days ending at
     ASOF (log returns). Drop names with too little history.
  2. Correlation matrix -> distance (1 - corr) -> AgglomerativeClustering (average linkage,
     precomputed distance, distance_threshold) — variable cluster count, matching the legacy fit's
     "many singletons + a few dense sector clusters" shape.
  3. Per member: corr_to_centroid = corr of its return series to its cluster's mean-return series.
  4. Name each cluster by its dominant sector (universe_stocks.sector), matching the existing style:
       n_members >= 3  ->  "{Sector}_{id}({n})"   e.g. "Energy_9(33)"
       n_members <  3  ->  "C{id}"                e.g. "C7"
  5. Write the batch under a new fit_date (idempotent: DELETE that fit_date first, then INSERT).

Schema written (unchanged): symbol, cluster_id, cluster_name, corr_to_centroid, n_members, fit_date.

CLI:
  python -m resonance.features.cluster_fit                 # asof = latest OHLC date
  python -m resonance.features.cluster_fit 2026-07-31      # explicit asof
  python -m resonance.features.cluster_fit 2026-07-31 --dry-run          # fit, print, no write
  python -m resonance.features.cluster_fit --threshold 0.80             # tune cluster granularity

Re-runnable / cron-safe (weekly): `0 3 * * 0 cd <repo> && ~/.pyenv/versions/cc/bin/python -m
resonance.features.cluster_fit`.
"""
from __future__ import annotations

import argparse
import sqlite3

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering

from resonance.data import access

DB = "data/trade_history.db"

# --- fit parameters ---------------------------------------------------------------------------
LOOKBACK_DAYS = 90        # trading sessions of daily returns used to estimate correlation
MIN_OBS = 60              # a symbol needs at least this many return observations to be clustered
MIN_PERIODS = 30          # min overlap for a pairwise correlation to be trusted (else -> 0)
DIST_THRESHOLD = 0.50     # cut the tree here: distance = 1 - corr, so 0.50 <=> corr ~0.50 average.
                          # Tuned 2026-08-01 vs the 2026-05-13 legacy fit: yields ~300 clusters
                          # (legacy ~224, same order) with coherent sector blocks — energy names,
                          # regional banks, and the semis/tech complex each group cleanly while
                          # idiosyncratic names fall out as singletons (as in the legacy table).
SECTOR_NAME_MIN = 3       # clusters with >= this many members get a "{Sector}_{id}(n)" name


# ---------------------------------------------------------------------------------- data load
def _load_returns(conn, asof):
    """Return (returns_df, sector_map).

    returns_df: index = date (last LOOKBACK_DAYS sessions <= asof), columns = symbol, values = log
    return of close. Symbols with < MIN_OBS observations are dropped. sector_map: {symbol: sector}
    from access.universe() — the full 2000-name union (core `universe_stocks` + the decoupled
    `resonance_universe` extras). Extras carry no sector yet, so they name-fall-through to "Unknown"
    in _name_cluster (same behavior as any core name with a null sector).
    """
    uni = access.universe(db=DB)
    syms = uni["syms"]
    sector_map = uni["sector"]

    # the LOOKBACK_DAYS trading dates ending at asof (inclusive)
    dates = pd.read_sql_query(
        "SELECT DISTINCT date FROM stock_daily_ohlc WHERE date <= ? ORDER BY date DESC LIMIT ?",
        conn, params=(asof, LOOKBACK_DAYS + 1))["date"].tolist()  # +1: one extra to seed the diff
    if not dates:
        raise SystemExit(f"no stock_daily_ohlc rows on/before {asof}")
    dates = sorted(dates)
    start = dates[0]

    ph = ",".join("?" * len(syms))
    px = pd.read_sql_query(
        f"""SELECT symbol, date, close FROM stock_daily_ohlc
            WHERE date >= ? AND date <= ? AND symbol IN ({ph})""",
        conn, params=[start, asof, *syms])
    if px.empty:
        raise SystemExit("no price rows in the lookback window")

    wide = px.pivot_table(index="date", columns="symbol", values="close").sort_index()
    rets = np.log(wide / wide.shift(1)).iloc[1:]           # drop the seed row's NaN
    rets = rets.dropna(axis=1, thresh=MIN_OBS)             # keep names with enough history
    return rets, sector_map


# ---------------------------------------------------------------------------------- clustering
def _fit_clusters(rets, threshold):
    """Correlation -> distance -> agglomerative labels. Returns a Series {symbol: raw_label}."""
    corr = rets.corr(min_periods=MIN_PERIODS)
    corr = corr.fillna(0.0)                                # no reliable overlap -> treat as uncorrelated
    dist = (1.0 - corr).clip(lower=0.0, upper=2.0).values
    np.fill_diagonal(dist, 0.0)
    dist = (dist + dist.T) / 2.0                           # enforce exact symmetry for sklearn

    model = AgglomerativeClustering(
        n_clusters=None, distance_threshold=threshold,
        metric="precomputed", linkage="average")
    labels = model.fit_predict(dist)
    return pd.Series(labels, index=corr.columns, name="raw_label")


def _name_cluster(cid, members, sector_map):
    """Dominant-sector name matching the legacy style."""
    n = len(members)
    if n < SECTOR_NAME_MIN:
        return f"C{cid}"
    sectors = [sector_map.get(s) or "Unknown" for s in members]
    dominant = pd.Series(sectors).value_counts().idxmax()
    return f"{dominant}_{cid}({n})"


def build_fit(conn, asof, threshold=DIST_THRESHOLD):
    """Compute the full cluster batch for ASOF. Returns (rows, meta).

    rows: list of dicts ready to insert (symbol, cluster_id, cluster_name, corr_to_centroid,
    n_members, fit_date). meta: {n_symbols, n_clusters, n_singletons, samples}.
    """
    rets, sector_map = _load_returns(conn, asof)
    raw = _fit_clusters(rets, threshold)

    # stable, human-friendly cluster_ids 1..N (ordered by first symbol appearance)
    order, seen = [], set()
    for lab in raw.values:
        if lab not in seen:
            seen.add(lab)
            order.append(lab)
    remap = {lab: i + 1 for i, lab in enumerate(order)}

    rows = []
    for lab in order:
        cid = remap[lab]
        members = raw.index[raw == lab].tolist()
        n = len(members)
        cname = _name_cluster(cid, members, sector_map)
        centroid = rets[members].mean(axis=1)             # equal-weight mean-return series
        for sym in members:
            c = rets[sym].corr(centroid) if n > 1 else 1.0
            rows.append({
                "symbol": sym, "cluster_id": cid, "cluster_name": cname,
                "corr_to_centroid": None if (c is None or np.isnan(c)) else round(float(c), 4),
                "n_members": n, "fit_date": asof,
            })

    n_clusters = len(order)
    n_singletons = sum(1 for lab in order if int((raw == lab).sum()) == 1)
    # a few dense sample clusters for the self-test print
    sizes = {remap[lab]: int((raw == lab).sum()) for lab in order}
    top = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)[:3]
    samples = []
    for cid, _ in top:
        cr = [r for r in rows if r["cluster_id"] == cid]
        samples.append({
            "cluster_id": cid, "cluster_name": cr[0]["cluster_name"],
            "members": [r["symbol"] for r in sorted(cr, key=lambda r: -(r["corr_to_centroid"] or 0))],
        })
    meta = {"n_symbols": len(rows), "n_clusters": n_clusters,
            "n_singletons": n_singletons, "samples": samples, "fit_date": asof}
    return rows, meta


# --------------------------------------------------------------------------------------- write
def write_fit(conn, rows, fit_date):
    """Idempotent per fit_date: DELETE that fit_date, then INSERT the batch. Old fits untouched."""
    cur = conn.cursor()
    cur.execute("DELETE FROM stock_clusters WHERE fit_date=?", (fit_date,))
    cur.executemany(
        """INSERT INTO stock_clusters
           (symbol, cluster_id, cluster_name, corr_to_centroid, n_members, fit_date)
           VALUES (:symbol, :cluster_id, :cluster_name, :corr_to_centroid, :n_members, :fit_date)""",
        rows)
    conn.commit()


# ----------------------------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="Refit stock_clusters correlation clusters.")
    ap.add_argument("asof", nargs="?", default=None,
                    help="fit date YYYY-MM-DD (default = latest stock_daily_ohlc date)")
    ap.add_argument("--threshold", type=float, default=DIST_THRESHOLD,
                    help=f"agglomerative distance cut (default {DIST_THRESHOLD}; higher = fewer clusters)")
    ap.add_argument("--dry-run", action="store_true", help="compute + print, do not write")
    args = ap.parse_args()

    # NOTE: this DB has several cron writers and three live readers. Without a busy timeout a
    # transient lock raises OperationalError and the job dies silently — cluster_fit did
    # exactly that every Sunday for 5 weeks before anyone looked at its log.
    conn = sqlite3.connect(DB, timeout=60)
    try:
        asof = args.asof
        if asof is None:
            asof = conn.execute("SELECT MAX(date) FROM stock_daily_ohlc").fetchone()[0]

        rows, meta = build_fit(conn, asof, args.threshold)

        if not args.dry_run:
            write_fit(conn, rows, asof)

        print(f"fit_date       : {meta['fit_date']}")
        print(f"n_symbols fit  : {meta['n_symbols']}")
        print(f"n_clusters     : {meta['n_clusters']}  (singletons: {meta['n_singletons']})")
        print(f"threshold      : {args.threshold}")
        print(f"written        : {'NO (dry-run)' if args.dry_run else 'YES'}")
        print("\n3 largest clusters:")
        for s in meta["samples"]:
            print(f"  [{s['cluster_id']}] {s['cluster_name']}")
            print(f"      {', '.join(s['members'][:25])}"
                  + (" ..." if len(s["members"]) > 25 else ""))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
