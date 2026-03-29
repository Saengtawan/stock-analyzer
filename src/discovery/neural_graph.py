"""
Neural Graph — connects all data layers into unified risk assessment.
Part of Discovery v14.0.

4 Layers:
  L0: Leading signals (BTC 3d momentum)
  L1: Thematic clusters (return-correlation, auto-detected)
  L2: Sector-macro cascade (vulnerability to VIX/crude shocks)
  L3: Stock risk profile (beta, PE, speculative, sensitivities)

Output: risk_score -1.0 (very risky) to +1.0 (very safe)
Used by sizer.py to adjust position size.
"""
import logging
from database.orm.base import get_session
from sqlalchemy import text
import numpy as np
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)


class NeuralGraph:
    """Connects all data layers into unified risk assessment."""

    def __init__(self, knowledge_graph, adaptive_params=None):
        self._kg = knowledge_graph
        self._adaptive = adaptive_params
        self._clusters = {}          # symbol -> cluster_id
        self._cluster_names = {}     # cluster_id -> name
        self._sector_vuln = {}       # (sector, event) -> vulnerability
        self._built = False
        self._ensure_tables()

    def build_all(self):
        """Build all graph layers. Safe to call multiple times."""
        self._build_thematic_clusters()
        self._build_sector_vulnerability()
        self._built = True
        logger.info("NeuralGraph: built all layers (clusters=%d, vuln=%d)",
                     len(set(self._clusters.values())),
                     len(self._sector_vuln))

    # === Main API ===

    def compute_risk_score(self, symbol, sector, macro):
        """Compute unified risk score from all graph layers.

        Returns dict with:
          risk_score: -1.0 (very risky) to +1.0 (very safe)
          risk_factors: list of contributing factors
          risk_level: HIGH/MODERATE/LOW
          size_mult: position size multiplier (0.5-1.0)
        """
        factors = []
        score = 0.0

        # === Layer 0: BTC leading signal -- REMOVED (v17) ===
        # IC = +0.004 = noise. No predictive power for stock 5d returns.
        # BTC data still collected via cron for future analysis.

        # === Layer 1: Thematic cluster ===
        # v17: Cluster health uses outcome-based thresholds from data
        # 248 clusters, spread +1.6% to -0.8%. Penalize negative clusters.
        cluster_id = self._clusters.get(symbol)
        if cluster_id is not None:
            cluster_name = self._cluster_names.get(cluster_id, f'C{cluster_id}')
            cluster_health = self._get_cluster_health(cluster_id, macro)
            if cluster_health is not None:
                # v17: Proportional penalty/bonus instead of hardcoded -1.0/+1.0
                if cluster_health < 0:
                    score += cluster_health * 0.15  # proportional: -0.5% -> -0.075
                    if cluster_health < -0.5:
                        factors.append(f'CLUSTER_WEAK: {cluster_name} health={cluster_health:+.1f}')
                elif cluster_health > 0.5:
                    score += cluster_health * 0.05  # smaller bonus
                    factors.append(f'CLUSTER_STRONG: {cluster_name}')

        # === Layer 2: Sector-macro -- VIX adaptive ===
        # v17: VIX bounce threshold learned from data (28 optimal, not 30)
        # VIX 25-28 is dead zone (Sharpe +0.004), VIX >= 28 is bounce (+0.211)
        # VIX 15-18 is also dead zone (Sharpe -0.026)
        vix = macro.get('vix_close') or 20
        vvix = macro.get('vvix_close')

        # v17: Use adaptive VIX thresholds
        vix_fear = 28  # learned from data (was 30)
        vix_dead_lo = 25  # dead zone lower
        vix_dead_hi = 28  # dead zone upper (was 30)

        # VVIX signal -- v17: adaptive crisis threshold
        vvix_crisis = 120
        if self._adaptive:
            vvix_crisis = self._adaptive.get(sector, 'BULL', 'vvix_crisis')
        if vvix is not None:
            if vvix > vvix_crisis:
                score += 0.15
                factors.append(f'VVIX={vvix:.0f}>{vvix_crisis} CRISIS bounce opportunity')
            elif vvix < 80:
                score += 0.05

        # VIX signal -- v17: adaptive thresholds
        if vix >= vix_fear:
            score += 0.15
            factors.append(f'VIX={vix:.0f}>={vix_fear} bounce WR=60%')
        elif vix_dead_lo <= vix < vix_dead_hi:
            score -= 0.10
            factors.append(f'VIX={vix:.0f} dead zone ({vix_dead_lo}-{vix_dead_hi})')

        # Sector vulnerability -- REMOVED (v17)
        # SectorScorer handles sector-macro correlation dynamically.
        # Static crude_shock rank table is redundant and less current.

        # === Layer 3: Stock risk profile (from KG) ===
        try:
            ctx = self._kg.get_context(symbol)
            spec = ctx['flags'].get('SPECULATIVE_FLAG', {})
            if spec:
                spec_score = spec.get('score', 0)
                if spec_score < -0.5:
                    score -= 0.15
                    factors.append(f'SPECULATIVE: {spec_score:+.1f}')
                elif spec_score < -0.3:
                    score -= 0.08
                    factors.append(f'RISKY: {spec_score:+.1f}')

            # VIX sensitivity -- flipped for DIP strategy
            # High VIX-sensitive stocks DROP more -> but also BOUNCE more
            # Only penalize in dead zone (VIX 25-30), boost in CRISIS (>30)
            vix_sens = ctx['flags'].get('VIX_SENSITIVE', {})
            if vix_sens:
                corr_val = vix_sens.get('score', 0)
                if vix > 30 and corr_val < -0.50:
                    score += 0.05  # sensitive stocks bounce harder in CRISIS
                elif 25 <= vix < 30 and corr_val < -0.50:
                    score -= 0.10  # dead zone: sensitive stocks hurt
                    factors.append(f'VIX_SENS_DEADZONE: {corr_val:+.2f}')
        except Exception:
            pass

        # Clamp and compute size multiplier
        score = max(-1.0, min(1.0, round(score, 2)))

        # v17: Linear size mapping instead of step function
        # score -1.0 -> size 0.5, score 0.0 -> size 1.0 (proportional)
        size_mult = max(0.5, min(1.0, 1.0 + score * 0.5))
        if score < -0.4:
            level = 'HIGH'
        elif score < -0.2:
            level = 'MODERATE'
        elif score < 0:
            level = 'LOW'
        else:
            level = 'SAFE'

        return {
            'risk_score': score,
            'risk_factors': factors,
            'risk_level': level,
            'size_mult': size_mult,
        }

    # === Weekend Risk ===

    def compute_weekend_risk(self, macro):
        """Predict Monday gap risk from Friday signals.

        Uses VVIX, BTC 5d, Breadth 5d, Copper 5d, 52w Lows, VIX term structure.
        All available on Friday before weekend.

        Returns:
            score: -1 (gap down risk) to +1 (gap up likely)
            factors: list of contributing signals
            action: 'GAP_UP_LIKELY' / 'NEUTRAL' / 'GAP_DOWN_RISK'
        """
        score = 0.0
        factors = []

        # 1. VVIX: calm = safe, extreme = danger -- v17: adaptive threshold
        vvix_crisis = 120
        if self._adaptive:
            vvix_crisis = self._adaptive.get('', 'BULL', 'vvix_crisis')
        vvix = macro.get('vvix_close')
        if vvix is not None:
            if vvix < 80:
                score += 0.30
                factors.append(f'VVIX={vvix:.0f} calm -> safe weekend')
            elif vvix < 100:
                score += 0.05
            elif vvix > vvix_crisis:
                score -= 0.25
                factors.append(f'VVIX={vvix:.0f}>{vvix_crisis} extreme -> risky weekend')
            elif vvix > 100:
                score -= 0.10

        # 2. BTC 3d momentum (leads risk-off)
        btc_3d = macro.get('btc_momentum_3d')
        if btc_3d is not None:
            if btc_3d > 3:
                score += 0.15
                factors.append(f'BTC 3d={btc_3d:+.1f}% strong')
            elif btc_3d < -3:
                score -= 0.20
                factors.append(f'BTC 3d={btc_3d:+.1f}% weak -> risk-off')

        # 3. Breadth trend (5d)
        breadth_5d = macro.get('breadth_delta_5d', 0)
        if breadth_5d > 5:
            score += 0.15
            factors.append(f'Breadth 5d={breadth_5d:+.0f} improving')
        elif breadth_5d < -5:
            score -= 0.15
            factors.append(f'Breadth 5d={breadth_5d:+.0f} falling')

        # 4. VIX term structure
        vix = macro.get('vix_close', 20)
        vix3m = macro.get('vix3m_close', 22)
        if vix and vix3m:
            spread = vix - vix3m
            if spread > 2:  # backwardation = panic
                score -= 0.20
                factors.append(f'VIX backwardation {spread:+.1f} -> panic')
            elif spread < -2:  # deep contango = calm
                score += 0.10

        # 5. Breadth level (data: <15 = extreme bounce +1.76%, 15-25 = dead zone)
        breadth = macro.get('pct_above_20d_ma') or 50
        if breadth < 15:
            score -= 0.15
            factors.append(f'Breadth={breadth:.0f}% very low')
        elif breadth > 60:
            score += 0.10

        # 6. VIX level
        if vix > 30:
            score -= 0.15
            factors.append(f'VIX={vix:.0f} high')
        elif vix < 16:
            score += 0.10

        # Clamp
        score = max(-1.0, min(1.0, round(score, 2)))

        if score > 0.15:
            action = 'GAP_UP_LIKELY'
        elif score < -0.30:
            action = 'GAP_DOWN_RISK'
        else:
            action = 'NEUTRAL'

        return {
            'weekend_score': score,
            'weekend_factors': factors,
            'weekend_action': action,
        }

    # === Layer 1: Thematic Clusters ===

    def _build_thematic_clusters(self):
        """Auto-detect stock clusters from return correlations."""
        with get_session() as session:
            # Load 6-month daily returns for universe stocks
            rows = session.execute(text("""
                SELECT symbol, date, close,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev
                FROM stock_daily_ohlc
                WHERE close > 0 AND date >= date('now', '-180 days')
                ORDER BY symbol, date
            """)).fetchall()

            stock_rets = defaultdict(dict)
            for sym, dt, close, prev in rows:
                if prev and prev > 0:
                    stock_rets[sym][dt] = (close / prev - 1) * 100

            # Filter to stocks with enough data
            valid_syms = [s for s in stock_rets if len(stock_rets[s]) >= 80]
            if len(valid_syms) < 50:
                logger.warning("NeuralGraph: not enough stocks for clustering (%d)", len(valid_syms))
                return

            # Build aligned return matrix
            all_dates = sorted(set(d for s in valid_syms for d in stock_rets[s]))
            sym_to_idx = {s: i for i, s in enumerate(valid_syms)}
            ret_matrix = np.full((len(valid_syms), len(all_dates)), np.nan)

            for i, sym in enumerate(valid_syms):
                for j, dt in enumerate(all_dates):
                    if dt in stock_rets[sym]:
                        ret_matrix[i, j] = stock_rets[sym][dt]

            # Compute correlation matrix (handle NaN)
            n = len(valid_syms)
            corr_matrix = np.zeros((n, n))
            for i in range(n):
                for j in range(i, n):
                    mask = ~np.isnan(ret_matrix[i]) & ~np.isnan(ret_matrix[j])
                    if mask.sum() >= 50:
                        corr = np.corrcoef(ret_matrix[i, mask], ret_matrix[j, mask])[0, 1]
                        if not np.isnan(corr):
                            corr_matrix[i, j] = corr
                            corr_matrix[j, i] = corr
                        else:
                            corr_matrix[i, j] = corr_matrix[j, i] = 0
                    else:
                        corr_matrix[i, j] = corr_matrix[j, i] = 0
                corr_matrix[i, i] = 1.0

            # Simple clustering: group stocks with avg pairwise corr > 0.5
            # Use agglomerative approach
            dist_matrix = 1 - corr_matrix
            np.fill_diagonal(dist_matrix, 0)

            try:
                from scipy.cluster.hierarchy import fcluster, linkage
                from scipy.spatial.distance import squareform

                # Convert to condensed form
                condensed = squareform(np.clip(dist_matrix, 0, 2))
                Z = linkage(condensed, method='average')
                labels = fcluster(Z, t=0.6, criterion='distance')  # corr > 0.4
            except ImportError:
                # Fallback: simple threshold clustering
                labels = np.arange(n)  # each stock its own cluster
                visited = set()
                cluster_id = 0
                for i in range(n):
                    if i in visited:
                        continue
                    group = [i]
                    for j in range(i + 1, n):
                        if j not in visited and corr_matrix[i, j] > 0.5:
                            group.append(j)
                    for idx in group:
                        labels[idx] = cluster_id
                        visited.add(idx)
                    cluster_id += 1

            # Store clusters
            self._clusters = {}
            self._cluster_names = {}
            cluster_members = defaultdict(list)

            for i, sym in enumerate(valid_syms):
                cid = int(labels[i])
                self._clusters[sym] = cid
                cluster_members[cid].append(sym)

            # Name clusters by most common sector
            sectors_map = dict(session.execute(text(
                "SELECT symbol, sector FROM stock_fundamentals")).fetchall())

            for cid, members in cluster_members.items():
                if len(members) < 3:
                    continue
                sector_counts = defaultdict(int)
                for m in members:
                    sector_counts[sectors_map.get(m, 'Unknown')] += 1
                top_sector = max(sector_counts, key=sector_counts.get)
                self._cluster_names[cid] = f'{top_sector}_{cid}({len(members)})'

            # Save to DB
            session.execute(text("DELETE FROM stock_clusters WHERE fit_date = date('now')"))
            for sym, cid in self._clusters.items():
                n_members = len(cluster_members.get(cid, []))
                session.execute(text("""
                    INSERT OR REPLACE INTO stock_clusters
                    (symbol, cluster_id, cluster_name, n_members, fit_date)
                    VALUES (:p0, :p1, :p2, :p3, date('now'))
                """), {'p0': sym, 'p1': cid, 'p2': self._cluster_names.get(cid, f'C{cid}'), 'p3': n_members})

            n_clusters = len(set(labels))
            big_clusters = sum(1 for members in cluster_members.values() if len(members) >= 5)
            logger.info("NeuralGraph: %d clusters (%d with 5+ members) from %d stocks",
                         n_clusters, big_clusters, len(valid_syms))

    def _get_cluster_health(self, cluster_id, macro):
        """Get recent health of a cluster (avg 5d return of members)."""
        members = [s for s, c in self._clusters.items() if c == cluster_id]
        if not members:
            return None

        with get_session() as session:
            placeholders = ','.join(f':p{i}' for i in range(len(members)))
            params = {f'p{i}': m for i, m in enumerate(members)}
            rows = session.execute(text(f"""
                SELECT AVG((s1.close / s2.close - 1) * 100)
                FROM stock_daily_ohlc s1
                JOIN stock_daily_ohlc s2 ON s1.symbol = s2.symbol
                WHERE s1.symbol IN ({placeholders})
                AND s1.date = (SELECT MAX(date) FROM stock_daily_ohlc)
                AND s2.date = (SELECT MAX(date) FROM stock_daily_ohlc WHERE date < (SELECT MAX(date) FROM stock_daily_ohlc WHERE date < (SELECT MAX(date) FROM stock_daily_ohlc WHERE date < (SELECT MAX(date) FROM stock_daily_ohlc WHERE date < (SELECT MAX(date) FROM stock_daily_ohlc)))))
            """), params).fetchone()

        return rows[0] if rows and rows[0] is not None else None

    # === Layer 2: Sector-Macro Vulnerability ===

    def _build_sector_vulnerability(self):
        """Compute per-sector vulnerability to macro shocks."""
        with get_session() as session:
            # VIX spike events (VIX change > 2pts in 1 day)
            macro_rows = session.execute(text("""
                SELECT date, vix_close, crude_close FROM macro_snapshots
                WHERE vix_close IS NOT NULL ORDER BY date
            """)).fetchall()

            sector_rows = session.execute(text("""
                SELECT date, sector, pct_change FROM sector_etf_daily_returns
                WHERE sector NOT IN ('S&P 500','US Dollar','Treasury Long','Gold')
                ORDER BY date
            """)).fetchall()

            sector_by_date = defaultdict(dict)
            for dt, sect, ret in sector_rows:
                sector_by_date[dt][sect] = ret or 0

            # VIX spike: compute avg sector return on spike day
            vix_spike_rets = defaultdict(list)
            for i in range(1, len(macro_rows)):
                vix_chg = macro_rows[i][1] - macro_rows[i-1][1]
                if vix_chg > 2:  # VIX spike
                    dt = macro_rows[i][0]
                    for sect, ret in sector_by_date.get(dt, {}).items():
                        vix_spike_rets[sect].append(ret)

            # Crude shock: |crude change| > 3%
            crude_shock_rets = defaultdict(list)
            for i in range(1, len(macro_rows)):
                if macro_rows[i-1][2] and macro_rows[i-1][2] > 0:
                    crude_chg = (macro_rows[i][2] / macro_rows[i-1][2] - 1) * 100
                    if abs(crude_chg) > 3:
                        dt = macro_rows[i][0]
                        for sect, ret in sector_by_date.get(dt, {}).items():
                            crude_shock_rets[sect].append(ret)

            # Store vulnerability
            session.execute(text("DELETE FROM sector_macro_vulnerability"))

            self._sector_vuln = {}
            for event_type, rets_by_sector in [
                ('VIX_SPIKE', vix_spike_rets),
                ('CRUDE_SHOCK', crude_shock_rets),
            ]:
                if not rets_by_sector:
                    continue
                # Rank sectors by vulnerability (most negative avg return = most vulnerable)
                sector_avgs = {s: np.mean(r) for s, r in rets_by_sector.items() if len(r) >= 5}
                ranked = sorted(sector_avgs.items(), key=lambda x: x[1])

                for rank, (sect, avg_ret) in enumerate(ranked, 1):
                    n_events = len(rets_by_sector[sect])
                    std_ret = float(np.std(rets_by_sector[sect]))

                    self._sector_vuln[(sect, event_type)] = {
                        'avg_return': round(avg_ret, 4),
                        'rank': rank,
                        'n_events': n_events,
                    }

                    session.execute(text("""
                        INSERT INTO sector_macro_vulnerability
                        (sector, event_type, avg_return, std_return, n_events,
                         vulnerability_rank, fit_date)
                        VALUES (:p0, :p1, :p2, :p3, :p4, :p5, date('now'))
                    """), {'p0': sect, 'p1': event_type, 'p2': round(avg_ret, 4),
                           'p3': round(std_ret, 4), 'p4': n_events, 'p5': rank})

            logger.info("NeuralGraph: sector vulnerability -- VIX:%d CRUDE:%d sectors",
                         len(vix_spike_rets), len(crude_shock_rets))

    # === DB ===

    def _ensure_tables(self):
        with get_session() as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS stock_clusters (
                    symbol TEXT NOT NULL,
                    cluster_id INTEGER NOT NULL,
                    cluster_name TEXT,
                    corr_to_centroid REAL,
                    n_members INTEGER,
                    fit_date TEXT,
                    UNIQUE(symbol, fit_date)
                )
            """))
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS sector_macro_vulnerability (
                    sector TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    avg_return REAL,
                    std_return REAL,
                    n_events INTEGER,
                    vulnerability_rank INTEGER,
                    fit_date TEXT,
                    UNIQUE(sector, event_type)
                )
            """))

    def load_from_db(self):
        """Load clusters + vulnerability from DB."""
        with get_session() as session:
            # Clusters
            rows = session.execute(text("""
                SELECT symbol, cluster_id, cluster_name FROM stock_clusters
                WHERE fit_date = (SELECT MAX(fit_date) FROM stock_clusters)
            """)).fetchall()
            self._clusters = {r[0]: r[1] for r in rows}
            self._cluster_names = {r[1]: r[2] for r in rows if r[2]}

            # Vulnerability
            rows = session.execute(text("""
                SELECT sector, event_type, avg_return, vulnerability_rank, n_events
                FROM sector_macro_vulnerability
            """)).fetchall()
            self._sector_vuln = {
                (r[0], r[1]): {'avg_return': r[2], 'rank': r[3], 'n_events': r[4]}
                for r in rows
            }
        self._built = bool(self._clusters or self._sector_vuln)
        if self._built:
            logger.info("NeuralGraph: loaded %d clusters, %d vulnerability entries",
                         len(set(self._clusters.values())), len(self._sector_vuln))

    def get_stats(self):
        return {
            'built': self._built,
            'n_clusters': len(set(self._clusters.values())),
            'n_stocks_clustered': len(self._clusters),
            'n_vulnerability': len(self._sector_vuln),
        }
