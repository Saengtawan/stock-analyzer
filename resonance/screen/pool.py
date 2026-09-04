"""resonance / screen / pool.py — high-recall candidate POOL from the feature table.

MECHANICAL. Zero AI tokens. This is a WIDE NET, not a selection. It reduces the ~1000-symbol
coil+prime feature table to a ~30-50 name pool that the brain (AI) then reads and *weights itself*.

DESIGN RULES (from README + memory principles — do not break):

  1. ADMISSION = MOVEMENT CONCENTRATION (rewritten 2026-09-04 — see the long note in pool() §3b).
     The pool's one job is to hand the AI names that will actually TRAVEL today, so a direction read
     has something to earn on. A name is admitted on three LEVELS: deeply below its own 252-day high
     (stored energy), high beta (able to move), tradeable size. That is a DEFINITION of what this
     system trades plus a tradeability floor — the same class of statement as the $400 price cap —
     not a prediction about any name and not a ranking. No axis is summed or scored; nothing is
     weighted (principle: "don't hardcode conclusions / AI does the weighting").

     This REPLACED a union-of-axes gate with a coil prerequisite. That gate was measured over 48,469
     buyable name-days and concentrated NOTHING: its pool moved >=±2% on 29.9% of name-days against
     29.3% for the market. The cause was a units error — the axes rank by PERCENTILE against a name's
     own history ("unusually quiet for itself"), so a mega-cap in a slow week scored like a stock down
     70%, while the real signal is an ABSOLUTE level (off-252d-high, monotone across five bands:
     9.3% -> 34.7% cleared +2%). The admitted cohort now moves >=±2% on 54% of name-days.

     The axes are still computed and still travel in the digest as DESCRIPTION (which kind of
     compression, how broad). They no longer decide membership, and `n_axes` is not quality — it
     measured ANTI-correlated with outcome (2-axis 18% cleared +2%, 4-axis 7%), because the
     compression axes are redundant and a high count mostly means "extremely asleep".

     Rollback: RESONANCE_POOL_MODE=axis_union restores the previous gate (and its shortlist) exactly.

  2. DIRECTION-AGNOSTIC (principle #3: gain is deceptive). Admission uses MAGNITUDE and capacity to
     move, never "up the most"; today's big gainer gets no special pass. This is deliberate and it
     is measurable: the admitted cohort rises >=+2% on ~28% of name-days and falls <=-2% on ~25%,
     median 0.00%. The machine buys MAGNITUDE and takes NO side. 100% of the directional edge must
     come from the AI's context read — which is also what makes that read falsifiable, since the
     cohort's own up/down rates (emitted as `cohort_baseline`) are the number a plan has to beat.

  3. NEVER SILENTLY CAP, and never silently swap the pond. The log states the admission thresholds,
     the dropped count, and — every run — how the admitted set differs from what the OLD axis gate
     would have shown (`axis_only_excluded` / `movement_only_added`), so a change of pond can never
     pass unnoticed.

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
import datetime
import glob
import json
import os

import numpy as np
import pandas as pd

CACHE = "resonance/cache"

# --- net width knobs (tuned on 2026-07-30 so the union lands ~50 with AXTI IN, CAG OUT) --------
# --- ADMISSION (movement concentration) — see the long note in pool() section 3b. These are LEVELS,
#     not percentile ranks, because the measured signal is a level. Direction-agnostic by construction.
DEPTH_MAX_PCT_FROM_HI = -50.0   # a spring must be compressed: >= 50% below its own 252d high
BETA_MIN = 1.5                  # ... and able to travel when it releases
MCAP_MIN = 1e9                  # tradeability floor (same class as PRICE_CAP, not a judgment)

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
    "released_recently",   # popped >=12% recently: loaded_spring axis is off, name still admitted
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


def _cohort_baseline(date, cache_dir=CACHE, lookback=20, db="data/trade_history.db"):
    """Rolling open->close record of the POOL ITSELF over the last `lookback` written sessions.

    Returns {sessions, name_days, up_pct, down_pct, moved_pct, median_pct} plus `by_gap_sign`,
    or {} if unavailable. This is the null hypothesis the AI must beat, measured rather than asserted.

    WHY THE GAP-SIGN SPLIT (added 2026-09-04): the pond-wide up-rate is the wrong bar for most names,
    because the two halves of the pond behave nothing alike. Measured over 861 graded pooled name-days:
        gap > 0   ->  up >=+2%  37.0%   down <=-2%  18.8%   EV +1.22%
        gap <= 0  ->  up >=+2%  17.0%   down <=-2%  32.6%   EV -0.88%
    A single blended number therefore sets too LOW a bar for an up-gapping name and too HIGH a bar for
    a down-gapping one — and the plan is asked to justify beating it. Both halves are reported so the
    comparison is like-for-like. This is measurement, not a rule: no name is admitted or excluded by
    its gap sign, nothing here says which to prefer, and the split is recomputed each run from the last
    N pool files rather than written down, so it re-measures itself if the relationship changes or
    inverts. Read-only; any failure degrades to {} rather than blocking the morning run."""
    try:
        import sqlite3
        prior = sorted(glob.glob(f"{cache_dir}/pool_*.json"))
        prior = [p for p in prior if os.path.basename(p)[5:15] < date][-lookback:]
        if not prior:
            return {}
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rets, sessions = [], 0
        by_sign = {"up_gap": [], "down_gap": []}
        for p in prior:
            d = os.path.basename(p)[5:15]
            try:
                with open(p) as f:
                    rows_ = json.load(f).get("digest") or []
            except Exception:
                continue
            syms = [r["sym"] for r in rows_]
            gaps = {r["sym"]: r.get("gap_pct") for r in rows_}
            if not syms:
                continue
            q = ("SELECT symbol, open, close FROM stock_daily_ohlc WHERE date=? AND open>0 "
                 "AND symbol IN (%s)" % ",".join("?" * len(syms)))
            got = con.execute(q, [d] + syms).fetchall()
            if got:
                sessions += 1
                for sym_, o, c in got:
                    if not (o and c):
                        continue
                    r_ = (c / o - 1) * 100.0
                    rets.append(r_)
                    g = gaps.get(sym_)
                    if g is not None:
                        by_sign["up_gap" if g > 0 else "down_gap"].append(r_)
        con.close()
        if len(rets) < 30:
            return {}
        a = np.asarray(rets, dtype=float)

        def _slice(xs):
            if len(xs) < 20:
                return None
            v = np.asarray(xs, dtype=float)
            return {"name_days": len(v),
                    "up_pct": round(100.0 * float((v >= 2).mean()), 1),
                    "down_pct": round(100.0 * float((v <= -2).mean()), 1),
                    "ev_pct": round(float(v.mean()), 2)}

        by_gap_sign = {k: _slice(v) for k, v in by_sign.items()}
        by_gap_sign = {k: v for k, v in by_gap_sign.items() if v}
        return {"sessions": sessions, "name_days": len(a),
                "by_gap_sign": by_gap_sign,
                "up_pct": round(100.0 * float((a >= 2).mean()), 1),
                "down_pct": round(100.0 * float((a <= -2).mean()), 1),
                "moved_pct": round(100.0 * float((np.abs(a) >= 2).mean()), 1),
                "median_pct": round(float(np.median(a)), 2)}
    except Exception:
        return {}


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
    # ⚠️ SCOPE FIX 2026-09-04. The reset was written to neutralize the loaded_spring AXIS by nulling the
    # depth columns — harmless when membership came from the axis union. Under the movement admission
    # those same columns ARE the admission, so nulling them silently DELETED the name from the pool.
    # That was an unintended consequence of the admission change, not a decision, and it was wrong on
    # the merits: measured over 29 sessions the 67 names it removed cleared +2% on 37.3% of days against
    # 27.6% for the admitted pool (holds on both folds: 41.5% / 30.8%). A name that popped 12%+ recently
    # is NOT discharged — it keeps moving. It is also more two-sided (down 32.8% vs 25.2%, sd 5.97 vs
    # 3.83), so this is variance rather than edge, which is exactly the judgement the AI should make and
    # the machine should not.
    # So: the reset keeps its ORIGINAL scope — it neutralizes the loaded_spring axis — and the admission
    # reads the UN-reset depth. Released names stay in the pool, flagged, and the brain decides.
    if "coil_recent_daily_rets" in df.columns:
        _released_mask = df["coil_recent_daily_rets"].apply(_max_up) >= RELEASE_UP_PCT
        released_reset = int(_released_mask.sum())
        df["coil_pct_from_252hi_admit"] = df["coil_pct_from_252hi"]   # admission reads this, un-reset
        df["released_recently"] = _released_mask
        for _col in ("coil_max_drawdown_pct", "coil_pct_from_252hi"):
            if _col in df.columns:
                df.loc[_released_mask, _col] = np.nan   # loaded_spring axis won't fire on these
    else:
        released_reset = 0
        df["coil_pct_from_252hi_admit"] = df.get("coil_pct_from_252hi")
        df["released_recently"] = False

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
    axis_union = path_extreme | path_broad

    # 3b) ADMISSION — MOVEMENT CONCENTRATION, measured (replaces the axis-union gate, 2026-09-04)
    #
    # The pool's job is NOT to pick winners and NOT to guess direction (that stays the AI's job, and
    # the pool must stay direction-agnostic — principle #2). Its job is to CONCENTRATE MOVEMENT: hand
    # the AI names that will actually travel today, so a direction read has something to earn on.
    #
    # The axis-union gate FAILED that job, measured over 48,469 buyable name-days (29 sessions,
    # open->close), of which the 19 sessions 08-03..08-27 are LIVE 09:0x-ET snapshots:
    #     whole market   moved >=±2%  29.3%   (up 15.3% / down 14.0%)
    #     axis-union     moved >=±2%  29.9%   (up 15.2% / down 14.6%)   <- identical to random
    # It concentrated nothing. The cause is a units error, not a bad idea: the axes rank by PERCENTILE
    # against a name's own history ("unusually quiet for itself"), so a mega-cap in a slow week scores
    # like a stock that has fallen 70%. But the spring is an ABSOLUTE level, and at that level the
    # signal is strong and perfectly monotone across 48k name-days:
    #     off 252d-high  -15..0 -> 9.3% cleared +2% | -30..-15 15.4% | -50..-30 22.3%
    #                    -70..-50 -> 30.6%          | <=-70%  34.7%
    # Beta is monotone the same way (<1.0 10.7% -> >2.5 26.1%): depth stores the energy, beta says the
    # name can actually travel. Both are LEVELS, so they are what we admit on.
    #
    #     admitted  moved >=±2%  54.1%  (1.85x the market), >=+5% 11.0% (vs 5.8% for the axis-union)
    #     ~31 names/session, holding on both folds of the live window.
    #
    # This is NOT a judgment or a hardcoded conclusion — it is the same class of statement as the
    # $400 price cap: a DEFINITION of what this system trades (a deeply compressed, high-beta name)
    # plus a tradeability floor. It says nothing about which way any name goes: the admitted cohort
    # is close to symmetric (up 29.2% / down 24.9%), exactly as intended. 100% of the directional
    # edge must come from the AI's context read — and now that is measurable, because the cohort's
    # own up/down rates are the baseline it has to beat.
    #
    # The axes are still computed and still travel in the digest as DESCRIPTION (which kind of
    # compression, how broad), they simply no longer decide membership.
    #
    # Rollback: RESONANCE_POOL_MODE=axis_union restores the previous gate exactly.
    POOL_MODE = os.environ.get("RESONANCE_POOL_MODE", "movement")
    _depth = (df["coil_pct_from_252hi_admit"] if "coil_pct_from_252hi_admit" in df.columns
              else (df["coil_pct_from_252hi"] if "coil_pct_from_252hi" in df.columns else None))
    _beta = df["prime_beta"] if "prime_beta" in df.columns else None
    _mcap = df["prime_market_cap"] if "prime_market_cap" in df.columns else None
    if POOL_MODE == "movement" and _depth is not None and _beta is not None and _mcap is not None:
        _adm = (_depth <= DEPTH_MAX_PCT_FROM_HI) & (_beta > BETA_MIN) & (_mcap >= MCAP_MIN)
        pooled = set(df.loc[_adm.fillna(False), "sym"])
    else:
        POOL_MODE = "axis_union"
        pooled = axis_union
    # (No membership cooldown: already-released springs are dropped upstream by the loaded_spring
    #  RELEASE reset — a discharged name no longer fires loaded_spring, and compression self-resets.)

    # what the coil prerequisite removed: names the ungated union WOULD have admitted (extreme on
    # any axis, or broad on >= BREADTH_MIN_AXES) but which carry NO qualifying coiled axis — the
    # pure gappers / newsmovers (primed-only, not a spring) this gate exists to reject.
    ungated = set(ext_by_sym) | {s for s, axs in broad_by_sym.items() if len(axs) >= BREADTH_MIN_AXES}
    primed_only_excluded = ungated - axis_union
    # transparency: how the two admissions differ today (never silently swap a pond)
    axis_only = axis_union - pooled          # old gate would have shown these; movement gate does not
    movement_only = pooled - axis_union      # newly visible (the measured cohort the old gate hid)


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
        # how this name would have entered under the OLD axis gate — description only, never a rank.
        # "none" = the movement admission surfaced it and the axis-union would have hidden it.
        row["entry"] = ("extreme" if s in path_extreme
                        else "broad" if s in path_broad else "none")
        digest.append(row)
    # ORDER: alphabetical, deliberately meaningless. It used to sort by n_axes ("breadth of
    # unusualness"), labelled presentation-only — but a forward check found n_axes ANTI-correlates with
    # outcome (2-axis names cleared +2% at 18%, 3-axis 16%, 4-axis just 7%), because the compression
    # axes are largely redundant: stacking atr+bb+rvol+consol mostly means "extremely asleep", not
    # "extremely interesting". Sorting by it silently floated the weakest names to the top of the page.
    # A neutral order can mislead nobody.
    digest.sort(key=lambda d: d["sym"])

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
    # SUPERSEDED 2026-09-04: the shortlist existed because the pool was a near-random pond and the
    # measured winner cohort had to be pointed at from inside it. The pool IS that cohort now
    # (section 3b admits on exactly these dimensions), so the shortlist no longer narrows anything.
    # It is kept populated — equal to the pool — so nothing downstream breaks and the meaning is
    # unchanged ("the measured cohort"); it is simply no longer a second, tighter cut. Under
    # RESONANCE_POOL_MODE=axis_union it reverts to the old narrowing behaviour.
    SL_BETA_MIN = 1.5
    # TRADEABILITY floor — the same class of constraint as PRICE_CAP (what the account can actually
    # transact), NOT a judgment axis. Without it the cohort's mean was distorted by a single sub-$300M
    # name that printed a +194% open-to-close day: it lifted the average from +0.59% to +3.03% while
    # leaving the median (+0.31%) and hit-rate (36-38%) untouched — i.e. pure tail noise from a name
    # nobody could have transacted at size. Any floor ($100M cap, or ~$5M/day traded) removes exactly
    # that one name and nothing else, so this costs no real candidate.
    SL_MCAP_MIN = 100e6
    shortlist = []
    for row in digest:
        if POOL_MODE == "axis_union":
            if "loaded_spring" not in (row.get("axes") or []):
                continue
            if (row.get("beta") or 0) <= SL_BETA_MIN:
                continue
            if (row.get("market_cap") or 0) < SL_MCAP_MIN:
                continue
        b, pv = row.get("beta"), row.get("pm_vol_vs_avg")
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

    # 4d) COHORT BASELINE — what this pond has actually done lately, computed from the last N sessions.
    # This is the number the AI's direction read has to BEAT. The pool is deliberately near-symmetric
    # (it concentrates movement, it does not pick sides), so "the cohort rose 28% of the time" is the
    # honest null hypothesis for every pick: a plan that takes names which clear +2% at 28% has added
    # nothing. It is computed ROLLING, never hardcoded, so it re-measures itself as the regime changes
    # and can never quietly go stale the way a written-down base rate does.
    # SPLIT-ARTIFACT EXCLUSIONS — count them, because a silent exclusion is how the release-reset bug
    # hid. `coil_dd_suspect` marks a name whose 252-day high looks pre-split, so its measured drawdown is
    # an artifact; build.py nulls `pct_from_252hi` for those, which under this admission removes them
    # from the pool. Unlike the release reset that is CORRECT — admitting on a depth we know is wrong
    # would be admitting on garbage — but it must be visible. Measured over 29 sessions: ~4.7 flagged a
    # day, of which ~1 would otherwise have qualified (29 name-days: 34.5% cleared +2%, EV +1.14%).
    # Those returns are not evidence the exclusion is costing us: a name that only LOOKS deeply fallen
    # is not the cohort this system trades, so it was never a candidate on the merits.
    dd_suspect_excluded = 0
    if "coil_dd_suspect" in df.columns:
        _sus = df["coil_dd_suspect"].fillna(False).astype(bool)
        _would = _sus & (df.get("prime_beta", 0) > BETA_MIN) & (df.get("prime_market_cap", 0) >= MCAP_MIN)
        dd_suspect_excluded = int(_would.sum())

    lookback_hint = 20
    cohort_baseline = _cohort_baseline(date, cache_dir, lookback=lookback_hint)

    # 4e) SNAPSHOT STAMP — the premarket columns (gap_pct, pm_vol_vs_avg, pm_range_pct) are read from
    # the tape AS IT STANDS WHEN THIS RUNS, typically ~09:00-09:05 ET. The brain decides ~20 minutes
    # later, and in that window a gap can more than halve: one replay quoted a digest gap of +11.77%
    # for a name that was +2.88% at the decision minute. The row is a SNAPSHOT, not the state at the
    # bell, so its age has to be visible rather than inferred.
    try:
        _now = datetime.datetime.now(datetime.timezone.utc).astimezone(
            datetime.timezone(datetime.timedelta(hours=-4)))
        built_at = _now.strftime("%Y-%m-%d %H:%M:%S ET")
    except Exception:
        built_at = None

    axis_contrib = {ax["name"]: len(extreme[ax["name"]]) for ax in AXES}
    dropped = buyable_size - len(pooled)

    # 5) transparency log (principle: never silently cap — say what was dropped)
    coiled = [a for a in AXES if a["group"] == "coiled"]
    primed = [a for a in AXES if a["group"] == "primed"]
    lines = [
        f"resonance pool — {date}",
        f"  universe={universe_size}  ->  price-cap <${PRICE_CAP:.0f} dropped {price_capped} (unbuyable on small capital)  ->  buyable={buyable_size}",
        f"  buyable={buyable_size}  ->  POOL={len(pooled)}   (mode={POOL_MODE})",
        (f"  SNAPSHOT: premarket columns (gap_pct, pm_vol_vs_avg, pm_range_pct) are as of {built_at} "
         f"— RECOMPUTE them from the tape at your decision minute before quoting them in a gate."
         if built_at else ""),
        (f"  ADMISSION (movement): off-252d-high <= {DEPTH_MAX_PCT_FROM_HI:.0f}%  AND  beta > {BETA_MIN}  "
         f"AND  mcap >= ${MCAP_MIN/1e9:.1f}B  — concentrates MOVEMENT (measured 54% of admitted names "
         f"travel >=±2% vs 29% for the market and 30% for the old axis gate). Direction stays the AI's job."
         if POOL_MODE == "movement" else
         f"  ADMISSION (axis_union, ROLLBACK MODE): coil prerequisite — >=1 coiled axis required."),
        f"  vs the old axis-union gate: it would have shown {len(axis_union)} names — "
        f"{len(axis_only)} of those are NOT admitted here, and {len(movement_only)} names it hid ARE. "
        f"(overlap {len(pooled & axis_union)})",
        f"  primed-only (would fail the old coil prerequisite): {len(primed_only_excluded)}.",
        (f"  SPLIT-ARTIFACT: {dd_suspect_excluded} name(s) excluded because their 252d high looks "
         f"pre-split, so the measured depth is an artifact — not admitted on a number we know is wrong."
         if dd_suspect_excluded else ""),
        f"  RELEASE RESET: {released_reset} names had the loaded_spring AXIS neutralized (popped "
        f">={RELEASE_UP_PCT:.0f}% recently). They REMAIN in the pool, flagged `released_recently` — the "
        f"reset scopes the axis, not membership (measured: these clear +2% at 37.3% vs 27.6% admitted).",
        f"  [old-gate reference only] axis entry paths: "
        f"EXTREME top-{PRIMARY_K} on a coiled axis -> {len(path_extreme)} names   |   "
        f"BROAD top-{BREADTH_Q:.0%} on >={BREADTH_MIN_AXES} axes (>=1 coiled) -> {len(path_broad)} "
        f"(+{len(path_broad - path_extreme)} unique)",
        (f"  SHORTLIST == POOL ({len(shortlist)}): the pool IS the measured cohort now, so the shortlist "
         f"no longer narrows. rank_in_pool is the read."
         if POOL_MODE == "movement" else
         f"  SHORTLIST (loaded_spring + beta>{SL_BETA_MIN}) -> {len(shortlist)} names"
         + (": " + ", ".join(d["sym"] for d in shortlist) if shortlist else " (none today)")),
        "  axes are DESCRIPTION only now (which kind of compression) — they no longer decide membership.",
        (f"  COHORT BASELINE (rolling, last {cohort_baseline['sessions']} sessions, "
         f"{cohort_baseline['name_days']} name-days): moved >=±2% {cohort_baseline['moved_pct']}%  |  "
         f"UP >=+2% {cohort_baseline['up_pct']}%   DOWN <=-2% {cohort_baseline['down_pct']}%   "
         f"median {cohort_baseline['median_pct']:+.2f}%  <- the number a direction read must BEAT"
         + ("".join(
             f"\n      by gap sign — {('UP-gap' if k == 'up_gap' else 'DOWN-gap'):8s}: "
             f"up {v['up_pct']}%  down {v['down_pct']}%  EV {v['ev_pct']:+.2f}%  (n={v['name_days']})"
             for k, v in (cohort_baseline.get("by_gap_sign") or {}).items())
            if cohort_baseline.get("by_gap_sign") else "")
         + f"\n      (measures the pool AS WRITTEN on those sessions; after an admission change it "
           f"takes ~{lookback_hint} sessions to converge on the new pond)"
         if cohort_baseline else "  COHORT BASELINE: not enough prior pool files to measure yet."),
        "  per-axis EXTREME contribution (top-K):",
        "    COILED  " + "  ".join(f"{a['name']}={axis_contrib[a['name']]}" for a in coiled),
        "    PRIMED  " + "  ".join(f"{a['name']}={axis_contrib[a['name']]}" for a in primed),
    ]
    log = "\n".join(lines)

    result = {
        "date": date,
        "built_at": built_at,       # premarket columns are as of THIS time, not the decision minute
        "universe_size": universe_size,
        "price_capped": price_capped,
        "buyable_size": buyable_size,
        "pool_size": len(pooled),
        "pool_mode": POOL_MODE,
        "admission": ({"depth_max_pct_from_hi": DEPTH_MAX_PCT_FROM_HI, "beta_min": BETA_MIN,
                       "mcap_min": MCAP_MIN} if POOL_MODE == "movement" else {"gate": "coil_prerequisite"}),
        "axis_union_size": len(axis_union),
        "axis_only_excluded": sorted(axis_only),
        "movement_only_added": sorted(movement_only),
        "dropped": dropped,
        "primed_only_excluded": len(primed_only_excluded),
        "released_reset": released_reset,
        "n_extreme": len(path_extreme),
        "n_broad": len(path_broad),
        "axis_contrib": axis_contrib,
        "dd_suspect_excluded": dd_suspect_excluded,  # split-artifact names that would else qualify
        "cohort_baseline": cohort_baseline,   # rolling null hypothesis the AI must beat (see 4d)
        "shortlist": shortlist,          # == pool under movement mode (see 4b)
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
    print(f"\n  sample of the pool (alphabetical — the order is NOT a ranking) — RAW components:")
    for d in res["digest"][: a.show]:
        print(f"    {d['sym']:6s} {str(d.get('sector'))[:14]:14s} [{d['entry']:7s}] "
              f"axes[{d['n_axes']}]={','.join(d['axes'])}")


if __name__ == "__main__":
    main()
