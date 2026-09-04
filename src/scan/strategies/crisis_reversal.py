"""
Crisis Reversal — contrarian strategy for high-VIX regimes.

Thesis: When VIX > 30 AND SPY breaks higher, forced covering and
capitulation bounces dominate. Normal momentum rules don't apply —
the best edge comes from buying oversold stocks as fear peaks.

Backtest findings (Phase 1, 2025+ data):
- VIX > 30 + SPY green: 79.2% WR, +5.84% EV (N=130, rare but clear)
- 5d down <-10% baseline: 73.4% WR, +3.16% EV (N=346)
- Combined: extreme-drop stocks during crisis = highest edge found

This strategy only activates when VIX > 25 (crisis regime threshold).
Rare setup — may yield 0 picks most days.
"""
import os
import sqlite3
import requests
import numpy as np
from dotenv import load_dotenv

from .base import BaseStrategy, ScanResult, Pick

load_dotenv()


class CrisisReversalStrategy(BaseStrategy):
    name = "crisis_reversal"
    description = "High-VIX contrarian bounce (VIX>25, 5d down <-10%)"
    expected_wr = 0.75
    expected_ev = 0.0300
    time_start = "09:30"
    time_end = "14:00"
    version = "1.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 3.0
    MIN_VIX = 25.0
    MIN_BETA = 0.5
    MAX_BETA = 2.0
    MIN_5D_DROP = -10.0  # stock must be down 10%+ in last 5 days
    SL_MIN_PCT = 2.5     # wide SL for crisis vol
    SL_ATR_MULT = 0.5
    TP_MIN_PCT = 5.0     # larger TP in crisis moves
    TP_ATR_MULT = 1.0
    TRAIL_PCT = 2.0      # wider trail in high vol
    MAX_PICKS = 3

    def scan(self) -> ScanResult:
        if not self.in_time_window():
            return self.out_of_window()

        conn = sqlite3.connect(self.DB_PATH)
        try:
            vix_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
            vix = float(vix_row[0]) if vix_row else 20.0
            if vix < self.MIN_VIX:
                return self.gate_failed(f"VIX {vix:.1f} < {self.MIN_VIX} — not crisis regime, use morning_drive")

            spy_rows = conn.execute("SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 2").fetchall()
            if len(spy_rows) < 2:
                return self.gate_failed("No SPY data")
            spy_daily = (spy_rows[0][0] / spy_rows[1][0] - 1) * 100
            if spy_daily <= 0:
                return self.gate_failed(f"SPY {spy_daily:+.2f}% — crisis reversal needs SPY bouncing (green)")

            syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
            betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())
            earnings_skip = set(r[0] for r in conn.execute(
                "SELECT symbol FROM earnings_calendar WHERE next_earnings_date IN (date('now'), date('now','+1 day'))"
            ).fetchall())
            sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())

            # 5-day history for momentum calc
            hist = {}
            for r in conn.execute("""
                SELECT symbol, date, open, high, low, close, volume FROM stock_daily_ohlc
                WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-7 days')
                ORDER BY symbol, date
            """):
                hist.setdefault(r[0], []).append(r[1:])
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
            days = hist.get(sym, [])
            if not s or len(days) < 5:
                continue
            db = s.get('dailyBar', {})
            now = db.get('c', 0)
            opn = db.get('o', 0)
            hi = db.get('h', 0)
            lo = db.get('l', 0)
            if now < self.MIN_PRICE or opn < 1:
                continue

            d0 = days[0]
            mom5d = (now / d0[3] - 1) * 100 if d0[3] else 0
            if mom5d > self.MIN_5D_DROP:  # not dropped enough
                continue

            beta = betas.get(sym)
            if beta is None or not (self.MIN_BETA <= beta < self.MAX_BETA):
                continue

            atr_pct = (hi - lo) / now * 100 if now > 0 else 4.0
            sl_pct = -max(self.SL_MIN_PCT, self.SL_ATR_MULT * atr_pct)
            tp_pct = max(self.TP_MIN_PCT, self.TP_ATR_MULT * atr_pct)
            sl_price = now * (1 + sl_pct / 100)
            tp_price = now * (1 + tp_pct / 100)

            score = 9
            sec = sectors.get(sym, '')
            reason = f"5d{mom5d:+.1f}% β{beta:.1f} ATR{atr_pct:.1f}% VIX{vix:.0f} SPY+{spy_daily:.1f}% {sec[:6]}"

            pick = Pick(
                symbol=sym, entry=now,
                sl_price=round(sl_price, 2), tp_price=round(tp_price, 2),
                trail_pct=self.TRAIL_PCT, reason=reason, score=score,
                atr_pct=atr_pct,
                extra={
                    'mom5d': round(mom5d, 2),
                    'beta': round(beta, 2),
                    'sector': sec,
                    'sl_pct': round(sl_pct, 2),
                    'tp_pct': round(tp_pct, 2),
                },
            )
            candidates.append(pick)

        if not candidates:
            return self.no_picks("No stocks with 5d < -10% and VIX crisis conditions")

        # Sort by deepest drop (most oversold first)
        candidates.sort(key=lambda p: p.extra['mom5d'])

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
            strategy=self.name,
            timestamp_et=self.time_et_str(),
            status='active',
            reason=f"{len(candidates)} crisis candidates → top {len(picks)}",
            picks=picks,
            regime=f"CRISIS VIX{vix:.0f} SPY+{spy_daily:.1f}%",
            metadata={'vix': round(vix, 1), 'spy_daily': round(spy_daily, 2)},
        )
