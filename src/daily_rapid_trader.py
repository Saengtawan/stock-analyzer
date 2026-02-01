#!/usr/bin/env python3
"""
DAILY RAPID TRADER - ระบบ Trading รายวัน

เป้าหมาย: 5-15% ต่อเดือน ผ่านการ compound หลายๆ trade เล็กๆ

การทำงาน:
1. เช็ค Portfolio - มีตัวไหนต้องขายบ้าง?
2. หาหุ้นใหม่ - ตัวไหนน่าซื้อ?
3. คำนวณ Position Size
4. ให้ SL/TP ที่ชัดเจน

Rules:
- Position Size: 25% ต่อตัว (max 4 ตัว)
- Stop Loss: 2.5%
- Take Profit: 3-5%
- Max Hold: 7 วัน
- ตัดขาดทุนเร็ว, ปล่อยกำไรวิ่ง (แต่ไม่นานเกินไป)
"""

import sys
import os
import json
from datetime import datetime
from typing import List, Dict, Optional

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screeners.rapid_rotation_screener import RapidRotationScreener, RapidRotationSignal
from rapid_portfolio_manager import RapidPortfolioManager, ExitSignal


class DailyRapidTrader:
    """
    Main Trading System

    ใช้ทุกวันเพื่อ:
    1. ตรวจสอบ positions ที่มีอยู่
    2. หาโอกาสใหม่
    3. บริหาร portfolio
    """

    # Configuration
    CAPITAL = 100000  # Total capital
    POSITION_SIZE_PCT = 25  # 25% per position
    MAX_POSITIONS = 4

    def __init__(self, capital: float = None):
        self.capital = capital or self.CAPITAL
        self.position_size = self.capital * self.POSITION_SIZE_PCT / 100
        self.screener = RapidRotationScreener()
        self.portfolio = RapidPortfolioManager()

    def run_daily_check(self) -> Dict:
        """
        Run complete daily check

        Returns:
            Dict with all trading decisions for today
        """
        print("=" * 70)
        print("🚀 DAILY RAPID TRADER")
        print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 70)
        print()

        result = {
            'date': datetime.now().isoformat(),
            'portfolio_status': None,
            'sell_orders': [],
            'buy_orders': [],
            'summary': {}
        }

        # Step 1: Check existing positions
        print("=" * 70)
        print("📊 STEP 1: CHECK PORTFOLIO")
        print("=" * 70)
        print()

        sell_orders = self._check_portfolio()
        result['sell_orders'] = sell_orders

        # Step 2: Find new opportunities
        print()
        print("=" * 70)
        print("🔍 STEP 2: FIND NEW OPPORTUNITIES")
        print("=" * 70)
        print()

        buy_orders = self._find_opportunities()
        result['buy_orders'] = buy_orders

        # Step 3: Summary
        print()
        print("=" * 70)
        print("📋 STEP 3: TODAY'S ACTION PLAN")
        print("=" * 70)
        print()

        self._print_action_plan(sell_orders, buy_orders)

        result['summary'] = {
            'total_sells': len(sell_orders),
            'total_buys': len(buy_orders),
            'portfolio_positions': len(self.portfolio.positions)
        }

        return result

    def _check_portfolio(self) -> List[Dict]:
        """Check existing positions for exit signals"""
        sell_orders = []

        if not self.portfolio.positions:
            print("ไม่มี Position ใน Portfolio")
            print()
            return sell_orders

        # Get portfolio summary
        summary = self.portfolio.get_portfolio_summary()
        print(f"Positions: {summary['positions']}")
        print(f"Total Value: ${summary['total_value']:,.2f}")
        print(f"Total P&L: ${summary['total_pnl_usd']:+,.2f} ({summary['total_pnl_pct']:+.2f}%)")
        print()

        # Check each position
        statuses = self.portfolio.check_all_positions()

        for status in statuses:
            icon = {
                ExitSignal.CRITICAL: "🔴",
                ExitSignal.WARNING: "🟠",
                ExitSignal.WATCH: "🟡",
                ExitSignal.TAKE_PROFIT: "🎯",
                ExitSignal.HOLD: "✅"
            }.get(status.signal, "⚪")

            print(f"{icon} {status.symbol}")
            print(f"   P&L: {status.pnl_pct:+.2f}% (${status.pnl_usd:+.2f})")
            print(f"   Days: {status.days_held} | Action: {status.action}")

            # Build sell order if needed
            if status.signal in [ExitSignal.CRITICAL, ExitSignal.WARNING, ExitSignal.TAKE_PROFIT]:
                order = {
                    'symbol': status.symbol,
                    'action': 'SELL',
                    'price': status.current_price,
                    'pnl_pct': status.pnl_pct,
                    'pnl_usd': status.pnl_usd,
                    'reason': status.action,
                    'urgency': status.signal.value,
                    'replacements': status.new_candidates
                }
                sell_orders.append(order)

            if status.new_candidates:
                print(f"   → Replace: {', '.join(status.new_candidates)}")
            print()

        return sell_orders

    def _find_opportunities(self) -> List[Dict]:
        """Find new buying opportunities"""
        buy_orders = []

        # Calculate available slots
        current_positions = len(self.portfolio.positions)
        available_slots = self.MAX_POSITIONS - current_positions

        if available_slots <= 0:
            print(f"Portfolio เต็มแล้ว ({current_positions}/{self.MAX_POSITIONS})")
            print("รอขายก่อนค่อยซื้อใหม่")
            return buy_orders

        print(f"Available slots: {available_slots}")
        print()

        # Load data and screen
        print("Loading market data...")
        self.screener.load_data()
        print(f"Loaded {len(self.screener.data_cache)} stocks")
        print()

        # Get existing positions to exclude
        existing = list(self.portfolio.positions.keys())

        # Get signals
        signals = self.screener.screen(top_n=10)
        signals = [s for s in signals if s.symbol not in existing]

        if not signals:
            print("ไม่มี Signal วันนี้")
            return buy_orders

        print(f"Found {len(signals)} signals (excluding existing positions)")
        print()

        # Build buy orders for top picks
        for i, signal in enumerate(signals[:available_slots], 1):
            shares = int(self.position_size / signal.entry_price)
            cost = shares * signal.entry_price

            order = {
                'rank': i,
                'symbol': signal.symbol,
                'action': 'BUY',
                'entry_price': signal.entry_price,
                'shares': shares,
                'cost': round(cost, 2),
                'stop_loss': signal.stop_loss,
                'take_profit': signal.take_profit,
                'max_loss': round(signal.max_loss, 2),
                'expected_gain': round(signal.expected_gain, 2),
                'risk_reward': signal.risk_reward,
                'score': signal.score,
                'reasons': signal.reasons
            }
            buy_orders.append(order)

            reasons_str = ', '.join(signal.reasons)
            print(f"{i}. {signal.symbol} (Score: {signal.score})")
            print(f"   BUY @ ${signal.entry_price:.2f} x {shares} shares = ${cost:,.2f}")
            print(f"   SL: ${signal.stop_loss:.2f} ({signal.max_loss:.1f}%)")
            print(f"   TP: ${signal.take_profit:.2f} (+{signal.expected_gain:.1f}%)")
            print(f"   R:R = {signal.risk_reward:.2f}")
            print(f"   Reasons: {reasons_str}")
            print()

        # Show more candidates
        if len(signals) > available_slots:
            print()
            print("📋 More candidates (backup):")
            for signal in signals[available_slots:available_slots+3]:
                print(f"   - {signal.symbol} (Score: {signal.score}) @ ${signal.entry_price:.2f}")

        return buy_orders

    def _print_action_plan(self, sell_orders: List[Dict], buy_orders: List[Dict]) -> None:
        """Print summary action plan"""

        # SELL orders
        if sell_orders:
            print("🔴 SELL ORDERS:")
            print("-" * 50)
            for order in sell_orders:
                urgency = order['urgency']
                icon = "🔴" if urgency == "CRITICAL" else "🟠" if urgency == "WARNING" else "🎯"
                print(f"  {icon} SELL {order['symbol']} @ ${order['price']:.2f}")
                print(f"     P&L: {order['pnl_pct']:+.2f}% | {order['reason']}")
                if order['replacements']:
                    print(f"     → Rotate to: {', '.join(order['replacements'])}")
            print()
        else:
            print("✅ No positions to sell")
            print()

        # BUY orders
        if buy_orders:
            print("🟢 BUY ORDERS:")
            print("-" * 50)
            for order in buy_orders:
                print(f"  📈 BUY {order['symbol']} @ ${order['entry_price']:.2f}")
                print(f"     Shares: {order['shares']} | Cost: ${order['cost']:,.2f}")
                print(f"     SL: ${order['stop_loss']:.2f} | TP: ${order['take_profit']:.2f}")
            print()
        else:
            print("📊 No new positions to add")
            print()

        # Total exposure
        print("=" * 50)
        current_value = sum(p.position_value for p in self.portfolio.positions.values())
        new_buys = sum(o['cost'] for o in buy_orders)
        sells = sum(self.portfolio.positions[o['symbol']].position_value
                   for o in sell_orders if o['symbol'] in self.portfolio.positions)

        print(f"Current Positions: ${current_value:,.2f}")
        print(f"Sells Today: ${sells:,.2f}")
        print(f"Buys Today: ${new_buys:,.2f}")
        print(f"Projected Positions: ${current_value - sells + new_buys:,.2f}")
        print()

        # Important reminders
        print("=" * 50)
        print("📌 IMPORTANT REMINDERS:")
        print("-" * 50)
        print("1. Stop Loss = ขายทันทีถ้าลงถึง SL")
        print("2. Take Profit = ขายเมื่อถึงเป้า")
        print("3. Time Stop = ถือไม่เกิน 7 วัน")
        print("4. Trail Stop = หลังขึ้น 3%+, trail ที่ 60%")
        print()
        print("⚠️  ถ้าหุ้นลงเกิน 1.5% = เตรียมขาย")
        print("🔴 ถ้าหุ้นลงเกิน 2.5% = ขายทันที!")
        print()

    def add_position_interactive(self, order: Dict) -> bool:
        """Add position from buy order"""
        try:
            self.portfolio.add_position(
                symbol=order['symbol'],
                shares=order['shares'],
                entry_price=order['entry_price'],
                stop_loss=order['stop_loss'],
                take_profit=order['take_profit']
            )
            return True
        except Exception as e:
            print(f"Error adding position: {e}")
            return False

    def remove_position_interactive(self, symbol: str) -> bool:
        """Remove position"""
        pos = self.portfolio.remove_position(symbol)
        if pos:
            print(f"Removed {symbol} from portfolio")
            return True
        return False


def main():
    """Run daily trading check"""
    import argparse

    parser = argparse.ArgumentParser(description='Daily Rapid Trader')
    parser.add_argument('--capital', type=float, default=100000,
                       help='Total capital (default: 100000)')
    parser.add_argument('--add', type=str,
                       help='Add position: SYMBOL,SHARES,PRICE,SL,TP')
    parser.add_argument('--remove', type=str,
                       help='Remove position: SYMBOL')
    args = parser.parse_args()

    trader = DailyRapidTrader(capital=args.capital)

    # Handle add/remove commands
    if args.add:
        parts = args.add.split(',')
        if len(parts) == 5:
            symbol, shares, price, sl, tp = parts
            trader.portfolio.add_position(
                symbol=symbol.upper(),
                shares=int(shares),
                entry_price=float(price),
                stop_loss=float(sl),
                take_profit=float(tp)
            )
            print(f"Added {symbol.upper()} to portfolio")
        else:
            print("Format: SYMBOL,SHARES,PRICE,SL,TP")
        return

    if args.remove:
        if trader.portfolio.remove_position(args.remove.upper()):
            print(f"Removed {args.remove.upper()}")
        else:
            print(f"Position not found: {args.remove}")
        return

    # Run daily check
    trader.run_daily_check()

    print("=" * 70)
    print("✅ DAILY CHECK COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
