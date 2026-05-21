"""ml_exit_scorer.py — Hybrid Exit ML inference module (Step 32b).

Routes per zone:
  Z4 entries → Z4-only model (validated CRISIS-safe, Phase 3 3/3 PASS)
  Z1/Z2/Z3 entries → Multi-zone universal model (Phase 4 +2.9 to +6.3%)

Models loaded from: backtests/models_prod_exit/
  lgb_exit_Z4_seed{0-4}.txt      ← Z4-only (88 features)
  lgb_exit_MULTI_seed{0-4}.txt   ← Multi-zone (89 features = 88 + zone_idx)

Config loaded from: config/exit_config.json

Default: enabled=false, threshold=0.35, min_hold_minutes=30
"""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb

PROJ = Path(__file__).resolve().parents[2]
EXIT_MODELS_DIR = PROJ / 'backtests' / 'models_prod_exit'
EXIT_CONFIG_PATH = PROJ / 'config' / 'exit_config.json'

ZONE_IDX = {'Z1': 1, 'Z2': 2, 'Z3': 3, 'Z4': 4}

# Routing: which model set to use for each zone
DEFAULT_ROUTING = {'Z1': 'multi', 'Z2': 'multi', 'Z3': 'multi', 'Z4': 'z4'}


class ExitScorer:
    """Hybrid Exit ML scorer — routes per zone.

    Features (Z4 model): 88-dim
      [72 entry-time pkl features] + [16 post-entry features]
    Features (Multi-zone model): 89-dim
      [72 entry-time pkl features] + [16 post-entry] + [1 zone_idx]
    """

    def __init__(self):
        self.config = self._load_config()
        self.routing = self.config.get('model_routing', DEFAULT_ROUTING)
        self.models = {}  # {model_set: [5 boosters]}
        # Z4-only
        try:
            self.models['z4'] = [
                lgb.Booster(model_file=str(EXIT_MODELS_DIR / f'lgb_exit_Z4_seed{s}.txt'))
                for s in range(5)
            ]
        except Exception as e:
            print(f"  ⚠️ ExitScorer: failed to load Z4 models: {e}")
        # Multi-zone (optional — may not exist if not deployed yet)
        try:
            self.models['multi'] = [
                lgb.Booster(model_file=str(EXIT_MODELS_DIR / f'lgb_exit_MULTI_seed{s}.txt'))
                for s in range(5)
            ]
        except Exception:
            pass  # Multi-zone optional

    def _load_config(self):
        try:
            return json.loads(EXIT_CONFIG_PATH.read_text())
        except Exception:
            return {'enabled': False, 'active_zones': ['Z4'],
                    'exit_threshold': 0.35, 'min_hold_minutes': 30,
                    'model_routing': DEFAULT_ROUTING}

    @property
    def enabled(self):
        return self.config.get('enabled', False)

    def get_model_set_for_zone(self, zone):
        """Return model set name ('z4' or 'multi') based on routing."""
        return self.routing.get(zone, 'z4')

    def build_features(self, position, current_bars, market_state=None, zone='Z4'):
        """Build feature vector for a position at current time.

        For Z4 model: 88-dim
        For Multi-zone model: 89-dim (appends zone_idx)
        """
        session_bars = [b for b in current_bars if b[0] >= 570]
        if not session_bars: return None
        day_open = next((b[1] for b in session_bars if b[0] == 570 and b[1] and b[1] > 0), None)
        if day_open is None: return None
        last = session_bars[-1]
        current_em = last[0]
        current_c = last[4]
        if current_c is None or current_c <= 0: return None
        entry_em = position['entry_em']
        entry_price = position['entry_price']
        mins_since_entry = current_em - entry_em
        if mins_since_entry < 5: return None
        mins_to_close = 960 - current_em
        if mins_to_close < 5: return None
        peak = entry_price; last_peak_em = entry_em
        session_history = [(em, c, h, l) for em, o, h, l, c in session_bars if c and c > 0]
        for em, c, h, l in session_history:
            if em <= entry_em: continue
            if em > current_em: break
            if h and h > peak: peak = h; last_peak_em = em
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
        post = [mins_since_entry, current_pnl_pct, hwm_gain_pct, drawdown_pct,
                bars_since_peak, mins_to_close,
                gain_from_open, vs_session_avg, range_today_pct,
                last_5min, last_15min, last_30min,
                position['entry_win_p'], position['entry_pred_r'],
                position['entry_mfo'], position['atr']]
        # Multi-zone adds zone_idx as final feature
        model_set = self.get_model_set_for_zone(zone)
        if model_set == 'multi':
            post.append(ZONE_IDX.get(zone, 4))
        return np.concatenate([position['entry_pkl_feats'], np.array(post)])

    def predict_hold_prob(self, zone, position, current_bars, market_state=None):
        """Predict P(EOD > current_price). Routes by zone.

        Returns 1.0 (always hold) if model unavailable or features insufficient.
        """
        model_set = self.get_model_set_for_zone(zone)
        if model_set not in self.models:
            # Fallback: try Z4 if multi missing or vice versa
            if 'z4' in self.models: model_set = 'z4'
            else: return 1.0
        X = self.build_features(position, current_bars, market_state, zone=zone)
        if X is None: return 1.0
        X = X.reshape(1, -1)
        return float(np.mean([m.predict(X) for m in self.models[model_set]]))

    def should_exit(self, zone, position, current_bars, market_state=None):
        if not self.enabled: return False
        if zone not in self.config.get('active_zones', []): return False
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
