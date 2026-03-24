"""
Multi-Strategy Discovery v15.2 — 4 strategies ranked by volume.

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

# v15.3: quality filters (sim validated: Sharpe 1.82→2.10, Win 23→25/33)
MAX_VOLUME_RATIO = 3.0   # vol > 3x = panic sell (WR 42.9%, avg -2.44%)
MIN_MCAP_B = 30           # mcap < $30B = small cap don't bounce (worst $48B vs best $73B)


def _mcap(s):
    return _safe(s.get('market_cap'), 1e9) / 1e9


def _filter_quality(stocks):
    """Pre-filter: remove panic-sell + small cap stocks."""
    return [s for s in stocks if _vol(s) <= MAX_VOLUME_RATIO and _mcap(s) >= MIN_MCAP_B]


def strategy_dip(stocks, macro=None):
    """DIP BOUNCE: หุ้นลง -3% to -15%, beta < 1.5, volume OK."""
    picks = [s for s in _filter_quality(stocks)
             if -15 < _mom5(s) < -3
             and _beta(s) < 1.5
             and _vol(s) > 0.3]
    return sorted(picks, key=lambda x: _d20h(x))[:5]


def strategy_oversold(stocks, macro=None):
    """OVERSOLD EXTREME: หุ้นลงหนักมาก > -5%, far from 20d high."""
    picks = [s for s in _filter_quality(stocks)
             if _mom5(s) < -5
             and _d20h(s) < -10
             and _beta(s) < 2.0]
    return sorted(picks, key=lambda x: _mom5(x))[:5]


def strategy_value(stocks, macro=None):
    """VALUE: PE ต่ำ, ไม่ลงเยอะ, quality."""
    picks = [s for s in _filter_quality(stocks)
             if s.get('pe_forward') is not None and 3 < s['pe_forward'] < 15
             and _mom5(s) > -10
             and _beta(s) < 1.5
             and _safe(s.get('market_cap'), 0) > 5e9]
    return sorted(picks, key=lambda x: _safe(x.get('pe_forward'), 99))[:5]


def strategy_contrarian(stocks, macro=None):
    """SECTOR CONTRARIAN: ซื้อหุ้นดีที่สุดใน worst sector."""
    sector_rets = defaultdict(list)
    for s in stocks:
        sector_rets[s.get('sector', '')].append(_mom5(s))
    sector_avg = {sect: np.mean(rets) for sect, rets in sector_rets.items()
                  if len(rets) > 5 and sect}
    if not sector_avg:
        return []
    worst_sector = min(sector_avg, key=sector_avg.get)
    picks = [s for s in _filter_quality(stocks)
             if s.get('sector') == worst_sector
             and _beta(s) < 1.5
             and _mom5(s) > -15]
    return sorted(picks, key=lambda x: _mom5(x))[:5]


def strategy_vol_u(stocks, macro=None):
    """VOL U-SHAPE: หุ้น volume ต่ำมาก (<0.5x) หรือสูงมาก (>2x) = bounce signal.
    v16: validated WR 60-69% in NORMAL/ELEVATED regime (sim 2026-03-24).
    low vol dip = fake selling → bounce. extreme vol = capitulation → mean revert."""
    picks = [s for s in _filter_quality(stocks)
             if (_vol(s) < 0.5 or _vol(s) > 2.0)
             and _beta(s) < 1.5]
    return sorted(picks, key=lambda x: abs(_vol(x) - 1.0), reverse=True)[:5]


def strategy_relative_strength(stocks, macro=None):
    """RELATIVE STRENGTH: หุ้นที่ยังขึ้นในตลาดที่ลง (momentum > 0).
    v16: validated WR 54% in MILD_DOWN (vs DIP 42%), 56% in MILD_UP (vs DIP 51%).
    Logic: stocks going UP while market drifts down = institutional accumulation,
    relative strength = quality that holds up. NOT mean-reversion."""
    picks = [s for s in _filter_quality(stocks)
             if _mom5(s) > 0           # positive 5d momentum (going up)
             and _d20h(s) > -5         # near 20d high (strong)
             and _beta(s) < 1.5]
    # Rank by momentum desc (strongest relative strength first)
    return sorted(picks, key=lambda x: -_mom5(x))[:5]


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
    """Learn which strategy works best per condition, auto-select."""

    def __init__(self):
        self._best_by_condition = {}  # condition → strategy name
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

        self._fitted = True
        self._fit_time = time.time()
        self.save_to_db()

        elapsed = time.time() - t0
        logger.info("StrategySelector: fitted in %.1fs — %s", elapsed,
                     self._best_by_condition)
        return True

    def select(self, vix, breadth):
        """Select best strategy for current conditions.

        Returns (strategy_name, condition).
        """
        condition = detect_condition(vix, breadth)
        name = self._best_by_condition.get(condition, 'DIP')
        return name, condition

    def get_picks(self, strategy_name, stocks, macro=None):
        """Run selected strategy on stock pool."""
        spec = STRATEGIES.get(strategy_name)
        if not spec:
            return []
        return spec['fn'](stocks, macro)

    def get_all_picks(self, stocks, macro=None):
        """Run ALL strategies, rank by volume, enforce max per strategy."""
        result = {}
        for name, spec in STRATEGIES.items():
            picks = spec['fn'](stocks, macro)
            # Sort each strategy's picks by volume_ratio desc
            picks.sort(key=lambda x: -_vol(x))
            result[name] = picks[:MAX_PER_STRATEGY]
        return result

    def get_ranked_picks(self, stocks, macro=None, market_regime=None):
        """Get unified ranked list across all strategies.
        Returns list of (strategy_name, pick_dict) sorted by volume_ratio desc.
        Deduped by symbol, max 2 per strategy, max 8 total.

        v16: market_regime=(trend, vol_regime) boosts the preferred strategy
        for current regime to the top of the ranking.
        """
        all_picks = []
        for name, spec in STRATEGIES.items():
            picks = spec['fn'](stocks, macro)
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
        conn.commit()
        conn.close()

    def load_from_db(self):
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT condition, strategy_name FROM strategy_selection").fetchall()
        conn.close()
        if not rows:
            return False
        self._best_by_condition = {r[0]: r[1] for r in rows}
        self._fitted = True
        self._fit_time = time.time()
        logger.info("StrategySelector: loaded from DB — %s",
                     self._best_by_condition)
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
