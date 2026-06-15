"""Riser-lane dynamic exit — validated 2026-06-14 (return-per-drawdown optimal).

Risers (Z1 gain-ranked momentum picks) do NOT respond to per-pick fade prediction
(U-shape recovery; see project_riser_momentum_lane memory). The ONLY robust exit is a
regime-conditional trailing stop, gated by an ORTHOGONAL pair of volatility signals:

    gate_on = (VIX_at_entry >= 22)  OR  (own_range[first 20min] >= 3.0%)
      where own_range = max(cur_pnl) - min(cur_pnl) over snaps with elapsed <= 20min
      (market-vol regime  OR  stock's own early choppiness — corr 0.00, complementary)

    if gate_on:  trailing SL 1.0% from peak (arm after peak >= +1%, min-hold 20min)
    else:        hold to EOD

Validated (riser holdout 2025-05+, N=264): hold-EOD ret/DD 0.85 -> gated trail ret/DD 1.97,
total +69 -> +123, 3-way 3/3, remove-top3 +18.8. Lookahead-clean (own_range known by el=20).
Disable: env RISER_EXIT_DYNAMIC=0 -> always hold-EOD.
"""
from __future__ import annotations
import os, sqlite3, datetime as _dt
from typing import Optional
from src.exit_ml.inference import tomin, sector_of, ROOT
from src.exit_ml.inference_v18 import _fetch_bars, _get_vix

VIX_GATE = 22.0
OWN_RANGE_GATE = 3.0      # % (max-min of cur_pnl over first 20 min)
OWN_WINDOW_MIN = 20       # minutes — known by the time trail arms (el>=20)
TRAIL_PCT = 1.0           # giveback from peak to exit
TRAIL_ARM = 1.0           # peak must reach +1% before trail arms
MIN_HOLD = 20             # minutes


def is_riser_pick(symbol: str, date: Optional[str], db_journal: str) -> bool:
    """True if `symbol` was a riser_picks selection on `date` (today if None)."""
    try:
        con = sqlite3.connect(db_journal)
        if date:
            row = con.execute("SELECT 1 FROM riser_picks WHERE symbol=? AND scan_date=? LIMIT 1",
                              (symbol, date)).fetchone()
        else:
            row = con.execute("SELECT 1 FROM riser_picks WHERE symbol=? ORDER BY scan_date DESC LIMIT 1",
                              (symbol,)).fetchone()
        con.close()
        return row is not None
    except sqlite3.OperationalError:
        return False


def predict_exit_riser(
    symbol: str, entry_price: float, entry_time_et: str,
    db_path: str, current_em: Optional[int] = None,
    vix_at_entry: Optional[float] = None, date: Optional[str] = None,
) -> dict:
    """Riser dynamic-trail verdict. Same signature shape as v18.
    Verdicts: HOLD / TRAIL_EXIT / ERROR."""
    sector = sector_of(symbol, db_path) or "?"
    entry_em = tomin(entry_time_et)
    fill_em = entry_em + 5

    if vix_at_entry is None:
        vix_at_entry = _get_vix(db_path, date)

    # fetch stock bars (sec_etfs empty — riser exit needs only the stock + VIX)
    sym_bars, _ = _fetch_bars(symbol, [], db_path, date)
    if len(sym_bars) < 3:
        return {"verdict": "ERROR", "reason": f"too few bars ({len(sym_bars)})", "sector": sector}

    fill_price = entry_price if (entry_price and entry_price > 0) else None
    if fill_price is None:
        for em, o, *_ in sym_bars:
            if em >= fill_em:
                fill_price = o; break
    if not fill_price:
        return {"verdict": "ERROR", "reason": "no valid fill price", "sector": sector}

    fwd = [b for b in sym_bars if b[0] >= fill_em]
    if current_em is not None:
        fwd = [b for b in fwd if b[0] <= current_em]
    if not fwd:
        return {"verdict": "HOLD", "sector": sector, "reason": "too fresh (no bars after fill yet)"}

    # build (elapsed, cur_pnl) series
    series = [(b[0] - fill_em, (b[4] / fill_price - 1) * 100) for b in fwd]  # (el, cur)
    # own_range over first OWN_WINDOW_MIN (causal — known by el=OWN_WINDOW_MIN)
    early = [c for el, c in series if el <= OWN_WINDOW_MIN]
    own_range = (max(early) - min(early)) if len(early) >= 2 else 0.0

    vix_on = (vix_at_entry is not None and vix_at_entry >= VIX_GATE)
    own_on = own_range >= OWN_RANGE_GATE
    dynamic = os.environ.get("RISER_EXIT_DYNAMIC", "1") != "0"
    gate_on = dynamic and (vix_on or own_on)
    gate_txt = (f"VIX {vix_at_entry:.1f}{'≥' if vix_on else '<'}22"
                + (" OR " if True else "")
                + f"own_range {own_range:.2f}{'≥' if own_on else '<'}3.0")

    hwm = 0.0
    for el, cur in series:
        hwm = max(hwm, cur)
        m = (fill_em + el)
        tt = f"{m // 60:02d}:{m % 60:02d}"
        # own_range only usable once its window has closed (el >= OWN_WINDOW_MIN)
        window_ready = el >= OWN_WINDOW_MIN
        gate_now = dynamic and (vix_on or (own_on and window_ready))
        if gate_now and el >= MIN_HOLD and hwm >= TRAIL_ARM and (hwm - cur) >= TRAIL_PCT:
            return {"verdict": "TRAIL_EXIT", "exit_time": tt, "cur_pnl_pct": float(cur),
                    "hwm_pct": float(hwm), "sector": sector, "vix_at_entry": vix_at_entry,
                    "own_range": float(own_range), "gate": gate_txt,
                    "reason": f"riser trail: peak {hwm:+.2f}% gave back to {cur:+.2f}% "
                              f"(gate ON: {gate_txt})"}
    last_cur = series[-1][1]
    mode = "trail-armed (no trigger yet)" if gate_on else "hold-EOD (calm regime)"
    return {"verdict": "HOLD", "sector": sector, "cur_pnl_pct": float(last_cur),
            "hwm_pct": float(hwm), "vix_at_entry": vix_at_entry, "own_range": float(own_range),
            "gate": gate_txt,
            "reason": f"HOLD — {mode}, cur {last_cur:+.2f}% (gate {'ON' if gate_on else 'OFF'}: {gate_txt})"}
