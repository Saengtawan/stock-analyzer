#!/usr/bin/env python3
"""
Test Manual Exit Portfolio Manager

ทดสอบระบบ Manual Exit ที่:
1. ไม่เอาหุ้นออกอัตโนมัติ
2. แค่เปลี่ยนสถานะเป็น "exit_signal"
3. ให้ผู้ใช้ตัดสินใจเอง
"""

import sys
import os
sys.path.append('src')

from portfolio_manager_manual_exit import PortfolioManagerManualExit
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")


def demo_manual_exit():
    """Demo การใช้งาน Manual Exit System"""

    print("=" * 80)
    print("🧪 TESTING MANUAL EXIT PORTFOLIO MANAGER")
    print("=" * 80)
    print()

    # สร้าง manager (ใช้ test file)
    test_file = 'portfolio_test_manual.json'

    # ลบ file เก่าถ้ามี
    if os.path.exists(test_file):
        os.remove(test_file)

    manager = PortfolioManagerManualExit(test_file)

    print("=" * 80)
    print("STEP 1: เพิ่มหุ้นเข้า Portfolio")
    print("=" * 80)
    print()

    # เพิ่มหุ้นตัวอย่าง (ใช้ราคาจริงจาก market)
    print("Adding test positions...")

    # ใช้หุ้นจริงที่มีโอกาสมี exit signal
    test_positions = [
        {'symbol': 'AAPL', 'entry_price': 230.0, 'amount': 1000, 'entry_date': '2025-12-15'},
        {'symbol': 'TSLA', 'entry_price': 420.0, 'amount': 1000, 'entry_date': '2025-12-20'},
        {'symbol': 'NVDA', 'entry_price': 950.0, 'amount': 1000, 'entry_date': '2025-12-25'},
    ]

    for pos in test_positions:
        manager.add_position(
            symbol=pos['symbol'],
            entry_price=pos['entry_price'],
            amount=pos['amount'],
            entry_date=pos['entry_date']
        )

    print()
    print("=" * 80)
    print("STEP 2: Monitor Positions (ตรวจหา Exit Signals)")
    print("=" * 80)
    print()

    # Monitor ครั้งแรก
    summary = manager.monitor_positions(update_signals=True)

    print()
    print("=" * 80)
    print("STEP 3: แสดง Exit Signals (ถ้ามี)")
    print("=" * 80)
    print()

    if summary['exit_signals_new'] > 0 or summary['exit_signals_existing'] > 0:
        exit_signals = manager.list_exit_signals()

        if exit_signals:
            print()
            print("=" * 80)
            print("STEP 4: ตัวอย่างการตัดสินใจ")
            print("=" * 80)
            print()

            # ตัวอย่าง: ออกตัวแรก, clear ตัวที่สอง
            if len(exit_signals) >= 1:
                first_symbol = exit_signals[0]['symbol']

                print(f"📍 ตัดสินใจ {first_symbol}:")
                print(f"   Exit Signal: {exit_signals[0]['exit_signal']['rule']}")
                print(f"   PnL: {exit_signals[0]['exit_signal']['pnl_pct_at_signal']:+.2f}%")

                user_decision = input(f"\n   ต้องการออกจาก {first_symbol} ไหม? (y/n): ").strip().lower()

                if user_decision == 'y':
                    print(f"\n   ✅ ออกจาก {first_symbol}")
                    manager.manual_exit(first_symbol)
                else:
                    print(f"\n   🔄 Clear exit signal และถือต่อ")
                    manager.clear_exit_signal(first_symbol)

            if len(exit_signals) >= 2:
                second_symbol = exit_signals[1]['symbol']

                print()
                print(f"📍 ตัดสินใจ {second_symbol}:")
                print(f"   Exit Signal: {exit_signals[1]['exit_signal']['rule']}")
                print(f"   PnL: {exit_signals[1]['exit_signal']['pnl_pct_at_signal']:+.2f}%")

                user_decision = input(f"\n   ต้องการออกจาก {second_symbol} ไหม? (y/n): ").strip().lower()

                if user_decision == 'y':
                    print(f"\n   ✅ ออกจาก {second_symbol}")
                    manager.manual_exit(second_symbol)
                else:
                    print(f"\n   🔄 Clear exit signal และถือต่อ")
                    manager.clear_exit_signal(second_symbol)

    else:
        print("✅ ไม่มี exit signals - หุ้นทั้งหมดยัง active")

    print()
    print("=" * 80)
    print("STEP 5: Portfolio Summary")
    print("=" * 80)
    print()

    manager.show_portfolio()

    print()
    print("=" * 80)
    print("🎯 TEST COMPLETE")
    print("=" * 80)
    print()
    print("💡 Key Learnings:")
    print("   1. หุ้นไม่ถูกเอาออกอัตโนมัติ")
    print("   2. มี exit signal → status เปลี่ยนเป็น 'exit_signal'")
    print("   3. คุณเลือกได้: manual_exit() หรือ clear_exit_signal()")
    print("   4. ยืดหยุ่น แต่ยังมี system คอยเตือน")
    print()
    print(f"Test file: {test_file}")
    print("=" * 80)


def demo_workflow():
    """Demo workflow ประจำวัน"""

    print()
    print("=" * 80)
    print("📅 DAILY WORKFLOW EXAMPLE")
    print("=" * 80)
    print()

    test_file = 'portfolio_test_manual.json'

    if not os.path.exists(test_file):
        print("⚠️  Run demo_manual_exit() first to create test portfolio")
        return

    manager = PortfolioManagerManualExit(test_file)

    print("Morning routine:")
    print()
    print("1. Monitor positions")

    summary = manager.monitor_positions(update_signals=True)

    if summary['exit_signals_new'] > 0:
        print()
        print("2. Review exit signals")
        manager.list_exit_signals()

        print()
        print("3. Make decisions:")
        print("   - manual_exit('SYMBOL') → exit position")
        print("   - clear_exit_signal('SYMBOL') → ignore signal and hold")

    print()
    print("4. Check portfolio summary")
    manager.show_portfolio()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'workflow':
        demo_workflow()
    else:
        demo_manual_exit()
