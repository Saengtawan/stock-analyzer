"""Exit ML v17c inference — single-symbol verdict from current 5m bars."""
from __future__ import annotations
import json, pickle, sqlite3
from pathlib import Path
from typing import Optional
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "backtests/models_exit_v17c/spec.json"
MODELS_PATH = ROOT / "backtests/models_exit_v17c/sector_specialists.pkl"

with open(SPEC_PATH) as f:
    SPEC = json.load(f)
with open(MODELS_PATH, "rb") as f:
    MODELS = pickle.load(f)


def tomin(t: str) -> int:
    """'09:30' or '2026-06-04 09:30:56' -> minutes-of-day."""
    if " " in t:
        t = t.split(" ")[1]
    return int(t[:2]) * 60 + int(t[3:5])


def zone_of(em: int) -> str:
    mfo = em - 570
    if mfo <= 9: return "Z1"
    if mfo <= 29: return "Z2"
    if mfo <= 44: return "Z3"
    return "Z4"


def sector_of(symbol: str, db_path: str) -> Optional[str]:
    con = sqlite3.connect(db_path)
    row = con.execute(
        "SELECT sector FROM stock_fundamentals WHERE symbol=?", (symbol,)
    ).fetchone()
    con.close()
    if not row or not row[0]: return None
    return SPEC["sector_name_map"].get(row[0])


def threshold_of(sector: str, zone: str) -> float:
    if zone == "Z1": return SPEC["zone_overrides"]["Z1_universal"]
    if zone == "Z4" and sector == "Energy":
        return SPEC["zone_overrides"]["Z4_Energy"]
    return SPEC["thresholds_default"].get(sector, 0.20)


def dd_gate_of(sector: str, zone: str) -> Optional[float]:
    if zone != "Z1": return None
    gates = SPEC["z1_dd_gate_pct"]
    return gates.get(sector, gates["_default"])


def build_features(
    entry_em: int, entry_price: float,
    sym_bars: list, etf_data: dict, sec_etfs: list,
    e_gain: float, e_beta: float, sec_name: str,
) -> list:
    """Build feature snapshots after entry (parity with training build_base).
    sym_bars: [(em, o, h, l, c, v)] from entry_em onwards (entry_em is the post-fill bar)
    etf_data: {etf_sym: {em: cumulative_pct}} for each sec_etf
    Returns [{em, X, c, cur_pnl}]
    """
    if not sym_bars: return []
    distress = SPEC["distress_etfs"][sec_name]
    d1, d2 = distress[0], distress[1]
    peak = entry_price
    peak_em = entry_em
    closes = {entry_em: entry_price}
    hh, ll, ph, pl = 0, 0, entry_price, entry_price
    vxx_entry = etf_data.get("VXX", {}).get(entry_em, 0)
    sec_peaks = {e: {"val": etf_data.get(e, {}).get(entry_em, 0), "em": entry_em} for e in sec_etfs}
    sec_entries = {e: etf_data.get(e, {}).get(entry_em, 0) for e in sec_etfs}
    snaps = []
    for em, o, h, l, c, v in sym_bars:
        if not c or c <= 0: continue
        closes[em] = c
        if h and h > peak: peak, peak_em = h, em
        if h and h > ph: hh += 1
        if l and l < pl: ll += 1
        ph = max(ph, h or 0)
        pl = min(pl, l or float("inf"))
        for e in sec_etfs:
            vnow = etf_data.get(e, {}).get(em, 0)
            if vnow > sec_peaks[e]["val"]:
                sec_peaks[e] = {"val": vnow, "em": em}
        ms = em - entry_em
        if ms < 10: continue
        pnl = (c / entry_price - 1) * 100
        hwm = (peak / entry_price - 1) * 100
        dd = (c / peak - 1) * 100
        bsp = (em - peak_em) // 5
        max_dd = min((closes[k] / peak - 1) * 100 for k in closes)
        c5 = closes.get(em - 5); c15 = closes.get(em - 15); c30 = closes.get(em - 30)
        l5 = (c / c5 - 1) * 100 if c5 else 0
        l15 = (c / c15 - 1) * 100 if c15 else 0
        l30 = (c / c30 - 1) * 100 if c30 else 0
        X = [
            vxx_entry, e_gain, e_beta, (entry_em - 570) / 75,
            ms, 960 - em, pnl, hwm, dd, max_dd, bsp, hh - ll, l5, l15, l30,
            etf_data.get("VXX", {}).get(em, 0) - vxx_entry,
        ]
        for e in sec_etfs:
            vnow = etf_data.get(e, {}).get(em, 0)
            ventry = sec_entries[e]
            vpeak = sec_peaks[e]["val"]
            vpeak_em = sec_peaks[e]["em"]
            X.extend([vnow, vnow - ventry, vnow - vpeak, em - vpeak_em])
        d1_dec = etf_data.get(d1, {}).get(em, 0) - sec_peaks.get(d1, {"val": 0})["val"]
        d2_dec = etf_data.get(d2, {}).get(em, 0) - sec_peaks.get(d2, {"val": 0})["val"]
        distress_v = max(0, -d1_dec) + max(0, -d2_dec)
        X.append(distress_v)
        X.append(distress_v * abs(dd))
        X.extend([
            dd * bsp,
            dd * etf_data.get("VXX", {}).get(em, 0),
            dd * etf_data.get("SPY", {}).get(em, 0),
        ])
        snaps.append({"em": em, "X": X, "c": c, "cur_pnl": pnl})
    return snaps


def predict_exit(
    symbol: str, entry_price: float, entry_time_et: str,
    db_path: str, current_em: Optional[int] = None,
    vix_at_entry: Optional[float] = None,
    date: Optional[str] = None,
) -> dict:
    """Return verdict dict for the symbol at current time.

    entry_time_et: 'HH:MM' or full 'YYYY-MM-DD HH:MM:SS'
    current_em: minutes-of-day for the current 5m bar close (None = use latest available)
    vix_at_entry: VIX at entry (None = pull from macro_snapshots)
    date: 'YYYY-MM-DD' (None = today / max-date for symbol; for replay set explicitly)

    Returns: {'verdict', 'reason', 'ml_prob', 'threshold', 'dd_gate', 'cur_pnl_pct', ...}
    """
    sector = sector_of(symbol, db_path)
    if sector is None:
        return {"verdict": "ERROR", "reason": f"sector unknown for {symbol}"}
    if MODELS.get(sector) is None:
        return {"verdict": "ERROR", "reason": f"no model for sector {sector}"}

    entry_em = tomin(entry_time_et)
    fill_em = entry_em + 5
    zone = zone_of(entry_em)

    # VIX safety gate
    if vix_at_entry is not None and vix_at_entry >= SPEC["vix_safety_gate"]["cutoff"]:
        return {
            "verdict": "CRISIS_HOLD",
            "reason": f"VIX {vix_at_entry:.1f} >= {SPEC['vix_safety_gate']['cutoff']} — Exit ML disabled (hold-EOD)",
            "sector": sector, "zone": zone,
            "vix_at_entry": vix_at_entry,
        }

    # 2026-06-04: Live-mode bar fetching.
    # If date == today_et, try Alpaca live API first (DB has no real-time data
    # during market hours). Fallback to DB for historical replay.
    import datetime as _dt, os as _os
    try:
        from zoneinfo import ZoneInfo as _ZI
        today_et_str = _dt.datetime.now(_ZI("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        today_et_str = _dt.date.today().isoformat()

    con = sqlite3.connect(db_path)
    if date is None:
        today_row = con.execute("SELECT MAX(date) FROM intraday_bars_5m WHERE symbol=?", (symbol,)).fetchone()
        today = today_row[0] if today_row and today_row[0] else today_et_str
    else:
        today = date

    use_live = (today == today_et_str)
    sym_bars = []
    etf_data = {}
    sec_etfs = SPEC["sector_etfs"][sector]

    def _et_min_from_iso(t_iso):
        # bar 't' from Alpaca is UTC ISO; convert to ET minutes-of-day
        try:
            from zoneinfo import ZoneInfo as _ZI
            dt_utc = _dt.datetime.fromisoformat(t_iso.replace("Z", "+00:00"))
            dt_et = dt_utc.astimezone(_ZI("America/New_York"))
            return dt_et.hour * 60 + dt_et.minute
        except Exception:
            return None

    if use_live:
        # Load .env so ALPACA_API_KEY/SECRET are available
        try:
            from pathlib import Path as _P
            env_p = _P(__file__).resolve().parents[2] / ".env"
            if env_p.exists():
                for ln in env_p.read_text().splitlines():
                    ln = ln.strip()
                    if ln and not ln.startswith("#") and "=" in ln:
                        k, v = ln.split("=", 1)
                        _os.environ.setdefault(k.strip(), v.strip().strip('"\''))
            from src.scan.alpaca_bars import fetch_today_bars
            all_syms = [symbol] + list(sec_etfs)
            live_bars = fetch_today_bars(all_syms)
            # Symbol bars
            for b in live_bars.get(symbol, []):
                em = _et_min_from_iso(b["t"])
                if em is None: continue
                sym_bars.append((em, b["o"], b["h"], b["l"], b["c"], b["v"]))
            # ETF bars → cumulative %
            for e in sec_etfs:
                eb = live_bars.get(e, [])
                if not eb: continue
                op = eb[0]["o"]
                etf_data[e] = {}
                for b in eb:
                    em = _et_min_from_iso(b["t"])
                    if em is None: continue
                    etf_data[e][em] = (b["c"] / op - 1) * 100 if op else 0
        except Exception as _e:
            sym_bars = []  # fall through to DB

    # DB fallback (historical replay, or if live fetch failed)
    if not sym_bars:
        bars = con.execute(
            "SELECT time_et, open, high, low, close, volume "
            "FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et>='09:30' "
            "ORDER BY time_et", (symbol, today)
        ).fetchall()
        sym_bars = [(tomin(t), o, h, l, c, v) for t, o, h, l, c, v in bars if c]
        for e in sec_etfs:
            rr = con.execute(
                "SELECT time_et, open, close FROM intraday_bars_5m "
                "WHERE symbol=? AND date=? AND time_et>='09:30' ORDER BY time_et",
                (e, today)
            ).fetchall()
            if not rr: continue
            op = rr[0][1]
            etf_data[e] = {tomin(t): (c / op - 1) * 100 if op else 0 for t, _, c in rr}
    con.close()

    if len(sym_bars) < 3:
        return {"verdict": "ERROR", "reason": f"too few bars ({len(sym_bars)})"}

    # Find fill price (next bar open after entry)
    fill_price = None
    for em, o, _, _, _, _ in sym_bars:
        if em >= fill_em:
            fill_price = o; break
    if fill_price is None:
        return {"verdict": "ERROR", "reason": "no fill bar after entry"}

    # Forward bars from fill onwards
    fwd_bars = [b for b in sym_bars if b[0] >= fill_em]
    snaps = build_features(
        fill_em, fill_price, fwd_bars, etf_data, sec_etfs,
        e_gain=0.0, e_beta=1.0, sec_name=sector,
    )
    if not snaps:
        return {"verdict": "ERROR", "reason": "no feature snaps built"}

    # If current_em given, filter to snaps up to current_em
    if current_em is not None:
        snaps_use = [s for s in snaps if s["em"] <= current_em]
    else:
        snaps_use = snaps
    if not snaps_use:
        return {
            "verdict": "HOLD",
            "reason": f"trade too fresh (< {SPEC['min_hold_minutes']} min)",
            "sector": sector, "zone": zone,
        }

    # Score with ensemble
    X = np.array([s["X"] for s in snaps_use])
    models = MODELS[sector]
    probs = np.mean([m.predict_proba(X)[:, 1] for m in models], axis=0)

    THR = threshold_of(sector, zone)
    gate = dd_gate_of(sector, zone)

    # Scan snaps; find first that triggers exit
    for i, snap in enumerate(snaps_use):
        if snap["em"] - fill_em < SPEC["min_hold_minutes"]: continue
        p = float(probs[i])
        if p < THR: continue
        if gate is not None and snap["cur_pnl"] > gate: continue
        # EXIT
        return {
            "verdict": "EXIT",
            "reason": f"ml_prob={p:.3f} >= thr={THR:.2f} ({sector} {zone}), "
                      f"cur_pnl={snap['cur_pnl']:+.2f}%"
                      + (f" <= gate {gate:+.2f}%" if gate is not None else ""),
            "ml_prob": p, "threshold": THR, "dd_gate": gate,
            "cur_pnl_pct": snap["cur_pnl"], "trigger_em": snap["em"],
            "trigger_price": snap["c"],
            "sector": sector, "zone": zone, "fill_price": fill_price,
            "vix_at_entry": vix_at_entry,
        }

    # No trigger
    latest = snaps_use[-1]
    return {
        "verdict": "HOLD",
        "reason": f"no exit signal (latest p={float(probs[-1]):.3f} thr={THR:.2f}, "
                  f"cur_pnl={latest['cur_pnl']:+.2f}%)",
        "ml_prob": float(probs[-1]), "threshold": THR, "dd_gate": gate,
        "cur_pnl_pct": latest["cur_pnl"], "max_prob_so_far": float(probs.max()),
        "sector": sector, "zone": zone, "fill_price": fill_price,
        "vix_at_entry": vix_at_entry,
    }
