"""swing/features/mechanical.py — the PREDICTABLE layer for the swing sibling of resonance.

Measures volatility COMPRESSION + trend LEADERSHIP mechanically from daily bars — the swing
analog of resonance's coil. Two well-known, structurally-real compression patterns:
  - TTM Squeeze (Carter): Bollinger Bands inside Keltner Channels = volatility coiled/loaded.
  - VCP (Minervini): a leader making progressively TIGHTER pullbacks on DRYING volume.

Philosophy (same as resonance): NO hardcoded 'buy' thresholds. Everything is either a raw pattern
definition (BB-in-KC) or measured RELATIVE to the stock's own history (percentile of its own ATR).
Direction / catalyst / regime are NOT decided here — that is the AI's job (brain/decide.md). This
layer only answers, mechanically: "how compressed, and how strong, is this name right now."

Point-in-time safe (consumes bars with date < asof; resonance.data.access.daily enforces it).
Pure read. Touches NOTHING in resonance/.

compute(bars) -> dict of mechanical features, or None if too little history.
  bars: list of {d,o,h,l,c,v} oldest->newest (exactly what access.daily(...)['bars'] returns).
"""
import numpy as np


def _sma_series(a, n):
    out = np.full(len(a), np.nan)
    if len(a) >= n:
        cs = np.cumsum(np.insert(a, 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _ema_series(a, n):
    e = np.full(len(a), np.nan)
    if len(a) < n:
        return e
    k = 2.0 / (n + 1)
    e[n - 1] = np.mean(a[:n])
    for i in range(n, len(a)):
        e[i] = a[i] * k + e[i - 1] * (1 - k)
    return e


def _rolling_std(a, n):
    out = np.full(len(a), np.nan)
    for i in range(n - 1, len(a)):
        out[i] = np.std(a[i - n + 1:i + 1])  # population std (ddof=0), matches most charting
    return out


def _true_range(h, l, c):
    tr = np.empty(len(c))
    tr[0] = h[0] - l[0]
    for i in range(1, len(c)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return tr


def _atr_series(h, l, c, n):
    return _ema_series(_true_range(h, l, c), n)


def _pct_rank(series, value):
    """Percentile of `value` within the finite entries of series (0=lowest, 1=highest)."""
    s = series[np.isfinite(series)]
    if len(s) == 0 or not np.isfinite(value):
        return None
    return float((s < value).mean())


def _pivots(arr, k, kind):
    idx = []
    for i in range(k, len(arr) - k):
        w = arr[i - k:i + k + 1]
        if kind == "high" and arr[i] == w.max():
            idx.append(i)
        elif kind == "low" and arr[i] == w.min():
            idx.append(i)
    return idx


def _contractions(h, l, look=70, k=3):
    """Sequence of recent pullback depths (peak->trough %), newest last. VCP = these SHRINK."""
    h2, l2 = h[-look:], l[-look:]
    highs = _pivots(h2, k, "high")
    depths = []
    for hi in highs:
        seg_lows = [l2[j] for j in range(hi + 1, len(l2))]
        if seg_lows:
            trough = min(seg_lows)
            if h2[hi] > 0:
                depths.append(round((h2[hi] - trough) / h2[hi] * 100, 2))
    depths = depths[-4:]  # last few contractions
    is_contracting = len(depths) >= 2 and all(
        depths[i] <= depths[i - 1] + 1e-9 for i in range(1, len(depths))
    )
    return depths, is_contracting


def compute(bars, min_bars=150):
    if not bars or len(bars) < min_bars:
        return None
    o = np.array([b["o"] for b in bars], float)
    h = np.array([b["h"] for b in bars], float)
    l = np.array([b["l"] for b in bars], float)
    c = np.array([b["c"] for b in bars], float)
    v = np.array([b["v"] if b["v"] is not None else 0 for b in bars], float)
    if np.any(~np.isfinite(c)) or c[-1] <= 0:
        return None
    px = float(c[-1])

    # ---- trend / leadership (Minervini-style stack, no tuned numbers, just the ordering) ----
    sma20 = _sma_series(c, 20)
    sma50 = _sma_series(c, 50)
    sma150 = _sma_series(c, 150)
    stack_n = 0
    if np.isfinite(sma20[-1]) and px > sma20[-1]:
        stack_n += 1
    if np.isfinite(sma20[-1]) and np.isfinite(sma50[-1]) and sma20[-1] > sma50[-1]:
        stack_n += 1
    if np.isfinite(sma50[-1]) and np.isfinite(sma150[-1]) and sma50[-1] > sma150[-1]:
        stack_n += 1
    uptrend = bool(px > sma50[-1]) if np.isfinite(sma50[-1]) else False
    sma150_rising = np.isfinite(sma150[-6]) and sma150[-1] > sma150[-6]

    # ---- TTM Squeeze (BB inside KC = coiled) ----
    std20 = _rolling_std(c, 20)
    ema20 = _ema_series(c, 20)
    atr20 = _atr_series(h, l, c, 20)
    bb_up, bb_lo = sma20 + 2 * std20, sma20 - 2 * std20
    kc_up, kc_lo = ema20 + 1.5 * atr20, ema20 - 1.5 * atr20
    on = (bb_up < kc_up) & (bb_lo > kc_lo)
    squeeze_on = bool(on[-1]) if np.isfinite(bb_up[-1]) and np.isfinite(kc_up[-1]) else False
    # consecutive days currently on
    sq_days = 0
    for i in range(len(on) - 1, -1, -1):
        if on[i]:
            sq_days += 1
        else:
            break
    # fired = was on within last 5 bars, now off (energy just released)
    squeeze_fired = (not squeeze_on) and bool(on[-6:-1].any())

    # TTM momentum histogram: linreg of (close - avg(donchian-mid, sma20)) over 20
    hh = np.array([h[max(0, i - 19):i + 1].max() for i in range(len(h))])
    ll = np.array([l[max(0, i - 19):i + 1].min() for i in range(len(l))])
    mid = ((hh + ll) / 2 + sma20) / 2
    mom_src = c - mid
    seg = mom_src[-20:]
    if np.all(np.isfinite(seg)):
        xr = np.arange(20)
        slope, intercept = np.polyfit(xr, seg, 1)
        mom_val = float(slope * 19 + intercept)  # fitted value at latest bar
    else:
        mom_val = None

    # ---- tightness (relative to the name's OWN 6-month history — no absolute number) ----
    atr_pct_series = np.where(c > 0, atr20 / c * 100, np.nan)
    atr_pct = float(atr_pct_series[-1]) if np.isfinite(atr_pct_series[-1]) else None
    atr_pct_ptile = _pct_rank(atr_pct_series[-126:], atr_pct) if atr_pct is not None else None
    rng10 = float((h[-10:].max() - l[-10:].min()) / px * 100)

    # ---- volume dry-up (contraction fuel) ----
    vol10 = float(v[-10:].mean())
    vol50 = float(v[-50:].mean()) if v[-50:].mean() > 0 else None
    vol_dryup = round(vol10 / vol50, 2) if vol50 else None  # <1 = drying up

    # ---- VCP contraction structure ----
    depths, is_contracting = _contractions(h, l)

    # ==== resonance-style extra compression axes (RAW, direction-agnostic, no tuning) ============
    rng = h - l
    todays_rng = float(rng[-1])
    # NR7 / NR4 — narrowest-range day (Crabel); on daily bars = a coiling swing bar
    nr7 = bool(todays_rng <= rng[-7:].min())
    nr4 = bool(todays_rng <= rng[-4:].min())
    narrowest_of_n = int((rng[-20:] > todays_rng).sum())        # of last 20, how many were WIDER

    # realized-vol contraction: short-window vs long-window std of daily returns (<1 = winding down)
    drets = np.diff(c) / c[:-1]
    rvol_short = float(np.std(drets[-10:]) * 100) if len(drets) >= 10 else None
    rvol_long = float(np.std(drets[-40:]) * 100) if len(drets) >= 40 else None
    rvol_ratio = round(rvol_short / rvol_long, 3) if (rvol_short and rvol_long) else None

    # range contraction: mean daily range last 10d / last 40d (<1 = tightening) — VCP-family
    rpct = np.where(c > 0, rng / c * 100, np.nan)
    m10, m40 = np.nanmean(rpct[-10:]), np.nanmean(rpct[-40:])
    range_contraction = round(float(m10 / m40), 3) if np.isfinite(m40) and m40 else None

    # Bollinger bandwidth percentile (Bollinger squeeze) — LOW = squeezed vs own history
    bbw = np.where(np.isfinite(sma20) & (sma20 != 0), (bb_up - bb_lo) / sma20, np.nan)
    bbw_now = bbw[-1]
    bb_bandwidth_ptile = _pct_rank(bbw[-126:], bbw_now)
    _b106 = bbw[-106:][np.isfinite(bbw[-106:])]
    bb_squeeze_106 = bool(np.isfinite(bbw_now) and _b106.size and bbw_now <= _b106.min())

    # loaded spring: deep prior drawdown from the 252d high (stored energy from a FALL) — a beaten-down
    # coil, the opposite of a leader. resonance admits both; emitted raw, the AI decides if it fits.
    hi_252 = float(h[-252:].max()) if len(h) >= 60 else float(h.max())
    max_drawdown_pct = round((px / hi_252 - 1) * 100, 2) if hi_252 else None
    # ============================================================================================

    # ---- position vs highs ----
    hi_20 = float(h[-20:].max())
    dist_20hi = round((px / hi_20 - 1) * 100, 2) if hi_20 > 0 else None

    # ---- realized-vol floor: distinguish a real coil from a merger/buyout-PINNED flatline.
    # A pinned name has a tiny ATR percentile too (looks "tight") but is dead, not loaded. Average
    # absolute daily return over 20d separates them: coils still breathe (~1%+), pins are ~0%. ----
    rets = np.abs(np.diff(c[-21:]) / c[-21:-1]) * 100 if len(c) >= 21 else np.array([])
    adr20 = float(rets.mean()) if len(rets) else None

    # ---- own returns (for RS vs SPY, computed by the pool) ----
    def _ret(n):
        return round((px / c[-1 - n] - 1) * 100, 2) if len(c) > n and c[-1 - n] > 0 else None
    ret_21, ret_63, ret_126 = _ret(21), _ret(63), _ret(126)

    # NOTE (resonance parity): we do NOT emit a composite "compression score" and we do NOT rank.
    # These are RAW components only — the AI weights them (principle: don't hardcode conclusions).
    return {
        "px": round(px, 2),
        # trend / leadership
        "uptrend": uptrend, "stack_n": stack_n, "sma150_rising": bool(sma150_rising),
        # squeeze
        "squeeze_on": squeeze_on, "squeeze_days": sq_days, "squeeze_fired": squeeze_fired,
        "ttm_mom": round(mom_val, 3) if mom_val is not None else None,
        "ttm_mom_up": (mom_val is not None and mom_val > 0),
        # vcp / tightness
        "atr_pct": round(atr_pct, 2) if atr_pct is not None else None,
        "atr_pct_ptile": round(atr_pct_ptile, 2) if atr_pct_ptile is not None else None,
        "range10_pct": round(rng10, 2),
        "adr20": round(adr20, 2) if adr20 is not None else None,
        "vol_dryup": vol_dryup,
        "contractions": depths, "is_contracting": bool(is_contracting),
        "dist_20hi_pct": dist_20hi,
        # resonance-style extra compression axes (raw; AI weighs)
        "nr7": nr7, "nr4": nr4, "narrowest_of_n": narrowest_of_n,
        "rvol_short": round(rvol_short, 2) if rvol_short is not None else None,
        "rvol_long": round(rvol_long, 2) if rvol_long is not None else None,
        "rvol_ratio": rvol_ratio,
        "range_contraction": range_contraction,
        "bb_bandwidth_ptile": round(bb_bandwidth_ptile, 2) if bb_bandwidth_ptile is not None else None,
        "bb_squeeze_106": bb_squeeze_106,
        "max_drawdown_pct": max_drawdown_pct,
        # returns (RS filled in by pool vs SPY)
        "ret_21": ret_21, "ret_63": ret_63, "ret_126": ret_126,
    }
