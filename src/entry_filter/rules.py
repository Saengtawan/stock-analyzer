"""Entry filter v1 rules — pure-function evaluator, no IO."""
from __future__ import annotations
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

    PASS rules are conjunctive (all must hold). If a feature is missing,
    that specific check is skipped (graceful fallback — do not drop pick).
    """
    fails = []
    skipped = []

    if zone == "Z1":
        # Double gate: β≥1.2 + sector≠Industrials
        # (β threshold relaxed 1.5→1.2 on 2026-06-04 to catch β 1.2-1.5 winners
        #  like ASML/AVGO that were borderline-skipped. Trade-off accepted:
        #  WR drops ~2pp vs 1.5 threshold, but N rises ~30%.
        #  VIX 14-18 dropped earlier same day — too restrictive.)
        if _is_missing(beta): skipped.append("β?")
        elif beta < 1.2: fails.append(f"β={beta:.2f}<1.2")
        if _is_missing(sector): skipped.append("sec?")
        elif sector == "Industrials": fails.append("sec=Industrial")

    elif zone == "Z2":
        # DOW≠Mon + gain≤3 + SPY≥-0.3 + sector∉{Utilities,Real Estate}
        if _is_missing(dow): skipped.append("dow?")
        elif dow == 0: fails.append("DOW=Mon")
        if _is_missing(gain_from_open): skipped.append("gain?")
        elif gain_from_open > 3: fails.append(f"gain={gain_from_open:.1f}>3")
        if _is_missing(spy_intra): skipped.append("spy?")
        elif spy_intra < -0.3: fails.append(f"spy={spy_intra:.2f}<-0.3")
        if _is_missing(sector): skipped.append("sec?")
        elif sector in ("Utilities", "Real Estate"): fails.append(f"sec={sector}")

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
