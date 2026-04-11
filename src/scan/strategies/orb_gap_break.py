"""
ORB Gap Break (09:30-09:35) — buy gap ups at open, trail 1% from peak.

Backtest (walk-forward 2025+, 5-min bars):

  Setup                              N     WR      EV
  Gap +3-5% + vol 2x                 344   80.2%   +0.41%
  Gap +3-5% + vol 3x                 75    85.3%   +0.99%
  Gap +5-8% + vol 2x                 339   81.7%   +0.22%
  Gap +8-15% + vol 2x                321   89.1%   +1.19% ⭐
  Gap 15%+ + trail 1%                173   83.2%   +0.77%
  Top 3/day gap ≥5%                  745   81.5%   +0.46%

Thesis: Stocks gapping up 5%+ at open on strong volume tend to
continue the initial momentum. Trail 1% from peak captures the
spike without giving back gains.

Entry: at 09:30 open (market order)
Exit: Trail 1% from peak (no hard SL — trust the trail)
Universe: Gap ≥ 5% over prev close, top 3 per day by gap size
"""
import os
import sqlite3
import requests
import numpy as np
from dotenv import load_dotenv

from .base import BaseStrategy, ScanResult, Pick

load_dotenv()


class OrbGapBreakStrategy(BaseStrategy):
    name = "orb_gap_break"
    description = "09:30-09:35 gap up ≥5% break at open, trail 1% from peak"
    expected_wr = 0.815
    expected_ev = 0.0046  # +0.46%
    time_start = "09:30"
    time_end = "09:35"
    version = "1.0"

    DB_PATH = "data/trade_history.db"
    MIN_PRICE = 3.0
    MIN_GAP = 5.0      # min gap% vs prev close
    MAX_GAP = 25.0     # too big = priced in / earnings shock
    MIN_DOLLAR_VOL = 5e6
    MAX_PICKS = 3      # top 3 per day by gap size

    def scan(self) -> ScanResult:
        if not self.in_time_window():
            return self.out_of_window()

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

            # Prev day close for gap calc
            prev_close = {}
            for r in conn.execute("""
                SELECT symbol, close FROM stock_daily_ohlc
                WHERE date = (SELECT MAX(date) FROM stock_daily_ohlc WHERE date < date('now'))
            """):
                prev_close[r[0]] = r[1]
        finally:
            conn.close()

        # Fetch snapshots
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
            db = s.get('dailyBar', {})
            pb = s.get('prevDailyBar', {})
            # Current open — at 09:30 this is the opening print
            opn = db.get('o', 0)
            now = db.get('c', 0)
            hi = db.get('h', 0)
            lo = db.get('l', 0)
            vol = db.get('v', 0)
            pc = prev_close.get(sym) or pb.get('c', 0)

            if opn < 1 or now < self.MIN_PRICE or not pc or pc <= 0:
                continue

            gap = (opn / pc - 1) * 100
            if not (self.MIN_GAP <= gap < self.MAX_GAP):
                continue

            # Dollar volume check (basic liquidity)
            if opn * vol < self.MIN_DOLLAR_VOL and vol > 0:
                # Not enough volume yet — might still qualify at open, skip low liquidity
                continue

            sec = sectors.get(sym, '')
            # Entry = current price (snapshot close, which at 09:30 is near open)
            # In actual execution, market order at 09:30 will fill at open
            entry = now if now > 0 else opn

            # Trail 1% exit — set initial SL at entry - 1% as worst case
            # (will be raised as peak rises)
            initial_sl = entry * 0.99

            # Expected reach: avg winner from backtest ~+1.7%
            target = entry * 1.02

            reason = f"GAP +{gap:.1f}% @ open={opn:.2f} prev={pc:.2f} {sec[:6]}"

            candidates.append(Pick(
                symbol=sym,
                entry=entry,
                sl_price=round(initial_sl, 2),
                tp_price=round(target, 2),
                trail_pct=1.0,
                reason=reason,
                score=int(min(9, gap)),  # score by gap size
                atr_pct=None,
                extra={
                    'gap': round(gap, 2),
                    'open': round(opn, 2),
                    'prev_close': round(pc, 2),
                    'sector': sec,
                },
            ))

        if not candidates:
            return self.no_picks(f"No stocks with gap ≥ {self.MIN_GAP}% + liquidity")

        # Sort by gap size descending, take top MAX_PICKS
        candidates.sort(key=lambda p: -p.extra['gap'])
        picks = candidates[:self.MAX_PICKS]

        return ScanResult(
            strategy=self.name,
            timestamp_et=self.time_et_str(),
            status='active',
            reason=f"{len(candidates)} gap ≥{self.MIN_GAP}% → top {len(picks)} by gap size",
            picks=picks,
            regime=f"{len(candidates)} gap candidates",
            metadata={
                'expected_wr': self.expected_wr,
                'expected_ev': self.expected_ev,
                'exit': 'trail 1% from peak',
                'n_candidates': len(candidates),
            },
        )
