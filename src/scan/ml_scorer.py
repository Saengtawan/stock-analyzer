"""
ML Scorer v20 — 09:30 bucket upgraded with V7+cross features and 365d window.

v20 changes (09:30 bucket only):
  - Features: V7 (37) + cross-asset ETF intraday (25) = 62 features
  - Training window: 365d (vs v19 = 180d)
  - Validated 24-month walk-forward: 71.0% WR / +1.94% avg
    (vs v19: 62.9% WR / +1.37% avg → +8.1pp WR / +0.57pp avg)

Other buckets retain v19 design — separately validated improvement only at 09:30.
  09:30  tp1 v20  V7+cross 365d   thr 0.45  WR=71.0% avg=+1.94%  ⭐ v20
  10:00  Huber + Q25 + Conf       thr 0.10  WR=66.6% avg=+0.93%  v19
  10:45  tp1 classifier            thr 0.55  WR=63.8% avg=+1.11%  v19
  11:30  tp1 classifier            thr 0.60  WR=65.8% avg=+1.53%  v19
"""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb

MODEL_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v19'
V20_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v20'  # 09:30 only
V16_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v16'  # rollback ref


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

    # Confidence regime gates — original v16 design
    # 09:30: conf >= 0.60 (gate uncertain regime picks)
    # 10:00: conf >= 0.55 (mid-day regime check)
    # 10:45/11:30: tp1 alone (no conf gate)
    CONF_THRESHOLDS = {
        '09:30-10:00': 0.60,
        '10:00-10:45': 0.55,
    }

    # Q25 downside filter — Huber bucket (10:00) only
    # 10:00: Q25 >= -0.2 (reject high-variance faders)
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
        # 09:30 v20 features (V7+cross). Falls back to v19 if v20 dir missing.
        v20_feats_path = V20_DIR / 'features_0930.txt'
        if v20_feats_path.exists():
            with open(v20_feats_path) as f:
                self.features_0930 = [line.strip() for line in f if line.strip()]
        else:
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
        # Load primary models per bucket. 09:30 prefers v20, others use v19.
        for bucket, (pattern, n_seeds) in self.MODEL_FILES.items():
            base_dir = V20_DIR if bucket == '09:30-10:00' else MODEL_DIR
            ensemble = []
            for s in range(n_seeds):
                mp = base_dir / pattern.format(s)
                if not mp.exists():
                    mp = MODEL_DIR / pattern.format(s)  # fall back to v19
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
        # Negative = pre-market (shouldn't be called — in_time_window guards this)
        # but be defensive: return out-of-window marker
        if minutes_from_open < 0:
            return 'pre_market'
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
        """Per-bucket thresholds — original v16 validated values.

        These came from training-time validation (not post-hoc tuning):
          09:30  tp1 P(reach +1%) >= 0.45
          10:00  Huber predicted PnL >= 0.10%
          10:45  tp1 P(reach +1%) >= 0.55
          11:30  tp1 P(reach +1%) >= 0.60
        """
        if minutes_from_open >= 120:       # 11:30-13:00 tp1
            return 0.60
        if minutes_from_open >= 75:        # 10:45-11:30 tp1
            return 0.55
        if minutes_from_open >= 30:        # 10:00-10:45 Huber
            return 0.10
        return 0.45                        # 09:30 tp1

    def can_reach_75(self, minutes_from_open: int) -> bool:
        # Tradeable window: 0 (09:30) to 210 (13:00)
        # Pre-market (< 0) and 13:00+ (>= 210) both skip
        return 0 <= minutes_from_open < 210


_SCORER_INSTANCE = None


def get_scorer() -> MLScorer:
    global _SCORER_INSTANCE
    if _SCORER_INSTANCE is None:
        _SCORER_INSTANCE = MLScorer()
    return _SCORER_INSTANCE
