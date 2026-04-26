"""
ML Scorer v25 — Two-stage ML + hard rules + Tech-specialized 09:30.

Architecture per bucket:
  Stage 1: tp1 win model (MIN-seed of 5 bagging seeds)
           v25 ADDITION: Tech sector at 09:30 → Tech-specialized model
  Stage 2: loss reject model (MAX-seed of 5 bagging seeds)
  Stage 3: per-bucket hard rules (in ml_filter.py)

Hard rules (v24):
  09:30 — skip if mom20d > 20 (anti-extreme)
  10:00 — skip if sector_etf intra < -0.3% (sector strength)
  10:45 — skip if mom20d > 20
  11:30 — no rule

Tech specialization (v25, 09:30 only — validated):
  Tech sectors (Technology + Communication Services) use specialized model
  Validated +3.1pp WR vs unified at 09:30 (only bucket where this helps).
  Other sectors at 09:30 use unified model.

24-month walk-forward HONEST validation (v25 vs v24):
  09:30  WR≈68.7%  +3.1pp from Tech routing 🎯
  10:00  WR=68.8%  same as v24
  10:45  WR=72.2%  same as v24 (already >70%)
  11:30  WR=61.3%  same as v24

Avg WR projection: ~67.8% (vs v24 67.1%)
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

    # v23: Loss reject models per bucket.
    LOSS_MODEL_FILES = {
        '09:30-10:00': ('lgb_loss_0930_1000_seed{}.txt', 5),
        '10:00-10:45': ('lgb_loss_1000_1045_seed{}.txt', 5),
        '10:45-11:30': ('lgb_loss_1045_1130_seed{}.txt', 5),
        '11:30-13:00': ('lgb_loss_1130_1300_seed{}.txt', 5),
    }

    # v25: Tech-specialized 09:30 models (validated +3.1pp WR for Tech stocks).
    # Used at 09:30 only (other buckets validated to NOT benefit from specialization).
    TECH_MODEL_FILES_0930 = ('lgb_tp1_tech_0930_1000_seed{}.txt', 5)
    TECH_LOSS_FILES_0930 = ('lgb_loss_tech_0930_1000_seed{}.txt', 5)
    TECH_SECTORS = {'Technology', 'Communication Services'}

    LOSS_THRESHOLDS = {
        '09:30-10:00': 0.35,
        '10:00-10:45': 0.45,
        '10:45-11:30': 0.30,
        '11:30-13:00': 0.35,
    }

    def __init__(self):
        self.models = {}
        self.loss_models = {}
        self.tech_models_0930 = []   # v25: Tech-specialized 09:30
        self.tech_loss_0930 = []     # v25: Tech-specialized loss 09:30
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
        # v25: Load Tech-specialized 09:30 models.
        pattern, n_seeds = self.TECH_MODEL_FILES_0930
        for s in range(n_seeds):
            mp = V22_DIR / pattern.format(s)
            if mp.exists():
                self.tech_models_0930.append(lgb.Booster(model_file=str(mp)))
        pattern, n_seeds = self.TECH_LOSS_FILES_0930
        for s in range(n_seeds):
            mp = V22_DIR / pattern.format(s)
            if mp.exists():
                self.tech_loss_0930.append(lgb.Booster(model_file=str(mp)))

    def get_bucket(self, minutes_from_open: int) -> str:
        # Negative = pre-market (shouldn't be called — in_time_window guards this)
        # but be defensive: return out-of-window marker
        if minutes_from_open < 0:
            return 'pre_market'
        for (lo, hi), name in self.BUCKETS.items():
            if lo <= minutes_from_open < hi:
                return name
        return '14:00-16:00'

    def score(self, features: dict, minutes_from_open: int, sector: str = '') -> float:
        """Score stock with v25 two-stage + Tech-specialized 09:30 routing.

        Stage 1 (tp1 win): MIN of 5 seeds — picks where ALL agree on win.
                          v25: Tech stocks at 09:30 use Tech-specialized model.
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

        # v25: route Tech stocks at 09:30 → Tech-specialized model (+3.1pp WR validated)
        is_tech_0930 = (bucket == '09:30-10:00' and
                        sector in self.TECH_SECTORS and
                        len(self.tech_models_0930) == 5)
        if is_tech_0930:
            tp1_ensemble = self.tech_models_0930
            loss_ensemble = self.tech_loss_0930 or self.loss_models.get(bucket)
        else:
            tp1_ensemble = ensemble
            loss_ensemble = self.loss_models.get(bucket)

        preds = [float(m.predict(arr)[0]) for m in tp1_ensemble]
        win_score = min(preds)

        # v23 loss reject
        loss_thr = self.LOSS_THRESHOLDS.get(bucket)
        if loss_ensemble and loss_thr is not None:
            loss_preds = [float(m.predict(arr)[0]) for m in loss_ensemble]
            if max(loss_preds) > loss_thr:
                return 0.0
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
