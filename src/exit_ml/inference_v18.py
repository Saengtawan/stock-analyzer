"""Exit ML v18 inference — two-sided stack (SL / prop-trail / model-PL).

Separate module from v17c (inference.py) so v17c stays the instant rollback.
Reuses build_features/tomin/zone_of/sector_of from inference.py for BASE features,
then appends the v18 augmented features computed LIVE the SAME way as the training
dataset builder (/tmp/exit_aug_build.py):
    X += [spy_dd, spy_dd*|stock_dd|, sector_breadth]
where
    spy_dd      = SPY cumulative% minus its running intraday high  (<=0)
    stock_dd    = build_features X[8] (stock close vs its own peak)
    breadth     = count of this sector's ETFs whose cumulative% is >0.3 below
                  their own running intraday high

Stack (per 5-min snap, first hit wins) — backtests/models_exit_v18/spec.json:
    1 SL    : elapsed>=20 & cur<=-2.5
    2 TRAIL : elapsed>=25 & hwm>=1.0 & cur>=0 & (hwm-cur)>=max(1.0,0.4*hwm) & spy_dd<=-0.3
    3 PL    : elapsed>=60 & p>=0.55 & cur>=0.3 & spy_dd<=-0.3
    4 else  : HOLD to EOD
Inherits v17c VIX>=28 safety gate (skip Exit ML -> hold-EOD).
"""
from __future__ import annotations
import json, pickle, sqlite3, datetime as _dt, os as _os
from pathlib import Path
from typing import Optional
import numpy as np

from src.exit_ml.inference import (
    build_features, tomin, zone_of, sector_of, ROOT,
)

SPEC_V18_PATH = ROOT / "backtests/models_exit_v18/spec.json"
MODELS_V18_PATH = ROOT / "backtests/models_exit_v18/sector_specialists.pkl"

with open(SPEC_V18_PATH) as f:
    SPEC18 = json.load(f)
with open(MODELS_V18_PATH, "rb") as f:
    MODELS18 = pickle.load(f)

# stack thresholds (mirror spec.json exit_stack)
_ST = SPEC18["exit_stack"]
SL_HOLD, SL_CUR = _ST["1_SL"]["min_hold_min"], _ST["1_SL"]["cur_pnl_lte"]
TR_HOLD, TR_HWM = _ST["2_trail_prop"]["min_hold_min"], _ST["2_trail_prop"]["hwm_gte"]
TR_SPYDD = _ST["2_trail_prop"]["spy_dd_lte"]
PL_HOLD, PL_P = _ST["3_model_PL"]["min_hold_min"], _ST["3_model_PL"]["p_gte"]
PL_CUR, PL_SPYDD = _ST["3_model_PL"]["cur_gte"], _ST["3_model_PL"]["spy_dd_lte"]
VIX_CUTOFF = 28.0  # inherit v17c safety gate


def _ensemble_p(sector: str, X: np.ndarray) -> np.ndarray:
    ms = MODELS18.get(sector)
    if not ms:
        return np.zeros(len(X))
    return np.mean([m.predict_proba(X)[:, 1] for m in ms], axis=0)


def _running_dd(cum_map: dict, em: int) -> float:
    """value(em) - max(value(k) for k<=em), from a {em: cumulative%} map."""
    ks = [k for k in cum_map if k <= em]
    if not ks:
        return 0.0
    now = cum_map[max(ks)]
    hi = max(cum_map[k] for k in ks)
    return now - hi


def augment(snaps: list, etf_data: dict, sec_etfs: list) -> np.ndarray:
    """Append [spy_dd, spy_dd*|stock_dd|, breadth] to each snap's base X.
    Parity with /tmp/exit_aug_build.py."""
    spy_map = etf_data.get("SPY", {})
    out = []
    for s in snaps:
        em = s["em"]
        X = list(s["X"])
        stock_dd = X[8] if len(X) > 8 else 0.0
        sdd = _running_dd(spy_map, em)
        breadth = sum(
            1 for e in sec_etfs
            if _running_dd(etf_data.get(e, {}), em) < -0.3
        )
        X += [sdd, sdd * abs(stock_dd), breadth]
        out.append(X)
    return np.array(out)


def predict_exit_v18(
    symbol: str, entry_price: float, entry_time_et: str,
    db_path: str, current_em: Optional[int] = None,
    vix_at_entry: Optional[float] = None,
    date: Optional[str] = None,
) -> dict:
    """v18 verdict. Same signature as v17c predict_exit. Returns dict with
    'verdict' in {HOLD, SL_EXIT, TRAIL_EXIT, PL_EXIT, ERROR, VIX_SKIP}."""
    sector = sector_of(symbol, db_path)
    if sector is None:
        return {"verdict": "ERROR", "reason": f"no sector mapping for {symbol}"}
    if sector not in SPEC18.get("_sector_etfs_ref", SPEC18.get("sector_etfs", {})) and \
       sector not in _SEC_ETFS_FALLBACK:
        pass  # handled below by sec_etfs lookup

    entry_em = tomin(entry_time_et)
    fill_em = entry_em + 5
    zone = zone_of(entry_em)

    # VIX safety gate (inherit v17c)
    if vix_at_entry is None:
        vix_at_entry = _get_vix(db_path, date)
    if vix_at_entry is not None and vix_at_entry >= VIX_CUTOFF:
        return {
            "verdict": "VIX_SKIP", "sector": sector, "zone": zone,
            "reason": f"VIX {vix_at_entry:.1f} >= {VIX_CUTOFF} — Exit ML off (hold-EOD)",
            "vix_at_entry": vix_at_entry,
        }

    sec_etfs = _SEC_ETFS[sector]
    sym_bars, etf_data = _fetch_bars(symbol, sec_etfs, db_path, date)
    if len(sym_bars) < 3:
        return {"verdict": "ERROR", "reason": f"too few bars ({len(sym_bars)})"}

    fill_price = entry_price
    if fill_price is None or fill_price <= 0:
        for em, o, *_ in sym_bars:
            if em >= fill_em:
                fill_price = o; break
    if not fill_price or fill_price <= 0:
        return {"verdict": "ERROR", "reason": "no valid fill price"}

    fwd_bars = [b for b in sym_bars if b[0] >= fill_em]
    snaps = build_features(fill_em, fill_price, fwd_bars, etf_data, sec_etfs,
                           e_gain=0.0, e_beta=1.0, sec_name=sector)
    if not snaps:
        return {"verdict": "HOLD", "sector": sector, "zone": zone,
                "reason": "too fresh — no feature snap yet (need >=10 min after fill)"}

    if current_em is not None:
        snaps = [s for s in snaps if s["em"] <= current_em]
    if not snaps:
        return {"verdict": "HOLD", "sector": sector, "zone": zone,
                "reason": "too fresh (no snap up to current_em)"}

    X = augment(snaps, etf_data, sec_etfs)
    p = _ensemble_p(sector, X)

    # walk the v18 stack
    hwm = 0.0
    for i, s in enumerate(snaps):
        cur = s["cur_pnl"]; hwm = max(hwm, cur)
        em = s["em"]; el = em - fill_em
        sdd = X[i][-3]
        tt = f"{em // 60:02d}:{em % 60:02d}"
        if el >= SL_HOLD and cur <= SL_CUR:
            return _verdict("SL_EXIT", cur, tt, sector, zone, p[i], sdd, hwm,
                            f"SL: held {el}m & {cur:+.2f}% <= {SL_CUR}")
        if (el >= TR_HOLD and hwm >= TR_HWM and cur >= 0
                and (hwm - cur) >= max(1.0, 0.4 * hwm) and sdd <= TR_SPYDD):
            return _verdict("TRAIL_EXIT", cur, tt, sector, zone, p[i], sdd, hwm,
                            f"TRAIL: peak {hwm:+.2f}% gave back to {cur:+.2f}% & SPY dd {sdd:+.2f}")
        if (el >= PL_HOLD and p[i] >= PL_P and cur >= PL_CUR and sdd <= PL_SPYDD):
            return _verdict("PL_EXIT", cur, tt, sector, zone, p[i], sdd, hwm,
                            f"PL: p {p[i]:.2f}>={PL_P} & {cur:+.2f}% & SPY dd {sdd:+.2f}")

    last = snaps[-1]
    return {"verdict": "HOLD", "sector": sector, "zone": zone,
            "cur_pnl_pct": last["cur_pnl"], "hwm_pct": hwm,
            "ml_prob": float(p[-1]), "spy_dd": float(X[-1][-3]),
            "reason": f"HOLD — cur {last['cur_pnl']:+.2f}% hwm {hwm:+.2f}%, no exit rule fired"}


def _verdict(v, cur, tt, sector, zone, p, sdd, hwm, reason):
    return {"verdict": v, "exit_time": tt, "cur_pnl_pct": float(cur),
            "hwm_pct": float(hwm), "sector": sector, "zone": zone,
            "ml_prob": float(p), "spy_dd": float(sdd), "reason": reason}


# ---- bar fetch (live Alpaca + DB fallback) — mirrors inference.predict_exit ----
def _fetch_bars(symbol, sec_etfs, db_path, date):
    try:
        from zoneinfo import ZoneInfo as _ZI
        today_et = _dt.datetime.now(_ZI("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        today_et = _dt.date.today().isoformat()
    con = sqlite3.connect(db_path)
    if date is None:
        r = con.execute("SELECT MAX(date) FROM intraday_bars_5m WHERE symbol=?", (symbol,)).fetchone()
        today = r[0] if r and r[0] else today_et
    else:
        today = date
    use_live = (today == today_et)
    sym_bars, etf_data = [], {}

    def _emin(t_iso):
        try:
            from zoneinfo import ZoneInfo as _ZI
            d = _dt.datetime.fromisoformat(t_iso.replace("Z", "+00:00"))
            d = d.astimezone(_ZI("America/New_York"))
            return d.hour * 60 + d.minute
        except Exception:
            return None

    if use_live:
        try:
            env_p = ROOT / ".env"
            if env_p.exists():
                for ln in env_p.read_text().splitlines():
                    ln = ln.strip()
                    if ln and not ln.startswith("#") and "=" in ln:
                        k, v = ln.split("=", 1)
                        _os.environ.setdefault(k.strip(), v.strip().strip('"\''))
            from src.scan.alpaca_bars import fetch_today_bars
            live = fetch_today_bars([symbol] + list(sec_etfs))
            for b in live.get(symbol, []):
                em = _emin(b["t"])
                if em is not None:
                    sym_bars.append((em, b["o"], b["h"], b["l"], b["c"], b["v"]))
            for e in sec_etfs:
                eb = live.get(e, [])
                if not eb:
                    continue
                op = eb[0]["o"]; etf_data[e] = {}
                for b in eb:
                    em = _emin(b["t"])
                    if em is not None:
                        etf_data[e][em] = (b["c"] / op - 1) * 100 if op else 0
        except Exception:
            sym_bars = []
    if not sym_bars:
        bars = con.execute(
            "SELECT time_et,open,high,low,close,volume FROM intraday_bars_5m "
            "WHERE symbol=? AND date=? AND time_et>='09:30' ORDER BY time_et",
            (symbol, today)).fetchall()
        sym_bars = [(tomin(t), o, h, l, c, v) for t, o, h, l, c, v in bars if c]
        for e in sec_etfs:
            rr = con.execute(
                "SELECT time_et,open,close FROM intraday_bars_5m "
                "WHERE symbol=? AND date=? AND time_et>='09:30' ORDER BY time_et",
                (e, today)).fetchall()
            if rr:
                op = rr[0][1]
                etf_data[e] = {tomin(t): (c / op - 1) * 100 if op else 0 for t, _, c in rr}
    con.close()
    return sym_bars, etf_data


def _get_vix(db_path, date):
    con = sqlite3.connect(db_path)
    if date:
        r = con.execute("SELECT vix_close FROM macro_snapshots WHERE date<=? AND vix_close IS NOT NULL ORDER BY date DESC LIMIT 1", (date,)).fetchone()
    else:
        r = con.execute("SELECT vix_close FROM macro_snapshots WHERE vix_close IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone()
    con.close()
    return r[0] if r and r[0] else None


# sector ETF lists — reuse v17c spec (same per-sector lists; v18 trained on these)
from src.exit_ml.inference import SPEC as _SPEC17
_SEC_ETFS = _SPEC17["sector_etfs"]
_SEC_ETFS_FALLBACK = set(_SEC_ETFS.keys())
