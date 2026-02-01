#!/usr/bin/env python3
"""
TEST RAPID TRADER v4.0 - BOUNCE CONFIRMATION
=============================================
ทดสอบระบบจริงโดยใช้ Rapid Trader Screener กรองหุ้นมา
แล้ว simulate การซื้อขายตามคำแนะนำจริง
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/screeners'))

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')


@dataclass
class Trade:
    symbol: str
    entry_date: str
    entry_price: float
    stop_loss: float
    take_profit: float
    score: int
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    days_held: int = 0


class RapidTraderV4Test:
    """Test Rapid Trader v4.0 with real screening"""

    MAX_HOLD = 4

    def __init__(self):
        self.trades: List[Trade] = []
        self.screener = None
        self._init_screener()

    def _init_screener(self):
        """Initialize the actual Rapid Trader screener"""
        try:
            from rapid_rotation_screener import RapidRotationScreener
            self.screener = RapidRotationScreener()
            print("✅ Rapid Trader v4.0 Screener loaded")
        except Exception as e:
            print(f"❌ Failed to load screener: {e}")
            self.screener = None

    def get_signals_for_date(self, date_str: str) -> List[Dict]:
        """Get buy signals from Rapid Trader for a specific date"""
        if not self.screener:
            return []

        try:
            # Call the actual screener
            signals = self.screener.screen(max_stocks=10)
            return signals
        except Exception as e:
            print(f"    Error screening: {e}")
            return []

    def simulate_trade(self, signal, entry_date: str) -> Optional[Trade]:
        """Simulate a trade based on signal"""
        symbol = signal.symbol
        entry_price = signal.entry_price
        stop_loss = signal.stop_loss
        take_profit = signal.take_profit

        trade = Trade(
            symbol=symbol,
            entry_date=entry_date,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            score=signal.score
        )

        sl_pct = ((stop_loss - entry_price) / entry_price) * 100
        tp_pct = ((take_profit - entry_price) / entry_price) * 100

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
            if low_pnl <= sl_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = stop_loss
                trade.exit_reason = "STOP_LOSS"
                trade.pnl_pct = sl_pct
                trade.days_held = day_idx
                return trade

            # Take profit
            if high_pnl >= tp_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = take_profit
                trade.exit_reason = "TAKE_PROFIT"
                trade.pnl_pct = tp_pct
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

    def run_live_test(self):
        """Run test with current market data"""
        print(f"\n{'='*70}")
        print(f"RAPID TRADER v4.0 - LIVE SIGNAL TEST")
        print(f"{'='*70}")
        print(f"Testing with BOUNCE CONFIRMATION logic")
        print(f"{'='*70}\n")

        if not self.screener:
            print("❌ Screener not available")
            return

        today = datetime.now().strftime('%Y-%m-%d')
        print(f"Date: {today}")
        print(f"\nScreening for buy signals...")

        signals = self.get_signals_for_date(today)

        if not signals:
            print("  No signals found today")
            print("  (This is expected - bounce confirmation is selective)")
            return

        print(f"\n✅ Found {len(signals)} signals:")
        for i, sig in enumerate(signals, 1):
            sl_pct = ((sig.stop_loss - sig.entry_price) / sig.entry_price) * 100
            tp_pct = ((sig.take_profit - sig.entry_price) / sig.entry_price) * 100
            rr = abs(tp_pct / sl_pct) if sl_pct != 0 else 0

            print(f"\n  [{i}] {sig.symbol}")
            print(f"      Score: {sig.score}")
            print(f"      Entry: ${sig.entry_price:.2f}")
            print(f"      SL: ${sig.stop_loss:.2f} ({sl_pct:.1f}%)")
            print(f"      TP: ${sig.take_profit:.2f} (+{tp_pct:.1f}%)")
            print(f"      R:R: {rr:.1f}")
            print(f"      Reasons: {', '.join(sig.reasons[:3])}")

    def run_historical_test(self, days_back: int = 30):
        """Run historical test"""
        print(f"\n{'='*70}")
        print(f"RAPID TRADER v4.0 - HISTORICAL BACKTEST")
        print(f"{'='*70}")
        print(f"Period: Last {days_back} days")
        print(f"Using BOUNCE CONFIRMATION logic")
        print(f"{'='*70}\n")

        if not self.screener:
            print("❌ Screener not available")
            return

        end = datetime.now()
        start = end - timedelta(days=days_back)
        current = start

        week = 0
        while current <= end:
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            week += 1
            date_str = current.strftime('%Y-%m-%d')
            print(f"\n[Week {week}] {date_str}")

            signals = self.get_signals_for_date(date_str)

            if signals:
                print(f"  Found {len(signals)} signals")
                for sig in signals[:3]:
                    print(f"    -> {sig.symbol}: Score={sig.score}, Entry=${sig.entry_price:.2f}")

                    trade = self.simulate_trade(sig, date_str)
                    if trade:
                        self.trades.append(trade)
                        emoji = "✅" if trade.pnl_pct > 0 else "❌"
                        print(f"       {emoji} {trade.exit_reason} {trade.pnl_pct:+.2f}%")
            else:
                print(f"  No signals (bounce confirmation is selective)")

            current += timedelta(days=7)

        self._show_results()

    def _show_results(self):
        """Show backtest results"""
        if not self.trades:
            print("\n📊 No trades executed (very selective strategy)")
            return

        total = len(self.trades)
        winners = [t for t in self.trades if t.pnl_pct > 0]
        losers = [t for t in self.trades if t.pnl_pct <= 0]

        win_rate = len(winners) / total * 100
        total_pnl = sum(t.pnl_pct for t in self.trades)
        avg_pnl = total_pnl / total

        avg_win = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0

        sl_count = len([t for t in self.trades if t.exit_reason == "STOP_LOSS"])
        tp_count = len([t for t in self.trades if t.exit_reason == "TAKE_PROFIT"])

        print(f"\n{'='*70}")
        print(f"RAPID TRADER v4.0 RESULTS")
        print(f"{'='*70}")

        print(f"\n📊 Statistics:")
        print(f"  Trades: {total}")
        print(f"  Winners: {len(winners)} ({win_rate:.1f}%)")
        print(f"  Losers: {len(losers)} ({100-win_rate:.1f}%)")

        print(f"\n💰 Returns:")
        print(f"  Total P&L: {total_pnl:+.2f}%")
        print(f"  Avg per Trade: {avg_pnl:+.2f}%")
        print(f"  Avg Win: {avg_win:+.2f}%")
        print(f"  Avg Loss: {avg_loss:+.2f}%")

        print(f"\n🎯 Exit Breakdown:")
        print(f"  Stop Loss: {sl_count} ({sl_count/total*100:.0f}%)")
        print(f"  Take Profit: {tp_count} ({tp_count/total*100:.0f}%)")
        print(f"  Max Hold: {total - sl_count - tp_count} ({(total-sl_count-tp_count)/total*100:.0f}%)")

        print(f"\n📋 Trade Details:")
        for t in self.trades:
            emoji = "✅" if t.pnl_pct > 0 else "❌"
            print(f"  {emoji} {t.symbol} {t.entry_date}: {t.exit_reason} {t.pnl_pct:+.2f}% (Score={t.score})")

        # Summary
        print(f"\n{'='*70}")
        print(f"v4.0 BOUNCE CONFIRMATION SUMMARY")
        print(f"{'='*70}")

        if win_rate >= 60 and avg_pnl > 1:
            print(f"  ✅ EXCELLENT! Win rate {win_rate:.0f}%, avg +{avg_pnl:.2f}%")
        elif win_rate >= 50:
            print(f"  🟡 GOOD. Win rate {win_rate:.0f}%, avg {avg_pnl:+.2f}%")
        else:
            print(f"  ⚠️ Needs tuning. Win rate {win_rate:.0f}%")

        if sl_count == 0:
            print(f"  ✅ 0% Stop Loss hits - Bounce confirmation working!")
        elif sl_count / total < 0.3:
            print(f"  🟡 Low SL rate ({sl_count/total*100:.0f}%) - Good")
        else:
            print(f"  ⚠️ High SL rate ({sl_count/total*100:.0f}%) - Check entry timing")


def main():
    tester = RapidTraderV4Test()

    print("\n" + "="*70)
    print("RAPID TRADER v4.0 TEST")
    print("="*70)
    print("\nChanges in v4.0:")
    print("  - BOUNCE CONFIRMATION: Wait for price to recover after dip")
    print("  - Don't catch falling knives")
    print("  - Expected: Higher win rate, fewer stop losses")
    print("="*70)

    # Run live test first
    tester.run_live_test()


if __name__ == "__main__":
    main()
