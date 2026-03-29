"""
Knowledge Graph — stock relationships, context flags, macro impact chains.
Part of Discovery v11.0 Contextual Intelligence.

Maps: supply chains, sector dependencies, speculative flags, macro sensitivities.
Used by ContextScorer to penalize bad picks (PSNY mom=+13% shouldn't be selected).
"""
import logging
from database.orm.base import get_session
from sqlalchemy import text
import json
import numpy as np
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)

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
        inserted = 0
        with get_session() as session:
            for chain_name, tiers in SUPPLY_CHAINS.items():
                tier_names = list(tiers.keys())
                for i in range(len(tier_names) - 1):
                    upstream_tier = tier_names[i]
                    downstream_tier = tier_names[i + 1]
                    for sym_up in tiers[upstream_tier]:
                        for sym_down in tiers[downstream_tier]:
                            try:
                                session.execute(text("""
                                    INSERT OR REPLACE INTO stock_relationships
                                    (symbol_from, symbol_to, relationship_type, strength, tier, metadata_json)
                                    VALUES (:p0, :p1, 'SUPPLY_CHAIN', 1.0, :p2, :p3)
                                """), {'p0': sym_up, 'p1': sym_down, 'p2': i,
                                       'p3': json.dumps({'chain': chain_name, 'from_tier': upstream_tier, 'to_tier': downstream_tier})})
                                inserted += 1
                            except Exception:
                                pass
        logger.info("KnowledgeGraph: %d supply chain relationships", inserted)

    def _build_sector_correlations(self):
        """Compute sector-sector correlations from ETF returns."""
        with get_session() as session:
            rows = session.execute(text("""
                SELECT date, sector, pct_change FROM sector_etf_daily_returns
                WHERE sector NOT IN ('S&P 500', 'US Dollar', 'Treasury Long', 'Gold')
                ORDER BY date
            """)).fetchall()

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
                        session.execute(text("""
                            INSERT OR REPLACE INTO stock_relationships
                            (symbol_from, symbol_to, relationship_type, strength, metadata_json)
                            VALUES (:p0, :p1, 'SECTOR_CORRELATION', :p2, :p3)
                        """), {'p0': s1, 'p1': s2, 'p2': round(corr, 3),
                               'p3': json.dumps({'type': 'sector_pair', 'correlation': round(corr, 3)})})
        logger.info("KnowledgeGraph: sector correlations computed")

    def _build_macro_sensitivities(self):
        """Compute per-stock sensitivity to crude CHANGES and VIX CHANGES.

        v13.1 fix: correlate crude/VIX daily CHANGE with stock daily RETURN.
        Loads macro changes separately to avoid SQL LAG cross-symbol bug.
        """
        with get_session() as session:
            # Load macro daily changes (computed in Python, not SQL LAG)
            macro_rows = session.execute(text("""
                SELECT date, crude_close, vix_close FROM macro_snapshots
                WHERE crude_close > 0 AND vix_close > 0
                ORDER BY date
            """)).fetchall()

            macro_chg = {}  # date -> (crude_chg%, vix_chg_pts)
            for i in range(1, len(macro_rows)):
                dt = macro_rows[i][0]
                prev_crude = macro_rows[i-1][1]
                prev_vix = macro_rows[i-1][2]
                if prev_crude > 0:
                    crude_chg = (macro_rows[i][1] / prev_crude - 1) * 100
                    vix_chg = macro_rows[i][2] - prev_vix
                    macro_chg[dt] = (crude_chg, vix_chg)

            # Load stock daily returns
            stock_rows = session.execute(text("""
                SELECT symbol, date, close,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close
                FROM stock_daily_ohlc
                WHERE close > 0
                ORDER BY symbol, date
            """)).fetchall()

        stock_rets = defaultdict(list)
        crude_chg_by_sym = defaultdict(list)
        vix_chg_by_sym = defaultdict(list)

        for sym, dt, close, prev_close in stock_rows:
            if not prev_close or prev_close <= 0:
                continue
            if dt not in macro_chg:
                continue
            stock_ret = (close / prev_close - 1) * 100
            c_chg, v_chg = macro_chg[dt]

            stock_rets[sym].append(stock_ret)
            crude_chg_by_sym[sym].append(c_chg)
            vix_chg_by_sym[sym].append(v_chg)

        inserted = 0
        with get_session() as session:
            for sym in stock_rets:
                if len(stock_rets[sym]) < 100:
                    continue
                rets = np.array(stock_rets[sym])
                crude_arr = np.array(crude_chg_by_sym[sym])
                vix_arr = np.array(vix_chg_by_sym[sym])

                # Crude sensitivity: corr(crude daily change, stock daily return)
                crude_corr = float(np.corrcoef(crude_arr, rets)[0, 1])
                if not np.isnan(crude_corr) and abs(crude_corr) > 0.05:
                    session.execute(text("""
                        INSERT OR REPLACE INTO stock_context
                        (symbol, context_type, context_value, score)
                        VALUES (:p0, 'CRUDE_SENSITIVE', :p1, :p2)
                    """), {'p0': sym, 'p1': f'corr={crude_corr:.3f}', 'p2': round(crude_corr, 3)})
                    inserted += 1

                # VIX sensitivity: corr(VIX daily change, stock daily return)
                vix_corr = float(np.corrcoef(vix_arr, rets)[0, 1])
                if not np.isnan(vix_corr) and abs(vix_corr) > 0.05:
                    session.execute(text("""
                        INSERT OR REPLACE INTO stock_context
                        (symbol, context_type, context_value, score)
                        VALUES (:p0, 'VIX_SENSITIVE', :p1, :p2)
                    """), {'p0': sym, 'p1': f'corr={vix_corr:.3f}', 'p2': round(vix_corr, 3)})
                    inserted += 1
        logger.info("KnowledgeGraph: %d macro sensitivities computed", inserted)

    def _build_speculative_flags(self):
        """Flag speculative/risky stocks."""
        with get_session() as session:
            # Get fundamentals
            stocks = session.execute(text("""
                SELECT symbol, market_cap, beta, sector FROM stock_fundamentals
            """)).fetchall()

            # Get price + volatility from OHLC
            vol_data = session.execute(text("""
                SELECT symbol, AVG(close) as avg_price,
                       AVG((high-low)/NULLIF(close,0)*100) as avg_range_pct,
                       COUNT(*) as n_days
                FROM stock_daily_ohlc
                WHERE close > 0 AND date >= date('now', '-180 days')
                GROUP BY symbol
            """)).fetchall()

        vol_map = {r[0]: {'price': r[1], 'range': r[2] or 3, 'days': r[3]} for r in vol_data}

        inserted = 0
        with get_session() as session:
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
                    session.execute(text("""
                        INSERT OR REPLACE INTO stock_context
                        (symbol, context_type, context_value, score)
                        VALUES (:p0, 'SPECULATIVE_FLAG', :p1, :p2)
                    """), {'p0': sym, 'p1': json.dumps(flags), 'p2': round(risk_score, 2)})
                    inserted += 1
        logger.info("KnowledgeGraph: %d speculative flags set", inserted)

    def _build_macro_impact_chains(self):
        """Store macro impact chains (clear old + insert fresh)."""
        with get_session() as session:
            session.execute(text("DELETE FROM macro_impact_chains"))
            for chain in MACRO_CHAINS:
                session.execute(text("""
                    INSERT INTO macro_impact_chains
                    (trigger_type, affected_sectors, direction, magnitude, historical_evidence, confidence)
                    VALUES (:p0, :p1, 'MIXED', :p2, :p3, 0.7)
                """), {'p0': chain['trigger'],
                       'p1': json.dumps({'positive': chain['positive'], 'negative': chain['negative']}),
                       'p2': chain['magnitude'], 'p3': chain['evidence']})
        logger.info("KnowledgeGraph: %d macro impact chains stored", len(MACRO_CHAINS))

    def get_context(self, symbol: str) -> dict:
        """Get all context for a stock."""
        with get_session() as session:
            # Context flags
            flags = session.execute(text("""
                SELECT context_type, context_value, score
                FROM stock_context WHERE symbol = :p0
            """), {'p0': symbol}).fetchall()

            # Supply chain
            upstream = session.execute(text("""
                SELECT symbol_from, metadata_json FROM stock_relationships
                WHERE symbol_to = :p0 AND relationship_type = 'SUPPLY_CHAIN'
            """), {'p0': symbol}).fetchall()

            downstream = session.execute(text("""
                SELECT symbol_to, metadata_json FROM stock_relationships
                WHERE symbol_from = :p0 AND relationship_type = 'SUPPLY_CHAIN'
            """), {'p0': symbol}).fetchall()

            return {
                'flags': {r[0]: {'value': r[1], 'score': r[2]} for r in flags},
                'upstream': [{'symbol': r[0], 'meta': json.loads(r[1]) if r[1] else {}} for r in upstream],
                'downstream': [{'symbol': r[0], 'meta': json.loads(r[1]) if r[1] else {}} for r in downstream],
            }

    def get_risk_score(self, symbol: str) -> float:
        """Get aggregate risk score for a stock. Negative = risky."""
        ctx = self.get_context(symbol)
        score = 0
        for flag_type, data in ctx['flags'].items():
            score += data.get('score', 0)
        return round(score, 2)

    def get_stats(self) -> dict:
        with get_session() as session:
            n_rel = session.execute(text('SELECT COUNT(*) FROM stock_relationships')).fetchone()[0]
            n_ctx = session.execute(text('SELECT COUNT(*) FROM stock_context')).fetchone()[0]
            n_chains = session.execute(text('SELECT COUNT(*) FROM macro_impact_chains')).fetchone()[0]
            return {'relationships': n_rel, 'contexts': n_ctx, 'impact_chains': n_chains, 'built': self._built}
