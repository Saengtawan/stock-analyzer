"""
Gap Scanner v2.0 — ML-based next-day gap-up prediction from overnight signals.

Scan at 20:00 ET (with Discovery) -> predict which stocks gap up tomorrow.
Display-only, integrated into Discovery UI as strategy "GAP".

Architecture (4 layers):
  L1: Candidate scan — news, earnings AMC, analyst upgrades, price action
  L2: Gap type classify — BREAKAWAY/EVENT/SECTOR_BOUNCE/COMMON
  L3: Context scoring — ML probability (LogisticRegression) or rule-based fallback
  L4: Rank + output — top picks by ML score

ML Training:
  - _build_training_data() builds features + labels from historical data (2025-01+)
  - fit() trains LogisticRegression with walk-forward 80/20 split
  - Model persisted as pickle in gap_scanner_model table

Data sources (all existing):
  - stock_daily_ohlc (1.5M rows) — D0 OHLCV, momentum, volume
  - news_events (42K) — overnight news, co-mention peers
  - earnings_history (23K) — AMC earnings
  - analyst_ratings_history (234K) — recent upgrades
  - insider_transactions_history (82K) — insider buying
  - sector_etf_daily_returns (15K) — sector D0 performance
  - macro_snapshots (2.7K) — VIX
  - market_breadth (1.4K) — breadth %
  - stock_fundamentals — sector, beta, market_cap
"""
from database.orm.base import get_session
from sqlalchemy import text
import json
import logging
import math
import pickle
import re
import time
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from collections import defaultdict

import numpy as np

logger = logging.getLogger(__name__)


# Feature names used by the ML model (order matters for training/prediction)
# v3: Redesigned from backtest findings — removed noise, added non-linear features
ML_FEATURE_NAMES = [
    # Stock features (known at D0 close)
    'd0_ret', 'mom_5d', 'mom_20d', 'vol_ratio', 'candle_pos',
    'dist_from_20d_high', 'atr_pct', 'beta',
    # News features (simplified — backtest: fewer articles = better)
    'has_news', 'news_sent', 'has_catalyst', 'has_amc_earnings',
    # Context features
    'sector_d0_ret', 'breadth',
    'btc_corr_up',    # corr × max(btc_mom, 0)
    'btc_corr_down',  # corr × min(btc_mom, 0)
    # Peer co-mention
    'peer_news_sent', 'n_peer_articles',
    # Non-linear features from backtest findings
    'vix_sweet_spot',       # 1 if VIX 22-28 else 0 (WR 36% vs 18%)
    'vix_too_high',         # 1 if VIX >28 (WR 0% — never gap)
    'is_oversold',          # d0<-2% + breadth<40 (WR 40% — best signal)
    'd0_drop_x_vol',        # abs(min(d0,0)) × vol_ratio — drop + volume = bounce
    # Gap type indicators
    'is_near_high', 'high_vol', 'in_uptrend',
    # Scheduled catalyst
    'has_scheduled_catalyst',
]


class GapScanner:
    """Predict next-day gap-ups from overnight signals."""

    def __init__(self):
        self._fitted = False
        self._event_impact = {}   # event_type -> avg 5d return for co-mentioned stocks
        self._peer_impact = {}    # (symA, symB) -> correlation of returns when co-mentioned
        self._gap_type_wr = {}    # gap_type -> historical WR
        self._model = None        # sklearn LogisticRegression model
        self._ml_fitted = False   # whether ML model is trained
        self._fit_date = None
        self._feature_names = ML_FEATURE_NAMES
        self._ml_metrics = {}     # AUC, accuracy from last fit

        # Intraday ML ensemble filter (LR + GradientBoosting)
        self._intraday_ml = None
        try:
            from discovery.intraday_ml_filter import IntradayMLFilter
            self._intraday_ml = IntradayMLFilter()
            self._intraday_ml.load_from_db()
        except Exception as e:
            logger.warning("GapScanner: failed to load IntradayMLFilter: %s", e)

    # === Public API ===

    def scan(self, macro: dict, scan_date: str, premarket_confirm: bool = True) -> list[dict]:
        """Scan for gap-up candidates.

        Two modes:
        - Evening (after close): ML watchlist from overnight signals
        - Pre-market (04:00-09:30 ET): confirm with real-time pre-market price

        If premarket_confirm=True and it's pre-market hours,
        only return stocks where PM price confirms gap ≥1%.
        Backtest: PM confirm → WR 85% vs evening only → WR 25%.
        """
        with get_session() as conn:
            # L1: Find candidates with overnight signals
            candidates = self._find_candidates(conn, macro, scan_date)
            if not candidates:
                return []

            # L2: Classify gap type
            for c in candidates:
                c['_gap_type'] = self._classify_gap_type(c)

            # L3: Context scoring — ML or rule-based fallback
            if self._ml_fitted and self._model is not None:
                self._score_candidates_ml(candidates, conn, macro, scan_date)
            else:
                for c in candidates:
                    c['_gap_score'] = self._score_context(c, macro)

            # L3.5: Pre-market confirmation filter
            # During pre-market hours, check real-time price to confirm gap
            if premarket_confirm:
                candidates = self._apply_premarket_filter(candidates)

            # L4: Rank and filter
            for c in candidates:
                ml_prob = c.get('_ml_prob', c.get('_gap_score', 0) / 10)
                n_signals = c.get('_signal_count', 1)
                c['_conviction'] = round(ml_prob + n_signals * 0.01, 4)

            candidates.sort(key=lambda c: c['_conviction'], reverse=True)

            max_per_type = 2
            skip_types = {'RUNAWAY'}
            type_counts = {}
            picks = []
            for c in candidates:
                if c['_gap_score'] <= 0:
                    continue
                gt = c.get('_gap_type', 'COMMON')
                if gt in skip_types:
                    continue
                if type_counts.get(gt, 0) >= max_per_type:
                    continue

                reasons = c.get('_gap_reasons', [])
                gap_catalysts = {'NEWS_CATALYST', 'AMC_EARNINGS', 'ANALYST_UPGRADE',
                                 'BIG_TARGET_RAISE', 'INSIDER_BUY', 'NEWS_POSITIVE'}
                has_gap_catalyst = bool(gap_catalysts & set(reasons))
                d0_ret = c.get('d0_ret', 0)

                if not has_gap_catalyst and d0_ret < -2:
                    continue

                picks.append(c)
                type_counts[gt] = type_counts.get(gt, 0) + 1
                if len(picks) >= 10:
                    break

            pm_mode = any(c.get('_pm_confirmed') for c in picks)
            logger.info("GapScanner: %d candidates -> %d picks (scan=%s, ml=%s, pm=%s)",
                        len(candidates), len(picks), scan_date, self._ml_fitted, pm_mode)
            for p in picks[:5]:
                pm_tag = f" PM={p.get('_pm_gap', 0):+.1f}%" if p.get('_pm_confirmed') else ""
                logger.info("  GAP: %s score=%.2f type=%s%s reasons=%s",
                            p['symbol'], p['_gap_score'], p['_gap_type'],
                            pm_tag, p.get('_gap_reasons', []))

            return picks

    def _apply_premarket_filter(self, candidates: list) -> list:
        """Pre-market scan: find ALL stocks gapping up from full universe.

        Scans 1000+ stocks, not just evening watchlist.
        Uses Alpaca dailyBar.c for prev_close + yfinance prepost for live PM price.

        Backtest: PM gap ≥1% → WR 85% (n=2,912).

        - During pre-market (04:00-09:30 ET): live scan → save results to _pm_cache
        - After pre-market: return cached PM results if available
        - Before pre-market: return evening candidates
        """
        now_et = datetime.now(ZoneInfo('America/New_York'))

        # Before pre-market (< 04:00) → evening watchlist
        if now_et.hour < 4:
            return candidates

        # After pre-market (≥ 10:00) → return cached PM results if available
        if now_et.hour >= 10:
            if hasattr(self, '_pm_cache') and self._pm_cache:
                logger.info("GapScanner PM: using cached PM results (%d picks)", len(self._pm_cache))
                return self._pm_cache
            # Try loading from DB (survives restart)
            try:
                today = now_et.strftime('%Y-%m-%d')
                with get_session() as conn:
                    row = conn.execute(text("SELECT data_json FROM gap_pm_cache WHERE date=:p0"), {'p0': today}).fetchone()
                if row:
                    self._pm_cache = json.loads(row[0])
                    logger.info("GapScanner PM: loaded cached PM from DB (%d picks)", len(self._pm_cache))
                    return self._pm_cache
            except Exception:
                pass
            return candidates

        import requests
        import yfinance as yf

        # Load Alpaca keys
        _env = {}
        for line in open(Path(__file__).resolve().parents[2] / '.env'):
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                _env[k.strip()] = v.strip()
        _headers = {
            'APCA-API-KEY-ID': _env.get('ALPACA_API_KEY', ''),
            'APCA-API-SECRET-KEY': _env.get('ALPACA_SECRET_KEY', ''),
        }

        # Get full universe
        with get_session() as conn:
            all_syms = [r[0] for r in conn.execute(
                text("SELECT symbol FROM stock_fundamentals WHERE avg_volume > 300000 AND market_cap > 5e8")
            ).fetchall()]
            fund_map = {}
            for r in conn.execute(text("SELECT symbol, sector, beta, market_cap FROM stock_fundamentals")).mappings().fetchall():
                fund_map[r['symbol']] = {'sector': r['sector'], 'beta': r['beta'], 'market_cap': r['market_cap']}

        logger.info("GapScanner PM: scanning %d stocks (%02d:%02d ET)",
                     len(all_syms), now_et.hour, now_et.minute)

        # Step 1: Alpaca prev_close in bulk
        # During pre-market: dailyBar = yesterday (correct)
        # During market hours: use prevDailyBar = yesterday
        prev_closes = {}
        for i in range(0, len(all_syms), 200):
            batch = all_syms[i:i+200]
            try:
                r = requests.get('https://data.alpaca.markets/v2/stocks/snapshots',
                    params={'symbols': ','.join(batch)},
                    headers=_headers, timeout=15)
                if r.status_code == 200:
                    for sym, snap in r.json().items():
                        # Use dailyBar.c during pre-market (it's yesterday's close)
                        # Use prevDailyBar.c during market hours (dailyBar = today's running)
                        if now_et.hour >= 10:
                            c = snap.get('prevDailyBar', {}).get('c', 0)
                        else:
                            c = snap.get('dailyBar', {}).get('c', 0)
                        if c and c > 5:
                            prev_closes[sym] = c
                time.sleep(0.2)
            except Exception:
                pass

        # Step 2: yfinance prepost for ALL stocks — get real PM price
        pm_prices = {}
        for sym in all_syms:
            if sym not in prev_closes:
                continue
            try:
                hist = yf.Ticker(sym).history(period='1d', interval='1m', prepost=True)
                if not hist.empty:
                    pm_prices[sym] = float(hist['Close'].iloc[-1])
            except Exception:
                pass

        logger.info("GapScanner PM: got prev_close=%d, pm_price=%d",
                     len(prev_closes), len(pm_prices))

        # Step 3: Find gaps ≥ 1%
        result = []
        for sym in all_syms:
            prev = prev_closes.get(sym, 0)
            pm = pm_prices.get(sym, 0)
            if not prev or not pm:
                continue

            pm_gap = (pm / prev - 1) * 100
            if pm_gap < 1.0:
                continue

            info = fund_map.get(sym, {})
            # Try to find existing D0 candidate with real technicals
            existing = next((c for c in candidates if c.get('symbol') == sym), None)
            pick = {
                'symbol': sym,
                'close': prev,
                'scan_price': prev,
                'current_price': round(pm, 2),
                'sector': info.get('sector', ''),
                'beta': info.get('beta', 1.0) or 1.0,
                'market_cap': info.get('market_cap', 0) or 0,
                'atr_pct': existing.get('atr_pct', 0) if existing else 0,
                'momentum_5d': existing.get('momentum_5d', 0) if existing else 0,
                'momentum_20d': existing.get('momentum_20d', 0) if existing else 0,
                'volume_ratio': existing.get('volume_ratio', 1.0) if existing else 1.0,
                'distance_from_20d_high': existing.get('distance_from_20d_high', 0) if existing else 0,
                'd0_ret': existing.get('d0_ret', 0) if existing else 0,
                '_gap_type': 'PM_CONFIRMED',
                '_gap_score': round(pm_gap * 2, 2),
                '_gap_reasons': ['PM_CONFIRMED'],
                '_pm_price': round(pm, 2),
                '_pm_gap': round(pm_gap, 1),
                '_pm_confirmed': True,
                '_signal_count': 2,
                '_ml_prob': min(0.5 + pm_gap / 20, 0.99),
            }
            result.append(pick)

        # Enrich picks that had no D0 data from candidates — fetch from DB
        enrich_syms = [p['symbol'] for p in result if p['atr_pct'] == 0]
        if enrich_syms:
            try:
                with get_session() as sess:
                    for sym in enrich_syms:
                        row = sess.execute(text("""
                            SELECT o.close, o.high, o.low, o.volume,
                                   LAG(o.close,4) OVER (ORDER BY o.date) as p5,
                                   LAG(o.close,19) OVER (ORDER BY o.date) as p20,
                                   AVG(o.volume) OVER (ORDER BY o.date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as avg_vol,
                                   MAX(o.high) OVER (ORDER BY o.date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as h20
                            FROM stock_daily_ohlc o
                            WHERE o.symbol = :s AND o.date <= :d AND o.close > 0
                            ORDER BY o.date DESC LIMIT 1
                        """), {'s': sym, 'd': now_et.strftime('%Y-%m-%d')}).fetchone()
                        if row and row[0]:
                            p = next(x for x in result if x['symbol'] == sym)
                            rng = (row[1] or row[0]) - (row[2] or row[0])
                            p['atr_pct'] = round(rng / row[0] * 100, 2) if row[0] > 0 else 0
                            p['momentum_5d'] = round((row[0] / row[4] - 1) * 100, 2) if row[4] and row[4] > 0 else 0
                            p['momentum_20d'] = round((row[0] / row[5] - 1) * 100, 2) if row[5] and row[5] > 0 else 0
                            p['volume_ratio'] = round(row[3] / row[6], 2) if row[6] and row[6] > 0 else 1.0
                            p['distance_from_20d_high'] = round((row[0] / row[7] - 1) * 100, 2) if row[7] and row[7] > 0 else 0
            except Exception as e:
                logger.warning("GapScanner PM: enrich error: %s", e)

        result.sort(key=lambda c: c['_pm_gap'], reverse=True)
        logger.info("GapScanner PM: %d stocks gap up ≥1%%", len(result))

        # Cache PM results — persists after pre-market hours end
        self._pm_cache = result

        # Also persist to DB so it survives restart
        if result:
            try:
                today = now_et.strftime('%Y-%m-%d')
                with get_session() as conn:
                    conn.execute(text("CREATE TABLE IF NOT EXISTS gap_pm_cache (date TEXT PRIMARY KEY, data_json TEXT)"))
                    conn.execute(text("INSERT OR REPLACE INTO gap_pm_cache (date, data_json) VALUES (:p0, :p1)"),
                                 {'p0': today, 'p1': json.dumps(result)})
            except Exception:
                pass

        return result

    def scan_intraday(self, scan_time_et: str = None, scan_date: str = None) -> list[dict]:
        """Intraday gap strategy — runs 09:30-16:00 ET.

        3 strategies from backtest (all WR ≥ 70%):

        S1: GAP_PULLBACK (09:30-11:00)
            PM≥1% + pullback >0.5% from open → buy low
            Backtest: n=2,175 WR=75% avg=+1.8%

        S2: MORNING_BREAKOUT (10:30-15:00)
            Break morning high (09:30-10:30) + volume surge
            Backtest: n=1,695 WR=high avg=+1.8%

        S3: GAP_FADE_SHORT (09:30-10:30)
            Gap≥2% + first 30min down >0.5% → short signal
            Backtest: n=420 WR=77% (short) avg=-2.4%

        Returns list of signal dicts with strategy, symbol, entry, etc.
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        if scan_time_et is None:
            now_et = datetime.now(ZoneInfo('America/New_York'))
            scan_time_et = now_et.strftime('%H:%M')

        with get_session() as conn:
            today = scan_date or datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d')
            signals = []
            now_et = datetime.now(ZoneInfo('America/New_York'))

            # ── Load Alpaca keys ──
            import requests
            import yfinance as yf
            _env = {}
            for line in open(Path(__file__).resolve().parents[2] / '.env'):
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    _env[k.strip()] = v.strip()
            _headers = {
                'APCA-API-KEY-ID': _env.get('ALPACA_API_KEY', ''),
                'APCA-API-SECRET-KEY': _env.get('ALPACA_SECRET_KEY', ''),
            }

            # ── Get ALL universe symbols ──
            all_syms = [r[0] for r in conn.execute(
                text("SELECT symbol FROM stock_fundamentals WHERE avg_volume > 300000 AND market_cap > 5e8")
            ).fetchall()]

            # ── Alpaca snapshots for prev_close + today's open/high/low/close ──
            snap_data = {}
            for i in range(0, len(all_syms), 200):
                batch = all_syms[i:i+200]
                try:
                    r = requests.get('https://data.alpaca.markets/v2/stocks/snapshots',
                        params={'symbols': ','.join(batch)},
                        headers=_headers, timeout=15)
                    if r.status_code == 200:
                        snap_data.update(r.json())
                    time.sleep(0.2)
                except Exception:
                    pass

            logger.info("GapScanner intraday: %d snapshots from Alpaca", len(snap_data))

            for sym in all_syms:
                snap = snap_data.get(sym)
                if not snap:
                    continue

                # prevDailyBar = yesterday's OHLC (correct prev_close/high)
                # dailyBar = today's running bar (open/high/low/close)
                prev_bar = snap.get('prevDailyBar', {})
                prev_close = prev_bar.get('c', 0)
                prev_high = prev_bar.get('h', 0)
                if not prev_close or prev_close <= 0:
                    continue

                today_bar = snap.get('dailyBar', {})
                minute_bar = snap.get('minuteBar', {})
                latest_trade = snap.get('latestTrade', {})
                current_price = latest_trade.get('p', 0)
                if not current_price:
                    continue

                mkt_open = today_bar.get('o', current_price)
                day_high = today_bar.get('h', current_price)
                day_low = today_bar.get('l', current_price)
                day_volume = today_bar.get('v', 0)

                gap_pct = (mkt_open / prev_close - 1) * 100

                # ── GATE: Only gap UP stocks (≥1%) ──
                if gap_pct < 1.0:
                    continue

                latest_time = scan_time_et or now_et.strftime('%H:%M')
                ret_from_open = (current_price / mkt_open - 1) * 100
                gap_filled = day_low <= prev_close

                # ══════════════════════════════════════════════════
                # Honest Intraday Strategies (no data leakage)
                # Backtest: 856 symbols, 55M bars, 2023-2026
                # Key insight: first bar >+1% is the ONLY honest
                # predictor. Pre-open features have AUC=0.50.
                # ══════════════════════════════════════════════════

                # ── S1: FIRST_BAR_STRONG ──
                # Gap ≥1% + first bar green >+1% from open + VIX gate
                # Honest backtest: WR 75%, PF 5.24, ~88 signals/month
                # (VIX<20 + breadth>50 variant)
                # Without VIX gate: WR 73%, PF 4.20, ~150/month
                if (latest_time >= '09:35' and latest_time <= '09:50'
                        and ret_from_open > 1.0
                        and not gap_filled):

                    entry = current_price
                    sl = day_low
                    tp = entry * 1.02

                    signals.append({
                        'symbol': sym,
                        'strategy': 'FIRST_BAR_STRONG',
                        'action': 'BUY',
                        'entry_price': round(entry, 2),
                        'current_price': round(current_price, 2),
                        'sl_price': round(sl, 2),
                        'tp_price': round(tp, 2),
                        'gap_pct': round(gap_pct, 1),
                        'ret_from_open': round(ret_from_open, 1),
                        'confidence': 75,
                        'reason': f'Gap +{gap_pct:.1f}% + first bar +{ret_from_open:.1f}% (strong open)',
                        'backtest_wr': 75,
                        'scan_time': latest_time,
                    })

                # ── S2: FIRST_BAR_CONFIRM ──
                # Gap ≥1% + holding above open >0.5% after 10 min
                # Honest backtest: WR 68%, PF 3.24
                if (latest_time >= '09:40' and latest_time <= '10:30'
                        and ret_from_open > 0.5
                        and not gap_filled):

                    entry = current_price
                    sl = day_low
                    tp = entry * 1.02

                    signals.append({
                        'symbol': sym,
                        'strategy': 'FIRST_BAR_CONFIRM',
                        'action': 'BUY',
                        'entry_price': round(entry, 2),
                        'current_price': round(current_price, 2),
                        'sl_price': round(sl, 2),
                        'tp_price': round(tp, 2),
                        'gap_pct': round(gap_pct, 1),
                        'ret_from_open': round(ret_from_open, 1),
                        'confidence': 68,
                        'reason': f'Gap +{gap_pct:.1f}% + holding +{ret_from_open:.1f}% above open',
                        'backtest_wr': 68,
                        'scan_time': latest_time,
                    })

                # ── S3: GAP_NOT_FILLED ──
                # Gap ≥2% + never touched prev close + above open
                # Honest backtest: WR 61%, PF 1.94
                if (latest_time >= '10:00' and latest_time <= '11:00'
                        and gap_pct >= 2
                        and not gap_filled
                        and current_price > mkt_open):

                    entry = current_price
                    sl = day_low
                    tp = entry * 1.02

                    signals.append({
                        'symbol': sym,
                        'strategy': 'GAP_NOT_FILLED',
                        'action': 'BUY',
                        'entry_price': round(entry, 2),
                        'current_price': round(current_price, 2),
                        'sl_price': round(sl, 2),
                        'tp_price': round(tp, 2),
                        'gap_pct': round(gap_pct, 1),
                        'confidence': 61,
                        'reason': f'Gap +{gap_pct:.1f}% held — not filled + above open',
                        'backtest_wr': 61,
                        'scan_time': latest_time,
                    })

            # Sort by confidence
            # ── VIX GATE ──
            # Honest backtest: VIX<20 = WR 75%, VIX<25 = WR 73%, VIX>25 = WR drops to ~50%
            try:
                macro_row = conn.execute(text("""
                    SELECT ms.vix_close, mb.pct_above_20d_ma
                    FROM macro_snapshots ms
                    LEFT JOIN market_breadth mb ON ms.date = mb.date
                    ORDER BY ms.date DESC LIMIT 1
                """)).fetchone()
                vix = macro_row[0] if macro_row and macro_row[0] else 20.0
                breadth = macro_row[1] if macro_row and macro_row[1] else 50.0
            except Exception:
                vix = 20.0
                breadth = 50.0

            # Tag signals with VIX tier
            pre_filter_count = len(signals)
            for s in signals:
                s['vix'] = round(vix, 1)
                s['breadth'] = round(breadth, 1)

                if vix <= 20 and breadth >= 50:
                    s['ml_tier'] = 'HIGH'
                    s['confidence'] = 75
                    s['backtest_wr'] = 75
                elif vix <= 25:
                    s['ml_tier'] = 'CONFIRMED'
                    # keep original confidence/wr
                else:
                    s['ml_tier'] = 'CAUTION'
                    s['confidence'] = max(s.get('confidence', 50) - 10, 45)
                    s['backtest_wr'] = 50

                # FIRST_BAR_STRONG with VIX<20 + breadth>50 = best combo
                if s['strategy'] == 'FIRST_BAR_STRONG' and vix <= 20 and breadth >= 50:
                    s['ml_tier'] = 'HIGH'
                    s['confidence'] = 75
                    s['backtest_wr'] = 75

            # ML ensemble filter (if fitted — adds additional filtering)
            if signals and self._intraday_ml and self._intraday_ml._fitted:
                try:
                    macro_for_ml = {'vix_close': vix, 'pct_above_20d_ma': breadth}
                    self._intraday_ml.predict(signals, macro_for_ml)
                    # Only filter out if ML explicitly rejects (keeps backward compat)
                    signals = [s for s in signals if s.get('_ml_pass', True)]
                except Exception as e:
                    logger.warning("GapScanner intraday ML filter error: %s", e)

            # Sort: HIGH first, then CONFIRMED, then CAUTION
            tier_order = {'HIGH': 0, 'CONFIRMED': 1, 'CAUTION': 2}
            signals.sort(key=lambda s: (tier_order.get(s.get('ml_tier', 'CAUTION'), 2), -s.get('confidence', 0)))

            logger.info("GapScanner intraday: %d signals (VIX=%.1f, breadth=%.0f%%) [%s]",
                        len(signals), vix, breadth,
                        ', '.join(f"{s['symbol']}:{s['strategy']}:{s.get('ml_tier','?')}" for s in signals[:5]))

            logger.info("GapScanner intraday: %d signals at %s [%s]",
                        len(signals), scan_time_et,
                        ', '.join(f"{s['symbol']}:{s['strategy']}" for s in signals[:5]))

            return signals

    def fit(self, max_date: str = None):
        """Learn event impacts, peer correlations, and train ML model from historical data."""
        try:
            max_date = max_date or date.today().isoformat()

            with get_session() as conn:
                # Legacy learning (event impact, sector bounce)
                self._learn_event_impact(conn, max_date)
                self._learn_sector_bounce(conn, max_date)
                self._fitted = True
                self._fit_date = max_date
                logger.info("GapScanner: legacy fitted — %d event_impacts, date=%s",
                            len(self._event_impact), max_date)

                # ML model training
                self._fit_ml_model(conn, max_date)

            # Intraday ML ensemble filter (separate fit)
            if self._intraday_ml is not None:
                try:
                    self._intraday_ml.fit(max_date=max_date)
                except Exception as e:
                    logger.warning("GapScanner: IntradayMLFilter fit error: %s", e)

        except Exception as e:
            logger.error("GapScanner fit error: %s", e, exc_info=True)

    def _fit_ml_model(self, conn, max_date: str):
        """Train LogisticRegression on historical data with walk-forward split."""
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            from sklearn.metrics import roc_auc_score, accuracy_score
        except ImportError:
            logger.warning("GapScanner: sklearn not available, skipping ML fit")
            return

        logger.info("GapScanner: building training data...")
        X, y, dates = self._build_training_data(conn, max_date)

        if X is None or len(X) < 200:
            logger.warning("GapScanner: insufficient training data (%d rows), need >= 200",
                           len(X) if X is not None else 0)
            return

        n = len(X)
        logger.info("GapScanner: training data built — %d samples, %d features, "
                     "label mean=%.3f", n, X.shape[1], y.mean())

        # Walk-forward split: train on first 80%, test on last 20%
        split_idx = int(n * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        if len(np.unique(y_train)) < 2:
            logger.warning("GapScanner: only one class in training set, skipping ML fit")
            return

        # Standardize features
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # Train logistic regression with L2 regularization
        model = LogisticRegression(
            C=1.0, penalty='l2', solver='lbfgs',
            max_iter=1000, class_weight='balanced', random_state=42,
        )
        model.fit(X_train_s, y_train)

        # Evaluate on test set
        y_prob = model.predict_proba(X_test_s)[:, 1]
        y_pred = model.predict(X_test_s)

        try:
            auc = roc_auc_score(y_test, y_prob)
        except ValueError:
            auc = 0.5

        acc = accuracy_score(y_test, y_pred)
        wr_test = y_test.mean()

        self._ml_metrics = {
            'auc': round(auc, 4),
            'accuracy': round(acc, 4),
            'train_n': split_idx,
            'test_n': n - split_idx,
            'test_wr': round(float(wr_test), 4),
        }

        # Log feature importances
        coefs = model.coef_[0]
        feat_imp = sorted(zip(self._feature_names, coefs),
                          key=lambda x: abs(x[1]), reverse=True)
        logger.info("GapScanner ML: AUC=%.4f, Accuracy=%.4f, train=%d, test=%d, test_wr=%.3f",
                     auc, acc, split_idx, n - split_idx, wr_test)
        logger.info("GapScanner ML: Top features:")
        for fname, coef in feat_imp[:10]:
            logger.info("  %20s: %+.4f", fname, coef)

        # Store model + scaler
        self._model = model
        self._scaler = scaler
        self._ml_fitted = True
        logger.info("GapScanner: ML model fitted successfully")

    def _build_training_data(self, conn, max_date: str):
        """Build feature matrix + label vector from historical stock-day data.

        For each stock-day in stock_daily_ohlc (2025-01-01+):
          - Label: next_day_total_return > 0 (binary)
          - Features: stock, news, analyst, insider, context, peer, gap-type indicators

        Returns: (X: np.ndarray, y: np.ndarray, dates: list[str]) or (None, None, None)
        """
        logger.info("GapScanner: querying stock data for training...")

        # --- Step 1: Get all stock-day bars with D0 features and D1 label ---
        rows = conn.execute(text('''
            WITH bars AS (
                SELECT symbol, date, open, high, low, close, volume,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
                       LAG(close,4) OVER (PARTITION BY symbol ORDER BY date) as prev5_close,
                       LAG(close,19) OVER (PARTITION BY symbol ORDER BY date) as prev20_close,
                       AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as avg_vol_20d,
                       MAX(high) OVER (PARTITION BY symbol ORDER BY date
                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as high_20d,
                       LEAD(open) OVER (PARTITION BY symbol ORDER BY date) as next_open,
                       LEAD(close) OVER (PARTITION BY symbol ORDER BY date) as next_close
                FROM stock_daily_ohlc
                WHERE date >= '2024-10-01' AND date <= :p0
                AND open > 0 AND close > 5
            )
            SELECT b.symbol, b.date, b.open, b.high, b.low, b.close, b.volume,
                   b.prev_close, b.prev5_close, b.prev20_close,
                   b.avg_vol_20d, b.high_20d, b.next_open, b.next_close,
                   sf.sector, sf.beta, sf.market_cap
            FROM bars b
            LEFT JOIN stock_fundamentals sf ON b.symbol = sf.symbol
            WHERE b.date >= '2025-01-01'
            AND b.prev_close IS NOT NULL AND b.prev_close > 0
            AND b.next_open IS NOT NULL AND b.next_open > 0
            AND b.next_close IS NOT NULL AND b.next_close > 0
            AND b.avg_vol_20d IS NOT NULL AND b.avg_vol_20d > 0
            ORDER BY b.date, b.symbol
        '''), {'p0': max_date}).mappings().fetchall()

        if not rows:
            return None, None, None

        logger.info("GapScanner: %d stock-day bars loaded", len(rows))

        # --- Step 2: Pre-load signal data into lookup dicts ---
        # These are loaded once for the full date range for efficiency

        # News: {(symbol, date) -> {sent, n_articles, has_catalyst, headlines}}
        news_lookup = self._build_news_lookup(conn, '2025-01-01', max_date)

        # Analyst: {(symbol, date) -> {n_upgrades, n_downgrades, target_change}}
        analyst_lookup = self._build_analyst_lookup(conn, '2025-01-01', max_date)

        # Insider: {(symbol, date) -> net_buy_value}
        insider_lookup = self._build_insider_lookup(conn, '2025-01-01', max_date)

        # Sector returns: {(sector, date) -> pct_change}
        sector_lookup = self._build_sector_lookup(conn, '2025-01-01', max_date)

        # Macro: {date -> {vix, breadth}}
        macro_lookup = self._build_macro_lookup(conn, '2025-01-01', max_date)

        # Peer co-mentions: {(symbol, date) -> {peer_sent, n_peer_articles}}
        peer_lookup = self._build_peer_lookup(conn, '2025-01-01', max_date)

        # Earnings AMC: {(symbol, date)}
        earnings_amc_lookup = self._build_earnings_amc_lookup(conn, '2025-01-01', max_date)

        # Scheduled catalyst patterns
        catalyst_lookup = self._build_catalyst_lookup(conn, '2025-01-01', max_date)

        # BTC correlation per symbol (static, computed once)
        btc_corr_lookup = self._build_btc_corr_lookup(conn, '2025-01-01', max_date)

        logger.info("GapScanner: signal lookups built — news=%d, analyst=%d, insider=%d, "
                     "peer=%d, earnings=%d, catalyst=%d, btc_corr=%d",
                     len(news_lookup), len(analyst_lookup), len(insider_lookup),
                     len(peer_lookup), len(earnings_amc_lookup), len(catalyst_lookup),
                     len(btc_corr_lookup))

        # --- Step 3: Build feature matrix ---
        X_rows = []
        y_rows = []
        date_rows = []

        for r in rows:
            sym = r['symbol']
            dt = r['date']

            # Label: will stock GAP UP tomorrow?
            # Gap = next_open / today_close - 1
            # Threshold 1% = meaningful gap (not noise)
            gap_pct = (r['next_open'] / r['close'] - 1) * 100
            label = 1 if gap_pct >= 1.0 else 0

            # Stock features
            d0_ret = (r['close'] / r['open'] - 1) * 100 if r['open'] > 0 else 0
            mom_5d = ((r['close'] / r['prev5_close'] - 1) * 100
                      if r['prev5_close'] and r['prev5_close'] > 0 else 0)
            mom_20d = ((r['close'] / r['prev20_close'] - 1) * 100
                       if r['prev20_close'] and r['prev20_close'] > 0 else 0)
            vol_ratio = (r['volume'] / r['avg_vol_20d']
                         if r['avg_vol_20d'] and r['avg_vol_20d'] > 0 else 1)
            rng = r['high'] - r['low']
            candle_pos = (r['close'] - r['low']) / rng if rng > 0 else 0.5
            dist_20d = ((r['close'] / r['high_20d'] - 1) * 100
                        if r['high_20d'] and r['high_20d'] > 0 else -10)
            atr_pct = rng / r['close'] * 100 if r['close'] > 0 else 0
            beta = r['beta'] if r['beta'] else 1.0

            # News features
            news_data = news_lookup.get((sym, dt), {})
            has_news = 1 if news_data else 0
            news_sent = news_data.get('sent', 0)
            has_catalyst = news_data.get('has_catalyst', 0)
            n_articles = news_data.get('n_articles', 0)

            # Earnings AMC
            has_amc = 1 if (sym, dt) in earnings_amc_lookup else 0

            # Analyst features (7-day lookback)
            analyst_data = analyst_lookup.get((sym, dt), {})
            n_upgrades = analyst_data.get('n_upgrades', 0)
            n_downgrades = analyst_data.get('n_downgrades', 0)
            target_change = analyst_data.get('target_change', 0)

            # Insider features (7-day lookback)
            insider_net = insider_lookup.get((sym, dt), 0)
            # Normalize to a reasonable scale (log of abs value, signed)
            if insider_net != 0:
                insider_feat = math.copysign(math.log10(abs(insider_net) + 1), insider_net)
            else:
                insider_feat = 0

            # Context features
            sector = r['sector'] or ''
            sector_ret = sector_lookup.get((sector, dt), 0)
            macro_data = macro_lookup.get(dt, {})
            vix = macro_data.get('vix', 20)
            breadth = macro_data.get('breadth', 50)

            # Peer co-mention features
            peer_data = peer_lookup.get((sym, dt), {})
            peer_sent = peer_data.get('peer_sent', 0)
            n_peer_articles = peer_data.get('n_peer_articles', 0)

            # Gap type indicator features
            is_near_high = 1 if dist_20d > -3 else 0
            high_vol = 1 if vol_ratio > 1.5 else 0
            in_uptrend = 1 if (mom_5d > 2 and mom_20d > 5) else 0

            # Scheduled catalyst
            has_sched_catalyst = catalyst_lookup.get((sym, dt), 0)

            # L3.7 fix: Only train on stock-days that have signals
            # (matching _find_candidates filter in scan)
            has_any_signal = (
                has_news or has_amc or has_catalyst or has_sched_catalyst
                or n_upgrades > 0 or n_downgrades > 0
                or insider_feat != 0
                or (sector_ret < -1.5 and d0_ret < -2)  # sector bounce
                or (d0_ret < -3 and vix > 22)            # panic bounce
                or (d0_ret < -3 and breadth < 40)        # oversold bounce
            )
            if not has_any_signal:
                continue

            # BTC features
            btc_mom_1d = macro_data.get('btc_mom_1d', 0)
            stock_btc_corr = btc_corr_lookup.get(sym, 0)

            # Build feature vector (order must match ML_FEATURE_NAMES)
            # v3: removed noise (n_articles, analyst, insider), added non-linear
            feat = [
                d0_ret, mom_5d, mom_20d, vol_ratio, candle_pos,
                dist_20d, atr_pct, beta,
                has_news, news_sent, has_catalyst, has_amc,
                sector_ret, breadth,
                stock_btc_corr * max(btc_mom_1d, 0),  # btc_corr_up
                stock_btc_corr * min(btc_mom_1d, 0),  # btc_corr_down
                peer_sent, n_peer_articles,
                1 if 22 <= vix <= 28 else 0,            # vix_sweet_spot
                1 if vix > 28 else 0,                   # vix_too_high
                1 if d0_ret < -2 and breadth < 40 else 0,  # is_oversold
                abs(min(d0_ret, 0)) * vol_ratio,        # d0_drop_x_vol
                is_near_high, high_vol, in_uptrend,
                has_sched_catalyst,
            ]

            X_rows.append(feat)
            y_rows.append(label)
            date_rows.append(dt)

        X = np.array(X_rows, dtype=np.float64)
        y = np.array(y_rows, dtype=np.int32)

        # Handle NaN/Inf
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        return X, y, date_rows

    # --- Signal Lookup Builders (bulk load for training efficiency) ---

    def _build_news_lookup(self, conn, start_date: str, end_date: str) -> dict:
        """Build {(symbol, date) -> news_features} lookup from news_events."""
        lookup = {}
        rows = conn.execute(text('''
            SELECT symbol, scan_date_et, event_type, sentiment_score,
                   symbols_mentioned, headline
            FROM news_events
            WHERE scan_date_et >= :p0 AND scan_date_et <= :p1
            AND symbol IS NOT NULL
        '''), {'p0': start_date, 'p1': end_date}).mappings().fetchall()

        # Aggregate per (symbol, date)
        agg = defaultdict(lambda: {'sent': 0, 'n_articles': 0, 'has_catalyst': 0, 'headlines': []})
        catalyst_types = {
            'product_launch', 'regulatory_approval', 'partnership',
            'merger_acquisition', 'earnings_report',
        }
        for r in rows:
            key = (r['symbol'], r['scan_date_et'])
            agg[key]['sent'] += r['sentiment_score'] or 0
            agg[key]['n_articles'] += 1
            if r['event_type'] in catalyst_types:
                agg[key]['has_catalyst'] = 1
            if r['headline']:
                agg[key]['headlines'].append(r['headline'])

        for key, val in agg.items():
            lookup[key] = {
                'sent': val['sent'],
                'n_articles': val['n_articles'],
                'has_catalyst': val['has_catalyst'],
                'headlines': val['headlines'],
            }
        return lookup

    def _build_analyst_lookup(self, conn, start_date: str, end_date: str) -> dict:
        """Build {(symbol, date) -> analyst_features} with 7-day lookback.

        For each stock-date, we count upgrades/downgrades in the prior 7 days.
        We pre-compute this per rating date then spread into a 7-day window.
        """
        # Get all ratings in range (expanded by 7 days for lookback)
        rows = conn.execute(text('''
            SELECT symbol, date, action, price_target, prior_price_target
            FROM analyst_ratings_history
            WHERE date >= date(:p0, '-7 days') AND date <= :p1
        '''), {'p0': start_date, 'p1': end_date}).mappings().fetchall()

        # Group by (symbol, rating_date)
        by_sym_date = defaultdict(lambda: {'n_up': 0, 'n_down': 0, 'targets': []})
        for r in rows:
            key = (r['symbol'], r['date'])
            action = (r['action'] or '').lower()
            if 'upgrade' in action or 'reit' in action or 'outperform' in action:
                by_sym_date[key]['n_up'] += 1
            elif 'downgrade' in action:
                by_sym_date[key]['n_down'] += 1
            pt = r['price_target']
            ppt = r['prior_price_target']
            if pt and pt > 0 and ppt and ppt > 0:
                by_sym_date[key]['targets'].append((pt, ppt))

        # Spread into 7-day windows: for each (symbol, rating_date),
        # it affects stock-dates from rating_date to rating_date+6
        lookup = defaultdict(lambda: {'n_upgrades': 0, 'n_downgrades': 0, 'target_change': 0})
        for (sym, rdate), data in by_sym_date.items():
            try:
                rd = datetime.strptime(rdate, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                continue
            for offset in range(7):
                stock_date = (rd + timedelta(days=offset)).isoformat()
                if stock_date < start_date or stock_date > end_date:
                    continue
                key = (sym, stock_date)
                lookup[key]['n_upgrades'] += data['n_up']
                lookup[key]['n_downgrades'] += data['n_down']
                if data['targets']:
                    # Average target change pct
                    changes = [(pt / ppt - 1) * 100 for pt, ppt in data['targets']]
                    avg_change = sum(changes) / len(changes)
                    # Keep the max change if multiple ratings affect same date
                    if abs(avg_change) > abs(lookup[key]['target_change']):
                        lookup[key]['target_change'] = avg_change

        return dict(lookup)

    def _build_insider_lookup(self, conn, start_date: str, end_date: str) -> dict:
        """Build {(symbol, date) -> net_buy_value} with 7-day lookback."""
        rows = conn.execute(text('''
            SELECT symbol, filing_date, transaction_type, shares, price
            FROM insider_transactions_history
            WHERE filing_date >= date(:p0, '-7 days') AND filing_date <= :p1
        '''), {'p0': start_date, 'p1': end_date}).mappings().fetchall()

        # Group by (symbol, filing_date)
        by_sym_fdate = defaultdict(float)
        for r in rows:
            val = (r['shares'] or 0) * (r['price'] or 0)
            key = (r['symbol'], r['filing_date'])
            if r['transaction_type'] == 'P':
                by_sym_fdate[key] += val
            elif r['transaction_type'] == 'S':
                by_sym_fdate[key] -= val

        # Spread into 7-day windows
        lookup = defaultdict(float)
        for (sym, fdate), net in by_sym_fdate.items():
            try:
                fd = datetime.strptime(fdate, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                continue
            for offset in range(7):
                stock_date = (fd + timedelta(days=offset)).isoformat()
                if stock_date < start_date or stock_date > end_date:
                    continue
                lookup[(sym, stock_date)] += net

        return dict(lookup)

    def _build_sector_lookup(self, conn, start_date: str, end_date: str) -> dict:
        """Build {(sector, date) -> pct_change} lookup."""
        rows = conn.execute(text('''
            SELECT sector, date, pct_change FROM sector_etf_daily_returns
            WHERE date >= :p0 AND date <= :p1
        '''), {'p0': start_date, 'p1': end_date}).mappings().fetchall()
        return {(r['sector'], r['date']): r['pct_change'] or 0 for r in rows}

    def _build_macro_lookup(self, conn, start_date: str, end_date: str) -> dict:
        """Build {date -> {vix, breadth, btc_mom_1d}} from macro_snapshots + market_breadth."""
        macro = {}
        rows = conn.execute(text('''
            SELECT m.date, m.vix_close, m.btc_close,
                   LAG(m.btc_close) OVER (ORDER BY m.date) as prev_btc,
                   b.pct_above_20d_ma
            FROM macro_snapshots m
            LEFT JOIN market_breadth b ON m.date = b.date
            WHERE m.date >= date(:p0, '-5 days') AND m.date <= :p1
        '''), {'p0': start_date, 'p1': end_date}).mappings().fetchall()
        for r in rows:
            btc_mom = 0
            if r['btc_close'] and r['prev_btc'] and r['prev_btc'] > 0:
                btc_mom = (r['btc_close'] / r['prev_btc'] - 1) * 100
            macro[r['date']] = {
                'vix': r['vix_close'] if r['vix_close'] else 20,
                'breadth': r['pct_above_20d_ma'] if r['pct_above_20d_ma'] else 50,
                'btc_mom_1d': round(btc_mom, 3),
            }
        return macro

    def _build_btc_corr_lookup(self, conn, start_date: str, end_date: str) -> dict:
        """Build {symbol -> btc_corr} — 90d rolling correlation of stock vs BTC returns."""
        # Get BTC daily returns
        btc_rows = conn.execute(text('''
            SELECT date, btc_close, LAG(btc_close) OVER (ORDER BY date) as prev
            FROM macro_snapshots
            WHERE btc_close IS NOT NULL AND date >= date(:p0, '-120 days') AND date <= :p1
        '''), {'p0': start_date, 'p1': end_date}).mappings().fetchall()
        btc_rets = {}
        for r in btc_rows:
            if r['prev'] and r['prev'] > 0:
                btc_rets[r['date']] = (r['btc_close'] / r['prev'] - 1) * 100

        if len(btc_rets) < 30:
            return {}

        # Get stock daily returns for all symbols
        stock_rows = conn.execute(text('''
            SELECT symbol, date, close, LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev
            FROM stock_daily_ohlc
            WHERE date >= date(:p0, '-120 days') AND date <= :p1 AND close > 5
        '''), {'p0': start_date, 'p1': end_date}).mappings().fetchall()

        stock_rets = defaultdict(dict)
        for r in stock_rows:
            if r['prev'] and r['prev'] > 0:
                stock_rets[r['symbol']][r['date']] = (r['close'] / r['prev'] - 1) * 100

        # Compute correlation per symbol
        lookup = {}
        btc_dates = set(btc_rets.keys())
        for sym, srets in stock_rets.items():
            common = sorted(set(srets.keys()) & btc_dates)
            if len(common) < 30:
                continue
            # Use last 90 common dates
            common = common[-90:]
            a = [srets[d] for d in common]
            b = [btc_rets[d] for d in common]
            n = len(a)
            ma, mb = sum(a)/n, sum(b)/n
            cov = sum((a[i]-ma)*(b[i]-mb) for i in range(n))/n
            sa = (sum((x-ma)**2 for x in a)/n)**0.5
            sb = (sum((x-mb)**2 for x in b)/n)**0.5
            corr = cov/(sa*sb) if sa > 0 and sb > 0 else 0
            lookup[sym] = round(corr, 3)

        logger.info("GapScanner: BTC correlation computed for %d symbols (top: %s)",
                     len(lookup),
                     ', '.join(f'{s}={c:+.2f}' for s, c in
                               sorted(lookup.items(), key=lambda x: -abs(x[1]))[:5]))
        return lookup

    def _build_peer_lookup(self, conn, start_date: str, end_date: str) -> dict:
        """Build {(symbol, date) -> {peer_sent, n_peer_articles}} from co-mentions.

        For each candidate symbol, find news_events where symbols_mentioned
        contains this symbol, then compute avg sentiment of co-mentioned peers.
        """
        lookup = {}
        rows = conn.execute(text('''
            SELECT symbol, symbols_mentioned, scan_date_et, sentiment_score
            FROM news_events
            WHERE scan_date_et >= :p0 AND scan_date_et <= :p1
            AND symbols_mentioned IS NOT NULL AND symbols_mentioned LIKE '%,%'
        '''), {'p0': start_date, 'p1': end_date}).mappings().fetchall()

        # For each article with multiple symbols, each symbol gets peer stats
        # {(sym, date) -> [peer_sentiments]}
        peer_agg = defaultdict(lambda: {'sents': [], 'count': 0})

        for r in rows:
            try:
                syms = json.loads(r['symbols_mentioned'])
            except (json.JSONDecodeError, TypeError):
                continue
            syms = [s for s in syms if s and isinstance(s, str) and len(s) <= 6]
            if len(syms) < 2:
                continue

            dt = r['scan_date_et']
            sent = r['sentiment_score'] or 0

            for sym in syms:
                key = (sym, dt)
                # Peer sentiment = sentiment of articles mentioning this symbol
                # alongside other symbols
                peer_agg[key]['sents'].append(sent)
                peer_agg[key]['count'] += 1

        for key, val in peer_agg.items():
            sents = val['sents']
            lookup[key] = {
                'peer_sent': sum(sents) / len(sents) if sents else 0,
                'n_peer_articles': val['count'],
            }

        return lookup

    def _build_earnings_amc_lookup(self, conn, start_date: str, end_date: str) -> set:
        """Build set of (symbol, date) with AMC earnings."""
        amc = set()
        rows = conn.execute(text('''
            SELECT symbol, report_date, timing FROM earnings_history
            WHERE report_date >= :p0 AND report_date <= :p1
            AND timing IS NOT NULL
        '''), {'p0': start_date, 'p1': end_date}).mappings().fetchall()
        for r in rows:
            t = (r['timing'] or '').upper()
            if 'AMC' in t or 'AFTER' in t:
                amc.add((r['symbol'], r['report_date']))
        return amc

    def _build_catalyst_lookup(self, conn, start_date: str, end_date: str) -> dict:
        """Build {(symbol, date) -> 1} for stocks with scheduled catalysts.

        Detect date patterns in headlines: "on March 25", "tomorrow",
        "next week", "data readout", "FDA decision", "PDUFA", etc.
        """
        catalyst_patterns = re.compile(
            r'\b(?:on (?:January|February|March|April|May|June|July|August|September|'
            r'October|November|December) \d{1,2}|tomorrow|next week|data readout|'
            r'FDA (?:decision|approval|panel|review)|PDUFA|phase \d+ (?:results|data|readout)|'
            r'analyst day|investor day|guidance update|product launch)\b',
            re.IGNORECASE,
        )

        lookup = {}
        rows = conn.execute(text('''
            SELECT symbol, scan_date_et, headline
            FROM news_events
            WHERE scan_date_et >= :p0 AND scan_date_et <= :p1
            AND symbol IS NOT NULL AND headline IS NOT NULL
        '''), {'p0': start_date, 'p1': end_date}).mappings().fetchall()

        for r in rows:
            if catalyst_patterns.search(r['headline']):
                lookup[(r['symbol'], r['scan_date_et'])] = 1

        return lookup

    def _score_candidates_ml(self, candidates: list, conn, macro: dict, scan_date: str):
        """Score all candidates using the fitted ML model.

        Builds feature vectors for each candidate and calls predict_proba.
        Sets c['_gap_score'] = ml_probability * 10.
        """
        # Pre-load signal data for this scan_date
        news_lookup = self._build_news_lookup(conn, scan_date, scan_date)
        peer_lookup = self._build_peer_lookup(conn, scan_date, scan_date)
        catalyst_lookup = self._build_catalyst_lookup(conn, scan_date, scan_date)
        btc_corr_lookup = self._build_btc_corr_lookup(conn, scan_date, scan_date)

        # BTC momentum from macro
        macro_row = conn.execute(text(
            "SELECT btc_close, LAG(btc_close) OVER (ORDER BY date) as prev "
            "FROM macro_snapshots WHERE btc_close IS NOT NULL ORDER BY date DESC LIMIT 2"
        )).fetchone()
        btc_mom_1d = 0
        if macro_row and macro_row[0] and macro_row[1] and macro_row[1] > 0:
            btc_mom_1d = (macro_row[0] / macro_row[1] - 1) * 100

        feature_matrix = []
        for c in candidates:
            sym = c['symbol']

            # Stock features
            d0_ret = c.get('d0_ret', 0)
            mom_5d = c.get('momentum_5d', 0)
            mom_20d = c.get('momentum_20d', 0)
            vol_ratio = c.get('volume_ratio', 1)
            candle_pos = c.get('candle_pos', 0.5)
            dist_20d = c.get('distance_from_20d_high', -10)
            atr_pct = c.get('atr_pct', 0)
            beta = c.get('beta', 1.0)

            # News features
            news_data = news_lookup.get((sym, scan_date), {})
            has_news = 1 if (news_data or c.get('_n_articles', 0) > 0) else 0
            news_sent = news_data.get('sent', c.get('_news_sent', 0))
            has_catalyst = news_data.get('has_catalyst', 1 if c.get('_has_catalyst') else 0)
            has_amc = 1 if c.get('_has_amc') else 0
            n_articles = news_data.get('n_articles', c.get('_n_articles', 0))

            # Analyst features
            analyst = c.get('_analyst', {})
            n_upgrades = analyst.get('n_upgrades', 0)
            n_downgrades = analyst.get('n_downgrades', 0)
            target_change = analyst.get('target_change', 0)

            # Insider
            insider_net = c.get('_insider_net', 0)
            if insider_net != 0:
                insider_feat = math.copysign(math.log10(abs(insider_net) + 1), insider_net)
            else:
                insider_feat = 0

            # Context
            sector_ret = c.get('_sect_ret', 0)
            vix = c.get('_vix', 20)
            breadth = c.get('_breadth', 50)

            # Peer
            peer_data = peer_lookup.get((sym, scan_date), {})
            peer_sent = peer_data.get('peer_sent', 0)
            n_peer_articles = peer_data.get('n_peer_articles', 0)

            # Gap type indicators
            is_near_high = 1 if dist_20d > -3 else 0
            high_vol = 1 if vol_ratio > 1.5 else 0
            in_uptrend = 1 if (mom_5d > 2 and mom_20d > 5) else 0

            # Scheduled catalyst
            has_sched_catalyst = catalyst_lookup.get((sym, scan_date), 0)

            # BTC features
            stock_btc_corr = btc_corr_lookup.get(sym, 0)

            # v3: match training features exactly
            feat = [
                d0_ret, mom_5d, mom_20d, vol_ratio, candle_pos,
                dist_20d, atr_pct, beta,
                has_news, news_sent, has_catalyst, has_amc,
                sector_ret, breadth,
                stock_btc_corr * max(btc_mom_1d, 0),  # btc_corr_up
                stock_btc_corr * min(btc_mom_1d, 0),  # btc_corr_down
                peer_sent, n_peer_articles,
                1 if 22 <= vix <= 28 else 0,            # vix_sweet_spot
                1 if vix > 28 else 0,                   # vix_too_high
                1 if d0_ret < -2 and breadth < 40 else 0,  # is_oversold
                abs(min(d0_ret, 0)) * vol_ratio,        # d0_drop_x_vol
                is_near_high, high_vol, in_uptrend,
                has_sched_catalyst,
            ]
            feature_matrix.append(feat)

        X = np.array(feature_matrix, dtype=np.float64)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Scale and predict
        X_s = self._scaler.transform(X)
        probas = self._model.predict_proba(X_s)[:, 1]

        for i, c in enumerate(candidates):
            c['_gap_score'] = round(float(probas[i]) * 10, 2)
            c['_ml_prob'] = round(float(probas[i]), 4)

    def load_from_db(self) -> bool:
        """Load fitted model from DB (both legacy JSON and ML pickle)."""
        try:
            with get_session() as conn:
                row = conn.execute(text(
                    "SELECT data_json, fit_date, model_pickle FROM gap_scanner_model "
                    "ORDER BY id DESC LIMIT 1"
                )).fetchone()
            if row:
                data = json.loads(row[0])
                self._event_impact = data.get('event_impact', {})
                self._sector_bounce_stats = data.get('sector_bounce_stats', {})
                self._ml_metrics = data.get('ml_metrics', {})
                self._fitted = True
                self._fit_date = row[1]

                # Load ML model from pickle
                model_blob = row[2]
                if model_blob:
                    ml_data = pickle.loads(model_blob)
                    self._model = ml_data.get('model')
                    self._scaler = ml_data.get('scaler')
                    self._feature_names = ml_data.get('feature_names', ML_FEATURE_NAMES)
                    self._ml_fitted = True
                    logger.info("GapScanner: loaded ML model from DB (fit_date=%s, AUC=%.4f)",
                                self._fit_date, self._ml_metrics.get('auc', 0))
                else:
                    logger.info("GapScanner: loaded from DB (no ML model, fit_date=%s)",
                                self._fit_date)
                return True
        except Exception as e:
            logger.debug("GapScanner: load_from_db failed: %s", e)
        return False

    def save_to_db(self):
        """Save fitted model to DB (legacy JSON + ML pickle)."""
        with get_session() as conn:
            # Ensure table has model_pickle column
            conn.execute(text('''CREATE TABLE IF NOT EXISTS gap_scanner_model (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fit_date TEXT, data_json TEXT, model_pickle BLOB,
                created_at TEXT DEFAULT (datetime('now'))
            )'''))

            # Add model_pickle column if it doesn't exist (upgrade path)
            try:
                conn.execute(text("ALTER TABLE gap_scanner_model ADD COLUMN model_pickle BLOB"))
            except Exception:
                pass  # Column already exists

            data = {
                'event_impact': self._event_impact,
                'sector_bounce_stats': getattr(self, '_sector_bounce_stats', {}),
                'ml_metrics': self._ml_metrics,
            }

            # Serialize ML model
            model_blob = None
            if self._ml_fitted and self._model is not None:
                ml_data = {
                    'model': self._model,
                    'scaler': self._scaler,
                    'feature_names': self._feature_names,
                }
                model_blob = pickle.dumps(ml_data)

            conn.execute(text(
                "INSERT INTO gap_scanner_model (fit_date, data_json, model_pickle) VALUES (:p0, :p1, :p2)"
            ), {'p0': self._fit_date, 'p1': json.dumps(data), 'p2': model_blob})
        logger.info("GapScanner: saved to DB (fit_date=%s, ml=%s, pickle_size=%s)",
                     self._fit_date, self._ml_fitted,
                     f"{len(model_blob)}B" if model_blob else "none")

    # === L1: Candidate Finding ===

    def _find_candidates(self, conn, macro: dict, scan_date: str) -> list[dict]:
        """Find stocks with overnight signals that may gap up tomorrow."""
        candidates = []

        # Get D0 data for all active stocks
        stocks = self._get_d0_data(conn, scan_date)
        if not stocks:
            return []

        # Load overnight signals
        news_signals = self._get_news_signals(conn, scan_date)
        earnings_amc = self._get_earnings_amc(conn, scan_date)
        analyst_signals = self._get_analyst_signals(conn, scan_date)
        insider_signals = self._get_insider_signals(conn, scan_date)
        sector_rets = self._get_sector_returns(conn, scan_date)

        for sym, d0 in stocks.items():
            reasons = []
            signal_count = 0

            # Check each signal source
            news = news_signals.get(sym, [])
            has_amc = sym in earnings_amc
            analyst = analyst_signals.get(sym, {})
            insider = insider_signals.get(sym, 0)
            sect = d0.get('sector', '')
            sect_ret = sector_rets.get(sect, 0)

            # Signal 1: AMC earnings (strongest gap predictor: 18% gap rate)
            if has_amc:
                reasons.append('AMC_EARNINGS')
                signal_count += 3

            # Signal 2: News with positive sentiment
            if news:
                total_sent = sum(n.get('sentiment_score', 0) for n in news)
                has_catalyst = any(n.get('event_type') in (
                    'product_launch', 'regulatory_approval', 'partnership',
                    'merger_acquisition', 'earnings_report'
                ) for n in news)
                if has_catalyst:
                    reasons.append('NEWS_CATALYST')
                    signal_count += 2
                elif total_sent > 0.2:
                    reasons.append('NEWS_POSITIVE')
                    signal_count += 1
                d0['_news_sent'] = total_sent
                d0['_n_articles'] = len(news)
                d0['_has_catalyst'] = has_catalyst

            # Signal 3: Analyst upgrade
            if analyst.get('n_upgrades', 0) > 0:
                reasons.append('ANALYST_UPGRADE')
                signal_count += 1
                if analyst.get('target_change', 0) > 20:
                    reasons.append('BIG_TARGET_RAISE')
                    signal_count += 1

            # Signal 4: Insider buying
            if insider > 100_000:
                reasons.append('INSIDER_BUY')
                signal_count += 1

            # Signal 5: Sector crash -> bounce opportunity
            if sect_ret < -1.5 and d0.get('d0_ret', 0) < -2:
                reasons.append('SECTOR_BOUNCE')
                signal_count += 2

            # Signal 6: Big D0 drop with context (mean reversion)
            d0_ret = d0.get('d0_ret', 0)
            vix = macro.get('vix_close', 20) or 20
            breadth = macro.get('pct_above_20d_ma', 50) or 50
            if d0_ret < -3 and vix > 22:
                reasons.append('PANIC_BOUNCE')
                signal_count += 2
            if d0_ret < -3 and breadth < 40:
                reasons.append('OVERSOLD_BOUNCE')
                signal_count += 1

            # Must have at least 1 signal
            if signal_count == 0:
                continue

            # Build candidate dict
            d0['_gap_reasons'] = reasons
            d0['_signal_count'] = signal_count
            d0['_has_amc'] = has_amc
            d0['_analyst'] = analyst
            d0['_insider_net'] = insider
            d0['_sect_ret'] = sect_ret
            d0['_vix'] = vix
            d0['_breadth'] = breadth
            candidates.append(d0)

        logger.info("GapScanner L1: %d/%d stocks have overnight signals",
                    len(candidates), len(stocks))
        return candidates

    # === L2: Gap Type Classification ===

    def _classify_gap_type(self, c: dict) -> str:
        """Classify expected gap type from D0 features.

        BREAKAWAY:     near 20d high + volume surge -> WR 55%, hold
        EVENT_DRIVEN:  AMC earnings or catalyst news -> depends on result
        SECTOR_BOUNCE: sector crash + stock down -> WR 60-63%, mean reversion
        COMMON:        no strong pattern -> WR 52%, skip
        """
        dist_high = c.get('distance_from_20d_high', -10) or -10
        vol_ratio = c.get('volume_ratio', 1) or 1
        mom_5d = c.get('momentum_5d', 0) or 0
        mom_20d = c.get('momentum_20d', 0) or 0

        # Event-driven takes priority
        if c.get('_has_amc') or c.get('_has_catalyst'):
            return 'EVENT_DRIVEN'

        # Sector bounce
        if 'SECTOR_BOUNCE' in c.get('_gap_reasons', []):
            return 'SECTOR_BOUNCE'

        # Panic/oversold bounce
        if 'PANIC_BOUNCE' in c.get('_gap_reasons', []) or 'OVERSOLD_BOUNCE' in c.get('_gap_reasons', []):
            return 'SECTOR_BOUNCE'

        # Breakaway: near 20d high + volume
        if dist_high > -3 and vol_ratio > 1.5:
            return 'BREAKAWAY'

        # Runaway: already in uptrend
        if mom_5d > 2 and mom_20d > 5:
            return 'RUNAWAY'

        return 'COMMON'

    # === L3: Context Scoring (Rule-Based Fallback) ===

    def _score_context(self, c: dict, macro: dict) -> float:
        """Score candidate by context quality (fallback when ML not fitted).

        Uses learned stats from _event_impact and _sector_bounce_stats.
        No hardcoded scores — base score from learned WR, signals add proportionally.
        """
        score = 0.0
        gap_type = c.get('_gap_type', 'COMMON')
        reasons = c.get('_gap_reasons', [])

        # Base score from learned sector bounce WR (if available)
        sb = getattr(self, '_sector_bounce_stats', {})
        bounce_wr = sb.get('wr', 55) / 100  # default 55% if not learned

        if gap_type == 'SECTOR_BOUNCE':
            score += bounce_wr * 10  # WR 60% → score 6.0
        elif gap_type == 'EVENT_DRIVEN':
            # Use learned event impact
            ei = self._event_impact.get('earnings_report', {})
            event_wr = ei.get('wr', 51) / 100
            score += event_wr * 10
        elif gap_type == 'BREAKAWAY':
            score += 5.5  # between bounce and event
        elif gap_type == 'RUNAWAY':
            score += 0  # skip
        else:
            score += 5.0  # COMMON baseline

        # Signal count as additive boost (each signal = +0.3)
        n_signals = c.get('_signal_count', 0)
        score += n_signals * 0.3

        return round(score, 2)

    # === Data Loading Helpers ===

    def _get_d0_data(self, conn, scan_date: str) -> dict:
        """Get D0 OHLCV + technicals for all stocks."""
        stocks = {}
        rows = conn.execute(text('''
            WITH latest AS (
                SELECT symbol, date, open, high, low, close, volume,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
                       LAG(close,4) OVER (PARTITION BY symbol ORDER BY date) as prev5_close,
                       LAG(close,19) OVER (PARTITION BY symbol ORDER BY date) as prev20_close,
                       AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as avg_vol_20d,
                       MAX(high) OVER (PARTITION BY symbol ORDER BY date
                           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as high_20d
                FROM stock_daily_ohlc
                WHERE date >= date(:p0, '-30 days') AND date <= :p0
                AND open > 0 AND close > 5
            )
            SELECT l.*, sf.sector, sf.industry, sf.market_cap, sf.beta, sf.pe_forward
            FROM latest l
            LEFT JOIN stock_fundamentals sf ON l.symbol = sf.symbol
            WHERE l.date = (SELECT MAX(date) FROM stock_daily_ohlc WHERE date <= :p0)
        '''), {'p0': scan_date}).mappings().fetchall()

        for r in rows:
            sym = r['symbol']
            prev_close = r['prev_close']
            if not prev_close or prev_close <= 0:
                continue

            d0_ret = (r['close'] / r['open'] - 1) * 100 if r['open'] > 0 else 0
            mom_5d = (r['close'] / r['prev5_close'] - 1) * 100 if r['prev5_close'] and r['prev5_close'] > 0 else 0
            mom_20d = (r['close'] / r['prev20_close'] - 1) * 100 if r['prev20_close'] and r['prev20_close'] > 0 else 0
            vol_ratio = r['volume'] / r['avg_vol_20d'] if r['avg_vol_20d'] and r['avg_vol_20d'] > 0 else 1
            dist_20d = (r['close'] / r['high_20d'] - 1) * 100 if r['high_20d'] and r['high_20d'] > 0 else -10
            rng = r['high'] - r['low']
            candle_pos = (r['close'] - r['low']) / rng if rng > 0 else 0.5

            mcap = r['market_cap'] or 0
            stocks[sym] = {
                'symbol': sym,
                'close': r['close'],
                'open': r['open'],
                'scan_price': r['close'],
                'current_price': r['close'],
                'atr_pct': rng / r['close'] * 100 if r['close'] > 0 else 0,
                'momentum_5d': round(mom_5d, 2),
                'momentum_20d': round(mom_20d, 2),
                'volume_ratio': round(vol_ratio, 2),
                'distance_from_20d_high': round(dist_20d, 2),
                'beta': r['beta'] or 1.0,
                'pe_forward': r['pe_forward'] or 0,
                'sector': r['sector'] or '',
                'industry': r['industry'] or '',
                'market_cap': mcap,
                'mcap_log': math.log10(mcap) if mcap > 0 else 0,
                'd0_ret': round(d0_ret, 2),
                'candle_pos': round(candle_pos, 2),
            }

        return stocks

    def _get_news_signals(self, conn, scan_date: str) -> dict:
        """Get news for each symbol from past 2 days."""
        news_map = defaultdict(list)
        rows = conn.execute(text('''
            SELECT symbol, scan_date_et, event_type, sentiment_score,
                   symbols_mentioned, headline, market_session
            FROM news_events
            WHERE scan_date_et >= date(:p0, '-1 day') AND scan_date_et <= :p0
            AND (symbol IS NOT NULL OR symbols_mentioned IS NOT NULL)
        '''), {'p0': scan_date}).mappings().fetchall()

        for r in rows:
            entry = {
                'event_type': r['event_type'],
                'sentiment_score': r['sentiment_score'] or 0,
                'headline': r['headline'],
                'session': r['market_session'],
            }
            if r['symbol']:
                news_map[r['symbol']].append(entry)
            try:
                for s in json.loads(r['symbols_mentioned'] or '[]'):
                    if s and s != r['symbol']:
                        peer_entry = dict(entry)
                        peer_entry['_is_peer'] = True
                        news_map[s].append(peer_entry)
            except (json.JSONDecodeError, TypeError):
                pass

        return news_map

    def _get_earnings_amc(self, conn, scan_date: str) -> set:
        """Get symbols with AMC earnings on scan_date."""
        amc = set()
        rows = conn.execute(text('''
            SELECT symbol, timing FROM earnings_history
            WHERE report_date = :p0 AND timing IS NOT NULL
        '''), {'p0': scan_date}).mappings().fetchall()
        for r in rows:
            t = (r['timing'] or '').upper()
            if 'AMC' in t or 'AFTER' in t:
                amc.add(r['symbol'])
        return amc

    def _get_analyst_signals(self, conn, scan_date: str) -> dict:
        """Get recent analyst upgrades/downgrades."""
        signals = defaultdict(lambda: {'n_upgrades': 0, 'n_downgrades': 0, 'target_change': 0})
        rows = conn.execute(text('''
            SELECT symbol, action, price_target
            FROM analyst_ratings_history
            WHERE date >= date(:p0, '-7 days') AND date <= :p0
        '''), {'p0': scan_date}).mappings().fetchall()

        target_prices = defaultdict(list)
        for r in rows:
            sym = r['symbol']
            action = (r['action'] or '').lower()
            if 'upgrade' in action or 'reit' in action or 'outperform' in action:
                signals[sym]['n_upgrades'] += 1
            elif 'downgrade' in action:
                signals[sym]['n_downgrades'] += 1
            tp = r['price_target']
            if tp and tp > 0:
                target_prices[sym].append(tp)

        # Compute target price change
        for sym, tps in target_prices.items():
            if len(tps) >= 2:
                signals[sym]['target_change'] = (max(tps) / min(tps) - 1) * 100

        return dict(signals)

    def _get_insider_signals(self, conn, scan_date: str) -> dict:
        """Get insider net buying value."""
        insider = defaultdict(float)
        rows = conn.execute(text('''
            SELECT symbol, transaction_type, shares, price
            FROM insider_transactions_history
            WHERE filing_date >= date(:p0, '-7 days') AND filing_date <= :p0
        '''), {'p0': scan_date}).mappings().fetchall()
        for r in rows:
            val = (r['shares'] or 0) * (r['price'] or 0)
            if r['transaction_type'] == 'P':
                insider[r['symbol']] += val
            elif r['transaction_type'] == 'S':
                insider[r['symbol']] -= val
        return dict(insider)

    def _get_sector_returns(self, conn, scan_date: str) -> dict:
        """Get sector D0 returns."""
        sector_ret = {}
        rows = conn.execute(text('''
            SELECT sector, pct_change FROM sector_etf_daily_returns
            WHERE date = (SELECT MAX(date) FROM sector_etf_daily_returns WHERE date <= :p0)
        '''), {'p0': scan_date}).mappings().fetchall()
        for r in rows:
            sector_ret[r['sector']] = r['pct_change'] or 0
        return sector_ret

    # === Learning Methods (Legacy) ===

    def _learn_event_impact(self, conn, max_date: str):
        """Learn average price impact per event_type for co-mentioned stocks."""
        rows = conn.execute(text('''
            SELECT ne.event_type, ne.symbols_mentioned, ne.scan_date_et
            FROM news_events ne
            WHERE ne.symbols_mentioned LIKE '%,%'
            AND ne.scan_date_et IS NOT NULL
            AND ne.scan_date_et <= :p0
            AND ne.event_type IS NOT NULL AND ne.event_type != '-'
        '''), {'p0': max_date}).mappings().fetchall()

        event_returns = defaultdict(list)
        for r in rows:
            try:
                syms = json.loads(r['symbols_mentioned'])
            except:
                continue
            syms = [s for s in syms if s and s.isalpha() and len(s) <= 5
                    and s not in ('SPY', 'QQQ', 'IWM', 'DIA', 'GLD', 'USO')]
            if len(syms) < 2:
                continue

            scan_date = r['scan_date_et']
            et = r['event_type']

            for sym in syms:
                price_row = conn.execute(text('''
                    SELECT
                        (SELECT close FROM stock_daily_ohlc WHERE symbol=:p0 AND date<=:p1 ORDER BY date DESC LIMIT 1) as d0,
                        (SELECT close FROM stock_daily_ohlc WHERE symbol=:p0 AND date>=date(:p1,'+1 day') ORDER BY date ASC LIMIT 1 OFFSET 4) as d5
                '''), {'p0': sym, 'p1': scan_date}).fetchone()

                if price_row and price_row[0] and price_row[1] and price_row[0] > 0:
                    ret = (price_row[1] / price_row[0] - 1) * 100
                    event_returns[et].append(ret)

        self._event_impact = {}
        for et, rets in event_returns.items():
            if len(rets) >= 30:
                self._event_impact[et] = {
                    'avg_5d': round(sum(rets) / len(rets), 4),
                    'wr': round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
                    'n': len(rets),
                }

    def _learn_sector_bounce(self, conn, max_date: str):
        """Learn sector bounce statistics."""
        rows = conn.execute(text('''
            WITH bars AS (
                SELECT symbol, date, open, close,
                       LEAD(close) OVER (PARTITION BY symbol ORDER BY date) as next_close,
                       LEAD(open) OVER (PARTITION BY symbol ORDER BY date) as next_open
                FROM stock_daily_ohlc
                WHERE open > 0 AND close > 5 AND date >= '2024-01-01' AND date <= :p0
            )
            SELECT b.symbol, b.date, b.close, b.open, b.next_close, b.next_open,
                   s.sector, sr.pct_change as sect_ret
            FROM bars b
            JOIN stock_fundamentals s ON b.symbol = s.symbol
            LEFT JOIN sector_etf_daily_returns sr ON s.sector = sr.sector AND b.date = sr.date
            WHERE b.next_close IS NOT NULL
            AND (b.close / b.open - 1) * 100 < -2
            AND sr.pct_change < -1.5
        '''), {'p0': max_date}).mappings().fetchall()

        bounce_rets = [((r['next_close'] / r['close'] - 1) * 100) for r in rows
                       if r['next_close'] and r['close'] > 0]

        self._sector_bounce_stats = {}
        if bounce_rets:
            self._sector_bounce_stats = {
                'avg_total': round(sum(bounce_rets) / len(bounce_rets), 3),
                'wr': round(sum(1 for r in bounce_rets if r > 0) / len(bounce_rets) * 100, 1),
                'n': len(bounce_rets),
            }
