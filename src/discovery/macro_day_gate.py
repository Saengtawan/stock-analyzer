"""
Macro Day Gate — ML-based day quality prediction for Discovery.

Predicts whether TODAY is a good day to pick stocks (WR > 50%).
Controls pick QUANTITY: more picks on good days, fewer on bad days.

Walk-forward validated: AUC 0.60, Top 20% days WR=66.7%, Bot 20% WR=40.4%

Key features (by importance):
  recent_wr (0.14), skew (0.14), btc_ret5d (0.09), vvix (0.08),
  hyg_ret5d (0.07), gold_ret5d (0.06)

Refit: every 30 days via AutoRefitOrchestrator (rolling 500-day window).
"""
import logging
import pickle
import time
from collections import defaultdict

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

from database.orm.base import get_session
from sqlalchemy import text

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    'vix', 'vix_term', 'yld_spread', 'y10', 'y3m',
    'vix_chg5d', 'spy_ret5d', 'crude_ret5d', 'gold_ret5d', 'btc_ret5d',
    'vix_chg1d', 'spy_ret1d',
    'skew', 'vvix', 'hyg_ret5d', 'recent_wr',
]

TRAIN_WINDOW = 500  # days


class MacroDayGate:
    """Predict day quality from macro features. Controls pick volume."""

    def __init__(self):
        self._model = None
        self._fitted = False
        self._fitted_at = 0
        self._auc = 0.0
        self._n_days = 0

    def load_from_db(self) -> bool:
        try:
            with get_session() as session:
                row = session.execute(text(
                    'SELECT model_blob, auc, n_days FROM macro_day_gate WHERE id = 1'
                )).fetchone()
            if row and row[0]:
                data = pickle.loads(row[0])
                self._model = data['model']
                self._auc = data.get('auc', row[1] or 0)
                self._n_days = data.get('n_days', row[2] or 0)
                self._fitted = True
                self._fitted_at = time.time()
                logger.info("MacroDayGate: loaded (AUC=%.4f, N=%d days)", self._auc, self._n_days)
                return True
        except Exception as e:
            logger.debug("MacroDayGate: load error: %s", e)
        return False

    def save_to_db(self):
        if not self._fitted:
            return
        data = {
            'model': self._model,
            'features': FEATURE_NAMES,
            'auc': self._auc,
            'n_days': self._n_days,
        }
        blob = pickle.dumps(data)
        try:
            with get_session() as session:
                session.execute(text('''
                    CREATE TABLE IF NOT EXISTS macro_day_gate (
                        id INTEGER PRIMARY KEY, model_blob BLOB,
                        created_at TEXT, auc REAL, n_days INTEGER
                    )
                '''))
                session.execute(text('DELETE FROM macro_day_gate'))
                session.execute(text('''
                    INSERT INTO macro_day_gate (id, model_blob, created_at, auc, n_days)
                    VALUES (1, :blob, datetime('now'), :auc, :n)
                '''), {'blob': blob, 'auc': self._auc, 'n': self._n_days})
            logger.info("MacroDayGate: saved (AUC=%.4f, N=%d)", self._auc, self._n_days)
        except Exception as e:
            logger.error("MacroDayGate: save error: %s", e)

    def fit(self, max_date: str = None):
        """Train on historical day-level outcomes."""
        day_data = self._load_day_data(max_date)
        if len(day_data) < TRAIN_WINDOW + 90:
            logger.warning("MacroDayGate: insufficient data (%d days, need %d)",
                           len(day_data), TRAIN_WINDOW + 90)
            return

        X = np.array([d['features'] for d in day_data])
        y = np.array([d['good'] for d in day_data])
        X = np.nan_to_num(X, nan=0, posinf=0, neginf=0)

        # Train on ALL available data (more data = better generalization)
        self._model = GradientBoostingClassifier(
            n_estimators=150, max_depth=3, learning_rate=0.05,
            subsample=0.8, random_state=42,
        )
        self._model.fit(X, y)
        self._fitted = True
        self._fitted_at = time.time()
        self._n_days = len(X)

        # Walk-forward AUC: train on 70%, test on 30%
        split = int(len(X) * 0.7)
        if split >= TRAIN_WINDOW and len(X) - split >= 50:
            from sklearn.metrics import roc_auc_score
            val_model = GradientBoostingClassifier(
                n_estimators=150, max_depth=3, learning_rate=0.05,
                subsample=0.8, random_state=42,
            )
            val_model.fit(X[:split], y[:split])
            val_probs = val_model.predict_proba(X[split:])[:, 1]
            try:
                self._auc = roc_auc_score(y[split:], val_probs)
            except Exception:
                self._auc = 0.5
        else:
            self._auc = 0.5

        logger.info("MacroDayGate: fitted on %d days, AUC=%.4f", self._n_days, self._auc)

    def predict(self, macro: dict) -> dict:
        """Predict day quality from current macro features.

        Returns:
            {
                'day_prob': float (0-1, probability of good day),
                'day_quality': str ('HIGH', 'NORMAL', 'LOW', 'SKIP'),
                'pick_fraction': float (0-1, recommended fraction of picks to take),
            }
        """
        if not self._fitted or self._model is None:
            return {'day_prob': 0.5, 'day_quality': 'NORMAL', 'pick_fraction': 1.0}

        features = self._extract_features(macro)
        X = np.array([features])
        X = np.nan_to_num(X, nan=0, posinf=0, neginf=0)

        prob = self._model.predict_proba(X)[0, 1]

        # Map probability to action
        if prob >= 0.65:
            quality = 'HIGH'
            fraction = 1.0
        elif prob >= 0.45:
            quality = 'NORMAL'
            fraction = 1.0
        elif prob >= 0.30:
            quality = 'LOW'
            fraction = 0.5  # top half only
        else:
            quality = 'SKIP'
            fraction = 0.0

        return {
            'day_prob': round(float(prob), 4),
            'day_quality': quality,
            'pick_fraction': fraction,
        }

    def needs_refit(self, max_age_days: int = 30) -> bool:
        if not self._fitted:
            return True
        age = (time.time() - self._fitted_at) / 86400
        return age > max_age_days

    def _extract_features(self, macro: dict) -> list:
        """Extract 16 features from macro dict (same as training)."""
        vix = macro.get('vix_close', 20) or 20
        vix3m = macro.get('vix3m_close', 20) or 20
        vix_term = vix / vix3m if vix3m > 0 else 1.0

        return [
            vix,
            vix_term,
            macro.get('yield_spread', 0) or 0,
            macro.get('yield_10y', 0) or 0,
            macro.get('yield_3m', 0) or 0,
            macro.get('vix_delta_5d', 0) or 0,
            macro.get('spy_5d_ret', 0) or 0,
            macro.get('crude_delta_5d_pct', 0) or 0,
            macro.get('gold_delta_5d_pct', 0) or 0,
            macro.get('btc_momentum_3d', 0) or 0,  # closest to btc_ret5d
            macro.get('vix_delta_1d', vix - (macro.get('vix_prev', vix) or vix)) or 0,
            macro.get('spy_1d_ret', 0) or 0,
            macro.get('skew_close', 0) or 0,
            macro.get('vvix_close', 0) or 0,
            macro.get('hyg_delta_5d_pct', 0) or 0,
            macro.get('recent_discovery_wr', 0.5) or 0.5,
        ]

    def _load_day_data(self, max_date: str = None) -> list:
        """Load day-level training data from DB."""
        date_filter = f"AND o.scan_date <= '{max_date}'" if max_date else ""

        with get_session() as session:
            rows = session.execute(text(f'''
                SELECT o.scan_date, o.actual_return_d3,
                       m.vix_close, m.vix3m_close, m.yield_spread, m.yield_10y, m.yield_3m,
                       m.spy_close, m.crude_close, m.gold_close, m.dxy_close,
                       m.btc_close, m.hyg_close, m.usdjpy_close, m.skew_close, m.vvix_close
                FROM discovery_outcomes o
                LEFT JOIN macro_snapshots m ON o.scan_date = m.date
                WHERE o.actual_return_d3 IS NOT NULL AND m.vix_close IS NOT NULL
                {date_filter}
                ORDER BY o.scan_date
            ''')).fetchall()

        # Aggregate to day level
        days_dict = defaultdict(lambda: {'macro': None, 'wins': 0, 'total': 0})
        for r in rows:
            sd = r[0]
            days_dict[sd]['macro'] = r[2:]
            days_dict[sd]['total'] += 1
            if r[1] > 0:
                days_dict[sd]['wins'] += 1

        day_list = sorted(days_dict.keys())

        # Build features with lagged values
        result = []
        for i, d in enumerate(day_list):
            info = days_dict[d]
            if info['total'] < 3:
                continue
            m = info['macro']
            if any(v is None for v in m[:5]):
                continue

            vix, vix3m, yld_spread, y10, y3m, spy, crude, gold, dxy, btc, hyg, usdjpy, skew, vvix = m
            vt = vix / vix3m if vix3m and vix3m > 0 else 1.0

            # 5-day-ago macro
            d5_idx = max(0, i - 5)
            m5 = days_dict[day_list[d5_idx]]['macro'] if day_list[d5_idx] in days_dict else None

            # 1-day-ago macro
            d1_idx = max(0, i - 1)
            m1 = days_dict[day_list[d1_idx]]['macro'] if day_list[d1_idx] in days_dict else None

            # Recent WR (last 5 days)
            recent_wr_vals = []
            for j in range(max(0, i - 5), i):
                dj = day_list[j]
                if days_dict[dj]['total'] >= 3:
                    recent_wr_vals.append(days_dict[dj]['wins'] / days_dict[dj]['total'])
            avg_recent_wr = float(np.mean(recent_wr_vals)) if recent_wr_vals else 0.5

            def _safe_ret(new, old):
                if new and old and old > 0:
                    return (new / old - 1) * 100
                return 0.0

            feats = [
                vix, vt, yld_spread or 0, y10 or 0, y3m or 0,
                (vix - m5[0]) if m5 and m5[0] else 0,
                _safe_ret(spy, m5[5]) if m5 else 0,
                _safe_ret(crude, m5[6]) if m5 else 0,
                _safe_ret(gold, m5[7]) if m5 else 0,
                _safe_ret(btc, m5[9]) if m5 else 0,
                (vix - m1[0]) if m1 and m1[0] else 0,
                _safe_ret(spy, m1[5]) if m1 else 0,
                skew or 0,
                vvix or 0,
                _safe_ret(hyg, m5[10]) if m5 else 0,
                avg_recent_wr,
            ]

            wr = info['wins'] / info['total']
            result.append({
                'date': d,
                'features': feats,
                'good': 1 if wr > 0.5 else 0,
            })

        return result
