"""
ORB Pre-market Prep — watchlist generation (03:00-09:30 ET).

Thesis: Before market open, identify stocks likely to qualify for the
morning_drive entry window (09:50-10:45). This is NOT a BUY signal
strategy — it produces a watchlist that the trader monitors at open.

Output:
- Up to 10 candidates with PM gap, 5d momentum, volume, catalyst info
- Key levels: PDH, PDL, previous close
- No entry signals, no SL/TP (not ready to trade yet)

What this strategy does:
1. Scan universe 200 + hot inject (stocks with 5%+ move yesterday)
2. Identify pre-market gap candidates (PM gap ±2% or 5d ±5%)
3. Enrich with sector / catalyst / beta / earnings context
4. Output sorted list by mix of gap size + 5d momentum + catalyst

Why no BUY signals:
- At 03:00-09:30 we don't know opening print, can't measure gain-from-open
- Morning_drive's edge (gain 3-5% at 09:50) requires knowing open price
- Entering at prev_close → hold is different strategy (OVN-like)
"""
import os
import sqlite3
import requests
import numpy as np
from dotenv import load_dotenv

from .base import BaseStrategy, ScanResult, Pick

load_dotenv()


class OrbPrepStrategy(BaseStrategy):
    name = "orb_prep"
    description = "Pre-market watchlist generation (03:00-09:30 ET)"
    expected_wr = 0.0  # not a trade strategy, no WR
    expected_ev = 0.0
    time_start = "03:00"
    time_end = "09:30"
    version = "1.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 3.0
    MIN_ABS_GAP = 2.0       # |gap| >= 2% to be watchable
    MIN_5D_ABS_MOM = 5.0    # OR 5d momentum >= 5%
    MIN_VOL_RATIO = 1.0     # loose — PM vol typically low
    MAX_WATCHLIST = 15

    def scan(self) -> ScanResult:
        if not self.in_time_window():
            return self.out_of_window()

        conn = sqlite3.connect(self.DB_PATH)
        try:
            # Macro context
            br = conn.execute("SELECT ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1").fetchone()
            ad_ratio = float(br[0]) if br and br[0] else 0.0
            spy_rows = conn.execute("SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 2").fetchall()
            spy_daily = (spy_rows[0][0] / spy_rows[1][0] - 1) * 100 if len(spy_rows) >= 2 else 0
            vix_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
            vix = float(vix_row[0]) if vix_row else 20.0

            syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
            hot = [r[0] for r in conn.execute("""
                SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
                JOIN universe_stocks u ON d.symbol = u.symbol
                WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
                AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
                AND ABS(d.close - d.open) * 1.0 / d.open >= 0.05
                AND d.volume * d.close >= 20000000
            """).fetchall()]
            syms = list(set(syms + hot))

            sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
            betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())

            # Earnings flag (for context, not skip)
            earnings_today = set(r[0] for r in conn.execute(
                "SELECT symbol FROM earnings_calendar WHERE next_earnings_date = date('now')"
            ).fetchall())

            # News catalyst context (last 12h positive)
            news_syms = set(r[0] for r in conn.execute("""
                SELECT DISTINCT symbol FROM news_events
                WHERE published_at >= datetime('now','-12 hours')
                AND sentiment_label IN ('positive','very_positive')
            """).fetchall())

            # 5d history for momentum
            hist = {}
            for r in conn.execute("""
                SELECT symbol, date, open, high, low, close, volume FROM stock_daily_ohlc
                WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-7 days')
                ORDER BY symbol, date
            """):
                hist.setdefault(r[0], []).append(r[1:])

            # Previous day high/low/close (PDH/PDL) from latest daily bar
            pdh_pdl = {}
            for r in conn.execute("""
                SELECT symbol, high, low, close FROM stock_daily_ohlc
                WHERE date = (SELECT MAX(date) FROM stock_daily_ohlc)
            """):
                pdh_pdl[r[0]] = (r[1], r[2], r[3])
        finally:
            conn.close()

        # Alpaca snapshots for pre-market data
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

        candidates = []
        for sym in syms:
            s = snaps.get(sym)
            days = hist.get(sym, [])
            if not s or len(days) < 3:
                continue

            db = s.get('dailyBar', {})
            lt = s.get('latestTrade', {})
            yest_close = db.get('c', 0)
            if yest_close < self.MIN_PRICE:
                continue

            # PM price from latestTrade (may be stale if no PM activity)
            pm_price = lt.get('p', yest_close) if lt else yest_close
            pm_gap = (pm_price / yest_close - 1) * 100 if yest_close > 0 else 0

            # 5d momentum from historical
            d0 = days[0]
            mom5d = (yest_close / d0[3] - 1) * 100 if d0[3] else 0

            # Must qualify on either PM gap OR 5d momentum
            if abs(pm_gap) < self.MIN_ABS_GAP and abs(mom5d) < self.MIN_5D_ABS_MOM:
                continue

            # Previous day data
            pdh, pdl, prev_close = pdh_pdl.get(sym, (yest_close, yest_close, yest_close))

            beta = betas.get(sym)
            sec = sectors.get(sym, '')
            has_news = sym in news_syms
            has_earnings = sym in earnings_today

            # Classification
            if mom5d >= 10 and pm_gap >= 0:
                tag = 'HOT_STREAK'
            elif mom5d >= 5 and pm_gap > 0:
                tag = 'MOMENTUM'
            elif mom5d <= -5 and pm_gap >= 0:
                tag = 'REVERSAL'
            elif pm_gap >= 2:
                tag = 'GAP_UP'
            elif pm_gap <= -2:
                tag = 'GAP_DOWN'
            else:
                tag = 'WATCH'

            reason_bits = [tag, f"PM{pm_gap:+.1f}%", f"5d{mom5d:+.1f}%"]
            if beta is not None:
                reason_bits.append(f"β{beta:.1f}")
            if sec:
                reason_bits.append(sec[:6])
            if has_news:
                reason_bits.append("news")
            if has_earnings:
                reason_bits.append("EARN⚠️")
            reason = " ".join(reason_bits)

            # Watchlist pick (no SL/TP since not trading yet)
            pick = Pick(
                symbol=sym,
                entry=pm_price,
                sl_price=0.0,  # not set — wait for open
                tp_price=None,
                reason=reason,
                score=None,
                atr_pct=None,
                extra={
                    'tag': tag,
                    'pm_gap': round(pm_gap, 2),
                    'mom5d': round(mom5d, 2),
                    'yest_close': round(yest_close, 2),
                    'pdh': round(pdh, 2),
                    'pdl': round(pdl, 2),
                    'beta': round(beta, 2) if beta else None,
                    'sector': sec,
                    'has_news': has_news,
                    'has_earnings': has_earnings,
                },
            )
            candidates.append(pick)

        if not candidates:
            return self.no_picks("No stocks meet PM watchlist criteria")

        # Rank: earnings first (riskier but most volatile), then by combined gap+mom magnitude
        def rank_key(p):
            mag = abs(p.extra['pm_gap']) + abs(p.extra['mom5d']) / 3
            return (-mag,)
        candidates.sort(key=rank_key)

        # Diversify max 3 per sector (looser for watchlist)
        sec_count = {}
        picks = []
        for c in candidates:
            sec = c.extra['sector']
            if sec_count.get(sec, 0) >= 3:
                continue
            sec_count[sec] = sec_count.get(sec, 0) + 1
            picks.append(c)
            if len(picks) >= self.MAX_WATCHLIST:
                break

        return ScanResult(
            strategy=self.name,
            timestamp_et=self.time_et_str(),
            status='active',
            reason=f"{len(candidates)} watchlist candidates → top {len(picks)} (for 09:50 entry)",
            picks=picks,
            regime=f"SPY{spy_daily:+.1f}% AD{ad_ratio:.1f} VIX{vix:.0f}",
            metadata={
                'ad_ratio': round(ad_ratio, 2),
                'spy_daily': round(spy_daily, 2),
                'vix': round(vix, 1),
                'note': 'WATCHLIST ONLY — no entries until 09:50',
            },
        )
