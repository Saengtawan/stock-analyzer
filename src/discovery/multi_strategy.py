"""
Multi-Strategy Discovery v15.2 — 4 strategies ranked by volume.

v17 DEPRECATION NOTE:
  When v17.enabled=true in discovery.yaml, the hardcoded strategy functions below
  (strategy_dip, strategy_oversold, etc.) and REGIME_STRATEGY_MAP are bypassed.
  AdaptiveStockSelector (adaptive_stock_selector.py) replaces all strategy functions
  with a single learned model. SectorScorer (sector_scorer.py) replaces
  REGIME_STRATEGY_MAP sector preferences. This file remains for:
  - v16 fallback when v17.enabled=false
  - StrategySelector walk-forward learning (display-only)
  - detect_condition() still used by engine.py for scan_info

Strategies (validated on 75K signals, Sharpe=1.50):
  DIP:        Buy quality dips (-3% to -15%) — $/trade=+$0.26
  OVERSOLD:   Buy extreme oversold (< -5%) — $/trade=+$0.61
  VALUE:      Buy cheap quality (PE < 15) — $/trade=+$0.49
  CONTRARIAN: Buy best in worst sector — $/trade=+$0.91 (best)

Ranking: volume_ratio desc (confirmed via sim: Sharpe 1.13 vs 0.56 ATR×depth)
Max 2 per strategy, 8 total picks.
SL = 0.8×ATR (floor 1.5%, cap 3.5%)
TP = 2×ATR (floor 2%, cap 5%)

Walk-forward learns which strategy works best per condition (BULL/NORMAL/STRESS).
Auto-refit every 30 days.
"""
import logging
import sqlite3
import time
import numpy as np
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


# === Strategy Functions ===

def _safe(val, default=0):
    """Handle None values."""
    return val if val is not None else default


def _mom5(s):
    """Get momentum_5d from either field name."""
    return _safe(s.get('momentum_5d', s.get('mom_5d')), 0)

def _mom20(s):
    return _safe(s.get('momentum_20d', s.get('mom_20d')), 0)

def _d20h(s):
    return _safe(s.get('distance_from_20d_high', s.get('d20h')), 0)

def _vol(s):
    return _safe(s.get('volume_ratio', s.get('vol_ratio')), 1)

def _beta(s):
    return _safe(s.get('beta'), 1)

# v17: All thresholds below are DEFAULTS — overridden by learned params when available.
# StrategySelector.fit() learns optimal thresholds per condition via grid search.
STRATEGY_DEFAULTS = {
    'quality': {'max_vol': 3.0, 'min_mcap_b': 30},
    'DIP':     {'mom_min': -15, 'mom_max': -3, 'max_beta': 1.5, 'min_vol': 0.3},
    'OVERSOLD':{'mom_max': -5, 'max_d20h': -10, 'max_beta': 2.0},
    'VALUE':   {'pe_min': 3, 'pe_max': 15, 'mom_min': -10, 'max_beta': 1.5, 'min_mcap': 5e9},
    'CONTRARIAN': {'max_beta': 1.5, 'mom_min': -15, 'min_sector_stocks': 5},
    'VOL_U':   {'vol_low': 0.5, 'vol_high': 2.0, 'max_beta': 1.5},
    'RS':      {'min_mom5': 0, 'min_d20h': -5, 'max_beta': 1.5},
}


def _mcap(s):
    return _safe(s.get('market_cap'), 1e9) / 1e9


def _filter_quality(stocks, params=None):
    """Pre-filter: remove panic-sell + small cap stocks. v17: learned thresholds."""
    p = params or STRATEGY_DEFAULTS['quality']
    max_v = p.get('max_vol', 3.0)
    min_m = p.get('min_mcap_b', 30)
    return [s for s in stocks if _vol(s) <= max_v and _mcap(s) >= min_m]


def strategy_dip(stocks, macro=None, params=None):
    """DIP BOUNCE: หุ้นลง, beta ต่ำ, volume OK. v17: thresholds learned."""
    p = params or STRATEGY_DEFAULTS['DIP']
    picks = [s for s in _filter_quality(stocks, params)
             if p.get('mom_min', -15) < _mom5(s) < p.get('mom_max', -3)
             and _beta(s) < p.get('max_beta', 1.5)
             and _vol(s) > p.get('min_vol', 0.3)]
    return sorted(picks, key=lambda x: _d20h(x))[:5]


def strategy_oversold(stocks, macro=None, params=None):
    """OVERSOLD EXTREME: หุ้นลงหนักมาก, far from 20d high. v17: thresholds learned."""
    p = params or STRATEGY_DEFAULTS['OVERSOLD']
    picks = [s for s in _filter_quality(stocks, params)
             if _mom5(s) < p.get('mom_max', -5)
             and _d20h(s) < p.get('max_d20h', -10)
             and _beta(s) < p.get('max_beta', 2.0)]
    return sorted(picks, key=lambda x: _mom5(x))[:5]


def strategy_value(stocks, macro=None, params=None):
    """VALUE: PE ต่ำ, ไม่ลงเยอะ, quality. v17: thresholds learned."""
    p = params or STRATEGY_DEFAULTS['VALUE']
    picks = [s for s in _filter_quality(stocks, params)
             if s.get('pe_forward') is not None
             and p.get('pe_min', 3) < s['pe_forward'] < p.get('pe_max', 15)
             and _mom5(s) > p.get('mom_min', -10)
             and _beta(s) < p.get('max_beta', 1.5)
             and _safe(s.get('market_cap'), 0) > p.get('min_mcap', 5e9)]
    return sorted(picks, key=lambda x: _safe(x.get('pe_forward'), 99))[:5]


def strategy_contrarian(stocks, macro=None, params=None):
    """SECTOR CONTRARIAN: ซื้อหุ้นดีที่สุดใน worst sector. v17: thresholds learned."""
    p = params or STRATEGY_DEFAULTS['CONTRARIAN']
    sector_rets = defaultdict(list)
    for s in stocks:
        sector_rets[s.get('sector', '')].append(_mom5(s))
    sector_avg = {sect: np.mean(rets) for sect, rets in sector_rets.items()
                  if len(rets) > p.get('min_sector_stocks', 5) and sect}
    if not sector_avg:
        return []
    worst_sector = min(sector_avg, key=sector_avg.get)
    picks = [s for s in _filter_quality(stocks, params)
             if s.get('sector') == worst_sector
             and _beta(s) < p.get('max_beta', 1.5)
             and _mom5(s) > p.get('mom_min', -15)]
    return sorted(picks, key=lambda x: _mom5(x))[:5]


def strategy_vol_u(stocks, macro=None, params=None):
    """VOL U-SHAPE: volume ต่ำมากหรือสูงมาก = bounce signal. v17: thresholds learned."""
    p = params or STRATEGY_DEFAULTS['VOL_U']
    picks = [s for s in _filter_quality(stocks, params)
             if (_vol(s) < p.get('vol_low', 0.5) or _vol(s) > p.get('vol_high', 2.0))
             and _beta(s) < p.get('max_beta', 1.5)]
    return sorted(picks, key=lambda x: abs(_vol(x) - 1.0), reverse=True)[:5]


def strategy_relative_strength(stocks, macro=None, params=None):
    """RELATIVE STRENGTH: หุ้นที่ยังขึ้นในตลาดที่ลง. v17: thresholds learned."""
    p = params or STRATEGY_DEFAULTS['RS']
    picks = [s for s in _filter_quality(stocks, params)
             if _mom5(s) > p.get('min_mom5', 0)
             and _d20h(s) > p.get('min_d20h', -5)
             and _beta(s) < p.get('max_beta', 1.5)]
    return sorted(picks, key=lambda x: -_mom5(x))[:5]


# v17 DEPRECATED: Replaced by AdaptiveStockSelector when v17.enabled=true.
# Kept for v16 fallback and StrategySelector walk-forward learning.
STRATEGIES = {
    'DIP':        {'fn': strategy_dip, 'desc': 'Buy quality dips (-3% to -15%)'},
    'OVERSOLD':   {'fn': strategy_oversold, 'desc': 'Buy extreme oversold (< -5%)'},
    'VALUE':      {'fn': strategy_value, 'desc': 'Buy cheap quality (PE < 15)'},
    'CONTRARIAN': {'fn': strategy_contrarian, 'desc': 'Buy best in worst sector'},
    'VOL_U':      {'fn': strategy_vol_u, 'desc': 'Volume U-shape (low/extreme vol bounce)'},
    'RS':         {'fn': strategy_relative_strength, 'desc': 'Relative strength (up in down market)'},
}

# v15.2: SL/TP from ATR (sim validated: SL=0.8×ATR cap 3.5%, TP=2×ATR cap 5%)
STRATEGY_SLTP = {
    'DIP':        {'sl_pct': 3.5, 'tp_pct': 5.0},
    'OVERSOLD':   {'sl_pct': 3.5, 'tp_pct': 5.0},
    'VALUE':      {'sl_pct': 3.5, 'tp_pct': 5.0},
    'CONTRARIAN': {'sl_pct': 3.5, 'tp_pct': 5.0},
    'VOL_U':      {'sl_pct': 3.5, 'tp_pct': 5.0},
    'RS':         {'sl_pct': 3.5, 'tp_pct': 5.0},
}

# v16.1: Regime → preferred strategy map
# v17 DEPRECATED: Replaced by SectorScorer learned sector ranking.
# Updated from backtest 2026-03-24:
#   STRONG_DOWN: DIP/OVERSOLD work (61% WR — post-crash bounce) — keep
#   MILD_DOWN: DIP fails (42%) → RS wins (54%) — SWITCH
#   MILD_UP: DIP weak (51%) → RS better (56%) — SWITCH
#   STRONG_UP/CHOPPY: DIP/VOL_U work — keep
REGIME_STRATEGY_MAP = {
    ('STRONG_UP', 'HIGH_VOL'):     'DIP',
    ('STRONG_UP', 'ELEVATED'):     'VOL_U',
    ('STRONG_UP', 'NORMAL_VOL'):   'VOL_U',
    ('STRONG_UP', 'LOW_VOL'):      'DIP',
    ('MILD_UP', 'HIGH_VOL'):       'DIP',
    ('MILD_UP', 'ELEVATED'):       'RS',        # v16.1: RS beats DIP here
    ('MILD_UP', 'NORMAL_VOL'):     'RS',        # v16.1: RS 56% vs DIP 51%
    ('MILD_UP', 'LOW_VOL'):        'RS',        # v16.1: momentum in calm uptrend
    ('CHOPPY', 'HIGH_VOL'):        'OVERSOLD',
    ('CHOPPY', 'ELEVATED'):        'VOL_U',
    ('CHOPPY', 'NORMAL_VOL'):      'VOL_U',
    ('CHOPPY', 'LOW_VOL'):         'DIP',
    ('MILD_DOWN', 'HIGH_VOL'):     'OVERSOLD',
    ('MILD_DOWN', 'ELEVATED'):     'RS',        # v16.1: RS beats DIP in mild down
    ('MILD_DOWN', 'NORMAL_VOL'):   'RS',        # v16.1: RS 54% vs DIP 42%
    ('MILD_DOWN', 'LOW_VOL'):      'RS',        # v16.1: don't catch falling knives
    ('STRONG_DOWN', 'HIGH_VOL'):   'DIP',       # v16.1: keep — post-crash bounce 61%
    ('STRONG_DOWN', 'ELEVATED'):   'DIP',       # v16.1: keep — oversold bounce works
    ('STRONG_DOWN', 'NORMAL_VOL'): 'OVERSOLD',  # keep — deep oversold bounce
    ('STRONG_DOWN', 'LOW_VOL'):    'OVERSOLD',
}

MAX_PER_STRATEGY = 2
MAX_TOTAL_PICKS = 8


def detect_condition(vix, breadth):
    """Classify market condition from VIX + breadth."""
    vix = vix or 20
    breadth = breadth or 50
    if vix > 25 and breadth < 35:
        return 'STRESS'
    if vix < 18 and breadth > 55:
        return 'BULL'
    return 'NORMAL'


class StrategySelector:
    """Learn which strategy works best per condition + optimal thresholds."""

    def __init__(self):
        self._best_by_condition = {}  # condition → strategy name
        self._learned_params = {}     # v17: {strategy_name: {param: value}}
        self._fit_stats = {}
        self._fitted = False
        self._fit_time = 0.0
        self._ensure_tables()

    def fit(self, max_date=None):
        """Walk-forward learn: which strategy best per condition."""
        t0 = time.time()
        data = self._load_data(max_date)
        if not data:
            logger.warning("StrategySelector: no data")
            return False

        # Group by date
        by_date = defaultdict(list)
        for d in data:
            by_date[d['date']].append(d)

        # For each condition: backtest all strategies
        for condition in ['BULL', 'NORMAL', 'STRESS']:
            cond_dates = [dt for dt, stocks in by_date.items()
                          if len(stocks) > 50
                          and detect_condition(stocks[0]['vix'],
                                              stocks[0]['breadth']) == condition]

            if len(cond_dates) < 20:
                self._best_by_condition[condition] = 'DIP'
                continue

            best_sharpe = -999
            best_name = 'DIP'

            for strat_name, spec in STRATEGIES.items():
                rets = []
                for dt in cond_dates:
                    stocks = by_date[dt]
                    picks = spec['fn'](stocks)
                    for p in picks:
                        rets.append(p.get('fwd_5d', 0))

                if len(rets) < 30:
                    continue

                avg = np.mean(rets)
                std = max(np.std(rets), 0.01)
                sharpe = avg / std
                wr = sum(1 for r in rets if r > 0) / len(rets) * 100

                self._fit_stats[(condition, strat_name)] = {
                    'avg': round(avg, 3), 'wr': round(wr, 1),
                    'sharpe': round(sharpe, 3), 'n': len(rets),
                }

                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_name = strat_name

            self._best_by_condition[condition] = best_name
            logger.info("StrategySelector: %s → %s (sharpe=%.3f)",
                        condition, best_name, best_sharpe)

        # v17: Learn optimal thresholds per strategy via grid search
        self._learned_params = self._learn_strategy_thresholds(by_date)

        self._fitted = True
        self._fit_time = time.time()
        self.save_to_db()

        elapsed = time.time() - t0
        logger.info("StrategySelector: fitted in %.1fs — %s params=%s", elapsed,
                     self._best_by_condition,
                     {k: len(v) for k, v in self._learned_params.items()})
        return True

    def _learn_strategy_thresholds(self, by_date):
        """v17: Grid search optimal thresholds for each strategy.

        For each strategy, vary key thresholds and find the combo with best Sharpe.
        Returns {strategy_name: {param: best_value}}.
        """
        all_stocks = []
        for dt, stocks in by_date.items():
            for s in stocks:
                all_stocks.append(s)
        if len(all_stocks) < 5000:
            return {}

        learned = {}

        # DIP: learn mom_min, mom_max, max_beta
        best_sharpe = -999
        best_p = STRATEGY_DEFAULTS['DIP'].copy()
        for mom_min in [-20, -15, -12, -10]:
            for mom_max in [-5, -3, -2, -1]:
                if mom_max <= mom_min:
                    continue
                for max_beta in [1.2, 1.5, 2.0]:
                    p = {'mom_min': mom_min, 'mom_max': mom_max,
                         'max_beta': max_beta, 'min_vol': 0.3}
                    rets = [s.get('fwd_5d', 0) for s in all_stocks
                            if mom_min < _mom5(s) < mom_max
                            and _beta(s) < max_beta
                            and _vol(s) > 0.3
                            and _mcap(s) >= 30]
                    if len(rets) < 100:
                        continue
                    sharpe = np.mean(rets) / max(np.std(rets), 0.01)
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_p = p
        learned['DIP'] = best_p
        logger.info("StrategySelector v17: DIP learned %s (sharpe=%.3f)", best_p, best_sharpe)

        # OVERSOLD: learn mom_max, max_d20h, max_beta
        best_sharpe = -999
        best_p = STRATEGY_DEFAULTS['OVERSOLD'].copy()
        for mom_max in [-8, -5, -3]:
            for max_d20h in [-15, -10, -7, -5]:
                for max_beta in [1.5, 2.0, 2.5]:
                    p = {'mom_max': mom_max, 'max_d20h': max_d20h, 'max_beta': max_beta}
                    rets = [s.get('fwd_5d', 0) for s in all_stocks
                            if _mom5(s) < mom_max
                            and _d20h(s) < max_d20h
                            and _beta(s) < max_beta
                            and _mcap(s) >= 30]
                    if len(rets) < 100:
                        continue
                    sharpe = np.mean(rets) / max(np.std(rets), 0.01)
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_p = p
        learned['OVERSOLD'] = best_p
        logger.info("StrategySelector v17: OVERSOLD learned %s (sharpe=%.3f)", best_p, best_sharpe)

        # VOL_U: learn vol_low, vol_high, max_beta
        best_sharpe = -999
        best_p = STRATEGY_DEFAULTS['VOL_U'].copy()
        for vol_low in [0.3, 0.5, 0.7]:
            for vol_high in [1.5, 2.0, 2.5, 3.0]:
                for max_beta in [1.2, 1.5, 2.0]:
                    p = {'vol_low': vol_low, 'vol_high': vol_high, 'max_beta': max_beta}
                    rets = [s.get('fwd_5d', 0) for s in all_stocks
                            if (_vol(s) < vol_low or _vol(s) > vol_high)
                            and _beta(s) < max_beta
                            and _mcap(s) >= 30]
                    if len(rets) < 100:
                        continue
                    sharpe = np.mean(rets) / max(np.std(rets), 0.01)
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_p = p
        learned['VOL_U'] = best_p
        logger.info("StrategySelector v17: VOL_U learned %s (sharpe=%.3f)", best_p, best_sharpe)

        # RS: learn min_mom5, min_d20h, max_beta
        best_sharpe = -999
        best_p = STRATEGY_DEFAULTS['RS'].copy()
        for min_mom5 in [-2, 0, 1, 2]:
            for min_d20h in [-10, -5, -3, 0]:
                for max_beta in [1.2, 1.5, 2.0]:
                    p = {'min_mom5': min_mom5, 'min_d20h': min_d20h, 'max_beta': max_beta}
                    rets = [s.get('fwd_5d', 0) for s in all_stocks
                            if _mom5(s) > min_mom5
                            and _d20h(s) > min_d20h
                            and _beta(s) < max_beta
                            and _mcap(s) >= 30]
                    if len(rets) < 100:
                        continue
                    sharpe = np.mean(rets) / max(np.std(rets), 0.01)
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_p = p
        learned['RS'] = best_p
        logger.info("StrategySelector v17: RS learned %s (sharpe=%.3f)", best_p, best_sharpe)

        return learned

    def select(self, vix, breadth):
        """Select best strategy for current conditions.

        Returns (strategy_name, condition).
        """
        condition = detect_condition(vix, breadth)
        name = self._best_by_condition.get(condition, 'DIP')
        return name, condition

    def get_picks(self, strategy_name, stocks, macro=None):
        """Run selected strategy on stock pool with learned params."""
        spec = STRATEGIES.get(strategy_name)
        if not spec:
            return []
        params = self._learned_params.get(strategy_name)
        return spec['fn'](stocks, macro, params=params)

    def get_all_picks(self, stocks, macro=None):
        """Run ALL strategies with learned thresholds, rank by volume."""
        result = {}
        for name, spec in STRATEGIES.items():
            params = self._learned_params.get(name)
            picks = spec['fn'](stocks, macro, params=params)
            picks.sort(key=lambda x: -_vol(x))
            result[name] = picks[:MAX_PER_STRATEGY]
        return result

    def get_ranked_picks(self, stocks, macro=None, market_regime=None):
        """Get unified ranked list across all strategies.
        Returns list of (strategy_name, pick_dict) sorted by volume_ratio desc.
        Deduped by symbol, max 2 per strategy, max 8 total.

        v17: Each strategy uses learned thresholds.
        v16: market_regime=(trend, vol_regime) boosts the preferred strategy.
        """
        all_picks = []
        for name, spec in STRATEGIES.items():
            params = self._learned_params.get(name)
            picks = spec['fn'](stocks, macro, params=params)
            for p in picks:
                p['_strategy'] = name
                all_picks.append((name, p))

        # v16: regime-adaptive sorting — preferred strategy first, then volume desc
        if market_regime:
            preferred = REGIME_STRATEGY_MAP.get(market_regime, 'DIP')
            all_picks.sort(key=lambda x: (
                0 if x[0] == preferred else 1,  # preferred strategy first
                -_vol(x[1])                      # then volume_ratio desc
            ))
        else:
            all_picks.sort(key=lambda x: -_vol(x[1]))

        # Enforce limits
        seen = set()
        strat_count = defaultdict(int)
        result = []
        for strat, p in all_picks:
            sym = p.get('symbol', '')
            if sym in seen:
                continue
            if strat_count[strat] >= MAX_PER_STRATEGY:
                continue
            if len(result) >= MAX_TOTAL_PICKS:
                break
            seen.add(sym)
            strat_count[strat] += 1
            result.append((strat, p))
        return result

    def get_sltp(self, strategy_name):
        """Get SL/TP defaults for a strategy."""
        return STRATEGY_SLTP.get(strategy_name, STRATEGY_SLTP['DIP'])

    def needs_refit(self, days=30):
        if not self._fitted:
            return True
        return (time.time() - self._fit_time) > days * 86400

    # === Data Loading ===

    def _load_data(self, max_date=None):
        """Load stock data with forward returns for strategy backtesting."""
        conn = sqlite3.connect(str(DB_PATH))
        date_filter = f"AND s.date <= '{max_date}'" if max_date else ""
        rows = conn.execute(f"""
            SELECT s.symbol, s.date, s.close, sf.sector, sf.beta,
                   sf.pe_forward, sf.market_cap, sf.avg_volume,
                   LAG(s.close, 5) OVER (PARTITION BY s.symbol ORDER BY s.date) as c5a,
                   LAG(s.close, 20) OVER (PARTITION BY s.symbol ORDER BY s.date) as c20a,
                   LEAD(s.close, 5) OVER (PARTITION BY s.symbol ORDER BY s.date) as c5f,
                   s.high, s.low, s.volume,
                   m.vix_close, mb.pct_above_20d_ma
            FROM stock_daily_ohlc s
            JOIN stock_fundamentals sf ON s.symbol = sf.symbol
            LEFT JOIN macro_snapshots m ON s.date = m.date
            LEFT JOIN market_breadth mb ON s.date = mb.date
            WHERE s.close > 0 AND sf.market_cap > 3e9 AND sf.avg_volume > 100000
            AND m.vix_close IS NOT NULL AND s.date >= date('now', '-15 months')
            {date_filter}
            ORDER BY s.symbol, s.date
        """).fetchall()
        conn.close()

        data = []
        for r in rows:
            if not all([r[8], r[9], r[10]]): continue
            if r[8] <= 0 or r[9] <= 0: continue

            close = r[2]
            high_val = r[11] or close
            low_val = r[12] or close

            data.append({
                'symbol': r[0], 'date': r[1], 'close': close,
                'sector': r[3] or '', 'beta': r[4] or 1,
                'pe_forward': r[5], 'market_cap': r[6] or 1e9,
                'mom_5d': (close / r[8] - 1) * 100,
                'mom_20d': (close / r[9] - 1) * 100,
                'fwd_5d': (r[10] / close - 1) * 100,
                'd20h': -5,  # simplified, would need 20d high
                'vol_ratio': r[13] / r[7] if r[7] > 0 else 1,
                'vix': r[14], 'breadth': r[15] or 50,
            })

        logger.info("StrategySelector: loaded %d stock-days", len(data))
        return data

    # === DB Persistence ===

    def _ensure_tables(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_selection (
                condition TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                sharpe REAL,
                avg_return REAL,
                win_rate REAL,
                n_days INTEGER,
                fit_date TEXT DEFAULT (date('now')),
                UNIQUE(condition)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discovery_strategy_picks (
                scan_date TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                rank INTEGER,
                symbol TEXT NOT NULL,
                score REAL,
                rationale TEXT,
                UNIQUE(scan_date, strategy_name, symbol)
            )
        """)
        conn.commit()
        conn.close()

    def save_to_db(self):
        import json as _json
        conn = sqlite3.connect(str(DB_PATH))
        for condition, strat_name in self._best_by_condition.items():
            stats = self._fit_stats.get((condition, strat_name), {})
            conn.execute("""
                INSERT OR REPLACE INTO strategy_selection
                (condition, strategy_name, sharpe, avg_return, win_rate, n_days)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (condition, strat_name,
                  stats.get('sharpe'), stats.get('avg'),
                  stats.get('wr'), stats.get('n')))
        # v17: Save learned strategy thresholds
        if self._learned_params:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_learned_params (
                    strategy_name TEXT NOT NULL PRIMARY KEY,
                    params_json TEXT NOT NULL,
                    fit_date TEXT DEFAULT (date('now'))
                )
            """)
            for strat, params in self._learned_params.items():
                conn.execute("""
                    INSERT OR REPLACE INTO strategy_learned_params
                    (strategy_name, params_json) VALUES (?, ?)
                """, (strat, _json.dumps(params)))
        conn.commit()
        conn.close()

    def load_from_db(self):
        import json as _json
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT condition, strategy_name FROM strategy_selection").fetchall()
        if not rows:
            conn.close()
            return False
        self._best_by_condition = {r[0]: r[1] for r in rows}
        # v17: Load learned thresholds
        try:
            param_rows = conn.execute(
                "SELECT strategy_name, params_json FROM strategy_learned_params"
            ).fetchall()
            self._learned_params = {r[0]: _json.loads(r[1]) for r in param_rows}
        except Exception:
            self._learned_params = {}
        conn.close()
        self._fitted = True
        self._fit_time = time.time()
        logger.info("StrategySelector: loaded from DB — %s learned_params=%s",
                     self._best_by_condition,
                     {k: len(v) for k, v in self._learned_params.items()})
        return True

    def save_picks(self, scan_date, all_picks):
        """Save all strategies' picks for UI display."""
        import json
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "DELETE FROM discovery_strategy_picks WHERE scan_date=?",
            (scan_date,))
        for strat_name, picks in all_picks.items():
            for rank, p in enumerate(picks, 1):
                mom = _safe(p.get('mom_5d', p.get('momentum_5d')), 0)
                sector = p.get('sector', '')
                beta = _safe(p.get('beta'), 1)
                pe = p.get('pe_forward')
                rationale = json.dumps({
                    'sector': sector, 'mom_5d': round(mom, 1),
                    'beta': round(beta, 2), 'pe': round(pe, 0) if pe else None,
                })
                conn.execute("""
                    INSERT OR REPLACE INTO discovery_strategy_picks
                    (scan_date, strategy_name, rank, symbol, score, rationale)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (scan_date, strat_name, rank, p.get('symbol', ''),
                      round(mom, 1), rationale))
        conn.commit()
        conn.close()

    def get_stats(self):
        return {
            'fitted': self._fitted,
            'best_by_condition': self._best_by_condition,
            'fit_stats': {f'{c}_{s}': v for (c, s), v in self._fit_stats.items()},
        }
