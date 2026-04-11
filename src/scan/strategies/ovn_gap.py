"""
Overnight Gap Play — buy before close, sell at/after next open.

Thesis: Stocks with strong 5-day momentum + today's green close near high +
elevated volume are more likely to gap up overnight and continue the trend.

From v1 prompts (OVN 800K daily bars):
- 5d mom >10% + today +2% + vol 2x+: 10% hit +3% gap
- 5d mom >5% + vol 2x: 5.6% hit +3% gap
- baseline (no setup): 1.9% hit +3%
- Tuesday/Wednesday bonus (gap rate ~14% vs Thursday 12%)

Note: backtest v2 suite didn't re-validate OVN specifically. These
numbers come from v1 prompt data (hit +3% rate, not buy-hold-close).
Paper trade before sizing up.
"""
import os
import sqlite3
import requests
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

from .base import BaseStrategy, ScanResult, Pick, ET

load_dotenv()


class OvernightGapStrategy(BaseStrategy):
    name = "ovn_gap"
    description = "Overnight gap play — buy near close, exit at/after next open"
    expected_wr = 0.55  # rough estimate from v1 prompts
    expected_ev = 0.005
    time_start = "15:30"
    time_end = "15:55"
    version = "1.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 5.0
    MIN_5D_MOM = 5.0
    MIN_TODAY_RET = 2.0
    MIN_VOL_RATIO = 2.0
    MIN_CLOSE_POS = 0.5   # close in upper half of day range
    MIN_AD = 1.0
    SL_MIN_PCT = 2.0      # wider for overnight hold
    SL_ATR_MULT = 0.7
    TP_MIN_PCT = 3.0
    TP_ATR_MULT = 1.0
    MAX_PICKS = 3

    def scan(self) -> ScanResult:
        if not self.in_time_window():
            return self.out_of_window()

        day_name = datetime.now(ET).strftime('%A')
        good_day = day_name in ('Tuesday', 'Wednesday')

        conn = sqlite3.connect(self.DB_PATH)
        try:
            br = conn.execute("SELECT ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1").fetchone()
            ad_ratio = float(br[0]) if br and br[0] else 0.0
            if ad_ratio < self.MIN_AD:
                return self.gate_failed(f"AD {ad_ratio:.2f} < {self.MIN_AD}")

            spy_rows = conn.execute("SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 2").fetchall()
            spy_daily = (spy_rows[0][0] / spy_rows[1][0] - 1) * 100 if len(spy_rows) >= 2 else 0
            vix_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
            vix = float(vix_row[0]) if vix_row else 20.0

            syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
            earnings_skip = set(r[0] for r in conn.execute(
                "SELECT symbol FROM earnings_calendar WHERE next_earnings_date = date('now','+1 day')"
            ).fetchall())
            sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
            betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())

            # 5d history
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
            db = s.get('dailyBar', {}); pb = s.get('prevDailyBar', {})
            last_close = db.get('c', 0)
            prev_close = pb.get('c', 0)
            hi = db.get('h', 0); lo = db.get('l', 0)
            vol = db.get('v', 0)
            if last_close < self.MIN_PRICE or prev_close < 1:
                continue

            today_ret = (last_close / prev_close - 1) * 100
            d0 = days[0]
            mom5d = (last_close / d0[3] - 1) * 100 if d0[3] else 0
            if mom5d < self.MIN_5D_MOM:
                continue
            if today_ret < self.MIN_TODAY_RET:
                continue

            avg_vol = np.mean([d[5] for d in days[:-1]]) if len(days) > 1 else 1
            vol_ratio = vol / avg_vol if avg_vol > 0 else 0
            if vol_ratio < self.MIN_VOL_RATIO:
                continue

            rng = hi - lo
            cp = (last_close - lo) / rng if rng > 0 else 0.5
            if cp < self.MIN_CLOSE_POS:
                continue

            # ATR
            trs = [max(d[2]-d[3], abs(d[2]-days[i-1][4]), abs(d[3]-days[i-1][4]))
                   for i, d in enumerate(days[1:], 1)]
            atr_pct = np.mean(trs[-4:]) / last_close * 100 if trs else 3.0

            sl_pct = -max(self.SL_MIN_PCT, self.SL_ATR_MULT * atr_pct)
            tp_pct = max(self.TP_MIN_PCT, self.TP_ATR_MULT * atr_pct)
            sl_price = last_close * (1 + sl_pct / 100)
            tp_price = last_close * (1 + tp_pct / 100)

            beta = betas.get(sym, 1.5)
            sec = sectors.get(sym, '')
            score = 5 + (1 if good_day else 0) + (1 if spy_daily > 0 else 0)
            reason = f"5d{mom5d:+.1f}% T{today_ret:+.1f}% vol{vol_ratio:.1f}x cp{cp:.2f} {day_name[:3]} {sec[:6]}"

            pick = Pick(
                symbol=sym, entry=last_close,
                sl_price=round(sl_price, 2), tp_price=round(tp_price, 2),
                reason=reason, score=score, atr_pct=atr_pct,
                extra={
                    'mom5d': round(mom5d, 2),
                    'today_ret': round(today_ret, 2),
                    'vol_ratio': round(vol_ratio, 2),
                    'close_pos': round(cp, 2),
                    'beta': round(beta, 2),
                    'sector': sec,
                    'sl_pct': round(sl_pct, 2),
                    'tp_pct': round(tp_pct, 2),
                },
            )
            candidates.append(pick)

        if not candidates:
            return self.no_picks("No stocks meet OVN setup criteria")

        candidates.sort(key=lambda p: -p.extra['mom5d'])
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
            reason=f"{len(candidates)} OVN candidates → top {len(picks)} | {day_name}",
            picks=picks,
            regime=f"SPY{spy_daily:+.1f}% VIX{vix:.0f} {day_name}",
            metadata={'ad_ratio': round(ad_ratio, 2), 'day': day_name, 'good_day': good_day},
        )
