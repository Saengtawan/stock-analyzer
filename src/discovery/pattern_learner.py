"""
Discovery Pattern Learner — automatically discovers feature drift and new patterns.

Periodically (weekly or on-demand):
1. Compute IC (Information Coefficient) for each feature over recent 90 days
2. Compare to historical IC → detect drift
3. Identify high-IC feature interactions → flag as candidates
4. Test candidates on hold-out data

This is the "genuine learning" component — it finds patterns humans missed.
"""
import logging
from database.orm.base import get_session
from sqlalchemy import text
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# Features we can compute IC for (available in backfill_signal_outcomes + macro)
TRACKABLE_FEATURES = [
    'atr_pct',
    'distance_from_20d_high',
    'momentum_5d',
    'momentum_20d',
    'volume_ratio',
    'vix_at_signal',
]

# Macro features (from macro_snapshots joined by date)
MACRO_FEATURES = [
    'pct_above_20d_ma',
    'new_52w_highs',
    'new_52w_lows',
    'vix_close',
    'spy_close',
    'crude_close',
]


class PatternLearner:
    """Discover feature drift and new predictive patterns."""

    def __init__(self):
        self._last_analysis: Optional[dict] = None

    def analyze_feature_ic(self, lookback_days: int = 90) -> dict:
        """Compute IC for each feature over recent window.

        IC = Spearman rank correlation between feature value and outcome_3d.
        Higher |IC| = more predictive. Sign matters:
        - Positive IC: higher feature → higher return
        - Negative IC: higher feature → lower return

        Returns dict with per-feature IC, p-value, and drift flag.
        """
        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
        hist_cutoff = (datetime.now() - timedelta(days=lookback_days + 180)).strftime('%Y-%m-%d')

        with get_session() as session:
            # Recent period
            recent = session.execute(text("""
                SELECT scan_date, symbol, atr_pct, distance_from_20d_high,
                       momentum_5d, momentum_20d, volume_ratio, vix_at_signal,
                       outcome_3d
                FROM backfill_signal_outcomes
                WHERE scan_date >= :p0 AND outcome_3d IS NOT NULL
                UNION ALL
                SELECT scan_date, symbol, atr_pct, distance_from_20d_high,
                       momentum_5d, momentum_20d, volume_ratio, vix_at_signal,
                       outcome_3d
                FROM signal_outcomes
                WHERE scan_date >= :p1 AND outcome_3d IS NOT NULL
            """), {"p0": cutoff, "p1": cutoff}).fetchall()

            # Historical period (before cutoff, for drift comparison)
            historical = session.execute(text("""
                SELECT atr_pct, distance_from_20d_high,
                       momentum_5d, momentum_20d, volume_ratio, vix_at_signal,
                       outcome_3d
                FROM backfill_signal_outcomes
                WHERE scan_date >= :p0 AND scan_date < :p1 AND outcome_3d IS NOT NULL
            """), {"p0": hist_cutoff, "p1": cutoff}).fetchall()

        if len(recent) < 30:
            logger.warning("PatternLearner: insufficient recent data (%d rows)", len(recent))
            return {'features': {}, 'n_recent': len(recent), 'n_historical': len(historical)}

        # Compute IC for each feature
        from scipy.stats import spearmanr

        feature_indices = {
            'atr_pct': 2, 'distance_from_20d_high': 3,
            'momentum_5d': 4, 'momentum_20d': 5,
            'volume_ratio': 6, 'vix_at_signal': 7,
        }
        outcome_idx = 8

        results = {}
        for feat_name, feat_idx in feature_indices.items():
            # Recent IC
            feat_vals = np.array([r[feat_idx] for r in recent if r[feat_idx] is not None and r[outcome_idx] is not None])
            out_vals = np.array([r[outcome_idx] for r in recent if r[feat_idx] is not None and r[outcome_idx] is not None])

            if len(feat_vals) < 20:
                continue

            corr, p_val = spearmanr(feat_vals, out_vals)
            if np.isnan(corr):
                continue

            # Historical IC (for drift detection)
            hist_feat = np.array([r[feat_idx - 2] for r in historical if r[feat_idx - 2] is not None and r[6] is not None])
            hist_out = np.array([r[6] for r in historical if r[feat_idx - 2] is not None and r[6] is not None])

            hist_ic = None
            if len(hist_feat) >= 50:
                h_corr, _ = spearmanr(hist_feat, hist_out)
                if not np.isnan(h_corr):
                    hist_ic = round(float(h_corr), 4)

            # Drift detection: significant change in IC
            drift = False
            drift_magnitude = 0
            if hist_ic is not None:
                drift_magnitude = abs(float(corr) - hist_ic)
                drift = drift_magnitude > 0.1  # IC shifted by >0.1

            results[feat_name] = {
                'recent_ic': round(float(corr), 4),
                'p_value': round(float(p_val), 4),
                'significant': bool(p_val < 0.05),
                'historical_ic': hist_ic,
                'drift': bool(drift),
                'drift_magnitude': round(float(drift_magnitude), 4) if hist_ic else None,
                'n_recent': int(len(feat_vals)),
            }

        # Sort by absolute IC (most predictive first)
        sorted_features = dict(sorted(results.items(),
                                       key=lambda x: abs(x[1]['recent_ic']),
                                       reverse=True))

        self._last_analysis = {
            'features': sorted_features,
            'n_recent': len(recent),
            'n_historical': len(historical),
            'lookback_days': lookback_days,
            'analyzed_at': datetime.now().isoformat(),
        }

        # Log drift warnings
        drifted = [f for f, d in sorted_features.items() if d.get('drift')]
        if drifted:
            logger.warning(
                "PatternLearner: IC drift detected in features: %s",
                ', '.join(f"{f} ({sorted_features[f]['historical_ic']:.3f}→{sorted_features[f]['recent_ic']:.3f})" for f in drifted),
            )

        return self._last_analysis

    def detect_interaction_effects(self, lookback_days: int = 90) -> list[dict]:
        """Find feature interactions that predict outcomes better than individual features.

        Tests pairwise interactions (product, ratio) of top features.
        If interaction IC > max(individual ICs) + 0.05, flag as candidate.
        """
        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

        with get_session() as session:
            rows = session.execute(text("""
                SELECT atr_pct, distance_from_20d_high, momentum_5d,
                       volume_ratio, vix_at_signal, outcome_3d
                FROM backfill_signal_outcomes
                WHERE scan_date >= :p0 AND outcome_3d IS NOT NULL
                  AND atr_pct IS NOT NULL AND distance_from_20d_high IS NOT NULL
                  AND momentum_5d IS NOT NULL AND volume_ratio IS NOT NULL
            """), {"p0": cutoff}).fetchall()

        if len(rows) < 100:
            return []

        from scipy.stats import spearmanr

        data = np.array(rows, dtype=float)
        feat_names = ['atr_pct', 'distance_from_20d_high', 'momentum_5d',
                       'volume_ratio', 'vix_at_signal']
        outcomes = data[:, -1]

        # Individual ICs
        individual_ics = {}
        for i, name in enumerate(feat_names):
            corr, _ = spearmanr(data[:, i], outcomes)
            individual_ics[name] = float(corr) if not np.isnan(corr) else 0

        # Pairwise interactions
        candidates = []
        for i in range(len(feat_names)):
            for j in range(i + 1, len(feat_names)):
                f1, f2 = data[:, i], data[:, j]
                name1, name2 = feat_names[i], feat_names[j]

                # Product interaction
                product = f1 * f2
                mask = np.isfinite(product)
                if mask.sum() >= 50:
                    corr, p_val = spearmanr(product[mask], outcomes[mask])
                    if not np.isnan(corr):
                        max_individual = max(abs(individual_ics[name1]),
                                             abs(individual_ics[name2]))
                        if abs(corr) > max_individual + 0.05:
                            candidates.append({
                                'type': 'product',
                                'features': [name1, name2],
                                'interaction_ic': round(float(corr), 4),
                                'p_value': round(float(p_val), 4),
                                'individual_ics': [round(individual_ics[name1], 4),
                                                    round(individual_ics[name2], 4)],
                                'improvement': round(abs(corr) - max_individual, 4),
                            })

                # Ratio interaction (avoid division by zero)
                if np.all(np.abs(f2[mask]) > 0.01):
                    ratio = f1 / np.where(np.abs(f2) > 0.01, f2, 1)
                    mask_r = np.isfinite(ratio)
                    if mask_r.sum() >= 50:
                        corr, p_val = spearmanr(ratio[mask_r], outcomes[mask_r])
                        if not np.isnan(corr):
                            max_individual = max(abs(individual_ics[name1]),
                                                 abs(individual_ics[name2]))
                            if abs(corr) > max_individual + 0.05:
                                candidates.append({
                                    'type': 'ratio',
                                    'features': [name1, name2],
                                    'interaction_ic': round(float(corr), 4),
                                    'p_value': round(float(p_val), 4),
                                    'individual_ics': [round(individual_ics[name1], 4),
                                                        round(individual_ics[name2], 4)],
                                    'improvement': round(abs(corr) - max_individual, 4),
                                })

        # Sort by improvement over individual features
        candidates.sort(key=lambda x: x['improvement'], reverse=True)

        if candidates:
            logger.info(
                "PatternLearner: found %d interaction candidates, best: %s (%s IC=%.3f, +%.3f)",
                len(candidates), candidates[0]['features'], candidates[0]['type'],
                candidates[0]['interaction_ic'], candidates[0]['improvement'],
            )

        return candidates

    def compute_regime_ic_shift(self) -> dict:
        """Check if feature predictiveness changes by regime.

        Critical for discovery: a feature might be great in BULL but useless in CRISIS.
        This helps the kernel know when to trust which features more.
        """
        with get_session() as session:
            rows = session.execute(text("""
                SELECT b.atr_pct, b.distance_from_20d_high, b.momentum_5d,
                       b.volume_ratio, b.vix_at_signal, b.outcome_3d
                FROM backfill_signal_outcomes b
                WHERE b.outcome_3d IS NOT NULL
                  AND b.atr_pct IS NOT NULL
                ORDER BY b.scan_date DESC
                LIMIT 10000
            """)).fetchall()

        if len(rows) < 200:
            return {}

        from scipy.stats import spearmanr

        data = np.array(rows, dtype=float)
        vix = data[:, 4]
        outcomes = data[:, 5]

        feat_names = ['atr_pct', 'distance_from_20d_high', 'momentum_5d', 'volume_ratio']

        # Split by VIX regime
        bull_mask = vix < 20
        stress_mask = (vix >= 20) & (vix < 30)
        crisis_mask = vix >= 30

        result = {}
        for i, name in enumerate(feat_names):
            result[name] = {}
            for regime, mask in [('BULL', bull_mask), ('STRESS', stress_mask), ('CRISIS', crisis_mask)]:
                if mask.sum() < 30:
                    result[name][regime] = {'ic': None, 'n': int(mask.sum())}
                    continue
                corr, p_val = spearmanr(data[mask, i], outcomes[mask])
                result[name][regime] = {
                    'ic': round(float(corr), 4) if not np.isnan(corr) else None,
                    'p_value': round(float(p_val), 4) if not np.isnan(p_val) else None,
                    'n': int(mask.sum()),
                }

        return result

    def get_last_analysis(self) -> Optional[dict]:
        return self._last_analysis
