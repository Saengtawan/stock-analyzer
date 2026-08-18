"""swing/screen/pool.py — build the RAW POOL for the swing sibling. RESONANCE-FAITHFUL version.

Mirrors resonance/screen/pool.py exactly in spirit:
  - UNION-OF-AXES, never a weighted composite. A name enters the pool if it is unusual on >= 1
    COMPRESSION axis (the coil prerequisite for swing). No compression score, no ranking, no
    penalties, no direction/strength gate — "don't hardcode conclusions; the AI does the weighting."
  - Only STRUCTURAL prerequisites gate (like resonance's buyable price-cap / liquidity / already-fired
    exclusion): tradable liquidity, and a realized-vol floor that drops merger/buyout-PINNED flatlines
    (the swing analog of resonance's release gate — a dead tape is not a coil).
  - Trend / RS / distance-from-high are EMITTED RAW for the AI to weigh; they do NOT gate. Whether
    "leadership" matters to a VCP is the AI's call, not a hardcoded filter.

Read-only. Reuses resonance.data.access (mode=ro). Writes ONLY under swing/. Touches NOTHING in resonance/.

Run:  python -m swing.screen.pool [ASOF=today]      Out: swing/pool/<asof>.json + printed table.
"""
import os
import sys
import json
import datetime

import resonance.data.access as R
from swing.features import mechanical

# --- structural prerequisites only (buyable/liquidity/alive — NOT alpha tuning, NOT ranking) ---
MIN_DVOL  = float(os.environ.get("SWING_MIN_DVOL", 15e6))   # avg $ vol/day -> tradable
MIN_ADR   = float(os.environ.get("SWING_MIN_ADR", 0.8))     # avg abs daily % -> drop pinned flatlines
# --- compression axes: percentile-relative selection (mirrors resonance BREADTH_Q), no fixed cutoff ---
BREADTH_Q = float(os.environ.get("SWING_BREADTH_Q", 0.06))  # tightest this fraction of the universe = a "tight" axis hit
TOP_N     = int(os.environ.get("SWING_TOP_N", 45))          # display/enrichment cap only (see note at cut)
OUT_DIR   = "swing/pool"


def _ret(closes, n):
    return (closes[-1] / closes[-1 - n] - 1) * 100 if len(closes) > n and closes[-1 - n] > 0 else None


def _spy_returns(asof):
    d = R.daily("SPY", asof, 260)
    cs = [b["c"] for b in d["bars"] if b["c"] is not None]
    return {"r21": _ret(cs, 21), "r63": _ret(cs, 63), "r126": _ret(cs, 126)}


def _avg_dvol(bars, n=20):
    vals = [b["c"] * b["v"] for b in bars[-n:] if b["c"] and b["v"]]
    return sum(vals) / len(vals) if vals else 0.0


def build(asof, verbose=True):
    spy = _spy_returns(asof)
    syms = R.universe()["syms"]

    # ---- pass 1: compute raw mechanical for every STRUCTURALLY-eligible name (no compression gate yet) ----
    cand = []
    scanned = 0
    for sym in syms:
        if sym == "SPY":
            continue
        try:
            d = R.daily(sym, asof, 260)
        except Exception:
            continue
        bars = d.get("bars") or []
        if len(bars) < 150:
            continue
        scanned += 1
        m = mechanical.compute(bars)
        if m is None:
            continue
        if _avg_dvol(bars) < MIN_DVOL:                      # structural: tradable
            continue
        if m["adr20"] is None or m["adr20"] < MIN_ADR:      # structural: not a pinned/dead flatline
            continue
        m["sym"] = sym
        m["avg_dvol_m"] = round(_avg_dvol(bars) / 1e6, 1)
        m["rs_63"] = round(m["ret_63"] - spy["r63"], 2) if (m["ret_63"] is not None and spy["r63"] is not None) else None
        m["rs_126"] = round(m["ret_126"] - spy["r126"], 2) if (m["ret_126"] is not None and spy["r126"] is not None) else None
        cand.append(m)

    # ---- compression axes (resonance-style blend; UNION, no composite) ----
    # Continuous axes are PERCENTILE-RELATIVE across the universe (bottom BREADTH_Q), never a fixed
    # threshold — the resonance way. Booleans (squeeze/nr7/contracting) are raw pattern hits.
    def _low_cut(key):
        vals = sorted(x[key] for x in cand if x.get(key) is not None)
        return vals[max(0, int(len(vals) * BREADTH_Q) - 1)] if vals else None

    cuts = {k: _low_cut(k) for k in
            ("atr_pct_ptile", "rvol_ratio", "range_contraction", "bb_bandwidth_ptile", "max_drawdown_pct")}

    def _hit(m, key):
        return cuts[key] is not None and m.get(key) is not None and m[key] <= cuts[key]

    pool = []
    for m in cand:
        axes = []
        if m["squeeze_on"]:         axes.append("squeeze")
        if m["squeeze_fired"]:      axes.append("fired")
        if m["is_contracting"]:     axes.append("contract")   # VCP pullback sequence
        if m["nr7"]:                axes.append("nr7")        # narrow-range day (Crabel)
        if m["bb_squeeze_106"] or _hit(m, "bb_bandwidth_ptile"): axes.append("bbsqz")  # Bollinger squeeze
        if _hit(m, "atr_pct_ptile"):        axes.append("tight")       # ATR% low vs own history
        if _hit(m, "rvol_ratio"):           axes.append("rvolcontr")   # short vol << long vol
        if _hit(m, "range_contraction"):    axes.append("rangecontr")  # range 10d/40d tightening
        if _hit(m, "max_drawdown_pct"):     axes.append("loaded")      # deep prior fall (loaded spring)
        if axes:                                            # union prerequisite: unusual on >= 1 axis
            m["axes"] = axes
            m["n_axes"] = len(axes)
            pool.append(m)

    # display/enrichment cap ONLY (not a judgment): order BREADTH-FIRST — by how MANY independent
    # compression axes corroborate (a COUNT, resonance's breadth idea), tiebreak tightness. This is a
    # raw count, NOT a weighted score; the AI is told to weigh all axes itself, not trust the order.
    pool.sort(key=lambda x: (-x["n_axes"], x["atr_pct_ptile"] if x["atr_pct_ptile"] is not None else 1.0))
    full_n = len(pool)
    pool = pool[:TOP_N]

    for m in pool:                                          # enrich finalists with context the AI judges on
        try:
            f = R.fundamentals(m["sym"])
            m["sector"] = f.get("sector") if f else None
        except Exception:
            m["sector"] = None
        try:
            m["catalyst"] = R.catalyst(m["sym"], asof)
        except Exception:
            m["catalyst"] = None

    os.makedirs(OUT_DIR, exist_ok=True)
    out = {"asof": asof, "spy": spy, "scanned": scanned,
           "union_n": full_n, "shown_n": len(pool), "breadth_q": BREADTH_Q, "pool": pool}
    path = os.path.join(OUT_DIR, f"{asof}.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2, default=str)

    if verbose:
        print(f"[swing pool] asof={asof}  scanned={scanned}  union={full_n}  shown={len(pool)}  -> {path}")
        print(f"  SPY 63d {spy['r63']:.1f}%  (RS emitted raw; NOT a gate)  | 9 axes, percentile top {BREADTH_Q:.0%}")
        print(f"  (order = breadth: # of axes corroborating, a COUNT — NOT a ranking. AI weighs all axes.)")
        print(f"  {'sym':7}{'sect':12}{'px':>8}{'rs63':>7}{'#ax':>4}{'atrP':>6}{'dryup':>7}  axes")
        for m in pool:
            sect = (m.get("sector") or "")[:10]
            print(f"  {m['sym']:7}{sect:12}{m['px']:>8.2f}{(m['rs_63'] if m['rs_63'] is not None else 0):>7.1f}"
                  f"{m['n_axes']:>4}{(m['atr_pct_ptile'] if m['atr_pct_ptile'] is not None else 0):>6.2f}"
                  f"{(m['vol_dryup'] if m['vol_dryup'] is not None else 0):>7.2f}  {','.join(m['axes'])}")
    return out


if __name__ == "__main__":
    asof = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    build(asof)
