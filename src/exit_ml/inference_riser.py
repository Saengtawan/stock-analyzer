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

# BELL-GUARD (2026-07-11, user deploy): the 10 market-signal-sensitive bellwethers (corr 0.48-0.73
# w/ riser outcomes). Their MEAN gain-trend 09:36->09:45 predicts the day at the POOL level; used here
# as an early-EXIT guard on the (idiosyncratic) steady pick — bail near entry when the market cohort
# is rolling over, which flags the days the pick would ride to the -4% hard-stop.
# Validated (steady+capture-peak, N=293, wf_1min clean): SAME return/total but WR 78->85, Sharpe
# 0.66->0.80, worst -4.0->-2.3 (tail cut free). IN-SAMPLE -> track forward. Disable: RISER_BELL_GUARD=0.
_BELLWETHERS = ["AAL", "CVNA", "AFRM", "RDDT", "CRWD", "NEM", "TSLA", "ARM", "COHR", "NCLH"]


def _bell_trend(db_path: str, date: Optional[str]) -> Optional[float]:
    """Mean gain-trend of the 10 bellwethers from 09:36 (em 576) to 09:45 (em 585), % of open.
    = mean over bellwethers of (close@585 - close@576)/open. None if <4 have data."""
    diffs = []
    for s in _BELLWETHERS:
        try:
            bars, _ = _fetch_bars(s, [], db_path, date)
        except Exception:
            continue
        o = next((b[1] for b in bars if b[0] >= 570), None)
        le576 = [b[4] for b in bars if 570 <= b[0] <= 576]
        le585 = [b[4] for b in bars if 570 <= b[0] <= 585]
        if o and o > 0 and le576 and le585:
            diffs.append((le585[-1] - le576[-1]) / o * 100)
    return (sum(diffs) / len(diffs)) if len(diffs) >= 4 else None


def _etf_trend(sym: str, db_path: str, date: Optional[str]) -> Optional[float]:
    """Single-ETF gain-trend 09:36->09:45 (% of open). IWM (small-caps) ~= the bellwether cohort
    (corr 0.53) but a single always-available ETF; BELL-or-IWM (either down) beats bell alone
    (steady+capture N=294: WR 85->87, worst -2.3->-1.9, mean +0.94->+0.97). 2026-07-11."""
    try:
        bars, _ = _fetch_bars(sym, [], db_path, date)
    except Exception:
        return None
    o = next((b[1] for b in bars if b[0] >= 570), None)
    le576 = [b[4] for b in bars if 570 <= b[0] <= 576]
    le585 = [b[4] for b in bars if 570 <= b[0] <= 585]
    if o and o > 0 and le576 and le585:
        return (le585[-1] - le576[-1]) / o * 100
    return None


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

    # fetch stock bars (sec_etfs empty — riser exit needs only the stock + VIX). 1Min resolution:
    # capture-peak with a tight give-back (0.5%) only works on 1-min bars — on 5-min bars the coarse
    # close/high can't lock near the peak (validated: 1min+arm0.5/gb0.5 x35 vs 5min x13). Live=Alpaca
    # 1Min; historical DB fallback is intraday_bars_5m (5-min) so backtest-from-DB stays 5-min.
    _tf = os.environ.get("RISER_EXIT_TF", "1Min")
    sym_bars, _ = _fetch_bars(symbol, [], db_path, date, timeframe=_tf)
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

    # build (elapsed, cur=close-pnl, hi=high-pnl) series. hi lets CAPTURE-PEAK trail from the true
    # intraday peak (a peak seen only in the 5-min high still arms the lock).
    series = [(b[0] - fill_em, (b[4] / fill_price - 1) * 100, (b[2] / fill_price - 1) * 100) for b in fwd]
    # own_range over first OWN_WINDOW_MIN (causal — known by el=OWN_WINDOW_MIN)
    early = [c for el, c, hi in series if el <= OWN_WINDOW_MIN]
    own_range = (max(early) - min(early)) if len(early) >= 2 else 0.0

    vix_on = (vix_at_entry is not None and vix_at_entry >= VIX_GATE)
    own_on = own_range >= OWN_RANGE_GATE
    dynamic = os.environ.get("RISER_EXIT_DYNAMIC", "1") != "0"
    gate_on = dynamic and (vix_on or own_on)
    vix_str = f"{vix_at_entry:.1f}" if vix_at_entry is not None else "n/a"
    gate_txt = (f"VIX {vix_str}{'≥' if vix_on else '<'}22"
                f" OR own_range {own_range:.2f}{'≥' if own_on else '<'}3.0")

    # --- REGIME-AWARE EXIT (Phase 2-3, 2026-06-24; at-scan refit same day). Enable: RISER_REGIME_EXIT=1.
    #   Market GREEN at scan -> hold-EOD (sustain). Market RED at scan -> exit ~10:05 (pump-fade:
    #   capture pop before EOD fade). Signal = AT-SCAN SPY intraday (spy_intra<=0), validated to beat
    #   prior-day regime: green-EOD/red-fast vs always-hold = +Δ ALL 5 yrs (red subset hold -1.84 ->
    #   exit@10:05 -0.56). PEAK-FADE is an ACTION (both regimes): stock off peak + SPY rolling over ->
    #   EXIT (market-led fade). Fallback to prior-day BEAR if SPY intra n/a. Disable: RISER_REGIME_EXIT=0.
    gb_thr = float(os.environ.get("RISER_GIVEBACK_THR", "1.5"))
    spy_thr = float(os.environ.get("RISER_SPY_DD_THR", "-0.3"))
    REGIME_EXIT = os.environ.get("RISER_REGIME_EXIT", "0") == "1"
    regime_bull = None
    spy_intra_entry = None
    spy_dd_at = {}
    if REGIME_EXIT:
        try:
            from src.scan.riser_winp import _prior_day_regime
            _rg = _prior_day_regime(date) if date else None
            regime_bull = _rg["bull"] if _rg else None
        except Exception:
            regime_bull = None
        try:  # running SPY intraday drawdown per minute + SPY intraday at entry (at-scan market)
            _sb, _ = _fetch_bars("SPY", [], db_path, date)
            _spk = 0.0; _spy_open = None; _spy_at_entry = None
            for _b in _sb:
                if _spy_open is None and _b[0] >= 570:
                    _spy_open = _b[1]            # SPY 09:30 open (first bar at/after 570)
                if _b[0] <= entry_em:
                    _spy_at_entry = _b[4]        # SPY close at/just before entry (= market at scan)
                _spk = max(_spk, _b[2])
                if _spk > 0:
                    spy_dd_at[_b[0]] = (_b[4] / _spk - 1) * 100
            if _spy_open and _spy_open > 0 and _spy_at_entry is not None:
                spy_intra_entry = (_spy_at_entry / _spy_open - 1) * 100
        except Exception:
            pass

    # FAST-EXIT signal = AT-SCAN market (SPY intraday red this morning), validated 2026-06-24
    # to beat prior-day regime: green-EOD/red-fast vs always-hold = +Δ ALL 5 years (red subset
    # hold-EOD -1.84 -> exit@10:05 -0.56). market red -> capture pop, exit ~10:05 before EOD fade;
    # market green -> hold-EOD (momentum sustains). Falls back to prior-day BEAR if SPY intra n/a.
    # Disable at-scan (use prior-day regime): RISER_SPYINTRA_EXIT=0.
    if os.environ.get("RISER_SPYINTRA_EXIT", "1") != "0" and spy_intra_entry is not None:
        market_red = spy_intra_entry <= 0
        regime_src = f"SPY_intra {spy_intra_entry:+.2f}% at scan"
    else:
        market_red = (regime_bull == 0)
        regime_src = "prior-day BEAR"

    # CAPTURE-PEAK mode (2026-07-08, user deploy LIVE). Objective = RISK-ADJUSTED COMPOUNDING, not
    # arithmetic mean: high-WR + low-DD lets you size up -> compounds MORE. Validated (308 riser
    # picks, wf_1min replay, relative so bar-source bias cancels): sized to same maxDD -20%, hold-EOD
    # x8.6 vs TRAIL-capture+hard-stop x28.7 (3.3x). WR 58->70, maxDD ~halved EVERY year (2024/25 also
    # win raw geo; 2026 raw geo lower but DD still lower = the user's stated objective: win often,
    # don't gamble EOD, compound). Trail from intraday HIGH (arm +1%, lock on 1% give-back) + hard-SL
    # -4% (cuts the 12 disasters <-5% at ~0 mean cost). Replaces peak-fade/fast/gated-trail when on.
    # Rollback: RISER_CAPTURE_PEAK=0 -> old regime-exit. Tunables: RISER_CAP_ARM/CAP_GB/HARD_SL.
    CAPTURE_PEAK = os.environ.get("RISER_CAPTURE_PEAK", "1") == "1"
    CAP_ARM = float(os.environ.get("RISER_CAP_ARM", "1.0"))    # peak must reach +1% to arm the lock
    CAP_GB = float(os.environ.get("RISER_CAP_GB", "1.0"))      # give-back from peak to lock the gain
    HARD_SL = float(os.environ.get("RISER_HARD_SL", "4.0"))    # wide stop cuts disasters (not U-recovery)
    # CONFIRM (2026-07-08): don't lock until the peak is CONFIRMED — no new intraday high for
    # CAP_CONFIRM minutes. Without it, arm0.5 fires on the first small pop-and-dip (WDC 07-08: locked
    # +0.04% @09:56 on a +0.63% wiggle, missing the +1.5% real peak @10:00). With confirm=3, it lets
    # the stock keep making higher highs, then locks ~3 min after the peak holds -> WDC ~+1.0% ($559,
    # the 556-560 the user wanted). Compounding-NEUTRAL (WR unchanged ~70%) but captures peaks higher.
    CAP_CONFIRM = int(os.environ.get("RISER_CAP_CONFIRM", "3"))
    # BELL-GUARD: compute the bellwether trend once (only if enabled + in capture-peak mode + the
    # series reaches 09:45). bell_trend<0 -> early-exit at the first bar >= 09:45 (em 585).
    BELL_GUARD = os.environ.get("RISER_BELL_GUARD", "1") == "1"
    HOLD_ON_UP = os.environ.get("RISER_HOLD_ON_UP", "0") == "1"   # user choice B: hold to EOD on up-days
    bell_trend = None; iwm_trend = None
    if CAPTURE_PEAK and (BELL_GUARD or HOLD_ON_UP) and any((fill_em + el) >= 585 for el, _, _ in series):
        bell_trend = _bell_trend(db_path, date)
        iwm_trend = _etf_trend("IWM", db_path, date)   # small-cap risk proxy — combined w/ bell (either down)
    hwm = 0.0; hwm_hi = 0.0; last_hi_m = fill_em
    for el, cur, hi in series:
        hwm = max(hwm, cur)
        m = (fill_em + el)
        if hi > hwm_hi:
            hwm_hi = hi; last_hi_m = m          # new intraday high -> reset the confirm clock
        tt = f"{m // 60:02d}:{m % 60:02d}"
        if CAPTURE_PEAK:
            _bell_dn = bell_trend is not None and bell_trend < 0
            _iwm_dn = iwm_trend is not None and iwm_trend < 0
            if BELL_GUARD and (_bell_dn or _iwm_dn) and m >= 585:
                _who = "+".join(([f"bell{bell_trend:+.2f}"] if _bell_dn else [])
                                + ([f"IWM{iwm_trend:+.2f}"] if _iwm_dn else []))
                return {"verdict": "TRAIL_EXIT", "exit_time": tt, "cur_pnl_pct": float(cur),
                        "hwm_pct": float(hwm_hi), "sector": sector, "vix_at_entry": vix_at_entry,
                        "own_range": float(own_range), "gate": gate_txt,
                        "bell_trend": (float(bell_trend) if bell_trend is not None else None),
                        "iwm_trend": (float(iwm_trend) if iwm_trend is not None else None),
                        "reason": f"BELL-GUARD @{tt}: market cohort trending down (09:36->09:45: {_who}%) "
                                  f"— bail near entry (cut tail; day flagged weak)"}
            if el >= 15 and cur <= -HARD_SL:
                return {"verdict": "TRAIL_EXIT", "exit_time": tt, "cur_pnl_pct": float(cur),
                        "hwm_pct": float(hwm_hi), "sector": sector, "vix_at_entry": vix_at_entry,
                        "own_range": float(own_range), "gate": gate_txt,
                        "reason": f"HARD-STOP @{tt}: {cur:+.2f}% <= -{HARD_SL:.1f}% (cut disaster, protect compounding)"}
            # HOLD-ON-UP (2026-07-11, user choice B): on an UP day (past 09:45, guard did NOT fire =>
            # bellwether/IWM both trending up = strong/trending market), SKIP the capture-peak lock and
            # HOLD to EOD (hard-stop above still caps disasters). Catches the trending winners the tight
            # capture clips (07-09 NCLH +4.33 EOD vs +1.17 capture). Validated steady N=294: mean +0.97
            # ->+1.15, total +285->+337 (up-days 37%) at the cost of consistency (WR 87->81, Sharpe
            # 0.81->0.51, worst -1.9->-4.0). USER chose upside over consistency. Disable: RISER_HOLD_ON_UP=0.
            if HOLD_ON_UP and m >= 585 and (bell_trend is not None or iwm_trend is not None):
                continue   # up-day -> hold to EOD (no capture lock)
            if el >= 15 and hwm_hi >= CAP_ARM and (hwm_hi - cur) >= CAP_GB and (m - last_hi_m) >= CAP_CONFIRM:
                return {"verdict": "TRAIL_EXIT", "exit_time": tt, "cur_pnl_pct": float(cur),
                        "hwm_pct": float(hwm_hi), "sector": sector, "vix_at_entry": vix_at_entry,
                        "own_range": float(own_range), "gate": gate_txt,
                        "reason": f"CAPTURE-PEAK @{tt}: peak {hwm_hi:+.2f}% -> lock {cur:+.2f}% (give-back {hwm_hi-cur:.1f}%>={CAP_GB:.1f}%, peak confirmed {CAP_CONFIRM}m)"}
            continue   # capture-peak replaces the old regime-exit/gated-trail branches below
        # REGIME-AWARE EXIT actions (only when RISER_REGIME_EXIT=1, after min-hold)
        if REGIME_EXIT and el >= MIN_HOLD:
            _sdd = spy_dd_at.get(m)
            # (a) PEAK-FADE action: stock gave back from peak + SPY rolling over -> EXIT (both regimes)
            if hwm >= 1.0 and (hwm - cur) >= gb_thr and _sdd is not None and _sdd <= spy_thr:
                return {"verdict": "TRAIL_EXIT", "exit_time": tt, "cur_pnl_pct": float(cur),
                        "hwm_pct": float(hwm), "sector": sector, "vix_at_entry": vix_at_entry,
                        "own_range": float(own_range), "gate": gate_txt, "spy_dd": float(_sdd),
                        "reason": f"PEAK-FADE exit @{tt}: peak {hwm:+.2f}%->{cur:+.2f}% + SPY {_sdd:+.2f}% from peak (market-led fade)"}
            # (b) 10:05 fast-exit: market red at scan = pump-fade -> capture pop before EOD fade
            if market_red and m >= 605 and cur < hwm:
                return {"verdict": "TRAIL_EXIT", "exit_time": tt, "cur_pnl_pct": float(cur),
                        "hwm_pct": float(hwm), "sector": sector, "vix_at_entry": vix_at_entry,
                        "own_range": float(own_range), "gate": gate_txt,
                        "reason": f"FAST-EXIT @{tt}: {regime_src} (market red), off peak ({hwm:+.2f}%->{cur:+.2f}%) -> capture pop before EOD fade"}
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
    # --- PEAK-FADE advisory (2026-06-23): stock gives back from its peak + market (SPY) rolling
    # over from ITS intraday peak = "stock หลุด peak" confluence. ADVISORY ONLY — does NOT change
    # the HOLD/TRAIL verdict (backtest: confluence auto-exit ≈ hold / slightly worse, U-recovery
    # clips winners; but it cuts the worst trade and is a useful discretionary signal on clean
    # market-led fades like COIN 2026-06-22). Disable: RISER_PEAK_ALERT=0. Thresholds tunable.
    peak_fade = hwm - last_cur
    spy_dd = None
    if os.environ.get("RISER_PEAK_ALERT", "1") != "0":
        try:
            spy_bars, _ = _fetch_bars("SPY", [], db_path, date)
            spy_cut = [b for b in spy_bars if current_em is None or b[0] <= current_em]
            if spy_cut:
                spk = max(b[2] for b in spy_cut)  # SPY intraday high
                if spk > 0:
                    spy_dd = (spy_cut[-1][4] / spk - 1) * 100  # SPY close vs its peak
        except Exception:
            spy_dd = None
    gb_thr = float(os.environ.get("RISER_GIVEBACK_THR", "1.5"))
    spy_thr = float(os.environ.get("RISER_SPY_DD_THR", "-0.3"))
    peak_alert = bool(hwm >= 1.0 and peak_fade >= gb_thr
                      and spy_dd is not None and spy_dd <= spy_thr)
    advisory = ""
    if spy_dd is not None and peak_alert:
        advisory = (f"  ⚠️ PEAK_FADE: stock {peak_fade:.2f}% from peak + SPY {spy_dd:+.2f}% "
                    f"from peak — CONSIDER EXIT (market-led fade)")
    return {"verdict": "HOLD", "sector": sector, "cur_pnl_pct": float(last_cur),
            "hwm_pct": float(hwm), "vix_at_entry": vix_at_entry, "own_range": float(own_range),
            "gate": gate_txt, "spy_dd": (float(spy_dd) if spy_dd is not None else None),
            "peak_fade": float(peak_fade), "peak_alert": peak_alert,
            "reason": f"HOLD — {mode}, cur {last_cur:+.2f}% (gate {'ON' if gate_on else 'OFF'}: {gate_txt}){advisory}"}
