"""
swing_filter — Daily/swing trading ML strategy.

Scan window: 15:55-16:00 ET (after market close)
Entry: market close (next day open in practice)
Hold: variable, up to 30 days
Exit: rule-based (TP +5%, no SL, time stop 30d)

Validated 2026-05-26 via 5-phase Funnel:
  F1 (6mo monthly refit):   WR 94.9% / EV +3.83% / Sharpe 1.96
  F2 (cross-regime):        4/5 regimes positive (Crisis N=0 in test)
  F3 (TRUE OOS 75 days):    WR 95.0% / EV +4.17% / N=715
  F4 (smoke tests):         6/7 pass (1 false alarm)

Position management:
  - Max 5 concurrent positions
  - 5% of capital per position
  - Rank by ml_prob descending
  - Skip if already holding the symbol
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
    description = "Swing ML — +5% in 30d, validated WR 95% / EV +4.17%"
    expected_wr = 0.95
    expected_ev = 4.17 / 100
    time_start = "15:55"
    time_end = "16:00"
    version = "1.0"

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
        for seed in range(5):
            mp = MODELS_DIR / f'lgb_swing_seed{seed}.txt'
            if mp.exists():
                self._models.append(lgb.Booster(model_file=str(mp)))
        if not self._models:
            raise FileNotFoundError("No swing models found in " + str(MODELS_DIR))

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
