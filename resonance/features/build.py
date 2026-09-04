"""resonance / features / build.py — run coil+prime across the FULL active universe (~1000) for a
date, EFFICIENTLY, and write one compact per-symbol feature table to cache/.

MECHANICAL. Zero AI tokens. This is the batch that runs once before the open. To stay fast we
BULK-READ each DB feed a handful of times (not ~7000 per-symbol queries): one windowed pull per
table, grouped in pandas, reshaped into the SAME digest dicts that data.access returns, then fed
through compute_coil / compute_prime. The output keeps RAW components only — no weighting, no
final score (the AI weights later).

  python -m resonance.features.build 2026-07-30              # build + write parquet
  python -m resonance.features.build 2026-07-30 --selftest   # + AXTI vs CAG + top-15 eyeball

Output: resonance/cache/features_<DATE>.parquet  (one row per symbol, coil_* / prime_* columns).
"""
from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
import time
import zoneinfo

import numpy as np
import pandas as pd

from resonance.data import access
from resonance.features.coil import compute_coil
from resonance.features.prime import compute_prime

DB = access.DB
ET = zoneinfo.ZoneInfo("America/New_York")
PM_LO, PM_HI = access.PM_WINDOW              # '04:00','09:30'
CACHE = "resonance/cache"


# --------------------------------------------------------------------------- db plumbing
def _conn():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def _read(conn, sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


def _d(x, nd=3):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), nd)


# --------------------------------------------------------------- bulk daily -> coil digests
def bulk_daily(conn, asof, cal_days=420):
    """One windowed pull of daily OHLCV for the whole universe -> {sym: access.daily-shaped digest}
    (bars oldest->newest + 52w context). cal_days must cover ~252 trading bars + ATR/BB warmup."""
    lo = (datetime.date.fromisoformat(asof) - datetime.timedelta(days=cal_days)).isoformat()
    yr = (datetime.date.fromisoformat(asof) - datetime.timedelta(days=365)).isoformat()
    df = _read(conn,
               """SELECT symbol, date, open, high, low, close, volume FROM stock_daily_ohlc
                  WHERE date >= ? AND date < ? ORDER BY symbol, date""",
               (lo, asof))
    out = {}
    for sym, g in df.groupby("symbol", sort=False):
        # g is already date-sorted within symbol by the ORDER BY above
        bars = [{"d": d, "o": _d(o, 3), "h": _d(h, 3), "l": _d(l, 3), "c": _d(c, 3),
                 "v": int(v) if pd.notna(v) else None}
                for d, o, h, l, c, v in zip(g["date"], g["open"], g["high"], g["low"],
                                            g["close"], g["volume"])]
        closes = [b["c"] for b in bars if b["c"] is not None]
        last_close = closes[-1] if closes else None
        g52 = g[g["date"] >= yr]
        hi252 = float(g52["high"].max()) if len(g52) else None
        lo252 = float(g52["low"].min()) if len(g52) else None
        # SPLIT-ARTIFACT GUARD (added 09-04). `stock_daily_ohlc` is not always split-adjusted, so a name
        # that split shows a PRE-split 252d high against a POST-split last close and reports a fake, huge
        # drawdown. That matters more than it sounds: depth off the 252d high is the single strongest
        # winner dimension in this pool, so a fake -96% puts a broken row straight into the winner region.
        # Audit on one session found 4 of 41 pooled names with a corrupted high (one implied a $5,629 high
        # against a real $221 — off by 24x). Detect it structurally: if the 252d high towers over the
        # name's OWN recent trading range, the old bars are on a different share basis. Neutralize the
        # derived depth (leave the raw high visible + flag it) rather than guessing an adjustment factor.
        # Two independent tells, because a split can be recent (recent bars still pre-split) or old:
        #  (a) the 252d high towers over the name's own recent range, and
        #  (b) a DISCONTINUITY — one session where the close falls >=45% and simply stays there. A real
        #      crash bleeds over sessions and usually retraces some; an unadjusted split is an instant,
        #      permanent step down. This is what separates a genuine -85% drawdown (the winner shape we
        #      WANT) from a bookkeeping artifact (which must not be allowed to fake that shape).
        recent_hi = max((b["c"] for b in bars[-60:] if b["c"] is not None), default=None)
        _towers = bool(hi252 and recent_hi and hi252 > 3.0 * recent_hi)
        _step = False
        _cl = [b["c"] for b in bars if b["c"] is not None]
        for i in range(1, len(_cl)):
            if _cl[i-1] and _cl[i] and _cl[i] <= 0.55 * _cl[i-1]:
                after = _cl[i:i+10]
                if after and max(after) < 0.75 * _cl[i-1]:   # never came back = a step, not a selloff
                    _step = True
                    break
        dd_suspect = bool(_towers or _step)
        _pct_hi = (_d((last_close / hi252 - 1) * 100)
                   if (last_close and hi252 and not dd_suspect) else None)
        out[sym] = {
            "sym": sym, "asof": asof, "n": len(bars),
            "last_close": last_close,
            "hi_252": _d(hi252, 3), "lo_252": _d(lo252, 3),
            "dd_suspect": dd_suspect,        # True = 252d high looks pre-split; depth NOT trustworthy
            "pct_from_252hi": _pct_hi,
            "pct_from_252lo": _d((last_close / lo252 - 1) * 100) if (last_close and lo252) else None,
            "bars": bars,
        }
    return out


# ----------------------------------------------------- bulk premarket -> premarket digests
def bulk_premarket(conn, asof, daily_digests, avg_sessions=20, cal_days=40):
    """Premarket wake for every symbol on `asof` + each name's own 20-session premkt-vol average,
    reshaped to access.premarket()'s digest. prev_close comes from the daily digest (D-1 close)."""
    # today's premarket bars
    today = _read(conn,
                  """SELECT symbol, time_et, high, low, close, volume FROM intraday_bars_5m
                     WHERE date = ? AND substr(time_et,1,5) >= ? AND substr(time_et,1,5) < ?
                     ORDER BY symbol, time_et""",
                  (asof, PM_LO, PM_HI))
    # prior-session premarket volume per (symbol,date) -> own 20-session average
    lo = (datetime.date.fromisoformat(asof) - datetime.timedelta(days=cal_days)).isoformat()
    prior = _read(conn,
                  """SELECT symbol, date, SUM(volume) AS pmvol FROM intraday_bars_5m
                     WHERE date >= ? AND date < ? AND substr(time_et,1,5) >= ? AND substr(time_et,1,5) < ?
                     GROUP BY symbol, date""",
                  (lo, asof, PM_LO, PM_HI))
    avg_pm = {}
    for sym, g in prior.groupby("symbol", sort=False):
        v = g.sort_values("date")["pmvol"].dropna().to_numpy()[-avg_sessions:]
        if v.size:
            avg_pm[sym] = float(v.mean())

    out = {}
    for sym, g in today.groupby("symbol", sort=False):
        pm_vol = float(g["volume"].sum()) if len(g) else 0.0
        pm_hi = float(g["high"].max()) if len(g) else None
        pm_lo = float(g["low"].min()) if len(g) else None
        pm_last = float(g.sort_values("time_et")["close"].iloc[-1]) if len(g) else None
        prev_close = (daily_digests.get(sym) or {}).get("last_close")
        a = avg_pm.get(sym)
        out[sym] = {
            "sym": sym, "date": asof,
            "prev_close": _d(prev_close, 3), "pm_last": _d(pm_last, 3),
            "gap_pct": _d((pm_last / prev_close - 1) * 100, 2) if (pm_last and prev_close) else None,
            "pm_vol": int(pm_vol),
            "pm_vol_vs_avg": _d(pm_vol / a, 2) if (pm_vol and a) else None,
            "pm_range_pct": _d((pm_hi - pm_lo) / prev_close * 100, 2) if (pm_hi and pm_lo and prev_close) else None,
            "pm_high": _d(pm_hi, 3), "pm_low": _d(pm_lo, 3),
            "n_bars": int(len(g)),
            "avg_pm_vol_20d": int(a) if a else None,
        }
    return out


def _latest_per_symbol(df, datecol="date"):
    """Given rows already filtered date<asof, keep the single most-recent row per symbol."""
    if not len(df):
        return {}
    idx = df.groupby("symbol")[datecol].idxmax()
    return {r["symbol"]: r for _, r in df.loc[idx].iterrows()}


# ------------------------------------------------- bulk positioning -> positioning digests
def bulk_positioning(conn, asof, si_days=150, opt_days=45, dsv_days=120):
    """short_interest + options_flow + daily_short_volume (latest<asof each) + major_holders,
    reshaped to access.positioning()'s digest."""
    def win(days):
        return (datetime.date.fromisoformat(asof) - datetime.timedelta(days=days)).isoformat()

    si = _latest_per_symbol(_read(conn,
        """SELECT symbol,date,short_pct_float,short_ratio,short_change_pct,shares_short
           FROM short_interest WHERE date >= ? AND date < ?""", (win(si_days), asof)))
    of = _latest_per_symbol(_read(conn,
        """SELECT symbol,date,put_call_ratio,call_volume,put_volume,unusual_call,unusual_put
           FROM options_flow WHERE date >= ? AND date < ?""", (win(opt_days), asof)))
    dsv = _latest_per_symbol(_read(conn,
        """SELECT symbol,date,short_vol_ratio FROM daily_short_volume
           WHERE date >= ? AND date < ?""", (win(dsv_days), asof)))
    mh = _read(conn, """SELECT symbol,insider_pct,institution_pct,float_institution_pct,institution_count
                        FROM major_holders_summary""")
    mh = {r["symbol"]: r for _, r in mh.iterrows()}

    syms = set(si) | set(of) | set(dsv) | set(mh)
    out = {}
    for sym in syms:
        d = {"sym": sym}
        s = si.get(sym)
        d["short"] = None if s is None else {
            "date": s["date"], "short_pct_float": _d(s["short_pct_float"], 2),
            "short_ratio": _d(s["short_ratio"], 2), "short_change_pct": _d(s["short_change_pct"], 2),
            "shares_short": int(s["shares_short"]) if pd.notna(s["shares_short"]) else None}
        o = of.get(sym)
        d["options"] = None if o is None else {
            "date": o["date"], "put_call_ratio": _d(o["put_call_ratio"], 3),
            "call_volume": int(o["call_volume"]) if pd.notna(o["call_volume"]) else None,
            "put_volume": int(o["put_volume"]) if pd.notna(o["put_volume"]) else None,
            "unusual_call": int(o["unusual_call"]) if pd.notna(o["unusual_call"]) else None,
            "unusual_put": int(o["unusual_put"]) if pd.notna(o["unusual_put"]) else None}
        v = dsv.get(sym)
        d["short_vol"] = None if v is None else {
            "date": v["date"], "short_vol_ratio": _d(v["short_vol_ratio"], 3),
            "stale": v["date"] < access.DSV_STALE_AFTER and asof > access.DSV_STALE_AFTER}
        m = mh.get(sym)
        d["holders"] = None if m is None else {
            "insider_pct": _d(m["insider_pct"], 2), "institution_pct": _d(m["institution_pct"], 2),
            "float_institution_pct": _d(m["float_institution_pct"], 2),
            "institution_count": int(m["institution_count"]) if pd.notna(m["institution_count"]) else None}
        out[sym] = d
    return out


# ------------------------------------------------- bulk fundamentals -> fundamentals digests
def bulk_fundamentals(conn):
    df = _read(conn,
        """SELECT symbol,sector,industry,beta,float_shares,shares_out,market_cap,avg_volume,
                  pe_trailing,pe_forward,updated_at FROM stock_fundamentals""")
    out = {}
    for _, r in df.iterrows():
        flt, shr = r["float_shares"], r["shares_out"]
        out[r["symbol"]] = {
            "sym": r["symbol"], "covered": True, "sector": r["sector"], "industry": r["industry"],
            "beta": _d(r["beta"], 3),
            "float_shares": int(flt) if pd.notna(flt) else None,
            "shares_out": int(shr) if pd.notna(shr) else None,
            "market_cap": int(r["market_cap"]) if pd.notna(r["market_cap"]) else None,
            "avg_volume": int(r["avg_volume"]) if pd.notna(r["avg_volume"]) else None,
            "pe_trailing": _d(r["pe_trailing"], 2), "pe_forward": _d(r["pe_forward"], 2),
            "float_pct_of_shares": _d(flt / shr * 100, 2) if (pd.notna(flt) and pd.notna(shr) and shr) else None,
            "updated_at": r["updated_at"]}
    return out


# ------------------------------------------------------ bulk catalyst -> catalyst digests
def bulk_catalyst(conn, asof, news_lookback_days=3):
    """News (window, matched on symbol col OR symbols_mentioned JSON) + earnings proximity (stale
    table) + analyst actions (7d), reshaped to access.catalyst()'s digest. One pull per feed."""
    lo_dt = (datetime.date.fromisoformat(asof) - datetime.timedelta(days=news_lookback_days))
    news_lo = f"{lo_dt.isoformat()}T00:00:00Z"
    news_cut = f"{asof}T13:30:00Z"          # 09:30 ET
    nrows = _read(conn,
        """SELECT published_at,symbol,symbols_mentioned,sentiment_label,impact_score,headline
           FROM news_events WHERE published_at >= ? AND published_at < ?
           ORDER BY published_at DESC""", (news_lo, news_cut))

    # explode each news row to every mentioned symbol (symbol col + parsed JSON list)
    news_by_sym: dict[str, list] = {}
    for _, r in nrows.iterrows():
        syms = set()
        if pd.notna(r["symbol"]) and r["symbol"]:
            syms.add(r["symbol"])
        sm = r["symbols_mentioned"]
        if isinstance(sm, str) and sm.strip().startswith("["):
            try:
                syms.update(x for x in json.loads(sm) if isinstance(x, str))
            except (ValueError, TypeError):
                pass
        for s in syms:
            news_by_sym.setdefault(s, []).append(r)

    # earnings (one row per symbol; stale table)
    er = _read(conn, "SELECT symbol,next_earnings_date FROM earnings_calendar")
    earn_by_sym = {r["symbol"]: r["next_earnings_date"] for _, r in er.iterrows()}

    # analyst last 7d
    a_lo = (datetime.date.fromisoformat(asof) - datetime.timedelta(days=7)).isoformat()
    arows = _read(conn,
        """SELECT symbol,date,firm,action,to_grade,price_target FROM analyst_ratings
           WHERE date <= ? AND date >= ? ORDER BY date DESC""", (asof, a_lo))
    an_by_sym: dict[str, list] = {}
    for _, r in arows.iterrows():
        an_by_sym.setdefault(r["symbol"], []).append(r)

    syms = set(news_by_sym) | set(earn_by_sym) | set(an_by_sym)
    out = {}
    for sym in syms:
        nl = news_by_sym.get(sym, [])
        impacts = [float(r["impact_score"]) for r in nl if pd.notna(r["impact_score"])]
        news = {
            "n": len(nl),
            "n_pos": sum(1 for r in nl if r["sentiment_label"] == "positive"),
            "n_neg": sum(1 for r in nl if r["sentiment_label"] == "negative"),
            "max_impact": round(max(impacts), 3) if impacts else None,
            "latest": [{"t": r["published_at"], "sentiment": r["sentiment_label"],
                        "headline": (r["headline"] or "")[:90]} for r in nl[:3]]}

        earnings = None
        ed = earn_by_sym.get(sym)
        if ed:
            try:
                dte = (datetime.date.fromisoformat(ed) - datetime.date.fromisoformat(asof)).days
            except (ValueError, TypeError):
                dte = None
            earnings = {"next_date": ed, "days_to": dte, "stale": dte is not None and dte < 0}

        al = an_by_sym.get(sym, [])
        analyst = {
            "n_7d": len(al),
            "n_up": sum(1 for r in al if str(r["action"]).lower() in ("up", "upgrade")),
            "n_down": sum(1 for r in al if str(r["action"]).lower() in ("down", "downgrade")),
            "latest": [{"date": r["date"], "firm": r["firm"], "action": r["action"],
                        "to_grade": r["to_grade"], "price_target": _d(r["price_target"], 2)} for r in al[:3]]}
        out[sym] = {"sym": sym, "date": asof, "news": news, "earnings": earnings, "analyst": analyst}
    return out


# --------------------------------------------------------------------------------- build
def build(asof, write=True, cache_dir=CACHE):
    """Compute coil+prime for the full active universe on `asof`; return (DataFrame, timings)."""
    t0 = time.time()
    conn = _conn()
    timings = {}
    try:
        uni = access.universe()
        syms = uni["syms"]
        sector_map = uni["sector"]
        timings["universe"] = time.time() - t0

        t = time.time(); daily_d = bulk_daily(conn, asof);      timings["daily"] = time.time() - t
        t = time.time(); pm_d = bulk_premarket(conn, asof, daily_d); timings["premarket"] = time.time() - t
        t = time.time(); pos_d = bulk_positioning(conn, asof);  timings["positioning"] = time.time() - t
        t = time.time(); fund_d = bulk_fundamentals(conn);      timings["fundamentals"] = time.time() - t
        t = time.time(); cat_d = bulk_catalyst(conn, asof);     timings["catalyst"] = time.time() - t
    finally:
        conn.close()

    t = time.time()
    rows = []
    for sym in syms:
        dd = daily_d.get(sym)
        if not dd or dd.get("n", 0) == 0:
            continue                                   # no price history -> nothing to coil
        coil = compute_coil(dd)
        prime = compute_prime(pm_d.get(sym), cat_d.get(sym), pos_d.get(sym), fund_d.get(sym))
        uni_sec = sector_map.get(sym)
        sec = prime.get("sector") if (not uni_sec or uni_sec == "Unknown") else uni_sec
        row = {"sym": sym, "asof": asof, "sector": sec or uni_sec}
        row.update({f"coil_{k}": v for k, v in coil.items()})
        row.update({f"prime_{k}": v for k, v in prime.items()})
        rows.append(row)
    df = pd.DataFrame(rows)
    timings["compute"] = time.time() - t
    timings["total"] = time.time() - t0

    if write:
        import os
        os.makedirs(cache_dir, exist_ok=True)
        path = f"{cache_dir}/features_{asof}.parquet"
        try:
            df.to_parquet(path, index=False)
        except Exception:                              # pyarrow missing -> json fallback
            path = f"{cache_dir}/features_{asof}.json"
            df.to_json(path, orient="records")
        timings["_path"] = path
    return df, timings


# ---------------------------------------------------------------------- eyeball composite
_COIL_HI_IS_MORE = {                 # sign to orient each raw feature so higher = "more interesting"
    "coil_atr_pct_pctile": -1,       # tighter = coiled
    "coil_bb_bandwidth_pctile": -1,  # squeeze
    "coil_rvol_ratio": -1,           # contracting
    "coil_range_contraction": -1,    # tightening
    "coil_consol_len": +1,           # longer quiet
    "coil_max_drawdown_pct": -1,     # deeper prior fall (more negative) = more loaded spring
    "prime_gap_abs": +1,
    "prime_pm_vol_vs_avg": +1,       # wake
    "prime_short_pct_float": +1,     # squeeze fuel
    "prime_news_max_impact": +1,
}


def eyeball_composite(df):
    """SANITY EYEBALL ONLY — an equal-weight z-score sum to see if coil+prime separates the field.
    This is NOT the selection: the AI does the real weighting later (README/principle)."""
    z = pd.DataFrame(index=df.index)
    for col, sign in _COIL_HI_IS_MORE.items():
        if col not in df:
            continue
        s = pd.to_numeric(df[col], errors="coerce") * sign
        mu, sd = s.mean(), s.std(ddof=0)
        z[col] = (s - mu) / sd if sd and np.isfinite(sd) else 0.0
    score = z.fillna(0.0).mean(axis=1)          # equal weight over available components
    return score


# ------------------------------------------------------------------------------------- CLI
def _selftest(df, timings):
    pd.set_option("display.width", 200); pd.set_option("display.max_columns", 200)
    print("\n" + "=" * 78)
    print("SELF-TEST — coil+prime raw components (AXTI expect strongly coiled+primed; CAG quiet)")
    print("=" * 78)
    show = ["coil_max_drawdown_pct", "coil_pct_from_252hi", "coil_consol_len", "coil_atr_pct_pctile",
            "coil_bb_bandwidth_pctile", "coil_rvol_ratio", "coil_range_contraction",
            "prime_gap_pct", "prime_pm_vol_vs_avg", "prime_short_pct_float", "prime_short_change_pct",
            "prime_news_present", "prime_news_max_impact", "prime_small_float", "prime_earn_upcoming"]
    show = [c for c in show if c in df.columns]
    for sym in ("AXTI", "CAG"):
        r = df[df["sym"] == sym]
        if not len(r):
            print(f"\n{sym}: (not in universe/build)"); continue
        print(f"\n{sym}  ({r.iloc[0].get('sector')})")
        for c in show:
            print(f"   {c:32s} {r.iloc[0][c]}")

    df = df.copy()
    df["eyeball"] = eyeball_composite(df)
    top = df.sort_values("eyeball", ascending=False).head(15)
    print("\n" + "=" * 78)
    print("TOP-15 by EQUAL-WEIGHT Z-SCORE EYEBALL  (⚠ sanity separation check ONLY — NOT the pick;")
    print("the AI weights the raw components itself downstream)")
    print("=" * 78)
    cols = ["sym", "sector", "eyeball", "coil_max_drawdown_pct", "coil_consol_len",
            "coil_atr_pct_pctile", "prime_gap_pct", "prime_pm_vol_vs_avg", "prime_short_pct_float",
            "prime_news_max_impact"]
    cols = [c for c in cols if c in top.columns]
    with pd.option_context("display.float_format", lambda v: f"{v:.2f}"):
        print(top[cols].to_string(index=False))
    axti_rank = df.sort_values("eyeball", ascending=False).reset_index(drop=True)
    ar = axti_rank.index[axti_rank["sym"] == "AXTI"]
    if len(ar):
        print(f"\nAXTI eyeball rank: #{int(ar[0]) + 1} of {len(df)}")


def main():
    ap = argparse.ArgumentParser(description="build coil+prime feature table for the universe")
    ap.add_argument("asof")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    df, timings = build(a.asof, write=not a.no_write)
    print(f"\nbuilt {len(df)} symbols for {a.asof}")
    print("timings (s): " + "  ".join(f"{k}={v:.2f}" for k, v in timings.items() if not k.startswith("_")))
    if "_path" in timings:
        print("wrote " + timings["_path"])
    if a.selftest:
        _selftest(df, timings)


if __name__ == "__main__":
    main()
