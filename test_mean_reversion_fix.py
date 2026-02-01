#!/usr/bin/env python3
"""
MEAN REVERSION FIX TEST
========================
ปัญหา: Buy the Dip ปัจจุบันซื้อตอนราคากำลังตก (catching falling knife)
แก้ไข: รอ BOUNCE CONFIRMATION ก่อนซื้อ

เปรียบเทียบ:
- v3 (เดิม): ซื้อวันที่ราคาลง
- v4 (แก้): รอราคา bounce ก่อน
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')


UNIVERSE = [
    'NVDA', 'AMD', 'TSLA', 'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT',
    'AVGO', 'MU', 'PLTR', 'COIN', 'SNOW', 'CRM', 'ORCL', 'NOW',
    'JPM', 'GS', 'V', 'MA', 'HD', 'LOW', 'CAT', 'DE',
]


@dataclass
class Trade:
    symbol: str
    strategy: str
    entry_date: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    days_held: int = 0


class MeanReversionComparison:
    """Compare old vs new mean reversion logic"""

    # Exit params
    SL_PCT = 2.0
    TP_PCT = 5.0
    MAX_HOLD = 5

    def __init__(self):
        self.trades_v3: List[Trade] = []
        self.trades_v4: List[Trade] = []

    def check_v3_entry(self, hist: pd.DataFrame) -> Tuple[bool, str]:
        """
        v3 (เดิม): Buy when price is FALLING
        - mom_1d < 0
        - price < SMA5
        """
        if len(hist) < 5:
            return False, ""

        current = hist['Close'].iloc[-1]
        prev = hist['Close'].iloc[-2]
        sma5 = hist['Close'].tail(5).mean()

        mom_1d = ((current / prev) - 1) * 100

        # v3 logic: enter when falling
        if mom_1d < 0 and current < sma5:
            return True, f"v3: Dip {mom_1d:.1f}%, below SMA5"

        return False, ""

    def check_v4_entry(self, hist: pd.DataFrame) -> Tuple[bool, str]:
        """
        v4 (แก้ไข): Buy AFTER bounce confirmation
        - Yesterday was down
        - Today is UP (green candle)
        - Still below SMA5 (oversold area)
        """
        if len(hist) < 3:
            return False, ""

        today = hist.iloc[-1]
        yesterday = hist.iloc[-2]
        day_before = hist.iloc[-3]

        current = today['Close']
        sma5 = hist['Close'].tail(5).mean()

        # Yesterday was a dip?
        yesterday_change = ((yesterday['Close'] / day_before['Close']) - 1) * 100

        # Today is bouncing?
        today_change = ((today['Close'] / yesterday['Close']) - 1) * 100

        # v4 logic: enter AFTER bounce
        if yesterday_change < -0.5 and today_change > 0 and today['Close'] > today['Open']:
            # Still in oversold area
            if current < sma5 * 1.02:
                return True, f"v4: Yesterday {yesterday_change:.1f}%, Today BOUNCE {today_change:.1f}%"

        return False, ""

    def simulate_trade(self, symbol: str, entry_date: str, entry_price: float, strategy: str) -> Optional[Trade]:
        """Simulate trade"""
        sl = entry_price * (1 - self.SL_PCT / 100)
        tp = entry_price * (1 + self.TP_PCT / 100)

        trade = Trade(
            symbol=symbol,
            strategy=strategy,
            entry_date=entry_date,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit=tp
        )

        try:
            start = datetime.strptime(entry_date, '%Y-%m-%d')
            end = start + timedelta(days=20)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start, end=end)

            if hist.empty:
                return None
        except:
            return None

        for day_idx, (date, row) in enumerate(hist.iterrows()):
            if day_idx == 0:
                continue

            low = row['Low']
            high = row['High']
            close = row['Close']

            low_pnl = ((low - entry_price) / entry_price) * 100
            high_pnl = ((high - entry_price) / entry_price) * 100
            close_pnl = ((close - entry_price) / entry_price) * 100

            # Stop loss
            if low_pnl <= -self.SL_PCT:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = sl
                trade.exit_reason = "STOP_LOSS"
                trade.pnl_pct = -self.SL_PCT
                trade.days_held = day_idx
                return trade

            # Take profit
            if high_pnl >= self.TP_PCT:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = tp
                trade.exit_reason = "TAKE_PROFIT"
                trade.pnl_pct = self.TP_PCT
                trade.days_held = day_idx
                return trade

            # Max hold
            if day_idx >= self.MAX_HOLD:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = close
                trade.exit_reason = "MAX_HOLD"
                trade.pnl_pct = close_pnl
                trade.days_held = day_idx
                return trade

        return None

    def run_comparison(self, start_date: str, end_date: str):
        """Run both strategies and compare"""
        print(f"\n{'='*70}")
        print(f"MEAN REVERSION COMPARISON TEST")
        print(f"{'='*70}")
        print(f"\nv3 (เดิม): ซื้อวันที่ราคาลง (catching falling knife)")
        print(f"v4 (แก้):  รอ bounce confirmation ก่อนซื้อ")
        print(f"\nPeriod: {start_date} to {end_date}")
        print(f"{'='*70}\n")

        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        current = start
        week = 0

        while current <= end:
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            date_str = current.strftime('%Y-%m-%d')
            week += 1

            print(f"\n[Week {week}] {date_str}")

            for symbol in UNIVERSE[:10]:  # Test with 10 stocks
                try:
                    lookup_start = current - timedelta(days=30)
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(start=lookup_start, end=current + timedelta(days=1))

                    if len(hist) < 10:
                        continue

                    current_price = hist['Close'].iloc[-1]

                    # Check v3 entry
                    v3_ok, v3_reason = self.check_v3_entry(hist)
                    if v3_ok:
                        trade = self.simulate_trade(symbol, date_str, current_price, "v3")
                        if trade:
                            self.trades_v3.append(trade)
                            emoji = "✅" if trade.pnl_pct > 0 else "❌"
                            print(f"  v3 {symbol}: {v3_reason}")
                            print(f"      {emoji} {trade.exit_reason} {trade.pnl_pct:+.2f}%")

                    # Check v4 entry
                    v4_ok, v4_reason = self.check_v4_entry(hist)
                    if v4_ok:
                        trade = self.simulate_trade(symbol, date_str, current_price, "v4")
                        if trade:
                            self.trades_v4.append(trade)
                            emoji = "✅" if trade.pnl_pct > 0 else "❌"
                            print(f"  v4 {symbol}: {v4_reason}")
                            print(f"      {emoji} {trade.exit_reason} {trade.pnl_pct:+.2f}%")

                except Exception as e:
                    continue

            current += timedelta(days=7)

        self._show_comparison()

    def _show_comparison(self):
        """Show comparison results"""
        print(f"\n{'='*70}")
        print(f"COMPARISON RESULTS")
        print(f"{'='*70}")

        for name, trades in [("v3 (เดิม - ซื้อตอนตก)", self.trades_v3),
                             ("v4 (แก้ - รอ bounce)", self.trades_v4)]:
            if not trades:
                print(f"\n{name}: No trades")
                continue

            total = len(trades)
            winners = [t for t in trades if t.pnl_pct > 0]
            losers = [t for t in trades if t.pnl_pct <= 0]

            win_rate = len(winners) / total * 100
            total_pnl = sum(t.pnl_pct for t in trades)
            avg_pnl = total_pnl / total

            avg_win = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
            avg_loss = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0

            sl_count = len([t for t in trades if t.exit_reason == "STOP_LOSS"])
            tp_count = len([t for t in trades if t.exit_reason == "TAKE_PROFIT"])

            print(f"\n{name}:")
            print(f"  Trades: {total}")
            print(f"  Win Rate: {win_rate:.1f}%")
            print(f"  Total P&L: {total_pnl:+.2f}%")
            print(f"  Avg Trade: {avg_pnl:+.2f}%")
            print(f"  Avg Win: {avg_win:+.2f}%")
            print(f"  Avg Loss: {avg_loss:+.2f}%")
            print(f"  Stop Loss hits: {sl_count} ({sl_count/total*100:.0f}%)")
            print(f"  Take Profit hits: {tp_count} ({tp_count/total*100:.0f}%)")

        # Direct comparison
        if self.trades_v3 and self.trades_v4:
            v3_wr = len([t for t in self.trades_v3 if t.pnl_pct > 0]) / len(self.trades_v3) * 100
            v4_wr = len([t for t in self.trades_v4 if t.pnl_pct > 0]) / len(self.trades_v4) * 100

            v3_avg = sum(t.pnl_pct for t in self.trades_v3) / len(self.trades_v3)
            v4_avg = sum(t.pnl_pct for t in self.trades_v4) / len(self.trades_v4)

            print(f"\n{'='*70}")
            print(f"WINNER:")
            print(f"{'='*70}")
            print(f"  Win Rate: v3={v3_wr:.1f}% vs v4={v4_wr:.1f}% → {'v4 WINS' if v4_wr > v3_wr else 'v3 WINS'}")
            print(f"  Avg Trade: v3={v3_avg:+.2f}% vs v4={v4_avg:+.2f}% → {'v4 WINS' if v4_avg > v3_avg else 'v3 WINS'}")

            if v4_wr > v3_wr and v4_avg > v3_avg:
                print(f"\n  ✅ v4 (รอ bounce) ดีกว่า!")
                print(f"     Improvement: +{v4_wr - v3_wr:.1f}% win rate, +{v4_avg - v3_avg:.2f}% per trade")
            elif v3_wr > v4_wr and v3_avg > v4_avg:
                print(f"\n  ⚠️ v3 (เดิม) ดีกว่า - bounce confirmation อาจ miss โอกาส")
            else:
                print(f"\n  🟡 ผลใกล้เคียงกัน - ต้องทดสอบเพิ่มเติม")


def main():
    comparison = MeanReversionComparison()

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

    comparison.run_comparison(start_date, end_date)


if __name__ == "__main__":
    main()
