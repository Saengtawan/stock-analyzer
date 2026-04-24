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
from datetime import datetime
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
    MAX_GAIN = 5.0   # gain ≥5% = chased/pumped — all strategies drop to 53-71% WR (2026-04-14 backtest)

    @staticmethod
    def _compute_vol_trend(bars):
        """Ratio of last-3-bars vol to first-3-bars vol. Proxy for volume decay/surge."""
        if not bars or len(bars) < 6:
            return 1.0
        first3 = sum(b.get('v', 0) for b in bars[:3]) / 3
        last3 = sum(b.get('v', 0) for b in bars[-3:]) / 3
        return min(20.0, last3 / first3) if first3 > 0 else 1.0

    @staticmethod
    def _compute_path_features(bars, day_open):
        """v8 path features: detect lower highs, choppy paths, fading momentum.
        Computed from intraday 5-min bars up to current scan time."""
        defaults = {
            'path_r_squared': 0, 'path_peak_diff': 0, 'path_low_diff': 0,
            'path_consol_range': 0, 'path_max_drawdown': 0, 'path_choppiness': 0,
        }
        if not bars or len(bars) < 4 or not day_open or day_open < 1:
            return defaults

        import numpy as np
        gains_c = [(b.get('c', day_open) / day_open - 1) * 100 for b in bars]
        gains_h = [(b.get('h', day_open) / day_open - 1) * 100 for b in bars]
        gains_l = [(b.get('l', day_open) / day_open - 1) * 100 for b in bars]

        # 1. R-squared (path linearity)
        x = np.arange(len(gains_c))
        corr = np.corrcoef(x, gains_c)[0, 1]
        r_sq = corr ** 2 if not np.isnan(corr) else 0

        # 2. Peak diff (lower high detection)
        peaks = []
        for i in range(1, len(gains_h) - 1):
            if gains_h[i] > gains_h[i - 1] and gains_h[i] > gains_h[i + 1]:
                peaks.append(gains_h[i])
        peak_diff = (peaks[-1] - peaks[-2]) if len(peaks) >= 2 else 0

        # 3. Low diff (higher low detection)
        low_pts = []
        for i in range(1, len(gains_l) - 1):
            if gains_l[i] < gains_l[i - 1] and gains_l[i] < gains_l[i + 1]:
                low_pts.append(gains_l[i])
        low_diff = (low_pts[-1] - low_pts[-2]) if len(low_pts) >= 2 else 0

        # 4. Consolidation range (last 4 bars)
        last4 = bars[-min(4, len(bars)):]
        consol = (max(b.get('h', 0) for b in last4) - min(b.get('l', 1e9) for b in last4)) / day_open * 100

        # 5. Max drawdown during path
        running_max = gains_c[0]
        max_dd = 0
        for g in gains_c:
            if g > running_max:
                running_max = g
            dd = g - running_max
            if dd < max_dd:
                max_dd = dd

        # 6. Choppiness (direction changes / bars)
        changes = sum(1 for i in range(2, len(gains_c))
                      if (gains_c[i] - gains_c[i - 1]) * (gains_c[i - 1] - gains_c[i - 2]) < 0)
        chop = changes / len(gains_c) if gains_c else 0

        return {
            'path_r_squared': r_sq,
            'path_peak_diff': peak_diff,
            'path_low_diff': low_diff,
            'path_consol_range': consol,
            'path_max_drawdown': max_dd,
            'path_choppiness': chop,
        }

    @staticmethod
    def _compute_speed_features(bars, day_open):
        """v9 speed + extended path features for 10:00+ anti-fade detection."""
        defaults = {
            'path_speed_late': 0, 'path_speed_accel': 0, 'path_momentum_accel': 0,
            'path_speed_early': 0, 'path_up_vol_ratio': 0, 'path_support_touches': 0,
            'path_bar_size_trend': 0, 'path_wick_ratio': 0, 'path_lower_wick_ratio': 0,
            'path_gap_ratio': 0, 'path_time_at_high': 0, 'path_vol_at_peaks': 0,
            'path_vwap_slope': 0, 'path_ret_skewness': 0,
        }
        if not bars or len(bars) < 6 or not day_open or day_open < 1:
            return defaults

        import numpy as np
        gains = [(b.get('c', day_open) / day_open - 1) * 100 for b in bars]
        n = len(gains)
        third = max(1, n // 3)

        # Speed features
        early_speed = (gains[third] - gains[0]) / (third * 5) if third > 0 else 0
        late_speed = (gains[-1] - gains[-third]) / (third * 5) if third > 0 else 0
        speed_accel = late_speed - early_speed

        # Momentum acceleration
        rets = [gains[i] - gains[i-1] for i in range(1, n)]
        mid = len(rets) // 2
        mom_accel = np.mean(rets[mid:]) - np.mean(rets[:mid]) if mid > 0 and rets else 0

        # Volume features
        up_vol = sum(b.get('v', 0) for i, b in enumerate(bars) if i > 0 and gains[i] > gains[i-1])
        dn_vol = sum(b.get('v', 0) for i, b in enumerate(bars) if i > 0 and gains[i] <= gains[i-1])
        up_vol_ratio = np.log1p(up_vol) - np.log1p(dn_vol)

        # Support touches
        running_low = gains[0]
        touches = 0
        for g in gains:
            if g <= running_low * 1.001:
                touches += 1
            if g < running_low:
                running_low = g
        support_touches = touches / n

        # Bar size trend
        ranges = [(b.get('h', 0) - b.get('l', 0)) / day_open * 100 for b in bars if b.get('h') and b.get('l')]
        bar_size_trend = np.corrcoef(np.arange(len(ranges)), ranges)[0, 1] if len(ranges) > 3 else 0
        if np.isnan(bar_size_trend):
            bar_size_trend = 0

        # Wick ratios
        wick_ratios = []
        lower_wick_ratios = []
        for b in bars:
            h, l, o, c = b.get('h', 0), b.get('l', 0), b.get('o', 0), b.get('c', 0)
            rng = h - l
            if rng > 0:
                wick_ratios.append((h - max(o, c)) / rng)
                lower_wick_ratios.append((min(o, c) - l) / rng)
        wick_ratio = np.mean(wick_ratios) if wick_ratios else 0
        lower_wick = np.mean(lower_wick_ratios) if lower_wick_ratios else 0

        # Gap ratio
        gaps = [(bars[i].get('o', 0) / bars[i-1].get('c', 1) - 1) * 100
                for i in range(1, len(bars)) if bars[i-1].get('c', 0) > 0]
        gap_ratio = np.mean(gaps) if gaps else 0

        # Time at high
        if gains:
            g_max, g_min = max(gains), min(gains)
            g_range = g_max - g_min
            time_at_high = sum(1 for g in gains if g >= g_max - 0.25 * g_range) / n if g_range > 0 else 0.5
        else:
            time_at_high = 0.5

        # Volume at peaks vs dips
        if len(bars) > 2:
            med_gain = np.median(gains)
            peak_vol = np.mean([b.get('v', 0) for i, b in enumerate(bars) if gains[i] >= med_gain]) or 1
            dip_vol = np.mean([b.get('v', 0) for i, b in enumerate(bars) if gains[i] < med_gain]) or 1
            vol_at_peaks = np.log(peak_vol) - np.log(dip_vol)
        else:
            vol_at_peaks = 0

        # VWAP slope
        cum_pv = 0; cum_v = 0; vwap_diffs = []
        for i, b in enumerate(bars):
            v = b.get('v', 0) or 0; cum_v += v; cum_pv += b.get('c', day_open) * v
            vwap = cum_pv / cum_v if cum_v > 0 else b.get('c', day_open)
            vwap_diffs.append((b.get('c', day_open) / vwap - 1) * 100)
        vwap_slope = np.corrcoef(np.arange(len(vwap_diffs)), vwap_diffs)[0, 1] if len(vwap_diffs) > 3 else 0
        if np.isnan(vwap_slope):
            vwap_slope = 0

        # Return skewness
        from scipy.stats import skew as scipy_skew
        try:
            ret_skew = float(scipy_skew(rets)) if len(rets) > 3 else 0
        except Exception:
            ret_skew = 0

        return {
            'path_speed_late': late_speed,
            'path_speed_accel': speed_accel,
            'path_momentum_accel': mom_accel,
            'path_speed_early': early_speed,
            'path_up_vol_ratio': up_vol_ratio,
            'path_support_touches': support_touches,
            'path_bar_size_trend': bar_size_trend,
            'path_wick_ratio': wick_ratio,
            'path_lower_wick_ratio': lower_wick,
            'path_gap_ratio': gap_ratio,
            'path_time_at_high': time_at_high,
            'path_vol_at_peaks': vol_at_peaks,
            'path_vwap_slope': vwap_slope,
            'path_ret_skewness': ret_skew if not np.isnan(ret_skew) else 0,
        }

    REQUIRE_75_THRESHOLD = True
    MAX_PICKS = 3

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

            spy_rows = conn.execute("SELECT spy_close FROM macro_snapshots WHERE spy_close IS NOT NULL ORDER BY date DESC LIMIT 5").fetchall()
            if len(spy_rows) < 2 or not spy_rows[0][0] or not spy_rows[1][0]:
                return self.gate_failed("No SPY data")
            spy_daily = (spy_rows[0][0] / spy_rows[1][0] - 1) * 100
            spy_green = 1 if spy_daily > 0 else 0

            vix_row = conn.execute("SELECT vix_close FROM macro_snapshots WHERE vix_close IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone()
            vix = float(vix_row[0]) if vix_row and vix_row[0] else 20.0

            vix_5d_row = conn.execute("SELECT vix_close FROM macro_snapshots WHERE vix_close IS NOT NULL ORDER BY date DESC LIMIT 1 OFFSET 4").fetchone()
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

            # Universe — exclude ETFs (they're in top 200 by volume but not tradeable setups)
            syms = [r[0] for r in conn.execute(
                "SELECT symbol FROM universe_stocks WHERE sector != 'ETF' ORDER BY dollar_vol DESC LIMIT 200"
            ).fetchall()]
            sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
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

            # Sector 3d trend — set to 0 to match training data (sec3d=0 in pkl).
            # Feeding non-zero values here would cause train/live feature mismatch.
            # Fix properly: rebuild pkl with computed sec3d + retrain.
            sector_3d = {}

            # v3 new features: insider, news, earnings, PM vol, short interest
            insider_net = {}
            for r in conn.execute("""
                SELECT symbol,
                    SUM(CASE WHEN transaction_type='purchase' THEN shares ELSE 0 END) as buys,
                    SUM(CASE WHEN transaction_type='sale' THEN shares ELSE 0 END) as sells
                FROM insider_transactions
                WHERE transaction_date >= date('now','-30 days')
                GROUP BY symbol
            """):
                total = (r[1] or 0) + (r[2] or 0)
                if total > 0:
                    insider_net[r[0]] = ((r[1] or 0) - (r[2] or 0)) / total

            news_sent = {}
            for r in conn.execute("""
                SELECT symbol, AVG(CASE
                    WHEN sentiment_label='very_positive' THEN 2
                    WHEN sentiment_label='positive' THEN 1
                    WHEN sentiment_label='negative' THEN -1
                    WHEN sentiment_label='very_negative' THEN -2 ELSE 0 END)
                FROM news_events
                WHERE published_at >= datetime('now','-1 day')
                AND symbol IS NOT NULL GROUP BY symbol
            """):
                news_sent[r[0]] = r[1] or 0

            earn_days = {}
            for r in conn.execute("""
                SELECT symbol, MIN(julianday(next_earnings_date) - julianday('now'))
                FROM earnings_calendar
                WHERE next_earnings_date >= date('now')
                GROUP BY symbol
            """):
                earn_days[r[0]] = min(r[1] or 60, 60)

            pm_vol_today = {}
            pm_vol_avg = {}
            for r in conn.execute("""
                SELECT symbol, SUM(volume) FROM intraday_bars_5m
                WHERE date = date('now') AND time_et < '09:30'
                GROUP BY symbol
            """):
                pm_vol_today[r[0]] = r[1] or 0
            for r in conn.execute("""
                SELECT symbol, AVG(vol) FROM (
                    SELECT symbol, date, SUM(volume) as vol FROM intraday_bars_5m
                    WHERE time_et < '09:30' AND date >= date('now','-14 days') AND date < date('now')
                    GROUP BY symbol, date
                ) GROUP BY symbol
            """):
                pm_vol_avg[r[0]] = r[1] or 0

            short_pct = {}
            try:
                for r in conn.execute("""
                    SELECT si.symbol, si.short_pct_float FROM short_interest si
                    INNER JOIN (SELECT symbol, MAX(date) as md FROM short_interest GROUP BY symbol) latest
                    ON si.symbol = latest.symbol AND si.date = latest.md
                """):
                    short_pct[r[0]] = r[1] or 0
            except Exception:
                pass
        finally:
            conn.close()

        # Alpaca snapshots
        hdr = {
            'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'),
            'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY'),
        }
        snaps = {}
        for i in range(0, len(syms), 100):
            batch = ','.join(syms[i:i+100])
            r = requests.get(f'https://data.alpaca.markets/v2/stocks/snapshots?symbols={batch}',
                             headers=hdr, timeout=15)
            if r.status_code == 200:
                snaps.update(r.json())

        # Fetch ETF snapshots (SPY, IWM, USO + all sector ETFs + SMH for semis) for regime detection
        # Includes XLB (Basic Materials) — fixed missing from L1 ranking
        etf_syms = ['SPY', 'IWM', 'USO', 'XLK', 'XLV', 'XLF', 'XLY', 'XLC', 'XLI',
                    'XLP', 'XLE', 'XLB', 'XLRE', 'XLU', 'SMH']
        r = requests.get(f'https://data.alpaca.markets/v2/stocks/snapshots?symbols={",".join(etf_syms)}',
                         headers=hdr, timeout=15)
        etf_snaps = r.json() if r.status_code == 200 else {}

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
            prev_vol = pb.get('v', 1)
            vol_ratio = db.get('v', 0) / prev_vol if prev_vol > 0 else 0
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
            sec3d = sector_3d.get(sec, 0)

            # Live multi-bar features from Alpaca 5-min bars
            sym_bars = bars_by_sym.get(sym, [])
            if sym_bars:
                day_open = sym_bars[0].get('o', opn)
                bar_feats = extract_multibar_features(sym_bars, day_open)
            else:
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
                'sec3d': sec3d,
                'mom5d': mom5,
                'mom20d': mom20,
                'dist_sma20': dist_sma20,
                'pct_52w_hi': pct_52w_hi,
                'pct_52w_lo': pct_52w_lo,
                'dow': dow,
                # v3 new features
                'insider_net_30d': insider_net.get(sym, 0),
                'news_sentiment': news_sent.get(sym, 0),
                'earnings_days': earn_days.get(sym, 60),
                'pm_vol_ratio': (pm_vol_today.get(sym, 0) / pm_vol_avg[sym]
                                 if pm_vol_avg.get(sym, 0) > 0 else 0),
                'short_pct': short_pct.get(sym, 0),
                # v6 macro features
                'btc_5d_chg': btc_5d_chg,
                'jpy_5d_chg': jpy_5d_chg,
                'skew': skew_v,
                'vvix': vvix_v,
                'vix_term_spread': vix_term_spread,
                'sec_rel_strength': max(-20, min(20, gain - sec3d)),
                # v7 intraday features
                'gain_first30': bar_feats.get('gain_first30', 0),
                'entry_vs_first30': bar_feats.get('entry_vs_first30', 0),
                'pullback_depth': bar_feats.get('pullback_depth', 0),
                'vol_trend': self._compute_vol_trend(sym_bars) if sym_bars else 1.0,
                'consec_green': bar_feats.get('consec_green', 0),
                'time_since_peak': bar_feats.get('time_since_peak', 0),
                # v8 path features (anti-fade: lower highs, choppy path detection)
                **self._compute_path_features(sym_bars, opn),
                # v9 speed features
                **self._compute_speed_features(sym_bars, opn),
                # v9 gap interactions (for 09:30 bucket)
                'gap_x_vol': gap_from_prev * vol_ratio,
                'gap_x_beta': gap_from_prev * beta,
                'gap_x_spy': gap_from_prev * spy_green,
                'gap_x_pm': gap_from_prev * (pm_vol_today.get(sym, 0) / pm_vol_avg[sym]
                            if pm_vol_avg.get(sym, 0) > 0 else 0),
                'gap_abs': abs(gap_from_prev),
                'vol_x_pm': vol_ratio * (pm_vol_today.get(sym, 0) / pm_vol_avg[sym]
                            if pm_vol_avg.get(sym, 0) > 0 else 0),
                'gain_x_vol': gain * vol_ratio,
                'gap_x_vix': gap_from_prev * vix,
                'mom5_x_gap': mom5 * gap_from_prev,
                'beta_x_spy': beta * spy_green,
                # Cross-asset intraday features (for Confidence ML)
                'spy_intra': spy_intra,
                'qqq_intra': etf_intraday('QQQ'),
                'iwm_intra': iwm_intra,
                'uso_intra': uso_intra,
                'vxx_intra': etf_intraday('VXX'),
                'gld_intra': etf_intraday('GLD'),
                'hyg_intra': etf_intraday('HYG'),
                'tlt_intra': etf_intraday('TLT'),
                'smh_intra': etf_intraday('SMH'),
                'xle_intra': etf_intraday('XLE'),
                'xlk_intra': etf_intraday('XLK'),
                'xlv_intra': etf_intraday('XLV'),
                'iwm_spy_spread': iwm_intra - spy_intra,
                'xlk_spy_spread': etf_intraday('XLK') - spy_intra,
                'uso_iwm_combo': uso_intra * (1.0 if (iwm_intra - spy_intra) < -0.3 else 0.0),
                'vxx_spy_combo': etf_intraday('VXX') * (1.0 if spy_intra < 0 else 0.0),
                'anomaly_score': anomaly_score,
            }

            prob = scorer.score(features, minutes_from_open)

            if self.REQUIRE_75_THRESHOLD and prob < threshold:
                continue

            # Q25 downside filter: reject high-variance faders (10:00+ only)
            if not scorer.passes_q25_filter(features, minutes_from_open):
                continue

            # Confidence gate: reject if model is uncertain (regime-aware, 10:00+ only)
            if not scorer.passes_confidence_filter(features, minutes_from_open):
                continue

            atr_pct = (hi - lo) / now * 100 if now > 0 else 3.0
            # Trail 5% at 09:30 (wider for early whipsaw), 3% at 10:00+ (tighter momentum)
            # Clean backtest 2026-04-24: unified 3% hurt avg (-0.09%) without WR benefit.
            trail = 5.0 if minutes_from_open < 30 else 3.0
            sl_price = now * (1 - trail / 100)
            q25 = scorer.score_q25(features, minutes_from_open)
            reason = (
                f"ML pnl={prob:.3f} q25={q25:.3f} "
                f"gain+{gain:.1f}% β{beta:.1f} {sec[:6]}"
            )

            candidates.append(Pick(
                symbol=sym, entry=now,
                sl_price=round(sl_price, 2),
                tp_price=None,
                trail_pct=trail,
                reason=reason,
                score=int(prob * 10),
                atr_pct=atr_pct,
                extra={
                    'ml_prob': round(prob, 4),
                    'ml_q25': round(q25, 4),
                    'threshold': round(threshold, 4),
                    'bucket': bucket,
                    'gain_pct': round(gain, 2),
                    'beta': round(beta, 2),
                    'sector': sec,
                },
            ))

        if not candidates:
            return self.no_picks(
                f"No picks ≥ threshold {threshold:.2f} "
                f"(bucket {scorer.get_bucket(minutes_from_open)})"
            )

        # Regime handling now done via ML (Confidence + Q25 + cross-asset features)
        # USO+IWM hardcoded rule removed — ML handles it
        candidates.sort(key=lambda p: -p.extra['ml_prob'])

        # === Industry Rotation filter (L1) — STRICTER ===
        # Require mapped ETF in TOP 3 (not just "not in bottom 3").
        # Previously: only reject bottom 3 → on red days where 8/11 ETFs
        # are red, middle-rank Tech still passed despite market weakness.
        # Now ranks 12 ETFs (added XLB Basic Materials).
        etf_intra = {
            'XLK': etf_intraday('XLK'), 'XLV': etf_intraday('XLV'),
            'XLF': etf_intraday('XLF'), 'XLY': etf_intraday('XLY'),
            'XLC': etf_intraday('XLC'), 'XLI': etf_intraday('XLI'),
            'XLP': etf_intraday('XLP'), 'XLE': etf_intraday('XLE'),
            'XLU': etf_intraday('XLU'), 'XLRE': etf_intraday('XLRE'),
            'XLB': etf_intraday('XLB'),
            'SMH': etf_intraday('SMH') if 'SMH' in etf_snaps else etf_intraday('XLK'),
        }
        etf_ranked = sorted(etf_intra.items(), key=lambda x: -x[1])
        hot_etfs = {e[0] for e in etf_ranked[:3]}
        cold_etfs = {e[0] for e in etf_ranked[-3:]}

        # SPY red-day gate: raise score threshold if market is weak
        spy_red = spy_intra < -0.3
        # Sector cap: 1 per sector on red days (vs 2 on normal days)
        sector_cap = 1 if spy_red else 2

        # === L3: Stock vs peers (30-min relative strength) ===
        # L2 (sector fade from peak) removed 2026-04-24: backtest showed
        # it only added 71 additional rejections on top of L1 (3%) and
        # marginal WR impact. Largely redundant with L1 Industry Rotation.
        # Compare stock's last ~30-min change to its mapped ETF's last ~30-min change.
        # Needs 5-min bars for both stock (bars_by_sym) and ETF (fetch below).
        REL_THRESHOLDS = {'10:00-10:45': -0.30, '10:45-11:30': -0.10, '11:30-13:00': 0.10}
        l3_active = minutes_from_open >= 30  # skip 09:30 bucket

        etf_bars = {}
        if l3_active:
            try:
                etf_bars = fetch_today_bars(list(etf_intra.keys()))
            except Exception:
                etf_bars = {}

        def recent_change_pct(bars, bars_back=6):
            """% change over last ~30 min (bars_back × 5min)."""
            if not bars or len(bars) < 2:
                return 0.0
            now_c = bars[-1].get('c', 0)
            idx = max(0, len(bars) - 1 - bars_back)
            past_c = bars[idx].get('c', 0)
            return (now_c / past_c - 1) * 100 if past_c > 0 else 0.0

        etf_recent_mom = {e: recent_change_pct(etf_bars.get(e, []), 6) for e in etf_intra.keys()}

        def stock_etf(sym):
            """Map stock to primary ETF (industry > sector fallback)."""
            ind = (industries.get(sym) or '').lower()
            if 'semiconduct' in ind: return 'SMH'
            if 'software' in ind or 'information technology' in ind: return 'XLK'
            if 'bank' in ind or 'insurance' in ind or 'capital market' in ind or 'financial' in ind: return 'XLF'
            if 'oil' in ind or 'gas' in ind or 'energy' in ind: return 'XLE'
            if 'utility' in ind or 'utilities' in ind: return 'XLU'
            if 'reit' in ind or 'real estate' in ind: return 'XLRE'
            if 'aerospace' in ind or 'airline' in ind or 'machinery' in ind or 'industrial' in ind: return 'XLI'
            if 'drug' in ind or 'biotech' in ind or 'medical' in ind or 'health' in ind: return 'XLV'
            if 'retail' in ind or 'auto' in ind or 'leisure' in ind or 'restaurant' in ind: return 'XLY'
            if 'beverage' in ind or 'tobacco' in ind or 'household' in ind or 'grocery' in ind or 'staple' in ind: return 'XLP'
            if 'internet' in ind or 'media' in ind or 'entertainment' in ind or 'telecom' in ind: return 'XLC'
            # Sector fallback
            return sector_to_etf.get(sectors.get(sym, ''), 'XLK')

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

        # Diversify sector + L1/L3 filters
        bucket_key = scorer.get_bucket(minutes_from_open)
        sec_count = {}
        picks = []
        skipped = {'cold': [], 'not_hot': [], 'rel': [], 'recent': []}
        for c in candidates:
            if c.symbol in recent_syms:
                skipped['recent'].append(c.symbol)
                continue
            sec = c.extra['sector']
            if sec_count.get(sec, 0) >= sector_cap:
                continue
            etf = stock_etf(c.symbol)

            # L1 STRICTER: require mapped ETF in TOP 3 (not just "not bottom 3")
            if etf not in hot_etfs:
                if etf in cold_etfs:
                    skipped['cold'].append((c.symbol, etf))
                else:
                    skipped['not_hot'].append((c.symbol, etf))
                continue

            # L3: Stock vs peers — reject if stock weaker than sector in last 30-min (10:00+ only)
            if l3_active and bucket_key in REL_THRESHOLDS:
                stock_bars = bars_by_sym.get(c.symbol, [])
                stock_recent = recent_change_pct(stock_bars, 6)
                sector_recent = etf_recent_mom.get(etf, 0)
                rel_strength = stock_recent - sector_recent
                if rel_strength < REL_THRESHOLDS[bucket_key]:
                    skipped['rel'].append((c.symbol, etf, round(rel_strength, 2)))
                    continue
                c.extra['rel_strength'] = round(rel_strength, 2)

            c.extra['etf'] = etf
            c.extra['etf_rank'] = next((i for i, (e, _) in enumerate(etf_ranked) if e == etf), -1) + 1
            sec_count[sec] = sec_count.get(sec, 0) + 1
            picks.append(c)
            if len(picks) >= self.MAX_PICKS:
                break

        bucket = scorer.get_bucket(minutes_from_open)
        # Realistic WR from 24-month walk-forward (v16 + L1 + L3 + slippage)
        # Earlier "88% at 09:30" was cherry-picked 7 months; below reflects full-cycle reality.
        WR_BY_BUCKET = {
            '09:30-10:00': 69,
            '10:00-10:45': 61,
            '10:45-11:30': 67,
            '11:30-13:00': 70,
        }
        expected_wr = WR_BY_BUCKET.get(bucket, 65)

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
                'model_version': 'v11_confidence',
                'anomaly_score': round(anomaly_score, 2),
            },
        )
