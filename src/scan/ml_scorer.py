"""
ML Scorer v27 — Multi-architecture: tabular + multi-timeframe + Tech routing.

Architecture (v27 selective deployment based on validation):
  09:30  Tech sector  → Tech-specialized model (v25 routing)
         Other sector → unified model
         Hard rule: mom20d ≤ 20
         mfo=5 (09:35 bar) threshold = 0.40 (looser, v26)

  10:00  ALL stocks   → multi-timeframe model (v27, +6.2pp WR! 🎯)
         Hard rule: sector_etf ≥ -0.3%

  10:45  ALL stocks   → unified model (multi-tf hurts here)
         Hard rule: mom20d ≤ 20

  11:30  ALL stocks   → multi-timeframe model (v27, +1.6pp WR)
         No hard rule

24-month walk-forward HONEST validation (v27):
  09:30  Tech-routed + mfo-tuned       WR≈68.5%  avg=+1.55%
  10:00  multi-tf model                WR≈73.7%  avg=+1.79%  🎯 OVER 70%!
  10:45  unified                       WR=70.3%  avg=+0.67%  🎯 (already)
  11:30  multi-tf model                WR=62.9%  avg=+0.45%

Avg WR: ~68.9% (vs v26 67.6%, +1.3pp)
Best buckets: 10:00 = 73.7%, 10:45 = 70.3%
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

    # v27: Multi-timeframe models (10:00 + 11:30 only — validated to help these buckets).
    # 09:30 not enough bars for higher TFs; 10:45 multi-tf hurt. Selective deploy.
    TF_BUCKETS = {'10:00-10:45', '11:30-13:00'}
    TF_MODEL_FILES = {
        '10:00-10:45': ('lgb_tp1_tf_1000_1045_seed{}.txt', 5),
        '11:30-13:00': ('lgb_tp1_tf_1130_1300_seed{}.txt', 5),
    }
    TF_LOSS_FILES = {
        '10:00-10:45': ('lgb_loss_tf_1000_1045_seed{}.txt', 5),
        '11:30-13:00': ('lgb_loss_tf_1130_1300_seed{}.txt', 5),
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
        self.tech_models_0930 = []   # v25: Tech-specialized 09:30
        self.tech_loss_0930 = []     # v25: Tech-specialized loss 09:30
        self.tf_models = {}          # v27: Multi-timeframe models per bucket
        self.tf_loss_models = {}     # v27: Multi-timeframe loss models per bucket
        self.features_late_tf = []   # v27: Features list with multi-tf (71)
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
        # v27: features with multi-timeframe (71 features for 10:00 + 11:30)
        v27_late_tf = V22_DIR / 'features_late_tf.txt'
        if v27_late_tf.exists():
            with open(v27_late_tf) as f:
                self.features_late_tf = [line.strip() for line in f if line.strip()]
        else:
            self.features_late_tf = self.features_late

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
        # v27: Load multi-timeframe models for 10:00 + 11:30 buckets.
        for bucket, (pattern, n_seeds) in self.TF_MODEL_FILES.items():
            ensemble = []
            for s in range(n_seeds):
                mp = V22_DIR / pattern.format(s)
                if mp.exists():
                    ensemble.append(lgb.Booster(model_file=str(mp)))
            if ensemble:
                self.tf_models[bucket] = ensemble
        for bucket, (pattern, n_seeds) in self.TF_LOSS_FILES.items():
            ensemble = []
            for s in range(n_seeds):
                mp = V22_DIR / pattern.format(s)
                if mp.exists():
                    ensemble.append(lgb.Booster(model_file=str(mp)))
            if ensemble:
                self.tf_loss_models[bucket] = ensemble

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
        """Score stock with v27 architecture.

        Routing logic:
        - Tech sectors at 09:30 → Tech-specialized model (v25)
        - 10:00 + 11:30 buckets → multi-timeframe models (v27, +6.2pp at 10:00!)
        - All others → unified models (v22)
        """
        bucket = self.get_bucket(minutes_from_open)
        ensemble = self.models.get(bucket)
        if not ensemble:
            return 0.0

        # v25: Tech routing at 09:30
        is_tech_0930 = (bucket == '09:30-10:00' and
                        sector in self.TECH_SECTORS and
                        len(self.tech_models_0930) == 5)
        # v27: Multi-tf routing at 10:00 + 11:30 (validated to help)
        use_tf = (bucket in self.TF_BUCKETS and
                  bucket in self.tf_models and
                  len(self.tf_models[bucket]) == 5)

        # Pick feature list + ensembles
        if is_tech_0930:
            feat_list = self.features_0930
            tp1_ensemble = self.tech_models_0930
            loss_ensemble = self.tech_loss_0930 or self.loss_models.get(bucket)
        elif use_tf:
            feat_list = self.features_late_tf
            tp1_ensemble = self.tf_models[bucket]
            loss_ensemble = self.tf_loss_models.get(bucket) or self.loss_models.get(bucket)
        elif bucket == '09:30-10:00':
            feat_list = self.features_0930
            tp1_ensemble = ensemble
            loss_ensemble = self.loss_models.get(bucket)
        else:
            feat_list = self.features_late
            tp1_ensemble = ensemble
            loss_ensemble = self.loss_models.get(bucket)

        row = [features.get(f, 0.0) for f in feat_list]
        arr = np.array([row], dtype=float)
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
        """Per-bucket tp1 win thresholds — v26 (per-mfo at 09:30).

        Pick passes if: win_min >= threshold AND loss_max <= LOSS_THRESHOLDS.

        v26: mfo=5 (09:35 bar) uses looser 0.40 (whipsaw zone but signal fresh).
        Validated: +0.5pp WR, +11% picks, +10% total profit at 09:30.

        24-month walk-forward (v26):
          09:35 (mfo=5) win>=0.40 + loss<=0.35  ← looser at first bar
          09:40+        win>=0.42 + loss<=0.35
          10:00         win>=0.30 + loss<=0.45  WR=67.5%
          10:45         win>=0.22 + loss<=0.30  WR=70.3%
          11:30         win>=0.18 + loss<=0.35  WR=61.3%
        """
        if minutes_from_open >= 120:       # 11:30-13:00
            return 0.18
        if minutes_from_open >= 75:        # 10:45-11:30
            return 0.22
        if minutes_from_open >= 30:        # 10:00-10:45
            return 0.30
        # 09:30 bucket: mfo=5 (09:35 bar) gets looser threshold (whipsaw zone)
        if minutes_from_open <= 5:
            return 0.40                    # 09:35 bar
        return 0.42                        # 09:40-09:55

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
