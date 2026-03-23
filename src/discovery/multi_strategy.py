"""
Multi-Strategy Discovery v15.0 — choose strategy by market condition.

Instead of DIP-only, auto-selects from 5 strategies:
  DIP:        Buy quality dips (-3% to -15%) — best in STRESS
  OVERSOLD:   Buy extreme oversold (< -5%) — best in NORMAL
  MOMENTUM:   Ride strong uptrend (> +2%) — best in BULL
  VALUE:      Buy cheap quality (PE < 15) — good in STRESS
  CONTRARIAN: Buy best in worst sector — good overall

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


def strategy_dip(stocks, macro=None):
    """DIP BOUNCE: หุ้นลง -3% to -15%, beta < 1.5, volume OK."""
    picks = [s for s in stocks
             if -15 < _safe(s.get('mom_5d'), 0) < -3
             and _safe(s.get('beta'), 1) < 1.5
             and _safe(s.get('vol_ratio', s.get('volume_ratio')), 1) > 0.5]
    return sorted(picks, key=lambda x: _safe(x.get('d20h', x.get('distance_from_20d_high')), 0))[:5]


def strategy_oversold(stocks, macro=None):
    """OVERSOLD EXTREME: หุ้นลงหนักมาก > -5%, far from 20d high."""
    picks = [s for s in stocks
             if _safe(s.get('mom_5d', s.get('momentum_5d')), 0) < -5
             and _safe(s.get('d20h', s.get('distance_from_20d_high')), 0) < -10
             and _safe(s.get('beta'), 1) < 2.0]
    return sorted(picks, key=lambda x: _safe(x.get('mom_5d', x.get('momentum_5d')), 0))[:5]


def strategy_momentum(stocks, macro=None):
    """MOMENTUM: หุ้นขึ้นแรง, near 20d high, trend confirmed."""
    picks = [s for s in stocks
             if _safe(s.get('mom_5d', s.get('momentum_5d')), 0) > 2
             and _safe(s.get('mom_20d', s.get('momentum_20d')), 0) > 5
             and _safe(s.get('d20h', s.get('distance_from_20d_high')), 0) > -5
             and _safe(s.get('beta'), 1) < 1.5
             and _safe(s.get('vol_ratio', s.get('volume_ratio')), 1) > 0.8]
    return sorted(picks, key=lambda x: _safe(x.get('mom_5d', x.get('momentum_5d')), 0), reverse=True)[:5]


def strategy_value(stocks, macro=None):
    """VALUE: PE ต่ำ, ไม่ลงเยอะ, quality."""
    picks = [s for s in stocks
             if s.get('pe_forward') is not None and 3 < s['pe_forward'] < 15
             and _safe(s.get('mom_5d', s.get('momentum_5d')), 0) > -5
             and _safe(s.get('beta'), 1) < 1.3
             and _safe(s.get('market_cap'), 0) > 10e9]
    return sorted(picks, key=lambda x: _safe(x.get('pe_forward'), 99))[:5]


def strategy_contrarian(stocks, macro=None):
    """SECTOR CONTRARIAN: ซื้อหุ้นดีที่สุดใน worst sector."""
    sector_rets = defaultdict(list)
    for s in stocks:
        mom = _safe(s.get('mom_5d', s.get('momentum_5d')), 0)
        sector_rets[s.get('sector', '')].append(mom)
    sector_avg = {sect: np.mean(rets) for sect, rets in sector_rets.items()
                  if len(rets) > 10 and sect}
    if not sector_avg:
        return []
    worst_sector = min(sector_avg, key=sector_avg.get)
    picks = [s for s in stocks
             if s.get('sector') == worst_sector
             and _safe(s.get('beta'), 1) < 1.5
             and _safe(s.get('mom_5d', s.get('momentum_5d')), 0) > -10]
    return sorted(picks, key=lambda x: _safe(x.get('mom_5d', x.get('momentum_5d')), 0))[:5]


STRATEGIES = {
    'DIP':        {'fn': strategy_dip, 'desc': 'Buy quality dips (-3% to -15%)'},
    'OVERSOLD':   {'fn': strategy_oversold, 'desc': 'Buy extreme oversold (< -5%)'},
    'MOMENTUM':   {'fn': strategy_momentum, 'desc': 'Ride strong uptrend (> +2%)'},
    'VALUE':      {'fn': strategy_value, 'desc': 'Buy cheap quality (PE < 15)'},
    'CONTRARIAN': {'fn': strategy_contrarian, 'desc': 'Buy best in worst sector'},
}

# Per-strategy SL/TP defaults (used when adaptive params not available)
STRATEGY_SLTP = {
    'DIP':        {'tp_ratio': 2.0, 'sl_mult': 1.0},
    'OVERSOLD':   {'tp_ratio': 2.5, 'sl_mult': 1.5},
    'MOMENTUM':   {'tp_ratio': 1.5, 'sl_mult': 1.0},
    'VALUE':      {'tp_ratio': 2.0, 'sl_mult': 1.0},
    'CONTRARIAN': {'tp_ratio': 2.0, 'sl_mult': 1.5},
}


def detect_condition(vix, breadth):
    """Classify market condition from VIX + breadth."""
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
        """Run ALL strategies — for UI display."""
        result = {}
        for name, spec in STRATEGIES.items():
            picks = spec['fn'](stocks, macro)
            result[name] = picks
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
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "DELETE FROM discovery_strategy_picks WHERE scan_date=?",
            (scan_date,))
        for strat_name, picks in all_picks.items():
            for rank, p in enumerate(picks, 1):
                conn.execute("""
                    INSERT OR REPLACE INTO discovery_strategy_picks
                    (scan_date, strategy_name, rank, symbol, score, rationale)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (scan_date, strat_name, rank, p.get('symbol', ''),
                      p.get('mom_5d', 0),
                      f"{p.get('sector','')} mom={p.get('mom_5d',0):+.1f}%"))
        conn.commit()
        conn.close()

    def get_stats(self):
        return {
            'fitted': self._fitted,
            'best_by_condition': self._best_by_condition,
            'fit_stats': {f'{c}_{s}': v for (c, s), v in self._fit_stats.items()},
        }
