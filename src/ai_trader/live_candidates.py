"""Live candidate adapter — turns the morning scan dump into Candidate + Context.

Source: data/riser_dumps/<date>/min_0936.jsonl (the real live candidate set that
ml_filter emits each morning — "what's up today", shared infra, not riser logic).
Each dump row: sym, sec, gain, gap, spy_intra, price, range_exp, ...

Liquidity (dollar_vol) isn't in the dump -> computed from daily OHLC, same as backtest.
This keeps the new system's candidate universe identical to what actually traded.
"""
from __future__ import annotations
import json, os, sqlite3
import numpy as np
from .contract import Candidate, Context

DB = "data/trade_history.db"
DUMPS = "data/riser_dumps"


def _dollar_vol(p, sym, date, _cache={}):
    key = (sym, date)
    if key in _cache:
        return _cache[key]
    r = [x for x in p.execute(
        "SELECT close,volume FROM stock_daily_ohlc WHERE symbol=? AND date<? "
        "ORDER BY date DESC LIMIT 20", (sym, date)) if x[0] is not None]
    val = None if len(r) < 10 else r[0][0] * float(np.mean([x[1] or 0 for x in r]))
    _cache[key] = val
    return val


def from_dump(date, scan="0936", dumps=DUMPS, db=DB):
    """Return (candidates, context) for `date` from the 09:36 dump. ([], ctx) if none."""
    path = os.path.join(dumps, date, f"min_{scan}.jsonl")
    if not os.path.exists(path):
        return [], Context(date=date)
    rows = [json.loads(l) for l in open(path) if l.strip()]
    p = sqlite3.connect(db)
    spy_morning = 0.0
    cands = []
    for r in rows:
        spy_morning = r.get("spy_intra", spy_morning)  # same for the day
        dv = _dollar_vol(p, r["sym"], date)
        if dv is None:
            continue
        cands.append(Candidate(
            sym=r["sym"], gain=r.get("gain", 0.0), gap=r.get("gap", 0.0),
            dollar_vol=dv, price=r.get("price", 0.0), sector=r.get("sec", ""),
            extra={"win_p": r.get("win_p"), "range_exp": r.get("range_exp")}))
    # VIX from prior macro snapshot
    m = p.execute("SELECT vix_close FROM macro_snapshots WHERE date<? AND vix_close IS NOT NULL "
                  "ORDER BY date DESC LIMIT 1", (date,)).fetchone()
    ctx = Context(date=date, spy_morning=spy_morning, vix=(m[0] if m else 0.0),
                  n_gainers=len(cands))
    return cands, ctx
