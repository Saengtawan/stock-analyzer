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

    # 2026-05-30: MARKET entry — enter at current scan price (`now`), 100% fill.
    # WF (6mo, thr 0.75): MARKET beats adaptive-LIMIT on every zone up to ~0.40-0.50%
    # slippage (ALL +3630% vs +2663%); limit discarded 173 runaway winners (99% WR).
    # Reversible: set False to restore adaptive-limit (dip-wait) entry.
    MARKET_ENTRY = True

    # 2026-05-30: per-zone max buy price = `now` × (1 + budget). Display-only — the
    # slippage ceiling beyond which the WF MARKET edge erodes vs LIMIT (wf_slip).
    # Z1/Z2/Z3 still beat limit on total even at 0.50%; Z4 breakeven ~0.40% (fragile).
    ZONE_SLIP_BUDGET = {'Z1': 0.005, 'Z2': 0.005, 'Z3': 0.005, 'Z4': 0.004}

    def scan(self) -> ScanResult:
        if not self.in_time_window():
            return self.out_of_window()

        scorer = get_scorer()

        # 2026-06-07: H12-A multi-model opt-in via env flag (default: production unchanged).
        # Set ML_FILTER_VARIANT=h12a → swap to per-(zone,sector) V-2/V-C models +
        # cell filter (S2 Z1, S7 Z2/Z3, none Z4) + regime gates (VIX<20 Z1, vix_5d<0 Z2,
        # sec>0+¬Fri Z3, Option E* Z4). Default unset → existing single-zone behavior.
        # Spec: backtests/research/H12A_FINAL_spec.md
        # 2026-06-07: H12-B = H12-A + AD-conditional WIN_THR on Z1/Z3 only.
        #   AD>1.5 → 0.68 (broad rally, lower bar) ; AD<0.7 → 0.80 (thin tape, raise bar)
        #   else 0.75. Z2/Z4 keep base 0.75. WF 2yr: +27pp total vs H12-A, Sharpe 3.3,
        #   7/9 quarters win, same worst-day. AD is mechanistic (winner base-rate rises
        #   with breadth) + beats SPY/VIX conditioning + adds selection beyond flat-lower.
        #   Spec: backtests/research/H12B_FINAL_spec.md. Disable: set ML_FILTER_VARIANT=h12a.
        import os as _os_h12a
        _h12_variant = _os_h12a.environ.get('ML_FILTER_VARIANT', '')
        h12a_enabled = _h12_variant in ('h12a', 'h12b')
        h12b_ad_cond = _h12_variant == 'h12b'
        h12a_scorer = None
        if h12a_enabled:
            try:
                from ..ml_scorer_h12a import get_scorer_h12a as _get_h12a
                from ..h12a_picker import score_and_filter_h12a as _h12a_score_filter
                from ..h12a_picker import get_zone as _h12a_get_zone
                h12a_scorer = _get_h12a()
                print(f'[ml_filter] H12 mode enabled (variant={_h12_variant}, '
                      f'AD-conditional={h12b_ad_cond})', flush=True)
            except Exception as _e:
                print(f'[ml_filter] H12 load failed, falling back to v1: {_e}', flush=True)
                h12a_enabled = False
                h12b_ad_cond = False
                h12a_scorer = None
        # 2026-06-18: Lean foundation SHADOW lane — scores Z1/Z2 with ml_scorer_lean
        # (pooled+sector+calibrated, beats 235 per-sector on WF), logs its top-1 pick
        # + quantile abstention alongside the live pick. Does NOT change trading.
        # Enable: LEAN_SHADOW=1. See memory research_lean_vs_235_ablation.
        _lean_shadow = _os_h12a.environ.get('LEAN_SHADOW', '0') == '1'
        lean_scorer = None
        _lean_pool = []
        if _lean_shadow:
            try:
                from ..ml_scorer_lean import get_scorer_lean as _get_lean
                lean_scorer = _get_lean()
                print('[ml_filter] LEAN shadow enabled (Z1/Z2)', flush=True)
            except Exception as _e:
                print(f'[ml_filter] LEAN shadow load failed: {_e}', flush=True)
                lean_scorer = None
        # 2026-06-10: VIX-stress satellite lane. Opens VIX>=20 / vix_5d>=0 blocks
        # (currently hard-blocked) at win_p>=0.80 with stop-2%/TP+3% exit. Validated
        # multi-window (+47% / blended Sharpe 3.72->4.60, robust across 24 configs).
        # Core gets slot priority; lane fills remaining (core Z1/Z2 sit out in high VIX).
        # OFF by default. Enable: H12A_VIX_LANE=live. Reverse: =off + restart.
        _vix_lane_enabled = (h12a_enabled and h12a_scorer is not None
                             and _os_h12a.environ.get('H12A_VIX_LANE', 'off') == 'live')
        _vix_lane_thr = float(_os_h12a.environ.get('H12A_VIX_LANE_THR', '0.80'))
        _vix_lane_sl = 0.02   # stop -2% from entry
        _vix_lane_tp = 0.03   # take-profit +3% from entry

        # [timing] perf instrumentation — log-only, no behavior change (2026-05-30)
        from time import perf_counter as _pc
        _t_scan0 = _pc()
        _t_fetch0 = _t_fetch1 = None
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
            # P5 (2026-05-30): widened -300 -> -400 cal days so >=250 prior TRADING
            # days are available; closes_full is sliced to [-250:] below to match the
            # no-leak trainer window exactly (was ~206 rows -> 52w + days_since skew).
            daily_hist = defaultdict(list)
            for r in conn.execute("""
                SELECT symbol, date, close FROM stock_daily_ohlc
                WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-400 days')
                ORDER BY symbol, date
            """):
                daily_hist[r[0]].append((r[1], r[2]))

            # 14-day ATR window. P5 (2026-05-30): widened -15 -> -30 cal days so >=15
            # prior TRADING rows exist (was ~10-11 -> feat_atr_pct_14d stuck at 1.0).
            daily_hl = defaultdict(list)
            for r in conn.execute("""
                SELECT symbol, date, high, low, open, close FROM stock_daily_ohlc
                WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-30 days')
                ORDER BY symbol, date
            """):
                # tuple is (date, high, low, open, close)
                daily_hl[r[0]].append((r[1], r[2], r[3], r[4], r[5]))  # date,h,l,o,c

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
        _t_fetch0 = _pc()  # [timing]
        with ThreadPoolExecutor(max_workers=len(all_batches)) as ex:
            for batch_bars in ex.map(_fetch_bars, all_batches):
                all_bars.update(batch_bars)
        _t_fetch1 = _pc()  # [timing]

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
        # 2026-06-10: MOM-30 informational list (manual-trade). 2-signal linear
        # (rs+ -0.198*sec_etf) on the cell-ok+threshold pool (NO regime gate),
        # exit +30min. Step 1 validated: net +0.6-0.9%/trade WR70% all liquid
        # buckets, 3/3 folds. Surfaced in scan output only — NOT engine picks
        # (manual exit). Disable: H12A_MOM30=0.
        _mom30_pool = []

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
            # P5 (2026-05-30): slice to last 250 prior trading days to match the
            # no-leak trainer's closes_full = [...][-250:].
            hist_full = daily_hist.get(sym, [])
            closes_full = ([h[1] for h in hist_full if h[1] is not None][-250:]
                           if len(hist_full) >= 100 else [])
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
            # Days since 52w hi/lo. P5 (2026-05-30): drop the >=252 guard (live window
            # is ~250 prior trading days, never 252) to match the no-leak trainer which
            # computes over closes_full[-252:] whenever len(closes_full) >= 100.
            if len(closes_full) >= 100:
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
                        c_prev = hl_list[i-1][4]  # prev close (matches training true-range)
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
            # entries: (date, high, low, open, close)
            ranges = []
            for row in hl_hist:
                if len(row) >= 4 and row[3] and row[3] > 0:
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

            # 2026-06-18: lean shadow scoring (Z1/Z2 only; score() returns None elsewhere)
            if lean_scorer is not None:
                _lp = lean_scorer.score(features, minutes_from_open, sec)
                if _lp is not None:
                    _lean_pool.append({'sym': sym, 'sec': sec, 'mfo': minutes_from_open,
                                       'zone': lean_scorer.get_zone(minutes_from_open),
                                       'score': float(_lp), 'price': round(float(now), 2)})

            # 2026-06-07: H12-A scoring + cell+regime filter when enabled
            if h12a_enabled and h12a_scorer is not None:
                import datetime as _dt_h12a
                _h_dow = _dt_h12a.datetime.now(ET).weekday()
                _h_score, _h_reason = _h12a_score_filter(
                    h12a_scorer, features, minutes_from_open, sec,
                    vix=vix,
                    vix_5d_chg=vix_5d_chg,
                    sec_rel_strength=features.get('sec_rel_strength', 0.0),
                    spy_intra=spy_intra,
                    dow=_h_dow,
                )
                if _os_h12a.environ.get('H12A_DUMP'):
                    import json as _json_d
                    _wp_raw = _h_score if _h_score > 0 else h12a_scorer.score(features, minutes_from_open, sec)
                    with open('/tmp/h12a_dump.jsonl', 'a') as _f:
                        _f.write(_json_d.dumps({'sym': sym, 'mfo': minutes_from_open, 'sec': sec,
                            'gain': round(features.get('gain_from_open', 0), 2),
                            'win_p': round(float(_wp_raw), 4), 'spy_intra': round(float(spy_intra or 0), 3),
                            'price': round(float(now), 2),
                            'gap': round(float(features.get('gap_from_prev', 0) or 0), 3),
                            'range_exp': round(float(features.get('range_exp', 0) or 0), 3),
                            'score': round(float(_h_score), 4), 'reason': _h_reason}) + '\n')
                # MOM-30 pool: cell-ok + win_p>=thr (NO regime gate). Informational.
                if _os_h12a.environ.get('H12A_MOM30', '1') == '1' and 'cell_bad' not in _h_reason:
                    _wp_m = _h_score if _h_score > 0 else h12a_scorer.score(features, minutes_from_open, sec)
                    if _wp_m >= threshold:
                        _rs_m = features.get('gain_from_open', 0.0) - (spy_intra or 0.0)
                        _se_col = self._SECTOR_ETF.get(sec)
                        _se_m = features.get(_se_col, 0.0) if _se_col else 0.0
                        _mom30_pool.append(dict(
                            sym=sym, score=0.217 * _rs_m - 0.198 * _se_m,
                            rs=round(_rs_m, 2), sec_etf=round(_se_m, 2),
                            price=round(now, 2), wp=round(float(_wp_m), 3),
                            zone=_h12a_get_zone(minutes_from_open), sec=sec[:10]))
                _vix_lane = False
                if _h_score <= 0:
                    # VIX-stress lane: rescue VIX>=20 / vix_5d>=0 regime blocks (NOT
                    # cell_bad) at win_p>=thr. Flows through with stop/TP exit below.
                    if (_vix_lane_enabled
                            and ('VIX=' in _h_reason or 'vix_5d_chg' in _h_reason)
                            and 'cell_bad' not in _h_reason):
                        _wp_lane = h12a_scorer.score(features, minutes_from_open, sec)
                        if _wp_lane >= _vix_lane_thr:
                            _vix_lane = True
                            prob = _wp_lane
                        else:
                            continue
                    else:
                        continue  # filtered by H12-A cell/regime gate
                else:
                    prob = _h_score
                # H12-B: AD-conditional effective threshold on Z1/Z3 only.
                # ⚠️ LOOKAHEAD-FLAWED — DO NOT RE-ENABLE (reverted 2026-06-08).
                # Backtest used SAME-DAY EOD ad_ratio to set the morning threshold,
                # but market_breadth updates EOD-only (cron ~17:00 ET), so live can
                # only see PRIOR-day AD. corr(same-day, prior-day AD)=-0.04 → the
                # +27pp edge was lookahead; prior-day AD ≈ H12-A or worse on Sharpe.
                # No legit at-scan proxy (spy_intra) beat H12-A flat 0.75. Kept dormant
                # for record only. See backtests/research/H12B_FINAL_spec.md (REVERTED).
                _eff_thr = threshold
                if h12b_ad_cond:
                    _h12_zone = _h12a_get_zone(minutes_from_open)
                    if _h12_zone in ('Z1', 'Z3'):
                        if ad_ratio > 1.5:
                            _eff_thr = 0.68
                        elif ad_ratio < 0.7:
                            _eff_thr = 0.80
                        # else: keep base 0.75
                if self.REQUIRE_75_THRESHOLD and prob < _eff_thr:
                    continue
            else:
                _eff_thr = threshold  # no AD-conditional in non-H12 path
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
                # 2026-05-30: MARKET entry at current scan price (`now`), 100% fill.
                # Falls back to adaptive-limit (dip-wait) when MARKET_ENTRY=False.
                max_buy = None
                slip_budget = None
                if self.MARKET_ENTRY:
                    limit_price = now
                    slip_budget = self.ZONE_SLIP_BUDGET.get(zone_name, 0.004)
                    max_buy = now * (1 + slip_budget)
                    entry_tag = (f"MARKET@${now:.2f} "
                                 f"(max ${max_buy:.2f} +{slip_budget*100:.1f}%)")
                else:
                    limit_price = adaptive_limit  # ML-predicted dip-wait limit
                    entry_tag = f"LIMIT@${adaptive_limit:.2f} (dip {(1-pred_ratio)*100:.2f}%)"
                zone_sl_pct = getattr(scorer, 'ZONE_HARD_SL', {}).get(zone_name)
                if zone_sl_pct:
                    sl_price = limit_price * (1 - zone_sl_pct)
                    sl_tag = f"hardSL@{-zone_sl_pct*100:.1f}%"
                else:
                    sl_price = 0  # disabled (pure hold)
                    sl_tag = "no SL"
                # VIX-stress lane: override pure-hold-EOD with stop-2%/TP+3%
                _lane_tp_price = None
                if _vix_lane:
                    sl_price = limit_price * (1 - _vix_lane_sl)
                    _lane_tp_price = limit_price * (1 + _vix_lane_tp)
                    sl_tag = (f"VIXlane SL-{_vix_lane_sl*100:.0f}%/"
                              f"TP+{_vix_lane_tp*100:.0f}%")
                # 2026-06-11: optional take-profit suggestion (manual). Set
                # H12A_TP_PCT=3 -> emit TP@+3% on the pick. Backtest: TP caps
                # winners so avg < hold-EOD, but locks gains + avoids fade-days.
                _tp_pct = 0.0
                try:
                    _tp_pct = float(_os_h12a.environ.get('H12A_TP_PCT', '0') or 0)
                except ValueError:
                    _tp_pct = 0.0
                _tp_tag = ''
                if not _vix_lane and _tp_pct > 0:
                    _lane_tp_price = limit_price * (1 + _tp_pct / 100.0)
                    _tp_tag = f" TP@+{_tp_pct:.1f}% (${_lane_tp_price:.2f})"
                reason = (
                    f"{'[VIX-LANE] ' if _vix_lane else ''}"
                    f"ML p={prob:.3f} thr={_eff_thr:.2f} adapt_lim={pred_ratio:.4f} "
                    f"gain+{gain:.1f}% β{beta:.1f} {sec[:6]} "
                    f"{entry_tag} pure-hold-EOD ({sl_tag}){_tp_tag}"
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
                    f"ML p={prob:.3f} thr={_eff_thr:.2f} "
                    f"gain+{gain:.1f}% β{beta:.1f} {sec[:6]} "
                    f"trail{trail}%+hardSL{HARD_SL_PCT}%+lock@+{LOCK_TRIGGER_PCT}%/+{LOCK_AT_PCT}%"
                )

            extra_dict = {
                'ml_prob': round(prob, 4),
                'threshold': round(_eff_thr, 4),
                'bucket': bucket,
                'gain_pct': round(gain, 2),
                'beta': round(beta, 2),
                'sector': sec,
                'limit_price': round(limit_price, 2),
                'max_buy_price': round(max_buy, 2) if max_buy else None,
                'slip_budget_pct': round(slip_budget * 100, 2) if slip_budget else None,
                'exit_strategy': 'vix_lane_sl_tp' if _vix_lane else 'pure_hold_eod',
                'vix_lane': _vix_lane,
                # 2026-06-04: stash per-symbol features used by entry_filter
                'mom20d': round(mom20, 2) if mom20 is not None else None,
            }

            candidates.append(Pick(
                symbol=sym, entry=limit_price,
                sl_price=round(sl_price, 2) if sl_price else None,
                tp_price=round(_lane_tp_price, 2) if _lane_tp_price else None,
                trail_pct=trail,
                reason=reason,
                score=int(prob * 10),
                atr_pct=atr_pct,
                extra=extra_dict,
            ))

        # 2026-06-10: MOM-30 informational output (manual trade, exit +30min).
        # Top-5 of cell-ok+thr pool by 2-signal score (rs+, sec_etf-). Step 1
        # validated net +0.6-0.9%/trade WR70%. Printed + journaled, NOT auto-traded.
        if _mom30_pool:
            try:
                _m30 = sorted(_mom30_pool, key=lambda x: -x['score'])[:5]
                _lines = [f"  {i+1}. {p['sym']:<6} ${p['price']:<8.2f} "
                          f"score{p['score']:+.2f} (rs{p['rs']:+.1f} secETF{p['sec_etf']:+.1f}) "
                          f"{p['zone']} {p['sec']} wp{p['wp']:.2f}" for i, p in enumerate(_m30)]
                print("\n📈 MOM-30 picks (2-signal, EXIT +30min — manual):\n" + "\n".join(_lines)
                      + "\n   (Step1: net +0.6-0.9%/trade WR70%, large-cap. exit at entry+30min)\n",
                      flush=True)
                from pathlib import Path as _MPath
                _mlog = _MPath(__file__).resolve().parents[3] / 'data' / 'mom30_picks.jsonl'
                import json as _mjson, datetime as _mdt
                with open(_mlog, 'a') as _mf:
                    _mf.write(_mjson.dumps({'ts': now_et.isoformat(), 'mfo': minutes_from_open,
                                            'picks': _m30}) + "\n")
            except Exception as _me:
                print(f"[ml_filter] MOM-30 output error (skipped): {_me}", flush=True)

        if not candidates:
            try:
                _fetch_ms = (_t_fetch1 - _t_fetch0) * 1000 if (_t_fetch0 and _t_fetch1) else -1
                print(f"[ml_filter:timing] mfo={minutes_from_open} "
                      f"total={(_pc()-_t_scan0)*1000:.0f}ms fetch={_fetch_ms:.0f}ms "
                      f"syms={len(syms)} bars={len(all_bars)} cands=0 "
                      f"picks=0 status=no_picks", flush=True)
            except Exception:
                pass
            return self.no_picks(
                f"No picks ≥ threshold {threshold:.2f} "
                f"(bucket {scorer.get_bucket(minutes_from_open)})"
            )

        # 2026-05-14 Step 18: F1 (win only) ranking — drop +0.10×gain bonus.
        # WF Top-1 grid (Nov 2025 - Apr 2026, 9 formulas tested):
        #   F1 win only:      +959% / WR 89% / worst -3.50%  ⭐ BEST
        #   F3 w+0.10g (old): +785% / WR 83% / worst -4.48%  (was current)
        # Δ = +174% total, +6pp WR, -1pp tail. Win score already incorporates
        # momentum via gain_from_open feature — adding it again was double-count.
        # Core picks get slot priority; VIX-stress lane fills remaining (core Z1/Z2
        # sit out in high VIX → slots free). vix_lane=False sorts before True.
        candidates.sort(key=lambda p: (p.extra.get('vix_lane', False), -p.extra['ml_prob']))

        # 2026-06-04: entry_filter v1 (rule-based per-zone selection)
        # Applied AFTER ML threshold gate, BEFORE top-1 selection.
        # spec: backtests/entry_filter_v1/spec.json
        # Toggle: set env ENTRY_FILTER_ENABLED=0 to disable.
        all_candidates = list(candidates)  # keep full list for logging
        self.last_all_candidates = all_candidates  # 2026-06-12: hook for riser_momentum lane (re-rank Z1 by gain)
        # 2026-06-18: LEAN SHADOW — top-1/zone by lean score + causal quantile abstention,
        # journal to lean_picks. Shadow only (NO effect on engine picks/returns).
        if _lean_shadow and _lean_pool:
            try:
                from ..lean_abstain import decide as _lean_decide, record as _lean_record, DEFAULT_Q
                _ldate = now_et.strftime('%Y-%m-%d'); _lts = now_et.strftime('%Y-%m-%d %H:%M:%S')
                _byz = {}
                for _c in _lean_pool:
                    _z = _c['zone']
                    if _z and (_z not in _byz or _c['score'] > _byz[_z]['score']):
                        _byz[_z] = _c
                for _z, _top in _byz.items():
                    _dec = _lean_decide(_z, _top['score'], _ldate, q=DEFAULT_Q)
                    _lean_record(_ldate, _lts, _z, _top['mfo'], _top['sym'], _top['sec'],
                                 _top['score'], int(_dec['trade']), DEFAULT_Q, _dec['thr'], len(_lean_pool))
                    print(f"[lean-shadow] {_z} top1={_top['sym']} score={_top['score']:.3f} "
                          f"trade={_dec['trade']} ({_dec['reason']})", flush=True)
            except Exception as _e:
                print(f'[ml_filter] lean shadow record failed: {_e}', flush=True)
        filter_verdicts = {}  # symbol -> (passes: bool, reason: str)
        import os as _os
        if _os.environ.get('ENTRY_FILTER_ENABLED', '1') == '1':
            try:
                from src.entry_filter.rules import evaluate as _ef_evaluate, zone_of_mfo as _ef_zone
                import datetime as _dt
                _zone_str = _ef_zone(minutes_from_open)
                _dow = _dt.datetime.now(ET).weekday()
                survivors = []
                for c in candidates:
                    fx = c.extra
                    # VIX-stress lane picks bypass entry_filter (own validated sleeve)
                    if fx.get('vix_lane'):
                        filter_verdicts[c.symbol] = (True, 'vix_lane_bypass')
                        survivors.append(c)
                        continue
                    passes, reason = _ef_evaluate(
                        zone=_zone_str,
                        beta=fx.get('beta'),
                        sector=fx.get('sector'),
                        vix=vix,                # outer-scope macro
                        dow=_dow,
                        gain_from_open=fx.get('gain_pct'),
                        spy_intra=spy_intra,    # outer-scope macro
                        mom20d=fx.get('mom20d'),
                    )
                    filter_verdicts[c.symbol] = (passes, reason)
                    if passes:
                        survivors.append(c)
                # Replace candidates with survivors for downstream selection
                # If no survivors, downstream still has empty list (handled gracefully)
                candidates = survivors
            except Exception as _e:
                # Graceful fallback — never break engine
                try:
                    print(f"[ml_filter] entry_filter error (skipped): {_e}", flush=True)
                except Exception:
                    pass
                filter_verdicts = {}

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
        pick_ids = []
        try:
            journal = get_journal()
            for p in picks:
                pid = journal.record_pick(
                    strategy=self.name, bucket=bucket, symbol=p.symbol,
                    entry=p.entry, sl_price=p.sl_price, tp_price=p.tp_price,
                    trail_pct=p.trail_pct,
                    ml_prob=p.extra.get('ml_prob'),
                    ml_threshold=p.extra.get('threshold'),
                    expected_wr=expected_wr / 100,
                    reason=p.reason,
                    features=p.extra,
                )
                pick_ids.append(pid)
        except Exception:
            pick_ids = []

        # 2026-06-02: Port from v2.7.0 — record ALL candidates with rank info
        # → enables sim-vs-live parity for post-market analysis. Logging only.
        # 2026-06-04: log filter_verdict + filter_reason from entry_filter v1
        try:
            zone_name_log = scorer.get_zone(minutes_from_open) if scorer.USE_ZONES else None
            # Rank across ALL ml-passing candidates (pre-filter set) so log shows true rank
            sorted_r9 = sorted(all_candidates, key=lambda p: -p.extra.get('r9_score',
                p.extra.get('ml_prob', 0) * max(0.0, 1 - p.extra.get('pred_ratio', 1.0)) ** 0.5))
            sorted_win = sorted(all_candidates, key=lambda p: -p.extra.get('ml_prob', 0))
            r9_rank = {p.symbol: i+1 for i, p in enumerate(sorted_r9)}
            win_rank = {p.symbol: i+1 for i, p in enumerate(sorted_win)}
            picked_syms = {p.symbol for p in picks}
            scored_rows = []
            for c in all_candidates:
                prob = c.extra.get('ml_prob', 0.0)
                pr = c.extra.get('pred_ratio', 1.0)
                fv = filter_verdicts.get(c.symbol)
                f_pass = fv[0] if fv else True
                f_reason = fv[1] if fv else None
                scored_rows.append({
                    'symbol': c.symbol,
                    'win_p': prob,
                    'loss_p': None,
                    'pred_r': pr,
                    'r9_score': prob * max(0.0, 1 - pr) ** 0.5,
                    'passed_filter': True,
                    'rank_by_win': win_rank.get(c.symbol),
                    'rank_by_r9': r9_rank.get(c.symbol),
                    'selected': c.symbol in picked_syms,
                    'sector': c.extra.get('sector'),
                    'beta': c.extra.get('beta'),
                    'gain_from_open': c.extra.get('gain_pct'),
                    'gain_from_prev': None,
                    'scan_price': None,
                    'adaptive_limit': c.extra.get('limit_price'),
                    'user_limit': c.entry,
                    'features': c.extra,
                    'filter_verdict': 'PASS' if f_pass else 'SKIP',
                    'filter_reason': f_reason,
                })
            if scored_rows:
                first_pick_id = pick_ids[0] if pick_ids else None
                journal.record_candidates_batch(
                    scored_rows, pick_id=first_pick_id,
                    strategy=self.name, zone=zone_name_log, mfo=minutes_from_open,
                )
        except Exception:
            pass  # logging failure must not break scan

        regime_str = f"SPY{spy_daily:+.1f}% AD{ad_ratio:.1f} VIX{vix:.0f} anom{anomaly_score:.1f}"

        # 2026-06-04: surface entry_filter activity in reason text
        n_all = len(all_candidates) if 'all_candidates' in dir() else len(candidates)
        n_passed_filter = len(candidates)
        n_filtered_out = n_all - n_passed_filter
        if n_filtered_out > 0:
            reason = (f"{n_all} ML-passing → {n_filtered_out} filtered out → "
                      f"{n_passed_filter} survivors → top {len(picks)} (expected WR ~{expected_wr:.0f}%)")
        else:
            reason = f"{n_all} ML-passing → top {len(picks)} (expected WR ~{expected_wr:.0f}%)"

        # [timing] log-only — total scan time + parallel bar-fetch slice (active path)
        try:
            _fetch_ms = (_t_fetch1 - _t_fetch0) * 1000 if (_t_fetch0 and _t_fetch1) else -1
            print(f"[ml_filter:timing] mfo={minutes_from_open} "
                  f"total={(_pc()-_t_scan0)*1000:.0f}ms fetch={_fetch_ms:.0f}ms "
                  f"syms={len(syms)} bars={len(all_bars)} cands={len(candidates)} "
                  f"picks={len(picks)} status=active", flush=True)
        except Exception:
            pass

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
