"""
ml_scorer_lean — Lean pooled foundation scorer (v1, 2026-06-18).

Drop-in alternative to ml_scorer_h12a with the SAME interface
(`score(features, mfo, sector) -> win_p`). Built from the ablation that proved
a single pooled model per zone (+ sector as a categorical feature, mean-of-seeds
+ isotonic calibration) BEATS the 235 per-sector arch on walk-forward with 3-5x
less overfit. See memory research_lean_vs_235_ablation.

Architecture per zone:
  - models.pkl     : list of N LGBMClassifier seeds (mean-aggregated)
  - calibrator.pkl : isotonic regression (raw mean prob -> calibrated win_p)
  - meta.json      : features (15/12), sector_categories, label, mfo_range, eval_mfo

Coverage: Z1 (macro-15) + Z2 (intraday-clean-12) ONLY. Z3/Z4 have no lean model
(WF: Z3 weak, Z4 negative) -> score() returns None there so the caller falls back
to gates / the existing scorer. Both feature sets are parity-clean (no
gain_from_open / gap_from_prev / vs_vwap, which are train/serve open-skewed).

Stateless + per-candidate. Quantile abstention is a SEPARATE day-level component
(it needs cross-day rolling history) — not handled here.
"""
from __future__ import annotations
import os
import json
import pickle
from pathlib import Path
from typing import Optional, Dict, List

import numpy as np
import pandas as pd

_MODELS_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_lean_v1'

# Zone <- minutes_from_open, same mapping as H12-A.
_ZONE_BOUNDS = [('Z1', 0, 9), ('Z2', 10, 29), ('Z3', 30, 44), ('Z4', 45, 75)]


def _zone_for(mfo: int) -> Optional[str]:
    for z, lo, hi in _ZONE_BOUNDS:
        if lo <= mfo <= hi:
            return z
    return None


class MLScorerLean:
    """Lean pooled scorer. Covers Z1/Z2; returns None elsewhere (caller falls back)."""

    def __init__(self, models_dir: Path = _MODELS_DIR):
        self.models_dir = Path(models_dir)
        self.models: Dict[str, list] = {}
        self.calibrators: Dict[str, object] = {}
        self.features: Dict[str, List[str]] = {}
        self.sector_cats: Dict[str, List[str]] = {}
        self.meta: Dict[str, dict] = {}
        self._load()

    def _load(self):
        loaded = []
        for zone in ('Z1', 'Z2', 'Z3', 'Z4'):
            zd = self.models_dir / zone
            if not (zd / 'models.pkl').exists():
                continue
            self.models[zone] = pickle.load(open(zd / 'models.pkl', 'rb'))
            cal = zd / 'calibrator.pkl'
            self.calibrators[zone] = pickle.load(open(cal, 'rb')) if cal.exists() else None
            m = json.load(open(zd / 'meta.json'))
            self.meta[zone] = m
            self.features[zone] = m['features']
            self.sector_cats[zone] = m['sector_categories']
            loaded.append(f"{zone}({len(self.models[zone])} seeds, {len(m['features'])} feat)")
        print(f"[MLScorerLean] loaded {self.models_dir.name}: " + (", ".join(loaded) or "NOTHING"))

    @staticmethod
    def get_zone(mfo: int) -> Optional[str]:
        return _zone_for(mfo)

    def has_zone(self, mfo: int) -> bool:
        z = _zone_for(mfo)
        return z is not None and z in self.models

    def _row(self, features: dict, zone: str, sector: str) -> pd.DataFrame:
        feat_list = self.features[zone]
        data = {f: [float(features.get(f, 0.0) or 0.0)] for f in feat_list}
        X = pd.DataFrame(data)
        X['sector'] = pd.Categorical([sector], categories=self.sector_cats[zone])
        return X[feat_list + ['sector']]

    def score(self, features: dict, mfo: int, sector: str = '') -> Optional[float]:
        """Calibrated win_p for this candidate, or None if the zone has no lean model.

        None => caller should fall back to the existing scorer / gates.
        """
        zone = _zone_for(mfo)
        if zone is None or zone not in self.models:
            return None
        X = self._row(features, zone, sector)
        raw = float(np.mean([m.predict_proba(X)[:, 1][0] for m in self.models[zone]]))
        cal = self.calibrators.get(zone)
        return float(cal.predict([raw])[0]) if cal is not None else raw


_SINGLETON: Optional[MLScorerLean] = None


def get_scorer_lean() -> MLScorerLean:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = MLScorerLean()
    return _SINGLETON
