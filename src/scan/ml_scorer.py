"""
ML Scorer — Direct Profit model.

Model predicts "will this pick actually profit with trail 3% + sell at 13:00?"
This directly matches the real trading strategy, unlike the old model that
predicted "will reach +1%" which didn't account for trail/exit mechanics.

Backtest: WR 90.7%, avg +2.48%, $5K→$14,536 (+191%)
vs old (gain×safe): WR 89.8%, avg +2.26%, $5K→$13,206 (+164%)
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
        self.models_profit = {}
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
            model_files = m.get('profit_model_files') or []
            ensemble = []
            for mf in model_files:
                if not mf: continue
                mp = MODEL_DIR / mf
                if mp.exists():
                    ensemble.append(lgb.Booster(model_file=str(mp)))
            if ensemble:
                self.models_profit[bucket] = ensemble

    def get_bucket(self, minutes_from_open: int) -> str:
        for (lo, hi), name in self.BUCKETS.items():
            if lo <= minutes_from_open < hi:
                return name
        return '14:00-16:00'

    def score(self, features: dict, minutes_from_open: int) -> float:
        """Direct profit probability — will this pick profit with trail 3% + sell 13:00?"""
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.models_profit.get(bucket)
        if not ensemble:
            return 0.0
        row = [features.get(f, 0.0) for f in self.features]
        arr = np.array([row], dtype=float)
        preds = [float(m.predict(arr)[0]) for m in ensemble]
        return sum(preds) / len(preds)

    def threshold_75(self, minutes_from_open: int) -> float:
        bucket = self.get_bucket(minutes_from_open)
        meta = self.metadata.get(bucket, {})
        return meta.get('profit_threshold') or meta.get('threshold_75')

    def can_reach_75(self, minutes_from_open: int) -> bool:
        return self.threshold_75(minutes_from_open) is not None

    def score_gain(self, features: dict, minutes_from_open: int) -> float:
        return self.score(features, minutes_from_open)

    def score_safe(self, features: dict, minutes_from_open: int) -> float:
        return 1.0


_SCORER_INSTANCE = None


def get_scorer() -> MLScorer:
    global _SCORER_INSTANCE
    if _SCORER_INSTANCE is None:
        _SCORER_INSTANCE = MLScorer()
    return _SCORER_INSTANCE
