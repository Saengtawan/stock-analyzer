"""
ML Scorer v21 — canonical features (no lookahead bias).

v21 fixes silent train/inference mismatches present in v20.1:
  - vol_ratio: today_vol / (30d_avg_daily × fraction_of_day_elapsed)
  - vol_accel: last3 vs prev3 (matches live's logic)
  - range_exp: range_pct / 10d_avg_range (per-stock adaptive)
  - consol: 5 bars (matches live)

24-month walk-forward HONEST validation:
  09:30  tp1  56 base + 5 interactions  thr 0.45  WR=63.6%  avg=+1.49%
  10:00  Huber+Q25+Conf v19              thr 0.10  WR=66.6%  avg=+0.93%
  10:45  tp1  56 base                    thr 0.25  WR=66.7%  avg=+0.70%
  11:30  tp1  56 base                    thr 0.22  WR=58.9%  avg=+0.39%

v20.1 reported 71% WR was INFLATED by lookahead bias. v21 = honest WR.
Live ml_filter.py must compute features the same way (see ml_filter.py audit).
"""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb

MODEL_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v19'
V21_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v21'  # tp1 buckets
V20_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v20'  # rollback ref


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
        # 09:30 v21 features (56 base + 5 interactions = 61).
        v21_0930 = V21_DIR / 'features_0930.txt'
        if v21_0930.exists():
            with open(v21_0930) as f:
                self.features_0930 = [line.strip() for line in f if line.strip()]
        else:
            v19_0930 = MODEL_DIR / 'features_0930.txt'
            if v19_0930.exists():
                with open(v19_0930) as f:
                    self.features_0930 = [line.strip() for line in f if line.strip()]
            else:
                self.features_0930 = self.features_v7
        # 10:45 / 11:30 v21 features (56 base, no interactions).
        v21_late = V21_DIR / 'features_late.txt'
        if v21_late.exists():
            with open(v21_late) as f:
                self.features_late = [line.strip() for line in f if line.strip()]
        else:
            self.features_late = self.features_0930
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

    # Buckets that use v21 models (tp1 classifier, canonical features, no lookahead).
    # 10:00-10:45 (Huber) stays on v19.
    V21_BUCKETS = {'09:30-10:00', '10:45-11:30', '11:30-13:00'}

    def _load_models(self):
        # Load primary models per bucket. v21 for tp1 buckets, v19 elsewhere.
        for bucket, (pattern, n_seeds) in self.MODEL_FILES.items():
            base_dir = V21_DIR if bucket in self.V21_BUCKETS else MODEL_DIR
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

        # 09:30 uses features_0930 (56 base + 5 interactions).
        # 10:45 / 11:30 use features_late (56 base, interactions hurt these buckets).
        # 10:00 (Huber) uses v9 features.
        if bucket == '09:30-10:00':
            feat_list = self.features_0930
        elif bucket in self.V21_BUCKETS:
            feat_list = self.features_late
        else:
            feat_list = self.features_v9
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
        """Per-bucket thresholds — v21 canonical (no lookahead).

        v21 thresholds re-tuned because canonical vol_ratio shifted prediction range.
        24-month walk-forward HONEST validation:
          09:30  tp1 v21  P(reach +1%) >= 0.45  WR=63.6%  avg=+1.49%
          10:00  Huber v19  predicted PnL >= 0.10  WR=66.6%  avg=+0.93%
          10:45  tp1 v21  P(reach +1%) >= 0.25  WR=66.7%  avg=+0.70%
          11:30  tp1 v21  P(reach +1%) >= 0.22  WR=58.9%  avg=+0.39%

        v20.1 reported 71% was inflated by lookahead bias — not real.
        """
        if minutes_from_open >= 120:       # 11:30-13:00 tp1 v21
            return 0.22
        if minutes_from_open >= 75:        # 10:45-11:30 tp1 v21
            return 0.25
        if minutes_from_open >= 30:        # 10:00-10:45 Huber v19
            return 0.10
        return 0.45                        # 09:30 tp1 v21

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
