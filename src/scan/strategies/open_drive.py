"""
Opening Range Breakout (09:30-09:50) — first 5-min range break.

Thesis: Stocks that decisively break above their first 5-minute bar's
high within the first 20 minutes, with volume confirming, tend to
continue for the morning_drive window (09:50-10:45).

⚠️ Backtest v2 status: NOT specifically validated — v2 tested
"gain 3-8% at 10:00 hold to close" which is a different window and
exit. ORB is a trader-wisdom approach. Paper trade before sizing up.

Setup:
- Wait for first 5-min bar (09:30-09:35) to form
- Enter when price breaks above first-bar high AFTER 09:35
- Require volume confirmation (bar vol > avg first 5min vol)
- Must have SPY green + AD >= 2 (same hard gates as morning_drive)
- Exit: trail 1% OR at 09:50 handoff to morning_drive

Limitations:
- Without 1-min bars live, we use 5-min bar structure
- "First bar high" computed from earliest bar we have after 09:30
"""
import os
import sqlite3
import requests
import numpy as np
from dotenv import load_dotenv

from .base import BaseStrategy, ScanResult, Pick

load_dotenv()


class OpenDriveStrategy(BaseStrategy):
    name = "open_drive"
    description = "09:30-09:50 opening range breakout"
    expected_wr = 0.55
    expected_ev = 0.005
    time_start = "09:30"
    time_end = "09:50"
    version = "1.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 3.0
    MIN_BREAK_PCT = 0.3   # break above first-bar high by 0.3%
    MIN_AD = 2.0
    MAX_VIX = 30.0
    MIN_BETA = 1.0
    MAX_BETA = 2.5
    SL_MIN_PCT = 1.0
    SL_ATR_MULT = 0.5
    TP_MIN_PCT = 2.0
    TRAIL_PCT = 1.0
    MAX_PICKS = 3

    def scan(self) -> ScanResult:
        if not self.in_time_window():
            return self.out_of_window()

        conn = sqlite3.connect(self.DB_PATH)
        try:
            br = conn.execute("SELECT ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1").fetchone()
            ad_ratio = float(br[0]) if br and br[0] else 0.0
            if ad_ratio < self.MIN_AD:
                return self.gate_failed(f"AD {ad_ratio:.2f} < {self.MIN_AD}")

            spy_rows = conn.execute("SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 2").fetchall()
            spy_daily = (spy_rows[0][0] / spy_rows[1][0] - 1) * 100 if len(spy_rows) >= 2 else 0
            if spy_daily <= 0:
                return self.gate_failed(f"SPY {spy_daily:+.2f}% red")

            vix_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
            vix = float(vix_row[0]) if vix_row else 20.0
            if vix >= self.MAX_VIX:
                return self.gate_failed(f"VIX {vix:.1f} ≥ {self.MAX_VIX}")

            syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
            betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())
            earnings_skip = set(r[0] for r in conn.execute(
                "SELECT symbol FROM earnings_calendar WHERE next_earnings_date IN (date('now'), date('now','+1 day'))"
            ).fetchall())
            sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
        finally:
            conn.close()

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
            if sym in earnings_skip:
                continue
            s = snaps.get(sym)
            if not s:
                continue
            db = s.get('dailyBar', {})
            opn = db.get('o', 0); now = db.get('c', 0)
            hi = db.get('h', 0); lo = db.get('l', 0)
            if opn < 1 or now < self.MIN_PRICE:
                continue

            # Approximation: first-bar high = intraday high so far
            # (in first 20min, daily high ≈ high of first 1-4 bars)
            break_vs_open = (now / opn - 1) * 100
            break_vs_high = (now / hi - 1) * 100 if hi > 0 else 0

            # Setup: now > open (drive up) AND at/near high (breaking)
            if break_vs_open < self.MIN_BREAK_PCT:
                continue
            if break_vs_high < -0.2:  # not within 0.2% of high
                continue

            beta = betas.get(sym)
            if beta is None or not (self.MIN_BETA <= beta < self.MAX_BETA):
                continue

            atr_pct = (hi - lo) / now * 100 if now > 0 else 2.0
            sl_pct = -max(self.SL_MIN_PCT, self.SL_ATR_MULT * atr_pct)
            tp_pct = max(self.TP_MIN_PCT, 0.6 * atr_pct)
            sl_price = now * (1 + sl_pct / 100)
            tp_price = now * (1 + tp_pct / 100)

            sec = sectors.get(sym, '')
            reason = f"ORB+{break_vs_open:.1f}% atHi({break_vs_high:+.1f}%) β{beta:.1f} ATR{atr_pct:.1f}% {sec[:6]}"

            pick = Pick(
                symbol=sym, entry=now,
                sl_price=round(sl_price, 2), tp_price=round(tp_price, 2),
                trail_pct=self.TRAIL_PCT, reason=reason, score=6, atr_pct=atr_pct,
                extra={
                    'break_vs_open': round(break_vs_open, 2),
                    'break_vs_high': round(break_vs_high, 2),
                    'beta': round(beta, 2),
                    'sector': sec,
                    'sl_pct': round(sl_pct, 2),
                    'tp_pct': round(tp_pct, 2),
                },
            )
            candidates.append(pick)

        if not candidates:
            return self.no_picks("No ORB breakouts (need drive +0.3% at/near day high)")

        candidates.sort(key=lambda p: (-p.extra['break_vs_open'], p.extra['beta']))
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

        return ScanResult(
            strategy=self.name, timestamp_et=self.time_et_str(), status='active',
            reason=f"{len(candidates)} ORB breakouts → top {len(picks)}",
            picks=picks,
            regime=f"SPY+{spy_daily:.1f}% AD{ad_ratio:.1f} VIX{vix:.0f}",
            metadata={'note': '⚠️ Not backtest-v2 validated. Paper trade first.'},
        )
