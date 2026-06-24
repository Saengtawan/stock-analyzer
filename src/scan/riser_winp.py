"""Riser win_p v2 — LOOKAHEAD-SAFE quality-feature scorer (built 2026-06-24).

Replaces the flat prod win_p (77 OHLCV feats, AUC 0.508 = coin-flip) with an 8-feature
GBM ensemble that learns the REAL levers found this session: regime-gated momentum +
sector rotation + live market state + identity. WF-OOF AUC 0.561 — but the GATE is what
matters (AUC is NOT the deploy metric): trade only if win_p>=0.5 → net +0.89 WR61%
(vs trade-all -0.47), >=0.55 → +1.53, >=0.6 → +2.47 WR76%. All lookahead-safe.

8 features (model in cache/riser_winp_v1.pkl):
  gainXbull, spiXbull, sec_tech, secXbull, mom20_prevday, rel_sec, paXbull, credit_prevday
where bull/mom20/credit are PRIOR-DAY (available at 09:36 scan, no lookahead) and
gain/spi/rel_sec are at-scan (snapshot dailyBar / etf_snaps).

USAGE (shadow first — verify parity vs backtest before gating):
  from src.scan.riser_winp import score_pick
  wp = score_pick(sym, gain, spy_intra, sector, date)   # returns float or None

DEPLOY DISCIPLINE: shadow-log win_p, DON'T gate trades, until live≈backtest parity
confirmed + forward N accumulated. Then gate at win_p>=0.5.
"""
from __future__ import annotations
import os, gzip, json, glob, pickle, sqlite3, statistics as st
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
PKL = ROOT / "cache/riser_winp_v1.pkl"
DB = str(ROOT / "data/trade_history.db")
SNAP_DIR = ROOT / "data/scan_snapshots"

SEC2ETF = {'Technology': 'XLK', 'Consumer Cyclical': 'XLY', 'Healthcare': 'XLV',
           'Financial Services': 'XLF', 'Industrials': 'XLI', 'Energy': 'XLE', 'Basic Materials': 'XLB'}
SECCODE = {'Technology': 0, 'Consumer Cyclical': 1, 'Healthcare': 2, 'Industrials': 3,
           'Financial Services': 4, 'Basic Materials': 5, 'Energy': 6}

_MODEL = None


def _load():
    global _MODEL
    if _MODEL is None:
        with open(PKL, "rb") as f:
            _MODEL = pickle.load(f)
    return _MODEL


def _prior_day_regime(date: str) -> Optional[dict]:
    """bull / mom20 / credit from PRIOR-day macro rows (lookahead-safe at 09:36 scan)."""
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT date,vix_close,spy_close,spy_regime,hyg_close FROM macro_snapshots "
        "WHERE vix_close IS NOT NULL AND spy_close IS NOT NULL AND date < ? ORDER BY date DESC LIMIT 40",
        (date,)).fetchall()
    con.close()
    if len(rows) < 22:
        return None
    rows = rows[::-1]  # ascending; rows[-1] = most recent PRIOR day
    pm = rows[-1]
    spy = [r[2] for r in rows]
    mom20 = (pm[2] / spy[-21] - 1) * 100
    hyg = [r[4] for r in rows if r[4] is not None]
    credit = 1 if (len(hyg) >= 21 and pm[4] and pm[4] > st.mean(hyg[-21:-1])) else 0
    return {'bull': 1 if pm[3] == 'BULL' else 0, 'mom20': mom20, 'credit': credit}


def _sector_etf_intra(sector: str, date: str) -> Optional[float]:
    """Own-sector ETF intraday gain at 09:36 from the latest snapshot (at-scan)."""
    etf = SEC2ETF.get(sector)
    if not etf:
        return None
    snaps = sorted(glob.glob(str(SNAP_DIR / f"{date}_09-3*.json.gz")))
    snaps = [s for s in snaps if 'db_state' not in s]
    if not snaps:
        return None
    try:
        d = json.load(gzip.open(snaps[-1]))
        db = d.get('etf_snaps', {}).get(etf, {}).get('dailyBar', {})
        o, c = db.get('o', 0), db.get('c', 0)
        return (c / o - 1) * 100 if o > 0 else None
    except Exception:
        return None


def _prior_avg(sym: str, date: str) -> float:
    try:
        from src.scan import stock_track_record as STR
        ps = STR.prior_stats(sym, date)
        return (ps[1] or 0) if ps else 0.0
    except Exception:
        return 0.0


def _consistency(sym: str, date: str) -> float:
    """v3: −stdev of the stock's last-20 PRIOR outcomes (stable track record = predictable).
    Lookahead-safe (date < today only). 0 if <5 priors."""
    try:
        from src.scan import stock_track_record as STR
        con = sqlite3.connect(STR.DB)
        rows = con.execute("SELECT eod_ret FROM stock_outcomes WHERE symbol=? AND date<? ORDER BY date DESC LIMIT 20",
                           (sym, date)).fetchall()
        con.close()
        pri = [r[0] for r in rows]
        return -st.pstdev(pri) if len(pri) >= 5 else 0.0
    except Exception:
        return 0.0


def score_pick(sym: str, gain: float, spy_intra: float, sector: str,
               date: str, all_gains: Optional[list] = None) -> Optional[float]:
    """Return win_p in [0,1] for a riser candidate, or None if data unavailable.
    v3 (10 feats). Pass all_gains = list of today's mover gains for the cross-sectional
    rank feature (grank); omit → neutral 0.5. Mirrors training build EXACTLY — verify
    parity vs backtest before gating."""
    rg = _prior_day_regime(date)
    if rg is None:
        return None
    bull = rg['bull']
    seci = _sector_etf_intra(sector, date)
    rel_sec = (gain - seci) if seci is not None else (gain - (spy_intra or 0))
    pa = _prior_avg(sym, date)
    cons = _consistency(sym, date)
    if all_gains:
        srt = sorted(all_gains, reverse=True)
        try:
            rk = srt.index(gain)
        except ValueError:
            rk = min(range(len(srt)), key=lambda i: abs(srt[i] - gain))
        grank = rk / max(1, len(srt) - 1)
    else:
        grank = 0.5
    feats = [gain * bull, (spy_intra or 0) * bull, 1 if sector == 'Technology' else 0,
             SECCODE.get(sector, 7) * bull, rg['mom20'], rel_sec, pa * bull, rg['credit'],
             cons, grank * bull]
    import numpy as np
    X = np.array([feats])
    m = _load()
    return float(np.mean([mdl.predict_proba(X)[:, 1][0] for mdl in m['models']]))


if __name__ == "__main__":
    import sys
    # quick self-test: score a candidate
    sym = sys.argv[1] if len(sys.argv) > 1 else 'NVDA'
    gain = float(sys.argv[2]) if len(sys.argv) > 2 else 2.5
    spi = float(sys.argv[3]) if len(sys.argv) > 3 else 0.1
    sec = sys.argv[4] if len(sys.argv) > 4 else 'Technology'
    date = sys.argv[5] if len(sys.argv) > 5 else '2026-06-23'
    wp = score_pick(sym, gain, spi, sec, date)
    print(f"win_p({sym}, gain={gain}, spi={spi}, {sec}, {date}) = {wp}")
