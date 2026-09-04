"""Riser identity picker — gate (stock identity) + ML ranker (within-gate win-classifier).

The assembled system from research_stock_identity_edge (2026-06-20):
  L3 gate:   stock_track_record.passes_gate (prior_n>=6 & prior_avg>0) — the EDGE.
  L2 ranker: win-classifier ensemble trained ONLY on gate-passed history — ranks within gate.
Picks top-1 by mean ML prob among gate survivors; abstains if no candidate passes the gate.
Falls back to rank-by-gain if models absent.
"""
from __future__ import annotations
import json, glob
from pathlib import Path
import lightgbm as lgb
import numpy as np
from src.scan import stock_track_record as STR

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / 'backtests' / 'models_riser_identity'


class RiserIdentityPicker:
    def __init__(self):
        self.meta = json.load(open(MODELS / 'meta.json'))
        self.feats = self.meta['feats']
        self.boosters = [lgb.Booster(model_file=p) for p in sorted(glob.glob(str(MODELS / 'winrank_seed*.txt')))]

    def _score(self, feat: dict) -> float:
        x = np.array([[feat.get(f, 0.0) for f in self.feats]], float)
        return float(np.mean([b.predict(x)[0] for b in self.boosters]))

    def pick(self, candidates: list[dict], scan_date: str) -> dict | None:
        """candidates: [{'sym','date','gain_from_open', <features...>}]. Returns chosen dict or None.
        Gate by identity, rank survivors by ML win prob (fallback gain)."""
        gated = [c for c in candidates if STR.passes_gate(c['sym'], scan_date)]
        if not gated:
            return None  # abstain — no PROVEN-good stock today
        if self.boosters:
            for c in gated:
                c['_winp'] = self._score(c)
            return max(gated, key=lambda c: c['_winp'])
        return max(gated, key=lambda c: c.get('gain_from_open', 0))


_picker = None
def get_picker():
    global _picker
    if _picker is None:
        _picker = RiserIdentityPicker()
    return _picker
