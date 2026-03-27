"""
Sector Scorer — v17 Layer 1.

Scores each sector from 4 learned features:
  1. momentum_5d:       sector ETF 5d return
  2. macro_corr_signal: rolling 30d correlation between macro instruments and sector
  3. analyst_net_7d:    net analyst upgrades - downgrades per sector (7d window)
  4. options_pc:        1 - avg P/C ratio per sector (bullish if low P/C)

Feature weights = rolling IC vs sector 5d forward return (auto-learned).
Top 5 sectors = allowed, Bottom 3 = blocked, Middle 3 = allowed with penalty.

Replaces: CRUDE_SENSITIVE frozenset, get_crisis_sectors(), get_stress_sectors(),
          REGIME_STRATEGY_MAP in multi_strategy.py.

Walk-forward safe: fit(max_date) only uses data up to max_date.
"""
import logging
from database.orm.base import get_session
from sqlalchemy import text
import time
import numpy as np
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)

SECTORS = [
    'Technology', 'Healthcare', 'Financial Services', 'Consumer Cyclical',
    'Consumer Defensive', 'Industrials', 'Energy', 'Utilities',
    'Basic Materials', 'Real Estate', 'Communication Services',
]

# Macro instruments for correlation analysis
MACRO_INSTRUMENTS = [
    ('crude_close', 'Crude'),
    ('gold_close', 'Gold'),
    ('vix_close', 'VIX'),
    ('yield_10y', 'Yield10Y'),
    ('dxy_close', 'DXY'),
    ('btc_close', 'BTC'),
    ('copper_close', 'Copper'),
    ('usdjpy_close', 'USDJPY'),
]

FEATURES = ['momentum_5d', 'macro_corr_signal', 'analyst_net_7d', 'options_pc']
MIN_IC = 0.02
MIN_OBS = 30
MAX_CHANGE_PCT = 30
N_ALLOWED = 5    # top 5 allowed
N_BLOCKED = 3    # bottom 3 blocked


class SectorScorer:
    """Score sectors adaptively — replaces hardcoded sector rules."""

    def __init__(self, adaptive_params=None):
        self._adaptive = adaptive_params  # v17: for learned N_BLOCKED
        self._weights = {}          # {feature: weight}
        self._sector_etf_map = {}   # {sector: etf}
        self._fitted = False
        self._fit_time = 0.0
        self._fit_stats = {}
        self._ensure_tables()

    def fit(self, max_date=None) -> bool:
        """Learn feature weights from historical sector data."""
        t0 = time.time()
        old_weights = dict(self._weights)

        # conn via get_session()
        conn.execute('PRAGMA busy_timeout=5000')

        try:
            # Build sector ETF mapping
            self._sector_etf_map = self._load_sector_etf_map(conn)
            if not self._sector_etf_map:
                logger.warning("SectorScorer: no sector ETF mapping found")
                return False

            date_filter = f"AND date <= '{max_date}'" if max_date else ""

            # Load raw data
            sector_returns = self._load_sector_returns(conn, date_filter)
            macro_data = self._load_macro_data(conn, date_filter)
            analyst_data = self._load_analyst_data(conn, date_filter)
            options_data = self._load_options_data(conn, date_filter)

        finally:
            pass

        if len(sector_returns) < 100:
            logger.warning("SectorScorer: insufficient sector data (%d)", len(sector_returns))
            return False

        # Compute features per (date, sector)
        features_by_ds, fwd_returns = self._compute_features(
            sector_returns, macro_data, analyst_data, options_data)

        if len(fwd_returns) < 200:
            logger.warning("SectorScorer: insufficient feature data (%d)", len(fwd_returns))
            return False

        # Learn IC-based weights
        for feat_name in FEATURES:
            feat_vals = []
            ret_vals = []
            for key, fwd in fwd_returns.items():
                feat_row = features_by_ds.get(key, {})
                val = feat_row.get(feat_name)
                if val is not None:
                    feat_vals.append(val)
                    ret_vals.append(fwd)

            if len(feat_vals) < MIN_OBS:
                self._weights[feat_name] = 0.0
                continue

            ic = float(np.corrcoef(feat_vals, ret_vals)[0, 1])
            if np.isnan(ic):
                ic = 0.0

            if abs(ic) > MIN_IC:
                weight = ic  # use IC directly as weight (already in [-1, 1])
            else:
                weight = 0.0

            # Safety guard
            if feat_name in old_weights and old_weights[feat_name] != 0:
                old_w = old_weights[feat_name]
                if abs(weight - old_w) / max(abs(old_w), 0.01) > MAX_CHANGE_PCT / 100:
                    if weight > old_w:
                        weight = old_w * (1 + MAX_CHANGE_PCT / 100)
                    else:
                        weight = old_w * (1 - MAX_CHANGE_PCT / 100)

            self._weights[feat_name] = round(weight, 4)
            logger.info("SectorScorer: %s IC=%.4f weight=%.4f (n=%d)",
                        feat_name, ic, weight, len(feat_vals))

        self._fitted = True
        self._fit_time = time.time()
        self.save_to_db()

        elapsed = time.time() - t0
        logger.info("SectorScorer: fitted in %.1fs — weights=%s", elapsed, self._weights)
        return True

    def score(self, macro: dict, date: str = None) -> dict:
        """Score each sector for today. Returns {sector: score}.

        Uses latest data from DB + macro dict for real-time scoring.
        """
        if not self._fitted:
            return {s: 0.0 for s in SECTORS}

        # conn via get_session()
        conn.execute('PRAGMA busy_timeout=3000')

        try:
            scores = {}
            for sector in SECTORS:
                features = self._compute_sector_features_live(
                    conn, sector, macro, date)
                score = sum(
                    features.get(f, 0) * self._weights.get(f, 0)
                    for f in FEATURES
                )
                scores[sector] = round(score, 4)
        finally:
            pass

        return scores

    def get_allowed_sectors(self, macro: dict, date: str = None):
        """Returns (allowed_sectors, blocked_sectors).

        Top N_ALLOWED by score = allowed.
        Bottom N_BLOCKED = blocked.
        Middle = allowed (no penalty).
        """
        scores = self.score(macro, date)
        if not scores:
            return set(SECTORS), set()

        # v17: Use learned N_BLOCKED if available
        n_blocked = N_BLOCKED
        if self._adaptive:
            n_blocked = int(self._adaptive.get('', 'BULL', 'n_blocked'))

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        allowed = {s for s, _ in ranked[:len(ranked) - n_blocked]}
        blocked = {s for s, _ in ranked[-n_blocked:]} if len(ranked) > n_blocked else set()

        # Don't block if scores are very close (within 0.01)
        if ranked and len(ranked) > n_blocked:
            top_score = ranked[0][1]
            bottom_score = ranked[-n_blocked][1]
            if abs(top_score - bottom_score) < 0.01:
                blocked = set()
                allowed = set(SECTORS)

        return allowed, blocked

    def needs_refit(self, days=30) -> bool:
        if not self._fitted:
            return True
        return (time.time() - self._fit_time) > days * 86400

    # === Feature Computation ===

    def _compute_features(self, sector_returns, macro_data, analyst_data, options_data):
        """Compute features per (date, sector) and forward returns.

        Returns:
            features_by_ds: {(date, sector): {feature: value}}
            fwd_returns: {(date, sector): 5d_forward_return}
        """
        # Build sector momentum (5d)
        sector_mom = {}  # {(date, sector): momentum_5d}
        by_sector = defaultdict(list)
        for dt, sector, pct_change in sector_returns:
            by_sector[sector].append((dt, pct_change or 0))

        for sector, rows in by_sector.items():
            rows.sort()
            for i in range(5, len(rows)):
                dt = rows[i][0]
                mom5 = sum(r[1] for r in rows[i-5:i])
                sector_mom[(dt, sector)] = mom5

        # Build macro-sector correlation signals
        macro_corr = self._compute_macro_corr_signals(sector_returns, macro_data)

        # Build analyst net upgrades (7d window)
        analyst_net = {}  # {(date, sector): net_upgrades}
        for dt, sector, ups, downs in analyst_data:
            analyst_net[(dt, sector)] = (ups or 0) - (downs or 0)

        # Build options signal (sparse)
        options_sig = {}  # {(date, sector): signal}
        for dt, sector, pc in options_data:
            if pc and pc > 0:
                options_sig[(dt, sector)] = 1.0 - pc  # bullish if P/C < 1

        # Forward returns from sector ETFs
        fwd_returns = {}
        for sector, rows in by_sector.items():
            rows.sort()
            for i in range(len(rows) - 5):
                dt = rows[i][0]
                fwd_5d = sum(r[1] for r in rows[i+1:i+6])
                fwd_returns[(dt, sector)] = fwd_5d

        # Combine features
        features_by_ds = {}
        all_keys = set(sector_mom.keys()) | set(fwd_returns.keys())
        for key in all_keys:
            features_by_ds[key] = {
                'momentum_5d': sector_mom.get(key, 0),
                'macro_corr_signal': macro_corr.get(key, 0),
                'analyst_net_7d': analyst_net.get(key, 0),
                'options_pc': options_sig.get(key),
            }

        return features_by_ds, fwd_returns

    def _compute_macro_corr_signals(self, sector_returns, macro_data):
        """Compute rolling 30d correlation between macro instruments and sectors.

        For each sector-date: sum(corr_i × instrument_5d_change_i) for instruments
        where |corr_i| > 0.3 (meaningful correlation).
        """
        # Build daily macro dict {date: {instrument: value}}
        macro_by_date = {}
        for row in macro_data:
            dt = row[0]
            macro_by_date[dt] = {
                inst[0]: row[i+1] for i, inst in enumerate(MACRO_INSTRUMENTS)
                if row[i+1] is not None
            }

        # Build daily sector return dict {(date, sector): pct_change}
        sector_by_ds = {}
        dates_by_sector = defaultdict(list)
        for dt, sector, pct in sector_returns:
            sector_by_ds[(dt, sector)] = pct or 0
            dates_by_sector[sector].append(dt)

        # Compute rolling 30d correlations and signals
        macro_corr = {}
        sorted_dates = sorted(macro_by_date.keys())

        for sector in SECTORS:
            sector_dates = sorted(set(dates_by_sector.get(sector, [])))
            if len(sector_dates) < 35:
                continue

            for i in range(30, len(sector_dates)):
                dt = sector_dates[i]
                window_dates = sector_dates[i-30:i]

                # Get sector returns in window
                sect_rets = [sector_by_ds.get((d, sector), 0) for d in window_dates]

                # For each macro instrument, compute correlation
                signal = 0.0
                for inst_col, inst_name in MACRO_INSTRUMENTS:
                    inst_vals = []
                    for d in window_dates:
                        m = macro_by_date.get(d, {})
                        inst_vals.append(m.get(inst_col))

                    # Skip if too many missing
                    valid = [(s, v) for s, v in zip(sect_rets, inst_vals) if v is not None]
                    if len(valid) < 20:
                        continue

                    s_arr = np.array([x[0] for x in valid])
                    v_arr = np.array([x[1] for x in valid])

                    # Compute 5d change of instrument
                    if len(v_arr) >= 6:
                        inst_5d_chg = (v_arr[-1] / v_arr[-6] - 1) * 100 if v_arr[-6] > 0 else 0
                    else:
                        inst_5d_chg = 0

                    corr = np.corrcoef(s_arr, np.diff(np.concatenate([[v_arr[0]], v_arr])))[0, 1]
                    if np.isnan(corr):
                        continue

                    # Only use instruments with meaningful correlation
                    if abs(corr) > 0.3:
                        signal += corr * inst_5d_chg

                macro_corr[(dt, sector)] = round(signal, 4)

        return macro_corr

    def _compute_sector_features_live(self, conn, sector, macro, date):
        """Compute features for a single sector using latest data."""
        features = {}

        # 1. Momentum 5d — from sector_etf_daily_returns
        etf = self._sector_etf_map.get(sector)
        if etf:
            rows = conn.execute("""
                SELECT pct_change FROM sector_etf_daily_returns
                WHERE sector = ? ORDER BY date DESC LIMIT 5
            """, (sector,)).fetchall()
            features['momentum_5d'] = sum(r[0] or 0 for r in rows) if rows else 0

        # 2. Macro correlation signal — use current macro state
        # Simplified live version: use known strong correlations
        features['macro_corr_signal'] = 0
        try:
            rows = conn.execute("""
                SELECT date, crude_close, gold_close, vix_close, yield_10y,
                       dxy_close, btc_close, copper_close
                FROM macro_snapshots ORDER BY date DESC LIMIT 30
            """).fetchall()
            if len(rows) >= 6:
                # Compute sector-macro correlation from recent 30d
                sect_rows = conn.execute("""
                    SELECT date, pct_change FROM sector_etf_daily_returns
                    WHERE sector = ? ORDER BY date DESC LIMIT 30
                """, (sector,)).fetchall()

                if len(sect_rows) >= 20:
                    s_rets = np.array([r[1] or 0 for r in sect_rows[::-1]])
                    signal = 0.0
                    for col_idx, (inst_col, inst_name) in enumerate(
                        [('crude_close', 'Crude'), ('gold_close', 'Gold'),
                         ('vix_close', 'VIX')]):
                        # Use top-3 most impactful instruments
                        vals = [r[col_idx + 1] for r in rows[::-1] if r[col_idx + 1]]
                        if len(vals) >= 20:
                            v_arr = np.array(vals[:len(s_rets)])
                            v_chg = np.diff(v_arr) / np.maximum(v_arr[:-1], 0.01) * 100
                            min_len = min(len(s_rets) - 1, len(v_chg))
                            if min_len >= 15:
                                corr = np.corrcoef(s_rets[1:min_len+1], v_chg[:min_len])[0, 1]
                                if not np.isnan(corr) and abs(corr) > 0.3:
                                    inst_5d = (vals[-1] / vals[-6] - 1) * 100 if vals[-6] > 0 else 0
                                    signal += corr * inst_5d
                    features['macro_corr_signal'] = round(signal, 4)
        except Exception:
            pass

        # 3. Analyst net 7d
        try:
            row = conn.execute("""
                SELECT
                    SUM(CASE WHEN arh.price_target > arh.prior_price_target * 1.05
                         AND arh.prior_price_target > 0 THEN 1 ELSE 0 END) as ups,
                    SUM(CASE WHEN arh.price_target < arh.prior_price_target * 0.95
                         AND arh.prior_price_target > 0 THEN 1 ELSE 0 END) as downs
                FROM analyst_ratings_history arh
                JOIN stock_fundamentals sf ON arh.symbol = sf.symbol
                WHERE sf.sector = ?
                AND arh.date >= date('now', '-7 days')
                AND arh.price_target > 0
            """, (sector,)).fetchone()
            if row:
                features['analyst_net_7d'] = (row[0] or 0) - (row[1] or 0)
            else:
                features['analyst_net_7d'] = 0
        except Exception:
            features['analyst_net_7d'] = 0

        # 4. Options P/C
        try:
            row = conn.execute("""
                SELECT AVG(o.pc_volume_ratio)
                FROM options_daily_summary o
                JOIN stock_fundamentals sf ON o.symbol = sf.symbol
                WHERE sf.sector = ?
                AND o.collected_date >= date('now', '-3 days')
                AND o.pc_volume_ratio > 0
            """, (sector,)).fetchone()
            if row and row[0]:
                features['options_pc'] = round(1.0 - row[0], 4)
            else:
                features['options_pc'] = None  # no data
        except Exception:
            features['options_pc'] = None

        return features

    # === Data Loading ===

    def _load_sector_etf_map(self, conn):
        rows = conn.execute("""
            SELECT DISTINCT sector, etf FROM sector_etf_daily_returns
            WHERE sector IS NOT NULL AND sector != ''
            AND sector NOT IN ('S&P 500', 'US Dollar', 'Treasury Long', 'Gold')
        """).fetchall()
        return {r[0]: r[1] for r in rows}

    def _load_sector_returns(self, conn, date_filter):
        rows = conn.execute(f"""
            SELECT date, sector, pct_change FROM sector_etf_daily_returns
            WHERE sector IS NOT NULL AND sector != ''
            AND sector NOT IN ('S&P 500', 'US Dollar', 'Treasury Long', 'Gold')
            AND date >= date('now', '-15 months')
            {date_filter}
            ORDER BY sector, date
        """).fetchall()
        return rows

    def _load_macro_data(self, conn, date_filter):
        cols = ', '.join(inst[0] for inst in MACRO_INSTRUMENTS)
        rows = conn.execute(f"""
            SELECT date, {cols} FROM macro_snapshots
            WHERE date >= date('now', '-15 months')
            {date_filter}
            ORDER BY date
        """).fetchall()
        return rows

    def _load_analyst_data(self, conn, date_filter):
        """Load analyst upgrade/downgrade counts per sector per date."""
        rows = conn.execute(f"""
            SELECT arh.date, sf.sector,
                SUM(CASE WHEN arh.price_target > arh.prior_price_target * 1.05
                     AND arh.prior_price_target > 0 THEN 1 ELSE 0 END) as ups,
                SUM(CASE WHEN arh.price_target < arh.prior_price_target * 0.95
                     AND arh.prior_price_target > 0 THEN 1 ELSE 0 END) as downs
            FROM analyst_ratings_history arh
            JOIN stock_fundamentals sf ON arh.symbol = sf.symbol
            WHERE arh.price_target > 0
            AND arh.date >= date('now', '-15 months')
            {date_filter.replace('date', 'arh.date')}
            GROUP BY arh.date, sf.sector
        """).fetchall()
        return rows

    def _load_options_data(self, conn, date_filter):
        """Load average P/C ratio per sector per date."""
        try:
            rows = conn.execute(f"""
                SELECT o.collected_date, sf.sector, AVG(o.pc_volume_ratio)
                FROM options_daily_summary o
                JOIN stock_fundamentals sf ON o.symbol = sf.symbol
                WHERE o.pc_volume_ratio > 0
                {date_filter.replace('date', 'o.collected_date')}
                GROUP BY o.collected_date, sf.sector
            """).fetchall()
            return rows
        except Exception:
            return []  # table may not exist

    # === DB Persistence ===

    def _ensure_tables(self):
        # conn via get_session()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sector_scores (
                date TEXT NOT NULL,
                sector TEXT NOT NULL,
                score REAL NOT NULL,
                rank INTEGER,
                allowed INTEGER DEFAULT 1,
                momentum_5d REAL,
                macro_corr_signal REAL,
                analyst_net REAL,
                options_signal REAL,
                UNIQUE(date, sector)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sector_scorer_weights (
                feature TEXT NOT NULL,
                weight REAL NOT NULL,
                ic REAL,
                n_observations INTEGER,
                fit_date TEXT NOT NULL,
                UNIQUE(feature)
            )
        """)

    def save_to_db(self):
        from datetime import date as date_cls
        fit_date = date_cls.today().isoformat()
        # conn via get_session()
        for feat, weight in self._weights.items():
            ic = self._fit_stats.get(feat, {}).get('ic', 0)
            n = self._fit_stats.get(feat, {}).get('n', 0)
            conn.execute("""
                INSERT OR REPLACE INTO sector_scorer_weights
                (feature, weight, ic, n_observations, fit_date)
                VALUES (?, ?, ?, ?, ?)
            """, (feat, weight, ic, n, fit_date))
        logger.info("SectorScorer: saved weights to DB — %s", self._weights)

    def load_from_db(self) -> bool:
        # conn via get_session()
        try:
            rows = conn.execute(
                "SELECT feature, weight, ic FROM sector_scorer_weights"
            ).fetchall()
            etf_map = self._load_sector_etf_map(conn)
        except Exception:
            return False

        if not rows:
            return False

        self._weights = {r[0]: r[1] for r in rows}
        self._sector_etf_map = etf_map
        self._fitted = True
        self._fit_time = time.time()
        logger.info("SectorScorer: loaded from DB — weights=%s", self._weights)
        return True

    def get_stats(self) -> dict:
        return {
            'fitted': self._fitted,
            'weights': dict(self._weights),
            'n_sectors': len(self._sector_etf_map),
        }
