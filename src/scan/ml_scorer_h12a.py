"""H12-A multi-model scorer (V-2 for Z1, V-C for Z2/Z3/Z4).

Loads per-(zone, sector) models from backtests/models_prod_v23_h12a/.

For each scoring call:
  - Get zone from mfo
  - If sector has a trained specialist → use sector ensemble (5 seeds min)
  - Else → use generalist ensemble (5 seeds min)

Output: win_p ∈ [0, 1] (probability the pick will hit label_z12_market_3dd / label_z34_market).

Usage:
    from src.scan.ml_scorer_h12a import get_scorer_h12a
    scorer = get_scorer_h12a()
    win_p = scorer.score(features, mfo, sector)
    cell = scorer.get_cell_rating(zone, sector)   # {N, WR, avg} or None
"""
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
import lightgbm as lgb
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT / 'backtests/models_prod_v23_h12a'
CELL_RATINGS_PATH = ROOT / 'configs/h12a_cell_ratings.json'

ZONES = [
    ('Z1', 0, 9),
    ('Z2', 10, 29),
    ('Z3', 30, 44),
    ('Z4', 45, 75),
]

SECTORS = ['Technology', 'Industrials', 'Consumer Cyclical', 'Financial Services',
           'Basic Materials', 'Healthcare', 'Energy', 'Communication Services',
           'Consumer Defensive', 'Utilities', 'Real Estate']


def _sec_safe(s: str) -> str:
    return s.replace(' ', '_').replace('/', '_')


class MLScorerH12A:
    """Multi-model scorer for H12-A architecture."""

    def __init__(self, models_dir: Path = MODELS_DIR,
                 cell_ratings_path: Path = CELL_RATINGS_PATH):
        self.models_dir = Path(models_dir)
        self.cell_ratings_path = Path(cell_ratings_path)

        # Per-zone state
        self.generalist: Dict[str, List[lgb.Booster]] = {}   # zone -> [5 boosters]
        self.specialists: Dict[str, Dict[str, List[lgb.Booster]]] = {}  # zone -> sector -> [5 boosters]
        self.features: Dict[str, List[str]] = {}  # zone -> feature list
        self.meta: Dict[str, dict] = {}           # zone -> meta dict
        self.cell_ratings: Dict[str, Dict[str, dict]] = {}  # zone -> sector -> {N, WR, avg}

        self._load_all_zones()
        self._load_cell_ratings()

        loaded = sum(1 for z in self.generalist if self.generalist[z])
        if loaded < 4:
            print(f"⚠️  MLScorerH12A: only {loaded}/4 zones loaded — check {self.models_dir}")

    def _load_zone(self, zone: str):
        zone_dir = self.models_dir / zone
        if not zone_dir.exists():
            print(f"  ⚠️  {zone}: dir missing ({zone_dir})")
            return

        # Meta + features
        meta_path = zone_dir / 'meta.json'
        if not meta_path.exists():
            print(f"  ⚠️  {zone}: meta.json missing")
            return
        with open(meta_path) as f:
            meta = json.load(f)
        self.meta[zone] = meta
        self.features[zone] = meta['features']

        # Generalist boosters (5 seeds)
        gen_list = []
        for s in range(5):
            p = zone_dir / f'generalist_seed{s}.txt'
            if p.exists():
                gen_list.append(lgb.Booster(model_file=str(p)))
        if len(gen_list) != 5:
            print(f"  ⚠️  {zone}: only {len(gen_list)}/5 generalist boosters")
            return
        self.generalist[zone] = gen_list

        # Sector specialists
        self.specialists[zone] = {}
        for sec in meta.get('sectors', []):
            sec_list = []
            for s in range(5):
                p = zone_dir / f'sector_{_sec_safe(sec)}_seed{s}.txt'
                if p.exists():
                    sec_list.append(lgb.Booster(model_file=str(p)))
            if len(sec_list) == 5:
                self.specialists[zone][sec] = sec_list

        print(f"  {zone}: 5 generalist + {len(self.specialists[zone])} sectors loaded "
              f"({meta['arch']}, label={meta['label']})")

    def _load_all_zones(self):
        print(f"[MLScorerH12A] loading from {self.models_dir}")
        for zone, _, _ in ZONES:
            self._load_zone(zone)

    def _load_cell_ratings(self):
        if not self.cell_ratings_path.exists():
            print(f"  ⚠️  cell ratings not found: {self.cell_ratings_path}")
            return
        with open(self.cell_ratings_path) as f:
            data = json.load(f)
        self.cell_ratings = data.get('cells_by_zone', {})
        print(f"  cell ratings: {sum(len(v) for v in self.cell_ratings.values())} "
              f"(zone, sector) pairs loaded")

    @staticmethod
    def get_zone(mfo: int) -> Optional[str]:
        for zone, lo, hi in ZONES:
            if lo <= mfo <= hi:
                return zone
        return None

    def _row(self, features: dict, zone: str) -> np.ndarray:
        feat_list = self.features.get(zone, [])
        row = [features.get(f, 0.0) for f in feat_list]
        return np.array([row], dtype=float)

    def score(self, features: dict, mfo: int, sector: str = '') -> float:
        """Return win_p ∈ [0, 1] for this pick.

        Routing:
          - If sector has trained specialist → use specialist (5 seeds min)
          - Else → fall back to generalist (5 seeds min)
        """
        zone = self.get_zone(mfo)
        if not zone or zone not in self.generalist:
            return 0.0
        arr = self._row(features, zone)

        # Sector specialist if available
        if sector and sector in self.specialists.get(zone, {}):
            boosters = self.specialists[zone][sector]
        else:
            boosters = self.generalist[zone]

        # min() of 5 seeds (conservative — matches research aggregation)
        preds = [float(b.predict(arr)[0]) for b in boosters]
        return min(preds)

    def get_cell_rating(self, zone: str, sector: str) -> Optional[dict]:
        """Return {N, WR, avg} for (zone, sector) or None if not in ratings."""
        return self.cell_ratings.get(zone, {}).get(sector)

    def passes_cell_filter(self, zone: str, sector: str) -> bool:
        """Apply per-zone cell filter:
          - Z1: S2 → (avg > 0) OR (WR >= 50)
          - Z2/Z3: S7 → (avg > 0) AND (WR >= 50)
          - Z4: none (Option E* handles in strategy)
        Missing cells (sector never appeared in training): default PASS (defensive).
        """
        if zone == 'Z4':
            return True
        cell = self.get_cell_rating(zone, sector)
        if cell is None:
            return True  # graceful fallback — unknown sectors pass cell, regime gates still filter

        if zone == 'Z1':
            return (cell['avg'] > 0) or (cell['WR'] >= 50)
        else:  # Z2 / Z3
            return (cell['avg'] > 0) and (cell['WR'] >= 50)


# Singleton (lazy-loaded)
_INSTANCE: Optional[MLScorerH12A] = None


def get_scorer_h12a() -> MLScorerH12A:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MLScorerH12A()
    return _INSTANCE
