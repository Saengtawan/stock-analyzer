"""H12-A picking logic — encapsulates cell filter + hard gates + Option E* + top-1.

Designed as a thin module that ml_filter.py can call once H12-A is enabled
(env ML_FILTER_VARIANT=h12a). Keeps the H12-A logic isolated from the 1000+
line production strategy file.

Usage from ml_filter.py:
    from src.scan.h12a_picker import score_and_filter_h12a, pick_top1_per_zone

    # For each candidate:
    sc, gate_reason = score_and_filter_h12a(scorer, features, mfo, sector,
                                              vix=vix, spy_intra=spy_intra,
                                              vix_5d_chg=vix_5d_chg,
                                              sec_rel_strength=sec_rel_strength,
                                              dow=dow)
    if sc < 0:
        # filtered out
        continue
    candidates.append({...})

    picks = pick_top1_per_zone(candidates)
"""
from __future__ import annotations
from typing import Optional, Dict, List, Any, Tuple

# Z4 Option E* sectors
Z4_GOOD_SECTORS = {'Consumer Defensive', 'Basic Materials', 'Technology'}
Z4_VIX_CRISIS = 25.0


def get_zone(mfo: int) -> Optional[str]:
    if 0 <= mfo <= 9: return 'Z1'
    if 10 <= mfo <= 29: return 'Z2'
    if 30 <= mfo <= 44: return 'Z3'
    if 45 <= mfo <= 75: return 'Z4'
    return None


def passes_regime_gate(zone: str,
                       vix: Optional[float],
                       vix_5d_chg: Optional[float],
                       sec_rel_strength: Optional[float],
                       spy_intra: Optional[float],
                       dow: Optional[int],
                       sector: str) -> Tuple[bool, str]:
    """H12-A hard regime gates per zone.

    Returns (passes, reason_if_blocked).
    Missing features → graceful PASS (don't drop).
    """
    if zone == 'Z1':
        # VIX < 20 AND sec_rel_strength > 0
        if vix is not None and vix >= 20:
            return False, f'Z1 VIX={vix:.1f}>=20'
        if sec_rel_strength is not None and sec_rel_strength <= 0:
            return False, f'Z1 sec_strength={sec_rel_strength:.2f}<=0'
        return True, 'Z1 regime OK'

    if zone == 'Z2':
        # vix_5d_chg < 0 (VIX trending down)
        if vix_5d_chg is not None and vix_5d_chg >= 0:
            return False, f'Z2 vix_5d_chg={vix_5d_chg:.2f}>=0 (rising)'
        return True, 'Z2 regime OK'

    if zone == 'Z3':
        # sec_rel_strength > 0 AND DOW != Friday (4)
        if sec_rel_strength is not None and sec_rel_strength <= 0:
            return False, f'Z3 sec_strength={sec_rel_strength:.2f}<=0'
        if dow == 4:
            return False, 'Z3 DOW=Fri'
        return True, 'Z3 regime OK'

    if zone == 'Z4':
        # Option E*:
        #   if vix < 25:
        #     if sector in GOOD_SECTORS: spy_intra > 0.2
        #     else:                       spy_intra > 0.5
        #   else (crisis):                spy_intra > 0.5
        if vix is None or spy_intra is None:
            return True, 'Z4 missing VIX/SPY (graceful pass)'
        if vix < Z4_VIX_CRISIS:
            if sector in Z4_GOOD_SECTORS:
                if spy_intra <= 0.2:
                    return False, f'Z4 calm+good sec SPY={spy_intra:.2f}<=0.2'
            else:
                if spy_intra <= 0.5:
                    return False, f'Z4 calm+other sec SPY={spy_intra:.2f}<=0.5'
        else:  # crisis
            if spy_intra <= 0.5:
                return False, f'Z4 crisis(VIX={vix:.1f}) SPY={spy_intra:.2f}<=0.5'
        return True, 'Z4 Option E* OK'

    return True, f'unknown_zone={zone}'


def score_and_filter_h12a(scorer, features: dict, mfo: int, sector: str,
                          *,
                          vix: Optional[float] = None,
                          vix_5d_chg: Optional[float] = None,
                          sec_rel_strength: Optional[float] = None,
                          spy_intra: Optional[float] = None,
                          dow: Optional[int] = None) -> Tuple[float, str]:
    """One-shot H12-A scoring + filtering.

    Returns (score, reason). If score is 0 or negative, the pick is filtered out.
    """
    zone = get_zone(mfo)
    if not zone:
        return 0.0, 'out_of_zone'

    # 1) Score using H12-A scorer
    win_p = scorer.score(features, mfo, sector)

    # 2) Cell filter (S2/S7/none)
    if not scorer.passes_cell_filter(zone, sector):
        cell = scorer.get_cell_rating(zone, sector) or {}
        return 0.0, f'{zone} cell_bad (sec={sector} WR={cell.get("WR",0):.0f}% avg={cell.get("avg",0):+.2f}%)'

    # 3) Regime gate (Z1 VIX<20, Z2 vix_5d<0, Z3 sec>0+¬Fri, Z4 Option E*)
    passes, reason = passes_regime_gate(zone, vix, vix_5d_chg, sec_rel_strength,
                                         spy_intra, dow, sector)
    if not passes:
        return 0.0, reason

    return win_p, f'{zone} OK ({reason})'


def pick_top1_per_zone(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Select top-1 per zone by win_p score.

    Each candidate must have: 'sym', 'mfo', 'win_p' (and any other metadata).
    Returns up to 4 picks (one per zone, if a candidate exists in that zone).
    """
    by_zone: Dict[str, List[Dict[str, Any]]] = {'Z1': [], 'Z2': [], 'Z3': [], 'Z4': []}
    for c in candidates:
        z = get_zone(c['mfo'])
        if z:
            by_zone[z].append(c)
    picks = []
    for z, cs in by_zone.items():
        if not cs: continue
        top = max(cs, key=lambda x: x['win_p'])
        picks.append(top)
    return picks
