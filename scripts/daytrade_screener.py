#!/usr/bin/env python3
"""
daytrade_screener.py — v7.8
==============================
Progressive day trade screener — runs every 5 min during market hours.
Applies stricter filters as time passes, scores remaining candidates,
and prints top 3 recommendations when confidence is highest.

Gating logic (tightens over time):
  09:00 ET  Gate 1 — Pre-market: gap%, volume, analyst support
  09:35 ET  Gate 2 — ORB formed: entry_vs_orb, orb_direction, vs_spy_rs
  09:45 ET  Gate 3 — Momentum check: still above ORB, volume holding
  10:00 ET  Gate 4 — Confirmed: VWAP holding, sector ETF agrees
  10:30+    Gate 5 — Late entry: only highest-conviction setups

Scoring (0-100):
  market_breadth  20pts  — is today a good day overall?
  premarket       25pts  — gap%, pre-market volume, direction clarity
  orb_quality     25pts  — range tight + break clearly above ORB
  relative_str    15pts  — vs_spy_rs, sector ETF
  fundamentals    15pts  — bull_score, short_pct, analyst upside

Usage (manual):
  python3 scripts/daytrade_screener.py                # current time gate
  python3 scripts/daytrade_screener.py --gate 2       # force gate 2
  python3 scripts/daytrade_screener.py --top 5        # show top 5

Cron (TZ=America/New_York):
  */5 9,10 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/daytrade_screener.py >> logs/daytrade_screener.log 2>&1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import os
import sys
import argparse
from datetime import datetime, time, timedelta

import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')


def get_gate(now_et: datetime) -> int:
    t = now_et.time()
    if t < time(9, 35):   return 1   # pre-market only
    if t < time(9, 45):   return 2   # ORB just formed
    if t < time(10, 0):   return 3   # momentum check
    if t < time(10, 30):  return 4   # confirmed
    if t < time(11, 0):   return 5   # late entry, very strict
    return 6                          # too late for day trade


def get_market_breadth_score(session: object, today: str) -> tuple[float, dict]:
    """Score 0-20 based on today's market conditions."""
    row = session.execute(
        text("SELECT pct_above_20d_ma, ad_ratio, new_52w_highs, new_52w_lows, vix_close "
             "FROM v_market_regime WHERE date = :p0"),
        {"p0": today}
    ).fetchone()

    if not row:
        # Use macro_snapshots as fallback
        ms = session.execute(
            text("SELECT vix_close FROM macro_snapshots WHERE date = :p0"),
            {"p0": today}
        ).fetchone()
        vix = ms['vix_close'] if ms else 20
        score = 10 if vix < 20 else (5 if vix < 24 else 0)
        return score, {'vix': vix, 'note': 'breadth_unavailable'}

    pct20  = row['pct_above_20d_ma'] or 40
    adr    = row['ad_ratio'] or 1.0
    highs  = row['new_52w_highs'] or 0
    lows   = row['new_52w_lows'] or 0
    vix    = row['vix_close'] or 20

    score = 0
    if pct20 >= 55:  score += 8
    elif pct20 >= 45: score += 5
    elif pct20 >= 35: score += 2

    if adr >= 1.5:   score += 6
    elif adr >= 1.0: score += 3
    elif adr >= 0.7: score += 1

    if highs > lows * 2: score += 6
    elif highs > lows:   score += 3

    # VIX penalty
    if vix > 30:  score = max(0, score - 8)
    elif vix > 24: score = max(0, score - 4)

    return min(score, 20), {
        'pct_above_20ma': pct20, 'ad_ratio': round(adr, 2),
        'highs_lows': f"{highs}/{lows}", 'vix': vix
    }


def get_candidates(session: object, today: str) -> list[dict]:
    """Get all candidate symbols from today's screener runs + recent signal_outcomes."""
    syms = set()

    rows = session.execute(
        text("SELECT DISTINCT symbol FROM screener_rejections WHERE scan_date = :p0"),
        {"p0": today}
    ).fetchall()
    syms.update(r[0] for r in rows)

    rows = session.execute(
        text("SELECT DISTINCT symbol FROM signal_outcomes WHERE scan_date = :p0"),
        {"p0": today}
    ).fetchall()
    syms.update(r[0] for r in rows)

    return [{'symbol': s} for s in sorted(syms)]


def fetch_live_prices(symbols: list[str]) -> dict[str, dict]:
    """Fetch latest 1m bars for all candidates + SPY."""
    if not symbols:
        return {}
    syms = list(set(symbols + ['SPY']))
    try:
        df = yf.download(syms, period='1d', interval='1m',
                         auto_adjust=True, progress=False, group_by='ticker')
        if df is None or df.empty:
            return {}
        result = {}
        if len(syms) == 1:
            sym = syms[0]
            if not df.empty:
                last = df.iloc[-1]
                result[sym] = {
                    'price': float(last['Close']),
                    'open':  float(df.iloc[0]['Open']),
                    'high':  float(df['High'].max()),
                    'low':   float(df['Low'].min()),
                }
        else:
            for sym in syms:
                try:
                    sdf = df[sym].dropna(how='all')
                    if sdf.empty: continue
                    result[sym] = {
                        'price': float(sdf.iloc[-1]['Close']),
                        'open':  float(sdf.iloc[0]['Open']),
                        'high':  float(sdf['High'].max()),
                        'low':   float(sdf['Low'].min()),
                    }
                except Exception:
                    pass
        return result
    except Exception:
        return {}


def score_candidate(sym: str, px: dict, spy_px: dict,
                    pm: dict | None, ac: dict | None, mhs: dict | None,
                    si: dict | None, market_score: float, gate: int) -> dict:
    """Score a single candidate. Returns score dict with breakdown."""
    score = market_score   # starts with market context (0-20)
    breakdown = {'market': round(market_score)}

    price = px.get('price', 0)
    open_ = px.get('open', 0)
    spy_price = spy_px.get('price', 0)
    spy_open  = spy_px.get('open', 0)

    if not price or not open_:
        return {'symbol': sym, 'score': 0, 'skip': 'no_price'}

    # -- Premarket score (0-25) --
    pm_score = 0
    gap_pct = 0
    if pm:
        gap_pct = pm.get('premarket_gap_pct') or 0
        f5      = pm.get('first_5min_return') or 0
        vol_r   = pm.get('premarket_vol_ratio') or 0

        if gap_pct >= 5:   pm_score += 10
        elif gap_pct >= 3: pm_score += 6
        elif gap_pct >= 1: pm_score += 3

        if f5 >= 1.0:      pm_score += 8
        elif f5 >= 0.3:    pm_score += 4
        elif f5 < -0.5:    pm_score -= 4   # bad open

        if vol_r >= 3:     pm_score += 7
        elif vol_r >= 1.5: pm_score += 4

    score += max(0, min(pm_score, 25))
    breakdown['premarket'] = max(0, min(pm_score, 25))

    # -- ORB quality score (0-25) — gate 2+ only --
    orb_score = 0
    if gate >= 2:
        stock_pct = (price / open_ - 1) * 100 if open_ > 0 else 0
        spy_pct   = (spy_price / spy_open - 1) * 100 if spy_open > 0 and spy_price > 0 else 0
        vs_spy    = stock_pct - spy_pct   # relative strength

        # Price above open (positive direction)
        if stock_pct >= 1.5:  orb_score += 10
        elif stock_pct >= 0.5: orb_score += 5
        elif stock_pct < 0:   orb_score -= 5

        # Relative strength vs SPY
        if vs_spy >= 2:   orb_score += 10
        elif vs_spy >= 1: orb_score += 6
        elif vs_spy < 0:  orb_score -= 3

        # Clear direction: high away from low
        if price > 0:
            intraday_range = (px['high'] - px['low']) / price * 100
            if intraday_range < 2 and stock_pct > 0:
                orb_score += 5   # tight controlled move upward

    score += max(0, min(orb_score, 25))
    breakdown['orb_rs'] = max(0, min(orb_score, 25))

    # -- Fundamental / analyst score (0-15) --
    fund_score = 0
    if ac:
        bull = ac.get('bull_score') or 0
        upside = ac.get('upside_pct') or 0
        if bull >= 1.5:   fund_score += 5
        elif bull >= 1.0: fund_score += 3
        if upside >= 30:  fund_score += 5
        elif upside >= 15: fund_score += 3

    if mhs:
        inst_pct = mhs.get('institution_pct') or 0
        if inst_pct >= 70:  fund_score += 3
        elif inst_pct >= 50: fund_score += 1

    if si:
        short_pct = si.get('short_pct_float') or 0
        if short_pct >= 15: fund_score += 2   # squeeze potential
        elif short_pct > 20: fund_score -= 2  # high short = dangerous

    score += max(0, min(fund_score, 15))
    breakdown['fundamental'] = max(0, min(fund_score, 15))

    # -- Gate penalty — later gate = must be higher --
    gate_threshold = {1: 30, 2: 40, 3: 50, 4: 55, 5: 65, 6: 999}
    min_score = gate_threshold.get(gate, 999)

    return {
        'symbol':     sym,
        'score':      round(score),
        'min_score':  min_score,
        'passes':     score >= min_score,
        'price':      round(price, 2),
        'gap_pct':    round(gap_pct, 2),
        'breakdown':  breakdown,
    }


def main():
    parser = argparse.ArgumentParser(description='Progressive day trade screener')
    parser.add_argument('--gate', type=int, default=None, help='Force gate (1-6)')
    parser.add_argument('--top', type=int, default=3, help='Show top N (default: 3)')
    parser.add_argument('--all', action='store_true', help='Show all candidates (debug)')
    args = parser.parse_args()

    now_et  = datetime.now(ET)
    today   = now_et.date().strftime('%Y-%m-%d')
    time_et = now_et.strftime('%H:%M')
    gate    = args.gate or get_gate(now_et)

    if gate >= 6 and not args.gate:
        print(f"[{time_et}] Too late for day trade entry (gate={gate}) — exiting")
        sys.exit(0)

    print(f"\n{'='*60}")
    print(f"  DAY TRADE SCREENER  {today}  {time_et} ET  [Gate {gate}]")
    print(f"{'='*60}")

    with get_session() as session:
        # Market breadth context
        market_score, market_ctx = get_market_breadth_score(session, today)
        print(f"  Market: pct_above_20MA={market_ctx.get('pct_above_20ma','?')}% "
              f"A/D={market_ctx.get('ad_ratio','?')} VIX={market_ctx.get('vix','?')} "
              f"-> score={round(market_score)}/20")

        if market_score < 5 and not args.gate:
            print(f"  Market too weak (score={round(market_score)}) — no day trade today")
            return

        # Get candidates
        candidates = get_candidates(session, today)
        if not candidates:
            print(f"  No candidates found for {today}")
            return

        candidate_syms = [c['symbol'] for c in candidates]
        print(f"  {len(candidate_syms)} candidates to screen")

        # Fetch live prices
        prices = fetch_live_prices(candidate_syms[:200])  # limit to top 200
        spy_px = prices.get('SPY', {})

        # Load context data
        def get_pm(sym):
            r = session.execute(
                text("SELECT * FROM premarket_analysis WHERE symbol=:p0 AND date=:p1"),
                {"p0": sym, "p1": today}
            ).fetchone()
            return dict(r._mapping) if r else None

        def get_ac(sym):
            r = session.execute(
                text("SELECT * FROM analyst_consensus WHERE symbol=:p0"),
                {"p0": sym}
            ).fetchone()
            return dict(r._mapping) if r else None

        def get_mhs(sym):
            r = session.execute(
                text("SELECT * FROM major_holders_summary WHERE symbol=:p0"),
                {"p0": sym}
            ).fetchone()
            return dict(r._mapping) if r else None

        def get_si(sym):
            r = session.execute(
                text("SELECT * FROM short_interest WHERE symbol=:p0 ORDER BY date DESC LIMIT 1"),
                {"p0": sym}
            ).fetchone()
            return dict(r._mapping) if r else None

        # Score all candidates
        scored = []
        for sym in candidate_syms[:200]:
            px = prices.get(sym, {})
            if not px:
                continue
            result = score_candidate(
                sym, px, spy_px,
                get_pm(sym), get_ac(sym), get_mhs(sym), get_si(sym),
                market_score, gate
            )
            scored.append(result)

    # Filter and sort
    passing = [s for s in scored if s.get('passes')]
    passing.sort(key=lambda x: x['score'], reverse=True)

    print(f"\n  Passed gate {gate} threshold: {len(passing)}/{len(scored)} candidates")

    if not passing:
        # Show top 3 even if none pass threshold
        all_scored = sorted([s for s in scored if not s.get('skip')],
                            key=lambda x: x['score'], reverse=True)
        print(f"\n  No strong setups at gate {gate}. Best available:")
        passing = all_scored[:3]

    top = passing[:args.top]

    print(f"\n{'-'*60}")
    print(f"  TOP {len(top)} SETUPS:")
    print(f"{'-'*60}")

    for i, c in enumerate(top, 1):
        bd = c.get('breakdown', {})
        flag = '[OK]' if c.get('passes') else '[??]'
        print(f"\n  {i}. {flag} {c['symbol']:6s}  score={c['score']}/100  "
              f"price=${c['price']}  gap={c['gap_pct']:+.1f}%")
        print(f"     breakdown: market={bd.get('market',0)} "
              f"premarket={bd.get('premarket',0)} "
              f"orb/rs={bd.get('orb_rs',0)} "
              f"fundamental={bd.get('fundamental',0)}")

    if top:
        best = top[0]
        print(f"\n  BEST SETUP: {best['symbol']} (score={best['score']}/100)")
        if gate <= 2:
            print(f"     -> Watch for ORB breakout above ${best['price']*1.005:.2f}")
            print(f"     -> Entry confirmation: re-check at Gate {gate+1}")
        elif gate <= 4:
            print(f"     -> Enter near current price ${best['price']}")
            print(f"     -> SL = ${best['price']*0.98:.2f} (-2%)  TP = ${best['price']*1.04:.2f} (+4%)")
        else:
            print(f"     -> Late entry — use tighter SL=1.5%  TP=3.0%")

    print(f"\n{'='*60}\n")


if __name__ == '__main__':
    main()
