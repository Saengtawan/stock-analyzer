"""
Adaptive Parameter Learner — learns optimal parameters per (sector × regime).
Part of Discovery v13.1.

Replaces 7 hardcoded values with 231 learned values (7 params × 33 groups).
Each (sector, regime) group learns its own optimal:
  tp_ratio, sl_mult, atr_max, mom_cut, d0_close_min, elite_sigma

Walk-forward safe: fit(max_date) only uses data up to max_date.
Auto-refits every 30 days via AutoRefitOrchestrator.
"""
import logging
import sqlite3
import time
import numpy as np
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'

SECTORS = [
    'Technology', 'Healthcare', 'Financial Services',
    'Consumer Cyclical', 'Consumer Defensive', 'Industrials',
    'Energy', 'Utilities', 'Basic Materials', 'Real Estate',
    'Communication Services',
]
REGIMES = ['BULL', 'STRESS', 'CRISIS']

PARAM_GRID = {
    'tp_ratio':     [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5],
    'sl_mult':      [0.5, 0.75, 1.0, 1.5, 2.0, 2.5],
    'atr_max':      [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0],
    'mom_cut':      [-3, -2, -1, 0, 1, 2, 3, 4, 5],
    'd0_close_min': [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40],
    'elite_sigma':  [0.3, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0],
}

DEFAULTS = {
    'tp_ratio': 1.0,
    'sl_mult': 1.5,
    'atr_max': 5.0,
    'mom_cut': 3.0,
    'd0_close_min': 0.30,
    'elite_sigma': 0.8,
}

MIN_GROUP_SIZE = 100
MAX_CHANGE_PCT = 30  # safety: max ±30% change per refit cycle


def _classify_regime(vix, breadth):
    if vix < 20 and breadth > 50:
        return 'BULL'
    if vix > 28 or breadth < 25:
        return 'CRISIS'
    return 'STRESS'


def _sim_trade(d1o, d1h, d1l, d3h, d3l, d3c, atr, tp_ratio, sl_mult):
    """Simulate trade: entry D1 open, exit on TP/SL hit or D3 close."""
    sl = max(1.5, min(5.0, sl_mult * atr))
    tp = max(0.5, tp_ratio * atr)
    for h, l in [(d1h, d1l), (d3h, d3l)]:
        if (l / d1o - 1) * 100 <= -sl:
            return -sl
        if (h / d1o - 1) * 100 >= tp:
            return tp
    return (d3c / d1o - 1) * 100


class AdaptiveParameterLearner:
    """Learn optimal parameters per (sector × regime) from historical data."""

    def __init__(self):
        self._params = {}       # {(sector, regime): {param: value}}
        self._fitted = False
        self._fit_date = None
        self._fit_time = 0.0
        self._fit_stats = {}
        self._ensure_tables()

    def fit(self, max_date: str = None) -> bool:
        """Learn optimal parameters from historical data.

        Args:
            max_date: only use data up to this date (walk-forward).
                      None = use all available data.
        """
        t0 = time.time()
        data = self._load_data(max_date)
        if not data:
            logger.warning("AdaptiveParams: no data loaded")
            return False

        # Classify into (sector, regime) groups
        groups = defaultdict(list)
        for row in data:
            sector = row['sector']
            regime = _classify_regime(row['vix'], row['breadth'])
            groups[(sector, regime)].append(row)

        old_params = dict(self._params)
        self._params = {}
        self._fit_stats = {}

        for sector in SECTORS:
            for regime in REGIMES:
                key = (sector, regime)
                sigs = groups.get(key, [])

                if len(sigs) < MIN_GROUP_SIZE:
                    self._params[key] = dict(DEFAULTS)
                    self._fit_stats[key] = {
                        'n': len(sigs), 'source': 'default',
                    }
                    continue

                learned = self._learn_group(sigs, key)
                # Safety guard: cap change at ±30%
                if key in old_params:
                    learned = self._apply_guard(learned, old_params[key])

                self._params[key] = learned
                self._fit_stats[key] = {
                    'n': len(sigs), 'source': 'learned',
                    'params': dict(learned),
                }

        self._fitted = True
        self._fit_date = max_date or 'all'
        self._fit_time = time.time()

        n_learned = sum(1 for s in self._fit_stats.values()
                        if s['source'] == 'learned')
        elapsed = time.time() - t0
        logger.info(
            "AdaptiveParams: fitted %d/%d groups in %.1fs (max_date=%s)",
            n_learned, len(SECTORS) * len(REGIMES), elapsed,
            max_date or 'all')

        self.save_to_db()
        return True

    def get(self, sector: str, regime: str, param: str) -> float:
        """Get learned parameter with fallback chain.

        1. Exact match (sector, regime)
        2. Sector-level median (across regimes)
        3. Regime-level median (across sectors)
        4. Global default
        """
        key = (sector, regime)
        if key in self._params and param in self._params[key]:
            return self._params[key][param]

        # Sector-level fallback
        vals = [self._params[k].get(param)
                for k in self._params if k[0] == sector
                and param in self._params.get(k, {})]
        vals = [v for v in vals if v is not None]
        if vals:
            return float(np.median(vals))

        # Regime-level fallback
        vals = [self._params[k].get(param)
                for k in self._params if k[1] == regime
                and param in self._params.get(k, {})]
        vals = [v for v in vals if v is not None]
        if vals:
            return float(np.median(vals))

        return DEFAULTS.get(param, 0)

    def needs_refit(self, days: int = 30) -> bool:
        if not self._fitted:
            return True
        return (time.time() - self._fit_time) > days * 86400

    # === Learning methods ===

    def _learn_group(self, sigs, key):
        """Learn all parameters for one (sector, regime) group."""
        params = {}

        # 1. tp_ratio + sl_mult — joint grid search (best Sharpe)
        tp_r, sl_m = self._learn_tp_sl(sigs)
        params['tp_ratio'] = tp_r
        params['sl_mult'] = sl_m

        # 2. atr_max — WR sweep
        params['atr_max'] = self._learn_threshold(
            sigs, 'atr', PARAM_GRID['atr_max'], mode='upper')

        # 3. mom_cut — WR sweep
        params['mom_cut'] = self._learn_threshold(
            sigs, 'mom', PARAM_GRID['mom_cut'], mode='upper')

        # 4. d0_close_min — WR sweep
        params['d0_close_min'] = self._learn_threshold(
            sigs, 'd0_pos', PARAM_GRID['d0_close_min'], mode='lower')

        # 5. elite_sigma — best E[R] per pick
        params['elite_sigma'] = self._learn_elite_sigma(sigs)

        logger.debug(
            "AdaptiveParams [%s]: tp=%.2f sl=%.2f atr≤%.1f mom≤%.0f d0≥%.2f σ=%.1f (n=%d)",
            key, tp_r, sl_m, params['atr_max'], params['mom_cut'],
            params['d0_close_min'], params['elite_sigma'], len(sigs))

        return params

    def _learn_tp_sl(self, sigs):
        """Joint grid search for best (tp_ratio, sl_mult) by Sharpe."""
        # Only use signals with OHLC data
        ohlc_sigs = [s for s in sigs if s.get('d1o')]
        if len(ohlc_sigs) < 50:
            return DEFAULTS['tp_ratio'], DEFAULTS['sl_mult']

        best_sharpe = -999
        best_tp, best_sl = DEFAULTS['tp_ratio'], DEFAULTS['sl_mult']

        for tp_r in PARAM_GRID['tp_ratio']:
            for sl_m in PARAM_GRID['sl_mult']:
                pnls = []
                for s in ohlc_sigs:
                    pnl = _sim_trade(
                        s['d1o'], s['d1h'], s['d1l'],
                        s['d3h'], s['d3l'], s['d3c'],
                        s['atr'], tp_r, sl_m)
                    pnls.append(pnl)
                p = np.array(pnls)
                if len(p) < 30:
                    continue
                sharpe = p.mean() / max(p.std(), 0.01)
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_tp = tp_r
                    best_sl = sl_m

        return best_tp, best_sl

    def _learn_threshold(self, sigs, feature, grid, mode='upper'):
        """Sweep threshold to find best WR.

        mode='upper': keep signals where feature <= threshold (e.g. ATR, momentum)
        mode='lower': keep signals where feature >= threshold (e.g. d0_close_min)
        """
        best_wr = 0
        best_cut = grid[len(grid) // 2]  # middle as default

        for cut in grid:
            if mode == 'upper':
                filtered = [s for s in sigs if s.get(feature, 0) <= cut]
            else:
                filtered = [s for s in sigs if s.get(feature, 0) >= cut]

            if len(filtered) < 50:
                continue

            wr = sum(1 for s in filtered if s['o5d'] > 0) / len(filtered)
            if wr > best_wr:
                best_wr = wr
                best_cut = cut

        return float(best_cut)

    def _learn_elite_sigma(self, sigs):
        """Find elite_sigma that maximizes E[R] per selected pick."""
        ohlc_sigs = [s for s in sigs if s.get('d1o')]
        if len(ohlc_sigs) < 50:
            return DEFAULTS['elite_sigma']

        # Compute stock E[R] proxy = outcome_5d for each signal
        ers = np.array([s['o5d'] for s in ohlc_sigs])

        best_er_per_pick = -999
        best_sigma = DEFAULTS['elite_sigma']

        for sigma in PARAM_GRID['elite_sigma']:
            threshold = ers.mean() + sigma * ers.std()
            elite_mask = ers >= threshold
            n_elite = elite_mask.sum()
            if n_elite < 5:
                continue
            elite_er = ers[elite_mask].mean()
            if elite_er > best_er_per_pick:
                best_er_per_pick = elite_er
                best_sigma = sigma

        return best_sigma

    def _apply_guard(self, new_params, old_params):
        """Cap parameter changes at ±MAX_CHANGE_PCT per cycle."""
        guarded = {}
        for name, new_val in new_params.items():
            old_val = old_params.get(name)
            if old_val and old_val != 0:
                change_pct = abs(new_val - old_val) / abs(old_val) * 100
                if change_pct > MAX_CHANGE_PCT:
                    if new_val > old_val:
                        new_val = old_val * (1 + MAX_CHANGE_PCT / 100)
                    else:
                        new_val = old_val * (1 - MAX_CHANGE_PCT / 100)
                    new_val = round(new_val, 4)
            guarded[name] = new_val
        return guarded

    # === Data loading ===

    def _load_data(self, max_date=None):
        """Load historical signals with OHLC for SL/TP simulation."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            date_filter = f"AND b.scan_date <= '{max_date}'" if max_date else ""
            rows = conn.execute(f"""
                SELECT b.scan_date, b.symbol, b.sector,
                       b.atr_pct, b.momentum_5d, b.distance_from_20d_high,
                       b.volume_ratio, b.outcome_5d, b.vix_at_signal,
                       COALESCE(m.vix_close, 20) as vix,
                       COALESCE(mb.pct_above_20d_ma, 50) as breadth,
                       d0.high as d0h, d0.low as d0l, d0.close as d0c,
                       d0.open as d0o,
                       d1.open as d1o, d1.high as d1h, d1.low as d1l,
                       d3.high as d3h, d3.low as d3l, d3.close as d3c
                FROM backfill_signal_outcomes b
                LEFT JOIN macro_snapshots m ON b.scan_date = m.date
                LEFT JOIN market_breadth mb ON b.scan_date = mb.date
                LEFT JOIN signal_daily_bars d0
                    ON b.scan_date=d0.scan_date AND b.symbol=d0.symbol
                    AND d0.day_offset=0
                LEFT JOIN signal_daily_bars d1
                    ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol
                    AND d1.day_offset=1
                LEFT JOIN signal_daily_bars d3
                    ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol
                    AND d3.day_offset=3
                WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0
                AND b.sector IS NOT NULL
                AND m.vix_close IS NOT NULL AND mb.pct_above_20d_ma IS NOT NULL
                {date_filter}
                ORDER BY b.scan_date
            """).fetchall()
        finally:
            conn.close()

        if not rows:
            return []

        data = []
        for r in rows:
            d0h = r[11] or 0
            d0l = r[12] or 0
            d0c = r[13] or 0
            d0_range = d0h - d0l
            d0_pos = (d0c - d0l) / d0_range if d0_range > 0 else 0.5

            entry = {
                'scan_date': r[0], 'symbol': r[1], 'sector': r[2],
                'atr': r[3], 'mom': r[4] or 0,
                'd20h': r[5] or -5, 'vol': r[6] or 1,
                'o5d': r[7], 'vix': r[9], 'breadth': r[10],
                'd0_pos': d0_pos,
            }

            # OHLC for SL/TP sim (may be None if bars missing)
            if r[15] and r[15] > 0:
                entry.update({
                    'd1o': r[15], 'd1h': r[16], 'd1l': r[17],
                    'd3h': r[18], 'd3l': r[19], 'd3c': r[20],
                })

            data.append(entry)

        logger.info("AdaptiveParams: loaded %d signals (max_date=%s)",
                     len(data), max_date or 'all')
        return data

    # === DB persistence ===

    def _ensure_tables(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS adaptive_parameters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sector TEXT NOT NULL,
                regime TEXT NOT NULL,
                param_name TEXT NOT NULL,
                param_value REAL NOT NULL,
                n_signals INTEGER,
                metric_value REAL,
                fit_date TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(sector, regime, param_name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS adaptive_parameter_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sector TEXT NOT NULL,
                regime TEXT NOT NULL,
                param_name TEXT NOT NULL,
                old_value REAL,
                new_value REAL,
                n_signals INTEGER,
                reason TEXT,
                changed_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()

    def save_to_db(self):
        """Persist learned parameters to DB."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            for (sector, regime), params in self._params.items():
                stats = self._fit_stats.get((sector, regime), {})
                n_sigs = stats.get('n', 0)
                for name, value in params.items():
                    # Check old value for history
                    old = conn.execute("""
                        SELECT param_value FROM adaptive_parameters
                        WHERE sector=? AND regime=? AND param_name=?
                    """, (sector, regime, name)).fetchone()
                    old_val = old[0] if old else None

                    conn.execute("""
                        INSERT INTO adaptive_parameters
                        (sector, regime, param_name, param_value, n_signals, fit_date)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(sector, regime, param_name)
                        DO UPDATE SET param_value=?, n_signals=?,
                                      fit_date=?, created_at=datetime('now')
                    """, (sector, regime, name, value, n_sigs, self._fit_date,
                          value, n_sigs, self._fit_date))

                    if old_val is not None and abs(old_val - value) > 0.001:
                        conn.execute("""
                            INSERT INTO adaptive_parameter_history
                            (sector, regime, param_name, old_value, new_value,
                             n_signals, reason)
                            VALUES (?, ?, ?, ?, ?, ?, 'auto-refit')
                        """, (sector, regime, name, old_val, value, n_sigs))

            conn.commit()
            logger.info("AdaptiveParams: saved %d groups to DB",
                        len(self._params))
        finally:
            conn.close()

    def load_from_db(self) -> bool:
        """Load previously learned parameters from DB."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                SELECT sector, regime, param_name, param_value, n_signals
                FROM adaptive_parameters
            """).fetchall()
        finally:
            conn.close()

        if not rows:
            return False

        self._params = {}
        for sector, regime, name, value, n_sigs in rows:
            key = (sector, regime)
            if key not in self._params:
                self._params[key] = {}
            self._params[key][name] = value

        self._fitted = True
        self._fit_date = 'loaded'
        self._fit_time = time.time()
        logger.info("AdaptiveParams: loaded %d groups from DB", len(self._params))
        return True

    # === Stats ===

    def get_all(self) -> dict:
        """All learned parameters as nested dict."""
        result = {}
        for (sector, regime), params in sorted(self._params.items()):
            if sector not in result:
                result[sector] = {}
            result[sector][regime] = dict(params)
        return result

    def get_stats(self) -> dict:
        return {
            'fitted': self._fitted,
            'fit_date': self._fit_date,
            'n_groups': len(self._params),
            'n_learned': sum(1 for s in self._fit_stats.values()
                            if s.get('source') == 'learned'),
            'n_default': sum(1 for s in self._fit_stats.values()
                            if s.get('source') == 'default'),
        }

    def print_summary(self):
        """Print human-readable parameter table."""
        print(f"\n{'Sector':<25s} {'Regime':<8s} {'TP':>5s} {'SL':>5s} "
              f"{'ATR≤':>5s} {'Mom≤':>5s} {'D0≥':>5s} {'σ':>4s} {'N':>5s}")
        print("-" * 75)
        for sector in SECTORS:
            for regime in REGIMES:
                key = (sector, regime)
                p = self._params.get(key, DEFAULTS)
                stats = self._fit_stats.get(key, {})
                n = stats.get('n', 0)
                src = stats.get('source', '?')
                marker = '' if src == 'learned' else ' (D)'
                print(f"{sector:<25s} {regime:<8s} "
                      f"{p.get('tp_ratio', 1.0):>4.1f}x "
                      f"{p.get('sl_mult', 1.5):>4.1f}x "
                      f"{p.get('atr_max', 5.0):>4.1f} "
                      f"{p.get('mom_cut', 3):>+4.0f} "
                      f"{p.get('d0_close_min', 0.3):>4.2f} "
                      f"{p.get('elite_sigma', 0.8):>3.1f} "
                      f"{n:>5d}{marker}")
