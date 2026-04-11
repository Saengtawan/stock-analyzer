"""
ML Scorer — uses trained LightGBM models to score candidates.

Trained via /tmp/bt_ml_production.py from 2025+ data (301K samples).
Target label: reach +1% at any point after entry before close
(matches trail 1% from peak exit).

Per-bucket models in backtests/models_prod/ with prob thresholds
that achieve 75%+ WR on walk-forward test set.

Usage:
    from src.scan.ml_scorer import MLScorer
    scorer = MLScorer()
    prob = scorer.score_candidate(features_dict, bucket='10:00-10:45')
    if prob >= scorer.threshold_75(bucket):
        # high-conviction pick
"""
import os
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb

# v2 = ensemble of 5 models per bucket, achieves 75%+ for 5/6 buckets
MODEL_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v2'


class MLScorer:
    BUCKETS = {
        # minutes from open → bucket name
        (0, 30):    '09:30-10:00',
        (30, 75):   '10:00-10:45',
        (75, 120):  '10:45-11:30',
        (120, 180): '11:30-13:00',
        (180, 270): '13:00-14:00',
        (270, 400): '14:00-16:00',
    }

    def __init__(self):
        self.models = {}
        self.metadata = {}
        self._load_features()
        self._load_models()

    def _load_features(self):
        with open(MODEL_DIR / 'features.txt') as f:
            self.features = [line.strip() for line in f if line.strip()]

    def _load_models(self):
        """Load ensemble models. Each bucket has 5 LightGBM models averaged."""
        with open(MODEL_DIR / 'metadata.json') as f:
            meta_list = json.load(f)
        for m in meta_list:
            bucket = m['bucket']
            self.metadata[bucket] = m
            model_files = m.get('model_files') or [m.get('model_file')]
            ensemble = []
            for mf in model_files:
                if not mf: continue
                mp = MODEL_DIR / mf
                if mp.exists():
                    ensemble.append(lgb.Booster(model_file=str(mp)))
            if ensemble:
                self.models[bucket] = ensemble

    def get_bucket(self, minutes_from_open: int) -> str:
        for (lo, hi), name in self.BUCKETS.items():
            if lo <= minutes_from_open < hi:
                return name
        return '14:00-16:00'

    def score(self, features: dict, minutes_from_open: int) -> float:
        """Return ensemble-averaged probability [0,1] from bucket models."""
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.models.get(bucket)
        if not ensemble:
            return 0.0
        row = [features.get(f, 0.0) for f in self.features]
        arr = np.array([row], dtype=float)
        preds = [float(m.predict(arr)[0]) for m in ensemble]
        return sum(preds) / len(preds)

    def threshold_75(self, minutes_from_open: int) -> float:
        """Return prob threshold that achieves 75% WR, or None if bucket
        cannot reach 75% even at tight threshold."""
        bucket = self.get_bucket(minutes_from_open)
        meta = self.metadata.get(bucket, {})
        return meta.get('threshold_75')

    def can_reach_75(self, minutes_from_open: int) -> bool:
        return self.threshold_75(minutes_from_open) is not None

    def expected_top5_wr(self, minutes_from_open: int) -> float:
        bucket = self.get_bucket(minutes_from_open)
        return self.metadata.get(bucket, {}).get('test_top5_wr', 0.0)


# Shared singleton (load once per process)
_SCORER_INSTANCE = None


def get_scorer() -> MLScorer:
    global _SCORER_INSTANCE
    if _SCORER_INSTANCE is None:
        _SCORER_INSTANCE = MLScorer()
    return _SCORER_INSTANCE
