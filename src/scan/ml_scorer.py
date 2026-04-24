"""
ML Scorer v16 mixed — trained on 5.3yr data (2021-04 → 2026-04).

Per-bucket walk-forward validation (7 unseen months 2025-10 to 2026-04):
  09:30  tp1 classifier      thr 0.45    WR=88%  avg=+2.01%  trail 3→2→1
  10:00  Huber + Q25 + Conf  thr 0.10    WR=80%  avg=+1.82%  trail 3%
  10:45  tp1 classifier      thr 0.55    WR=79%  avg=+2.74%  trail 3%
  11:30  tp1 classifier      thr 0.60    WR=81%  avg=+2.91%  trail 3%

Why mixed (Huber for 10:00, tp1 for 10:45/11:30):
- 10:00: strong momentum bucket — Huber's smooth ranking captures it best
- 10:45/11:30: noisier — tp1's binary "will it hit +1%?" cuts noise better
- avg/trade jump: 10:45 +1.49→+2.74 (+84%), 11:30 +1.06→+2.91 (+175%)

For 10:45/11:30, tp1 alone is the gate (no Q25/Conf needed —
tp1 already directly answers "is this trade worth taking?").

v16 mixed vs v9 production: +37% avg/trade across 10+ buckets.
"""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb

MODEL_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v16'
V9_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v9'  # rollback ref


class MLScorer:
    BUCKETS = {
        (0, 30):    '09:30-10:00',
        (30, 75):   '10:00-10:45',
        (75, 120):  '10:45-11:30',
        (120, 210): '11:30-13:00',  # match feature_builder training ranges
        (210, 270): '13:00-14:00',
        (270, 390): '14:00-16:00',  # 14:00 + 120 min = 16:00
    }

    # Primary model per bucket (returns score for threshold_75() check)
    # 09:30, 10:45, 11:30: tp1 classifier (probability of reaching +1%)
    # 10:00:               Huber tight (Huber wins this bucket — see docstring)
    MODEL_FILES = {
        '09:30-10:00': ('lgb_tp1_0930_1000_seed{}.txt', 5),
        '10:00-10:45': ('lgb_tight_1000_1045_seed{}.txt', 5),
        '10:45-11:30': ('lgb_tp1_1045_1130_seed{}.txt', 5),
        '11:30-13:00': ('lgb_tp1_1130_1300_seed{}.txt', 5),
    }

    # Q25 model files — only 10:00 (Huber bucket needs Q25 downside floor)
    # 10:45/11:30 use tp1 alone (binary "hit +1%" directly cuts downside)
    Q25_MODEL_FILES = {
        '10:00-10:45': ('lgb_q25_1000_1045_seed{}.txt', 5),
    }

    # Confidence model files — only 09:30 + 10:00 (tp1 buckets don't need conf gate)
    CONF_MODEL_FILES = {
        '09:30-10:00': ('lgb_conf_0930_1000_seed{}.txt', 5),
        '10:00-10:45': ('lgb_conf_1000_1045_seed{}.txt', 5),
    }

    # Confidence thresholds — only Huber bucket (10:00) + 09:30 keep conf gate
    # 10:45 / 11:30 use tp1 only (no conf threshold needed)
    CONF_THRESHOLDS = {
        '09:30-10:00': 0.60,
        '10:00-10:45': 0.55,
    }

    # Q25 thresholds — only 10:00 (Huber bucket)
    # 10:00: Q25>=-0.2 → WR 80%
    Q25_THRESHOLDS = {
        '10:00-10:45': -0.2,
    }

    def __init__(self):
        self.models = {}
        self.q25_models = {}
        self.conf_models = {}
        self._load_features()
        self._load_models()

    def _load_features(self):
        v7_dir = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v7'
        with open(v7_dir / 'features.txt') as f:
            self.features_v7 = [line.strip() for line in f if line.strip()]
        with open(MODEL_DIR / 'features.txt') as f:
            self.features_v9 = [line.strip() for line in f if line.strip()]
        # 09:30 uses v7 features + 10 engineered gap interactions
        features_0930_path = MODEL_DIR / 'features_0930.txt'
        if features_0930_path.exists():
            with open(features_0930_path) as f:
                self.features_0930 = [line.strip() for line in f if line.strip()]
        else:
            self.features_0930 = self.features_v7
        # Confidence model uses extended features (v9 + cross-asset + anomaly)
        conf_feats_path = MODEL_DIR / 'features_confidence.txt'
        if conf_feats_path.exists():
            with open(conf_feats_path) as f:
                self.features_confidence = [line.strip() for line in f if line.strip()]
        else:
            self.features_confidence = self.features_v9
        # 09:30 confidence uses v7+engineered+cross-asset+anomaly
        conf_0930_path = MODEL_DIR / 'features_confidence_0930.txt'
        if conf_0930_path.exists():
            with open(conf_0930_path) as f:
                self.features_confidence_0930 = [line.strip() for line in f if line.strip()]
        else:
            self.features_confidence_0930 = self.features_0930

    def _load_models(self):
        # Load mean (Huber) models
        for bucket, (pattern, n_seeds) in self.MODEL_FILES.items():
            ensemble = []
            for s in range(n_seeds):
                mp = MODEL_DIR / pattern.format(s)
                if mp.exists():
                    ensemble.append(lgb.Booster(model_file=str(mp)))
            if ensemble:
                self.models[bucket] = ensemble

        # Load Q25 models
        for bucket, (pattern, n_seeds) in self.Q25_MODEL_FILES.items():
            ensemble = []
            for s in range(n_seeds):
                mp = MODEL_DIR / pattern.format(s)
                if mp.exists():
                    ensemble.append(lgb.Booster(model_file=str(mp)))
            if ensemble:
                self.q25_models[bucket] = ensemble

        # Load Confidence models
        for bucket, (pattern, n_seeds) in self.CONF_MODEL_FILES.items():
            ensemble = []
            for s in range(n_seeds):
                mp = MODEL_DIR / pattern.format(s)
                if mp.exists():
                    ensemble.append(lgb.Booster(model_file=str(mp)))
            if ensemble:
                self.conf_models[bucket] = ensemble

    def get_bucket(self, minutes_from_open: int) -> str:
        for (lo, hi), name in self.BUCKETS.items():
            if lo <= minutes_from_open < hi:
                return name
        return '14:00-16:00'

    def score(self, features: dict, minutes_from_open: int) -> float:
        """Score stock with bucket-appropriate mean model."""
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.models.get(bucket)
        if not ensemble:
            return 0.0

        # 09:30 uses features_0930 (matches what tp1 model was trained on)
        feat_list = self.features_0930 if minutes_from_open < 30 else self.features_v9
        row = [features.get(f, 0.0) for f in feat_list]
        arr = np.array([row], dtype=float)
        preds = [float(m.predict(arr)[0]) for m in ensemble]
        return sum(preds) / len(preds)

    def score_q25(self, features: dict, minutes_from_open: int) -> float:
        """Score stock's downside (Q25) — lower = more likely to fade."""
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.q25_models.get(bucket)
        if not ensemble:
            return 0.0  # no Q25 model for this bucket

        # 09:30 uses v7+engineered features, 10:00+ uses v9
        feat_list = self.features_0930 if minutes_from_open < 30 else self.features_v9
        row = [features.get(f, 0.0) for f in feat_list]
        arr = np.array([row], dtype=float)
        preds = [float(m.predict(arr)[0]) for m in ensemble]
        return sum(preds) / len(preds)

    def passes_q25_filter(self, features: dict, minutes_from_open: int) -> bool:
        """Check if stock passes Q25 downside filter.
        Returns True if Q25 prediction >= bucket threshold, or if no Q25 model."""
        bucket = self.get_bucket(minutes_from_open)
        threshold = self.Q25_THRESHOLDS.get(bucket)
        if threshold is None:
            return True  # 09:30 has no Q25 filter

        q25_score = self.score_q25(features, minutes_from_open)
        return q25_score >= threshold

    def score_confidence(self, features: dict, minutes_from_open: int) -> float:
        """Score probability that primary prediction will be correct.
        Returns 0-1 (higher = more confident)."""
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.conf_models.get(bucket)
        if not ensemble:
            return 1.0  # no confidence model for this bucket = pass

        # 09:30 uses different feature list (v7+engineered) than 10:00+ (v9)
        feat_list = (self.features_confidence_0930 if minutes_from_open < 30
                     else self.features_confidence)
        row = [features.get(f, 0.0) for f in feat_list]
        arr = np.array([row], dtype=float)
        preds = [float(m.predict(arr)[0]) for m in ensemble]
        return sum(preds) / len(preds)

    def passes_confidence_filter(self, features: dict, minutes_from_open: int) -> bool:
        """Check if confidence exceeds threshold (regime-aware gate).
        Returns True if confident, False if uncertain (skip trade)."""
        bucket = self.get_bucket(minutes_from_open)
        threshold = self.CONF_THRESHOLDS.get(bucket)
        if threshold is None:
            return True  # 09:30 has no confidence gate

        conf = self.score_confidence(features, minutes_from_open)
        return conf >= threshold

    def score_gain(self, features: dict, minutes_from_open: int) -> float:
        return self.score(features, minutes_from_open)

    def score_profit(self, features: dict, minutes_from_open: int) -> float:
        return self.score(features, minutes_from_open)

    def score_big(self, features: dict, minutes_from_open: int) -> float:
        return self.score(features, minutes_from_open)

    def threshold_75(self, minutes_from_open: int) -> float:
        """Per-bucket thresholds (validated 7-month walk-forward 2026-04-23)."""
        if minutes_from_open >= 120:       # 11:30-13:00 tp1 (P(reach +1%) >= 60%)
            return 0.60
        if minutes_from_open >= 75:        # 10:45-11:30 tp1 (P(reach +1%) >= 55%)
            return 0.55
        if minutes_from_open >= 30:        # 10:00-10:45 Huber tight
            return 0.10
        return 0.45                        # 09:30 tp1 (P(reach +1%) >= 45%)

    def can_reach_75(self, minutes_from_open: int) -> bool:
        # 13:00+ (mins >= 210) has 48% WR coin flip — skip.
        # 11:30-13:00 bucket extends to 210 per training data.
        return minutes_from_open < 210


_SCORER_INSTANCE = None


def get_scorer() -> MLScorer:
    global _SCORER_INSTANCE
    if _SCORER_INSTANCE is None:
        _SCORER_INSTANCE = MLScorer()
    return _SCORER_INSTANCE
