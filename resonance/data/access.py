"""resonance / data / access.py — read-only, token-lean channels over the DB.

The resonance bet is PRE-OPEN: each morning of trading day D (= `asof`/`date` below) we screen the
universe BEFORE 09:30 ET. So every channel here is point-in-time for that moment:

  - Anything CLOSE-STAMPED (daily OHLC, macro, breadth, sector returns, options_flow, short data,
    prior analyst/news of past days) uses ONLY rows with `date < asof` — the most recent completed
    value is D-1's close. Never touch D's own close-stamped row (that is look-ahead).
  - SAME-DAY intraday is limited to the PREMARKET window (04:00-09:29 ET) — knowable before the
    open. No 09:30+ bar is ever read.
  - News is cut at published_at < D 09:30 ET (13:30 UTC).
  - Slowly-varying snapshots (fundamentals, holders, clusters, relationships) are treated as
    current/static; their staleness is noted, not faked into a time series.

Every channel RETURNS A COMPACT DIGEST — a few computed fields per symbol or a small dict — never a
raw dump. `daily()` is the one exception: it hands back the recent daily *series* because the coil
feature legitimately needs it to compute a name's "normal"; it is still bounded by `lookback` and
rounded.

Read-only: connections open with mode=ro; writes are blocked at the DB layer.

Coverage (from STEP 1 inspection, DB snapshot 2026-08-01):
  USABLE   stock_daily_ohlc, intraday_bars_5m, stock_fundamentals, short_interest, options_flow,
           news_events, analyst_ratings, macro_snapshots, market_breadth, sector_etf_daily_returns,
           universe_stocks, institutional_holdings, major_holders_summary, stock_clusters,
           stock_relationships
  STALE    earnings_calendar (fetched 2026-05-01; most next dates already passed — proximity only,
           trust only when next_earnings_date > asof), daily_short_volume (latest 2026-06-15 ~6wk
           behind live), stock_clusters/relationships (fit thru 2026-05-13 / snapshot 2026-05-08)
  EMPTY    cboe_put_call, sector_movers   (channels stubbed, return None)

CLI:
  python -m resonance.data.access daily        SYM ASOF [LOOKBACK]
  python -m resonance.data.access premarket    SYM DATE
  python -m resonance.data.access fundamentals SYM
  python -m resonance.data.access positioning  SYM ASOF
  python -m resonance.data.access catalyst     SYM DATE
  python -m resonance.data.access peers        SYM
  python -m resonance.data.access cluster      SYM ASOF
  python -m resonance.data.access rotation     DATE
  python -m resonance.data.access tape         DATE
  python -m resonance.data.access universe
"""
from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
import zoneinfo

DB = "data/trade_history.db"
ET = zoneinfo.ZoneInfo("America/New_York")

# Freshness bounds observed in STEP 1 — used only to annotate digests, never to hide data.
DSV_STALE_AFTER = "2026-06-15"   # daily_short_volume last date
PM_WINDOW = ("04:00", "09:30")   # premarket [start inclusive, open exclusive)


# ---------------------------------------------------------------------------- db plumbing
def _conn(db=DB):
    """Read-only connection. Writes are blocked at the DB layer."""
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def _rows(sql, params=(), db=DB):
    c = _conn(db)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


def _row(sql, params=(), db=DB):
    r = _rows(sql, params, db)
    return r[0] if r else None


def _d(x, nd=2):
    """Round if numeric-ish, else pass through / None."""
    if x is None:
        return None
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return x


def _prev_trading_date(asof, db=DB):
    """Most recent stock_daily_ohlc date strictly before asof (D-1 completed session)."""
    r = _row("SELECT MAX(date) FROM stock_daily_ohlc WHERE date < ?", (asof,), db)
    return r[0] if r else None


# --------------------------------------------------------------------------------- daily
def daily(sym, asof, lookback=40, db=DB):
    """Recent daily OHLCV for `sym`, bars with date < asof (prior completed sessions only — no
    look-ahead onto D's own close). Returns a compact digest PLUS the bounded series the coil
    feature needs to compute the name's 'normal':

      {sym, asof, prev_date, n, last_close, avg_vol,
       hi_252, lo_252, pct_from_252hi, pct_from_252lo,
       bars: [{d, o, h, l, c, v}, ...]}   (oldest→newest, len<=lookback, rounded)
    """
    rows = _rows(
        """SELECT date, open, high, low, close, volume FROM stock_daily_ohlc
           WHERE symbol=? AND date < ? ORDER BY date DESC LIMIT ?""",
        (sym, asof, int(lookback)), db,
    )
    if not rows:
        return {"sym": sym, "asof": asof, "n": 0, "bars": []}
    rows = rows[::-1]  # oldest→newest
    bars = [{"d": d, "o": _d(o, 3), "h": _d(h, 3), "l": _d(l, 3),
             "c": _d(cl, 3), "v": int(v) if v is not None else None}
            for (d, o, h, l, cl, v) in rows]
    closes = [b["c"] for b in bars if b["c"] is not None]
    vols = [b["v"] for b in bars if b["v"] is not None]
    last_close = closes[-1] if closes else None

    # 52-week context uses a wider window than `lookback` so it stays meaningful.
    w = _row(
        """SELECT MAX(high), MIN(low) FROM stock_daily_ohlc
           WHERE symbol=? AND date < ? AND date >= date(?, '-365 day')""",
        (sym, asof, asof), db,
    )
    hi252, lo252 = (w or (None, None))
    return {
        "sym": sym, "asof": asof, "prev_date": bars[-1]["d"], "n": len(bars),
        "last_close": last_close,
        "avg_vol": int(sum(vols) / len(vols)) if vols else None,
        "hi_252": _d(hi252, 3), "lo_252": _d(lo252, 3),
        "pct_from_252hi": _d((last_close / hi252 - 1) * 100) if (last_close and hi252) else None,
        "pct_from_252lo": _d((last_close / lo252 - 1) * 100) if (last_close and lo252) else None,
        "bars": bars,
    }


# ----------------------------------------------------------------------------- premarket
def premarket(sym, date, db=DB):
    """Premarket (04:00-09:29 ET) wake for `sym` on `date`, vs prior close. Point-in-time pre-open:
    only same-day premarket bars + prior daily close are read; NO 09:30+ bar.

      {sym, date, prev_close, pm_last, gap_pct, pm_vol, pm_vol_vs_avg, pm_range_pct,
       pm_high, pm_low, n_bars, avg_pm_vol_20d}

    gap_pct  = premarket last price vs prior close (the pre-open gap indication — 09:30 open is not
               yet knowable). pm_vol_vs_avg = today's premarket volume / avg premarket volume over
               the prior 20 sessions (how 'awake' the name is before the bell).
    """
    lo, hi = PM_WINDOW
    agg = _row(
        """SELECT SUM(volume), MAX(high), MIN(low), COUNT(*),
                  (SELECT close FROM intraday_bars_5m
                   WHERE symbol=? AND date=? AND substr(time_et,1,5)>=? AND substr(time_et,1,5)<?
                   ORDER BY time_et DESC LIMIT 1)
           FROM intraday_bars_5m
           WHERE symbol=? AND date=? AND substr(time_et,1,5)>=? AND substr(time_et,1,5)<?""",
        (sym, date, lo, hi, sym, date, lo, hi), db,
    )
    pm_vol, pm_hi, pm_lo, n_bars, pm_last = (agg or (None, None, None, 0, None))

    prev_close = None
    pc = _row(
        """SELECT close FROM stock_daily_ohlc WHERE symbol=? AND date < ? ORDER BY date DESC LIMIT 1""",
        (sym, date), db,
    )
    if pc:
        prev_close = pc[0]

    # avg premarket volume over the prior 20 sessions (this symbol's own normal)
    pv = _rows(
        """SELECT date, SUM(volume) FROM intraday_bars_5m
           WHERE symbol=? AND date < ? AND substr(time_et,1,5)>=? AND substr(time_et,1,5)<?
           GROUP BY date ORDER BY date DESC LIMIT 20""",
        (sym, date, lo, hi), db,
    )
    pm_avgs = [v for (_, v) in pv if v]
    avg_pm = (sum(pm_avgs) / len(pm_avgs)) if pm_avgs else None

    return {
        "sym": sym, "date": date,
        "prev_close": _d(prev_close, 3),
        "pm_last": _d(pm_last, 3),
        "gap_pct": _d((pm_last / prev_close - 1) * 100) if (pm_last and prev_close) else None,
        "pm_vol": int(pm_vol) if pm_vol else 0,
        "pm_vol_vs_avg": _d(pm_vol / avg_pm) if (pm_vol and avg_pm) else None,
        "pm_range_pct": _d((pm_hi - pm_lo) / prev_close * 100) if (pm_hi and pm_lo and prev_close) else None,
        "pm_high": _d(pm_hi, 3), "pm_low": _d(pm_lo, 3),
        "n_bars": n_bars or 0,
        "avg_pm_vol_20d": int(avg_pm) if avg_pm else None,
    }


# -------------------------------------------------------------------------- fundamentals
def fundamentals(sym, db=DB):
    """Static 'who/what' snapshot for `sym` (stock_fundamentals is a current snapshot, updated
    ~weekly; treated as slowly-varying — not a time series).

      {sym, sector, industry, beta, float_shares, shares_out, market_cap, avg_volume,
       pe_trailing, pe_forward, float_pct_of_shares, updated_at}  (None if uncovered)
    """
    r = _row(
        """SELECT sector, industry, beta, float_shares, shares_out, market_cap, avg_volume,
                  pe_trailing, pe_forward, updated_at
           FROM stock_fundamentals WHERE symbol=?""",
        (sym,), db,
    )
    if not r:
        return {"sym": sym, "covered": False}
    (sector, industry, beta, flt, shr, mcap, avol, pet, pef, upd) = r
    return {
        "sym": sym, "covered": True,
        "sector": sector, "industry": industry,
        "beta": _d(beta, 3),
        "float_shares": int(flt) if flt else None,
        "shares_out": int(shr) if shr else None,
        "market_cap": int(mcap) if mcap else None,
        "avg_volume": int(avol) if avol else None,
        "pe_trailing": _d(pet), "pe_forward": _d(pef),
        "float_pct_of_shares": _d(flt / shr * 100) if (flt and shr) else None,
        "updated_at": upd,
    }


# --------------------------------------------------------------------------- positioning
def positioning(sym, asof, db=DB):
    """Squeeze-fuel / positioning for `sym`, all point-in-time (date < asof for close-stamped feeds).

      {sym,
       short: {date, short_pct_float, short_ratio, short_change_pct, shares_short},
       short_vol: {date, short_vol_ratio, stale}   (daily_short_volume; stale if latest < live),
       options: {date, put_call_ratio, call_volume, put_volume, unusual_call, unusual_put},
       holders: {insider_pct, institution_pct, float_institution_pct, institution_count}}

    Any sub-block is None when the symbol isn't covered by that feed.
    """
    out = {"sym": sym}

    si = _row(
        """SELECT date, short_pct_float, short_ratio, short_change_pct, shares_short
           FROM short_interest WHERE symbol=? AND date < ? ORDER BY date DESC LIMIT 1""",
        (sym, asof), db,
    )
    out["short"] = None if not si else {
        "date": si[0], "short_pct_float": _d(si[1]), "short_ratio": _d(si[2]),
        "short_change_pct": _d(si[3]), "shares_short": int(si[4]) if si[4] else None,
    }

    dsv = _row(
        """SELECT date, short_vol_ratio FROM daily_short_volume
           WHERE symbol=? AND date < ? ORDER BY date DESC LIMIT 1""",
        (sym, asof), db,
    )
    out["short_vol"] = None if not dsv else {
        "date": dsv[0], "short_vol_ratio": _d(dsv[1], 3),
        "stale": dsv[0] < DSV_STALE_AFTER and asof > DSV_STALE_AFTER,
    }

    of = _row(
        """SELECT date, put_call_ratio, call_volume, put_volume, unusual_call, unusual_put
           FROM options_flow WHERE symbol=? AND date < ? ORDER BY date DESC LIMIT 1""",
        (sym, asof), db,
    )
    out["options"] = None if not of else {
        "date": of[0], "put_call_ratio": _d(of[1], 3),
        "call_volume": int(of[2]) if of[2] else None, "put_volume": int(of[3]) if of[3] else None,
        "unusual_call": int(of[4]) if of[4] is not None else None,
        "unusual_put": int(of[5]) if of[5] is not None else None,
    }

    mh = _row(
        """SELECT insider_pct, institution_pct, float_institution_pct, institution_count
           FROM major_holders_summary WHERE symbol=?""",
        (sym,), db,
    )
    out["holders"] = None if not mh else {
        "insider_pct": _d(mh[0]), "institution_pct": _d(mh[1]),
        "float_institution_pct": _d(mh[2]), "institution_count": int(mh[3]) if mh[3] else None,
    }
    return out


# ------------------------------------------------------------------------------ catalyst
def catalyst(sym, date, news_lookback_days=3, db=DB):
    """Point-in-time catalyst read for `sym` going into `date`'s open.

    News: published_at in [date - news_lookback_days, date 09:30 ET) — matched on `symbol` OR the
    symbols_mentioned JSON. Earnings: point-in-time from earnings_history (fresh: past actuals +
    forward dates) — the most-recent PAST report (release driver: did it just report + beat size)
    and the NEXT UPCOMING report (event risk). Analyst: rating actions with date <= asof, last 7d.

      {sym, date,
       news: {n, n_pos, n_neg, max_impact, latest:[{t, sentiment, headline}...]},
       earnings: {last:{report_date, days_since, eps_estimate, eps_actual, surprise_pct, timing},
                  next:{report_date, days_until, eps_estimate, timing}, stale, source},
       analyst: {n_7d, n_up, n_down, latest:[{date, firm, action, to_grade, price_target}...]}}
    """
    # ---- news, cut at 09:30 ET on `date` (13:30 UTC) ----------------------------------
    lo_dt = (datetime.date.fromisoformat(date) - datetime.timedelta(days=news_lookback_days))
    lo = f"{lo_dt.isoformat()}T00:00:00Z"
    cut = f"{date}T13:30:00Z"
    like = f'%"{sym}"%'
    nrows = _rows(
        """SELECT published_at, sentiment_label, sentiment_score, impact_score, headline
           FROM news_events
           WHERE published_at >= ? AND published_at < ?
             AND (symbol = ? OR symbols_mentioned LIKE ?)
           ORDER BY published_at DESC LIMIT 200""",
        (lo, cut, sym, like), db,
    )
    n_pos = sum(1 for r in nrows if r[1] == "positive")
    n_neg = sum(1 for r in nrows if r[1] == "negative")
    impacts = [float(r[3]) for r in nrows if _numeric(r[3])]
    news = {
        "n": len(nrows), "n_pos": n_pos, "n_neg": n_neg,
        "max_impact": round(max(impacts), 3) if impacts else None,
        "latest": [{"t": r[0], "sentiment": r[1], "headline": (r[4] or "")[:90]} for r in nrows[:3]],
    }

    # ---- earnings, point-in-time from earnings_history (fresh: past actuals + fwd dates) --
    # Look-ahead guards: (1) "past" = report_date STRICTLY < date, so a same-day report (BMO/AMC)
    # that hasn't cleared pre-open is never treated as reported; (2) "next" (report_date >= date)
    # never returns eps_actual/surprise_pct — some forward rows in the table already carry backfilled
    # actuals, and surfacing them would leak the result of an event that hasn't happened yet.
    asof_d = datetime.date.fromisoformat(date)
    lr = _row(
        """SELECT report_date, eps_estimate, eps_actual, surprise_pct, timing
           FROM earnings_history WHERE symbol=? AND report_date < ?
           ORDER BY report_date DESC LIMIT 1""",
        (sym, date), db,
    )
    nr = _row(
        """SELECT report_date, eps_estimate, timing
           FROM earnings_history WHERE symbol=? AND report_date >= ?
           ORDER BY report_date ASC LIMIT 1""",
        (sym, date), db,
    )
    last = next_ = None
    if lr:
        try:
            days_since = (asof_d - datetime.date.fromisoformat(lr[0])).days
        except ValueError:
            days_since = None
        last = {"report_date": lr[0], "days_since": days_since,
                "eps_estimate": _d(lr[1], 3), "eps_actual": _d(lr[2], 3),
                "surprise_pct": _d(lr[3], 2), "timing": lr[4]}
    if nr:
        try:
            days_until = (datetime.date.fromisoformat(nr[0]) - asof_d).days
        except ValueError:
            days_until = None
        next_ = {"report_date": nr[0], "days_until": days_until,
                 "eps_estimate": _d(nr[1], 3), "timing": nr[2]}
    earnings = None if (last is None and next_ is None) else {
        "last": last, "next": next_, "stale": False, "source": "earnings_history",
    }

    # ---- analyst actions, date <= asof, last 7 days -----------------------------------
    a_lo = (datetime.date.fromisoformat(date) - datetime.timedelta(days=7)).isoformat()
    arows = _rows(
        """SELECT date, firm, action, to_grade, from_grade, price_target, prior_target
           FROM analyst_ratings WHERE symbol=? AND date <= ? AND date >= ?
           ORDER BY date DESC LIMIT 20""",
        (sym, date, a_lo), db,
    )
    n_up = sum(1 for r in arows if (r[2] or "").lower() in ("up", "upgrade"))
    n_down = sum(1 for r in arows if (r[2] or "").lower() in ("down", "downgrade"))
    analyst = {
        "n_7d": len(arows), "n_up": n_up, "n_down": n_down,
        "latest": [{"date": r[0], "firm": r[1], "action": r[2], "to_grade": r[3],
                    "price_target": _d(r[5])} for r in arows[:3]],
        "note": "date-only feed (no intraday ts); same-day rows assumed pre-market",
    }
    return {"sym": sym, "date": date, "news": news, "earnings": earnings, "analyst": analyst}


def _numeric(x):
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------- peers / clusters
def peers(sym, db=DB):
    """Static relationship graph for `sym` (stock_relationships — single snapshot 2026-05-08).
    Returns compact edges both directions: [{other, type, strength, tier, dir}]."""
    rows = _rows(
        """SELECT symbol_to, relationship_type, strength, tier, 'out' FROM stock_relationships WHERE symbol_from=?
           UNION ALL
           SELECT symbol_from, relationship_type, strength, tier, 'in' FROM stock_relationships WHERE symbol_to=?""",
        (sym, sym), db,
    )
    return {"sym": sym, "n": len(rows),
            "edges": [{"other": r[0], "type": r[1], "strength": _d(r[2], 2),
                       "tier": r[3], "dir": r[4]} for r in rows[:25]]}


def cluster(sym, asof, db=DB):
    """Correlation cluster membership for `sym` as of the latest fit_date <= asof (stock_clusters;
    fit thru 2026-05-13). Returns the cluster + its members (compact)."""
    r = _row(
        """SELECT cluster_id, cluster_name, corr_to_centroid, n_members, fit_date
           FROM stock_clusters WHERE symbol=? AND fit_date <= ? ORDER BY fit_date DESC LIMIT 1""",
        (sym, asof), db,
    )
    if not r:
        return {"sym": sym, "covered": False}
    cid, cname, corr, nmem, fit = r
    members = [x[0] for x in _rows(
        "SELECT symbol FROM stock_clusters WHERE cluster_id=? AND fit_date=? LIMIT 30",
        (cid, fit), db)]
    return {"sym": sym, "covered": True, "cluster_id": cid, "cluster_name": cname,
            "corr_to_centroid": _d(corr, 3), "n_members": nmem, "fit_date": fit,
            "members": members}


# ------------------------------------------------------------------------------ rotation
def rotation(date, db=DB):
    """Sector-rotation tape as of prior close (sector_etf_daily_returns, latest date < asof).
    Leaderboard of the 11 sector ETFs (+ index/macro proxies present) by yesterday's pct_change.

      {asof_close_date, leaders: [{etf, sector, pct_change, vs_spy}...]}  sorted desc.
    """
    d = _row("SELECT MAX(date) FROM sector_etf_daily_returns WHERE date < ?", (date,), db)
    if not d or not d[0]:
        return {"asof_close_date": None, "leaders": []}
    d = d[0]
    rows = _rows(
        """SELECT etf, sector, pct_change, vs_spy FROM sector_etf_daily_returns
           WHERE date=? ORDER BY pct_change DESC""",
        (d,), db,
    )
    return {"asof_close_date": d,
            "leaders": [{"etf": r[0], "sector": r[1], "pct_change": _d(r[2], 3),
                         "vs_spy": _d(r[3], 3)} for r in rows]}


# ---------------------------------------------------------------------------------- tape
def tape(date, db=DB):
    """Macro regime + breadth as of prior close (point-in-time: date < asof). Combines
    macro_snapshots + market_breadth into one compact regime digest.

      {asof_close_date,
       macro: {vix, vix3m, vix_term_spread, skew, vvix, yield_10y, yield_spread, dxy, btc,
               gold, crude, hyg, regime_label},
       breadth: {date, pct_above_20d, pct_above_50d, ad_ratio, new_52w_highs, new_52w_lows}}
    """
    m = _row(
        """SELECT date, vix_close, vix3m_close, skew_close, vvix_close, yield_10y, yield_spread,
                  dxy_close, btc_close, gold_close, crude_close, hyg_close, regime_label
           FROM macro_snapshots WHERE date < ? ORDER BY date DESC LIMIT 1""",
        (date,), db,
    )
    macro = None
    if m:
        vix, vix3m = m[1], m[2]
        macro = {
            "vix": _d(vix), "vix3m": _d(vix3m),
            "vix_term_spread": _d((vix3m - vix)) if (vix is not None and vix3m is not None) else None,
            "skew": _d(m[3]), "vvix": _d(m[4]), "yield_10y": _d(m[5], 3),
            "yield_spread": _d(m[6], 3), "dxy": _d(m[7]), "btc": _d(m[8]),
            "gold": _d(m[9]), "crude": _d(m[10]), "hyg": _d(m[11]), "regime_label": m[12],
        }

    b = _row(
        """SELECT date, pct_above_20d_ma, pct_above_50d_ma, ad_ratio, new_52w_highs, new_52w_lows
           FROM market_breadth WHERE date < ? ORDER BY date DESC LIMIT 1""",
        (date,), db,
    )
    breadth = None if not b else {
        "date": b[0], "pct_above_20d": _d(b[1]), "pct_above_50d": _d(b[2]),
        "ad_ratio": _d(b[3], 3), "new_52w_highs": b[4], "new_52w_lows": b[5],
    }
    return {"asof_close_date": (m[0] if m else None), "macro": macro, "breadth": breadth}


# ------------------------------------------------------------------------------ universe
def universe(db=DB, min_dollar_vol=0.0):
    """Active liquid symbol list = UNION of the live core (`universe_stocks`, what auto_trading
    reads) and the DECOUPLED resonance spring pool (`resonance_universe`, built by
    resonance.universe.build_universe — extra liquid small/mid-caps auto_trading never sees).

    Each symbol carries a `source` tag: 'core' (universe_stocks) or 'resonance' (extras only).
    Core wins on de-dup. `resonance_universe` is optional — if the table is absent the result is
    exactly the old core-only list, so this is backward-compatible.

      {n, n_core, n_resonance, updated_at,
       syms:   [...],                 core first (by $-vol), then resonance extras (by $-vol),
       sector: {sym: sector},         core sectors only (extras have no sector yet -> absent),
       source: {sym: 'core'|'resonance'}}

    `min_dollar_vol` filters the core rows on `dollar_vol` (as before). The resonance pool is
    already liquidity-screened at build time; its `avg_dollar_vol` is used for the same floor.
    """
    # ETFs (sector='ETF' in universe_stocks: GLD/TLT/BND/IBIT/IGV...) have no earnings/catalyst and
    # cannot be a spring — they leak into the pool via the structural-low-vol path (bond/gold ETFs
    # are perpetually quiet). Exclude at the source so they never reach features/pool/AI.
    core = _rows(
        """SELECT symbol, sector, dollar_vol FROM universe_stocks
           WHERE status='active' AND COALESCE(dollar_vol,0) >= ?
             AND COALESCE(sector,'') != 'ETF' ORDER BY dollar_vol DESC""",
        (min_dollar_vol,), db,
    )
    core_syms = [r[0] for r in core]
    seen = set(core_syms)

    # resonance extras — optional table; de-duped against core, never overriding it.
    extras = []
    try:
        extras = _rows(
            """SELECT symbol, avg_dollar_vol FROM resonance_universe
               WHERE status='active' AND COALESCE(avg_dollar_vol,0) >= ?
               ORDER BY avg_dollar_vol DESC""",
            (min_dollar_vol,), db,
        )
    except sqlite3.OperationalError:
        extras = []   # table not built yet -> core-only (backward compatible)
    extra_syms = [r[0] for r in extras if r[0] not in seen]

    upd = _row("SELECT MAX(updated_at) FROM universe_stocks", (), db)
    source = {s: "core" for s in core_syms}
    source.update({s: "resonance" for s in extra_syms})
    return {"n": len(core_syms) + len(extra_syms),
            "n_core": len(core_syms), "n_resonance": len(extra_syms),
            "updated_at": (upd[0] if upd else None),
            "syms": core_syms + extra_syms,
            "sector": {r[0]: r[1] for r in core},
            "source": source}


# ----------------------------------------------------------- empty-table stubs (noted)
def put_call(date, db=DB):
    """STUB — cboe_put_call is EMPTY in this DB. Returns None so callers can no-op cleanly."""
    return None


def sector_movers(date, db=DB):
    """STUB — sector_movers table is EMPTY. Use rotation() (sector_etf_daily_returns) instead."""
    return None


# ----------------------------------------------------------------------------------- CLI
def _pp(obj):
    print(json.dumps(obj, indent=2, default=str))


def main():
    ap = argparse.ArgumentParser(description="resonance read-only data channels")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("daily"); d.add_argument("sym"); d.add_argument("asof"); d.add_argument("lookback", nargs="?", default="40")
    p = sub.add_parser("premarket"); p.add_argument("sym"); p.add_argument("date")
    f = sub.add_parser("fundamentals"); f.add_argument("sym")
    po = sub.add_parser("positioning"); po.add_argument("sym"); po.add_argument("asof")
    ca = sub.add_parser("catalyst"); ca.add_argument("sym"); ca.add_argument("date")
    pe = sub.add_parser("peers"); pe.add_argument("sym")
    cl = sub.add_parser("cluster"); cl.add_argument("sym"); cl.add_argument("asof")
    ro = sub.add_parser("rotation"); ro.add_argument("date")
    ta = sub.add_parser("tape"); ta.add_argument("date")
    sub.add_parser("universe")

    a = ap.parse_args()
    if a.cmd == "daily":
        r = daily(a.sym, a.asof, int(a.lookback))
        # keep CLI output compact: show digest + head/tail of series
        head = r.get("bars", [])
        r2 = {k: v for k, v in r.items() if k != "bars"}
        r2["bars_head"] = head[:2]; r2["bars_tail"] = head[-2:]
        _pp(r2)
    elif a.cmd == "premarket":
        _pp(premarket(a.sym, a.date))
    elif a.cmd == "fundamentals":
        _pp(fundamentals(a.sym))
    elif a.cmd == "positioning":
        _pp(positioning(a.sym, a.asof))
    elif a.cmd == "catalyst":
        _pp(catalyst(a.sym, a.date))
    elif a.cmd == "peers":
        _pp(peers(a.sym))
    elif a.cmd == "cluster":
        _pp(cluster(a.sym, a.asof))
    elif a.cmd == "rotation":
        _pp(rotation(a.date))
    elif a.cmd == "tape":
        _pp(tape(a.date))
    elif a.cmd == "universe":
        u = universe()
        _pp({"n": u["n"], "n_core": u["n_core"], "n_resonance": u["n_resonance"],
             "updated_at": u["updated_at"],
             "core_head": u["syms"][:10],
             "resonance_head": [s for s in u["syms"] if u["source"].get(s) == "resonance"][:10]})


if __name__ == "__main__":
    main()
