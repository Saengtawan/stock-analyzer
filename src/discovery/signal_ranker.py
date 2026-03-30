"""
Signal Ranker — Soft ML ranking for intraday signals by predicted EOD return.

Sorts all signals by LightGBM-predicted same-day return and highlights top 3.
Does NOT filter — only sorts + adds rank metadata.

Features (12, all known before entry):
  gap_pct, prev_day_return, prev_day_range, mcap_log, beta,
  volume_ratio, atr_5d, vix, breadth, consecutive_down_days,
  dist_from_20d_high, sector_encoded

Target: EOD return = (close / open - 1) * 100

Model: LGBMRegressor persisted as pickle in signal_ranker_model table.
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

RANKER_FEATURE_NAMES = [
    'gap_pct',
    'prev_day_return',
    'prev_day_range',
    'mcap_log',
    'beta',
    'volume_ratio',
    'atr_5d',
    'vix',
    'breadth',
    'consecutive_down_days',
    'dist_from_20d_high',
    'sector_encoded',
]


class SignalRanker:
    """Rank intraday signals by predicted EOD return using LightGBM.

    Soft ranking: all signals shown, top 3 highlighted.
    Does NOT filter — only sorts + adds rank info.
    """

    def __init__(self):
        self._model = None
        self._fitted = False
        self._fit_date = None
        self._metrics = {}
        self._sector_map = {}  # sector_name -> int encoding

    # ── Public API ──

    def fit(self, max_date: str = None):
        """Train LGBMRegressor on historical signal returns."""
        try:
            from lightgbm import LGBMRegressor
        except ImportError:
            logger.warning("SignalRanker: lightgbm not available, skipping fit")
            return

        max_date = max_date or date.today().isoformat()

        logger.info("SignalRanker: building training data up to %s ...", max_date)

        with get_session() as conn:
            X, y, self._sector_map = self._build_training_data(conn, max_date)

        if X is None or len(X) < 200:
            logger.warning("SignalRanker: insufficient training data (%d rows), need >= 200",
                           len(X) if X is not None else 0)
            return

        n = len(X)
        logger.info("SignalRanker: %d samples, %d features, target mean=%.3f, std=%.3f",
                     n, X.shape[1], float(np.mean(y)), float(np.std(y)))

        # Walk-forward split: 80% train / 20% test
        split_idx = int(n * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        if len(X_train) < 50:
            logger.warning("SignalRanker: too few training samples (%d), skipping", len(X_train))
            return

        # Train LightGBM regressor
        model = LGBMRegressor(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1,
        )
        model.fit(X_train, y_train)

        # Evaluate
        y_pred_test = model.predict(X_test)
        residuals = y_test - y_pred_test
        mae = float(np.mean(np.abs(residuals)))
        rmse = float(np.sqrt(np.mean(residuals ** 2)))

        # Rank correlation (Spearman)
        try:
            from scipy.stats import spearmanr
            rank_corr, rank_pval = spearmanr(y_test, y_pred_test)
            rank_corr = float(rank_corr)
        except ImportError:
            # Fallback: manual rank correlation
            rank_corr = float(np.corrcoef(y_test, y_pred_test)[0, 1])

        # Top-3 precision: among test signals where model predicts top 3, what % are actually top 3?
        if len(y_test) >= 6:
            k = min(3, len(y_test) // 2)
            pred_top_k = set(np.argsort(y_pred_test)[-k:])
            actual_top_k = set(np.argsort(y_test)[-k:])
            top_k_overlap = len(pred_top_k & actual_top_k)
            top_k_precision = top_k_overlap / k if k > 0 else 0.0
        else:
            top_k_precision = 0.0

        self._metrics = {
            'mae': round(mae, 4),
            'rmse': round(rmse, 4),
            'rank_corr': round(rank_corr, 4),
            'top3_precision': round(top_k_precision, 4),
            'train_n': split_idx,
            'test_n': n - split_idx,
            'target_mean': round(float(np.mean(y)), 4),
            'target_std': round(float(np.std(y)), 4),
        }

        # Feature importances
        importances = sorted(zip(RANKER_FEATURE_NAMES, model.feature_importances_),
                             key=lambda x: x[1], reverse=True)
        logger.info("SignalRanker: MAE=%.4f, RMSE=%.4f, rank_corr=%.4f, top3_prec=%.2f",
                     mae, rmse, rank_corr, top_k_precision)
        logger.info("SignalRanker: feature importance (top 6):")
        for fname, imp in importances[:6]:
            logger.info("  %25s: %.4f", fname, imp)

        self._model = model
        self._fitted = True
        self._fit_date = max_date

        self.save_to_db()
        logger.info("SignalRanker: fitted and saved to DB (n=%d, date=%s)", n, max_date)

    def rank(self, signals: list, macro: dict) -> list:
        """Add '_ml_rank', '_ml_predicted_return', '_ml_top3' to each signal.

        If not fitted, returns signals unchanged (no ranking).
        Top 3 get '_ml_top3' = True for highlighting.
        All signals are kept — this is soft ranking, not filtering.
        """
        if not self._fitted or self._model is None:
            return signals

        if not signals:
            return signals

        X = self._build_predict_features(signals, macro)
        if X is None or len(X) == 0:
            return signals

        try:
            predictions = self._model.predict(X)
        except Exception as e:
            logger.warning("SignalRanker predict error: %s", e)
            return signals

        # Assign predicted return to each signal
        for i, s in enumerate(signals):
            s['_ml_predicted_return'] = round(float(predictions[i]), 2)

        # Rank by predicted return (highest first)
        ranked_indices = sorted(range(len(signals)),
                                key=lambda i: predictions[i], reverse=True)

        for rank_pos, idx in enumerate(ranked_indices):
            signals[idx]['_ml_rank'] = rank_pos + 1
            signals[idx]['_ml_top3'] = (rank_pos < 3)

        return signals

    def save_to_db(self):
        """Pickle model + metadata to signal_ranker_model table."""
        if not self._fitted or self._model is None:
            return

        try:
            model_blob = pickle.dumps(self._model)
            metrics_json = json.dumps({
                **self._metrics,
                'sector_map': self._sector_map,
            })

            with get_session() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS signal_ranker_model (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fit_date TEXT,
                        model_pickle BLOB,
                        metrics_json TEXT,
                        created_at TEXT DEFAULT (datetime('now'))
                    )
                """))

                conn.execute(text("""
                    INSERT INTO signal_ranker_model (fit_date, model_pickle, metrics_json)
                    VALUES (:fit_date, :model, :metrics)
                """), {
                    'fit_date': self._fit_date,
                    'model': model_blob,
                    'metrics': metrics_json,
                })

            logger.info("SignalRanker: saved to DB (fit_date=%s)", self._fit_date)
        except Exception as e:
            logger.error("SignalRanker save_to_db error: %s", e, exc_info=True)

    def load_from_db(self) -> bool:
        """Load latest model from DB. Returns True if loaded successfully."""
        try:
            with get_session() as conn:
                tbl = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='signal_ranker_model'"
                )).fetchone()
                if not tbl:
                    logger.info("SignalRanker: no model table yet")
                    return False

                row = conn.execute(text("""
                    SELECT fit_date, model_pickle, metrics_json
                    FROM signal_ranker_model
                    ORDER BY id DESC LIMIT 1
                """)).fetchone()

            if not row:
                logger.info("SignalRanker: no saved model found")
                return False

            self._fit_date = row[0]
            self._model = pickle.loads(row[1])
            raw_metrics = json.loads(row[2]) if row[2] else {}
            self._sector_map = raw_metrics.pop('sector_map', {})
            self._metrics = raw_metrics
            self._fitted = True

            logger.info("SignalRanker: loaded from DB (fit_date=%s, metrics=%s)",
                        self._fit_date, self._metrics)
            return True

        except Exception as e:
            logger.warning("SignalRanker load_from_db error: %s", e)
            return False

    # ── Private: Training Data ──

    def _build_training_data(self, conn, max_date: str):
        """Build feature matrix + target from historical gap-down bounce days.

        Uses stock_daily_ohlc with window functions for features.
        Joins macro_snapshots (VIX), market_breadth, stock_fundamentals.
        Target: (close / open - 1) * 100 (same-day return).

        Returns (X, y, sector_map) or (None, None, {}).
        """
        # Main OHLC data with window features
        rows = conn.execute(text("""
            WITH bars AS (
                SELECT symbol, date, open, close, high, low, volume,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
                       LAG(open) OVER (PARTITION BY symbol ORDER BY date) as prev_open,
                       LAG(high) OVER (PARTITION BY symbol ORDER BY date) as prev_high,
                       LAG(low) OVER (PARTITION BY symbol ORDER BY date) as prev_low,
                       LAG(volume) OVER (PARTITION BY symbol ORDER BY date) as prev_volume,
                       LAG(close, 2) OVER (PARTITION BY symbol ORDER BY date) as prev2_close,
                       AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as avg_vol_20d,
                       MAX(high) OVER (PARTITION BY symbol ORDER BY date
                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as high_20d,
                       AVG((high - low) / NULLIF(close, 0) * 100) OVER (
                           PARTITION BY symbol ORDER BY date
                           ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) as atr_5d
                FROM stock_daily_ohlc
                WHERE date >= '2020-01-01' AND date <= :max_date
                  AND open > 0 AND close > 5
            )
            SELECT b.symbol, b.date, b.open, b.close, b.high, b.low, b.volume,
                   b.prev_close, b.prev_open, b.prev_high, b.prev_low, b.prev_volume,
                   b.prev2_close, b.avg_vol_20d, b.high_20d, b.atr_5d,
                   sf.beta, sf.market_cap, sf.sector
            FROM bars b
            LEFT JOIN stock_fundamentals sf ON b.symbol = sf.symbol
            WHERE b.date >= '2020-01-01' AND b.date <= :max_date
              AND b.prev_close IS NOT NULL AND b.prev_close > 0
              AND b.avg_vol_20d IS NOT NULL AND b.avg_vol_20d > 0
              AND b.prev2_close IS NOT NULL AND b.prev2_close > 0
              AND (b.open / b.prev_close - 1) * 100 < -2.0
              AND b.close > b.open
            ORDER BY b.date, b.symbol
        """), {'max_date': max_date}).mappings().fetchall()

        if not rows:
            logger.warning("SignalRanker: no training rows found")
            return None, None, {}

        logger.info("SignalRanker: %d gap-down bounce days loaded", len(rows))

        # Load macro lookup: {date -> {vix, breadth}}
        macro_rows = conn.execute(text("""
            SELECT ms.date, ms.vix_close, mb.pct_above_20d_ma
            FROM macro_snapshots ms
            LEFT JOIN market_breadth mb ON ms.date = mb.date
            WHERE ms.date >= '2020-01-01' AND ms.date <= :max_date
        """), {'max_date': max_date}).mappings().fetchall()

        macro_lookup = {}
        for m in macro_rows:
            macro_lookup[m['date']] = {
                'vix': m['vix_close'] or 20.0,
                'breadth': m['pct_above_20d_ma'] or 50.0,
            }

        # Build sector encoding
        all_sectors = sorted(set(r['sector'] or 'Unknown' for r in rows))
        sector_map = {s: i for i, s in enumerate(all_sectors)}

        # Count consecutive down days per (symbol, date)
        # Group rows by symbol first, then count backward
        from collections import defaultdict
        symbol_dates = defaultdict(list)
        for r in rows:
            symbol_dates[r['symbol']].append(r)

        # Pre-load consecutive down day counts from OHLC
        # This is expensive per-row, so we compute a lookup
        consec_down_lookup = self._compute_consecutive_down_days(conn, max_date)

        X_list = []
        y_list = []

        for r in rows:
            prev_close = r['prev_close']
            prev_open = r['prev_open'] or prev_close
            prev_high = r['prev_high'] or prev_close
            prev_low = r['prev_low'] or prev_close
            prev2_close = r['prev2_close']

            gap_pct = (r['open'] / prev_close - 1) * 100
            prev_day_return = (prev_close / prev2_close - 1) * 100
            prev_day_range = (prev_high - prev_low) / prev_close * 100 if prev_close > 0 else 0.0
            mcap_log = math.log10(r['market_cap']) if r['market_cap'] and r['market_cap'] > 0 else 10.0
            beta = r['beta'] or 1.0
            volume_ratio = (r['prev_volume'] / r['avg_vol_20d']
                            if r['prev_volume'] and r['avg_vol_20d'] and r['avg_vol_20d'] > 0
                            else 1.0)
            atr_5d = r['atr_5d'] or 2.0

            macro_day = macro_lookup.get(r['date'], {})
            vix = macro_day.get('vix', 20.0)
            breadth = macro_day.get('breadth', 50.0)

            consec_down = consec_down_lookup.get((r['symbol'], r['date']), 0)

            dist_20d_high = ((prev_close / r['high_20d'] - 1) * 100
                             if r['high_20d'] and r['high_20d'] > 0
                             else 0.0)

            sector = r['sector'] or 'Unknown'
            sector_enc = sector_map.get(sector, 0)

            features = [
                gap_pct,
                prev_day_return,
                prev_day_range,
                mcap_log,
                beta,
                volume_ratio,
                atr_5d,
                vix,
                breadth,
                consec_down,
                dist_20d_high,
                sector_enc,
            ]

            # Target: same-day return (close / open - 1) * 100
            target = (r['close'] / r['open'] - 1) * 100

            X_list.append(features)
            y_list.append(target)

        X = np.array(X_list, dtype=np.float64)
        y = np.array(y_list, dtype=np.float64)

        # Handle NaN/inf
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

        return X, y, sector_map

    def _compute_consecutive_down_days(self, conn, max_date: str) -> dict:
        """Compute consecutive down days for each (symbol, date) pair.

        Returns dict[(symbol, date)] -> int count of consecutive prior close < prev_close.
        Uses a window query + Python counting for accuracy.
        """
        lookup = {}

        try:
            # Load recent close data grouped by symbol to count streaks
            rows = conn.execute(text("""
                SELECT symbol, date, close,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close
                FROM stock_daily_ohlc
                WHERE date >= '2019-06-01' AND date <= :max_date
                  AND close > 0
                ORDER BY symbol, date
            """), {'max_date': max_date}).fetchall()

            if not rows:
                return lookup

            current_sym = None
            streak = 0

            for row in rows:
                sym, dt, close, prev_close = row[0], row[1], row[2], row[3]

                if sym != current_sym:
                    current_sym = sym
                    streak = 0
                    continue

                if prev_close and prev_close > 0 and close < prev_close:
                    streak += 1
                else:
                    streak = 0

                lookup[(sym, dt)] = streak

        except Exception as e:
            logger.warning("SignalRanker: consecutive_down_days computation error: %s", e)

        return lookup

    def _build_predict_features(self, signals: list, macro: dict) -> np.ndarray:
        """Build feature matrix for live prediction from signal dicts + macro.

        Handles missing features gracefully with defaults.
        """
        if not signals:
            return None

        vix = macro.get('vix', macro.get('vix_close', 20.0)) or 20.0
        breadth = macro.get('breadth', macro.get('pct_above_20d_ma', 50.0)) or 50.0

        # Enrich signals that need DB features
        symbols_need_db = [s['symbol'] for s in signals
                           if 'prev_day_return' not in s or s.get('prev_day_return') is None]

        db_features = {}
        if symbols_need_db:
            try:
                db_features = self._load_db_features(symbols_need_db)
            except Exception as e:
                logger.warning("SignalRanker: DB feature load error: %s", e)

        X_list = []
        for s in signals:
            sym = s['symbol']
            db = db_features.get(sym, {})

            gap_pct = s.get('gap_pct', 0.0)
            prev_day_return = s.get('prev_day_return', db.get('prev_day_return', 0.0))
            prev_day_range = s.get('prev_day_range', db.get('prev_day_range', 2.0))
            mcap_log = s.get('mcap_log', db.get('mcap_log', 10.0))
            beta = s.get('beta', db.get('beta', 1.0))
            volume_ratio = s.get('volume_ratio', db.get('volume_ratio', 1.0))
            atr_5d = s.get('atr_5d', db.get('atr_5d', 2.0))
            consec_down = s.get('consecutive_down_days', db.get('consecutive_down_days', 0))
            dist_20d_high = s.get('dist_from_20d_high', db.get('dist_from_20d_high', 0.0))

            sector = s.get('sector', db.get('sector', 'Unknown'))
            sector_enc = self._sector_map.get(sector, 0)

            features = [
                gap_pct,
                prev_day_return,
                prev_day_range,
                mcap_log,
                beta,
                volume_ratio,
                atr_5d,
                vix,
                breadth,
                consec_down,
                dist_20d_high,
                sector_enc,
            ]
            X_list.append(features)

        X = np.array(X_list, dtype=np.float64)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        return X

    def _load_db_features(self, symbols: list) -> dict:
        """Load features from DB for symbols that don't have them in the signal dict.

        Returns {symbol: {prev_day_return, prev_day_range, mcap_log, beta, ...}}.
        """
        result = {}
        if not symbols:
            return result

        with get_session() as conn:
            for sym in symbols:
                try:
                    row = conn.execute(text("""
                        WITH bars AS (
                            SELECT close, high, low, volume, open,
                                   LAG(close) OVER (ORDER BY date) as prev_close,
                                   LAG(high) OVER (ORDER BY date) as prev_high,
                                   LAG(low) OVER (ORDER BY date) as prev_low,
                                   LAG(volume) OVER (ORDER BY date) as prev_volume,
                                   AVG(volume) OVER (ORDER BY date
                                       ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as avg_vol_20d,
                                   MAX(high) OVER (ORDER BY date
                                       ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as high_20d,
                                   AVG((high - low) / NULLIF(close, 0) * 100) OVER (
                                       ORDER BY date
                                       ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) as atr_5d
                            FROM stock_daily_ohlc
                            WHERE symbol = :sym
                            ORDER BY date DESC LIMIT 5
                        )
                        SELECT close, prev_close, prev_high, prev_low, prev_volume,
                               avg_vol_20d, high_20d, atr_5d
                        FROM bars
                        WHERE prev_close IS NOT NULL
                        LIMIT 1
                    """), {'sym': sym}).fetchone()

                    if not row:
                        continue

                    close, prev_close, prev_high, prev_low, prev_volume, avg_vol_20d, high_20d, atr_5d = row

                    prev_day_return = ((close / prev_close - 1) * 100
                                       if prev_close and prev_close > 0 else 0.0)
                    prev_day_range = (((prev_high or close) - (prev_low or close)) / close * 100
                                      if close and close > 0 else 2.0)
                    volume_ratio = ((prev_volume / avg_vol_20d)
                                    if prev_volume and avg_vol_20d and avg_vol_20d > 0
                                    else 1.0)
                    dist_20d_high = ((close / high_20d - 1) * 100
                                     if high_20d and high_20d > 0 else 0.0)

                    # Fundamentals
                    fund_row = conn.execute(text("""
                        SELECT market_cap, beta, sector
                        FROM stock_fundamentals
                        WHERE symbol = :sym
                    """), {'sym': sym}).fetchone()

                    mcap_log = 10.0
                    beta = 1.0
                    sector = 'Unknown'
                    if fund_row:
                        mcap_log = (math.log10(fund_row[0])
                                    if fund_row[0] and fund_row[0] > 0 else 10.0)
                        beta = fund_row[1] or 1.0
                        sector = fund_row[2] or 'Unknown'

                    # Consecutive down days (simplified: check last 5 bars)
                    consec_rows = conn.execute(text("""
                        SELECT close, LAG(close) OVER (ORDER BY date) as prev_close
                        FROM stock_daily_ohlc
                        WHERE symbol = :sym
                        ORDER BY date DESC LIMIT 10
                    """), {'sym': sym}).fetchall()

                    consec_down = 0
                    for cr in consec_rows:
                        if cr[1] and cr[1] > 0 and cr[0] < cr[1]:
                            consec_down += 1
                        else:
                            break

                    result[sym] = {
                        'prev_day_return': prev_day_return,
                        'prev_day_range': prev_day_range,
                        'mcap_log': mcap_log,
                        'beta': beta,
                        'volume_ratio': volume_ratio,
                        'atr_5d': atr_5d or 2.0,
                        'consecutive_down_days': consec_down,
                        'dist_from_20d_high': dist_20d_high,
                        'sector': sector,
                    }

                except Exception as e:
                    logger.debug("SignalRanker: failed to load DB features for %s: %s", sym, e)

        return result
