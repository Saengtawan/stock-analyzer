"""
Morning Drive Continuation — primary intraday strategy.

Thesis: Stocks that gap up or break out in the first 30min tend to continue
for another 30-60min before momentum fades. Enter during the 09:50-10:45
window when 3-5% gain + SPY support + reasonable volume confirms the move.

Backtest findings (2025+, 20M 5-min bars, 274K symbol-days):
- Baseline 10:00 entry +3-8% gain = 57% WR, +0.88% EV
- 09:50-10:45 sustained edge window (54-57% WR)
- Sweet spot gain = 3-5% (57% WR +0.86% EV)
- SPY green adds +8pp WR at 10:00
- Beta 1.0-2.0 sweet spot (60% WR)
- Trail 1% from peak = best EV (+0.93%) beats fixed TP/SL
- SL -0.5% = 28% WR (noise stops) → use -1.5% minimum

Hard filters (backtest-validated):
- SPY green daily (required)
- AD ratio ≥ 2 (required)
- Gain 3-5% from open (sweet spot)
- Beta 1.0-2.0
- VIX < 30 (else different regime)
- No earnings today/tomorrow
- Not overextended (chg <= 5%, not chase)

Rejected from v1 (flawed or invalid):
- Sec3d bonus (look-ahead bug found)
- Catalyst bonus (backtest: hurts momentum 58% vs 40% insider)
- Intraday bounce mode (42-52% across all drops — no edge)
- Tight SL -0.5% (noise stops)
"""
import os
import sqlite3
import requests
import numpy as np
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv

from .base import BaseStrategy, ScanResult, Pick, ET

load_dotenv()

TIME_START = "09:50"
TIME_END = "10:45"


class MorningDriveStrategy(BaseStrategy):
    name = "morning_drive"
    description = "09:50-10:45 momentum continuation, gain 3-5% entries"
    expected_wr = 0.60
    expected_ev = 0.0088  # +0.88% per trade
    time_start = TIME_START
    time_end = TIME_END
    version = "1.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 3.0
    MIN_GAIN = 3.0
    MAX_GAIN = 5.0
    MIN_BETA = 1.0
    MAX_BETA = 2.0
    MIN_AD = 2.0
    MAX_VIX = 30.0
    SL_MIN_PCT = 1.5    # min SL distance
    SL_ATR_MULT = 0.5   # or 0.5 * ATR
    TP_MIN_PCT = 3.0
    TP_ATR_MULT = 1.0
    TRAIL_PCT = 1.0     # trail 1% from peak
    MAX_PICKS = 3

    def scan(self) -> ScanResult:
        # 1. Time window check
        if not self.in_time_window():
            return self.out_of_window()

        # 2. Load gates + data
        conn = sqlite3.connect(self.DB_PATH)
        try:
            # AD gate
            br = conn.execute(
                "SELECT ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1"
            ).fetchone()
            ad_ratio = float(br[0]) if br and br[0] else 0.0
            if ad_ratio < self.MIN_AD:
                return self.gate_failed(f"AD ratio {ad_ratio:.2f} < {self.MIN_AD} (no edge)")

            # SPY direction + VIX
            spy_rows = conn.execute(
                "SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 2"
            ).fetchall()
            if len(spy_rows) < 2:
                return self.gate_failed("No SPY data")
            spy_daily = (spy_rows[0][0] / spy_rows[1][0] - 1) * 100
            if spy_daily <= 0:
                return self.gate_failed(f"SPY {spy_daily:+.2f}% red (hard skip per backtest)")

            vix_row = conn.execute(
                "SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1"
            ).fetchone()
            vix = float(vix_row[0]) if vix_row else 20.0
            if vix >= self.MAX_VIX:
                return self.gate_failed(f"VIX {vix:.1f} ≥ {self.MAX_VIX} — wrong regime (use crisis_reversal)")

            # Universe
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

            # Metadata
            betas = dict(conn.execute(
                "SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL"
            ).fetchall())
            earnings_skip = set(r[0] for r in conn.execute("""
                SELECT symbol FROM earnings_calendar
                WHERE next_earnings_date IN (date('now'), date('now','+1 day'))
            """).fetchall())
            sectors = dict(conn.execute(
                "SELECT symbol, sector FROM universe_stocks"
            ).fetchall())
        finally:
            conn.close()

        # 3. Fetch Alpaca snapshots
        hdr = {
            'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'),
            'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY'),
        }
        snaps = {}
        for i in range(0, len(syms), 100):
            batch = ','.join(syms[i:i+100])
            r = requests.get(
                f'https://data.alpaca.markets/v2/stocks/snapshots?symbols={batch}',
                headers=hdr, timeout=15,
            )
            if r.status_code == 200:
                snaps.update(r.json())

        # 4. Filter candidates per entry criteria
        candidates = []
        for sym in syms:
            if sym in earnings_skip:
                continue
            s = snaps.get(sym)
            if not s:
                continue
            db = s.get('dailyBar', {})
            opn = db.get('o', 0)
            now = db.get('c', 0)
            hi = db.get('h', 0)
            lo = db.get('l', 0)
            if opn < 1 or now < self.MIN_PRICE:
                continue

            gain = (now / opn - 1) * 100
            if not (self.MIN_GAIN <= gain < self.MAX_GAIN):
                continue

            beta = betas.get(sym)
            if beta is None or not (self.MIN_BETA <= beta < self.MAX_BETA):
                continue

            # Intraday range as ATR proxy
            atr_pct = (hi - lo) / now * 100 if now > 0 else 3.0

            # SL/TP
            sl_pct = -max(self.SL_MIN_PCT, self.SL_ATR_MULT * atr_pct)
            tp_pct = max(self.TP_MIN_PCT, self.TP_ATR_MULT * atr_pct)
            sl_price = now * (1 + sl_pct / 100)
            tp_price = now * (1 + tp_pct / 100)

            # Score (simplified — most factors are hard gates)
            score = 2  # SPY green (required)
            score += 2  # AD ≥ 2 (required)
            score += 1  # gain in sweet spot (required)
            score += 1  # beta in sweet spot (required)
            # Bonus factors
            if 20 <= vix < 30:
                score += 1  # mid-vol edge
            sec = sectors.get(sym, '')

            reason = (
                f"gap +{gain:.1f}% β{beta:.1f} ATR{atr_pct:.1f}% {sec[:6]} "
                f"SPY+{spy_daily:.1f}% AD{ad_ratio:.1f} VIX{vix:.0f}"
            )

            pick = Pick(
                symbol=sym,
                entry=now,
                sl_price=round(sl_price, 2),
                tp_price=round(tp_price, 2),
                trail_pct=self.TRAIL_PCT,
                reason=reason,
                score=score,
                atr_pct=atr_pct,
                extra={
                    'gain_pct': round(gain, 2),
                    'beta': round(beta, 2),
                    'sector': sec,
                    'sl_pct': round(sl_pct, 2),
                    'tp_pct': round(tp_pct, 2),
                },
            )
            candidates.append(pick)

        if not candidates:
            return self.no_picks("No stocks with gap 3-5% + β 1-2 in window")

        # 5. Sort by score, then beta low (less volatile preferred within sweet spot)
        candidates.sort(key=lambda p: (-p.score, p.extra['beta']))

        # 6. Diversify: max 2 per sector
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
            reason=f"{len(candidates)} candidates → top {len(picks)}",
            picks=picks,
            regime=f"SPY+{spy_daily:.1f}% AD{ad_ratio:.1f} VIX{vix:.0f}",
            metadata={
                'ad_ratio': round(ad_ratio, 2),
                'spy_daily': round(spy_daily, 2),
                'vix': round(vix, 1),
                'candidates_count': len(candidates),
            },
        )
