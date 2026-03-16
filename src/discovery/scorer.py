"""
Discovery Scorer — Layer 1 hard filters + Layer 2 composite score.

Layer 1: beta [0.3, 0.8], atr_pct <= 5.0, distance_from_high >= -3
Layer 2: IC-weighted composite from 20 features, score 0-100
"""
import logging
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'discovery.yaml'


def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)['discovery']


class DiscoveryScorer:
    def __init__(self):
        cfg = _load_config()
        self.l1 = cfg['layer1']
        self.l2 = cfg['layer2']

        # Precompute normalization ranges (from training data distribution)
        # These are p02/p98 from the expanded dataset
        self._ranges = {
            'volume_ratio':       (0.30, 1.20),
            'momentum_5d':        (-8.0, 5.0),
            'vix_term_structure':  (0.90, 1.15),
            'new_52w_highs':      (30, 400),
            'bull_score':         (0, 1),
            'vix_close':          (15.0, 30.0),
            'news_count':         (1, 50),
            'news_pos_ratio':     (0.2, 0.9),
            'highs_lows_ratio':   (0.5, 15.0),
            'ad_ratio':           (0.5, 2.5),
            'mcap_log':           (9.0, 12.0),
            'sector_1d_change':   (-2.0, 2.0),
            'momentum_20d':       (-15.0, 15.0),
            'vix3m_close':        (18.0, 28.0),
            'rsi':                (25, 75),
            'upside_pct':         (-20, 40),
            # v1.2: Macro stress features (p02/p98 from macro_snapshots Feb-Mar 2026)
            'breadth_delta_5d':   (-25.0, 10.0),
            'crude_close':        (60.0, 100.0),
            'stress_score':       (0.0, 60.0),
            'vix_delta_5d':       (-5.0, 12.0),
        }

    def passes_layer1(self, stock: dict) -> tuple[bool, str]:
        """Apply hard safety filters. Returns (pass, reject_reason)."""
        beta = stock.get('beta')
        atr = stock.get('atr_pct')
        dist = stock.get('distance_from_high')

        if beta is None or atr is None or dist is None:
            return False, 'missing_data'

        min_beta = self.l1.get('min_beta', 0.0)
        if beta < min_beta:
            return False, f'beta={beta:.2f}<{min_beta}'
        if beta > self.l1['max_beta']:
            return False, f'beta={beta:.2f}>{self.l1["max_beta"]}'
        if atr > self.l1['max_atr_pct']:
            return False, f'atr={atr:.1f}>{self.l1["max_atr_pct"]}'
        if dist < self.l1['min_distance_from_high']:
            return False, f'dist={dist:.1f}<{self.l1["min_distance_from_high"]}'

        return True, ''

    def compute_layer2_score(self, stock: dict) -> float:
        """Compute IC-weighted composite score (0-100) from Layer 2 features."""
        features_cfg = self.l2['features']
        total_weight = 0.0
        weighted_sum = 0.0
        features_used = 0

        for feat_name, feat_cfg in features_cfg.items():
            raw = stock.get(feat_name)
            if raw is None:
                continue

            weight = feat_cfg['weight']
            direction = feat_cfg['direction']

            # Normalize to 0-1
            pmin, pmax = self._ranges.get(feat_name, (0, 1))
            if pmax == pmin:
                normalized = 0.5
            else:
                normalized = (raw - pmin) / (pmax - pmin)
                normalized = max(0.0, min(1.0, normalized))

            # If IC is negative (direction=-1), invert
            if direction < 0:
                normalized = 1.0 - normalized

            weighted_sum += normalized * weight
            total_weight += weight
            features_used += 1

        if total_weight == 0 or features_used < 3:
            return 0.0

        # Normalize by actual weight used (handle missing features)
        raw_score = weighted_sum / total_weight

        # Scale to 0-100 (calibrated from training: p02=0.35, p98=0.65)
        score = (raw_score - 0.35) / (0.65 - 0.35) * 100
        return max(0.0, min(100.0, score))
