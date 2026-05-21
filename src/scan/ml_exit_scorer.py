"""ml_exit_scorer.py — Exit ML inference module (Step 32 candidate).

Separate from ml_scorer.py (entry). Loads trained Exit ML models and provides:
- ExitScorer class with predict(position, current_bars, market_state)
- Returns hold_prob (P(EOD > current_price))
- shouldExit(position, ...) -> bool with config

Usage in engine:
    from src.scan.ml_exit_scorer import ExitScorer
    scorer = ExitScorer()
    every 5 min in position_exit_monitor:
        for pos in active_positions:
            if scorer.should_exit(pos, bars, market_state):
                place_sell_order(pos, reason='exit_ml')

Models loaded from: backtests/models_prod_exit/lgb_exit_Z4_seed{0-4}.txt
Config loaded from: config/exit_config.yaml

Default: Z4 only, threshold=0.35, min_hold_minutes=30
"""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb

PROJ = Path(__file__).resolve().parents[2]
EXIT_MODELS_DIR = PROJ / 'backtests' / 'models_prod_exit'
EXIT_CONFIG_PATH = PROJ / 'config' / 'exit_config.json'


class ExitScorer:
    """Per-zone Exit ML scorer (currently Z4 only).

    Features (in order, must match training):
      [72 entry-time pkl features] (from entry record)
      [16 post-entry features]:
        mins_since_entry, current_pnl_pct, hwm_gain_pct, drawdown_from_peak_pct,
        bars_since_peak, mins_to_close,
        gain_from_open_pct, vs_session_avg_pct, range_today_pct,
        last_5min_pct, last_15min_pct, last_30min_pct,
        entry_win_p, entry_pred_r, entry_mfo, atr_pct_14d
    """

    def __init__(self):
        self.config = self._load_config()
        self.models = {}  # {zone: [5 boosters]}
        for zone in self.config.get('active_zones', ['Z4']):
            try:
                self.models[zone] = [
                    lgb.Booster(model_file=str(EXIT_MODELS_DIR / f'lgb_exit_{zone}_seed{s}.txt'))
                    for s in range(5)
                ]
            except Exception as e:
                print(f"  ⚠️ ExitScorer: failed to load {zone} models: {e}")

    def _load_config(self):
        try:
            return json.loads(EXIT_CONFIG_PATH.read_text())
        except Exception:
            return {'enabled': False, 'active_zones': ['Z4'],
                    'exit_threshold': 0.35, 'min_hold_minutes': 30}

    @property
    def enabled(self):
        return self.config.get('enabled', False)

    def build_features(self, position, current_bars, market_state=None):
        """Build feature vector for a position at current time.

        Args:
            position: dict with keys:
                'sym', 'entry_em', 'entry_price', 'entry_pkl_feats' (72-dim np.array),
                'entry_win_p', 'entry_pred_r', 'entry_mfo', 'atr'
            current_bars: list of (em, o, h, l, c) for the day (full bars cache)
            market_state: optional dict (currently unused, placeholder for future)

        Returns:
            np.ndarray of shape (88,) or None if insufficient data.
        """
        session_bars = [b for b in current_bars if b[0] >= 570]
        if not session_bars: return None
        day_open = next((b[1] for b in session_bars if b[0] == 570 and b[1] and b[1] > 0), None)
        if day_open is None: return None
        # Determine current em
        last = session_bars[-1]
        current_em = last[0]
        current_c = last[4]
        if current_c is None or current_c <= 0: return None
        entry_em = position['entry_em']
        entry_price = position['entry_price']
        mins_since_entry = current_em - entry_em
        if mins_since_entry < 5: return None  # too early to evaluate
        mins_to_close = 960 - current_em
        if mins_to_close < 5: return None
        # Walk session, track peak
        peak = entry_price; last_peak_em = entry_em
        session_history = [(em, c, h, l) for em, o, h, l, c in session_bars if c and c > 0]
        for em, c, h, l in session_history:
            if em <= entry_em: continue
            if em > current_em: break
            if h and h > peak: peak = h; last_peak_em = em
        # Compute features
        current_pnl_pct = (current_c - entry_price) / entry_price * 100
        hwm_gain_pct = (peak - entry_price) / entry_price * 100
        drawdown_pct = (current_c - peak) / peak * 100
        bars_since_peak = current_em - last_peak_em
        gain_from_open = (current_c - day_open) / day_open * 100
        sess_closes = [c_ for em_, c_, _, _ in session_history if em_ <= current_em]
        sess_avg = np.mean(sess_closes) if sess_closes else current_c
        vs_session_avg = (current_c - sess_avg) / sess_avg * 100 if sess_avg else 0
        highs = [h_ for em_, c_, h_, l_ in session_history if em_ <= current_em and h_ and h_ > 0]
        lows = [l_ for em_, c_, h_, l_ in session_history if em_ <= current_em and l_ and l_ > 0]
        range_today_pct = (max(highs) - min(lows)) / day_open * 100 if highs and lows else 0

        def price_at(target_em):
            for em_, c_, h_, l_ in session_history:
                if em_ == target_em: return c_
            return None
        c5, c15, c30 = price_at(current_em - 5), price_at(current_em - 15), price_at(current_em - 30)
        last_5min = (current_c - c5) / c5 * 100 if c5 else 0
        last_15min = (current_c - c15) / c15 * 100 if c15 else 0
        last_30min = (current_c - c30) / c30 * 100 if c30 else 0
        post = np.array([
            mins_since_entry, current_pnl_pct, hwm_gain_pct, drawdown_pct,
            bars_since_peak, mins_to_close,
            gain_from_open, vs_session_avg, range_today_pct,
            last_5min, last_15min, last_30min,
            position['entry_win_p'], position['entry_pred_r'],
            position['entry_mfo'], position['atr'],
        ])
        return np.concatenate([position['entry_pkl_feats'], post])

    def predict_hold_prob(self, zone, position, current_bars, market_state=None):
        """Predict P(EOD > current_price). Returns 1.0 if no model or features unavailable."""
        if zone not in self.models: return 1.0
        X = self.build_features(position, current_bars, market_state)
        if X is None: return 1.0
        X = X.reshape(1, -1)
        return float(np.mean([m.predict(X) for m in self.models[zone]]))

    def should_exit(self, zone, position, current_bars, market_state=None):
        """Decision: should we exit this position now?"""
        if not self.enabled: return False
        if zone not in self.config.get('active_zones', []): return False
        # Min hold check
        last_em = current_bars[-1][0] if current_bars else 0
        if last_em - position['entry_em'] < self.config.get('min_hold_minutes', 30):
            return False
        hold_prob = self.predict_hold_prob(zone, position, current_bars, market_state)
        return hold_prob < self.config.get('exit_threshold', 0.35)


_INSTANCE = None
def get_exit_scorer():
    global _INSTANCE
    if _INSTANCE is None: _INSTANCE = ExitScorer()
    return _INSTANCE
