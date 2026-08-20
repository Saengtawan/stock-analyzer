"""resonance / features / coil.py — COMPRESSION / stored-energy features.

MECHANICAL. Zero AI tokens. Pure ta-lib/pandas/numpy compute over a name's own recent daily
series (the `bars` handed back by `data.access.daily()`). Everything here is
**direction-agnostic** — it measures how *tightly wound* a stock is versus its OWN normal, not
which way it might go. The AI weights these raw components later; we do NOT emit a single
"coil score" (principle: don't hardcode conclusions).

The bet (README): volatility clusters and mean-reverts, so a name that is unusually QUIET vs its
own history is *due* for a move — magnitude is predictable even when direction is not. So each
component answers a version of "is range unusually tight right now, and how long has it been
that way / how much energy got stored?" — with enough context (the raw value AND its own-history
percentile) that the AI can interpret it.

Raw components returned (per symbol), each a plain number or None when history is too short:

  price / context
    last_close, n_bars
    pct_from_252hi, pct_from_252lo        distance from the name's own 52w extremes

  ATR compression
    atr_pct                               ATR(14) as % of close, NOW
    atr_pct_median                        median of that series over the window
    atr_pct_pctile                        percentile of NOW vs its own history (LOW = tight/coiled)

  Bollinger squeeze
    bb_bandwidth                          (upper-lower)/mid *100 using BBANDS(20,2), NOW
    bb_bandwidth_median
    bb_bandwidth_pctile                   LOW = squeeze
    bb_squeeze_106                        is NOW bandwidth the lowest in the last 106 bands? (bool)

  narrow-range flags
    todays_range_pct                      today's H-L as % of close
    nr7                                   today's range narrowest of the last 7 (bool)
    nr4                                    ... last 4 (bool)
    narrowest_of_n                        how many of the last 20 days had a WIDER range than today

  realized-vol contraction
    rvol_short                            annualized stdev of daily log-returns, short window (~10d)
    rvol_long                             ... long window (~60d)
    rvol_ratio                            short/long  (<1 = contracting)
    rvol_short_pctile                     percentile of the rolling short-rvol series (LOW = quiet)

  consolidation length / range contraction
    consol_len                            consecutive recent QUIET days. A day is "quiet" only if BOTH
                                          its close-to-close move (|daily return|) AND its intraday H-L
                                          range are small; ANY big move RESETS the streak to 0. (This
                                          measures "how long has it been genuinely still", NOT "loaded".)
    range_contraction                     mean range last 10d / mean range last 40d (<1 = tightening)

  recent move / discharge (has the spring ALREADY released? — a coil must be QUIET, not just loaded)
    recent_max_abs_move_5d                max |daily return| over the last ~5 PRIOR trading days
                                          (HIGH = recently violent / a falling knife, NOT quiet)
    abs_ret_3d                            |cumulative 3-prior-day return| (magnitude of the recent run)
    last_ret_1d                           signed most-recent completed day's close-to-close return
    max_up_move_2d                        biggest UP day in the last 2 prior days (HIGH = already popped)

  raw recent daily returns (point-in-time, date<asof — NO flag, NO threshold, NO judgment; just the
  numbers so a reader/AI can SEE whether the spring already fired and decide "discharged" itself)
    recent_daily_rets                     list of the last ~5 prior close-to-close daily % returns,
                                          MOST-RECENT FIRST (e.g. AXTI [+29.x, +27.x, -13.x, ...])
    ret_prev1d                            signed most-recent completed day's close-to-close % return
    ret_prev2d                            the day before that
    ret_prev3d                            the day before that

  loaded spring (a big PRIOR move that stored energy — e.g. AXTI 143 -> 37)
    max_drawdown_pct                      deepest peak->trough drop within the window (magnitude)
    ret_63d                               ~quarter return (context for the drawdown)
    pct_from_window_high                  last_close vs the highest high in the window
    range_252_pct                         (252hi-252lo)/252lo *100 — how much ground the name covers

Return: dict[str -> float|bool|None]. No weighting, no ranking.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import talib

# window knobs (trading days)
_ATR = 14
_BB = 20
_RVOL_SHORT = 10
_RVOL_LONG = 60
_MIN_BARS = 30          # below this we cannot compute stable percentiles
_TRADING_YEAR = 252

# --- consol_len is RELATIVE to each stock's own norm (no absolute vol threshold) ------------------
# A "quiet day" = both its close-to-close move AND its intraday range are BELOW the stock's own
# trailing median (i.e. it is genuinely compressing vs itself), not below a fixed 4%/5%. The old
# absolute cut (4%/5%) rewarded STRUCTURALLY-calm names: a utility whose normal day is ~0.8% never
# broke the streak, so consol_len saturated (287) and it sat in the pool forever without ever being
# "coiled". Relative-to-self, a utility at its normal vol oscillates around its own median -> the
# streak breaks constantly (consol_len small), while a name tightening BELOW its own (more volatile)
# baseline accumulates a real streak. Aligns consol with the self-percentile axes (atr/bb).
_CONSOL_BASELINE_MIN = 20  # need this many finite days to have a meaningful own-baseline median
_RECENT_MOVE_WIN = 5       # look-back = 5 trading days = 1 calendar week (spring cooldown window)
# Split-adjustment artifact guard for the drawdown / loaded_spring axis: an UNadjusted split shows
# as a single-day close ratio far outside any real daily move and fakes a huge drawdown (BKNG -97%,
# NINE -98.9% while only -23% from its 252d high). A liquid coil name does not move >~45% down or
# >~80% up in one real session; such a step is a split/data break. We rebase across it before
# measuring drawdown. Conservative by design: a false positive only means loaded_spring does not
# fire on that name (a cleaner miss), never a fake spring contaminating the pool.
_SPLIT_LO = 0.55           # one-day close ratio below this (>45% drop) = split-like down break
_SPLIT_HI = 1.80           # one-day close ratio above this (>80% gain) = split-like up break (reverse split)


def _series(bars):
    """bars: list of {d,o,h,l,c,v} oldest->newest (from access.daily). -> aligned float arrays."""
    o = np.array([b["o"] for b in bars], dtype=float)
    h = np.array([b["h"] for b in bars], dtype=float)
    l = np.array([b["l"] for b in bars], dtype=float)
    c = np.array([b["c"] for b in bars], dtype=float)
    return o, h, l, c


def _pctile(series, value):
    """Fraction of finite history strictly below `value` (0..1). None if nothing to compare."""
    if value is None or not np.isfinite(value):
        return None
    arr = np.asarray(series, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    return float((arr < value).mean())


def _f(x, nd=4):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return round(v, nd)


def compute_coil(daily_digest):
    """daily_digest: the dict returned by access.daily() (has `bars`, and 52w context fields).
    Returns the raw compression component dict (see module docstring)."""
    bars = (daily_digest or {}).get("bars") or []
    n = len(bars)
    out = {"n_bars": n,
           "last_close": _f((daily_digest or {}).get("last_close"), 3),
           "pct_from_252hi": _f((daily_digest or {}).get("pct_from_252hi"), 3),
           "pct_from_252lo": _f((daily_digest or {}).get("pct_from_252lo"), 3)}

    if n < _MIN_BARS:
        # not enough history for stable percentiles — return context-only, rest None
        for k in ("atr_pct", "atr_pct_median", "atr_pct_pctile", "bb_bandwidth",
                  "bb_bandwidth_median", "bb_bandwidth_pctile", "bb_squeeze_106",
                  "todays_range_pct", "nr7", "nr4", "narrowest_of_n",
                  "rvol_short", "rvol_long", "rvol_ratio", "rvol_short_pctile",
                  "consol_len", "range_contraction", "max_drawdown_pct", "ret_63d",
                  "pct_from_window_high", "range_252_pct",
                  "recent_max_abs_move_5d", "abs_ret_3d", "last_ret_1d", "max_up_move_2d",
                  "ret_prev1d", "ret_prev2d", "ret_prev3d"):
            out[k] = None
        out["recent_daily_rets"] = []            # raw list — empty when history too short
        return out

    o, h, l, c = _series(bars)

    # ---- ATR compression -----------------------------------------------------------------
    atr = talib.ATR(h, l, c, timeperiod=_ATR)
    atr_pct_series = atr / c * 100.0
    atr_pct_now = atr_pct_series[-1]
    out["atr_pct"] = _f(atr_pct_now)
    out["atr_pct_median"] = _f(np.nanmedian(atr_pct_series))
    out["atr_pct_pctile"] = _f(_pctile(atr_pct_series[:-1], atr_pct_now))

    # ---- Bollinger squeeze ----------------------------------------------------------------
    up, mid, low = talib.BBANDS(c, timeperiod=_BB, nbdevup=2, nbdevdn=2)
    bbw_series = (up - low) / mid * 100.0
    bbw_now = bbw_series[-1]
    out["bb_bandwidth"] = _f(bbw_now)
    out["bb_bandwidth_median"] = _f(np.nanmedian(bbw_series))
    out["bb_bandwidth_pctile"] = _f(_pctile(bbw_series[:-1], bbw_now))
    recent_bbw = bbw_series[-106:]
    recent_bbw = recent_bbw[np.isfinite(recent_bbw)]
    out["bb_squeeze_106"] = bool(np.isfinite(bbw_now) and recent_bbw.size and bbw_now <= recent_bbw.min())

    # ---- narrow-range flags ---------------------------------------------------------------
    rng = h - l                                   # true daily range (H-L), absolute
    rng_pct = rng / c * 100.0
    todays_rng = rng[-1]
    out["todays_range_pct"] = _f(rng_pct[-1])
    out["nr7"] = bool(todays_rng <= rng[-7:].min())
    out["nr4"] = bool(todays_rng <= rng[-4:].min())
    last20 = rng[-20:]
    out["narrowest_of_n"] = int((last20 > todays_rng).sum())   # how many of last 20 were wider

    # ---- realized-vol contraction ---------------------------------------------------------
    logret = np.diff(np.log(c))
    def _rvol(win):
        if logret.size < win:
            return None
        return float(np.std(logret[-win:], ddof=1) * np.sqrt(_TRADING_YEAR) * 100.0)
    rv_s = _rvol(_RVOL_SHORT)
    rv_l = _rvol(_RVOL_LONG)
    out["rvol_short"] = _f(rv_s)
    out["rvol_long"] = _f(rv_l)
    out["rvol_ratio"] = _f(rv_s / rv_l) if (rv_s and rv_l) else None
    # rolling short-rvol series for a self-percentile (is current quiet vs its own norm?)
    rser = pd.Series(logret).rolling(_RVOL_SHORT).std(ddof=1) * np.sqrt(_TRADING_YEAR) * 100.0
    rser = rser.to_numpy()
    out["rvol_short_pctile"] = _f(_pctile(rser[:-1], rser[-1] if rser.size else None))

    # ---- consolidation length: consecutive recent QUIET days ------------------------------
    # A day is "quiet" only if BOTH its close-to-close move AND its intraday range are small; ANY
    # big move RESETS the streak. (OLD BUG: compared H-L to the window median ONLY and never looked
    # at close-to-close return — so a name doing ±10-13% DAILY moves kept counting as "quiet"
    # because the median range was itself inflated by the volatility. AXTI reported 18 quiet days
    # while it was melting down. consol_len must mean "genuinely still", not "loaded".)
    ret_pct = np.diff(c) / c[:-1] * 100.0             # close-to-close daily % moves; [-1] = most recent (D-1)
    abs_ret = np.full(n, np.nan)
    abs_ret[1:] = np.abs(ret_pct)                     # bar 0 has no prior day -> no return
    # own-baseline medians (relative reference — a day is "quiet" only if compressed vs ITSELF).
    ref_absret = np.nanmedian(abs_ret) if np.isfinite(abs_ret).sum() >= _CONSOL_BASELINE_MIN else np.nan
    ref_range = np.nanmedian(rng_pct) if np.isfinite(rng_pct).sum() >= _CONSOL_BASELINE_MIN else np.nan
    consol = 0
    if np.isfinite(ref_absret) and np.isfinite(ref_range):
        for i in range(n - 1, 0, -1):                 # newest -> older; stop before bar 0 (no return)
            quiet = (np.isfinite(abs_ret[i]) and abs_ret[i] < ref_absret
                     and np.isfinite(rng_pct[i]) and rng_pct[i] < ref_range)
            if quiet:
                consol += 1
            else:
                break
    out["consol_len"] = int(consol)
    m10 = np.nanmean(rng[-10:]) if n >= 10 else np.nan
    m40 = np.nanmean(rng[-40:]) if n >= 40 else np.nanmean(rng)
    out["range_contraction"] = _f(m10 / m40) if (np.isfinite(m10) and np.isfinite(m40) and m40) else None

    # ---- loaded spring (prior move / stored energy) --------------------------------------
    # Clean split-adjustment artifacts before measuring drawdown (see _SPLIT_LO/_SPLIT_HI). A raw
    # split discontinuity in `c` fakes a -90%+ drawdown and fires loaded_spring on a name that never
    # fell (BKNG/NINE 08-19). Rebase every bar by the product of all split-like steps at-or-after it
    # so the drawdown is measured on a continuous, split-consistent series.
    c_adj = c.astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        step = c_adj[1:] / c_adj[:-1]                          # step[i] = ratio from bar i to bar i+1
    split_idx = np.where(np.isfinite(step) & ((step < _SPLIT_LO) | (step > _SPLIT_HI)))[0]
    if split_idx.size:
        factor = np.ones(n)
        for i in split_idx:                                   # rebase bars 0..i by this break's ratio
            factor[: i + 1] *= step[i]
        c_adj = c_adj * factor
    out["max_drawdown_artifact"] = bool(split_idx.size)       # surfaced so the pool/AI can see the clean-up
    run_max = np.maximum.accumulate(c_adj)
    dd = (c_adj / run_max - 1.0) * 100.0
    out["max_drawdown_pct"] = _f(np.nanmin(dd))               # most negative = deepest prior fall (split-clean)
    out["ret_63d"] = _f((c[-1] / c[-64] - 1.0) * 100.0) if n >= 64 else None
    win_hi = np.nanmax(h)
    out["pct_from_window_high"] = _f((c[-1] / win_hi - 1.0) * 100.0) if win_hi else None
    win_hi252 = np.nanmax(h[-_TRADING_YEAR:])
    win_lo252 = np.nanmin(l[-_TRADING_YEAR:])
    out["range_252_pct"] = _f((win_hi252 - win_lo252) / win_lo252 * 100.0) if win_lo252 else None

    # ---- recent move / discharge (has the spring ALREADY released?) -----------------------
    # loaded_spring (deep drawdown / far from 52w high) fires on a name that has fallen a LOT — but
    # that is equally a "falling knife that just exploded". These fields quantify how VIOLENT the
    # name has been in the last few PRIOR sessions, so the pool can require a coil to be genuinely
    # QUIET (not-yet-released) and reject a knife that already popped. All point-in-time (date<asof).
    if ret_pct.size:
        recent = ret_pct[-_RECENT_MOVE_WIN:]                          # last <=5 prior trading days
        out["recent_max_abs_move_5d"] = _f(float(np.nanmax(np.abs(recent))))
        out["last_ret_1d"] = _f(float(ret_pct[-1]))                   # signed most-recent-day move
        out["max_up_move_2d"] = _f(float(np.nanmax(ret_pct[-2:])))    # biggest UP day in last 2 (pop)
        # RAW recent daily returns — most-recent first, plain numbers. NO flag / threshold / verdict:
        # just the series so a reader (the AI) can SEE if the spring already fired and judge for itself.
        out["recent_daily_rets"] = [_f(float(x), 2) for x in recent[::-1]]
        out["ret_prev1d"] = _f(float(ret_pct[-1]), 2)
        out["ret_prev2d"] = _f(float(ret_pct[-2]), 2) if ret_pct.size >= 2 else None
        out["ret_prev3d"] = _f(float(ret_pct[-3]), 2) if ret_pct.size >= 3 else None
    else:
        out["recent_max_abs_move_5d"] = out["last_ret_1d"] = out["max_up_move_2d"] = None
        out["recent_daily_rets"] = []
        out["ret_prev1d"] = out["ret_prev2d"] = out["ret_prev3d"] = None
    out["abs_ret_3d"] = _f(abs((c[-1] / c[-4] - 1.0) * 100.0)) if n >= 4 else None

    return out


# ------------------------------------------------------------------------------------- CLI
if __name__ == "__main__":
    import argparse
    import json
    from resonance.data import access
    ap = argparse.ArgumentParser(description="coil (compression) features for one symbol")
    ap.add_argument("sym"); ap.add_argument("asof"); ap.add_argument("lookback", nargs="?", default="300")
    a = ap.parse_args()
    dg = access.daily(a.sym, a.asof, int(a.lookback))
    print(json.dumps({"sym": a.sym, "asof": a.asof, **compute_coil(dg)}, indent=2, default=str))
