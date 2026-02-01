#!/usr/bin/env python3
"""
ทดสอบ Exit Signals ด้วย Mock Data
เพื่อยืนยันว่าระบบทำงานถูกต้อง
"""

import sys
sys.path.append('src')

from portfolio_manager import PortfolioManager
from datetime import datetime, timedelta
import pandas as pd

def create_mock_price_data(entry_price, scenario):
    """สร้าง mock price data สำหรับทดสอบ"""
    dates = pd.date_range(start=datetime.now() - timedelta(days=15),
                         end=datetime.now(), freq='D')

    if scenario == 'profit':
        # Scenario: กำไร +5%
        prices = [entry_price * (1 + i*0.003) for i in range(len(dates))]
    elif scenario == 'loss':
        # Scenario: ขาดทุน -7%
        prices = [entry_price * (1 - i*0.005) for i in range(len(dates))]
    elif scenario == 'trailing':
        # Scenario: ขึ้น +8% แล้วลงมา -3% from peak
        prices = []
        for i in range(len(dates)):
            if i < 10:
                prices.append(entry_price * (1 + i*0.008))  # ขึ้น
            else:
                prices.append(prices[9] * 0.97)  # ลงจาก peak
    else:
        # Flat
        prices = [entry_price] * len(dates)

    return pd.DataFrame({
        'Close': prices,
        'High': [p * 1.01 for p in prices],
        'Low': [p * 0.99 for p in prices],
        'Volume': [1000000] * len(dates)
    }, index=dates)


def test_exit_scenarios():
    """ทดสอบ exit scenarios ต่างๆ"""

    print("=" * 80)
    print("🧪 ทดสอบ Exit Signals - Manual Testing")
    print("=" * 80)

    # Test positions
    test_cases = [
        {
            'symbol': 'PROFIT_TEST',
            'entry_price': 100.0,
            'scenario': 'profit',
            'expected': 'HOLD (กำไร +5% แต่ยังไม่ถึง trailing)'
        },
        {
            'symbol': 'LOSS_TEST',
            'entry_price': 100.0,
            'scenario': 'loss',
            'expected': 'EXIT (ขาดทุน -7% ถึง hard stop -6%)'
        },
        {
            'symbol': 'TRAILING_TEST',
            'entry_price': 100.0,
            'scenario': 'trailing',
            'expected': 'EXIT (ลงจาก peak -3% ถึง trailing stop)'
        },
        {
            'symbol': 'FLAT_TEST',
            'entry_price': 100.0,
            'scenario': 'flat',
            'expected': 'HOLD (ไม่ขึ้นไม่ลง รอต่อ)'
        }
    ]

    print("\n📊 Test Cases:")
    print()

    from advanced_exit_rules import AdvancedExitRules
    exit_rules = AdvancedExitRules()

    for i, test in enumerate(test_cases, 1):
        print(f"{i}. {test['symbol']}")
        print(f"   Entry: ${test['entry_price']:.2f}")
        print(f"   Scenario: {test['scenario']}")

        # Create mock data
        hist_data = create_mock_price_data(test['entry_price'], test['scenario'])
        spy_data = create_mock_price_data(500, 'profit')  # Mock SPY

        current_price = hist_data['Close'].iloc[-1]
        peak_price = hist_data['Close'].max()

        position = {
            'symbol': test['symbol'],
            'entry_price': test['entry_price'],
            'entry_date': (datetime.now() - timedelta(days=15)).isoformat(),
            'highest_price': peak_price,
            'days_held': 15
        }

        # Test exit
        should_exit, reason, exit_price = exit_rules.should_exit(
            position, datetime.now(), hist_data, spy_data
        )

        current_return = ((current_price - test['entry_price']) / test['entry_price']) * 100
        peak_return = ((peak_price - test['entry_price']) / test['entry_price']) * 100

        print(f"   Current: ${current_price:.2f} ({current_return:+.2f}%)")
        print(f"   Peak: ${peak_price:.2f} ({peak_return:+.2f}%)")

        if should_exit:
            print(f"   ❌ EXIT SIGNAL: {reason}")
        else:
            print(f"   ✅ HOLD")

        print(f"   Expected: {test['expected']}")
        print()

    print("=" * 80)
    print("✅ ทดสอบเสร็จสิ้น")
    print("=" * 80)
    print()
    print("💡 สรุป:")
    print("   - ถ้า Exit Signals ตรงตาม Expected = ระบบทำงานถูกต้อง!")
    print("   - ถ้าไม่ตรง = มีปัญหาที่ต้องแก้")
    print()


def check_real_positions():
    """เช็ค positions จริงใน portfolio"""
    print("=" * 80)
    print("📊 ตรวจสอบ Positions จริง")
    print("=" * 80)

    try:
        pm = PortfolioManager(use_advanced=True)

        if not pm.portfolio['active']:
            print("\n⚠️ ไม่มี active positions")
            return

        print(f"\nพบ {len(pm.portfolio['active'])} positions:")
        print()

        for pos in pm.portfolio['active']:
            print(f"📌 {pos['symbol']}")
            print(f"   Entry: ${pos['entry_price']:.2f} on {pos['entry_date']}")
            print(f"   Days Held: {pos.get('days_held', 0)}")

            # Try to get current price
            import yfinance as yf
            try:
                ticker = yf.Ticker(pos['symbol'])
                hist = ticker.history(period='1d')

                if not hist.empty:
                    current = float(hist['Close'].iloc[-1])
                    ret = ((current - pos['entry_price']) / pos['entry_price']) * 100
                    print(f"   Current: ${current:.2f} ({ret:+.2f}%)")
                else:
                    print(f"   ⚠️ ไม่มีข้อมูลราคาปัจจุบัน (market ปิด?)")
            except Exception as e:
                print(f"   ⚠️ Error: {e}")

            print()

    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    print("\n")

    # Test 1: Mock scenarios
    test_exit_scenarios()

    print("\n" + "="*80 + "\n")

    # Test 2: Real positions
    check_real_positions()

    print("\n")
