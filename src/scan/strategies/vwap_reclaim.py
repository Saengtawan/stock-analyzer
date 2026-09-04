"""
VWAP Reclaim (13:30-15:30) — afternoon trend resumption.

Thesis: Stocks that dipped below VWAP in the morning/lunch and reclaim
it in the afternoon often resume the daily trend into close. The reclaim
represents institutional demand returning after lunch.

⚠️ Not backtest-v2 validated. Paper trade first.

Setup:
- Current price > VWAP (reclaim happened)
- Stock had intraday drop (low < VWAP significantly)
- Daily change positive (not a dead stock)
- SPY green + AD >= 2
"""
import os
import sqlite3
import requests
import numpy as np
from dotenv import load_dotenv

from .base import BaseStrategy, ScanResult, Pick

load_dotenv()


class VwapReclaimStrategy(BaseStrategy):
    name = "vwap_reclaim"
    description = "13:30-15:30 VWAP reclaim after intraday dip"
    expected_wr = 0.52
    expected_ev = 0.004
    time_start = "13:30"
    time_end = "15:30"
    version = "1.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 3.0
    MIN_VS_VWAP = 0.1       # at least 0.1% above VWAP (reclaimed)
    MAX_VS_VWAP = 1.5       # not too far above (fresh reclaim, not extended)
    MIN_INTRADAY_DIP = -1.0 # low was at least 1% below VWAP
    MIN_DAILY_GAIN = 0.5    # stock positive on day
    MIN_BETA = 1.0
    MAX_BETA = 2.5
    MIN_AD = 2.0
    MAX_VIX = 30.0
    SL_MIN_PCT = 1.5
    TP_MIN_PCT = 2.5
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
            vwap = db.get('vw', 0)
            if opn < 1 or now < self.MIN_PRICE or vwap < 1:
                continue

            vs_vwap = (now / vwap - 1) * 100
            low_vs_vwap = (lo / vwap - 1) * 100 if vwap > 0 else 0
            daily_gain = (now / opn - 1) * 100

            # Must be above VWAP now (reclaim)
            if not (self.MIN_VS_VWAP <= vs_vwap <= self.MAX_VS_VWAP):
                continue
            # Must have dipped below VWAP intraday
            if low_vs_vwap > self.MIN_INTRADAY_DIP:
                continue
            # Must be positive on day
            if daily_gain < self.MIN_DAILY_GAIN:
                continue

            beta = betas.get(sym)
            if beta is None or not (self.MIN_BETA <= beta < self.MAX_BETA):
                continue

            atr_pct = (hi - lo) / now * 100 if now > 0 else 2.0
            sl_pct = -max(self.SL_MIN_PCT, 0.6 * atr_pct)
            tp_pct = max(self.TP_MIN_PCT, 1.0 * atr_pct)
            sl_price = now * (1 + sl_pct / 100)
            tp_price = now * (1 + tp_pct / 100)

            sec = sectors.get(sym, '')
            reason = f"VWAP reclaim +{vs_vwap:.1f}% (dipped {low_vs_vwap:.1f}%) daily+{daily_gain:.1f}% β{beta:.1f} {sec[:6]}"

            pick = Pick(
                symbol=sym, entry=now,
                sl_price=round(sl_price, 2), tp_price=round(tp_price, 2),
                trail_pct=self.TRAIL_PCT, reason=reason, score=5, atr_pct=atr_pct,
                extra={
                    'vs_vwap': round(vs_vwap, 2),
                    'low_vs_vwap': round(low_vs_vwap, 2),
                    'daily_gain': round(daily_gain, 2),
                    'beta': round(beta, 2),
                    'sector': sec,
                    'sl_pct': round(sl_pct, 2),
                    'tp_pct': round(tp_pct, 2),
                },
            )
            candidates.append(pick)

        if not candidates:
            return self.no_picks("No VWAP reclaim setups (need above VWAP after dipping below)")

        candidates.sort(key=lambda p: (-p.extra['daily_gain'], p.extra['beta']))
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
            reason=f"{len(candidates)} VWAP reclaims → top {len(picks)}",
            picks=picks,
            regime=f"SPY+{spy_daily:.1f}% AD{ad_ratio:.1f} VIX{vix:.0f}",
            metadata={'note': '⚠️ Not backtest-v2 validated. Paper trade first.'},
        )
