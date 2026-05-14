"""
ML Filter Strategy — ultra-strict ML-scored picks across the trading day.

This strategy runs any time 09:30-16:00. For each qualifying candidate,
it extracts features and scores with the ensemble bucket model, then
only returns picks whose probability exceeds the 75%-WR threshold
validated by backtest.

Expected performance (backtest walk-forward, 2025+ data):
  v3 (31 features, no AD hard gate, trail 3%):
  09:30-10:00  73% WR, avg +2.1%  — trail 3% full size
  10:00-10:45  SKIP — dip avg -4.2% > trail 3%, WR <55%
  10:45-11:30  64% WR, avg +1.5%  — top 50% prob, trail 3%
  11:30-13:00  SKIP — lunch dead zone, all EV negative
  13:00-14:00  69% WR, avg +1.0%  — trail 3%
  14:00-16:00  SKIP — WR <75%

3 active buckets: 09:30-10:00, 10:45-11:30, 13:00-14:00.
Exit: trailing stop 3% (acts as both SL and TP).
No AD hard gate — model uses ad_ratio as feature instead.
"""
import os
import sqlite3
import requests
import numpy as np
import pytz
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

from .base import BaseStrategy, ScanResult, Pick, ET
from ..ml_scorer import get_scorer
from ..alpaca_bars import fetch_today_bars, extract_multibar_features
from ..journal import get_journal

load_dotenv()


class MLFilterStrategy(BaseStrategy):
    name = "ml_filter"
    description = "Ensemble ML scoring — only picks where prob ≥ 75% threshold"
    expected_wr = 0.67  # realistic (24-month walk-forward + slippage + L1/L3 filters)
    expected_ev = 0.015
    time_start = "09:30"
    time_end = "13:00"
    version = "2.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 3.0
    MIN_GAIN = 2.0   # loose — let ML decide

    @staticmethod
    def _compute_multi_tf(bars, day_open):
        """v27: Multi-timeframe features (15m/30m/1h aggregates) from 5-min bars."""
        def _tf(window_bars, tag):
            if not window_bars or day_open <= 0:
                return {f'{tag}_gain': 0.0, f'{tag}_range': 0.0,
                        f'{tag}_vol_norm': 1.0, f'{tag}_green_pct': 0.0,
                        f'{tag}_high_break': 0.0}
            o = window_bars[0].get('o', 0); c = window_bars[-1].get('c', 0)
            hi = max(b.get('h', 0) for b in window_bars)
            lo = min(b.get('l', 9e9) for b in window_bars)
            vol = sum(b.get('v', 0) or 0 for b in window_bars)
            green = sum(1 for b in window_bars if b.get('c', 0) > b.get('o', 0))
            avg_bar_vol = vol / len(window_bars) if window_bars else 1
            first_bar_vol = window_bars[0].get('v', 1) or 1
            high_break = 1.0 if c >= hi - 0.001 else 0.0
            return {
                f'{tag}_gain': (c / o - 1) * 100 if o > 0 else 0.0,
                f'{tag}_range': (hi - lo) / day_open * 100,
                f'{tag}_vol_norm': min(20.0, avg_bar_vol / first_bar_vol) if first_bar_vol > 0 else 1.0,
                f'{tag}_green_pct': green / len(window_bars) if window_bars else 0.0,
                f'{tag}_high_break': high_break,
            }
        out = {}
        out.update(_tf(bars[-3:] if len(bars) >= 3 else bars, '15m'))
        out.update(_tf(bars[-6:] if len(bars) >= 6 else bars, '30m'))
        out.update(_tf(bars[-12:] if len(bars) >= 12 else bars, '1h'))
        return out

    # v24 hybrid sector strength rule (10:00 bucket): skip if stock's sector ETF down >0.3% intra
    _SECTOR_ETF = {
        'Technology': 'xlk_intra',
        'Healthcare': 'xlv_intra',
        'Health Care': 'xlv_intra',
        'Financial Services': 'xlf_intra',
        'Financials': 'xlf_intra',
        'Consumer Cyclical': 'xly_intra',
        'Communication Services': 'xlc_intra',
        'Industrials': 'xli_intra',
        'Consumer Defensive': 'xlp_intra',
        'Energy': 'xle_intra',
        'Basic Materials': 'xlb_intra',
        'Real Estate': 'xlre_intra',
        'Utilities': 'xlu_intra',
    }
    MAX_GAIN = 5.0   # gain ≥5% = chased/pumped — all strategies drop to 53-71% WR (2026-04-14 backtest)

    # 2026-04-30: skip Real Estate — uncalibrated (0 strict WF picks, expanded neg).
    # WELL fade case (live 2026-04-29) confirms: model generalized into REIT blind spot.
    # Consumer Defensive removed from blacklist — 1-yr WF showed 6/6 picks won (avg +2.23%);
    #   PM 2026-04-29 loss was variance, replacements only refill 3/6 slots at 67% WR.
    SECTOR_BLACKLIST = {'Real Estate'}

    REQUIRE_75_THRESHOLD = True
    MAX_PICKS = 1  # 2026-04-30: top-1 deployed (WF: 100% WR, +2.98% avg, +672%/yr)

    def scan(self) -> ScanResult:
        if not self.in_time_window():
            return self.out_of_window()

        scorer = get_scorer()
        now_et = datetime.now(ET)
        minutes_from_open = (now_et.hour - 9) * 60 + (now_et.minute - 30)

        # Pre-market defensive guard (in_time_window() already catches < 09:30)
        if minutes_from_open < 0:
            return self.out_of_window()

        bucket = scorer.get_bucket(minutes_from_open)

        if self.REQUIRE_75_THRESHOLD and not scorer.can_reach_75(minutes_from_open):
            return self.gate_failed(
                f"Bucket {bucket} cannot achieve 75% WR at any threshold. "
                f"Skip this window (use heuristic strategies or wait)."
            )

        threshold = scorer.threshold_75(minutes_from_open)

        conn = sqlite3.connect(self.DB_PATH)
        try:
            # AD ratio — passed to ML as feature (no hard gate; model handles regime)
            br = conn.execute("SELECT ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1").fetchone()
            ad_ratio = float(br[0]) if br and br[0] else 0.0

            spy_rows = conn.execute("SELECT spy_close FROM macro_snapshots WHERE spy_close IS NOT NULL ORDER BY date DESC LIMIT 50").fetchall()
            if len(spy_rows) < 2 or not spy_rows[0][0] or not spy_rows[1][0]:
                return self.gate_failed("No SPY data")
            spy_daily = (spy_rows[0][0] / spy_rows[1][0] - 1) * 100
            spy_green = 1 if spy_daily > 0 else 0

            # 2026-05-04: MoE soft regime weight (sigmoid based on SPY vs 50ma)
            # w_28m = 1 / (1 + exp(-(spy/spy_50ma - 1) * 50))
            # >0.5 = bull (favor 28m), <0.5 = bear (favor 49m)
            if len(spy_rows) >= 50:
                spy_50ma = sum(r[0] for r in spy_rows[:50] if r[0]) / 50
                spy_now = spy_rows[0][0]
                spy_vs_50ma = (spy_now / spy_50ma - 1) if spy_50ma > 0 else 0
                regime_weight = 1.0 / (1.0 + np.exp(-spy_vs_50ma * 50))  # sigmoid
            else:
                regime_weight = 1.0  # default: pure 28m if not enough data
            scorer.set_regime_weight(regime_weight)

            vix_row = conn.execute("SELECT vix_close FROM macro_snapshots WHERE vix_close IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone()
            vix = float(vix_row[0]) if vix_row and vix_row[0] else 20.0

            # OFFSET 5 = 5 trading days back (matches trainer's shift(5))
            vix_5d_row = conn.execute("SELECT vix_close FROM macro_snapshots WHERE vix_close IS NOT NULL ORDER BY date DESC LIMIT 1 OFFSET 5").fetchone()
            vix_5d_chg = (vix - float(vix_5d_row[0])) if vix_5d_row and vix_5d_row[0] else 0.0

            # v6 macro features: btc/jpy 5d change, skew, vvix, vix term spread
            macro_now = conn.execute("SELECT btc_close, usdjpy_close, skew_close, vvix_close, vix3m_close FROM macro_snapshots WHERE btc_close IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone()
            macro_5d = conn.execute("SELECT btc_close, usdjpy_close FROM macro_snapshots WHERE btc_close IS NOT NULL ORDER BY date DESC LIMIT 1 OFFSET 5").fetchone()
            if macro_now and macro_5d:
                btc_5d_chg = (macro_now[0] / macro_5d[0] - 1) * 100 if macro_now[0] and macro_5d[0] else 0
                jpy_5d_chg = (macro_now[1] / macro_5d[1] - 1) * 100 if macro_now[1] and macro_5d[1] else 0
                skew_v = float(macro_now[2]) if macro_now[2] else 145.0
                vvix_v = float(macro_now[3]) if macro_now[3] else 100.0
                vix_term_spread = (float(macro_now[4]) - vix) if macro_now[4] else 1.5
            else:
                btc_5d_chg = jpy_5d_chg = 0; skew_v = 145; vvix_v = 100; vix_term_spread = 1.5

            # Universe — exclude ETFs. Top 500 (expanded 2026-04-29 from 200).
            # Reason: catches stocks like AMKR/CNC/MOH that pumped +5-10% but were rank 400-500.
            # All 500 have current data + ≥1y history + 99.7% daily coverage.
            # 2026-05-05 BUG FIX: universe_stocks table is empty/legacy. Use universe_daily_snapshot.
            syms = [r[0] for r in conn.execute(
                """SELECT symbol FROM universe_daily_snapshot
                   WHERE date=(SELECT MAX(date) FROM universe_daily_snapshot)
                   AND sector != 'ETF' ORDER BY dollar_vol DESC LIMIT 500"""
            ).fetchall()]
            sectors = dict(conn.execute(
                """SELECT symbol, sector FROM universe_daily_snapshot
                   WHERE date=(SELECT MAX(date) FROM universe_daily_snapshot)"""
            ).fetchall())
            industries = dict(conn.execute("SELECT symbol, industry FROM stock_fundamentals WHERE industry IS NOT NULL").fetchall())
            betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())
            mcaps = dict(conn.execute("SELECT symbol, market_cap FROM stock_fundamentals WHERE market_cap IS NOT NULL").fetchall())
            earnings_skip = set(r[0] for r in conn.execute(
                "SELECT symbol FROM earnings_calendar WHERE next_earnings_date IN (date('now'), date('now','+1 day'))"
            ).fetchall())

            # Per-stock daily history for momentum/SMA/52w
            daily_hist = defaultdict(list)
            for r in conn.execute("""
                SELECT symbol, date, close FROM stock_daily_ohlc
                WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-300 days')
                ORDER BY symbol, date
            """):
                daily_hist[r[0]].append((r[1], r[2]))

            # 10-day range avg
            daily_hl = defaultdict(list)
            for r in conn.execute("""
                SELECT symbol, date, high, low, open FROM stock_daily_ohlc
                WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-15 days')
                ORDER BY symbol, date
            """):
                # tuple is (date, high, low, open)
                daily_hl[r[0]].append((r[1], r[2], r[3], r[4]))  # date,h,l,o

            # 30-day avg daily volume (for v21 canonical vol_ratio = today_so_far / (avg_daily * frac_elapsed))
            avg_daily_vol = {}
            for r in conn.execute("""
                SELECT symbol, AVG(volume) FROM stock_daily_ohlc
                WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-30 days')
                AND volume IS NOT NULL AND volume > 0
                GROUP BY symbol
            """):
                avg_daily_vol[r[0]] = float(r[1]) if r[1] else 0.0

            # NOTE: 6 features were dropped from v22 model (sec3d, insider_net_30d,
            # news_sentiment, earnings_days, pm_vol_ratio, short_pct). Their SQL
            # queries were removed — they were always 0 in pkl, model never used them.
        finally:
            conn.close()

        # 2026-05-07 v2: TRUE FIX — single source of truth (1-min bars only).
        # Replaces snapshot fetch + override workaround.
        # Snapshot endpoint had 30-60s lag → caused FFIV-style bad picks.
        # 1-min bar endpoint is fresh + tick-accurate.
        # Benefits: 50% fewer API calls, 1-2s faster scan, cleaner architecture.
        # Cost: rewrote ~80 lines into ~50 lines.
        hdr = {
            'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'),
            'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY'),
        }
        from concurrent.futures import ThreadPoolExecutor

        etf_syms = ['SPY', 'IWM', 'USO', 'XLK', 'XLV', 'XLF', 'XLY', 'XLC', 'XLI',
                    'XLP', 'XLE', 'XLB', 'XLRE', 'XLU', 'SMH']

        today_str = now_et.strftime('%Y-%m-%d')
        market_open_iso = ET.localize(datetime.strptime(f'{today_str} 09:30:00',
            '%Y-%m-%d %H:%M:%S')).astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
        now_utc_iso = now_et.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')

        def _fetch_bars(symbols_csv):
            """Fetch 1-min bars from market open to NOW (real-time)."""
            try:
                params = {'symbols': symbols_csv, 'timeframe': '1Min',
                          'start': market_open_iso, 'end': now_utc_iso,
                          'limit': 10000, 'feed': 'sip'}
                r = requests.get('https://data.alpaca.markets/v2/stocks/bars',
                                 headers=hdr, params=params, timeout=15)
                if r.status_code == 403:
                    params['feed'] = 'iex'
                    r = requests.get('https://data.alpaca.markets/v2/stocks/bars',
                                     headers=hdr, params=params, timeout=15)
                if r.status_code == 200:
                    return r.json().get('bars', {})
            except Exception:
                pass
            return {}

        # Get prev_close from DB (single query)
        conn = sqlite3.connect(self.DB_PATH)
        try:
            prev_closes = dict(conn.execute(
                "SELECT symbol, close FROM stock_daily_ohlc "
                "WHERE date = (SELECT MAX(date) FROM stock_daily_ohlc)").fetchall())
        finally:
            conn.close()

        # Parallel 1-min bar fetch (5 batches × 100 stocks + ETF batch)
        stock_batches = [','.join(syms[i:i+100]) for i in range(0, len(syms), 100)]
        all_batches = stock_batches + [','.join(etf_syms)]
        all_bars = {}
        with ThreadPoolExecutor(max_workers=len(all_batches)) as ex:
            for batch_bars in ex.map(_fetch_bars, all_batches):
                all_bars.update(batch_bars)

        # Wait+retry if first scan within 90s (1-min bar 09:30 not settled yet)
        etf_with_bars = sum(1 for s in etf_syms if all_bars.get(s))
        if etf_with_bars == 0 and minutes_from_open == 0:
            import time as _time
            market_open_local = ET.localize(datetime.strptime(f'{today_str} 09:30:00', '%Y-%m-%d %H:%M:%S'))
            seconds_in = (now_et - market_open_local).total_seconds()
            if seconds_in < 90:
                wait_sec = max(0, 70 - seconds_in)
                if wait_sec > 0:
                    print(f"[ml_filter] Waiting {wait_sec:.0f}s for bar 09:30 to complete...")
                    _time.sleep(wait_sec)
                now_utc_iso = datetime.now(ET).astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
                all_bars = {}
                with ThreadPoolExecutor(max_workers=len(all_batches)) as ex:
                    for batch_bars in ex.map(_fetch_bars, all_batches):
                        all_bars.update(batch_bars)
                etf_with_bars = sum(1 for s in etf_syms if all_bars.get(s))

        if etf_with_bars == 0:
            return self.gate_failed(
                "Market data not ready — no 1-min bars available yet. "
                "Wait until next scan cycle.")

        # Build snapshot-equivalent from 1-min bars (single source of truth)
        def _build_snap(sym, bars):
            if not bars: return None
            opens = [b['o'] for b in bars]
            highs = [b['h'] for b in bars]
            lows = [b['l'] for b in bars]
            closes = [b['c'] for b in bars]
            vols = [b['v'] for b in bars]
            vws = [b.get('vw', b['c']) for b in bars]
            tot_vol = sum(vols) or 1
            vwap_today = sum(v*p for v, p in zip(vols, vws)) / tot_vol
            return {
                'dailyBar': {'o': opens[0], 'h': max(highs), 'l': min(lows),
                             'c': closes[-1], 'v': sum(vols), 'vw': vwap_today,
                             't': bars[0]['t']},
                'prevDailyBar': {'c': prev_closes.get(sym, 0)},
            }

        snaps = {sym: _build_snap(sym, all_bars.get(sym, [])) for sym in syms}
        snaps = {k: v for k, v in snaps.items() if v is not None}
        etf_snaps = {sym: _build_snap(sym, all_bars.get(sym, [])) for sym in etf_syms}
        etf_snaps = {k: v for k, v in etf_snaps.items() if v is not None}

        # Dump snapshots for retrospective sim — self-contained replay.
        # Per-scan: snaps + etf_snaps + DB state used. Per-day: daily history (separate file).
        # Storage: ~80 KB/scan × 42 scans + ~3 MB/day = ~140 MB/month, ~1.7 GB/year.
        try:
            import gzip, json
            snap_dir = Path(self.DB_PATH).parent / 'scan_snapshots'
            snap_dir.mkdir(exist_ok=True)

            # Read model version (mtime of zone Z1 model)
            from ..ml_scorer import V22_DIR as _V22
            import datetime as _dt
            try:
                model_mtime = (_V22 / 'lgb_tp1_Z1_seed0.txt').stat().st_mtime
                model_version = _dt.datetime.fromtimestamp(model_mtime).strftime('%Y-%m-%d_%H-%M')
            except Exception:
                model_version = 'unknown'

            ts_str = now_et.strftime('%Y-%m-%d_%H-%M-%S')
            payload = {
                'scan_ts_et': now_et.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'minutes_from_open': minutes_from_open,
                'bucket': bucket,
                'threshold': threshold,
                'model_version': model_version,
                'sector_blacklist': sorted(self.SECTOR_BLACKLIST),
                'snaps': snaps,
                'etf_snaps': etf_snaps,
                # DB-derived state (captured at scan time)
                'sectors': sectors,
                'betas': betas,
                'mcaps': mcaps,
                'industries': industries,
                'earnings_skip': sorted(earnings_skip),
                'macro': {
                    'spy_green': spy_green, 'spy_daily': spy_daily,
                    'vix': vix, 'vix_5d_chg': vix_5d_chg,
                    'btc_5d_chg': btc_5d_chg, 'jpy_5d_chg': jpy_5d_chg,
                    'skew': skew_v, 'vvix': vvix_v,
                    'vix_term_spread': vix_term_spread, 'ad_ratio': ad_ratio,
                },
            }
            with gzip.open(snap_dir / f'{ts_str}.json.gz', 'wt') as f:
                json.dump(payload, f)

            # Per-day DB state (daily_hist, daily_hl, avg_daily_vol) — written once per day
            day_str = now_et.strftime('%Y-%m-%d')
            day_state_path = snap_dir / f'db_state_{day_str}.json.gz'
            if not day_state_path.exists():
                day_payload = {
                    'date': day_str,
                    # Convert defaultdict to dict for JSON
                    'daily_hist': {k: v for k, v in daily_hist.items()},
                    'daily_hl': {k: v for k, v in daily_hl.items()},
                    'avg_daily_vol': avg_daily_vol,
                }
                with gzip.open(day_state_path, 'wt') as f:
                    json.dump(day_payload, f)
        except Exception:
            pass  # non-fatal — sim is nice-to-have, scan continues

        def etf_intraday(sym):
            s = etf_snaps.get(sym, {})
            db = s.get('dailyBar', {})
            o = db.get('o', 0); c = db.get('c', 0)
            return (c / o - 1) * 100 if o > 0 else 0

        spy_intra = etf_intraday('SPY')
        iwm_intra = etf_intraday('IWM')
        uso_intra = etf_intraday('USO')

        # Sector ETF intraday changes
        sector_to_etf = {
            'Technology': 'XLK', 'Healthcare': 'XLV', 'Health Care': 'XLV',
            'Financial Services': 'XLF', 'Financials': 'XLF',
            'Consumer Cyclical': 'XLY', 'Communication Services': 'XLC',
            'Industrials': 'XLI', 'Consumer Defensive': 'XLP',
            'Energy': 'XLE', 'Basic Materials': 'XLB',
            'Real Estate': 'XLRE', 'Utilities': 'XLU',
        }
        sector_chg = {sec: etf_intraday(etf) for sec, etf in sector_to_etf.items()}

        # Anomaly score: multi-asset z-score (from 2021-2026 baseline)
        # Replaces USO+IWM hardcoded rule — ML handles regime via features
        ETF_BASELINES = {
            'USO': (-0.02, 0.61), 'VXX': (0.04, 1.74), 'IWM': (-0.01, 0.59),
            'SPY': (-0.19, 0.52), 'XLE': (0.04, 0.85), 'XLK': (0.01, 0.58),
            'GLD': (-0.01, 0.32), 'TLT': (-0.00, 0.31),
        }
        z_scores = []
        for sym, (mean, std) in ETF_BASELINES.items():
            chg = etf_intraday(sym)
            z = abs((chg - mean) / (std + 0.01))
            z_scores.append(z)
        anomaly_score = np.sqrt(sum(z**2 for z in z_scores)) / np.sqrt(len(z_scores)) if z_scores else 0

        # Pre-filter: stocks with gain in range (to reduce bar fetch calls)
        pre_qualified = []
        for sym in syms:
            if sym in earnings_skip or sym == 'SPY': continue
            s = snaps.get(sym)
            if not s: continue
            db = s.get('dailyBar', {})
            pb = s.get('prevDailyBar', {})
            now = db.get('c', 0)
            prev_c = pb.get('c', 0)
            if now < self.MIN_PRICE or prev_c < 1: continue
            # Filter from PREV CLOSE (total move including overnight gap)
            # Backtest 24mo: equivalent WR (67.7 vs 67.4), -23% picks = less overtrading
            total_gain = (now / prev_c - 1) * 100
            if self.MIN_GAIN <= total_gain < self.MAX_GAIN:
                pre_qualified.append(sym)

        # Fetch today's 5-min bars for pre-qualified symbols (for multi-bar features)
        bars_by_sym = {}
        if pre_qualified:
            try:
                bars_by_sym = fetch_today_bars(pre_qualified[:100])
            except Exception:
                bars_by_sym = {}

        # Append bars_by_sym to most recent snapshot (for replay multibar features)
        try:
            import gzip, json
            snap_dir = Path(self.DB_PATH).parent / 'scan_snapshots'
            ts_str = now_et.strftime('%Y-%m-%d_%H-%M-%S')
            snap_path = snap_dir / f'{ts_str}.json.gz'
            if snap_path.exists():
                with gzip.open(snap_path, 'rt') as f:
                    payload = json.load(f)
                payload['bars_by_sym'] = bars_by_sym
                payload['pre_qualified'] = pre_qualified
                with gzip.open(snap_path, 'wt') as f:
                    json.dump(payload, f)
        except Exception:
            pass

        dow = now_et.weekday()
        candidates = []

        for sym in syms:
            if sym in earnings_skip: continue
            if sym == 'SPY': continue
            s = snaps.get(sym)
            if not s: continue
            db = s.get('dailyBar', {})
            pb = s.get('prevDailyBar', {})
            opn = db.get('o', 0); now = db.get('c', 0)
            hi = db.get('h', 0); lo = db.get('l', 0)
            prev_c = pb.get('c', 0)
            if opn < 1 or now < self.MIN_PRICE or prev_c < 1:
                continue

            # Filter from PREV CLOSE (matches pre_qualify filter above)
            total_gain = (now / prev_c - 1) * 100
            if not (self.MIN_GAIN <= total_gain < self.MAX_GAIN):
                continue
            gain = (now / opn - 1) * 100  # keep for model feature

            # Build feature vector matching training
            range_pct = (hi - lo) / opn * 100 if opn > 0 else 0
            from_peak_pct = (now / hi - 1) * 100 if hi > 0 else 0
            vwap = db.get('vw', 0)
            vs_vwap = (now / vwap - 1) * 100 if vwap > 0 else 0
            # v21 canonical vol_ratio: today_so_far / (30d_avg_daily * fraction_of_day_elapsed).
            # No lookahead. today_so_far = dailyBar.v (cumulative volume up to current bar).
            today_vol = db.get('v', 0) or 0
            avg_daily = avg_daily_vol.get(sym, 0)
            fraction_elapsed = max(5, minutes_from_open + 5) / 390.0  # mfo=0 means 5 min elapsed
            expected = avg_daily * fraction_elapsed if avg_daily > 0 else 0
            vol_ratio = min(20.0, today_vol / expected) if expected > 0 else 1.0
            gap_from_prev = (opn / prev_c - 1) * 100

            beta = betas.get(sym, 1.5)
            mcap = mcaps.get(sym, 0) or 0
            mcap_bucket = 4 if mcap >= 100e9 else (3 if mcap >= 20e9 else (2 if mcap >= 5e9 else (1 if mcap >= 500e6 else 0)))

            # Momentum from daily history
            hist = daily_hist.get(sym, [])
            if len(hist) < 21: continue
            closes = [h[1] for h in hist[-21:] if h[1] is not None]
            if len(closes) < 21: continue
            mom5 = (closes[-1] / closes[-6] - 1) * 100 if closes[-6] else 0
            mom20 = (closes[-1] / closes[0] - 1) * 100 if closes[0] else 0
            sma20 = np.mean(closes[-20:])
            dist_sma20 = (now / sma20 - 1) * 100 if sma20 > 0 else 0

            # 52w high/low from history
            hist_full = daily_hist.get(sym, [])
            closes_full = [h[1] for h in hist_full if h[1] is not None] if len(hist_full) >= 100 else []
            if len(closes_full) >= 100:
                h52w = max(closes_full)
                l52w = min(closes_full)
                pct_52w_hi = (now / h52w - 1) * 100 if h52w > 0 else 0
                pct_52w_lo = (now / l52w - 1) * 100 if l52w > 0 else 0
            else:
                pct_52w_hi = 0
                pct_52w_lo = 0

            # 2026-05-13: 16 new features (Step 2 of methodology)
            # Daily-derived (8): SMA20/50, 52w extremes + staleness, RSI, ATR
            if len(closes_full) >= 50:
                sma50_d = float(np.mean(closes_full[-50:]))
                feat_dist_sma20_d = (now / sma20 - 1) * 100 if sma20 > 0 else 0
                feat_dist_sma50_d = (now / sma50_d - 1) * 100 if sma50_d > 0 else 0
            else:
                feat_dist_sma20_d = feat_dist_sma50_d = 0
            # Days since 52w hi/lo (from closes_full, recent window)
            if len(closes_full) >= 252:
                window = closes_full[-252:]
                idx_hi = int(np.argmax(window))
                idx_lo = int(np.argmin(window))
                feat_days_since_hi52w = (len(window) - 1) - idx_hi
                feat_days_since_lo52w = (len(window) - 1) - idx_lo
            else:
                feat_days_since_hi52w = feat_days_since_lo52w = 0
            # RSI 14-day from closes
            if len(closes_full) >= 15:
                deltas = np.diff(closes_full[-15:])
                gains_rsi = np.where(deltas > 0, deltas, 0).mean()
                losses_rsi = np.where(deltas < 0, -deltas, 0).mean()
                if losses_rsi > 0:
                    rs_v = gains_rsi / losses_rsi
                    feat_rsi_14d = 100 - 100/(1+rs_v)
                else:
                    feat_rsi_14d = 100
            else:
                feat_rsi_14d = 50
            # ATR 14-day pct (using daily_hl)
            hl_list = daily_hl.get(sym, [])
            if len(hl_list) >= 15 and now > 0:
                trs = []
                for i in range(len(hl_list)-14, len(hl_list)):
                    if i > 0:
                        h_t, l_t = hl_list[i][1], hl_list[i][2]
                        c_prev = hl_list[i-1][1]  # Use prev high as approx prev close
                        if h_t is not None and l_t is not None and c_prev is not None:
                            tr = max(h_t-l_t, abs(h_t-c_prev), abs(l_t-c_prev))
                            trs.append(tr)
                feat_atr_pct_14d = (float(np.mean(trs)) / now * 100) if trs else 1.0
            else:
                feat_atr_pct_14d = 1.0
            # Intraday-derived (8)
            mfo_safe = max(1, minutes_from_open)
            feat_velocity = gain / mfo_safe
            feat_range_x_velocity = range_pct * abs(feat_velocity)
            feat_vol_gain_div = vol_ratio / (abs(gain) + 1)
            feat_intraday_rsi = (max(-10, min(10, gain)) + 10) * 5
            feat_mom_x_vol = mom20 * vol_ratio
            # sector ETFs avg (computed below at line ~603+)
            sec_etfs_for_avg = [etf_intraday(e) for e in ['XLB','XLC','XLE','XLF','XLI','XLK','XLP','XLRE','XLU','XLV','XLY','SMH','QQQ','IWM','DBC','EEM','GLD','HYG','IGV','IEF','LQD','TLT','USO','UUP','VXX']]
            feat_sec_avg_intra = float(np.mean(sec_etfs_for_avg)) if sec_etfs_for_avg else 0
            feat_stock_vs_sec = gain - feat_sec_avg_intra
            feat_combined_momentum = feat_rsi_14d * 0.5 + feat_intraday_rsi * 0.5

            # 10-day range
            hl_hist = daily_hl.get(sym, [])
            # entries: (date, high, low, open)
            ranges = []
            for row in hl_hist:
                if len(row) == 4 and row[3] and row[3] > 0:
                    ranges.append((row[1] - row[2]) / row[3] * 100)
            rng10 = np.mean(ranges) if ranges else 3.0
            range_exp = range_pct / rng10 if rng10 > 0 else 1

            sec = sectors.get(sym, '')
            if sec in self.SECTOR_BLACKLIST:
                continue
            # sec3d dropped from v22 (always 0 in trainer) — sec_rel_strength uses 0 implicitly.

            # Live multi-bar features from Alpaca 5-min bars
            sym_bars = bars_by_sym.get(sym, [])
            if sym_bars:
                day_open = sym_bars[0].get('o', opn)
                bar_feats = extract_multibar_features(sym_bars, day_open)
            else:
                day_open = opn
                bar_feats = {
                    'bars_since_hi': 0, 'vol_accel': 1.0, 'hh_count': 0,
                    'consol': range_pct, 'consec_green': 0,
                    'pullback_depth': 0, 'slope_5': 0, 'slope_10': 0,
                    'gain_first30': 0, 'entry_vs_first30': 0, 'time_since_peak': 0,
                }

            features = {
                'mins_from_open': minutes_from_open,
                'gain_from_open': gain,
                'range_pct': range_pct,
                'from_peak_pct': from_peak_pct,
                'vs_vwap': vs_vwap,
                'vol_ratio': vol_ratio,
                'vol_accel': bar_feats.get('vol_accel', 1.0),
                'bars_since_hi': bar_feats.get('bars_since_hi', 0),
                'hh_count': bar_feats.get('hh_count', 0),
                'consol': bar_feats.get('consol', range_pct),
                'range_exp': range_exp,
                'gap_from_prev': gap_from_prev,
                'beta': beta,
                'mcap_bucket': mcap_bucket,
                'spy_green': spy_green,
                'spy_intra': spy_intra,
                'vix': vix,
                'vix_5d_chg': vix_5d_chg,
                'ad_ratio': ad_ratio,
                'mom5d': mom5,
                'mom20d': mom20,
                'dist_sma20': dist_sma20,
                'pct_52w_hi': pct_52w_hi,
                'pct_52w_lo': pct_52w_lo,
                'dow': dow,
                # v6 macro features
                'btc_5d_chg': btc_5d_chg,
                'jpy_5d_chg': jpy_5d_chg,
                'skew': skew_v,
                'vvix': vvix_v,
                'vix_term_spread': vix_term_spread,
                'sec_rel_strength': max(-20, min(20, gain)),  # sec3d=0 implicit
                # v27: multi-timeframe features (used by 10:00 + 11:30 models)
                **self._compute_multi_tf(sym_bars, opn),
                # Cross-asset intraday features (v22 model uses 25 of these)
                'spy_intra': spy_intra,
                'qqq_intra': etf_intraday('QQQ'),
                'iwm_intra': iwm_intra,
                'uso_intra': uso_intra,
                'vxx_intra': etf_intraday('VXX'),
                'gld_intra': etf_intraday('GLD'),
                'hyg_intra': etf_intraday('HYG'),
                'tlt_intra': etf_intraday('TLT'),
                'smh_intra': etf_intraday('SMH'),
                # Sector ETFs (added for v20 09:30 model)
                'xlb_intra': etf_intraday('XLB'),
                'xlc_intra': etf_intraday('XLC'),
                'xle_intra': etf_intraday('XLE'),
                'xlf_intra': etf_intraday('XLF'),
                'xli_intra': etf_intraday('XLI'),
                'xlk_intra': etf_intraday('XLK'),
                'xlp_intra': etf_intraday('XLP'),
                'xlre_intra': etf_intraday('XLRE'),
                'xlu_intra': etf_intraday('XLU'),
                'xlv_intra': etf_intraday('XLV'),
                'xly_intra': etf_intraday('XLY'),
                # Other cross-asset (added for v20 09:30 model)
                'dbc_intra': etf_intraday('DBC'),
                'eem_intra': etf_intraday('EEM'),
                'igv_intra': etf_intraday('IGV'),
                'ief_intra': etf_intraday('IEF'),
                'lqd_intra': etf_intraday('LQD'),
                'uup_intra': etf_intraday('UUP'),
                'iwm_spy_spread': iwm_intra - spy_intra,
                'xlk_spy_spread': etf_intraday('XLK') - spy_intra,
                'uso_iwm_combo': uso_intra * (1.0 if (iwm_intra - spy_intra) < -0.3 else 0.0),
                'vxx_spy_combo': etf_intraday('VXX') * (1.0 if spy_intra < 0 else 0.0),
                'anomaly_score': anomaly_score,
                # Quality interactions (used by v20.1 09:30 model only — late buckets ignore)
                'gain_x_spy': gain * spy_intra,
                'vol_x_mcap': vol_ratio * mcap_bucket,
                'gain_x_xlk': gain * etf_intraday('XLK'),
                'gain_div_vix': gain / (vix / 20.0) if vix > 0 else 0.0,
                'range_pullback': range_pct * (5 - max(0, min(5, gain))),
                # 2026-05-12: Spike-fade features (Iter 2 for Z1)
                # Computed from 09:30 5-min bar OHLC (day_open, hi, lo, current_close)
                'range_930_pct': ((hi - lo) / day_open * 100) if (day_open > 0 and hi > lo) else 0.0,
                'wick_top_pct': ((hi - max(day_open, now)) / (hi - lo)) if (hi > lo) else 0.0,
                'wick_bot_pct': ((min(day_open, now) - lo) / (hi - lo)) if (hi > lo) else 0.0,
                'body_pct': (abs(now - day_open) / (hi - lo)) if (hi > lo) else 0.0,
                'pos_in_range': ((now - lo) / (hi - lo)) if (hi > lo) else 0.5,
                'gain_from_low_930': ((now / lo - 1) * 100) if lo > 0 else 0.0,
                # 2026-05-13: 16 new features (Step 2 ML methodology)
                'feat_dist_sma20_d': feat_dist_sma20_d,
                'feat_dist_sma50_d': feat_dist_sma50_d,
                'feat_pct_from_hi52w': pct_52w_hi,
                'feat_pct_from_lo52w': pct_52w_lo,
                'feat_days_since_hi52w': feat_days_since_hi52w,
                'feat_days_since_lo52w': feat_days_since_lo52w,
                'feat_rsi_14d': feat_rsi_14d,
                'feat_atr_pct_14d': feat_atr_pct_14d,
                'feat_velocity': feat_velocity,
                'feat_range_x_velocity': feat_range_x_velocity,
                'feat_vol_gain_div': feat_vol_gain_div,
                'feat_intraday_rsi': feat_intraday_rsi,
                'feat_mom_x_vol': feat_mom_x_vol,
                'feat_sec_avg_intra': feat_sec_avg_intra,
                'feat_stock_vs_sec': feat_stock_vs_sec,
                'feat_combined_momentum': feat_combined_momentum,
            }

            prob = scorer.score(features, minutes_from_open, sector=sec)

            if self.REQUIRE_75_THRESHOLD and prob < threshold:
                continue

            # v24 hybrid: per-bucket hard rules (validated +0.6 to +1.9pp WR).
            # Rules apply ON TOP of ML score — gives ML candidates that the
            # model couldn't filter due to depth=3 trees missing 3+ way interactions.
            mfo = minutes_from_open
            if mfo < 30:
                # 09:30 — anti-extreme: skip if mom20 > 20 (overextended)
                if features.get('mom20d', 0) > 20:
                    continue
            elif mfo < 75:
                # 10:00 — sector strength: skip if stock's sector ETF down >0.3%
                sec_etf_col = self._SECTOR_ETF.get(sec)
                if sec_etf_col and features.get(sec_etf_col, 0) < -0.3:
                    continue
            elif mfo < 120:
                # 10:45 — anti-extreme: skip if mom20 > 20
                if features.get('mom20d', 0) > 20:
                    continue
            # 11:30+ : no rule (validated rules don't help this bucket)

            atr_pct = (hi - lo) / now * 100 if now > 0 else 3.0
            # 2026-05-14: Step 12 per-zone ATR-adaptive buffer.
            # buffer = base_buf + atr_coef × atr_pct_14d (daily ATR)
            # WF: Combined +662%/6mo (vs Step 10 +588%, +13% improvement).
            pred_ratio = scorer.predict_adaptive_limit_ratio(features, minutes_from_open, sector=sec)
            zone_name = scorer.get_zone(minutes_from_open) if scorer.USE_ZONES else None
            zone_cfg = getattr(scorer, 'ZONE_LIMIT_CONFIG', {}).get(zone_name)
            if zone_cfg:
                atr_14d = features.get('feat_atr_pct_14d', 3.0)
                buf = zone_cfg['base_buf'] + zone_cfg['atr_coef'] * atr_14d
            else:
                buf = getattr(scorer, 'ADAPTIVE_LIMIT_BUFFER', 0.010)  # fallback
            adaptive_limit = now * pred_ratio * (1 + buf)
            # Z4 dip filter
            if zone_name == 'Z4':
                min_dip = getattr(scorer, 'Z4_DIP_FILTER', 0.005)
                if (1 - pred_ratio) < min_dip:
                    continue  # skip Z4 pick if predicted dip too small

            is_eod = True  # all zones now use EOD strategy
            if is_eod:
                # Pure hold to EOD — no SL, no trail, no lock for Z1/Z2/Z3
                # Z4 exception (Step 17): Hard SL = ZONE_HARD_SL['Z4'] from limit_price
                # WF: caps worst trade from -4.68% → -3.10% (Z4 RIVN 2025-12-12 case)
                trail = 0
                # 2026-05-14: Use adaptive limit (ML-predicted) instead of 09:30 open
                limit_price = adaptive_limit
                zone_sl_pct = getattr(scorer, 'ZONE_HARD_SL', {}).get(zone_name)
                if zone_sl_pct:
                    sl_price = limit_price * (1 - zone_sl_pct)
                    sl_tag = f"hardSL@{-zone_sl_pct*100:.1f}%"
                else:
                    sl_price = 0  # disabled (pure hold)
                    sl_tag = "no SL"
                reason = (
                    f"ML p={prob:.3f} adapt_lim={pred_ratio:.4f} (dip {(1-pred_ratio)*100:.2f}%) "
                    f"gain+{gain:.1f}% β{beta:.1f} {sec[:6]} "
                    f"LIMIT@${day_open:.2f} pure-hold-EOD ({sl_tag})"
                )
            else:
                # Legacy for Z2/Z3/Z4 until retrained
                base_trail = 5.0 if gain >= 2.0 else 2.5
                if features.get('mcap_bucket', 0) == 2:
                    base_trail = max(base_trail, 4.0)
                if features.get('vix', 18) >= 25:
                    base_trail = max(base_trail, 4.0)
                if beta >= 1.5:
                    base_trail = max(base_trail, 4.0)
                trail = round(min(7.0, max(2.5, base_trail)), 1)
                HARD_SL_PCT = 2.0
                LOCK_TRIGGER_PCT = 2.0
                LOCK_AT_PCT = 0.5
                trail_sl = now * (1 - trail / 100)
                hard_sl = now * (1 - HARD_SL_PCT / 100)
                sl_price = max(trail_sl, hard_sl)
                limit_price = now
                reason = (
                    f"ML p={prob:.3f} thr={threshold:.2f} "
                    f"gain+{gain:.1f}% β{beta:.1f} {sec[:6]} "
                    f"trail{trail}%+hardSL{HARD_SL_PCT}%+lock@+{LOCK_TRIGGER_PCT}%/+{LOCK_AT_PCT}%"
                )

            extra_dict = {
                'ml_prob': round(prob, 4),
                'threshold': round(threshold, 4),
                'bucket': bucket,
                'gain_pct': round(gain, 2),
                'beta': round(beta, 2),
                'sector': sec,
                'limit_price': round(limit_price, 2),
                'exit_strategy': 'pure_hold_eod',
            }

            candidates.append(Pick(
                symbol=sym, entry=limit_price,
                sl_price=round(sl_price, 2) if sl_price else None,
                tp_price=None,
                trail_pct=trail,
                reason=reason,
                score=int(prob * 10),
                atr_pct=atr_pct,
                extra=extra_dict,
            ))

        if not candidates:
            return self.no_picks(
                f"No picks ≥ threshold {threshold:.2f} "
                f"(bucket {scorer.get_bucket(minutes_from_open)})"
            )

        # 2026-05-05: U coef 0.05 → 0.10 (joint validation, +1% total, plateau 0.07-0.15).
        # 2026-05-01: Reverted to U formula ranking + Top-1 after fixing stale data bug.
        # WF: WR 100% (12/12 months), avg +3.06%, +$790/yr — best of all tested.
        # U formula = ml_prob + 0.10×gain_from_open (favor high confidence + intraday momentum).
        # Stale data bug fixed: ETF data now refreshed via 1-min bars at market open.
        candidates.sort(key=lambda p: -(p.extra['ml_prob'] + 0.10 * p.extra.get('gain_pct', 0)))

        # Cross-scan dedup: skip symbols picked in last 60 min (prevent double-entry)
        try:
            from pathlib import Path as _Path
            j_db = _Path(__file__).resolve().parents[3] / 'data' / 'scan_journal.db'
            _conn = sqlite3.connect(str(j_db))
            recent_syms = set(r[0] for r in _conn.execute(
                "SELECT symbol FROM scan_picks WHERE scan_ts >= datetime('now', '-60 minutes')"
            ).fetchall())
            _conn.close()
        except Exception:
            recent_syms = set()

        # Sector diversification (max 2/sector) — only structural filter
        sec_count = {}
        picks = []
        for c in candidates:
            if c.symbol in recent_syms:
                continue
            sec = c.extra['sector']
            if sec_count.get(sec, 0) >= 2:
                continue
            sec_count[sec] = sec_count.get(sec, 0) + 1
            picks.append(c)
            if len(picks) >= self.MAX_PICKS:
                break

        bucket = scorer.get_bucket(minutes_from_open)
        # Original v16 validated WR — keep for journal drift monitoring
        WR_BY_BUCKET = {
            '09:30-10:00': 88,
            '10:00-10:45': 80,
            '10:45-11:30': 79,
            '11:30-13:00': 81,
        }
        expected_wr = WR_BY_BUCKET.get(bucket, 80)

        # Record picks to journal for drift monitoring
        try:
            journal = get_journal()
            for p in picks:
                journal.record_pick(
                    strategy=self.name, bucket=bucket, symbol=p.symbol,
                    entry=p.entry, sl_price=p.sl_price, tp_price=p.tp_price,
                    trail_pct=p.trail_pct,
                    ml_prob=p.extra.get('ml_prob'),
                    ml_threshold=p.extra.get('threshold'),
                    expected_wr=expected_wr / 100,
                    reason=p.reason,
                    features=p.extra,
                )
        except Exception:
            pass

        regime_str = f"SPY{spy_daily:+.1f}% AD{ad_ratio:.1f} VIX{vix:.0f} anom{anomaly_score:.1f}"

        reason = f"{len(candidates)} ML-passing → top {len(picks)} (expected WR ~{expected_wr:.0f}%)"

        return ScanResult(
            strategy=self.name,
            timestamp_et=self.time_et_str(),
            status='active',
            reason=reason,
            picks=picks,
            regime=regime_str,
            metadata={
                'bucket': bucket,
                'threshold_75': threshold,
                'expected_wr': expected_wr,
                'model_version': 'v22',
                'anomaly_score': round(anomaly_score, 2),
            },
        )
