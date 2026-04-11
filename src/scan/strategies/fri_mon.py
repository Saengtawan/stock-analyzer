"""
Friday→Monday Weekend Hold.

Thesis: Friday's momentum/oversold conditions often carry over the weekend.
Three specific setups:
  1. FRI_RALLY — Friday rally 3%+ continues Monday
  2. BAD_WEEK_BOUNCE — week down 5%+ + Friday bounce 2%+ = reversal
  3. FRI_DUMP_VOL — Friday dump 3%+ on vol 2x = oversold bounce Monday

From v1 prompts (162K Fri-Mon pairs):
- Baseline Fri→Mon close: +0.37% avg, 24% hit +3%
- Best setups: 34% Mon +3% rate (1.4x baseline)
- Sell Monday close > Monday open (+0.37% vs +0.32%)

Runs only on Friday 15:00-15:55. VIX<30 required (weekend gap risk).
"""
import os
import sqlite3
import requests
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

from .base import BaseStrategy, ScanResult, Pick, ET

load_dotenv()


class FriMonStrategy(BaseStrategy):
    name = "fri_mon"
    description = "Friday→Monday weekend hold (rally/bounce/dump setups)"
    expected_wr = 0.40  # conservative from prompts 34% Mon +3% rate
    expected_ev = 0.005
    time_start = "15:00"
    time_end = "15:55"
    version = "1.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 5.0
    MIN_CLOSE_POS = 0.5
    MIN_AD = 1.0
    MAX_VIX = 30.0
    SL_MIN_PCT = 2.5      # widest — weekend gap risk
    SL_ATR_MULT = 0.8
    TP_MIN_PCT = 3.0
    TP_ATR_MULT = 1.0
    MAX_PICKS = 3

    def scan(self) -> ScanResult:
        day_name = datetime.now(ET).strftime('%A')
        if day_name != 'Friday':
            return self.gate_failed(f"Runs only on Friday (today: {day_name})")

        if not self.in_time_window():
            return self.out_of_window()

        conn = sqlite3.connect(self.DB_PATH)
        try:
            br = conn.execute("SELECT ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1").fetchone()
            ad_ratio = float(br[0]) if br and br[0] else 0.0
            if ad_ratio < self.MIN_AD:
                return self.gate_failed(f"AD {ad_ratio:.2f} < {self.MIN_AD}")

            vix_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
            vix = float(vix_row[0]) if vix_row else 20.0
            if vix >= self.MAX_VIX:
                return self.gate_failed(f"VIX {vix:.1f} ≥ {self.MAX_VIX} — weekend gap risk too high")

            spy_rows = conn.execute("SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 2").fetchall()
            spy_daily = (spy_rows[0][0] / spy_rows[1][0] - 1) * 100 if len(spy_rows) >= 2 else 0

            syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
            # Skip stocks reporting earnings Mon-Tue (earnings overnight = different play)
            earnings_skip = set(r[0] for r in conn.execute("""
                SELECT symbol FROM earnings_calendar
                WHERE next_earnings_date BETWEEN date('now','+2 day') AND date('now','+3 day')
            """).fetchall())
            sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
            betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())

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
            last_close = db.get('c', 0)
            last_open = db.get('o', 0)
            hi = db.get('h', 0); lo = db.get('l', 0)
            vol = db.get('v', 0)
            if last_close < self.MIN_PRICE or last_open < 1:
                continue

            fri_ret = (last_close / last_open - 1) * 100
            d0 = days[0]
            mom5d = (last_close / d0[3] - 1) * 100 if d0[3] else 0
            avg_vol = np.mean([d[5] for d in days[:-1]]) if len(days) > 1 else 1
            vol_ratio = vol / avg_vol if avg_vol > 0 else 0
            rng = hi - lo
            cp = (last_close - lo) / rng if rng > 0 else 0.5

            # Classify setup
            setup = None
            if fri_ret >= 3:
                setup = 'FRI_RALLY'
            elif mom5d <= -5 and fri_ret >= 2:
                setup = 'BAD_WEEK_BOUNCE'
            elif fri_ret <= -3 and vol_ratio >= 2:
                setup = 'FRI_DUMP_VOL'
            if not setup:
                continue

            if cp < self.MIN_CLOSE_POS:
                continue

            trs = [max(d[2]-d[3], abs(d[2]-days[i-1][4]), abs(d[3]-days[i-1][4]))
                   for i, d in enumerate(days[1:], 1)]
            atr_pct = np.mean(trs[-4:]) / last_close * 100 if trs else 3.0
            sl_pct = -max(self.SL_MIN_PCT, self.SL_ATR_MULT * atr_pct)
            tp_pct = max(self.TP_MIN_PCT, self.TP_ATR_MULT * atr_pct)
            sl_price = last_close * (1 + sl_pct / 100)
            tp_price = last_close * (1 + tp_pct / 100)

            beta = betas.get(sym, 1.5)
            sec = sectors.get(sym, '')
            score = 6 + (1 if setup == 'FRI_RALLY' else 0)
            reason = f"{setup} Fri{fri_ret:+.1f}% 5d{mom5d:+.1f}% vol{vol_ratio:.1f}x cp{cp:.2f} β{beta:.1f}"

            pick = Pick(
                symbol=sym, entry=last_close,
                sl_price=round(sl_price, 2), tp_price=round(tp_price, 2),
                reason=reason, score=score, atr_pct=atr_pct,
                extra={
                    'setup': setup,
                    'fri_ret': round(fri_ret, 2),
                    'mom5d': round(mom5d, 2),
                    'vol_ratio': round(vol_ratio, 2),
                    'beta': round(beta, 2),
                    'sector': sec,
                    'sl_pct': round(sl_pct, 2),
                    'tp_pct': round(tp_pct, 2),
                },
            )
            candidates.append(pick)

        if not candidates:
            return self.no_picks("No Friday setups qualifying")

        # Prefer FRI_RALLY > BAD_WEEK_BOUNCE > FRI_DUMP_VOL
        setup_rank = {'FRI_RALLY': 0, 'BAD_WEEK_BOUNCE': 1, 'FRI_DUMP_VOL': 2}
        candidates.sort(key=lambda p: (setup_rank.get(p.extra['setup'], 9), -abs(p.extra['fri_ret'])))

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
            reason=f"{len(candidates)} Fri-Mon candidates → top {len(picks)}",
            picks=picks,
            regime=f"SPY{spy_daily:+.1f}% VIX{vix:.0f}",
            metadata={'ad_ratio': round(ad_ratio, 2), 'vix': round(vix, 1)},
        )
