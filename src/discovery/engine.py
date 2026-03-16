"""
Discovery Engine — background scanner for high-confidence stock picks.
Display-only, does NOT execute trades. Does NOT interfere with Rapid Trader.

Scan: daily at 20:00 ET (after market close)
Price refresh: every 5 min during market hours
Storage: discovery_picks table in trade_history.db
"""
import sqlite3
import logging
import math
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

try:
    from loguru import logger as _loguru
    # Bridge standard logging → loguru so Discovery logs appear in web_app.log
    class _InterceptHandler(logging.Handler):
        def emit(self, record):
            _loguru.opt(depth=6, exception=record.exc_info).log(record.levelname, record.getMessage())
    logging.getLogger('discovery').addHandler(_InterceptHandler())
    logging.getLogger('discovery').setLevel(logging.DEBUG)
except ImportError:
    pass

import numpy as np
import pandas as pd
import yaml

from discovery.models import DiscoveryPick
from discovery.scorer import DiscoveryScorer

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'
CONFIG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'discovery.yaml'


class DiscoveryEngine:
    """Scans universe for high-confidence, low-risk stock picks."""

    def __init__(self):
        self.scorer = DiscoveryScorer()
        self._picks: list[DiscoveryPick] = []
        self._last_scan: Optional[str] = None
        self._last_price_refresh: float = 0.0
        self._scan_progress: dict = {}  # live progress for UI polling
        self._ensure_table()
        self._load_picks_from_db()

        with open(CONFIG_PATH) as f:
            self._config = yaml.safe_load(f)['discovery']

    def get_scan_progress(self) -> dict:
        return self._scan_progress.copy()

    def _ensure_table(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discovery_picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                scan_price REAL NOT NULL,
                current_price REAL,
                layer2_score REAL,
                beta REAL,
                atr_pct REAL,
                distance_from_high REAL,
                rsi REAL,
                momentum_5d REAL,
                momentum_20d REAL,
                volume_ratio REAL,
                sl_price REAL,
                sl_pct REAL,
                tp1_price REAL,
                tp1_pct REAL,
                tp2_price REAL,
                tp2_pct REAL,
                sector TEXT,
                market_cap REAL,
                vix_close REAL,
                pct_above_20d_ma REAL,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(scan_date, symbol)
            )
        """)
        # Add columns for L2 features, outcomes, and enrichment (safe if already exist)
        new_cols = [
            ('vix_term_structure', 'REAL'), ('new_52w_highs', 'REAL'),
            ('bull_score', 'REAL'), ('news_count', 'REAL'), ('news_pos_ratio', 'REAL'),
            ('highs_lows_ratio', 'REAL'), ('ad_ratio', 'REAL'), ('mcap_log', 'REAL'),
            ('sector_1d_change', 'REAL'), ('vix3m_close', 'REAL'), ('upside_pct', 'REAL'),
            ('outcome_1d', 'REAL'), ('outcome_2d', 'REAL'), ('outcome_3d', 'REAL'),
            ('outcome_5d', 'REAL'), ('outcome_max_gain_5d', 'REAL'), ('outcome_max_dd_5d', 'REAL'),
            ('days_to_earnings', 'INTEGER'), ('put_call_ratio', 'REAL'), ('short_pct_float', 'REAL'),
            ('benchmark_xlu_5d', 'REAL'), ('benchmark_xle_5d', 'REAL'), ('benchmark_spy_5d', 'REAL'),
            ('breadth_delta_5d', 'REAL'), ('vix_delta_5d', 'REAL'),
            ('crude_close', 'REAL'), ('gold_close', 'REAL'), ('hyg_close', 'REAL'),
            ('dxy_delta_5d', 'REAL'), ('stress_score', 'REAL'),
            ('expected_gain', 'REAL'), ('rr_ratio', 'REAL'),
        ]
        for col_name, col_type in new_cols:
            try:
                conn.execute(f"ALTER TABLE discovery_picks ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
        conn.close()

    def _load_picks_from_db(self):
        """Load active picks from DB."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM discovery_picks
            WHERE status = 'active'
            ORDER BY layer2_score DESC
        """).fetchall()
        conn.close()

        self._picks = []
        for r in rows:
            self._picks.append(DiscoveryPick(
                symbol=r['symbol'], scan_date=r['scan_date'],
                scan_price=r['scan_price'], current_price=r['current_price'] or r['scan_price'],
                layer2_score=r['layer2_score'] or 0,
                beta=r['beta'] or 0, atr_pct=r['atr_pct'] or 0,
                distance_from_high=r['distance_from_high'] or 0,
                rsi=r['rsi'] or 0, momentum_5d=r['momentum_5d'] or 0,
                momentum_20d=r['momentum_20d'] or 0, volume_ratio=r['volume_ratio'] or 0,
                sl_price=r['sl_price'] or 0, sl_pct=r['sl_pct'] or 0,
                tp1_price=r['tp1_price'] or 0, tp1_pct=r['tp1_pct'] or 0,
                tp2_price=r['tp2_price'] or 0, tp2_pct=r['tp2_pct'] or 0,
                expected_gain=r['expected_gain'] or 0, rr_ratio=r['rr_ratio'] or 0,
                sector=r['sector'] or '', market_cap=r['market_cap'] or 0,
                vix_close=r['vix_close'] or 0, pct_above_20d_ma=r['pct_above_20d_ma'] or 0,
                vix_term_structure=r['vix_term_structure'] or 0,
                new_52w_highs=r['new_52w_highs'] or 0,
                bull_score=r['bull_score'], news_count=r['news_count'] or 0,
                news_pos_ratio=r['news_pos_ratio'],
                highs_lows_ratio=r['highs_lows_ratio'] or 0,
                ad_ratio=r['ad_ratio'] or 0, mcap_log=r['mcap_log'] or 0,
                sector_1d_change=r['sector_1d_change'] or 0,
                vix3m_close=r['vix3m_close'] or 0, upside_pct=r['upside_pct'],
                days_to_earnings=r['days_to_earnings'],
                put_call_ratio=r['put_call_ratio'],
                short_pct_float=r['short_pct_float'],
                # Macro stress (v1.2)
                breadth_delta_5d=r['breadth_delta_5d'],
                vix_delta_5d=r['vix_delta_5d'],
                crude_close=r['crude_close'],
                gold_close=r['gold_close'],
                dxy_delta_5d=r['dxy_delta_5d'],
                stress_score=r['stress_score'],
                status=r['status'] or 'active',
            ))

        if self._picks:
            self._last_scan = self._picks[0].scan_date
            logger.info(f"Discovery: loaded {len(self._picks)} active picks from {self._last_scan}")

    def get_picks(self, auto_refresh: bool = True) -> list[dict]:
        """Return current picks as dicts for API. Applies sector diversification."""
        if auto_refresh:
            self._maybe_refresh_prices()
        max_display = self._config.get('schedule', {}).get('max_picks_display', 10)
        div_cfg = self._config.get('diversification', {})
        max_per_sector = div_cfg.get('max_per_sector', 3)

        # Apply sector diversification (picks already sorted by score desc)
        sector_counts: dict[str, int] = {}
        diversified = []
        for p in self._picks:
            sector = p.sector or 'Unknown'
            cnt = sector_counts.get(sector, 0)
            if cnt >= max_per_sector:
                continue
            sector_counts[sector] = cnt + 1
            diversified.append(p)
            if len(diversified) >= max_display:
                break

        return [p.to_dict() for p in diversified]

    def get_last_scan(self) -> Optional[str]:
        return self._last_scan

    def get_stats(self) -> dict:
        """Historical performance statistics from picks with filled outcomes."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Overall stats (picks with outcome data)
        stats_row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) as wins_5d,
                   SUM(CASE WHEN outcome_5d IS NOT NULL THEN 1 ELSE 0 END) as has_outcome,
                   AVG(outcome_1d) as avg_1d,
                   AVG(outcome_5d) as avg_5d,
                   AVG(outcome_max_gain_5d) as avg_max_gain,
                   AVG(outcome_max_dd_5d) as avg_max_dd,
                   SUM(CASE WHEN status='hit_tp1' THEN 1 ELSE 0 END) as tp1_hits,
                   SUM(CASE WHEN status='hit_sl' THEN 1 ELSE 0 END) as sl_hits
            FROM discovery_picks
        """).fetchone()

        # Sector breakdown
        sector_rows = conn.execute("""
            SELECT sector, COUNT(*) as n,
                   SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) as wins,
                   AVG(outcome_5d) as avg_5d
            FROM discovery_picks
            WHERE outcome_5d IS NOT NULL
            GROUP BY sector ORDER BY n DESC
        """).fetchall()

        # Score tier breakdown
        tier_rows = conn.execute("""
            SELECT CASE
                WHEN layer2_score >= 80 THEN 'A+'
                WHEN layer2_score >= 70 THEN 'A'
                WHEN layer2_score >= 60 THEN 'B'
                ELSE 'C' END as tier,
                COUNT(*) as n,
                SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) as wins,
                AVG(outcome_5d) as avg_5d
            FROM discovery_picks
            WHERE outcome_5d IS NOT NULL
            GROUP BY tier ORDER BY tier
        """).fetchall()

        # Active picks sector distribution
        active_sectors = conn.execute("""
            SELECT sector, COUNT(*) as n FROM discovery_picks
            WHERE status = 'active' GROUP BY sector ORDER BY n DESC
        """).fetchall()

        # Benchmark comparison (Marcus test: does L2 beat sector beta?)
        try:
            bench_row = conn.execute("""
                SELECT AVG(outcome_5d) as picks_avg,
                       AVG(benchmark_xlu_5d) as xlu_avg,
                       AVG(benchmark_xle_5d) as xle_avg,
                       AVG(benchmark_spy_5d) as spy_avg,
                       COUNT(*) as n
                FROM discovery_picks
                WHERE outcome_5d IS NOT NULL AND benchmark_spy_5d IS NOT NULL
            """).fetchone()
        except Exception:
            bench_row = None  # benchmark columns not yet created

        conn.close()

        total = stats_row['total'] or 0
        has_outcome = stats_row['has_outcome'] or 0
        wins = stats_row['wins_5d'] or 0

        # Benchmark data
        bench_n = bench_row['n'] or 0 if bench_row else 0
        benchmark = None
        if bench_n > 0:
            picks_avg = bench_row['picks_avg'] or 0
            basket_avg = ((bench_row['xlu_avg'] or 0) + (bench_row['xle_avg'] or 0)) / 2
            benchmark = {
                'n': bench_n,
                'picks_avg_5d': round(picks_avg, 3),
                'xlu_avg_5d': round(bench_row['xlu_avg'] or 0, 3),
                'xle_avg_5d': round(bench_row['xle_avg'] or 0, 3),
                'spy_avg_5d': round(bench_row['spy_avg'] or 0, 3),
                'basket_avg_5d': round(basket_avg, 3),
                'alpha_vs_basket': round(picks_avg - basket_avg, 3),
                'alpha_vs_spy': round(picks_avg - (bench_row['spy_avg'] or 0), 3),
            }

        return {
            'total_picks': total,
            'has_outcome': has_outcome,
            'win_rate_5d': round(wins / has_outcome * 100, 1) if has_outcome > 0 else None,
            'avg_return_1d': round(stats_row['avg_1d'], 2) if stats_row['avg_1d'] else None,
            'avg_return_5d': round(stats_row['avg_5d'], 2) if stats_row['avg_5d'] else None,
            'avg_max_gain': round(stats_row['avg_max_gain'], 2) if stats_row['avg_max_gain'] else None,
            'avg_max_dd': round(stats_row['avg_max_dd'], 2) if stats_row['avg_max_dd'] else None,
            'tp1_hits': stats_row['tp1_hits'] or 0,
            'sl_hits': stats_row['sl_hits'] or 0,
            'by_sector': [{'sector': r['sector'], 'n': r['n'], 'wr': round(r['wins'] / r['n'] * 100, 0) if r['n'] else 0, 'avg': round(r['avg_5d'], 2) if r['avg_5d'] else 0} for r in sector_rows],
            'by_tier': [{'tier': r['tier'], 'n': r['n'], 'wr': round(r['wins'] / r['n'] * 100, 0) if r['n'] else 0, 'avg': round(r['avg_5d'], 2) if r['avg_5d'] else 0} for r in tier_rows],
            'active_sectors': [{'sector': r['sector'], 'n': r['n']} for r in active_sectors],
            'benchmark': benchmark,
        }

    def _maybe_refresh_prices(self):
        """Reload picks from DB + refresh prices if >5 min since last refresh."""
        refresh_interval = self._config.get('schedule', {}).get('price_refresh_minutes', 5) * 60
        now = time.monotonic()
        if now - self._last_price_refresh < refresh_interval:
            return
        self._last_price_refresh = now
        # Always reload from DB (cron scan writes to DB in separate process)
        self._load_picks_from_db()
        if not self._picks:
            return
        try:
            self.refresh_prices()
        except Exception as e:
            logger.error(f"Discovery: auto price refresh failed: {e}")

    def run_scan(self) -> list[DiscoveryPick]:
        """Full scan: load universe → Layer 1 → Layer 2 → compute SL/TP → save."""
        from api.yfinance_utils import fetch_history

        scan_date = date.today().isoformat()
        logger.info(f"Discovery scan starting for {scan_date}")
        self._scan_progress = {'status': 'loading', 'pct': 0, 'stage': 'Loading universe...', 'l1': 0, 'l2': 0}

        # 1. Load universe + fundamentals
        stocks = self._load_universe()
        logger.info(f"Discovery: {len(stocks)} stocks in universe")
        self._scan_progress.update(stage=f'Loaded {len(stocks)} stocks', pct=5)

        # 2. Load macro/breadth (market-wide, same for all stocks today)
        macro = self._load_macro(scan_date)

        # 2.5 VIX — no hard gate. L2 scoring penalizes high VIX via 4 features (24.8% weight).
        vix = macro.get('vix_close', 0) or 0

        adaptive_min_score = self._config['layer2']['min_score']  # 35
        qg = self._config.get('quality_gates', {})
        tp_sl_cfg = self._config.get('smart_tp_sl', {})

        logger.info(f"Discovery: VIX={vix:.1f}, min_score={adaptive_min_score}, gates=dynamic")

        # 3. Compute per-stock technical features via yfinance
        candidates = []
        batch_size = 50
        symbols = list(stocks.keys())
        total_batches = (len(symbols) + batch_size - 1) // batch_size

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            batch_str = ' '.join(batch)
            batch_num = i // batch_size + 1
            pct = 5 + int(batch_num / total_batches * 80)
            self._scan_progress.update(status='scanning', pct=pct, stage=f'Batch {batch_num}/{total_batches}', l1=len(candidates))
            logger.info(f"Discovery: fetching batch {batch_num}/{total_batches}")

            try:
                import yfinance as yf
                data = yf.download(batch_str, period='1y', interval='1d',
                                   auto_adjust=True, progress=False, threads=False)
            except Exception as e:
                logger.error(f"Discovery: yfinance batch error: {e}")
                continue

            for sym in batch:
                try:
                    if len(batch) == 1:
                        df = data
                    else:
                        df = data.xs(sym, axis=1, level=1) if sym in data.columns.get_level_values(1) else None

                    if df is None or df.empty or len(df) < 20:
                        continue

                    features = self._compute_technical(df, sym, stocks.get(sym, {}))
                    if features is None:
                        continue

                    # Layer 1 check
                    passed, reason = self.scorer.passes_layer1(features)
                    if not passed:
                        continue

                    # Merge macro features
                    features.update(macro)
                    candidates.append(features)

                except Exception as e:
                    logger.debug(f"Discovery: error processing {sym}: {e}")
                    continue

            # Rate limit between batches
            if i + batch_size < len(symbols):
                time.sleep(1)

        logger.info(f"Discovery: {len(candidates)} passed Layer 1")
        self._scan_progress.update(status='scoring', pct=87, stage=f'L1 passed: {len(candidates)}', l1=len(candidates))

        # 4. Load per-stock sentiment/analyst/options/news
        self._enrich_candidates(candidates)
        self._scan_progress.update(pct=92, stage=f'Scoring {len(candidates)} candidates...')

        # 5. Dynamic quality gates + L2 scoring + Smart TP/SL (v2.1)
        # v2.1: mom5d reject-zone [0,3) replaces hard gate <0.
        # U-shape: pullback (<0) WR=72%, danger [0,3) WR=38%, momentum (>=3) WR=77%.
        # n=45: WR=73.3%, TP_hit=78%, avg=+2.92%, 16 active days.
        min_sector_1d = qg.get('min_sector_1d_change', 0.0)
        min_mom20d = qg.get('min_momentum_20d', 0.0)
        mom5d_rej_lo = qg.get('momentum_5d_reject_low', 0.0)
        mom5d_rej_hi = qg.get('momentum_5d_reject_high', 3.0)
        mom5d_max = qg.get('momentum_5d_max', 10.0)
        min_vol = qg.get('min_volume_ratio', 0.4)

        tp_atr_mult = tp_sl_cfg.get('tp_atr_mult', 1.20)
        tp_floor = tp_sl_cfg.get('tp_floor', 2.5)
        sl_atr_mult = tp_sl_cfg.get('sl_atr_mult', 0.80)
        sl_floor = tp_sl_cfg.get('sl_floor', 2.0)
        tp2_mult = tp_sl_cfg.get('tp2_multiplier', 2.0)

        picks = []
        for c in candidates:
            score = self.scorer.compute_layer2_score(c)
            if score < adaptive_min_score:
                continue

            # Dynamic quality gates (sector rotation — no hardcoded sectors)
            mom5d = c.get('momentum_5d', 0) or 0
            mom20d = c.get('momentum_20d', 0) or 0
            vol_ratio = c.get('volume_ratio', 0) or 0
            sector_1d = c.get('sector_1d_change')

            if sector_1d is None or sector_1d <= min_sector_1d:
                continue
            if mom20d <= min_mom20d:
                continue
            if mom5d_rej_lo <= mom5d < mom5d_rej_hi:
                continue
            if mom5d >= mom5d_max:
                continue
            if vol_ratio < min_vol:
                continue

            # Smart TP/SL: ATR-proportional with floors
            price = c['close']
            atr_pct = c.get('atr_pct', 2.0)

            tp_pct = max(tp_floor, tp_atr_mult * atr_pct)
            sl_pct = max(sl_floor, sl_atr_mult * atr_pct)
            tp2_pct = tp_pct * tp2_mult

            sl_price = price * (1 - sl_pct / 100)
            tp1_price = price * (1 + tp_pct / 100)
            tp2_price = price * (1 + tp2_pct / 100)

            levels = {
                'sl_price': round(sl_price, 2), 'sl_pct': round(sl_pct, 1),
                'tp1_price': round(tp1_price, 2), 'tp1_pct': round(tp_pct, 1),
                'tp2_price': round(tp2_price, 2), 'tp2_pct': round(tp2_pct, 1),
                'expected_gain': round(tp_pct, 1),
                'rr_ratio': round(tp_pct / sl_pct, 2) if sl_pct > 0 else 0,
            }
            logger.info(f"Discovery: {c['symbol']} sector_1d={sector_1d:+.1f} mom20d={mom20d:+.1f} mom5d={mom5d:+.1f} vol={vol_ratio:.2f} TP={tp_pct:.1f}% SL={sl_pct:.1f}%")

            pick = DiscoveryPick(
                symbol=c['symbol'], scan_date=scan_date, scan_price=price,
                current_price=price, layer2_score=score,
                beta=c.get('beta', 0), atr_pct=c['atr_pct'],
                distance_from_high=c.get('distance_from_high', 0),
                rsi=c.get('rsi', 0), momentum_5d=c.get('momentum_5d', 0),
                momentum_20d=c.get('momentum_20d', 0),
                volume_ratio=c.get('volume_ratio', 0),
                sector=c.get('sector', ''), market_cap=c.get('market_cap', 0),
                vix_close=macro.get('vix_close', 0),
                pct_above_20d_ma=macro.get('pct_above_20d_ma', 0),
                # L2 features (persisted for calibration)
                vix_term_structure=c.get('vix_term_structure', 0),
                new_52w_highs=c.get('new_52w_highs', 0),
                bull_score=c.get('bull_score'),
                news_count=c.get('news_count', 0),
                news_pos_ratio=c.get('news_pos_ratio'),
                highs_lows_ratio=c.get('highs_lows_ratio', 0),
                ad_ratio=c.get('ad_ratio', 0),
                mcap_log=c.get('mcap_log', 0),
                sector_1d_change=c.get('sector_1d_change', 0),
                vix3m_close=c.get('vix3m_close', 0),
                upside_pct=c.get('upside_pct'),
                days_to_earnings=c.get('days_to_earnings'),
                put_call_ratio=c.get('put_call_ratio'),
                short_pct_float=c.get('short_pct_float'),
                # Macro stress (v1.2)
                breadth_delta_5d=macro.get('breadth_delta_5d'),
                vix_delta_5d=macro.get('vix_delta_5d'),
                crude_close=macro.get('crude_close'),
                gold_close=macro.get('gold_close'),
                dxy_delta_5d=macro.get('dxy_delta_5d'),
                stress_score=macro.get('stress_score'),
                **levels,
            )
            picks.append(pick)

        # Sort by score descending
        picks.sort(key=lambda p: p.layer2_score, reverse=True)
        logger.info(f"Discovery: {len(picks)} picks passed L2 (score >= {adaptive_min_score:.0f})")

        # Log sector distribution
        pick_sectors: dict[str, int] = {}
        for p in picks:
            s = p.sector or 'Unknown'
            pick_sectors[s] = pick_sectors.get(s, 0) + 1
        sectors_summary = ', '.join(f"{s}:{n}" for s, n in sorted(pick_sectors.items(), key=lambda x: -x[1]))
        logger.info(f"Discovery: {len(picks)} total picks | sectors: {sectors_summary}")
        self._scan_progress.update(pct=97, stage=f'L2 passed: {len(picks)} picks', l2=len(picks))

        # 6. Deactivate all previous active picks + save new scan to DB
        #    Each scan replaces the full active set. Old picks kept as 'replaced' for calibration.
        self._expire_old_picks(scan_date)
        self._deactivate_previous_picks(scan_date)
        self._save_picks(picks, scan_date)

        self._picks = picks
        self._last_scan = scan_date
        self._scan_progress = {'status': 'done', 'pct': 100, 'stage': f'Done: {len(picks)} picks', 'l1': len(candidates), 'l2': len(picks)}
        return picks

    def refresh_prices(self):
        """Refresh current prices for active picks (called every 5 min)."""
        if not self._picks:
            return

        symbols = [p.symbol for p in self._picks]
        try:
            import yfinance as yf
            data = yf.download(' '.join(symbols), period='1d', interval='1m',
                               auto_adjust=True, progress=False, threads=False)
            if data.empty:
                return

            conn = sqlite3.connect(str(DB_PATH))
            for pick in self._picks:
                try:
                    if len(symbols) == 1:
                        close_col = data['Close']
                    else:
                        if pick.symbol not in data.columns.get_level_values(1):
                            continue
                        close_col = data['Close'][pick.symbol]

                    latest = close_col.dropna().iloc[-1] if not close_col.dropna().empty else None
                    if latest and latest > 0:
                        pick.current_price = float(latest)

                        # Check SL/TP hits
                        if pick.current_price <= pick.sl_price and pick.status == 'active':
                            pick.status = 'hit_sl'
                        elif pick.current_price >= pick.tp1_price and pick.status == 'active':
                            pick.status = 'hit_tp1'

                        conn.execute(
                            "UPDATE discovery_picks SET current_price=?, status=?, updated_at=datetime('now') WHERE symbol=? AND scan_date=?",
                            (pick.current_price, pick.status, pick.symbol, pick.scan_date))
                except Exception:
                    continue

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Discovery price refresh error: {e}")

    def _compute_technical(self, df: pd.DataFrame, symbol: str, fund: dict) -> Optional[dict]:
        """Compute technical features from daily OHLCV bars."""
        try:
            df = df.dropna(subset=['Close'])
            if len(df) < 20:
                return None

            close = df['Close'].values
            high = df['High'].values
            low = df['Low'].values
            volume = df['Volume'].values
            current = float(close[-1])

            if current <= 0:
                return None

            # ATR (14-period)
            tr = []
            for i in range(1, len(df)):
                tr.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
            atr_14 = float(np.mean(tr[-14:])) if len(tr) >= 14 else float(np.mean(tr))
            atr_pct = atr_14 / current * 100

            # RSI (14-period)
            deltas = np.diff(close)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            if len(gains) >= 14:
                avg_gain = float(np.mean(gains[-14:]))
                avg_loss = float(np.mean(losses[-14:]))
                if avg_loss > 0:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                else:
                    rsi = 100
            else:
                rsi = 50

            # Momentum
            if len(close) >= 6:
                momentum_5d = (close[-1] / close[-6] - 1) * 100
            else:
                momentum_5d = 0

            if len(close) >= 21:
                momentum_20d = (close[-1] / close[-21] - 1) * 100
            else:
                momentum_20d = 0

            # Distance from 52-week high (negative convention: 0=at high)
            high_52w = float(np.max(high[-252:])) if len(high) >= 252 else float(np.max(high))
            distance_from_high = (current / high_52w - 1) * 100 if high_52w > 0 else 0

            # Volume ratio (today vs 20d avg)
            if len(volume) >= 21:
                avg_vol_20 = float(np.mean(volume[-21:-1]))
                volume_ratio = float(volume[-1]) / avg_vol_20 if avg_vol_20 > 0 else 1.0
            else:
                volume_ratio = 1.0

            # Distance from 20d MA (%) — mean-reversion signal (v1.7)
            if len(close) >= 20:
                ma_20 = float(np.mean(close[-20:]))
                dist_from_20d_ma = (current / ma_20 - 1) * 100 if ma_20 > 0 else 0
            else:
                dist_from_20d_ma = 0

            # ROC 10d (%) — rate of change (v1.7)
            if len(close) >= 11:
                roc_10d = (close[-1] / close[-11] - 1) * 100
            else:
                roc_10d = 0

            return {
                'symbol': symbol,
                'close': current,
                'atr_pct': atr_pct,
                'rsi': rsi,
                'momentum_5d': momentum_5d,
                'momentum_20d': momentum_20d,
                'distance_from_high': distance_from_high,
                'volume_ratio': volume_ratio,
                'dist_from_20d_ma': dist_from_20d_ma,
                'roc_10d': roc_10d,
                'beta': fund.get('beta'),
                'sector': fund.get('sector', ''),
                'market_cap': fund.get('market_cap', 0),
                'mcap_log': math.log10(fund.get('market_cap', 1e9) + 1),
            }
        except Exception as e:
            logger.debug(f"Discovery: tech compute error for {symbol}: {e}")
            return None

    def _load_universe(self) -> dict:
        """Load stock universe with fundamentals from DB."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT symbol, beta, pe_forward, market_cap, sector, avg_volume
            FROM stock_fundamentals
            WHERE market_cap > 1e9 AND avg_volume > 100000
        """).fetchall()
        conn.close()
        return {r['symbol']: dict(r) for r in rows}

    def _load_macro(self, scan_date: str) -> dict:
        """Load latest macro/breadth data + compute derived stress features."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        macro_row = conn.execute("""
            SELECT m.vix_close, m.vix3m_close, m.gold_close, m.crude_close, m.hyg_close,
                   m.dxy_close, m.yield_spread,
                   b.pct_above_20d_ma, b.new_52w_highs, b.new_52w_lows, b.ad_ratio
            FROM macro_snapshots m
            LEFT JOIN market_breadth b ON m.date = b.date
            ORDER BY m.date DESC LIMIT 1
        """).fetchone()

        if not macro_row:
            conn.close()
            return {}

        result = dict(macro_row)

        # Derived: VIX term structure
        vix = result.get('vix_close', 20)
        vix3m = result.get('vix3m_close', 20)
        result['vix_term_structure'] = vix3m / vix if vix and vix > 0 else 1.0

        highs = result.get('new_52w_highs', 100)
        lows = result.get('new_52w_lows', 100)
        result['highs_lows_ratio'] = highs / max(lows, 1) if highs is not None and lows is not None else 1.0

        # --- Derived delta features (5-day rate of change) ---
        # Get macro 6 days ago for delta computation
        macro_5d = conn.execute("""
            SELECT vix_close, dxy_close, crude_close FROM macro_snapshots
            ORDER BY date DESC LIMIT 1 OFFSET 5
        """).fetchone()

        breadth_5d = conn.execute("""
            SELECT pct_above_20d_ma FROM market_breadth
            ORDER BY date DESC LIMIT 1 OFFSET 5
        """).fetchone()

        conn.close()

        # VIX delta 5d
        if macro_5d and macro_5d['vix_close'] and vix:
            result['vix_delta_5d'] = round(vix - macro_5d['vix_close'], 2)
        else:
            result['vix_delta_5d'] = 0.0

        # DXY delta 5d
        dxy = result.get('dxy_close')
        if macro_5d and macro_5d['dxy_close'] and dxy:
            result['dxy_delta_5d'] = round(dxy - macro_5d['dxy_close'], 2)
        else:
            result['dxy_delta_5d'] = 0.0

        # Breadth delta 5d
        breadth_now = result.get('pct_above_20d_ma')
        if breadth_5d and breadth_5d['pct_above_20d_ma'] and breadth_now:
            result['breadth_delta_5d'] = round(breadth_now - breadth_5d['pct_above_20d_ma'], 2)
        else:
            result['breadth_delta_5d'] = 0.0

        # Crude oil delta 5d (% change) — used for Energy sector gate
        crude_now = result.get('crude_close')
        crude_5d_ago = macro_5d['crude_close'] if macro_5d and macro_5d['crude_close'] else None
        if crude_now and crude_5d_ago and crude_5d_ago > 0:
            result['crude_delta_5d_pct'] = round((crude_now - crude_5d_ago) / crude_5d_ago * 100, 2)
        else:
            result['crude_delta_5d_pct'] = None

        # Market Stress Score (0-100, higher = more stress)
        # Combines 6 symptoms that appear in ANY crisis
        stress_components = []

        # 1. VIX acceleration: +10 in 5 days = max stress
        vix_d = result.get('vix_delta_5d', 0)
        stress_components.append(min(1.0, max(0.0, vix_d / 10.0)))

        # 2. Breadth collapse: -20 in 5 days = max stress
        breadth_d = result.get('breadth_delta_5d', 0)
        stress_components.append(min(1.0, max(0.0, -breadth_d / 20.0)))

        # 3. VIX backwardation: VIX > VIX3M = panic
        vts = result.get('vix_term_structure', 1.0)
        stress_components.append(min(1.0, max(0.0, (1.0 - vts) / 0.1)))

        # 4. VIX level: >30 = high stress
        stress_components.append(min(1.0, max(0.0, (vix - 20) / 15.0)) if vix else 0.0)

        # 5. DXY surge: +2 in 5 days = risk-off flow
        dxy_d = result.get('dxy_delta_5d', 0)
        stress_components.append(min(1.0, max(0.0, dxy_d / 2.0)))

        # 6. Breadth level: <30% = capitulation
        if breadth_now and breadth_now > 0:
            stress_components.append(min(1.0, max(0.0, (50 - breadth_now) / 25.0)))
        else:
            stress_components.append(0.0)

        result['stress_score'] = round(sum(stress_components) / len(stress_components) * 100, 1)

        return result

    def _enrich_candidates(self, candidates: list):
        """Add analyst/news/options data from DB to candidates."""
        if not candidates:
            return

        symbols = [c['symbol'] for c in candidates]
        placeholders = ','.join('?' * len(symbols))
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Analyst consensus
        rows = conn.execute(f"SELECT symbol, bull_score, upside_pct FROM analyst_consensus WHERE symbol IN ({placeholders})", symbols).fetchall()
        analyst = {r['symbol']: dict(r) for r in rows}

        # News sentiment
        rows = conn.execute(f"""
            SELECT symbol, AVG(sentiment_score) as avg_news_sentiment, COUNT(*) as news_count,
                   SUM(CASE WHEN sentiment_label='positive' THEN 1 ELSE 0 END) as news_pos,
                   SUM(CASE WHEN sentiment_label='negative' THEN 1 ELSE 0 END) as news_neg
            FROM news_events WHERE symbol IN ({placeholders}) AND symbol IS NOT NULL
            GROUP BY symbol
        """, symbols).fetchall()
        news = {r['symbol']: dict(r) for r in rows}

        # Options flow
        rows = conn.execute(f"SELECT symbol, put_call_ratio FROM options_flow WHERE symbol IN ({placeholders}) GROUP BY symbol HAVING MAX(date)", symbols).fetchall()
        options = {r['symbol']: dict(r) for r in rows}

        # Earnings proximity — use earnings_history (richer data than earnings_calendar)
        today_str = date.today().isoformat()
        rows = conn.execute(f"""
            SELECT symbol, MIN(report_date) as next_date
            FROM earnings_history
            WHERE symbol IN ({placeholders}) AND report_date >= ?
            GROUP BY symbol
        """, symbols + [today_str]).fetchall()
        earnings = {}
        for r in rows:
            try:
                ed = datetime.strptime(r['next_date'][:10], '%Y-%m-%d').date()
                earnings[r['symbol']] = (ed - date.today()).days
            except Exception:
                pass

        # Short interest
        rows = conn.execute(f"SELECT symbol, short_pct_float FROM short_interest WHERE symbol IN ({placeholders})", symbols).fetchall()
        short_data = {r['symbol']: r['short_pct_float'] for r in rows}

        # Sector ETF returns (by sector name → ETF ticker)
        rows = conn.execute("""
            SELECT etf, sector, pct_change FROM sector_etf_daily_returns
            WHERE date = (SELECT MAX(date) FROM sector_etf_daily_returns)
        """).fetchall()
        sector_returns_by_name = {r['sector']: r['pct_change'] for r in rows if r['sector']}
        spy_return = next((r['pct_change'] for r in rows if r['etf'] == 'SPY'), 0)

        conn.close()

        # Merge into candidates
        for c in candidates:
            sym = c['symbol']

            if sym in analyst:
                c['bull_score'] = analyst[sym].get('bull_score')
                c['upside_pct'] = analyst[sym].get('upside_pct')

            if sym in news:
                n = news[sym]
                c['avg_news_sentiment'] = n.get('avg_news_sentiment')
                c['news_count'] = n.get('news_count')
                pos = n.get('news_pos', 0) or 0
                neg = n.get('news_neg', 0) or 0
                c['news_pos_ratio'] = pos / (pos + neg) if (pos + neg) > 0 else None

            if sym in options:
                c['put_call_ratio'] = options[sym].get('put_call_ratio')

            # Sector 1d change — map stock sector name to ETF return
            stock_sector = c.get('sector', '')
            c['sector_1d_change'] = sector_returns_by_name.get(stock_sector, spy_return)

            # Earnings proximity
            if sym in earnings:
                c['days_to_earnings'] = earnings[sym]

            # Short interest
            if sym in short_data:
                c['short_pct_float'] = short_data[sym]

    def _save_picks(self, picks: list[DiscoveryPick], scan_date: str):
        """Save picks to DB with all L2 features for future calibration."""
        conn = sqlite3.connect(str(DB_PATH))
        for p in picks:
            conn.execute("""
                INSERT OR REPLACE INTO discovery_picks
                (scan_date, symbol, scan_price, current_price, layer2_score,
                 beta, atr_pct, distance_from_high, rsi, momentum_5d, momentum_20d, volume_ratio,
                 sl_price, sl_pct, tp1_price, tp1_pct, tp2_price, tp2_pct,
                 expected_gain, rr_ratio,
                 sector, market_cap, vix_close, pct_above_20d_ma, status,
                 vix_term_structure, new_52w_highs, bull_score, news_count, news_pos_ratio,
                 highs_lows_ratio, ad_ratio, mcap_log, sector_1d_change, vix3m_close, upside_pct,
                 days_to_earnings, put_call_ratio, short_pct_float,
                 breadth_delta_5d, vix_delta_5d, crude_close, gold_close, dxy_delta_5d, stress_score)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (p.scan_date, p.symbol, p.scan_price, p.current_price, p.layer2_score,
                  p.beta, p.atr_pct, p.distance_from_high, p.rsi, p.momentum_5d,
                  p.momentum_20d, p.volume_ratio,
                  p.sl_price, p.sl_pct, p.tp1_price, p.tp1_pct, p.tp2_price, p.tp2_pct,
                  p.expected_gain, p.rr_ratio,
                  p.sector, p.market_cap, p.vix_close, p.pct_above_20d_ma, p.status,
                  p.vix_term_structure, p.new_52w_highs, p.bull_score, p.news_count,
                  p.news_pos_ratio, p.highs_lows_ratio, p.ad_ratio, p.mcap_log,
                  p.sector_1d_change, p.vix3m_close, p.upside_pct,
                  p.days_to_earnings, p.put_call_ratio, p.short_pct_float,
                  p.breadth_delta_5d, p.vix_delta_5d, p.crude_close, p.gold_close,
                  p.dxy_delta_5d, p.stress_score))
        conn.commit()
        conn.close()
        logger.info(f"Discovery: saved {len(picks)} picks for {scan_date}")

    def _deactivate_previous_picks(self, new_scan_date: str):
        """Deactivate all active picks from previous scans (new scan replaces them)."""
        conn = sqlite3.connect(str(DB_PATH))
        n = conn.execute("""
            UPDATE discovery_picks SET status = 'replaced', updated_at = datetime('now')
            WHERE status = 'active' AND scan_date != ?
        """, (new_scan_date,)).rowcount
        conn.commit()
        conn.close()
        if n:
            logger.info(f"Discovery: deactivated {n} picks from previous scans")

    def _expire_old_picks(self, current_date: str):
        """Expire picks older than max_pick_age_days."""
        max_age = self._config.get('schedule', {}).get('max_pick_age_days', 5)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            UPDATE discovery_picks SET status = 'expired', updated_at = datetime('now')
            WHERE status = 'active' AND julianday(?) - julianday(scan_date) > ?
        """, (current_date, max_age))
        conn.commit()
        conn.close()


# Singleton
_engine: Optional[DiscoveryEngine] = None


def get_discovery_engine() -> DiscoveryEngine:
    global _engine
    if _engine is None:
        _engine = DiscoveryEngine()
    return _engine
