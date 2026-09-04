"""Bridge: ml_filter scan picks → IBKR paper orders.

Per-trade budget = min(cash, TOTAL_TRADING_ALLOCATION) / remaining_slots.
No PDT (live = cash account; paper = $250K > $25K threshold).
"""
import os
import sys
from datetime import datetime
import pytz
from pathlib import Path

from src.scan.engine import run_scan
from src.brokers.ibkr_broker import IBKRBroker

ET = pytz.timezone('US/Eastern')
MAX_CONCURRENT_POSITIONS = 2
TOTAL_TRADING_ALLOCATION = float(os.getenv('IBKR_TOTAL_BUDGET', '3000'))  # simulates live equity


def execute_picks():
    now_et = datetime.now(ET)
    print(f"[{now_et.strftime('%H:%M')}] ml_filter scan + IBKR execution")

    result = run_scan('ml_filter')
    if result.status != 'active' or not result.picks:
        print(f"  No picks: {result.status} — {result.reason}")
        return

    broker = IBKRBroker()
    try:
        if not broker.connect():
            print("  IBKR not connected — picks not executed")
            return

        summary = broker.account_summary()
        cash = summary['cash']
        print(f"  Account: cash=${cash:,.0f}  buying_power=${summary['buying_power']:,.0f}")

        existing = {p.symbol for p in broker.get_positions()}
        print(f"  Existing positions ({len(existing)}): {existing}")

        slots = MAX_CONCURRENT_POSITIONS - len(existing)
        if slots <= 0:
            print(f"  Max positions ({MAX_CONCURRENT_POSITIONS}) reached — no new orders")
            return

        # Per-trade = cap / max_positions (fixed equal-size, replenish on close)
        per_trade = TOTAL_TRADING_ALLOCATION / MAX_CONCURRENT_POSITIONS
        if per_trade > cash:
            per_trade = cash  # safety: don't exceed actual cash
        if per_trade < 100:
            print(f"  ⚠️ Per-trade ${per_trade:.0f} too small — skip")
            return
        print(f"  Allocation: cap=${TOTAL_TRADING_ALLOCATION:,.0f} / {MAX_CONCURRENT_POSITIONS} = "
              f"${per_trade:,.0f}/trade (fixed equal-size)  slots open: {slots}")

        executed = 0
        for pick in result.picks:
            if executed >= slots: break
            if pick.symbol in existing:
                print(f"  {pick.symbol}: already held — skip")
                continue
            print(f"  → BUY {pick.symbol} @ ~${pick.entry:.2f}  budget ${per_trade:,.0f}  "
                  f"trail 3.0% (initial, tightened by monitor)")
            qty, buy, stop = broker.buy_with_dynamic_trail(
                pick.symbol, pick.entry,
                budget=per_trade,
                initial_trail_pct=3.0,
            )
            if qty > 0:
                print(f"    placed: {qty} shares, buy={buy.order.orderId}, stop={stop.order.orderId}")
                executed += 1
            else:
                print(f"    qty=0 (budget too small for share price)")

        print(f"  Executed {executed} new orders")
    finally:
        broker.disconnect()


if __name__ == '__main__':
    execute_picks()
