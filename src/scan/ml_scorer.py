"""
ML Scorer — dual-model scoring: gain probability × safety probability.

Model A (gain): predicts "will reach +1% before close"
Model B (safe): predicts "won't dip > -3% before close"
Combined score = prob_gain × prob_safe

Combined model selects picks that are BOTH profitable AND safe,
reducing SL hits from 7% → 0% while maintaining similar total profit
through compound growth (less drawdown = more capital for next trade).
"""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb

MODEL_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v3'


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
        self.models_safe = {}
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
            # Gain models
            for key, store in [('model_files', self.models_gain), ('safe_model_files', self.models_safe)]:
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

    def score_safe(self, features: dict, minutes_from_open: int) -> float:
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.models_safe.get(bucket)
        return self._score_ensemble(ensemble, features) if ensemble else 0.5

    def score(self, features: dict, minutes_from_open: int) -> float:
        """Combined score = gain × safe. Higher = profitable AND safe."""
        return self.score_gain(features, minutes_from_open) * self.score_safe(features, minutes_from_open)

    def threshold_75(self, minutes_from_open: int) -> float:
        bucket = self.get_bucket(minutes_from_open)
        meta = self.metadata.get(bucket, {})
        return meta.get('threshold_75')

    def can_reach_75(self, minutes_from_open: int) -> bool:
        return self.threshold_75(minutes_from_open) is not None

    # Keep for backward compat
    def expected_top5_wr(self, minutes_from_open: int) -> float:
        bucket = self.get_bucket(minutes_from_open)
        return self.metadata.get(bucket, {}).get('test_top5_wr', 0.0)


_SCORER_INSTANCE = None


def get_scorer() -> MLScorer:
    global _SCORER_INSTANCE
    if _SCORER_INSTANCE is None:
        _SCORER_INSTANCE = MLScorer()
    return _SCORER_INSTANCE
