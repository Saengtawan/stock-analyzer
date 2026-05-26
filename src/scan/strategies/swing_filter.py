"""
swing_filter — Short-window swing ML strategy (v2.0).

Version: swing_v2.0 (deployed 2026-05-26)
Scan window: 15:55 ET (post-close) → 09:29 ET next day (pre-open)
Entry: market close → next day open
Hold: up to 7 days
Exit: pure hold — TP +2% if hit, else time stop 7d (NO SL)

Universe filter (v2.0): price≥$5, mcap≥$1B, ADV≥$10M (~936 symbols)
Label: "+2% touch AND no DD <-3% within 7 days" (L_touch_2_dd-3_in_7d)
Threshold: 0.75

Validated 2026-05-26 via 4-phase Funnel:
  F1 (6mo walk-forward):  WR 93%   / EV +1.78% / Worst -2.27% / Sharpe 12.97
  F2 (cross-regime):      Elevated regime only in test period
  F3 (TRUE OOS 75 days):  WR 100%  / EV +1.99% / Worst +1.48% / N=96
  F4 (smoke tests):       4/4 pass

Position management:
  - Max 5 concurrent positions
  - 5% of capital per position
  - Rank by ml_prob descending
  - Skip if already holding the symbol

v1.0 archived at backtests/models_swing_v1.0_2026-05-26/ (rejected — tail risk
-94% from GOEV bankruptcy. v2.0 universe filter + short window fixes this.)
"""
import json
import numpy as np
import pandas as pd
import lightgbm as lgb
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base import BaseStrategy, Pick, ScanResult

MODELS_DIR = Path(__file__).parent.parent.parent.parent / 'backtests' / 'models_swing'
CONFIG_PATH = MODELS_DIR / 'swing_config.json'


class SwingFilter(BaseStrategy):
    """Swing ML — multi-day hold, daily-bar features, 5-seed ensemble."""

    name = "swing_filter"
    description = "Swing ML v2.0 — +2% in 7d w/ DD<-3%, WR 100% OOS / Sharpe 12.97"
    expected_wr = 0.93
    expected_ev = 1.78 / 100
    # Swing strategy uses daily EOD features. Valid window = post-close to pre-next-open.
    # ET 15:55 (today close) → ET 09:29 next day (pre-open). Crosses midnight, see in_time_window().
    time_start = "15:55"
    time_end = "09:29"
    version = "2.0"

    def in_time_window(self) -> bool:
        """Valid: AFTER close (15:55+) OR BEFORE next open (00:00-09:29)."""
        now = self.time_et_str()
        # Post-close today
        if now >= "15:55":
            return True
        # Pre-open next day (still using yesterday's EOD data)
        if now <= "09:29":
            return True
        return False

    def __init__(self):
        self._models = None
        self._config = None
        self._feature_cols = None

    def _ensure_loaded(self):
        if self._models is not None:
            return
        if not CONFIG_PATH.exists():
            raise FileNotFoundError(f"swing_config.json not found at {CONFIG_PATH}")
        self._config = json.load(open(CONFIG_PATH))
        self._feature_cols = self._config['feature_cols']
        self._models = []
        # Try v2 models first, fall back to v1 (legacy)
        version_tag = 'v2' if self._config.get('strategy_version', '').startswith('swing_v2') else ''
        for seed in range(5):
            fname = f'lgb_swing_v2_seed{seed}.txt' if version_tag == 'v2' else f'lgb_swing_seed{seed}.txt'
            mp = MODELS_DIR / fname
            if mp.exists():
                self._models.append(lgb.Booster(model_file=str(mp)))
        if not self._models:
            raise FileNotFoundError(f"No swing models found ({version_tag}) in {MODELS_DIR}")

    def _predict(self, features: dict) -> float:
        """Ensemble predict for one symbol."""
        arr = np.array([[features.get(f, -999.0) for f in self._feature_cols]])
        probs = [m.predict(arr)[0] for m in self._models]
        return float(np.mean(probs))

    def scan(self) -> ScanResult:
        if not self.in_time_window():
            return self.out_of_window()

        try:
            self._ensure_loaded()
        except Exception as e:
            return ScanResult(
                strategy=self.name,
                timestamp_et=self.time_et_str(),
                status='skipped_gate',
                reason=f"model_load_failed: {e}",
            )

        # Build today's features for all universe stocks
        try:
            from ..swing_features import build_today_features
            features_df = build_today_features()
            if len(features_df) == 0:
                return self.no_picks("no_features_today")
        except Exception as e:
            return ScanResult(
                strategy=self.name,
                timestamp_et=self.time_et_str(),
                status='skipped_gate',
                reason=f"feature_build_failed: {e}",
            )

        # Score all
        threshold = self._config['threshold']
        tp_pct = self._config['exit_rules']['tp_pct']
        sl_pct = self._config['exit_rules']['sl_pct']
        time_stop = self._config['exit_rules']['time_stop_days']
        max_positions = self._config['position_sizing']['max_concurrent']

        picks = []
        for _, row in features_df.iterrows():
            feat_dict = {c: row[c] if c in row and not pd.isna(row[c]) else -999.0
                         for c in self._feature_cols}
            prob = self._predict(feat_dict)
            if prob < threshold:
                continue
            entry = float(row['close'])
            tp_price = entry * (1 + tp_pct / 100)
            picks.append(Pick(
                symbol=row['symbol'],
                entry=entry,
                sl_price=None,
                tp_price=tp_price,
                trail_pct=None,
                reason=f"swing_ml prob={prob:.3f} TP +{tp_pct}% time={time_stop}d",
                score=int(prob * 100),
                extra={
                    'ml_prob': prob,
                    'threshold': threshold,
                    'time_stop_days': time_stop,
                    'tp_pct': tp_pct,
                    'sl_pct': sl_pct,
                    'strategy_version': self._config['strategy_version'],
                },
            ))

        # Rank by prob desc, take top max_positions
        picks.sort(key=lambda p: -p.extra['ml_prob'])
        picks = picks[:max_positions]

        if not picks:
            return self.no_picks(f"no_picks above threshold {threshold}")

        return ScanResult(
            strategy=self.name,
            timestamp_et=self.time_et_str(),
            status='active',
            reason=f"swing_filter {self.version} | {len(picks)} picks @ threshold {threshold}",
            picks=picks,
            regime="",
            metadata={
                'strategy_version': self._config['strategy_version'],
                'expected_wr': self.expected_wr,
                'expected_ev': self.expected_ev,
            },
        )
