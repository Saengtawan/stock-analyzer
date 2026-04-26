"""
ML Scorer v22 — UNIFIED architecture across all 4 buckets.

Single design: tp1 binary classifier (5-seed bagging ensemble) + MIN-seed selection.
Replaces v19 Huber+Q25+Conf complex stack at 10:00 (was different architecture).

24-month walk-forward HONEST validation:
  09:30  min-seed ≥ 0.42  WR=65.3%  avg=+1.57%
  10:00  min-seed ≥ 0.30  WR=69.5%  avg=+1.65%   (was Huber: 66.6%/+0.93%, +2.9pp)
  10:45  min-seed ≥ 0.22  WR=68.4%  avg=+0.64%
  11:30  min-seed ≥ 0.18  WR=60.8%  avg=+0.45%

Key v22 features:
  - bagging_fraction=0.8 + feature_fraction=0.8 → real ensemble diversity
  - MIN of 5 seeds → "all seeds agree" filter, removes lucky outliers
  - Canonical features (no lookahead) — backtest = live
"""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb

MODEL_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v19'
V22_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v22'  # tp1 buckets


class MLScorer:
    BUCKETS = {
        (0, 30):    '09:30-10:00',
        (30, 75):   '10:00-10:45',
        (75, 120):  '10:45-11:30',
        (120, 210): '11:30-13:00',  # match feature_builder training ranges
        (210, 270): '13:00-14:00',
        (270, 390): '14:00-16:00',  # 14:00 + 120 min = 16:00
    }

    # Primary model per bucket — uniform v22 architecture (tp1 + min-seed).
    # All 4 buckets use same tp1 binary classifier with 5-seed bagging ensemble.
    MODEL_FILES = {
        '09:30-10:00': ('lgb_tp1_0930_1000_seed{}.txt', 5),
        '10:00-10:45': ('lgb_tp1_1000_1045_seed{}.txt', 5),
        '10:45-11:30': ('lgb_tp1_1045_1130_seed{}.txt', 5),
        '11:30-13:00': ('lgb_tp1_1130_1300_seed{}.txt', 5),
    }

    def __init__(self):
        self.models = {}
        self._load_features()
        self._load_models()

    def _load_features(self):
        v7_dir = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v7'
        with open(v7_dir / 'features.txt') as f:
            self.features_v7 = [line.strip() for line in f if line.strip()]
        with open(MODEL_DIR / 'features.txt') as f:
            self.features_v9 = [line.strip() for line in f if line.strip()]
        # 09:30 v22 features (56 base + 5 interactions = 61).
        v22_0930 = V22_DIR / 'features_0930.txt'
        if v22_0930.exists():
            with open(v22_0930) as f:
                self.features_0930 = [line.strip() for line in f if line.strip()]
        else:
            v19_0930 = MODEL_DIR / 'features_0930.txt'
            if v19_0930.exists():
                with open(v19_0930) as f:
                    self.features_0930 = [line.strip() for line in f if line.strip()]
            else:
                self.features_0930 = self.features_v7
        # 10:00 / 10:45 / 11:30 v22 features (56 base, no interactions).
        v22_late = V22_DIR / 'features_late.txt'
        if v22_late.exists():
            with open(v22_late) as f:
                self.features_late = [line.strip() for line in f if line.strip()]
        else:
            self.features_late = self.features_0930

    def _load_models(self):
        # Load tp1 models — uniform v22 architecture for all 4 buckets.
        for bucket, (pattern, n_seeds) in self.MODEL_FILES.items():
            ensemble = []
            for s in range(n_seeds):
                mp = V22_DIR / pattern.format(s)
                if not mp.exists():
                    mp = MODEL_DIR / pattern.format(s)  # fall back to v19
                if mp.exists():
                    ensemble.append(lgb.Booster(model_file=str(mp)))
            if ensemble:
                self.models[bucket] = ensemble

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
        """Score stock with bucket-appropriate model.

        Uniform v22 architecture: all 4 buckets use tp1 binary classifier
        with min-seed selection (worst seed agreement).
        """
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.models.get(bucket)
        if not ensemble:
            return 0.0

        # 09:30 uses features_0930 (56 base + 5 interactions).
        # 10:00 / 10:45 / 11:30 use features_late (56 base, no interactions).
        feat_list = self.features_0930 if bucket == '09:30-10:00' else self.features_late
        row = [features.get(f, 0.0) for f in feat_list]
        arr = np.array([row], dtype=float)
        preds = [float(m.predict(arr)[0]) for m in ensemble]
        return min(preds)  # MIN of 5 seeds — filters lucky outliers

    def score_q25(self, features: dict, minutes_from_open: int) -> float:
        """Deprecated in v22. Always returns 0.0 — kept for caller compat."""
        return 0.0

    def passes_q25_filter(self, features: dict, minutes_from_open: int) -> bool:
        """No Q25 in v22 (deprecated). Always passes — kept for caller compat."""
        return True

    def passes_confidence_filter(self, features: dict, minutes_from_open: int) -> bool:
        """No Conf gate in v22 (deprecated). Always passes — kept for caller compat."""
        return True

    def threshold_75(self, minutes_from_open: int) -> float:
        """Per-bucket thresholds — v22 (uniform tp1 + min-seed across all 4 buckets).

        Picks must have ALL 5 seeds confident (worst-case agreement), not just
        1 outlier. Validated 24-month walk-forward HONEST results:

          09:30  tp1 v22  min-seed >= 0.42  WR=65.3%  avg=+1.57%
          10:00  tp1 v22  min-seed >= 0.30  WR=69.5%  avg=+1.65%
          10:45  tp1 v22  min-seed >= 0.22  WR=68.4%  avg=+0.64%
          11:30  tp1 v22  min-seed >= 0.18  WR=60.8%  avg=+0.45%

        v22 at 10:00 replaces v19 Huber+Q25+Conf complex stack —
        +2.9pp WR, +0.72pp avg, simpler architecture.
        """
        if minutes_from_open >= 120:       # 11:30-13:00
            return 0.18
        if minutes_from_open >= 75:        # 10:45-11:30
            return 0.22
        if minutes_from_open >= 30:        # 10:00-10:45
            return 0.30
        return 0.42                        # 09:30-10:00

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
