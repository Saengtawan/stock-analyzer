"""
Adaptive Stock Selector — v17 Layer 2.

Replaces ALL hardcoded strategy functions (DIP, OVERSOLD, VALUE, CONTRARIAN,
VOL_U, RS) with a single learned model that predicts 5d positive return.

Model: LogisticRegression (primary, <1s fit) or LightGBM (fallback if AUC<0.52).
Features (13): momentum_5d, momentum_20d, volume_ratio, beta, atr_pct, rsi,
  d20h, pe_forward, mcap_log, sector_score, vix, breadth, crude_delta_5d.
Target: 5d forward return > 0 (binary).

Training data: stock_daily_ohlc (1.5M rows, 15-month window).
Walk-forward: 60d rolling retrain.

No strategy labels — just: "given these features in this context, probability = X%"
"""
import logging
from database.orm.base import get_session
from sqlalchemy import text
import time
import pickle
import json
from discovery.multi_strategy import classify_regime, classify_strategy, PC_BULLISH, PC_BEARISH
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

FEATURES = [
    # Stock-level (9)
    'momentum_5d', 'momentum_20d', 'volume_ratio', 'beta', 'atr_pct',
    'rsi', 'd20h', 'pe_forward', 'mcap_log',
    # Stock context (3) — raw sensitivities, ML decides if good/bad
    'stock_news_sent', 'crude_sensitivity', 'vix_sensitivity',
    # Sector (3) — raw, no contrarian manipulation
    'sector_mom_1d', 'sector_news_sent', 'sector_analyst_net',
    # Market (7) — broad market state
    'vix', 'breadth', 'crude_delta_5d',
    'vix_spread', 'breadth_delta_5d', 'spy_5d_ret', 'n_sectors_up',
    # Context (2) — learned
    'strat_sharpe', 'cluster_health',
]

MAX_TRAIN_ROWS = 200_000  # cap to keep fit time <5s
MIN_TRAIN_ROWS = 5000
MIN_AUC = 0.52            # minimum acceptable AUC
AUC_GUARD = 0.02          # new model must be within this of old AUC


GAP_FEATURES = [
    'momentum_5d', 'd20h', 'volume_ratio', 'atr_pct', 'beta',
    'vix', 'breadth', 'vix_spread',
    'd0_ret', 'close_pos', 'vol_vs_avg', 'lower_shadow', 'body_size',
]


class AdaptiveStockSelector:
    """Learned stock selection — replaces hardcoded strategies."""

    def __init__(self):
        self._model = None
        self._feature_names = FEATURES
        self._feature_means = None
        self._feature_stds = None
        self._auc = 0.0
        self._n_train = 0
        # v17: Gap predictor (evening scan → filter gap-up stocks)
        self._gap_model = None
        self._gap_means = None
        self._gap_stds = None
        self._gap_auc = 0.0
        self._feature_importance = {}
        self._fitted = False
        self._fit_time = 0.0
        self._ensure_tables()

    def fit(self, max_date=None, sector_scorer=None) -> bool:
        """Train stock selection model on historical data.

        Args:
            max_date: walk-forward cutoff
            sector_scorer: SectorScorer for computing sector_score feature
        """
        t0 = time.time()
        old_auc = self._auc

        # Load and compute features
        X, y, feature_names = self._build_training_data(max_date, sector_scorer)
        if X is None or len(X) < MIN_TRAIN_ROWS:
            logger.warning("AdaptiveStockSelector: insufficient data (%s rows)",
                           len(X) if X is not None else 0)
            return False

        logger.info("AdaptiveStockSelector: training on %d rows, %d features",
                     len(X), len(feature_names))

        # Imputation: replace NaN with column mean
        self._feature_means = np.nanmean(X, axis=0)
        self._feature_stds = np.nanstd(X, axis=0)
        self._feature_stds[self._feature_stds < 1e-10] = 1.0

        X_clean = np.where(np.isnan(X), self._feature_means, X)
        # Z-score normalize
        X_norm = (X_clean - self._feature_means) / self._feature_stds

        # Split for validation (last 20% as OOS)
        split = int(len(X_norm) * 0.8)
        X_train, X_val = X_norm[:split], X_norm[split:]
        y_train, y_val = y[:split], y[split:]

        # Try LogisticRegression first
        model, auc = self._fit_logistic(X_train, y_train, X_val, y_val)

        # Fallback to LightGBM if LR underperforms
        if auc < MIN_AUC:
            lgb_model, lgb_auc = self._fit_lgbm(X_train, y_train, X_val, y_val)
            if lgb_auc > auc:
                model, auc = lgb_model, lgb_auc
                logger.info("AdaptiveStockSelector: LightGBM AUC=%.4f > LR AUC", lgb_auc)

        # Guard: don't regress
        if old_auc > 0 and auc < old_auc - AUC_GUARD:
            logger.warning("AdaptiveStockSelector: new AUC=%.4f < old=%.4f — keeping old model",
                           auc, old_auc)
            return True  # keep old model, still "fitted"

        self._model = model
        self._auc = auc
        self._n_train = len(X_train)
        self._feature_names = feature_names

        # Feature importance
        try:
            if hasattr(model, 'coef_'):
                coefs = model.coef_[0]
                self._feature_importance = {
                    f: round(float(abs(c)), 4)
                    for f, c in zip(feature_names, coefs)
                }
            elif hasattr(model, 'feature_importances_'):
                imps = model.feature_importances_
                self._feature_importance = {
                    f: round(float(i), 4)
                    for f, i in zip(feature_names, imps)
                }
        except Exception:
            pass

        # v17: Train gap predictor (evening features → next day gap up?)
        self._fit_gap_model(X, y, feature_names)

        self._fitted = True
        self._fit_time = time.time()
        self.save_to_db()

        elapsed = time.time() - t0
        logger.info("AdaptiveStockSelector: fitted in %.1fs — AUC=%.4f gap_AUC=%.4f n=%d",
                     elapsed, auc, self._gap_auc, self._n_train)
        return True

    def _fit_gap_model(self, X_outcome, y_outcome, feature_names):
        """Train gap predictor from same training data.
        Uses D0 candle features to predict gap_up (next day open > today close).
        """
        try:
            from sklearn.linear_model import LogisticRegression as LR
            from sklearn.preprocessing import StandardScaler as SS
            from sklearn.metrics import roc_auc_score as auc_score

            with get_session() as session:
                rows = session.execute(text('''
                    SELECT b.momentum_5d, b.distance_from_20d_high, b.volume_ratio, b.atr_pct,
                           d0.open, d0.high, d0.low, d0.close, d0.volume,
                           d1.open as d1o,
                           COALESCE(m.vix_close, 20), COALESCE(m.vix3m_close, 22),
                           COALESCE(mb.pct_above_20d_ma, 50),
                           COALESCE(sf.beta, 1), COALESCE(sf.avg_volume, 1)
                    FROM backfill_signal_outcomes b
                    JOIN signal_daily_bars d0 ON b.scan_date=d0.scan_date AND b.symbol=d0.symbol AND d0.day_offset=0
                    JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
                    LEFT JOIN macro_snapshots m ON b.scan_date = m.date
                    LEFT JOIN market_breadth mb ON b.scan_date = mb.date
                    LEFT JOIN stock_fundamentals sf ON b.symbol = sf.symbol
                    WHERE d0.close > 0 AND d1.open > 0 AND d0.open > 0 AND d0.high > d0.low
                    AND sf.avg_volume > 0 AND m.vix_close IS NOT NULL
                    ORDER BY b.scan_date
                ''')).fetchall()

            if len(rows) < 5000:
                logger.warning("Gap model: not enough data (%d)", len(rows))
                return

            X_gap = []; y_gap = []
            for r in rows:
                mom5,d20h,vol,atr,d0o,d0h,d0l,d0c,d0v,d1o,vix,vix3m,breadth,beta,avg_vol = r
                d0_range = d0h - d0l
                X_gap.append([
                    mom5 or 0, d20h or 0, vol or 1, atr, beta,
                    vix, breadth, vix - vix3m,
                    (d0c/d0o - 1)*100,              # d0_ret
                    (d0c - d0l)/d0_range,            # close_pos
                    d0v/avg_vol,                     # vol_vs_avg
                    (min(d0o,d0c)-d0l)/d0_range,     # lower_shadow
                    abs(d0c-d0o)/d0o*100,            # body_size
                ])
                y_gap.append(1 if d1o/d0c > 1.0 else 0)  # gap up = open > close

            X_g = np.array(X_gap); y_g = np.array(y_gap)
            split = int(len(X_g) * 0.8)
            self._gap_means = np.nanmean(X_g[:split], axis=0)
            self._gap_stds = np.nanstd(X_g[:split], axis=0)
            self._gap_stds[self._gap_stds < 1e-10] = 1.0

            X_gn = (X_g - self._gap_means) / self._gap_stds
            mdl = LR(max_iter=200).fit(X_gn[:split], y_g[:split])
            probs = mdl.predict_proba(X_gn[split:])[:,1]
            self._gap_auc = round(auc_score(y_g[split:], probs), 4)
            self._gap_model = mdl

            logger.info("Gap model: AUC=%.4f on %d signals", self._gap_auc, len(rows))
        except Exception as e:
            logger.error("Gap model fit error: %s", e)
            self._gap_auc = 0.0

    def predict_gap(self, candidate):
        """Predict gap-up probability for a single candidate.
        Uses D0 candle features available at evening scan.
        Returns float probability 0-1, or 0.5 if model not fitted.
        """
        if not self._gap_model or self._gap_means is None:
            return 0.5
        try:
            c = candidate
            d0o = c.get('open', c['close'])
            d0h = c.get('day_high', c['close'])
            d0l = c.get('day_low', c['close'])
            d0c = c['close']
            d0v = c.get('volume', 0) or 0
            avg_vol = c.get('avg_volume', 1) or 1
            d0_range = d0h - d0l
            if d0_range <= 0 or d0o <= 0: return 0.5

            vix = c.get('vix_close') or c.get('vix_at_signal') or 20
            vix3m = c.get('vix3m_close') or (vix * 1.05)
            breadth = c.get('pct_above_20d_ma') or 50

            feat = np.array([[
                c.get('momentum_5d') or 0,
                c.get('distance_from_20d_high') or 0,
                c.get('volume_ratio') or 1,
                c.get('atr_pct') or 3,
                c.get('beta') or 1,
                vix, breadth, vix - vix3m,
                (d0c/d0o - 1)*100,
                (d0c - d0l)/d0_range,
                d0v/avg_vol if avg_vol > 0 else 1,
                (min(d0o,d0c) - d0l)/d0_range,
                abs(d0c - d0o)/d0o*100,
            ]])
            feat = (feat - self._gap_means) / self._gap_stds
            return float(self._gap_model.predict_proba(feat)[0, 1])
        except Exception:
            return 0.5

    def predict(self, candidates, sector_scores=None, context_map=None):
        """Score each candidate by learned model.

        Args:
            candidates: list of candidate dicts
            sector_scores: {sector: score} from SectorScorer
            context_map: {symbol: {smart_er, strat_sharpe, sect_sharpe}}

        Returns:
            list of (probability, candidate) sorted by probability desc.
        """
        if not self._fitted or self._model is None:
            return []

        sector_scores = sector_scores or {}
        context_map = context_map or {}

        # Build feature matrix
        X = []
        valid_candidates = []
        for c in candidates:
            ctx = context_map.get(c.get('symbol', ''), {})
            row = self._extract_features(c, sector_scores, context=ctx)
            if row is not None:
                X.append(row)
                valid_candidates.append(c)

        if not X:
            return []

        X = np.array(X, dtype=np.float64)

        # Impute and normalize (same as training)
        X = np.where(np.isnan(X), self._feature_means, X)
        X = (X - self._feature_means) / self._feature_stds

        # Predict probabilities
        try:
            probs = self._model.predict_proba(X)[:, 1]
        except Exception as e:
            logger.error("AdaptiveStockSelector: predict error: %s", e)
            return []

        # Return sorted by probability
        results = [(float(prob), cand) for prob, cand in zip(probs, valid_candidates)]
        results.sort(key=lambda x: x[0], reverse=True)
        return results

    def needs_refit(self, days=30) -> bool:
        if not self._fitted:
            return True
        return (time.time() - self._fit_time) > days * 86400

    # === Model Training ===

    def _fit_logistic(self, X_train, y_train, X_val, y_val):
        """Fit LogisticRegression. Returns (model, auc)."""
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score

        model = LogisticRegression(
            C=1.0, max_iter=200, solver='lbfgs', random_state=42)
        model.fit(X_train, y_train)

        try:
            y_pred = model.predict_proba(X_val)[:, 1]
            auc = roc_auc_score(y_val, y_pred)
        except Exception:
            auc = 0.5

        logger.info("AdaptiveStockSelector: LogisticRegression AUC=%.4f", auc)
        return model, round(auc, 4)

    def _fit_lgbm(self, X_train, y_train, X_val, y_val):
        """Fit LightGBM as fallback. Returns (model, auc)."""
        try:
            import lightgbm as lgb
            from sklearn.metrics import roc_auc_score

            model = lgb.LGBMClassifier(
                n_estimators=100, max_depth=5, learning_rate=0.1,
                min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                random_state=42, verbose=-1)
            model.fit(X_train, y_train)

            y_pred = model.predict_proba(X_val)[:, 1]
            auc = roc_auc_score(y_val, y_pred)
            logger.info("AdaptiveStockSelector: LightGBM AUC=%.4f", auc)
            return model, round(auc, 4)

        except ImportError:
            logger.info("AdaptiveStockSelector: LightGBM not available, using LR only")
            return None, 0.0
        except Exception as e:
            logger.error("AdaptiveStockSelector: LightGBM fit error: %s", e)
            return None, 0.0

    # === Feature Engineering ===

    def _build_training_data(self, max_date, sector_scorer):
        """Build (X, y) from stock_daily_ohlc + macro + sector.

        Returns (X: np.array, y: np.array, feature_names: list).
        """
        with get_session() as session:
            session.execute(text('PRAGMA busy_timeout=5000'))

            date_filter = f"AND s.date <= '{max_date}'" if max_date else ""

            # Load OHLCV + fundamentals + macro in one query
            rows = session.execute(text(f"""
                SELECT s.symbol, s.date, s.close, s.high, s.low, s.volume,
                       sf.beta, sf.pe_forward, sf.market_cap, sf.avg_volume, sf.sector,
                       m.vix_close, m.crude_close,
                       mb.pct_above_20d_ma
                FROM stock_daily_ohlc s
                JOIN stock_fundamentals sf ON s.symbol = sf.symbol
                LEFT JOIN macro_snapshots m ON s.date = m.date
                LEFT JOIN market_breadth mb ON s.date = mb.date
                WHERE s.close > 0
                  AND sf.market_cap > 3e9
                  AND sf.avg_volume > 100000
                  AND s.date >= date('now', '-15 months')
                  {date_filter}
                  AND m.vix_close IS NOT NULL
                ORDER BY s.symbol, s.date
            """)).fetchall()

            # v17: Load additional raw features for 25-feature model
            # Sector ETF daily returns (sector_mom_1d)
            sector_mom_map = {}
            try:
                for r in session.execute(text("""
                    SELECT date, sector, pct_change FROM sector_etf_daily_returns
                    WHERE sector IS NOT NULL AND sector NOT IN ('S&P 500','US Dollar','Treasury Long','Gold')
                """)).fetchall():
                    sector_mom_map[(r[0], r[1])] = r[2] or 0
            except Exception: pass

            # News sentiment per sector (7d rolling avg)
            sector_news_map = {}
            try:
                for r in session.execute(text("""
                    SELECT sf.sector, ne.scan_date_et,
                           AVG(ne.sentiment_score) as avg_sent
                    FROM news_events ne
                    JOIN stock_fundamentals sf ON ne.symbol = sf.symbol
                    WHERE ne.sentiment_score IS NOT NULL AND ne.scan_date_et IS NOT NULL
                    GROUP BY sf.sector, ne.scan_date_et
                """)).fetchall():
                    sector_news_map[(r[1], r[0])] = r[2] or 0
            except Exception: pass

            # Analyst net per sector per date
            sector_analyst_map = {}
            try:
                for r in session.execute(text("""
                    SELECT sf.sector, arh.date,
                        SUM(CASE WHEN arh.price_target > arh.prior_price_target*1.05 AND arh.prior_price_target>0 THEN 1 ELSE 0 END) -
                        SUM(CASE WHEN arh.price_target < arh.prior_price_target*0.95 AND arh.prior_price_target>0 THEN 1 ELSE 0 END) as net
                    FROM analyst_ratings_history arh
                    JOIN stock_fundamentals sf ON arh.symbol = sf.symbol
                    WHERE arh.price_target > 0
                    GROUP BY sf.sector, arh.date
                """)).fetchall():
                    sector_analyst_map[(r[1], r[0])] = r[2] or 0
            except Exception: pass

            # Stock context (crude/VIX sensitivity)
            crude_sens_map = {}
            vix_sens_map = {}
            try:
                for r in session.execute(text("SELECT symbol, context_type, score FROM stock_context WHERE context_type IN ('CRUDE_SENSITIVE','VIX_SENSITIVE')")).fetchall():
                    if r[1] == 'CRUDE_SENSITIVE': crude_sens_map[r[0]] = r[2] or 0
                    else: vix_sens_map[r[0]] = r[2] or 0
            except Exception: pass

            # N sectors up per date
            n_sectors_up_map = {}
            try:
                for r in session.execute(text("""
                    SELECT date, SUM(CASE WHEN pct_change > 0 THEN 1 ELSE 0 END) as n_up
                    FROM sector_etf_daily_returns
                    WHERE sector NOT IN ('S&P 500','US Dollar','Treasury Long','Gold') AND sector IS NOT NULL
                    GROUP BY date
                """)).fetchall():
                    n_sectors_up_map[r[0]] = r[1] or 0
            except Exception: pass

            # SPY 5d return + breadth delta + VIX spread per date
            macro_extra_map = {}
            try:
                mrows = session.execute(text("""
                    SELECT m.date, m.vix_close, m.vix3m_close, m.spy_close,
                           mb.pct_above_20d_ma
                    FROM macro_snapshots m
                    LEFT JOIN market_breadth mb ON m.date = mb.date
                    WHERE m.vix_close IS NOT NULL
                    ORDER BY m.date
                """)).fetchall()
                for idx, r in enumerate(mrows):
                    vix_spread = (r[1] - r[2]) if r[1] and r[2] else 0
                    spy_5d = ((r[3] / mrows[idx-5][3]) - 1) * 100 if idx >= 5 and mrows[idx-5][3] and r[3] else 0
                    breadth_d5 = (r[4] - mrows[idx-5][4]) if idx >= 5 and r[4] and mrows[idx-5][4] else 0
                    macro_extra_map[r[0]] = {'vix_spread': vix_spread, 'spy_5d': spy_5d, 'breadth_d5': breadth_d5}
            except Exception: pass

            # News sentiment per stock (7d)
            stock_news_map = {}
            try:
                for r in session.execute(text("""
                    SELECT ne.symbol, ne.scan_date_et, AVG(ne.sentiment_score) as avg_sent
                    FROM news_events ne
                    WHERE ne.symbol IS NOT NULL AND ne.symbol != '' AND ne.sentiment_score IS NOT NULL
                    GROUP BY ne.symbol, ne.scan_date_et
                """)).fetchall():
                    stock_news_map[(r[1], r[0])] = r[1] and r[2] or 0
            except Exception: pass

        if len(rows) < MIN_TRAIN_ROWS:
            return None, None, None

        # Group by symbol for feature computation
        from collections import defaultdict
        by_symbol = defaultdict(list)
        for r in rows:
            by_symbol[r[0]].append(r)

        # v17: Pre-compute strategy×regime and sector×regime Sharpes for context
        # First pass: collect outcomes by strategy×regime and sector×regime
        _strat_rets = defaultdict(list)
        _sect_rets = defaultdict(list)
        for sym, stock_rows in by_symbol.items():
            if len(stock_rows) < 25:
                continue
            closes = [rr[2] for rr in stock_rows]
            sector = stock_rows[0][10]
            for i in range(20, len(stock_rows) - 5):
                close = closes[i]
                fwd_ret = (closes[i+5] / close - 1) * 100
                mom5 = (close / closes[i-5] - 1) * 100 if closes[i-5] > 0 else 0
                d20h_val = (close / max(closes[max(0,i-19):i+1]) - 1) * 100 if closes else 0
                vol_r = stock_rows[i][5] / stock_rows[0][9] if stock_rows[0][9] > 0 else 1
                vix_val = stock_rows[i][11] or 20
                br_val = stock_rows[i][13] or 50
                st = classify_strategy(mom5, d20h_val, vol_r)
                rg = classify_regime(vix_val, br_val)
                _strat_rets[(rg, st)].append(fwd_ret)
                _sect_rets[(rg, sector)].append(fwd_ret)

        strat_sharpe_map = {k: np.mean(v)/max(np.std(v),0.01)
                            for k,v in _strat_rets.items() if len(v) >= 30}
        sect_sharpe_map = {k: np.mean(v)/max(np.std(v),0.01)
                           for k,v in _sect_rets.items() if len(v) >= 30}
        logger.info("AdaptiveStockSelector: pre-computed %d strat×regime, %d sect×regime Sharpes",
                     len(strat_sharpe_map), len(sect_sharpe_map))

        # Compute features per stock-day
        X_rows = []
        y_rows = []

        for sym, stock_rows in by_symbol.items():
            if len(stock_rows) < 25:
                continue

            closes = [r[2] for r in stock_rows]
            highs = [r[3] for r in stock_rows]
            lows = [r[4] for r in stock_rows]
            volumes = [r[5] for r in stock_rows]
            beta = stock_rows[0][6]
            pe = stock_rows[0][7]
            mcap = stock_rows[0][8]
            avg_vol = stock_rows[0][9]
            sector = stock_rows[0][10]

            for i in range(20, len(stock_rows) - 5):
                r = stock_rows[i]
                close = closes[i]
                dt = r[1]

                # Target: 5d forward return > 0
                fwd_close = closes[i + 5]
                fwd_ret = (fwd_close / close - 1) * 100
                target = 1 if fwd_ret > 0 else 0

                # Features
                mom5 = (close / closes[i-5] - 1) * 100 if closes[i-5] > 0 else 0
                mom20 = (close / closes[i-20] - 1) * 100 if closes[i-20] > 0 else 0
                vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 1
                mcap_log = np.log10(mcap + 1) if mcap else 10

                # ATR 14d
                trs = []
                for j in range(max(1, i-13), i+1):
                    tr = max(highs[j] - lows[j],
                             abs(highs[j] - closes[j-1]),
                             abs(lows[j] - closes[j-1]))
                    trs.append(tr)
                atr_pct = (np.mean(trs) / close * 100) if close > 0 and trs else 3

                # RSI 14d
                deltas = [closes[j] - closes[j-1] for j in range(max(1, i-13), i+1)]
                gains = [max(d, 0) for d in deltas]
                losses = [max(-d, 0) for d in deltas]
                avg_gain = np.mean(gains) if gains else 0
                avg_loss = np.mean(losses) if losses else 0.01
                rsi = 100 - (100 / (1 + avg_gain / max(avg_loss, 0.01)))

                # d20h
                high_20d = max(highs[max(0, i-19):i+1]) if i >= 1 else close
                d20h = (close / high_20d - 1) * 100 if high_20d > 0 else 0

                # Macro
                vix = r[11] or 20
                crude = r[12] or 75
                breadth = r[13] or 50

                # Crude 5d change
                if i >= 5:
                    crude_5d_ago_row = stock_rows[i-5]
                    crude_5d_ago = crude_5d_ago_row[12] or crude
                    crude_delta = (crude / crude_5d_ago - 1) * 100 if crude_5d_ago > 0 else 0
                else:
                    crude_delta = 0

                # v17: 25 raw features — ML decides everything
                strat = classify_strategy(mom5, d20h, vol_ratio)
                rgm = classify_regime(vix, breadth)
                strat_sharpe = strat_sharpe_map.get((rgm, strat), 0)

                # New raw context features
                stock_news = stock_news_map.get((dt, sym), 0) or 0
                crude_sens = crude_sens_map.get(sym, 0)
                vix_sens = vix_sens_map.get(sym, 0)
                sect_mom_1d = sector_mom_map.get((dt, sector), 0)
                sect_news = sector_news_map.get((dt, sector), 0) or 0
                sect_analyst = sector_analyst_map.get((dt, sector), 0)
                me = macro_extra_map.get(dt, {})
                vix_spread = me.get('vix_spread', 0)
                breadth_d5 = me.get('breadth_d5', 0)
                spy_5d = me.get('spy_5d', 0)
                n_up = n_sectors_up_map.get(dt, 5)
                cluster_h = sect_sharpe_map.get((rgm, sector), 0)  # proxy for cluster health

                feature_row = [
                    # Stock (9)
                    mom5, mom20, vol_ratio, beta or 1, atr_pct,
                    rsi, d20h, pe or np.nan, mcap_log,
                    # Stock context (3)
                    stock_news, crude_sens, vix_sens,
                    # Sector (3)
                    sect_mom_1d, sect_news, sect_analyst,
                    # Market (7)
                    vix, breadth, crude_delta,
                    vix_spread, breadth_d5, spy_5d, n_up,
                    # Context (2)
                    strat_sharpe, cluster_h,
                ]
                X_rows.append(feature_row)
                y_rows.append(target)

        if len(X_rows) < MIN_TRAIN_ROWS:
            return None, None, None

        # Cap training size for speed
        if len(X_rows) > MAX_TRAIN_ROWS:
            # Keep most recent rows
            X_rows = X_rows[-MAX_TRAIN_ROWS:]
            y_rows = y_rows[-MAX_TRAIN_ROWS:]

        X = np.array(X_rows, dtype=np.float64)
        y = np.array(y_rows, dtype=np.int32)

        logger.info("AdaptiveStockSelector: built %d training rows (%.1f%% positive)",
                     len(X), y.mean() * 100)
        return X, y, FEATURES

    def _extract_features(self, candidate, sector_scores, context=None):
        """Extract feature vector from a candidate dict for prediction.

        context: dict with 'smart_er', 'strat_sharpe', 'sect_sharpe' if available.
        """
        c = candidate
        ctx = context or {}
        try:
            row = [
                # Stock (9)
                c.get('momentum_5d') or 0,
                c.get('momentum_20d') or 0,
                c.get('volume_ratio') or 1,
                c.get('beta') or 1,
                c.get('atr_pct') or 3,
                c.get('rsi') or 50,
                c.get('distance_from_20d_high') or -5,
                c.get('pe_forward'),  # may be None → NaN
                np.log10((c.get('market_cap') or 1e9) + 1),
                # Stock context (3)
                ctx.get('stock_news_sent', 0),
                ctx.get('crude_sensitivity', 0),
                ctx.get('vix_sensitivity', 0),
                # Sector (3)
                ctx.get('sector_mom_1d', 0),
                ctx.get('sector_news_sent', 0),
                ctx.get('sector_analyst_net', 0),
                # Market (7)
                c.get('vix_close') or c.get('vix_at_signal') or 20,
                c.get('pct_above_20d_ma') or 50,
                c.get('crude_delta_5d_pct') or 0,
                ctx.get('vix_spread', 0),
                ctx.get('breadth_delta_5d', 0),
                ctx.get('spy_5d_ret', 0),
                ctx.get('n_sectors_up', 5),
                # Context (2)
                ctx.get('strat_sharpe', 0),
                ctx.get('cluster_health', 0),
            ]
            return [float(v) if v is not None else np.nan for v in row]
        except Exception:
            return None

    # === DB Persistence ===

    def _ensure_tables(self):
        with get_session() as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS stock_selector_model (
                    id INTEGER PRIMARY KEY,
                    model_blob BLOB NOT NULL,
                    feature_names TEXT NOT NULL,
                    feature_means TEXT,
                    feature_stds TEXT,
                    fit_date TEXT NOT NULL,
                    n_train INTEGER,
                    auc REAL,
                    feature_importance TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """))
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS stock_selector_history (
                    fit_date TEXT NOT NULL,
                    n_train INTEGER,
                    auc REAL,
                    wr_top_decile REAL,
                    avg_return_top_decile REAL,
                    feature_importance TEXT,
                    UNIQUE(fit_date)
                )
            """))

    def save_to_db(self):
        from datetime import date as date_cls
        fit_date = date_cls.today().isoformat()

        model_blob = pickle.dumps(self._model)
        feat_names = json.dumps(self._feature_names)
        feat_means = json.dumps(self._feature_means.tolist()) if self._feature_means is not None else None
        feat_stds = json.dumps(self._feature_stds.tolist()) if self._feature_stds is not None else None
        feat_imp = json.dumps(self._feature_importance)

        with get_session() as session:
            # Save current model (single row, replace)
            session.execute(text("DELETE FROM stock_selector_model"))
            session.execute(text("""
                INSERT INTO stock_selector_model
                (model_blob, feature_names, feature_means, feature_stds,
                 fit_date, n_train, auc, feature_importance)
                VALUES (:p0, :p1, :p2, :p3, :p4, :p5, :p6, :p7)
            """), {'p0': model_blob, 'p1': feat_names, 'p2': feat_means, 'p3': feat_stds,
                   'p4': fit_date, 'p5': self._n_train, 'p6': self._auc, 'p7': feat_imp})

            # Save to history
            session.execute(text("""
                INSERT OR REPLACE INTO stock_selector_history
                (fit_date, n_train, auc, feature_importance)
                VALUES (:p0, :p1, :p2, :p3)
            """), {'p0': fit_date, 'p1': self._n_train, 'p2': self._auc, 'p3': feat_imp})
        logger.info("AdaptiveStockSelector: saved model to DB (AUC=%.4f, %d bytes)",
                     self._auc, len(model_blob))

    def load_from_db(self) -> bool:
        try:
            with get_session() as session:
                row = session.execute(text("""
                    SELECT model_blob, feature_names, feature_means, feature_stds,
                           n_train, auc, feature_importance
                    FROM stock_selector_model LIMIT 1
                """)).fetchone()
        except Exception:
            return False

        if not row or not row[0]:
            return False

        try:
            self._model = pickle.loads(row[0])
            self._feature_names = json.loads(row[1]) if row[1] else FEATURES
            self._feature_means = np.array(json.loads(row[2])) if row[2] else None
            self._feature_stds = np.array(json.loads(row[3])) if row[3] else None
            self._n_train = row[4] or 0
            self._auc = row[5] or 0
            self._feature_importance = json.loads(row[6]) if row[6] else {}

            self._fitted = True
            self._fit_time = time.time()
            logger.info("AdaptiveStockSelector: loaded from DB — AUC=%.4f n=%d",
                         self._auc, self._n_train)
            return True
        except Exception as e:
            logger.error("AdaptiveStockSelector: load error: %s", e)
            return False

    def get_stats(self) -> dict:
        return {
            'fitted': self._fitted,
            'auc': self._auc,
            'n_train': self._n_train,
            'feature_importance': self._feature_importance,
            'feature_names': self._feature_names,
        }
