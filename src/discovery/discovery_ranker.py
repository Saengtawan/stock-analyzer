"""
Discovery Ranker — Soft ML ranking for evening Discovery picks by predicted 3-day return.

Sorts all picks by LightGBM-predicted 3-day return and highlights top 3.
Does NOT filter — only sorts + adds rank metadata.

Features (23, all known at scan time, enriched from stock_daily_ohlc):
  Stock-level: predicted_er, atr_5d, beta, momentum_5d, momentum_20d,
               volume_ratio, dist_from_20d_high, close_position, pe_forward, mcap_log
  Relative:    momentum_5d_rank, atr_5d_rank, volume_ratio_rank, dist_from_20d_high_rank
  Macro:       vix_close, breadth, vix_term, breadth_delta_5d, spy_5d_ret
  Context:     day_of_week, is_monday, regime_encoded, day_return

Target: actual_return_d3 from discovery_outcomes

Model: LGBMRegressor persisted as pickle in discovery_ranker_model table.
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

FEATURES = [
    # Stock-level from OHLC (10)
    'predicted_er',          # layer2_score proxy
    'atr_5d',                # real ATR from OHLC (avg 5d range %)
    'beta',
    'momentum_5d',           # 5-day price return %
    'momentum_20d',          # 20-day price return %
    'volume_ratio',          # volume / 20d avg volume
    'dist_from_20d_high',    # % below 20d high
    'close_position',        # where in day's range (0=low, 1=high)
    'pe_forward',
    'mcap_log',
    # Relative within same scan day (4)
    'momentum_5d_rank',
    'atr_5d_rank',
    'volume_ratio_rank',
    'dist_from_20d_high_rank',
    # Macro (5)
    'vix_close',
    'breadth',
    'vix_term',
    'breadth_delta_5d',
    'spy_5d_ret',
    # Context (4)
    'day_of_week',
    'is_monday',
    'regime_encoded',
    'day_return',            # scan-day return %
]

REGIME_MAP = {'BULL': 0, 'STRESS': 1, 'CRISIS': 2}
STRATEGY_MAP = {'DIP': 0, 'RS': 1, 'VALUE': 2, 'OVERSOLD': 3, 'CONTRARIAN': 4, 'GAP': 5}

# SQL CTE that computes per-stock features from stock_daily_ohlc
_ENRICHED_SQL = """
WITH bars AS (
    SELECT symbol, date, close, open, high, low, volume,
           LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
           LAG(close, 5) OVER (PARTITION BY symbol ORDER BY date) as close_5d,
           LAG(close, 20) OVER (PARTITION BY symbol ORDER BY date) as close_20d,
           AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                             ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as avg_vol,
           MAX(high) OVER (PARTITION BY symbol ORDER BY date
                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as high_20d,
           AVG((high - low) / NULLIF(close, 0) * 100) OVER (
               PARTITION BY symbol ORDER BY date
               ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) as atr_5d
    FROM stock_daily_ohlc
    WHERE date >= '2019-12-01'
)
SELECT d.scan_date, d.symbol, d.actual_return_d3, d.sector, d.regime,
       d.predicted_er,
       d.atr_pct as d_atr_pct,
       b.close, b.prev_close,
       (b.close / NULLIF(b.close_5d, 0) - 1) * 100 as momentum_5d,
       (b.close / NULLIF(b.close_20d, 0) - 1) * 100 as momentum_20d,
       b.volume / NULLIF(b.avg_vol, 0) as volume_ratio,
       (b.close / NULLIF(b.high_20d, 0) - 1) * 100 as dist_from_20d_high,
       b.atr_5d,
       (b.close - b.low) / NULLIF(b.high - b.low, 0) as close_position,
       (b.close / NULLIF(b.open, 0) - 1) * 100 as day_return,
       sf.beta, sf.pe_forward, LOG10(NULLIF(sf.market_cap, 0)) as mcap_log,
       m.vix_close as m_vix, d.vix_close as d_vix, m.vix3m_close,
       mb.pct_above_20d_ma as breadth
FROM discovery_outcomes d
JOIN bars b ON d.symbol = b.symbol AND d.scan_date = b.date
LEFT JOIN stock_fundamentals sf ON d.symbol = sf.symbol
LEFT JOIN macro_snapshots m ON d.scan_date = m.date
LEFT JOIN market_breadth mb ON d.scan_date = mb.date
WHERE d.actual_return_d3 IS NOT NULL
  AND d.scan_date <= :max_date
ORDER BY d.scan_date, d.symbol
"""


class DiscoveryRanker:
    """Rank Discovery picks by predicted 3-day return using LightGBM.

    Uses 75K historical outcomes enriched with real per-stock OHLC features
    to learn which picks perform best.
    Soft ranking: all picks shown, sorted by predicted return.
    """

    def __init__(self):
        self._model = None  # LGBMRegressor
        self._scaler = None
        self._fitted = False
        self._fit_date = None
        self._metrics = {}
        self._sector_map = {}  # sector_name -> int encoding
        self._strategy_map = dict(STRATEGY_MAP)

    # ── Public API ──

    def fit(self, max_date: str = None):
        """Train LGBMRegressor on discovery_outcomes. Walk-forward: train on all data before max_date."""
        try:
            from lightgbm import LGBMRegressor
        except ImportError:
            logger.warning("DiscoveryRanker: lightgbm not available, skipping fit")
            return

        max_date = max_date or date.today().isoformat()

        logger.info("DiscoveryRanker: building enriched training data up to %s ...", max_date)

        with get_session() as conn:
            X, y, meta = self._build_training_data(conn, max_date)

        if X is None or len(X) < 500:
            logger.warning("DiscoveryRanker: insufficient training data (%d rows), need >= 500",
                           len(X) if X is not None else 0)
            return

        n = len(X)
        logger.info("DiscoveryRanker: %d samples, %d features, target mean=%.4f, std=%.4f",
                     n, X.shape[1], float(np.mean(y)), float(np.std(y)))

        # Walk-forward split: 80% train / 20% test (time-ordered)
        split_idx = int(n * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        if len(X_train) < 200:
            logger.warning("DiscoveryRanker: too few training samples (%d), skipping", len(X_train))
            return

        # Train LightGBM regressor
        model = LGBMRegressor(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_samples=50,
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
            rank_corr = float(rank_corr) if not np.isnan(rank_corr) else 0.0
        except ImportError:
            rank_corr = float(np.corrcoef(y_test, y_pred_test)[0, 1])
            if np.isnan(rank_corr):
                rank_corr = 0.0

        # Top-3 precision: among test signals where model predicts top 3, what % are actually top 3?
        top3_precision = 0.0
        if len(y_test) >= 6:
            k = min(3, len(y_test) // 2)
            pred_top_k = set(np.argsort(y_pred_test)[-k:])
            actual_top_k = set(np.argsort(y_test)[-k:])
            top_k_overlap = len(pred_top_k & actual_top_k)
            top3_precision = top_k_overlap / k if k > 0 else 0.0

        # Walk-forward daily evaluation: for each test day, rank and measure top-3 vs all
        test_dates = meta['scan_dates'][split_idx:]
        unique_test_dates = sorted(set(test_dates))
        top3_avg_returns = []
        all_avg_returns = []
        daily_rank_corrs = []
        top3_wrs = []
        all_wrs = []

        for d in unique_test_dates:
            mask = [i for i in range(len(y_test)) if test_dates[i] == d]
            if len(mask) < 3:
                continue
            d_y = y_test[mask]
            d_pred = y_pred_test[mask]
            top3_idx = np.argsort(d_pred)[-3:]
            top3_avg_returns.append(float(np.mean(d_y[top3_idx])))
            all_avg_returns.append(float(np.mean(d_y)))
            top3_wrs.append(float(np.mean(d_y[top3_idx] > 0)))
            all_wrs.append(float(np.mean(d_y > 0)))
            try:
                from scipy.stats import spearmanr as _sp
                rc, _ = _sp(d_y, d_pred)
                if not np.isnan(rc):
                    daily_rank_corrs.append(float(rc))
            except Exception:
                pass

        top3_avg = np.mean(top3_avg_returns) if top3_avg_returns else 0.0
        all_avg = np.mean(all_avg_returns) if all_avg_returns else 0.0
        daily_corr_mean = np.mean(daily_rank_corrs) if daily_rank_corrs else 0.0
        top3_wr = np.mean(top3_wrs) if top3_wrs else 0.0
        all_wr = np.mean(all_wrs) if all_wrs else 0.0

        self._metrics = {
            'mae': round(mae, 4),
            'rmse': round(rmse, 4),
            'rank_corr': round(rank_corr, 4),
            'top3_precision': round(top3_precision, 4),
            'top3_avg_ret': round(float(top3_avg), 4),
            'all_avg_ret': round(float(all_avg), 4),
            'top3_lift': round(float(top3_avg - all_avg), 4),
            'top3_wr': round(float(top3_wr), 4),
            'all_wr': round(float(all_wr), 4),
            'wr_lift': round(float(top3_wr - all_wr), 4),
            'daily_rank_corr': round(float(daily_corr_mean), 4),
            'train_n': split_idx,
            'test_n': n - split_idx,
            'test_days': len(unique_test_dates),
            'target_mean': round(float(np.mean(y)), 4),
            'target_std': round(float(np.std(y)), 4),
        }

        # Feature importances
        importances = sorted(zip(FEATURES, model.feature_importances_),
                             key=lambda x: x[1], reverse=True)
        logger.info("DiscoveryRanker: MAE=%.4f, RMSE=%.4f, rank_corr=%.4f, top3_prec=%.2f",
                     mae, rmse, rank_corr, top3_precision)
        logger.info("DiscoveryRanker: top3_avg_ret=%.4f, all_avg_ret=%.4f, lift=%.4f, daily_corr=%.4f",
                     top3_avg, all_avg, top3_avg - all_avg, daily_corr_mean)
        logger.info("DiscoveryRanker: top3_wr=%.1f%%, all_wr=%.1f%%, wr_lift=%.1f%%",
                     top3_wr * 100, all_wr * 100, (top3_wr - all_wr) * 100)
        logger.info("DiscoveryRanker: feature importance (top 10):")
        for fname, imp in importances[:10]:
            logger.info("  %30s: %.0f", fname, imp)

        self._model = model
        self._fitted = True
        self._fit_date = max_date

        self.save_to_db()
        logger.info("DiscoveryRanker: fitted and saved to DB (n=%d, date=%s)", n, max_date)

    def rank(self, picks: list, macro: dict) -> list:
        """Score picks, add _rank_score, sort by predicted return.

        If not fitted, returns picks unchanged (no ranking).
        Top 3 get '_rank_top3' = True for highlighting.
        All picks are kept -- this is soft ranking, not filtering.
        """
        if not self._fitted or self._model is None:
            return picks

        if not picks:
            return picks

        X = self._build_predict_features(picks, macro)
        if X is None or len(X) == 0:
            return picks

        try:
            predictions = self._model.predict(X)
        except Exception as e:
            logger.warning("DiscoveryRanker predict error: %s", e)
            return picks

        # Assign predicted return to each pick
        for i, p in enumerate(picks):
            p._rank_score = round(float(predictions[i]), 4)
            p._rank_predicted_d3 = round(float(predictions[i]), 2)

        # Rank by predicted return (highest first)
        ranked_indices = sorted(range(len(picks)),
                                key=lambda i: predictions[i], reverse=True)

        for rank_pos, idx in enumerate(ranked_indices):
            picks[idx]._rank_position = rank_pos + 1
            picks[idx]._rank_top3 = (rank_pos < 3)

        logger.info("DiscoveryRanker: ranked %d picks, top pred=%.2f%%, bottom=%.2f%%",
                     len(picks),
                     float(predictions[ranked_indices[0]]),
                     float(predictions[ranked_indices[-1]]))

        return picks

    def save_to_db(self):
        """Pickle model + metadata to discovery_ranker_model table."""
        if not self._fitted or self._model is None:
            return

        try:
            model_blob = pickle.dumps(self._model)
            scaler_blob = pickle.dumps(self._scaler) if self._scaler else None
            metrics_json = json.dumps({
                **self._metrics,
                'sector_map': self._sector_map,
                'strategy_map': self._strategy_map,
            })

            with get_session() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS discovery_ranker_model (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fit_date TEXT,
                        model_pickle BLOB,
                        scaler_pickle BLOB,
                        metrics_json TEXT,
                        created_at TEXT DEFAULT (datetime('now'))
                    )
                """))

                conn.execute(text("""
                    INSERT INTO discovery_ranker_model (fit_date, model_pickle, scaler_pickle, metrics_json)
                    VALUES (:fit_date, :model, :scaler, :metrics)
                """), {
                    'fit_date': self._fit_date,
                    'model': model_blob,
                    'scaler': scaler_blob,
                    'metrics': metrics_json,
                })

            logger.info("DiscoveryRanker: saved to DB (fit_date=%s)", self._fit_date)
        except Exception as e:
            logger.error("DiscoveryRanker save_to_db error: %s", e, exc_info=True)

    def load_from_db(self) -> bool:
        """Load latest model from DB. Returns True if loaded successfully."""
        try:
            with get_session() as conn:
                tbl = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='discovery_ranker_model'"
                )).fetchone()
                if not tbl:
                    logger.info("DiscoveryRanker: no model table yet")
                    return False

                row = conn.execute(text("""
                    SELECT fit_date, model_pickle, scaler_pickle, metrics_json
                    FROM discovery_ranker_model
                    ORDER BY id DESC LIMIT 1
                """)).fetchone()

            if not row:
                logger.info("DiscoveryRanker: no saved model found")
                return False

            self._fit_date = row[0]
            self._model = pickle.loads(row[1])
            self._scaler = pickle.loads(row[2]) if row[2] else None
            raw_metrics = json.loads(row[3]) if row[3] else {}
            self._sector_map = raw_metrics.pop('sector_map', {})
            self._strategy_map = raw_metrics.pop('strategy_map', dict(STRATEGY_MAP))
            self._metrics = raw_metrics
            self._fitted = True

            logger.info("DiscoveryRanker: loaded from DB (fit_date=%s, metrics=%s)",
                        self._fit_date, {k: v for k, v in self._metrics.items()
                                         if k in ('rank_corr', 'top3_lift', 'daily_rank_corr',
                                                   'top3_wr', 'wr_lift', 'train_n')})
            return True

        except Exception as e:
            logger.warning("DiscoveryRanker load_from_db error: %s", e)
            return False

    # ── Private: Training Data ──

    def _build_training_data(self, conn, max_date: str):
        """Build feature matrix from discovery_outcomes JOIN stock_daily_ohlc + macro + fundamentals.

        Real per-stock features (momentum, volume_ratio, ATR, close_position, day_return)
        are computed from OHLC bars via SQL window functions rather than being hardcoded to 0.

        Returns (X, y, meta) where meta contains scan_dates for walk-forward eval.
        """
        rows = conn.execute(text(_ENRICHED_SQL), {'max_date': max_date}).fetchall()

        if not rows:
            return None, None, {}

        logger.info("DiscoveryRanker: enriched query returned %d rows", len(rows))

        # Pre-compute SPY 5d returns and breadth delta 5d
        spy_by_date = {}
        macro_rows = conn.execute(text(
            "SELECT date, spy_close FROM macro_snapshots WHERE spy_close IS NOT NULL ORDER BY date"
        )).fetchall()
        for dt, spy in macro_rows:
            spy_by_date[dt] = spy

        breadth_by_date = {}
        breadth_rows = conn.execute(text(
            "SELECT date, pct_above_20d_ma FROM market_breadth WHERE pct_above_20d_ma IS NOT NULL ORDER BY date"
        )).fetchall()
        for dt, b in breadth_rows:
            breadth_by_date[dt] = b

        # Compute 5d lookbacks
        sorted_spy_dates = sorted(spy_by_date.keys())
        spy_5d_ret = {}
        for i, dt in enumerate(sorted_spy_dates):
            if i >= 5:
                prev_dt = sorted_spy_dates[i - 5]
                prev_spy = spy_by_date.get(prev_dt, 0)
                if prev_spy and prev_spy > 0:
                    spy_5d_ret[dt] = (spy_by_date[dt] / prev_spy - 1) * 100
                else:
                    spy_5d_ret[dt] = 0.0
            else:
                spy_5d_ret[dt] = 0.0

        sorted_breadth_dates = sorted(breadth_by_date.keys())
        breadth_delta_5d = {}
        for i, dt in enumerate(sorted_breadth_dates):
            if i >= 5:
                prev_dt = sorted_breadth_dates[i - 5]
                breadth_delta_5d[dt] = breadth_by_date[dt] - breadth_by_date.get(prev_dt, 0)
            else:
                breadth_delta_5d[dt] = 0.0

        # Group rows by scan_date for relative features
        from collections import defaultdict
        date_groups = defaultdict(list)
        for row in rows:
            date_groups[row[0]].append(row)

        # Build feature matrix
        X_list = []
        y_list = []
        scan_dates = []

        for scan_dt in sorted(date_groups.keys()):
            group = date_groups[scan_dt]

            # Extract per-row values for within-day ranking
            mom5ds = [_safe_float(r[9]) for r in group]    # momentum_5d
            atrs = [_safe_float(r[13]) for r in group]     # atr_5d
            vol_ratios = [_safe_float(r[11]) for r in group]  # volume_ratio
            dist_highs = [_safe_float(r[12]) for r in group]  # dist_from_20d_high

            # Compute ranks within the day (0-1 percentile)
            mom5d_ranks = _rank_pct(mom5ds)
            atr_ranks = _rank_pct(atrs)
            vol_ratio_ranks = _rank_pct(vol_ratios)
            dist_high_ranks = _rank_pct(dist_highs)

            for i, row in enumerate(group):
                (scan_date_val, symbol, actual_d3, sector, regime,
                 predicted_er, d_atr_pct, close, prev_close,
                 momentum_5d, momentum_20d, volume_ratio, dist_from_20d_high,
                 atr_5d, close_position, day_return,
                 beta, pe_forward, mcap_log,
                 m_vix, d_vix, vix3m, breadth) = row

                # Use best available VIX
                vix = _safe_float(m_vix, 20.0) or _safe_float(d_vix, 20.0)
                vix3m_val = _safe_float(vix3m, vix)
                vix_term = (vix / vix3m_val) if vix3m_val and vix3m_val > 0 else 1.0

                # Day of week from scan_date
                try:
                    from datetime import datetime as _dt
                    dt_obj = _dt.strptime(scan_date_val, '%Y-%m-%d')
                    dow = dt_obj.weekday()
                except Exception:
                    dow = 2

                # Regime encoding
                regime_enc = REGIME_MAP.get(regime, 1)

                features = [
                    _safe_float(predicted_er),
                    _safe_float(atr_5d, 2.0),
                    _safe_float(beta, 1.0),
                    _safe_float(momentum_5d),
                    _safe_float(momentum_20d),
                    _safe_float(volume_ratio, 1.0),
                    _safe_float(dist_from_20d_high),
                    _safe_float(close_position, 0.5),
                    _safe_float(pe_forward),
                    _safe_float(mcap_log, 10.0),
                    mom5d_ranks[i],
                    atr_ranks[i],
                    vol_ratio_ranks[i],
                    dist_high_ranks[i],
                    vix,
                    _safe_float(breadth, 50.0),
                    vix_term,
                    breadth_delta_5d.get(scan_date_val, 0.0),
                    spy_5d_ret.get(scan_date_val, 0.0),
                    float(dow),
                    1.0 if dow == 0 else 0.0,
                    float(regime_enc),
                    _safe_float(day_return),
                ]

                X_list.append(features)
                y_list.append(actual_d3)
                scan_dates.append(scan_date_val)

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.float32)

        # Replace NaN/Inf
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

        logger.info("DiscoveryRanker: built %d samples, %d features", len(X), X.shape[1])

        meta = {'scan_dates': scan_dates}
        return X, y, meta

    def _build_predict_features(self, picks, macro: dict) -> np.ndarray:
        """Build feature matrix from live picks + macro dict for prediction.

        picks: list of DiscoveryPick objects
        macro: dict with vix_close, vix3m_close, pct_above_20d_ma, etc.
        """
        if not picks:
            return None

        n = len(picks)

        # Extract per-pick values for relative features
        mom5ds = [_safe_float(getattr(p, 'momentum_5d', 0.0)) for p in picks]
        atrs = [_safe_float(getattr(p, 'atr_pct', 0.0)) for p in picks]
        vol_ratios = [_safe_float(getattr(p, 'volume_ratio', 0.0)) for p in picks]
        dist_highs = [_safe_float(getattr(p, 'distance_from_20d_high', 0.0)) for p in picks]

        mom5d_ranks = _rank_pct(mom5ds)
        atr_ranks = _rank_pct(atrs)
        vol_ratio_ranks = _rank_pct(vol_ratios)
        dist_high_ranks = _rank_pct(dist_highs)

        # Macro features
        vix = _safe_float(macro.get('vix_close'), 20.0)
        vix3m = _safe_float(macro.get('vix3m_close'), 20.0)
        vix_term = (vix / vix3m) if vix3m and vix3m > 0 else 1.0
        breadth = _safe_float(macro.get('pct_above_20d_ma'), 50.0)
        breadth_delta = _safe_float(macro.get('breadth_delta_5d'))
        spy_5d = _safe_float(macro.get('spy_5d_ret'))

        # Day of week
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            et_now = datetime.now(ZoneInfo('America/New_York'))
            dow = et_now.weekday()
        except Exception:
            dow = 2

        X_list = []
        for i, p in enumerate(picks):
            # Regime from pick or macro
            regime_str = getattr(p, '_regime', None) or macro.get('regime', 'STRESS')
            regime_enc = REGIME_MAP.get(regime_str, 1)

            mcap = getattr(p, 'market_cap', 0) or 0
            mcap_log = math.log10(mcap) if mcap > 0 else 10.0

            features = [
                _safe_float(getattr(p, 'layer2_score', 0.0)),   # predicted_er
                _safe_float(getattr(p, 'atr_pct', 0.0), 2.0),  # atr_5d
                _safe_float(getattr(p, 'beta', 1.0), 1.0),
                _safe_float(getattr(p, 'momentum_5d', 0.0)),
                _safe_float(getattr(p, 'momentum_20d', 0.0)),
                _safe_float(getattr(p, 'volume_ratio', 0.0), 1.0),
                _safe_float(getattr(p, 'distance_from_20d_high', 0.0)),
                _safe_float(getattr(p, 'close_position', 0.5), 0.5),
                _safe_float(getattr(p, 'pe_forward', 0.0)) if hasattr(p, 'pe_forward') else 0.0,
                mcap_log,
                mom5d_ranks[i],
                atr_ranks[i],
                vol_ratio_ranks[i],
                dist_high_ranks[i],
                vix,
                breadth,
                vix_term,
                breadth_delta,
                spy_5d,
                float(dow),
                1.0 if dow == 0 else 0.0,
                float(regime_enc),
                _safe_float(getattr(p, 'day_return', 0.0)),  # day_return
            ]
            X_list.append(features)

        X = np.array(X_list, dtype=np.float32)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        return X


def _safe_float(val, default: float = 0.0) -> float:
    """Convert value to float, returning default if None/NaN."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _rank_pct(vals: list) -> list:
    """Compute within-group percentile ranks (0-1)."""
    n = len(vals)
    if n <= 1:
        return [0.5] * n
    arr = np.array(vals, dtype=np.float64)
    arr = np.nan_to_num(arr, nan=0.0)
    sorted_idx = np.argsort(arr)
    ranks = np.empty(n)
    for pos, idx in enumerate(sorted_idx):
        ranks[idx] = pos / (n - 1)
    return ranks.tolist()
