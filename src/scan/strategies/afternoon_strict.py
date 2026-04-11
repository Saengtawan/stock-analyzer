"""
Afternoon Strict Continuation — secondary intraday strategy.

Thesis: Stocks that are still making fresh highs into early afternoon
(13:00-13:30), with volume confirming and market supportive, have
unusually high continuation rate — backtest shows WR 65.2% when ALL
strict filters met, vs baseline 51% for loose 13:00 entries.

Backtest findings (Phase 1 + 2, 2025+ data):
- 13:00 baseline +3-8% gain: 51.8% WR, +0.31% EV (no edge)
- 13:00 + fresh peak + vol 1.5x + SPY green: 65.2% WR, +2.79% EV ⭐
- 12:00 requires SPY green: 56.1% WR
- 14:00+ no filter rescues the dead zone

This strategy runs for a 30-min window only. All 4 strict filters
required. Few picks per day (sparse), high conviction.
"""
import os
import sqlite3
import requests
import numpy as np
from dotenv import load_dotenv

from .base import BaseStrategy, ScanResult, Pick

load_dotenv()


class AfternoonStrictStrategy(BaseStrategy):
    name = "afternoon_strict"
    description = "13:00-13:30 strict afternoon continuation (fresh peak + vol + SPY green)"
    expected_wr = 0.65
    expected_ev = 0.0279  # +2.79%
    time_start = "13:00"
    time_end = "13:30"
    version = "1.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 3.0
    MIN_GAIN = 3.0
    MAX_GAIN = 8.0
    MIN_BETA = 1.0
    MAX_BETA = 2.0
    MIN_AD = 2.0
    MIN_VOL_PACE = 1.5
    MAX_VIX = 30.0
    STALE_THRESHOLD = -1.5  # must be within 1.5% of day's high
    SL_MIN_PCT = 2.0        # wider than morning (afternoon entries)
    SL_ATR_MULT = 0.5
    TP_MIN_PCT = 3.5
    TP_ATR_MULT = 1.0
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
            if len(spy_rows) < 2:
                return self.gate_failed("No SPY data")
            spy_daily = (spy_rows[0][0] / spy_rows[1][0] - 1) * 100
            if spy_daily <= 0:
                return self.gate_failed(f"SPY {spy_daily:+.2f}% red (required green)")

            vix_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
            vix = float(vix_row[0]) if vix_row else 20.0
            if vix >= self.MAX_VIX:
                return self.gate_failed(f"VIX {vix:.1f} ≥ {self.MAX_VIX}")

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

        # Compute sector day returns (for sector-positive filter)
        sector_today_avg = {}
        sec_rets = {}
        for sym in syms:
            s = snaps.get(sym, {})
            db = s.get('dailyBar', {}); pb = s.get('prevDailyBar', {})
            pc = pb.get('c', 0); now = db.get('c', 0)
            if pc > 0 and now > 0:
                sec = sectors.get(sym)
                if sec:
                    sec_rets.setdefault(sec, []).append((now / pc - 1) * 100)
        sector_today_avg = {s: np.mean(v) for s, v in sec_rets.items() if len(v) >= 5}

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
            vol = db.get('v', 0); pb = s.get('prevDailyBar', {})
            prev_vol = pb.get('v', 1)
            if opn < 1 or now < self.MIN_PRICE:
                continue

            gain = (now / opn - 1) * 100
            if not (self.MIN_GAIN <= gain < self.MAX_GAIN):
                continue

            beta = betas.get(sym)
            if beta is None or not (self.MIN_BETA <= beta < self.MAX_BETA):
                continue

            # Strict filter 1: Fresh peak (not stale >1.5% below high)
            from_peak_pct = (now / hi - 1) * 100 if hi > 0 else 0
            if from_peak_pct < self.STALE_THRESHOLD:
                continue

            # Strict filter 2: Volume surge — using vol ratio as proxy for pace
            # (at 13:00 we have ~52% of expected daily volume)
            vol_ratio = vol / prev_vol if prev_vol > 0 else 0
            # expected at 13:00 = ~0.52 of full day, so vol_ratio should be ≥ 0.78 (1.5 × 0.52)
            if vol_ratio < 0.78:
                continue

            # Strict filter 3: Sector positive today
            sec = sectors.get(sym, '')
            sec_today = sector_today_avg.get(sec, 0)
            if sec_today < 0.3:  # sector must be positive by 0.3%+
                continue

            atr_pct = (hi - lo) / now * 100 if now > 0 else 3.0
            sl_pct = -max(self.SL_MIN_PCT, self.SL_ATR_MULT * atr_pct)
            tp_pct = max(self.TP_MIN_PCT, self.TP_ATR_MULT * atr_pct)
            sl_price = now * (1 + sl_pct / 100)
            tp_price = now * (1 + tp_pct / 100)

            score = 9  # all 4 strict filters passed = max score
            reason = (
                f"gap+{gain:.1f}% β{beta:.1f} fresh(-{abs(from_peak_pct):.1f}%) "
                f"vol{vol_ratio:.1f}x {sec[:6]}+{sec_today:.1f}% "
                f"SPY+{spy_daily:.1f}%"
            )

            pick = Pick(
                symbol=sym, entry=now,
                sl_price=round(sl_price, 2), tp_price=round(tp_price, 2),
                trail_pct=self.TRAIL_PCT, reason=reason, score=score,
                atr_pct=atr_pct,
                extra={
                    'gain_pct': round(gain, 2),
                    'beta': round(beta, 2),
                    'sector': sec,
                    'sl_pct': round(sl_pct, 2),
                    'tp_pct': round(tp_pct, 2),
                    'from_peak': round(from_peak_pct, 2),
                    'sec_today': round(sec_today, 2),
                },
            )
            candidates.append(pick)

        if not candidates:
            return self.no_picks("No stocks pass all 4 strict filters")

        candidates.sort(key=lambda p: (p.extra['beta'], p.extra['from_peak']))

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
            reason=f"{len(candidates)} strict candidates → top {len(picks)}",
            picks=picks,
            regime=f"SPY+{spy_daily:.1f}% AD{ad_ratio:.1f} VIX{vix:.0f}",
            metadata={
                'ad_ratio': round(ad_ratio, 2),
                'spy_daily': round(spy_daily, 2),
                'vix': round(vix, 1),
                'candidates_count': len(candidates),
            },
        )
