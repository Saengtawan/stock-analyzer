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
    expected_wr = 0.80  # average of 5 active buckets
    expected_ev = 0.015
    time_start = "09:30"
    time_end = "14:00"
    version = "2.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 3.0
    MIN_GAIN = 2.0   # loose — let ML decide
    MAX_GAIN = 10.0
    REQUIRE_75_THRESHOLD = True
    MAX_PICKS = 3

    def scan(self) -> ScanResult:
        if not self.in_time_window():
            return self.out_of_window()

        scorer = get_scorer()
        now_et = datetime.now(ET)
        minutes_from_open = (now_et.hour - 9) * 60 + (now_et.minute - 30)

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

            vix_5d_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 5 OFFSET 4").fetchone()
            vix_5d_chg = (vix - float(vix_5d_row[0])) if vix_5d_row else 0.0

            # Universe
            syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
            sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
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

            # Sector 3d trend
            sector_3d = {}
            for r in conn.execute("""
                SELECT u.sector, AVG((d.close - d.open) / d.open * 100.0)
                FROM stock_daily_ohlc d JOIN universe_stocks u ON d.symbol = u.symbol
                WHERE d.date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-3 days')
                AND u.sector IS NOT NULL GROUP BY u.sector
            """):
                sector_3d[r[0]] = r[1] or 0

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

        # SPY intraday direction
        spy_snap = snaps.get('SPY', {})
        spy_db = spy_snap.get('dailyBar', {})
        spy_intra = 0
        if spy_db.get('o', 0) > 0:
            spy_intra = (spy_db.get('c', 0) / spy_db.get('o', 1) - 1) * 100

        # Pre-filter: stocks with gain in range (to reduce bar fetch calls)
        pre_qualified = []
        for sym in syms:
            if sym in earnings_skip or sym == 'SPY': continue
            s = snaps.get(sym)
            if not s: continue
            db = s.get('dailyBar', {})
            opn = db.get('o', 0); now = db.get('c', 0)
            if opn < 1 or now < self.MIN_PRICE: continue
            gain = (now / opn - 1) * 100
            if self.MIN_GAIN <= gain < self.MAX_GAIN:
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

            gain = (now / opn - 1) * 100
            if not (self.MIN_GAIN <= gain < self.MAX_GAIN):
                continue

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
            closes = [h[1] for h in hist[-21:]]
            mom5 = (closes[-1] / closes[-6] - 1) * 100 if closes[-6] else 0
            mom20 = (closes[-1] / closes[0] - 1) * 100 if closes[0] else 0
            sma20 = np.mean(closes[-20:])
            dist_sma20 = (now / sma20 - 1) * 100 if sma20 > 0 else 0

            # 52w high/low from history
            hist_full = daily_hist.get(sym, [])
            if len(hist_full) >= 100:
                closes_full = [h[1] for h in hist_full]
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
            }

            prob_gain = scorer.score_gain(features, minutes_from_open)
            prob = scorer.score(features, minutes_from_open)

            if self.REQUIRE_75_THRESHOLD and prob < threshold:
                continue

            atr_pct = (hi - lo) / now * 100 if now > 0 else 3.0
            sl_price = now * 0.97  # trail 3% acts as SL from entry
            prob_gain = scorer.score_gain(features, minutes_from_open)
            prob_profit = scorer.score_profit(features, minutes_from_open)
            reason = (
                f"ML g={prob_gain:.2f}×p={prob_profit:.2f}={prob:.3f} "
                f"gain+{gain:.1f}% β{beta:.1f} {sec[:6]}"
            )

            candidates.append(Pick(
                symbol=sym, entry=now,
                sl_price=round(sl_price, 2),
                tp_price=None,
                trail_pct=3.0,
                reason=reason,
                score=int(prob * 10),
                atr_pct=atr_pct,
                extra={
                    'ml_prob': round(prob, 4),
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

        candidates.sort(key=lambda p: -p.extra['ml_prob'])
        # Diversify max 2/sector
        sec_count = {}
        picks = []
        for c in candidates:
            sec = c.extra['sector']
            if sec_count.get(sec, 0) >= 2:
                continue
            sec_count[sec] = sec_count.get(sec, 0) + 1
            picks.append(c)
            if len(picks) >= self.MAX_PICKS:
                break

        bucket = scorer.get_bucket(minutes_from_open)
        expected_wr = scorer.metadata[bucket].get('test_top1_wr', 75)

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

        return ScanResult(
            strategy=self.name,
            timestamp_et=self.time_et_str(),
            status='active',
            reason=f"{len(candidates)} ML-passing → top {len(picks)} (expected WR ~{expected_wr:.0f}%)",
            picks=picks,
            regime=f"SPY+{spy_daily:.1f}% AD{ad_ratio:.1f} VIX{vix:.0f}",
            metadata={
                'bucket': bucket,
                'threshold_75': threshold,
                'expected_wr': expected_wr,
                'model_version': 'prod_v2_ensemble5',
            },
        )
