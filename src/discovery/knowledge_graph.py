"""
Knowledge Graph — stock relationships, context flags, macro impact chains.
Part of Discovery v11.0 Contextual Intelligence.

Maps: supply chains, sector dependencies, speculative flags, macro sensitivities.
Used by ContextScorer to penalize bad picks (PSNY mom=+13% shouldn't be selected).
"""
import logging
import sqlite3
import json
import numpy as np
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'

# Known supply chains (major tiers)
SUPPLY_CHAINS = {
    'semiconductor': {
        'raw': ['FCX', 'NEM'],
        'equipment': ['ASML', 'AMAT', 'LRCX', 'KLAC'],
        'foundry': ['TSM'],
        'memory': ['MU'],
        'design': ['NVDA', 'AMD', 'AVGO', 'QCOM', 'INTC', 'MRVL'],
        'packaging': ['AMKR', 'ASX'],
        'customer': ['MSFT', 'GOOGL', 'AMZN', 'META', 'AAPL'],
    },
    'energy': {
        'upstream': ['XOM', 'CVX', 'COP', 'EOG', 'DVN', 'PXD', 'FANG'],
        'midstream': ['WMB', 'KMI', 'ET', 'MPLX', 'OKE'],
        'downstream': ['MPC', 'VLO', 'PSX'],
        'services': ['SLB', 'HAL', 'BKR'],
    },
    'auto': {
        'materials': ['AA', 'NUE', 'STLD'],
        'parts': ['APTV', 'BWA', 'LEA', 'ALV'],
        'assembly': ['F', 'GM', 'TSLA', 'RIVN'],
        'dealers': ['AN', 'PAG', 'LAD', 'SAH'],
    },
    'healthcare': {
        'pharma': ['JNJ', 'PFE', 'MRK', 'LLY', 'ABBV', 'BMY'],
        'biotech': ['AMGN', 'GILD', 'REGN', 'VRTX', 'BIIB'],
        'devices': ['MDT', 'ABT', 'SYK', 'BSX', 'EW'],
        'insurance': ['UNH', 'CI', 'HUM', 'CVS', 'ELV'],
    },
}

# Macro impact chains (data-validated from cross-year analysis)
MACRO_CHAINS = [
    {'trigger': 'CRUDE_SPIKE', 'condition': 'crude_5d_change > 5%',
     'positive': ['Energy'], 'negative': ['Consumer Cyclical', 'Industrials', 'Technology'],
     'magnitude': 1.5, 'evidence': '2022-03, 2022-06, 2026-03'},
    {'trigger': 'VIX_SPIKE', 'condition': 'VIX > 30',
     'positive': ['Utilities'], 'negative': ['Technology', 'Consumer Cyclical'],
     'magnitude': 2.0, 'evidence': '2022-01, 2022-06, 2022-10'},
    {'trigger': 'RATE_HIKE', 'condition': 'yield_10y rising > 0.2%/month',
     'positive': ['Financial Services'], 'negative': ['Real Estate', 'Utilities'],
     'magnitude': 1.0, 'evidence': '2022 full year'},
    {'trigger': 'BREADTH_CRASH', 'condition': 'breadth < 20%',
     'positive': [], 'negative': ['ALL'],
     'magnitude': 2.5, 'evidence': '2022-01, 2022-09, 2025-03'},
    {'trigger': 'WAR', 'condition': 'geopolitical conflict',
     'positive': ['Energy', 'Industrials'], 'negative': ['Technology', 'Consumer Cyclical'],
     'magnitude': 2.0, 'evidence': '2022-02 (Ukraine), 2026-03 (Iran)'},
]


class KnowledgeGraph:
    """Build and query stock relationship graph."""

    def __init__(self):
        self._built = False

    def build_all(self):
        """Build complete knowledge graph."""
        self._build_supply_chains()
        self._build_sector_correlations()
        self._build_macro_sensitivities()
        self._build_speculative_flags()
        self._build_macro_impact_chains()
        self._built = True
        logger.info("KnowledgeGraph: built complete graph")

    def _build_supply_chains(self):
        """Store supply chain relationships."""
        conn = sqlite3.connect(str(DB_PATH))
        inserted = 0
        for chain_name, tiers in SUPPLY_CHAINS.items():
            tier_names = list(tiers.keys())
            for i in range(len(tier_names) - 1):
                upstream_tier = tier_names[i]
                downstream_tier = tier_names[i + 1]
                for sym_up in tiers[upstream_tier]:
                    for sym_down in tiers[downstream_tier]:
                        try:
                            conn.execute("""
                                INSERT OR REPLACE INTO stock_relationships
                                (symbol_from, symbol_to, relationship_type, strength, tier, metadata_json)
                                VALUES (?, ?, 'SUPPLY_CHAIN', 1.0, ?, ?)
                            """, (sym_up, sym_down, i,
                                  json.dumps({'chain': chain_name, 'from_tier': upstream_tier, 'to_tier': downstream_tier})))
                            inserted += 1
                        except Exception:
                            pass
        conn.commit()
        conn.close()
        logger.info("KnowledgeGraph: %d supply chain relationships", inserted)

    def _build_sector_correlations(self):
        """Compute sector-sector correlations from ETF returns."""
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute("""
            SELECT date, sector, pct_change FROM sector_etf_daily_returns
            WHERE sector NOT IN ('S&P 500', 'US Dollar', 'Treasury Long', 'Gold')
            ORDER BY date
        """).fetchall()

        daily = defaultdict(dict)
        for r in rows:
            daily[r[0]][r[1]] = r[2] or 0
        dates = sorted(daily.keys())
        sectors = sorted(set(r[1] for r in rows))

        # Build return matrix
        for i, s1 in enumerate(sectors):
            for j, s2 in enumerate(sectors):
                if i >= j:
                    continue
                r1 = [daily[d].get(s1, 0) for d in dates]
                r2 = [daily[d].get(s2, 0) for d in dates]
                corr = float(np.corrcoef(r1, r2)[0, 1])
                if abs(corr) > 0.3:
                    conn.execute("""
                        INSERT OR REPLACE INTO stock_relationships
                        (symbol_from, symbol_to, relationship_type, strength, metadata_json)
                        VALUES (?, ?, 'SECTOR_CORRELATION', ?, ?)
                    """, (s1, s2, round(corr, 3),
                          json.dumps({'type': 'sector_pair', 'correlation': round(corr, 3)})))

        conn.commit()
        conn.close()
        logger.info("KnowledgeGraph: sector correlations computed")

    def _build_macro_sensitivities(self):
        """Compute per-stock sensitivity to crude, VIX, SPY."""
        conn = sqlite3.connect(str(DB_PATH))

        # Get stock returns + macro
        rows = conn.execute("""
            SELECT s.symbol, s.date, s.close,
                   LAG(s.close) OVER (PARTITION BY s.symbol ORDER BY s.date) as prev_close,
                   m.crude_close, m.vix_close, m.spy_close
            FROM stock_daily_ohlc s
            JOIN macro_snapshots m ON s.date = m.date
            WHERE s.close > 0
            ORDER BY s.symbol, s.date
        """).fetchall()

        stock_rets = defaultdict(list)
        crude_by_sym = defaultdict(list)
        vix_by_sym = defaultdict(list)

        for r in rows:
            if r[3] and r[3] > 0:
                ret = (r[2] / r[3] - 1) * 100
                stock_rets[r[0]].append(ret)
                crude_by_sym[r[0]].append(r[4] or 75)
                vix_by_sym[r[0]].append(r[5] or 20)

        inserted = 0
        for sym in stock_rets:
            if len(stock_rets[sym]) < 100:
                continue
            rets = np.array(stock_rets[sym])
            crude = np.array(crude_by_sym[sym])
            vix_arr = np.array(vix_by_sym[sym])

            # Crude sensitivity
            crude_corr = float(np.corrcoef(crude[:-1], rets[1:])[0, 1]) if len(crude) > 10 else 0
            if abs(crude_corr) > 0.1:
                conn.execute("""
                    INSERT OR REPLACE INTO stock_context
                    (symbol, context_type, context_value, score)
                    VALUES (?, 'CRUDE_SENSITIVE', ?, ?)
                """, (sym, f'corr={crude_corr:.3f}', round(crude_corr, 3)))
                inserted += 1

            # VIX sensitivity
            vix_corr = float(np.corrcoef(vix_arr[:-1], rets[1:])[0, 1]) if len(vix_arr) > 10 else 0
            if abs(vix_corr) > 0.1:
                conn.execute("""
                    INSERT OR REPLACE INTO stock_context
                    (symbol, context_type, context_value, score)
                    VALUES (?, 'VIX_SENSITIVE', ?, ?)
                """, (sym, f'corr={vix_corr:.3f}', round(vix_corr, 3)))
                inserted += 1

        conn.commit()
        conn.close()
        logger.info("KnowledgeGraph: %d macro sensitivities computed", inserted)

    def _build_speculative_flags(self):
        """Flag speculative/risky stocks."""
        conn = sqlite3.connect(str(DB_PATH))

        # Get fundamentals
        stocks = conn.execute("""
            SELECT symbol, market_cap, beta, sector FROM stock_fundamentals
        """).fetchall()

        # Get price + volatility from OHLC
        vol_data = conn.execute("""
            SELECT symbol, AVG(close) as avg_price,
                   AVG((high-low)/NULLIF(close,0)*100) as avg_range_pct,
                   COUNT(*) as n_days
            FROM stock_daily_ohlc
            WHERE close > 0 AND date >= date('now', '-180 days')
            GROUP BY symbol
        """).fetchall()
        vol_map = {r[0]: {'price': r[1], 'range': r[2] or 3, 'days': r[3]} for r in vol_data}

        inserted = 0
        for sym, mcap, beta, sector in stocks:
            v = vol_map.get(sym, {'price': 50, 'range': 3, 'days': 0})
            flags = []
            risk_score = 0

            if v['price'] and v['price'] < 10:
                flags.append('LOW_PRICE')
                risk_score -= 0.3

            if mcap and mcap < 1e9:
                flags.append('SMALL_CAP')
                risk_score -= 0.2

            if beta and beta > 2.0:
                flags.append('HIGH_BETA')
                risk_score -= 0.2

            if v['range'] > 5:
                flags.append('HIGH_VOLATILITY')
                risk_score -= 0.3

            if v['days'] < 100:
                flags.append('LOW_HISTORY')
                risk_score -= 0.1

            if flags:
                conn.execute("""
                    INSERT OR REPLACE INTO stock_context
                    (symbol, context_type, context_value, score)
                    VALUES (?, 'SPECULATIVE_FLAG', ?, ?)
                """, (sym, json.dumps(flags), round(risk_score, 2)))
                inserted += 1

        conn.commit()
        conn.close()
        logger.info("KnowledgeGraph: %d speculative flags set", inserted)

    def _build_macro_impact_chains(self):
        """Store macro impact chains."""
        conn = sqlite3.connect(str(DB_PATH))
        for chain in MACRO_CHAINS:
            conn.execute("""
                INSERT OR REPLACE INTO macro_impact_chains
                (trigger_type, affected_sectors, direction, magnitude, historical_evidence, confidence)
                VALUES (?, ?, 'MIXED', ?, ?, 0.7)
            """, (chain['trigger'],
                  json.dumps({'positive': chain['positive'], 'negative': chain['negative']}),
                  chain['magnitude'], chain['evidence']))
        conn.commit()
        conn.close()
        logger.info("KnowledgeGraph: %d macro impact chains stored", len(MACRO_CHAINS))

    def get_context(self, symbol: str) -> dict:
        """Get all context for a stock."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            # Context flags
            flags = conn.execute("""
                SELECT context_type, context_value, score
                FROM stock_context WHERE symbol = ?
            """, (symbol,)).fetchall()

            # Supply chain
            upstream = conn.execute("""
                SELECT symbol_from, metadata_json FROM stock_relationships
                WHERE symbol_to = ? AND relationship_type = 'SUPPLY_CHAIN'
            """, (symbol,)).fetchall()

            downstream = conn.execute("""
                SELECT symbol_to, metadata_json FROM stock_relationships
                WHERE symbol_from = ? AND relationship_type = 'SUPPLY_CHAIN'
            """, (symbol,)).fetchall()

            return {
                'flags': {r[0]: {'value': r[1], 'score': r[2]} for r in flags},
                'upstream': [{'symbol': r[0], 'meta': json.loads(r[1]) if r[1] else {}} for r in upstream],
                'downstream': [{'symbol': r[0], 'meta': json.loads(r[1]) if r[1] else {}} for r in downstream],
            }
        finally:
            conn.close()

    def get_risk_score(self, symbol: str) -> float:
        """Get aggregate risk score for a stock. Negative = risky."""
        ctx = self.get_context(symbol)
        score = 0
        for flag_type, data in ctx['flags'].items():
            score += data.get('score', 0)
        return round(score, 2)

    def get_stats(self) -> dict:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            n_rel = conn.execute('SELECT COUNT(*) FROM stock_relationships').fetchone()[0]
            n_ctx = conn.execute('SELECT COUNT(*) FROM stock_context').fetchone()[0]
            n_chains = conn.execute('SELECT COUNT(*) FROM macro_impact_chains').fetchone()[0]
            return {'relationships': n_rel, 'contexts': n_ctx, 'impact_chains': n_chains, 'built': self._built}
        finally:
            conn.close()
