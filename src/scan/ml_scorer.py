"""
ML Scorer v23 — Two-stage architecture: tp1 win + loss reject.

Stage 1 (tp1 win, MIN-seed):
  - 5-seed bagging classifier predicts P(reach +1%)
  - MIN of seeds = "all seeds agree" filter

Stage 2 (loss reject, MAX-seed):
  - Separate 5-seed classifier predicts P(loss > 1%)
  - MAX of seeds = "ANY seed says big loss" → reject pick

Pick passes only if: win_min >= threshold AND loss_max <= LOSS_THRESHOLDS[bucket].

24-month walk-forward HONEST validation (v23 vs v22.1):
  09:30  win>=0.42 + loss<=0.35  WR=65.6%  avg=+1.60%  (vs 63.2%/+1.40%, +2.4pp)
  10:00  win>=0.30 + loss<=0.45  WR=67.5%  avg=+1.64%  (vs 66.6%/+1.45%, +0.9pp)
  10:45  win>=0.22 + loss<=0.30  WR=70.3%  avg=+0.67%  (vs 68.7%/+0.60%, +1.6pp)
  11:30  win>=0.18 + loss<=0.35  WR=61.3%  avg=+0.51%  (vs 61.0%/+0.48%, marginal)

Key features:
  - bagging_fraction=0.8 + feature_fraction=0.8 → real ensemble diversity
  - MIN(win) AND MAX(loss) — "all agree win, none warn loss" filter
  - Canonical features (no lookahead) — backtest = live
  - label_decay for tp1, label_fixed3 for loss model
  - ETF excluded from training universe (matches live)
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

    # Primary tp1 model per bucket — uniform v22 architecture (tp1 + min-seed).
    MODEL_FILES = {
        '09:30-10:00': ('lgb_tp1_0930_1000_seed{}.txt', 5),
        '10:00-10:45': ('lgb_tp1_1000_1045_seed{}.txt', 5),
        '10:45-11:30': ('lgb_tp1_1045_1130_seed{}.txt', 5),
        '11:30-13:00': ('lgb_tp1_1130_1300_seed{}.txt', 5),
    }

    # v23: Loss reject models per bucket — predict P(label_fixed3 <= -1%).
    # Pick rejected if MAX of 5 seed loss preds > LOSS_THRESHOLDS[bucket].
    LOSS_MODEL_FILES = {
        '09:30-10:00': ('lgb_loss_0930_1000_seed{}.txt', 5),
        '10:00-10:45': ('lgb_loss_1000_1045_seed{}.txt', 5),
        '10:45-11:30': ('lgb_loss_1045_1130_seed{}.txt', 5),
        '11:30-13:00': ('lgb_loss_1130_1300_seed{}.txt', 5),
    }

    LOSS_THRESHOLDS = {
        '09:30-10:00': 0.35,
        '10:00-10:45': 0.45,
        '10:45-11:30': 0.30,
        '11:30-13:00': 0.35,
    }

    def __init__(self):
        self.models = {}
        self.loss_models = {}
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
        # Load tp1 win models.
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
        # Load loss reject models (v23).
        for bucket, (pattern, n_seeds) in self.LOSS_MODEL_FILES.items():
            ensemble = []
            for s in range(n_seeds):
                mp = V22_DIR / pattern.format(s)
                if mp.exists():
                    ensemble.append(lgb.Booster(model_file=str(mp)))
            if ensemble:
                self.loss_models[bucket] = ensemble

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
        """Score stock with v23 two-stage architecture.

        Stage 1 (tp1 win): MIN of 5 seeds — picks where ALL agree on win.
        Stage 2 (loss reject): MAX of 5 seeds — reject if ANY seed says big loss.

        Returns 0.0 if rejected by loss model. Otherwise tp1 min-seed score.
        """
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.models.get(bucket)
        if not ensemble:
            return 0.0

        feat_list = self.features_0930 if bucket == '09:30-10:00' else self.features_late
        row = [features.get(f, 0.0) for f in feat_list]
        arr = np.array([row], dtype=float)
        preds = [float(m.predict(arr)[0]) for m in ensemble]
        win_score = min(preds)  # MIN of 5 seeds — filters lucky outliers

        # v23 loss reject: skip if any seed predicts high loss probability
        loss_ensemble = self.loss_models.get(bucket)
        loss_thr = self.LOSS_THRESHOLDS.get(bucket)
        if loss_ensemble and loss_thr is not None:
            loss_preds = [float(m.predict(arr)[0]) for m in loss_ensemble]
            if max(loss_preds) > loss_thr:
                return 0.0  # rejected — high loss probability
        return win_score

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
        """Per-bucket tp1 win thresholds — v23 (two-stage architecture).

        Pick passes if: win_min >= threshold AND loss_max <= LOSS_THRESHOLDS.

        24-month walk-forward (v23 with loss reject):
          09:30  win>=0.42 + loss<=0.35  WR=65.6%  avg=+1.60%
          10:00  win>=0.30 + loss<=0.45  WR=67.5%  avg=+1.64%
          10:45  win>=0.22 + loss<=0.30  WR=70.3%  avg=+0.67%
          11:30  win>=0.18 + loss<=0.35  WR=61.3%  avg=+0.51%
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
