"""resonance / features / prime.py — RELEASE-TRIGGER features (why it might fire TODAY).

MECHANICAL. Zero AI tokens. Pure dict-reshaping over the point-in-time digests handed back by
`data.access`: premarket() (wake/gap), catalyst() (news/earnings/analyst), positioning()
(short/options/holders), fundamentals() (float/mcap). We surface the RAW components the AI will
weight later — and we surface STALE flags rather than hiding them (earnings table is stale;
daily_short_volume lags live). No single "prime score", no direction call baked in.

Coil says a name is *due*; prime says it has a REASON to release now. Both are needed for a
hold-to-close bet: coil = magnitude, catalyst = direction + durability (README bet).

Raw components returned (per symbol):

  premarket wake
    has_premarket                is there any 04:00-09:29 bar today?
    gap_pct                      premkt last vs prior close (pre-open gap indication)
    gap_abs                      |gap_pct| (magnitude, direction-agnostic view of energy)
    pm_vol, pm_vol_vs_avg        premarket volume, and vs this name's own 20d premkt avg (WAKE)
    pm_range_pct                 premkt hi-lo as % of prior close
    pm_n_bars

  news catalyst (point-in-time, cut at 09:30 ET)
    news_n, news_n_pos, news_n_neg
    news_net_sentiment           n_pos - n_neg
    news_max_impact              strongest impact_score in the window (None if unscored)
    news_present                 news_n > 0

  squeeze fuel (short)
    short_pct_float              % of float sold short (higher = more squeeze fuel)
    short_ratio                  days-to-cover
    short_change_pct             change vs prior report (rising short = building fuel)
    short_date                   report date (context; short data is slow-moving)

  options positioning
    put_call_ratio               <1 = call-heavy
    opt_unusual_call, opt_unusual_put
    opt_date

  earnings proximity  (STALE table — trust only forward dates; stale flag surfaced)
    earn_days_to                 days to next_earnings_date (negative = already passed)
    earn_upcoming                0 <= days_to <= 7 (a real near-term catalyst)
    earn_stale                   next_date already in the past (do NOT trust as upcoming)

  analyst actions (last 7d)
    analyst_n_7d, analyst_n_up, analyst_n_down
    analyst_net                  n_up - n_down
    analyst_last_target

  float / size (small float = easier to move)
    float_shares, shares_out, float_pct_of_shares
    market_cap, beta
    small_float                  float_shares < 50M (rough "easy to move" flag)
    sector, fund_covered

  stale flags (surfaced, never hidden)
    short_vol_stale              daily_short_volume feed lags live

Return: dict[str -> number|bool|None].
"""
from __future__ import annotations

_SMALL_FLOAT = 50_000_000     # rough "easy to move" threshold (shares)

# --- gap sanity guard (belt-and-suspenders vs a residual raw-vs-adjusted split mismatch) ----------
# The root fix is consistent split+dividend adjustment across the daily + intraday fetchers, so a
# split can no longer inject a fake gap. But a residual mismatch (a split landing between a re-backfill
# and its use, a stale unadjusted row) must NEVER be able to pool/rank a name on a fabricated spring.
# So: a physically-implausible gap that NOTHING corroborates is treated as untrustworthy — the gap
# AXIS is neutralized for that name (gap_pct/gap_abs -> None so it can't rank on gap), while the raw
# value + the reason are SURFACED (never silently dropped). Other axes (coil, volume, news) are intact.
_GAP_SUSPECT_PCT = 60.0       # |gap| beyond this is implausible for a single overnight move ...
_PM_VOL_CORROB = 3.0          # ... unless corroborated: premarket volume >= 3x this name's own norm


def _gap_corroborated(gap, news_n, pm_vol_vs_avg):
    """Would real-world evidence justify a >60% overnight move? News in the window, or a genuine
    premarket volume surge vs this name's own 20d premarket norm. (A split artifact has neither: it
    is a pure price relabel with no fresh news and no abnormal premarket participation.)"""
    if gap is None or abs(gap) <= _GAP_SUSPECT_PCT:
        return True   # not even suspect -> nothing to corroborate
    if (news_n or 0) > 0:
        return True
    if pm_vol_vs_avg is not None and pm_vol_vs_avg >= _PM_VOL_CORROB:
        return True
    return False


def _num(x):
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def compute_prime(pm=None, cat=None, pos=None, fund=None):
    """pm/cat/pos/fund: the digests from access.premarket / catalyst / positioning / fundamentals
    (any may be None / partial). Returns the raw release-trigger component dict."""
    pm = pm or {}
    cat = cat or {}
    pos = pos or {}
    fund = fund or {}
    out = {}

    # ---- premarket wake -------------------------------------------------------------------
    gap = _num(pm.get("gap_pct"))
    out["has_premarket"] = bool((pm.get("n_bars") or 0) > 0)
    out["gap_pct"] = gap
    out["gap_abs"] = abs(gap) if gap is not None else None
    out["gap_pct_raw"] = gap      # always the un-neutralized gap (guard may null gap_pct below)
    out["pm_vol"] = pm.get("pm_vol")
    out["pm_vol_vs_avg"] = _num(pm.get("pm_vol_vs_avg"))
    out["pm_range_pct"] = _num(pm.get("pm_range_pct"))
    out["pm_n_bars"] = pm.get("n_bars") or 0

    # ---- news catalyst --------------------------------------------------------------------
    news = cat.get("news") or {}
    n_pos, n_neg = (news.get("n_pos") or 0), (news.get("n_neg") or 0)
    out["news_n"] = news.get("n") or 0
    out["news_n_pos"] = n_pos
    out["news_n_neg"] = n_neg
    out["news_net_sentiment"] = n_pos - n_neg
    out["news_max_impact"] = _num(news.get("max_impact"))
    out["news_present"] = bool((news.get("n") or 0) > 0)

    # ---- gap sanity guard (see module top) ------------------------------------------------
    # Surface the raw gap + flag; neutralize the gap AXIS only when the gap is implausibly large
    # AND uncorroborated (the split-artifact signature). Corroborated big gaps (real runners with
    # news / a premarket volume surge) are KEPT — flagged as large but trusted.
    out["gap_suspect"] = bool(gap is not None and abs(gap) > _GAP_SUSPECT_PCT)
    corroborated = _gap_corroborated(gap, out["news_n"], out["pm_vol_vs_avg"])
    out["gap_corroborated"] = corroborated if out["gap_suspect"] else None
    if out["gap_suspect"] and not corroborated:
        out["gap_pct"] = None                 # neutralize the gap axis for pooling/ranking
        out["gap_abs"] = None                 # (gap_pct_raw above preserves the surfaced value)

    # ---- squeeze fuel (short) -------------------------------------------------------------
    short = pos.get("short") or {}
    out["short_pct_float"] = _num(short.get("short_pct_float"))
    out["short_ratio"] = _num(short.get("short_ratio"))
    out["short_change_pct"] = _num(short.get("short_change_pct"))
    out["short_date"] = short.get("date")

    # ---- options positioning --------------------------------------------------------------
    opt = pos.get("options") or {}
    out["put_call_ratio"] = _num(opt.get("put_call_ratio"))
    out["opt_unusual_call"] = opt.get("unusual_call")
    out["opt_unusual_put"] = opt.get("unusual_put")
    out["opt_date"] = opt.get("date")

    # ---- short-volume staleness (surface, don't hide) -------------------------------------
    sv = pos.get("short_vol") or {}
    out["short_vol_stale"] = bool(sv.get("stale")) if sv else None

    # ---- earnings proximity (STALE table) -------------------------------------------------
    earn = cat.get("earnings") or {}
    dte = earn.get("days_to")
    out["earn_days_to"] = dte
    out["earn_stale"] = bool(earn.get("stale")) if earn else None
    out["earn_upcoming"] = bool(dte is not None and 0 <= dte <= 7)

    # ---- analyst actions ------------------------------------------------------------------
    an = cat.get("analyst") or {}
    n_up, n_down = (an.get("n_up") or 0), (an.get("n_down") or 0)
    out["analyst_n_7d"] = an.get("n_7d") or 0
    out["analyst_n_up"] = n_up
    out["analyst_n_down"] = n_down
    out["analyst_net"] = n_up - n_down
    latest = (an.get("latest") or [])
    out["analyst_last_target"] = _num(latest[0].get("price_target")) if latest else None

    # ---- float / size ---------------------------------------------------------------------
    flt = fund.get("float_shares")
    out["float_shares"] = flt
    out["shares_out"] = fund.get("shares_out")
    out["float_pct_of_shares"] = _num(fund.get("float_pct_of_shares"))
    out["market_cap"] = fund.get("market_cap")
    out["beta"] = _num(fund.get("beta"))
    out["small_float"] = bool(flt is not None and flt < _SMALL_FLOAT)
    out["sector"] = fund.get("sector")
    out["fund_covered"] = bool(fund.get("covered"))

    return out


# ------------------------------------------------------------------------------------- CLI
if __name__ == "__main__":
    import argparse
    import json
    from resonance.data import access
    ap = argparse.ArgumentParser(description="prime (release-trigger) features for one symbol")
    ap.add_argument("sym"); ap.add_argument("date")
    a = ap.parse_args()
    pm = access.premarket(a.sym, a.date)
    cat = access.catalyst(a.sym, a.date)
    pos = access.positioning(a.sym, a.date)
    fund = access.fundamentals(a.sym)
    print(json.dumps({"sym": a.sym, "date": a.date, **compute_prime(pm, cat, pos, fund)},
                     indent=2, default=str))
