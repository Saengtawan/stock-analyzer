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
V22_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v22'  # tp1 buckets (28m current)
V22_49M_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v22_49m'  # 49m regime-mixed
V22_1M_DIR = Path(__file__).resolve().parents[2] / 'backtests' / 'models_prod_v22_1m'  # 1-min trained ensemble partner


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
        '10:00-10:45': 0.55,  # 2026-04-29: loosened 0.45→0.55. WF: WR 85.6→86.6%, total +312→+387%, WorstMo 69→75%.
        '10:45-11:30': 0.30,
        '11:30-13:00': 0.35,
    }

    # === MFO ZONE SCORING (NEW 2026-04-29) ===
    # Pure mfo-zone replaces bucket-based scoring. WF: 94.4% → 94.5% WR, +43% total, +4pp worst mo.
    # Zones: Z1 open vol, Z2 late open, Z3 chase, Z4 sweet/gold.
    USE_ZONES = True
    ZONES = [
        ('Z1', 0, 9),    # early open volatility
        ('Z2', 10, 29),  # late open settling
        ('Z3', 30, 44),  # chase zone
        ('Z4', 45, 75),  # sweet/gold zone
    ]
    # 2026-05-06: Fine-tuned on 1-min validation 500-sym (Task 4) + ensemble (A3).
    # Z2/Z3 from 0.75 → 0.50 (looser plateau), Z1/Z4 unchanged.
    # WF: WR 87.6% (=baseline), avg +2.27%, total +495%/yr (+95% over Task 4 alone).
    ZONE_THRESHOLDS = {
        # 2026-05-14: Per-zone optimized via Step 10 grid search.
        # Adaptive limit (Step 7) + buffer 1.0% achieves fill >80% per zone.
        # Win threshold tuned per zone to balance fill rate + WR.
        # WF (Nov 2025 - Apr 2026, monthly refit):
        #   Z1: fill 87%, WR 88%, +189%/6mo, worst -2.42%
        #   Z2: fill 88%, WR 91%, +189%/6mo, worst -1.93%
        #   Z3: fill 91%, WR 74%, +108%/6mo, worst -2.67%
        #   Z4: fill 92%, WR 66%, +102%/6mo, worst -1.62% (with dip filter 0.5%)
        'Z1': 0.75,  # 2026-05-29: 0.60→0.75. WF+live: <0.70 picks WR 22%; 0.70-0.75 = LITE/AMKR (-8.5%/-6.5%). 0.75 keeps WR 82%/worst -2.19%, total unchanged.
        'Z2': 0.75,  # 2026-05-29: uniform 0.75 (user). WF: WR 85%/+155%/worst -3.08% (vs 0.65: 86%/+156%) — near-identical, passes floor.
        'Z3': 0.75,  # 2026-05-29: uniform 0.75 (user). WF: WR 77%/+150%/worst -3.34% (vs 0.50: 74%/+150%) — WR +3pp, passes floor.
        'Z4': 0.75,  # 2026-05-29: uniform 0.75 (user). WF flat for Z4: WR 82%/+212%/worst -3.10%; win_p doesn't bind (Z4_DIP + loss_thr govern).
    }
    # 2026-05-14: Z4 specific filter — only pick if ML predicts dip >= 0.5%
    Z4_DIP_FILTER = 0.005  # 0.5% minimum predicted dip
    # 2026-05-14: Adaptive limit buffer (above ML predicted low)
    ADAPTIVE_LIMIT_BUFFER = 0.010  # 1.0% above predicted low (fallback)
    # 2026-05-14 Step 12: Per-zone ATR-adaptive buffer.
    # buffer = base_buf + atr_coef × atr_pct_14d
    # WF (Nov 2025 - Apr 2026): Z1 +211%, Z2 +224%, Z3 +125%, Z4 +102%, Combined +662%
    ZONE_LIMIT_CONFIG = {
        'Z1': {'base_buf': 0.005, 'atr_coef': 0.0020},  # fill 93%, WR 89%, +211%, -2.85%
        'Z2': {'base_buf': 0.005, 'atr_coef': 0.0015},  # fill 94%, WR 90%, +224%, -1.77%
        'Z3': {'base_buf': 0.005, 'atr_coef': 0.0015},  # fill 95%, WR 75%, +125%, -2.55%
        'Z4': {'base_buf': 0.010, 'atr_coef': 0.0000},  # fill 92%, WR 66%, +102%, -1.62% (keep Step 10)
    }
    # 2026-05-06: Loss thresholds tuned (Task 3 + Task 4 sweep).
    ZONE_LOSS_THR = {
        'Z1': 0.40,  # was 0.35 — slightly looser (Task 3 best)
        'Z2': 0.20,  # was 0.35 — much tighter (Task 3 best)
        'Z3': 0.40,  # was 0.55 — tighter (Task 3 best)
        'Z4': 0.50,  # was 0.55 — tighter (Task 3 best)
    }
    # 2026-05-14 Step 17: Per-zone Hard Stop Loss (% from fill_price).
    # Z1/Z2/Z3 keep pure hold to EOD (worst already < -3%). Z4 adds -3% SL
    # because worst-trade RIVN 2025-12-12 went to -4.68% without SL.
    # WF (Nov 2025 - Apr 2026, refit monthly):
    #   Z4 pure:    WR 92%, +259%, worst -4.68%
    #   Z4 SL -3%:  WR 91%, +254%, worst -3.10%  ← deployed
    # Trade-off: lose -5% total to cap tail from -4.68%→-3.10%.
    ZONE_HARD_SL = {
        'Z4': 0.03,  # 3% from fill_price
    }

    # === MoE soft (Mixture of Experts) — 2026-05-04 ===
    # Combine 28m specialist (current production) + 49m regime-mixed.
    # Weight via regime_weight (sigmoid on SPY vs 50-day MA).
    # WF: WR 99.6%→100% (12/12 months), avg +3.16%→+3.17%, total -$19/yr (insurance premium).
    # 2026-05-06: Re-enabled for Triple Blend (MoE 5m + 1m_profit ensemble).
    #   Bull: regime_weight ≈0.95 → mostly 28m (current)
    #   Bear: regime_weight drops → 49m takes over (insurance)
    # 2026-05-13 deploy: Disabled MoE/1m ensemble because new feature set (77 features for Z1/Z2,
    # 72 for Z3/Z4) doesn't match legacy 49m and 1m models (61-feat). WF validation used 28m only.
    USE_MOE = False

    USE_ENSEMBLE_1M = False
    ENSEMBLE_W_5M = 1.0   # weight for MoE-blended 5m output (irrelevant when 1m off)
    ENSEMBLE_W_1M = 0.0   # weight for 1m_profit model (disabled)

    def __init__(self):
        self.models = {}
        self.loss_models = {}
        self.tech_models_0930 = []   # v25: Tech-specialized 09:30
        self.tech_loss_0930 = []     # v25: Tech-specialized loss 09:30
        self.tf_models = {}          # v27: Multi-timeframe models per bucket
        self.tf_loss_models = {}     # v27: Multi-timeframe loss models per bucket
        self.features_late_tf = []   # v27: Features list with multi-tf (71)
        # NEW: zone-based models (overrides bucket if USE_ZONES=True)
        self.zone_tp1_models = {}    # zone_name → 5 boosters (28m specialist)
        self.zone_loss_models = {}   # zone_name → 5 boosters
        self.zone_features = {}      # zone_name → feature list
        # MoE: 49m expert models
        self.zone_tp1_models_49m = {}
        self.zone_loss_models_49m = {}
        # 1m ensemble partner
        self.zone_tp1_models_1m = {}
        self.zone_loss_models_1m = {}
        # 2026-05-14: Adaptive limit models (predicts intraday_low / scan_price ratio)
        self.zone_adaptlim_models = {}
        # Regime weight (set per-scan from outside)
        self.regime_weight = 1.0  # default = pure 28m
        self._load_features()
        self._load_models()
        if self.USE_ZONES:
            self._load_zone_models()
        if self.USE_MOE:
            self._load_moe_models()
        if self.USE_ENSEMBLE_1M:
            self._load_1m_models()
        self._load_adaptlim_models()

    def _load_moe_models(self):
        """Load 49m expert models for MoE soft."""
        for zname, lo, hi in self.ZONES:
            tp1_ens, loss_ens = [], []
            for s in range(5):
                tp1_path = V22_49M_DIR / f'lgb_tp1_{zname}_seed{s}.txt'
                loss_path = V22_49M_DIR / f'lgb_loss_{zname}_seed{s}.txt'
                if tp1_path.exists(): tp1_ens.append(lgb.Booster(model_file=str(tp1_path)))
                if loss_path.exists(): loss_ens.append(lgb.Booster(model_file=str(loss_path)))
            if len(tp1_ens) == 5 and len(loss_ens) == 5:
                self.zone_tp1_models_49m[zname] = tp1_ens
                self.zone_loss_models_49m[zname] = loss_ens
        if len(self.zone_tp1_models_49m) < 4:
            print(f"⚠️  MoE: Only {len(self.zone_tp1_models_49m)}/4 49m zone models loaded — disabling USE_MOE")
            self.USE_MOE = False

    def set_regime_weight(self, w: float):
        """Set MoE regime weight (0.0 = pure 49m, 1.0 = pure 28m). Called per-scan."""
        self.regime_weight = max(0.0, min(1.0, w))

    def _load_adaptlim_models(self):
        """Load adaptive limit models (Step 7) — predicts intraday low ratio per stock."""
        for zname, lo, hi in self.ZONES:
            ens = []
            for s in range(5):
                p = V22_DIR / f'lgb_adaptlim_{zname}_seed{s}.txt'
                if p.exists():
                    ens.append(lgb.Booster(model_file=str(p)))
            if len(ens) == 5:
                self.zone_adaptlim_models[zname] = ens

    def predict_adaptive_limit_ratio(self, features: dict, mfo: int, sector: str = '') -> float:
        """Predict intraday_low_ratio = min(low after scan) / scan_price for a candidate.
        Returns ratio in [0.90, 1.00] typically. Lower = bigger predicted dip.
        """
        if not self.USE_ZONES:
            return 1.0  # fallback: scan price
        zone = self.get_zone(mfo)
        if zone is None or zone not in self.zone_adaptlim_models:
            return 1.0
        feat_list = self.zone_features.get(zone, self.features_late)
        row = [features.get(f, 0.0) for f in feat_list]
        arr = np.array([row], dtype=float)
        preds = [float(m.predict(arr)[0]) for m in self.zone_adaptlim_models[zone]]
        return float(np.mean(preds))  # MEAN of 5 seeds for regression

    def _load_1m_models(self):
        """Load 1m-trained models for A3 ensemble."""
        for zname, lo, hi in self.ZONES:
            tp1_ens, loss_ens = [], []
            for s in range(5):
                tp1_path = V22_1M_DIR / f'lgb_tp1_{zname}_seed{s}.txt'
                loss_path = V22_1M_DIR / f'lgb_loss_{zname}_seed{s}.txt'
                if tp1_path.exists(): tp1_ens.append(lgb.Booster(model_file=str(tp1_path)))
                if loss_path.exists(): loss_ens.append(lgb.Booster(model_file=str(loss_path)))
            if len(tp1_ens) == 5 and len(loss_ens) == 5:
                self.zone_tp1_models_1m[zname] = tp1_ens
                self.zone_loss_models_1m[zname] = loss_ens
        if len(self.zone_tp1_models_1m) < 4:
            print(f"⚠️  1m ensemble: Only {len(self.zone_tp1_models_1m)}/4 zones loaded — disabling")
            self.USE_ENSEMBLE_1M = False

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

    def _load_zone_models(self):
        """Load mfo-zone models from production dir. Each zone has tp1+loss × 5 seeds."""
        for zname, lo, hi in self.ZONES:
            tp1_ensemble, loss_ensemble = [], []
            for s in range(5):
                tp1_path = V22_DIR / f'lgb_tp1_{zname}_seed{s}.txt'
                loss_path = V22_DIR / f'lgb_loss_{zname}_seed{s}.txt'
                if tp1_path.exists(): tp1_ensemble.append(lgb.Booster(model_file=str(tp1_path)))
                if loss_path.exists(): loss_ensemble.append(lgb.Booster(model_file=str(loss_path)))
            if len(tp1_ensemble) == 5 and len(loss_ensemble) == 5:
                self.zone_tp1_models[zname] = tp1_ensemble
                self.zone_loss_models[zname] = loss_ensemble
                # Use 09:30 features (with interactions) for Z1+Z2, late features for Z3+Z4
                feat_path = V22_DIR / f'features_zone_{zname.lower()}.txt'
                if feat_path.exists():
                    with open(feat_path) as f:
                        self.zone_features[zname] = [l.strip() for l in f if l.strip()]
                else:
                    self.zone_features[zname] = self.features_0930 if zname in ('Z1','Z2') else self.features_late
        if len(self.zone_tp1_models) < 4:
            print(f"⚠️  Only {len(self.zone_tp1_models)}/4 zone models loaded — disabling USE_ZONES")
            self.USE_ZONES = False

    def get_zone(self, minutes_from_open: int) -> str:
        """Return zone name for given mfo, or '' if outside tradeable range."""
        for zname, lo, hi in self.ZONES:
            if lo <= minutes_from_open <= hi:
                return zname
        return ''

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
        - USE_ZONES=True → route to mfo-zone model (NEW 2026-04-29, WF +43% total)
        - Else: bucket-based routing (Tech-specialized at 09:30, multi-tf at 10:00)
        """
        # NEW: zone-based routing (overrides bucket if zones loaded)
        if self.USE_ZONES:
            zone = self.get_zone(minutes_from_open)
            if zone and zone in self.zone_tp1_models:
                feat_list = self.zone_features.get(zone, self.features_late)
                row = [features.get(f, 0.0) for f in feat_list]
                arr = np.array([row], dtype=float)
                # 28m predictions (specialist)
                preds_28 = [float(m.predict(arr)[0]) for m in self.zone_tp1_models[zone]]
                win_28 = min(preds_28)
                loss_28 = max([float(m.predict(arr)[0]) for m in self.zone_loss_models[zone]])

                # MoE soft: blend with 49m expert if enabled
                if self.USE_MOE and zone in self.zone_tp1_models_49m:
                    preds_49 = [float(m.predict(arr)[0]) for m in self.zone_tp1_models_49m[zone]]
                    win_49 = min(preds_49)
                    loss_49 = max([float(m.predict(arr)[0]) for m in self.zone_loss_models_49m[zone]])
                    w = self.regime_weight
                    win_5m = w * win_28 + (1.0 - w) * win_49
                    loss_5m = w * loss_28 + (1.0 - w) * loss_49
                else:
                    win_5m = win_28
                    loss_5m = loss_28

                # 1m ensemble: blend 5m output with 1m model
                if self.USE_ENSEMBLE_1M and zone in self.zone_tp1_models_1m:
                    preds_1m = [float(m.predict(arr)[0]) for m in self.zone_tp1_models_1m[zone]]
                    win_1m = min(preds_1m)
                    loss_1m = max([float(m.predict(arr)[0]) for m in self.zone_loss_models_1m[zone]])
                    win_score = self.ENSEMBLE_W_5M * win_5m + self.ENSEMBLE_W_1M * win_1m
                    loss_score = self.ENSEMBLE_W_5M * loss_5m + self.ENSEMBLE_W_1M * loss_1m
                else:
                    win_score = win_5m
                    loss_score = loss_5m

                # Loss reject (using combined loss)
                loss_thr = self.ZONE_LOSS_THR.get(zone)
                if loss_thr is not None and loss_score > loss_thr:
                    return 0.0
                return win_score
            return 0.0  # mfo outside tradeable zones (76+) → skip

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
        # NEW 2026-04-29: zone-based thresholds (overrides bucket if USE_ZONES)
        if self.USE_ZONES:
            zone = self.get_zone(minutes_from_open)
            base = self.ZONE_THRESHOLDS.get(zone, 99.0)
            # 2026-06-09: per-zone threshold env override (reversible tune).
            # Z1/Z4 lowered 0.75->0.68: WF holdout +44 trade-days (126->170),
            # total +118%->+147%, Sharpe 5.27->4.45 (still excellent), WR 67->62.
            # Z2/Z3 kept 0.75 (lowering craters Sharpe 13.8->4.1 / 6.9->3.1).
            # Restore: unset H12A_THR_* envs -> back to ZONE_THRESHOLDS.
            import os as _os_thr
            _ov = _os_thr.environ.get(f'H12A_THR_{zone}')
            if _ov:
                try:
                    return float(_ov)
                except ValueError:
                    pass
            return base
        if minutes_from_open >= 120:       # 11:30-13:00
            return 0.18
        if minutes_from_open >= 75:        # 10:45-11:30
            return 0.28                    # 2026-04-29: raised 0.22→0.28. WF: bucket WR 67→89%, total WR +3.9pp, worstMo +5pp.
        if minutes_from_open >= 30:        # 10:00-10:45
            return 0.30
        # 09:30 bucket: mfo=5 (09:35 bar) gets looser threshold (whipsaw zone)
        if minutes_from_open <= 5:
            return 0.40                    # 09:35 bar
        return 0.42                        # 09:40-09:55

    def can_reach_75(self, minutes_from_open: int) -> bool:
        # Tradeable window: 09:30-10:45 (mfo 0-75)
        # NEW 2026-04-29 (zone-based): drop mfo 76+ entirely.
        # WF: zone scoring with mfo 0-75 only → 94.5% WR, +825% total over 6 months.
        # Pre-market (< 0) and 11:30+ (>= 76) both skip.
        if self.USE_ZONES:
            return 0 <= minutes_from_open <= 75
        return 0 <= minutes_from_open < 120


_SCORER_INSTANCE = None


def get_scorer() -> MLScorer:
    global _SCORER_INSTANCE
    if _SCORER_INSTANCE is None:
        _SCORER_INSTANCE = MLScorer()
    return _SCORER_INSTANCE
