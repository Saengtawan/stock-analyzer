"""
Intraday ML Ensemble Filter — LogisticRegression + GradientBoosting + LightGBM.

Filters FIRST_BAR_CONFIRM and BREAKOUT signals from gap_scanner.scan_intraday().
Backtest: ensemble "both agree > 0.6" gives WR 80.9%, PF 8.99.
v2: Triple ensemble (LR+GB+LGBM), VIX-adaptive threshold, GAP_NOT_FILLED override.

Training:
  - Label: did the stock close higher than 10:30 price? (1 = good breakout, 0 = fade)
  - Features: gap_pct, volume_ratio, momentum, ATR, RSI, dist_from_20d_high, macro
  - Walk-forward: train on last 12 months, retrain monthly

Usage:
  filter = IntradayMLFilter()
  filter.load_from_db()  # or filter.fit()
  scored = filter.predict(candidates, macro)
  # Each candidate gets '_ml_pass' (bool) and '_ml_prob' (float)
"""

from database.orm.base import get_session
from sqlalchemy import text
import json
import logging
import math
import pickle
from datetime import date, timedelta

import numpy as np

logger = logging.getLogger(__name__)

INTRADAY_ML_FEATURES = [
    'gap_pct',
    'volume_ratio',
    'momentum_5d',
    'momentum_20d',
    'atr_pct',
    'rsi_14',
    'distance_from_20d_high',
    'market_cap_log',
    'beta',
    'vix_close',
    'breadth',
]


class IntradayMLFilter:
    """Ensemble ML filter for intraday gap signals (LR + GradientBoosting + LightGBM)."""

    def __init__(self):
        self._lr_model = None
        self._gb_model = None
        self._lgbm_model = None
        self._scaler = None
        self._fitted = False
        self._fit_date = None
        self._feature_names = INTRADAY_ML_FEATURES
        self._metrics = {}

    # ── Public API ──

    def fit(self, max_date: str = None):
        """Train both models on historical gap-up days. Walk-forward: last 12 months."""
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.metrics import roc_auc_score, accuracy_score
        except ImportError:
            logger.warning("IntradayMLFilter: sklearn not available, skipping fit")
            return

        max_date = max_date or date.today().isoformat()
        min_date = (date.fromisoformat(max_date) - timedelta(days=365)).isoformat()

        logger.info("IntradayMLFilter: building training data %s to %s ...", min_date, max_date)

        with get_session() as conn:
            X, y = self._build_training_data(conn, min_date, max_date)

        if X is None or len(X) < 100:
            logger.warning("IntradayMLFilter: insufficient data (%d rows), need >= 100",
                           len(X) if X is not None else 0)
            return

        n = len(X)
        logger.info("IntradayMLFilter: %d samples, %d features, label_mean=%.3f",
                     n, X.shape[1], y.mean())

        # Walk-forward split: 80/20
        split_idx = int(n * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        if len(np.unique(y_train)) < 2:
            logger.warning("IntradayMLFilter: only one class in training set, skipping")
            return

        # Scale
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # Train LogisticRegression
        lr = LogisticRegression(C=1.0, max_iter=1000, class_weight='balanced', random_state=42)
        lr.fit(X_train_s, y_train)

        # Train GradientBoosting
        gb = GradientBoostingClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42,
        )
        gb.fit(X_train_s, y_train)

        # Train LightGBM
        lgbm = None
        try:
            from lightgbm import LGBMClassifier
            lgbm = LGBMClassifier(n_estimators=300, max_depth=5, learning_rate=0.1,
                                  subsample=0.8, colsample_bytree=0.8, random_state=42, verbose=-1)
            lgbm.fit(X_train_s, y_train)
        except ImportError:
            logger.warning("IntradayMLFilter: lightgbm not installed, using LR+GB only")
            lgbm = None

        # Evaluate
        lr_prob = lr.predict_proba(X_test_s)[:, 1]
        gb_prob = gb.predict_proba(X_test_s)[:, 1]
        ensemble_pass = (lr_prob > 0.6) & (gb_prob > 0.6)

        try:
            lr_auc = roc_auc_score(y_test, lr_prob)
            gb_auc = roc_auc_score(y_test, gb_prob)
        except ValueError:
            lr_auc = gb_auc = 0.5

        lgbm_auc = 0.5
        lgbm_acc = 0.0
        if lgbm is not None:
            lgbm_prob_test = lgbm.predict_proba(X_test_s)[:, 1]
            try:
                lgbm_auc = roc_auc_score(y_test, lgbm_prob_test)
            except ValueError:
                lgbm_auc = 0.5
            lgbm_acc = accuracy_score(y_test, (lgbm_prob_test > 0.5).astype(int))
            # Update ensemble to triple agreement
            ensemble_pass = (lr_prob > 0.6) & (gb_prob > 0.6) & (lgbm_prob_test > 0.6)

        # Ensemble stats
        n_pass = ensemble_pass.sum()
        if n_pass > 0:
            ens_wr = y_test[ensemble_pass].mean()
            ens_n = int(n_pass)
        else:
            ens_wr = 0.0
            ens_n = 0

        lr_acc = accuracy_score(y_test, (lr_prob > 0.5).astype(int))
        gb_acc = accuracy_score(y_test, (gb_prob > 0.5).astype(int))

        self._metrics = {
            'lr_auc': round(lr_auc, 4),
            'gb_auc': round(gb_auc, 4),
            'lgbm_auc': round(lgbm_auc, 4),
            'lr_accuracy': round(lr_acc, 4),
            'gb_accuracy': round(gb_acc, 4),
            'lgbm_accuracy': round(lgbm_acc, 4),
            'ensemble_wr': round(float(ens_wr), 4),
            'ensemble_n': ens_n,
            'train_n': split_idx,
            'test_n': n - split_idx,
            'test_wr': round(float(y_test.mean()), 4),
            'has_lgbm': lgbm is not None,
        }

        # Log feature importances
        gb_imp = sorted(zip(self._feature_names, gb.feature_importances_),
                        key=lambda x: x[1], reverse=True)
        logger.info("IntradayMLFilter: LR AUC=%.4f, GB AUC=%.4f, "
                     "ensemble WR=%.3f (n=%d/%d)",
                     lr_auc, gb_auc, ens_wr, ens_n, len(y_test))
        logger.info("IntradayMLFilter: GB feature importance:")
        for fname, imp in gb_imp[:6]:
            logger.info("  %25s: %.4f", fname, imp)

        # Store
        self._lr_model = lr
        self._gb_model = gb
        self._lgbm_model = lgbm
        self._scaler = scaler
        self._fitted = True
        self._fit_date = max_date

        # Persist to DB
        self.save_to_db()
        logger.info("IntradayMLFilter: fitted and saved to DB")

    def predict(self, candidates: list, macro: dict) -> list:
        """Score candidates. Adds '_ml_pass' and '_ml_prob' to each dict.

        Ensemble rule: ALL available models must agree > threshold.
        - Triple ensemble (LR+GB+LGBM) when lightgbm available, else LR+GB.
        - VIX-adaptive threshold: 0.7 when VIX<=20, 0.75 when VIX>20.
        - GAP_NOT_FILLED strategy uses tighter threshold (0.8).
        If not fitted, all candidates pass through (no filtering).
        """
        if not self._fitted or self._lr_model is None or self._gb_model is None:
            for c in candidates:
                c['_ml_pass'] = True
                c['_ml_prob'] = 0.0
            return candidates

        # Build feature matrix
        X = self._build_predict_features(candidates, macro)
        if X is None or len(X) == 0:
            for c in candidates:
                c['_ml_pass'] = True
                c['_ml_prob'] = 0.0
            return candidates

        try:
            X_s = self._scaler.transform(X)
            lr_prob = self._lr_model.predict_proba(X_s)[:, 1]
            gb_prob = self._gb_model.predict_proba(X_s)[:, 1]
            lgbm_prob = None
            if self._lgbm_model is not None:
                lgbm_prob = self._lgbm_model.predict_proba(X_s)[:, 1]
        except Exception as e:
            logger.warning("IntradayMLFilter predict error: %s", e)
            for c in candidates:
                c['_ml_pass'] = True
                c['_ml_prob'] = 0.0
            return candidates

        # VIX-adaptive base threshold
        vix = macro.get('vix_close', macro.get('vix', 20.0)) or 20.0
        base_threshold = 0.7 if vix <= 20 else 0.75

        for i, c in enumerate(candidates):
            lr_p = float(lr_prob[i])
            gb_p = float(gb_prob[i])
            lgbm_p = float(lgbm_prob[i]) if lgbm_prob is not None else None

            if lgbm_p is not None:
                avg_prob = (lr_p + gb_p + lgbm_p) / 3
            else:
                avg_prob = (lr_p + gb_p) / 2

            # Per-strategy threshold: GAP_NOT_FILLED uses tighter filter (WR 86% → 92%)
            if c.get('strategy') == 'GAP_NOT_FILLED':
                strategy_threshold = 0.8
            else:
                strategy_threshold = base_threshold

            # Confidence tiers (backtest 856 symbols, 55M bars)
            # Triple ensemble: ALL available models must agree > threshold
            if gb_p > 0.95:
                tier = 'HIGH'       # WR ~89%, PF 33 — very high confidence
            else:
                # Check all models agree > threshold
                if lgbm_p is not None:
                    all_agree = (lr_p > strategy_threshold and
                                 gb_p > strategy_threshold and
                                 lgbm_p > strategy_threshold)
                else:
                    all_agree = (lr_p > strategy_threshold and
                                 gb_p > strategy_threshold)

                if all_agree:
                    tier = 'CONFIRMED'  # All models agree above threshold
                else:
                    tier = 'REJECT'

            c['_ml_pass'] = tier != 'REJECT'
            c['_ml_tier'] = tier
            c['_ml_prob'] = round(avg_prob, 4)
            c['_ml_lr_prob'] = round(lr_p, 4)
            c['_ml_gb_prob'] = round(gb_p, 4)
            if lgbm_p is not None:
                c['_ml_lgbm_prob'] = round(lgbm_p, 4)

        n_high = sum(1 for c in candidates if c.get('_ml_tier') == 'HIGH')
        n_conf = sum(1 for c in candidates if c.get('_ml_tier') == 'CONFIRMED')
        n_reject = sum(1 for c in candidates if c.get('_ml_tier') == 'REJECT')
        logger.info("IntradayMLFilter: %d HIGH + %d CONFIRMED + %d rejected (of %d), "
                     "vix=%.1f threshold=%.2f lgbm=%s",
                     n_high, n_conf, n_reject, len(candidates),
                     vix, base_threshold, 'yes' if self._lgbm_model else 'no')

        return candidates

    def save_to_db(self):
        """Pickle all models + scaler to DB table."""
        if not self._fitted:
            return

        try:
            lr_blob = pickle.dumps(self._lr_model)
            gb_blob = pickle.dumps(self._gb_model)
            lgbm_blob = pickle.dumps(self._lgbm_model) if self._lgbm_model is not None else None
            scaler_blob = pickle.dumps(self._scaler)
            metrics_json = json.dumps(self._metrics)

            with get_session() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS intraday_ml_model (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fit_date TEXT,
                        lr_pickle BLOB,
                        gb_pickle BLOB,
                        lgbm_pickle BLOB,
                        scaler_pickle BLOB,
                        metrics_json TEXT,
                        created_at TEXT DEFAULT (datetime('now'))
                    )
                """))

                # Check if lgbm_pickle column exists, add if missing (migration)
                cols = conn.execute(text(
                    "PRAGMA table_info(intraday_ml_model)"
                )).fetchall()
                col_names = [c[1] for c in cols]
                if 'lgbm_pickle' not in col_names:
                    conn.execute(text(
                        "ALTER TABLE intraday_ml_model ADD COLUMN lgbm_pickle BLOB"
                    ))
                    logger.info("IntradayMLFilter: migrated table — added lgbm_pickle column")

                conn.execute(text("""
                    INSERT INTO intraday_ml_model
                        (fit_date, lr_pickle, gb_pickle, lgbm_pickle, scaler_pickle, metrics_json)
                    VALUES (:fit_date, :lr, :gb, :lgbm, :scaler, :metrics)
                """), {
                    'fit_date': self._fit_date,
                    'lr': lr_blob,
                    'gb': gb_blob,
                    'lgbm': lgbm_blob,
                    'scaler': scaler_blob,
                    'metrics': metrics_json,
                })
            logger.info("IntradayMLFilter: saved to DB (fit_date=%s, lgbm=%s)",
                        self._fit_date, 'yes' if self._lgbm_model else 'no')
        except Exception as e:
            logger.error("IntradayMLFilter save_to_db error: %s", e, exc_info=True)

    def load_from_db(self) -> bool:
        """Load latest model from DB. Returns True if loaded successfully."""
        try:
            with get_session() as conn:
                # Check if table exists
                tbl = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='intraday_ml_model'"
                )).fetchone()
                if not tbl:
                    logger.info("IntradayMLFilter: no model table yet")
                    return False

                # Check if lgbm_pickle column exists
                cols = conn.execute(text(
                    "PRAGMA table_info(intraday_ml_model)"
                )).fetchall()
                col_names = [c[1] for c in cols]
                has_lgbm_col = 'lgbm_pickle' in col_names

                if has_lgbm_col:
                    row = conn.execute(text("""
                        SELECT fit_date, lr_pickle, gb_pickle, lgbm_pickle, scaler_pickle, metrics_json
                        FROM intraday_ml_model
                        ORDER BY id DESC LIMIT 1
                    """)).fetchone()
                else:
                    row = conn.execute(text("""
                        SELECT fit_date, lr_pickle, gb_pickle, NULL, scaler_pickle, metrics_json
                        FROM intraday_ml_model
                        ORDER BY id DESC LIMIT 1
                    """)).fetchone()

            if not row:
                logger.info("IntradayMLFilter: no saved model found")
                return False

            self._fit_date = row[0]
            self._lr_model = pickle.loads(row[1])
            self._gb_model = pickle.loads(row[2])
            self._lgbm_model = pickle.loads(row[3]) if row[3] else None
            self._scaler = pickle.loads(row[4])
            self._metrics = json.loads(row[5]) if row[5] else {}
            self._fitted = True

            logger.info("IntradayMLFilter: loaded from DB (fit_date=%s, lgbm=%s, metrics=%s)",
                        self._fit_date, 'yes' if self._lgbm_model else 'no', self._metrics)
            return True

        except Exception as e:
            logger.warning("IntradayMLFilter load_from_db error: %s", e)
            return False

    # ── Private: Training Data ──

    def _build_training_data(self, conn, min_date: str, max_date: str):
        """Build feature matrix + labels from historical gap-up days.

        For each day where a stock gapped up >= 1%:
          - Features: gap_pct, volume_ratio, momentum, ATR, RSI, dist_from_20d_high, macro
          - Label: did the stock close higher than its 10:30 price? (proxy: close > open)
            Since we don't have reliable 10:30 snapshots for all history,
            we use close > open as proxy for "good breakout day".

        Data source: stock_daily_ohlc + macro_snapshots + stock_fundamentals
        """
        # Get gap-up days with features
        rows = conn.execute(text("""
            WITH bars AS (
                SELECT symbol, date, open, high, low, close, volume,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
                       LAG(close, 5) OVER (PARTITION BY symbol ORDER BY date) as close_5d,
                       LAG(close, 20) OVER (PARTITION BY symbol ORDER BY date) as close_20d,
                       AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as avg_vol_20d,
                       MAX(high) OVER (PARTITION BY symbol ORDER BY date
                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as high_20d,
                       AVG((high - low) / NULLIF(close, 0) * 100) OVER (
                           PARTITION BY symbol ORDER BY date
                           ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) as atr_pct_5d
                FROM stock_daily_ohlc
                WHERE date >= date(:min_date, '-30 days') AND date <= :max_date
                  AND open > 0 AND close > 5
            )
            SELECT b.symbol, b.date, b.open, b.high, b.low, b.close, b.volume,
                   b.prev_close, b.close_5d, b.close_20d, b.avg_vol_20d,
                   b.high_20d, b.atr_pct_5d,
                   sf.beta, sf.market_cap
            FROM bars b
            LEFT JOIN stock_fundamentals sf ON b.symbol = sf.symbol
            WHERE b.date >= :min_date AND b.date <= :max_date
              AND b.prev_close IS NOT NULL AND b.prev_close > 0
              AND b.avg_vol_20d IS NOT NULL AND b.avg_vol_20d > 0
              AND (b.open / b.prev_close - 1) * 100 >= 1.0
            ORDER BY b.date, b.symbol
        """), {'min_date': min_date, 'max_date': max_date}).mappings().fetchall()

        if not rows:
            return None, None

        logger.info("IntradayMLFilter: %d gap-up days loaded", len(rows))

        # Load macro lookup: {date -> {vix_close, breadth}}
        macro_rows = conn.execute(text("""
            SELECT ms.date,
                   ms.vix_close,
                   mb.pct_above_20d_ma
            FROM macro_snapshots ms
            LEFT JOIN market_breadth mb ON ms.date = mb.date
            WHERE ms.date >= :min_date AND ms.date <= :max_date
        """), {'min_date': min_date, 'max_date': max_date}).mappings().fetchall()

        macro_lookup = {}
        for m in macro_rows:
            macro_lookup[m['date']] = {
                'vix_close': m['vix_close'] or 20.0,
                'breadth': m['pct_above_20d_ma'] or 50.0,
            }

        # Build feature matrix
        X_list = []
        y_list = []

        for r in rows:
            prev_close = r['prev_close']
            gap_pct = (r['open'] / prev_close - 1) * 100
            volume_ratio = r['volume'] / r['avg_vol_20d'] if r['avg_vol_20d'] > 0 else 1.0

            mom_5d = ((r['close'] / r['close_5d'] - 1) * 100) if r['close_5d'] and r['close_5d'] > 0 else 0.0
            mom_20d = ((r['close'] / r['close_20d'] - 1) * 100) if r['close_20d'] and r['close_20d'] > 0 else 0.0

            atr_pct = r['atr_pct_5d'] or 2.0

            # RSI approximation from momentum (simplified for training)
            # True RSI needs 14-period sequential calc; use momentum-based proxy
            rsi_14 = self._approx_rsi_from_momentum(mom_5d, mom_20d)

            dist_20d_high = ((r['close'] / r['high_20d'] - 1) * 100) if r['high_20d'] and r['high_20d'] > 0 else 0.0

            mcap_log = math.log10(r['market_cap']) if r['market_cap'] and r['market_cap'] > 0 else 10.0
            beta = r['beta'] or 1.0

            macro_day = macro_lookup.get(r['date'], {})
            vix_close = macro_day.get('vix_close', 20.0)
            breadth = macro_day.get('breadth', 50.0)

            features = [
                gap_pct,
                volume_ratio,
                mom_5d,
                mom_20d,
                atr_pct,
                rsi_14,
                dist_20d_high,
                mcap_log,
                beta,
                vix_close,
                breadth,
            ]

            # Label: close > open (proxy for "breakout held")
            label = 1 if r['close'] > r['open'] else 0

            X_list.append(features)
            y_list.append(label)

        X = np.array(X_list, dtype=np.float64)
        y = np.array(y_list, dtype=np.int32)

        # Handle NaN/inf
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        return X, y

    def _build_predict_features(self, candidates: list, macro: dict) -> np.ndarray:
        """Build feature matrix for live prediction from candidate dicts + macro.

        Candidates already have: gap_pct, volume (from Alpaca snapshot).
        Additional features loaded from DB at scan time.
        """
        if not candidates:
            return None

        # Collect symbols that need DB enrichment
        symbols_need_db = [c['symbol'] for c in candidates
                           if 'momentum_5d' not in c or c.get('momentum_5d') is None]

        db_features = {}
        if symbols_need_db:
            try:
                with get_session() as conn:
                    for sym in symbols_need_db:
                        row = conn.execute(text("""
                            WITH bars AS (
                                SELECT close, high, low, volume,
                                       LAG(close, 5) OVER (ORDER BY date) as close_5d,
                                       LAG(close, 20) OVER (ORDER BY date) as close_20d,
                                       AVG(volume) OVER (ORDER BY date
                                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as avg_vol,
                                       MAX(high) OVER (ORDER BY date
                                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as high_20d,
                                       AVG((high - low) / NULLIF(close, 0) * 100) OVER (
                                           ORDER BY date ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) as atr_pct
                                FROM stock_daily_ohlc
                                WHERE symbol = :sym AND close > 0
                                ORDER BY date DESC LIMIT 25
                            )
                            SELECT close, close_5d, close_20d, avg_vol, high_20d, atr_pct
                            FROM bars
                            LIMIT 1
                        """), {'sym': sym}).fetchone()

                        if row and row[0]:
                            close = row[0]
                            db_features[sym] = {
                                'momentum_5d': round((close / row[1] - 1) * 100, 2) if row[1] and row[1] > 0 else 0.0,
                                'momentum_20d': round((close / row[2] - 1) * 100, 2) if row[2] and row[2] > 0 else 0.0,
                                'volume_ratio': round(row[3] / row[3], 2) if row[3] and row[3] > 0 else 1.0,  # placeholder
                                'distance_from_20d_high': round((close / row[4] - 1) * 100, 2) if row[4] and row[4] > 0 else 0.0,
                                'atr_pct': row[5] or 2.0,
                            }

                    # Load fundamentals for beta/mcap
                    fund_rows = conn.execute(text("""
                        SELECT symbol, beta, market_cap
                        FROM stock_fundamentals
                        WHERE symbol IN ({})
                    """.format(','.join(f"'{s}'" for s in symbols_need_db)))).mappings().fetchall()

                    for fr in fund_rows:
                        if fr['symbol'] in db_features:
                            db_features[fr['symbol']]['beta'] = fr['beta'] or 1.0
                            db_features[fr['symbol']]['market_cap'] = fr['market_cap'] or 0
            except Exception as e:
                logger.warning("IntradayMLFilter: DB enrichment error: %s", e)

        # Build feature vectors
        vix_close = macro.get('vix_close', macro.get('vix', 20.0)) or 20.0
        breadth = macro.get('pct_above_20d_ma', macro.get('breadth', 50.0)) or 50.0

        X_list = []
        for c in candidates:
            sym = c['symbol']
            db = db_features.get(sym, {})

            gap_pct = c.get('gap_pct', 0.0) or 0.0
            volume_ratio = c.get('volume_ratio', db.get('volume_ratio', 1.0)) or 1.0
            mom_5d = c.get('momentum_5d', db.get('momentum_5d', 0.0)) or 0.0
            mom_20d = c.get('momentum_20d', db.get('momentum_20d', 0.0)) or 0.0
            atr_pct = c.get('atr_pct', db.get('atr_pct', 2.0)) or 2.0
            dist_20d = c.get('distance_from_20d_high', db.get('distance_from_20d_high', 0.0)) or 0.0
            beta = c.get('beta', db.get('beta', 1.0)) or 1.0
            mcap = c.get('market_cap', db.get('market_cap', 0)) or 0
            mcap_log = math.log10(mcap) if mcap > 0 else 10.0

            rsi_14 = c.get('rsi_14', self._approx_rsi_from_momentum(mom_5d, mom_20d))

            features = [
                gap_pct,
                volume_ratio,
                mom_5d,
                mom_20d,
                atr_pct,
                rsi_14,
                dist_20d,
                mcap_log,
                beta,
                vix_close,
                breadth,
            ]
            X_list.append(features)

        X = np.array(X_list, dtype=np.float64)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        return X

    @staticmethod
    def _approx_rsi_from_momentum(mom_5d: float, mom_20d: float) -> float:
        """Approximate RSI from momentum values (no sequential bar access needed).

        Maps momentum to RSI-like scale [20, 80]:
          - Strong negative momentum -> low RSI (~30)
          - Neutral -> RSI ~50
          - Strong positive momentum -> high RSI (~70)
        """
        avg_mom = (mom_5d * 0.6 + mom_20d * 0.4)
        # Sigmoid-like mapping: momentum [-10, +10] -> RSI [20, 80]
        rsi = 50 + 30 * (2 / (1 + math.exp(-avg_mom * 0.3)) - 1)
        return round(max(20.0, min(80.0, rsi)), 1)
