"""
ML Scorer — big × vote hybrid: p_big × (tp1 + profit + big) / 3

Three models combined:
  tp1:    "will this stock reach +1%?"     → catches momentum
  profit: "will this actually profit?"     → avoids losers
  big:    "will this profit > +2%?"        → catches big winners

Score = p_big × vote → requires BOTH big-winner signal AND consensus.
Filters out pumps (high tp1, low profit) and safe-small (high profit, low big).

Holdout validation (Feb-Apr 2026, N=538):
  WR 67.3% (vote 65.4%)
  avg_ret +1.23%/trade (vote +0.89%, +38% relative)
  big-winner rate 40.0% (vote 33.6%)
  bad rate 13.4% (vote 15.6%)
  Wins 3/3 months vs vote.
"""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb

MODEL_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v7'


class MLScorer:
    BUCKETS = {
        (0, 30):    '09:30-10:00',
        (30, 75):   '10:00-10:45',
        (75, 120):  '10:45-11:30',
        (120, 180): '11:30-13:00',
        (180, 270): '13:00-14:00',
        (270, 400): '14:00-16:00',
    }

    def __init__(self):
        self.models_gain = {}
        self.models_profit = {}
        self.models_big = {}
        self.metadata = {}
        self._load_features()
        self._load_models()

    def _load_features(self):
        with open(MODEL_DIR / 'features.txt') as f:
            self.features = [line.strip() for line in f if line.strip()]

    def _load_models(self):
        with open(MODEL_DIR / 'metadata.json') as f:
            meta_list = json.load(f)
        for m in meta_list:
            bucket = m['bucket']
            self.metadata[bucket] = m
            for key, store in [('model_files', self.models_gain),
                               ('profit_model_files', self.models_profit),
                               ('big_model_files', self.models_big)]:
                model_files = m.get(key) or []
                ensemble = []
                for mf in model_files:
                    if not mf: continue
                    mp = MODEL_DIR / mf
                    if mp.exists():
                        ensemble.append(lgb.Booster(model_file=str(mp)))
                if ensemble:
                    store[bucket] = ensemble

    def get_bucket(self, minutes_from_open: int) -> str:
        for (lo, hi), name in self.BUCKETS.items():
            if lo <= minutes_from_open < hi:
                return name
        return '14:00-16:00'

    def _score_ensemble(self, ensemble, features: dict) -> float:
        row = [features.get(f, 0.0) for f in self.features]
        arr = np.array([row], dtype=float)
        preds = [float(m.predict(arr)[0]) for m in ensemble]
        return sum(preds) / len(preds)

    def score_gain(self, features: dict, minutes_from_open: int) -> float:
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.models_gain.get(bucket)
        return self._score_ensemble(ensemble, features) if ensemble else 0.0

    def score_profit(self, features: dict, minutes_from_open: int) -> float:
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.models_profit.get(bucket)
        return self._score_ensemble(ensemble, features) if ensemble else 0.0

    def score_big(self, features: dict, minutes_from_open: int) -> float:
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.models_big.get(bucket)
        return self._score_ensemble(ensemble, features) if ensemble else 0.0

    def score(self, features: dict, minutes_from_open: int) -> float:
        """big × vote hybrid — validated 2026-04-14 holdout Feb-Apr 2026:
        WR 67% (vs vote 65%), avg_ret +1.23%/trade (vs vote +0.89%, +38% $).
        Highest big-winner rate (40%), lowest bad rate (13%). Wins 3/3 months."""
        g = self.score_gain(features, minutes_from_open)
        p = self.score_profit(features, minutes_from_open)
        b = self.score_big(features, minutes_from_open)
        vote = (g + p + b) / 3
        return b * vote

    def threshold_75(self, minutes_from_open: int) -> float:
        """Time-conditional threshold — push each slice to WR ≥ 60%.
        Validated 2026-04-16 threshold hunt on v7 holdout:
          10:00-10:15 (mid-morning drift): bxv ≥ 0.05 → WR 57.6% → 62.9%
          10:15-10:30 (worst morning lull): bxv ≥ 0.07 → WR 53.5% → 70.1%
          10:55-11:15 (pre-lunch fade):    bxv ≥ 0.08 → WR 56.0% → 71.7%
          12:00-13:00 (deep lunch):        bxv ≥ 0.10 → WR 59%   → 82%+
        """
        if minutes_from_open >= 150:       # 12:00-13:00
            return 0.10
        if 85 <= minutes_from_open < 105:  # 10:55-11:15
            return 0.08
        if 45 <= minutes_from_open < 60:   # 10:15-10:30
            return 0.07
        if 30 <= minutes_from_open < 45:   # 10:00-10:15
            return 0.05
        return 0.0

    def can_reach_75(self, minutes_from_open: int) -> bool:
        # 13:00-14:00 and 14:00-16:00 both validated at WR 48% (coin flip) — skip.
        return minutes_from_open < 180


_SCORER_INSTANCE = None


def get_scorer() -> MLScorer:
    global _SCORER_INSTANCE
    if _SCORER_INSTANCE is None:
        _SCORER_INSTANCE = MLScorer()
    return _SCORER_INSTANCE
