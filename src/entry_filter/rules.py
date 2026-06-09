"""Entry filter rules — pure-function evaluator, no IO.

Supports two specs (env-toggleable):
  - v1 (default): Original 14-rule entry filter (deployed 2026-06-04)
  - v2-h12a: Minimal 1-rule (Z1 gain≤4.5 only) — set ENTRY_FILTER_SPEC=v2-h12a
"""
from __future__ import annotations
import os
from typing import Tuple

# Zone mfo ranges (mins_from_open)
def zone_of_mfo(mfo: int) -> str:
    if mfo <= 9: return "Z1"
    if mfo <= 29: return "Z2"
    if mfo <= 44: return "Z3"
    return "Z4"


def _is_missing(x) -> bool:
    """Treat None/NaN as missing (graceful PASS)."""
    if x is None: return True
    try:
        return x != x  # NaN check
    except Exception:
        return False


def _evaluate_h12a(
    zone: str,
    gain_from_open: float | None = None,
) -> Tuple[bool, str]:
    """H12-A spec: keep only Z1 gain≤4.5 (DD-control with explicit evidence).

    All other 13 rules dropped per H12-A research (each cost 0-36pp on 3yr
    without DD evidence). See backtests/entry_filter_v1/spec.h12a.json.
    """
    if zone == "Z1":
        # 2026-06-09: gain cap now env-controllable. Set H12A_Z1_GAIN_CAP=off to
        # disable (WF showed it blocks only ~2 picks/2yr on H12-A's gated stream —
        # near no-op since win_p 0.75 already filters extended names). Default 4.5
        # preserved for safety if env unset. Reversible: remove .env line → 4.5.
        cap_env = os.environ.get("H12A_Z1_GAIN_CAP", "4.5").strip().lower()
        if cap_env in ("off", "none", ""):
            return (True, "Z1 PASS (gain cap OFF)")
        cap = float(cap_env)
        if _is_missing(gain_from_open):
            return (True, "Z1 PASS (gain missing — graceful)")
        if gain_from_open > cap:
            return (False, f"Z1 SKIP: gain={gain_from_open:.1f}>{cap} (DD-control)")
        return (True, "Z1 PASS (H12-A)")
    # Z2/Z3/Z4: no entry filter rules in H12-A
    return (True, f"{zone} PASS (H12-A — no EF rules for this zone)")


def evaluate(
    zone: str,
    beta: float | None = None,
    sector: str | None = None,
    vix: float | None = None,
    dow: int | None = None,
    gain_from_open: float | None = None,
    spy_intra: float | None = None,
    mom20d: float | None = None,
) -> Tuple[bool, str]:
    """Return (passes, reason_string).

    Routes to spec based on env ENTRY_FILTER_SPEC:
      - default (v1): conjunctive 14-rule filter
      - v2-h12a: 1-rule minimal (Z1 gain≤4.5 only)

    PASS rules are conjunctive (all must hold). If a feature is missing,
    that specific check is skipped (graceful fallback — do not drop pick).
    """
    if os.environ.get("ENTRY_FILTER_SPEC", "v1") == "v2-h12a":
        return _evaluate_h12a(zone, gain_from_open=gain_from_open)

    fails = []
    skipped = []

    if zone == "Z1":
        # Triple gate: β≥1.2 + sector≠Industrials + gain≤4.5
        # gain≤4.5 added 2026-06-04 (DD-control): 1-month live evidence FSLR+4.6
        # DD -4.58%, AXTI+5.99 DD -2.79% (intraday pain). Recent 1mo: blocks
        # AXTI+FSLR+ANET, keeps F/HPE/FICO/AVGO winners. avgDD -1.10→-0.60,
        # p10DD -1.93→-0.99, bad%(DD<-2) 10→0. 3yr cost: sum -8% (-19% rel).
        if _is_missing(beta): skipped.append("β?")
        elif beta < 1.2: fails.append(f"β={beta:.2f}<1.2")
        if _is_missing(sector): skipped.append("sec?")
        elif sector == "Industrials": fails.append("sec=Industrial")
        if _is_missing(gain_from_open): skipped.append("gain?")
        elif gain_from_open > 4.5: fails.append(f"gain={gain_from_open:.1f}>4.5 (Z1 DD-control)")

    elif zone == "Z2":
        # DOW≠Mon + gain≤3 + SPY≥-0.3 + sector∉{Utilities,Real Estate} + β≤1.5
        # (β≤1.5 added 2026-06-04: research 555 picks/3yr — Z2 high-β (β≥1.5)
        #  = 40% WR / -2.0% avg, β≤1.5 = 75% WR / +1.50% avg. RCL β=1.78
        #  in May 2026 confirmed pattern. +5.8pp WR research, ~+0.5pp/pick.)
        if _is_missing(dow): skipped.append("dow?")
        elif dow == 0: fails.append("DOW=Mon")
        if _is_missing(gain_from_open): skipped.append("gain?")
        elif gain_from_open > 3: fails.append(f"gain={gain_from_open:.1f}>3")
        if _is_missing(spy_intra): skipped.append("spy?")
        elif spy_intra < -0.3: fails.append(f"spy={spy_intra:.2f}<-0.3")
        if _is_missing(sector): skipped.append("sec?")
        elif sector in ("Utilities", "Real Estate"): fails.append(f"sec={sector}")
        if _is_missing(beta): skipped.append("β?")
        elif beta > 1.5: fails.append(f"β={beta:.2f}>1.5 (Z2 prefers low-β)")

    elif zone == "Z3":
        if _is_missing(mom20d): skipped.append("mom20d?")
        elif mom20d < 0: fails.append(f"mom20d={mom20d:.1f}<0")
        elif mom20d > 25: fails.append(f"mom20d={mom20d:.1f}>25 (over-extended)")  # Gap 1
        if _is_missing(spy_intra): skipped.append("spy?")
        elif spy_intra < -0.3: fails.append(f"spy={spy_intra:.2f}<-0.3")
        if _is_missing(gain_from_open): skipped.append("gain?")
        elif gain_from_open > 3: fails.append(f"gain={gain_from_open:.1f}>3")

    elif zone == "Z4":
        if _is_missing(mom20d): skipped.append("mom20d?")
        elif mom20d < 0: fails.append(f"mom20d={mom20d:.1f}<0")
        elif mom20d > 25: fails.append(f"mom20d={mom20d:.1f}>25 (over-extended)")  # Gap 1

    else:
        return (True, f"unknown_zone={zone} (PASS by default)")

    if fails:
        reason = f"{zone} SKIP: " + ", ".join(fails)
        if skipped:
            reason += f" [skipped: {','.join(skipped)}]"
        return (False, reason)

    if skipped:
        return (True, f"{zone} PASS (graceful — {','.join(skipped)} missing)")
    return (True, f"{zone} PASS")


# Convenience wrapper: feature-dict-keyed entry
def evaluate_from_features(zone: str, feats: dict, sector: str | None = None,
                            dow: int | None = None) -> Tuple[bool, str]:
    """Extract relevant features from a flat dict + apply evaluate()."""
    return evaluate(
        zone=zone,
        beta=feats.get("beta"),
        sector=sector,
        vix=feats.get("vix"),
        dow=dow,
        gain_from_open=feats.get("gain_from_open"),
        spy_intra=feats.get("spy_intra"),
        mom20d=feats.get("mom20d"),
    )
