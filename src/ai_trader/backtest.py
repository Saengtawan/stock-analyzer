"""Deterministic backtest of the RULE layer over history.

Proves the new spine runs end-to-end and reproduces the raw stats we found,
THROUGH the framework (contract -> candidates/context -> plan -> decide -> exit).

Data: cache/wf_1min_bars.db (1-min OHLC, em = minutes-from-midnight; 570=09:30,
576=09:36, 955=15:55) + data/trade_history.db (daily OHLC for prev_close +
liquidity). EOD returns are relative within the same source (OK for expectancy;
absolute wf_1min drifts ~0.27 vs SIP).

Plan modes:
  --plan always   : enable gap_down_reversal every day (no regime gate)
  --plan spy_red  : enable it ONLY on red-tape mornings (the AI's job, mechanised)

Usage:
  python3 -m src.ai_trader.backtest --plan spy_red --cost 0.30
"""
from __future__ import annotations
import argparse, sqlite3
import numpy as np
from .contract import Candidate, Context, Plan
from .scanner import decide
from .classifies.base import PositionState
from .scanner import default_registry
from .premarket_ai import decide_plan

W = "cache/wf_1min_bars.db"
DB = "data/trade_history.db"


def _liq_cache(p):
    cache = {}
    def liq(s, day):
        if (s, day) in cache:
            return cache[(s, day)]
        r = [x for x in p.execute(
            "SELECT close,volume FROM stock_daily_ohlc WHERE symbol=? AND date<? "
            "ORDER BY date DESC LIMIT 20", (s, day)) if x[0] is not None]
        if len(r) < 10:
            cache[(s, day)] = (None, None)
        else:
            c = np.array([x[0] for x in r]); v = np.array([x[1] or 0 for x in r])
            cache[(s, day)] = (c[0] * v.mean(), c[0])
        return cache[(s, day)]
    return liq


def build_day(w, liq, day, dec_em=576):
    """Return (candidates, context) for one day at decision minute dec_em."""
    dd = {}
    for sym, em, o, h, l, c in w.execute(
        "SELECT sym,em,o,h,l,c FROM bars WHERE date=? AND em BETWEEN 570 AND 955", (day,)):
        dd.setdefault(sym, {})[em] = (o, h, l, c)
    spy = dd.get("SPY", {})
    if 570 not in spy or dec_em not in spy or spy[570][0] <= 0:
        return None, None, None
    ctx = Context(date=day,
                  spy_morning=(spy[dec_em][3] / spy[570][0] - 1) * 100)
    cands = []
    for s, d in dd.items():
        if s == "SPY" or 570 not in d or dec_em not in d or d[570][0] <= 0:
            continue
        dolvol, pc = liq(s, day)
        if not dolvol or not pc:
            continue
        o930 = d[570][0]
        gain = (d[dec_em][3] / o930 - 1) * 100
        if gain < 1:
            continue
        peak = max(h for m, (o, h, l, c) in d.items() if 570 <= m <= dec_em)
        cands.append(Candidate(
            sym=s, gain=gain, gap=(o930 / pc - 1) * 100, dollar_vol=dolvol,
            price=d[dec_em][3], peak_gain=(peak / o930 - 1) * 100,
            extra={"day_bars": d}))
    ctx.n_gainers = len(cands)
    return cands, ctx, dd


def run_exit(cand, dec_em, registry_cls):
    """Walk 1-min bars from entry, apply the classify's exit, return realized %."""
    d = cand.extra["day_bars"]
    seq = sorted((m, v) for m, v in d.items() if m >= dec_em)
    e = seq[0][1][3]  # entry = decision-bar close (~09:36 display)
    if e <= 0:
        return None
    peak_pnl = 0.0
    for m, (o, h, l, c) in seq:
        cur = (c / e - 1) * 100
        peak_pnl = max(peak_pnl, (h / e - 1) * 100)
        st = PositionState(minutes_held=m - dec_em, cur_pnl=cur, peak_pnl=peak_pnl)
        if registry_cls.exit(st) == "EXIT":
            return cur
    return (seq[-1][1][3] / e - 1) * 100  # hold to EOD


def make_plan(mode, day):
    """Build the day's plan. 'news' = mechanical sentiment gate. 'llm' = Claude's
    qualitative headline read (plans/llm_verdicts.json). 'always' = enable every day
    (the classify's regime_ok still gates to red tape at open) = no-news-gate baseline."""
    if mode == "news":
        return decide_plan(day, backend="mechanical")
    if mode == "llm":
        return decide_plan(day, backend="llm")
    return Plan(date=day, regime="always",
                enabled_classifies=["gap_down_reversal"], generated_by="test")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="llm", choices=["always", "news", "llm"])
    ap.add_argument("--cost", type=float, default=0.30)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-06-28")
    ap.add_argument("--dec", type=int, default=576)  # decision minute (576=09:36)
    ap.add_argument("--maxpos", type=int, default=1)  # positions/day (>1 = diversify cell)
    a = ap.parse_args()

    w = sqlite3.connect(W); p = sqlite3.connect(DB)
    liq = _liq_cache(p)
    reg = default_registry()
    gdr = reg["gap_down_reversal"]
    dates = [r[0] for r in w.execute(
        "SELECT DISTINCT date FROM bars WHERE date>=? AND date<=? ORDER BY date",
        (a.start, a.end))]

    per_year = {}
    n_trade_days = 0
    for day in dates:
        cands, ctx, dd = build_day(w, liq, day, a.dec)
        if cands is None:
            continue
        plan = make_plan(a.plan, day)
        plan.max_positions = a.maxpos
        picks = decide(cands, plan, ctx, reg)
        if not picks:
            continue
        n_trade_days += 1
        for pk in picks:
            r = run_exit(pk.candidate, a.dec, gdr)
            if r is None:
                continue
            per_year.setdefault(day[:4], []).append(r - a.cost)

    print(f"=== ai_trader backtest | plan={a.plan} cost={a.cost} dec={a.dec} ===")
    print(f"trade-days={n_trade_days}")
    allv = []
    for y in sorted(per_year):
        v = per_year[y]; allv += v
        print(f"  {y}: N={len(v):4}  net{np.mean(v):+.3f}  WR{sum(x>0 for x in v)/len(v)*100:.0f}%  "
              f"worst{min(v):+.1f}  total{sum(v):+.0f}")
    if allv:
        print(f"  ALL: N={len(allv)}  net{np.mean(allv):+.3f}  "
              f"WR{sum(x>0 for x in allv)/len(allv)*100:.0f}%  total{sum(allv):+.0f}")


if __name__ == "__main__":
    main()
