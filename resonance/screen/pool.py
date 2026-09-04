"""resonance / screen / pool.py — high-recall candidate POOL from the feature table.

MECHANICAL. Zero AI tokens. This is a WIDE NET, not a selection. It reduces the ~1000-symbol
coil+prime feature table to a ~30-50 name pool that the brain (AI) then reads and *weights itself*.

DESIGN RULES (from README + memory principles — do not break):

  1. UNION-OF-AXES, never a weighted composite, gated by a COIL PREREQUISITE. A name enters the
     pool if it is unusual on a resonance axis — but resonance trades COILED SPRINGS, so a name is
     admitted ONLY IF it is unusual on at least one COILED axis (atr_compression, bb_squeeze,
     rvol_contraction, consolidation, loaded_spring). The spring comes first; the PRIMED axes
     (pm_wake, gap, news, short_fuel, options) are the TRIGGER — they add conviction and are still
     surfaced in the digest, but a pure gapper/newsmover with NO coil (e.g. BE / AMZN 2026-07-31,
     which entered on gap+news alone with zero coiled axis) is exactly the earnings-gapper /
     gain-chase the system exists to reject, so primed axes can NO LONGER admit a name on their own.
     We still deliberately do NOT sum/score the axes into one number and take the top-N — that
     would bake in the very weighting the AI is supposed to do downstream (principle: "don't
     hardcode conclusions / AI does the weighting"). This gate is not ranking or judging; it
     enforces the system's DEFINITION (it trades springs). Membership is BINARY and per-axis; no
     single number ranks names for selection.

     Two equal-weight entry paths (both are still pure per-axis membership, NOT a composite; both
     require >= 1 coiled axis):
       (a) EXTREME  — a name is in the top-K most-unusual of ANY ONE *coiled* axis. (A primed-only
                      extreme no longer enters.)
       (b) BROAD    — a name is in the top BREADTH_Q (e.g. top 4%) of >= BREADTH_MIN_AXES DISTINCT
                      axes at once, AT LEAST ONE of which is coiled. This rescues the real
                      coiled+primed profile — a name that is strongly unusual across SEVERAL axes
                      but extreme on none (this is exactly AXTI on 2026-07-30: top ~2-3% on
                      consolidation, loaded_spring, gap AND short_fuel, yet top-K on none). Path (b)
                      does not weight axes against each other — every axis is one equal binary vote
                      — so it stays faithful to "the AI does the weighting". Without it, a shallow
                      max-per-axis net silently drops the very setup we exist to find; a net deep
                      enough to catch it by path (a) alone floods to 150+ names.

     A coiled name with primed triggers = the ideal (spring + trigger). A coiled-only name =
     allowed (loaded; the trigger may come intraday). A primed-only name (no coil) = EXCLUDED.

  2. DIRECTION-AGNOSTIC (principle #3: gain is deceptive). Axes rank by MAGNITUDE / unusualness vs
     the field, never by "up the most". The gap axis uses |gap| (prime_gap_abs), not signed gap.
     A coiled-quiet name and a primed-active name are equally welcome; today's big gainer gets no
     special pass.

  3. NEVER SILENTLY CAP. The pool is whatever the two paths produce; every other name is reported
     as "dropped — unusual on no axis", with a count. K / BREADTH_Q are the *declared* net width,
     logged with each axis's contribution, not a hidden trim.

The axes (each contributes its own top-K + its top-BREADTH_Q, then union):

  COILED (stored energy — "due" to move; magnitude is the predictable thing)
    atr_compression   coil_atr_pct_pctile        LOW  = ATR unusually tight vs its own history
    bb_squeeze        coil_bb_bandwidth_pctile   LOW  = Bollinger bands unusually pinched
    rvol_contraction  coil_rvol_ratio            LOW  = short realized-vol << long (winding down)
    consolidation     coil_consol_len            HIGH = many consecutive quiet days
    loaded_spring     coil_max_drawdown_pct      LOW  = deep prior fall  (AXTI 143->37)
                      coil_pct_from_252hi        LOW  = far below its own 52w high

  PRIMED (a reason to release TODAY — direction + durability)
    pm_wake           prime_pm_vol_vs_avg        HIGH = premarket volume waking up vs own 20d avg
    gap               prime_gap_abs              HIGH = |pre-open gap| (direction-agnostic energy)
    news              prime_news_max_impact      HIGH = strongest scored news impact (tie: news_n)
    short_fuel        prime_short_pct_float      HIGH = squeeze fuel (% float short)
                      prime_short_change_pct     HIGH = short building vs prior report
    options           prime_opt_unusual_call     HIGH = unusual call OR put activity flagged
                      prime_opt_unusual_put      HIGH

Output:
  (a) a COMPACT per-symbol digest of the pooled names — the subset of raw feature columns the brain
      needs, plus the list of axes that surfaced each name ("why it's here"). Token-light.
  (b) a transparency log: pool size, per-axis contribution counts, and the dropped-count.
  Written to resonance/cache/pool_<DATE>.json.

  pool(date) -> dict
  python -m resonance.screen.pool <DATE>            # build/load features, run pool, print log
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import numpy as np
import pandas as pd

CACHE = "resonance/cache"

# --- net width knobs (tuned on 2026-07-30 so the union lands ~50 with AXTI IN, CAG OUT) --------
PRIMARY_K = 4            # path (a) EXTREME: top-K most-unusual per axis metric
BREADTH_Q = 0.04         # path (b) BROAD: "unusual on an axis" = top 4% of that axis
BREADTH_MIN_AXES = 3     # path (b): a name enters if broadly unusual on >= this many DISTINCT axes

# --- loaded_spring RELEASE reset: a spring fires ONCE. loaded_spring (deep drawdown / far below
#     52w high) does NOT reset on its own after the spring pops (a name still sits far below its
#     high even after a +27% day), so it would keep re-firing on an already-released name. Fix: if
#     the name made a big UP day recently (the release), loaded_spring is neutralized (it discharged
#     — no longer a loaded coil). The COMPRESSION axes self-reset (a pop expands vol), so this is
#     only needed for loaded_spring. This replaces the old membership-cooldown patch.
RELEASE_UP_PCT = 12.0    # a single-day up-move >= this in the recent window = the spring already fired



# --------------------------------------------------------------------------- axis definitions
# Each axis: one or more (column, direction) metrics. A name is IN the axis's EXTREME set if it
# lands in the top-PRIMARY_K of ANY metric; IN the axis's BROAD set if it lands in the top-
# BREADTH_Q of ANY metric. direction "low" -> most-unusual = smallest value; "high" -> largest.
# positive_only: metric is a 0/1 flag (options) — only genuinely-flagged (>0) names can qualify,
# never zero-fill from nlargest.
AXES = [
    # --- COILED ------------------------------------------------------------------------------
    {"name": "atr_compression", "group": "coiled",
     "metrics": [("coil_atr_pct_pctile", "low")]},
    {"name": "bb_squeeze", "group": "coiled",
     "metrics": [("coil_bb_bandwidth_pctile", "low")]},
    {"name": "rvol_contraction", "group": "coiled",
     "metrics": [("coil_rvol_ratio", "low")]},
    {"name": "consolidation", "group": "coiled",
     "metrics": [("coil_consol_len", "high")]},
    {"name": "loaded_spring", "group": "coiled",
     "metrics": [("coil_max_drawdown_pct", "low"), ("coil_pct_from_252hi", "low")]},
    # --- PRIMED ------------------------------------------------------------------------------
    {"name": "pm_wake", "group": "primed",
     "metrics": [("prime_pm_vol_vs_avg", "high")]},
    {"name": "gap", "group": "primed",
     "metrics": [("prime_gap_abs", "high")]},
    {"name": "news", "group": "primed",
     "metrics": [("prime_news_max_impact", "high")], "tiebreak": "prime_news_n"},
    {"name": "short_fuel", "group": "primed",
     "metrics": [("prime_short_pct_float", "high"), ("prime_short_change_pct", "high")]},
    {"name": "options", "group": "primed", "positive_only": True,
     "metrics": [("prime_opt_unusual_call", "high"), ("prime_opt_unusual_put", "high")]},
]

# COIL PREREQUISITE: resonance trades springs, so a name is only admitted to the pool if it is
# unusual on at least one of these COILED axes. PRIMED axes are the trigger — surfaced in the
# digest, adding conviction — but they can never admit a name on their own. This enforces the
# system's DEFINITION (spring first); it is not ranking/judging (the AI still weights the survivors).
COILED_AXES = {ax["name"] for ax in AXES if ax["group"] == "coiled"}

# Raw columns carried into the compact digest the brain reads (token-light: only decision-relevant).
DIGEST_COLS = [
    "coil_dd_suspect",   # True = 252d high looks pre-split; depth suppressed, do not read as a crash
    "sym", "sector", "coil_last_close",
    # coil (stored energy)
    "coil_atr_pct_pctile", "coil_bb_bandwidth_pctile", "coil_rvol_ratio", "coil_rvol_short_pctile",
    "coil_consol_len", "coil_nr7", "coil_bb_squeeze_106",
    "coil_max_drawdown_pct", "coil_pct_from_252hi", "coil_pct_from_window_high",
    # recent move / discharge (is it genuinely QUIET, or a knife that already released?)
    "coil_recent_max_abs_move_5d", "coil_abs_ret_3d", "coil_last_ret_1d", "coil_max_up_move_2d",
    # RAW recent daily returns (numbers only — the AI SEES if the spring already fired & judges itself)
    "coil_recent_daily_rets", "coil_ret_prev1d", "coil_ret_prev2d", "coil_ret_prev3d",
    # prime (release trigger)
    "prime_gap_pct", "prime_gap_suspect", "prime_gap_pct_raw", "prime_pm_vol_vs_avg", "prime_pm_range_pct",
    "prime_news_n", "prime_news_max_impact", "prime_news_net_sentiment",
    "prime_short_pct_float", "prime_short_change_pct", "prime_short_ratio",
    "prime_put_call_ratio", "prime_opt_unusual_call", "prime_opt_unusual_put",
    "prime_earn_upcoming", "prime_earn_days_to", "prime_analyst_net",
    "prime_float_shares", "prime_small_float", "prime_market_cap", "prime_beta",
]


# --------------------------------------------------------------------------------- load / build
def load_features(date, cache_dir=CACHE):
    """Read cache/features_<DATE>.(parquet|json); build it via features.build if absent."""
    pq = f"{cache_dir}/features_{date}.parquet"
    js = f"{cache_dir}/features_{date}.json"
    if os.path.exists(pq):
        try:
            return pd.read_parquet(pq)
        except Exception:
            pass
    if os.path.exists(js):
        return pd.read_json(js)
    # not cached -> build (mechanical; no AI). build writes the cache itself.
    from resonance.features.build import build
    df, _ = build(date, write=True, cache_dir=cache_dir)
    return df


# ------------------------------------------------------------------------------- axis selection
def _axis_members(df, axis):
    """Return (extreme_set, broad_set) for one axis.

    extreme_set = symbols in the top-PRIMARY_K most-unusual of ANY of the axis's metrics.
    broad_set   = symbols in the top-BREADTH_Q (fraction of that metric's non-null field) of ANY
                  metric — the wider "unusual on this axis" set counted for the breadth path.
    Both are over NON-NULL values only. `tiebreak` (higher first) breaks ties when a metric
    saturates (e.g. news impact clustered at 1.0). positive_only axes drop zeros (0/1 flags)."""
    tiebreak = axis.get("tiebreak")
    positive_only = axis.get("positive_only", False)
    extreme, broad = set(), set()
    for col, direction in axis["metrics"]:
        s = pd.to_numeric(df[col], errors="coerce")
        sub = pd.DataFrame({"sym": df["sym"], "v": s})[s.notna()].copy()
        if positive_only:
            sub = sub[sub["v"] > 0]
        if not len(sub):
            continue
        # orient so that ascending sort puts most-unusual first
        sub["rank_v"] = sub["v"] if direction == "low" else -sub["v"]
        if tiebreak and tiebreak in df.columns:
            tb = pd.to_numeric(df[tiebreak], errors="coerce").reindex(df.index)
            sub["rank_tb"] = -tb.reindex(sub.index).fillna(-np.inf)   # higher tiebreak first
            sub = sub.sort_values(["rank_v", "rank_tb", "sym"], kind="mergesort")
        else:
            sub = sub.sort_values(["rank_v", "sym"], kind="mergesort")
        syms = sub["sym"].tolist()
        # binary 0/1 flag: every flagged name IS the unusual set; percentile is meaningless.
        k_broad = len(syms) if positive_only else max(1, int(round(len(syms) * BREADTH_Q)))
        extreme |= set(syms[:PRIMARY_K])
        broad |= set(syms[:k_broad])
    return extreme, broad


def _round(v):
    """Compact numeric rounding for the digest (keeps the AI's read token-light)."""
    if v is None:
        return None
    if isinstance(v, (list, tuple, np.ndarray)):   # raw series (e.g. recent_daily_rets) -> clean list
        return [_round(x) for x in v]
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if not np.isfinite(f):
        return None
    if abs(f) >= 1e6:                       # market cap, float shares
        return int(round(f))
    return round(f, 3)


def pool(date, cache_dir=CACHE, write=True):
    """Build the high-recall candidate pool for `date`.

    Returns a dict: {date, pool_size, universe_size, dropped, axis_contrib, digest, log}. `digest`
    is a list of compact per-symbol dicts (DIGEST_COLS + `axes` = which axes surfaced the name)."""
    df = load_features(date, cache_dir)
    universe_size = len(df)

    # loaded_spring RELEASE reset: neutralize the loaded_spring metrics for any name that already
    # popped (a single recent daily up-move >= RELEASE_UP_PCT). It discharged, so it must not count
    # as a loaded coil (else it re-fires day after day — the bug the old cooldown patched). Compression
    # axes self-reset already; this targets loaded_spring only. Direction: UP moves only (the release).
    def _max_up(v):
        try:
            arr = np.asarray(v, dtype=float)
            return float(np.nanmax(arr)) if arr.size else -1e9
        except Exception:
            return -1e9
    if "coil_recent_daily_rets" in df.columns:
        _released_mask = df["coil_recent_daily_rets"].apply(_max_up) >= RELEASE_UP_PCT
        released_reset = int(_released_mask.sum())
        for _col in ("coil_max_drawdown_pct", "coil_pct_from_252hi"):
            if _col in df.columns:
                df.loc[_released_mask, _col] = np.nan   # loaded_spring axis won't fire on these
    else:
        released_reset = 0

    # Account constraint (small capital): only names buyable under $400/share. This is NOT a
    # judgment axis — it just removes names the AI could never size, so it never wastes a pick on
    # one. Gate on the EXPECTED entry price = prior close adjusted by the premarket gap (MSFT prior
    # close $390 but +12% gap -> opens ~$439, unbuyable), NOT the raw prior close. Unknown price
    # passes through (execute has a <$400 backstop).
    PRICE_CAP = 400.0
    if "coil_last_close" in df.columns:
        _gap = df["prime_gap_pct"].fillna(0.0) if "prime_gap_pct" in df.columns else 0.0
        _est_open = df["coil_last_close"] * (1.0 + _gap / 100.0)
        price_capped = int((_est_open >= PRICE_CAP).sum())
        df = df[~(_est_open >= PRICE_CAP)].copy()
    else:
        price_capped = 0
    buyable_size = len(df)

    # 1) run each axis independently -> its EXTREME (top-K) and BROAD (top-Q) sets
    extreme, broad = {}, {}
    for ax in AXES:
        e, b = _axis_members(df, ax)
        extreme[ax["name"]] = e
        broad[ax["name"]] = b

    # 2) per-symbol: which axes it is EXTREME on / BROADLY-unusual on ("why it's here")
    ext_by_sym: dict[str, list] = {}
    broad_by_sym: dict[str, list] = {}
    for ax in AXES:
        for s in extreme[ax["name"]]:
            ext_by_sym.setdefault(s, []).append(ax["name"])
        for s in broad[ax["name"]]:
            broad_by_sym.setdefault(s, []).append(ax["name"])

    # No mechanical discharge gate (operator: don't hardcode volatility thresholds). The raw recent
    # daily returns (coil_recent_daily_rets / ret_prev1d..3d / max_abs_move_5d / max_up_move_2d) are
    # in the digest; the AI judges "already released / discharged" itself. Coil stays the prerequisite.

    # 3) two entry paths (both binary, equal-weight, no composite) — GATED BY THE COIL PREREQUISITE.
    #    resonance trades springs: a name is admitted ONLY IF it is unusual on >= 1 coiled axis.
    #    Primed axes are the trigger (surfaced in the digest, add conviction) but can never admit a
    #    name alone. This enforces the system's DEFINITION (it trades springs); it does not rank/judge.
    #    (a) EXTREME: top-K on any one COILED axis
    #    (b) BROAD:   broadly unusual on >= BREADTH_MIN_AXES axes, AT LEAST ONE of them coiled
    def _coil_eligible(sym, axs):
        return any(a in COILED_AXES for a in axs)

    path_extreme = {s for s, axs in ext_by_sym.items() if _coil_eligible(s, axs)}
    path_broad = {s for s, axs in broad_by_sym.items()
                  if len(axs) >= BREADTH_MIN_AXES and _coil_eligible(s, axs)}
    pooled = path_extreme | path_broad
    # (No membership cooldown: already-released springs are dropped upstream by the loaded_spring
    #  RELEASE reset — a discharged name no longer fires loaded_spring, and compression self-resets.)

    # what the coil prerequisite removed: names the ungated union WOULD have admitted (extreme on
    # any axis, or broad on >= BREADTH_MIN_AXES) but which carry NO qualifying coiled axis — the
    # pure gappers / newsmovers (primed-only, not a spring) this gate exists to reject.
    ungated = set(ext_by_sym) | {s for s, axs in broad_by_sym.items() if len(axs) >= BREADTH_MIN_AXES}
    primed_only_excluded = ungated - pooled


    # 4) compact digest for the pooled names (token-light; raw columns only, AI weights them)
    cols = [c for c in DIGEST_COLS if c in df.columns]
    pdf = df[df["sym"].isin(pooled)].copy()
    digest = []
    for _, r in pdf.iterrows():
        s = r["sym"]
        row = {c.replace("coil_", "").replace("prime_", ""): _round(r[c]) for c in cols}
        row["axes"] = sorted(broad_by_sym.get(s, []))              # every axis it is unusual on
        row["axes_extreme"] = sorted(ext_by_sym.get(s, []))        # subset it is top-K on
        row["n_axes"] = len(row["axes"])
        row["entry"] = "extreme" if s in path_extreme else "broad"
        digest.append(row)
    # order by breadth of unusualness (how many axes), then sym — presentation only, NOT a score
    digest.sort(key=lambda d: (-d["n_axes"], d["sym"]))

    # 4b) MECHANICAL SHORTLIST — the measured winner profile, computed here (NOT argued by the AI).
    # Forward study of 995 pooled name-days (29 sessions, open->close) found catalyst/news/gap have ZERO
    # separating power, while this combination did — and it held OUT-OF-SAMPLE: in-sample (->08-18) n=18
    # avg +1.69% / 44% cleared +2%; out-of-sample (08-19->09-02) n=17 avg +1.48% median +1.96% / 47%
    # cleared +2% against a 13% baseline on the same sessions. It fires on ~1-2 names a session.
    # WHY IT LIVES IN CODE: every gate written into the decide prompt is prose-satisfiable, so an
    # articulate model clears it and still buys the wrong cohort (the losing picks cited every gate by
    # name). Selecting the cohort is a MECHANICAL job; the AI's job is direction (take/veto) on it.
    # This does NOT decide anything — the AI may veto every name here, may abstain, and may still pick
    # off-shortlist; it just no longer has to FIND the cohort itself.
    # pm_vol is deliberately NOT a cut here (changed 09-04). It measured as the strongest single return
    # separator, but a threshold on it does two wrong things at once: it drops genuinely coiled springs
    # that are quiet pre-open and release during RTH (on one session five such names ran +2.3% to +7.4%),
    # and it waves through the awake-but-COLLAPSING name (the −20.9% disaster had the highest premarket
    # volume in its pool). Volume has no sign; a number cannot fix that. The right instrument is the
    # CONTEXT read — and it works: on replay the agent vetoed that name on its actual pre-open facts
    # (revenue miss + cut volume guidance). So pm_vol stays as INFORMATION (raw value + rank_in_pool) for
    # the AI to weigh as the trigger question ("is the release starting today?"), not as a gate.
    SL_BETA_MIN = 1.5
    shortlist = []
    for row in digest:
        if "loaded_spring" not in (row.get("axes") or []):
            continue
        b, pv = row.get("beta"), row.get("pm_vol_vs_avg")
        if b is None or b <= SL_BETA_MIN:
            continue
        shortlist.append({"sym": row["sym"], "beta": b, "pm_vol_vs_avg": pv,
                          "pct_from_252hi": row.get("pct_from_252hi"),
                          "short_pct_float": row.get("short_pct_float"),
                          "gap_pct": row.get("gap_pct"), "news_n": row.get("news_n"),
                          "market_cap": row.get("market_cap"), "axes": row.get("axes")})
    shortlist.sort(key=lambda d: -(d.get("pm_vol_vs_avg") or 0))

    # 4c) PERCENTILE RANKS — the same information WITHOUT a threshold, so the AI can judge instead of
    # obeying. The shortlist above is one frozen cut of these dimensions; a frozen cut is a hardcoded
    # rule and will break when the regime changes (that is how the old rule systems died). These ranks
    # say WHERE each name sits inside TODAY'S pool on the dimensions that historically carried the
    # winners — deep drawdown (stored energy), beta (can it actually move), premarket volume (is anyone
    # acting yet), short interest (is there a forced buyer). No cutoff, no verdict: raw position.
    def _pct_rank(vals, v):
        xs = [x for x in vals if x is not None]
        if v is None or not xs:
            return None
        return round(100.0 * sum(1 for x in xs if x <= v) / len(xs))
    _dims = {"drawdown_depth": [(-(r.get("pct_from_252hi") or 0)) for r in digest],
             "beta": [r.get("beta") for r in digest],
             "pm_vol_vs_avg": [r.get("pm_vol_vs_avg") for r in digest],
             "short_pct_float": [r.get("short_pct_float") for r in digest]}
    for row in digest:
        row["rank_in_pool"] = {
            "drawdown_depth": _pct_rank(_dims["drawdown_depth"], -(row.get("pct_from_252hi") or 0)),
            "beta": _pct_rank(_dims["beta"], row.get("beta")),
            "pm_vol_vs_avg": _pct_rank(_dims["pm_vol_vs_avg"], row.get("pm_vol_vs_avg")),
            "short_pct_float": _pct_rank(_dims["short_pct_float"], row.get("short_pct_float")),
        }

    axis_contrib = {ax["name"]: len(extreme[ax["name"]]) for ax in AXES}
    dropped = buyable_size - len(pooled)

    # 5) transparency log (principle: never silently cap — say what was dropped)
    coiled = [a for a in AXES if a["group"] == "coiled"]
    primed = [a for a in AXES if a["group"] == "primed"]
    lines = [
        f"resonance pool — {date}",
        f"  universe={universe_size}  ->  price-cap <${PRICE_CAP:.0f} dropped {price_capped} (unbuyable on small capital)  ->  buyable={buyable_size}",
        f"  buyable={buyable_size}  ->  POOL={len(pooled)}   (dropped {dropped}: unusual on no coiled axis)",
        f"  COIL PREREQUISITE: {len(primed_only_excluded)} excluded as primed-only (no coil / not a spring) "
        f"— gap/news/etc. alone can no longer admit a name.",
        f"  RELEASE RESET: {released_reset} names had loaded_spring neutralized (already popped "
        f">={RELEASE_UP_PCT:.0f}% recently = discharged, no longer a loaded coil).",
        f"  entry paths (both require >=1 coiled axis): "
        f"EXTREME top-{PRIMARY_K} on a coiled axis -> {len(path_extreme)} names   |   "
        f"BROAD top-{BREADTH_Q:.0%} on >={BREADTH_MIN_AXES} axes (>=1 coiled) -> {len(path_broad)} "
        f"(+{len(path_broad - path_extreme)} unique)",
        f"  SHORTLIST (winner-region reference: loaded_spring + beta>{SL_BETA_MIN}; pm_vol is INFO, not a cut) -> {len(shortlist)} names"
        + (": " + ", ".join(d["sym"] for d in shortlist) if shortlist else " (none today)"),
        "  union-of-coiled-axes (binary per-axis membership; no composite; direction-agnostic; primed=trigger only).",
        "  per-axis EXTREME contribution (top-K):",
        "    COILED  " + "  ".join(f"{a['name']}={axis_contrib[a['name']]}" for a in coiled),
        "    PRIMED  " + "  ".join(f"{a['name']}={axis_contrib[a['name']]}" for a in primed),
    ]
    log = "\n".join(lines)

    result = {
        "date": date,
        "universe_size": universe_size,
        "price_capped": price_capped,
        "buyable_size": buyable_size,
        "pool_size": len(pooled),
        "dropped": dropped,
        "primed_only_excluded": len(primed_only_excluded),
        "released_reset": released_reset,
        "n_extreme": len(path_extreme),
        "n_broad": len(path_broad),
        "axis_contrib": axis_contrib,
        "shortlist": shortlist,          # mechanical winner-profile candidates (see 4b)
        "digest": digest,
        "log": log,
    }

    if write:
        os.makedirs(cache_dir, exist_ok=True)
        path = f"{cache_dir}/pool_{date}.json"
        with open(path, "w") as f:
            json.dump(result, f, indent=1, default=str)
        result["_path"] = path
    return result


# ------------------------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="high-recall candidate pool (union-of-axes) for a date")
    ap.add_argument("date")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--show", type=int, default=12, help="print this many digest rows")
    a = ap.parse_args()
    res = pool(a.date, write=not a.no_write)
    print(res["log"])
    if res.get("_path"):
        print(f"  wrote {res['_path']}")
    print(f"\n  sample of the pool (most axes first) — RAW components, the AI weights them:")
    for d in res["digest"][: a.show]:
        print(f"    {d['sym']:6s} {str(d.get('sector'))[:14]:14s} [{d['entry']:7s}] "
              f"axes[{d['n_axes']}]={','.join(d['axes'])}")


if __name__ == "__main__":
    main()
