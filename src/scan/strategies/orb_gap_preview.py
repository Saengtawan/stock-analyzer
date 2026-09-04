"""
ORB Gap Preview (04:00-09:29) — preview gap candidates BEFORE market open.

Thesis: Same as orb_gap_break but uses PM (pre-market) latestTrade as
proxy for expected opening gap. At 04:00 PM just started, signal is
weak. At 09:25, PM price is usually within 0.5% of actual open.

⚠️ Pre-market prices can diverge from open — PM accuracy improves as
09:30 approaches. Treat as WATCHLIST, not committed entry.

Output:
- Top 5-10 stocks with PM gap ≥ 3% vs prev close
- Shows expected entry size per orb_gap_break rules
- Confidence: higher if closer to 09:30
- At 09:30, run orb_gap_break for actual entry

Usage flow:
  04:00-06:00: directional early warning (PM thin, low confidence)
  06:00-08:00: conviction builds, institutional trading active
  08:00-09:29: high confidence, final picks
  09:30: orb_gap_break takes over with real open price
"""
import os
import sqlite3
import requests
from datetime import datetime
from dotenv import load_dotenv

from .base import BaseStrategy, ScanResult, Pick, ET

load_dotenv()


class OrbGapPreviewStrategy(BaseStrategy):
    name = "orb_gap_preview"
    description = "04:00-09:29 pre-market gap preview (uses PM price as open proxy)"
    expected_wr = 0.815   # same as orb_gap_break if PM ≈ open
    expected_ev = 0.0046
    time_start = "04:00"
    time_end = "09:29"
    version = "1.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 3.0
    MIN_GAP = 3.0        # slightly looser (3% vs 5%) for preview
    MAX_GAP = 25.0
    MAX_PICKS = 10       # show more for watchlist

    def scan(self) -> ScanResult:
        if not self.in_time_window():
            return self.out_of_window()

        now_et = datetime.now(ET)
        mins_to_open = (9 - now_et.hour) * 60 + (30 - now_et.minute)
        # Confidence bucket
        if mins_to_open > 180:       # before 06:30
            confidence = 'LOW'
            conf_note = 'PM thin — low confidence, directional only'
        elif mins_to_open > 60:      # 06:30-08:30
            confidence = 'MED'
            conf_note = 'PM building — medium confidence'
        else:                        # within 60 min of open
            confidence = 'HIGH'
            conf_note = 'Close to open — high confidence, prep orders'

        conn = sqlite3.connect(self.DB_PATH)
        try:
            syms = [r[0] for r in conn.execute(
                "SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200"
            ).fetchall()]
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
            earnings_skip = set(r[0] for r in conn.execute(
                "SELECT symbol FROM earnings_calendar WHERE next_earnings_date IN (date('now'), date('now','+1 day'))"
            ).fetchall())
            news_syms = set(r[0] for r in conn.execute("""
                SELECT DISTINCT symbol FROM news_events
                WHERE published_at >= datetime('now','-12 hours')
                AND sentiment_label IN ('positive','very_positive')
            """).fetchall())

            # Prev day close for gap calc
            prev_close = {}
            for r in conn.execute("""
                SELECT symbol, close FROM stock_daily_ohlc
                WHERE date = (SELECT MAX(date) FROM stock_daily_ohlc)
            """):
                prev_close[r[0]] = r[1]
        finally:
            conn.close()

        # Fetch snapshots to get latestTrade (PM price)
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
            if sym in earnings_skip: continue
            if sym == 'SPY': continue
            s = snaps.get(sym)
            if not s: continue

            # Use latestTrade as PM price proxy
            lt = s.get('latestTrade', {})
            pm_price = lt.get('p', 0)
            pm_ts = lt.get('t', '')
            if pm_price < self.MIN_PRICE: continue

            pc = prev_close.get(sym)
            if not pc:
                db = s.get('dailyBar', {})
                pc = db.get('c', 0)
            if not pc or pc <= 0: continue

            pm_gap = (pm_price / pc - 1) * 100
            if not (self.MIN_GAP <= pm_gap < self.MAX_GAP): continue

            sec = sectors.get(sym, '')
            has_news = sym in news_syms

            # Score by gap size + news bonus
            score = int(min(9, pm_gap / 3))  # 0-9 by gap size
            if has_news: score = min(9, score + 1)

            reason_bits = [f"PM gap +{pm_gap:.1f}%", f"PM=${pm_price:.2f}", f"prev=${pc:.2f}"]
            if sec: reason_bits.append(sec[:6])
            if has_news: reason_bits.append('news')
            reason_bits.append(f'[{confidence}]')

            candidates.append(Pick(
                symbol=sym,
                entry=pm_price,
                sl_price=round(pm_price * 0.99, 2),  # provisional
                tp_price=round(pm_price * 1.02, 2),
                trail_pct=1.0,
                reason=' '.join(reason_bits),
                score=score,
                extra={
                    'pm_gap': round(pm_gap, 2),
                    'pm_price': round(pm_price, 2),
                    'prev_close': round(pc, 2),
                    'sector': sec,
                    'has_news': has_news,
                    'pm_timestamp': pm_ts[:19] if pm_ts else '',
                    'confidence': confidence,
                    'mins_to_open': mins_to_open,
                },
            ))

        if not candidates:
            return self.no_picks(
                f"No PM gap ≥ {self.MIN_GAP}% yet ({mins_to_open}min to open, {confidence})"
            )

        # Sort by gap size descending
        candidates.sort(key=lambda p: -p.extra['pm_gap'])
        picks = candidates[:self.MAX_PICKS]

        return ScanResult(
            strategy=self.name,
            timestamp_et=self.time_et_str(),
            status='active',
            reason=(
                f"{len(candidates)} PM gap candidates → top {len(picks)} "
                f"| {confidence} confidence ({mins_to_open}min to open) | {conf_note}"
            ),
            picks=picks,
            regime=f"Pre-market {confidence}",
            metadata={
                'confidence': confidence,
                'mins_to_open': mins_to_open,
                'note': 'WATCHLIST — at 09:30 run orb_gap_break for actual entries with real open prices',
            },
        )
